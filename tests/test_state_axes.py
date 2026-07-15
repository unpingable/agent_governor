# SPDX-License-Identifier: Apache-2.0
"""Tests for the closed six-axis state vocabulary.

Slice: closed axis vocabulary + mechanical checker (ruled 2026-07-15).
The law under test is the operator_mode law transplanted to portfolio state:
allowlist per axis, novel string -> typed violation, never a de-facto state.
"""

from __future__ import annotations

import pytest

from governor.state_axes import (
    AXES,
    AXIS_VOCABULARY,
    LEGACY_VALUE_MAP,
    AxisViolation,
    UnmappedAxisValueError,
    all_vocabulary_values,
    current_prose_block,
    is_canonical_prose_header,
    migrate_axis_value,
    migrate_state_axes,
    parse_prose_axis_blocks,
    validate_state_axes,
)


class TestVocabularyShape:
    def test_every_axis_has_a_vocabulary(self):
        assert set(AXIS_VOCABULARY) == set(AXES)

    def test_unknown_is_a_member_everywhere(self):
        """Absent evidence stays unknown — unknown is honest, not a violation."""
        for axis in AXES:
            assert "unknown" in AXIS_VOCABULARY[axis]

    def test_vocabulary_values_are_snake_case_tokens(self):
        for axis, value in all_vocabulary_values():
            assert value == value.lower()
            assert " " not in value


class TestValidation:
    def test_closed_values_validate_clean(self):
        axes = {axis: sorted(AXIS_VOCABULARY[axis])[0] for axis in AXES}
        assert validate_state_axes(axes) == []

    def test_novel_value_is_a_typed_violation(self):
        violations = validate_state_axes({"custody": "ns1_closed_unpushed"})
        assert violations == [
            AxisViolation("novel_value", "custody", "ns1_closed_unpushed")
        ]
        # The violation message teaches the fix, not just the failure.
        assert "never mints a state" in violations[0].describe()

    def test_unknown_axis_name_is_a_typed_violation(self):
        violations = validate_state_axes({"push_state": "ahead_2"})
        assert violations == [AxisViolation("unknown_axis", "push_state", "ahead_2")]

    def test_nested_form_is_validated_on_its_state_field(self):
        assert validate_state_axes({"custody": {"state": "partial", "detail": "x"}}) == []
        bad = validate_state_axes({"custody": {"state": "sort_of_done"}})
        assert bad == [AxisViolation("novel_value", "custody", "sort_of_done")]

    def test_malformed_value_is_a_typed_violation(self):
        violations = validate_state_axes({"custody": 7})
        assert len(violations) == 1
        assert violations[0].kind == "malformed"


class TestMigration:
    def test_migration_is_total_over_the_legacy_map(self):
        """Every mapped legacy value lands inside the closed vocabulary."""
        for axis, mapping in LEGACY_VALUE_MAP.items():
            for legacy, (closed, _detail) in mapping.items():
                assert closed in AXIS_VOCABULARY[axis], (axis, legacy, closed)

    def test_migration_is_idempotent_on_closed_values(self):
        for axis, value in all_vocabulary_values():
            closed, detail = migrate_axis_value(axis, value)
            assert closed == value
            assert detail is None

    def test_novel_value_refuses_rather_than_guessing(self):
        with pytest.raises(UnmappedAxisValueError):
            migrate_axis_value("custody", "vibes_good")

    def test_legacy_nuance_moves_into_detail(self):
        closed, detail = migrate_axis_value("custody", "ns1_closed_unpushed")
        assert closed == "partial"
        assert "e71303f" in detail

    def test_migrate_state_axes_preserves_existing_detail(self):
        axes = {
            "custody": {
                "state": "ns1_closed_unpushed",
                "detail": "operator-authored nuance",
            }
        }
        migrated, changed = migrate_state_axes(axes)
        assert changed
        assert migrated["custody"]["state"] == "partial"
        assert migrated["custody"]["detail"] == "operator-authored nuance"

    def test_migrate_state_axes_no_change_on_clean_input(self):
        axes = {"selection": "unselected", "custody": {"state": "partial", "basis": "b"}}
        migrated, changed = migrate_state_axes(axes)
        assert not changed
        assert migrated == axes


class TestProseParsing:
    NIGHTSHIFT_STYLE = (
        "Some narrative before.\n"
        "\n"
        "State axes: admission=`ratified`; selection=`unselected`;\n"
        "plan_approval=`unverifiable` (NS-1 exact artifact unpreserved);\n"
        "runtime_activity=`inactive`;\n"
        "effect_authority=`none_evidenced`; custody=`partial` (NS-2..6 unbuilt).\n"
        "\n"
        "## Later section\n"
        "\n"
        "State axes: admission=`ratified`; custody=`complete`.\n"
    )

    def test_parses_multiline_block_with_parenthetical_detail(self):
        block = current_prose_block(self.NIGHTSHIFT_STYLE)
        assert block is not None
        assert block.values == {
            "admission": "ratified",
            "selection": "unselected",
            "plan_approval": "unverifiable",
            "runtime_activity": "inactive",
            "effect_authority": "none_evidenced",
            "custody": "partial",
        }

    def test_first_block_wins_later_blocks_are_history(self):
        blocks = parse_prose_axis_blocks(self.NIGHTSHIFT_STYLE)
        assert len(blocks) == 2
        assert blocks[0].values["custody"] == "partial"
        assert blocks[1].values["custody"] == "complete"

    def test_midline_drifted_header_is_still_visible(self):
        """A header buried mid-paragraph must not hide from the checker."""
        text = "and must be measured dynamically. Current axes: admission=`ratified`;\ncustody=`complete`.\n"
        block = current_prose_block(text)
        assert block is not None
        assert block.header == "Current axes"
        assert not is_canonical_prose_header(block)

    def test_generic_prose_about_axes_does_not_false_positive(self):
        text = "The six axes: these are described elsewhere.\nNo tokens here.\n"
        assert current_prose_block(text) is None

    def test_canonical_header_recognized(self):
        block = current_prose_block("State axes: custody=`partial`.\n")
        assert block is not None
        assert is_canonical_prose_header(block)
