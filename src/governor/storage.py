"""
SQLite storage backend with WAL mode for concurrent access.

Per MULTI_AGENT.md:
- ACID transactions out of the box
- Multiple readers, single writer (WAL mode)
- No external dependencies
- File-based = git-trackable schema, portable
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from uuid import UUID


# Schema version for migrations
SCHEMA_VERSION = 4


SCHEMA = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

-- Facts: empirical claims backed by receipts
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    claim_type TEXT NOT NULL,
    claim_json TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    file_hashes_json TEXT NOT NULL DEFAULT '{}',
    epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    invalidated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_facts_claim_type ON facts(claim_type);
CREATE INDEX IF NOT EXISTS idx_facts_epoch ON facts(epoch);
CREATE INDEX IF NOT EXISTS idx_facts_invalidated ON facts(invalidated_at);

-- Decisions: normative choices that persist
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    choice TEXT NOT NULL,
    claim_json TEXT NOT NULL,
    rationale TEXT,
    supersedes_id TEXT,
    epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (supersedes_id) REFERENCES decisions(id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_topic ON decisions(topic);
CREATE INDEX IF NOT EXISTS idx_decisions_epoch ON decisions(epoch);

-- Leases: resource locking during verification
CREATE TABLE IF NOT EXISTS leases (
    scope TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leases_expires ON leases(expires_at);
CREATE INDEX IF NOT EXISTS idx_leases_agent ON leases(agent_id);

-- Work reservations: coordination without hard locks
CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reservations_agent ON reservations(agent_id);
CREATE INDEX IF NOT EXISTS idx_reservations_expires ON reservations(expires_at);

-- Epoch counter (global monotonic)
CREATE TABLE IF NOT EXISTS epoch_counter (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    value INTEGER NOT NULL DEFAULT 0
);

-- Proposals (FSM state)
CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    claims_json TEXT NOT NULL,
    receipts_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    agent_id TEXT,
    epoch INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proposals_state ON proposals(state);
CREATE INDEX IF NOT EXISTS idx_proposals_agent ON proposals(agent_id);

-- Agents registry
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    agent_class TEXT NOT NULL,
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    registered_at TEXT NOT NULL,
    last_heartbeat TEXT NOT NULL,
    permissions_json TEXT NOT NULL DEFAULT '{}'
);

-- Rejections log
CREATE TABLE IF NOT EXISTS rejections (
    id TEXT PRIMARY KEY,
    proposal_id TEXT,
    claim_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    suggestion TEXT,
    created_at TEXT NOT NULL,
    agent_id TEXT,
    FOREIGN KEY (proposal_id) REFERENCES proposals(id)
);

CREATE INDEX IF NOT EXISTS idx_rejections_proposal ON rejections(proposal_id);
CREATE INDEX IF NOT EXISTS idx_rejections_created ON rejections(created_at);
"""


SCHEMA_V2 = """
-- Evidence persistence (Layer 1)
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content_hash TEXT,
    locator TEXT NOT NULL,
    scope TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    collected_by TEXT,
    run_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_kind ON evidence(kind);
CREATE INDEX IF NOT EXISTS idx_evidence_collected_by ON evidence(collected_by);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id);

-- Run provenance (Layer 1)
CREATE TABLE IF NOT EXISTS run_provenance (
    run_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    model_id TEXT,
    prompt_hash TEXT,
    tool_path_hash TEXT,
    source_urls_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_agent ON run_provenance(agent_id);
"""


SCHEMA_V3 = """
-- Layer 2: Commit level and assumptions on facts/decisions
ALTER TABLE facts ADD COLUMN commit_level TEXT;
ALTER TABLE facts ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE decisions ADD COLUMN commit_level TEXT;
ALTER TABLE decisions ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]';
"""

# Individual ALTER statements for migration (executescript can't mix ALTER with IF NOT EXISTS)
_SCHEMA_V3_STMTS = [
    "ALTER TABLE facts ADD COLUMN commit_level TEXT",
    "ALTER TABLE facts ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE decisions ADD COLUMN commit_level TEXT",
    "ALTER TABLE decisions ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]'",
]


