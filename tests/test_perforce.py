# SPDX-License-Identifier: Apache-2.0
"""Tests for Perforce governance module.

Integrity invariants on explicit authority substrate. Tests work whether
or not P4 is installed - they use mocking for P4 CLI interactions.
"""

import pytest
import tempfile
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from governor.perforce import (
    # Availability
    p4_available,
    P4NotAvailableError,
    # Types
    CheckType,
    Severity,
    Violation,
    CheckResult,
    LockState,
    Changelist,
    DepotDOIMapping,
    # Configuration
    P4Connection,
    ChangelistIntegrityConfig,
    LockSemanticsConfig,
    ImmutableReleasesConfig,
    DOIMappingConfig,
    P4GovernanceConfig,
    # Client
    P4Client,
    # Checkers
    ChangelistIntegrityChecker,
    LockSemanticsChecker,
    ImmutableReleaseChecker,
    DOIMappingChecker,
    # Governor
    P4Governor,
    DOIMappingStore,
    # Convenience
    create_p4_governor,
    check_pre_submit,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def default_config():
    """Create a default P4GovernanceConfig."""
    return P4GovernanceConfig()


@pytest.fixture
def mock_p4_client():
    """Create a mock P4 client."""
    client = MagicMock(spec=P4Client)
    client.is_available.return_value = True
    return client


# =============================================================================
# Tests: Types
# =============================================================================


class TestCheckType:
    """Test CheckType enum."""

    def test_values(self):
        """Test enum values."""
        assert CheckType.CHANGELIST_INTEGRITY.value == "changelist_integrity"
        assert CheckType.LOCK_SEMANTICS.value == "lock_semantics"
        assert CheckType.IMMUTABLE_RELEASE.value == "immutable_release"
        assert CheckType.DOI_MAPPING.value == "doi_mapping"

    def test_count(self):
        """Test enum has expected count."""
        assert len(CheckType) == 4


class TestSeverity:
    """Test Severity enum."""

    def test_values(self):
        """Test enum values."""
        assert Severity.WARN.value == "warn"
        assert Severity.BLOCK.value == "block"


class TestViolation:
    """Test Violation dataclass."""

    def test_creation(self):
        """Test basic creation."""
        v = Violation(
            check_type=CheckType.CHANGELIST_INTEGRITY,
            message="Test violation",
        )
        assert v.check_type == CheckType.CHANGELIST_INTEGRITY
        assert v.message == "Test violation"
        assert v.changelist is None
        assert v.severity == Severity.WARN

    def test_to_dict(self):
        """Test serialization."""
        v = Violation(
            check_type=CheckType.LOCK_SEMANTICS,
            message="File locked",
            changelist=12345,
            file_path="//depot/test.txt",
            severity=Severity.BLOCK,
        )
        d = v.to_dict()
        assert d["check_type"] == "lock_semantics"
        assert d["message"] == "File locked"
        assert d["changelist"] == 12345
        assert d["file_path"] == "//depot/test.txt"
        assert d["severity"] == "block"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "check_type": "immutable_release",
            "message": "CL is immutable",
            "changelist": 99999,
            "severity": "block",
        }
        v = Violation.from_dict(data)
        assert v.check_type == CheckType.IMMUTABLE_RELEASE
        assert v.changelist == 99999


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_creation_passed(self):
        """Test creation for passed check."""
        r = CheckResult(passed=True, check_type=CheckType.DOI_MAPPING)
        assert r.passed is True
        assert r.violations == []

    def test_creation_failed(self):
        """Test creation with violations."""
        v = Violation(check_type=CheckType.CHANGELIST_INTEGRITY, message="Error")
        r = CheckResult(passed=False, violations=[v])
        assert r.passed is False
        assert len(r.violations) == 1

    def test_to_dict(self):
        """Test serialization."""
        v = Violation(check_type=CheckType.LOCK_SEMANTICS, message="Locked")
        r = CheckResult(passed=False, violations=[v], check_type=CheckType.LOCK_SEMANTICS)
        d = r.to_dict()
        assert d["passed"] is False
        assert len(d["violations"]) == 1
        assert d["check_type"] == "lock_semantics"


