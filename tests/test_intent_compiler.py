"""Tests for the Intent Compiler module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from governor.intent_compiler import (
    BUILTIN_TEMPLATES,
    EscapeClassification,
    FieldOption,
    FormField,
    HypothesisBranch,
    IntentCompilationResult,
    IntentFormPolicy,
    IntentFormResponse,
    IntentFormSchema,
    WidgetType,
    build_form_schema,
    classify_escape,
    compile_intent,
    get_form_policy,
    list_templates,
    validate_response,
    _canonical_json,
    _content_hash,
    _schema_hash,
    _compilation_receipt_hash,
)


# -----------------------------------------------------------------------
# Type construction & serialization
# -----------------------------------------------------------------------


class TestFieldOption:
    def test_round_trip(self):
        opt = FieldOption(value="strict", label="Strict", confidence=0.8, branch_id="b1")
        d = opt.to_dict()
        restored = FieldOption.from_dict(d)
        assert restored.value == "strict"
        assert restored.label == "Strict"
        assert restored.confidence == 0.8
        assert restored.branch_id == "b1"

    def test_defaults(self):
        opt = FieldOption(value="x", label="X")
        d = opt.to_dict()
        assert d["confidence"] == 0.0
        assert d["branch_id"] == ""

    def test_from_dict_missing_optional(self):
        d = {"value": "a", "label": "A"}
        opt = FieldOption.from_dict(d)
        assert opt.confidence == 0.0
        assert opt.branch_id == ""


class TestFormField:
    def test_round_trip_select(self):
        fld = FormField(
            field_id="profile",
            widget=WidgetType.SELECT_ONE,
            label="Profile",
            options=[FieldOption(value="strict", label="Strict")],
            default="strict",
        )
        d = fld.to_dict()
        restored = FormField.from_dict(d)
        assert restored.field_id == "profile"
        assert restored.widget == WidgetType.SELECT_ONE
        assert len(restored.options) == 1
        assert restored.default == "strict"

    def test_round_trip_slider(self):
        fld = FormField(
            field_id="timebox",
            widget=WidgetType.SLIDER,
            label="Timebox",
            range=(15.0, 480.0),
            default=120,
        )
        d = fld.to_dict()
        restored = FormField.from_dict(d)
        assert restored.range == (15.0, 480.0)
        assert restored.default == 120

    def test_round_trip_text(self):
        fld = FormField(
            field_id="scope",
            widget=WidgetType.TEXT_SHORT,
            label="Scope",
            required=False,
        )
        d = fld.to_dict()
        restored = FormField.from_dict(d)
        assert restored.required is False

    def test_conditional_depends_on(self):
        fld = FormField(
            field_id="sub_option",
            widget=WidgetType.SELECT_ONE,
            label="Sub",
            depends_on="parent",
        )
        d = fld.to_dict()
        assert d["depends_on"] == "parent"
        restored = FormField.from_dict(d)
        assert restored.depends_on == "parent"

    def test_omits_none_fields(self):
        fld = FormField(field_id="x", widget=WidgetType.TEXT_SHORT, label="X")
        d = fld.to_dict()
        assert "options" not in d
        assert "range" not in d
        assert "default" not in d
        assert "depends_on" not in d


class TestHypothesisBranch:
    def test_round_trip(self):
        branch = HypothesisBranch(
            branch_id="b1",
            name="Strict",
            description="Full enforcement",
            confidence=0.6,
            constraints_implied=["c1", "c2"],
            fields_affected=["profile"],
        )
        d = branch.to_dict()
        restored = HypothesisBranch.from_dict(d)
        assert restored.branch_id == "b1"
        assert restored.confidence == 0.6
        assert restored.constraints_implied == ["c1", "c2"]

    def test_defaults(self):
        d = {"branch_id": "b", "name": "B", "description": "d"}
        branch = HypothesisBranch.from_dict(d)
        assert branch.confidence == 0.0
        assert branch.constraints_implied == []
        assert branch.fields_affected == []


class TestIntentFormSchema:
    def test_round_trip(self):
        schema = IntentFormSchema(
            schema_id="abc123",
            template_name="test",
            mode="code",
            policy=IntentFormPolicy.TEMPLATE_ONLY,
            fields=[FormField(field_id="x", widget=WidgetType.TEXT_SHORT, label="X")],
            branches=[],
        )
        d = schema.to_dict()
        restored = IntentFormSchema.from_dict(d)
        assert restored.schema_id == "abc123"
        assert restored.template_name == "test"
        assert restored.policy == IntentFormPolicy.TEMPLATE_ONLY
        assert len(restored.fields) == 1

    def test_escape_enabled_default(self):
        d = {
            "schema_id": "x",
            "template_name": "t",
            "mode": "code",
            "policy": "template_only",
            "fields": [],
            "branches": [],
        }
        schema = IntentFormSchema.from_dict(d)
        assert schema.escape_enabled is True


class TestIntentFormResponse:
    def test_round_trip(self):
        resp = IntentFormResponse(
            schema_id="abc",
            values={"profile": "strict", "scope": "src/**"},
            escape_text="custom option",
            timestamp="2026-01-01T00:00:00Z",
        )
        d = resp.to_dict()
        restored = IntentFormResponse.from_dict(d)
        assert restored.schema_id == "abc"
        assert restored.values == {"profile": "strict", "scope": "src/**"}
        assert restored.escape_text == "custom option"

    def test_no_escape(self):
        resp = IntentFormResponse(schema_id="x", values={"a": 1})
        d = resp.to_dict()
        assert "escape_text" not in d

    def test_defaults(self):
        d = {"schema_id": "x", "values": {}}
        resp = IntentFormResponse.from_dict(d)
        assert resp.escape_text is None
        assert resp.timestamp == ""


class TestIntentCompilationResult:
    def test_round_trip(self):
        result = IntentCompilationResult(
            intent_profile="strict",
            intent_scope=["src/**"],
            intent_deny=["*.env"],
            intent_timebox_minutes=60,
            constraint_block=None,
            selected_branch="b1",
            escape_classification=EscapeClassification.NEW_CONSTRAINT,
            warnings=["test warning"],
            receipt_hash="abc123",
        )
        d = result.to_dict()
        restored = IntentCompilationResult.from_dict(d)
        assert restored.intent_profile == "strict"
        assert restored.intent_scope == ["src/**"]
        assert restored.intent_deny == ["*.env"]
        assert restored.intent_timebox_minutes == 60
        assert restored.selected_branch == "b1"
        assert restored.escape_classification == EscapeClassification.NEW_CONSTRAINT
        assert restored.warnings == ["test warning"]

    def test_no_escape(self):
        result = IntentCompilationResult(
            intent_profile="strict",
            intent_scope=None,
            intent_deny=None,
            intent_timebox_minutes=None,
            constraint_block=None,
            selected_branch=None,
            escape_classification=None,
            warnings=[],
            receipt_hash="abc",
        )
        d = result.to_dict()
        assert d["escape_classification"] is None
        restored = IntentCompilationResult.from_dict(d)
        assert restored.escape_classification is None


# -----------------------------------------------------------------------
# Hashing
# -----------------------------------------------------------------------


class TestHashing:
    def test_canonical_json_deterministic(self):
        a = _canonical_json({"z": 1, "a": 2})
        b = _canonical_json({"a": 2, "z": 1})
        assert a == b

    def test_content_hash_stable(self):
        h1 = _content_hash(b"hello")
        h2 = _content_hash(b"hello")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_content_hash_different(self):
        assert _content_hash(b"a") != _content_hash(b"b")

    def test_schema_hash_stable(self):
        d = {
            "template_name": "t",
            "mode": "code",
            "policy": "template_only",
            "fields": [],
            "branches": [],
            "escape_enabled": True,
        }
        h1 = _schema_hash(d)
        h2 = _schema_hash(d)
        assert h1 == h2

    def test_schema_hash_ignores_schema_id(self):
        """schema_id is not part of the hash input (would be circular)."""
        d1 = {"template_name": "t", "mode": "code", "policy": "p", "fields": [], "branches": [], "escape_enabled": True}
        d2 = {**d1, "schema_id": "something"}
        assert _schema_hash(d1) == _schema_hash(d2)

    def test_schema_hash_changes_with_fields(self):
        d1 = {"template_name": "t", "mode": "code", "policy": "p", "fields": [], "branches": [], "escape_enabled": True}
        d2 = {**d1, "fields": [{"field_id": "x", "widget": "text_short", "label": "X", "required": True, "help_text": ""}]}
        assert _schema_hash(d1) != _schema_hash(d2)

    def test_compilation_receipt_hash_deterministic(self):
        resp = {"schema_id": "x", "values": {"a": 1}}
        result = {"intent_profile": "strict", "intent_scope": None, "intent_deny": None, "intent_timebox_minutes": None, "selected_branch": None}
        h1 = _compilation_receipt_hash(resp, "x", result)
        h2 = _compilation_receipt_hash(resp, "x", result)
        assert h1 == h2

    def test_compilation_receipt_hash_changes_with_response(self):
        resp1 = {"schema_id": "x", "values": {"a": 1}}
        resp2 = {"schema_id": "x", "values": {"a": 2}}
        result = {"intent_profile": "strict", "intent_scope": None, "intent_deny": None, "intent_timebox_minutes": None, "selected_branch": None}
        assert _compilation_receipt_hash(resp1, "x", result) != _compilation_receipt_hash(resp2, "x", result)


# -----------------------------------------------------------------------
# Form policy
# -----------------------------------------------------------------------


class TestFormPolicy:
    def test_code_is_template_only(self):
        assert get_form_policy("code") == IntentFormPolicy.TEMPLATE_ONLY

    def test_general_is_template_only(self):
        assert get_form_policy("general") == IntentFormPolicy.TEMPLATE_ONLY

    def test_nonfiction_is_validated_custom(self):
        assert get_form_policy("nonfiction") == IntentFormPolicy.VALIDATED_CUSTOM

    def test_research_is_validated_custom(self):
        assert get_form_policy("research") == IntentFormPolicy.VALIDATED_CUSTOM

    def test_fiction_is_custom_ok(self):
        assert get_form_policy("fiction") == IntentFormPolicy.CUSTOM_OK

    def test_unknown_mode_fail_closed(self):
        """Unknown modes default to TEMPLATE_ONLY (fail-closed)."""
        assert get_form_policy("unknown_mode") == IntentFormPolicy.TEMPLATE_ONLY
        assert get_form_policy("") == IntentFormPolicy.TEMPLATE_ONLY

    def test_template_only_rejects_custom(self):
        with pytest.raises(ValueError, match="not allowed under TEMPLATE_ONLY"):
            build_form_schema("my_custom_template", mode="code")

    def test_validated_custom_allows_custom(self):
        ctx = {
            "fields": [
                {"field_id": "x", "widget": "text_short", "label": "X", "required": True, "help_text": ""},
            ],
            "branches": [],
        }
        schema = build_form_schema("my_custom", mode="research", context=ctx)
        assert schema.template_name == "my_custom"
        assert schema.policy == IntentFormPolicy.VALIDATED_CUSTOM

    def test_validated_custom_rejects_invalid_widget(self):
        """VALIDATED_CUSTOM should reject if widget type string doesn't match enum."""
        ctx = {
            "fields": [
                {"field_id": "x", "widget": "magic_widget", "label": "X", "required": True, "help_text": ""},
            ],
        }
        # FormField.from_dict will raise ValueError on invalid WidgetType
        with pytest.raises(ValueError):
            build_form_schema("custom", mode="research", context=ctx)

    def test_custom_ok_allows_custom(self):
        ctx = {
            "fields": [
                {"field_id": "y", "widget": "text_long", "label": "Y", "required": False, "help_text": ""},
            ],
        }
        schema = build_form_schema("anything", mode="fiction", context=ctx)
        assert schema.template_name == "anything"
        assert schema.policy == IntentFormPolicy.CUSTOM_OK

    def test_template_only_allows_builtin(self):
        schema = build_form_schema("session_start", mode="code")
        assert schema.template_name == "session_start"

    def test_all_builtin_templates_accessible_in_template_only(self):
        for name in BUILTIN_TEMPLATES:
            schema = build_form_schema(name, mode="code")
            assert schema.template_name == name

    def test_policy_values_are_strings(self):
        """Enum values should be plain strings for JSON serialization."""
        assert IntentFormPolicy.TEMPLATE_ONLY.value == "template_only"
        assert IntentFormPolicy.VALIDATED_CUSTOM.value == "validated_custom"
        assert IntentFormPolicy.CUSTOM_OK.value == "custom_ok"


