# SPDX-License-Identifier: Apache-2.0
"""
Contradiction persistence ledger: Track dissent as first-class state.

Objections are not noise — they are structural signals. This module maintains
a persistent record of disagreements so they are never silently discarded.

Key invariants:
1. Objections with evidence BLOCK commit (hard objection)
2. Objections without evidence FLAG for review (soft objection)
3. Dissent is never silently discarded
4. Confidence trajectories are tracked per claim
5. Resolution requires explicit action (accept, dismiss, escalate)

Architecture:
- Objection: first-class record of disagreement
- DissentLedger: stores objections, tracks confidence trajectories, enforces rules
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class ObjectionSeverity(str, Enum):
    """Severity of an objection."""

    LOW = "low"
    """Minor concern — does not block."""

    MEDIUM = "medium"
    """Significant concern — flags for review."""

    HIGH = "high"
    """Critical concern — blocks commit if evidence attached."""

    CRITICAL = "critical"
    """Must be resolved before any progress. Always blocks."""


class ObjectionStatus(str, Enum):
    """Status of an objection."""

    OPEN = "open"
    """Active, unresolved objection."""

    ACCEPTED = "accepted"
    """Objection accepted — claim modified or retracted."""

    DISMISSED = "dismissed"
    """Objection dismissed — with stated reason."""

    ESCALATED = "escalated"
    """Escalated for human review."""

    SUPERSEDED = "superseded"
    """Replaced by a newer objection on the same claim."""


class BlockVerdict(str, Enum):
    """Whether an objection blocks commit."""

    BLOCKS = "blocks"
    """Hard block — cannot proceed."""

    FLAGS = "flags"
    """Soft flag — proceed with caution."""

    CLEAR = "clear"
    """No block — objection resolved or insufficient severity."""


# =============================================================================
# Core Types
# =============================================================================


@dataclass
class EvidencePointer:
    """Lightweight pointer to evidence supporting an objection."""

    description: str
    locator: str = ""  # URL, hash, trace ID
    evidence_type: str = "unspecified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "locator": self.locator,
            "evidence_type": self.evidence_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidencePointer":
        return cls(
            description=data["description"],
            locator=data.get("locator", ""),
            evidence_type=data.get("evidence_type", "unspecified"),
        )


@dataclass
class Objection:
    """
    A first-class record of disagreement with a claim.

    Objections with evidence block commit; without evidence they flag for review.
    """

    objection_id: str
    claim_id: str
    agent_id: str
    reason: str
    severity: ObjectionSeverity
    status: ObjectionStatus = ObjectionStatus.OPEN
    evidence: list[EvidencePointer] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    resolution_reason: str | None = None

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence) > 0

    @property
    def is_open(self) -> bool:
        return self.status == ObjectionStatus.OPEN

    @property
    def is_resolved(self) -> bool:
        return self.status in {
            ObjectionStatus.ACCEPTED,
            ObjectionStatus.DISMISSED,
            ObjectionStatus.ESCALATED,
            ObjectionStatus.SUPERSEDED,
        }

    @property
    def blocks_commit(self) -> bool:
        """Does this objection block commit?"""
        if not self.is_open:
            return False
        if self.severity == ObjectionSeverity.CRITICAL:
            return True
        if self.severity == ObjectionSeverity.HIGH and self.has_evidence:
            return True
        return False

    @property
    def flags_review(self) -> bool:
        """Does this objection flag for review (soft block)?"""
        if not self.is_open:
            return False
        if self.blocks_commit:
            return False  # It's a hard block, not just a flag
        if self.severity in {ObjectionSeverity.MEDIUM, ObjectionSeverity.HIGH}:
            return True
        return False

    def get_verdict(self) -> BlockVerdict:
        if self.blocks_commit:
            return BlockVerdict.BLOCKS
        if self.flags_review:
            return BlockVerdict.FLAGS
        return BlockVerdict.CLEAR

    def to_dict(self) -> dict[str, Any]:
        return {
            "objection_id": self.objection_id,
            "claim_id": self.claim_id,
            "agent_id": self.agent_id,
            "reason": self.reason,
            "severity": self.severity.value,
            "status": self.status.value,
            "evidence": [e.to_dict() for e in self.evidence],
            "has_evidence": self.has_evidence,
            "blocks_commit": self.blocks_commit,
            "flags_review": self.flags_review,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_reason": self.resolution_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Objection":
        return cls(
            objection_id=data["objection_id"],
            claim_id=data["claim_id"],
            agent_id=data["agent_id"],
            reason=data["reason"],
            severity=ObjectionSeverity(data["severity"]),
            status=ObjectionStatus(data.get("status", "open")),
            evidence=[EvidencePointer.from_dict(e) for e in data.get("evidence", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            resolved_at=(
                datetime.fromisoformat(data["resolved_at"])
                if data.get("resolved_at")
                else None
            ),
            resolution_reason=data.get("resolution_reason"),
        )


@dataclass
class ConfidenceSnapshot:
    """A point-in-time confidence reading for trajectory tracking."""

    claim_id: str
    confidence: float
    step: int
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ClaimDissentSummary:
    """Summary of dissent activity for a single claim."""

    claim_id: str
    total_objections: int
    open_objections: int
    blocking_objections: int
    flagging_objections: int
    has_unresolved_dissent: bool
    highest_severity: ObjectionSeverity | None


# =============================================================================
# Dissent Ledger
# =============================================================================


class DissentLedger:
    """
    Persistent ledger for tracking objections and confidence trajectories.

    Never silently discards dissent. Resolution requires explicit action.
    """

    def __init__(self):
        self.objections: dict[str, Objection] = {}
        self.confidence_history: list[ConfidenceSnapshot] = []
        self.step: int = 0

        # Metrics
        self.total_objections_filed: int = 0
        self.total_objections_accepted: int = 0
        self.total_objections_dismissed: int = 0
        self.total_objections_escalated: int = 0

    def tick(self) -> None:
        """Advance step counter."""
        self.step += 1

    # =========================================================================
    # Filing Objections
    # =========================================================================

    def file_objection(
        self,
        claim_id: str,
        agent_id: str,
        reason: str,
        severity: ObjectionSeverity,
        evidence: list[EvidencePointer] | None = None,
    ) -> Objection:
        """
        File an objection against a claim.

        Returns the created Objection.
        """
        obj = Objection(
            objection_id=f"obj_{uuid.uuid4().hex[:12]}",
            claim_id=claim_id,
            agent_id=agent_id,
            reason=reason,
            severity=severity,
            evidence=evidence or [],
        )
        self.objections[obj.objection_id] = obj
        self.total_objections_filed += 1
        return obj

    def add_evidence(
        self,
        objection_id: str,
        evidence: EvidencePointer,
    ) -> bool:
        """Add evidence to an existing objection. Returns True if added."""
        obj = self.objections.get(objection_id)
        if obj is None or not obj.is_open:
            return False
        obj.evidence.append(evidence)
        return True

    # =========================================================================
    # Resolution
    # =========================================================================

    def accept(self, objection_id: str, reason: str = "") -> bool:
        """Accept an objection (claim will be modified/retracted)."""
        obj = self.objections.get(objection_id)
        if obj is None or not obj.is_open:
            return False
        obj.status = ObjectionStatus.ACCEPTED
        obj.resolved_at = datetime.now()
        obj.resolution_reason = reason
        self.total_objections_accepted += 1
        return True

    def dismiss(self, objection_id: str, reason: str) -> bool:
        """
        Dismiss an objection with a stated reason.

        Reason is REQUIRED — dissent is never silently discarded.
        """
        if not reason:
            return False  # Must provide reason
        obj = self.objections.get(objection_id)
        if obj is None or not obj.is_open:
            return False
        obj.status = ObjectionStatus.DISMISSED
        obj.resolved_at = datetime.now()
        obj.resolution_reason = reason
        self.total_objections_dismissed += 1
        return True

    def escalate(self, objection_id: str, reason: str = "") -> bool:
        """Escalate an objection for human review."""
        obj = self.objections.get(objection_id)
        if obj is None or not obj.is_open:
            return False
        obj.status = ObjectionStatus.ESCALATED
        obj.resolved_at = datetime.now()
        obj.resolution_reason = reason or "Escalated for human review"
        self.total_objections_escalated += 1
        return True

    def supersede(self, objection_id: str, new_objection_id: str) -> bool:
        """Mark an objection as superseded by a newer one."""
        obj = self.objections.get(objection_id)
        if obj is None or not obj.is_open:
            return False
        obj.status = ObjectionStatus.SUPERSEDED
        obj.resolved_at = datetime.now()
        obj.resolution_reason = f"Superseded by {new_objection_id}"
        return True

    # =========================================================================
    # Confidence Trajectory
    # =========================================================================

    def record_confidence(self, claim_id: str, confidence: float) -> None:
        """Record a confidence snapshot for trajectory tracking."""
        self.confidence_history.append(ConfidenceSnapshot(
            claim_id=claim_id,
            confidence=confidence,
            step=self.step,
        ))

    def get_trajectory(self, claim_id: str) -> list[ConfidenceSnapshot]:
        """Get confidence trajectory for a claim."""
        return [s for s in self.confidence_history if s.claim_id == claim_id]

    # =========================================================================
    # Queries
    # =========================================================================

    def get(self, objection_id: str) -> Objection | None:
        return self.objections.get(objection_id)

    def open_objections(self) -> list[Objection]:
        return [o for o in self.objections.values() if o.is_open]

    def resolved_objections(self) -> list[Objection]:
        return [o for o in self.objections.values() if o.is_resolved]

    def objections_for_claim(self, claim_id: str) -> list[Objection]:
        return [o for o in self.objections.values() if o.claim_id == claim_id]

    def open_objections_for_claim(self, claim_id: str) -> list[Objection]:
        return [o for o in self.objections_for_claim(claim_id) if o.is_open]

    def blocking_objections(self) -> list[Objection]:
        return [o for o in self.objections.values() if o.blocks_commit]

    def flagging_objections(self) -> list[Objection]:
        return [o for o in self.objections.values() if o.flags_review]

    def objections_by_agent(self, agent_id: str) -> list[Objection]:
        return [o for o in self.objections.values() if o.agent_id == agent_id]

    # =========================================================================
    # Commit Gate
    # =========================================================================

    def can_commit(self, claim_id: str) -> tuple[bool, list[Objection]]:
        """
        Check if a claim can be committed given outstanding objections.

        Returns (can_commit, blocking_objections).
        """
        blockers = [
            o for o in self.open_objections_for_claim(claim_id)
            if o.blocks_commit
        ]
        return len(blockers) == 0, blockers

    def claim_summary(self, claim_id: str) -> ClaimDissentSummary:
        """Get dissent summary for a claim."""
        objs = self.objections_for_claim(claim_id)
        open_objs = [o for o in objs if o.is_open]
        blocking = [o for o in open_objs if o.blocks_commit]
        flagging = [o for o in open_objs if o.flags_review]

        severities = [o.severity for o in open_objs]
        severity_order = [
            ObjectionSeverity.CRITICAL,
            ObjectionSeverity.HIGH,
            ObjectionSeverity.MEDIUM,
            ObjectionSeverity.LOW,
        ]
        highest = None
        for s in severity_order:
            if s in severities:
                highest = s
                break

        return ClaimDissentSummary(
            claim_id=claim_id,
            total_objections=len(objs),
            open_objections=len(open_objs),
            blocking_objections=len(blocking),
            flagging_objections=len(flagging),
            has_unresolved_dissent=len(open_objs) > 0,
            highest_severity=highest,
        )

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "total_objections": len(self.objections),
            "total_filed": self.total_objections_filed,
            "open": len(self.open_objections()),
            "blocking": len(self.blocking_objections()),
            "flagging": len(self.flagging_objections()),
            "accepted": self.total_objections_accepted,
            "dismissed": self.total_objections_dismissed,
            "escalated": self.total_objections_escalated,
            "confidence_snapshots": len(self.confidence_history),
        }

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "objections": {
                oid: o.to_dict() for oid, o in self.objections.items()
            },
            "metrics": self.get_metrics(),
        }


# =============================================================================
# Convenience
# =============================================================================


def create_dissent_ledger() -> DissentLedger:
    """Create a new dissent ledger."""
    return DissentLedger()
