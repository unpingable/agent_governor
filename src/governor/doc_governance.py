# SPDX-License-Identifier: Apache-2.0
"""
Document Governance — Docs as Governed Artifacts.

Docs make claims. Claims without grounding rot. This module extends
the governor's evidence discipline to documentation: docs declare scope,
link to live systems, and decay when their assumptions drift.

Spec: DOC_GOVERNANCE_SPEC.md (Layer 4, Item #10 of AG2 build order)

Core principle: Docs don't become trustworthy because they're well-written.
They become trustworthy because they can't say things the system won't back.

What the governor does: Constrain what docs claim, track staleness, surface
authority violations.
What the governor does NOT do: Write docs, enforce style, generate content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DocScope(str, Enum):
    """What a doc is allowed to claim."""
    DESCRIPTIVE = "descriptive"       # "What exists" — no authority claims
    PROCEDURAL = "procedural"         # "How to do X" — linked to execution
    AUTHORITATIVE = "authoritative"   # "You must / must not" — requires evidence


class DocStatus(str, Enum):
    """Current governance status of a document."""
    CURRENT = "current"       # Verified within TTL, links valid
    STALE = "stale"           # TTL expired or linked artifacts changed
    HISTORICAL = "historical" # Explicitly demoted, kept for reference
    UNSAFE = "unsafe"         # Authoritative doc with broken links or dropped commitments


class LinkKind(str, Enum):
    """Type of connection between a doc and a live artifact."""
    CODE = "code"          # Source file or directory
    SCRIPT = "script"      # Executable automation
    TEST = "test"          # Test file or command
    PANEL = "panel"        # Dashboard / monitoring panel
    DECISION = "decision"  # Decision ledger entry
    ANCHOR = "anchor"      # Continuity anchor
    RUNBOOK = "runbook"    # Another governed doc


class CheckSeverity(str, Enum):
    """Severity of a governance finding."""
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DocLink:
    """Connection between a doc and a live artifact."""
    kind: LinkKind
    target: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "target": self.target,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DocLink:
        return cls(
            kind=LinkKind(d["kind"]),
            target=d["target"],
            description=d.get("description", ""),
        )

    def exists(self) -> bool:
        """Check if the link target exists on disk."""
        if self.kind in (LinkKind.CODE, LinkKind.SCRIPT, LinkKind.TEST, LinkKind.RUNBOOK):
            return Path(self.target).exists()
        # Non-filesystem links (panels, decisions, anchors) can't be checked here
        return True


@dataclass
class GovDoc:
    """A governed document artifact."""
    doc_id: str
    path: str
    scope: DocScope
    links: list[DocLink] = field(default_factory=list)
    ttl_days: int | None = None
    registered_at: str = ""
    last_verified: str = ""
    status: DocStatus = DocStatus.CURRENT
    content_hash: str = ""

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = datetime.now(timezone.utc).isoformat()
        if not self.last_verified:
            self.last_verified = self.registered_at
        if not self.doc_id:
            self.doc_id = hashlib.sha256(self.path.encode()).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "path": self.path,
            "scope": self.scope.value,
            "links": [l.to_dict() for l in self.links],
            "ttl_days": self.ttl_days,
            "registered_at": self.registered_at,
            "last_verified": self.last_verified,
            "status": self.status.value,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GovDoc:
        return cls(
            doc_id=d["doc_id"],
            path=d["path"],
            scope=DocScope(d["scope"]),
            links=[DocLink.from_dict(l) for l in d.get("links", [])],
            ttl_days=d.get("ttl_days"),
            registered_at=d.get("registered_at", ""),
            last_verified=d.get("last_verified", ""),
            status=DocStatus(d.get("status", "current")),
            content_hash=d.get("content_hash", ""),
        )

    @property
    def ttl(self) -> timedelta | None:
        """TTL as timedelta."""
        return timedelta(days=self.ttl_days) if self.ttl_days else None

    def is_ttl_expired(self) -> bool:
        """Check if the doc's TTL has expired since last verification."""
        if self.ttl_days is None:
            return False
        try:
            last = datetime.fromisoformat(self.last_verified)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = datetime.now(timezone.utc) - last
            return elapsed > timedelta(days=self.ttl_days)
        except (ValueError, TypeError):
            return False

    def compute_content_hash(self) -> str:
        """Compute SHA-256 hash of the doc's current content."""
        p = Path(self.path)
        if p.exists():
            return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        return ""