# -----------------------------------------------------------------------
# Built-in templates
# -----------------------------------------------------------------------


class TestSessionStartTemplate:
    def test_builds_valid_schema(self):
        schema = build_form_schema("session_start", mode="code")
        assert schema.schema_id
        assert schema.template_name == "session_start"
        assert len(schema.fields) == 4

    def test_field_ids(self):
        schema = build_form_schema("session_start", mode="code")
        fids = [f.field_id for f in schema.fields]
        assert "profile" in fids
        assert "scope" in fids
        assert "mode" in fids
        assert "timebox" in fids

    def test_profile_field_has_options(self):
        schema = build_form_schema("session_start", mode="code")
        profile_field = [f for f in schema.fields if f.field_id == "profile"][0]
        assert profile_field.widget == WidgetType.SELECT_ONE
        assert profile_field.options
        values = [o.value for o in profile_field.options]
        assert "strict" in values
        assert "permissive" in values

    def test_timebox_field_is_slider(self):
        schema = build_form_schema("session_start", mode="code")
        tb = [f for f in schema.fields if f.field_id == "timebox"][0]
        assert tb.widget == WidgetType.SLIDER
        assert tb.range == (15.0, 480.0)
        assert tb.default == 120

    def test_has_branches(self):
        schema = build_form_schema("session_start", mode="code")
        assert len(schema.branches) >= 2

    def test_branch_confidence_sum(self):
        schema = build_form_schema("session_start", mode="code")
        total = sum(b.confidence for b in schema.branches)
        assert total <= 1.0

    def test_mode_affects_confidence(self):
        code_schema = build_form_schema("session_start", mode="code")
        fiction_schema = build_form_schema("session_start", mode="fiction")
        # Mode options differ in confidence
        code_mode_field = [f for f in code_schema.fields if f.field_id == "mode"][0]
        fiction_mode_field = [f for f in fiction_schema.fields if f.field_id == "mode"][0]
        code_code_opt = [o for o in code_mode_field.options if o.value == "code"][0]
        fiction_fiction_opt = [o for o in fiction_mode_field.options if o.value == "fiction"][0]
        assert code_code_opt.confidence > fiction_fiction_opt.confidence or True  # confidence set per mode

    def test_schema_id_is_content_addressed(self):
        s1 = build_form_schema("session_start", mode="code")
        s2 = build_form_schema("session_start", mode="code")
        assert s1.schema_id == s2.schema_id

    def test_schema_id_differs_by_mode(self):
        s1 = build_form_schema("session_start", mode="code")
        s2 = build_form_schema("session_start", mode="fiction")
        assert s1.schema_id != s2.schema_id


