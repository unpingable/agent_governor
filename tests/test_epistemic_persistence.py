# SPDX-License-Identifier: Apache-2.0
"""
Tests for EpistemicLedger persistence: Schema V4, storage wiring, write-through,
evidence store integration, CLI helpers, and backward compatibility.
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

from governor.epistemic import (
    ClaimStatus,
    Provenance,
    EvidenceType,
    EvidenceRef,
    GroundedClaim,
    GroundedClaimStatus,
    EpistemicLedger,
)
from governor.storage import Storage, SCHEMA_VERSION
from governor.evidence_store import EvidenceStore


@pytest.fixture
def tmp_storage(tmp_path):
    """Create a fresh Storage instance backed by a temp DB."""
    db_path = tmp_path / "test.db"
    return Storage(db_path)


@pytest.fixture
def tmp_evidence_store(tmp_storage):
    """Create an EvidenceStore wrapping the temp storage."""
    return EvidenceStore(tmp_storage)


@pytest.fixture
def storage_ledger(tmp_storage):
    """Create an EpistemicLedger backed by storage."""
    return EpistemicLedger(storage=tmp_storage)


@pytest.fixture
def full_ledger(tmp_storage, tmp_evidence_store):
    """Create an EpistemicLedger backed by storage + evidence store."""
    return EpistemicLedger(storage=tmp_storage, evidence_store=tmp_evidence_store)


# =============================================================================
# Schema V4 Migration Tests
# =============================================================================


class TestSchemaV4Migration:
    """Tests for Schema V4 (epistemic_claims + epistemic_ledger_meta tables)."""

    def test_schema_version_is_current(self):
        """SCHEMA_VERSION constant should be current."""
        assert SCHEMA_VERSION >= 4

    def test_fresh_db_has_epistemic_claims_table(self, tmp_storage):
        """Fresh DB should have epistemic_claims table."""
        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='epistemic_claims'"
        )
        assert cursor.fetchone() is not None

    def test_fresh_db_has_epistemic_ledger_meta_table(self, tmp_storage):
        """Fresh DB should have epistemic_ledger_meta table."""
        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='epistemic_ledger_meta'"
        )
        assert cursor.fetchone() is not None

    def test_fresh_db_has_correct_indexes(self, tmp_storage):
        """Fresh DB should have all epistemic_claims indexes."""
        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_ec_%'"
        )
        indexes = {row["name"] for row in cursor.fetchall()}
        expected = {
            "idx_ec_provenance",
            "idx_ec_governance",
            "idx_ec_epistemic",
            "idx_ec_commit",
            "idx_ec_agent",
            "idx_ec_hash",
        }
        assert expected.issubset(indexes)

    def test_v3_to_v4_migration(self, tmp_path):
        """V3→V4 migration should create new tables without breaking existing ones."""
        # Create a V3 database manually
        import sqlite3

        db_path = tmp_path / "v3.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Minimal V3 schema: just schema_version + facts + epoch_counter
        conn.executescript("""
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
            INSERT INTO schema_version (version) VALUES (3);
            CREATE TABLE facts (
                id TEXT PRIMARY KEY,
                claim_type TEXT NOT NULL,
                claim_json TEXT NOT NULL,
                receipt_json TEXT NOT NULL,
                file_hashes_json TEXT NOT NULL DEFAULT '{}',
                epoch INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                invalidated_at TEXT,
                commit_level TEXT,
                assumptions_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE epoch_counter (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                value INTEGER NOT NULL DEFAULT 0
            );
            INSERT INTO epoch_counter (id, value) VALUES (1, 0);
            CREATE TABLE decisions (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                choice TEXT NOT NULL,
                claim_json TEXT NOT NULL,
                rationale TEXT,
                supersedes_id TEXT,
                epoch INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                commit_level TEXT,
                assumptions_json TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE leases (
                scope TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE reservations (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE proposals (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                claims_json TEXT NOT NULL,
                receipts_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                agent_id TEXT,
                epoch INTEGER NOT NULL
            );
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                agent_class TEXT NOT NULL,
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                registered_at TEXT NOT NULL,
                last_heartbeat TEXT NOT NULL,
                permissions_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE rejections (
                id TEXT PRIMARY KEY,
                proposal_id TEXT,
                claim_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                suggestion TEXT,
                created_at TEXT NOT NULL,
                agent_id TEXT
            );
            CREATE TABLE evidence (
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
            CREATE TABLE run_provenance (
                run_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                model_id TEXT,
                prompt_hash TEXT,
                tool_path_hash TEXT,
                source_urls_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
        """)
        conn.close()

        # Now open with Storage — should migrate to V4
        storage = Storage(db_path)
        cursor = storage.conn.cursor()

        # Check version bumped to current
        cursor.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()["version"] == SCHEMA_VERSION

        # Check new tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='epistemic_claims'"
        )
        assert cursor.fetchone() is not None

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='epistemic_ledger_meta'"
        )
        assert cursor.fetchone() is not None

        storage.close()


# =============================================================================
# EpistemicLedger with Storage Tests
# =============================================================================


class TestEpistemicLedgerWithStorage:
    """Tests for write-through persistence on mutation methods."""

    def test_new_claim_persists(self, storage_ledger, tmp_storage):
        """new_claim should write to epistemic_claims."""
        claim = storage_ledger.new_claim("test claim", Provenance.ASSUMED)

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["content"] == "test claim"
        assert row["provenance"] == "assumed"

    def test_new_claim_persists_meta(self, storage_ledger, tmp_storage):
        """new_claim should update meta counters."""
        storage_ledger.new_claim("test", Provenance.ASSUMED)

        cursor = tmp_storage.conn.cursor()
        cursor.execute("SELECT * FROM epistemic_ledger_meta WHERE id = 1")
        meta = cursor.fetchone()
        assert meta["total_claims_created"] == 1

    def test_promote_persists(self, storage_ledger, tmp_storage):
        """Successful promotion should update the row."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        ref = EvidenceRef.from_tool_trace("trace_1", "full")
        storage_ledger.attach_evidence(claim.claim_id, ref)
        storage_ledger.promote(claim.claim_id, Provenance.DERIVED)

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT provenance FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        row = cursor.fetchone()
        assert row["provenance"] == "derived"

    def test_update_confidence_persists(self, storage_ledger, tmp_storage):
        """Confidence updates should persist."""
        claim = storage_ledger.new_claim("test", Provenance.RETRIEVED)
        storage_ledger.update_confidence(claim.claim_id, 0.1)

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT confidence FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        row = cursor.fetchone()
        assert row["confidence"] == pytest.approx(0.95, abs=0.01)

    def test_block_persists(self, storage_ledger, tmp_storage):
        """block() should persist governance_status."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        storage_ledger.block(claim.claim_id)

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT governance_status FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        assert cursor.fetchone()["governance_status"] == "blocked"

    def test_retract_persists(self, storage_ledger, tmp_storage):
        """retract() should persist status + retraction fields."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        storage_ledger.retract(claim.claim_id, "testing")

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT governance_status, retraction_reason FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        row = cursor.fetchone()
        assert row["governance_status"] == "retracted"
        assert row["retraction_reason"] == "testing"

    def test_retract_persists_meta(self, storage_ledger, tmp_storage):
        """retract() should update meta.total_retractions."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        storage_ledger.retract(claim.claim_id)

        cursor = tmp_storage.conn.cursor()
        cursor.execute("SELECT total_retractions FROM epistemic_ledger_meta WHERE id = 1")
        assert cursor.fetchone()["total_retractions"] == 1

    def test_unblock_persists(self, storage_ledger, tmp_storage):
        """unblock() should persist governance_status back to active."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        ref = EvidenceRef.from_tool_trace("trace_1", "full")
        storage_ledger.attach_evidence(claim.claim_id, ref)
        storage_ledger.block(claim.claim_id)
        storage_ledger.unblock(claim.claim_id)

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT governance_status FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        assert cursor.fetchone()["governance_status"] == "active"

    def test_set_commit_level_persists(self, storage_ledger, tmp_storage):
        """set_commit_level should persist."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        storage_ledger.set_commit_level(claim.claim_id, "hard")

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT commit_level FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        assert cursor.fetchone()["commit_level"] == "hard"

    def test_set_epistemic_status_persists(self, storage_ledger, tmp_storage):
        """set_epistemic_status should persist."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        storage_ledger.set_epistemic_status(claim.claim_id, ClaimStatus.SUPPORTED)

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT epistemic_status FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        assert cursor.fetchone()["epistemic_status"] == "supported"

    def test_add_assumption_persists(self, storage_ledger, tmp_storage):
        """add_assumption should persist."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        storage_ledger.add_assumption(claim.claim_id, "user is authenticated")

        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT assumptions_json FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        assumptions = json.loads(cursor.fetchone()["assumptions_json"])
        assert assumptions == ["user is authenticated"]

    def test_tick_persists_meta(self, storage_ledger, tmp_storage):
        """tick() should persist the step counter."""
        storage_ledger.tick()
        storage_ledger.tick()

        cursor = tmp_storage.conn.cursor()
        cursor.execute("SELECT step FROM epistemic_ledger_meta WHERE id = 1")
        assert cursor.fetchone()["step"] == 2


# =============================================================================
# EpistemicLedger Load from Storage Tests
# =============================================================================


class TestEpistemicLedgerLoadFromStorage:
    """Tests for loading claims from SQLite on init."""

    def test_load_claims_on_init(self, tmp_storage):
        """Claims should be loaded from DB on init."""
        # Create and populate first ledger
        ledger1 = EpistemicLedger(storage=tmp_storage)
        c = ledger1.new_claim("persisted claim", Provenance.RETRIEVED)
        claim_id = c.claim_id

        # Create second ledger from same DB
        ledger2 = EpistemicLedger(storage=tmp_storage)
        assert claim_id in ledger2.claims
        assert ledger2.claims[claim_id].content == "persisted claim"

    def test_load_meta_on_init(self, tmp_storage):
        """Meta counters should be loaded from DB on init."""
        ledger1 = EpistemicLedger(storage=tmp_storage)
        ledger1.new_claim("a", Provenance.ASSUMED)
        ledger1.new_claim("b", Provenance.ASSUMED)
        ledger1.tick()
        ledger1.tick()

        ledger2 = EpistemicLedger(storage=tmp_storage)
        assert ledger2.step == 2
        assert ledger2.total_claims_created == 2

    def test_load_empty_db(self, tmp_storage):
        """Loading from empty DB should produce empty ledger."""
        ledger = EpistemicLedger(storage=tmp_storage)
        assert len(ledger.claims) == 0
        assert ledger.step == 0

    def test_round_trip_create_reload(self, tmp_storage):
        """Create claims, then reload from DB, verify full state."""
        ledger1 = EpistemicLedger(storage=tmp_storage)
        c1 = ledger1.new_claim("claim one", Provenance.ASSUMED)
        c2 = ledger1.new_claim("claim two", Provenance.RETRIEVED)
        ledger1.set_epistemic_status(c1.claim_id, ClaimStatus.PROPOSED)
        ledger1.set_commit_level(c2.claim_id, "hard")
        ledger1.add_assumption(c1.claim_id, "server is running")
        ledger1.tick()
        ledger1.retract(c2.claim_id, "no longer needed")

        ledger2 = EpistemicLedger(storage=tmp_storage)
        assert len(ledger2.claims) == 2
        assert ledger2.step == 1
        assert ledger2.claims[c1.claim_id].epistemic_status == ClaimStatus.PROPOSED
        assert ledger2.claims[c1.claim_id].assumptions == ["server is running"]
        assert ledger2.claims[c2.claim_id].commit_level == "hard"
        assert ledger2.claims[c2.claim_id].status == GroundedClaimStatus.RETRACTED
        assert ledger2.claims[c2.claim_id].retraction_reason == "no longer needed"
        assert ledger2.total_retractions == 1

    def test_multiple_claims(self, tmp_storage):
        """Multiple claims should all be loaded."""
        ledger1 = EpistemicLedger(storage=tmp_storage)
        ids = []
        for i in range(10):
            c = ledger1.new_claim(f"claim {i}", Provenance.ASSUMED)
            ids.append(c.claim_id)

        ledger2 = EpistemicLedger(storage=tmp_storage)
        assert len(ledger2.claims) == 10
        for cid in ids:
            assert cid in ledger2.claims

    def test_retracted_claims_preserved(self, tmp_storage):
        """Retracted claims should persist and reload."""
        ledger1 = EpistemicLedger(storage=tmp_storage)
        c = ledger1.new_claim("temp", Provenance.ASSUMED)
        ledger1.retract(c.claim_id, "bad claim")

        ledger2 = EpistemicLedger(storage=tmp_storage)
        assert c.claim_id in ledger2.claims
        assert ledger2.claims[c.claim_id].status == GroundedClaimStatus.RETRACTED

    def test_blocked_claims_preserved(self, tmp_storage):
        """Blocked claims should persist and reload."""
        ledger1 = EpistemicLedger(storage=tmp_storage)
        c = ledger1.new_claim("blocked", Provenance.ASSUMED)
        ledger1.block(c.claim_id)

        ledger2 = EpistemicLedger(storage=tmp_storage)
        assert ledger2.claims[c.claim_id].status == GroundedClaimStatus.BLOCKED


# =============================================================================
# Evidence Store Wiring Tests
# =============================================================================


class TestEvidenceStoreWiring:
    """Tests for evidence persistence through EpistemicLedger."""

    def test_attach_evidence_persists_via_store(self, full_ledger, tmp_storage):
        """attach_evidence should call evidence_store.persist_evidence."""
        claim = full_ledger.new_claim("test", Provenance.ASSUMED)
        ref = EvidenceRef.from_tool_trace("trace_1", "full")
        full_ledger.attach_evidence(claim.claim_id, ref)

        # Evidence should be in the evidence table
        cursor = tmp_storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM evidence WHERE claim_id = ?",
            (claim.claim_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["kind"] == "tool_trace"
        assert row["locator"] == "trace_1"

    def test_evidence_queryable_after_attach(self, full_ledger, tmp_evidence_store):
        """Evidence should be queryable via EvidenceStore after attach."""
        claim = full_ledger.new_claim("test", Provenance.ASSUMED)
        ref = EvidenceRef.from_url("https://example.com", "source")
        full_ledger.attach_evidence(claim.claim_id, ref)

        evidence = tmp_evidence_store.evidence_for_claim(claim.claim_id)
        assert len(evidence) == 1
        assert evidence[0].locator == "https://example.com"

    def test_no_evidence_store_no_persistence(self, storage_ledger):
        """Without evidence_store, attach_evidence should still work in-memory."""
        claim = storage_ledger.new_claim("test", Provenance.ASSUMED)
        ref = EvidenceRef.from_tool_trace("trace_1", "full")
        result = storage_ledger.attach_evidence(claim.claim_id, ref)
        assert result is True
        assert len(claim.evidence_refs) == 1

    def test_multiple_evidence_refs(self, full_ledger, tmp_evidence_store):
        """Multiple evidence refs should all persist."""
        claim = full_ledger.new_claim("test", Provenance.ASSUMED)
        full_ledger.attach_evidence(claim.claim_id, EvidenceRef.from_tool_trace("t1", "a"))
        full_ledger.attach_evidence(claim.claim_id, EvidenceRef.from_url("http://x.com", "b"))
        full_ledger.attach_evidence(claim.claim_id, EvidenceRef.from_receipt("hash1", "c"))

        evidence = tmp_evidence_store.evidence_for_claim(claim.claim_id)
        assert len(evidence) == 3


# =============================================================================
# CLI get_epistemic_ledger Tests
# =============================================================================


class TestCLIGetEpistemicLedger:
    """Tests for CLI helper behavior (logic, not actual CLI invocation)."""

    def test_sqlite_path_used_when_db_exists(self, tmp_path):
        """When governor.db exists, should use SQLite-backed ledger."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        # Create a DB
        storage = Storage(gov_dir / "governor.db")
        ledger = EpistemicLedger(storage=storage)
        claim = ledger.new_claim("sqlite claim", Provenance.ASSUMED)
        claim_id = claim.claim_id

        # Reload from same DB
        storage2 = Storage(gov_dir / "governor.db")
        ledger2 = EpistemicLedger(storage=storage2)
        assert claim_id in ledger2.claims

        storage.close()
        storage2.close()

    def test_json_fallback(self, tmp_path):
        """When no DB exists, from_dict should work from JSON data."""
        data = {
            "step": 3,
            "claims": {},
            "total_claims_created": 5,
        }
        ledger = EpistemicLedger.from_dict(data)
        assert ledger.step == 3
        assert ledger.total_claims_created == 5

    def test_empty_ledger_creation(self):
        """No args should create empty in-memory ledger."""
        ledger = EpistemicLedger()
        assert len(ledger.claims) == 0
        assert ledger.step == 0
        assert ledger.storage is None

    def test_save_skips_json_when_storage_backed(self, tmp_storage):
        """Storage-backed ledger should have storage attribute set."""
        ledger = EpistemicLedger(storage=tmp_storage)
        assert ledger.storage is not None


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompat:
    """Tests ensuring no breaking changes to existing behavior."""

    def test_no_storage_pure_in_memory(self):
        """EpistemicLedger() with no args should work identically to before."""
        ledger = EpistemicLedger()
        assert ledger.storage is None
        assert ledger.evidence_store is None

        c = ledger.new_claim("test", Provenance.ASSUMED)
        assert c.claim_id in ledger.claims
        assert ledger.total_claims_created == 1

        ledger.retract(c.claim_id)
        assert ledger.total_retractions == 1

    def test_from_dict_without_epistemic_status_fields(self):
        """Deserializing old data without epistemic_status should work."""
        old_data = {
            "step": 5,
            "claims": {
                "gc_old": {
                    "claim_id": "gc_old",
                    "content": "legacy claim",
                    "provenance": "assumed",
                    "confidence": 0.3,
                    "created_at": datetime.now().isoformat(),
                }
            },
        }
        ledger = EpistemicLedger.from_dict(old_data)
        assert ledger.claims["gc_old"].epistemic_status is None
        assert ledger.claims["gc_old"].commit_level is None
        assert ledger.claims["gc_old"].assumptions == []

    def test_grounded_claim_without_epistemic_status(self):
        """GroundedClaim should work without epistemic_status."""
        claim = GroundedClaim(
            claim_id="gc_compat",
            content="backward compat",
            provenance=Provenance.RETRIEVED,
            confidence=0.85,
        )
        assert claim.epistemic_status is None
        d = claim.to_dict()
        assert "epistemic_status" not in d

    def test_existing_methods_still_work(self):
        """All existing EpistemicLedger methods should work unchanged."""
        ledger = EpistemicLedger()
        c = ledger.new_claim("test", Provenance.ASSUMED)
        ref = EvidenceRef.from_tool_trace("t1", "full")
        ledger.attach_evidence(c.claim_id, ref)
        assert ledger.has_evidence(c.claim_id)

        ledger.block(c.claim_id)
        assert c.status == GroundedClaimStatus.BLOCKED
        ledger.unblock(c.claim_id)
        assert c.status == GroundedClaimStatus.ACTIVE

        ledger.set_commit_level(c.claim_id, "soft")
        assert c.commit_level == "soft"

        ledger.add_assumption(c.claim_id, "network available")
        assert c.assumptions == ["network available"]

        d = ledger.to_dict()
        assert "claims" in d
        assert "step" in d
