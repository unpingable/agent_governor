"""Tests for Code Autopilot profile configuration."""

import json
from pathlib import Path

import pytest

from governor.autopilot import (
    ViolationDefault,
    ApprovalPath,
    EvidenceRequired,
    AnchorStrictness,
    ScopeEnforcement,
    ChangeLimit,
    ProfileConfig,
    AUTOPILOT_PROFILES,
    get_autopilot_profile,
    list_autopilot_profiles,
    apply_autopilot_profile,
    load_autopilot_config,
    resolve_violation_action,
    check_change_limits,
)


class TestEnums:
    """Tests for autopilot enums."""

    def test_violation_default_values(self):
        """Test ViolationDefault enum values."""
        assert ViolationDefault.IGNORE.value == "ignore"
        assert ViolationDefault.WARN.value == "warn"
        assert ViolationDefault.BLOCK.value == "block"

    def test_approval_path_values(self):
        """Test ApprovalPath enum values."""
        assert ApprovalPath.AUTO.value == "auto"
        assert ApprovalPath.PROMPT.value == "prompt"
        assert ApprovalPath.REQUIRE_HUMAN.value == "require_human"

    def test_evidence_required_values(self):
        """Test EvidenceRequired enum values."""
        assert EvidenceRequired.NONE.value == "none"
        assert EvidenceRequired.TESTS.value == "tests"
        assert EvidenceRequired.TESTS_STATIC.value == "tests+static"
        assert EvidenceRequired.TESTS_STATIC_REVIEW.value == "tests+static+review"


class TestChangeLimit:
    """Tests for ChangeLimit dataclass."""

    def test_creation_empty(self):
        """Test ChangeLimit with no limits."""
        limit = ChangeLimit()
        assert limit.max_files is None
        assert limit.max_loc is None
        assert limit.max_modules is None

    def test_creation_with_values(self):
        """Test ChangeLimit with values."""
        limit = ChangeLimit(max_files=10, max_loc=500, max_modules=3)
        assert limit.max_files == 10
        assert limit.max_loc == 500
        assert limit.max_modules == 3

    def test_exceeds_files(self):
        """Test exceeds check for files."""
        limit = ChangeLimit(max_files=5)
        exceeded, reason = limit.exceeds(files=10)
        assert exceeded
        assert "max_files" in reason

    def test_exceeds_loc(self):
        """Test exceeds check for LOC."""
        limit = ChangeLimit(max_loc=100)
        exceeded, reason = limit.exceeds(loc=200)
        assert exceeded
        assert "max_loc" in reason

    def test_exceeds_modules(self):
        """Test exceeds check for modules."""
        limit = ChangeLimit(max_modules=2)
        exceeded, reason = limit.exceeds(modules=5)
        assert exceeded
        assert "max_modules" in reason

    def test_exceeds_within_limit(self):
        """Test exceeds when within limits."""
        limit = ChangeLimit(max_files=10, max_loc=500)
        exceeded, reason = limit.exceeds(files=5, loc=200)
        assert not exceeded
        assert reason is None

    def test_to_dict(self):
        """Test serialization."""
        limit = ChangeLimit(max_files=10, max_loc=500)
        d = limit.to_dict()
        assert d["max_files"] == 10
        assert d["max_loc"] == 500
        assert d["max_modules"] is None

    def test_from_dict(self):
        """Test deserialization."""
        d = {"max_files": 20, "max_loc": 1000}
        limit = ChangeLimit.from_dict(d)
        assert limit.max_files == 20
        assert limit.max_loc == 1000


