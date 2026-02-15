"""Engineering standards regression guards.

These tests enforce invariants from docs/ENGINEERING_STANDARDS.md mechanically.
If a test here fails, either the code or the standard needs updating — not
both silently.

Three sections:
  1. Schema version discipline: every persisted type emits and validates schema_version.
  2. Authority default guard: no .get() defaults on authority-bearing fields in kernel modules.
  3. Doc-test sync: the standards doc and test registry stay in agreement.
"""

from __future__ import annotations

import importlib
import re
from datetime import date
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

# Known-safe allowlist: (filename, line_substring, reason, review_until).
# Each entry is a .get() usage that has been reviewed and confirmed safe.
# review_until: the allowlist entry expires on this date and must be re-reviewed.
# Set to None for permanent exceptions (truly cannot affect a gate verdict).
AUTHORITY_GET_ALLOWLIST: list[tuple[str, str, str, date | None]] = [
    # gate_receipt: schema_version default is intentional (legacy compat)
    ("gate_receipt.py", '"schema_version", 1',
     "legacy compat default", None),
    # gate_receipt: these are metadata, not authority
    ("gate_receipt.py", '"principal_id", "local"',
     "metadata, not authority", None),
    ("gate_receipt.py", '"tenant_id", "default"',
     "metadata, not authority", None),
    ("gate_receipt.py", '"auth_method", "none"',
     "metadata, not authority", None),
    # daemon: verdict here is a query filter (None = no filter), not a gate default
    ("daemon.py", 'verdict = params.get("verdict")',
     "query filter, not gate default", None),
    # continuity: legacy Anchor deserialization — defaults to least-restrictive values.
    # These should be revisited when Anchor gets schema_version (backlog item).
    ("continuity.py", '"severity", "correct"',
     "legacy default, least-restrictive", date(2026, 8, 15)),
    ("continuity.py", '"constraint_class", "preference"',
     "legacy default, least-restrictive", date(2026, 8, 15)),
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
                        for al_file, al_substr, _reason, _expiry in AUTHORITY_GET_ALLOWLIST
                    ):
                        continue
                    violations.append(f"{module_name}:{i}: {line.strip()}")

        assert not violations, (
            f"Found .get() defaults on authority-bearing fields in kernel modules. "
            f"Either make these explicit (no default) or add to AUTHORITY_GET_ALLOWLIST "
            f"in test_standards.py after review:\n" + "\n".join(violations)
        )

    def test_allowlist_not_expired(self):
        """Allowlist entries with review_until must be re-reviewed before expiry."""
        today = date.today()
        expired = []
        for filename, substr, reason, review_until in AUTHORITY_GET_ALLOWLIST:
            if review_until is not None and today > review_until:
                expired.append(
                    f"{filename}: {substr!r} — {reason} "
                    f"(expired {review_until.isoformat()})"
                )
        assert not expired, (
            f"Allowlist entries have expired and need re-review. Either fix the "
            f"underlying code, extend the date, or promote to permanent (None):\n"
            + "\n".join(expired)
        )


# =============================================================================
# 3. Doc ↔ Test Sync
# =============================================================================


class TestDocTestSync:
    """The standards doc and test registry must stay in agreement."""

    def test_versioned_types_listed_in_doc(self):
        """Every type in SCHEMA_VERSIONED_TYPES must appear in ENGINEERING_STANDARDS.md."""
        doc_path = Path(__file__).parent.parent / "docs" / "ENGINEERING_STANDARDS.md"
        doc_text = doc_path.read_text(encoding="utf-8")

        missing = []
        for entry in SCHEMA_VERSIONED_TYPES:
            # Check that the constant name appears in the doc
            if entry["constant"] not in doc_text and entry["class_name"] not in doc_text:
                missing.append(f"{entry['class_name']} ({entry['constant']})")

        assert not missing, (
            f"Schema-versioned types registered in test_standards.py but not mentioned "
            f"in docs/ENGINEERING_STANDARDS.md: {missing}"
        )

    def test_doc_known_gaps_section_exists(self):
        """The doc must have a Known Gaps section listing unversioned persisted types."""
        doc_path = Path(__file__).parent.parent / "docs" / "ENGINEERING_STANDARDS.md"
        doc_text = doc_path.read_text(encoding="utf-8")
        assert "Known Gaps" in doc_text, (
            "docs/ENGINEERING_STANDARDS.md must have a 'Known Gaps' section "
            "listing persisted types without schema_version"
        )