class TestLockState:
    """Test LockState dataclass."""

    def test_creation_unlocked(self):
        """Test creation for unlocked file."""
        ls = LockState(file_path="//depot/file.txt", locked=False)
        assert ls.file_path == "//depot/file.txt"
        assert ls.locked is False
        assert ls.lock_holder is None

    def test_creation_locked(self):
        """Test creation for locked file."""
        ls = LockState(
            file_path="//depot/file.txt",
            locked=True,
            lock_holder="user1",
            lock_client="ws1",
            lock_type="exclusive",
        )
        assert ls.locked is True
        assert ls.lock_holder == "user1"

    def test_to_dict(self):
        """Test serialization."""
        ls = LockState(file_path="//depot/f.txt", locked=True, lock_holder="u")
        d = ls.to_dict()
        assert d["locked"] is True
        assert d["lock_holder"] == "u"


class TestChangelist:
    """Test Changelist dataclass."""

    def test_creation(self):
        """Test basic creation."""
        cl = Changelist(
            number=12345,
            user="testuser",
            client="testclient",
            status="submitted",
            description="Test change",
        )
        assert cl.number == 12345
        assert cl.user == "testuser"
        assert cl.files == []

    def test_to_dict(self):
        """Test serialization."""
        cl = Changelist(
            number=1,
            user="u",
            client="c",
            status="pending",
            description="desc",
            files=["//depot/a.txt"],
            labels=["release"],
        )
        d = cl.to_dict()
        assert d["number"] == 1
        assert d["files"] == ["//depot/a.txt"]
        assert d["labels"] == ["release"]


class TestDepotDOIMapping:
    """Test DepotDOIMapping dataclass."""

    def test_creation(self):
        """Test basic creation."""
        m = DepotDOIMapping(
            doi="10.1234/test",
            depot_path="//depot/papers/test/...",
            changelist=12345,
            timestamp=datetime(2025, 1, 1),
        )
        assert m.doi == "10.1234/test"
        assert m.changelist == 12345

    def test_to_dict(self):
        """Test serialization."""
        m = DepotDOIMapping(
            doi="10.5678/example",
            depot_path="//depot/example/...",
            changelist=99,
            timestamp=datetime(2025, 6, 15, 12, 0, 0),
            content_hash="abc123",
        )
        d = m.to_dict()
        assert d["doi"] == "10.5678/example"
        assert d["content_hash"] == "abc123"

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "doi": "10.9999/test",
            "depot_path": "//depot/test",
            "changelist": 1,
            "timestamp": "2025-01-01T00:00:00",
        }
        m = DepotDOIMapping.from_dict(data)
        assert m.doi == "10.9999/test"
        assert m.changelist == 1

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        m1 = DepotDOIMapping(
            doi="10.test/round",
            depot_path="//depot/round",
            changelist=42,
            timestamp=datetime(2025, 3, 1, 9, 30, 0),
        )
        d = m1.to_dict()
        m2 = DepotDOIMapping.from_dict(d)
        assert m1.doi == m2.doi
        assert m1.changelist == m2.changelist


# =============================================================================
# Tests: Configuration
# =============================================================================


class TestP4Connection:
    """Test P4Connection dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = P4Connection()
        assert c.port == ""
        assert c.user == ""
        assert c.client == ""

    def test_to_dict(self):
        """Test serialization."""
        c = P4Connection(port="ssl:p4.example.com:1666", user="testuser")
        d = c.to_dict()
        assert d["port"] == "ssl:p4.example.com:1666"

    def test_from_dict(self):
        """Test deserialization."""
        data = {"port": "p4:1666", "user": "u", "client": "c"}
        c = P4Connection.from_dict(data)
        assert c.port == "p4:1666"


class TestChangelistIntegrityConfig:
    """Test ChangelistIntegrityConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = ChangelistIntegrityConfig()
        assert c.enabled is True
        assert c.require_metadata_match is True
        assert c.allow_prior_cl_reference is True

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        c1 = ChangelistIntegrityConfig(enabled=False)
        d = c1.to_dict()
        c2 = ChangelistIntegrityConfig.from_dict(d)
        assert c1.enabled == c2.enabled


