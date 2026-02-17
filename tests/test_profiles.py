# SPDX-License-Identifier: Apache-2.0
"""
Tests for config profiles.

Covers: ProfileSettings, built-in profiles, ProfileManager (list, activate,
deactivate, create, delete), persistence, apply_profile, and edge cases.
"""

import json
import tempfile
from pathlib import Path

import pytest

from governor.profiles import (
    BUILTIN_PROFILES,
    ProfileManager,
    ProfileSettings,
    apply_profile,
    get_profile_manager,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def gov_dir(tmp_path):
    """Create a temporary governor directory."""
    d = tmp_path / ".governor"
    d.mkdir()
    return d


# =============================================================================
# TestProfileSettings
# =============================================================================


class TestProfileSettings:
    """Dataclass creation and serialization."""

    def test_creation(self):
        p = ProfileSettings(
            envelope_mode="strict",
            boil_preset="BLACK_TEA",
            jurisdiction="FACTUAL",
            strict_mode=True,
            description="Test profile",
        )
        assert p.envelope_mode == "strict"
        assert p.boil_preset == "BLACK_TEA"
        assert p.jurisdiction == "FACTUAL"
        assert p.strict_mode is True
        assert p.description == "Test profile"

    def test_to_dict(self):
        p = ProfileSettings(
            envelope_mode="exploratory",
            boil_preset="GREEN_TEA",
            jurisdiction="SPECULATIVE",
            strict_mode=False,
        )
        d = p.to_dict()
        assert d["envelope_mode"] == "exploratory"
        assert d["boil_preset"] == "GREEN_TEA"
        assert d["jurisdiction"] == "SPECULATIVE"
        assert d["strict_mode"] is False
        assert d["description"] == ""

    def test_from_dict(self):
        data = {
            "envelope_mode": "strict",
            "boil_preset": "BOIL",
            "jurisdiction": "FACTUAL",
            "strict_mode": True,
            "description": "Loaded",
        }
        p = ProfileSettings.from_dict(data)
        assert p.envelope_mode == "strict"
        assert p.boil_preset == "BOIL"
        assert p.description == "Loaded"

    def test_from_dict_no_description(self):
        data = {
            "envelope_mode": "strict",
            "boil_preset": "FRENCH_PRESS",
            "jurisdiction": "FACTUAL",
            "strict_mode": True,
        }
        p = ProfileSettings.from_dict(data)
        assert p.description == ""

    def test_roundtrip(self):
        original = ProfileSettings(
            envelope_mode="exploratory",
            boil_preset="OOLONG",
            jurisdiction="ADVERSARIAL",
            strict_mode=False,
            description="Round trip test",
        )
        restored = ProfileSettings.from_dict(original.to_dict())
        assert restored.envelope_mode == original.envelope_mode
        assert restored.boil_preset == original.boil_preset
        assert restored.jurisdiction == original.jurisdiction
        assert restored.strict_mode == original.strict_mode
        assert restored.description == original.description


# =============================================================================
# TestBuiltinProfiles
# =============================================================================


class TestBuiltinProfiles:
    """Verify built-in profile definitions."""

    def test_has_expected_profiles(self):
        assert "strict" in BUILTIN_PROFILES
        assert "permissive" in BUILTIN_PROFILES
        assert "research" in BUILTIN_PROFILES
        assert "production" in BUILTIN_PROFILES
        assert "audit" in BUILTIN_PROFILES
        assert "research_mode" in BUILTIN_PROFILES

    def test_strict_profile(self):
        p = BUILTIN_PROFILES["strict"]
        assert p.envelope_mode == "strict"
        assert p.strict_mode is True
        assert p.jurisdiction == "FACTUAL"

    def test_permissive_profile(self):
        p = BUILTIN_PROFILES["permissive"]
        assert p.envelope_mode == "exploratory"
        assert p.strict_mode is False
        assert p.boil_preset == "GREEN_TEA"

    def test_research_profile(self):
        p = BUILTIN_PROFILES["research"]
        assert p.envelope_mode == "exploratory"
        assert p.strict_mode is False

    def test_production_profile(self):
        p = BUILTIN_PROFILES["production"]
        assert p.envelope_mode == "strict"
        assert p.strict_mode is True
        assert p.boil_preset == "FRENCH_PRESS"

    def test_audit_profile(self):
        p = BUILTIN_PROFILES["audit"]
        assert p.envelope_mode == "strict"
        assert p.boil_preset == "BOIL"
        assert p.strict_mode is True

    def test_all_have_descriptions(self):
        for name, p in BUILTIN_PROFILES.items():
            assert p.description, f"Profile {name} missing description"

    def test_research_mode_profile(self):
        p = BUILTIN_PROFILES["research_mode"]
        assert p.envelope_mode == "exploratory"
        assert p.strict_mode is False
        assert p.boil_preset == "OOLONG"
        assert p.jurisdiction == "SPECULATIVE"

    def test_count(self):
        assert len(BUILTIN_PROFILES) == 6


# =============================================================================
# TestProfileManager
# =============================================================================


class TestProfileManager:
    """Manager: list, get, activate, deactivate, create, delete."""

    def test_init_loads_builtins(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        profiles = mgr.list_profiles()
        assert "strict" in profiles
        assert "permissive" in profiles
        assert len(profiles) >= 5

    def test_get_builtin(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        p = mgr.get("strict")
        assert p is not None
        assert p.envelope_mode == "strict"

    def test_get_nonexistent(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        assert mgr.get("nonexistent") is None

    def test_no_active_initially(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        name, settings = mgr.get_active()
        assert name is None
        assert settings is None

    def test_activate(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        result = mgr.activate("strict")
        assert result.envelope_mode == "strict"
        name, settings = mgr.get_active()
        assert name == "strict"
        assert settings is not None

    def test_activate_nonexistent_raises(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        with pytest.raises(KeyError):
            mgr.activate("nonexistent")

    def test_deactivate(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        mgr.activate("strict")
        mgr.deactivate()
        name, _ = mgr.get_active()
        assert name is None

    def test_activate_persists(self, gov_dir):
        mgr1 = ProfileManager(governor_dir=gov_dir)
        mgr1.activate("research")

        mgr2 = ProfileManager(governor_dir=gov_dir)
        name, _ = mgr2.get_active()
        assert name == "research"

    def test_deactivate_persists(self, gov_dir):
        mgr1 = ProfileManager(governor_dir=gov_dir)
        mgr1.activate("strict")
        mgr1.deactivate()

        mgr2 = ProfileManager(governor_dir=gov_dir)
        name, _ = mgr2.get_active()
        assert name is None

    def test_is_builtin(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        assert mgr.is_builtin("strict") is True
        assert mgr.is_builtin("custom") is False


# =============================================================================
# TestCustomProfiles
# =============================================================================


class TestCustomProfiles:
    """Create, delete, persist custom profiles."""

    def test_create_custom(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        mgr.create("my_profile", ProfileSettings(
            envelope_mode="exploratory",
            boil_preset="OOLONG",
            jurisdiction="SPECULATIVE",
            strict_mode=False,
            description="My custom profile",
        ))
        p = mgr.get("my_profile")
        assert p is not None
        assert p.description == "My custom profile"

    def test_create_overwrites_builtin_raises(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        with pytest.raises(ValueError):
            mgr.create("strict", ProfileSettings(
                envelope_mode="exploratory",
                boil_preset="GREEN_TEA",
                jurisdiction="SPECULATIVE",
                strict_mode=False,
            ))

    def test_custom_persists(self, gov_dir):
        mgr1 = ProfileManager(governor_dir=gov_dir)
        mgr1.create("persisted", ProfileSettings(
            envelope_mode="strict",
            boil_preset="FRENCH_PRESS",
            jurisdiction="FACTUAL",
            strict_mode=True,
            description="Should persist",
        ))

        mgr2 = ProfileManager(governor_dir=gov_dir)
        p = mgr2.get("persisted")
        assert p is not None
        assert p.description == "Should persist"

    def test_delete_custom(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        mgr.create("deleteme", ProfileSettings(
            envelope_mode="exploratory",
            boil_preset="GREEN_TEA",
            jurisdiction="SPECULATIVE",
            strict_mode=False,
        ))
        assert mgr.get("deleteme") is not None
        mgr.delete("deleteme")
        assert mgr.get("deleteme") is None

    def test_delete_builtin_raises(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        with pytest.raises(ValueError):
            mgr.delete("strict")

    def test_delete_nonexistent_raises(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        with pytest.raises(KeyError):
            mgr.delete("nonexistent")

    def test_delete_active_deactivates(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        mgr.create("temp", ProfileSettings(
            envelope_mode="exploratory",
            boil_preset="GREEN_TEA",
            jurisdiction="SPECULATIVE",
            strict_mode=False,
        ))
        mgr.activate("temp")
        name, _ = mgr.get_active()
        assert name == "temp"

        mgr.delete("temp")
        name, _ = mgr.get_active()
        assert name is None

    def test_multiple_custom(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        mgr.create("a", ProfileSettings(
            envelope_mode="strict", boil_preset="BOIL",
            jurisdiction="FACTUAL", strict_mode=True,
        ))
        mgr.create("b", ProfileSettings(
            envelope_mode="exploratory", boil_preset="GREEN_TEA",
            jurisdiction="SPECULATIVE", strict_mode=False,
        ))
        profiles = mgr.list_profiles()
        assert "a" in profiles
        assert "b" in profiles
        assert len(profiles) == 8  # 6 builtin + 2 custom


# =============================================================================
# TestApplyProfile
# =============================================================================


class TestApplyProfile:
    """Applying profiles writes state files."""

    def test_apply_strict(self, gov_dir):
        settings = BUILTIN_PROFILES["strict"]
        applied = apply_profile(gov_dir, settings)
        assert applied["envelope"] == "strict"
        assert applied["boil"] == "BLACK_TEA"
        assert applied["jurisdiction"] == "FACTUAL"
        assert applied["strict_mode"] == "enabled"

    def test_apply_permissive(self, gov_dir):
        settings = BUILTIN_PROFILES["permissive"]
        applied = apply_profile(gov_dir, settings)
        assert applied["envelope"] == "exploratory"
        assert applied["strict_mode"] == "disabled"

    def test_writes_envelope_file(self, gov_dir):
        apply_profile(gov_dir, BUILTIN_PROFILES["strict"])
        assert (gov_dir / ".envelope").read_text() == "strict"

    def test_writes_boil_file(self, gov_dir):
        apply_profile(gov_dir, BUILTIN_PROFILES["audit"])
        assert (gov_dir / ".boil_mode").read_text() == "BOIL"

    def test_writes_jurisdiction_file(self, gov_dir):
        apply_profile(gov_dir, BUILTIN_PROFILES["permissive"])
        assert (gov_dir / ".jurisdiction").read_text() == "SPECULATIVE"

    def test_writes_strict_mode_file(self, gov_dir):
        apply_profile(gov_dir, BUILTIN_PROFILES["production"])
        assert (gov_dir / ".strict_mode").read_text() == "enabled"

    def test_apply_overwrites(self, gov_dir):
        apply_profile(gov_dir, BUILTIN_PROFILES["strict"])
        assert (gov_dir / ".envelope").read_text() == "strict"

        apply_profile(gov_dir, BUILTIN_PROFILES["permissive"])
        assert (gov_dir / ".envelope").read_text() == "exploratory"


# =============================================================================
# TestGetProfileManager
# =============================================================================


class TestGetProfileManager:
    """Convenience constructor."""

    def test_returns_manager(self, gov_dir):
        mgr = get_profile_manager(gov_dir)
        assert isinstance(mgr, ProfileManager)
        assert len(mgr.list_profiles()) >= 5

    def test_respects_existing_state(self, gov_dir):
        mgr1 = get_profile_manager(gov_dir)
        mgr1.activate("audit")

        mgr2 = get_profile_manager(gov_dir)
        name, _ = mgr2.get_active()
        assert name == "audit"


# =============================================================================
# TestEdgeCases
# =============================================================================


class TestEdgeCases:
    """Boundary conditions and error paths."""

    def test_active_profile_file_with_invalid_name(self, gov_dir):
        (gov_dir / ".profile").write_text("nonexistent_profile")
        mgr = ProfileManager(governor_dir=gov_dir)
        name, _ = mgr.get_active()
        assert name is None  # Invalid profile ignored

    def test_corrupt_profiles_json(self, gov_dir):
        (gov_dir / "profiles.json").write_text("not valid json{{{")
        # Should raise on load
        with pytest.raises(json.JSONDecodeError):
            ProfileManager(governor_dir=gov_dir)

    def test_empty_profiles_json(self, gov_dir):
        (gov_dir / "profiles.json").write_text("{}")
        mgr = ProfileManager(governor_dir=gov_dir)
        # Should still have builtins
        assert len(mgr.list_profiles()) == 6

    def test_switch_between_profiles(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)

        mgr.activate("strict")
        name, s = mgr.get_active()
        assert name == "strict"
        assert s.strict_mode is True

        mgr.activate("permissive")
        name, s = mgr.get_active()
        assert name == "permissive"
        assert s.strict_mode is False

    def test_apply_custom_profile(self, gov_dir):
        mgr = ProfileManager(governor_dir=gov_dir)
        custom = ProfileSettings(
            envelope_mode="exploratory",
            boil_preset="OOLONG",
            jurisdiction="ADVERSARIAL",
            strict_mode=False,
            description="Custom adversarial",
        )
        mgr.create("adversarial", custom)
        applied = apply_profile(gov_dir, custom)
        assert applied["jurisdiction"] == "ADVERSARIAL"
        assert applied["envelope"] == "exploratory"
