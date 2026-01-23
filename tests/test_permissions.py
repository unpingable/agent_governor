"""Tests for agent permissions system."""

import pytest
from pathlib import Path

from governor.claims import (
    Claim,
    ClaimType,
    file_exists,
    decision,
    changeset,
    work_reservation,
)
from governor.permissions import (
    AgentPermissions,
    PermissionManager,
    DEFAULT_PERMISSIONS,
    ARCHITECT_PERMISSIONS,
    IMPLEMENTER_PERMISSIONS,
    DOCS_PERMISSIONS,
    PROFILES,
    create_default_config,
)


class TestAgentPermissions:
    """Tests for AgentPermissions dataclass."""

    def test_default_permissions(self):
        """Test default permission values."""
        perms = AgentPermissions()

        assert perms.can_propose_decisions is False
        assert perms.can_propose_changesets is True
        assert perms.can_propose_facts is True
        assert perms.max_files_per_changeset == 20

    def test_can_touch_path_allowed(self):
        """Test path matching against allowed patterns."""
        perms = AgentPermissions(allowed_paths=["src/**", "tests/**"])

        assert perms.can_touch_path("src/main.py")
        assert perms.can_touch_path("src/api/users.py")
        assert perms.can_touch_path("tests/test_main.py")
        assert not perms.can_touch_path("docs/README.md")

    def test_can_touch_path_denied_takes_precedence(self):
        """Test that denied paths override allowed paths."""
        perms = AgentPermissions(
            allowed_paths=["**/*"],
            denied_paths=[".governor/**", "*.toml"],
        )

        assert perms.can_touch_path("src/main.py")
        assert not perms.can_touch_path(".governor/config.toml")
        assert not perms.can_touch_path("pyproject.toml")

    def test_can_decide_topic_no_restrictions(self):
        """Test topic decisions without restrictions."""
        perms = AgentPermissions(
            can_propose_decisions=True,
            allowed_decision_topics=[],  # No restrictions
        )

        assert perms.can_decide_topic("anything")
        assert perms.can_decide_topic("framework")

    def test_can_decide_topic_with_restrictions(self):
        """Test topic decisions with whitelist."""
        perms = AgentPermissions(
            can_propose_decisions=True,
            allowed_decision_topics=["framework", "database"],
        )

        assert perms.can_decide_topic("framework")
        assert perms.can_decide_topic("database")
        assert not perms.can_decide_topic("auth")

    def test_can_decide_topic_case_insensitive(self):
        """Test topic matching is case insensitive."""
        perms = AgentPermissions(
            can_propose_decisions=True,
            allowed_decision_topics=["Framework"],
        )

        assert perms.can_decide_topic("framework")
        assert perms.can_decide_topic("FRAMEWORK")

    def test_check_claim_decision_blocked(self):
        """Test that decision claims are blocked without permission."""
        perms = AgentPermissions(can_propose_decisions=False)
        claim = decision("framework", "react")

        allowed, reason = perms.check_claim(claim)

        assert not allowed
        assert "cannot propose decisions" in reason.lower()

    def test_check_claim_decision_allowed(self):
        """Test that decision claims are allowed with permission."""
        perms = AgentPermissions(
            can_propose_decisions=True,
            allowed_decision_topics=["framework"],
        )
        claim = decision("framework", "react")

        allowed, reason = perms.check_claim(claim)

        assert allowed

    def test_check_claim_decision_wrong_topic(self):
        """Test that decisions for wrong topics are blocked."""
        perms = AgentPermissions(
            can_propose_decisions=True,
            allowed_decision_topics=["framework"],
        )
        claim = decision("database", "postgresql")

        allowed, reason = perms.check_claim(claim)

        assert not allowed
        assert "database" in reason

    def test_check_claim_changeset_blocked(self):
        """Test that changeset claims are blocked without permission."""
        perms = AgentPermissions(can_propose_changesets=False)
        claim = changeset("diff...", paths=["src/main.py"])

        allowed, reason = perms.check_claim(claim)

        assert not allowed
        assert "cannot propose changesets" in reason.lower()

    def test_check_claim_changeset_path_blocked(self):
        """Test that changesets to blocked paths are rejected."""
        perms = AgentPermissions(
            allowed_paths=["src/**"],
            denied_paths=[],
        )
        claim = changeset("diff...", paths=["docs/README.md"])

        allowed, reason = perms.check_claim(claim)

        assert not allowed
        assert "docs/README.md" in reason

    def test_check_claim_changeset_too_many_files(self):
        """Test that changesets exceeding file limit are rejected."""
        perms = AgentPermissions(
            max_files_per_changeset=3,
            allowed_paths=["*", "src/*", "src/**/*"],  # Allow all paths for this test
        )
        claim = changeset("diff...", paths=["a.py", "b.py", "c.py", "d.py", "e.py"])

        allowed, reason = perms.check_claim(claim)

        assert not allowed
        assert "5 files" in reason
        assert "max is 3" in reason

    def test_check_claim_file_exists(self):
        """Test file_exists claims respect path restrictions."""
        perms = AgentPermissions(allowed_paths=["src/**"])

        allowed1, _ = perms.check_claim(file_exists("src/main.py"))
        allowed2, _ = perms.check_claim(file_exists("docs/README.md"))

        assert allowed1
        assert not allowed2

    def test_check_claim_work_reservation_path_restricted(self):
        """Test work reservations respect path restrictions."""
        perms = AgentPermissions(allowed_paths=["src/**"])
        claim = work_reservation("implement feature", scope=["docs/api.md"])

        allowed, reason = perms.check_claim(claim)

        assert not allowed
        assert "docs/api.md" in reason

    def test_to_dict_from_dict_roundtrip(self):
        """Test serialization roundtrip."""
        perms = AgentPermissions(
            can_propose_decisions=True,
            allowed_paths=["src/**"],
            denied_paths=[".git/**"],
            allowed_decision_topics=["framework"],
            max_files_per_changeset=15,
        )

        data = perms.to_dict()
        restored = AgentPermissions.from_dict(data)

        assert restored.can_propose_decisions == perms.can_propose_decisions
        assert restored.allowed_paths == perms.allowed_paths
        assert restored.denied_paths == perms.denied_paths
        assert restored.allowed_decision_topics == perms.allowed_decision_topics
        assert restored.max_files_per_changeset == perms.max_files_per_changeset


