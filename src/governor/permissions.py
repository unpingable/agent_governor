# SPDX-License-Identifier: Apache-2.0
"""
Agent permissions system.

Per MULTI_AGENT.md:
- Per-agent permissions in config
- Path globs (allowed/denied)
- Decision topic whitelists
- Blast radius limits
"""

import fnmatch
import sys
from dataclasses import dataclass, field

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pathlib import Path
from typing import Any

from .claims import Claim, ClaimType


@dataclass
class AgentPermissions:
    """
    Permissions for a specific agent or agent class.

    Defines what an agent can propose and what resources it can touch.
    """

    # What can the agent propose?
    can_propose_decisions: bool = False
    can_propose_changesets: bool = True
    can_propose_facts: bool = True
    can_propose_reservations: bool = True

    # Path restrictions
    allowed_paths: list[str] = field(default_factory=lambda: ["**/*"])
    denied_paths: list[str] = field(default_factory=list)

    # Decision restrictions
    allowed_decision_topics: list[str] = field(default_factory=list)

    # Blast radius limits
    max_files_per_changeset: int = 20

    def can_touch_path(self, path: str) -> bool:
        """Check if agent can modify a path."""
        # Denied paths take precedence
        for pattern in self.denied_paths:
            if fnmatch.fnmatch(path, pattern):
                return False

        # Check against allowed paths
        for pattern in self.allowed_paths:
            if fnmatch.fnmatch(path, pattern):
                return True

        return False

    def can_decide_topic(self, topic: str) -> bool:
        """Check if agent can make decisions on a topic."""
        if not self.can_propose_decisions:
            return False

        if not self.allowed_decision_topics:
            return True  # No restrictions

        return topic.lower() in [t.lower() for t in self.allowed_decision_topics]

    def check_claim(self, claim: Claim) -> tuple[bool, str]:
        """
        Check if a claim is allowed by these permissions.

        Returns (allowed, reason).
        """
        # Decision claims
        if claim.type == ClaimType.DECISION:
            if not self.can_propose_decisions:
                return False, "Agent cannot propose decisions"
            if claim.topic and not self.can_decide_topic(claim.topic):
                return False, f"Agent cannot decide on topic '{claim.topic}'"

        # Changeset claims
        elif claim.type == ClaimType.CHANGESET:
            if not self.can_propose_changesets:
                return False, "Agent cannot propose changesets"

            # Check path restrictions
            if claim.paths:
                for path in claim.paths:
                    if not self.can_touch_path(path):
                        return False, f"Agent cannot modify path '{path}'"

                # Check blast radius
                if len(claim.paths) > self.max_files_per_changeset:
                    return False, (
                        f"Changeset touches {len(claim.paths)} files, "
                        f"max is {self.max_files_per_changeset}"
                    )

        # File-related facts
        elif claim.type in (ClaimType.FILE_EXISTS, ClaimType.SYMBOL_DEFINED, ClaimType.API_SURFACE):
            if not self.can_propose_facts:
                return False, "Agent cannot propose facts"
            if claim.path and not self.can_touch_path(claim.path):
                return False, f"Agent cannot access path '{claim.path}'"

        # Work reservations
        elif claim.type == ClaimType.WORK_RESERVATION:
            if not self.can_propose_reservations:
                return False, "Agent cannot propose work reservations"
            if claim.scope:
                for path in claim.scope:
                    if not self.can_touch_path(path):
                        return False, f"Agent cannot reserve path '{path}'"

        return True, "OK"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "can_propose_decisions": self.can_propose_decisions,
            "can_propose_changesets": self.can_propose_changesets,
            "can_propose_facts": self.can_propose_facts,
            "can_propose_reservations": self.can_propose_reservations,
            "allowed_paths": self.allowed_paths,
            "denied_paths": self.denied_paths,
            "allowed_decision_topics": self.allowed_decision_topics,
            "max_files_per_changeset": self.max_files_per_changeset,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentPermissions":
        """Deserialize from dict."""
        return cls(
            can_propose_decisions=data.get("can_propose_decisions", False),
            can_propose_changesets=data.get("can_propose_changesets", True),
            can_propose_facts=data.get("can_propose_facts", True),
            can_propose_reservations=data.get("can_propose_reservations", True),
            allowed_paths=data.get("allowed_paths", ["**/*"]),
            denied_paths=data.get("denied_paths", []),
            allowed_decision_topics=data.get("allowed_decision_topics", []),
            max_files_per_changeset=data.get("max_files_per_changeset", 20),
        )