class TestProfileConfig:
    """Tests for ProfileConfig dataclass."""

    def test_creation(self):
        """Test ProfileConfig creation."""
        config = ProfileConfig(
            name="test",
            description="Test profile",
            violation_default=ViolationDefault.WARN,
            retry_budget=3,
            evidence_required=EvidenceRequired.TESTS,
            scope_enforcement=ScopeEnforcement.WARN,
        )
        assert config.name == "test"
        assert config.violation_default == ViolationDefault.WARN
        assert config.retry_budget == 3

    def test_to_dict(self):
        """Test serialization."""
        config = ProfileConfig(
            name="test",
            description="Test",
            violation_default=ViolationDefault.BLOCK,
            retry_budget=1,
            evidence_required=EvidenceRequired.TESTS_STATIC,
            scope_enforcement=ScopeEnforcement.BLOCK,
            change_ceiling=ChangeLimit(max_files=10),
            anchor_strictness=AnchorStrictness.HARD,
            approval_path=ApprovalPath.REQUIRE_HUMAN,
        )
        d = config.to_dict()
        assert d["name"] == "test"
        assert d["violation_default"] == "block"
        assert d["change_ceiling"]["max_files"] == 10
        assert d["anchor_strictness"] == "hard"

    def test_from_dict(self):
        """Test deserialization."""
        d = {
            "name": "custom",
            "description": "Custom profile",
            "violation_default": "warn",
            "retry_budget": 2,
            "evidence_required": "tests",
            "scope_enforcement": "off",
        }
        config = ProfileConfig.from_dict(d)
        assert config.name == "custom"
        assert config.violation_default == ViolationDefault.WARN
        assert config.evidence_required == EvidenceRequired.TESTS

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = ProfileConfig(
            name="roundtrip",
            description="Test roundtrip",
            violation_default=ViolationDefault.BLOCK,
            retry_budget=1,
            evidence_required=EvidenceRequired.TESTS_STATIC_REVIEW,
            scope_enforcement=ScopeEnforcement.BLOCK,
            change_ceiling=ChangeLimit(max_files=5, max_loc=100),
        )
        restored = ProfileConfig.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.violation_default == original.violation_default
        assert restored.change_ceiling.max_files == 5


class TestBuiltinProfiles:
    """Tests for built-in autopilot profiles."""

    def test_all_profiles_exist(self):
        """Test all expected profiles exist."""
        expected = ["greenfield", "established", "production", "hotfix", "refactor"]
        for name in expected:
            assert name in AUTOPILOT_PROFILES

    def test_greenfield_profile(self):
        """Test greenfield profile configuration."""
        p = AUTOPILOT_PROFILES["greenfield"]
        assert p.violation_default == ViolationDefault.WARN
        assert p.retry_budget == 3
        assert p.evidence_required == EvidenceRequired.NONE
        assert p.scope_enforcement == ScopeEnforcement.OFF
        assert p.anchor_strictness == AnchorStrictness.SOFT
        assert p.approval_path == ApprovalPath.AUTO
        assert p.exploration_budget == 0.8

    def test_established_profile(self):
        """Test established profile configuration."""
        p = AUTOPILOT_PROFILES["established"]
        assert p.violation_default == ViolationDefault.BLOCK
        assert p.evidence_required == EvidenceRequired.TESTS
        assert p.scope_enforcement == ScopeEnforcement.WARN

    def test_production_profile(self):
        """Test production profile configuration."""
        p = AUTOPILOT_PROFILES["production"]
        assert p.violation_default == ViolationDefault.BLOCK
        assert p.retry_budget == 1
        assert p.evidence_required == EvidenceRequired.TESTS_STATIC_REVIEW
        assert p.scope_enforcement == ScopeEnforcement.BLOCK
        assert p.anchor_strictness == AnchorStrictness.HARD
        assert p.approval_path == ApprovalPath.REQUIRE_HUMAN
        assert p.change_ceiling is not None
        assert p.change_ceiling.max_files == 20

    def test_hotfix_profile(self):
        """Test hotfix profile configuration."""
        p = AUTOPILOT_PROFILES["hotfix"]
        assert p.violation_default == ViolationDefault.BLOCK
        assert p.violation_in_scope == ViolationDefault.WARN  # Different in-scope
        assert p.boil_level == "BOIL"
        assert p.exploration_budget == 0.0
        assert p.change_ceiling is not None

    def test_refactor_profile(self):
        """Test refactor profile configuration."""
        p = AUTOPILOT_PROFILES["refactor"]
        assert p.violation_default == ViolationDefault.WARN
        assert p.anchor_strictness == AnchorStrictness.SOFT


