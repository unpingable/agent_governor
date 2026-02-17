# SPDX-License-Identifier: Apache-2.0
"""
Tests for evidence persistence: EvidenceStore, RunProvenance, and schema v2 migration.
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governor.epistemic import EvidenceRef, EvidenceType
from governor.evidence_store import (
    EvidenceStore,
    RunProvenance,
    create_evidence_store,
)
from governor.storage import SCHEMA, SCHEMA_V2, SCHEMA_VERSION, Storage


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def storage(tmp_dir):
    return Storage(tmp_dir / "governor.db")


@pytest.fixture
def store(storage):
    return EvidenceStore(storage)


@pytest.fixture
def sample_ref():
    return EvidenceRef(
        ref_id="ev_abc123",
        ref_type=EvidenceType.TOOL_TRACE,
        locator="trace_xyz",
        scope="full_claim",
        confidence=0.9,
    )


# =============================================================================
# TestRunProvenance
# =============================================================================


class TestRunProvenance:
    """Tests for RunProvenance dataclass and EvidenceStore run methods."""

    def test_record_run_basic(self, store):
        run = store.record_run(agent_id="agent_1")
        assert run.run_id.startswith("run_")
        assert run.agent_id == "agent_1"
        assert run.model_id is None
        assert run.source_urls == frozenset()

    def test_record_run_all_fields(self, store):
        run = store.record_run(
            agent_id="agent_2",
            model_id="gpt-4",
            prompt_hash="ph_abc",
            tool_path_hash="th_def",
            source_urls=frozenset({"https://a.com", "https://b.com"}),
        )
        assert run.model_id == "gpt-4"
        assert run.prompt_hash == "ph_abc"
        assert run.tool_path_hash == "th_def"
        assert run.source_urls == frozenset({"https://a.com", "https://b.com"})

    def test_record_run_unique_ids(self, store):
        r1 = store.record_run(agent_id="a")
        r2 = store.record_run(agent_id="a")
        assert r1.run_id != r2.run_id

    def test_get_run(self, store):
        run = store.record_run(agent_id="agent_x", model_id="claude-3")
        fetched = store.get_run(run.run_id)
        assert fetched is not None
        assert fetched.run_id == run.run_id
        assert fetched.agent_id == "agent_x"
        assert fetched.model_id == "claude-3"

    def test_get_run_nonexistent(self, store):
        assert store.get_run("nonexistent_run") is None

    def test_runs_by_agent(self, store):
        store.record_run(agent_id="a1")
        store.record_run(agent_id="a1")
        store.record_run(agent_id="a2")
        runs = store.runs_by_agent("a1")
        assert len(runs) == 2
        assert all(r.agent_id == "a1" for r in runs)

    def test_runs_by_agent_empty(self, store):
        assert store.runs_by_agent("nobody") == []

    def test_from_vote(self):
        class FakeVote:
            agent_id = "voter_1"
            model_id = "gpt-4"
            prompt_hash = "p123"
            tool_path_hash = "t456"
            source_urls = frozenset({"https://example.com"})

        run = RunProvenance.from_vote(FakeVote())
        assert run.agent_id == "voter_1"
        assert run.model_id == "gpt-4"
        assert run.source_urls == frozenset({"https://example.com"})

    def test_from_vote_with_no_model_id(self):
        class FakeVote:
            agent_id = "voter_2"
            prompt_hash = "p"
            tool_path_hash = "t"
            source_urls = frozenset()

        run = RunProvenance.from_vote(FakeVote())
        assert run.model_id is None

    def test_to_dict_roundtrip(self, store):
        run = store.record_run(
            agent_id="a",
            model_id="m",
            source_urls=frozenset({"https://x.com"}),
        )
        d = run.to_dict()
        restored = RunProvenance.from_dict(d)
        assert restored.run_id == run.run_id
        assert restored.agent_id == run.agent_id
        assert restored.model_id == run.model_id
        assert restored.source_urls == run.source_urls

    def test_from_row_roundtrip(self, store):
        run = store.record_run(
            agent_id="row_agent",
            model_id="claude-opus",
            source_urls=frozenset({"https://a.com"}),
        )
        fetched = store.get_run(run.run_id)
        assert fetched is not None
        assert fetched.agent_id == "row_agent"
        assert fetched.model_id == "claude-opus"
        assert fetched.source_urls == frozenset({"https://a.com"})

    def test_run_count(self, store):
        assert store.run_count() == 0
        store.record_run(agent_id="a")
        store.record_run(agent_id="b")
        assert store.run_count() == 2

    def test_record_run_from_vote(self, store):
        class FakeVote:
            agent_id = "voter_3"
            model_id = "claude-3.5"
            prompt_hash = "ph"
            tool_path_hash = "tph"
            source_urls = frozenset({"https://src.com"})

        run = store.record_run_from_vote(FakeVote())
        assert run.agent_id == "voter_3"
        assert run.model_id == "claude-3.5"
        fetched = store.get_run(run.run_id)
        assert fetched is not None
        assert fetched.model_id == "claude-3.5"


# =============================================================================
# TestEvidencePersistence
# =============================================================================


class TestEvidencePersistence:
    """Tests for evidence persistence methods."""

    def test_persist_basic(self, store, sample_ref):
        updated = store.persist_evidence("claim_1", sample_ref)
        assert updated.evidence_id is not None
        assert updated.claim_id == "claim_1"
        assert updated.persisted_at is not None

    def test_persist_with_run_id(self, store, sample_ref):
        run = store.record_run(agent_id="a")
        updated = store.persist_evidence("claim_1", sample_ref, run_id=run.run_id)
        assert updated.run_id == run.run_id

    def test_persist_with_collected_by(self, store, sample_ref):
        updated = store.persist_evidence(
            "claim_1", sample_ref, collected_by="agent_a"
        )
        assert updated.collected_by == "agent_a"

    def test_generates_evidence_id(self, store, sample_ref):
        sample_ref.evidence_id = None
        updated = store.persist_evidence("claim_1", sample_ref)
        assert updated.evidence_id is not None
        assert updated.evidence_id.startswith("evi_")

    def test_preserves_existing_evidence_id(self, store):
        ref = EvidenceRef(
            ref_id="ev_keep",
            ref_type=EvidenceType.URL,
            locator="https://example.com",
            scope="test",
            evidence_id="custom_evi_id",
        )
        updated = store.persist_evidence("claim_1", ref)
        assert updated.evidence_id == "custom_evi_id"

    def test_computes_content_hash(self, store, sample_ref):
        updated = store.persist_evidence("claim_1", sample_ref)
        assert updated.content_hash is not None
        assert len(updated.content_hash) == 16

    def test_returns_updated_ref(self, store, sample_ref):
        updated = store.persist_evidence(
            "claim_1", sample_ref, collected_by="ag", run_id="run_x"
        )
        assert updated is sample_ref  # Same object mutated
        assert updated.claim_id == "claim_1"
        assert updated.collected_by == "ag"
        assert updated.run_id == "run_x"

    def test_get_by_id(self, store, sample_ref):
        updated = store.persist_evidence("claim_1", sample_ref)
        fetched = store.get_evidence(updated.evidence_id)
        assert fetched is not None
        assert fetched.evidence_id == updated.evidence_id
        assert fetched.claim_id == "claim_1"
        assert fetched.ref_type == EvidenceType.TOOL_TRACE

    def test_get_nonexistent(self, store):
        assert store.get_evidence("nonexistent") is None

    def test_for_claim_ordered(self, store):
        ref1 = EvidenceRef(
            ref_id="ev_1", ref_type=EvidenceType.URL,
            locator="loc1", scope="s1",
        )
        ref2 = EvidenceRef(
            ref_id="ev_2", ref_type=EvidenceType.TOOL_TRACE,
            locator="loc2", scope="s2",
        )
        ref3 = EvidenceRef(
            ref_id="ev_3", ref_type=EvidenceType.URL,
            locator="loc1", scope="s1",
        )
        store.persist_evidence("claim_a", ref1)
        store.persist_evidence("claim_a", ref2)
        store.persist_evidence("claim_b", ref3)

        results = store.evidence_for_claim("claim_a")
        assert len(results) == 2

    def test_for_claim_empty(self, store):
        assert store.evidence_for_claim("no_claim") == []

    def test_by_kind(self, store):
        ref_url = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l1", scope="s",
        )
        ref_trace = EvidenceRef(
            ref_id="e2", ref_type=EvidenceType.TOOL_TRACE, locator="l2", scope="s",
        )
        store.persist_evidence("c1", ref_url)
        store.persist_evidence("c2", ref_trace)

        urls = store.evidence_by_kind("url")
        assert len(urls) == 1
        assert urls[0].ref_type == EvidenceType.URL

    def test_by_agent(self, store):
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l", scope="s",
        )
        store.persist_evidence("c1", ref, collected_by="agent_x")
        ref2 = EvidenceRef(
            ref_id="e2", ref_type=EvidenceType.URL, locator="l2", scope="s",
        )
        store.persist_evidence("c2", ref2, collected_by="agent_y")

        results = store.evidence_by_agent("agent_x")
        assert len(results) == 1

    def test_by_run(self, store):
        run = store.record_run(agent_id="a")
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.RECEIPT, locator="l", scope="s",
        )
        store.persist_evidence("c1", ref, run_id=run.run_id)

        results = store.evidence_by_run(run.run_id)
        assert len(results) == 1
        assert results[0].run_id == run.run_id

    def test_count_total(self, store):
        assert store.evidence_count() == 0
        ref1 = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l1", scope="s",
        )
        ref2 = EvidenceRef(
            ref_id="e2", ref_type=EvidenceType.URL, locator="l2", scope="s",
        )
        store.persist_evidence("c1", ref1)
        store.persist_evidence("c2", ref2)
        assert store.evidence_count() == 2

    def test_count_by_claim(self, store):
        ref1 = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l1", scope="s",
        )
        ref2 = EvidenceRef(
            ref_id="e2", ref_type=EvidenceType.URL, locator="l2", scope="s",
        )
        ref3 = EvidenceRef(
            ref_id="e3", ref_type=EvidenceType.URL, locator="l1", scope="s",
        )
        store.persist_evidence("c1", ref1)
        store.persist_evidence("c1", ref2)
        store.persist_evidence("c2", ref3)
        assert store.evidence_count(claim_id="c1") == 2
        assert store.evidence_count(claim_id="c2") == 1

    def test_append_only_no_update_delete(self, store):
        """EvidenceStore has no update/delete methods for evidence."""
        assert not hasattr(store, "update_evidence")
        assert not hasattr(store, "delete_evidence")


# =============================================================================
# TestEvidenceRefExtensions
# =============================================================================


class TestEvidenceRefExtensions:
    """Tests for the new EvidenceRef persistence fields."""

    def test_new_fields_default_none(self):
        ref = EvidenceRef(
            ref_id="ev_1",
            ref_type=EvidenceType.URL,
            locator="https://example.com",
            scope="test",
        )
        assert ref.evidence_id is None
        assert ref.claim_id is None
        assert ref.collected_by is None
        assert ref.run_id is None
        assert ref.content_hash is None
        assert ref.persisted_at is None

    def test_backward_compat(self):
        """Existing code that doesn't set persistence fields still works."""
        ref = EvidenceRef.from_tool_trace("trace_1", "my_scope")
        assert ref.ref_id.startswith("ev_")
        assert ref.ref_type == EvidenceType.TOOL_TRACE
        assert ref.locator == "trace_1"
        assert ref.scope == "my_scope"

    def test_to_dict_excludes_none(self):
        ref = EvidenceRef(
            ref_id="ev_1",
            ref_type=EvidenceType.URL,
            locator="https://example.com",
            scope="test",
        )
        d = ref.to_dict()
        assert "evidence_id" not in d
        assert "claim_id" not in d
        assert "collected_by" not in d
        assert "run_id" not in d
        assert "content_hash" not in d
        assert "persisted_at" not in d

    def test_to_dict_includes_set_fields(self):
        ref = EvidenceRef(
            ref_id="ev_1",
            ref_type=EvidenceType.URL,
            locator="https://example.com",
            scope="test",
            evidence_id="evi_123",
            claim_id="claim_456",
            content_hash="abcdef",
        )
        d = ref.to_dict()
        assert d["evidence_id"] == "evi_123"
        assert d["claim_id"] == "claim_456"
        assert d["content_hash"] == "abcdef"

    def test_from_dict_with_persistence_fields(self):
        data = {
            "ref_id": "ev_1",
            "ref_type": "url",
            "locator": "https://example.com",
            "scope": "test",
            "confidence": 0.9,
            "evidence_id": "evi_abc",
            "claim_id": "claim_xyz",
            "collected_by": "agent_1",
            "run_id": "run_123",
            "content_hash": "deadbeef",
            "persisted_at": "2025-01-01T00:00:00",
        }
        ref = EvidenceRef.from_dict(data)
        assert ref.evidence_id == "evi_abc"
        assert ref.claim_id == "claim_xyz"
        assert ref.collected_by == "agent_1"
        assert ref.run_id == "run_123"
        assert ref.content_hash == "deadbeef"
        assert ref.persisted_at is not None

    def test_from_dict_without_persistence_fields(self):
        data = {
            "ref_id": "ev_1",
            "ref_type": "url",
            "locator": "https://example.com",
            "scope": "test",
        }
        ref = EvidenceRef.from_dict(data)
        assert ref.evidence_id is None
        assert ref.claim_id is None

    def test_from_row_populates_all(self, store, sample_ref):
        updated = store.persist_evidence("claim_1", sample_ref, collected_by="ag")
        fetched = store.get_evidence(updated.evidence_id)
        assert fetched is not None
        assert fetched.evidence_id == updated.evidence_id
        assert fetched.claim_id == "claim_1"
        assert fetched.collected_by == "ag"
        assert fetched.content_hash is not None
        assert fetched.persisted_at is not None

    def test_compute_content_hash_deterministic(self):
        ref = EvidenceRef(
            ref_id="ev_1",
            ref_type=EvidenceType.URL,
            locator="https://example.com",
            scope="test",
        )
        h1 = ref.compute_content_hash()
        h2 = ref.compute_content_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_compute_content_hash_different_inputs(self):
        ref1 = EvidenceRef(
            ref_id="ev_1", ref_type=EvidenceType.URL,
            locator="https://a.com", scope="s",
        )
        ref2 = EvidenceRef(
            ref_id="ev_2", ref_type=EvidenceType.URL,
            locator="https://b.com", scope="s",
        )
        assert ref1.compute_content_hash() != ref2.compute_content_hash()


