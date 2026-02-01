"""
Grounding Audit Pipeline: Closed-loop hallucination detection and prevention.

Connects the truth ledger to hallucination detection as a governor.
Every claim gets audited; failures are classified by type and fed back
to tighten gating rules.

Core loop:
  1. Assertion enters pipeline
  2. Detection signals computed (evidence count, independence, novelty, etc.)
  3. Failure modes classified (NO_EVIDENCE, CITE_DRIFT, SPECIOUS_PRECISION, etc.)
  4. Audit decision issued (ALLOW_HARD, DOWNGRADE_SOFT, BLOCK, NEEDS_MORE_WORK)
  5. Adaptive thresholds tuned from audit outcomes

Key insight: hallucination is not "a bad answer" — it is a failed commit
or a leak. The ledger records HOW it failed, and the governor tightens
gates specifically against the failure modes actually observed.

Toggle via config.toml:
    [audit]
    grounding_audit = true
    adaptive_thresholds = true
    pre_commit_gate = true
    post_commit_review = true
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import json
import uuid


# =============================================================================
# Enums
# =============================================================================


class GroundingStatus(str, Enum):
    """Result of a grounding audit."""

    GROUNDED = "grounded"
    """Claim has sufficient evidence and meets all requirements."""

    WEAK = "weak"
    """Evidence exists but is insufficient (quantity, independence, freshness)."""

    UNGROUNDED = "ungrounded"
    """No adequate evidence. Claim is floating."""

    CONTRADICTED = "contradicted"
    """Counter-evidence exists that invalidates the claim."""

    UNKNOWN = "unknown"
    """Cannot determine grounding status (use sparingly)."""

    @property
    def is_problematic(self) -> bool:
        return self in {
            GroundingStatus.UNGROUNDED,
            GroundingStatus.CONTRADICTED,
        }

    @property
    def severity_weight(self) -> float:
        """Weight for adaptive threshold tuning."""
        return {
            GroundingStatus.GROUNDED: 0.0,
            GroundingStatus.WEAK: 0.5,
            GroundingStatus.UNGROUNDED: 1.0,
            GroundingStatus.CONTRADICTED: 1.5,
            GroundingStatus.UNKNOWN: 0.3,
        }[self]


class AuditStage(str, Enum):
    """When the audit runs in the pipeline."""

    PRE_COMMIT = "pre_commit"
    """Synchronous gate before claim enters ledger as HARD."""

    POST_COMMIT = "post_commit"
    """Asynchronous review after commit (same turn)."""

    PERIODIC = "periodic"
    """TTL enforcement / revalidation of stale claims."""

    INCIDENT = "incident"
    """Post-fact investigation triggered by contradiction or user flag."""

    @property
    def leak_weight(self) -> float:
        """Weight for adaptive tuning. Later detection = worse leak."""
        return {
            AuditStage.PRE_COMMIT: 1.0,   # Good catch
            AuditStage.POST_COMMIT: 3.0,   # Bad leak
            AuditStage.PERIODIC: 2.0,      # Stale leak
            AuditStage.INCIDENT: 5.0,      # Worst leak
        }[self]


class FailureMode(str, Enum):
    """Learnable failure type classifications."""

    NO_EVIDENCE = "no_evidence"
    """Asserted with empty evidence refs."""

    WEAK_EVIDENCE = "weak_evidence"
    """Evidence exists but strength insufficient for claim scope."""

    CITE_DRIFT = "cite_drift"
    """Citations don't actually support the asserted proposition."""

    SOURCE_ALIASING = "source_aliasing"
    """False independence — multiple supports from same origin."""

    TEMPORAL_STALENESS = "temporal_staleness"
    """Expired or too old for the volatility class."""

    ENTAILMENT_OVERREACH = "entailment_overreach"
    """Evidence supports a weaker claim than what was asserted."""

    SPECIOUS_PRECISION = "specious_precision"
    """Numbers/dates invented without source support."""

    ENTITY_CONFLATION = "entity_conflation"
    """Ontology swap — person/org/version conflated."""

    COUNTEREVIDENCE_IGNORED = "counterevidence_ignored"
    """Known contradicting evidence was not addressed."""

    TOOL_MISREAD = "tool_misread"
    """Tool output was misinterpreted."""

    PROMPT_INJECTION = "prompt_injection"
    """Untrusted text was treated as instruction or fact."""

    WRONG_EVIDENCE_TYPE = "wrong_evidence_type"
    """Evidence exists but wrong kind for the claim type."""

    NONE = "none"
    """No failure detected (claim is grounded)."""


class AuditDecision(str, Enum):
    """Decision issued by the audit pipeline."""

    ALLOW_HARD = "allow_hard"
    """Claim meets all requirements for HARD commitment."""

    DOWNGRADE_SOFT = "downgrade_soft"
    """Claim doesn't meet HARD requirements but can be SOFT."""

    BLOCK = "block"
    """Claim fails requirements and must not be committed."""

    NEEDS_MORE_WORK = "needs_more_work"
    """Requirements unmet but potentially fixable (schedule retriever/falsifier)."""