class TestLockSemanticsConfig:
    """Test LockSemanticsConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = LockSemanticsConfig()
        assert c.enabled is True
        assert c.treat_as_authoritative is True
        assert c.block_cross_agent_claims is True


class TestImmutableReleasesConfig:
    """Test ImmutableReleasesConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = ImmutableReleasesConfig()
        assert c.enabled is True
        assert "published" in c.tags
        assert "release" in c.tags
        assert c.allow_fork_with_audit is True


class TestDOIMappingConfig:
    """Test DOIMappingConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = DOIMappingConfig()
        assert c.enabled is True
        assert "{doi_suffix}" in c.depot_pattern


class TestP4GovernanceConfig:
    """Test P4GovernanceConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = P4GovernanceConfig()
        assert c.enabled is True
        assert isinstance(c.connection, P4Connection)
        assert isinstance(c.changelist_integrity, ChangelistIntegrityConfig)

    def test_to_dict(self):
        """Test serialization."""
        c = P4GovernanceConfig(enabled=False)
        d = c.to_dict()
        assert d["enabled"] is False
        assert "connection" in d
        assert "changelist_integrity" in d

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "enabled": False,
            "connection": {"port": "test:1666"},
        }
        c = P4GovernanceConfig.from_dict(data)
        assert c.enabled is False
        assert c.connection.port == "test:1666"

    def test_save_and_load(self, temp_dir):
        """Test save and load."""
        c1 = P4GovernanceConfig(
            enabled=True,
            connection=P4Connection(port="ssl:p4:1666"),
        )
        path = temp_dir / "config.yaml"
        c1.save(path)

        c2 = P4GovernanceConfig.load(path)
        assert c2.enabled is True
        assert c2.connection.port == "ssl:p4:1666"

    def test_load_nonexistent(self, temp_dir):
        """Test loading nonexistent file returns defaults."""
        c = P4GovernanceConfig.load(temp_dir / "missing.yaml")
        assert c.enabled is True


# =============================================================================
# Tests: P4 Client (Mocked)
# =============================================================================


class TestP4Client:
    """Test P4Client with mocked subprocess."""

    def test_is_available_true(self):
        """Test is_available when p4 is installed."""
        with patch("governor.perforce.p4_available", return_value=True):
            client = P4Client()
            assert client.is_available() is True

    def test_is_available_false(self):
        """Test is_available when p4 is not installed."""
        with patch("governor.perforce.p4_available", return_value=False):
            client = P4Client()
            assert client.is_available() is False

    def test_get_changelist_not_available(self):
        """Test get_changelist when p4 not available."""
        with patch("governor.perforce.p4_available", return_value=False):
            client = P4Client()
            result = client.get_changelist(12345)
            assert result is None

    def test_get_files_in_cl_not_available(self):
        """Test get_files_in_cl when p4 not available."""
        with patch("governor.perforce.p4_available", return_value=False):
            client = P4Client()
            result = client.get_files_in_cl(12345)
            assert result == []

    def test_get_lock_status_not_available(self):
        """Test get_lock_status when p4 not available."""
        with patch("governor.perforce.p4_available", return_value=False):
            client = P4Client()
            result = client.get_lock_status("//depot/test.txt")
            assert result.locked is False

    def test_get_labels_not_available(self):
        """Test get_labels when p4 not available."""
        with patch("governor.perforce.p4_available", return_value=False):
            client = P4Client()
            result = client.get_labels(12345)
            assert result == []

    def test_get_pending_changelists_not_available(self):
        """Test get_pending_changelists when p4 not available."""
        with patch("governor.perforce.p4_available", return_value=False):
            client = P4Client()
            result = client.get_pending_changelists()
            assert result == []


# =============================================================================
# Tests: Checkers
# =============================================================================


