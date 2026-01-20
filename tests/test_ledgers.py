"""Tests for split ledgers (facts and decisions)."""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from governor.claims import Claim, ClaimType, file_exists, decision
from governor.receipts import FileSnapshot, CmdRun
from governor.ledgers import Fact, Decision, FactLedger, DecisionLedger


class TestFact:
    """Test Fact dataclass."""

    def test_create_fact(self):
        """Can create a Fact with required fields."""
        claim = file_exists("src/main.py")
        receipt = FileSnapshot(
            path="src/main.py",
            blob_hash="abc123",
            size_bytes=100,
            timestamp=datetime.now(timezone.utc),
        )

        fact = Fact(
            id=pytest.importorskip("uuid").uuid4(),
            claim=claim,
            receipt=receipt,
            created_at=datetime.now(timezone.utc),
        )

        assert fact.claim == claim
        assert fact.receipt == receipt

    def test_fact_with_file_hashes(self):
        """Fact can store file hashes for staleness detection."""
        from uuid import uuid4

        claim = file_exists("config.py")
        receipt = FileSnapshot(
            path="config.py",
            blob_hash="xyz",
            size_bytes=50,
            timestamp=datetime.now(timezone.utc),
        )

        fact = Fact(
            id=uuid4(),
            claim=claim,
            receipt=receipt,
            created_at=datetime.now(timezone.utc),
            file_hashes={"config.py": "abc123", "settings.py": "def456"},
        )

        assert fact.file_hashes["config.py"] == "abc123"

    def test_fact_serialization(self):
        """Fact survives JSON round-trip."""
        from uuid import uuid4

        claim = file_exists("test.py")
        receipt = FileSnapshot(
            path="test.py",
            blob_hash="hash",
            size_bytes=10,
            timestamp=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

        original = Fact(
            id=uuid4(),
            claim=claim,
            receipt=receipt,
            created_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            file_hashes={"test.py": "hash"},
        )

        data = original.to_dict()
        restored = Fact.from_dict(data)

        assert restored.id == original.id
        assert restored.claim == original.claim
        assert restored.file_hashes == original.file_hashes


class TestDecision:
    """Test Decision dataclass."""

    def test_create_decision(self):
        """Can create a Decision."""
        from uuid import uuid4

        claim = decision("framework", "react")

        dec = Decision(
            id=uuid4(),
            claim=claim,
            created_at=datetime.now(timezone.utc),
        )

        assert dec.topic == "framework"
        assert dec.choice == "react"

    def test_decision_requires_decision_claim_type(self):
        """Decision must have DECISION claim type."""
        from uuid import uuid4

        claim = file_exists("test.py")  # Wrong type

        with pytest.raises(ValueError, match="DECISION claim type"):
            Decision(
                id=uuid4(),
                claim=claim,
                created_at=datetime.now(timezone.utc),
            )

    def test_decision_with_rationale(self):
        """Decision can have rationale."""
        from uuid import uuid4

        claim = decision("database", "postgresql")

        dec = Decision(
            id=uuid4(),
            claim=claim,
            created_at=datetime.now(timezone.utc),
            rationale="Better JSON support and performance",
        )

        assert dec.rationale == "Better JSON support and performance"

    def test_decision_serialization(self):
        """Decision survives JSON round-trip."""
        from uuid import uuid4

        claim = decision("styling", "tailwind")
        supersedes_id = uuid4()

        original = Decision(
            id=uuid4(),
            claim=claim,
            created_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            rationale="Faster development",
            supersedes=supersedes_id,
        )

        data = original.to_dict()
        restored = Decision.from_dict(data)

        assert restored.id == original.id
        assert restored.topic == "styling"
        assert restored.choice == "tailwind"
        assert restored.rationale == "Faster development"
        assert restored.supersedes == supersedes_id


class TestFactLedger:
    """Test FactLedger class."""

    @pytest.fixture
    def ledger(self, tmp_path):
        """Create a FactLedger in a temp directory."""
        governor_dir = tmp_path / ".governor"
        return FactLedger(governor_dir)

    @pytest.fixture
    def sample_receipt(self):
        """Create a sample receipt."""
        return FileSnapshot(
            path="src/main.py",
            blob_hash="abc123",
            size_bytes=100,
            timestamp=datetime.now(timezone.utc),
        )

    def test_creates_directory_structure(self, tmp_path):
        """Ledger creates facts/ and receipts/ directories."""
        governor_dir = tmp_path / ".governor"
        FactLedger(governor_dir)

        assert (governor_dir / "facts").exists()
        assert (governor_dir / "facts" / "receipts").exists()
        assert (governor_dir / "facts" / "index.json").exists()

    def test_add_fact(self, ledger, sample_receipt):
        """Can add a fact to the ledger."""
        claim = file_exists("src/main.py")

        fact = ledger.add(claim, sample_receipt)

        assert fact.id is not None
        assert fact.claim == claim
        assert ledger.count == 1

    def test_get_fact(self, ledger, sample_receipt):
        """Can retrieve a fact by ID."""
        claim = file_exists("test.py")
        fact = ledger.add(claim, sample_receipt)

        retrieved = ledger.get(fact.id)

        assert retrieved is not None
        assert retrieved.id == fact.id

    def test_query_by_claim_type(self, ledger, sample_receipt):
        """Can query facts by claim type."""
        claim1 = file_exists("a.py")
        claim2 = Claim(type=ClaimType.TESTS_PASS, command=("pytest",))

        cmd_receipt = CmdRun(
            command=("pytest",),
            exit_code=0,
            stdout_hash="x",
            stderr_hash="y",
            cwd="/",
            duration_ms=100,
            timestamp=datetime.now(timezone.utc),
        )

        ledger.add(claim1, sample_receipt)
        ledger.add(claim2, cmd_receipt)

        file_facts = ledger.query(claim_type=ClaimType.FILE_EXISTS)
        test_facts = ledger.query(claim_type=ClaimType.TESTS_PASS)

        assert len(file_facts) == 1
        assert len(test_facts) == 1

    def test_query_by_path(self, ledger, sample_receipt):
        """Can query facts by path."""
        ledger.add(file_exists("a.py"), sample_receipt)
        ledger.add(file_exists("b.py"), sample_receipt)

        results = ledger.query(path="a.py")

        assert len(results) == 1
        assert results[0].claim.path == "a.py"

    def test_invalidate_fact(self, ledger, sample_receipt):
        """Can invalidate a fact."""
        fact = ledger.add(file_exists("test.py"), sample_receipt)

        assert ledger.invalidate(fact.id) is True
        assert ledger.get(fact.id) is None
        assert ledger.count == 0

    def test_invalidate_nonexistent(self, ledger):
        """Invalidating nonexistent fact returns False."""
        from uuid import uuid4

        assert ledger.invalidate(uuid4()) is False

    def test_persists_to_disk(self, tmp_path, sample_receipt):
        """Facts persist across ledger instances."""
        governor_dir = tmp_path / ".governor"

        # Create and add
        ledger1 = FactLedger(governor_dir)
        fact = ledger1.add(file_exists("test.py"), sample_receipt)

        # Load in new instance
        ledger2 = FactLedger(governor_dir)

        assert ledger2.count == 1
        assert ledger2.get(fact.id) is not None

    def test_check_staleness_fresh(self, ledger, tmp_path):
        """Fresh fact is not stale."""
        test_file = tmp_path / "code.py"
        test_file.write_text("print('hello')")
        file_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        receipt = FileSnapshot(
            path="code.py",
            blob_hash=file_hash,
            size_bytes=15,
            timestamp=datetime.now(timezone.utc),
        )

        fact = ledger.add(
            file_exists("code.py"),
            receipt,
            file_hashes={"code.py": file_hash},
        )

        assert ledger.check_staleness(fact, base_path=tmp_path) is False

    def test_check_staleness_file_changed(self, ledger, tmp_path):
        """Fact becomes stale when file changes."""
        test_file = tmp_path / "code.py"
        test_file.write_text("print('hello')")
        original_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        receipt = FileSnapshot(
            path="code.py",
            blob_hash=original_hash,
            size_bytes=15,
            timestamp=datetime.now(timezone.utc),
        )

        fact = ledger.add(
            file_exists("code.py"),
            receipt,
            file_hashes={"code.py": original_hash},
        )

        # Modify the file
        test_file.write_text("print('changed')")

        assert ledger.check_staleness(fact, base_path=tmp_path) is True

    def test_check_staleness_file_deleted(self, ledger, tmp_path):
        """Fact becomes stale when file is deleted."""
        test_file = tmp_path / "code.py"
        test_file.write_text("content")
        file_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()

        receipt = FileSnapshot(
            path="code.py",
            blob_hash=file_hash,
            size_bytes=7,
            timestamp=datetime.now(timezone.utc),
        )

        fact = ledger.add(
            file_exists("code.py"),
            receipt,
            file_hashes={"code.py": file_hash},
        )

        # Delete the file
        test_file.unlink()

        assert ledger.check_staleness(fact, base_path=tmp_path) is True

    def test_invalidate_stale(self, ledger, tmp_path):
        """Can invalidate all stale facts at once."""
        # Create two files
        file1 = tmp_path / "a.py"
        file2 = tmp_path / "b.py"
        file1.write_text("a")
        file2.write_text("b")

        hash1 = hashlib.sha256(b"a").hexdigest()
        hash2 = hashlib.sha256(b"b").hexdigest()

        receipt = FileSnapshot(
            path="test",
            blob_hash="x",
            size_bytes=1,
            timestamp=datetime.now(timezone.utc),
        )

        fact1 = ledger.add(
            file_exists("a.py"), receipt, file_hashes={"a.py": hash1}
        )
        fact2 = ledger.add(
            file_exists("b.py"), receipt, file_hashes={"b.py": hash2}
        )

        # Change one file
        file1.write_text("changed")

        stale_ids = ledger.invalidate_stale(base_path=tmp_path)

        assert fact1.id in stale_ids
        assert fact2.id not in stale_ids
        assert ledger.count == 1


class TestDecisionLedger:
    """Test DecisionLedger class."""

    @pytest.fixture
    def ledger(self, tmp_path):
        """Create a DecisionLedger in a temp directory."""
        governor_dir = tmp_path / ".governor"
        return DecisionLedger(governor_dir)

    def test_creates_directory_structure(self, tmp_path):
        """Ledger creates decisions/ directory."""
        governor_dir = tmp_path / ".governor"
        DecisionLedger(governor_dir)

        assert (governor_dir / "decisions").exists()
        assert (governor_dir / "decisions" / "index.json").exists()

    def test_add_decision(self, ledger):
        """Can add a decision."""
        claim = decision("framework", "react")

        dec = ledger.add(claim)

        assert dec.topic == "framework"
        assert dec.choice == "react"
        assert ledger.count == 1

    def test_add_decision_with_rationale(self, ledger):
        """Can add a decision with rationale."""
        claim = decision("database", "postgresql")

        dec = ledger.add(claim, rationale="Best for our use case")

        assert dec.rationale == "Best for our use case"

    def test_get_decision(self, ledger):
        """Can retrieve a decision by ID."""
        claim = decision("api", "rest")
        dec = ledger.add(claim)

        retrieved = ledger.get(dec.id)

        assert retrieved is not None
        assert retrieved.id == dec.id

    def test_query_by_topic(self, ledger):
        """Can query decisions by topic."""
        ledger.add(decision("framework", "react"))
        ledger.add(decision("database", "postgresql"))
        ledger.add(decision("framework", "vue"))  # Same topic, will supersede

        framework_decisions = ledger.query(topic="framework")

        # Both framework decisions are active (no supersedes set)
        assert len(framework_decisions) == 2

    def test_get_by_topic(self, ledger):
        """Can get current decision for a topic."""
        ledger.add(decision("framework", "react"))

        current = ledger.get_by_topic("framework")

        assert current is not None
        assert current.choice == "react"

    def test_get_by_topic_returns_none(self, ledger):
        """Returns None when no decision for topic."""
        assert ledger.get_by_topic("nonexistent") is None

    def test_check_conflict_found(self, ledger):
        """Detects conflict with existing decision."""
        ledger.add(decision("framework", "react"))

        conflicting_claim = decision("framework", "vue")
        conflict = ledger.check_conflict(conflicting_claim)

        assert conflict is not None
        assert conflict.choice == "react"

    def test_check_conflict_none(self, ledger):
        """No conflict when same choice."""
        ledger.add(decision("framework", "react"))

        same_claim = decision("framework", "react")
        conflict = ledger.check_conflict(same_claim)

        assert conflict is None

    def test_check_conflict_different_topic(self, ledger):
        """No conflict for different topic."""
        ledger.add(decision("framework", "react"))

        different_topic = decision("database", "postgresql")
        conflict = ledger.check_conflict(different_topic)

        assert conflict is None

    def test_revise_decision(self, ledger):
        """Can revise an existing decision."""
        original = ledger.add(decision("framework", "react"))

        new_claim = decision("framework", "vue")
        revised = ledger.revise(original.id, new_claim, rationale="Migrating")

        assert revised is not None
        assert revised.supersedes == original.id
        assert revised.choice == "vue"
        assert revised.rationale == "Migrating"

    def test_revise_filters_superseded(self, ledger):
        """Superseded decisions don't appear in queries."""
        original = ledger.add(decision("framework", "react"))
        ledger.revise(original.id, decision("framework", "vue"))

        active = ledger.query(topic="framework")

        assert len(active) == 1
        assert active[0].choice == "vue"

    def test_revise_nonexistent(self, ledger):
        """Revising nonexistent decision returns None."""
        from uuid import uuid4

        result = ledger.revise(uuid4(), decision("x", "y"))
        assert result is None

    def test_active_count(self, ledger):
        """active_count excludes superseded decisions."""
        original = ledger.add(decision("framework", "react"))
        ledger.revise(original.id, decision("framework", "vue"))
        ledger.add(decision("database", "postgresql"))

        assert ledger.count == 3  # Total including superseded
        assert ledger.active_count == 2  # Only active

    def test_persists_to_disk(self, tmp_path):
        """Decisions persist across ledger instances."""
        governor_dir = tmp_path / ".governor"

        # Create and add
        ledger1 = DecisionLedger(governor_dir)
        dec = ledger1.add(decision("framework", "react"))

        # Load in new instance
        ledger2 = DecisionLedger(governor_dir)

        assert ledger2.count == 1
        retrieved = ledger2.get(dec.id)
        assert retrieved is not None
        assert retrieved.choice == "react"

    def test_case_insensitive_topic_query(self, ledger):
        """Topic queries are case-insensitive."""
        ledger.add(decision("Framework", "react"))

        results = ledger.query(topic="framework")

        assert len(results) == 1