class AuditSeverity(str, Enum):
    """Severity of audit findings."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def numeric(self) -> int:
        return {"low": 1, "medium": 2, "high": 3}[self.value]


class AssertionScope(str, Enum):
    """Scope of an assertion."""

    INTERNAL_PREMISE = "internal_premise"
    """Used as internal reasoning step."""

    USER_OUTPUT = "user_output"
    """Presented to the user as output."""

    ACTION_TRIGGER = "action_trigger"
    """Used to trigger an action (file write, command, etc.)."""

    @property
    def risk_multiplier(self) -> float:
        """Higher scope = more dangerous if wrong."""
        return {
            AssertionScope.INTERNAL_PREMISE: 1.0,
            AssertionScope.USER_OUTPUT: 1.5,
            AssertionScope.ACTION_TRIGGER: 2.0,
        }[self]


class ClaimRisk(str, Enum):
    """Risk level of a claim."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def k_required(self) -> int:
        """Minimum independent evidence items."""
        return {"low": 1, "medium": 2, "high": 3}[self.value]

    @property
    def independence_threshold(self) -> float:
        return {"low": 0.6, "medium": 0.7, "high": 0.7}[self.value]


class AuditResolution(str, Enum):
    """How a problematic audit was resolved."""

    RETRACTED = "retracted"
    """Claim was withdrawn."""

    DOWNGRADED = "downgraded"
    """Claim was downgraded from HARD to SOFT."""

    FIXED = "fixed"
    """Additional evidence was provided and claim now passes."""

    LEFT_OPEN = "left_open"
    """Unresolved — flagged for review."""


# =============================================================================
# Detection Signals (Feature Vector)
# =============================================================================


@dataclass
class DetectionSignals:
    """
    Feature vector computed for each assertion during audit.

    These signals are used for failure mode classification
    and stored with the audit record for adaptive tuning.
    """

    # Evidence quality
    evidence_count: int = 0
    evidence_strength_sum: float = 0.0
    evidence_kinds: list[str] = field(default_factory=list)

    # Independence
    independence_score: float = 0.0  # Min pairwise independence [0, 1]
    source_aliasing_score: float = 0.0  # How much evidence shares origin [0, 1]

    # Coverage
    citation_coverage: float = 0.0  # Fraction of claim supported by citations [0, 1]

    # Novelty
    novel_entity_count: int = 0  # Entities not in evidence
    novel_number_count: int = 0  # Numbers/dates not in evidence

    # Precision
    specious_precision_score: float = 0.0  # Suspicious exactness [0, 1]

    # Temporal
    freshness_age_seconds: float = 0.0  # Age of most recent evidence
    is_stale: bool = False

    # Confidence
    confidence_language_score: float = 0.0  # "definitely/clearly" presence [0, 1]
    confidence_evidence_gap: float = 0.0  # confidence_language - evidence_strength

    # Stability
    cross_run_instability: float = 0.0  # How much claim changes across rounds [0, 1]

    # Tool use
    tool_misread_risk: float = 0.0  # Compression ratio risk [0, 1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_count": self.evidence_count,
            "evidence_strength_sum": self.evidence_strength_sum,
            "evidence_kinds": self.evidence_kinds,
            "independence_score": self.independence_score,
            "source_aliasing_score": self.source_aliasing_score,
            "citation_coverage": self.citation_coverage,
            "novel_entity_count": self.novel_entity_count,
            "novel_number_count": self.novel_number_count,
            "specious_precision_score": self.specious_precision_score,
            "freshness_age_seconds": self.freshness_age_seconds,
            "is_stale": self.is_stale,
            "confidence_language_score": self.confidence_language_score,
            "confidence_evidence_gap": self.confidence_evidence_gap,
            "cross_run_instability": self.cross_run_instability,
            "tool_misread_risk": self.tool_misread_risk,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectionSignals":
        return cls(
            evidence_count=data.get("evidence_count", 0),
            evidence_strength_sum=data.get("evidence_strength_sum", 0.0),
            evidence_kinds=data.get("evidence_kinds", []),
            independence_score=data.get("independence_score", 0.0),
            source_aliasing_score=data.get("source_aliasing_score", 0.0),
            citation_coverage=data.get("citation_coverage", 0.0),
            novel_entity_count=data.get("novel_entity_count", 0),
            novel_number_count=data.get("novel_number_count", 0),
            specious_precision_score=data.get("specious_precision_score", 0.0),
            freshness_age_seconds=data.get("freshness_age_seconds", 0.0),
            is_stale=data.get("is_stale", False),
            confidence_language_score=data.get("confidence_language_score", 0.0),
            confidence_evidence_gap=data.get("confidence_evidence_gap", 0.0),
            cross_run_instability=data.get("cross_run_instability", 0.0),
            tool_misread_risk=data.get("tool_misread_risk", 0.0),
        )


# =============================================================================
# Grounding Audit Record
# =============================================================================


