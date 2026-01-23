"""Core types for the agent governor."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


class ProposalStatus(Enum):
    """Status of a proposal in the system."""
    PENDING = "pending"
    COMMITTED = "committed"
    REJECTED = "rejected"


@dataclass
class Evidence:
    """
    Evidence supporting a claim.
    
    Per NLAI: Language is a proposal, not an authority.
    Evidence must be external/verifiable, not model output.
    """
    type: str  # "file_exists", "test_passed", "api_verified", etc.
    source: str  # Path, URL, or identifier
    content_hash: Optional[str] = None  # SHA256 of verified content
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        # Evidence cannot be "model said so"
        forbidden_types = {"model_output", "self_consistency", "looks_right"}
        if self.type.lower() in forbidden_types:
            raise ValueError(f"Evidence type '{self.type}' violates NLAI - model output is not evidence")


@dataclass
class Contradiction:
    """A detected contradiction between claims."""
    existing_claim: str
    existing_commit_id: "CommitID"
    new_claim: str
    reason: str
    id: UUID = field(default_factory=uuid4)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __str__(self) -> str:
        return f"Contradiction: '{self.new_claim}' conflicts with '{self.existing_claim}' - {self.reason}"


@dataclass  
class ProposalResult:
    """Result of proposing a change to the governor."""
    status: ProposalStatus
    claim: str
    evidence: Optional[Evidence] = None
    contradiction: Optional[Contradiction] = None
    commit_id: Optional["CommitID"] = None
    rejection_reason: Optional[str] = None
    
    @property
    def accepted(self) -> bool:
        return self.status == ProposalStatus.COMMITTED
    
    @property
    def rejected(self) -> bool:
        return self.status == ProposalStatus.REJECTED


# Forward reference for type hints
CommitID = UUID