class TestChangelistIntegrityChecker:
    """Test ChangelistIntegrityChecker."""

    def test_check_disabled(self, default_config, mock_p4_client):
        """Test check when disabled."""
        default_config.changelist_integrity.enabled = False
        checker = ChangelistIntegrityChecker(default_config, mock_p4_client)
        result = checker.check(12345)
        assert result.passed is True

    def test_check_missing_claimed_file(self, default_config, mock_p4_client):
        """Test check catches missing claimed files."""
        mock_p4_client.get_files_in_cl.return_value = ["//depot/a.txt"]
        checker = ChangelistIntegrityChecker(default_config, mock_p4_client)

        result = checker.check(12345, metadata_claims=["//depot/b.txt"])

        assert result.passed is False
        assert len(result.violations) == 1
        assert "not in changelist" in result.violations[0].message

    def test_check_all_files_present(self, default_config, mock_p4_client):
        """Test check passes when all claimed files present."""
        mock_p4_client.get_files_in_cl.return_value = ["//depot/a.txt", "//depot/b.txt"]
        checker = ChangelistIntegrityChecker(default_config, mock_p4_client)

        result = checker.check(12345, metadata_claims=["//depot/a.txt"])

        assert result.passed is True


class TestLockSemanticsChecker:
    """Test LockSemanticsChecker."""

    def test_check_disabled(self, default_config, mock_p4_client):
        """Test check when disabled."""
        default_config.lock_semantics.enabled = False
        checker = LockSemanticsChecker(default_config, mock_p4_client)
        result = checker.check_lock_authority("//depot/file.txt")
        assert result.passed is True

    def test_check_unlocked_file(self, default_config, mock_p4_client):
        """Test check passes for unlocked file."""
        mock_p4_client.get_lock_status.return_value = LockState(
            file_path="//depot/file.txt",
            locked=False,
        )
        checker = LockSemanticsChecker(default_config, mock_p4_client)
        result = checker.check_lock_authority("//depot/file.txt", agent_id="agent1")
        assert result.passed is True

    def test_check_locked_by_other(self, default_config, mock_p4_client):
        """Test check fails when locked by another agent."""
        mock_p4_client.get_lock_status.return_value = LockState(
            file_path="//depot/file.txt",
            locked=True,
            lock_holder="other_agent",
        )
        checker = LockSemanticsChecker(default_config, mock_p4_client)
        result = checker.check_lock_authority("//depot/file.txt", agent_id="agent1")

        assert result.passed is False
        assert "locked by" in result.violations[0].message

    def test_check_locked_by_self(self, default_config, mock_p4_client):
        """Test check passes when locked by same agent."""
        mock_p4_client.get_lock_status.return_value = LockState(
            file_path="//depot/file.txt",
            locked=True,
            lock_holder="agent1",
        )
        checker = LockSemanticsChecker(default_config, mock_p4_client)
        result = checker.check_lock_authority("//depot/file.txt", agent_id="agent1")
        assert result.passed is True


class TestImmutableReleaseChecker:
    """Test ImmutableReleaseChecker."""

    def test_check_disabled(self, default_config, mock_p4_client):
        """Test check when disabled."""
        default_config.immutable_releases.enabled = False
        checker = ImmutableReleaseChecker(default_config, mock_p4_client)
        result = checker.check_modification_attempt(12345)
        assert result.passed is True

    def test_mark_immutable(self, default_config, mock_p4_client):
        """Test marking CL as immutable."""
        checker = ImmutableReleaseChecker(default_config, mock_p4_client)

        # Valid tag
        assert checker.mark_immutable(12345, "release") is True
        assert checker.is_immutable(12345) is True

        # Invalid tag
        assert checker.mark_immutable(99999, "invalid_tag") is False

    def test_check_immutable_cl(self, default_config, mock_p4_client):
        """Test check fails for immutable CL."""
        checker = ImmutableReleaseChecker(default_config, mock_p4_client)
        checker.mark_immutable(12345, "published")

        result = checker.check_modification_attempt(12345)

        assert result.passed is False
        assert "immutable" in result.violations[0].message

    def test_check_mutable_cl(self, default_config, mock_p4_client):
        """Test check passes for mutable CL."""
        mock_p4_client.get_labels.return_value = []
        checker = ImmutableReleaseChecker(default_config, mock_p4_client)

        result = checker.check_modification_attempt(12345)

        assert result.passed is True