@dataclass
class GroundingAudit:
    """
    Record of a grounding evaluation for an assertion.

    Append-only. Each assertion can have 0..N audits
    (pre-commit, post-commit, periodic, incident).
    """

    audit_id: str
    assertion_id: str  # What was audited
    stage: AuditStage
    status: GroundingStatus
    decision: AuditDecision

    # Failure analysis
    failure_modes: list[FailureMode] = field(default_factory=list)
    severity: AuditSeverity = AuditSeverity.LOW

    # Detection signals snapshot
    signals: DetectionSignals = field(default_factory=DetectionSignals)

    # Resolution
    resolution: AuditResolution | None = None
    notes: str = ""

    # Counter-evidence
    counterevidence_refs: list[str] = field(default_factory=list)

    # Provenance
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "audit_pipeline"  # Agent/tool that ran the audit

    def __post_init__(self):
        if not self.failure_modes:
            self.failure_modes = []

    @property
    def is_clean(self) -> bool:
        """Did the audit find no issues?"""
        return self.status == GroundingStatus.GROUNDED

    @property
    def is_problematic(self) -> bool:
        return self.status.is_problematic

    @property
    def leak_score(self) -> float:
        """Severity-weighted leak score for adaptive tuning."""
        return self.status.severity_weight * self.stage.leak_weight * self.severity.numeric

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "assertion_id": self.assertion_id,
            "stage": self.stage.value,
            "status": self.status.value,
            "decision": self.decision.value,
            "failure_modes": [f.value for f in self.failure_modes],
            "severity": self.severity.value,
            "signals": self.signals.to_dict(),
            "resolution": self.resolution.value if self.resolution else None,
            "notes": self.notes,
            "counterevidence_refs": self.counterevidence_refs,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "is_clean": self.is_clean,
            "leak_score": self.leak_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundingAudit":
        return cls(
            audit_id=data["audit_id"],
            assertion_id=data["assertion_id"],
            stage=AuditStage(data["stage"]),
            status=GroundingStatus(data["status"]),
            decision=AuditDecision(data["decision"]),
            failure_modes=[FailureMode(f) for f in data.get("failure_modes", [])],
            severity=AuditSeverity(data.get("severity", "low")),
            signals=DetectionSignals.from_dict(data.get("signals", {})),
            resolution=(
                AuditResolution(data["resolution"]) if data.get("resolution") else None
            ),
            notes=data.get("notes", ""),
            counterevidence_refs=data.get("counterevidence_refs", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by", "audit_pipeline"),
        )


# =============================================================================
# Policy Entry (Thresholds per claim type)
# =============================================================================


@dataclass
class PolicyEntry:
    """
    Gating thresholds for a specific (claim_type, risk, scope) combination.

    These are the knobs the governor reads and the adaptive tuner adjusts.
    """

    # Key
    claim_type: str  # e.g. "static_fact", "code", "volatile_fact", etc.
    risk: ClaimRisk = ClaimRisk.LOW
    scope: AssertionScope = AssertionScope.INTERNAL_PREMISE

    # Evidence requirements
    k_required: int = 1  # Min independent evidence items
    independence_threshold: float = 0.6  # Min pairwise independence
    min_evidence_strength: float = 0.7  # Min sum of evidence strengths

    # Novelty limits
    max_novel_numbers: int = 1  # Novel numbers before downgrade
    max_specious_precision: float = 0.6  # Specious precision threshold

    # Temporal
    freshness_max_seconds: float = 0.0  # 0 = no freshness requirement
    ttl_seconds: float = 0.0  # 0 = no TTL

    # Rounds
    stabilization_rounds: int = 1  # Consecutive stable rounds required

    # Evidence type requirements (Layer 3)
    required_evidence_kinds: set[str] | None = None  # None = any type accepted

    @property
    def key(self) -> str:
        return f"{self.claim_type}:{self.risk.value}:{self.scope.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_type": self.claim_type,
            "risk": self.risk.value,
            "scope": self.scope.value,
            "k_required": self.k_required,
            "independence_threshold": self.independence_threshold,
            "min_evidence_strength": self.min_evidence_strength,
            "max_novel_numbers": self.max_novel_numbers,
            "max_specious_precision": self.max_specious_precision,
            "freshness_max_seconds": self.freshness_max_seconds,
            "ttl_seconds": self.ttl_seconds,
            "stabilization_rounds": self.stabilization_rounds,
            "required_evidence_kinds": sorted(self.required_evidence_kinds) if self.required_evidence_kinds else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyEntry":
        return cls(
            claim_type=data["claim_type"],
            risk=ClaimRisk(data.get("risk", "low")),
            scope=AssertionScope(data.get("scope", "internal_premise")),
            k_required=data.get("k_required", 1),
            independence_threshold=data.get("independence_threshold", 0.6),
            min_evidence_strength=data.get("min_evidence_strength", 0.7),
            max_novel_numbers=data.get("max_novel_numbers", 1),
            max_specious_precision=data.get("max_specious_precision", 0.6),
            freshness_max_seconds=data.get("freshness_max_seconds", 0.0),
            ttl_seconds=data.get("ttl_seconds", 0.0),
            stabilization_rounds=data.get("stabilization_rounds", 1),
            required_evidence_kinds=set(data["required_evidence_kinds"]) if data.get("required_evidence_kinds") else None,
        )


# =============================================================================
# Policy Store (Threshold Matrix + Adaptive Tuning)
# =============================================================================


def _default_policies() -> dict[str, PolicyEntry]:
    """Build the default policy matrix."""
    policies = {}

    # --- STATIC_FACT ---
    for risk, scope in _risk_scope_combos():
        entry = PolicyEntry(
            claim_type="static_fact",
            risk=risk,
            scope=scope,
            k_required=risk.k_required,
            independence_threshold=risk.independence_threshold,
            min_evidence_strength=0.7 * risk.k_required,
            max_novel_numbers=max(0, 2 - risk.k_required),
            max_specious_precision=0.7 - 0.1 * risk.k_required,
            ttl_seconds=180 * 86400 / (risk.k_required ** 2),  # 180d/45d/20d
            stabilization_rounds=risk.k_required,
            required_evidence_kinds={"web_source", "document", "url"},
        )
        policies[entry.key] = entry

    # --- VOLATILE_FACT ---
    for risk, scope in _risk_scope_combos():
        fresh = {ClaimRisk.LOW: 21600, ClaimRisk.MEDIUM: 10800, ClaimRisk.HIGH: 3600}
        ttl = {ClaimRisk.LOW: 21600, ClaimRisk.MEDIUM: 10800, ClaimRisk.HIGH: 3600}
        entry = PolicyEntry(
            claim_type="volatile_fact",
            risk=risk,
            scope=scope,
            k_required=risk.k_required,
            independence_threshold=risk.independence_threshold,
            min_evidence_strength=0.8 * risk.k_required,
            max_novel_numbers=max(0, 1 - (risk.k_required - 1)),
            max_specious_precision=0.6 - 0.1 * risk.k_required,
            freshness_max_seconds=fresh[risk],
            ttl_seconds=ttl[risk],
            stabilization_rounds=risk.k_required,
            required_evidence_kinds={"live_retrieval", "web_source"},
        )
        policies[entry.key] = entry

    # --- CODE ---
    for risk, scope in _risk_scope_combos():
        entry = PolicyEntry(
            claim_type="code",
            risk=risk,
            scope=scope,
            k_required=1,  # Code verified by test/lint, not quorum
            independence_threshold=0.6,
            min_evidence_strength=0.9,
            max_novel_numbers=max(0, 2 - risk.k_required),
            max_specious_precision=0.6 - 0.1 * risk.k_required,
            ttl_seconds={ClaimRisk.LOW: 30 * 86400, ClaimRisk.MEDIUM: 14 * 86400, ClaimRisk.HIGH: 7 * 86400}[risk],
            stabilization_rounds=min(2, risk.k_required),
            required_evidence_kinds={"test_result", "receipt"},
        )
        policies[entry.key] = entry

    # --- MATH ---
    for risk, scope in _risk_scope_combos():
        entry = PolicyEntry(
            claim_type="math",
            risk=risk,
            scope=scope,
            k_required=1,  # Proof-based, not quorum
            independence_threshold=0.6,
            min_evidence_strength=0.9,
            max_novel_numbers=0,
            max_specious_precision=0.5,
            stabilization_rounds=1,
            required_evidence_kinds={"calc_result", "cryptographic_proof"},
        )
        policies[entry.key] = entry

    # --- PROCEDURE ---
    for risk, scope in _risk_scope_combos():
        entry = PolicyEntry(
            claim_type="procedure",
            risk=risk,
            scope=scope,
            k_required=max(1, risk.k_required - 1),
            independence_threshold=risk.independence_threshold,
            min_evidence_strength=0.7 + 0.1 * (risk.k_required - 1),
            max_novel_numbers=max(0, 2 - risk.k_required),
            max_specious_precision=0.6 - 0.1 * risk.k_required,
            ttl_seconds={ClaimRisk.LOW: 30 * 86400, ClaimRisk.MEDIUM: 14 * 86400, ClaimRisk.HIGH: 7 * 86400}[risk],
            stabilization_rounds=risk.k_required,
            required_evidence_kinds={"tool_trace", "test_result", "receipt"},
        )
        policies[entry.key] = entry

    # --- JUDGMENT / PLAN ---
    for risk, scope in _risk_scope_combos():
        entry = PolicyEntry(
            claim_type="judgment",
            risk=risk,
            scope=scope,
            k_required=max(0, risk.k_required - 1),  # Soft by default
            independence_threshold=0.6,
            min_evidence_strength=0.0 if risk == ClaimRisk.LOW else 0.7,
            max_novel_numbers=3,
            max_specious_precision=0.8,
            stabilization_rounds=risk.k_required,
            required_evidence_kinds=None,  # Subjective — dissent gate suffices
        )
        policies[entry.key] = entry

    return policies


def _risk_scope_combos() -> list[tuple[ClaimRisk, AssertionScope]]:
    """Generate all risk x scope combinations."""
    return [
        (risk, scope)
        for risk in ClaimRisk
        for scope in AssertionScope
    ]


class PolicyStore:
    """
    Threshold matrix the governor reads.

    Stores PolicyEntry per (claim_type, risk, scope).
    Supports adaptive tuning: thresholds adjust based on observed failures.
    """

    def __init__(self):
        self.policies: dict[str, PolicyEntry] = _default_policies()
        self.adjustment_history: list[dict[str, Any]] = []

    def get(
        self,
        claim_type: str,
        risk: ClaimRisk = ClaimRisk.LOW,
        scope: AssertionScope = AssertionScope.INTERNAL_PREMISE,
    ) -> PolicyEntry:
        """Get policy for a claim type/risk/scope. Falls back to defaults."""
        key = f"{claim_type}:{risk.value}:{scope.value}"
        if key in self.policies:
            return self.policies[key]

        # Fallback: try just claim_type with low/internal
        fallback_key = f"{claim_type}:{ClaimRisk.LOW.value}:{AssertionScope.INTERNAL_PREMISE.value}"
        if fallback_key in self.policies:
            return self.policies[fallback_key]

        # Final fallback: generic static_fact policy
        return PolicyEntry(claim_type=claim_type, risk=risk, scope=scope)

    def tighten(
        self,
        claim_type: str,
        risk: ClaimRisk,
        scope: AssertionScope,
        field: str,
        amount: float,
        reason: str = "",
    ) -> bool:
        """
        Tighten a specific threshold. Returns True if adjustment made.

        Tightening means: more evidence required, stricter limits.
        """
        policy = self.get(claim_type, risk, scope)

        old_value = getattr(policy, field, None)
        if old_value is None:
            return False

        # Direction depends on field
        if field in ("k_required", "independence_threshold", "min_evidence_strength", "stabilization_rounds"):
            # Higher = tighter
            new_value = old_value + amount
        elif field in ("max_novel_numbers", "max_specious_precision", "freshness_max_seconds", "ttl_seconds"):
            # Lower = tighter
            new_value = max(0, old_value - amount)
        else:
            return False

        setattr(policy, field, new_value)

        self.adjustment_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "claim_type": claim_type,
            "risk": risk.value,
            "scope": scope.value,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "direction": "tighten",
            "reason": reason,
        })

        return True

    def relax(
        self,
        claim_type: str,
        risk: ClaimRisk,
        scope: AssertionScope,
        field: str,
        amount: float,
        reason: str = "",
    ) -> bool:
        """
        Relax a specific threshold. Returns True if adjustment made.

        Relaxing means: less evidence required, looser limits.
        Only allowed for certain fields (never loosen independence for VOLATILE).
        """
        policy = self.get(claim_type, risk, scope)

        old_value = getattr(policy, field, None)
        if old_value is None:
            return False

        # Direction depends on field
        if field in ("k_required", "independence_threshold", "min_evidence_strength", "stabilization_rounds"):
            new_value = max(0, old_value - amount)
            # Floor: never relax below absolute minimum
            if field == "k_required":
                new_value = max(1, new_value)
            elif field == "independence_threshold":
                new_value = max(0.5, new_value)
        elif field in ("max_novel_numbers", "max_specious_precision", "freshness_max_seconds", "ttl_seconds"):
            new_value = old_value + amount
        else:
            return False

        setattr(policy, field, new_value)

        self.adjustment_history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "claim_type": claim_type,
            "risk": risk.value,
            "scope": scope.value,
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "direction": "relax",
            "reason": reason,
        })

        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "policies": {k: v.to_dict() for k, v in self.policies.items()},
            "adjustment_history": self.adjustment_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyStore":
        store = cls()
        store.policies = {
            k: PolicyEntry.from_dict(v) for k, v in data.get("policies", {}).items()
        }
        store.adjustment_history = data.get("adjustment_history", [])
        return store


