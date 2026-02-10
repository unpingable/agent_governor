"""Contract tests for v2 intent compiler endpoints.

Verifies that Maude's Intent* models can deserialize Governor's actual
/v2/intent/* responses.  Covers wire compatibility, not just happy path:

  - Template list stability (names + descriptions)
  - Schema determinism (same template → same schema_id)
  - Validation rejects invalid types/ranges/options with structured errors
  - Compilation returns typed fields + receipt hash
  - Policy gating matches governor mode

Governor runs in GOVERNOR_MODE=code → policy=template_only.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


# -- /v2/intent/templates ---------------------------------------------------


async def test_templates_deserialize(client):
    """GET /v2/intent/templates deserializes into IntentTemplateList."""
    result = await client.intent_templates()
    assert len(result.templates) == 3


async def test_template_names_stable(client):
    """Template names are the canonical set: session_start, task_scope, verification_config."""
    result = await client.intent_templates()
    names = sorted(t.name for t in result.templates)
    assert names == ["session_start", "task_scope", "verification_config"]


async def test_templates_have_descriptions(client):
    """Every template has a non-empty description."""
    result = await client.intent_templates()
    for t in result.templates:
        assert isinstance(t.description, str)
        assert len(t.description) > 0, f"Template {t.name} has empty description"


# -- /v2/intent/schema/{template} -------------------------------------------


async def test_schema_session_start_deserializes(client):
    """GET /v2/intent/schema/session_start returns valid IntentFormSchema."""
    schema = await client.intent_schema("session_start")
    assert schema.template_name == "session_start"
    assert schema.schema_id  # non-empty
    assert len(schema.fields) == 4


async def test_schema_task_scope_deserializes(client):
    """GET /v2/intent/schema/task_scope returns valid IntentFormSchema."""
    schema = await client.intent_schema("task_scope")
    assert schema.template_name == "task_scope"
    assert len(schema.fields) == 5


async def test_schema_verification_config_deserializes(client):
    """GET /v2/intent/schema/verification_config returns valid IntentFormSchema."""
    schema = await client.intent_schema("verification_config")
    assert schema.template_name == "verification_config"
    assert len(schema.fields) == 4


async def test_schema_is_deterministic(client):
    """Same template → same schema_id (content-addressed)."""
    s1 = await client.intent_schema("session_start")
    s2 = await client.intent_schema("session_start")
    assert s1.schema_id == s2.schema_id
    assert len(s1.schema_id) == 64  # SHA-256 hex


async def test_schema_has_branches(client):
    """session_start schema includes hypothesis branches with confidence."""
    schema = await client.intent_schema("session_start")
    assert len(schema.branches) >= 2
    for branch in schema.branches:
        assert isinstance(branch.branch_id, str)
        assert isinstance(branch.name, str)
        assert isinstance(branch.confidence, float)
        assert 0.0 <= branch.confidence <= 1.0


async def test_schema_fields_have_required_attrs(client):
    """Every field has field_id, widget, label, required."""
    schema = await client.intent_schema("session_start")
    for f in schema.fields:
        assert isinstance(f.field_id, str)
        assert isinstance(f.widget, str)
        assert isinstance(f.label, str)
        assert isinstance(f.required, bool)


async def test_schema_select_fields_have_options(client):
    """Fields with widget=select_one have a non-empty options list."""
    schema = await client.intent_schema("session_start")
    select_fields = [f for f in schema.fields if f.widget == "select_one"]
    assert len(select_fields) > 0, "Expected at least one select_one field"
    for f in select_fields:
        assert f.options is not None
        assert len(f.options) > 0
        for opt in f.options:
            assert isinstance(opt.value, str)
            assert isinstance(opt.label, str)
            assert isinstance(opt.confidence, float)


async def test_schema_mode_matches_governor(client):
    """Schema mode reflects the governor's running mode."""
    schema = await client.intent_schema("session_start")
    # Governor runs in GOVERNOR_MODE=code
    assert schema.mode == "code"