# =============================================================================
# TestAuditTrail
# =============================================================================


class TestAuditTrail:
    """Tests for audit trail queries."""

    def test_by_agent(self, store):
        run = store.record_run(agent_id="agent_a", model_id="m1")
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l", scope="s",
        )
        store.persist_evidence("c1", ref, collected_by="agent_a", run_id=run.run_id)

        trail = store.audit_trail(agent_id="agent_a")
        assert len(trail) == 1
        assert trail[0]["collected_by"] == "agent_a"
        assert "run_provenance" in trail[0]
        assert trail[0]["run_provenance"]["model_id"] == "m1"

    def test_by_claim(self, store):
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l", scope="s",
        )
        store.persist_evidence("target_claim", ref)
        store.persist_evidence("other_claim", EvidenceRef(
            ref_id="e2", ref_type=EvidenceType.URL, locator="l2", scope="s2",
        ))

        trail = store.audit_trail(claim_id="target_claim")
        assert len(trail) == 1
        assert trail[0]["claim_id"] == "target_claim"

    def test_by_run(self, store):
        run = store.record_run(agent_id="a")
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l", scope="s",
        )
        store.persist_evidence("c1", ref, run_id=run.run_id)

        trail = store.audit_trail(run_id=run.run_id)
        assert len(trail) == 1
        assert trail[0]["run_id"] == run.run_id

    def test_combined_filters(self, store):
        run = store.record_run(agent_id="agent_a")
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l", scope="s",
        )
        store.persist_evidence("c1", ref, collected_by="agent_a", run_id=run.run_id)
        # Another evidence from different agent
        ref2 = EvidenceRef(
            ref_id="e2", ref_type=EvidenceType.URL, locator="l2", scope="s",
        )
        store.persist_evidence("c1", ref2, collected_by="agent_b")

        trail = store.audit_trail(agent_id="agent_a", claim_id="c1")
        assert len(trail) == 1

    def test_joins_run_provenance(self, store):
        run = store.record_run(
            agent_id="a", model_id="claude-3",
            source_urls=frozenset({"https://x.com"}),
        )
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.TOOL_TRACE, locator="t", scope="s",
        )
        store.persist_evidence("c1", ref, run_id=run.run_id)

        trail = store.audit_trail(run_id=run.run_id)
        assert len(trail) == 1
        rp = trail[0]["run_provenance"]
        assert rp["agent_id"] == "a"
        assert rp["model_id"] == "claude-3"
        assert "https://x.com" in rp["source_urls"]

    def test_no_run_provenance(self, store):
        """Evidence without a run_id should not have run_provenance in result."""
        ref = EvidenceRef(
            ref_id="e1", ref_type=EvidenceType.URL, locator="l", scope="s",
        )
        store.persist_evidence("c1", ref)
        trail = store.audit_trail(claim_id="c1")
        assert len(trail) == 1
        assert "run_provenance" not in trail[0]