class TestPredefinedProfiles:
    """Tests for predefined permission profiles."""

    def test_default_profile_exists(self):
        """Test default profile exists."""
        assert "default" in PROFILES
        assert DEFAULT_PERMISSIONS is not None

    def test_architect_profile_can_decide(self):
        """Test architect profile can make decisions."""
        assert ARCHITECT_PERMISSIONS.can_propose_decisions

    def test_implementer_profile_cannot_decide(self):
        """Test implementer profile cannot make decisions."""
        assert not IMPLEMENTER_PERMISSIONS.can_propose_decisions

    def test_docs_profile_path_restrictions(self):
        """Test docs profile has appropriate path restrictions."""
        assert DOCS_PERMISSIONS.can_touch_path("docs/README.md")
        assert DOCS_PERMISSIONS.can_touch_path("API.md")
        assert not DOCS_PERMISSIONS.can_touch_path("CLAUDE.md")  # Explicitly denied


class TestPermissionManager:
    """Tests for PermissionManager."""

    @pytest.fixture
    def governor_dir(self, tmp_path):
        """Create a governor directory."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        return gov_dir

    def test_loads_defaults_without_config(self, governor_dir):
        """Test that default permissions are used without config."""
        manager = PermissionManager(governor_dir)

        perms = manager.get_permissions("unknown-agent")

        assert perms is not None
        assert perms.can_propose_changesets

    def test_loads_config_file(self, governor_dir):
        """Test loading permissions from config file."""
        config = '''
[permissions.default]
can_propose_decisions = true
max_files_per_changeset = 5

[permissions.test-agent]
can_propose_decisions = false
allowed_paths = ["specific/**"]
'''
        (governor_dir / "config.toml").write_text(config)

        manager = PermissionManager(governor_dir)

        default_perms = manager.get_permissions("some-agent")
        assert default_perms.can_propose_decisions
        assert default_perms.max_files_per_changeset == 5

        specific_perms = manager.get_permissions("test-agent")
        assert not specific_perms.can_propose_decisions
        assert specific_perms.allowed_paths == ["specific/**"]

    def test_agent_class_fallback(self, governor_dir):
        """Test fallback to agent class permissions."""
        config = '''
[permissions.default]
can_propose_decisions = false

[permissions.architect]
can_propose_decisions = true
'''
        (governor_dir / "config.toml").write_text(config)

        manager = PermissionManager(governor_dir)

        # Unknown agent with architect class should get architect perms
        perms = manager.get_permissions("unknown-agent", agent_class="architect")

        assert perms.can_propose_decisions

    def test_check_claim_delegates(self, governor_dir):
        """Test check_claim uses correct permissions."""
        config = '''
[permissions.default]
can_propose_decisions = false

[permissions.architect]
can_propose_decisions = true
allowed_decision_topics = ["framework"]
'''
        (governor_dir / "config.toml").write_text(config)

        manager = PermissionManager(governor_dir)

        # Default agent cannot decide
        allowed, _ = manager.check_claim(
            "worker-1",
            decision("framework", "react"),
        )
        assert not allowed

        # Architect can decide on framework
        allowed, _ = manager.check_claim(
            "architect-1",
            decision("framework", "react"),
            agent_class="architect",
        )
        assert allowed

    def test_all_permissions(self, governor_dir):
        """Test getting all configured permissions."""
        config = '''
[permissions.default]
can_propose_decisions = false

[permissions.architect]
can_propose_decisions = true
'''
        (governor_dir / "config.toml").write_text(config)

        manager = PermissionManager(governor_dir)
        all_perms = manager.all_permissions()

        assert "default" in all_perms
        assert "architect" in all_perms


class TestCreateDefaultConfig:
    """Tests for create_default_config."""

    def test_creates_config_file(self, tmp_path):
        """Test config file is created."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        create_default_config(gov_dir)

        assert (gov_dir / "config.toml").exists()

    def test_does_not_overwrite_existing(self, tmp_path):
        """Test existing config is not overwritten."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        config_path = gov_dir / "config.toml"
        config_path.write_text("# Custom config")

        create_default_config(gov_dir)

        assert config_path.read_text() == "# Custom config"

    def test_created_config_is_valid(self, tmp_path):
        """Test created config can be loaded."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        create_default_config(gov_dir)

        # Should not raise
        manager = PermissionManager(gov_dir)
        assert manager.get_permissions("test") is not None
