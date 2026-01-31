"""
Multi-agent quorum protocol for claim commitment.

Proposals requiring quorum collect votes from eligible agents, enforce
stability windows (Δt), and gate FSM transitions. Both quorum AND dissent
checks must pass before a proposal can proceed.

Key invariants:
1. Votes are positive consensus (not objections — those live in dissent.py)
2. Each claim type has a Δt budget, minimum voters (k), and approval threshold
3. Consensus must remain stable for Δt before it counts
4. A REJECT vote during stabilization resets the stability clock
5. Old consensus expires via TTL integration
6. Both gates must pass: no blocking dissent AND quorum reached
7. Risk multiplier scales effective Δt window
8. Fingerprint immutability prevents semantic laundering
9. Independence scoring ensures diverse method signatures

State transitions:
    COLLECTING ──(threshold met)──→ STABILIZING
    STABILIZING ──(Δt elapsed)──→ REACHED
    STABILIZING ──(new REJECT)──→ COLLECTING  (reset clock)
    REACHED ──(dissent filed)──→ CONTESTED
    CONTESTED ──(dissent resolved)──→ REACHED
    CONTESTED ──(decision: commit)──→ RESOLVED_COMMIT
    CONTESTED ──(decision: reject)──→ RESOLVED_REJECT
    CONTESTED ──(stuck/oscillation)──→ ESCALATED
    COLLECTING ──(timeout)──→ FAILED
    REACHED ──(TTL expired)──→ EXPIRED

Terminal states: FAILED, EXPIRED, ESCALATED, RESOLVED_COMMIT, RESOLVED_REJECT
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .dissent import DissentLedger, EvidencePointer
from .ttl import VolatilityClass


# =============================================================================
# Enums
# =============================================================================


class ClaimType(str, Enum):
    """Claim types with Δt budgets for quorum decisions."""

    MATH = "math"
    """Mathematical / logical claims. Fast consensus, low k."""

    CODE = "code"
    """Code-level claims. Quick consensus, low k."""

    STATIC_FACT = "static_fact"
    """Stable factual claims. Medium consensus window."""

    VOLATILE_FACT = "volatile_fact"
    """Time-sensitive factual claims. Longer window, more voters."""

    PROCEDURE = "procedure"
    """Procedural/operational claims. High stakes, large k."""

    JUDGMENT = "judgment"
    """Value judgments. Highest stakes, human-in-loop."""


class VoteVerdict(str, Enum):
    """Verdict cast by a voter."""

    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class QuorumStatus(str, Enum):
    """Status of a quorum consensus process."""

    COLLECTING = "collecting"
    """Gathering votes from eligible agents."""

    STABILIZING = "stabilizing"
    """Threshold met; waiting for Δt stability window."""

    REACHED = "reached"
    """Consensus achieved and stable."""

    FAILED = "failed"
    """Not enough votes or too many rejections."""

    EXPIRED = "expired"
    """TTL expired on previously reached consensus."""

    CONTESTED = "contested"
    """Was reached, then dissent objection filed."""

    ESCALATED = "escalated"
    """Stuck contested beyond TTL×risk, or oscillation detected."""

    RESOLVED_COMMIT = "resolved_commit"
    """Contested → resolved in favor of commit."""

    RESOLVED_REJECT = "resolved_reject"
    """Contested → rejected."""


class RiskLevel(str, Enum):
    """Risk level for quorum proposals, scales effective Δt."""

    LOW = "low"
    """×1.0 multiplier."""

    MEDIUM = "medium"
    """×1.5 multiplier."""

    HIGH = "high"
    """×2.0 multiplier."""

    @property
    def multiplier(self) -> float:
        return _RISK_MULTIPLIERS[self]


_RISK_MULTIPLIERS: dict["RiskLevel", float] = {
    RiskLevel.LOW: 1.0,
    RiskLevel.MEDIUM: 1.5,
    RiskLevel.HIGH: 2.0,
}


# Terminal states — no further transitions allowed
TERMINAL_STATES: frozenset[QuorumStatus] = frozenset({
    QuorumStatus.FAILED,
    QuorumStatus.EXPIRED,
    QuorumStatus.ESCALATED,
    QuorumStatus.RESOLVED_COMMIT,
    QuorumStatus.RESOLVED_REJECT,
})


# =============================================================================
# Fingerprint
# =============================================================================


def compute_fingerprint(proposal_id: str, claim_type: ClaimType, content: str = "") -> str:
    """Compute a proposal fingerprint (SHA-256 truncated to 16 hex chars)."""
    data = f"{proposal_id}:{claim_type.value}:{content}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


# =============================================================================
# Policy
# =============================================================================


@dataclass
class QuorumPolicy:
    """Per-claim-type quorum parameters."""

    claim_type: ClaimType
    min_voters: int            # k agents required
    approval_threshold: float  # fraction needed (e.g. 0.67)
    delta_t: timedelta         # stability window
    volatility: VolatilityClass  # TTL class for consensus result
    requires_human: bool = False
    timeout: timedelta = field(default_factory=lambda: timedelta(hours=1))
    risk_multiplier: float = 1.0
    independence_threshold: float = 0.3

    @property
    def effective_delta_t(self) -> timedelta:
        """Δt scaled by risk multiplier."""
        return self.delta_t * self.risk_multiplier

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_type": self.claim_type.value,
            "min_voters": self.min_voters,
            "approval_threshold": self.approval_threshold,
            "delta_t_seconds": self.delta_t.total_seconds(),
            "effective_delta_t_seconds": self.effective_delta_t.total_seconds(),
            "volatility": self.volatility.value,
            "requires_human": self.requires_human,
            "timeout_seconds": self.timeout.total_seconds(),
            "risk_multiplier": self.risk_multiplier,
            "independence_threshold": self.independence_threshold,
        }


# Default policies per claim type (from TODO.md Δt budgets)
DEFAULT_POLICIES: dict[ClaimType, QuorumPolicy] = {
    ClaimType.MATH: QuorumPolicy(
        claim_type=ClaimType.MATH,
        min_voters=2,
        approval_threshold=0.5,
        delta_t=timedelta(seconds=1),
        volatility=VolatilityClass.PERMANENT,
        timeout=timedelta(minutes=5),
    ),
    ClaimType.CODE: QuorumPolicy(
        claim_type=ClaimType.CODE,
        min_voters=1,
        approval_threshold=0.5,
        delta_t=timedelta(seconds=10),
        volatility=VolatilityClass.STABLE,
        timeout=timedelta(minutes=30),
    ),
    ClaimType.STATIC_FACT: QuorumPolicy(
        claim_type=ClaimType.STATIC_FACT,
        min_voters=2,
        approval_threshold=0.67,
        delta_t=timedelta(seconds=120),
        volatility=VolatilityClass.MODERATE,
        timeout=timedelta(hours=1),
    ),
    ClaimType.VOLATILE_FACT: QuorumPolicy(
        claim_type=ClaimType.VOLATILE_FACT,
        min_voters=3,
        approval_threshold=0.67,
        delta_t=timedelta(seconds=300),
        volatility=VolatilityClass.VOLATILE,
        timeout=timedelta(hours=2),
    ),
    ClaimType.PROCEDURE: QuorumPolicy(
        claim_type=ClaimType.PROCEDURE,
        min_voters=3,
        approval_threshold=0.75,
        delta_t=timedelta(seconds=300),
        volatility=VolatilityClass.MODERATE,
        timeout=timedelta(hours=4),
    ),
    ClaimType.JUDGMENT: QuorumPolicy(
        claim_type=ClaimType.JUDGMENT,
        min_voters=3,
        approval_threshold=0.75,
        delta_t=timedelta(seconds=600),
        volatility=VolatilityClass.STABLE,
        requires_human=True,
        timeout=timedelta(hours=24),
    ),
}


# =============================================================================
# Vote
# =============================================================================


@dataclass
class Vote:
    """A single vote cast by an agent on a proposal."""

    vote_id: str
    proposal_id: str
    agent_id: str
    verdict: VoteVerdict
    reason: str
    evidence: list[EvidencePointer] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    # Optional method-signature hashes for independence scoring
    tool_path_hash: str | None = None
    sources_hash: str | None = None
    prompt_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "vote_id": self.vote_id,
            "proposal_id": self.proposal_id,
            "agent_id": self.agent_id,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "evidence": [e.to_dict() for e in self.evidence],
            "timestamp": self.timestamp.isoformat(),
        }
        if self.tool_path_hash is not None:
            d["tool_path_hash"] = self.tool_path_hash
        if self.sources_hash is not None:
            d["sources_hash"] = self.sources_hash
        if self.prompt_hash is not None:
            d["prompt_hash"] = self.prompt_hash
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Vote":
        return cls(
            vote_id=data["vote_id"],
            proposal_id=data["proposal_id"],
            agent_id=data["agent_id"],
            verdict=VoteVerdict(data["verdict"]),
            reason=data["reason"],
            evidence=[EvidencePointer.from_dict(e) for e in data.get("evidence", [])],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            tool_path_hash=data.get("tool_path_hash"),
            sources_hash=data.get("sources_hash"),
            prompt_hash=data.get("prompt_hash"),
        )


# =============================================================================
# Quorum State
# =============================================================================


@dataclass
class QuorumState:
    """
    Tracks consensus progress for a single proposal.

    Manages vote collection, threshold checking, and stability window.
    """

    proposal_id: str
    claim_type: ClaimType
    policy: QuorumPolicy
    status: QuorumStatus = QuorumStatus.COLLECTING
    votes: dict[str, Vote] = field(default_factory=dict)  # agent_id → Vote
    created_at: datetime = field(default_factory=datetime.now)
    stabilized_at: datetime | None = None  # when threshold first met
    reached_at: datetime | None = None     # when Δt window elapsed
    failed_at: datetime | None = None
    failed_reason: str | None = None
    # Fingerprint fields
    fingerprint: str | None = None
    fingerprint_locked: bool = False
    # Risk and resolution fields
    risk_level: RiskLevel = RiskLevel.LOW
    contested_at: datetime | None = None
    contest_reason: str | None = None
    escalated_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution: str | None = None  # "commit" or "reject"

    # Counts

    @property
    def approval_count(self) -> int:
        return sum(1 for v in self.votes.values() if v.verdict == VoteVerdict.APPROVE)

    @property
    def rejection_count(self) -> int:
        return sum(1 for v in self.votes.values() if v.verdict == VoteVerdict.REJECT)

    @property
    def abstain_count(self) -> int:
        return sum(1 for v in self.votes.values() if v.verdict == VoteVerdict.ABSTAIN)

    @property
    def total_votes(self) -> int:
        return len(self.votes)

    @property
    def non_abstain_votes(self) -> int:
        return self.approval_count + self.rejection_count

    @property
    def approval_ratio(self) -> float:
        """Fraction of non-abstain votes that are approvals."""
        non_abstain = self.non_abstain_votes
        if non_abstain == 0:
            return 0.0
        return self.approval_count / non_abstain

    @property
    def has_enough_voters(self) -> bool:
        """Whether minimum voter count (k) is met."""
        return self.total_votes >= self.policy.min_voters

    @property
    def threshold_met(self) -> bool:
        """Whether approval threshold is met with enough voters."""
        return self.has_enough_voters and self.approval_ratio >= self.policy.approval_threshold

    def is_stable(self, now: datetime | None = None) -> bool:
        """Whether effective Δt stability window has elapsed since threshold was met."""
        if self.stabilized_at is None:
            return False
        now = now or datetime.now()
        return (now - self.stabilized_at) >= self.policy.effective_delta_t

    def is_timed_out(self, now: datetime | None = None) -> bool:
        """Whether the quorum has exceeded its timeout."""
        now = now or datetime.now()
        return (now - self.created_at) >= self.policy.timeout

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "claim_type": self.claim_type.value,
            "status": self.status.value,
            "policy": self.policy.to_dict(),
            "votes": {aid: v.to_dict() for aid, v in self.votes.items()},
            "approval_count": self.approval_count,
            "rejection_count": self.rejection_count,
            "abstain_count": self.abstain_count,
            "approval_ratio": self.approval_ratio,
            "threshold_met": self.threshold_met,
            "created_at": self.created_at.isoformat(),
            "stabilized_at": self.stabilized_at.isoformat() if self.stabilized_at else None,
            "reached_at": self.reached_at.isoformat() if self.reached_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "failed_reason": self.failed_reason,
            "fingerprint": self.fingerprint,
            "fingerprint_locked": self.fingerprint_locked,
            "risk_level": self.risk_level.value,
            "contested_at": self.contested_at.isoformat() if self.contested_at else None,
            "contest_reason": self.contest_reason,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution": self.resolution,
        }


# =============================================================================
# Quorum Manager
# =============================================================================


class QuorumManager:
    """
    Manages quorum states for all proposals.

    Handles vote collection, status transitions, and integration with
    dissent and TTL subsystems.
    """

    def __init__(
        self,
        policies: dict[ClaimType, QuorumPolicy] | None = None,
        dissent_ledger: DissentLedger | None = None,
        independence_scorer: Any | None = None,
    ):
        self.policies = policies or dict(DEFAULT_POLICIES)
        self.quorums: dict[str, QuorumState] = {}  # proposal_id → QuorumState
        self.history: list[dict[str, Any]] = []     # transition log
        self.dissent_ledger = dissent_ledger
        self.independence_scorer = independence_scorer

    def get_policy(self, claim_type: ClaimType) -> QuorumPolicy:
        """Get the quorum policy for a claim type."""
        return self.policies[claim_type]

    def create_quorum(
        self,
        proposal_id: str,
        claim_type: ClaimType,
        created_at: datetime | None = None,
        content: str = "",
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> QuorumState:
        """
        Create a new quorum for a proposal.

        Returns the QuorumState in COLLECTING status.
        Computes and sets the fingerprint at creation time.
        """
        policy = self.get_policy(claim_type)
        now = created_at or datetime.now()
        fp = compute_fingerprint(proposal_id, claim_type, content)
        qs = QuorumState(
            proposal_id=proposal_id,
            claim_type=claim_type,
            policy=policy,
            status=QuorumStatus.COLLECTING,
            created_at=now,
            fingerprint=fp,
            risk_level=risk_level,
        )
        # Apply risk multiplier to policy
        if risk_level != RiskLevel.LOW:
            qs.policy = QuorumPolicy(
                claim_type=policy.claim_type,
                min_voters=policy.min_voters,
                approval_threshold=policy.approval_threshold,
                delta_t=policy.delta_t,
                volatility=policy.volatility,
                requires_human=policy.requires_human,
                timeout=policy.timeout,
                risk_multiplier=risk_level.multiplier,
                independence_threshold=policy.independence_threshold,
            )
        self.quorums[proposal_id] = qs
        self._log("created", proposal_id, claim_type=claim_type.value)
        return qs

    def cast_vote(
        self,
        proposal_id: str,
        agent_id: str,
        verdict: VoteVerdict,
        reason: str,
        evidence: list[EvidencePointer] | None = None,
        timestamp: datetime | None = None,
        tool_path_hash: str | None = None,
        sources_hash: str | None = None,
        prompt_hash: str | None = None,
    ) -> Vote | None:
        """
        Cast a vote on a proposal.

        Returns the Vote if accepted, None if the quorum is not in a votable state
        or the agent already voted.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None:
            return None

        # Only accept votes during COLLECTING or STABILIZING
        if qs.status not in {QuorumStatus.COLLECTING, QuorumStatus.STABILIZING}:
            return None

        # Prevent duplicate votes from same agent
        if agent_id in qs.votes:
            return None

        now = timestamp or datetime.now()
        vote = Vote(
            vote_id=f"vote_{uuid.uuid4().hex[:12]}",
            proposal_id=proposal_id,
            agent_id=agent_id,
            verdict=verdict,
            reason=reason,
            evidence=evidence or [],
            timestamp=now,
            tool_path_hash=tool_path_hash,
            sources_hash=sources_hash,
            prompt_hash=prompt_hash,
        )
        qs.votes[agent_id] = vote
        self._log("vote_cast", proposal_id, agent_id=agent_id, verdict=verdict.value)

        # Check for state transitions after vote
        self._evaluate_transitions(qs, now)

        return vote

    def check_status(self, proposal_id: str) -> QuorumStatus | None:
        """Check the current status of a quorum."""
        qs = self.quorums.get(proposal_id)
        if qs is None:
            return None
        return qs.status

    def get_quorum(self, proposal_id: str) -> QuorumState | None:
        """Get the full quorum state for a proposal."""
        return self.quorums.get(proposal_id)

    def update(self, proposal_id: str, now: datetime | None = None) -> QuorumStatus | None:
        """
        Re-evaluate a quorum's status (call periodically for timeout/stability checks).

        Returns the new status, or None if the proposal doesn't exist.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None:
            return None
        now = now or datetime.now()
        self._evaluate_transitions(qs, now)
        return qs.status

    def can_proceed(
        self,
        proposal_id: str,
        dissent_ledger: DissentLedger | None = None,
        now: datetime | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Check if a proposal can proceed to the next FSM state.

        All gates must pass:
        1. Quorum must be REACHED
        2. No blocking dissent (if dissent_ledger provided)
        3. Independence threshold met (if independence_scorer set)

        Returns (can_proceed, list of blocking reasons).
        """
        reasons: list[str] = []
        qs = self.quorums.get(proposal_id)

        if qs is None:
            return False, ["No quorum exists for this proposal"]

        # Re-evaluate first
        now = now or datetime.now()
        self._evaluate_transitions(qs, now)

        # Gate 1: Quorum status
        if qs.status != QuorumStatus.REACHED:
            reasons.append(f"Quorum status is {qs.status.value}, not reached")

        # Gate 2: Human approval required
        if qs.policy.requires_human:
            has_human_vote = any(
                v.agent_id.startswith("human:")
                for v in qs.votes.values()
                if v.verdict == VoteVerdict.APPROVE
            )
            if not has_human_vote:
                reasons.append("Requires human approval (agent_id starting with 'human:')")

        # Gate 3: Dissent check
        dl = dissent_ledger or self.dissent_ledger
        if dl is not None:
            can_commit, blockers = dl.can_commit(proposal_id)
            if not can_commit:
                for b in blockers:
                    reasons.append(f"Dissent blocks: {b.reason}")

        # Gate 4: Independence check
        if self.independence_scorer is not None:
            approve_votes = [
                v for v in qs.votes.values()
                if v.verdict == VoteVerdict.APPROVE
            ]
            result = self.independence_scorer.score_votes(approve_votes)
            if not result.passes_threshold:
                reasons.append(
                    f"Independence score {result.score:.2f} below threshold "
                    f"{qs.policy.independence_threshold:.2f}"
                )

        return len(reasons) == 0, reasons

    def contest(self, proposal_id: str, reason: str = "") -> bool:
        """
        Mark a REACHED quorum as CONTESTED (dissent was filed).

        Returns True if the transition was made.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None or qs.status != QuorumStatus.REACHED:
            return False
        qs.status = QuorumStatus.CONTESTED
        qs.contested_at = datetime.now()
        qs.contest_reason = reason or "Dissent filed"
        self._log("contested", proposal_id, reason=reason)
        return True

    def resolve_contest(self, proposal_id: str) -> bool:
        """
        Resolve a CONTESTED quorum back to REACHED (dissent was resolved).

        Returns True if the transition was made.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None or qs.status != QuorumStatus.CONTESTED:
            return False
        qs.status = QuorumStatus.REACHED
        self._log("contest_resolved", proposal_id)
        return True

    def escalate(self, proposal_id: str, reason: str) -> bool:
        """
        Escalate a CONTESTED quorum (stuck beyond TTL×risk, or oscillation).

        CONTESTED → ESCALATED. Returns True if the transition was made.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None or qs.status != QuorumStatus.CONTESTED:
            return False
        qs.status = QuorumStatus.ESCALATED
        qs.escalated_at = datetime.now()
        self._log("escalated", proposal_id, reason=reason)
        return True

    def resolve_commit(self, proposal_id: str) -> bool:
        """
        Resolve a CONTESTED quorum in favor of commit.

        CONTESTED → RESOLVED_COMMIT. Returns True if the transition was made.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None or qs.status != QuorumStatus.CONTESTED:
            return False
        qs.status = QuorumStatus.RESOLVED_COMMIT
        qs.resolved_at = datetime.now()
        qs.resolution = "commit"
        self._log("resolved_commit", proposal_id)
        return True

    def resolve_reject(self, proposal_id: str, reason: str = "") -> bool:
        """
        Resolve a CONTESTED quorum as rejected.

        CONTESTED → RESOLVED_REJECT. Returns True if the transition was made.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None or qs.status != QuorumStatus.CONTESTED:
            return False
        qs.status = QuorumStatus.RESOLVED_REJECT
        qs.resolved_at = datetime.now()
        qs.resolution = "reject"
        self._log("resolved_reject", proposal_id, reason=reason)
        return True

    def validate_fingerprint(self, proposal_id: str, content: str) -> bool:
        """
        Validate that proposal content matches its fingerprint.

        If the fingerprint is locked and doesn't match, auto-contests the quorum.
        Returns True if the fingerprint matches, False if mismatch (and auto-contested).
        """
        qs = self.quorums.get(proposal_id)
        if qs is None or qs.fingerprint is None:
            return True  # No fingerprint to validate

        new_fp = compute_fingerprint(proposal_id, qs.claim_type, content)
        if new_fp == qs.fingerprint:
            return True

        # Fingerprint mismatch
        if qs.fingerprint_locked:
            # Auto-contest if in REACHED state, otherwise log warning
            if qs.status == QuorumStatus.REACHED:
                self.contest(proposal_id, reason="Fingerprint mismatch detected")
            self._log("fingerprint_mismatch", proposal_id, locked=True)
            return False

        # Not locked yet — update fingerprint
        qs.fingerprint = new_fp
        self._log("fingerprint_updated", proposal_id)
        return True

    def fail(self, proposal_id: str, reason: str) -> bool:
        """
        Manually fail a quorum.

        Returns True if the transition was made.
        """
        qs = self.quorums.get(proposal_id)
        if qs is None:
            return False
        if qs.status in TERMINAL_STATES:
            return False
        qs.status = QuorumStatus.FAILED
        qs.failed_at = datetime.now()
        qs.failed_reason = reason
        self._log("failed", proposal_id, reason=reason)
        return True

    def enforce_ttl(self, now: datetime | None = None) -> list[str]:
        """
        Check all REACHED quorums for TTL expiry.

        Returns list of expired proposal IDs.
        """
        now = now or datetime.now()
        expired: list[str] = []

        for pid, qs in self.quorums.items():
            if qs.status != QuorumStatus.REACHED:
                continue
            if qs.reached_at is None:
                continue

            # Use the volatility class's implicit TTL
            from .ttl import DEFAULT_POLICIES as TTL_POLICIES
            ttl_policy = TTL_POLICIES.get(qs.policy.volatility)
            if ttl_policy is None or ttl_policy.ttl is None:
                continue  # Permanent — no expiry

            if (now - qs.reached_at) >= ttl_policy.ttl:
                qs.status = QuorumStatus.EXPIRED
                expired.append(pid)
                self._log("expired", pid)

        return expired

    # =========================================================================
    # Queries
    # =========================================================================

    def active_quorums(self) -> list[QuorumState]:
        """Get quorums that are still in progress (COLLECTING or STABILIZING)."""
        return [
            qs for qs in self.quorums.values()
            if qs.status in {QuorumStatus.COLLECTING, QuorumStatus.STABILIZING}
        ]

    def reached_quorums(self) -> list[QuorumState]:
        """Get quorums that have reached consensus."""
        return [
            qs for qs in self.quorums.values()
            if qs.status == QuorumStatus.REACHED
        ]

    def failed_quorums(self) -> list[QuorumState]:
        """Get quorums that failed."""
        return [
            qs for qs in self.quorums.values()
            if qs.status == QuorumStatus.FAILED
        ]

    def contested_quorums(self) -> list[QuorumState]:
        """Get quorums that are contested."""
        return [
            qs for qs in self.quorums.values()
            if qs.status == QuorumStatus.CONTESTED
        ]

    def get_metrics(self) -> dict[str, Any]:
        """Get quorum manager statistics."""
        by_status: dict[str, int] = {}
        for s in QuorumStatus:
            by_status[s.value] = sum(
                1 for qs in self.quorums.values() if qs.status == s
            )
        return {
            "total_quorums": len(self.quorums),
            "by_status": by_status,
            "total_votes": sum(qs.total_votes for qs in self.quorums.values()),
            "history_entries": len(self.history),
        }

    # =========================================================================
    # Internal
    # =========================================================================

    def _evaluate_transitions(self, qs: QuorumState, now: datetime) -> None:
        """Evaluate and apply state transitions for a quorum."""

        # Terminal states: no transitions
        if qs.status in TERMINAL_STATES:
            return

        # COLLECTING → check for timeout or threshold
        if qs.status == QuorumStatus.COLLECTING:
            if qs.is_timed_out(now):
                qs.status = QuorumStatus.FAILED
                qs.failed_at = now
                qs.failed_reason = "Timeout: insufficient votes"
                self._log("timeout", qs.proposal_id)
                return

            if qs.threshold_met:
                qs.status = QuorumStatus.STABILIZING
                qs.stabilized_at = now
                # Lock fingerprint on entering STABILIZING
                qs.fingerprint_locked = True
                self._log("stabilizing", qs.proposal_id)
                return

        # STABILIZING → check for stability or rejection reset
        if qs.status == QuorumStatus.STABILIZING:
            if qs.is_timed_out(now):
                qs.status = QuorumStatus.FAILED
                qs.failed_at = now
                qs.failed_reason = "Timeout during stabilization"
                self._log("timeout", qs.proposal_id)
                return

            # Check if a reject vote was cast (would have just been added)
            # If threshold no longer met, reset to COLLECTING
            if not qs.threshold_met:
                qs.status = QuorumStatus.COLLECTING
                qs.stabilized_at = None
                self._log("destabilized", qs.proposal_id)
                return

            # Check if Δt has elapsed (uses effective_delta_t via is_stable)
            if qs.is_stable(now):
                qs.status = QuorumStatus.REACHED
                qs.reached_at = now
                self._log("reached", qs.proposal_id)
                return

        # CONTESTED → check for auto-resolution
        if qs.status == QuorumStatus.CONTESTED:
            if qs.contested_at is not None:
                # Auto-reject if contested beyond decision deadline (timeout * 2)
                contest_duration = now - qs.contested_at
                decision_deadline = qs.policy.timeout * 2
                if contest_duration >= decision_deadline:
                    qs.status = QuorumStatus.RESOLVED_REJECT
                    qs.resolved_at = now
                    qs.resolution = "reject"
                    self._log("auto_resolved_reject", qs.proposal_id,
                              reason="Decision deadline exceeded")
                    return

    def _log(self, event: str, proposal_id: str, **kwargs: Any) -> None:
        """Log a quorum event."""
        entry: dict[str, Any] = {
            "event": event,
            "proposal_id": proposal_id,
            "timestamp": datetime.now().isoformat(),
        }
        entry.update(kwargs)
        self.history.append(entry)


# =============================================================================
# Convenience
# =============================================================================


def create_quorum_manager(
    policies: dict[ClaimType, QuorumPolicy] | None = None,
    dissent_ledger: DissentLedger | None = None,
    independence_scorer: Any | None = None,
) -> QuorumManager:
    """Create a QuorumManager with optional custom policies."""
    return QuorumManager(policies, dissent_ledger, independence_scorer)


def get_default_policy(claim_type: ClaimType) -> QuorumPolicy:
    """Get the default quorum policy for a claim type."""
    return DEFAULT_POLICIES[claim_type]