# =============================================================================
# TestMigration
# =============================================================================


class TestMigration:
    """Tests for schema v2 migration."""

    def test_fresh_db_has_both_tables(self, storage):
        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence'"
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_provenance'"
        )
        assert cursor.fetchone() is not None

    def test_v1_db_migrates_to_v2(self, tmp_dir):
        """Simulate a v1 database and verify migration creates new tables."""
        db_path = tmp_dir / "v1_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.commit()
        conn.close()

        # Now open with Storage which should trigger migration
        storage = Storage(db_path)
        cursor = storage.conn.cursor()

        # Verify tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence'"
        )
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='run_provenance'"
        )
        assert cursor.fetchone() is not None

        storage.close()

    def test_existing_data_preserved(self, tmp_dir):
        """Verify v1 data is preserved after migration."""
        db_path = tmp_dir / "preserve_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.execute(
            "INSERT INTO agents (id, agent_class, registered_at, last_heartbeat) "
            "VALUES ('test_agent', 'worker', '2025-01-01', '2025-01-01')"
        )
        conn.commit()
        conn.close()

        storage = Storage(db_path)
        cursor = storage.conn.cursor()
        cursor.execute("SELECT * FROM agents WHERE id = 'test_agent'")
        row = cursor.fetchone()
        assert row is not None
        assert row["agent_class"] == "worker"
        storage.close()

    def test_schema_version_updated(self, tmp_dir):
        """Verify schema version is updated after migration."""
        db_path = tmp_dir / "version_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.commit()
        conn.close()

        storage = Storage(db_path)
        cursor = storage.conn.cursor()
        cursor.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        assert row["version"] == SCHEMA_VERSION
        storage.close()

    def test_indexes_present(self, storage):
        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_evidence_%'"
        )
        evidence_indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_evidence_claim" in evidence_indexes
        assert "idx_evidence_kind" in evidence_indexes
        assert "idx_evidence_collected_by" in evidence_indexes
        assert "idx_evidence_run" in evidence_indexes

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_run_%'"
        )
        run_indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_run_agent" in run_indexes