# =============================================================================
# Failure Mode Classifier
# =============================================================================


def classify_failure_modes(signals: DetectionSignals, policy: PolicyEntry) -> list[FailureMode]:
    """
    Classify failure modes from detection signals.

    Returns list of detected failure modes (can be empty if clean).
    """
    modes = []

    # NO_EVIDENCE: no evidence at all
    if signals.evidence_count == 0:
        modes.append(FailureMode.NO_EVIDENCE)
        return modes  # If no evidence, skip other checks

    # WRONG_EVIDENCE_TYPE: evidence exists but wrong kind for claim type
    if policy.required_evidence_kinds is not None:
        provided_kinds = set(signals.evidence_kinds)
        if not provided_kinds.intersection(policy.required_evidence_kinds):
            modes.append(FailureMode.WRONG_EVIDENCE_TYPE)

    # WEAK_EVIDENCE: evidence exists but insufficient
    if signals.evidence_strength_sum < policy.min_evidence_strength:
        modes.append(FailureMode.WEAK_EVIDENCE)

    # SOURCE_ALIASING: false independence
    if signals.source_aliasing_score > 0.5:
        modes.append(FailureMode.SOURCE_ALIASING)

    # Independence below threshold
    if (signals.evidence_count >= 2
            and signals.independence_score < policy.independence_threshold):
        modes.append(FailureMode.SOURCE_ALIASING)

    # CITE_DRIFT: low citation coverage
    if signals.citation_coverage < 0.5 and signals.evidence_count > 0:
        modes.append(FailureMode.CITE_DRIFT)

    # SPECIOUS_PRECISION: suspicious exactness
    if (signals.specious_precision_score > policy.max_specious_precision
            or signals.novel_number_count > policy.max_novel_numbers):
        modes.append(FailureMode.SPECIOUS_PRECISION)

    # TEMPORAL_STALENESS
    if signals.is_stale:
        modes.append(FailureMode.TEMPORAL_STALENESS)
    elif (policy.freshness_max_seconds > 0
          and signals.freshness_age_seconds > policy.freshness_max_seconds):
        modes.append(FailureMode.TEMPORAL_STALENESS)

    # ENTAILMENT_OVERREACH: high confidence language, low evidence
    if signals.confidence_evidence_gap > 0.3:
        modes.append(FailureMode.ENTAILMENT_OVERREACH)

    # TOOL_MISREAD
    if signals.tool_misread_risk > 0.5:
        modes.append(FailureMode.TOOL_MISREAD)

    # ENTITY_CONFLATION: many novel entities
    if signals.novel_entity_count > 2:
        modes.append(FailureMode.ENTITY_CONFLATION)

    # COUNTEREVIDENCE_IGNORED: not detectable from signals alone,
    # requires external counter-evidence refs (handled at pipeline level)

    # Deduplicate
    return list(dict.fromkeys(modes))


