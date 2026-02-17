# SPDX-License-Identifier: Apache-2.0
"""Tests for Code Autopilot intent resource."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governor.intent import (
    Intent,
    IntentProvenance,
    BRANCH_HEURISTICS,
    DEFAULT_PROFILE,
    get_intent,
    set_intent,
    clear_intent,
    resolve_intent,
    suggest_profile_for_branch,
    format_provenance,
)


class TestIntent:
    """Tests for Intent dataclass."""

    def test_creation_defaults(self):
        """Test Intent creation with defaults."""
        intent = Intent(profile="established")
        assert intent.profile == "established"
        assert intent.scope is None
        assert intent.deny is None
        assert intent.timebox_minutes is None
        assert intent.source == "default"
        assert intent.set_at  # Should be auto-set
        assert intent.operator  # Should be auto-set

    def test_creation_full(self):
        """Test Intent creation with all fields."""
        intent = Intent(
            profile="hotfix",
            scope=["src/**"],
            deny=["migrations/**"],
            timebox_minutes=90,
            reason="fixing bug",
            operator="jbeck",
            source="cli",
        )
        assert intent.profile == "hotfix"
        assert intent.scope == ["src/**"]
        assert intent.deny == ["migrations/**"]
        assert intent.timebox_minutes == 90

    def test_is_expired_no_timebox(self):
        """Test is_expired with no timebox."""
        intent = Intent(profile="established")
        assert not intent.is_expired

    def test_is_expired_future(self):
        """Test is_expired with future expiry."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        intent = Intent(profile="hotfix", expires_at=future)
        assert not intent.is_expired

    def test_is_expired_past(self):
        """Test is_expired with past expiry."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        intent = Intent(profile="hotfix", expires_at=past)
        assert intent.is_expired

    def test_remaining_minutes(self):
        """Test remaining_minutes calculation."""
        future = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
        intent = Intent(profile="hotfix", expires_at=future)
        remaining = intent.remaining_minutes
        assert remaining is not None
        assert 40 <= remaining <= 45

    def test_remaining_minutes_no_timebox(self):
        """Test remaining_minutes with no timebox."""
        intent = Intent(profile="established")
        assert intent.remaining_minutes is None

    def test_path_allowed_no_scope(self):
        """Test path_allowed with no scope restrictions."""
        intent = Intent(profile="established")
        assert intent.path_allowed("any/path.py")

    def test_path_allowed_with_scope(self):
        """Test path_allowed with scope patterns."""
        intent = Intent(profile="hotfix", scope=["src/**", "tests/**"])
        assert intent.path_allowed("src/api/routes.py")
        assert intent.path_allowed("tests/test_api.py")
        assert not intent.path_allowed("docs/readme.md")

    def test_path_allowed_with_deny(self):
        """Test path_allowed with deny patterns."""
        intent = Intent(profile="hotfix", deny=["migrations/**"])
        assert intent.path_allowed("src/api.py")
        assert not intent.path_allowed("migrations/001_init.py")

    def test_path_allowed_scope_and_deny(self):
        """Test path_allowed with both scope and deny."""
        intent = Intent(
            profile="hotfix",
            scope=["src/**"],
            deny=["src/vendor/**"],
        )
        assert intent.path_allowed("src/api.py")
        assert not intent.path_allowed("src/vendor/lib.py")  # Deny takes precedence
        assert not intent.path_allowed("tests/test.py")  # Not in scope

    def test_to_dict(self):
        """Test serialization to dict."""
        intent = Intent(
            profile="hotfix",
            scope=["src/**"],
            reason="test",
            operator="test_user",
            source="cli",
        )
        d = intent.to_dict()
        assert d["profile"] == "hotfix"
        assert d["scope"] == ["src/**"]
        assert d["reason"] == "test"

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            "profile": "production",
            "scope": ["api/**"],
            "timebox_minutes": 60,
            "reason": "deploy",
            "source": "ci",
        }
        intent = Intent.from_dict(d)
        assert intent.profile == "production"
        assert intent.scope == ["api/**"]
        assert intent.timebox_minutes == 60

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        original = Intent(
            profile="refactor",
            scope=["lib/**"],
            deny=["lib/legacy/**"],
            timebox_minutes=120,
            reason="cleanup",
        )
        restored = Intent.from_dict(original.to_dict())
        assert restored.profile == original.profile
        assert restored.scope == original.scope
        assert restored.deny == original.deny
        assert restored.timebox_minutes == original.timebox_minutes

    def test_to_status_string_simple(self):
        """Test status string for simple intent."""
        intent = Intent(profile="established")
        assert intent.to_status_string() == "established"

    def test_to_status_string_with_scope(self):
        """Test status string with scope."""
        intent = Intent(profile="hotfix", scope=["src/**"])
        status = intent.to_status_string()
        assert "hotfix" in status
        assert "src/**" in status

    def test_to_status_string_with_timebox(self):
        """Test status string with timebox."""
        future = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        intent = Intent(profile="hotfix", expires_at=future)
        status = intent.to_status_string()
        assert "hotfix" in status
        assert "m" in status  # minutes indicator


class TestIntentProvenance:
    """Tests for IntentProvenance dataclass."""

    def test_creation(self):
        """Test provenance creation."""
        prov = IntentProvenance(
            layer="cli",
            value=Intent(profile="hotfix"),
            reason="CLI override",
        )
        assert prov.layer == "cli"
        assert prov.value.profile == "hotfix"

    def test_to_dict(self):
        """Test serialization."""
        prov = IntentProvenance(
            layer="session",
            source_path="/path/to/intent.json",
            value=Intent(profile="established"),
        )
        d = prov.to_dict()
        assert d["layer"] == "session"
        assert d["source_path"] == "/path/to/intent.json"
        assert d["value"]["profile"] == "established"


class TestBranchHeuristics:
    """Tests for branch heuristic suggestions."""

    def test_main_branch(self):
        """Test suggestion for main branch."""
        profile, auto, high_risk = suggest_profile_for_branch("main")
        assert profile == "production"
        assert not auto  # Never auto-apply production
        assert high_risk

    def test_master_branch(self):
        """Test suggestion for master branch."""
        profile, auto, high_risk = suggest_profile_for_branch("master")
        assert profile == "production"
        assert not auto
        assert high_risk

    def test_hotfix_branch(self):
        """Test suggestion for hotfix branch."""
        profile, auto, high_risk = suggest_profile_for_branch("hotfix/auth-fix")
        assert profile == "hotfix"
        assert not auto
        assert high_risk

    def test_feature_branch(self):
        """Test suggestion for feature branch."""
        profile, auto, high_risk = suggest_profile_for_branch("feature/new-api")
        assert profile == "established"
        assert auto  # Safe to auto-apply
        assert not high_risk

    def test_wip_branch(self):
        """Test suggestion for WIP branch."""
        profile, auto, high_risk = suggest_profile_for_branch("wip/experiment")
        assert profile == "greenfield"
        assert auto
        assert not high_risk

    def test_refactor_branch(self):
        """Test suggestion for refactor branch."""
        profile, auto, high_risk = suggest_profile_for_branch("refactor/cleanup")
        assert profile == "refactor"
        assert auto
        assert not high_risk

    def test_unknown_branch(self):
        """Test suggestion for unknown branch pattern."""
        profile, auto, high_risk = suggest_profile_for_branch("random-name")
        assert profile == DEFAULT_PROFILE
        assert not auto
        assert not high_risk

    def test_none_branch(self):
        """Test suggestion with no branch."""
        profile, auto, high_risk = suggest_profile_for_branch(None)
        assert profile == DEFAULT_PROFILE


class TestIntentStorage:
    """Tests for intent storage functions."""

    def test_set_and_get_intent(self, tmp_path):
        """Test setting and getting intent."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        intent = Intent(
            profile="hotfix",
            scope=["src/**"],
            reason="test",
        )
        set_intent(gov_dir, intent)

        loaded = get_intent(gov_dir)
        assert loaded is not None
        assert loaded.profile == "hotfix"
        assert loaded.scope == ["src/**"]

    def test_get_intent_not_set(self, tmp_path):
        """Test getting intent when not set."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        loaded = get_intent(gov_dir)
        assert loaded is None

    def test_clear_intent(self, tmp_path):
        """Test clearing intent."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        set_intent(gov_dir, Intent(profile="hotfix"))
        assert get_intent(gov_dir) is not None

        cleared = clear_intent(gov_dir)
        assert cleared is True
        assert get_intent(gov_dir) is None

    def test_clear_intent_not_set(self, tmp_path):
        """Test clearing when no intent set."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        cleared = clear_intent(gov_dir)
        assert cleared is False

    def test_expired_intent_auto_cleared(self, tmp_path):
        """Test that expired intent is auto-cleared on get."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        intent = Intent(profile="hotfix", expires_at=past)
        set_intent(gov_dir, intent)

        loaded = get_intent(gov_dir)
        assert loaded is None  # Should be cleared

    def test_timebox_sets_expiry(self, tmp_path):
        """Test that timebox_minutes sets expires_at."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        intent = Intent(profile="hotfix", timebox_minutes=60)
        assert intent.expires_at is None  # Not set yet

        set_intent(gov_dir, intent)
        loaded = get_intent(gov_dir)

        assert loaded is not None
        assert loaded.expires_at is not None
        assert loaded.remaining_minutes is not None
        assert 55 <= loaded.remaining_minutes <= 60


class TestResolveIntent:
    """Tests for intent resolution."""

    def test_resolve_default(self, tmp_path):
        """Test resolution falls back to default."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        intent, prov = resolve_intent(gov_dir)
        assert intent.profile == DEFAULT_PROFILE
        assert intent.source == "default"

    def test_resolve_cli_override(self, tmp_path):
        """Test CLI override takes precedence."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Set session intent
        set_intent(gov_dir, Intent(profile="established"))

        # CLI override should take precedence
        intent, prov = resolve_intent(gov_dir, cli_overrides={"profile": "hotfix"})
        assert intent.profile == "hotfix"
        assert intent.source == "cli"

    def test_resolve_env_var(self, tmp_path, monkeypatch):
        """Test environment variable takes precedence over session."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        monkeypatch.setenv("GOV_PROFILE", "production")

        # Set session intent
        set_intent(gov_dir, Intent(profile="established"))

        intent, prov = resolve_intent(gov_dir)
        assert intent.profile == "production"
        assert intent.source == "env"

    def test_resolve_session(self, tmp_path):
        """Test session intent is used."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        set_intent(gov_dir, Intent(profile="hotfix", reason="fix bug"))

        intent, prov = resolve_intent(gov_dir)
        assert intent.profile == "hotfix"
        assert intent.reason == "fix bug"

    def test_provenance_chain(self, tmp_path):
        """Test provenance chain is populated."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        intent, prov = resolve_intent(gov_dir)

        # Should have checked multiple layers
        layers = [p.layer for p in prov]
        assert "cli" in layers
        assert "env" in layers
        assert "session" in layers
        assert "default" in layers


class TestFormatProvenance:
    """Tests for provenance formatting."""

    def test_format_simple(self):
        """Test simple provenance formatting."""
        prov = [
            IntentProvenance(layer="cli", checked=True, reason="No CLI override"),
            IntentProvenance(
                layer="default",
                value=Intent(profile="established"),
                reason="System default",
            ),
        ]
        formatted = format_provenance(prov)
        assert "Intent resolution" in formatted
        assert "[cli]" in formatted
        assert "[default]" in formatted
        assert "established" in formatted
