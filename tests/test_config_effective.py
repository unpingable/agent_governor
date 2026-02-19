# SPDX-License-Identifier: Apache-2.0
"""Tests for config_effective: registry, collection, redaction."""

import json
import os
from pathlib import Path

import pytest

from governor.config_effective import (
    CONFIG_REGISTRY,
    ConfigEntry,
    ConfigSource,
    RedactionClass,
    collect_effective_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gov_dir(tmp_path):
    """Minimal .governor directory."""
    d = tmp_path / ".governor"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Registry structure
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_registry_is_ordered_dict(self):
        assert isinstance(CONFIG_REGISTRY, dict)
        assert len(CONFIG_REGISTRY) > 0

    def test_every_key_has_explain(self):
        for key, spec in CONFIG_REGISTRY.items():
            assert spec.explain, f"config key {key!r} has empty explain"

    def test_no_duplicate_keys(self):
        # Checked at import time by _reg assert, but verify here too
        keys = list(CONFIG_REGISTRY.keys())
        assert len(keys) == len(set(keys))

    def test_known_keys_present(self):
        assert "backend_type" in CONFIG_REGISTRY
        assert "model" in CONFIG_REGISTRY
        assert "api_key_set" in CONFIG_REGISTRY
        assert "envelope" in CONFIG_REGISTRY
        assert "mode" in CONFIG_REGISTRY


# ---------------------------------------------------------------------------
# ConfigEntry redaction
# ---------------------------------------------------------------------------

class TestConfigEntryRedaction:
    def test_public_shows_value(self):
        entry = ConfigEntry(
            key="test", raw_value="hello", source=ConfigSource.DEFAULT,
            source_detail={}, redaction=RedactionClass.PUBLIC, explain="test",
        )
        d = entry.to_dict()
        assert d["value"] == "hello"
        assert "raw_value" not in d

    def test_boolean_presence_shows_bool(self):
        entry = ConfigEntry(
            key="test", raw_value="sk-secret-key-12345", source=ConfigSource.ENV,
            source_detail={"var": "ANTHROPIC_API_KEY"},
            redaction=RedactionClass.BOOLEAN_PRESENCE, explain="test",
        )
        d = entry.to_dict()
        assert d["value"] is True
        assert "sk-secret" not in str(d)

    def test_boolean_presence_false_for_empty(self):
        entry = ConfigEntry(
            key="test", raw_value="", source=ConfigSource.DEFAULT,
            source_detail={}, redaction=RedactionClass.BOOLEAN_PRESENCE, explain="test",
        )
        assert entry.to_dict()["value"] is False

    def test_redacted_shows_stars(self):
        entry = ConfigEntry(
            key="test", raw_value="super-secret", source=ConfigSource.ENV,
            source_detail={"var": "SECRET"}, redaction=RedactionClass.REDACTED, explain="test",
        )
        d = entry.to_dict()
        assert d["value"] == "***"
        assert "super-secret" not in str(d)

    def test_hash_only_shows_prefix(self):
        entry = ConfigEntry(
            key="test", raw_value="my-secret-token", source=ConfigSource.ENV,
            source_detail={"var": "TOKEN"}, redaction=RedactionClass.HASH_ONLY, explain="test",
        )
        d = entry.to_dict()
        assert isinstance(d["value"], str)
        assert len(d["value"]) == 8
        assert "my-secret-token" not in str(d)

    def test_to_dict_never_contains_raw_value(self):
        for redaction in RedactionClass:
            entry = ConfigEntry(
                key="test", raw_value="secret123", source=ConfigSource.DEFAULT,
                source_detail={}, redaction=redaction, explain="test",
            )
            d = entry.to_dict()
            assert "raw_value" not in d

    def test_display_value_none(self):
        entry = ConfigEntry(
            key="test", raw_value=None, source=ConfigSource.DEFAULT,
            source_detail={}, redaction=RedactionClass.PUBLIC, explain="test",
        )
        assert entry.display_value() == "(none)"


# ---------------------------------------------------------------------------
# collect_effective_config
# ---------------------------------------------------------------------------

class TestCollectEffectiveConfig:
    def test_empty_gov_dir_returns_all_defaults(self, gov_dir):
        entries = collect_effective_config(gov_dir)
        assert len(entries) == len(CONFIG_REGISTRY)
        for entry in entries:
            if entry.key == "socket_path":
                continue  # computed, not default
            assert entry.source == ConfigSource.DEFAULT

    def test_key_ordering_matches_registry(self, gov_dir):
        entries = collect_effective_config(gov_dir)
        entry_keys = [e.key for e in entries]
        registry_keys = list(CONFIG_REGISTRY.keys())
        assert entry_keys == registry_keys

    def test_daemon_conf_overrides_default(self, gov_dir):
        conf = gov_dir / "daemon.conf"
        conf.write_text("[backend]\ntype = ollama\n")
        entries = collect_effective_config(gov_dir)
        by_key = {e.key: e for e in entries}
        assert by_key["backend_type"].raw_value == "ollama"
        assert by_key["backend_type"].source == ConfigSource.DAEMON_CONF

    def test_envelope_file_overrides(self, gov_dir):
        (gov_dir / ".envelope").write_text("exploratory")
        entries = collect_effective_config(gov_dir)
        by_key = {e.key: e for e in entries}
        assert by_key["envelope"].raw_value == "exploratory"
        assert by_key["envelope"].source == ConfigSource.ENVELOPE_FILE

    def test_profile_file_overrides(self, gov_dir):
        (gov_dir / ".profile").write_text("production")
        entries = collect_effective_config(gov_dir)
        by_key = {e.key: e for e in entries}
        assert by_key["profile"].raw_value == "production"
        assert by_key["profile"].source == ConfigSource.PROFILE_FILE
        # Production implies strict envelope
        assert by_key["envelope"].raw_value == "strict"
        assert by_key["envelope"].source == ConfigSource.PROFILE_FILE

    def test_env_var_overrides_config_file(self, gov_dir, monkeypatch):
        conf = gov_dir / "daemon.conf"
        conf.write_text("[backend]\ntype = ollama\n")
        monkeypatch.setenv("BACKEND_TYPE", "anthropic")
        entries = collect_effective_config(gov_dir)
        by_key = {e.key: e for e in entries}
        assert by_key["backend_type"].raw_value == "anthropic"
        assert by_key["backend_type"].source == ConfigSource.ENV

    def test_anthropic_api_key_boolean_presence(self, gov_dir, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-12345")
        entries = collect_effective_config(gov_dir)
        by_key = {e.key: e for e in entries}
        assert by_key["api_key_set"].raw_value is True
        assert by_key["api_key_set"].source == ConfigSource.ENV
        # Verify the actual key never appears in serialized output
        d = by_key["api_key_set"].to_dict()
        assert d["value"] is True
        assert "sk-ant" not in json.dumps(d)

    def test_intent_json_overrides_profile(self, gov_dir):
        (gov_dir / ".profile").write_text("strict")
        (gov_dir / "intent.json").write_text(json.dumps({"profile": "hotfix"}))
        entries = collect_effective_config(gov_dir)
        by_key = {e.key: e for e in entries}
        assert by_key["profile"].raw_value == "hotfix"
        assert by_key["profile"].source == ConfigSource.INTENT

    def test_unknown_keys_in_daemon_conf_ignored(self, gov_dir):
        conf = gov_dir / "daemon.conf"
        conf.write_text("[custom]\nsecret_api_key = sk-12345\n")
        entries = collect_effective_config(gov_dir)
        keys = [e.key for e in entries]
        assert "secret_api_key" not in keys
        assert "custom.secret_api_key" not in keys

    def test_socket_path_always_computed(self, gov_dir):
        entries = collect_effective_config(gov_dir)
        by_key = {e.key: e for e in entries}
        assert by_key["socket_path"].raw_value != ""
        assert "governor-" in by_key["socket_path"].raw_value
