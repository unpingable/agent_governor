"""
Constraint Compiler — Pre-execution constraint projection.

Resolves all applicable constraints for a given intent + scope into a portable
ConstraintBlock that any executor LLM can consume as a prompt prefix.

The governor still gates output afterward (belt and suspenders), but projection
reduces rejection churn by giving the executor the law before it speaks.

Spec: CONSTRAINT_COMPILER_SPEC.md (Layer 1, Item #3 of AG2 build order)

Core properties:
  - Pure: No side effects, no backend calls, no network
  - Deterministic: Same inputs → same output (modulo ledger state, which is hashed)
  - Content-addressed: Output includes hash of resolved constraint set
  - Monotonic: More specific intent/scope only adds constraints, never fewer
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConstraintKind(str, Enum):
    """Kind of resolved constraint."""

    ANCHOR = "anchor"
    INVARIANT = "invariant"
    SCAR = "scar"
    DECISION = "decision"
    SPINE_RULE = "spine_rule"
    SECURITY_PATTERN = "security_pattern"
    ENVELOPE = "envelope"
    PROFILE = "profile"
    OVERRIDE = "override"


class ConstraintSeverity(str, Enum):
    """Severity of a resolved constraint."""

    REJECT = "reject"
    WARN = "warn"
    INFO = "info"


class ScarClass(str, Enum):
    """Scar taxonomy for override eligibility."""

    HARD = "hard"
    """Never overridable. Provenance breaks, tamper detection, unknown tool execution."""

    SOFT = "soft"
    """Overridable with warrant. Risky refactors, sensitive paths."""

    PROCEDURAL = "procedural"
    """Overridable with warrant + mandatory review. Bypassed approvals."""


class OutputFormat(str, Enum):
    """Output format for constraint blocks."""

    PROMPT = "prompt"
    JSON = "json"
    SUMMARY = "summary"


# ---------------------------------------------------------------------------
# Core Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ResolvedConstraint:
    """Single resolved constraint."""

    constraint_id: str
    kind: ConstraintKind
    severity: ConstraintSeverity
    description: str
    pattern: str | None = None
    scope: str | None = None
    source: str = ""
    projection_priority: float = 0.5
    overruled_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "constraint_id": self.constraint_id,
            "kind": self.kind.value,
            "severity": self.severity.value,
            "description": self.description,
            "source": self.source,
            "projection_priority": self.projection_priority,
        }
        if self.pattern is not None:
            d["pattern"] = self.pattern
        if self.scope is not None:
            d["scope"] = self.scope
        if self.overruled_by is not None:
            d["overruled_by"] = self.overruled_by
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ResolvedConstraint:
        return cls(
            constraint_id=d["constraint_id"],
            kind=ConstraintKind(d["kind"]),
            severity=ConstraintSeverity(d["severity"]),
            description=d["description"],
            pattern=d.get("pattern"),
            scope=d.get("scope"),
            source=d.get("source", ""),
            projection_priority=d.get("projection_priority", 0.5),
            overruled_by=d.get("overruled_by"),
        )


@dataclass
class ConstraintSource:
    """Provenance for a group of constraints from one subsystem."""

    subsystem: str
    count: int
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "count": self.count,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConstraintSource:
        return cls(
            subsystem=d["subsystem"],
            count=d["count"],
            hash=d["hash"],
        )


@dataclass
class OverrideWarrant:
    """Explicit, scoped, expiring override of soft/procedural scars."""

    warrant_id: str
    invoked_by: str
    reason: str
    scope: list[str]
    constraints_overruled: list[str]
    expires_at: datetime
    risk_ack: bool = True
    required_followup: str | None = None
    quorum_signers: list[str] | None = None

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def remaining_seconds(self) -> float:
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0.0, delta.total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "warrant_id": self.warrant_id,
            "invoked_by": self.invoked_by,
            "reason": self.reason,
            "scope": self.scope,
            "constraints_overruled": self.constraints_overruled,
            "expires_at": self.expires_at.isoformat(),
            "risk_ack": self.risk_ack,
            "required_followup": self.required_followup,
            "quorum_signers": self.quorum_signers,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OverrideWarrant:
        return cls(
            warrant_id=d["warrant_id"],
            invoked_by=d["invoked_by"],
            reason=d["reason"],
            scope=d["scope"],
            constraints_overruled=d["constraints_overruled"],
            expires_at=datetime.fromisoformat(d["expires_at"]),
            risk_ack=d.get("risk_ack", True),
            required_followup=d.get("required_followup"),
            quorum_signers=d.get("quorum_signers"),
        )


@dataclass
class QuorumUnsatisfiedReceipt:
    """Warrant rejected: quorum could not be verified."""

    warrant_id: str
    required_signers: int
    verified_signers: int
    reason: str
    constraint_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "warrant_id": self.warrant_id,
            "required_signers": self.required_signers,
            "verified_signers": self.verified_signers,
            "reason": self.reason,
            "constraint_id": self.constraint_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QuorumUnsatisfiedReceipt:
        return cls(
            warrant_id=d["warrant_id"],
            required_signers=d["required_signers"],
            verified_signers=d["verified_signers"],
            reason=d["reason"],
            constraint_id=d["constraint_id"],
        )


@dataclass
class ConstraintBlock:
    """Compiled constraints for executor consumption."""

    constraints: list[ResolvedConstraint]
    sources: list[ConstraintSource]
    content_hash: str
    compiled_at: datetime
    intent: str | None = None
    scope: list[str] | None = None
    mode: str | None = None
    envelope: str = "strict"
    profile: str | None = None
    warrants: list[OverrideWarrant] = field(default_factory=list)
    quorum_failures: list[QuorumUnsatisfiedReceipt] = field(default_factory=list)
    exploratory_warning: bool = False

    @property
    def effective_constraints(self) -> list[ResolvedConstraint]:
        """Constraints not overruled by a warrant."""
        return [c for c in self.constraints if c.overruled_by is None]

    @property
    def overruled_constraints(self) -> list[ResolvedConstraint]:
        """Constraints overruled by a warrant."""
        return [c for c in self.constraints if c.overruled_by is not None]

    @property
    def hard_constraints(self) -> list[ResolvedConstraint]:
        """Effective reject-severity constraints."""
        return [
            c for c in self.effective_constraints
            if c.severity == ConstraintSeverity.REJECT
        ]

    @property
    def soft_constraints(self) -> list[ResolvedConstraint]:
        """Effective warn-severity constraints."""
        return [
            c for c in self.effective_constraints
            if c.severity == ConstraintSeverity.WARN
        ]

    @property
    def security_constraints(self) -> list[ResolvedConstraint]:
        """Effective security pattern constraints."""
        return [
            c for c in self.effective_constraints
            if c.kind == ConstraintKind.SECURITY_PATTERN
        ]

    @property
    def prompt_prefix(self) -> str:
        """Generate the human-readable prompt prefix."""
        return render_prompt_prefix(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraints": [c.to_dict() for c in self.constraints],
            "sources": [s.to_dict() for s in self.sources],
            "content_hash": self.content_hash,
            "compiled_at": self.compiled_at.isoformat(),
            "intent": self.intent,
            "scope": self.scope,
            "mode": self.mode,
            "envelope": self.envelope,
            "profile": self.profile,
            "warrants": [w.to_dict() for w in self.warrants],
            "quorum_failures": [q.to_dict() for q in self.quorum_failures],
            "exploratory_warning": self.exploratory_warning,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConstraintBlock:
        return cls(
            constraints=[ResolvedConstraint.from_dict(c) for c in d["constraints"]],
            sources=[ConstraintSource.from_dict(s) for s in d["sources"]],
            content_hash=d["content_hash"],
            compiled_at=datetime.fromisoformat(d["compiled_at"]),
            intent=d.get("intent"),
            scope=d.get("scope"),
            mode=d.get("mode"),
            envelope=d.get("envelope", "strict"),
            profile=d.get("profile"),
            warrants=[OverrideWarrant.from_dict(w) for w in d.get("warrants", [])],
            quorum_failures=[
                QuorumUnsatisfiedReceipt.from_dict(q)
                for q in d.get("quorum_failures", [])
            ],
            exploratory_warning=d.get("exploratory_warning", False),
        )

    def to_summary(self) -> str:
        """Generate a compact summary."""
        lines = []
        lines.append(f"Constraints: {len(self.constraints)} total")
        lines.append(f"  Hard (reject): {len(self.hard_constraints)}")
        lines.append(f"  Soft (warn):   {len(self.soft_constraints)}")
        lines.append(f"  Security:      {len(self.security_constraints)}")
        if self.overruled_constraints:
            lines.append(f"  Overruled:     {len(self.overruled_constraints)}")
        lines.append(f"Sources: {len(self.sources)}")
        for s in self.sources:
            lines.append(f"  {s.subsystem}: {s.count}")
        lines.append(f"Hash: {self.content_hash[:12]}")
        if self.warrants:
            lines.append(f"Active warrants: {len(self.warrants)}")
        if self.exploratory_warning:
            lines.append("WARNING: Exploratory mode — receipt requirements relaxed")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scar Classification
# ---------------------------------------------------------------------------


def classify_scar(stiffness: float) -> ScarClass:
    """Classify a scar by stiffness into the three-class taxonomy.

    Hard: stiffness >= 0.95 — never overridable
    Soft: 0.3 <= stiffness < 0.95 — overridable with warrant
    Procedural: stiffness < 0.3 — overridable with warrant + review
    """
    if stiffness >= 0.95:
        return ScarClass.HARD
    elif stiffness >= 0.3:
        return ScarClass.SOFT
    return ScarClass.PROCEDURAL


# ---------------------------------------------------------------------------
# Warrant Quorum Policy
# ---------------------------------------------------------------------------


def required_quorum(
    scar_class: ScarClass,
    profile: str | None = None,
    envelope: str = "strict",
) -> int:
    """Return required number of signers for an override warrant.

    Hard scars: never overridable (returns -1 as sentinel)
    Procedural scars in strict+production: 2 signers
    Everything else: 1 signer
    """
    if scar_class == ScarClass.HARD:
        return -1  # Never overridable
    if scar_class == ScarClass.PROCEDURAL and envelope == "strict" and profile == "production":
        return 2
    return 1


def check_warrant_quorum(
    warrant: OverrideWarrant,
    scar_class: ScarClass,
    profile: str | None = None,
    envelope: str = "strict",
) -> QuorumUnsatisfiedReceipt | None:
    """Check if a warrant satisfies quorum requirements.

    Returns None if quorum is satisfied, or a receipt if not.
    """
    required = required_quorum(scar_class, profile, envelope)
    if required == -1:
        return QuorumUnsatisfiedReceipt(
            warrant_id=warrant.warrant_id,
            required_signers=-1,
            verified_signers=0,
            reason="hard scar — never overridable",
            constraint_id="",
        )
    signers = len(warrant.quorum_signers or []) + 1  # +1 for the invoker
    if signers < required:
        return QuorumUnsatisfiedReceipt(
            warrant_id=warrant.warrant_id,
            required_signers=required,
            verified_signers=signers,
            reason=f"insufficient signers: {signers} < {required}",
            constraint_id="",
        )
    return None


# ---------------------------------------------------------------------------
# Constraint ID Generation
# ---------------------------------------------------------------------------


def make_constraint_id(kind: str, source: str, scope: str, pattern: str, description: str) -> str:
    """Generate a stable content-addressed constraint ID."""
    content = f"{kind}|{source}|{scope}|{pattern}|{description}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Scope Matching
# ---------------------------------------------------------------------------


def _scope_matches(constraint_scope: str | None, target_scopes: list[str] | None) -> bool:
    """Check if a constraint's scope matches any of the target scopes.

    If either is None/empty, the constraint is considered to match (global).
    """
    if not constraint_scope or not target_scopes:
        return True

    for target in target_scopes:
        if fnmatch.fnmatch(constraint_scope, target):
            return True
        if fnmatch.fnmatch(target, constraint_scope):
            return True

    return False


# ---------------------------------------------------------------------------
# Projection Priority
# ---------------------------------------------------------------------------


def compute_priority(
    kind: ConstraintKind,
    severity: ConstraintSeverity,
    scope: str | None,
    target_scopes: list[str] | None,
    is_scar_adjacent: bool = False,
) -> float:
    """Compute projection priority for a constraint.

    1. In-scope > out-of-scope
    2. Scar-adjacent > never violated
    3. File-specific > global
    4. Decision ledger > style preferences
    """
    priority = 0.5

    # Severity boost
    if severity == ConstraintSeverity.REJECT:
        priority += 0.3
    elif severity == ConstraintSeverity.WARN:
        priority += 0.1

    # In-scope boost
    if scope and target_scopes:
        for target in target_scopes:
            if fnmatch.fnmatch(scope, target) or fnmatch.fnmatch(target, scope):
                priority += 0.15
                break

    # Scar-adjacent boost
    if is_scar_adjacent:
        priority += 0.1

    # File-specific boost (narrow scope ranks higher)
    if scope and "/" in scope:
        priority += 0.05

    # Kind-specific boost
    if kind == ConstraintKind.DECISION:
        priority += 0.05

    return min(1.0, priority)


# ---------------------------------------------------------------------------
# Hash Utilities
# ---------------------------------------------------------------------------


def _hash_items(items: list[dict[str, Any]]) -> str:
    """Hash a list of serializable items."""
    content = json.dumps(items, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _content_hash(constraints: list[ResolvedConstraint]) -> str:
    """Compute the content hash of a resolved constraint set."""
    items = sorted(
        [c.to_dict() for c in constraints],
        key=lambda d: d["constraint_id"],
    )
    content = json.dumps(items, sort_keys=True, default=str)
    return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Resolution Layers
# ---------------------------------------------------------------------------


def _resolve_envelope(
    governor_dir: Path,
    envelope_mode: str | None = None,
) -> tuple[str, list[ResolvedConstraint]]:
    """Layer 1: Resolve envelope constraints."""
    from .envelopes import get_current_envelope, EnvelopeMode

    constraints: list[ResolvedConstraint] = []

    if envelope_mode:
        try:
            mode = EnvelopeMode(envelope_mode)
        except ValueError:
            mode = EnvelopeMode.STRICT
    else:
        config = get_current_envelope(governor_dir)
        mode = config.mode

    mode_str = mode.value

    if mode == EnvelopeMode.STRICT:
        constraints.append(ResolvedConstraint(
            constraint_id=make_constraint_id("envelope", "envelope", "", "", "strict mode"),
            kind=ConstraintKind.ENVELOPE,
            severity=ConstraintSeverity.REJECT,
            description="Strict mode: all claims require receipts",
            source="envelope",
            projection_priority=0.9,
        ))
    elif mode == EnvelopeMode.EXPLORATORY:
        constraints.append(ResolvedConstraint(
            constraint_id=make_constraint_id("envelope", "envelope", "", "", "exploratory mode"),
            kind=ConstraintKind.ENVELOPE,
            severity=ConstraintSeverity.INFO,
            description="Exploratory mode: receipt requirements relaxed",
            source="envelope",
            projection_priority=0.7,
        ))
    elif mode == EnvelopeMode.SLIM:
        constraints.append(ResolvedConstraint(
            constraint_id=make_constraint_id("envelope", "envelope", "", "", "slim mode"),
            kind=ConstraintKind.ENVELOPE,
            severity=ConstraintSeverity.WARN,
            description="Slim mode: decisions committed, receipts not required",
            source="envelope",
            projection_priority=0.8,
        ))

    return mode_str, constraints


def _resolve_profile(
    governor_dir: Path,
) -> tuple[str | None, list[ResolvedConstraint]]:
    """Layer 2: Resolve profile constraints."""
    from .profiles import ProfileManager

    constraints: list[ResolvedConstraint] = []
    pm = ProfileManager(governor_dir)
    name, settings = pm.get_active()

    if name and settings:
        constraints.append(ResolvedConstraint(
            constraint_id=make_constraint_id("profile", "profiles", "", "", name),
            kind=ConstraintKind.PROFILE,
            severity=ConstraintSeverity.INFO,
            description=f"Active profile: {name} — {settings.description}" if settings.description else f"Active profile: {name}",
            source="profiles",
            projection_priority=0.7,
        ))
        if settings.strict_mode:
            constraints.append(ResolvedConstraint(
                constraint_id=make_constraint_id("profile", "profiles", "", "", f"{name}-strict"),
                kind=ConstraintKind.PROFILE,
                severity=ConstraintSeverity.REJECT,
                description=f"Profile '{name}' enforces strict mode",
                source="profiles",
                projection_priority=0.85,
            ))

    return name, constraints


def _resolve_decisions(
    governor_dir: Path,
    target_scopes: list[str] | None = None,
) -> list[ResolvedConstraint]:
    """Layer 9: Resolve decision ledger constraints."""
    from .ledgers import DecisionLedger

    constraints: list[ResolvedConstraint] = []
    ledger = DecisionLedger(governor_dir)

    for decision in ledger.query():
        if decision.choice.startswith("[RETRACTED]"):
            continue
        cid = make_constraint_id(
            "decision", "decisions", "", decision.topic, decision.choice
        )
        constraints.append(ResolvedConstraint(
            constraint_id=cid,
            kind=ConstraintKind.DECISION,
            severity=ConstraintSeverity.REJECT,
            description=f"{decision.topic}: {decision.choice}" if decision.topic else decision.choice,
            source="decisions",
            projection_priority=compute_priority(
                ConstraintKind.DECISION, ConstraintSeverity.REJECT, None, target_scopes
            ),
        ))

    return constraints


def _resolve_anchors(
    governor_dir: Path,
    target_scopes: list[str] | None = None,
) -> list[ResolvedConstraint]:
    """Layer 10: Resolve continuity anchor constraints."""
    from .continuity import AnchorRegistry, Severity as ContinuitySeverity

    constraints: list[ResolvedConstraint] = []
    path = governor_dir / "continuity" / "anchors.json"

    if not path.exists():
        return constraints

    registry = AnchorRegistry.load(path)

    for anchor in registry.all():
        # Map continuity severity to constraint severity
        if anchor.severity == ContinuitySeverity.REJECT:
            sev = ConstraintSeverity.REJECT
        elif anchor.severity == ContinuitySeverity.CORRECT:
            sev = ConstraintSeverity.WARN
        else:
            sev = ConstraintSeverity.WARN

        # Build pattern string
        patterns: list[str] = []
        if anchor.required_patterns:
            patterns.extend(f"require:{p}" for p in anchor.required_patterns)
        if anchor.forbidden_patterns:
            patterns.extend(f"forbid:{p}" for p in anchor.forbidden_patterns)
        pattern_str = "; ".join(patterns) if patterns else None

        cid = make_constraint_id(
            "anchor", "anchors", "", pattern_str or "", anchor.description
        )
        constraints.append(ResolvedConstraint(
            constraint_id=cid,
            kind=ConstraintKind.ANCHOR,
            severity=sev,
            description=anchor.description,
            pattern=pattern_str,
            source="anchors",
            projection_priority=compute_priority(
                ConstraintKind.ANCHOR, sev, None, target_scopes
            ),
        ))

    return constraints


def _resolve_spine(
    governor_dir: Path,
    target_scopes: list[str] | None = None,
) -> list[ResolvedConstraint]:
    """Layer 6: Resolve spine (structure lock) constraints."""
    from .spine import SpineManager

    constraints: list[ResolvedConstraint] = []
    manager = SpineManager(governor_dir.parent)
    spine = manager.active_spine()

    if not spine:
        return constraints

    # Required files
    for path, status in spine.structure.get("files", {}).items():
        if status == "required":
            if not _scope_matches(path, target_scopes):
                continue
            cid = make_constraint_id("spine_rule", "spine", path, "", f"required file: {path}")
            constraints.append(ResolvedConstraint(
                constraint_id=cid,
                kind=ConstraintKind.SPINE_RULE,
                severity=ConstraintSeverity.REJECT,
                description=f"Required file: {path} (cannot be deleted)",
                scope=path,
                source="spine",
                projection_priority=compute_priority(
                    ConstraintKind.SPINE_RULE, ConstraintSeverity.REJECT, path, target_scopes
                ),
            ))

    # Required directories
    for dir_path, status in spine.structure.get("directories", {}).items():
        if status == "required":
            if not _scope_matches(dir_path, target_scopes):
                continue
            cid = make_constraint_id("spine_rule", "spine", dir_path, "", f"required dir: {dir_path}")
            constraints.append(ResolvedConstraint(
                constraint_id=cid,
                kind=ConstraintKind.SPINE_RULE,
                severity=ConstraintSeverity.REJECT,
                description=f"Required directory: {dir_path}",
                scope=dir_path,
                source="spine",
                projection_priority=compute_priority(
                    ConstraintKind.SPINE_RULE, ConstraintSeverity.REJECT, dir_path, target_scopes
                ),
            ))

    # Forbidden paths
    for pattern in spine.structure.get("forbidden_paths", []):
        cid = make_constraint_id("spine_rule", "spine", "", pattern, f"forbidden: {pattern}")
        constraints.append(ResolvedConstraint(
            constraint_id=cid,
            kind=ConstraintKind.SPINE_RULE,
            severity=ConstraintSeverity.REJECT,
            description=f"Forbidden path pattern: {pattern}",
            pattern=pattern,
            source="spine",
            projection_priority=compute_priority(
                ConstraintKind.SPINE_RULE, ConstraintSeverity.REJECT, None, target_scopes
            ),
        ))

    return constraints


def _resolve_invariants(
    governor_dir: Path,
    target_scopes: list[str] | None = None,
) -> list[ResolvedConstraint]:
    """Layer 7: Resolve invariant store constraints."""
    from .invariant_store import InvariantStore

    constraints: list[ResolvedConstraint] = []
    store = InvariantStore(governor_dir.parent)

    for spec in store.list_all():
        if not spec.enabled:
            continue

        # Build description
        if spec.kind == "test":
            desc = f"Test must pass: {spec.params.get('command', '?')}"
        elif spec.kind == "file-exists":
            path = spec.params.get("path", "?")
            if not _scope_matches(path, target_scopes):
                continue
            desc = f"File must exist: {path}"
        elif spec.kind == "dir-exists":
            path = spec.params.get("path", "?")
            if not _scope_matches(path, target_scopes):
                continue
            desc = f"Directory must exist: {path}"
        elif spec.kind == "forbidden":
            desc = f"Forbidden pattern: {spec.params.get('pattern', '?')}"
        elif spec.kind == "no-secrets":
            desc = "No secrets in files"
        elif spec.kind == "max-file-size":
            desc = f"Max file size: {spec.params.get('max_kb', '?')}KB"
        else:
            desc = f"Invariant: {spec.kind}"

        sev = ConstraintSeverity.REJECT if spec.on_violation == "block" else ConstraintSeverity.WARN

        cid = make_constraint_id("invariant", "invariants", "", spec.id, desc)
        constraints.append(ResolvedConstraint(
            constraint_id=cid,
            kind=ConstraintKind.INVARIANT,
            severity=sev,
            description=desc,
            source="invariants",
            projection_priority=compute_priority(
                ConstraintKind.INVARIANT, sev, None, target_scopes
            ),
        ))

    return constraints


def _resolve_scars(
    governor_dir: Path,
    target_scopes: list[str] | None = None,
) -> list[ResolvedConstraint]:
    """Layer 8: Resolve scar constraints (with classification)."""
    from .scars import ScarLedger, ScarConfig

    constraints: list[ResolvedConstraint] = []

    try:
        ledger = ScarLedger(ScarConfig())
        ledger_path = governor_dir / "scars"
        if not ledger_path.exists():
            return constraints
        # Attempt to load scars from the governor directory
        scars_file = governor_dir / "scars" / "scars.json"
        if scars_file.exists():
            import json as _json
            data = _json.loads(scars_file.read_text())
            from .scars import Scar
            for item in data:
                scar = Scar.from_dict(item)
                ledger._scars[scar.scar_id] = scar
    except Exception:
        return constraints

    for scar in ledger.list_scars():
        if not _scope_matches(scar.region, target_scopes):
            continue

        scar_class = classify_scar(scar.stiffness)

        # Hard scars always reject, others warn
        if scar_class == ScarClass.HARD:
            sev = ConstraintSeverity.REJECT
        else:
            sev = ConstraintSeverity.WARN

        cid = make_constraint_id("scar", "scars", scar.region, "", scar.description)
        constraints.append(ResolvedConstraint(
            constraint_id=cid,
            kind=ConstraintKind.SCAR,
            severity=sev,
            description=f"[{scar_class.value.upper()}] {scar.region}: {scar.description}" if scar.description else f"[{scar_class.value.upper()}] Scar on {scar.region}",
            scope=scar.region,
            source="scars",
            projection_priority=compute_priority(
                ConstraintKind.SCAR, sev, scar.region, target_scopes, is_scar_adjacent=True
            ),
        ))

    return constraints


def _resolve_security(
    target_scopes: list[str] | None = None,
) -> list[ResolvedConstraint]:
    """Layer 11: Resolve security pattern constraints."""
    from .security import (
        SECRET_PATTERNS,
        SQL_INJECTION_PATTERNS,
        COMMAND_INJECTION_PATTERNS,
        XSS_PATTERNS,
    )

    constraints: list[ResolvedConstraint] = []
    categories = [
        ("secret_leak", SECRET_PATTERNS, "Do not leak secrets"),
        ("sql_injection", SQL_INJECTION_PATTERNS, "No SQL injection"),
        ("command_injection", COMMAND_INJECTION_PATTERNS, "No command injection"),
        ("xss", XSS_PATTERNS, "No cross-site scripting"),
    ]

    for category, patterns, category_desc in categories:
        if not patterns:
            continue
        cid = make_constraint_id("security_pattern", "security", "", category, category_desc)
        constraints.append(ResolvedConstraint(
            constraint_id=cid,
            kind=ConstraintKind.SECURITY_PATTERN,
            severity=ConstraintSeverity.REJECT,
            description=f"{category_desc} ({len(patterns)} patterns)",
            pattern=category,
            source="security",
            projection_priority=compute_priority(
                ConstraintKind.SECURITY_PATTERN, ConstraintSeverity.REJECT, None, target_scopes
            ),
        ))

    return constraints


def _resolve_overrides(
    governor_dir: Path,
    constraints: list[ResolvedConstraint],
    target_scopes: list[str] | None = None,
    profile: str | None = None,
    envelope: str = "strict",
) -> tuple[list[OverrideWarrant], list[QuorumUnsatisfiedReceipt]]:
    """Apply active overrides as warrants to scar constraints.

    Converts OverrideReceipt entries from the OverrideManager into
    OverrideWarrant entries and marks matching constraints as overruled.
    """
    from .overrides import OverrideManager, create_override_manager

    warrants: list[OverrideWarrant] = []
    quorum_failures: list[QuorumUnsatisfiedReceipt] = []

    try:
        manager = create_override_manager(governor_dir)
        active = manager.list_active()
    except Exception:
        return warrants, quorum_failures

    for override in active:
        warrant = OverrideWarrant(
            warrant_id=override.id,
            invoked_by=override.operator,
            reason=override.reason,
            scope=override.scope,
            constraints_overruled=[],
            expires_at=datetime.fromisoformat(override.expires_at),
        )

        # Find scar constraints that this override could apply to
        for c in constraints:
            if c.kind != ConstraintKind.SCAR:
                continue
            if c.overruled_by is not None:
                continue

            # Check scope match
            if c.scope and override.scope:
                matched = any(
                    fnmatch.fnmatch(c.scope, s) or fnmatch.fnmatch(s, c.scope)
                    for s in override.scope
                )
                if not matched:
                    continue

            # Check scar class — hard scars cannot be overridden
            # Parse scar class from description
            scar_class = ScarClass.SOFT  # default
            desc_upper = c.description.upper()
            if "[HARD]" in desc_upper:
                scar_class = ScarClass.HARD
            elif "[PROCEDURAL]" in desc_upper:
                scar_class = ScarClass.PROCEDURAL

            quorum_result = check_warrant_quorum(warrant, scar_class, profile, envelope)
            if quorum_result:
                quorum_result.constraint_id = c.constraint_id
                quorum_failures.append(quorum_result)
                continue

            c.overruled_by = warrant.warrant_id
            warrant.constraints_overruled.append(c.constraint_id)

        if warrant.constraints_overruled:
            warrants.append(warrant)

    return warrants, quorum_failures


# ---------------------------------------------------------------------------
# Prompt Prefix Rendering
# ---------------------------------------------------------------------------


def render_prompt_prefix(block: ConstraintBlock) -> str:
    """Render a ConstraintBlock as a human-readable prompt prefix."""
    lines: list[str] = []
    lines.append(f"[GOVERNOR CONSTRAINTS — hash:{block.content_hash[:12]}]")
    lines.append("")

    if block.intent:
        lines.append(f"INTENT: {block.intent}")
    if block.scope:
        lines.append(f"SCOPE: {', '.join(block.scope)}")
    if block.mode:
        lines.append(f"MODE: {block.mode}")
    lines.append(f"ENVELOPE: {block.envelope}")
    if block.profile:
        lines.append(f"PROFILE: {block.profile}")
    lines.append("")

    if block.exploratory_warning:
        lines.append("WARNING: Exploratory mode — receipt requirements relaxed")
        lines.append("")

    # Hard constraints
    hard = block.hard_constraints
    # Separate security from other hard constraints
    non_security_hard = [c for c in hard if c.kind != ConstraintKind.SECURITY_PATTERN]
    security = block.security_constraints

    if non_security_hard:
        lines.append(f"HARD CONSTRAINTS (violation = rejection):")
        for c in sorted(non_security_hard, key=lambda x: -x.projection_priority):
            lines.append(f"- {c.kind.value.title()}: {c.description}")
        lines.append("")

    # Soft constraints
    soft = block.soft_constraints
    if soft:
        lines.append(f"SOFT CONSTRAINTS (violation = warning):")
        for c in sorted(soft, key=lambda x: -x.projection_priority):
            lines.append(f"- {c.kind.value.title()}: {c.description}")
        lines.append("")

    # Security patterns
    if security:
        lines.append(f"SECURITY (known patterns to avoid):")
        for c in security:
            lines.append(f"- {c.description}")
        lines.append("")

    # Overruled constraints
    overruled = block.overruled_constraints
    if overruled:
        for w in block.warrants:
            remaining_s = w.remaining_seconds
            if remaining_s > 3600:
                time_str = f"{remaining_s / 3600:.0f}h{(remaining_s % 3600) / 60:.0f}m"
            elif remaining_s > 60:
                time_str = f"{remaining_s / 60:.0f}m"
            else:
                time_str = f"{remaining_s:.0f}s"

            lines.append(
                f"OVERRULED CONSTRAINTS (warrant {w.warrant_id[:8]}, "
                f"expires {w.expires_at.isoformat()[:16]}Z):"
            )
            for c in overruled:
                if c.overruled_by == w.warrant_id:
                    lines.append(f"- {c.kind.value.title()}: {c.description}")
                    lines.append(f"  Overruled by: {w.invoked_by}, reason: \"{w.reason}\"")
            lines.append("")

    total = len(block.constraints)
    sources = len(block.sources)
    lines.append(f"[END CONSTRAINTS — {total} resolved, {sources} sources]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """Cached constraint compilation result."""

    cache_key: str
    block: ConstraintBlock
    nearest_warrant_expiry: datetime | None = None

    @property
    def is_valid(self) -> bool:
        if self.nearest_warrant_expiry and datetime.now(timezone.utc) >= self.nearest_warrant_expiry:
            return False
        return True


class ConstraintCache:
    """In-memory cache for compiled constraint blocks."""

    def __init__(self, max_size: int = 64) -> None:
        self._entries: dict[str, CacheEntry] = {}
        self._max_size = max_size

    def get(self, key: str) -> ConstraintBlock | None:
        entry = self._entries.get(key)
        if entry and entry.is_valid:
            return entry.block
        if entry:
            del self._entries[key]
        return None

    def put(self, key: str, block: ConstraintBlock) -> None:
        if len(self._entries) >= self._max_size:
            # Evict oldest
            oldest_key = next(iter(self._entries))
            del self._entries[oldest_key]

        nearest_expiry: datetime | None = None
        for w in block.warrants:
            if nearest_expiry is None or w.expires_at < nearest_expiry:
                nearest_expiry = w.expires_at

        self._entries[key] = CacheEntry(
            cache_key=key,
            block=block,
            nearest_warrant_expiry=nearest_expiry,
        )

    def invalidate(self) -> None:
        self._entries.clear()

    def size(self) -> int:
        return len(self._entries)


def _compute_cache_key(
    intent: str | None,
    scope: list[str] | None,
    mode: str | None,
    envelope: str,
    governor_dir: Path,
) -> str:
    """Compute the cache key for a compilation request."""
    parts = [
        str(intent or ""),
        ",".join(sorted(scope or [])),
        str(mode or ""),
        envelope,
        str(governor_dir),
    ]
    content = "|".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()[:24]


# Module-level cache
_cache = ConstraintCache()


# ---------------------------------------------------------------------------
# Main Compilation Function
# ---------------------------------------------------------------------------


def compile_constraints(
    intent: str | None = None,
    scope: str | list[str] | None = None,
    mode: str | None = None,
    governor_dir: Path | None = None,
    use_cache: bool = True,
) -> ConstraintBlock:
    """Resolve all applicable constraints for intent + scope.

    Pure function. No side effects. No backend calls.
    Deterministic on inputs (modulo ledger state).

    Args:
        intent: User-declared intent (e.g., 'production', 'hotfix').
        scope: File/directory scope (glob patterns).
        mode: Domain mode (code, fiction, nonfiction, ops).
        governor_dir: Path to .governor/ directory.
        use_cache: Whether to use the in-memory cache.

    Returns:
        ConstraintBlock with all resolved constraints.
    """
    if governor_dir is None:
        governor_dir = Path(".governor")

    # Normalize scope
    target_scopes: list[str] | None = None
    if scope:
        if isinstance(scope, str):
            target_scopes = [scope]
        else:
            target_scopes = list(scope)

    # Check cache
    envelope_str = "strict"  # will be overridden below
    if use_cache:
        cache_key = _compute_cache_key(intent, target_scopes, mode, "?", governor_dir)
        cached = _cache.get(cache_key)
        if cached:
            return cached

    # Resolve layers
    all_constraints: list[ResolvedConstraint] = []
    sources: list[ConstraintSource] = []

    # Layer 1: Envelope
    envelope_str, envelope_constraints = _resolve_envelope(governor_dir)
    if envelope_constraints:
        all_constraints.extend(envelope_constraints)
        sources.append(ConstraintSource(
            subsystem="envelope",
            count=len(envelope_constraints),
            hash=_hash_items([c.to_dict() for c in envelope_constraints]),
        ))

    # Layer 2: Profile
    profile_name, profile_constraints = _resolve_profile(governor_dir)
    if profile_constraints:
        all_constraints.extend(profile_constraints)
        sources.append(ConstraintSource(
            subsystem="profiles",
            count=len(profile_constraints),
            hash=_hash_items([c.to_dict() for c in profile_constraints]),
        ))

    # Layer 6: Spine
    spine_constraints = _resolve_spine(governor_dir, target_scopes)
    if spine_constraints:
        all_constraints.extend(spine_constraints)
        sources.append(ConstraintSource(
            subsystem="spine",
            count=len(spine_constraints),
            hash=_hash_items([c.to_dict() for c in spine_constraints]),
        ))

    # Layer 7: Invariants
    invariant_constraints = _resolve_invariants(governor_dir, target_scopes)
    if invariant_constraints:
        all_constraints.extend(invariant_constraints)
        sources.append(ConstraintSource(
            subsystem="invariants",
            count=len(invariant_constraints),
            hash=_hash_items([c.to_dict() for c in invariant_constraints]),
        ))

    # Layer 8: Scars
    scar_constraints = _resolve_scars(governor_dir, target_scopes)
    if scar_constraints:
        all_constraints.extend(scar_constraints)
        sources.append(ConstraintSource(
            subsystem="scars",
            count=len(scar_constraints),
            hash=_hash_items([c.to_dict() for c in scar_constraints]),
        ))

    # Layer 9: Decisions
    decision_constraints = _resolve_decisions(governor_dir, target_scopes)
    if decision_constraints:
        all_constraints.extend(decision_constraints)
        sources.append(ConstraintSource(
            subsystem="decisions",
            count=len(decision_constraints),
            hash=_hash_items([c.to_dict() for c in decision_constraints]),
        ))

    # Layer 10: Anchors
    anchor_constraints = _resolve_anchors(governor_dir, target_scopes)
    if anchor_constraints:
        all_constraints.extend(anchor_constraints)
        sources.append(ConstraintSource(
            subsystem="anchors",
            count=len(anchor_constraints),
            hash=_hash_items([c.to_dict() for c in anchor_constraints]),
        ))

    # Layer 11: Security
    security_constraints = _resolve_security(target_scopes)
    if security_constraints:
        all_constraints.extend(security_constraints)
        sources.append(ConstraintSource(
            subsystem="security",
            count=len(security_constraints),
            hash=_hash_items([c.to_dict() for c in security_constraints]),
        ))

    # Apply overrides (warrants)
    warrants, quorum_failures = _resolve_overrides(
        governor_dir, all_constraints, target_scopes, profile_name, envelope_str
    )

    # Compute content hash
    content_hash = _content_hash(all_constraints)

    # Detect exploratory warning
    exploratory_warning = envelope_str == "exploratory"

    block = ConstraintBlock(
        constraints=all_constraints,
        sources=sources,
        content_hash=content_hash,
        compiled_at=datetime.now(timezone.utc),
        intent=intent,
        scope=target_scopes,
        mode=mode,
        envelope=envelope_str,
        profile=profile_name,
        warrants=warrants,
        quorum_failures=quorum_failures,
        exploratory_warning=exploratory_warning,
    )

    # Cache the result
    if use_cache:
        cache_key = _compute_cache_key(intent, target_scopes, mode, envelope_str, governor_dir)
        _cache.put(cache_key, block)

    return block


# ---------------------------------------------------------------------------
# Constraint Diff
# ---------------------------------------------------------------------------


@dataclass
class ConstraintDiff:
    """Difference between two constraint compilations."""

    added: list[ResolvedConstraint]
    removed: list[ResolvedConstraint]
    changed: list[tuple[ResolvedConstraint, ResolvedConstraint]]
    left_hash: str
    right_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": [c.to_dict() for c in self.added],
            "removed": [c.to_dict() for c in self.removed],
            "changed": [
                {"before": a.to_dict(), "after": b.to_dict()}
                for a, b in self.changed
            ],
            "left_hash": self.left_hash,
            "right_hash": self.right_hash,
        }

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


def diff_constraints(left: ConstraintBlock, right: ConstraintBlock) -> ConstraintDiff:
    """Diff two constraint compilations."""
    left_by_id = {c.constraint_id: c for c in left.constraints}
    right_by_id = {c.constraint_id: c for c in right.constraints}

    added = [c for cid, c in right_by_id.items() if cid not in left_by_id]
    removed = [c for cid, c in left_by_id.items() if cid not in right_by_id]
    changed = []

    for cid in left_by_id:
        if cid in right_by_id:
            lc = left_by_id[cid]
            rc = right_by_id[cid]
            if (
                lc.severity != rc.severity
                or lc.overruled_by != rc.overruled_by
                or lc.description != rc.description
            ):
                changed.append((lc, rc))

    return ConstraintDiff(
        added=added,
        removed=removed,
        changed=changed,
        left_hash=left.content_hash,
        right_hash=right.content_hash,
    )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def get_cache() -> ConstraintCache:
    """Get the module-level cache (for testing/inspection)."""
    return _cache


def clear_cache() -> None:
    """Clear the module-level cache."""
    _cache.invalidate()
