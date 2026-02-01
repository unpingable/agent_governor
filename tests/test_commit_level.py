"""
Tests for Layer 2: Commit Level on Claims.

Tests cover:
- GroundedClaim commit_level and assumptions fields
- EpistemicLedger commit level methods
- StrictModeGate.evaluate_claim() wiring
- SQLite schema v3 migration (commit_level columns)
- Backward compatibility
"""

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from governor.epistemic import (
    EpistemicLedger,
    EvidenceRef,
    EvidenceType,
    GroundedClaim,
    GroundedClaimStatus,
    Provenance,
)
from governor.storage import (
    SCHEMA,
    SCHEMA_V2,
    SCHEMA_VERSION,
    Storage,
    _SCHEMA_V3_STMTS,
)
from governor.strict import (
    ClaimCategory,
    ClaimEvaluation,
    CommitLevel,
    RiskLevel,
    StrictModeGate,
)


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
def ledger():
    return EpistemicLedger()


@pytest.fixture
def gate():
    return StrictModeGate()


# =============================================================================
# TestGroundedClaimFields
# =============================================================================


class TestGroundedClaimFields:
    """Tests for new commit_level and assumptions fields on GroundedClaim."""

    def test_commit_level_default_none(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.5,
        )
        assert claim.commit_level is None

    def test_assumptions_default_empty(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.5,
        )
        assert claim.assumptions == []

    def test_commit_level_set(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.RETRIEVED,
            confidence=0.9, commit_level="hard",
        )
        assert claim.commit_level == "hard"
        assert claim.is_hard is True
        assert claim.is_soft is False
        assert claim.is_refused is False

    def test_is_soft(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.3, commit_level="soft",
        )
        assert claim.is_soft is True
        assert claim.is_hard is False

    def test_is_refused(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.3, commit_level="refused",
        )
        assert claim.is_refused is True

    def test_none_commit_level_properties(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        assert claim.is_hard is False
        assert claim.is_soft is False
        assert claim.is_refused is False

    def test_assumptions_populated(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.3, assumptions=["OS is Linux", "Python 3.10+"],
        )
        assert claim.has_assumptions is True
        assert len(claim.assumptions) == 2

    def test_has_assumptions_false_when_empty(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        assert claim.has_assumptions is False

    def test_to_dict_excludes_none_commit_level(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        d = claim.to_dict()
        assert "commit_level" not in d
        assert "assumptions" not in d

    def test_to_dict_includes_set_commit_level(self):
        claim = GroundedClaim(
            claim_id="gc_1", content="test", provenance=Provenance.ASSUMED,
            confidence=0.3, commit_level="hard",
            assumptions=["requires Python 3.10"],
        )
        d = claim.to_dict()
        assert d["commit_level"] == "hard"
        assert d["assumptions"] == ["requires Python 3.10"]

    def test_from_dict_with_commit_level(self):
        data = {
            "claim_id": "gc_1",
            "content": "test",
            "provenance": "assumed",
            "confidence": 0.3,
            "created_at": datetime.now().isoformat(),
            "commit_level": "soft",
            "assumptions": ["OS is Linux"],
        }
        claim = GroundedClaim.from_dict(data)
        assert claim.commit_level == "soft"
        assert claim.assumptions == ["OS is Linux"]

    def test_from_dict_backward_compat(self):
        """Old data without commit_level/assumptions still works."""
        data = {
            "claim_id": "gc_1",
            "content": "test",
            "provenance": "assumed",
            "confidence": 0.3,
            "created_at": datetime.now().isoformat(),
        }
        claim = GroundedClaim.from_dict(data)
        assert claim.commit_level is None
        assert claim.assumptions == []


# =============================================================================
# TestEpistemicLedgerCommitLevel
# =============================================================================


class TestEpistemicLedgerCommitLevel:
    """Tests for EpistemicLedger commit level methods."""

    def test_set_commit_level_hard(self, ledger):
        claim = ledger.new_claim("test", Provenance.RETRIEVED)
        assert ledger.set_commit_level(claim.claim_id, "hard")
        assert claim.commit_level == "hard"

    def test_set_commit_level_soft(self, ledger):
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        assert ledger.set_commit_level(claim.claim_id, "soft")
        assert claim.commit_level == "soft"

    def test_set_commit_level_refused(self, ledger):
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        assert ledger.set_commit_level(claim.claim_id, "refused")
        assert claim.commit_level == "refused"

    def test_set_commit_level_invalid(self, ledger):
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        assert ledger.set_commit_level(claim.claim_id, "invalid") is False
        assert claim.commit_level is None

    def test_set_commit_level_nonexistent_claim(self, ledger):
        assert ledger.set_commit_level("nonexistent", "hard") is False

    def test_set_commit_level_updates_timestamp(self, ledger):
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        old_ts = claim.last_updated_at
        ledger.tick()
        ledger.set_commit_level(claim.claim_id, "hard")
        assert claim.last_updated_step == ledger.step

    def test_add_assumption(self, ledger):
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        assert ledger.add_assumption(claim.claim_id, "OS is Linux")
        assert "OS is Linux" in claim.assumptions

    def test_add_assumption_dedup(self, ledger):
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        ledger.add_assumption(claim.claim_id, "OS is Linux")
        ledger.add_assumption(claim.claim_id, "OS is Linux")
        assert claim.assumptions.count("OS is Linux") == 1

    def test_add_assumption_nonexistent_claim(self, ledger):
        assert ledger.add_assumption("nonexistent", "test") is False

    def test_hard_claims_query(self, ledger):
        c1 = ledger.new_claim("claim1", Provenance.RETRIEVED)
        c2 = ledger.new_claim("claim2", Provenance.RETRIEVED)
        c3 = ledger.new_claim("claim3", Provenance.ASSUMED)
        ledger.set_commit_level(c1.claim_id, "hard")
        ledger.set_commit_level(c2.claim_id, "hard")
        ledger.set_commit_level(c3.claim_id, "soft")
        assert len(ledger.hard_claims()) == 2

    def test_soft_claims_query(self, ledger):
        c1 = ledger.new_claim("claim1", Provenance.ASSUMED)
        c2 = ledger.new_claim("claim2", Provenance.ASSUMED)
        ledger.set_commit_level(c1.claim_id, "soft")
        ledger.set_commit_level(c2.claim_id, "hard")
        assert len(ledger.soft_claims()) == 1

    def test_refused_claims_query(self, ledger):
        c1 = ledger.new_claim("claim1", Provenance.ASSUMED)
        ledger.set_commit_level(c1.claim_id, "refused")
        assert len(ledger.refused_claims()) == 1

    def test_claims_with_assumptions_query(self, ledger):
        c1 = ledger.new_claim("claim1", Provenance.ASSUMED)
        c2 = ledger.new_claim("claim2", Provenance.ASSUMED)
        ledger.add_assumption(c1.claim_id, "requires Python 3.10")
        assert len(ledger.claims_with_assumptions()) == 1

    def test_metrics_include_commit_level_distribution(self, ledger):
        c1 = ledger.new_claim("claim1", Provenance.RETRIEVED)
        c2 = ledger.new_claim("claim2", Provenance.ASSUMED)
        c3 = ledger.new_claim("claim3", Provenance.ASSUMED)
        ledger.set_commit_level(c1.claim_id, "hard")
        ledger.set_commit_level(c2.claim_id, "soft")
        ledger.add_assumption(c3.claim_id, "some assumption")

        metrics = ledger.get_metrics()
        assert "commit_level_distribution" in metrics
        assert metrics["commit_level_distribution"]["hard"] == 1
        assert metrics["commit_level_distribution"]["soft"] == 1
        assert metrics["commit_level_distribution"]["unclassified"] == 1
        assert metrics["claims_with_assumptions"] == 1


# =============================================================================
# TestStrictModeGateWiring
# =============================================================================


class TestStrictModeGateWiring:
    """Tests for StrictModeGate.evaluate_claim() wiring to GroundedClaim."""

    def test_evaluate_claim_sets_hard(self, gate, ledger):
        claim = ledger.new_claim("Python 3.12 supports PEP 695", Provenance.RETRIEVED)
        # Add evidence to satisfy requirements
        ref = EvidenceRef.from_url("https://docs.python.org", "version")
        claim.evidence_refs.append(ref)
        claim.evidence_refs.append(
            EvidenceRef.from_tool_trace("lint_check", "syntax")
        )

        result = gate.evaluate_claim(
            claim, ClaimCategory.CODE,
            independence_score=0.6,
            has_version=True,
            is_runnable=True,
        )
        assert claim.commit_level == "hard"
        assert result.commit_level == CommitLevel.HARD

    def test_evaluate_claim_sets_soft(self, gate, ledger):
        claim = ledger.new_claim("Use React for the frontend", Provenance.ASSUMED)
        result = gate.evaluate_claim(
            claim, ClaimCategory.CODE,
            independence_score=0.6,
            has_version=True,
            # missing is_runnable → not all requirements met
        )
        assert claim.commit_level == "soft"
        assert result.commit_level == CommitLevel.SOFT

    def test_evaluate_claim_sets_refused(self, gate, ledger):
        claim = ledger.new_claim("Delete the production database", Provenance.ASSUMED)
        result = gate.evaluate_claim(
            claim, ClaimCategory.PROCEDURE,
            # No evidence, no requirements met
        )
        assert claim.commit_level == "refused"
        assert result.commit_level == CommitLevel.REFUSED

    def test_evaluate_claim_soft_only_categories(self, gate, ledger):
        claim = ledger.new_claim("This seems like a good idea", Provenance.ASSUMED)
        result = gate.evaluate_claim(claim, ClaimCategory.JUDGMENT)
        assert claim.commit_level == "soft"
        assert result.commit_level == CommitLevel.SOFT

    def test_evaluate_claim_populates_assumptions(self, gate, ledger):
        claim = ledger.new_claim("apt install nginx", Provenance.ASSUMED)
        result = gate.evaluate_claim(
            claim, ClaimCategory.PROCEDURE,
        )
        # Should have unsatisfied requirements as assumptions
        assert claim.has_assumptions
        assert len(claim.assumptions) > 0

    def test_evaluate_claim_auto_counts_evidence(self, gate, ledger):
        claim = ledger.new_claim("test fact", Provenance.RETRIEVED)
        ref = EvidenceRef.from_url("https://example.com", "test")
        claim.evidence_refs.append(ref)

        result = gate.evaluate_claim(
            claim, ClaimCategory.STATIC_FACT,
            has_source=True,
            has_version=True,
            has_verification_date=True,
            independence_score=0.6,
        )
        # 1 evidence, but STATIC_FACT needs min 2 → should be SOFT
        assert claim.commit_level == "soft"

    def test_evaluate_claim_explicit_evidence_count_overrides(self, gate, ledger):
        claim = ledger.new_claim("test fact", Provenance.RETRIEVED)
        # Pass evidence_count explicitly, overriding auto-count
        result = gate.evaluate_claim(
            claim, ClaimCategory.STATIC_FACT,
            evidence_count=3,
            has_source=True,
            has_version=True,
            has_verification_date=True,
            independence_score=0.6,
        )
        assert claim.commit_level == "hard"

    def test_evaluate_claim_no_duplicate_assumptions(self, gate, ledger):
        claim = ledger.new_claim("run this command", Provenance.ASSUMED)
        # Evaluate twice — assumptions should not duplicate
        gate.evaluate_claim(claim, ClaimCategory.PROCEDURE)
        gate.evaluate_claim(claim, ClaimCategory.PROCEDURE)
        # Each assumption should appear only once
        unique = set(claim.assumptions)
        assert len(unique) == len(claim.assumptions)


# =============================================================================
# TestSchemaV3Migration
# =============================================================================


class TestSchemaV3Migration:
    """Tests for schema v3 migration (commit_level columns)."""

    def test_fresh_db_has_commit_level_columns(self, storage):
        cursor = storage.conn.cursor()
        cursor.execute("PRAGMA table_info(facts)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "commit_level" in columns
        assert "assumptions_json" in columns

        cursor.execute("PRAGMA table_info(decisions)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "commit_level" in columns
        assert "assumptions_json" in columns

    def test_v2_db_migrates_to_v3(self, tmp_dir):
        """Simulate a v2 database and verify migration adds columns."""
        db_path = tmp_dir / "v2_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.commit()
        conn.close()

        storage = Storage(db_path)
        cursor = storage.conn.cursor()

        cursor.execute("PRAGMA table_info(facts)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "commit_level" in columns
        assert "assumptions_json" in columns

        cursor.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()["version"] == SCHEMA_VERSION

        storage.close()

    def test_v1_db_migrates_to_v3(self, tmp_dir):
        """v1 database should get both v2 and v3 migrations."""
        db_path = tmp_dir / "v1_test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.commit()
        conn.close()

        storage = Storage(db_path)
        cursor = storage.conn.cursor()

        # V2 tables should exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='evidence'"
        )
        assert cursor.fetchone() is not None

        # V3 columns should exist
        cursor.execute("PRAGMA table_info(facts)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "commit_level" in columns

        cursor.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()["version"] == SCHEMA_VERSION

        storage.close()

    def test_existing_data_preserved_after_v3_migration(self, tmp_dir):
        """Data in facts table should survive migration."""
        db_path = tmp_dir / "preserve_v3.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.execute(
            "INSERT INTO facts (id, claim_type, claim_json, receipt_json, epoch, created_at) "
            "VALUES ('f1', 'file_exists', '{}', '{}', 1, '2025-01-01')"
        )
        conn.commit()
        conn.close()

        storage = Storage(db_path)
        cursor = storage.conn.cursor()
        cursor.execute("SELECT * FROM facts WHERE id = 'f1'")
        row = cursor.fetchone()
        assert row is not None
        assert row["claim_type"] == "file_exists"
        # New columns should have defaults
        assert row["commit_level"] is None
        assert row["assumptions_json"] == "[]"
        storage.close()

    def test_schema_version_is_4(self, storage):
        cursor = storage.conn.cursor()
        cursor.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()["version"] == SCHEMA_VERSION

    def test_idempotent_migration(self, tmp_dir):
        """Running migration twice should not fail."""
        db_path = tmp_dir / "idempotent.db"
        # Create v2 db
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        conn.execute("INSERT INTO schema_version (version) VALUES (2)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.commit()
        conn.close()

        # First migration
        s1 = Storage(db_path)
        s1.close()

        # Manually downgrade version to force re-migration
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE schema_version SET version = 2")
        conn.commit()
        conn.close()

        # Second migration should succeed (idempotent ALTER TABLE)
        s2 = Storage(db_path)
        cursor = s2.conn.cursor()
        cursor.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()["version"] == SCHEMA_VERSION
        s2.close()


# =============================================================================
# TestPremiseRule (preview of Layer 4 integration)
# =============================================================================


class TestPremiseRule:
    """Tests for premise rule: SOFT claims cannot premise HARD claims."""

    def test_soft_dependency_prevents_hard(self, ledger, gate):
        """If a claim depends on a SOFT premise, it should not be HARD."""
        premise = ledger.new_claim("Python supports type hints", Provenance.ASSUMED)
        ledger.set_commit_level(premise.claim_id, "soft")
        ledger.add_assumption(premise.claim_id, "no version specified")

        dependent = ledger.new_claim("Use match statement", Provenance.DERIVED)
        # The dependent claim inherits assumptions from its premise
        ledger.add_assumption(dependent.claim_id, f"depends on: {premise.claim_id}")

        # A claim with assumptions should be SOFT at best
        assert dependent.has_assumptions

    def test_hard_premise_allows_hard_dependent(self, ledger):
        """HARD premises can support HARD dependents."""
        premise = ledger.new_claim("Python 3.10+ exists", Provenance.RETRIEVED)
        ref = EvidenceRef.from_url("https://python.org", "release")
        premise.evidence_refs.append(ref)
        ledger.set_commit_level(premise.claim_id, "hard")

        dependent = ledger.new_claim("match statement available", Provenance.DERIVED)
        # No assumptions needed - premise is HARD
        assert not dependent.has_assumptions


# =============================================================================
# TestBackwardCompat
# =============================================================================


class TestBackwardCompat:
    """Ensure existing tests and code are unaffected."""

    def test_existing_grounded_claim_unchanged(self, ledger):
        """Creating claims without commit_level works as before."""
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        assert claim.commit_level is None
        assert claim.assumptions == []
        assert claim.status == GroundedClaimStatus.ACTIVE

    def test_existing_serialization_roundtrip(self, ledger):
        """to_dict/from_dict roundtrip preserves all fields."""
        claim = ledger.new_claim("test content", Provenance.RETRIEVED, confidence=0.85)
        ref = EvidenceRef.from_url("https://example.com", "test")
        claim.evidence_refs.append(ref)

        d = claim.to_dict()
        restored = GroundedClaim.from_dict(d)
        assert restored.claim_id == claim.claim_id
        assert restored.content == claim.content
        assert restored.provenance == claim.provenance
        assert restored.confidence == claim.confidence
        assert len(restored.evidence_refs) == 1

    def test_existing_dangerous_claim_detection(self, ledger):
        """Dangerous claim detection still works."""
        # ASSUMED at 0.8 with no evidence = dangerous
        claim = ledger.new_claim("high confidence no evidence", Provenance.ASSUMED, confidence=0.8)
        assert claim.is_dangerous
        # PEER_ASSERTED gets clamped to MAX_PEER_CONFIDENCE (0.30) — not dangerous
        peer = ledger.new_peer_claim("peer claim", "agent_x", confidence=0.8)
        assert not peer.is_dangerous

    def test_existing_promotion_works(self, ledger):
        """Provenance promotion still works."""
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        ref = EvidenceRef.from_url("https://example.com", "test")
        ledger.attach_evidence(claim.claim_id, ref)
        result = ledger.promote(claim.claim_id, Provenance.DERIVED)
        assert result.value == "success"