class TestProfileFunctions:
    """Tests for profile utility functions."""

    def test_get_autopilot_profile_exists(self):
        """Test getting existing profile."""
        p = get_autopilot_profile("established")
        assert p is not None
        assert p.name == "established"

    def test_get_autopilot_profile_not_exists(self):
        """Test getting non-existent profile."""
        p = get_autopilot_profile("nonexistent")
        assert p is None

    def test_list_autopilot_profiles(self):
        """Test listing all profiles."""
        profiles = list_autopilot_profiles()
        assert len(profiles) >= 5
        assert "greenfield" in profiles
        assert "production" in profiles


class TestApplyAutopilotProfile:
    """Tests for applying autopilot profiles."""

    def test_apply_profile(self, tmp_path):
        """Test applying a profile creates expected files."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        config = AUTOPILOT_PROFILES["production"]
        applied = apply_autopilot_profile(gov_dir, config)

        assert "envelope" in applied
        assert "boil" in applied
        assert "strict_mode" in applied
        assert "autopilot" in applied

        # Check files exist
        assert (gov_dir / ".envelope").exists()
        assert (gov_dir / ".boil_mode").exists()
        assert (gov_dir / ".strict_mode").exists()
        assert (gov_dir / ".autopilot").exists()

    def test_apply_profile_content(self, tmp_path):
        """Test applied profile file contents."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        config = AUTOPILOT_PROFILES["production"]
        apply_autopilot_profile(gov_dir, config)

        # Check envelope is strict for hard anchor strictness
        envelope = (gov_dir / ".envelope").read_text()
        assert envelope == "strict"

        # Check boil level
        boil = (gov_dir / ".boil_mode").read_text()
        assert boil == "DARJEELING"

        # Check strict mode
        strict = (gov_dir / ".strict_mode").read_text()
        assert strict == "enabled"

    def test_load_autopilot_config(self, tmp_path):
        """Test loading autopilot config."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        config = AUTOPILOT_PROFILES["hotfix"]
        apply_autopilot_profile(gov_dir, config)

        loaded = load_autopilot_config(gov_dir)
        assert loaded is not None
        assert loaded["profile"] == "hotfix"
        assert loaded["violation_default"] == "block"

    def test_load_autopilot_config_not_exists(self, tmp_path):
        """Test loading when no config exists."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        loaded = load_autopilot_config(gov_dir)
        assert loaded is None


class TestResolveViolationAction:
    """Tests for violation action resolution."""

    def test_resolve_default(self):
        """Test resolution uses profile default."""
        config = AUTOPILOT_PROFILES["greenfield"]
        action = resolve_violation_action(config)
        assert action == ViolationDefault.WARN

    def test_resolve_hotfix_in_scope(self):
        """Test hotfix uses different action in-scope."""
        config = AUTOPILOT_PROFILES["hotfix"]
        action = resolve_violation_action(config, path="src/api.py", scope=["src/**"])
        assert action == ViolationDefault.WARN

    def test_resolve_hotfix_out_of_scope(self):
        """Test hotfix uses default action out-of-scope."""
        config = AUTOPILOT_PROFILES["hotfix"]
        action = resolve_violation_action(config, path="docs/readme.md", scope=["src/**"])
        assert action == ViolationDefault.BLOCK


class TestCheckChangeLimits:
    """Tests for change limit checking."""

    def test_check_no_limits(self):
        """Test check when no limits defined."""
        config = AUTOPILOT_PROFILES["greenfield"]
        allowed, reason = check_change_limits(config, files=100, loc=10000)
        assert allowed
        assert reason is None

    def test_check_within_limits(self):
        """Test check within limits."""
        config = AUTOPILOT_PROFILES["production"]
        allowed, reason = check_change_limits(config, files=5, loc=100)
        assert allowed

    def test_check_exceeds_limits(self):
        """Test check exceeds limits."""
        config = AUTOPILOT_PROFILES["production"]
        allowed, reason = check_change_limits(config, files=50, loc=2000)
        assert not allowed
        assert "max_files" in reason or "max_loc" in reason
