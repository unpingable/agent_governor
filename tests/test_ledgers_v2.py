# SPDX-License-Identifier: Apache-2.0
"""Tests for SQLite-backed ledgers."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from governor.claims import Claim, ClaimType
from governor.receipts import FileSnapshot
from governor.storage import get_storage
from governor.ledgers_v2 import (
    Fact,
    Decision,
    SQLiteFactLedger,
    SQLiteDecisionLedger,
    ConflictError,
    get_ledgers,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def storage(tmp_path):
    """Create a storage instance."""
    governor_dir = tmp_path / ".governor"
    governor_dir.mkdir()
    return get_storage(governor_dir)


@pytest.fixture
def fact_ledger(storage):
    """Create a fact ledger."""
    return SQLiteFactLedger(storage)


@pytest.fixture
def decision_ledger(storage):
    """Create a decision ledger."""
    return SQLiteDecisionLedger(storage)


@pytest.fixture
def sample_file_claim():
    """Create a sample file exists claim."""
    return Claim(type=ClaimType.FILE_EXISTS, path="src/main.py")


@pytest.fixture
def sample_receipt():
    """Create a sample file snapshot receipt."""
    return FileSnapshot(
        path="src/main.py",
        blob_hash="abc123",
        size_bytes=100,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_decision_claim():
    """Create a sample decision claim."""
    return Claim(type=ClaimType.DECISION, topic="framework", choice="react")


# =============================================================================
# Fact Tests
# =============================================================================

class TestSQLiteFactLedger:
    """Tests for SQLiteFactLedger."""

    def test_add_fact(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test adding a fact."""
        fact = fact_ledger.add(sample_file_claim, sample_receipt)

        assert fact.id is not None
        assert fact.claim == sample_file_claim
        assert fact.receipt == sample_receipt
        assert fact.epoch > 0
        assert fact.is_valid

    def test_add_fact_with_file_hashes(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test adding a fact with file hashes."""
        file_hashes = {"src/main.py": "abc123", "src/utils.py": "def456"}
        fact = fact_ledger.add(sample_file_claim, sample_receipt, file_hashes=file_hashes)

        assert fact.file_hashes == file_hashes

    def test_get_fact(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test getting a fact by ID."""
        created = fact_ledger.add(sample_file_claim, sample_receipt)
        retrieved = fact_ledger.get(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.epoch == created.epoch

    def test_get_nonexistent_fact(self, fact_ledger):
        """Test getting a fact that doesn't exist."""
        result = fact_ledger.get(uuid4())
        assert result is None

    def test_query_by_claim_type(self, fact_ledger, sample_receipt):
        """Test querying facts by claim type."""
        claim1 = Claim(type=ClaimType.FILE_EXISTS, path="a.py")
        claim2 = Claim(type=ClaimType.FILE_EXISTS, path="b.py")
        claim3 = Claim(type=ClaimType.TESTS_PASS, command=("pytest",))

        fact_ledger.add(claim1, sample_receipt)
        fact_ledger.add(claim2, sample_receipt)
        fact_ledger.add(claim3, sample_receipt)

        file_facts = fact_ledger.query(claim_type=ClaimType.FILE_EXISTS)
        test_facts = fact_ledger.query(claim_type=ClaimType.TESTS_PASS)

        assert len(file_facts) == 2
        assert len(test_facts) == 1

    def test_query_by_path(self, fact_ledger, sample_receipt):
        """Test querying facts by path."""
        claim1 = Claim(type=ClaimType.FILE_EXISTS, path="a.py")
        claim2 = Claim(type=ClaimType.FILE_EXISTS, path="b.py")

        fact_ledger.add(claim1, sample_receipt)
        fact_ledger.add(claim2, sample_receipt)

        results = fact_ledger.query(path="a.py")

        assert len(results) == 1
        assert results[0].claim.path == "a.py"

    def test_invalidate_fact(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test invalidating a fact."""
        fact = fact_ledger.add(sample_file_claim, sample_receipt)

        result = fact_ledger.invalidate(fact.id)

        assert result
        retrieved = fact_ledger.get(fact.id)
        assert retrieved is not None
        assert not retrieved.is_valid

    def test_query_valid_only(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test that query filters out invalidated facts by default."""
        fact = fact_ledger.add(sample_file_claim, sample_receipt)
        fact_ledger.invalidate(fact.id)

        valid_results = fact_ledger.query()
        all_results = fact_ledger.query(valid_only=False)

        assert len(valid_results) == 0
        assert len(all_results) == 1

    def test_count(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test fact count."""
        assert fact_ledger.count == 0

        fact_ledger.add(sample_file_claim, sample_receipt)
        assert fact_ledger.count == 1

        fact2 = fact_ledger.add(sample_file_claim, sample_receipt)
        assert fact_ledger.count == 2

        fact_ledger.invalidate(fact2.id)
        assert fact_ledger.count == 1  # Only valid facts

    def test_epochs_increment(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test that epochs increment for each fact."""
        fact1 = fact_ledger.add(sample_file_claim, sample_receipt)
        fact2 = fact_ledger.add(sample_file_claim, sample_receipt)
        fact3 = fact_ledger.add(sample_file_claim, sample_receipt)

        assert fact1.epoch < fact2.epoch < fact3.epoch

    def test_get_by_epoch(self, fact_ledger, sample_file_claim, sample_receipt):
        """Test getting facts by epoch."""
        fact1 = fact_ledger.add(sample_file_claim, sample_receipt)
        fact2 = fact_ledger.add(sample_file_claim, sample_receipt)
        fact3 = fact_ledger.add(sample_file_claim, sample_receipt)

        # Get facts from fact2's epoch onwards
        results = fact_ledger.get_by_epoch(fact2.epoch)

        assert len(results) == 2
        epochs = [f.epoch for f in results]
        assert fact2.epoch in epochs
        assert fact3.epoch in epochs

    def test_check_staleness_with_changed_file(self, fact_ledger, sample_receipt, tmp_path):
        """Test staleness check when file changes."""
        # Create a file
        test_file = tmp_path / "test.py"
        test_file.write_text("original content")
        original_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        claim = Claim(type=ClaimType.FILE_EXISTS, path="test.py")
        fact = fact_ledger.add(claim, sample_receipt, file_hashes={"test.py": original_hash})

        # File hasn't changed
        assert not fact_ledger.check_staleness(fact, tmp_path)

        # Change the file
        test_file.write_text("modified content")

        # Now it's stale
        assert fact_ledger.check_staleness(fact, tmp_path)

    def test_check_staleness_with_deleted_file(self, fact_ledger, sample_receipt, tmp_path):
        """Test staleness check when file is deleted."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")
        original_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        claim = Claim(type=ClaimType.FILE_EXISTS, path="test.py")
        fact = fact_ledger.add(claim, sample_receipt, file_hashes={"test.py": original_hash})

        # Delete the file
        test_file.unlink()

        # Now it's stale
        assert fact_ledger.check_staleness(fact, tmp_path)

    def test_invalidate_stale(self, fact_ledger, sample_receipt, tmp_path):
        """Test invalidating stale facts."""
        # Create files
        file1 = tmp_path / "a.py"
        file2 = tmp_path / "b.py"
        file1.write_text("content a")
        file2.write_text("content b")

        hash1 = hashlib.sha256(file1.read_bytes()).hexdigest()
        hash2 = hashlib.sha256(file2.read_bytes()).hexdigest()

        claim1 = Claim(type=ClaimType.FILE_EXISTS, path="a.py")
        claim2 = Claim(type=ClaimType.FILE_EXISTS, path="b.py")

        fact1 = fact_ledger.add(claim1, sample_receipt, file_hashes={"a.py": hash1})
        fact2 = fact_ledger.add(claim2, sample_receipt, file_hashes={"b.py": hash2})

        # Change file1
        file1.write_text("modified content")

        # Invalidate stale
        stale_ids = fact_ledger.invalidate_stale(tmp_path)

        assert len(stale_ids) == 1
        assert fact1.id in stale_ids

        # Verify only fact2 is still valid
        valid_facts = fact_ledger.query()
        assert len(valid_facts) == 1
        assert valid_facts[0].id == fact2.id


# =============================================================================
# Decision Tests
# =============================================================================

class TestSQLiteDecisionLedger:
    """Tests for SQLiteDecisionLedger."""

    def test_add_decision(self, decision_ledger, sample_decision_claim):
        """Test adding a decision."""
        decision = decision_ledger.add(sample_decision_claim, rationale="Best option")

        assert decision.id is not None
        assert decision.topic == "framework"
        assert decision.choice == "react"
        assert decision.rationale == "Best option"
        assert decision.epoch > 0

    def test_add_requires_decision_claim_type(self, decision_ledger):
        """Test that add requires DECISION claim type."""
        claim = Claim(type=ClaimType.FILE_EXISTS, path="test.py")

        with pytest.raises(ValueError, match="DECISION claim type"):
            decision_ledger.add(claim)

    def test_get_decision(self, decision_ledger, sample_decision_claim):
        """Test getting a decision by ID."""
        created = decision_ledger.add(sample_decision_claim)
        retrieved = decision_ledger.get(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.topic == created.topic

    def test_get_by_topic(self, decision_ledger):
        """Test getting decision by topic."""
        claim = Claim(type=ClaimType.DECISION, topic="database", choice="postgresql")
        decision_ledger.add(claim)

        result = decision_ledger.get_by_topic("database")

        assert result is not None
        assert result.choice == "postgresql"

    def test_conflict_detection(self, decision_ledger):
        """Test that conflicting decisions are detected."""
        claim1 = Claim(type=ClaimType.DECISION, topic="framework", choice="react")
        claim2 = Claim(type=ClaimType.DECISION, topic="framework", choice="vue")

        decision_ledger.add(claim1)

        with pytest.raises(ConflictError) as exc_info:
            decision_ledger.add(claim2)

        assert "Conflict" in str(exc_info.value)
        assert exc_info.value.existing is not None
        assert exc_info.value.existing.choice == "react"

    def test_same_choice_no_conflict(self, decision_ledger):
        """Test that same choice doesn't cause conflict."""
        claim1 = Claim(type=ClaimType.DECISION, topic="framework", choice="react")
        claim2 = Claim(type=ClaimType.DECISION, topic="framework", choice="react")

        decision_ledger.add(claim1)
        decision2 = decision_ledger.add(claim2)  # Should not raise

        assert decision2 is not None

    def test_different_topics_no_conflict(self, decision_ledger):
        """Test that different topics don't conflict."""
        claim1 = Claim(type=ClaimType.DECISION, topic="framework", choice="react")
        claim2 = Claim(type=ClaimType.DECISION, topic="database", choice="postgresql")

        decision_ledger.add(claim1)
        decision2 = decision_ledger.add(claim2)  # Should not raise

        assert decision2 is not None

    def test_revise_decision(self, decision_ledger):
        """Test revising a decision."""
        claim1 = Claim(type=ClaimType.DECISION, topic="framework", choice="react")
        original = decision_ledger.add(claim1)

        claim2 = Claim(type=ClaimType.DECISION, topic="framework", choice="vue")
        revised = decision_ledger.revise(original.id, claim2, rationale="Changed our minds")

        assert revised is not None
        assert revised.choice == "vue"
        assert revised.supersedes == original.id

        # Original is now superseded
        active = decision_ledger.get_by_topic("framework")
        assert active.id == revised.id

    def test_query_active_only(self, decision_ledger):
        """Test that query filters superseded decisions by default."""
        claim1 = Claim(type=ClaimType.DECISION, topic="framework", choice="react")
        original = decision_ledger.add(claim1)

        claim2 = Claim(type=ClaimType.DECISION, topic="framework", choice="vue")
        decision_ledger.revise(original.id, claim2)

        active = decision_ledger.query(active_only=True)
        all_decisions = decision_ledger.query(active_only=False)

        assert len(active) == 1
        assert active[0].choice == "vue"
        assert len(all_decisions) == 2

    def test_count_and_active_count(self, decision_ledger):
        """Test count vs active_count."""
        claim1 = Claim(type=ClaimType.DECISION, topic="framework", choice="react")
        original = decision_ledger.add(claim1)

        assert decision_ledger.count == 1
        assert decision_ledger.active_count == 1

        claim2 = Claim(type=ClaimType.DECISION, topic="framework", choice="vue")
        decision_ledger.revise(original.id, claim2)

        assert decision_ledger.count == 2  # Both exist
        assert decision_ledger.active_count == 1  # Only one active

    def test_epochs_increment(self, decision_ledger):
        """Test that epochs increment for each decision."""
        d1 = decision_ledger.add(Claim(type=ClaimType.DECISION, topic="a", choice="1"))
        d2 = decision_ledger.add(Claim(type=ClaimType.DECISION, topic="b", choice="2"))
        d3 = decision_ledger.add(Claim(type=ClaimType.DECISION, topic="c", choice="3"))

        assert d1.epoch < d2.epoch < d3.epoch

    def test_get_by_epoch(self, decision_ledger):
        """Test getting decisions by epoch."""
        d1 = decision_ledger.add(Claim(type=ClaimType.DECISION, topic="a", choice="1"))
        d2 = decision_ledger.add(Claim(type=ClaimType.DECISION, topic="b", choice="2"))
        d3 = decision_ledger.add(Claim(type=ClaimType.DECISION, topic="c", choice="3"))

        # Get decisions from d2's epoch onwards
        results = decision_ledger.get_by_epoch(d2.epoch)

        assert len(results) == 2
        epochs = [d.epoch for d in results]
        assert d2.epoch in epochs
        assert d3.epoch in epochs

    def test_check_conflict_method(self, decision_ledger, sample_decision_claim):
        """Test check_conflict method."""
        decision_ledger.add(sample_decision_claim)

        # Same topic, different choice = conflict
        conflict_claim = Claim(type=ClaimType.DECISION, topic="framework", choice="vue")
        conflicting = decision_ledger.check_conflict(conflict_claim)
        assert conflicting is not None
        assert conflicting.choice == "react"

        # Same topic, same choice = no conflict
        same_claim = Claim(type=ClaimType.DECISION, topic="framework", choice="react")
        assert decision_ledger.check_conflict(same_claim) is None

        # Different topic = no conflict
        other_claim = Claim(type=ClaimType.DECISION, topic="database", choice="mongo")
        assert decision_ledger.check_conflict(other_claim) is None


# =============================================================================
# Integration Tests
# =============================================================================

class TestGetLedgers:
    """Tests for get_ledgers helper."""

    def test_get_ledgers(self, tmp_path):
        """Test getting both ledgers."""
        governor_dir = tmp_path / ".governor"
        governor_dir.mkdir()

        fact_ledger, decision_ledger = get_ledgers(governor_dir)

        assert isinstance(fact_ledger, SQLiteFactLedger)
        assert isinstance(decision_ledger, SQLiteDecisionLedger)

        # They should share the same storage
        assert fact_ledger.storage is decision_ledger.storage

    def test_ledgers_share_epoch(self, tmp_path):
        """Test that ledgers share the epoch counter."""
        governor_dir = tmp_path / ".governor"
        governor_dir.mkdir()

        fact_ledger, decision_ledger = get_ledgers(governor_dir)

        receipt = FileSnapshot(
            path="test.py",
            blob_hash="abc",
            size_bytes=100,
            timestamp=datetime.now(timezone.utc),
        )

        fact1 = fact_ledger.add(
            Claim(type=ClaimType.FILE_EXISTS, path="test.py"),
            receipt
        )
        decision1 = decision_ledger.add(
            Claim(type=ClaimType.DECISION, topic="a", choice="1")
        )
        fact2 = fact_ledger.add(
            Claim(type=ClaimType.FILE_EXISTS, path="test2.py"),
            receipt
        )

        # Epochs should be sequential across both ledgers
        assert fact1.epoch < decision1.epoch < fact2.epoch