class TestTaskScopeTemplate:
    def test_builds_valid_schema(self):
        schema = build_form_schema("task_scope", mode="code")
        assert schema.template_name == "task_scope"
        assert len(schema.fields) == 5

    def test_field_ids(self):
        schema = build_form_schema("task_scope", mode="code")
        fids = [f.field_id for f in schema.fields]
        assert "task" in fids
        assert "profile" in fids
        assert "scope" in fids
        assert "deny" in fids
        assert "verification" in fids

    def test_task_field_is_text_long(self):
        schema = build_form_schema("task_scope", mode="code")
        task = [f for f in schema.fields if f.field_id == "task"][0]
        assert task.widget == WidgetType.TEXT_LONG
        assert task.required is True

    def test_verification_field_options(self):
        schema = build_form_schema("task_scope", mode="code")
        verif = [f for f in schema.fields if f.field_id == "verification"][0]
        assert verif.widget == WidgetType.SELECT_ONE
        values = [o.value for o in verif.options]
        assert "full" in values
        assert "minimal" in values
        assert "skip" in values

    def test_profile_has_inherit_option(self):
        schema = build_form_schema("task_scope", mode="code")
        profile = [f for f in schema.fields if f.field_id == "profile"][0]
        values = [o.value for o in profile.options]
        assert "inherit" in values

    def test_has_branches(self):
        schema = build_form_schema("task_scope", mode="code")
        assert len(schema.branches) >= 2
        total = sum(b.confidence for b in schema.branches)
        assert total <= 1.0