# =============================================================================
# TestVoteExtensions
# =============================================================================


class TestVoteExtensions:
    """Tests for Vote model_id and source_urls fields."""

    def test_model_id_and_source_urls_fields(self):
        from governor.quorum import Vote, VoteVerdict

        vote = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="a1",
            verdict=VoteVerdict.APPROVE,
            reason="good",
            model_id="claude-3.5",
            source_urls=frozenset({"https://a.com", "https://b.com"}),
        )
        assert vote.model_id == "claude-3.5"
        assert vote.source_urls == frozenset({"https://a.com", "https://b.com"})

    def test_to_dict_from_dict_roundtrip(self):
        from governor.quorum import Vote, VoteVerdict

        vote = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="a1",
            verdict=VoteVerdict.APPROVE,
            reason="ok",
            model_id="gpt-4",
            source_urls=frozenset({"https://x.com"}),
        )
        d = vote.to_dict()
        assert d["model_id"] == "gpt-4"
        assert sorted(d["source_urls"]) == ["https://x.com"]

        restored = Vote.from_dict(d)
        assert restored.model_id == "gpt-4"
        assert restored.source_urls == frozenset({"https://x.com"})

    def test_backward_compat_no_new_fields(self):
        from governor.quorum import Vote, VoteVerdict

        vote = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="a1",
            verdict=VoteVerdict.APPROVE,
            reason="ok",
        )
        assert vote.model_id is None
        assert vote.source_urls == frozenset()
        d = vote.to_dict()
        assert "model_id" not in d
        assert "source_urls" not in d

    def test_from_dict_backward_compat(self):
        """from_dict without new fields should work."""
        from governor.quorum import Vote, VoteVerdict

        data = {
            "vote_id": "v1",
            "proposal_id": "p1",
            "agent_id": "a1",
            "verdict": "approve",
            "reason": "ok",
            "timestamp": datetime.now().isoformat(),
        }
        vote = Vote.from_dict(data)
        assert vote.model_id is None
        assert vote.source_urls == frozenset()

    def test_cast_vote_passes_through(self):
        from governor.quorum import (
            ClaimType,
            QuorumManager,
            VoteVerdict,
        )

        qm = QuorumManager()
        qm.create_quorum("p1", ClaimType.MATH)
        vote = qm.cast_vote(
            "p1", "a1", VoteVerdict.APPROVE, "good",
            model_id="claude-3.5",
            source_urls=frozenset({"https://src.com"}),
        )
        assert vote is not None
        assert vote.model_id == "claude-3.5"
        assert vote.source_urls == frozenset({"https://src.com"})