# ---------------------------------------------------------------------------
# Authority language detection
# ---------------------------------------------------------------------------

AUTHORITY_PATTERNS = [
    re.compile(r'\bMUST\b'),
    re.compile(r'\bMUST\s+NOT\b'),
    re.compile(r'\bSHALL\b'),
    re.compile(r'\bSHALL\s+NOT\b'),
    re.compile(r'\bNEVER\b'),
    re.compile(r'\bREQUIRED\b'),
    re.compile(r'\bMANDATORY\b'),
    re.compile(r'\bFORBIDDEN\b'),
]

# Don't match inside code blocks or YAML frontmatter
CODE_BLOCK_RE = re.compile(r'```.*?```', re.DOTALL)
FRONTMATTER_RE = re.compile(r'^---\n.*?\n---\n', re.DOTALL)


@dataclass
class AuthorityClaim:
    """An authority claim found in a document."""
    line_number: int
    text: str
    pattern: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "text": self.text,
            "pattern": self.pattern,
        }


def extract_authority_claims(content: str) -> list[AuthorityClaim]:
    """Extract authority language (MUST/SHALL/NEVER/etc.) from doc content.

    Skips code blocks and YAML frontmatter.
    """
    # Strip code blocks and frontmatter
    stripped = FRONTMATTER_RE.sub("", content)
    stripped = CODE_BLOCK_RE.sub("", stripped)

    claims: list[AuthorityClaim] = []
    for i, line in enumerate(stripped.split("\n"), 1):
        for pat in AUTHORITY_PATTERNS:
            if pat.search(line):
                claims.append(AuthorityClaim(
                    line_number=i,
                    text=line.strip(),
                    pattern=pat.pattern,
                ))
                break  # One match per line is enough
    return claims


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

@dataclass
class DocFinding:
    """A governance finding about a document."""
    severity: CheckSeverity
    category: str  # "authority", "adjacency", "staleness", "link"
    message: str
    line_number: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
        }
        if self.line_number is not None:
            d["line_number"] = self.line_number
        if self.details:
            d["details"] = self.details
        return d


@dataclass
class DocCheckResult:
    """Result of checking a governed document."""
    doc_id: str
    path: str
    scope: str
    status: str
    findings: list[DocFinding] = field(default_factory=list)
    authority_claims: int = 0
    grounded_claims: int = 0
    ungrounded_claims: int = 0
    links_valid: int = 0
    links_broken: int = 0
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "path": self.path,
            "scope": self.scope,
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "authority_claims": self.authority_claims,
            "grounded_claims": self.grounded_claims,
            "ungrounded_claims": self.ungrounded_claims,
            "links_valid": self.links_valid,
            "links_broken": self.links_broken,
            "passed": self.passed,
        }


def check_authority(doc: GovDoc, content: str) -> list[DocFinding]:
    """Check authority language against doc scope."""
    findings: list[DocFinding] = []
    claims = extract_authority_claims(content)

    if not claims:
        return findings

    if doc.scope != DocScope.AUTHORITATIVE:
        for c in claims:
            findings.append(DocFinding(
                severity=CheckSeverity.WARN,
                category="authority",
                message=(
                    f"Authority language in {doc.scope.value} doc: "
                    f"\"{c.text[:80]}{'...' if len(c.text) > 80 else ''}\""
                ),
                line_number=c.line_number,
                details={"pattern": c.pattern},
            ))

    return findings