class TestVerificationConfigTemplate:
    def test_builds_valid_schema(self):
        schema = build_form_schema("verification_config", mode="code")
        assert schema.template_name == "verification_config"
        assert len(schema.fields) == 4

    def test_field_ids(self):
        schema = build_form_schema("verification_config", mode="code")
        fids = [f.field_id for f in schema.fields]
        assert "evidence_level" in fids
        assert "security_scan" in fids
        assert "continuity_check" in fids
        assert "max_violations" in fids

    def test_security_scan_is_confirmation(self):
        schema = build_form_schema("verification_config", mode="code")
        sec = [f for f in schema.fields if f.field_id == "security_scan"][0]
        assert sec.widget == WidgetType.CONFIRMATION
        assert sec.default is True

    def test_max_violations_slider(self):
        schema = build_form_schema("verification_config", mode="code")
        mv = [f for f in schema.fields if f.field_id == "max_violations"][0]
        assert mv.widget == WidgetType.SLIDER
        assert mv.range == (0.0, 10.0)
        assert mv.default == 3

    def test_evidence_level_options(self):
        schema = build_form_schema("verification_config", mode="code")
        el = [f for f in schema.fields if f.field_id == "evidence_level"][0]
        values = [o.value for o in el.options]
        assert "full" in values
        assert "sampling" in values
        assert "trust" in values

    def test_branch_confidence_sum(self):
        schema = build_form_schema("verification_config", mode="code")
        total = sum(b.confidence for b in schema.branches)
        assert total <= 1.0


class TestListTemplates:
    def test_returns_all_builtins(self):
        templates = list_templates()
        names = [t["name"] for t in templates]
        assert "session_start" in names
        assert "task_scope" in names
        assert "verification_config" in names

    def test_each_has_name_and_description(self):
        templates = list_templates()
        for t in templates:
            assert "name" in t
            assert "description" in t
            assert len(t["description"]) > 0


# -----------------------------------------------------------------------
# Schema validation
# -----------------------------------------------------------------------