SCHEMA_V4 = """
-- Epistemic claims persistence (Layer 2)
CREATE TABLE IF NOT EXISTS epistemic_claims (
    claim_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    provenance TEXT NOT NULL,
    confidence REAL NOT NULL,
    governance_status TEXT NOT NULL DEFAULT 'active',
    epistemic_status TEXT,
    commit_level TEXT,
    assumptions_json TEXT NOT NULL DEFAULT '[]',
    source_agent_id TEXT,
    created_at TEXT NOT NULL,
    created_at_step INTEGER NOT NULL DEFAULT 0,
    last_updated_at TEXT NOT NULL,
    last_updated_step INTEGER NOT NULL DEFAULT 0,
    retracted_at_step INTEGER,
    retraction_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_ec_provenance ON epistemic_claims(provenance);
CREATE INDEX IF NOT EXISTS idx_ec_governance ON epistemic_claims(governance_status);
CREATE INDEX IF NOT EXISTS idx_ec_epistemic ON epistemic_claims(epistemic_status);
CREATE INDEX IF NOT EXISTS idx_ec_commit ON epistemic_claims(commit_level);
CREATE INDEX IF NOT EXISTS idx_ec_agent ON epistemic_claims(source_agent_id);
CREATE INDEX IF NOT EXISTS idx_ec_hash ON epistemic_claims(content_hash);

-- Epistemic ledger metadata (singleton row)
CREATE TABLE IF NOT EXISTS epistemic_ledger_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    step INTEGER NOT NULL DEFAULT 0,
    total_claims_created INTEGER NOT NULL DEFAULT 0,
    total_promotions_attempted INTEGER NOT NULL DEFAULT 0,
    total_promotions_forbidden INTEGER NOT NULL DEFAULT 0,
    total_retractions INTEGER NOT NULL DEFAULT 0
);
"""


@dataclass
class Lease:
    """A resource lease for coordination."""
    scope: str
    agent_id: str
    acquired_at: datetime
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "agent_id": self.agent_id,
            "acquired_at": self.acquired_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