class TestDOIMappingChecker:
    """Test DOIMappingChecker."""

    def test_check_disabled(self, default_config, mock_p4_client):
        """Test check when disabled."""
        default_config.doi_mapping.enabled = False
        checker = DOIMappingChecker(default_config, mock_p4_client)
        result = checker.verify_mapping("10.1234/test")
        assert result.passed is True

    def test_check_missing_mapping(self, default_config, mock_p4_client):
        """Test check fails for missing mapping."""
        checker = DOIMappingChecker(default_config, mock_p4_client)
        result = checker.verify_mapping("10.1234/nonexistent")

        assert result.passed is False
        assert "No mapping found" in result.violations[0].message

    def test_add_and_verify_mapping(self, default_config, mock_p4_client):
        """Test adding and verifying a mapping."""
        mock_p4_client.get_files_in_cl.return_value = ["//depot/papers/test/paper.pdf"]
        checker = DOIMappingChecker(default_config, mock_p4_client)

        mapping = DepotDOIMapping(
            doi="10.1234/test",
            depot_path="//depot/papers/test",
            changelist=12345,
            timestamp=datetime.now(),
        )
        checker.add_mapping(mapping)

        assert checker.get_mapping("10.1234/test") is not None

    def test_list_mappings(self, default_config, mock_p4_client):
        """Test listing all mappings."""
        checker = DOIMappingChecker(default_config, mock_p4_client)

        for i in range(3):
            mapping = DepotDOIMapping(
                doi=f"10.1234/test{i}",
                depot_path=f"//depot/test{i}",
                changelist=i,
                timestamp=datetime.now(),
            )
            checker.add_mapping(mapping)

        assert len(checker.list_mappings()) == 3


# =============================================================================
# Tests: P4 Governor
# =============================================================================


class TestP4Governor:
    """Test P4Governor main interface."""

    def test_creation_default(self, temp_dir):
        """Test creation with defaults."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            assert gov.config.enabled is True
            assert gov.is_available() is False

    def test_creation_with_config(self, temp_dir):
        """Test creation with custom config."""
        config = P4GovernanceConfig(enabled=False)
        gov = P4Governor(config=config, cwd=temp_dir)
        assert gov.config.enabled is False

    def test_load_config_from_file(self, temp_dir):
        """Test loading config from file."""
        gov_dir = temp_dir / ".governor"
        gov_dir.mkdir()
        config = P4GovernanceConfig(
            connection=P4Connection(port="test:1666")
        )
        config.save(gov_dir / "p4_policy.yaml")

        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            assert gov.config.connection.port == "test:1666"

    def test_check_changelist(self, temp_dir):
        """Test check_changelist method."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            result = gov.check_changelist(12345)
            assert result.check_type == CheckType.CHANGELIST_INTEGRITY

    def test_check_lock(self, temp_dir):
        """Test check_lock method."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            result = gov.check_lock("//depot/file.txt")
            assert result.check_type == CheckType.LOCK_SEMANTICS

    def test_check_immutable(self, temp_dir):
        """Test check_immutable method."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            result = gov.check_immutable(12345)
            assert result.check_type == CheckType.IMMUTABLE_RELEASE

    def test_mark_release(self, temp_dir):
        """Test mark_release method."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            assert gov.mark_release(12345, "release") is True
            result = gov.check_immutable(12345)
            assert result.passed is False

    def test_add_and_verify_doi(self, temp_dir):
        """Test DOI mapping methods."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            gov.add_doi_mapping("10.1234/test", "//depot/test", 12345)
            result = gov.verify_doi("10.1234/test")
            # Will pass because P4 is not available to verify files
            assert result is not None

    def test_pre_submit_check(self, temp_dir):
        """Test pre_submit_check method."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            violations = gov.pre_submit_check(12345)
            assert isinstance(violations, list)

    def test_should_block(self, temp_dir):
        """Test should_block method."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = P4Governor(cwd=temp_dir)
            should_block, blocking = gov.should_block(12345)
            assert isinstance(should_block, bool)
            assert isinstance(blocking, list)


