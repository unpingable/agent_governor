# SPDX-License-Identifier: Apache-2.0
"""
Evidence persistence: SQLite-backed storage for evidence and agent run provenance.

Layer 1 of the evidence persistence stack. Provides:
- RunProvenance: tracks agent runs (model, prompt, tools, sources)
- EvidenceStore: append-only evidence storage with claim/agent/run queries
- Audit trail: JOIN queries across evidence + run_provenance

Design:
- Append-only: no update/delete methods for evidence (immutability invariant)
- Parallel to EpistemicLedger: does not read/write ledger state
- All writes use storage.transaction() for atomicity
- No FK constraints (logical FKs, application-enforced)
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .epistemic import EvidenceRef, EvidenceType
from .storage import Storage, get_storage


# =============================================================================
# Run Provenance
# =============================================================================


@dataclass
class RunProvenance:
    """
    Tracks provenance of an agent run.

    Each run captures the agent identity, model used, prompt/tool hashes,
    and source URLs consulted. Evidence records link back to runs via run_id.
    """

    run_id: str
    agent_id: str
    model_id: str | None = None
    prompt_hash: str | None = None
    tool_path_hash: str | None = None
    source_urls: frozenset[str] = field(default_factory=frozenset)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "model_id": self.model_id,
            "prompt_hash": self.prompt_hash,
            "tool_path_hash": self.tool_path_hash,
            "source_urls": sorted(self.source_urls),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunProvenance":
        return cls(
            run_id=data["run_id"],
            agent_id=data["agent_id"],
            model_id=data.get("model_id"),
            prompt_hash=data.get("prompt_hash"),
            tool_path_hash=data.get("tool_path_hash"),
            source_urls=frozenset(data.get("source_urls", [])),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    @classmethod
    def from_row(cls, row: Any) -> "RunProvenance":
        """Create from SQLite row."""
        urls = json.loads(row["source_urls_json"]) if row["source_urls_json"] else []
        return cls(
            run_id=row["run_id"],
            agent_id=row["agent_id"],
            model_id=row["model_id"],
            prompt_hash=row["prompt_hash"],
            tool_path_hash=row["tool_path_hash"],
            source_urls=frozenset(urls),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @classmethod
    def from_vote(cls, vote: Any) -> "RunProvenance":
        """Create RunProvenance from a Vote object."""
        return cls(
            run_id=f"run_{uuid.uuid4().hex[:12]}",
            agent_id=vote.agent_id,
            model_id=getattr(vote, "model_id", None),
            prompt_hash=getattr(vote, "prompt_hash", None),
            tool_path_hash=getattr(vote, "tool_path_hash", None),
            source_urls=frozenset(getattr(vote, "source_urls", frozenset())),
        )


# =============================================================================
# Evidence Store
# =============================================================================


class EvidenceStore:
    """
    Append-only evidence persistence backed by SQLite.

    Provides methods for:
    - Recording agent runs (run provenance)
    - Persisting evidence refs (linking to claims and runs)
    - Querying evidence by claim, kind, agent, or run
    - Audit trail queries (JOIN evidence + run_provenance)

    Immutability invariant: no update/delete methods for evidence.
    """

    def __init__(self, storage: Storage):
        self.storage = storage

    # =========================================================================
    # Run Provenance
    # =========================================================================

    def record_run(
        self,
        agent_id: str,
        model_id: str | None = None,
        prompt_hash: str | None = None,
        tool_path_hash: str | None = None,
        source_urls: frozenset[str] | None = None,
    ) -> RunProvenance:
        """Record an agent run. Returns the RunProvenance with generated run_id."""
        run = RunProvenance(
            run_id=f"run_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            model_id=model_id,
            prompt_hash=prompt_hash,
            tool_path_hash=tool_path_hash,
            source_urls=source_urls or frozenset(),
        )
        with self.storage.transaction() as cursor:
            cursor.execute(
                "INSERT INTO run_provenance "
                "(run_id, agent_id, model_id, prompt_hash, tool_path_hash, "
                "source_urls_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run.run_id,
                    run.agent_id,
                    run.model_id,
                    run.prompt_hash,
                    run.tool_path_hash,
                    json.dumps(sorted(run.source_urls)),
                    run.created_at.isoformat(),
                ),
            )
        return run

    def record_run_from_vote(self, vote: Any) -> RunProvenance:
        """Record a run from a Vote object. Extracts model_id, hashes, source_urls."""
        return self.record_run(
            agent_id=vote.agent_id,
            model_id=getattr(vote, "model_id", None),
            prompt_hash=getattr(vote, "prompt_hash", None),
            tool_path_hash=getattr(vote, "tool_path_hash", None),
            source_urls=frozenset(getattr(vote, "source_urls", frozenset())),
        )

    def get_run(self, run_id: str) -> RunProvenance | None:
        """Get a run by ID."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM run_provenance WHERE run_id = ?", (run_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return RunProvenance.from_row(row)

    def runs_by_agent(self, agent_id: str) -> list[RunProvenance]:
        """Get all runs for an agent, ordered by creation time."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM run_provenance WHERE agent_id = ? ORDER BY created_at",
            (agent_id,),
        )
        return [RunProvenance.from_row(row) for row in cursor.fetchall()]

    def run_count(self) -> int:
        """Get total number of recorded runs."""
        cursor = self.storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM run_provenance")
        row = cursor.fetchone()
        return row["cnt"]

    # =========================================================================
    # Evidence Persistence
    # =========================================================================

    def persist_evidence(
        self,
        claim_id: str,
        ref: EvidenceRef,
        collected_by: str | None = None,
        run_id: str | None = None,
    ) -> EvidenceRef:
        """
        Persist an EvidenceRef to SQLite.

        Populates persistence fields (evidence_id, claim_id, content_hash,
        collected_by, run_id, persisted_at) and returns the updated ref.
        """
        now = datetime.now(timezone.utc)
        evidence_id = ref.evidence_id or f"evi_{uuid.uuid4().hex[:12]}"
        content_hash = ref.compute_content_hash()

        with self.storage.transaction() as cursor:
            cursor.execute(
                "INSERT INTO evidence "
                "(evidence_id, claim_id, kind, content_hash, locator, scope, "
                "confidence, collected_by, run_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evidence_id,
                    claim_id,
                    ref.ref_type.value,
                    content_hash,
                    ref.locator,
                    ref.scope,
                    ref.confidence,
                    collected_by,
                    run_id,
                    now.isoformat(),
                ),
            )

        # Return updated ref with persistence fields populated
        ref.evidence_id = evidence_id
        ref.claim_id = claim_id
        ref.collected_by = collected_by
        ref.run_id = run_id
        ref.content_hash = content_hash
        ref.persisted_at = now
        return ref

    def get_evidence(self, evidence_id: str) -> EvidenceRef | None:
        """Get a single evidence ref by ID."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return EvidenceRef.from_row(row)

    def evidence_for_claim(self, claim_id: str) -> list[EvidenceRef]:
        """Get all evidence for a claim, ordered by creation time."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence WHERE claim_id = ? ORDER BY created_at",
            (claim_id,),
        )
        return [EvidenceRef.from_row(row) for row in cursor.fetchall()]

    def evidence_by_kind(self, kind: str) -> list[EvidenceRef]:
        """Get all evidence of a specific kind."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence WHERE kind = ? ORDER BY created_at",
            (kind,),
        )
        return [EvidenceRef.from_row(row) for row in cursor.fetchall()]

    def evidence_by_agent(self, agent_id: str) -> list[EvidenceRef]:
        """Get all evidence collected by a specific agent."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence WHERE collected_by = ? ORDER BY created_at",
            (agent_id,),
        )
        return [EvidenceRef.from_row(row) for row in cursor.fetchall()]

    def evidence_by_run(self, run_id: str) -> list[EvidenceRef]:
        """Get all evidence associated with a specific run."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        )
        return [EvidenceRef.from_row(row) for row in cursor.fetchall()]

    def evidence_count(self, claim_id: str | None = None) -> int:
        """Get evidence count. If claim_id provided, count for that claim only."""
        cursor = self.storage.conn.cursor()
        if claim_id is not None:
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM evidence WHERE claim_id = ?",
                (claim_id,),
            )
        else:
            cursor.execute("SELECT COUNT(*) as cnt FROM evidence")
        row = cursor.fetchone()
        return row["cnt"]

    # =========================================================================
    # Audit Trail
    # =========================================================================

    def audit_trail(
        self,
        agent_id: str | None = None,
        claim_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query evidence with run provenance JOIN.

        Filters by agent_id, claim_id, and/or run_id.
        Returns dicts with evidence + run provenance fields.
        """
        sql = (
            "SELECT e.*, r.agent_id as run_agent_id, r.model_id, "
            "r.prompt_hash as run_prompt_hash, r.tool_path_hash as run_tool_path_hash, "
            "r.source_urls_json, r.created_at as run_created_at "
            "FROM evidence e "
            "LEFT JOIN run_provenance r ON e.run_id = r.run_id "
            "WHERE 1=1"
        )
        params: list[Any] = []

        if agent_id is not None:
            sql += " AND (e.collected_by = ? OR r.agent_id = ?)"
            params.extend([agent_id, agent_id])
        if claim_id is not None:
            sql += " AND e.claim_id = ?"
            params.append(claim_id)
        if run_id is not None:
            sql += " AND e.run_id = ?"
            params.append(run_id)

        sql += " ORDER BY e.created_at"

        cursor = self.storage.conn.cursor()
        cursor.execute(sql, params)

        results = []
        for row in cursor.fetchall():
            entry: dict[str, Any] = {
                "evidence_id": row["evidence_id"],
                "claim_id": row["claim_id"],
                "kind": row["kind"],
                "content_hash": row["content_hash"],
                "locator": row["locator"],
                "scope": row["scope"],
                "confidence": row["confidence"],
                "collected_by": row["collected_by"],
                "run_id": row["run_id"],
                "created_at": row["created_at"],
            }
            # Add run provenance if joined
            if row["run_agent_id"] is not None:
                entry["run_provenance"] = {
                    "agent_id": row["run_agent_id"],
                    "model_id": row["model_id"],
                    "prompt_hash": row["run_prompt_hash"],
                    "tool_path_hash": row["run_tool_path_hash"],
                    "source_urls": json.loads(row["source_urls_json"])
                    if row["source_urls_json"]
                    else [],
                    "created_at": row["run_created_at"],
                }
            results.append(entry)

        return results


# =============================================================================
# Convenience
# =============================================================================


def create_evidence_store(governor_dir: Path) -> EvidenceStore:
    """Create an EvidenceStore for a governor directory."""
    storage = get_storage(governor_dir)
    return EvidenceStore(storage)
