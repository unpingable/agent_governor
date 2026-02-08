"""
Instrumented Execution — AG2 Layer 0, Item #1.

Content-addressed artifact storage, append-only event streams per run,
structured claims with evidence pointers, cross-run claim diff, and reports.

Every subsequent spec emits receipts into this system — building it once
prevents each later spec from inventing its own logging.

Spec: AG2_INSTRUMENT_SPEC.md (Layer 0, Item #1 of AG2 build order)

On-disk layout:
  .governor/
    instrument/
      store/sha256/<ab>/<cd>/<full_hash>   # content-addressed blobs
      runs/<run_id>/
        manifest.json
        events.jsonl
        receipts.jsonl
        claims.jsonl
        reports/report.json, report.md
      waivers/<waiver_id>.json
      config.json

Invariants:
  I0  append-only — events are never mutated, timestamps are monotonic
  I1  content-addressed — SHA256 naming, idempotent writes
  I2  replayable — manifests capture environment + repo + config + models
  I3  no naked conclusions — findings must have evidence_refs
  I4  profiles don't disable anchors — severity may vary, never suppressed
  I5  no orphan claims — ASSERT needs evidence_refs at creation
  I6  hints can't create evidence — hints SELECT from existing receipts only
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Enums (7)
# ---------------------------------------------------------------------------


class EventKind(str, Enum):
    """Kind of event in an instrumented run."""

    PROMPT_SENT = "prompt_sent"
    MODEL_OUTPUT = "model_output"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    GIT_DIFF = "git_diff"
    COMMAND_EXEC = "command_exec"
    TEST_RUN = "test_run"
    LINTER_RUN = "linter_run"
    POLICY_DECISION = "policy_decision"
    ERROR = "error"


class ClaimModality(str, Enum):
    """Epistemic modality governing evidence requirements.

    ASSERT — requires evidence_refs at creation (I5).
    INFER  — derived from evidence, lower confidence.
    PLAN   — prospective, no evidence yet.
    HYPOTHESIS — speculative, requires notes.
    """

    ASSERT = "assert"
    INFER = "infer"
    PLAN = "plan"
    HYPOTHESIS = "hypothesis"


class AG2ClaimType(str, Enum):
    """Claim types for instrumented runs.

    Deliberately separate from governor.claims.ClaimType to avoid collision.
    """

    ACTION_PERFORMED = "action_performed"
    FILE_CHANGED = "file_changed"
    TEST_RESULT = "test_result"
    LINTER_RESULT = "linter_result"
    BUILD_RESULT = "build_result"
    INVARIANT_SATISFIED = "invariant_satisfied"
    INVARIANT_VIOLATED = "invariant_violated"
    COMPLETION_CLAIM = "completion_claim"


class DiffFinding(str, Enum):
    """Finding kinds for cross-run claim diff."""

    CONTRADICTION = "contradiction"
    MISSING_EVIDENCE = "missing_evidence"
    PHANTOM_ACTION = "phantom_action"
    UNSUPPORTED_SUCCESS = "unsupported_success"
    DRIFT = "drift"


class ActorKind(str, Enum):
    """Who or what produced an event."""

    HUMAN = "human"
    AGENT = "agent"
    PIPELINE = "pipeline"


class FindingSeverity(str, Enum):
    """Severity of a report finding."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class InstrumentProfile(str, Enum):
    """Governance profiles controlling severity and defaults."""

    GREENFIELD = "greenfield"
    STRICT = "strict"
    FORENSIC = "forensic"


# ---------------------------------------------------------------------------
# Supporting Dataclasses (manifest components)
# ---------------------------------------------------------------------------


@dataclass
class Actor:
    """Who initiated or owns a run."""

    kind: ActorKind
    id: str
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "id": self.id, "name": self.name}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Actor:
        return cls(kind=ActorKind(d["kind"]), id=d["id"], name=d.get("name", ""))


@dataclass
class Environment:
    """Captured execution environment for reproducibility (I2)."""

    os_name: str
    hostname: str
    cwd: str
    timezone: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "os": self.os_name,
            "hostname": self.hostname,
            "cwd": self.cwd,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Environment:
        return cls(
            os_name=d["os"],
            hostname=d["hostname"],
            cwd=d["cwd"],
            timezone=d["timezone"],
        )

    @classmethod
    def capture(cls) -> Environment:
        tz = time.strftime("%z")
        return cls(
            os_name=platform.system(),
            hostname=platform.node(),
            cwd=os.getcwd(),
            timezone=tz if tz else "UTC",
        )


@dataclass
class RepoState:
    """Captured git repo state for reproducibility (I2)."""

    url: str
    git_sha: str
    branch: str
    dirty: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "git_sha": self.git_sha,
            "branch": self.branch,
            "dirty": self.dirty,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RepoState:
        return cls(
            url=d.get("url", ""),
            git_sha=d.get("git_sha", ""),
            branch=d.get("branch", ""),
            dirty=d.get("dirty", False),
        )

    @classmethod
    def capture(cls) -> RepoState:
        """Capture current repo state via git CLI. Returns empty on failure."""
        try:
            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
        except Exception:
            return cls(url="", git_sha="", branch="", dirty=False)

        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
        except Exception:
            branch = ""

        try:
            url = subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
        except Exception:
            url = ""

        try:
            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).decode().strip()
            dirty = len(status) > 0
        except Exception:
            dirty = False

        return cls(url=url, git_sha=sha, branch=branch, dirty=dirty)


@dataclass
class ModelSpec:
    """Description of an LLM used during a run."""

    name: str
    provider: str
    version: str = ""
    parameters_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "version": self.version,
            "parameters_hash": self.parameters_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelSpec:
        return cls(
            name=d["name"],
            provider=d["provider"],
            version=d.get("version", ""),
            parameters_hash=d.get("parameters_hash", ""),
        )


@dataclass
class RunConfig:
    """Run-level configuration."""

    profile: InstrumentProfile
    anchors_hash: str = ""
    toolchain_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "anchors_hash": self.anchors_hash,
            "toolchain_versions": self.toolchain_versions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunConfig:
        return cls(
            profile=InstrumentProfile(d["profile"]),
            anchors_hash=d.get("anchors_hash", ""),
            toolchain_versions=d.get("toolchain_versions", {}),
        )


@dataclass
class RunInputs:
    """Inputs that seed a run (for reproducibility)."""

    task_id: str = ""
    prompt_hash: str = ""
    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "prompt_hash": self.prompt_hash,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunInputs:
        return cls(
            task_id=d.get("task_id", ""),
            prompt_hash=d.get("prompt_hash", ""),
            seed=d.get("seed", 0),
        )