def determine_grounding_status(failure_modes: list[FailureMode]) -> GroundingStatus:
    """Determine overall grounding status from failure modes."""
    if not failure_modes:
        return GroundingStatus.GROUNDED

    if FailureMode.COUNTEREVIDENCE_IGNORED in failure_modes:
        return GroundingStatus.CONTRADICTED

    if FailureMode.NO_EVIDENCE in failure_modes:
        return GroundingStatus.UNGROUNDED

    # Multiple failure modes or severe ones -> UNGROUNDED
    severe = {FailureMode.SPECIOUS_PRECISION, FailureMode.TOOL_MISREAD, FailureMode.PROMPT_INJECTION, FailureMode.WRONG_EVIDENCE_TYPE}
    if any(m in severe for m in failure_modes):
        return GroundingStatus.UNGROUNDED

    if len(failure_modes) >= 2:
        return GroundingStatus.UNGROUNDED

    # Single non-severe failure -> WEAK
    return GroundingStatus.WEAK


def determine_decision(
    status: GroundingStatus,
    failure_modes: list[FailureMode],
    has_counterevidence: bool = False,
) -> AuditDecision:
    """Determine audit decision from status and failure modes."""
    if status == GroundingStatus.GROUNDED:
        return AuditDecision.ALLOW_HARD

    if status == GroundingStatus.CONTRADICTED:
        return AuditDecision.BLOCK

    if status == GroundingStatus.UNGROUNDED:
        if FailureMode.NO_EVIDENCE in failure_modes:
            return AuditDecision.NEEDS_MORE_WORK
        if has_counterevidence:
            return AuditDecision.BLOCK
        return AuditDecision.BLOCK

    if status == GroundingStatus.WEAK:
        # Weak evidence: downgrade to SOFT
        return AuditDecision.DOWNGRADE_SOFT

    # UNKNOWN
    return AuditDecision.NEEDS_MORE_WORK