def check_adjacency(doc: GovDoc) -> list[DocFinding]:
    """Check execution adjacency requirements."""
    findings: list[DocFinding] = []

    if doc.scope == DocScope.PROCEDURAL:
        exec_links = [l for l in doc.links
                       if l.kind in (LinkKind.CODE, LinkKind.SCRIPT, LinkKind.TEST)]
        if not exec_links:
            findings.append(DocFinding(
                severity=CheckSeverity.ERROR,
                category="adjacency",
                message="Procedural doc must link to at least one CODE, SCRIPT, or TEST artifact",
            ))

    elif doc.scope == DocScope.AUTHORITATIVE:
        auth_links = [l for l in doc.links
                       if l.kind in (LinkKind.DECISION, LinkKind.ANCHOR)]
        if not auth_links:
            findings.append(DocFinding(
                severity=CheckSeverity.ERROR,
                category="adjacency",
                message="Authoritative doc must link to at least one DECISION or ANCHOR",
            ))

    return findings


def check_links(doc: GovDoc) -> tuple[int, int, list[DocFinding]]:
    """Check that all doc links point to valid targets.

    Returns (valid_count, broken_count, findings).
    """
    valid = 0
    broken = 0
    findings: list[DocFinding] = []

    for link in doc.links:
        if link.exists():
            valid += 1
        else:
            broken += 1
            findings.append(DocFinding(
                severity=CheckSeverity.ERROR,
                category="link",
                message=f"Broken link: {link.kind.value}:{link.target}",
                details={"kind": link.kind.value, "target": link.target},
            ))

    return valid, broken, findings


def check_staleness(doc: GovDoc) -> list[DocFinding]:
    """Check if a doc's TTL has expired."""
    findings: list[DocFinding] = []

    if doc.is_ttl_expired():
        findings.append(DocFinding(
            severity=CheckSeverity.WARN,
            category="staleness",
            message=f"Doc TTL expired (last verified: {doc.last_verified}, TTL: {doc.ttl_days}d)",
            details={
                "last_verified": doc.last_verified,
                "ttl_days": doc.ttl_days,
            },
        ))

    # Check if content has changed since last verification
    if doc.content_hash:
        current_hash = doc.compute_content_hash()
        if current_hash and current_hash != doc.content_hash:
            findings.append(DocFinding(
                severity=CheckSeverity.INFO,
                category="staleness",
                message="Document content changed since last verification",
                details={
                    "stored_hash": doc.content_hash,
                    "current_hash": current_hash,
                },
            ))

    return findings


def check_doc(doc: GovDoc, content: str | None = None) -> DocCheckResult:
    """Run all governance checks on a document.

    Args:
        doc: The governed document
        content: Document content (read from disk if not provided)

    Returns:
        DocCheckResult with findings and counts
    """
    if content is None:
        p = Path(doc.path)
        content = p.read_text() if p.exists() else ""

    all_findings: list[DocFinding] = []

    # Authority check
    auth_findings = check_authority(doc, content)
    all_findings.extend(auth_findings)

    # Count authority claims
    auth_claims = extract_authority_claims(content)
    authority_count = len(auth_claims)
    # For now, grounded = those in authoritative scope, ungrounded = those outside
    grounded = authority_count if doc.scope == DocScope.AUTHORITATIVE else 0
    ungrounded = authority_count - grounded

    # Adjacency check
    adj_findings = check_adjacency(doc)
    all_findings.extend(adj_findings)

    # Link check
    valid, broken, link_findings = check_links(doc)
    all_findings.extend(link_findings)

    # Staleness check
    stale_findings = check_staleness(doc)
    all_findings.extend(stale_findings)

    # Determine status
    has_errors = any(f.severity == CheckSeverity.ERROR for f in all_findings)
    is_stale = any(f.category == "staleness" and f.severity == CheckSeverity.WARN
                    for f in all_findings)

    status = doc.status
    if has_errors and doc.scope == DocScope.AUTHORITATIVE:
        status = DocStatus.UNSAFE
    elif is_stale:
        status = DocStatus.STALE

    return DocCheckResult(
        doc_id=doc.doc_id,
        path=doc.path,
        scope=doc.scope.value,
        status=status.value,
        findings=all_findings,
        authority_claims=authority_count,
        grounded_claims=grounded,
        ungrounded_claims=ungrounded,
        links_valid=valid,
        links_broken=broken,
        passed=not has_errors,
    )


