"""
Finite State Machine for proposal lifecycle.

States: DRAFT → PROPOSED → VERIFIED → APPLIED

Per BUILD_SPEC:
- DRAFT: Agent speculation. Nothing persistent. Expires.
- PROPOSED: Structured claims + pointers submitted. Waiting for verification.
- VERIFIED: Governor has run checks and produced receipts. Ready to apply.
- APPLIED: Patch written to working tree. Facts/decisions updated.

Rejection always returns to DRAFT with structured feedback.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from .claims import Claim
from .receipts import Receipt


class ProposalState(Enum):
    """States in the proposal lifecycle."""

    DRAFT = "draft"
    """Agent speculation. Nothing persistent."""

    PROPOSED = "proposed"
    """Claims submitted, waiting for verification."""

    VERIFIED = "verified"
    """Governor verified claims, receipts produced. Ready to apply."""

    APPLIED = "applied"
    """Patch applied to working tree."""

    REJECTED = "rejected"
    """Proposal rejected. Terminal state with feedback."""


class TransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: ProposalState, to_state: ProposalState, reason: str):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(
            f"Cannot transition from {from_state.value} to {to_state.value}: {reason}"
        )


@dataclass
class ClaimError:
    """Detailed error for a specific claim."""

    claim_index: int
    error_type: str  # "file_not_found", "verification_failed", etc.
    message: str
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "claim_index": self.claim_index,
            "error_type": self.error_type,
            "message": self.message,
        }
        if self.suggestion:
            data["suggestion"] = self.suggestion
        return data


@dataclass
class RejectionInfo:
    """Structured feedback when a proposal is rejected."""

    reason: str
    missing_receipts: list[str] = field(default_factory=list)
    """Receipt types that were required but not produced."""

    conflicting_decisions: list[UUID] = field(default_factory=list)
    """IDs of decisions that conflict with the proposal."""

    failed_claims: list[int] = field(default_factory=list)
    """Indices of claims that failed verification."""

    claim_errors: list[ClaimError] = field(default_factory=list)
    """Detailed errors for each failed claim."""

    details: dict[str, Any] = field(default_factory=dict)
    """Additional structured feedback."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "missing_receipts": self.missing_receipts,
            "conflicting_decisions": [str(d) for d in self.conflicting_decisions],
            "failed_claims": self.failed_claims,
            "claim_errors": [e.to_dict() for e in self.claim_errors],
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RejectionInfo":
        claim_errors = []
        for e in data.get("claim_errors", []):
            claim_errors.append(ClaimError(
                claim_index=e["claim_index"],
                error_type=e["error_type"],
                message=e["message"],
                suggestion=e.get("suggestion"),
            ))

        return cls(
            reason=data["reason"],
            missing_receipts=data.get("missing_receipts", []),
            conflicting_decisions=[
                UUID(d) for d in data.get("conflicting_decisions", [])
            ],
            failed_claims=data.get("failed_claims", []),
            claim_errors=claim_errors,
            details=data.get("details", {}),
        )

    def get_suggestions(self) -> list[str]:
        """Get actionable suggestions for resolving the rejection."""
        suggestions = []

        if self.conflicting_decisions:
            suggestions.append(
                "Use 'governor revise <decision-id>' to explicitly change a decision"
            )

        if self.missing_receipts:
            suggestions.append(
                "Ensure files exist and tests pass before proposing"
            )

        for error in self.claim_errors:
            if error.suggestion:
                suggestions.append(error.suggestion)

        if not suggestions:
            suggestions.append("Review the error details and fix the issues")

        return suggestions


