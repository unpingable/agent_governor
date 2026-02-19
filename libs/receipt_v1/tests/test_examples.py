# SPDX-License-Identifier: Apache-2.0
"""Tests for golden example receipts.

Two layers of validation:
1. JSON Schema (draft 2020-12) via jsonschema library — skipped if not installed.
   This is real schema validation, not structural approximation.
2. Structural + hash verification via receipt_v1.verify (always runs, zero deps).
   Enforces the same constraints the schema does, plus hash integrity.

Both layers must pass for examples to be considered valid.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from receipt_v1.verify import verify, verify_chain

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "receipt.schema.json"

# Array examples (chain files, demo traces) — excluded from single-receipt tests
_ARRAY_EXAMPLES = {"07_chain_two.json", "demo_trace.json"}

# Collect all single-receipt examples (not the chain arrays)
SINGLE_EXAMPLES = sorted(
    p for p in EXAMPLES_DIR.glob("*.json")
    if p.name not in _ARRAY_EXAMPLES
)


def _load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _try_import_jsonschema():
    """Try to import jsonschema; skip tests if not available."""
    try:
        import jsonschema
        return jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")


class TestExamplesSchemaValidation:
    """All golden examples must validate against receipt.schema.json."""

    def test_single_examples_validate(self):
        jsonschema = _try_import_jsonschema()
        schema = _load_schema()

        for path in SINGLE_EXAMPLES:
            with open(path) as f:
                data = json.load(f)
            try:
                jsonschema.validate(data, schema)
            except jsonschema.ValidationError as e:
                pytest.fail(f"{path.name} failed schema validation: {e.message}")

    def test_chain_example_validates(self):
        jsonschema = _try_import_jsonschema()
        schema = _load_schema()

        chain_path = EXAMPLES_DIR / "07_chain_two.json"
        with open(chain_path) as f:
            chain_data = json.load(f)

        assert isinstance(chain_data, list)
        for i, receipt in enumerate(chain_data):
            try:
                jsonschema.validate(receipt, schema)
            except jsonschema.ValidationError as e:
                pytest.fail(f"07_chain_two[{i}] failed schema validation: {e.message}")


class TestExamplesHashIntegrity:
    """All golden examples must have correct receipt_hash values."""

    def test_single_examples_hash_valid(self):
        for path in SINGLE_EXAMPLES:
            with open(path) as f:
                data = json.load(f)
            result = verify(data)
            assert result.ok, f"{path.name}: {result.errors}"

    def test_chain_integrity(self):
        chain_path = EXAMPLES_DIR / "07_chain_two.json"
        with open(chain_path) as f:
            chain_data = json.load(f)

        # Individual hash verification
        for i, receipt in enumerate(chain_data):
            result = verify(receipt)
            assert result.ok, f"07_chain_two[{i}]: {result.errors}"

        # Chain integrity
        result = verify_chain(chain_data)
        assert result.ok, f"Chain integrity: {result.errors}"
        assert not result.warnings, f"Chain warnings: {result.warnings}"


class TestExamplesSchemaRejectsJunk:
    """Verify schema rejects invalid ext keys."""

    def test_ext_unnamespaced_key_rejected_by_schema(self):
        jsonschema = _try_import_jsonschema()
        schema = _load_schema()

        # Load a valid example and add bad ext
        with open(SINGLE_EXAMPLES[0]) as f:
            data = json.load(f)
        data["ext"] = {"bad_key": "value"}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(data, schema)


class TestExamplesCompleteness:
    """Verify we have all 10 expected examples."""

    def test_expected_examples_exist(self):
        expected = [
            "01_allow_simple.json",
            "02_deny_scope.json",
            "03_deny_budget.json",
            "04_transform_narrow.json",
            "05_escalate_human.json",
            "06_allow_with_effects.json",
            "07_chain_two.json",
            "08_deny_unknown_tool.json",
            "09_allow_passthrough_warn.json",
            "10_execution_failure.json",
        ]
        for name in expected:
            path = EXAMPLES_DIR / name
            assert path.exists(), f"Missing example: {name}"


class TestDemoTrace:
    """Verify demo_trace.json: 4-receipt chain (deny + allow + failure + retry)."""

    def test_demo_trace_exists(self):
        path = EXAMPLES_DIR / "demo_trace.json"
        assert path.exists(), "Missing demo_trace.json"

    def test_demo_trace_structure(self):
        path = EXAMPLES_DIR / "demo_trace.json"
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 4

        # Expected sequence: deny, allow+success, allow+failure, allow+success(retry)
        assert data[0]["decision"]["action"] == "deny"
        assert data[1]["decision"]["action"] == "allow"
        assert data[1]["execution"]["status"] == "success"
        assert data[2]["execution"]["status"] == "failure"
        assert data[3]["execution"]["status"] == "success"
        assert data[3]["execution"]["attempt"] == 2

        # Same call_id on failure+retry
        assert data[2]["tool"]["call_id"] == data[3]["tool"]["call_id"]

    def test_demo_trace_hash_integrity(self):
        path = EXAMPLES_DIR / "demo_trace.json"
        with open(path) as f:
            data = json.load(f)
        for i, receipt in enumerate(data):
            result = verify(receipt)
            assert result.ok, f"demo_trace[{i}]: {result.errors}"

    def test_demo_trace_chain_integrity(self):
        path = EXAMPLES_DIR / "demo_trace.json"
        with open(path) as f:
            data = json.load(f)
        result = verify_chain(data)
        assert result.ok, f"demo_trace chain: {result.errors}"
        assert not result.warnings, f"demo_trace chain warnings: {result.warnings}"

    def test_demo_trace_schema_validation(self):
        jsonschema = _try_import_jsonschema()
        schema = _load_schema()
        path = EXAMPLES_DIR / "demo_trace.json"
        with open(path) as f:
            data = json.load(f)
        for i, receipt in enumerate(data):
            try:
                jsonschema.validate(receipt, schema)
            except jsonschema.ValidationError as e:
                pytest.fail(f"demo_trace[{i}] failed schema: {e.message}")


class TestResourceAccess:
    """Verify schema is accessible at runtime."""

    def test_schema_path_exists(self):
        from receipt_v1.resources import schema_path
        p = schema_path()
        assert p.exists()
        assert p.name == "receipt.schema.json"

    def test_schema_json_loads(self):
        from receipt_v1.resources import schema_json
        s = schema_json()
        assert s["title"] == "Receipt v1"
        assert s["properties"]["receipt_version"]["const"] == "1.0"
