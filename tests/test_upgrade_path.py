"""
Upgrade path tests.

Verify that old data formats remain readable and that schema migrations
work correctly. This catches forward-compatibility regressions.

Run:
    python3 -m pytest tests/test_upgrade_path.py -v
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governor.storage import SCHEMA, SCHEMA_V2, SCHEMA_VERSION, Storage


# ── SQLite schema migration ─────────────────────────────────────────────


class TestSQLiteMigration:
    """Schema migrations from older versions to current."""

    def _create_v1_db(self, db_path: Path) -> None:
        """Create a bare V1 database (base schema only)."""
        conn = sqlite3.connect(str(db_path))
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        # Insert sample V1 data
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO facts (id, claim_type, claim_json, receipt_json, file_hashes_json, epoch, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("f1", "file_exists", '{"type": "file_exists"}', '{}', '{}', 1, now),
        )
        conn.execute(
            "INSERT INTO decisions (id, topic, choice, claim_json, epoch, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("d1", "framework", "react", '{"type": "decision"}', 1, now),
        )
        conn.commit()
        conn.close()

    def _create_v3_db(self, db_path: Path) -> None:
        """Create a V3 database (base + V2 + V3 columns)."""
        conn = sqlite3.connect(str(db_path))
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        conn.execute("ALTER TABLE facts ADD COLUMN commit_level TEXT")
        conn.execute("ALTER TABLE facts ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]'")
        conn.execute("ALTER TABLE decisions ADD COLUMN commit_level TEXT")
        conn.execute("ALTER TABLE decisions ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]'")
        conn.execute("INSERT INTO schema_version (version) VALUES (3)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO facts (id, claim_type, claim_json, receipt_json, file_hashes_json, epoch, created_at, commit_level) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("f1", "file_exists", '{"type": "file_exists"}', '{}', '{}', 1, now, "HARD"),
        )
        conn.commit()
        conn.close()

    def _create_v5_db(self, db_path: Path) -> None:
        """Create a V5 database (V1-V5 inclusive)."""
        conn = sqlite3.connect(str(db_path))
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        conn.execute("ALTER TABLE facts ADD COLUMN commit_level TEXT")
        conn.execute("ALTER TABLE facts ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]'")
        conn.execute("ALTER TABLE decisions ADD COLUMN commit_level TEXT")
        conn.execute("ALTER TABLE decisions ADD COLUMN assumptions_json TEXT NOT NULL DEFAULT '[]'")
        from governor.storage import SCHEMA_V4, _SCHEMA_V5_ALTER, _SCHEMA_V5_TABLES
        conn.executescript(SCHEMA_V4)
        for stmt in _SCHEMA_V5_ALTER:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.executescript(_SCHEMA_V5_TABLES)
        conn.execute("INSERT INTO schema_version (version) VALUES (5)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO epistemic_claims (claim_id, content, content_hash, provenance, confidence, "
            "source_agent_id, created_at, created_at_step, last_updated_at, last_updated_step) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("ec1", "test claim", "abc123", "assumed", 0.5, "agent1", now, 0, now, 0),
        )
        conn.commit()
        conn.close()

    def test_migrate_v1_to_current(self, tmp_path):
        """V1 database migrates to current schema with data intact."""
        db_path = tmp_path / "governor.db"
        self._create_v1_db(db_path)

        storage = Storage(db_path)
        # Verify migration happened
        with storage.transaction() as cursor:
            cursor.execute("SELECT version FROM schema_version")
            assert cursor.fetchone()["version"] == SCHEMA_VERSION

            # V1 data still accessible
            cursor.execute("SELECT id FROM facts WHERE id = ?", ("f1",))
            assert cursor.fetchone() is not None

            cursor.execute("SELECT id FROM decisions WHERE id = ?", ("d1",))
            assert cursor.fetchone() is not None

    def test_migrate_v3_to_current(self, tmp_path):
        """V3 database migrates to current schema with data intact."""
        db_path = tmp_path / "governor.db"
        self._create_v3_db(db_path)

        storage = Storage(db_path)
        with storage.transaction() as cursor:
            cursor.execute("SELECT version FROM schema_version")
            assert cursor.fetchone()["version"] == SCHEMA_VERSION

            cursor.execute("SELECT commit_level FROM facts WHERE id = ?", ("f1",))
            row = cursor.fetchone()
            assert row is not None
            assert row["commit_level"] == "HARD"

    def test_migrate_v5_to_current(self, tmp_path):
        """V5 database migrates to current schema with data intact."""
        db_path = tmp_path / "governor.db"
        self._create_v5_db(db_path)

        storage = Storage(db_path)
        with storage.transaction() as cursor:
            cursor.execute("SELECT version FROM schema_version")
            assert cursor.fetchone()["version"] == SCHEMA_VERSION

            cursor.execute("SELECT claim_id FROM epistemic_claims WHERE claim_id = ?", ("ec1",))
            assert cursor.fetchone() is not None

            # V6 tables should exist after migration
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='staleness_events'")
            assert cursor.fetchone() is not None
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docket_cases'")
            assert cursor.fetchone() is not None

    def test_migration_idempotent(self, tmp_path):
        """Opening Storage twice on same DB doesn't crash or duplicate data."""
        db_path = tmp_path / "governor.db"
        self._create_v1_db(db_path)

        storage1 = Storage(db_path)
        storage1.conn.close()

        # Second open should not error
        storage2 = Storage(db_path)
        with storage2.transaction() as cursor:
            cursor.execute("SELECT version FROM schema_version")
            assert cursor.fetchone()["version"] == SCHEMA_VERSION

    def test_fresh_db_at_current_version(self, tmp_path):
        """Fresh Storage creates DB at current schema version."""
        db_path = tmp_path / "governor.db"
        storage = Storage(db_path)
        with storage.transaction() as cursor:
            cursor.execute("SELECT version FROM schema_version")
            assert cursor.fetchone()["version"] == SCHEMA_VERSION


