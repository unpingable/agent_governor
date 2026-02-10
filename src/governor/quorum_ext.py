"""Multi-agent quorum extensions — severity-based gating (AG2 Layer 2.1-D).

Extends existing quorum.py with:
- Severity-based quorum requirements (S1/S2/S3)
- Byzantine-lite model (compromised component handling)
- Two-man rule (human + independent confirmer for S3)
- Evidence domain independence (cross-domain confirmation)
- Adjudication routing (targeted re-checks on disputes)
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(Enum):
    """Claim severity tier for quorum gating."""
    S1 = "S1"  # Low — no quorum required
    S2 = "S2"  # Medium — basic confirmation
    S3 = "S3"  # High — full quorum + two-man rule


class QuorumCheckResult(Enum):
    """Result of a quorum check."""
    PASSED = "PASSED"
    FAILED_CONFIRMATIONS = "FAILED_CONFIRMATIONS"
    FAILED_DOMAINS = "FAILED_DOMAINS"
    FAILED_INDEPENDENCE = "FAILED_INDEPENDENCE"
    FAILED_TWO_MAN = "FAILED_TWO_MAN"
    NOT_REQUIRED = "NOT_REQUIRED"


class AdjudicationAction(Enum):
    """Actions for disagreement handling."""
    ADJUDICATION_REQUESTED = "adjudication_requested"
    INDEPENDENT_VERIFICATION = "independent_verification"
    EVIDENCE_REVIEW = "evidence_review"
    ESCALATED_TO_HUMAN = "escalated_to_human"


class ConfirmerType(Enum):
    """Type of entity providing confirmation."""
    HUMAN = "human"
    AGENT = "agent"
    INDEPENDENT = "independent"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default Byzantine fault tolerance: f = 1 assumed faulty agent
DEFAULT_FAULT_TOLERANCE = 1

# Evidence domains recognized by the system
EVIDENCE_DOMAINS = frozenset({
    "web", "local_file", "api", "computation",
    "database", "test_execution", "static_analysis",
})

# Model families for independence checks
MODEL_FAMILIES = frozenset({
    "claude", "gpt", "gemini", "llama", "mistral",
    "codex", "deepseek", "qwen", "human",
})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class QuorumRequirement:
    """Quorum requirements for a severity tier."""
    min_confirmations: int
    min_evidence_domains: int
    require_independence: bool
    require_two_man_rule: bool = False

    def to_dict(self) -> dict:
        return {
            "min_confirmations": self.min_confirmations,
            "min_evidence_domains": self.min_evidence_domains,
            "require_independence": self.require_independence,
            "require_two_man_rule": self.require_two_man_rule,
        }

    @classmethod
    def from_dict(cls, d: dict) -> QuorumRequirement:
        return cls(
            min_confirmations=d["min_confirmations"],
            min_evidence_domains=d["min_evidence_domains"],
            require_independence=d["require_independence"],
            require_two_man_rule=d.get("require_two_man_rule", False),
        )


# Default quorum requirements by severity
S1_QUORUM = QuorumRequirement(
    min_confirmations=0,
    min_evidence_domains=0,
    require_independence=False,
)

S2_QUORUM = QuorumRequirement(
    min_confirmations=1,
    min_evidence_domains=1,
    require_independence=False,
)

S3_QUORUM = QuorumRequirement(
    min_confirmations=2,
    min_evidence_domains=2,
    require_independence=True,
    require_two_man_rule=True,
)

SEVERITY_REQUIREMENTS: dict[Severity, QuorumRequirement] = {
    Severity.S1: S1_QUORUM,
    Severity.S2: S2_QUORUM,
    Severity.S3: S3_QUORUM,
}


@dataclass
class Confirmation:
    """A confirmation from an agent/human for a claim."""
    claim_id: str
    confirmer: str
    confirmer_type: ConfirmerType
    model_family: str = ""
    evidence_domain: str = ""
    confidence: float = 1.0
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "confirmer": self.confirmer,
            "confirmer_type": self.confirmer_type.value,
            "model_family": self.model_family,
            "evidence_domain": self.evidence_domain,
            "confidence": self.confidence,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Confirmation:
        return cls(
            claim_id=d["claim_id"],
            confirmer=d["confirmer"],
            confirmer_type=ConfirmerType(d["confirmer_type"]),
            model_family=d.get("model_family", ""),
            evidence_domain=d.get("evidence_domain", ""),
            confidence=d.get("confidence", 1.0),
            ts=d.get("ts", ""),
        )


@dataclass
class Rejection:
    """A rejection from an agent/human for a claim."""
    claim_id: str
    rejector: str
    rejector_type: ConfirmerType
    reason: str = ""
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "rejector": self.rejector,
            "rejector_type": self.rejector_type.value,
            "reason": self.reason,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Rejection:
        return cls(
            claim_id=d["claim_id"],
            rejector=d["rejector"],
            rejector_type=ConfirmerType(d["rejector_type"]),
            reason=d.get("reason", ""),
            ts=d.get("ts", ""),
        )


@dataclass
class QuorumCheckDetail:
    """Detailed result of a quorum check."""
    result: QuorumCheckResult
    severity: Severity
    requirement: QuorumRequirement
    confirmations_count: int = 0
    domains_count: int = 0
    model_families_count: int = 0
    has_human_approval: bool = False
    has_independent_confirmation: bool = False
    details: str = ""

    def to_dict(self) -> dict:
        return {
            "result": self.result.value,
            "severity": self.severity.value,
            "requirement": self.requirement.to_dict(),
            "confirmations_count": self.confirmations_count,
            "domains_count": self.domains_count,
            "model_families_count": self.model_families_count,
            "has_human_approval": self.has_human_approval,
            "has_independent_confirmation": self.has_independent_confirmation,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, d: dict) -> QuorumCheckDetail:
        return cls(
            result=QuorumCheckResult(d["result"]),
            severity=Severity(d["severity"]),
            requirement=QuorumRequirement.from_dict(d["requirement"]),
            confirmations_count=d.get("confirmations_count", 0),
            domains_count=d.get("domains_count", 0),
            model_families_count=d.get("model_families_count", 0),
            has_human_approval=d.get("has_human_approval", False),
            has_independent_confirmation=d.get("has_independent_confirmation", False),
            details=d.get("details", ""),
        )


@dataclass
class AdjudicationRequest:
    """Request for adjudication on a disputed claim."""
    claim_id: str
    action: AdjudicationAction
    confirmations: list[Confirmation] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    reason: str = ""
    resolved: bool = False
    resolution: str = ""
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "action": self.action.value,
            "confirmations": [c.to_dict() for c in self.confirmations],
            "rejections": [r.to_dict() for r in self.rejections],
            "reason": self.reason,
            "resolved": self.resolved,
            "resolution": self.resolution,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AdjudicationRequest:
        return cls(
            claim_id=d["claim_id"],
            action=AdjudicationAction(d["action"]),
            confirmations=[Confirmation.from_dict(c) for c in d.get("confirmations", [])],
            rejections=[Rejection.from_dict(r) for r in d.get("rejections", [])],
            reason=d.get("reason", ""),
            resolved=d.get("resolved", False),
            resolution=d.get("resolution", ""),
            ts=d.get("ts", ""),
        )


@dataclass
class QuorumExtState:
    """State for the extended quorum system."""
    checks: list[QuorumCheckDetail] = field(default_factory=list)
    adjudications: list[AdjudicationRequest] = field(default_factory=list)
    confirmations: list[Confirmation] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def record_check(self, check: QuorumCheckDetail) -> None:
        self.checks.append(check)

    def record_confirmation(self, conf: Confirmation) -> None:
        self.confirmations.append(conf)

    def record_rejection(self, rej: Rejection) -> None:
        self.rejections.append(rej)

    def record_adjudication(self, adj: AdjudicationRequest) -> None:
        self.adjudications.append(adj)

    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.result == QuorumCheckResult.PASSED)

    def failed_count(self) -> int:
        return sum(1 for c in self.checks
                   if c.result not in (QuorumCheckResult.PASSED, QuorumCheckResult.NOT_REQUIRED))

    def to_dict(self) -> dict:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "adjudications": [a.to_dict() for a in self.adjudications],
            "confirmations": [c.to_dict() for c in self.confirmations],
            "rejections": [r.to_dict() for r in self.rejections],
            "events": list(self.events),
        }

    @classmethod
    def from_dict(cls, d: dict) -> QuorumExtState:
        return cls(
            checks=[QuorumCheckDetail.from_dict(c) for c in d.get("checks", [])],
            adjudications=[AdjudicationRequest.from_dict(a) for a in d.get("adjudications", [])],
            confirmations=[Confirmation.from_dict(c) for c in d.get("confirmations", [])],
            rejections=[Rejection.from_dict(r) for r in d.get("rejections", [])],
            events=d.get("events", []),
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def hash_action(proposal_text: str) -> str:
    """Hash a proposal for two-man rule tracking."""
    return hashlib.sha256(proposal_text.encode()).hexdigest()[:16]


def get_requirement(severity: Severity) -> QuorumRequirement:
    """Get quorum requirement for a severity tier."""
    return SEVERITY_REQUIREMENTS[severity]


def check_quorum(
    severity: Severity,
    confirmations: list[Confirmation],
    *,
    requirement: QuorumRequirement | None = None,
) -> QuorumCheckDetail:
    """Check if quorum requirements are met for a given severity.

    S1 claims don't need quorum. S2 needs basic confirmation.
    S3 needs full quorum with independence and two-man rule.
    """
    req = requirement or get_requirement(severity)

    if severity == Severity.S1:
        return QuorumCheckDetail(
            result=QuorumCheckResult.NOT_REQUIRED,
            severity=severity,
            requirement=req,
            confirmations_count=len(confirmations),
            details="S1 claims do not require quorum",
        )

    # Count confirmations
    conf_count = len(confirmations)
    if conf_count < req.min_confirmations:
        return QuorumCheckDetail(
            result=QuorumCheckResult.FAILED_CONFIRMATIONS,
            severity=severity,
            requirement=req,
            confirmations_count=conf_count,
            details=f"need {req.min_confirmations} confirmations, have {conf_count}",
        )

    # Count distinct evidence domains
    domains = {c.evidence_domain for c in confirmations if c.evidence_domain}
    domain_count = len(domains)
    if domain_count < req.min_evidence_domains:
        return QuorumCheckDetail(
            result=QuorumCheckResult.FAILED_DOMAINS,
            severity=severity,
            requirement=req,
            confirmations_count=conf_count,
            domains_count=domain_count,
            details=f"need {req.min_evidence_domains} evidence domains, have {domain_count}",
        )

    # Check model family independence
    models = {c.model_family for c in confirmations if c.model_family}
    model_count = len(models)
    if req.require_independence and model_count < 2:
        return QuorumCheckDetail(
            result=QuorumCheckResult.FAILED_INDEPENDENCE,
            severity=severity,
            requirement=req,
            confirmations_count=conf_count,
            domains_count=domain_count,
            model_families_count=model_count,
            details=f"independence requires ≥2 model families, have {model_count}",
        )

    return QuorumCheckDetail(
        result=QuorumCheckResult.PASSED,
        severity=severity,
        requirement=req,
        confirmations_count=conf_count,
        domains_count=domain_count,
        model_families_count=model_count,
        details="quorum requirements met",
    )


def check_two_man_rule(
    severity: Severity,
    confirmations: list[Confirmation],
) -> QuorumCheckDetail:
    """Check two-man rule: S3 actions require human + independent confirmer.

    For non-S3 claims, returns NOT_REQUIRED.
    """
    req = get_requirement(severity)
    if not req.require_two_man_rule:
        return QuorumCheckDetail(
            result=QuorumCheckResult.NOT_REQUIRED,
            severity=severity,
            requirement=req,
            details="two-man rule not required for this severity",
        )

    has_human = any(c.confirmer_type == ConfirmerType.HUMAN for c in confirmations)
    has_independent = any(c.confirmer_type == ConfirmerType.INDEPENDENT for c in confirmations)

    if has_human and has_independent:
        return QuorumCheckDetail(
            result=QuorumCheckResult.PASSED,
            severity=severity,
            requirement=req,
            has_human_approval=True,
            has_independent_confirmation=True,
            details="two-man rule satisfied",
        )

    return QuorumCheckDetail(
        result=QuorumCheckResult.FAILED_TWO_MAN,
        severity=severity,
        requirement=req,
        has_human_approval=has_human,
        has_independent_confirmation=has_independent,
        details=f"two-man rule: human={'yes' if has_human else 'no'}, "
                f"independent={'yes' if has_independent else 'no'}",
    )


def check_full_quorum(
    severity: Severity,
    confirmations: list[Confirmation],
) -> QuorumCheckDetail:
    """Run full quorum check including two-man rule for S3.

    Combines check_quorum() and check_two_man_rule().
    """
    quorum_result = check_quorum(severity, confirmations)

    if quorum_result.result not in (QuorumCheckResult.PASSED, QuorumCheckResult.NOT_REQUIRED):
        return quorum_result

    if severity == Severity.S3:
        two_man = check_two_man_rule(severity, confirmations)
        if two_man.result == QuorumCheckResult.FAILED_TWO_MAN:
            return two_man

    return quorum_result


def handle_disagreement(
    claim_id: str,
    confirmations: list[Confirmation],
    rejections: list[Rejection],
) -> AdjudicationRequest:
    """Route disagreements to adjudication.

    When agents disagree, create an adjudication request for targeted re-checks.
    """
    if not rejections:
        return AdjudicationRequest(
            claim_id=claim_id,
            action=AdjudicationAction.INDEPENDENT_VERIFICATION,
            confirmations=confirmations,
            rejections=[],
            reason="no disagreement",
            resolved=True,
            resolution="no_dispute",
        )

    # Determine action based on disagreement severity
    conf_count = len(confirmations)
    rej_count = len(rejections)

    if rej_count >= conf_count:
        # More rejections than confirmations — escalate
        action = AdjudicationAction.ESCALATED_TO_HUMAN
        reason = f"rejections ({rej_count}) >= confirmations ({conf_count})"
    elif any(r.rejector_type == ConfirmerType.HUMAN for r in rejections):
        # Human rejected — evidence review
        action = AdjudicationAction.EVIDENCE_REVIEW
        reason = "human rejection requires evidence review"
    else:
        # Agent-only disagreement — request independent verification
        action = AdjudicationAction.ADJUDICATION_REQUESTED
        reason = f"{rej_count} agent rejection(s) vs {conf_count} confirmation(s)"

    return AdjudicationRequest(
        claim_id=claim_id,
        action=action,
        confirmations=confirmations,
        rejections=rejections,
        reason=reason,
    )


def classify_severity(
    *,
    irreversible: bool = False,
    scope_size: float = 0.0,
    risk_score: float = 0.0,
) -> Severity:
    """Classify a claim into a severity tier.

    S3: irreversible OR risk_score > 0.7
    S2: scope_size > 0.5 OR risk_score > 0.3
    S1: everything else
    """
    if irreversible or risk_score > 0.7:
        return Severity.S3
    if scope_size > 0.5 or risk_score > 0.3:
        return Severity.S2
    return Severity.S1


def compute_fault_tolerance(total_agents: int, f: int = DEFAULT_FAULT_TOLERANCE) -> int:
    """Compute minimum confirmations needed: k = f + 1.

    With f assumed faulty agents, need f+1 honest confirmations
    to guarantee at least one honest confirmer.
    """
    return f + 1


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def make_quorum_ext_event(
    action: str,
    claim_id: str = "",
    details: dict | None = None,
) -> dict:
    """Create a quorum extension telemetry event."""
    return {
        "type": "quorum_ext",
        "action": action,
        "claim_id": claim_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "details": details or {},
    }


def make_quorum_check_event(check: QuorumCheckDetail) -> dict:
    """Create event for a quorum check."""
    return make_quorum_ext_event("quorum_check", details=check.to_dict())


def make_disagreement_event(adj: AdjudicationRequest) -> dict:
    """Create event for a disagreement/adjudication."""
    return make_quorum_ext_event(
        "quorum_disagreement",
        claim_id=adj.claim_id,
        details={
            "action": adj.action.value,
            "confirmations": len(adj.confirmations),
            "rejections": len(adj.rejections),
            "reason": adj.reason,
        },
    )


def make_two_man_event(check: QuorumCheckDetail) -> dict:
    """Create event for a two-man rule check."""
    return make_quorum_ext_event("two_man_rule_check", details={
        "result": check.result.value,
        "human_approval": check.has_human_approval,
        "independent_confirmation": check.has_independent_confirmation,
    })


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class QuorumExtStore:
    """Persistence for extended quorum state."""

    def __init__(self, governor_dir: Path | None = None):
        base = governor_dir or Path(".governor")
        self.quorum_ext_dir = base / "quorum_ext"

    def save(self, state: QuorumExtState, run_id: str = "default") -> None:
        self.quorum_ext_dir.mkdir(parents=True, exist_ok=True)
        path = self.quorum_ext_dir / f"{run_id}.json"
        path.write_text(json.dumps(state.to_dict(), indent=2))

    def load(self, run_id: str = "default") -> QuorumExtState | None:
        path = self.quorum_ext_dir / f"{run_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return QuorumExtState.from_dict(data)

    def list_runs(self) -> list[str]:
        if not self.quorum_ext_dir.exists():
            return []
        return sorted(p.stem for p in self.quorum_ext_dir.glob("*.json"))
