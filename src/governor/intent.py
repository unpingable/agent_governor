# SPDX-License-Identifier: Apache-2.0
"""
Intent resource for Code Autopilot.

Intent is a first-class resource, not a flag. All interfaces (CLI, VS Code, MCP, CI)
read/write the same canonical object. This enables unified intent control across
the entire Governor surface.

Storage: .git/governor/intent.json (local, not committed, survives branch switches)

Resolution precedence (highest to lowest):
1. CLI override (--profile hotfix --scope "src/**")
2. Environment variable (GOV_PROFILE=hotfix)
3. Session state (.git/governor/intent.json)
4. Repo config (.governor.toml [defaults])
5. Branch heuristic (suggestion only for high-risk branches)
6. System default (established)

Core doctrine: Constraints are the product. Profile is the UX dial, not an escape hatch.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =============================================================================
# Constants
# =============================================================================

INTENT_FILE = "intent.json"
DEFAULT_PROFILE = "established"

# Branch patterns for heuristic suggestions
# Format: (pattern, suggested_profile, auto_apply)
# auto_apply=True only for low-risk branches
BRANCH_HEURISTICS: list[tuple[str, str, bool]] = [
    # High-risk: suggest but never auto-apply
    ("main", "production", False),
    ("master", "production", False),
    ("release/*", "production", False),
    ("hotfix/*", "hotfix", False),
    ("fix/*", "hotfix", False),
    # Medium-risk: safe to auto-apply
    ("feature/*", "established", True),
    ("refactor/*", "refactor", True),
    # Low-risk: explicitly experimental
    ("wip/*", "greenfield", True),
    ("experiment/*", "greenfield", True),
    ("spike/*", "greenfield", True),
]


# =============================================================================
# Intent Dataclass
# =============================================================================


@dataclass
class Intent:
    """
    Session intent for Code Autopilot.

    Represents what the user is trying to accomplish, which controls Governor
    behavior across all interfaces.
    """

    profile: str                        # greenfield|established|production|hotfix|refactor
    scope: list[str] | None = None      # glob patterns for allowed paths
    deny: list[str] | None = None       # glob patterns for forbidden paths
    timebox_minutes: int | None = None  # auto-expire duration
    reason: str | None = None           # why this intent was set
    operator: str = ""                  # who set it
    source: str = "default"             # cli|vscode|mcp|ci|env|config|heuristic|default
    set_at: str = ""                    # ISO datetime
    expires_at: str | None = None       # ISO datetime

    def __post_init__(self):
        if not self.set_at:
            self.set_at = datetime.now(timezone.utc).isoformat()
        if not self.operator:
            self.operator = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

    @property
    def is_expired(self) -> bool:
        """Check if this intent has expired."""
        if self.expires_at is None:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expires
        except (ValueError, TypeError):
            return False

    @property
    def remaining_minutes(self) -> int | None:
        """Get remaining minutes in timebox, or None if no timebox."""
        if self.expires_at is None:
            return None
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            delta = expires - datetime.now(timezone.utc)
            if delta.total_seconds() <= 0:
                return 0
            return int(delta.total_seconds() / 60)
        except (ValueError, TypeError):
            return None

    def path_allowed(self, path: str) -> bool:
        """Check if a path is allowed by this intent's scope/deny rules."""
        # If deny patterns set, check those first
        if self.deny:
            for pattern in self.deny:
                if fnmatch.fnmatch(path, pattern):
                    return False

        # If scope patterns set, path must match at least one
        if self.scope:
            for pattern in self.scope:
                if fnmatch.fnmatch(path, pattern):
                    return True
            return False

        # No scope means all paths allowed (subject to deny)
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "scope": self.scope,
            "deny": self.deny,
            "timebox_minutes": self.timebox_minutes,
            "reason": self.reason,
            "operator": self.operator,
            "source": self.source,
            "set_at": self.set_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Intent:
        return cls(
            profile=data.get("profile", DEFAULT_PROFILE),
            scope=data.get("scope"),
            deny=data.get("deny"),
            timebox_minutes=data.get("timebox_minutes"),
            reason=data.get("reason"),
            operator=data.get("operator", ""),
            source=data.get("source", "default"),
            set_at=data.get("set_at", ""),
            expires_at=data.get("expires_at"),
        )

    def to_status_string(self) -> str:
        """Format for status display: profile | scope | timebox."""
        parts = [self.profile]

        if self.scope:
            if len(self.scope) == 1:
                parts.append(self.scope[0])
            else:
                parts.append(f"{len(self.scope)} scopes")

        remaining = self.remaining_minutes
        if remaining is not None:
            if remaining <= 0:
                parts.append("EXPIRED")
            elif remaining < 60:
                parts.append(f"{remaining}m")
            else:
                hours = remaining // 60
                mins = remaining % 60
                if mins:
                    parts.append(f"{hours}h{mins}m")
                else:
                    parts.append(f"{hours}h")

        return " | ".join(parts)