# =============================================================================
# TestMethodSignatureFromVote
# =============================================================================


class TestMethodSignatureFromVote:
    """Tests for MethodSignature.from_vote with new Vote fields."""

    def test_extracts_model_id(self):
        from governor.independence import MethodSignature
        from governor.quorum import Vote, VoteVerdict

        vote = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="a1",
            verdict=VoteVerdict.APPROVE,
            reason="ok",
            tool_path_hash="t1",
            sources_hash="s1",
            prompt_hash="p1",
            model_id="claude-3.5",
        )
        sig = MethodSignature.from_vote(vote)
        assert sig is not None
        assert sig.model_tier == "claude-3.5"

    def test_extracts_source_urls(self):
        from governor.independence import MethodSignature
        from governor.quorum import Vote, VoteVerdict

        vote = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="a1",
            verdict=VoteVerdict.APPROVE,
            reason="ok",
            tool_path_hash="t1",
            sources_hash="s1",
            prompt_hash="p1",
            source_urls=frozenset({"https://a.com"}),
        )
        sig = MethodSignature.from_vote(vote)
        assert sig is not None
        assert sig.source_urls == frozenset({"https://a.com"})

    def test_defaults_when_missing(self):
        from governor.independence import MethodSignature
        from governor.quorum import Vote, VoteVerdict

        vote = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="a1",
            verdict=VoteVerdict.APPROVE,
            reason="ok",
            tool_path_hash="t1",
            sources_hash="s1",
            prompt_hash="p1",
        )
        sig = MethodSignature.from_vote(vote)
        assert sig is not None
        assert sig.model_tier == "standard"  # default when model_id is None
        assert sig.source_urls == frozenset()

    def test_returns_none_without_hashes(self):
        from governor.independence import MethodSignature
        from governor.quorum import Vote, VoteVerdict

        vote = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="a1",
            verdict=VoteVerdict.APPROVE,
            reason="ok",
            model_id="claude-3.5",
            source_urls=frozenset({"https://a.com"}),
        )
        sig = MethodSignature.from_vote(vote)
        assert sig is None


# =============================================================================
# TestConvenienceFactory
# =============================================================================


class TestConvenienceFactory:
    """Test create_evidence_store factory."""

    def test_create_evidence_store(self, tmp_dir):
        gov_dir = tmp_dir / ".governor"
        gov_dir.mkdir()
        store = create_evidence_store(gov_dir)
        assert isinstance(store, EvidenceStore)
        # Should work immediately
        run = store.record_run(agent_id="test")
        assert run.run_id.startswith("run_")


# =============================================================================
# TestExports
# =============================================================================


class TestExports:
    """Test that new types are exported from governor package."""

    def test_run_provenance_exported(self):
        from governor import RunProvenance
        assert RunProvenance is not None

    def test_evidence_store_exported(self):
        from governor import EvidenceStore
        assert EvidenceStore is not None

    def test_create_evidence_store_exported(self):
        from governor import create_evidence_store
        assert create_evidence_store is not None
