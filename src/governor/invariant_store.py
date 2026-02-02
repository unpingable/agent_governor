"""
Invariant store: persistent invariant spec management.

InvariantSpec is a serializable definition that maps to InvariantLibrary factories.
InvariantStore persists specs as JSON files in .governor/invariants/<id>.json
and materializes them into live Invariant objects.

Deferred 1: Invariant management CLI + execution shell.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re

from .invariants import (
    Invariant,
    InvariantLibrary,
    InvariantSet,
)


# =============================================================================
# Valid kinds and factory mapping
# =============================================================================

VALID_KINDS: dict[str, dict[str, Any]] = {
    "test": {
        "factory": "tests_must_pass",
        "required_params": ["command"],
        "optional_params": ["args", "cwd"],
        "description": "Test command must exit 0",
    },
    "file-exists": {
        "factory": "file_must_exist",
        "required_params": ["path"],
        "optional_params": [],
        "description": "File must exist",
    },
    "dir-exists": {
        "factory": "directory_must_exist",
        "required_params": ["path"],
        "optional_params": [],
        "description": "Directory must exist",
    },
    "forbidden": {
        "factory": "forbidden_pattern",
        "required_params": ["pattern"],
        "optional_params": ["description"],
        "description": "Files matching pattern must not be touched",
    },
    "no-secrets": {
        "factory": "no_secrets",
        "required_params": [],
        "optional_params": [],
        "description": "No secret/credential files",
    },
    "max-file-size": {
        "factory": "max_file_size",
        "required_params": ["max_kb"],
        "optional_params": [],
        "description": "No file may exceed size limit",
    },
}


# =============================================================================
# InvariantSpec
# =============================================================================


@dataclass
class InvariantSpec:
    """
    Serializable specification for an invariant definition.

    Maps to InvariantLibrary factory methods via `kind`.
    """

    id: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    on_violation: str = "block"
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        if self.kind not in VALID_KINDS:
            raise ValueError(
                f"Invalid kind '{self.kind}'. Valid: {sorted(VALID_KINDS.keys())}"
            )

    def validate_params(self) -> list[str]:
        """Validate params against kind requirements. Returns list of errors."""
        errors: list[str] = []
        info = VALID_KINDS[self.kind]
        for req in info["required_params"]:
            if req not in self.params:
                errors.append(f"Missing required param '{req}' for kind '{self.kind}'")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "params": dict(self.params),
            "on_violation": self.on_violation,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvariantSpec":
        return cls(
            id=data["id"],
            kind=data["kind"],
            params=data.get("params", {}),
            on_violation=data.get("on_violation", "block"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


# =============================================================================
# InvariantStore
# =============================================================================


class InvariantStore:
    """
    File-per-item persistence for invariant specs.

    Specs are stored as JSON in .governor/invariants/<id>.json.
    Follows SpineManager pattern.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or Path(".")
        self.invariant_dir = self.root / ".governor" / "invariants"

    def _ensure_dir(self) -> None:
        self.invariant_dir.mkdir(parents=True, exist_ok=True)

    def _spec_path(self, spec_id: str) -> Path:
        # Sanitize ID for filesystem safety
        safe_id = re.sub(r"[^\w\-.]", "_", spec_id)
        return self.invariant_dir / f"{safe_id}.json"

    def add(self, spec: InvariantSpec) -> None:
        """Add (or overwrite) an invariant spec."""
        self._ensure_dir()
        path = self._spec_path(spec.id)
        path.write_text(json.dumps(spec.to_dict(), indent=2) + "\n")

    def remove(self, spec_id: str) -> bool:
        """Remove a spec. Returns True if it existed."""
        path = self._spec_path(spec_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def get(self, spec_id: str) -> InvariantSpec | None:
        """Get a spec by ID."""
        path = self._spec_path(spec_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return InvariantSpec.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def list_all(self) -> list[InvariantSpec]:
        """List all invariant specs."""
        if not self.invariant_dir.exists():
            return []
        specs: list[InvariantSpec] = []
        for path in sorted(self.invariant_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                specs.append(InvariantSpec.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return specs

    def materialize(self, spec_id: str) -> Invariant | None:
        """Materialize a spec into a live Invariant."""
        spec = self.get(spec_id)
        if spec is None:
            return None
        return _materialize_spec(spec)

    def materialize_all(self) -> InvariantSet:
        """Materialize all specs into an InvariantSet."""
        inv_set = InvariantSet()
        for spec in self.list_all():
            inv = _materialize_spec(spec)
            if inv is not None:
                inv_set.add(inv)
        return inv_set


def _materialize_spec(spec: InvariantSpec) -> Invariant | None:
    """Convert an InvariantSpec into a live Invariant using InvariantLibrary factories."""
    info = VALID_KINDS.get(spec.kind)
    if info is None:
        return None

    factory_name = info["factory"]
    factory = getattr(InvariantLibrary, factory_name, None)
    if factory is None:
        return None

    # Build factory kwargs from spec params
    kwargs: dict[str, Any] = {"invariant_id": spec.id}

    if spec.kind == "test":
        kwargs["command"] = spec.params.get("command", "pytest")
        if "args" in spec.params:
            args = spec.params["args"]
            if isinstance(args, str):
                args = args.split()
            kwargs["args"] = args
        if "cwd" in spec.params:
            from pathlib import Path as P
            kwargs["cwd"] = P(spec.params["cwd"])

    elif spec.kind == "file-exists":
        kwargs["path"] = spec.params["path"]

    elif spec.kind == "dir-exists":
        kwargs["path"] = spec.params["path"]

    elif spec.kind == "forbidden":
        kwargs["pattern"] = spec.params["pattern"]
        if "description" in spec.params:
            kwargs["description"] = spec.params["description"]

    elif spec.kind == "no-secrets":
        pass  # No extra params

    elif spec.kind == "max-file-size":
        kwargs["max_kb"] = int(spec.params["max_kb"])

    try:
        inv = factory(**kwargs)
    except (TypeError, KeyError):
        return None

    # Apply spec-level overrides
    inv.on_violation = spec.on_violation
    inv.enabled = spec.enabled

    return inv