class Storage:
    """
    SQLite storage backend with WAL mode.

    Thread-safe with connection pooling per thread.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            # Enable WAL mode for concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys=ON")
            # Row factory for dict-like access
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return self._local.connection

    @property
    def conn(self) -> sqlite3.Connection:
        """Current thread's connection."""
        return self._get_connection()

    def _init_db(self) -> None:
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self.transaction() as cursor:
            # Check schema version
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            if not cursor.fetchone():
                # Fresh database - create schema
                cursor.executescript(SCHEMA)
                cursor.executescript(SCHEMA_V2)
                for stmt in _SCHEMA_V3_STMTS:
                    cursor.execute(stmt)
                cursor.executescript(SCHEMA_V4)
                cursor.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,)
                )
                # Initialize epoch counter
                cursor.execute(
                    "INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)"
                )
            else:
                # Check for migrations
                cursor.execute("SELECT version FROM schema_version")
                row = cursor.fetchone()
                current_version = row["version"] if row else 0
                if current_version < SCHEMA_VERSION:
                    self._migrate(cursor, current_version, SCHEMA_VERSION)

    def _migrate(
        self, cursor: sqlite3.Cursor, from_version: int, to_version: int
    ) -> None:
        """Run schema migrations."""
        if from_version < 2:
            cursor.executescript(SCHEMA_V2)
        if from_version < 3:
            for stmt in _SCHEMA_V3_STMTS:
                try:
                    cursor.execute(stmt)
                except sqlite3.OperationalError:
                    pass  # Column already exists (idempotent)
        if from_version < 4:
            cursor.executescript(SCHEMA_V4)
        cursor.execute(
            "UPDATE schema_version SET version = ?", (to_version,)
        )

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """
        Context manager for atomic transactions.

        Usage:
            with storage.transaction() as cursor:
                cursor.execute(...)
                cursor.execute(...)
            # Commits on exit, rolls back on exception
        """
        conn = self.conn
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def next_epoch(self) -> int:
        """
        Get and increment the global epoch counter.

        Atomic operation.
        """
        with self.transaction() as cursor:
            cursor.execute(
                "UPDATE epoch_counter SET value = value + 1 WHERE id = 1"
            )
            cursor.execute("SELECT value FROM epoch_counter WHERE id = 1")
            row = cursor.fetchone()
            return row["value"]

    def current_epoch(self) -> int:
        """Get current epoch without incrementing."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM epoch_counter WHERE id = 1")
        row = cursor.fetchone()
        return row["value"] if row else 0

    # =========================================================================
    # Lease operations
    # =========================================================================

    def acquire_lease(
        self,
        scope: str,
        agent_id: str,
        ttl_seconds: int = 300,
    ) -> Lease | None:
        """
        Try to acquire a lease on a scope.

        Returns the Lease if acquired, None if already held by another agent.
        """
        now = datetime.now(timezone.utc)
        expires_at = now + __import__("datetime").timedelta(seconds=ttl_seconds)

        with self.transaction() as cursor:
            # First, clean up expired leases
            cursor.execute(
                "DELETE FROM leases WHERE expires_at < ?",
                (now.isoformat(),)
            )

            # Check if scope is already leased
            cursor.execute(
                "SELECT agent_id, expires_at FROM leases WHERE scope = ?",
                (scope,)
            )
            row = cursor.fetchone()

            if row:
                if row["agent_id"] == agent_id:
                    # Same agent - extend lease
                    cursor.execute(
                        "UPDATE leases SET expires_at = ? WHERE scope = ?",
                        (expires_at.isoformat(), scope)
                    )
                    return Lease(
                        scope=scope,
                        agent_id=agent_id,
                        acquired_at=now,
                        expires_at=expires_at,
                    )
                else:
                    # Different agent holds it
                    return None

            # Acquire new lease
            cursor.execute(
                "INSERT INTO leases (scope, agent_id, acquired_at, expires_at) VALUES (?, ?, ?, ?)",
                (scope, agent_id, now.isoformat(), expires_at.isoformat())
            )

            return Lease(
                scope=scope,
                agent_id=agent_id,
                acquired_at=now,
                expires_at=expires_at,
            )

    def release_lease(self, scope: str, agent_id: str) -> bool:
        """
        Release a lease.

        Returns True if released, False if not held by this agent.
        """
        with self.transaction() as cursor:
            cursor.execute(
                "DELETE FROM leases WHERE scope = ? AND agent_id = ?",
                (scope, agent_id)
            )
            return cursor.rowcount > 0

    def get_lease(self, scope: str) -> Lease | None:
        """Get current lease for a scope, if any."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM leases WHERE scope = ?",
            (scope,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        lease = Lease(
            scope=row["scope"],
            agent_id=row["agent_id"],
            acquired_at=datetime.fromisoformat(row["acquired_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
        )

        # Check if expired
        if lease.is_expired():
            self.release_lease(scope, lease.agent_id)
            return None

        return lease

    def cleanup_expired_leases(self) -> int:
        """Remove all expired leases. Returns count removed."""
        now = datetime.now(timezone.utc)
        with self.transaction() as cursor:
            cursor.execute(
                "DELETE FROM leases WHERE expires_at < ?",
                (now.isoformat(),)
            )
            return cursor.rowcount

    # =========================================================================
    # Generic CRUD helpers
    # =========================================================================

    def insert(
        self,
        table: str,
        data: dict[str, Any],
    ) -> None:
        """Insert a row into a table."""
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = list(data.values())

        with self.transaction() as cursor:
            cursor.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                values
            )

    def update(
        self,
        table: str,
        id_column: str,
        id_value: Any,
        data: dict[str, Any],
    ) -> bool:
        """Update a row. Returns True if row existed."""
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        values = list(data.values()) + [id_value]

        with self.transaction() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {set_clause} WHERE {id_column} = ?",
                values
            )
            return cursor.rowcount > 0

    def delete(
        self,
        table: str,
        id_column: str,
        id_value: Any,
    ) -> bool:
        """Delete a row. Returns True if row existed."""
        with self.transaction() as cursor:
            cursor.execute(
                f"DELETE FROM {table} WHERE {id_column} = ?",
                (id_value,)
            )
            return cursor.rowcount > 0

    def query(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        """Query rows from a table."""
        sql = f"SELECT * FROM {table}"
        params: list[Any] = []

        if where:
            conditions = " AND ".join(f"{k} = ?" for k in where.keys())
            sql += f" WHERE {conditions}"
            params.extend(where.values())

        if order_by:
            sql += f" ORDER BY {order_by}"

        if limit:
            sql += f" LIMIT {limit}"

        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()

    def get_by_id(self, table: str, id_value: str) -> sqlite3.Row | None:
        """Get a row by ID."""
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM {table} WHERE id = ?", (id_value,))
        return cursor.fetchone()

    def close(self) -> None:
        """Close the connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


def get_storage(governor_dir: Path) -> Storage:
    """Get or create storage for a governor directory."""
    db_path = governor_dir / "governor.db"
    return Storage(db_path)