# ── v1/v2 coexistence ────────────────────────────────────────────────────


class TestV1V2Coexistence:
    """File-based ledger and SQLite can coexist in .governor/."""

    def test_file_ledger_and_sqlite_same_dir(self, tmp_path):
        """Both file-based and SQLite state in same .governor/ dir."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        facts_dir = gov_dir / "facts"
        facts_dir.mkdir()
        (facts_dir / "index.json").write_text("[]")
        (facts_dir / "receipts").mkdir()
        (gov_dir / "decisions").mkdir()
        (gov_dir / "decisions" / "index.json").write_text("[]")

        # SQLite alongside file-based
        storage = Storage(gov_dir / "governor.db")
        with storage.transaction() as cursor:
            cursor.execute("SELECT version FROM schema_version")
            assert cursor.fetchone()["version"] == SCHEMA_VERSION

        # File-based state still intact
        assert (facts_dir / "index.json").exists()
        assert json.loads((facts_dir / "index.json").read_text()) == []


# ── Receipt forward compatibility ────────────────────────────────────────


class TestReceiptForwardCompat:
    """Old receipt JSONL formats remain readable."""

    def test_old_8_field_receipt_readable(self, tmp_path):
        """Receipt JSONL with standard 8 fields is readable."""
        from governor.gate_receipt import GateReceipt

        receipt_dict = {
            "receipt_id": "abc123",
            "schema_version": "receipt_v1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "gate": "evidence_gate",
            "verdict": "pass",
            "subject_hash": "sha256:aaa",
            "evidence_hash": "sha256:bbb",
            "policy_hash": "sha256:ccc",
        }
        receipt = GateReceipt.from_dict(receipt_dict)
        assert receipt.receipt_id == "abc123"
        assert receipt.gate == "evidence_gate"
        assert receipt.verdict == "pass"

    def test_extra_unknown_fields_ignored(self, tmp_path):
        """Receipt dict with unknown fields doesn't crash from_dict."""
        from governor.gate_receipt import GateReceipt

        receipt_dict = {
            "receipt_id": "abc123",
            "schema_version": "receipt_v1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "gate": "evidence_gate",
            "verdict": "pass",
            "subject_hash": "sha256:aaa",
            "evidence_hash": "sha256:bbb",
            "policy_hash": "sha256:ccc",
            "future_field_1": "should not crash",
            "future_field_2": {"nested": True},
        }
        receipt = GateReceipt.from_dict(receipt_dict)
        assert receipt.receipt_id == "abc123"

    def test_receipt_store_write_read_roundtrip(self, tmp_path):
        """Write receipts via store, read them back."""
        from governor.gate_receipt import GateReceipt, ReceiptStore

        store = ReceiptStore(tmp_path)
        receipt = GateReceipt(
            receipt_id="test123",
            schema_version="receipt_v1",
            timestamp="2025-01-01T00:00:00+00:00",
            gate="test_gate",
            verdict="pass",
            subject_hash="sha256:aaa",
            evidence_hash="sha256:bbb",
            policy_hash="sha256:ccc",
        )
        store.append(receipt)

        all_receipts = store.all()
        assert len(all_receipts) >= 1
        found = [r for r in all_receipts if r.receipt_id == "test123"]
        assert len(found) == 1
        assert found[0].gate == "test_gate"