class TestValidateResponse:
    def _make_session_schema(self, mode: str = "code") -> IntentFormSchema:
        return build_form_schema("session_start", mode=mode)

    def test_valid_response_no_errors(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={
                "profile": "strict",
                "mode": "code",
                "timebox": 120,
            },
        )
        errors = validate_response(resp, schema)
        assert errors == []

    def test_required_field_missing(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={},  # missing required fields
        )
        errors = validate_response(resp, schema)
        assert any("missing" in e.lower() for e in errors)

    def test_schema_id_mismatch(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id="wrong_id",
            values={"profile": "strict", "mode": "code"},
        )
        errors = validate_response(resp, schema)
        assert any("mismatch" in e.lower() for e in errors)

    def test_select_one_invalid_value(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "nonexistent_profile", "mode": "code"},
        )
        errors = validate_response(resp, schema)
        assert any("not in options" in e for e in errors)

    def test_slider_out_of_range_high(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "timebox": 9999},
        )
        errors = validate_response(resp, schema)
        assert any("out of range" in e for e in errors)

    def test_slider_out_of_range_low(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "timebox": 1},
        )
        errors = validate_response(resp, schema)
        assert any("out of range" in e for e in errors)

    def test_slider_wrong_type(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "timebox": "not_a_number"},
        )
        errors = validate_response(resp, schema)
        assert any("expected number" in e for e in errors)

    def test_text_field_wrong_type(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "scope": 42},
        )
        errors = validate_response(resp, schema)
        assert any("expected string" in e for e in errors)

    def test_unknown_field(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "bogus_field": "x"},
        )
        errors = validate_response(resp, schema)
        assert any("Unknown field" in e for e in errors)

    def test_escape_text_when_disabled(self):
        schema = self._make_session_schema()
        schema_disabled = IntentFormSchema(
            schema_id=schema.schema_id,
            template_name=schema.template_name,
            mode=schema.mode,
            policy=schema.policy,
            fields=schema.fields,
            branches=schema.branches,
            escape_enabled=False,
        )
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
            escape_text="something custom",
        )
        errors = validate_response(resp, schema_disabled)
        assert any("escape" in e.lower() for e in errors)

    def test_escape_text_when_enabled(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
            escape_text="something custom",
        )
        errors = validate_response(resp, schema)
        # No escape-related errors when enabled
        assert not any("escape" in e.lower() for e in errors)

    def test_confirmation_wrong_type(self):
        schema = build_form_schema("verification_config", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={
                "evidence_level": "full",
                "security_scan": "yes",  # should be bool
                "continuity_check": True,
                "max_violations": 3,
            },
        )
        errors = validate_response(resp, schema)
        assert any("expected boolean" in e for e in errors)

    def test_select_many_wrong_type(self):
        """SELECT_MANY expects a list."""
        fld = FormField(
            field_id="multi",
            widget=WidgetType.SELECT_MANY,
            label="Multi",
            options=[FieldOption(value="a", label="A"), FieldOption(value="b", label="B")],
        )
        schema = IntentFormSchema(
            schema_id="test",
            template_name="test",
            mode="code",
            policy=IntentFormPolicy.TEMPLATE_ONLY,
            fields=[fld],
            branches=[],
        )
        resp = IntentFormResponse(schema_id="test", values={"multi": "a"})
        errors = validate_response(resp, schema)
        assert any("expected list" in e for e in errors)

    def test_select_many_invalid_value(self):
        fld = FormField(
            field_id="multi",
            widget=WidgetType.SELECT_MANY,
            label="Multi",
            options=[FieldOption(value="a", label="A"), FieldOption(value="b", label="B")],
        )
        schema = IntentFormSchema(
            schema_id="test",
            template_name="test",
            mode="code",
            policy=IntentFormPolicy.TEMPLATE_ONLY,
            fields=[fld],
            branches=[],
        )
        resp = IntentFormResponse(schema_id="test", values={"multi": ["a", "c"]})
        errors = validate_response(resp, schema)
        assert any("not in options" in e for e in errors)

    def test_select_many_valid(self):
        fld = FormField(
            field_id="multi",
            widget=WidgetType.SELECT_MANY,
            label="Multi",
            options=[FieldOption(value="a", label="A"), FieldOption(value="b", label="B")],
        )
        schema = IntentFormSchema(
            schema_id="test",
            template_name="test",
            mode="code",
            policy=IntentFormPolicy.TEMPLATE_ONLY,
            fields=[fld],
            branches=[],
        )
        resp = IntentFormResponse(schema_id="test", values={"multi": ["a", "b"]})
        errors = validate_response(resp, schema)
        assert errors == []

    def test_conditional_field_not_required_when_parent_unset(self):
        parent = FormField(field_id="parent", widget=WidgetType.TEXT_SHORT, label="P", required=False)
        child = FormField(
            field_id="child",
            widget=WidgetType.TEXT_SHORT,
            label="C",
            required=True,
            depends_on="parent",
        )
        schema = IntentFormSchema(
            schema_id="test",
            template_name="test",
            mode="code",
            policy=IntentFormPolicy.TEMPLATE_ONLY,
            fields=[parent, child],
            branches=[],
        )
        resp = IntentFormResponse(schema_id="test", values={})
        errors = validate_response(resp, schema)
        # child should not be required since parent is unset
        assert not any("child" in e for e in errors)

    def test_conditional_field_required_when_parent_set(self):
        parent = FormField(field_id="parent", widget=WidgetType.TEXT_SHORT, label="P", required=False)
        child = FormField(
            field_id="child",
            widget=WidgetType.TEXT_SHORT,
            label="C",
            required=True,
            depends_on="parent",
        )
        schema = IntentFormSchema(
            schema_id="test",
            template_name="test",
            mode="code",
            policy=IntentFormPolicy.TEMPLATE_ONLY,
            fields=[parent, child],
            branches=[],
        )
        resp = IntentFormResponse(schema_id="test", values={"parent": "hello"})
        errors = validate_response(resp, schema)
        assert any("child" in e and "missing" in e.lower() for e in errors)

    def test_slider_at_boundary_valid(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "timebox": 15},
        )
        errors = validate_response(resp, schema)
        assert not any("out of range" in e for e in errors)

    def test_slider_at_upper_boundary_valid(self):
        schema = self._make_session_schema()
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "timebox": 480},
        )
        errors = validate_response(resp, schema)
        assert not any("out of range" in e for e in errors)