# ---------------------------------------------------------------------------
# DocReceipt — verification receipt
# ---------------------------------------------------------------------------

@dataclass
class DocReceipt:
    """Verification receipt for a governed document."""
    doc_id: str
    verified_at: str
    status: str
    commitments_extracted: int
    links_valid: int
    links_broken: int
    authority_claims: int
    grounded_claims: int
    ungrounded_claims: int
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "verified_at": self.verified_at,
            "status": self.status,
            "commitments_extracted": self.commitments_extracted,
            "links_valid": self.links_valid,
            "links_broken": self.links_broken,
            "authority_claims": self.authority_claims,
            "grounded_claims": self.grounded_claims,
            "ungrounded_claims": self.ungrounded_claims,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_check_result(cls, result: DocCheckResult, content_hash: str) -> DocReceipt:
        return cls(
            doc_id=result.doc_id,
            verified_at=datetime.now(timezone.utc).isoformat(),
            status=result.status,
            commitments_extracted=result.authority_claims,
            links_valid=result.links_valid,
            links_broken=result.links_broken,
            authority_claims=result.authority_claims,
            grounded_claims=result.grounded_claims,
            ungrounded_claims=result.ungrounded_claims,
            content_hash=content_hash,
        )


# ---------------------------------------------------------------------------
# StalenessReport
# ---------------------------------------------------------------------------

@dataclass
class StalenessReport:
    """Staleness assessment for all governed docs."""
    total: int = 0
    current: int = 0
    stale: int = 0
    historical: int = 0
    unsafe: int = 0
    docs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "current": self.current,
            "stale": self.stale,
            "historical": self.historical,
            "unsafe": self.unsafe,
            "docs": self.docs,
        }


# ---------------------------------------------------------------------------
# DocStore — persistence
# ---------------------------------------------------------------------------

class DocStore:
    """Persistent store for governed documents.

    On-disk layout:
        .governor/docs/
            registry.json          # All registered docs
            receipts/<doc_id>.json # Verification receipts
    """

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.docs_dir = self.governor_dir / "docs"
        self.registry_path = self.docs_dir / "registry.json"
        self.receipts_dir = self.docs_dir / "receipts"

    def _ensure_dirs(self) -> None:
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> dict[str, dict[str, Any]]:
        if not self.registry_path.exists():
            return {}
        try:
            return json.loads(self.registry_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_registry(self, registry: dict[str, dict[str, Any]]) -> None:
        self._ensure_dirs()
        self.registry_path.write_text(json.dumps(registry, indent=2) + "\n")

    def register(self, doc: GovDoc) -> GovDoc:
        """Register a document for governance."""
        # Compute content hash
        doc.content_hash = doc.compute_content_hash()

        registry = self._load_registry()
        registry[doc.doc_id] = doc.to_dict()
        self._save_registry(registry)
        return doc

    def unregister(self, doc_id: str) -> bool:
        """Remove a document from governance."""
        registry = self._load_registry()
        if doc_id not in registry:
            return False
        del registry[doc_id]
        self._save_registry(registry)
        return True

    def get(self, doc_id: str) -> GovDoc | None:
        """Get a governed document by ID."""
        registry = self._load_registry()
        d = registry.get(doc_id)
        if d:
            return GovDoc.from_dict(d)
        return None

    def get_by_path(self, path: str) -> GovDoc | None:
        """Get a governed document by file path."""
        registry = self._load_registry()
        for d in registry.values():
            if d["path"] == path:
                return GovDoc.from_dict(d)
        return None

    def list_docs(self) -> list[GovDoc]:
        """List all governed documents."""
        registry = self._load_registry()
        return [GovDoc.from_dict(d) for d in registry.values()]

    def update(self, doc: GovDoc) -> None:
        """Update a document's record."""
        registry = self._load_registry()
        registry[doc.doc_id] = doc.to_dict()
        self._save_registry(registry)

    def save_receipt(self, receipt: DocReceipt) -> Path:
        """Save a verification receipt."""
        self._ensure_dirs()
        path = self.receipts_dir / f"{receipt.doc_id}.json"
        path.write_text(json.dumps(receipt.to_dict(), indent=2) + "\n")
        return path

    def load_receipt(self, doc_id: str) -> DocReceipt | None:
        """Load the latest verification receipt for a doc."""
        path = self.receipts_dir / f"{doc_id}.json"
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text())
            return DocReceipt(**d)
        except (json.JSONDecodeError, TypeError):
            return None

    def staleness_report(self) -> StalenessReport:
        """Generate a staleness report for all governed docs."""
        docs = self.list_docs()
        report = StalenessReport(total=len(docs))

        for doc in docs:
            result = check_doc(doc)
            status = DocStatus(result.status)

            if status == DocStatus.CURRENT:
                report.current += 1
            elif status == DocStatus.STALE:
                report.stale += 1
            elif status == DocStatus.HISTORICAL:
                report.historical += 1
            elif status == DocStatus.UNSAFE:
                report.unsafe += 1

            report.docs.append({
                "doc_id": doc.doc_id,
                "path": doc.path,
                "scope": doc.scope.value,
                "status": status.value,
                "finding_count": len(result.findings),
            })

        return report


