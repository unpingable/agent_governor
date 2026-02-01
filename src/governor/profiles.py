"""
Config profiles: Named governance presets that bundle envelope, boil, jurisdiction, and strict settings.

Profiles provide a single command to switch between governance postures:
  governor profile use strict
  governor profile use permissive
  governor profile use research

Each profile sets:
- Envelope mode (strict/exploratory)
- Boil preset (GREEN_TEA → BOIL)
- Jurisdiction (FACTUAL, SPECULATIVE, etc.)
- Strict mode (on/off)

Built-in profiles:
- STRICT: Full enforcement, fail-closed, factual jurisdiction
- PERMISSIVE: Exploratory mode, low heat, speculative allowed
- RESEARCH: Exploratory mode, medium heat, wide jurisdiction budget
- PRODUCTION: Strict mode, high heat, tight blast radius
- AUDIT: Strict mode with boil at max, factual only
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProfileSettings:
    """Bundled governance settings for a named profile."""

    envelope_mode: str  # "strict" or "exploratory"
    boil_preset: str  # GREEN_TEA, WHITE_TEA, OOLONG, BLACK_TEA, FRENCH_PRESS, BOIL
    jurisdiction: str  # FACTUAL, SPECULATIVE, ADVERSARIAL, etc.
    strict_mode: bool  # Whether strict programmer mode gate is active
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_mode": self.envelope_mode,
            "boil_preset": self.boil_preset,
            "jurisdiction": self.jurisdiction,
            "strict_mode": self.strict_mode,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProfileSettings":
        return cls(
            envelope_mode=data["envelope_mode"],
            boil_preset=data["boil_preset"],
            jurisdiction=data["jurisdiction"],
            strict_mode=data["strict_mode"],
            description=data.get("description", ""),
        )


# =============================================================================
# Built-in Profiles
# =============================================================================

BUILTIN_PROFILES: dict[str, ProfileSettings] = {
    "strict": ProfileSettings(
        envelope_mode="strict",
        boil_preset="BLACK_TEA",
        jurisdiction="FACTUAL",
        strict_mode=True,
        description="Full enforcement, fail-closed, factual jurisdiction.",
    ),
    "permissive": ProfileSettings(
        envelope_mode="exploratory",
        boil_preset="GREEN_TEA",
        jurisdiction="SPECULATIVE",
        strict_mode=False,
        description="Exploratory mode, low heat, speculative allowed.",
    ),
    "research": ProfileSettings(
        envelope_mode="exploratory",
        boil_preset="OOLONG",
        jurisdiction="SPECULATIVE",
        strict_mode=False,
        description="Exploratory mode, medium heat, wide budget for investigation.",
    ),
    "production": ProfileSettings(
        envelope_mode="strict",
        boil_preset="FRENCH_PRESS",
        jurisdiction="FACTUAL",
        strict_mode=True,
        description="Production deployment: strict mode, high heat, tight controls.",
    ),
    "audit": ProfileSettings(
        envelope_mode="strict",
        boil_preset="BOIL",
        jurisdiction="FACTUAL",
        strict_mode=True,
        description="Maximum enforcement for audit/compliance review.",
    ),
    "research_mode": ProfileSettings(
        envelope_mode="exploratory",
        boil_preset="OOLONG",
        jurisdiction="SPECULATIVE",
        strict_mode=False,
        description="Non-convergent epistemic control: hypothesis lifecycle, "
                    "entropy bounds, dominance caps, evidence impulses with decay.",
    ),
}


# =============================================================================
# Profile Manager
# =============================================================================

PROFILES_FILE = "profiles.json"
ACTIVE_PROFILE_FILE = ".profile"


@dataclass
class ProfileManager:
    """Manages governance profiles: list, activate, create custom."""

    governor_dir: Path
    profiles: dict[str, ProfileSettings] = field(default_factory=dict)
    active_profile: str | None = None

    def __post_init__(self):
        # Start with builtins
        self.profiles = dict(BUILTIN_PROFILES)
        # Load custom profiles on top
        self._load_custom()
        # Load active profile
        self._load_active()

    def _load_custom(self) -> None:
        """Load custom profiles from disk."""
        path = self.governor_dir / PROFILES_FILE
        if path.exists():
            data = json.loads(path.read_text())
            for name, pdata in data.items():
                self.profiles[name] = ProfileSettings.from_dict(pdata)

    def _save_custom(self) -> None:
        """Save custom (non-builtin) profiles to disk."""
        custom = {
            name: p.to_dict()
            for name, p in self.profiles.items()
            if name not in BUILTIN_PROFILES
        }
        path = self.governor_dir / PROFILES_FILE
        path.write_text(json.dumps(custom, indent=2))

    def _load_active(self) -> None:
        """Load active profile name from disk."""
        path = self.governor_dir / ACTIVE_PROFILE_FILE
        if path.exists():
            name = path.read_text().strip()
            if name in self.profiles:
                self.active_profile = name

    def _save_active(self) -> None:
        """Save active profile name to disk."""
        path = self.governor_dir / ACTIVE_PROFILE_FILE
        if self.active_profile:
            path.write_text(self.active_profile)
        elif path.exists():
            path.unlink()

    def list_profiles(self) -> dict[str, ProfileSettings]:
        """Return all available profiles."""
        return dict(self.profiles)

    def get(self, name: str) -> ProfileSettings | None:
        """Get a profile by name."""
        return self.profiles.get(name)

    def get_active(self) -> tuple[str | None, ProfileSettings | None]:
        """Get the active profile name and settings."""
        if self.active_profile and self.active_profile in self.profiles:
            return self.active_profile, self.profiles[self.active_profile]
        return None, None

    def activate(self, name: str) -> ProfileSettings:
        """
        Activate a profile. Returns the profile settings.

        Raises KeyError if profile doesn't exist.
        """
        if name not in self.profiles:
            raise KeyError(f"Profile not found: {name}")
        self.active_profile = name
        self._save_active()
        return self.profiles[name]

    def deactivate(self) -> None:
        """Deactivate the current profile."""
        self.active_profile = None
        self._save_active()

    def create(self, name: str, settings: ProfileSettings) -> None:
        """
        Create a custom profile.

        Raises ValueError if name conflicts with a builtin.
        """
        if name in BUILTIN_PROFILES:
            raise ValueError(f"Cannot overwrite builtin profile: {name}")
        self.profiles[name] = settings
        self._save_custom()

    def delete(self, name: str) -> None:
        """
        Delete a custom profile.

        Raises ValueError if trying to delete a builtin.
        Raises KeyError if profile doesn't exist.
        """
        if name in BUILTIN_PROFILES:
            raise ValueError(f"Cannot delete builtin profile: {name}")
        if name not in self.profiles:
            raise KeyError(f"Profile not found: {name}")
        del self.profiles[name]
        if self.active_profile == name:
            self.active_profile = None
            self._save_active()
        self._save_custom()

    def is_builtin(self, name: str) -> bool:
        """Check if a profile is builtin."""
        return name in BUILTIN_PROFILES


def apply_profile(governor_dir: Path, settings: ProfileSettings) -> dict[str, str]:
    """
    Apply profile settings to the governor directory.

    Writes envelope, boil, jurisdiction, and strict mode state files.
    Returns a dict of what was applied.
    """
    applied: dict[str, str] = {}

    # Envelope
    envelope_file = governor_dir / ".envelope"
    envelope_file.write_text(settings.envelope_mode)
    applied["envelope"] = settings.envelope_mode

    # Boil preset
    boil_file = governor_dir / ".boil_mode"
    boil_file.write_text(settings.boil_preset)
    applied["boil"] = settings.boil_preset

    # Jurisdiction
    jurisdiction_file = governor_dir / ".jurisdiction"
    jurisdiction_file.write_text(settings.jurisdiction)
    applied["jurisdiction"] = settings.jurisdiction

    # Strict mode
    strict_file = governor_dir / ".strict_mode"
    strict_file.write_text("enabled" if settings.strict_mode else "disabled")
    applied["strict_mode"] = "enabled" if settings.strict_mode else "disabled"

    return applied


def get_profile_manager(governor_dir: Path) -> ProfileManager:
    """Create a ProfileManager for the given governor directory."""
    return ProfileManager(governor_dir=governor_dir)