# Predefined permission profiles
DEFAULT_PERMISSIONS = AgentPermissions(
    can_propose_decisions=False,
    can_propose_changesets=True,
    can_propose_facts=True,
    allowed_paths=["src/**", "tests/**"],
    denied_paths=[".governor/**", "*.toml", ".github/**"],
    max_files_per_changeset=10,
)

ARCHITECT_PERMISSIONS = AgentPermissions(
    can_propose_decisions=True,
    can_propose_changesets=True,
    can_propose_facts=True,
    allowed_decision_topics=["framework", "api_style", "database", "auth", "architecture"],
    allowed_paths=["**/*"],
    denied_paths=[".governor/**"],
    max_files_per_changeset=50,
)

IMPLEMENTER_PERMISSIONS = AgentPermissions(
    can_propose_decisions=False,
    can_propose_changesets=True,
    can_propose_facts=True,
    allowed_paths=["src/**", "tests/**", "docs/**"],
    denied_paths=[".governor/**", "*.toml", ".github/**", "CLAUDE.md"],
    max_files_per_changeset=20,
)

DOCS_PERMISSIONS = AgentPermissions(
    can_propose_decisions=False,
    can_propose_changesets=True,
    can_propose_facts=True,
    allowed_paths=["docs/**", "*.md"],
    denied_paths=["CLAUDE.md", ".governor/**"],
    max_files_per_changeset=10,
)

PROFILES = {
    "default": DEFAULT_PERMISSIONS,
    "architect": ARCHITECT_PERMISSIONS,
    "implementer": IMPLEMENTER_PERMISSIONS,
    "docs": DOCS_PERMISSIONS,
}


class PermissionManager:
    """
    Manages agent permissions from config file.

    Loads permissions from .governor/config.toml.
    """

    def __init__(self, governor_dir: Path):
        self.governor_dir = Path(governor_dir)
        self.config_path = self.governor_dir / "config.toml"
        self._permissions: dict[str, AgentPermissions] = {}
        self._load()

    def _load(self) -> None:
        """Load permissions from config file."""
        if not self.config_path.exists():
            # Use defaults
            self._permissions = {"default": DEFAULT_PERMISSIONS}
            return

        with open(self.config_path, "rb") as f:
            config = tomllib.load(f)

        perms_config = config.get("permissions", {})

        for name, perms_data in perms_config.items():
            # Check if it extends a profile
            extends = perms_data.pop("extends", None)
            if extends and extends in PROFILES:
                base = PROFILES[extends].to_dict()
                base.update(perms_data)
                perms_data = base

            self._permissions[name] = AgentPermissions.from_dict(perms_data)

        # Ensure default exists
        if "default" not in self._permissions:
            self._permissions["default"] = DEFAULT_PERMISSIONS

    def get_permissions(self, agent_id: str, agent_class: str | None = None) -> AgentPermissions:
        """
        Get permissions for an agent.

        Priority:
        1. Specific agent ID permissions
        2. Agent class permissions
        3. Default permissions
        """
        # Check for agent-specific permissions
        if agent_id in self._permissions:
            return self._permissions[agent_id]

        # Check for class-specific permissions
        if agent_class and agent_class in self._permissions:
            return self._permissions[agent_class]

        # Fall back to default
        return self._permissions.get("default", DEFAULT_PERMISSIONS)

    def check_claim(
        self,
        agent_id: str,
        claim: Claim,
        agent_class: str | None = None,
    ) -> tuple[bool, str]:
        """
        Check if an agent can make a claim.

        Returns (allowed, reason).
        """
        perms = self.get_permissions(agent_id, agent_class)
        return perms.check_claim(claim)

    def all_permissions(self) -> dict[str, AgentPermissions]:
        """Get all configured permissions."""
        return dict(self._permissions)


def create_default_config(governor_dir: Path) -> None:
    """Create a default config.toml with permission examples."""
    config_path = governor_dir / "config.toml"

    if config_path.exists():
        return

    config_content = '''# Governor Configuration

[permissions.default]
# Default for unspecified agents
can_propose_decisions = false
can_propose_changesets = true
can_propose_facts = true
max_files_per_changeset = 10
allowed_paths = ["src/**", "tests/**"]
denied_paths = [".governor/**", "*.toml", ".github/**"]

[permissions.architect]
# For architecture/design agents
extends = "architect"
# Uncomment to customize:
# allowed_decision_topics = ["framework", "api_style", "database"]

[permissions.implementer]
# For code generation agents
extends = "implementer"
# Uncomment to customize:
# max_files_per_changeset = 30

[permissions.docs]
# For documentation agents
extends = "docs"
'''

    config_path.write_text(config_content)
