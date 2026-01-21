"""
Operating envelopes: Different modes for different contexts.

Per BUILD_SPEC:
- exploratory: hypotheses allowed, don't commit decisions
- strict: all claims require receipts

Envelopes control how strictly the governor enforces rules.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore


class EnvelopeMode(Enum):
    """Operating envelope modes."""

    EXPLORATORY = "exploratory"
    """Hypotheses allowed. Decisions not committed. Receipts optional."""

    STRICT = "strict"
    """All claims require receipts. Decisions committed. Full enforcement."""


@dataclass
class EnvelopeConfig:
    """Configuration for an operating envelope."""

    mode: EnvelopeMode
    require_receipts: bool
    commit_decisions: bool
    allow_conflicts: bool = False

    @classmethod
    def exploratory(cls) -> "EnvelopeConfig":
        """Create an exploratory envelope configuration."""
        return cls(
            mode=EnvelopeMode.EXPLORATORY,
            require_receipts=False,
            commit_decisions=False,
            allow_conflicts=True,
        )

    @classmethod
    def strict(cls) -> "EnvelopeConfig":
        """Create a strict envelope configuration."""
        return cls(
            mode=EnvelopeMode.STRICT,
            require_receipts=True,
            commit_decisions=True,
            allow_conflicts=False,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "require_receipts": self.require_receipts,
            "commit_decisions": self.commit_decisions,
            "allow_conflicts": self.allow_conflicts,
        }


def load_envelope_config(governor_dir: Path) -> tuple[EnvelopeMode, dict[str, EnvelopeConfig]]:
    """
    Load envelope configuration from config.toml.

    Returns (default_mode, {mode_name: config}).
    """
    config_path = governor_dir / "config.toml"

    if not config_path.exists():
        # Default to strict
        return EnvelopeMode.STRICT, {
            "exploratory": EnvelopeConfig.exploratory(),
            "strict": EnvelopeConfig.strict(),
        }

    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    envelopes_config = config.get("envelopes", {})
    default_mode_str = envelopes_config.get("default", "strict")

    try:
        default_mode = EnvelopeMode(default_mode_str)
    except ValueError:
        default_mode = EnvelopeMode.STRICT

    # Parse envelope definitions
    envelope_configs = {}

    if "exploratory" in envelopes_config:
        exp = envelopes_config["exploratory"]
        envelope_configs["exploratory"] = EnvelopeConfig(
            mode=EnvelopeMode.EXPLORATORY,
            require_receipts=exp.get("require_receipts", False),
            commit_decisions=exp.get("decisions_commit", False),
            allow_conflicts=exp.get("allow_conflicts", True),
        )
    else:
        envelope_configs["exploratory"] = EnvelopeConfig.exploratory()

    if "strict" in envelopes_config:
        strict = envelopes_config["strict"]
        envelope_configs["strict"] = EnvelopeConfig(
            mode=EnvelopeMode.STRICT,
            require_receipts=strict.get("require_receipts", True),
            commit_decisions=strict.get("decisions_commit", True),
            allow_conflicts=strict.get("allow_conflicts", False),
        )
    else:
        envelope_configs["strict"] = EnvelopeConfig.strict()

    return default_mode, envelope_configs


def get_current_envelope(governor_dir: Path) -> EnvelopeConfig:
    """
    Get the current envelope configuration.

    Checks for a .envelope file that overrides the default,
    otherwise uses the default from config.toml.
    """
    envelope_file = governor_dir / ".envelope"
    default_mode, configs = load_envelope_config(governor_dir)

    if envelope_file.exists():
        mode_str = envelope_file.read_text().strip()
        try:
            mode = EnvelopeMode(mode_str)
            return configs.get(mode.value, EnvelopeConfig.strict())
        except ValueError:
            pass

    return configs.get(default_mode.value, EnvelopeConfig.strict())


def set_envelope(governor_dir: Path, mode: EnvelopeMode) -> None:
    """Set the current envelope mode."""
    envelope_file = governor_dir / ".envelope"
    envelope_file.write_text(mode.value)


def clear_envelope(governor_dir: Path) -> None:
    """Clear the envelope override, reverting to default."""
    envelope_file = governor_dir / ".envelope"
    if envelope_file.exists():
        envelope_file.unlink()
