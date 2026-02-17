# SPDX-License-Identifier: Apache-2.0
"""
SQLite-backed ledgers with epochs and transactional semantics.

Per MULTI_AGENT.md:
- Every ledger entry has an epoch (monotonic counter)
- Enables optimistic concurrency
- Conflicts are detected structurally
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
from .storage import Storage, get_storage


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
    epoch: int
    file_hashes: dict[str, str] = field(default_factory=dict)
    invalidated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "claim": self.claim.to_dict(),
            "receipt": self.receipt.to_dict(),
            "created_at": self.created_at.isoformat(),
            "epoch": self.epoch,
            "file_hashes": self.file_hashes,
            "invalidated_at": self.invalidated_at.isoformat() if self.invalidated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fact":
        return cls(
            id=UUID(data["id"]),
            claim=Claim.from_dict(data["claim"]),
            receipt=receipt_from_dict(data["receipt"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            epoch=data.get("epoch", 0),
            file_hashes=data.get("file_hashes", {}),
            invalidated_at=datetime.fromisoformat(data["invalidated_at"]) if data.get("invalidated_at") else None,
        )

    @classmethod
    def from_row(cls, row) -> "Fact":
        """Create Fact from SQLite row."""
        return cls(
            id=UUID(row["id"]),
            claim=Claim.from_dict(json.loads(row["claim_json"])),
            receipt=receipt_from_dict(json.loads(row["receipt_json"])),
            created_at=datetime.fromisoformat(row["created_at"]),
            epoch=row["epoch"],
            file_hashes=json.loads(row["file_hashes_json"]),
            invalidated_at=datetime.fromisoformat(row["invalidated_at"]) if row["invalidated_at"] else None,
        )

    @property
    def is_valid(self) -> bool:
        """Whether this fact is still valid (not invalidated)."""
        return self.invalidated_at is None


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
    epoch: int
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
            "epoch": self.epoch,
            "rationale": self.rationale,
            "supersedes": str(self.supersedes) if self.supersedes else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Decision":
        return cls(
            id=UUID(data["id"]),
            claim=Claim.from_dict(data["claim"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            epoch=data.get("epoch", 0),
            rationale=data.get("rationale"),
            supersedes=UUID(data["supersedes"]) if data.get("supersedes") else None,
        )

    @classmethod
    def from_row(cls, row) -> "Decision":
        """Create Decision from SQLite row."""
        return cls(
            id=UUID(row["id"]),
            claim=Claim.from_dict(json.loads(row["claim_json"])),
            created_at=datetime.fromisoformat(row["created_at"]),
            epoch=row["epoch"],
            rationale=row["rationale"],
            supersedes=UUID(row["supersedes_id"]) if row["supersedes_id"] else None,
        )


class ConflictError(Exception):
    """Raised when a conflict is detected."""

    def __init__(self, message: str, existing: Decision | None = None):
        super().__init__(message)
        self.existing = existing


class SQLiteFactLedger:
    """
    SQLite-backed ledger for empirical facts.

    Facts auto-invalidate when referenced files change.
    Supports epochs for optimistic concurrency.
    """

    def __init__(self, storage: Storage):
        self.storage = storage

    def add(
        self,
        claim: Claim,
        receipt: Receipt,
        file_hashes: dict[str, str] | None = None,
        agent_id: str | None = None,
    ) -> Fact:
        """
        Add a verified fact to the ledger.

        Args:
            claim: The claim being asserted.
            receipt: The receipt proving the claim.
            file_hashes: Hashes of files this fact depends on.
            agent_id: Optional agent ID for lease acquisition.

        Returns:
            The created Fact.
        """
        fact_id = uuid4()
        epoch = self.storage.next_epoch()
        now = datetime.now(timezone.utc)

        # Build scope for lease if agent_id provided
        if agent_id and claim.path:
            scope = f"facts/files/{claim.path}"
            lease = self.storage.acquire_lease(scope, agent_id)
            if not lease:
                raise ConflictError(f"Resource locked: {scope}")

        with self.storage.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO facts (id, claim_type, claim_json, receipt_json,
                                   file_hashes_json, epoch, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(fact_id),
                    claim.type.value,
                    json.dumps(claim.to_dict()),
                    json.dumps(receipt.to_dict()),
                    json.dumps(file_hashes or {}),
                    epoch,
                    now.isoformat(),
                )
            )

        # Release lease if we acquired one
        if agent_id and claim.path:
            self.storage.release_lease(scope, agent_id)

        return Fact(
            id=fact_id,
            claim=claim,
            receipt=receipt,
            created_at=now,
            epoch=epoch,
            file_hashes=file_hashes or {},
        )

    def get(self, fact_id: UUID) -> Fact | None:
        """Get a fact by ID."""
        row = self.storage.get_by_id("facts", str(fact_id))
        if not row:
            return None
        return Fact.from_row(row)

    def query(
        self,
        claim_type: ClaimType | None = None,
        path: str | None = None,
        valid_only: bool = True,
    ) -> list[Fact]:
        """
        Query facts with optional filters.

        Args:
            claim_type: Filter by claim type.
            path: Filter by path (for file-related claims).
            valid_only: Only return non-invalidated facts.

        Returns:
            List of matching facts, newest first.
        """
        sql = "SELECT * FROM facts WHERE 1=1"
        params: list[Any] = []

        if valid_only:
            sql += " AND invalidated_at IS NULL"

        if claim_type is not None:
            sql += " AND claim_type = ?"
            params.append(claim_type.value)

        if path is not None:
            # Need to check claim_json for path
            sql += " AND json_extract(claim_json, '$.path') = ?"
            params.append(path)

        sql += " ORDER BY created_at DESC"

        cursor = self.storage.conn.cursor()
        cursor.execute(sql, params)
        return [Fact.from_row(row) for row in cursor.fetchall()]

    def invalidate(self, fact_id: UUID) -> bool:
        """
        Invalidate (soft-delete) a fact.

        Returns True if the fact was found and invalidated.
        """
        now = datetime.now(timezone.utc)
        return self.storage.update(
            "facts", "id", str(fact_id),
            {"invalidated_at": now.isoformat()}
        )

    def check_staleness(self, fact: Fact, base_path: Path | None = None) -> bool:
        """
        Check if a fact is stale (referenced files have changed).

        Returns True if the fact is stale, False if still valid.
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
        for fact in self.query(valid_only=True):
            if self.check_staleness(fact, base_path):
                stale_ids.append(fact.id)
                self.invalidate(fact.id)

        return stale_ids

    @property
    def count(self) -> int:
        """Number of valid facts in the ledger."""
        cursor = self.storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM facts WHERE invalidated_at IS NULL")
        return cursor.fetchone()[0]

    def all(self, include_invalidated: bool = False) -> list[Fact]:
        """Get all facts."""
        return self.query(valid_only=not include_invalidated)

    def get_by_epoch(self, min_epoch: int) -> list[Fact]:
        """Get facts created since a specific epoch."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM facts WHERE epoch >= ? ORDER BY epoch",
            (min_epoch,)
        )
        return [Fact.from_row(row) for row in cursor.fetchall()]


class SQLiteDecisionLedger:
    """
    SQLite-backed ledger for normative decisions.

    Decisions persist until explicitly superseded.
    Supports epochs for optimistic concurrency.
    """

    def __init__(self, storage: Storage):
        self.storage = storage

    def add(
        self,
        claim: Claim,
        rationale: str | None = None,
        supersedes: UUID | None = None,
        check_conflict: bool = True,
    ) -> Decision:
        """
        Add a decision to the ledger.

        Args:
            claim: The DECISION claim.
            rationale: Optional explanation for the decision.
            supersedes: ID of decision this replaces (if revising).
            check_conflict: Whether to check for conflicts.

        Returns:
            The created Decision.

        Raises:
            ConflictError: If there's a conflicting decision for the same topic.
        """
        if claim.type != ClaimType.DECISION:
            raise ValueError("Decision must have DECISION claim type")

        # Check for conflict
        if check_conflict and not supersedes:
            existing = self.get_by_topic(claim.topic or "")
            if existing and existing.choice != claim.choice:
                raise ConflictError(
                    f"Conflict: topic '{claim.topic}' already has decision "
                    f"'{existing.choice}' (epoch {existing.epoch})",
                    existing=existing,
                )

        decision_id = uuid4()
        epoch = self.storage.next_epoch()
        now = datetime.now(timezone.utc)

        with self.storage.transaction() as cursor:
            cursor.execute(
                """
                INSERT INTO decisions (id, topic, choice, claim_json, rationale,
                                       supersedes_id, epoch, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(decision_id),
                    claim.topic or "",
                    claim.choice or "",
                    json.dumps(claim.to_dict()),
                    rationale,
                    str(supersedes) if supersedes else None,
                    epoch,
                    now.isoformat(),
                )
            )

        return Decision(
            id=decision_id,
            claim=claim,
            created_at=now,
            epoch=epoch,
            rationale=rationale,
            supersedes=supersedes,
        )

    def get(self, decision_id: UUID) -> Decision | None:
        """Get a decision by ID."""
        row = self.storage.get_by_id("decisions", str(decision_id))
        if not row:
            return None
        return Decision.from_row(row)

    def query(self, topic: str | None = None, active_only: bool = True) -> list[Decision]:
        """
        Query decisions.

        Args:
            topic: Filter by topic.
            active_only: Only return non-superseded decisions.

        Returns:
            List of decisions, newest first.
        """
        cursor = self.storage.conn.cursor()

        if active_only:
            # Get superseded IDs
            cursor.execute("SELECT supersedes_id FROM decisions WHERE supersedes_id IS NOT NULL")
            superseded_ids = {row[0] for row in cursor.fetchall()}

            sql = "SELECT * FROM decisions WHERE 1=1"
            params: list[Any] = []

            if topic:
                sql += " AND topic = ?"
                params.append(topic.lower())

            sql += " ORDER BY created_at DESC"

            cursor.execute(sql, params)
            decisions = [Decision.from_row(row) for row in cursor.fetchall()]

            # Filter out superseded
            return [d for d in decisions if str(d.id) not in superseded_ids]
        else:
            sql = "SELECT * FROM decisions"
            params = []

            if topic:
                sql += " WHERE topic = ?"
                params.append(topic.lower())

            sql += " ORDER BY created_at DESC"

            cursor.execute(sql, params)
            return [Decision.from_row(row) for row in cursor.fetchall()]

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
        if not self.get(old_decision_id):
            return None

        return self.add(
            claim=new_claim,
            rationale=rationale,
            supersedes=old_decision_id,
            check_conflict=False,  # We're explicitly revising
        )

    @property
    def count(self) -> int:
        """Total number of decisions (including superseded)."""
        cursor = self.storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM decisions")
        return cursor.fetchone()[0]

    @property
    def active_count(self) -> int:
        """Number of active (non-superseded) decisions."""
        return len(self.query())

    def all(self, include_superseded: bool = True) -> list[Decision]:
        """Get all decisions."""
        return self.query(active_only=not include_superseded)

    def get_by_epoch(self, min_epoch: int) -> list[Decision]:
        """Get decisions created since a specific epoch."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM decisions WHERE epoch >= ? ORDER BY epoch",
            (min_epoch,)
        )
        return [Decision.from_row(row) for row in cursor.fetchall()]


def get_ledgers(governor_dir: Path) -> tuple[SQLiteFactLedger, SQLiteDecisionLedger]:
    """
    Get SQLite-backed ledgers for a governor directory.

    Returns (fact_ledger, decision_ledger).
    """
    storage = get_storage(governor_dir)
    return SQLiteFactLedger(storage), SQLiteDecisionLedger(storage)