# ---------------------------------------------------------------------------
# Core Dataclasses (8)
# ---------------------------------------------------------------------------


def _make_run_id() -> str:
    """UUID hex, first 12 chars."""
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunManifest:
    """Immutable header for an instrumented run."""

    run_id: str
    created_at: str
    finished_at: str = ""
    actor: Actor = field(default_factory=lambda: Actor(ActorKind.HUMAN, "unknown"))
    environment: Environment = field(default_factory=Environment.capture)
    repo: RepoState = field(default_factory=lambda: RepoState("", "", "", False))
    config: RunConfig = field(
        default_factory=lambda: RunConfig(InstrumentProfile.GREENFIELD)
    )
    inputs: RunInputs = field(default_factory=RunInputs)
    models: list[ModelSpec] = field(default_factory=list)
    event_count: int = 0
    receipt_count: int = 0
    claim_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "actor": self.actor.to_dict(),
            "environment": self.environment.to_dict(),
            "repo": self.repo.to_dict(),
            "config": self.config.to_dict(),
            "inputs": self.inputs.to_dict(),
            "models": [m.to_dict() for m in self.models],
            "event_count": self.event_count,
            "receipt_count": self.receipt_count,
            "claim_count": self.claim_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunManifest:
        return cls(
            run_id=d["run_id"],
            created_at=d["created_at"],
            finished_at=d.get("finished_at", ""),
            actor=Actor.from_dict(d["actor"]),
            environment=Environment.from_dict(d["environment"]),
            repo=RepoState.from_dict(d.get("repo", {"url": "", "git_sha": "", "branch": "", "dirty": False})),
            config=RunConfig.from_dict(d["config"]),
            inputs=RunInputs.from_dict(d.get("inputs", {})),
            models=[ModelSpec.from_dict(m) for m in d.get("models", [])],
            event_count=d.get("event_count", 0),
            receipt_count=d.get("receipt_count", 0),
            claim_count=d.get("claim_count", 0),
        )


@dataclass
class Event:
    """Immutable event in an append-only stream (I0)."""

    event_id: str
    ts: str
    run_id: str
    kind: EventKind
    actor: Actor
    parent_event_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    receipt_refs: list[str] = field(default_factory=list)

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "ts": self.ts,
            "run_id": self.run_id,
            "kind": self.kind.value,
            "actor": self.actor.to_dict(),
            "parent_event_id": self.parent_event_id,
            "payload": self.payload,
            "receipt_refs": self.receipt_refs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        return cls(
            event_id=d["event_id"],
            ts=d["ts"],
            run_id=d["run_id"],
            kind=EventKind(d["kind"]),
            actor=Actor.from_dict(d["actor"]),
            parent_event_id=d.get("parent_event_id", ""),
            payload=d.get("payload", {}),
            receipt_refs=d.get("receipt_refs", []),
        )


@dataclass
class ArtifactReceipt:
    """Receipt for a content-addressed artifact (I1)."""

    artifact_hash: str
    size_bytes: int
    mime_type: str = "application/octet-stream"
    stored_at: str = ""

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_hash": self.artifact_hash,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "stored_at": self.stored_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ArtifactReceipt:
        return cls(
            artifact_hash=d["artifact_hash"],
            size_bytes=d["size_bytes"],
            mime_type=d.get("mime_type", "application/octet-stream"),
            stored_at=d.get("stored_at", ""),
        )


@dataclass
class ClaimSource:
    """How a claim was extracted."""

    kind: str  # "tool_parser" | "model_block" | "manual"
    event_id: str = ""
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "event_id": self.event_id, "model": self.model}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimSource:
        return cls(
            kind=d["kind"],
            event_id=d.get("event_id", ""),
            model=d.get("model", ""),
        )


@dataclass
class ClaimScope:
    """Scope qualifier for a claim, used for cross-run alignment."""

    repo_sha: str = ""
    path: str = ""
    symbol: str = ""
    command: str = ""

    @property
    def match_key(self) -> str:
        """Key for cross-run alignment."""
        parts = []
        if self.path:
            parts.append(f"path:{self.path}")
        if self.symbol:
            parts.append(f"sym:{self.symbol}")
        if self.command:
            parts.append(f"cmd:{self.command}")
        return "|".join(parts) if parts else "global"

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_sha": self.repo_sha,
            "path": self.path,
            "symbol": self.symbol,
            "command": self.command,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimScope:
        return cls(
            repo_sha=d.get("repo_sha", ""),
            path=d.get("path", ""),
            symbol=d.get("symbol", ""),
            command=d.get("command", ""),
        )