@dataclass
class Proposal:
    """
    A proposal moving through the state machine.

    Tracks claims, receipts, and state transitions.
    """

    id: UUID
    claims: list[Claim]
    state: ProposalState
    created_at: datetime

    # Populated during verification
    receipts: list[Receipt] = field(default_factory=list)

    # Populated on rejection
    rejection: RejectionInfo | None = None

    # Metadata
    patch_path: str | None = None
    """Path to the patch file, if this is a changeset proposal."""

    applied_at: datetime | None = None
    """Timestamp when the proposal was applied."""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": str(self.id),
            "claims": [c.to_dict() for c in self.claims],
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "receipts": [r.to_dict() for r in self.receipts],
            "patch_path": self.patch_path,
        }

        if self.rejection:
            data["rejection"] = self.rejection.to_dict()

        if self.applied_at:
            data["applied_at"] = self.applied_at.isoformat()

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Proposal":
        from .receipts import receipt_from_dict

        return cls(
            id=UUID(data["id"]),
            claims=[Claim.from_dict(c) for c in data["claims"]],
            state=ProposalState(data["state"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            receipts=[receipt_from_dict(r) for r in data.get("receipts", [])],
            rejection=RejectionInfo.from_dict(data["rejection"])
                if data.get("rejection") else None,
            patch_path=data.get("patch_path"),
            applied_at=datetime.fromisoformat(data["applied_at"])
                if data.get("applied_at") else None,
        )


# Valid state transitions
_VALID_TRANSITIONS: dict[ProposalState, set[ProposalState]] = {
    ProposalState.DRAFT: {ProposalState.PROPOSED, ProposalState.REJECTED},
    ProposalState.PROPOSED: {ProposalState.VERIFIED, ProposalState.REJECTED},
    ProposalState.VERIFIED: {ProposalState.APPLIED, ProposalState.REJECTED},
    ProposalState.APPLIED: set(),  # Terminal state
    ProposalState.REJECTED: {ProposalState.DRAFT},  # Can retry from draft
}


class ProposalFSM:
    """
    State machine for managing proposal lifecycle.

    Enforces valid transitions and guards.
    """

    def __init__(self, proposal: Proposal):
        self.proposal = proposal

    @classmethod
    def create(cls, claims: list[Claim], patch_path: str | None = None) -> "ProposalFSM":
        """Create a new proposal in DRAFT state."""
        proposal = Proposal(
            id=uuid4(),
            claims=claims,
            state=ProposalState.DRAFT,
            created_at=datetime.now(timezone.utc),
            patch_path=patch_path,
        )
        return cls(proposal)

    @property
    def state(self) -> ProposalState:
        """Current state of the proposal."""
        return self.proposal.state

    @property
    def can_propose(self) -> bool:
        """Whether the proposal can transition to PROPOSED."""
        return ProposalState.PROPOSED in _VALID_TRANSITIONS.get(self.state, set())

    @property
    def can_verify(self) -> bool:
        """Whether the proposal can transition to VERIFIED."""
        return ProposalState.VERIFIED in _VALID_TRANSITIONS.get(self.state, set())

    @property
    def can_apply(self) -> bool:
        """Whether the proposal can transition to APPLIED."""
        return ProposalState.APPLIED in _VALID_TRANSITIONS.get(self.state, set())

    @property
    def is_terminal(self) -> bool:
        """Whether the proposal is in a terminal state."""
        return self.state == ProposalState.APPLIED

    def _transition(self, new_state: ProposalState, reason: str = "") -> None:
        """
        Attempt a state transition.

        Raises TransitionError if the transition is invalid.
        """
        valid_targets = _VALID_TRANSITIONS.get(self.state, set())

        if new_state not in valid_targets:
            raise TransitionError(
                self.state,
                new_state,
                reason or f"Not a valid transition from {self.state.value}",
            )

        self.proposal.state = new_state

    def propose(self) -> None:
        """
        Transition from DRAFT to PROPOSED.

        Call this after claims have been structured and submitted.
        """
        if not self.proposal.claims:
            raise TransitionError(
                self.state,
                ProposalState.PROPOSED,
                "Cannot propose with no claims",
            )

        self._transition(ProposalState.PROPOSED)

    def verify(self, receipts: list[Receipt]) -> None:
        """
        Transition from PROPOSED to VERIFIED.

        Call this after all claims have been verified and receipts produced.

        Args:
            receipts: The receipts proving the claims.
        """
        if not receipts:
            raise TransitionError(
                self.state,
                ProposalState.VERIFIED,
                "Cannot verify without receipts",
            )

        self._transition(ProposalState.VERIFIED)
        self.proposal.receipts = receipts

    def apply(self) -> None:
        """
        Transition from VERIFIED to APPLIED.

        Call this after the patch has been applied to the working tree.
        """
        self._transition(ProposalState.APPLIED)
        self.proposal.applied_at = datetime.now(timezone.utc)

    def reject(self, rejection: RejectionInfo) -> None:
        """
        Reject the proposal with structured feedback.

        Can be called from DRAFT, PROPOSED, or VERIFIED states.
        """
        if self.state == ProposalState.APPLIED:
            raise TransitionError(
                self.state,
                ProposalState.REJECTED,
                "Cannot reject an already-applied proposal",
            )

        self._transition(ProposalState.REJECTED)
        self.proposal.rejection = rejection

    def reset_to_draft(self) -> None:
        """
        Reset a rejected proposal back to DRAFT for retry.

        Clears rejection info and receipts.
        """
        if self.state != ProposalState.REJECTED:
            raise TransitionError(
                self.state,
                ProposalState.DRAFT,
                "Can only reset to draft from rejected state",
            )

        self._transition(ProposalState.DRAFT)
        self.proposal.rejection = None
        self.proposal.receipts = []


def create_proposal(
    claims: list[Claim],
    patch_path: str | None = None,
) -> ProposalFSM:
    """
    Convenience function to create a new proposal.

    Args:
        claims: The claims being made.
        patch_path: Optional path to the patch file.

    Returns:
        A ProposalFSM in DRAFT state.
    """
    return ProposalFSM.create(claims, patch_path)