async def test_schema_unknown_template_404(client):
    """Unknown template name returns 404 in template_only mode."""
    import httpx
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client.intent_schema("nonexistent_template_xyz")
    assert exc_info.value.response.status_code == 404


# -- /v2/intent/validate ----------------------------------------------------


async def test_validate_valid_response(client):
    """Valid values → valid=True, errors=[]."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_validate(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general"},
    )
    assert result.valid is True
    assert result.errors == []


async def test_validate_invalid_option_value(client):
    """Invalid select_one value → valid=False with structured error."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_validate(
        schema_id=schema.schema_id,
        values={"profile": "nonexistent_profile_xyz", "mode": "general"},
    )
    assert result.valid is False
    assert len(result.errors) > 0
    # Error should mention the offending field
    assert any("profile" in e.lower() for e in result.errors)


async def test_validate_unknown_schema_id(client):
    """Unknown schema_id → valid=False with 'not found' error."""
    result = await client.intent_validate(
        schema_id="bogus_schema_id_that_does_not_exist",
        values={"profile": "strict"},
    )
    assert result.valid is False
    assert len(result.errors) > 0
    assert any("not found" in e.lower() for e in result.errors)


async def test_validate_missing_required_field(client):
    """Missing required field → valid=False."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_validate(
        schema_id=schema.schema_id,
        values={},  # empty — missing required fields
    )
    assert result.valid is False


async def test_validate_returns_structured_errors(client):
    """Errors are strings, not opaque blobs."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_validate(
        schema_id=schema.schema_id,
        values={"profile": "bogus_value"},
    )
    assert result.valid is False
    for error in result.errors:
        assert isinstance(error, str)
        assert len(error) > 0


# -- /v2/intent/compile -----------------------------------------------------


async def test_compile_session_start(client):
    """Compile session_start → IntentCompilationResult with profile + receipt hash."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general"},
        template_name="session_start",
    )
    assert result.intent_profile == "strict"
    assert isinstance(result.receipt_hash, str)
    assert len(result.receipt_hash) == 64  # SHA-256 hex


async def test_compile_with_scope(client):
    """Scope field compiles to intent_scope list."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general", "scope": "src/**,tests/**"},
        template_name="session_start",
    )
    assert result.intent_scope == ["src/**", "tests/**"]


async def test_compile_with_timebox(client):
    """Timebox field compiles to intent_timebox_minutes."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general", "timebox": 90},
        template_name="session_start",
    )
    assert result.intent_timebox_minutes == 90


async def test_compile_with_escape_text(client):
    """Escape text → escape_classification field populated."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general"},
        template_name="session_start",
        escape_text="allow exception for testing",
    )
    assert result.escape_classification is not None
    assert isinstance(result.escape_classification, str)
    assert result.escape_classification == "waiver_candidate"


async def test_compile_receipt_hash_deterministic(client):
    """Same inputs → same receipt_hash (content-addressed)."""
    schema = await client.intent_schema("session_start")
    values = {"profile": "strict", "mode": "general"}
    r1 = await client.intent_compile(
        schema_id=schema.schema_id, values=values, template_name="session_start",
    )
    r2 = await client.intent_compile(
        schema_id=schema.schema_id, values=values, template_name="session_start",
    )
    assert r1.receipt_hash == r2.receipt_hash


async def test_compile_receipt_hash_changes_with_input(client):
    """Different inputs → different receipt_hash."""
    schema = await client.intent_schema("session_start")
    r1 = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general"},
        template_name="session_start",
    )
    r2 = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "permissive", "mode": "general"},
        template_name="session_start",
    )
    assert r1.receipt_hash != r2.receipt_hash