# ---------------------------------------------------------------------------
# Export — frontmatter injection, JSON sidecar
# ---------------------------------------------------------------------------

@dataclass
class ExportConfig:
    """Configuration for doc export."""
    format: str = "obsidian"  # "obsidian" | "json"
    output_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"format": self.format, "output_dir": self.output_dir}


def generate_frontmatter(doc: GovDoc) -> str:
    """Generate YAML frontmatter for Obsidian/Logseq export."""
    lines = ["---"]
    lines.append(f"gov_scope: {doc.scope.value}")
    lines.append(f"gov_status: {doc.status.value}")
    lines.append(f"gov_verified: {doc.last_verified[:10] if doc.last_verified else 'never'}")
    if doc.ttl_days:
        lines.append(f"gov_ttl: {doc.ttl_days}d")
    if doc.links:
        lines.append("gov_links:")
        for link in doc.links:
            lines.append(f"  - {link.kind.value}: {link.target}")
    if doc.content_hash:
        lines.append(f"gov_hash: {doc.content_hash}")
    lines.append("---")
    return "\n".join(lines)


def generate_sidecar(doc: GovDoc) -> dict[str, Any]:
    """Generate JSON sidecar for static site generators."""
    return {
        "doc_id": doc.doc_id,
        "scope": doc.scope.value,
        "status": doc.status.value,
        "verified": doc.last_verified,
        "ttl_days": doc.ttl_days,
        "links": [l.to_dict() for l in doc.links],
        "content_hash": doc.content_hash,
    }


# ---------------------------------------------------------------------------
# DocGovernor — top-level facade
# ---------------------------------------------------------------------------

