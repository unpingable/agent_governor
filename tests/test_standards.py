"""Engineering standards regression guards.

These tests enforce invariants from docs/ENGINEERING_STANDARDS.md mechanically.
If a test here fails, either the code or the standard needs updating — not
both silently.

Two sections:
  1. Schema version discipline: every persisted type emits and validates schema_version.
  2. Authority default guard: no .get() defaults on authority-bearing fields in kernel modules.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest


# =============================================================================
# 1. Schema Version Discipline
# =============================================================================

# Registry of persisted types that MUST have schema_version enforcement.
# Add new entries here when adding persisted state to the codebase.
SCHEMA_VERSIONED_TYPES = [
    {
        "module": "governor.gate_receipt",
        "class_name": "GateReceipt",
        "constant": "RECEIPT_SCHEMA_VERSION",
        # GateReceipt.from_dict needs explicit fields — use factory
        "factory": lambda mod: mod.create_receipt(
            gate="test", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        ),
    },
    {
        "module": "governor.correlator_telemetry",
        "class_name": "CorrelatorTelemetry",
        "constant": "CORRELATOR_SCHEMA_VERSION",
        "factory": lambda mod: mod.CorrelatorTelemetry(),
    },
    {
        "module": "governor.scope",
        "class_name": "ScopeGovernor",
        "constant": "SCOPE_SCHEMA_VERSION",
        "factory": lambda mod: mod.ScopeGovernor(),
    },
    {
        "module": "governor.semantic_stability",
        "class_name": "StabilityAuditResult",
        "constant": "STABILITY_SCHEMA_VERSION",
        # StabilityAuditResult needs many required fields — skip to_dict test,
        # test from_dict rejection only (more important anyway)
        "factory": None,
    },
]


class TestSchemaVersionDiscipline:
    """Every persisted type must emit schema_version and reject future versions."""

    @pytest.mark.parametrize(
        "entry",
        SCHEMA_VERSIONED_TYPES,
        ids=[e["module"].split(".")[-1] for e in SCHEMA_VERSIONED_TYPES],
    )
    def test_to_dict_includes_schema_version(self, entry):
        """to_dict() output must contain 'schema_version' key."""
        if entry["factory"] is None:
            pytest.skip(f"{entry['class_name']} requires complex construction")
        mod = importlib.import_module(entry["module"])
        obj = entry["factory"](mod)
        d = obj.to_dict()
        assert "schema_version" in d, (
            f"{entry['class_name']}.to_dict() missing 'schema_version' — "
            f"see docs/ENGINEERING_STANDARDS.md §3"
        )
        constant_val = getattr(mod, entry["constant"])
        assert d["schema_version"] == constant_val

    @pytest.mark.parametrize(
        "entry",
        SCHEMA_VERSIONED_TYPES,
        ids=[e["module"].split(".")[-1] for e in SCHEMA_VERSIONED_TYPES],
    )
    def test_from_dict_rejects_future_version(self, entry):
        """from_dict() must raise ValueError for schema_version > current."""
        mod = importlib.import_module(entry["module"])
        cls = getattr(mod, entry["class_name"])
        current = getattr(mod, entry["constant"])
        # Build a minimal dict that has a future version
        # (the rejection must happen BEFORE field parsing)
        future_dict = {"schema_version": current + 1}
        with pytest.raises(ValueError, match="newer than supported|Unknown.*schema.*version"):
            cls.from_dict(future_dict)

    def test_registry_is_complete(self):
        """Tripwire: any new _SCHEMA_VERSION constant must be added to the registry."""
        src_dir = Path(__file__).parent.parent / "src" / "governor"
        registered_modules = {e["module"].split(".")[-1] for e in SCHEMA_VERSIONED_TYPES}

        missing = []
        for py_file in sorted(src_dir.glob("*.py")):
            text = py_file.read_text(encoding="utf-8")
            # Look for FOO_SCHEMA_VERSION = <int> patterns
            matches = re.findall(r"^([A-Z_]+_SCHEMA_VERSION)\s*=\s*\d+", text, re.MULTILINE)
            if matches and py_file.stem not in registered_modules:
                missing.append(f"{py_file.stem}: {matches}")

        assert not missing, (
            f"Found _SCHEMA_VERSION constants not registered in test_standards.py: "
            f"{missing}. Add entries to SCHEMA_VERSIONED_TYPES."
        )


# =============================================================================
# 2. Authority Default Guard
# =============================================================================

# Authority-bearing field names — .get() with a default on these is suspicious.
# These fields can flip a gate verdict if defaulted incorrectly.
AUTHORITY_FIELDS = [
    "verdict",
    "allowed",
    "severity",
    "required",
    "forbidden",
    "constraint_class",
    "risk_level",
]

# Kernel modules where authority defaults are most dangerous.
KERNEL_MODULES = [
    "gate_receipt.py",
    "scope.py",
    "evidence_gate.py",
    "correlator_telemetry.py",
    "daemon.py",
    "continuity.py",
    "violation_resolver.py",
]

# Known-safe allowlist: (filename, line_content_substring) pairs.
# Each entry is a .get() usage that has been reviewed and confirmed safe.
AUTHORITY_GET_ALLOWLIST = [
    # gate_receipt: schema_version default is intentional (legacy compat)
    ("gate_receipt.py", '"schema_version", 1'),
    # gate_receipt: these are metadata, not authority
    ("gate_receipt.py", '"principal_id", "local"'),
    ("gate_receipt.py", '"tenant_id", "default"'),
    ("gate_receipt.py", '"auth_method", "none"'),
    # daemon: verdict here is a query filter (None = no filter), not a gate default
    ("daemon.py", 'verdict = params.get("verdict")'),
    # continuity: legacy Anchor deserialization — defaults to least-restrictive values
    # (preference, not invariant; correct, not critical). Reviewed 2026-02-15.
    ("continuity.py", '"severity", "correct"'),
    ("continuity.py", '"constraint_class", "preference"'),
]


class TestAuthorityDefaultGuard:
    """Flag .get() defaults on authority-bearing fields in kernel modules."""

    def test_no_unreviewed_authority_defaults(self):
        """Kernel modules must not silently default authority-bearing fields."""
        src_dir = Path(__file__).parent.parent / "src" / "governor"
        violations = []

        for module_name in KERNEL_MODULES:
            path = src_dir / module_name
            if not path.exists():
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                # Look for .get("field_name", default) patterns
                for field in AUTHORITY_FIELDS:
                    pattern = f'.get("{field}"'
                    if pattern not in line:
                        continue
                    # Check allowlist
                    if any(
                        module_name == al_file and al_substr in line
                        for al_file, al_substr in AUTHORITY_GET_ALLOWLIST
                    ):
                        continue
                    violations.append(f"{module_name}:{i}: {line.strip()}")

        assert not violations, (
            f"Found .get() defaults on authority-bearing fields in kernel modules. "
            f"Either make these explicit (no default) or add to AUTHORITY_GET_ALLOWLIST "
            f"in test_standards.py after review:\n" + "\n".join(violations)
        )