async def test_compile_task_scope_template(client):
    """Compile task_scope template — cross-template wire check."""
    schema = await client.intent_schema("task_scope")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"task": "Refactor auth module", "verification": "full"},
        template_name="task_scope",
    )
    assert isinstance(result.intent_profile, str)
    assert isinstance(result.receipt_hash, str)
    assert len(result.receipt_hash) == 64


async def test_compile_verification_config_template(client):
    """Compile verification_config template — cross-template wire check."""
    schema = await client.intent_schema("verification_config")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={
            "evidence_level": "full",
            "security_scan": True,
            "continuity_check": True,
            "max_violations": 3,
        },
        template_name="verification_config",
    )
    assert isinstance(result.receipt_hash, str)
    assert len(result.receipt_hash) == 64


async def test_compile_unknown_template_400(client):
    """Compiling with unknown template → 400."""
    import httpx
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await client.intent_compile(
            schema_id="x", values={}, template_name="nonexistent",
        )
    assert exc_info.value.response.status_code == 400


async def test_compile_all_result_fields_typed(client):
    """IntentCompilationResult fields have expected types."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general", "scope": "src/**"},
        template_name="session_start",
    )
    assert isinstance(result.intent_profile, str)
    assert result.intent_scope is None or isinstance(result.intent_scope, list)
    assert result.intent_deny is None or isinstance(result.intent_deny, list)
    assert result.intent_timebox_minutes is None or isinstance(result.intent_timebox_minutes, int)
    assert result.constraint_block is None or isinstance(result.constraint_block, dict)
    assert result.selected_branch is None or isinstance(result.selected_branch, str)
    assert result.escape_classification is None or isinstance(result.escape_classification, str)
    assert isinstance(result.warnings, list)
    assert isinstance(result.receipt_hash, str)


async def test_compile_selected_branch_present(client):
    """Compilation selects a branch (or None) from the schema."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general"},
        template_name="session_start",
    )
    # selected_branch should be None or one of the branch IDs
    if result.selected_branch is not None:
        branch_ids = [b.branch_id for b in schema.branches]
        assert result.selected_branch in branch_ids


# -- /v2/intent/policy ------------------------------------------------------


async def test_policy_deserializes(client):
    """GET /v2/intent/policy returns valid IntentPolicy."""
    policy = await client.intent_policy()
    assert isinstance(policy.mode, str)
    assert isinstance(policy.policy, str)


async def test_policy_code_mode_is_template_only(client):
    """Governor in code mode → policy=template_only (authoritative gating)."""
    policy = await client.intent_policy()
    assert policy.mode == "code"
    assert policy.policy == "template_only"


async def test_policy_values_in_allowed_set(client):
    """Policy value is one of the three defined policies."""
    policy = await client.intent_policy()
    assert policy.policy in ("template_only", "validated_custom", "custom_ok")


# -- Cross-endpoint consistency ---------------------------------------------


async def test_schema_policy_matches_policy_endpoint(client):
    """Schema.policy matches the standalone /policy endpoint."""
    schema = await client.intent_schema("session_start")
    policy = await client.intent_policy()
    assert schema.policy == policy.policy
    assert schema.mode == policy.mode


async def test_schema_id_round_trips_through_validate(client):
    """schema_id from schema endpoint works in validate endpoint."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_validate(
        schema_id=schema.schema_id,
        values={"profile": "strict"},
    )
    # Should not get "schema not found" — it should validate the values
    schema_not_found = any("not found" in e.lower() for e in result.errors)
    assert not schema_not_found, "schema_id from schema endpoint rejected by validate"


async def test_schema_id_round_trips_through_compile(client):
    """schema_id from schema endpoint works in compile endpoint."""
    schema = await client.intent_schema("session_start")
    result = await client.intent_compile(
        schema_id=schema.schema_id,
        values={"profile": "strict", "mode": "general"},
        template_name="session_start",
    )
    # If schema_id was rejected we'd get an error, not a valid profile
    assert result.intent_profile == "strict"
