# SPDX-License-Identifier: Apache-2.0
"""
Spine: Locked project structure for autonomous execution.

A spine is an immutable structural definition that constrains what autonomous
agents can do. Human defines the spine, governor enforces it mechanically.
Spines are stored in .governor/spines/ as YAML files.

Phase A1: Core types and management.
Phase A2: Integration with autonomous executor (future).
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re


@dataclass
class SpineViolation:
    """A specific violation of the spine structure."""

    path: str  # Dotted path to the violated constraint (e.g., "files.src/main.py")
    message: str
    constraint: str  # The spine rule that was violated
    actual: str = ""  # What was found instead


@dataclass
class SpineCheckResult:
    """Result of checking a proposal against a spine."""

    valid: bool
    violations: list[SpineViolation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": [
                {
                    "path": v.path,
                    "message": v.message,
                    "constraint": v.constraint,
                    "actual": v.actual,
                }
                for v in self.violations
            ],
        }


@dataclass
class Spine:
    """
    Locked project structure definition.

    The spine defines what files, directories, and structure the project
    must maintain. Autonomous agents cannot violate the spine.

    Structure format:
        {
            "files": {"src/main.py": "required", "README.md": "required"},
            "directories": {"src/": "required", "tests/": "required"},
            "forbidden_paths": ["*.secret", "credentials/*"],
            "required_patterns": {"tests/test_*.py": "at_least_one"},
            "custom_rules": {"max_file_size_kb": 500},
        }
    """

    id: str
    structure: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    locked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    locked_by: str = "human"
    unlock_requires: str = "explicit_confirmation"

    def verify_proposal(self, proposal: dict[str, Any]) -> SpineCheckResult:
        """
        Check if a proposal is compatible with this spine.

        The proposal should have keys like:
            "files_modified": list of file paths
            "files_created": list of file paths
            "files_deleted": list of file paths
        """
        violations: list[SpineViolation] = []

        files_deleted = proposal.get("files_deleted", [])
        files_modified = proposal.get("files_modified", [])
        files_created = proposal.get("files_created", [])

        # Check required files aren't deleted
        required_files = self.structure.get("files", {})
        for path, status in required_files.items():
            if status == "required" and path in files_deleted:
                violations.append(SpineViolation(
                    path=f"files.{path}",
                    message=f"Cannot delete required file: {path}",
                    constraint=f"files.{path} = required",
                    actual="deleted",
                ))

        # Check required directories aren't emptied
        required_dirs = self.structure.get("directories", {})
        for dir_path, status in required_dirs.items():
            if status == "required":
                # Check if all files in this directory are being deleted
                dir_prefix = dir_path.rstrip("/") + "/"
                deletions_in_dir = [f for f in files_deleted if f.startswith(dir_prefix)]
                if deletions_in_dir:
                    violations.append(SpineViolation(
                        path=f"directories.{dir_path}",
                        message=f"Deleting files from required directory: {dir_path}",
                        constraint=f"directories.{dir_path} = required",
                        actual=f"deleting {len(deletions_in_dir)} file(s)",
                    ))

        # Check forbidden paths
        forbidden = self.structure.get("forbidden_paths", [])
        all_touched = set(files_modified + files_created)
        for pattern in forbidden:
            regex = _glob_to_regex(pattern)
            for path in all_touched:
                if regex.match(path):
                    violations.append(SpineViolation(
                        path=f"forbidden_paths.{pattern}",
                        message=f"Touching forbidden path: {path}",
                        constraint=f"forbidden: {pattern}",
                        actual=path,
                    ))

        return SpineCheckResult(
            valid=len(violations) == 0,
            violations=violations,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "structure": self.structure,
            "description": self.description,
            "locked_at": self.locked_at,
            "locked_by": self.locked_by,
            "unlock_requires": self.unlock_requires,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Spine":
        return cls(
            id=data["id"],
            structure=data.get("structure", {}),
            description=data.get("description", ""),
            locked_at=data.get("locked_at", datetime.now().isoformat()),
            locked_by=data.get("locked_by", "human"),
            unlock_requires=data.get("unlock_requires", "explicit_confirmation"),
        )

    def save(self, path: Path) -> None:
        """Save spine to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> "Spine":
        """Load spine from JSON file."""
        data = json.loads(path.read_text())
        return cls.from_dict(data)


def _glob_to_regex(pattern: str) -> re.Pattern:
    """Convert a simple glob pattern to a regex."""
    # Escape everything except * and ?
    result = ""
    for ch in pattern:
        if ch == "*":
            result += ".*"
        elif ch == "?":
            result += "."
        elif ch in r"\.+^${}()|[]":
            result += "\\" + ch
        else:
            result += ch
    return re.compile(f"^{result}$")


# =============================================================================
# SpineManager
# =============================================================================


class SpineManager:
    """
    Manages spines for a project.

    Spines are stored as JSON in .governor/spines/<id>.json.
    One spine can be active at a time (stored in .governor/spines/_active.json).
    """

    def __init__(self, root: Path | None = None):
        self.root = root or Path(".")
        self.spine_dir = self.root / ".governor" / "spines"

    def _ensure_dir(self) -> None:
        self.spine_dir.mkdir(parents=True, exist_ok=True)

    def _spine_path(self, spine_id: str) -> Path:
        return self.spine_dir / f"{spine_id}.json"

    def _active_path(self) -> Path:
        return self.spine_dir / "_active.json"

    def lock(self, spine: Spine) -> None:
        """Lock a spine (save it as immutable)."""
        self._ensure_dir()
        spine.locked_at = datetime.now().isoformat()
        spine.save(self._spine_path(spine.id))

    def unlock(self, spine_id: str) -> bool:
        """Unlock (delete) a spine. Returns True if it existed."""
        path = self._spine_path(spine_id)
        if not path.exists():
            return False

        # If this was the active spine, deactivate
        active = self.active_spine()
        if active and active.id == spine_id:
            self._active_path().unlink(missing_ok=True)

        path.unlink()
        return True

    def get(self, spine_id: str) -> Spine | None:
        """Get a spine by ID."""
        path = self._spine_path(spine_id)
        if not path.exists():
            return None
        return Spine.load(path)

    def list_spines(self) -> list[Spine]:
        """List all locked spines."""
        if not self.spine_dir.exists():
            return []
        spines = []
        for path in sorted(self.spine_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                spines.append(Spine.load(path))
            except (json.JSONDecodeError, KeyError):
                continue
        return spines

    def active_spine(self) -> Spine | None:
        """Get the currently active spine."""
        active_path = self._active_path()
        if not active_path.exists():
            return None
        try:
            data = json.loads(active_path.read_text())
            spine_id = data.get("active_id")
            if spine_id:
                return self.get(spine_id)
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def set_active(self, spine_id: str) -> bool:
        """Set a spine as active. Returns False if spine doesn't exist."""
        if not self._spine_path(spine_id).exists():
            return False
        self._ensure_dir()
        self._active_path().write_text(
            json.dumps({"active_id": spine_id}) + "\n"
        )
        return True

    def deactivate(self) -> None:
        """Deactivate the current spine."""
        self._active_path().unlink(missing_ok=True)

    def verify_proposal(self, proposal: dict[str, Any]) -> SpineCheckResult:
        """Verify a proposal against the active spine."""
        spine = self.active_spine()
        if spine is None:
            return SpineCheckResult(valid=True)
        return spine.verify_proposal(proposal)