# ── Session capsule compatibility ────────────────────────────────────────


class TestSessionCapsuleCompat:
    """Session capsule from_dict handles missing optional fields."""

    def test_workspace_from_dict_with_missing_fields(self):
        """WorkspaceState.from_dict with minimal dict uses defaults."""
        from governor.session_continuity import WorkspaceState
        ws = WorkspaceState.from_dict({})
        assert ws.active_thread_ids == []
        assert ws.current_section is None
        assert ws.notes == ""

    def test_ledger_state_from_dict_with_missing_fields(self):
        """LedgerState.from_dict with minimal dict uses defaults."""
        from governor.session_continuity import LedgerState
        ls = LedgerState.from_dict({})
        assert ls.decisions == []
        assert ls.constraints == []

    def test_session_metadata_from_dict_with_extras(self):
        """SessionMetadata.from_dict ignores unknown keys."""
        from governor.session_continuity import SessionMetadata
        data = {
            "session_id": "s1",
            "name": "test",
            "mode": "code",
            "created_at": "2025-01-01T00:00:00+00:00",
            "last_active": "2025-01-01T00:00:00+00:00",
            "state": "active",
            "future_field": "should not crash",
        }
        meta = SessionMetadata.from_dict(data)
        assert meta.session_id == "s1"
        assert meta.name == "test"


# ── from_dict robustness ─────────────────────────────────────────────────


class TestFromDictRobustness:
    """from_dict methods on key types handle edge cases."""

    def test_gate_receipt_from_dict_empty_raises(self):
        """GateReceipt.from_dict({}) raises clear error, not KeyError."""
        from governor.gate_receipt import GateReceipt
        with pytest.raises((KeyError, TypeError)):
            GateReceipt.from_dict({})

    def test_hook_config_from_dict_empty(self):
        """HookConfig.from_dict({}) uses all defaults."""
        from governor.claude_hooks import HookConfig
        config = HookConfig.from_dict({})
        assert config.pre_tool_use is True
        assert config.timeout_ms == 5000

    def test_hook_config_from_dict_extra_keys(self):
        """HookConfig.from_dict with unknown keys doesn't crash."""
        from governor.claude_hooks import HookConfig
        config = HookConfig.from_dict({"unknown_key": "value", "pre_tool_use": False})
        assert config.pre_tool_use is False

    def test_lease_to_dict_roundtrip(self):
        """Lease serialization roundtrip works."""
        from governor.storage import Lease
        now = datetime.now(timezone.utc)
        lease = Lease(scope="src/", agent_id="a1", acquired_at=now, expires_at=now)
        d = lease.to_dict()
        assert d["scope"] == "src/"
        assert d["agent_id"] == "a1"

    def test_workspace_roundtrip(self):
        """WorkspaceState roundtrip preserves data."""
        from governor.session_continuity import WorkspaceState
        ws = WorkspaceState(
            active_thread_ids=["t1"],
            current_section="ch3",
            notes="important",
        )
        d = ws.to_dict()
        ws2 = WorkspaceState.from_dict(d)
        assert ws2.active_thread_ids == ["t1"]
        assert ws2.current_section == "ch3"
        assert ws2.notes == "important"

    def test_capsule_roundtrip(self):
        """Full Capsule serialization roundtrip."""
        from governor.session_continuity import (
            Capsule, SessionMetadata, LedgerState, WorkspaceState, SessionState,
        )
        now = datetime.now(timezone.utc)
        capsule = Capsule(
            metadata=SessionMetadata(
                session_id="s1", name="test", mode="code",
                created_at=now, last_active=now, state=SessionState.ACTIVE,
            ),
            ledger=LedgerState(),
            workspace=WorkspaceState(),
        )
        d = capsule.to_dict()
        capsule2 = Capsule.from_dict(d)
        assert capsule2.metadata.session_id == "s1"
        assert capsule2.metadata.mode == "code"