# =============================================================================
# Intent Provenance
# =============================================================================


@dataclass
class IntentProvenance:
    """
    Shows how intent was resolved.

    Used for audit trail and debugging intent resolution.
    """

    layer: str                     # cli|env|session|config|heuristic|default
    source_path: str | None = None # file path if applicable
    value: Intent | None = None    # the intent found at this layer (if any)
    checked: bool = True           # whether this layer was checked
    reason: str = ""               # why this layer was used/skipped

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "source_path": self.source_path,
            "value": self.value.to_dict() if self.value else None,
            "checked": self.checked,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IntentProvenance:
        value = None
        if data.get("value"):
            value = Intent.from_dict(data["value"])
        return cls(
            layer=data["layer"],
            source_path=data.get("source_path"),
            value=value,
            checked=data.get("checked", True),
            reason=data.get("reason", ""),
        )


# =============================================================================
# Branch Heuristics
# =============================================================================


def get_current_branch() -> str | None:
    """Get the current git branch name, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def suggest_profile_for_branch(branch: str | None) -> tuple[str, bool, bool]:
    """
    Suggest a profile based on branch name.

    Returns:
        (suggested_profile, should_auto_apply, is_high_risk)

    is_high_risk=True means the branch is production-like and auto-apply is forbidden.
    """
    if not branch:
        return DEFAULT_PROFILE, False, False

    for pattern, profile, auto_apply in BRANCH_HEURISTICS:
        if fnmatch.fnmatch(branch, pattern):
            is_high_risk = not auto_apply
            return profile, auto_apply, is_high_risk

    # No match: default to established, no auto-apply
    return DEFAULT_PROFILE, False, False


# =============================================================================
# Intent Storage
# =============================================================================


def _get_intent_path(gov_dir: Path) -> Path:
    """Get path to intent storage file."""
    # Store in .git/governor/ if it exists, otherwise .governor/
    git_governor = gov_dir.parent / ".git" / "governor"
    if git_governor.parent.exists():
        git_governor.mkdir(parents=True, exist_ok=True)
        return git_governor / INTENT_FILE
    return gov_dir / INTENT_FILE


def get_intent(gov_dir: Path) -> Intent | None:
    """
    Get current session intent from storage.

    Returns None if no intent is set or if the intent has expired.
    """
    path = _get_intent_path(gov_dir)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        intent = Intent.from_dict(data)

        # Check expiry
        if intent.is_expired:
            # Clear expired intent
            path.unlink()
            return None

        return intent
    except (json.JSONDecodeError, KeyError):
        return None


def set_intent(gov_dir: Path, intent: Intent) -> None:
    """
    Set session intent.

    Writes to storage file. If timebox_minutes is set, calculates expires_at.
    """
    # Calculate expiry if timebox set but no expires_at
    if intent.timebox_minutes and not intent.expires_at:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=intent.timebox_minutes)
        intent.expires_at = expires.isoformat()

    path = _get_intent_path(gov_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(intent.to_dict(), indent=2))


def clear_intent(gov_dir: Path) -> bool:
    """
    Clear session intent.

    Returns True if intent was cleared, False if no intent existed.
    """
    path = _get_intent_path(gov_dir)
    if path.exists():
        path.unlink()
        return True
    return False


# =============================================================================
# Intent Resolution
# =============================================================================


def _load_config_default(gov_dir: Path) -> Intent | None:
    """Load default profile from .governor.toml or config.json."""
    # Try .governor.toml first
    toml_path = gov_dir.parent / ".governor.toml"
    if toml_path.exists():
        try:
            # Simple TOML parsing for [defaults] section
            content = toml_path.read_text()
            in_defaults = False
            for line in content.split("\n"):
                line = line.strip()
                if line == "[defaults]":
                    in_defaults = True
                elif line.startswith("["):
                    in_defaults = False
                elif in_defaults and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key == "profile":
                        return Intent(
                            profile=value,
                            source="config",
                        )
        except Exception:
            pass

    # Try config.json
    config_path = gov_dir / "config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            if "default_profile" in data:
                return Intent(
                    profile=data["default_profile"],
                    source="config",
                )
        except (json.JSONDecodeError, KeyError):
            pass

    return None


def resolve_intent(
    gov_dir: Path,
    cli_overrides: dict[str, Any] | None = None,
) -> tuple[Intent, list[IntentProvenance]]:
    """
    Resolve effective intent from all layers.

    Resolution precedence (highest to lowest):
    1. CLI override (passed in cli_overrides)
    2. Environment variable (GOV_PROFILE)
    3. Session state (.git/governor/intent.json)
    4. Repo config (.governor.toml or config.json)
    5. Branch heuristic (auto-apply only for low-risk)
    6. System default (established)

    Returns:
        (resolved_intent, provenance_chain)
    """
    provenance: list[IntentProvenance] = []

    # Layer 1: CLI overrides
    if cli_overrides and cli_overrides.get("profile"):
        intent = Intent(
            profile=cli_overrides["profile"],
            scope=cli_overrides.get("scope"),
            deny=cli_overrides.get("deny"),
            timebox_minutes=cli_overrides.get("timebox_minutes"),
            reason=cli_overrides.get("reason"),
            source="cli",
        )
        provenance.append(IntentProvenance(
            layer="cli",
            value=intent,
            reason="Profile specified via CLI",
        ))
        return intent, provenance

    provenance.append(IntentProvenance(
        layer="cli",
        checked=True,
        reason="No CLI override",
    ))

    # Layer 2: Environment variable
    env_profile = os.environ.get("GOV_PROFILE")
    if env_profile:
        intent = Intent(
            profile=env_profile,
            source="env",
        )
        provenance.append(IntentProvenance(
            layer="env",
            value=intent,
            reason="GOV_PROFILE environment variable",
        ))
        return intent, provenance

    provenance.append(IntentProvenance(
        layer="env",
        checked=True,
        reason="GOV_PROFILE not set",
    ))

    # Layer 3: Session state
    session_intent = get_intent(gov_dir)
    if session_intent:
        provenance.append(IntentProvenance(
            layer="session",
            source_path=str(_get_intent_path(gov_dir)),
            value=session_intent,
            reason="Session intent file",
        ))
        return session_intent, provenance

    provenance.append(IntentProvenance(
        layer="session",
        source_path=str(_get_intent_path(gov_dir)),
        checked=True,
        reason="No session intent set",
    ))

    # Layer 4: Repo config
    config_intent = _load_config_default(gov_dir)
    if config_intent:
        provenance.append(IntentProvenance(
            layer="config",
            source_path=str(gov_dir.parent / ".governor.toml"),
            value=config_intent,
            reason="Repository default profile",
        ))
        return config_intent, provenance

    provenance.append(IntentProvenance(
        layer="config",
        checked=True,
        reason="No repository default configured",
    ))

    # Layer 5: Branch heuristic
    branch = get_current_branch()
    if branch:
        suggested, auto_apply, is_high_risk = suggest_profile_for_branch(branch)
        if auto_apply:
            intent = Intent(
                profile=suggested,
                source="heuristic",
                reason=f"Auto-applied from branch '{branch}'",
            )
            provenance.append(IntentProvenance(
                layer="heuristic",
                value=intent,
                reason=f"Branch '{branch}' -> {suggested} (auto-applied)",
            ))
            return intent, provenance
        else:
            # High-risk: suggest but don't apply
            provenance.append(IntentProvenance(
                layer="heuristic",
                checked=True,
                reason=f"Branch '{branch}' suggests {suggested} (not auto-applied, is_high_risk={is_high_risk})",
            ))
    else:
        provenance.append(IntentProvenance(
            layer="heuristic",
            checked=True,
            reason="Not in git repository or cannot determine branch",
        ))

    # Layer 6: System default
    intent = Intent(
        profile=DEFAULT_PROFILE,
        source="default",
    )
    provenance.append(IntentProvenance(
        layer="default",
        value=intent,
        reason=f"System default: {DEFAULT_PROFILE}",
    ))

    return intent, provenance


def format_provenance(provenance: list[IntentProvenance]) -> str:
    """Format provenance chain for human display."""
    lines = ["Intent resolution:"]
    for p in provenance:
        if p.value:
            lines.append(f"  [{p.layer}] -> {p.value.profile} ({p.reason})")
        else:
            lines.append(f"  [{p.layer}] (skipped: {p.reason})")
    return "\n".join(lines)
