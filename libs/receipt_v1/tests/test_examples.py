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

# Collect all single-receipt examples (not the chain array)
SINGLE_EXAMPLES = sorted(
    p for p in EXAMPLES_DIR.glob("*.json")
    if p.name != "07_chain_two.json"
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