def determine_severity(
    failure_modes: list[FailureMode],
    scope: AssertionScope,
    risk: ClaimRisk,
) -> AuditSeverity:
    """Determine severity of audit finding."""
    if not failure_modes:
        return AuditSeverity.LOW

    severe_modes = {
        FailureMode.COUNTEREVIDENCE_IGNORED,
        FailureMode.PROMPT_INJECTION,
        FailureMode.SPECIOUS_PRECISION,
    }

    # High severity if severe mode + high scope/risk
    if any(m in severe_modes for m in failure_modes):
        if scope == AssertionScope.ACTION_TRIGGER or risk == ClaimRisk.HIGH:
            return AuditSeverity.HIGH
        return AuditSeverity.MEDIUM

    # Multiple failure modes increase severity
    if len(failure_modes) >= 3:
        return AuditSeverity.HIGH

    if len(failure_modes) >= 2:
        return AuditSeverity.MEDIUM

    # Single mode with high scope
    if scope == AssertionScope.ACTION_TRIGGER:
        return AuditSeverity.MEDIUM

    return AuditSeverity.LOW


# =============================================================================
# Audit Pipeline
# =============================================================================


class AuditPipeline:
    """
    Grounding audit pipeline: detect, classify, gate, and tune.

    Core operations:
    - audit(): Run a full audit on an assertion
    - pre_commit_audit(): Gate before HARD commitment
    - post_commit_audit(): Review after commit
    - adapt_thresholds(): Tune policies from audit outcomes
    """

    def __init__(self, policy_store: PolicyStore | None = None):
        self.policy_store = policy_store or PolicyStore()
        self.audit_history: list[GroundingAudit] = []

        # Adaptive tuning state
        self.failure_mode_counts: dict[str, int] = {m.value: 0 for m in FailureMode}
        self.total_audits: int = 0
        self.total_clean: int = 0
        self.total_problematic: int = 0

    # =========================================================================
    # Core Audit
    # =========================================================================

    def audit(
        self,
        assertion_id: str,
        signals: DetectionSignals,
        claim_type: str = "static_fact",
        risk: ClaimRisk = ClaimRisk.LOW,
        scope: AssertionScope = AssertionScope.INTERNAL_PREMISE,
        stage: AuditStage = AuditStage.PRE_COMMIT,
        has_counterevidence: bool = False,
        notes: str = "",
    ) -> GroundingAudit:
        """
        Run a full grounding audit on an assertion.

        Returns a GroundingAudit record with decision.
        """
        # 1. Get policy
        policy = self.policy_store.get(claim_type, risk, scope)

        # 2. Classify failure modes
        failure_modes = classify_failure_modes(signals, policy)

        # Add counterevidence mode if flagged
        if has_counterevidence:
            if FailureMode.COUNTEREVIDENCE_IGNORED not in failure_modes:
                failure_modes.append(FailureMode.COUNTEREVIDENCE_IGNORED)

        # 3. Determine status
        status = determine_grounding_status(failure_modes)

        # 4. Determine decision
        decision = determine_decision(status, failure_modes, has_counterevidence)

        # 5. Determine severity
        severity = determine_severity(failure_modes, scope, risk)

        # 6. Create audit record
        audit = GroundingAudit(
            audit_id=f"ga_{uuid.uuid4().hex[:12]}",
            assertion_id=assertion_id,
            stage=stage,
            status=status,
            decision=decision,
            failure_modes=failure_modes,
            severity=severity,
            signals=signals,
            notes=notes,
        )

        # 7. Record
        self.audit_history.append(audit)
        self.total_audits += 1

        if audit.is_clean:
            self.total_clean += 1
        if audit.is_problematic:
            self.total_problematic += 1

        for mode in failure_modes:
            self.failure_mode_counts[mode.value] = (
                self.failure_mode_counts.get(mode.value, 0) + 1
            )

        return audit

    def pre_commit_audit(
        self,
        assertion_id: str,
        signals: DetectionSignals,
        claim_type: str = "static_fact",
        risk: ClaimRisk = ClaimRisk.LOW,
        scope: AssertionScope = AssertionScope.USER_OUTPUT,
        has_counterevidence: bool = False,
    ) -> GroundingAudit:
        """
        Pre-commit gate: synchronous check before HARD commitment.

        Returns audit with decision (ALLOW_HARD, DOWNGRADE_SOFT, BLOCK, NEEDS_MORE_WORK).
        """
        return self.audit(
            assertion_id=assertion_id,
            signals=signals,
            claim_type=claim_type,
            risk=risk,
            scope=scope,
            stage=AuditStage.PRE_COMMIT,
            has_counterevidence=has_counterevidence,
        )

    def post_commit_audit(
        self,
        assertion_id: str,
        signals: DetectionSignals,
        claim_type: str = "static_fact",
        risk: ClaimRisk = ClaimRisk.LOW,
        scope: AssertionScope = AssertionScope.USER_OUTPUT,
    ) -> GroundingAudit:
        """
        Post-commit review: check for cite drift, tool misread, specious precision.
        """
        return self.audit(
            assertion_id=assertion_id,
            signals=signals,
            claim_type=claim_type,
            risk=risk,
            scope=scope,
            stage=AuditStage.POST_COMMIT,
        )

    def incident_review(
        self,
        assertion_id: str,
        signals: DetectionSignals,
        claim_type: str = "static_fact",
        risk: ClaimRisk = ClaimRisk.HIGH,
        scope: AssertionScope = AssertionScope.USER_OUTPUT,
        has_counterevidence: bool = True,
        notes: str = "",
    ) -> GroundingAudit:
        """
        Incident review: high-fidelity post-fact investigation.
        """
        return self.audit(
            assertion_id=assertion_id,
            signals=signals,
            claim_type=claim_type,
            risk=risk,
            scope=scope,
            stage=AuditStage.INCIDENT,
            has_counterevidence=has_counterevidence,
            notes=notes,
        )

    # =========================================================================
    # Adaptive Threshold Tuning
    # =========================================================================

    def adapt_thresholds(self, window: int = 50) -> list[dict[str, Any]]:
        """
        Analyze recent audits and tighten thresholds where failure modes are rising.

        Returns list of adjustments made.
        """
        recent = self.audit_history[-window:]
        if len(recent) < 10:
            return []  # Not enough data

        adjustments = []

        # Count failure modes in recent window (weighted by stage)
        mode_scores: dict[str, float] = {}
        for audit in recent:
            for mode in audit.failure_modes:
                weight = audit.stage.leak_weight
                mode_scores[mode.value] = mode_scores.get(mode.value, 0.0) + weight

        total_weight = sum(a.stage.leak_weight for a in recent)
        if total_weight == 0:
            return []

        # Compute rates
        mode_rates = {k: v / total_weight for k, v in mode_scores.items()}

        # Apply deterministic tuning rules
        for mode_str, rate in mode_rates.items():
            if rate < 0.05:
                continue  # Below threshold

            mode = FailureMode(mode_str)

            if mode == FailureMode.SOURCE_ALIASING and rate > 0.1:
                adj = self._tighten_all_types(
                    "independence_threshold", 0.05,
                    f"SOURCE_ALIASING rate {rate:.2f}",
                )
                adjustments.extend(adj)

            elif mode == FailureMode.CITE_DRIFT and rate > 0.1:
                # Increase evidence strength requirement
                adj = self._tighten_all_types(
                    "min_evidence_strength", 0.1,
                    f"CITE_DRIFT rate {rate:.2f}",
                )
                adjustments.extend(adj)

            elif mode == FailureMode.SPECIOUS_PRECISION and rate > 0.1:
                adj = self._tighten_all_types(
                    "max_novel_numbers", 1,
                    f"SPECIOUS_PRECISION rate {rate:.2f}",
                )
                adjustments.extend(adj)

            elif mode == FailureMode.TEMPORAL_STALENESS and rate > 0.1:
                adj = self._tighten_all_types(
                    "ttl_seconds", 3600,
                    f"TEMPORAL_STALENESS rate {rate:.2f}",
                )
                adjustments.extend(adj)

        return adjustments

    def _tighten_all_types(
        self,
        field: str,
        amount: float,
        reason: str,
    ) -> list[dict[str, Any]]:
        """Tighten a field across all claim types at MEDIUM+ risk."""
        adjustments = []
        seen = set()

        for key, policy in self.policy_store.policies.items():
            if policy.risk in (ClaimRisk.MEDIUM, ClaimRisk.HIGH):
                if key not in seen:
                    seen.add(key)
                    if self.policy_store.tighten(
                        policy.claim_type, policy.risk, policy.scope,
                        field, amount, reason,
                    ):
                        adjustments.append({
                            "key": key,
                            "field": field,
                            "amount": amount,
                            "reason": reason,
                        })

        return adjustments

    # =========================================================================
    # Queries
    # =========================================================================

    def get_audit(self, audit_id: str) -> GroundingAudit | None:
        """Get an audit by ID."""
        for a in self.audit_history:
            if a.audit_id == audit_id:
                return a
        return None

    def get_audits_for_assertion(self, assertion_id: str) -> list[GroundingAudit]:
        """Get all audits for an assertion."""
        return [a for a in self.audit_history if a.assertion_id == assertion_id]

    def get_problematic_audits(self, limit: int = 50) -> list[GroundingAudit]:
        """Get recent problematic audits."""
        problematic = [a for a in self.audit_history if a.is_problematic]
        return problematic[-limit:]

    def get_recent_audits(self, limit: int = 50) -> list[GroundingAudit]:
        """Get recent audits."""
        return self.audit_history[-limit:]

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> dict[str, Any]:
        """Get pipeline metrics."""
        return {
            "total_audits": self.total_audits,
            "total_clean": self.total_clean,
            "total_problematic": self.total_problematic,
            "clean_rate": (
                self.total_clean / self.total_audits if self.total_audits > 0 else 1.0
            ),
            "problematic_rate": (
                self.total_problematic / self.total_audits if self.total_audits > 0 else 0.0
            ),
            "failure_mode_counts": dict(self.failure_mode_counts),
            "top_failure_modes": sorted(
                [(k, v) for k, v in self.failure_mode_counts.items() if v > 0],
                key=lambda x: x[1],
                reverse=True,
            )[:5],
            "policy_adjustments": len(self.policy_store.adjustment_history),
        }

    def get_failure_mode_rates(self, window: int = 100) -> dict[str, float]:
        """Get failure mode rates over recent window."""
        recent = self.audit_history[-window:]
        if not recent:
            return {}

        counts: dict[str, int] = {}
        for audit in recent:
            for mode in audit.failure_modes:
                counts[mode.value] = counts.get(mode.value, 0) + 1

        total = len(recent)
        return {k: v / total for k, v in counts.items()}

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_store": self.policy_store.to_dict(),
            "audit_history": [a.to_dict() for a in self.audit_history],
            "failure_mode_counts": dict(self.failure_mode_counts),
            "total_audits": self.total_audits,
            "total_clean": self.total_clean,
            "total_problematic": self.total_problematic,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditPipeline":
        store = PolicyStore.from_dict(data.get("policy_store", {}))
        pipeline = cls(store)
        pipeline.audit_history = [
            GroundingAudit.from_dict(a) for a in data.get("audit_history", [])
        ]
        pipeline.failure_mode_counts = data.get("failure_mode_counts", {m.value: 0 for m in FailureMode})
        pipeline.total_audits = data.get("total_audits", 0)
        pipeline.total_clean = data.get("total_clean", 0)
        pipeline.total_problematic = data.get("total_problematic", 0)
        return pipeline

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# =============================================================================
# Convenience Functions
# =============================================================================


def quick_audit(
    assertion_id: str,
    evidence_count: int = 0,
    evidence_strength: float = 0.0,
    novel_numbers: int = 0,
    claim_type: str = "static_fact",
    risk: str = "low",
    scope: str = "user_output",
) -> GroundingAudit:
    """Quick audit with minimal signal specification."""
    signals = DetectionSignals(
        evidence_count=evidence_count,
        evidence_strength_sum=evidence_strength,
        novel_number_count=novel_numbers,
    )
    pipeline = AuditPipeline()
    return pipeline.pre_commit_audit(
        assertion_id=assertion_id,
        signals=signals,
        claim_type=claim_type,
        risk=ClaimRisk(risk),
        scope=AssertionScope(scope),
    )


def create_pipeline(policy_store: PolicyStore | None = None) -> AuditPipeline:
    """Create an audit pipeline with optional custom policy store."""
    return AuditPipeline(policy_store)