class DocGovernor:
    """Top-level facade for document governance.

    Orchestrates registration, checking, verification, and export.
    """

    def __init__(self, governor_dir: Path | None = None):
        self.store = DocStore(governor_dir)

    def register(
        self,
        path: str,
        scope: DocScope | str,
        links: list[DocLink] | None = None,
        ttl_days: int | None = None,
    ) -> GovDoc:
        """Register a document for governance."""
        if isinstance(scope, str):
            scope = DocScope(scope)

        doc = GovDoc(
            doc_id="",
            path=path,
            scope=scope,
            links=links or [],
            ttl_days=ttl_days,
        )
        return self.store.register(doc)

    def unregister(self, path: str) -> bool:
        """Unregister a document."""
        doc = self.store.get_by_path(path)
        if doc:
            return self.store.unregister(doc.doc_id)
        return False

    def check(self, path: str) -> DocCheckResult:
        """Check a registered document."""
        doc = self.store.get_by_path(path)
        if not doc:
            return DocCheckResult(
                doc_id="",
                path=path,
                scope="unregistered",
                status="unregistered",
                findings=[DocFinding(
                    severity=CheckSeverity.ERROR,
                    category="registration",
                    message=f"Document not registered: {path}",
                )],
                passed=False,
            )
        return check_doc(doc)

    def check_all(self) -> list[DocCheckResult]:
        """Check all registered documents."""
        results = []
        for doc in self.store.list_docs():
            results.append(check_doc(doc))
        return results

    def verify(self, path: str) -> DocReceipt | None:
        """Verify a document and produce a receipt.

        Resets TTL and updates status.
        """
        doc = self.store.get_by_path(path)
        if not doc:
            return None

        result = check_doc(doc)
        content_hash = doc.compute_content_hash()

        # Update doc
        doc.last_verified = datetime.now(timezone.utc).isoformat()
        doc.content_hash = content_hash
        doc.status = DocStatus(result.status) if result.passed else doc.status
        if result.passed:
            doc.status = DocStatus.CURRENT
        self.store.update(doc)

        receipt = DocReceipt.from_check_result(result, content_hash)
        self.store.save_receipt(receipt)
        return receipt

    def demote(self, path: str) -> bool:
        """Demote a document to HISTORICAL."""
        doc = self.store.get_by_path(path)
        if not doc:
            return False
        doc.status = DocStatus.HISTORICAL
        self.store.update(doc)
        return True

    def promote(self, path: str) -> DocCheckResult | None:
        """Promote a HISTORICAL doc back to CURRENT (requires re-check)."""
        doc = self.store.get_by_path(path)
        if not doc:
            return None

        result = check_doc(doc)
        if result.passed:
            doc.status = DocStatus.CURRENT
            doc.last_verified = datetime.now(timezone.utc).isoformat()
            doc.content_hash = doc.compute_content_hash()
            self.store.update(doc)
        return result

    def status(self) -> StalenessReport:
        """Get staleness report for all docs."""
        return self.store.staleness_report()

    def stale_docs(self) -> list[GovDoc]:
        """List stale and unsafe documents."""
        docs = self.store.list_docs()
        stale = []
        for doc in docs:
            result = check_doc(doc)
            if DocStatus(result.status) in (DocStatus.STALE, DocStatus.UNSAFE):
                stale.append(doc)
        return stale

    def export_doc(self, path: str, fmt: str = "obsidian") -> str:
        """Export governance metadata for a document.

        Args:
            path: Document path
            fmt: "obsidian" (YAML frontmatter) or "json" (sidecar)

        Returns:
            Exported content as string
        """
        doc = self.store.get_by_path(path)
        if not doc:
            return ""

        if fmt == "json":
            return json.dumps(generate_sidecar(doc), indent=2)
        else:
            return generate_frontmatter(doc)

    def list_docs(self) -> list[GovDoc]:
        """List all governed documents."""
        return self.store.list_docs()


# ---------------------------------------------------------------------------
# Telemetry event
# ---------------------------------------------------------------------------

def make_doc_event(result: DocCheckResult) -> dict[str, Any]:
    """Create a telemetry event from a doc check result."""
    return {
        "type": "doc_governance_check",
        "doc_id": result.doc_id,
        "path": result.path,
        "scope": result.scope,
        "status": result.status,
        "findings": len(result.findings),
        "authority_claims": result.authority_claims,
        "grounded_claims": result.grounded_claims,
        "ungrounded_claims": result.ungrounded_claims,
        "links_valid": result.links_valid,
        "links_broken": result.links_broken,
        "passed": result.passed,
    }