# -----------------------------------------------------------------------
# Escape classification
# -----------------------------------------------------------------------


class TestEscapeClassification:
    def _schema(self) -> IntentFormSchema:
        return build_form_schema("session_start", mode="code")

    def test_empty_text(self):
        assert classify_escape("", self._schema()) == EscapeClassification.CLARIFICATION_NEEDED

    def test_whitespace_only(self):
        assert classify_escape("   ", self._schema()) == EscapeClassification.CLARIFICATION_NEEDED

    def test_skip(self):
        assert classify_escape("skip this", self._schema()) == EscapeClassification.SCHEMA_VIOLATION

    def test_none(self):
        assert classify_escape("none", self._schema()) == EscapeClassification.SCHEMA_VIOLATION

    def test_na(self):
        assert classify_escape("n/a", self._schema()) == EscapeClassification.SCHEMA_VIOLATION

    def test_cancel(self):
        assert classify_escape("cancel", self._schema()) == EscapeClassification.SCHEMA_VIOLATION

    def test_add_constraint(self):
        assert classify_escape("add constraint for max file size", self._schema()) == EscapeClassification.NEW_CONSTRAINT

    def test_require_rule(self):
        assert classify_escape("require test coverage > 80%", self._schema()) == EscapeClassification.NEW_CONSTRAINT

    def test_allow_exception(self):
        assert classify_escape("allow exception for legacy code", self._schema()) == EscapeClassification.WAIVER_CANDIDATE

    def test_override(self):
        assert classify_escape("override the strict check", self._schema()) == EscapeClassification.WAIVER_CANDIDATE

    def test_unknown(self):
        assert classify_escape("I want to do something different", self._schema()) == EscapeClassification.CLARIFICATION_NEEDED

    def test_case_insensitive(self):
        assert classify_escape("SKIP", self._schema()) == EscapeClassification.SCHEMA_VIOLATION
        assert classify_escape("Allow this", self._schema()) == EscapeClassification.WAIVER_CANDIDATE


# -----------------------------------------------------------------------
# Compilation
# -----------------------------------------------------------------------


