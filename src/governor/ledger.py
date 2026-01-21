"""
CodebaseLedger: Append-only record of architectural decisions.

The ledger is the authoritative state. Per NLAI, no state update occurs
without evidence that passes the admissibility predicate.
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from .types import Evidence, Contradiction


CommitID = UUID


@dataclass
class Commitment:
    """
    A committed architectural decision with provenance.
    
    Once committed, cannot be modified - only superseded by explicit revision.
    """
    id: CommitID
    claim: str
    evidence: Evidence
    timestamp: datetime
    topic: str  # For queryability: "framework", "api", "pattern", etc.
    supersedes: Optional[CommitID] = None  # If this revises a prior commitment
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "claim": self.claim,
            "evidence": {
                "type": self.evidence.type,
                "source": self.evidence.source,
                "content_hash": self.evidence.content_hash,
                "timestamp": self.evidence.timestamp.isoformat(),
            },
            "timestamp": self.timestamp.isoformat(),
            "topic": self.topic,
            "supersedes": str(self.supersedes) if self.supersedes else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Commitment":
        return cls(
            id=UUID(data["id"]),
            claim=data["claim"],
            evidence=Evidence(
                type=data["evidence"]["type"],
                source=data["evidence"]["source"],
                content_hash=data["evidence"].get("content_hash"),
                timestamp=datetime.fromisoformat(data["evidence"]["timestamp"]),
            ),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            topic=data["topic"],
            supersedes=UUID(data["supersedes"]) if data.get("supersedes") else None,
        )


@dataclass
class RejectionRecord:
    """Record of a rejected proposal - for debugging and proof-of-concept."""
    id: UUID
    claim: str
    reason: str
    timestamp: datetime
    contradiction: Optional[Contradiction] = None
    
    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "claim": self.claim,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "contradiction": str(self.contradiction) if self.contradiction else None,
        }


class CodebaseLedger:
    """
    Append-only ledger of architectural commitments.
    
    Backed by a JSON file in .governor/ directory, designed to be
    git-tracked for version control and rollback.
    """
    
    LEDGER_DIR = ".governor"
    COMMITMENTS_FILE = "commitments.json"
    REJECTIONS_FILE = "rejections.json"
    
    def __init__(self, git_root: Path):
        self.git_root = Path(git_root)
        self.ledger_path = self.git_root / self.LEDGER_DIR
        self.commitments_path = self.ledger_path / self.COMMITMENTS_FILE
        self.rejections_path = self.ledger_path / self.REJECTIONS_FILE
        
        # In-memory cache
        self._commitments: list[Commitment] = []
        self._rejections: list[RejectionRecord] = []
        
        self._ensure_initialized()
        self._load()
    
    def _ensure_initialized(self) -> None:
        """Create ledger directory and files if they don't exist."""
        self.ledger_path.mkdir(exist_ok=True)
        
        if not self.commitments_path.exists():
            self.commitments_path.write_text("[]")
        
        if not self.rejections_path.exists():
            self.rejections_path.write_text("[]")
        
        # Create .gitignore to NOT ignore anything (we want this tracked)
        gitignore = self.ledger_path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# Governor ledger should be git-tracked\n")
    
    def _load(self) -> None:
        """Load commitments and rejections from disk."""
        commitments_data = json.loads(self.commitments_path.read_text())
        self._commitments = [Commitment.from_dict(c) for c in commitments_data]
        
        rejections_data = json.loads(self.rejections_path.read_text())
        self._rejections = [
            RejectionRecord(
                id=UUID(r["id"]),
                claim=r["claim"],
                reason=r["reason"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            for r in rejections_data
        ]
    
    def _save(self) -> None:
        """Persist current state to disk."""
        commitments_data = [c.to_dict() for c in self._commitments]
        self.commitments_path.write_text(json.dumps(commitments_data, indent=2))
        
        rejections_data = [r.to_dict() for r in self._rejections]
        self.rejections_path.write_text(json.dumps(rejections_data, indent=2))
    
    def commit(
        self,
        claim: str,
        evidence: Evidence,
        topic: str,
        supersedes: Optional[CommitID] = None,
    ) -> CommitID:
        """
        Commit a claim with evidence to the ledger.
        
        Returns the CommitID for future reference.
        """
        commitment = Commitment(
            id=uuid4(),
            claim=claim,
            evidence=evidence,
            timestamp=datetime.now(timezone.utc),
            topic=topic,
            supersedes=supersedes,
        )
        self._commitments.append(commitment)
        self._save()
        return commitment.id
    
    def record_rejection(
        self,
        claim: str,
        reason: str,
        contradiction: Optional[Contradiction] = None,
    ) -> None:
        """Record a rejected proposal for debugging/demo purposes."""
        rejection = RejectionRecord(
            id=uuid4(),
            claim=claim,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
            contradiction=contradiction,
        )
        self._rejections.append(rejection)
        self._save()
    
    def query(self, topic: Optional[str] = None) -> list[Commitment]:
        """
        Query commitments, optionally filtered by topic.
        
        Returns most recent commitments first, excluding superseded ones.
        """
        # Build set of superseded IDs
        superseded = {c.supersedes for c in self._commitments if c.supersedes}
        
        # Filter to active (non-superseded) commitments
        active = [c for c in self._commitments if c.id not in superseded]
        
        # Filter by topic if specified
        if topic:
            active = [c for c in active if c.topic.lower() == topic.lower()]
        
        # Return newest first
        return sorted(active, key=lambda c: c.timestamp, reverse=True)
    
    def get_commitment(self, commit_id: CommitID) -> Optional[Commitment]:
        """Get a specific commitment by ID."""
        for c in self._commitments:
            if c.id == commit_id:
                return c
        return None
    
    def check_contradiction(self, new_claim: str, topic: str) -> Optional[Contradiction]:
        """
        Check if a new claim contradicts existing commitments.
        
        This is a simple keyword/semantic check - production version would
        use embedding similarity or more sophisticated NLP.
        """
        active_commitments = self.query(topic)
        
        # Simple heuristic: check for direct negations or conflicting values
        # This is intentionally naive - the real value is the architecture,
        # not this specific implementation
        new_lower = new_claim.lower()
        
        for existing in active_commitments:
            existing_lower = existing.claim.lower()
            
            # Check for framework contradictions
            frameworks = ["react", "vue", "angular", "svelte", "solid"]
            for fw in frameworks:
                if fw in new_lower and any(
                    other in existing_lower 
                    for other in frameworks 
                    if other != fw
                ):
                    return Contradiction(
                        existing_claim=existing.claim,
                        existing_commit_id=existing.id,
                        new_claim=new_claim,
                        reason=f"Framework conflict: existing commitment uses different framework",
                    )
            
            # Check for "not X" vs "X" patterns
            if f"not {new_lower}" in existing_lower or f"not {existing_lower}" in new_lower:
                return Contradiction(
                    existing_claim=existing.claim,
                    existing_commit_id=existing.id,
                    new_claim=new_claim,
                    reason="Direct negation of existing commitment",
                )
        
        return None
    
    @property
    def rejection_count(self) -> int:
        """Number of rejected proposals - useful for telemetry."""
        return len(self._rejections)
    
    @property
    def commitment_count(self) -> int:
        """Number of total commitments."""
        return len(self._commitments)
    
    def get_rejections(self, limit: int = 50) -> list[RejectionRecord]:
        """Get recent rejections for debugging/demo."""
        return sorted(self._rejections, key=lambda r: r.timestamp, reverse=True)[:limit]
