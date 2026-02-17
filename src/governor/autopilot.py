# SPDX-License-Identifier: Apache-2.0
"""
Code Autopilot profile configuration.

ProfileConfig extends the existing profile system with autopilot-specific settings.
Each profile controls multiple Governor subsystems:
- Enforcement: violation handling, retry budgets
- Evidence: what proof is required before approval
- Scope: path restrictions and change limits
- Anchor behavior: how strictly constraints are enforced
- Approval path: auto, prompt, or require human
- Governor subsystems: boil level, exploration budget, staleness threshold

Built-in profiles:
- greenfield: New project, experimenting (permissive)
- established: Existing patterns, steady work (default)
- production: High stakes, shipping (strict)
- hotfix: Emergency fix, time-boxed, scope-fenced
- refactor: Intentional pattern changes

Core doctrine: Constraints are the product. Profile is the UX dial, not an escape hatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class ViolationDefault(str, Enum):
    """Default action for violations under this profile."""

    IGNORE = "ignore"    # Log but allow
    WARN = "warn"        # Warn user but allow
    BLOCK = "block"      # Block the operation


class ApprovalPath(str, Enum):
    """How changes get approved under this profile."""

    AUTO = "auto"                 # Auto-approve if constraints pass
    PROMPT = "prompt"             # Prompt user for approval
    REQUIRE_HUMAN = "require_human"  # Require explicit human approval


class EvidenceRequired(str, Enum):
    """What evidence is required before approval."""

    NONE = "none"                          # No evidence required
    TESTS = "tests"                        # Tests must pass
    TESTS_STATIC = "tests+static"          # Tests + static analysis
    TESTS_STATIC_REVIEW = "tests+static+review"  # Full evidence chain


class AnchorStrictness(str, Enum):
    """How strictly anchors are enforced."""

    SOFT = "soft"   # Violations warn
    HARD = "hard"   # Violations block


class ScopeEnforcement(str, Enum):
    """How scope restrictions are enforced."""

    OFF = "off"     # No scope enforcement
    WARN = "warn"   # Warn on out-of-scope
    BLOCK = "block" # Block out-of-scope


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class ChangeLimit:
    """Limits on change size for this profile."""

    max_files: int | None = None    # Maximum files per change
    max_loc: int | None = None      # Maximum lines of code
    max_modules: int | None = None  # Maximum modules touched

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_files": self.max_files,
            "max_loc": self.max_loc,
            "max_modules": self.max_modules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChangeLimit:
        return cls(
            max_files=data.get("max_files"),
            max_loc=data.get("max_loc"),
            max_modules=data.get("max_modules"),
        )

    def exceeds(self, files: int = 0, loc: int = 0, modules: int = 0) -> tuple[bool, str | None]:
        """
        Check if change exceeds limits.

        Returns (exceeded, reason) where reason explains which limit was hit.
        """
        if self.max_files is not None and files > self.max_files:
            return True, f"Exceeds max_files ({files} > {self.max_files})"
        if self.max_loc is not None and loc > self.max_loc:
            return True, f"Exceeds max_loc ({loc} > {self.max_loc})"
        if self.max_modules is not None and modules > self.max_modules:
            return True, f"Exceeds max_modules ({modules} > {self.max_modules})"
        return False, None


@dataclass
class ProfileConfig:
    """
    Extended profile configuration for Code Autopilot.

    Controls how the Governor behaves for different scenarios:
    greenfield, established, production, hotfix, refactor.
    """

    name: str
    description: str

    # Enforcement
    violation_default: ViolationDefault
    retry_budget: int                      # 0/1/3 attempts before hard fail

    # Evidence requirements
    evidence_required: EvidenceRequired

    # Scope
    scope_enforcement: ScopeEnforcement
    change_ceiling: ChangeLimit | None = None

    # Anchor behavior
    anchor_strictness: AnchorStrictness = AnchorStrictness.SOFT

    # Approval path
    approval_path: ApprovalPath = ApprovalPath.AUTO

    # Governor subsystems
    boil_level: str = "OOLONG"             # GREEN_TEA, WHITE_TEA, OOLONG, BLACK_TEA, FRENCH_PRESS, BOIL
    exploration_budget: float = 0.5        # 0.0-1.0
    staleness_threshold_hours: int = 168   # 7 days default

    # Hotfix-specific: different handling in-scope vs out-of-scope
    violation_in_scope: ViolationDefault | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "violation_default": self.violation_default.value,
            "retry_budget": self.retry_budget,
            "evidence_required": self.evidence_required.value,
            "scope_enforcement": self.scope_enforcement.value,
            "change_ceiling": self.change_ceiling.to_dict() if self.change_ceiling else None,
            "anchor_strictness": self.anchor_strictness.value,
            "approval_path": self.approval_path.value,
            "boil_level": self.boil_level,
            "exploration_budget": self.exploration_budget,
            "staleness_threshold_hours": self.staleness_threshold_hours,
            "violation_in_scope": self.violation_in_scope.value if self.violation_in_scope else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProfileConfig:
        change_ceiling = None
        if data.get("change_ceiling"):
            change_ceiling = ChangeLimit.from_dict(data["change_ceiling"])

        violation_in_scope = None
        if data.get("violation_in_scope"):
            violation_in_scope = ViolationDefault(data["violation_in_scope"])

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            violation_default=ViolationDefault(data.get("violation_default", "warn")),
            retry_budget=data.get("retry_budget", 3),
            evidence_required=EvidenceRequired(data.get("evidence_required", "none")),
            scope_enforcement=ScopeEnforcement(data.get("scope_enforcement", "off")),
            change_ceiling=change_ceiling,
            anchor_strictness=AnchorStrictness(data.get("anchor_strictness", "soft")),
            approval_path=ApprovalPath(data.get("approval_path", "auto")),
            boil_level=data.get("boil_level", "OOLONG"),
            exploration_budget=data.get("exploration_budget", 0.5),
            staleness_threshold_hours=data.get("staleness_threshold_hours", 168),
            violation_in_scope=violation_in_scope,
        )


# =============================================================================
# Built-in Profiles
# =============================================================================


AUTOPILOT_PROFILES: dict[str, ProfileConfig] = {
    "greenfield": ProfileConfig(
        name="greenfield",
        description="New project, experimenting, learning patterns",
        violation_default=ViolationDefault.WARN,
        retry_budget=3,
        evidence_required=EvidenceRequired.NONE,
        scope_enforcement=ScopeEnforcement.OFF,
        change_ceiling=None,
        anchor_strictness=AnchorStrictness.SOFT,
        approval_path=ApprovalPath.AUTO,
        boil_level="GREEN_TEA",
        exploration_budget=0.8,
        staleness_threshold_hours=168,  # 7 days
    ),
    "established": ProfileConfig(
        name="established",
        description="Existing patterns, steady work",
        violation_default=ViolationDefault.BLOCK,
        retry_budget=3,
        evidence_required=EvidenceRequired.TESTS,
        scope_enforcement=ScopeEnforcement.WARN,
        change_ceiling=None,
        anchor_strictness=AnchorStrictness.SOFT,
        approval_path=ApprovalPath.PROMPT,
        boil_level="OOLONG",
        exploration_budget=0.5,
        staleness_threshold_hours=72,  # 3 days
    ),
    "production": ProfileConfig(
        name="production",
        description="High stakes, shipping to users",
        violation_default=ViolationDefault.BLOCK,
        retry_budget=1,
        evidence_required=EvidenceRequired.TESTS_STATIC_REVIEW,
        scope_enforcement=ScopeEnforcement.BLOCK,
        change_ceiling=ChangeLimit(max_files=20, max_loc=500),
        anchor_strictness=AnchorStrictness.HARD,
        approval_path=ApprovalPath.REQUIRE_HUMAN,
        boil_level="DARJEELING",
        exploration_budget=0.1,
        staleness_threshold_hours=24,  # 1 day
    ),
    "hotfix": ProfileConfig(
        name="hotfix",
        description="Emergency fix, time-boxed, scope-fenced",
        violation_default=ViolationDefault.BLOCK,      # Outside scope
        violation_in_scope=ViolationDefault.WARN,      # Inside scope
        retry_budget=1,
        evidence_required=EvidenceRequired.TESTS,
        scope_enforcement=ScopeEnforcement.BLOCK,
        change_ceiling=ChangeLimit(max_files=5, max_loc=100),
        anchor_strictness=AnchorStrictness.HARD,
        approval_path=ApprovalPath.PROMPT,
        boil_level="BOIL",
        exploration_budget=0.0,
        staleness_threshold_hours=1,
    ),
    "refactor": ProfileConfig(
        name="refactor",
        description="Intentional pattern changes, drift expected",
        violation_default=ViolationDefault.WARN,
        retry_budget=3,
        evidence_required=EvidenceRequired.TESTS_STATIC,
        scope_enforcement=ScopeEnforcement.WARN,
        change_ceiling=None,
        anchor_strictness=AnchorStrictness.SOFT,
        approval_path=ApprovalPath.PROMPT,
        boil_level="OOLONG",
        exploration_budget=0.6,
        staleness_threshold_hours=48,  # 2 days
    ),
}


# =============================================================================
# Profile Functions
# =============================================================================


def get_autopilot_profile(name: str) -> ProfileConfig | None:
    """
    Get an autopilot profile by name.

    Checks built-in profiles first, then custom profiles in .governor/autopilot_profiles.json.
    """
    return AUTOPILOT_PROFILES.get(name)


def list_autopilot_profiles() -> dict[str, ProfileConfig]:
    """List all available autopilot profiles."""
    return dict(AUTOPILOT_PROFILES)


def apply_autopilot_profile(
    gov_dir: Path,
    config: ProfileConfig,
) -> dict[str, str]:
    """
    Apply autopilot profile settings to the governor directory.

    This integrates with the existing profile/envelope/boil systems.
    Returns a dict of what was applied.
    """
    applied: dict[str, str] = {}

    # Envelope: strict vs exploratory based on anchor strictness
    envelope_mode = "strict" if config.anchor_strictness == AnchorStrictness.HARD else "exploratory"
    envelope_file = gov_dir / ".envelope"
    envelope_file.write_text(envelope_mode)
    applied["envelope"] = envelope_mode

    # Boil preset
    boil_file = gov_dir / ".boil_mode"
    boil_file.write_text(config.boil_level)
    applied["boil"] = config.boil_level

    # Strict mode: only for production-like profiles
    strict_mode = config.approval_path == ApprovalPath.REQUIRE_HUMAN
    strict_file = gov_dir / ".strict_mode"
    strict_file.write_text("enabled" if strict_mode else "disabled")
    applied["strict_mode"] = "enabled" if strict_mode else "disabled"

    # Jurisdiction based on exploration budget
    if config.exploration_budget >= 0.7:
        jurisdiction = "SPECULATIVE"
    elif config.exploration_budget >= 0.3:
        jurisdiction = "FACTUAL"
    else:
        jurisdiction = "FACTUAL"
    jurisdiction_file = gov_dir / ".jurisdiction"
    jurisdiction_file.write_text(jurisdiction)
    applied["jurisdiction"] = jurisdiction

    # Write autopilot-specific config
    autopilot_config = {
        "profile": config.name,
        "violation_default": config.violation_default.value,
        "retry_budget": config.retry_budget,
        "evidence_required": config.evidence_required.value,
        "scope_enforcement": config.scope_enforcement.value,
        "anchor_strictness": config.anchor_strictness.value,
        "approval_path": config.approval_path.value,
        "staleness_threshold_hours": config.staleness_threshold_hours,
    }
    if config.change_ceiling:
        autopilot_config["change_ceiling"] = config.change_ceiling.to_dict()
    if config.violation_in_scope:
        autopilot_config["violation_in_scope"] = config.violation_in_scope.value

    import json
    autopilot_file = gov_dir / ".autopilot"
    autopilot_file.write_text(json.dumps(autopilot_config, indent=2))
    applied["autopilot"] = config.name

    return applied


def load_autopilot_config(gov_dir: Path) -> dict[str, Any] | None:
    """Load autopilot config from .governor/.autopilot."""
    autopilot_file = gov_dir / ".autopilot"
    if not autopilot_file.exists():
        return None
    try:
        import json
        return json.loads(autopilot_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def resolve_violation_action(
    config: ProfileConfig,
    path: str | None = None,
    scope: list[str] | None = None,
) -> ViolationDefault:
    """
    Resolve the violation action for a given path under this profile.

    For hotfix profile, returns different action based on scope.
    """
    # Hotfix special case: in-scope vs out-of-scope handling
    if config.violation_in_scope and scope and path:
        import fnmatch
        for pattern in scope:
            if fnmatch.fnmatch(path, pattern):
                return config.violation_in_scope

    return config.violation_default


def check_change_limits(
    config: ProfileConfig,
    files: int = 0,
    loc: int = 0,
    modules: int = 0,
) -> tuple[bool, str | None]:
    """
    Check if a proposed change exceeds profile limits.

    Returns (allowed, reason). If not allowed, reason explains why.
    """
    if config.change_ceiling is None:
        return True, None

    exceeded, reason = config.change_ceiling.exceeds(files, loc, modules)
    if exceeded:
        return False, reason
    return True, None