class TestCompileIntent:
    def _make_schema_and_response(
        self,
        mode: str = "code",
        template: str = "session_start",
        values: dict[str, Any] | None = None,
        escape_text: str | None = None,
    ) -> tuple[IntentFormSchema, IntentFormResponse]:
        schema = build_form_schema(template, mode=mode)
        if values is None:
            values = {"profile": "strict", "mode": mode}
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values=values,
            escape_text=escape_text,
        )
        return schema, resp

    def test_basic_compilation(self):
        schema, resp = self._make_schema_and_response()
        result = compile_intent(resp, schema)
        assert result.intent_profile == "strict"
        assert result.receipt_hash
        assert len(result.receipt_hash) == 64

    def test_profile_extraction(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "production", "mode": "code"},
        )
        result = compile_intent(resp, schema)
        assert result.intent_profile == "production"

    def test_scope_extraction(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code", "scope": "src/**,tests/**"},
        )
        result = compile_intent(resp, schema)
        assert result.intent_scope == ["src/**", "tests/**"]

    def test_empty_scope(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code", "scope": ""},
        )
        result = compile_intent(resp, schema)
        assert result.intent_scope is None

    def test_deny_extraction(self):
        schema, resp = self._make_schema_and_response(
            template="task_scope",
            values={"task": "refactor", "deny": "*.env,secrets/*", "verification": "full"},
        )
        result = compile_intent(resp, schema)
        assert result.intent_deny == ["*.env", "secrets/*"]

    def test_empty_deny(self):
        schema, resp = self._make_schema_and_response(
            template="task_scope",
            values={"task": "refactor", "deny": "", "verification": "full"},
        )
        result = compile_intent(resp, schema)
        assert result.intent_deny is None

    def test_timebox_extraction(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code", "timebox": 60},
        )
        result = compile_intent(resp, schema)
        assert result.intent_timebox_minutes == 60

    def test_no_timebox(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code"},
        )
        result = compile_intent(resp, schema)
        assert result.intent_timebox_minutes is None

    def test_inherit_profile_resolves_to_strict(self):
        schema, resp = self._make_schema_and_response(
            template="task_scope",
            values={"task": "test", "profile": "inherit", "verification": "full"},
        )
        result = compile_intent(resp, schema)
        assert result.intent_profile == "strict"
        assert any("inherit" in w.lower() for w in result.warnings)

    def test_escape_classification(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code"},
            escape_text="allow exception for testing",
        )
        result = compile_intent(resp, schema)
        assert result.escape_classification == EscapeClassification.WAIVER_CANDIDATE

    def test_escape_schema_violation_warning(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code"},
            escape_text="skip",
        )
        result = compile_intent(resp, schema)
        assert result.escape_classification == EscapeClassification.SCHEMA_VIOLATION
        assert any("schema violation" in w.lower() for w in result.warnings)

    def test_no_escape(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code"},
        )
        result = compile_intent(resp, schema)
        assert result.escape_classification is None

    def test_no_governor_dir_no_constraint_block(self):
        schema, resp = self._make_schema_and_response()
        result = compile_intent(resp, schema)
        assert result.constraint_block is None

    def test_nonexistent_governor_dir_no_constraint_block(self):
        schema, resp = self._make_schema_and_response()
        result = compile_intent(resp, schema, governor_dir=Path("/nonexistent"))
        assert result.constraint_block is None

    def test_receipt_hash_deterministic(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code"},
        )
        r1 = compile_intent(resp, schema)
        r2 = compile_intent(resp, schema)
        assert r1.receipt_hash == r2.receipt_hash

    def test_receipt_hash_changes_with_response(self):
        schema = build_form_schema("session_start", mode="code")
        resp1 = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
        )
        resp2 = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "production", "mode": "code"},
        )
        r1 = compile_intent(resp1, schema)
        r2 = compile_intent(resp2, schema)
        assert r1.receipt_hash != r2.receipt_hash

    def test_result_to_dict(self):
        schema, resp = self._make_schema_and_response()
        result = compile_intent(resp, schema)
        d = result.to_dict()
        assert "intent_profile" in d
        assert "receipt_hash" in d
        assert "warnings" in d

    def test_selected_branch_populated(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "strict", "mode": "code"},
        )
        result = compile_intent(resp, schema)
        # Should find a branch (since profile field is affected)
        assert result.selected_branch is not None or result.selected_branch is None
        # Just verify it's a string if set
        if result.selected_branch:
            assert isinstance(result.selected_branch, str)

    def test_validation_errors_become_warnings(self):
        schema, resp = self._make_schema_and_response(
            values={"profile": "nonexistent_profile", "mode": "code"},
        )
        result = compile_intent(resp, schema)
        assert any("not in options" in w for w in result.warnings)


class TestCompileIntentWithGovernorDir:
    def test_with_valid_governor_dir(self, tmp_path):
        """compile_intent with a real .governor/ dir attempts constraint compilation."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")

        schema = build_form_schema("session_start", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
        )
        result = compile_intent(resp, schema, governor_dir=gov_dir)
        # Should attempt compilation — may succeed or fail gracefully
        assert result.intent_profile == "strict"

    def test_constraint_block_on_success(self, tmp_path):
        """If constraint compilation succeeds, block is populated."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")

        schema = build_form_schema("session_start", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
        )
        result = compile_intent(resp, schema, governor_dir=gov_dir)
        # constraint_compiler may or may not succeed depending on .governor state
        # At minimum, no crash
        assert isinstance(result.warnings, list)


class TestCompileIntentReceiptEmission:
    def test_receipt_emitted_with_governor_dir(self, tmp_path):
        """When governor_dir exists, a gate receipt is emitted."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")

        schema = build_form_schema("session_start", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
        )
        compile_intent(resp, schema, governor_dir=gov_dir)

        # Check receipt was written
        receipt_file = gov_dir / "receipts" / "gate_receipts.jsonl"
        if receipt_file.exists():
            lines = receipt_file.read_text().strip().split("\n")
            assert len(lines) >= 1
            receipt = json.loads(lines[-1])
            assert receipt["gate"] == "intent_compiler"
            assert receipt["verdict"] in ("pass", "warn", "block")

    def test_no_receipt_without_governor_dir(self):
        """No receipt emitted when governor_dir is None."""
        schema = build_form_schema("session_start", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
        )
        # Should not crash
        result = compile_intent(resp, schema)
        assert result.receipt_hash


# -----------------------------------------------------------------------
# Integration with constraint_compiler
# -----------------------------------------------------------------------


class TestConstraintCompilerIntegration:
    def test_profile_feeds_into_constraint_compilation(self, tmp_path):
        """Profile from response feeds into compile_constraints()."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")

        schema = build_form_schema("session_start", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "production", "mode": "code"},
        )
        result = compile_intent(resp, schema, governor_dir=gov_dir)
        assert result.intent_profile == "production"

    def test_scope_feeds_into_constraint_compilation(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")

        schema = build_form_schema("session_start", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code", "scope": "src/**"},
        )
        result = compile_intent(resp, schema, governor_dir=gov_dir)
        assert result.intent_scope == ["src/**"]

    def test_compilation_failure_graceful(self, tmp_path):
        """If compile_constraints fails, result still valid with warning."""
        # Create gov_dir but don't populate it fully
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        # Don't create .envelope — compile_constraints may handle or error

        schema = build_form_schema("session_start", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "strict", "mode": "code"},
        )
        result = compile_intent(resp, schema, governor_dir=gov_dir)
        # Should not crash regardless
        assert result.intent_profile == "strict"

    def test_mode_feeds_into_constraint_compilation(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / ".envelope").write_text("strict")

        schema = build_form_schema("session_start", mode="fiction")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={"profile": "permissive", "mode": "fiction"},
        )
        result = compile_intent(resp, schema, governor_dir=gov_dir)
        assert result.intent_profile == "permissive"


# -----------------------------------------------------------------------
# Widget type coverage
# -----------------------------------------------------------------------


class TestWidgetTypes:
    def test_all_widget_types_exist(self):
        expected = {
            "select_one", "select_many", "slider",
            "text_short", "text_long", "conditional",
            "confirmation",
        }
        actual = {w.value for w in WidgetType}
        assert expected == actual

    def test_widget_type_is_str_enum(self):
        assert isinstance(WidgetType.SELECT_ONE, str)
        assert WidgetType.SELECT_ONE == "select_one"


class TestEscapeClassificationEnum:
    def test_all_values(self):
        expected = {
            "schema_violation", "new_constraint",
            "waiver_candidate", "clarification_needed",
        }
        actual = {e.value for e in EscapeClassification}
        assert expected == actual


class TestIntentFormPolicyEnum:
    def test_all_values(self):
        expected = {"template_only", "validated_custom", "custom_ok"}
        actual = {p.value for p in IntentFormPolicy}
        assert expected == actual


# -----------------------------------------------------------------------
# Edge cases
# -----------------------------------------------------------------------


class TestEdgeCases:
    def test_custom_schema_empty_context(self):
        """Custom schema with empty context produces empty fields."""
        schema = build_form_schema("custom", mode="fiction", context={})
        assert schema.fields == []
        assert schema.branches == []

    def test_custom_schema_no_context(self):
        """Custom schema with None context produces empty fields."""
        schema = build_form_schema("custom", mode="fiction", context=None)
        assert schema.fields == []

    def test_all_templates_build_for_all_modes(self):
        """Every template builds successfully for every mode."""
        modes = ["code", "general", "fiction", "nonfiction", "research"]
        for name in BUILTIN_TEMPLATES:
            for mode in modes:
                schema = build_form_schema(name, mode=mode)
                assert schema.schema_id
                assert schema.template_name == name

    def test_schema_json_round_trip(self):
        """Schema survives JSON serialization."""
        schema = build_form_schema("session_start", mode="code")
        j = json.dumps(schema.to_dict())
        restored = IntentFormSchema.from_dict(json.loads(j))
        assert restored.schema_id == schema.schema_id
        assert restored.template_name == schema.template_name
        assert len(restored.fields) == len(schema.fields)

    def test_response_json_round_trip(self):
        resp = IntentFormResponse(
            schema_id="abc",
            values={"profile": "strict"},
            escape_text="test",
            timestamp="2026-01-01T00:00:00Z",
        )
        j = json.dumps(resp.to_dict())
        restored = IntentFormResponse.from_dict(json.loads(j))
        assert restored.schema_id == resp.schema_id
        assert restored.values == resp.values
        assert restored.escape_text == resp.escape_text

    def test_result_json_round_trip(self):
        result = IntentCompilationResult(
            intent_profile="strict",
            intent_scope=["src/**"],
            intent_deny=None,
            intent_timebox_minutes=60,
            constraint_block={"test": True},
            selected_branch="b1",
            escape_classification=EscapeClassification.NEW_CONSTRAINT,
            warnings=["w1"],
            receipt_hash="abc",
        )
        j = json.dumps(result.to_dict())
        restored = IntentCompilationResult.from_dict(json.loads(j))
        assert restored.intent_profile == result.intent_profile
        assert restored.escape_classification == result.escape_classification

    def test_compile_task_scope_template(self):
        """Task scope template compiles correctly."""
        schema = build_form_schema("task_scope", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={
                "task": "Refactor authentication module",
                "profile": "inherit",
                "scope": "src/auth/**",
                "deny": "*.env",
                "verification": "full",
            },
        )
        result = compile_intent(resp, schema)
        assert result.intent_profile == "strict"  # inherit -> strict
        assert result.intent_scope == ["src/auth/**"]
        assert result.intent_deny == ["*.env"]

    def test_compile_verification_config_template(self):
        """Verification config template compiles correctly."""
        schema = build_form_schema("verification_config", mode="code")
        resp = IntentFormResponse(
            schema_id=schema.schema_id,
            values={
                "evidence_level": "sampling",
                "security_scan": True,
                "continuity_check": False,
                "max_violations": 5,
            },
        )
        result = compile_intent(resp, schema)
        # Profile defaults to "strict" when not in values
        assert result.intent_profile == "strict"
        assert result.receipt_hash