# =============================================================================
# Tests: DOI Mapping Store
# =============================================================================


class TestDOIMappingStore:
    """Test DOIMappingStore."""

    def test_add_and_get(self, temp_dir):
        """Test adding and getting mappings."""
        store = DOIMappingStore(temp_dir / "doi_mappings")

        mapping = DepotDOIMapping(
            doi="10.1234/test",
            depot_path="//depot/test",
            changelist=12345,
            timestamp=datetime.now(),
        )
        store.add(mapping)

        retrieved = store.get("10.1234/test")
        assert retrieved is not None
        assert retrieved.doi == "10.1234/test"

    def test_list_all(self, temp_dir):
        """Test listing all mappings."""
        store = DOIMappingStore(temp_dir / "doi_mappings")

        for i in range(3):
            mapping = DepotDOIMapping(
                doi=f"10.1234/test{i}",
                depot_path=f"//depot/test{i}",
                changelist=i,
                timestamp=datetime.now(),
            )
            store.add(mapping)

        assert len(store.list_all()) == 3

    def test_remove(self, temp_dir):
        """Test removing a mapping."""
        store = DOIMappingStore(temp_dir / "doi_mappings")

        mapping = DepotDOIMapping(
            doi="10.1234/toremove",
            depot_path="//depot/toremove",
            changelist=1,
            timestamp=datetime.now(),
        )
        store.add(mapping)
        assert store.get("10.1234/toremove") is not None

        store.remove("10.1234/toremove")
        assert store.get("10.1234/toremove") is None

    def test_persistence(self, temp_dir):
        """Test that mappings persist across store instances."""
        store1 = DOIMappingStore(temp_dir / "doi_mappings")
        mapping = DepotDOIMapping(
            doi="10.1234/persist",
            depot_path="//depot/persist",
            changelist=42,
            timestamp=datetime.now(),
        )
        store1.add(mapping)

        # Create new store instance
        store2 = DOIMappingStore(temp_dir / "doi_mappings")
        retrieved = store2.get("10.1234/persist")

        assert retrieved is not None
        assert retrieved.changelist == 42


# =============================================================================
# Tests: Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_create_p4_governor(self, temp_dir):
        """Test create_p4_governor."""
        with patch("governor.perforce.p4_available", return_value=False):
            gov = create_p4_governor(temp_dir)
            assert isinstance(gov, P4Governor)

    def test_check_pre_submit(self, temp_dir):
        """Test check_pre_submit convenience function."""
        with patch("governor.perforce.p4_available", return_value=False):
            violations = check_pre_submit(12345, temp_dir)
            assert isinstance(violations, list)


# =============================================================================
# Tests: Integration
# =============================================================================


class TestIntegration:
    """Integration tests for P4 governance."""

    def test_full_workflow(self, temp_dir):
        """Test complete P4 governance workflow."""
        with patch("governor.perforce.p4_available", return_value=False):
            # Create governor
            gov = P4Governor(cwd=temp_dir)

            # 1. Add DOI mapping
            gov.add_doi_mapping("10.1234/paper", "//depot/papers/paper", 12345)

            # 2. Mark release as immutable
            gov.mark_release(12345, "published")

            # 3. Check if CL can be modified (should fail)
            result = gov.check_immutable(12345)
            assert result.passed is False

            # 4. Check pre-submit
            violations = gov.pre_submit_check(12345)
            blocking = [v for v in violations if v.severity == Severity.BLOCK]
            assert len(blocking) > 0

    def test_config_persistence(self, temp_dir):
        """Test config saves and loads correctly."""
        gov_dir = temp_dir / ".governor"
        gov_dir.mkdir()

        config1 = P4GovernanceConfig(
            enabled=True,
            connection=P4Connection(port="ssl:p4.example.com:1666"),
            immutable_releases=ImmutableReleasesConfig(tags=["custom_release"]),
        )
        config1.save(gov_dir / "p4_policy.yaml")

        config2 = P4GovernanceConfig.load(gov_dir / "p4_policy.yaml")
        assert config2.connection.port == "ssl:p4.example.com:1666"
        assert "custom_release" in config2.immutable_releases.tags
