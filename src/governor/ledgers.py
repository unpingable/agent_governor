"""
Split ledgers: Facts vs Decisions.

Per BUILD_SPEC:
- facts/ = empirical, auto-decays when files change
- decisions/ = normative, persists until explicitly revised

Don't mix these. "Tests pass" is a fact. "We use React" is a decision.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .claims import Claim, ClaimType
from .receipts import Receipt, receipt_from_dict


@dataclass
class Fact:
    """
    A verified fact backed by a receipt.

    Facts are empirical - they can become stale when the underlying
    files change. Each fact references the receipt that proves it.
    """

    id: UUID
    claim: Claim
    receipt: Receipt
    created_at: datetime
    file_hashes: dict[str, str] = field(default_factory=dict)
    """Hashes of files this fact depends on, for staleness detection."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "claim": self.claim.to_dict(),
            "receipt": self.receipt.to_dict(),
            "created_at": self.created_at.isoformat(),
            "file_hashes": self.file_hashes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fact":
        return cls(
            id=UUID(data["id"]),
            claim=Claim.from_dict(data["claim"]),
            receipt=receipt_from_dict(data["receipt"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            file_hashes=data.get("file_hashes", {}),
        )


@dataclass
class Decision:
    """
    A normative decision with provenance.

    Decisions persist until explicitly revised. They represent
    architectural choices, not empirical facts.
    """

    id: UUID
    claim: Claim  # Must be ClaimType.DECISION
    created_at: datetime
    rationale: str | None = None
    supersedes: UUID | None = None

    def __post_init__(self) -> None:
        if self.claim.type != ClaimType.DECISION:
            raise ValueError(
                f"Decision must have DECISION claim type, got {self.claim.type}"
            )

    @property
    def topic(self) -> str:
        """The decision topic (e.g., 'framework', 'database')."""
        return self.claim.topic or ""

    @property
    def choice(self) -> str:
        """The decision choice (e.g., 'react', 'postgresql')."""
        return self.claim.choice or ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "claim": self.claim.to_dict(),
            "created_at": self.created_at.isoformat(),
            "rationale": self.rationale,
            "supersedes": str(self.supersedes) if self.supersedes else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Decision":
        return cls(
            id=UUID(data["id"]),
            claim=Claim.from_dict(data["claim"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            rationale=data.get("rationale"),
            supersedes=UUID(data["supersedes"]) if data.get("supersedes") else None,
        )


class FactLedger:
    """
    Ledger for empirical facts backed by receipts.

    Facts auto-invalidate when referenced files change.
    """

    def __init__(self, governor_dir: Path):
        self.governor_dir = Path(governor_dir)
        self.facts_dir = self.governor_dir / "facts"
        self.index_path = self.facts_dir / "index.json"
        self.receipts_dir = self.facts_dir / "receipts"

        self._facts: dict[UUID, Fact] = {}
        self._ensure_initialized()
        self._load()

    def _ensure_initialized(self) -> None:
        """Create directory structure if needed."""
        self.facts_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(exist_ok=True)

        if not self.index_path.exists():
            self.index_path.write_text("[]")

    def _load(self) -> None:
        """Load facts from disk."""
        data = json.loads(self.index_path.read_text())
        self._facts = {UUID(f["id"]): Fact.from_dict(f) for f in data}

    def _save(self) -> None:
        """Persist facts to disk."""
        data = [f.to_dict() for f in self._facts.values()]
        self.index_path.write_text(json.dumps(data, indent=2))

    def add(
        self,
        claim: Claim,
        receipt: Receipt,
        file_hashes: dict[str, str] | None = None,
    ) -> Fact:
        """
        Add a verified fact to the ledger.

        Args:
            claim: The claim being asserted.
            receipt: The receipt proving the claim.
            file_hashes: Hashes of files this fact depends on.

        Returns:
            The created Fact.
        """
        fact = Fact(
            id=uuid4(),
            claim=claim,
            receipt=receipt,
            created_at=datetime.now(timezone.utc),
            file_hashes=file_hashes or {},
        )
        self._facts[fact.id] = fact
        self._save()
        return fact

    def get(self, fact_id: UUID) -> Fact | None:
        """Get a fact by ID."""
        return self._facts.get(fact_id)

    def query(
        self,
        claim_type: ClaimType | None = None,
        path: str | None = None,
    ) -> list[Fact]:
        """
        Query facts with optional filters.

        Args:
            claim_type: Filter by claim type.
            path: Filter by path (for file-related claims).

        Returns:
            List of matching facts, newest first.
        """
        results = list(self._facts.values())

        if claim_type is not None:
            results = [f for f in results if f.claim.type == claim_type]

        if path is not None:
            results = [f for f in results if f.claim.path == path]

        return sorted(results, key=lambda f: f.created_at, reverse=True)

    def invalidate(self, fact_id: UUID) -> bool:
        """
        Invalidate (remove) a fact.

        Returns True if the fact was found and removed.
        """
        if fact_id in self._facts:
            del self._facts[fact_id]
            self._save()
            return True
        return False

    def check_staleness(self, fact: Fact, base_path: Path | None = None) -> bool:
        """
        Check if a fact is stale (referenced files have changed).

        Args:
            fact: The fact to check.
            base_path: Base path for resolving relative file paths.

        Returns:
            True if the fact is stale, False if still valid.
        """
        if not fact.file_hashes:
            return False

        base = base_path or Path.cwd()

        for path, expected_hash in fact.file_hashes.items():
            full_path = base / path
            if not full_path.exists():
                return True  # File deleted = stale

            current_hash = hashlib.sha256(full_path.read_bytes()).hexdigest()
            if current_hash != expected_hash:
                return True  # File changed = stale

        return False

    def invalidate_stale(self, base_path: Path | None = None) -> list[UUID]:
        """
        Find and invalidate all stale facts.

        Returns list of invalidated fact IDs.
        """
        stale_ids = []
        for fact in list(self._facts.values()):
            if self.check_staleness(fact, base_path):
                stale_ids.append(fact.id)

        for fact_id in stale_ids:
            self.invalidate(fact_id)

        return stale_ids

    @property
    def count(self) -> int:
        """Number of facts in the ledger."""
        return len(self._facts)

    def all(self) -> list[Fact]:
        """Get all facts."""
        return list(self._facts.values())

    def get_changed_files_git(self, base_path: Path | None = None) -> set[str]:
        """
        Get files that have changed since last commit using git.

        Returns set of changed file paths (relative to repo root).
        """
        import subprocess

        base = base_path or Path.cwd()

        try:
            # Get uncommitted changes (staged + unstaged)
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=base,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return set()

            changed = set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()

            # Also get untracked files that might affect facts
            result2 = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=base,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result2.returncode == 0:
                for line in result2.stdout.strip().split("\n"):
                    if line and len(line) > 3:
                        # Format is "XY filename" where XY is status
                        changed.add(line[3:].strip())

            return changed

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return set()

    def invalidate_by_changed_files(
        self,
        changed_files: set[str],
        base_path: Path | None = None,
    ) -> list[UUID]:
        """
        Invalidate facts that depend on any of the changed files.

        Args:
            changed_files: Set of changed file paths.
            base_path: Base path for the project.

        Returns:
            List of invalidated fact IDs.
        """
        invalidated = []

        for fact in list(self._facts.values()):
            # Check if any of the fact's dependencies changed
            fact_files = set(fact.file_hashes.keys())

            # Also check the claim's path if it's a file-based claim
            if fact.claim.path:
                fact_files.add(fact.claim.path)

            if fact_files & changed_files:
                invalidated.append(fact.id)
                self.invalidate(fact.id)

        return invalidated

    def decay_check(self, base_path: Path | None = None) -> dict[str, list[UUID]]:
        """
        Perform a full decay check using both git and hash-based detection.

        Returns dict with 'git_invalidated' and 'hash_invalidated' lists.
        """
        base = base_path or Path.cwd()
        result = {"git_invalidated": [], "hash_invalidated": []}

        # First, check git for changed files
        changed = self.get_changed_files_git(base)
        if changed:
            result["git_invalidated"] = self.invalidate_by_changed_files(changed, base)

        # Then, hash-check remaining facts
        result["hash_invalidated"] = self.invalidate_stale(base)

        return result


class DecisionLedger:
    """
    Ledger for normative decisions.

    Decisions persist until explicitly superseded.
    """

    def __init__(self, governor_dir: Path):
        self.governor_dir = Path(governor_dir)
        self.decisions_dir = self.governor_dir / "decisions"
        self.index_path = self.decisions_dir / "index.json"

        self._decisions: dict[UUID, Decision] = {}
        self._ensure_initialized()
        self._load()

    def _ensure_initialized(self) -> None:
        """Create directory structure if needed."""
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

        if not self.index_path.exists():
            self.index_path.write_text("[]")

    def _load(self) -> None:
        """Load decisions from disk."""
        data = json.loads(self.index_path.read_text())
        self._decisions = {UUID(d["id"]): Decision.from_dict(d) for d in data}

    def _save(self) -> None:
        """Persist decisions to disk."""
        data = [d.to_dict() for d in self._decisions.values()]
        self.index_path.write_text(json.dumps(data, indent=2))

    def add(
        self,
        claim: Claim,
        rationale: str | None = None,
        supersedes: UUID | None = None,
    ) -> Decision:
        """
        Add a decision to the ledger.

        Args:
            claim: The DECISION claim.
            rationale: Optional explanation for the decision.
            supersedes: ID of decision this replaces (if revising).

        Returns:
            The created Decision.
        """
        decision = Decision(
            id=uuid4(),
            claim=claim,
            created_at=datetime.now(timezone.utc),
            rationale=rationale,
            supersedes=supersedes,
        )
        self._decisions[decision.id] = decision
        self._save()
        return decision

    def get(self, decision_id: UUID) -> Decision | None:
        """Get a decision by ID."""
        return self._decisions.get(decision_id)

    def query(self, topic: str | None = None) -> list[Decision]:
        """
        Query active decisions.

        Active = not superseded by another decision.

        Args:
            topic: Filter by topic.

        Returns:
            List of active decisions, newest first.
        """
        # Find superseded IDs
        superseded_ids = {
            d.supersedes for d in self._decisions.values() if d.supersedes
        }

        # Filter to active decisions
        active = [d for d in self._decisions.values() if d.id not in superseded_ids]

        if topic is not None:
            active = [d for d in active if d.topic.lower() == topic.lower()]

        return sorted(active, key=lambda d: d.created_at, reverse=True)

    def get_by_topic(self, topic: str) -> Decision | None:
        """
        Get the current active decision for a topic.

        Returns the most recent non-superseded decision for the topic.
        """
        decisions = self.query(topic)
        return decisions[0] if decisions else None

    def check_conflict(self, claim: Claim) -> Decision | None:
        """
        Check if a decision claim conflicts with existing decisions.

        A conflict occurs when there's already an active decision
        for the same topic with a different choice.

        Returns the conflicting decision, or None if no conflict.
        """
        if claim.type != ClaimType.DECISION:
            return None

        existing = self.get_by_topic(claim.topic or "")
        if existing and existing.choice != claim.choice:
            return existing

        return None

    def revise(
        self,
        old_decision_id: UUID,
        new_claim: Claim,
        rationale: str | None = None,
    ) -> Decision | None:
        """
        Revise an existing decision.

        Args:
            old_decision_id: The decision to supersede.
            new_claim: The new DECISION claim.
            rationale: Explanation for the revision.

        Returns:
            The new Decision, or None if old decision not found.
        """
        if old_decision_id not in self._decisions:
            return None

        return self.add(claim=new_claim, rationale=rationale, supersedes=old_decision_id)

    @property
    def count(self) -> int:
        """Total number of decisions (including superseded)."""
        return len(self._decisions)

    @property
    def active_count(self) -> int:
        """Number of active (non-superseded) decisions."""
        return len(self.query())

    def all(self) -> list[Decision]:
        """Get all decisions (including superseded)."""
        return list(self._decisions.values())