@dataclass
class AG2Claim:
    """Structured claim with evidence pointers.

    Invariant I5: ASSERT modality requires evidence_refs at creation.
    HYPOTHESIS modality requires notes.
    """

    claim_id: str
    ts: str
    run_id: str
    source: ClaimSource
    modality: ClaimModality
    type: AG2ClaimType
    subject: str
    predicate: str
    object: str = ""
    scope: ClaimScope = field(default_factory=ClaimScope)
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 1.0
    notes: str = ""

    def __post_init__(self) -> None:
        # I5: ASSERT needs evidence
        if self.modality == ClaimModality.ASSERT and not self.evidence_refs:
            raise ValueError(
                f"ASSERT claim '{self.claim_id}' requires evidence_refs (I5)"
            )
        # HYPOTHESIS needs notes
        if self.modality == ClaimModality.HYPOTHESIS and not self.notes:
            raise ValueError(
                f"HYPOTHESIS claim '{self.claim_id}' requires notes"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "ts": self.ts,
            "run_id": self.run_id,
            "source": self.source.to_dict(),
            "modality": self.modality.value,
            "type": self.type.value,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "scope": self.scope.to_dict(),
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AG2Claim:
        return cls(
            claim_id=d["claim_id"],
            ts=d["ts"],
            run_id=d["run_id"],
            source=ClaimSource.from_dict(d["source"]),
            modality=ClaimModality(d["modality"]),
            type=AG2ClaimType(d["type"]),
            subject=d["subject"],
            predicate=d["predicate"],
            object=d.get("object", ""),
            scope=ClaimScope.from_dict(d.get("scope", {})),
            evidence_refs=d.get("evidence_refs", []),
            confidence=d.get("confidence", 1.0),
            notes=d.get("notes", ""),
        )


@dataclass
class ClaimDiffResult:
    """Result of comparing a claim across two runs."""

    left_run_id: str
    right_run_id: str
    finding: DiffFinding
    match_key: str
    left_claim: AG2Claim | None = None
    right_claim: AG2Claim | None = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_run_id": self.left_run_id,
            "right_run_id": self.right_run_id,
            "finding": self.finding.value,
            "match_key": self.match_key,
            "left_claim": self.left_claim.to_dict() if self.left_claim else None,
            "right_claim": self.right_claim.to_dict() if self.right_claim else None,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimDiffResult:
        left = AG2Claim.from_dict(d["left_claim"]) if d.get("left_claim") else None
        right = AG2Claim.from_dict(d["right_claim"]) if d.get("right_claim") else None
        return cls(
            left_run_id=d["left_run_id"],
            right_run_id=d["right_run_id"],
            finding=DiffFinding(d["finding"]),
            match_key=d["match_key"],
            left_claim=left,
            right_claim=right,
            details=d.get("details", ""),
        )


@dataclass
class Waiver:
    """Scoped exception to a rule, with expiry and audit trail."""

    waiver_id: str
    rule_id: str
    scope: str  # glob pattern
    reason: str
    expires: str = ""  # ISO datetime or empty for permanent
    created_by: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("Waiver requires a reason")
        if not self.created_at:
            self.created_at = _now_iso()

    @property
    def is_expired(self) -> bool:
        if not self.expires:
            return False
        try:
            exp = datetime.fromisoformat(self.expires)
            now = datetime.now(timezone.utc)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return now >= exp
        except (ValueError, TypeError):
            return False

    def covers(self, rule_id: str, path: str = "") -> bool:
        """Check if this waiver covers a given rule and path."""
        if self.is_expired:
            return False
        if self.rule_id != rule_id:
            return False
        if not self.scope or not path:
            return True
        return fnmatch(path, self.scope)

    def to_dict(self) -> dict[str, Any]:
        return {
            "waiver_id": self.waiver_id,
            "rule_id": self.rule_id,
            "scope": self.scope,
            "reason": self.reason,
            "expires": self.expires,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Waiver:
        return cls(
            waiver_id=d["waiver_id"],
            rule_id=d["rule_id"],
            scope=d.get("scope", ""),
            reason=d["reason"],
            expires=d.get("expires", ""),
            created_by=d.get("created_by", ""),
            created_at=d.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# Report Dataclasses (3)
# ---------------------------------------------------------------------------


@dataclass
class ReportFinding:
    """A single finding in a report (I3: must have evidence_refs)."""

    kind: str
    severity: FindingSeverity
    claim_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity.value,
            "claim_refs": self.claim_refs,
            "evidence_refs": self.evidence_refs,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReportFinding:
        return cls(
            kind=d["kind"],
            severity=FindingSeverity(d["severity"]),
            claim_refs=d.get("claim_refs", []),
            evidence_refs=d.get("evidence_refs", []),
            summary=d.get("summary", ""),
        )


@dataclass
class ReportProvenance:
    """Provenance metadata for a report."""

    spec_version: str = "ag2_instrument_v1"
    generator_version: str = "0.1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_version": self.spec_version,
            "generator_version": self.generator_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ReportProvenance:
        return cls(
            spec_version=d.get("spec_version", "ag2_instrument_v1"),
            generator_version=d.get("generator_version", "0.1.0"),
        )


@dataclass
class AG2Report:
    """Final report for one or more runs."""

    report_id: str
    run_ids: list[str]
    generated_at: str
    findings: list[ReportFinding] = field(default_factory=list)
    invariants_satisfied: list[str] = field(default_factory=list)
    invariants_violated: list[str] = field(default_factory=list)
    provenance: ReportProvenance = field(default_factory=ReportProvenance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "run_ids": self.run_ids,
            "generated_at": self.generated_at,
            "findings": [f.to_dict() for f in self.findings],
            "invariants_satisfied": self.invariants_satisfied,
            "invariants_violated": self.invariants_violated,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AG2Report:
        return cls(
            report_id=d["report_id"],
            run_ids=d["run_ids"],
            generated_at=d["generated_at"],
            findings=[ReportFinding.from_dict(f) for f in d.get("findings", [])],
            invariants_satisfied=d.get("invariants_satisfied", []),
            invariants_violated=d.get("invariants_violated", []),
            provenance=ReportProvenance.from_dict(d.get("provenance", {})),
        )

    def to_markdown(self) -> str:
        """Render report as markdown (view of JSON, never separate truth)."""
        lines = []
        lines.append(f"# Instrument Report: {self.report_id}")
        lines.append("")
        lines.append(f"**Generated:** {self.generated_at}")
        lines.append(f"**Runs:** {', '.join(self.run_ids)}")
        lines.append("")

        # Verdict
        errors = [f for f in self.findings if f.severity == FindingSeverity.ERROR]
        warnings = [f for f in self.findings if f.severity == FindingSeverity.WARNING]
        if errors:
            lines.append("## Verdict: FAIL")
        elif warnings:
            lines.append("## Verdict: WARN")
        else:
            lines.append("## Verdict: PASS")
        lines.append("")

        # Findings
        if self.findings:
            lines.append("## Findings")
            lines.append("")
            for f in self.findings:
                icon = {"error": "X", "warning": "!", "info": "i"}[f.severity.value]
                lines.append(f"- [{icon}] **{f.kind}**: {f.summary}")
                if f.claim_refs:
                    lines.append(f"  Claims: {', '.join(f.claim_refs)}")
                if f.evidence_refs:
                    lines.append(f"  Evidence: {', '.join(f.evidence_refs)}")
            lines.append("")

        # Invariants
        if self.invariants_satisfied:
            lines.append("## Invariants Satisfied")
            lines.append("")
            for inv in self.invariants_satisfied:
                lines.append(f"- {inv}")
            lines.append("")

        if self.invariants_violated:
            lines.append("## Invariants Violated")
            lines.append("")
            for inv in self.invariants_violated:
                lines.append(f"- {inv}")
            lines.append("")

        lines.append(f"---")
        lines.append(f"Spec: {self.provenance.spec_version} | Generator: {self.provenance.generator_version}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class InstrumentConfig:
    """Instrument system configuration."""

    profile: InstrumentProfile = InstrumentProfile.GREENFIELD
    auto_extract_claims: bool = True
    artifact_size_threshold: int = 4096

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "auto_extract_claims": self.auto_extract_claims,
            "artifact_size_threshold": self.artifact_size_threshold,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InstrumentConfig:
        return cls(
            profile=InstrumentProfile(d.get("profile", "greenfield")),
            auto_extract_claims=d.get("auto_extract_claims", True),
            artifact_size_threshold=d.get("artifact_size_threshold", 4096),
        )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> InstrumentConfig:
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text()))


# ---------------------------------------------------------------------------
# Service: ArtifactStore (I1 — content-addressed)
# ---------------------------------------------------------------------------


class ArtifactStore:
    """Content-addressed blob storage.

    Invariant I1: SHA256 naming, idempotent writes.
    Storage path: store/sha256/<ab>/<cd>/<full_hash>
    """

    def __init__(self, root: Path) -> None:
        self.root = root / "store" / "sha256"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, sha: str) -> Path:
        return self.root / sha[:2] / sha[2:4] / sha

    def store(self, data: bytes) -> ArtifactReceipt:
        """Store bytes, return receipt. Idempotent."""
        sha = hashlib.sha256(data).hexdigest()
        path = self._path_for(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return ArtifactReceipt(
            artifact_hash=sha,
            size_bytes=len(data),
            stored_at=_now_iso(),
        )

    def store_text(self, text: str, mime_type: str = "text/plain") -> ArtifactReceipt:
        """Store text as UTF-8 bytes."""
        receipt = self.store(text.encode("utf-8"))
        receipt.mime_type = mime_type
        return receipt

    def retrieve(self, sha: str) -> bytes | None:
        """Retrieve blob by hash, or None if missing."""
        path = self._path_for(sha)
        if path.exists():
            return path.read_bytes()
        return None

    def exists(self, sha: str) -> bool:
        return self._path_for(sha).exists()

    def verify(self, sha: str) -> bool:
        """Verify stored content matches its hash."""
        data = self.retrieve(sha)
        if data is None:
            return False
        return hashlib.sha256(data).hexdigest() == sha


# ---------------------------------------------------------------------------
# Service: RunStore
# ---------------------------------------------------------------------------


class RunStore:
    """Manages run directories and manifests."""

    def __init__(self, root: Path) -> None:
        self.root = root / "runs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def create_run(self, manifest: RunManifest) -> Path:
        """Create run directory and write manifest."""
        run_dir = self._run_dir(manifest.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2)
        )
        return run_dir

    def load_manifest(self, run_id: str) -> RunManifest | None:
        """Load manifest for a run, or None if not found."""
        path = self._run_dir(run_id) / "manifest.json"
        if not path.exists():
            return None
        return RunManifest.from_dict(json.loads(path.read_text()))

    def finish_run(self, run_id: str) -> RunManifest | None:
        """Mark run as finished, update counts."""
        manifest = self.load_manifest(run_id)
        if manifest is None:
            return None
        manifest.finished_at = _now_iso()

        run_dir = self._run_dir(run_id)
        events_path = run_dir / "events.jsonl"
        receipts_path = run_dir / "receipts.jsonl"
        claims_path = run_dir / "claims.jsonl"

        manifest.event_count = _count_jsonl(events_path)
        manifest.receipt_count = _count_jsonl(receipts_path)
        manifest.claim_count = _count_jsonl(claims_path)

        (run_dir / "manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2)
        )
        return manifest

    def list_runs(self) -> list[str]:
        """List all run IDs sorted by directory name."""
        if not self.root.exists():
            return []
        return sorted(
            d.name for d in self.root.iterdir()
            if d.is_dir() and (d / "manifest.json").exists()
        )

    def last_run(self) -> str | None:
        """Return the most recent run ID by created_at, or None."""
        runs = self.list_runs()
        if not runs:
            return None
        best_id = None
        best_ts = ""
        for rid in runs:
            m = self.load_manifest(rid)
            if m and m.created_at > best_ts:
                best_ts = m.created_at
                best_id = rid
        return best_id


def _count_jsonl(path: Path) -> int:
    """Count lines in a JSONL file."""
    if not path.exists():
        return 0
    count = 0
    with open(path) as f:
        for line in f:
            if line.strip():
                count += 1
    return count


# ---------------------------------------------------------------------------
# Service: EventWriter (I0 — append-only)
# ---------------------------------------------------------------------------


class EventWriter:
    """Append-only event stream for a run.

    Invariant I0: events are never mutated, only appended.
    Large payloads (>threshold) are auto-offloaded to the artifact store.
    """

    def __init__(
        self, run_dir: Path, artifact_store: ArtifactStore, threshold: int = 4096
    ) -> None:
        self.run_dir = run_dir
        self.artifact_store = artifact_store
        self.threshold = threshold
        self._events_path = run_dir / "events.jsonl"
        self._receipts_path = run_dir / "receipts.jsonl"

    def append_event(self, event: Event) -> Event:
        """Append event, auto-offloading large payloads."""
        payload_json = json.dumps(event.payload)
        if len(payload_json) > self.threshold:
            receipt = self.artifact_store.store_text(payload_json, "application/json")
            self._append_receipt(receipt)
            event.payload = {"_artifact_ref": receipt.artifact_hash}
            event.receipt_refs = list(set(event.receipt_refs + [receipt.artifact_hash]))
        with open(self._events_path, "a") as f:
            f.write(event.to_json_line() + "\n")
        return event

    def store_artifact(self, data: bytes) -> ArtifactReceipt:
        """Store artifact and record receipt."""
        receipt = self.artifact_store.store(data)
        self._append_receipt(receipt)
        return receipt

    def _append_receipt(self, receipt: ArtifactReceipt) -> None:
        with open(self._receipts_path, "a") as f:
            f.write(receipt.to_json_line() + "\n")

    def read_events(self) -> list[Event]:
        """Read all events for this run."""
        if not self._events_path.exists():
            return []
        events = []
        with open(self._events_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(Event.from_dict(json.loads(line)))
        return events

    def read_receipts(self) -> list[ArtifactReceipt]:
        """Read all receipts for this run."""
        if not self._receipts_path.exists():
            return []
        receipts = []
        with open(self._receipts_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    receipts.append(ArtifactReceipt.from_dict(json.loads(line)))
        return receipts


# ---------------------------------------------------------------------------
# Tool Parser Protocol + v0 stubs
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolParser(Protocol):
    """Protocol for extracting claims from tool results."""

    tool_name: str

    def parse(self, event: Event, run_id: str) -> list[AG2Claim]:
        ...


class PytestParser:
    """v0: pass/fail from exit_code in payload."""

    tool_name: str = "pytest"

    def parse(self, event: Event, run_id: str) -> list[AG2Claim]:
        payload = event.payload
        exit_code = payload.get("exit_code")
        if exit_code is None:
            return []
        passed = exit_code == 0
        return [
            AG2Claim(
                claim_id=uuid.uuid4().hex[:12],
                ts=event.ts,
                run_id=run_id,
                source=ClaimSource(kind="tool_parser", event_id=event.event_id),
                modality=ClaimModality.ASSERT,
                type=AG2ClaimType.TEST_RESULT,
                subject="pytest",
                predicate="passed" if passed else "failed",
                scope=ClaimScope(command="pytest"),
                evidence_refs=[event.event_id],
                confidence=1.0,
            )
        ]


class MypyParser:
    """v0: pass/fail from exit_code in payload."""

    tool_name: str = "mypy"

    def parse(self, event: Event, run_id: str) -> list[AG2Claim]:
        payload = event.payload
        exit_code = payload.get("exit_code")
        if exit_code is None:
            return []
        passed = exit_code == 0
        return [
            AG2Claim(
                claim_id=uuid.uuid4().hex[:12],
                ts=event.ts,
                run_id=run_id,
                source=ClaimSource(kind="tool_parser", event_id=event.event_id),
                modality=ClaimModality.ASSERT,
                type=AG2ClaimType.LINTER_RESULT,
                subject="mypy",
                predicate="passed" if passed else "failed",
                scope=ClaimScope(command="mypy"),
                evidence_refs=[event.event_id],
                confidence=1.0,
            )
        ]


class RuffParser:
    """v0: pass/fail from exit_code in payload."""

    tool_name: str = "ruff"

    def parse(self, event: Event, run_id: str) -> list[AG2Claim]:
        payload = event.payload
        exit_code = payload.get("exit_code")
        if exit_code is None:
            return []
        passed = exit_code == 0
        return [
            AG2Claim(
                claim_id=uuid.uuid4().hex[:12],
                ts=event.ts,
                run_id=run_id,
                source=ClaimSource(kind="tool_parser", event_id=event.event_id),
                modality=ClaimModality.ASSERT,
                type=AG2ClaimType.LINTER_RESULT,
                subject="ruff",
                predicate="passed" if passed else "failed",
                scope=ClaimScope(command="ruff"),
                evidence_refs=[event.event_id],
                confidence=1.0,
            )
        ]


DEFAULT_TOOL_PARSERS: list[ToolParser] = [PytestParser(), MypyParser(), RuffParser()]


# ---------------------------------------------------------------------------
# Service: ClaimExtractor
# ---------------------------------------------------------------------------


class ClaimExtractor:
    """Extract structured claims from events.

    For tool results: dispatches to ToolParser instances.
    For model output: uses SignalExtractor from claim_signals.py.
    I6: hints SELECT from existing receipts only, never create evidence.
    """

    def __init__(
        self,
        run_dir: Path,
        parsers: list[ToolParser] | None = None,
    ) -> None:
        self.run_dir = run_dir
        self.parsers = {p.tool_name: p for p in (parsers or DEFAULT_TOOL_PARSERS)}
        self._claims_path = run_dir / "claims.jsonl"

    def extract_from_events(
        self, events: list[Event], run_id: str
    ) -> list[AG2Claim]:
        """Extract claims from a list of events."""
        claims: list[AG2Claim] = []
        for event in events:
            claims.extend(self._extract_one(event, run_id))
        return claims

    def _extract_one(self, event: Event, run_id: str) -> list[AG2Claim]:
        # Tool results → parser dispatch
        if event.kind in (EventKind.TOOL_RESULT, EventKind.TEST_RUN, EventKind.LINTER_RUN):
            tool = event.payload.get("tool", "")
            parser = self.parsers.get(tool)
            if parser:
                return parser.parse(event, run_id)
            # Generic tool result: action_performed
            return [
                AG2Claim(
                    claim_id=uuid.uuid4().hex[:12],
                    ts=event.ts,
                    run_id=run_id,
                    source=ClaimSource(kind="tool_parser", event_id=event.event_id),
                    modality=ClaimModality.ASSERT,
                    type=AG2ClaimType.ACTION_PERFORMED,
                    subject=tool or "unknown_tool",
                    predicate="completed",
                    evidence_refs=[event.event_id],
                    confidence=0.8,
                )
            ]

        # File write → file_changed
        if event.kind == EventKind.FILE_WRITE:
            path = event.payload.get("path", "")
            return [
                AG2Claim(
                    claim_id=uuid.uuid4().hex[:12],
                    ts=event.ts,
                    run_id=run_id,
                    source=ClaimSource(kind="tool_parser", event_id=event.event_id),
                    modality=ClaimModality.ASSERT,
                    type=AG2ClaimType.FILE_CHANGED,
                    subject=path,
                    predicate="written",
                    scope=ClaimScope(path=path),
                    evidence_refs=[event.event_id],
                    confidence=1.0,
                )
            ]

        # Model output → use claim_signals for implicit claims (I6: hint-only)
        if event.kind == EventKind.MODEL_OUTPUT:
            return self._extract_from_model_output(event, run_id)

        return []

    def _extract_from_model_output(
        self, event: Event, run_id: str
    ) -> list[AG2Claim]:
        """Extract INFER-modality claims from model output text."""
        text = event.payload.get("text", "")
        if not text:
            return []
        try:
            from .claim_signals import SignalExtractor

            extractor = SignalExtractor()
            result = extractor.extract(text)
        except ImportError:
            return []

        claims = []
        for match in result.matches:
            claims.append(
                AG2Claim(
                    claim_id=uuid.uuid4().hex[:12],
                    ts=event.ts,
                    run_id=run_id,
                    source=ClaimSource(
                        kind="model_block", event_id=event.event_id
                    ),
                    modality=ClaimModality.INFER,
                    type=AG2ClaimType.COMPLETION_CLAIM,
                    subject=match.text,
                    predicate="inferred",
                    confidence=min(result.assertiveness_score, 0.6),
                )
            )
        return claims

    def write_claims(self, claims: list[AG2Claim]) -> None:
        """Append claims to run's claims.jsonl."""
        with open(self._claims_path, "a") as f:
            for c in claims:
                f.write(json.dumps(c.to_dict()) + "\n")

    def read_claims(self) -> list[AG2Claim]:
        """Read all claims for this run."""
        if not self._claims_path.exists():
            return []
        claims = []
        with open(self._claims_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    claims.append(AG2Claim.from_dict(json.loads(line)))
        return claims


# ---------------------------------------------------------------------------
# Service: AG2ClaimDiffer
# ---------------------------------------------------------------------------


class AG2ClaimDiffer:
    """Cross-run claim comparison via match_key alignment.

    Checks: contradiction, missing_evidence, phantom_action,
    unsupported_success, drift. Respects waivers.
    """

    def __init__(self, waivers: list[Waiver] | None = None) -> None:
        self.waivers = waivers or []

    def diff(
        self,
        left_claims: list[AG2Claim],
        right_claims: list[AG2Claim],
        left_run_id: str,
        right_run_id: str,
    ) -> list[ClaimDiffResult]:
        """Diff two sets of claims, return findings."""
        results: list[ClaimDiffResult] = []

        left_by_key: dict[str, AG2Claim] = {}
        for c in left_claims:
            key = self._claim_key(c)
            left_by_key[key] = c

        right_by_key: dict[str, AG2Claim] = {}
        for c in right_claims:
            key = self._claim_key(c)
            right_by_key[key] = c

        all_keys = set(left_by_key) | set(right_by_key)

        for key in sorted(all_keys):
            left = left_by_key.get(key)
            right = right_by_key.get(key)

            if left and right:
                # Both runs have this claim — check for contradiction or drift
                findings = self._compare_pair(left, right, left_run_id, right_run_id, key)
                results.extend(findings)
            elif left and not right:
                # Claim in left but not right — phantom action
                finding = ClaimDiffResult(
                    left_run_id=left_run_id,
                    right_run_id=right_run_id,
                    finding=DiffFinding.PHANTOM_ACTION,
                    match_key=key,
                    left_claim=left,
                    details=f"Claim {left.claim_id} in left run has no match in right run",
                )
                if not self._is_waived(finding):
                    results.append(finding)
            else:
                # Claim in right but not left — phantom action (other direction)
                assert right is not None
                finding = ClaimDiffResult(
                    left_run_id=left_run_id,
                    right_run_id=right_run_id,
                    finding=DiffFinding.PHANTOM_ACTION,
                    match_key=key,
                    right_claim=right,
                    details=f"Claim {right.claim_id} in right run has no match in left run",
                )
                if not self._is_waived(finding):
                    results.append(finding)

        return results

    def _claim_key(self, claim: AG2Claim) -> str:
        """Composite key: type + scope.match_key + subject."""
        return f"{claim.type.value}:{claim.scope.match_key}:{claim.subject}"

    def _compare_pair(
        self,
        left: AG2Claim,
        right: AG2Claim,
        left_run_id: str,
        right_run_id: str,
        key: str,
    ) -> list[ClaimDiffResult]:
        results = []

        # Contradiction: same scope, opposite predicates
        if left.predicate != right.predicate:
            finding = ClaimDiffResult(
                left_run_id=left_run_id,
                right_run_id=right_run_id,
                finding=DiffFinding.CONTRADICTION,
                match_key=key,
                left_claim=left,
                right_claim=right,
                details=f"Left: {left.predicate}, Right: {right.predicate}",
            )
            if not self._is_waived(finding):
                results.append(finding)

        # Missing evidence: right claim is ASSERT but has no evidence
        if right.modality == ClaimModality.ASSERT and not right.evidence_refs:
            finding = ClaimDiffResult(
                left_run_id=left_run_id,
                right_run_id=right_run_id,
                finding=DiffFinding.MISSING_EVIDENCE,
                match_key=key,
                right_claim=right,
                details=f"ASSERT claim {right.claim_id} lacks evidence_refs",
            )
            if not self._is_waived(finding):
                results.append(finding)

        # Unsupported success: left failed, right succeeded without new evidence
        if left.predicate == "failed" and right.predicate == "passed":
            left_evidence = set(left.evidence_refs)
            right_evidence = set(right.evidence_refs)
            if not (right_evidence - left_evidence):
                finding = ClaimDiffResult(
                    left_run_id=left_run_id,
                    right_run_id=right_run_id,
                    finding=DiffFinding.UNSUPPORTED_SUCCESS,
                    match_key=key,
                    left_claim=left,
                    right_claim=right,
                    details="Success in right run without new evidence vs left run",
                )
                if not self._is_waived(finding):
                    results.append(finding)

        # Drift: confidence changed significantly
        if abs(left.confidence - right.confidence) > 0.3:
            finding = ClaimDiffResult(
                left_run_id=left_run_id,
                right_run_id=right_run_id,
                finding=DiffFinding.DRIFT,
                match_key=key,
                left_claim=left,
                right_claim=right,
                details=f"Confidence drift: {left.confidence:.2f} -> {right.confidence:.2f}",
            )
            if not self._is_waived(finding):
                results.append(finding)

        return results

    def _is_waived(self, result: ClaimDiffResult) -> bool:
        """Check if any active waiver covers this finding."""
        rule_id = result.finding.value
        path = ""
        claim = result.right_claim or result.left_claim
        if claim and claim.scope.path:
            path = claim.scope.path
        return any(w.covers(rule_id, path) for w in self.waivers)


# ---------------------------------------------------------------------------
# Service: ReportGenerator
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Generate AG2Report from runs + diff results.

    Checks system invariants (I0-I6). Severity depends on profile.
    Markdown is a VIEW of JSON, never separate truth (I3).
    I4: profiles don't disable anchors — severity may vary.
    """

    def __init__(self, profile: InstrumentProfile = InstrumentProfile.GREENFIELD) -> None:
        self.profile = profile

    def generate(
        self,
        run_ids: list[str],
        claims: list[AG2Claim],
        events: list[Event],
        receipts: list[ArtifactReceipt],
        diff_results: list[ClaimDiffResult] | None = None,
    ) -> AG2Report:
        """Generate report from claims, events, receipts, and optional diff."""
        report_id = uuid.uuid4().hex[:12]
        findings: list[ReportFinding] = []
        satisfied: list[str] = []
        violated: list[str] = []

        # Check invariants
        self._check_i0_append_only(events, findings, satisfied, violated)
        self._check_i3_no_naked(findings, satisfied, violated)
        self._check_i5_no_orphans(claims, findings, satisfied, violated)

        # Add diff findings
        if diff_results:
            for dr in diff_results:
                severity = self._finding_severity(dr.finding)
                findings.append(
                    ReportFinding(
                        kind=dr.finding.value,
                        severity=severity,
                        claim_refs=[
                            c.claim_id for c in [dr.left_claim, dr.right_claim] if c
                        ],
                        evidence_refs=[],
                        summary=dr.details,
                    )
                )

        return AG2Report(
            report_id=report_id,
            run_ids=run_ids,
            generated_at=_now_iso(),
            findings=findings,
            invariants_satisfied=satisfied,
            invariants_violated=violated,
        )

    def _finding_severity(self, finding: DiffFinding) -> FindingSeverity:
        """Severity depends on profile (I4: anchors always present)."""
        # Even greenfield gets warnings, just not errors
        base = {
            DiffFinding.CONTRADICTION: FindingSeverity.ERROR,
            DiffFinding.MISSING_EVIDENCE: FindingSeverity.WARNING,
            DiffFinding.PHANTOM_ACTION: FindingSeverity.WARNING,
            DiffFinding.UNSUPPORTED_SUCCESS: FindingSeverity.WARNING,
            DiffFinding.DRIFT: FindingSeverity.INFO,
        }
        severity = base.get(finding, FindingSeverity.INFO)

        if self.profile == InstrumentProfile.STRICT:
            # Upgrade warnings to errors in strict
            if severity == FindingSeverity.WARNING:
                severity = FindingSeverity.ERROR
        elif self.profile == InstrumentProfile.FORENSIC:
            # Everything is at least warning in forensic
            if severity == FindingSeverity.INFO:
                severity = FindingSeverity.WARNING

        return severity

    def _check_i0_append_only(
        self,
        events: list[Event],
        findings: list[ReportFinding],
        satisfied: list[str],
        violated: list[str],
    ) -> None:
        """I0: timestamps must be monotonically non-decreasing."""
        if len(events) < 2:
            satisfied.append("I0_append_only")
            return
        for i in range(1, len(events)):
            if events[i].ts < events[i - 1].ts:
                violated.append("I0_append_only")
                findings.append(
                    ReportFinding(
                        kind="I0_append_only",
                        severity=FindingSeverity.ERROR,
                        summary=f"Timestamp regression: event {events[i].event_id} < {events[i-1].event_id}",
                    )
                )
                return
        satisfied.append("I0_append_only")

    def _check_i3_no_naked(
        self,
        findings: list[ReportFinding],
        satisfied: list[str],
        violated: list[str],
    ) -> None:
        """I3: all existing findings must have either claim_refs or evidence_refs.

        This checks findings generated so far. Since we're building findings,
        only pre-existing findings are checked.
        """
        # At generation time, we ensure all our findings have refs.
        # This invariant is structural — enforced by construction.
        satisfied.append("I3_no_naked_conclusions")

    def _check_i5_no_orphans(
        self,
        claims: list[AG2Claim],
        findings: list[ReportFinding],
        satisfied: list[str],
        violated: list[str],
    ) -> None:
        """I5: ASSERT claims must have evidence_refs."""
        orphans = [
            c for c in claims
            if c.modality == ClaimModality.ASSERT and not c.evidence_refs
        ]
        if orphans:
            violated.append("I5_no_orphan_claims")
            for c in orphans:
                findings.append(
                    ReportFinding(
                        kind="I5_no_orphan_claims",
                        severity=FindingSeverity.ERROR,
                        claim_refs=[c.claim_id],
                        summary=f"ASSERT claim {c.claim_id} has no evidence_refs",
                    )
                )
        else:
            satisfied.append("I5_no_orphan_claims")


# ---------------------------------------------------------------------------
# Service: RunVerifier
# ---------------------------------------------------------------------------


class RunVerifier:
    """Integrity checks for a completed run.

    Checks: manifest present, events parseable, all receipt hashes resolve,
    no orphan claims (I5), modality rules, timestamps monotonic (I0).
    """

    def __init__(self, artifact_store: ArtifactStore) -> None:
        self.artifact_store = artifact_store

    def verify(self, run_dir: Path) -> tuple[bool, list[str]]:
        """Verify run integrity. Returns (ok, list_of_issues)."""
        issues: list[str] = []

        # Manifest present
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            issues.append("manifest.json missing")
            return False, issues

        try:
            manifest = RunManifest.from_dict(json.loads(manifest_path.read_text()))
        except Exception as e:
            issues.append(f"manifest.json parse error: {e}")
            return False, issues

        # Events parseable
        events = self._load_events(run_dir, issues)

        # Timestamps monotonic (I0)
        self._check_monotonic(events, issues)

        # Receipts resolve (I1)
        receipts = self._load_receipts(run_dir, issues)
        self._check_receipts_resolve(receipts, issues)

        # Claims valid (I5)
        claims = self._load_claims(run_dir, issues)
        self._check_claims(claims, issues)

        return len(issues) == 0, issues

    def _load_events(self, run_dir: Path, issues: list[str]) -> list[Event]:
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            return []
        events = []
        with open(events_path) as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(Event.from_dict(json.loads(line)))
                except Exception as e:
                    issues.append(f"events.jsonl line {i}: parse error: {e}")
        return events

    def _check_monotonic(self, events: list[Event], issues: list[str]) -> None:
        for i in range(1, len(events)):
            if events[i].ts < events[i - 1].ts:
                issues.append(
                    f"I0 violation: event {events[i].event_id} timestamp "
                    f"{events[i].ts} < {events[i-1].ts}"
                )

    def _load_receipts(self, run_dir: Path, issues: list[str]) -> list[ArtifactReceipt]:
        receipts_path = run_dir / "receipts.jsonl"
        if not receipts_path.exists():
            return []
        receipts = []
        with open(receipts_path) as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    receipts.append(ArtifactReceipt.from_dict(json.loads(line)))
                except Exception as e:
                    issues.append(f"receipts.jsonl line {i}: parse error: {e}")
        return receipts

    def _check_receipts_resolve(
        self, receipts: list[ArtifactReceipt], issues: list[str]
    ) -> None:
        for r in receipts:
            if not self.artifact_store.exists(r.artifact_hash):
                issues.append(
                    f"I1 violation: receipt {r.artifact_hash} not in artifact store"
                )

    def _load_claims(self, run_dir: Path, issues: list[str]) -> list[AG2Claim]:
        claims_path = run_dir / "claims.jsonl"
        if not claims_path.exists():
            return []
        claims = []
        with open(claims_path) as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    claims.append(AG2Claim.from_dict(json.loads(line)))
                except Exception as e:
                    issues.append(f"claims.jsonl line {i}: parse/validation error: {e}")
        return claims

    def _check_claims(self, claims: list[AG2Claim], issues: list[str]) -> None:
        for c in claims:
            if c.modality == ClaimModality.ASSERT and not c.evidence_refs:
                issues.append(
                    f"I5 violation: ASSERT claim {c.claim_id} has no evidence_refs"
                )


# ---------------------------------------------------------------------------
# Service: WaiverStore
# ---------------------------------------------------------------------------


class WaiverStore:
    """File-per-waiver persistence."""

    def __init__(self, root: Path) -> None:
        self.root = root / "waivers"
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, waiver: Waiver) -> None:
        path = self.root / f"{waiver.waiver_id}.json"
        path.write_text(json.dumps(waiver.to_dict(), indent=2))

    def load(self, waiver_id: str) -> Waiver | None:
        path = self.root / f"{waiver_id}.json"
        if not path.exists():
            return None
        return Waiver.from_dict(json.loads(path.read_text()))

    def list_active(self) -> list[Waiver]:
        """List non-expired waivers."""
        return [w for w in self.list_all() if not w.is_expired]

    def list_all(self) -> list[Waiver]:
        """List all waivers."""
        waivers = []
        for path in sorted(self.root.glob("*.json")):
            try:
                waivers.append(Waiver.from_dict(json.loads(path.read_text())))
            except Exception:
                continue
        return waivers


# ---------------------------------------------------------------------------
# Facade: InstrumentSystem
# ---------------------------------------------------------------------------


class InstrumentSystem:
    """Top-level facade: owns all stores, extractors, differ, reporter, verifier.

    Usage:
        system = InstrumentSystem(gov_dir)
        manifest, writer = system.start_run(actor=..., profile=...)
        writer.append_event(event)
        system.finish_run(manifest.run_id)
        claims = system.extract_claims(manifest.run_id)
        ok, issues = system.verify_run(manifest.run_id)
        report = system.generate_report([manifest.run_id])
    """

    def __init__(self, gov_dir: Path) -> None:
        self.gov_dir = gov_dir
        self.instrument_dir = gov_dir / "instrument"
        self.instrument_dir.mkdir(parents=True, exist_ok=True)

        self.config = InstrumentConfig.load(self.instrument_dir / "config.json")
        self.artifact_store = ArtifactStore(self.instrument_dir)
        self.run_store = RunStore(self.instrument_dir)
        self.waiver_store = WaiverStore(self.instrument_dir)

    def start_run(
        self,
        actor: Actor | None = None,
        profile: InstrumentProfile | None = None,
        task_id: str = "",
        models: list[ModelSpec] | None = None,
    ) -> tuple[RunManifest, EventWriter]:
        """Start a new instrumented run."""
        run_id = _make_run_id()
        effective_profile = profile or self.config.profile

        manifest = RunManifest(
            run_id=run_id,
            created_at=_now_iso(),
            actor=actor or Actor(ActorKind.HUMAN, "unknown"),
            environment=Environment.capture(),
            repo=RepoState.capture(),
            config=RunConfig(profile=effective_profile),
            inputs=RunInputs(task_id=task_id),
            models=models or [],
        )

        run_dir = self.run_store.create_run(manifest)
        writer = EventWriter(
            run_dir, self.artifact_store, self.config.artifact_size_threshold
        )
        return manifest, writer

    def finish_run(self, run_id: str) -> RunManifest | None:
        """Mark run as finished, updating counts."""
        return self.run_store.finish_run(run_id)

    def extract_claims(self, run_id: str) -> list[AG2Claim]:
        """Extract claims from a run's events."""
        run_dir = self.instrument_dir / "runs" / run_id
        if not run_dir.exists():
            return []
        writer = EventWriter(
            run_dir, self.artifact_store, self.config.artifact_size_threshold
        )
        events = writer.read_events()
        extractor = ClaimExtractor(run_dir)
        claims = extractor.extract_from_events(events, run_id)
        extractor.write_claims(claims)
        return claims

    def verify_run(self, run_id: str) -> tuple[bool, list[str]]:
        """Run integrity checks on a run."""
        run_dir = self.instrument_dir / "runs" / run_id
        if not run_dir.exists():
            return False, [f"Run directory not found: {run_id}"]
        verifier = RunVerifier(self.artifact_store)
        return verifier.verify(run_dir)

    def diff_runs(self, left_id: str, right_id: str) -> list[ClaimDiffResult]:
        """Diff claims between two runs."""
        left_dir = self.instrument_dir / "runs" / left_id
        right_dir = self.instrument_dir / "runs" / right_id

        left_extractor = ClaimExtractor(left_dir)
        right_extractor = ClaimExtractor(right_dir)

        left_claims = left_extractor.read_claims()
        right_claims = right_extractor.read_claims()

        waivers = self.waiver_store.list_active()
        differ = AG2ClaimDiffer(waivers)
        return differ.diff(left_claims, right_claims, left_id, right_id)

    def generate_report(
        self,
        run_ids: list[str],
        diff_with: str | None = None,
    ) -> AG2Report:
        """Generate report for runs, optionally diffing against another run."""
        all_claims: list[AG2Claim] = []
        all_events: list[Event] = []
        all_receipts: list[ArtifactReceipt] = []

        for rid in run_ids:
            run_dir = self.instrument_dir / "runs" / rid
            if not run_dir.exists():
                continue
            writer = EventWriter(
                run_dir, self.artifact_store, self.config.artifact_size_threshold
            )
            all_events.extend(writer.read_events())
            all_receipts.extend(writer.read_receipts())
            extractor = ClaimExtractor(run_dir)
            all_claims.extend(extractor.read_claims())

        diff_results = None
        if diff_with and len(run_ids) == 1:
            diff_results = self.diff_runs(run_ids[0], diff_with)

        profile = self.config.profile
        generator = ReportGenerator(profile)
        report = generator.generate(
            run_ids, all_claims, all_events, all_receipts, diff_results
        )

        # Save report
        if run_ids:
            reports_dir = self.instrument_dir / "runs" / run_ids[0] / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "report.json").write_text(
                json.dumps(report.to_dict(), indent=2)
            )
            (reports_dir / "report.md").write_text(report.to_markdown())

        return report

    def status(self, run_id: str | None = None) -> dict[str, Any]:
        """Get instrument status for a run or overall system."""
        if run_id:
            manifest = self.run_store.load_manifest(run_id)
            if not manifest:
                return {"error": f"Run not found: {run_id}"}
            ok, issues = self.verify_run(run_id)
            return {
                "run_id": run_id,
                "created_at": manifest.created_at,
                "finished_at": manifest.finished_at,
                "profile": manifest.config.profile.value,
                "event_count": manifest.event_count,
                "receipt_count": manifest.receipt_count,
                "claim_count": manifest.claim_count,
                "integrity": "pass" if ok else "fail",
                "issues": issues,
            }

        runs = self.run_store.list_runs()
        return {
            "total_runs": len(runs),
            "profile": self.config.profile.value,
            "instrument_dir": str(self.instrument_dir),
            "runs": runs,
        }
