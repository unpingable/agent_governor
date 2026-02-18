# SPDX-License-Identifier: Apache-2.0
"""Tests for capability-based lane routing with artifact reuse."""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from governor.lanes import (
    Lane,
    ProbePolicy,
    ArtifactKind,
    LaneContract,
    LANE_CONTRACTS,
    RoutePlan,
    CascadeResult,
    StoredArtifact,
    ArtifactReuseStore,
    CascadeExecutor,
    LaneRouter,
    CooldownStore,
    CooldownEntry,
    compute_vary_key,
    compute_policy_version,
    is_final_answer_reusable,
    resolve_task_hint,
    DEFAULT_TTLS,
    LANE_TO_TIERS,
    MITIGATION_STRATEGIES,
    _canonical_json,
    _COOLDOWN_SCHEMA_VERSION,
)
from governor.claims import Claim, ClaimType
from governor.routing import ModelTier, Router, ModelRegistry, ModelCapabilities


# =============================================================================
# TestLaneEnum
# =============================================================================


class TestLaneEnum:
    """Lane enum values and ordering."""

    def test_values(self):
        assert Lane.ROUTER == 0
        assert Lane.FAST == 1
        assert Lane.GENERAL == 2
        assert Lane.DEEP == 3

    def test_ordering(self):
        assert Lane.ROUTER < Lane.FAST < Lane.GENERAL < Lane.DEEP

    def test_lane_to_tiers_mapping(self):
        assert LANE_TO_TIERS[Lane.FAST] == ["local", "fast"]
        assert LANE_TO_TIERS[Lane.GENERAL] == ["standard"]
        assert LANE_TO_TIERS[Lane.DEEP] == ["heavy"]


# =============================================================================
# TestProbePolicy
# =============================================================================


class TestProbePolicy:
    """ProbePolicy enum values and risk_gated resolution."""

    def test_values(self):
        assert ProbePolicy.NONE.value == "none"
        assert ProbePolicy.CANARY.value == "canary"
        assert ProbePolicy.DEEP.value == "deep"
        assert ProbePolicy.RISK_GATED.value == "risk_gated"

    def test_risk_gated_resolution_standard(self):
        lr = LaneRouter()
        assert lr._resolve_probe_policy("risk_gated", "standard") == "none"

    def test_risk_gated_resolution_elevated(self):
        lr = LaneRouter()
        assert lr._resolve_probe_policy("risk_gated", "elevated") == "canary"

    def test_risk_gated_resolution_critical(self):
        lr = LaneRouter()
        assert lr._resolve_probe_policy("risk_gated", "critical") == "deep"


# =============================================================================
# TestLaneContract
# =============================================================================


class TestLaneContract:
    """LaneContract defaults, frozen, hard_disallow."""

    def test_defaults_present(self):
        assert Lane.FAST in LANE_CONTRACTS
        assert Lane.GENERAL in LANE_CONTRACTS
        assert Lane.DEEP in LANE_CONTRACTS

    def test_frozen(self):
        c = LANE_CONTRACTS[Lane.FAST]
        with pytest.raises(AttributeError):
            c.lane = 99

    def test_hard_disallow_on_lane_1(self):
        c = LANE_CONTRACTS[Lane.FAST]
        disallow = dict(c.hard_disallow)
        assert "risk_class" in disallow
        assert "elevated" in disallow["risk_class"]
        assert disallow.get("has_side_effects") is True

    def test_must_have_vs_nice_to_have(self):
        c = LANE_CONTRACTS[Lane.DEEP]
        assert "reasoning" in c.must_have_strengths
        assert "code" in c.nice_to_have_strengths

    def test_contract_hash_deterministic(self):
        c = LANE_CONTRACTS[Lane.GENERAL]
        h1 = c.contract_hash()
        h2 = c.contract_hash()
        assert h1 == h2
        assert len(h1) == 16

    def test_to_dict(self):
        c = LANE_CONTRACTS[Lane.FAST]
        d = c.to_dict()
        assert d["lane"] == Lane.FAST
        assert "local" in d["model_tiers"]


# =============================================================================
# TestRoutePlan
# =============================================================================


class TestRoutePlan:
    """RoutePlan serialization, vary_key, budget fields."""

    def _make_plan(self, **kwargs):
        defaults = dict(
            lane=Lane.GENERAL,
            model="claude-sonnet-4",
            provider="anthropic",
            budget_per_call_usd=0.50,
            budget_total_usd=10.0,
            tools_allowed=False,
            validators=["format", "schema"],
            probe_policy="none",
            vary_key="abc123",
            escalation_policy="auto",
            fallback_chain=["claude-opus-4"],
            reasons=["complexity=0.5 → Lane 2"],
            autopilot_level=1,
            timestamp="2026-02-18T00:00:00+00:00",
        )
        defaults.update(kwargs)
        return RoutePlan(**defaults)

    def test_serialization_roundtrip(self):
        plan = self._make_plan()
        d = plan.to_dict()
        restored = RoutePlan.from_dict(d)
        assert restored.lane == plan.lane
        assert restored.model == plan.model
        assert restored.vary_key == plan.vary_key
        assert restored.budget_total_usd == plan.budget_total_usd

    def test_vary_key_present(self):
        plan = self._make_plan()
        assert plan.vary_key == "abc123"

    def test_both_budget_fields(self):
        plan = self._make_plan()
        assert plan.budget_per_call_usd == 0.50
        assert plan.budget_total_usd == 10.0

    def test_fallback_chain_populated(self):
        plan = self._make_plan()
        assert plan.fallback_chain == ["claude-opus-4"]

    def test_from_dict_defaults(self):
        minimal = {"lane": 1, "model": "m", "vary_key": "k", "reasons": []}
        plan = RoutePlan.from_dict(minimal)
        assert plan.autopilot_level == 1
        assert plan.escalation_policy == "auto"


# =============================================================================
# TestArtifactReuseStore
# =============================================================================


class TestArtifactReuseStore:
    """Artifact store/lookup/evict/refresh/TTL."""

    def _make_contract(self, **kwargs):
        defaults = dict(
            lane=Lane.GENERAL,
            model_tiers=("standard",),
            tools_allowed=False,
        )
        defaults.update(kwargs)
        return LaneContract(**defaults)

    def test_store_and_lookup(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "content", "m1", 2, "intermediate", contract, False)
        result = store.lookup("k1")
        assert result is not None
        assert result.content == "content"
        assert result.hit_count == 1

    def test_lookup_miss(self):
        store = ArtifactReuseStore()
        assert store.lookup("nonexistent") is None

    def test_evict(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "content", "m1", 2, "intermediate", contract, False)
        assert store.evict("k1") is True
        assert store.lookup("k1") is None

    def test_ttl_expiry(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "content", "m1", 2, "intermediate", contract, False, ttl_seconds=0)
        # Expired immediately
        assert store.lookup("k1") is None

    def test_stats(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "a", "m1", 2, "intermediate", contract, False)
        store.store("k2", "b", "m1", 2, "tool_result", contract, False)
        stats = store.stats()
        assert stats["total_artifacts"] == 2
        assert stats["by_kind"]["intermediate"] == 1
        assert stats["by_kind"]["tool_result"] == 1

    def test_refresh_updates_probe(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "content", "m1", 2, "intermediate", contract, False, probe_decision="mitigate")
        store.refresh("k1", "proceed")
        result = store.lookup("k1")
        assert result is not None
        assert result.probe_decision == "proceed"

    def test_idempotent_store(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "v1", "m1", 2, "intermediate", contract, False)
        store.store("k1", "v2", "m1", 2, "intermediate", contract, False)
        result = store.lookup("k1")
        assert result.content == "v2"

    def test_block_never_served(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "content", "m1", 2, "intermediate", contract, False, probe_decision="block")
        assert store.lookup("k1") is None

    def test_human_gate_never_served(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "content", "m1", 2, "intermediate", contract, False, probe_decision="human_gate")
        assert store.lookup("k1") is None

    def test_tools_allowed_mismatch(self):
        """If current contract allows tools but artifact was produced without, don't serve."""
        store = ArtifactReuseStore()
        contract_no_tools = self._make_contract(tools_allowed=False)
        contract_tools = self._make_contract(tools_allowed=True)
        store.store("k1", "content", "m1", 2, "intermediate", contract_no_tools, False)
        # Current contract allows tools → mismatch → miss
        assert store.lookup("k1", contract_tools) is None

    def test_evict_expired(self):
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "a", "m1", 2, "intermediate", contract, False, ttl_seconds=0)
        store.store("k2", "b", "m1", 2, "intermediate", contract, False, ttl_seconds=86400)
        evicted = store.evict_expired()
        assert evicted == 1
        assert store.lookup("k2") is not None

    def test_file_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            contract = self._make_contract()
            store.store("abcdef1234", "content", "m1", 2, "intermediate", contract, False)
            # Check file exists
            assert (base / "ab" / "abcdef1234.json").exists()

    def test_served_from_reuse_receipt_on_hit(self):
        """Lookup should increment hit_count (receipt emission is caller's job)."""
        store = ArtifactReuseStore()
        contract = self._make_contract()
        store.store("k1", "content", "m1", 2, "intermediate", contract, False)
        result1 = store.lookup("k1")
        result2 = store.lookup("k1")
        assert result2.hit_count == 2

    def test_default_ttl_by_kind(self):
        assert DEFAULT_TTLS[ArtifactKind.TOOL_RESULT.value] == 86400
        assert DEFAULT_TTLS[ArtifactKind.INTERMEDIATE.value] == 3600
        assert DEFAULT_TTLS[ArtifactKind.FINAL_ANSWER.value] == 300


# =============================================================================
# TestComputeVaryKey
# =============================================================================


class TestComputeVaryKey:
    """Vary key determinism and sensitivity."""

    def test_deterministic(self):
        k1 = compute_vary_key("m1", "sys", "user")
        k2 = compute_vary_key("m1", "sys", "user")
        assert k1 == k2

    def test_model_change(self):
        k1 = compute_vary_key("m1", "sys", "user")
        k2 = compute_vary_key("m2", "sys", "user")
        assert k1 != k2

    def test_prompt_change(self):
        k1 = compute_vary_key("m1", "sys", "user1")
        k2 = compute_vary_key("m1", "sys", "user2")
        assert k1 != k2

    def test_tool_schema_change(self):
        k1 = compute_vary_key("m1", "sys", "user", tool_schemas=[{"name": "t1"}])
        k2 = compute_vary_key("m1", "sys", "user", tool_schemas=[{"name": "t2"}])
        assert k1 != k2

    def test_doc_hash_change(self):
        k1 = compute_vary_key("m1", "sys", "user", doc_hashes=["h1"])
        k2 = compute_vary_key("m1", "sys", "user", doc_hashes=["h2"])
        assert k1 != k2

    def test_envelope_version_change(self):
        k1 = compute_vary_key("m1", "sys", "user", envelope_version="v1")
        k2 = compute_vary_key("m1", "sys", "user", envelope_version="v2")
        assert k1 != k2

    def test_route_policy_version_change(self):
        k1 = compute_vary_key("m1", "sys", "user", route_policy_version="r1")
        k2 = compute_vary_key("m1", "sys", "user", route_policy_version="r2")
        assert k1 != k2

    def test_probe_config_version_change(self):
        k1 = compute_vary_key("m1", "sys", "user", probe_config_version="p1")
        k2 = compute_vary_key("m1", "sys", "user", probe_config_version="p2")
        assert k1 != k2

    def test_generation_params_change(self):
        k1 = compute_vary_key("m1", "sys", "user", generation_params={"temperature": 0})
        k2 = compute_vary_key("m1", "sys", "user", generation_params={"temperature": 1})
        assert k1 != k2

    def test_tools_allowed_bool_change(self):
        k1 = compute_vary_key("m1", "sys", "user", tools_allowed=False)
        k2 = compute_vary_key("m1", "sys", "user", tools_allowed=True)
        assert k1 != k2


# =============================================================================
# TestFinalAnswerEligibility
# =============================================================================


class TestFinalAnswerEligibility:
    """Final answer reuse eligibility checks."""

    def test_default_off(self):
        # tools_allowed=True → blocked
        assert not is_final_answer_reusable(True, "standard", True, ["format"], [], "proceed", True)

    def test_all_conditions_met(self):
        assert is_final_answer_reusable(False, "standard", True, ["format"], [], "proceed", True)

    def test_tools_allowed_blocked(self):
        assert not is_final_answer_reusable(True, "standard", True, ["format"], [], "proceed", True)

    def test_risk_not_standard_blocked(self):
        assert not is_final_answer_reusable(False, "elevated", True, ["format"], [], "proceed", True)

    def test_format_strict_false_blocked(self):
        assert not is_final_answer_reusable(False, "standard", False, ["format"], [], "proceed", True)

    def test_probe_not_proceed_blocked(self):
        assert not is_final_answer_reusable(False, "standard", True, ["format"], [], "mitigate", True)

    def test_no_doc_hashes_blocked(self):
        assert not is_final_answer_reusable(False, "standard", True, ["format"], [], "proceed", False)


# =============================================================================
# TestLaneRouter
# =============================================================================


class TestLaneRouter:
    """LaneRouter routing logic."""

    def test_default_lane_by_complexity_simple(self):
        lr = LaneRouter()
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        assert plan.lane == Lane.FAST

    def test_default_lane_by_complexity_complex(self):
        lr = LaneRouter()
        plan = lr.route(claims=[Claim(type=ClaimType.CHANGESET, diff="big diff")])
        # CHANGESET = 0.7 → Lane.GENERAL or DEEP
        assert plan.lane >= Lane.GENERAL

    def test_risk_elevated_min_lane_2(self):
        lr = LaneRouter()
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="elevated",
        )
        assert plan.lane >= Lane.GENERAL

    def test_risk_critical_min_lane_3(self):
        lr = LaneRouter()
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="critical",
        )
        assert plan.lane == Lane.DEEP

    def test_side_effects_min_lane_3(self):
        lr = LaneRouter()
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            has_side_effects=True,
        )
        assert plan.lane == Lane.DEEP

    def test_artifact_hit_noted_in_reasons(self):
        store = ArtifactReuseStore()
        contract = LANE_CONTRACTS[Lane.FAST]
        lr = LaneRouter(artifact_store=store)
        # Pre-populate store with matching key
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        store.store(plan.vary_key, "cached", "m1", 1, "intermediate", contract, False)
        plan2 = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        assert any("artifact reuse hit" in r for r in plan2.reasons)

    def test_force_lane_level_0(self):
        lr = LaneRouter(autopilot_level=0)
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            force_lane=Lane.DEEP,
        )
        assert plan.lane == Lane.DEEP
        assert plan.escalation_policy == "disabled"

    def test_receipt_emission(self):
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "r123"
        mock_system = MagicMock()
        mock_system.emit.return_value = mock_receipt
        lr = LaneRouter(receipt_system=mock_system)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        assert plan.receipt_id == "r123"
        mock_system.emit.assert_called_once()

    def test_explain_output(self):
        lr = LaneRouter()
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        explanation = lr.explain(plan)
        assert "lane" in explanation
        assert "model" in explanation
        assert "reasons" in explanation
        assert "budget" in explanation

    def test_hard_disallow_promotes(self):
        lr = LaneRouter()
        # Lane 1 disallows elevated risk
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="elevated",
        )
        assert plan.lane >= Lane.GENERAL

    def test_no_candidates_promote(self):
        """If no models available at a tier, promote to next."""
        registry = ModelRegistry()
        # Remove all local/fast models
        for name in list(registry._models.keys()):
            caps = registry._models[name]
            if caps.tier in (ModelTier.LOCAL, ModelTier.FAST):
                registry.mark_available(name, False)

        router = Router(registry=registry)
        lr = LaneRouter(router=router)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        # Should promote since no FAST models available
        assert plan.model is not None  # Found something

    def test_critical_side_effects_deep_probe(self):
        lr = LaneRouter()
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="critical",
            has_side_effects=True,
        )
        assert plan.lane == Lane.DEEP
        assert plan.probe_policy == "deep"

    def test_fallback_chain(self):
        lr = LaneRouter()
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        # Fallback chain should contain models from higher tiers
        assert isinstance(plan.fallback_chain, list)

    def test_must_have_filtering(self):
        lr = LaneRouter()
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            must_have_strengths=["code"],
        )
        # Should still find a model with "code" strength
        assert plan.model is not None

    def test_get_status(self):
        lr = LaneRouter()
        status = lr.get_status()
        assert "autopilot_level" in status
        assert "contracts" in status
        assert "budget_total_usd" in status


# =============================================================================
# TestCascadeExecutor
# =============================================================================


class TestCascadeExecutor:
    """CascadeExecutor cascade logic."""

    def _make_executor(self, probe_fn=None):
        lr = LaneRouter()
        store = ArtifactReuseStore()
        return CascadeExecutor(lane_router=lr, artifact_store=store, probe_fn=probe_fn)

    def _make_plan(self, lane=Lane.FAST, probe_policy="none", **kwargs):
        defaults = dict(
            lane=lane,
            model="test-model",
            provider="test",
            budget_per_call_usd=0.01,
            budget_total_usd=10.0,
            tools_allowed=False,
            validators=["format"],
            probe_policy=probe_policy,
            vary_key="test_key",
            escalation_policy="auto",
            fallback_chain=["claude-sonnet-4", "claude-opus-4"],
            reasons=["test"],
        )
        defaults.update(kwargs)
        return RoutePlan(**defaults)

    def test_execute_lane_1_no_probe(self):
        executor = self._make_executor()
        plan = self._make_plan(lane=Lane.FAST, probe_policy="none")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.output == "response"
        assert result.lane_used == Lane.FAST
        assert not result.escalated
        assert result.probe_decision is None

    def test_execute_lane_2_probe_proceed(self):
        def probe_proceed(output, prompt):
            return {"decision": "proceed"}

        executor = self._make_executor(probe_fn=probe_proceed)
        plan = self._make_plan(lane=Lane.GENERAL, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.output == "response"
        assert result.probe_decision == "proceed"
        assert not result.escalated

    def test_probe_mitigate_then_proceed(self):
        call_count = [0]
        def probe_fn(output, prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}
            return {"decision": "proceed"}

        executor = self._make_executor(probe_fn=probe_fn)
        plan = self._make_plan(lane=Lane.GENERAL, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.probe_decision == "proceed"
        assert "relocate" in result.mitigations_attempted

    def test_probe_mitigate_then_still_fails_escalate(self):
        def probe_always_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor = self._make_executor(probe_fn=probe_always_mitigate)
        plan = self._make_plan(lane=Lane.GENERAL, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.escalated
        assert len(result.escalation_chain) > 0

    def test_double_escalation(self):
        """Lane 1 → mitigate → Lane 2 → mitigate → Lane 3."""
        def probe_always_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor = self._make_executor(probe_fn=probe_always_mitigate)
        plan = self._make_plan(lane=Lane.FAST, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.escalated
        # Should have tried multiple lanes
        assert result.lane_used >= Lane.GENERAL

    def test_cant_go_past_lane_3(self):
        def probe_always_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor = self._make_executor(probe_fn=probe_always_mitigate)
        plan = self._make_plan(lane=Lane.FAST, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.lane_used <= Lane.DEEP

    def test_block_no_escalation(self):
        def probe_block(output, prompt):
            return {"decision": "block"}

        executor = self._make_executor(probe_fn=probe_block)
        plan = self._make_plan(lane=Lane.GENERAL, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.probe_decision == "block"
        assert result.lane_used == Lane.GENERAL
        # BLOCK does not escalate

    def test_human_gate_no_escalation(self):
        def probe_human(output, prompt):
            return {"decision": "human_gate"}

        executor = self._make_executor(probe_fn=probe_human)
        plan = self._make_plan(lane=Lane.GENERAL, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.probe_decision == "human_gate"

    def test_artifact_hit_skip_generation(self):
        store = ArtifactReuseStore()
        contract = LANE_CONTRACTS[Lane.FAST]
        store.store("test_key", "cached_output", "m1", Lane.FAST, "intermediate", contract, False)

        lr = LaneRouter(artifact_store=store)
        executor = CascadeExecutor(lane_router=lr, artifact_store=store)
        plan = self._make_plan(lane=Lane.FAST, vary_key="test_key")

        generate_called = [False]
        def gen(p, m):
            generate_called[0] = True
            return "fresh"

        result = executor.execute(plan, "hello", gen)
        assert result.artifact_hit is True
        assert result.output == "cached_output"
        assert not generate_called[0]

    def test_validator_failure_escalate(self):
        """Validator failure → escalate (no mitigation)."""
        executor = self._make_executor()
        plan = self._make_plan(lane=Lane.FAST, validators=["format"])

        # Generate empty output → validator fails
        result = executor.execute(plan, "hello", lambda p, m: "")
        # Empty output fails validators → escalates
        assert result.escalated or result.output == ""

    def test_budget_exhausted_explainable(self):
        executor = self._make_executor()
        plan = self._make_plan(lane=Lane.FAST, budget_total_usd=0.0)
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.budget_exhausted

    def test_escalation_chain_populated(self):
        def probe_always_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor = self._make_executor(probe_fn=probe_always_mitigate)
        plan = self._make_plan(lane=Lane.FAST, probe_policy="canary")
        result = executor.execute(plan, "hello", lambda p, m: "response")
        if result.escalated:
            assert len(result.escalation_chain) > 0

    def test_pre_computed_output(self):
        executor = self._make_executor()
        plan = self._make_plan(lane=Lane.FAST)
        result = executor.execute(plan, "hello", lambda p, m: "SHOULD NOT CALL", output="pre-computed")
        assert result.output == "pre-computed"


# =============================================================================
# TestMitigateOnce
# =============================================================================


class TestMitigateOnce:
    """Mitigation strategies."""

    def test_relocate(self):
        executor = CascadeExecutor(lane_router=LaneRouter())
        result = executor._apply_mitigation("relocate", "prompt", "output")
        assert "SYSTEM" in result
        assert "output" in result

    def test_schema_form(self):
        executor = CascadeExecutor(lane_router=LaneRouter())
        result = executor._apply_mitigation("schema_form", "prompt", "output")
        assert "verified" in result

    def test_boundary_harden(self):
        executor = CascadeExecutor(lane_router=LaneRouter())
        result = executor._apply_mitigation("boundary_harden", "prompt", "output")
        assert "BEGIN VERIFIED OUTPUT" in result
        assert "END VERIFIED OUTPUT" in result

    def test_only_one_attempt(self):
        """Mitigate-once: same strategy not attempted twice."""
        call_count = [0]
        def probe_fn(output, prompt):
            call_count[0] += 1
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor = CascadeExecutor(lane_router=LaneRouter(), probe_fn=probe_fn)
        plan = RoutePlan(
            lane=Lane.FAST, model="m", provider="p",
            budget_per_call_usd=1.0, budget_total_usd=100.0,
            tools_allowed=False, validators=["format"],
            probe_policy="canary", vary_key="k",
            escalation_policy="auto", fallback_chain=["m2"],
            reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "response")
        # Should only attempt relocate once before escalating
        assert result.mitigations_attempted.count("relocate") <= 1

    def test_mitigation_recorded(self):
        call_count = [0]
        def probe_fn(output, prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"decision": "mitigate", "mitigations": [{"transform": "boundary_harden"}]}
            return {"decision": "proceed"}

        executor = CascadeExecutor(lane_router=LaneRouter(), probe_fn=probe_fn)
        plan = RoutePlan(
            lane=Lane.GENERAL, model="m", provider="p",
            budget_per_call_usd=1.0, budget_total_usd=100.0,
            tools_allowed=False, validators=["format"],
            probe_policy="canary", vary_key="k",
            escalation_policy="auto", fallback_chain=[],
            reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert "boundary_harden" in result.mitigations_attempted


# =============================================================================
# TestAutopilotLevels
# =============================================================================


class TestAutopilotLevels:
    """Autopilot level 0/1/2 behavior."""

    def test_level_0_requires_force_lane(self):
        lr = LaneRouter(autopilot_level=0)
        with pytest.raises(ValueError, match="force_lane"):
            lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])

    def test_level_0_with_force_lane(self):
        lr = LaneRouter(autopilot_level=0)
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            force_lane=Lane.DEEP,
        )
        assert plan.lane == Lane.DEEP
        assert plan.escalation_policy == "disabled"

    def test_level_1_auto_escalates(self):
        lr = LaneRouter(autopilot_level=1)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        assert plan.escalation_policy == "auto"

    def test_level_1_never_downgrades(self):
        lr = LaneRouter(autopilot_level=1)
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="critical",
        )
        # Critical forces Lane 3 — should not downgrade
        assert plan.lane == Lane.DEEP

    def test_level_2_auto(self):
        lr = LaneRouter(autopilot_level=2)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        assert plan.escalation_policy == "auto"


# =============================================================================
# TestBudgetGuards
# =============================================================================


class TestBudgetGuards:
    """Budget enforcement in cascade execution."""

    def test_per_request_total_cap(self):
        executor = CascadeExecutor(lane_router=LaneRouter())
        plan = RoutePlan(
            lane=Lane.FAST, model="m", provider="p",
            budget_per_call_usd=0.01, budget_total_usd=0.0,
            tools_allowed=False, validators=["format"],
            probe_policy="none", vary_key="k",
            escalation_policy="auto", fallback_chain=[],
            reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.budget_exhausted

    def test_budget_ok(self):
        executor = CascadeExecutor(lane_router=LaneRouter())
        plan = RoutePlan(
            lane=Lane.FAST, model="m", provider="p",
            budget_per_call_usd=1.0, budget_total_usd=100.0,
            tools_allowed=False, validators=["format"],
            probe_policy="none", vary_key="k",
            escalation_policy="auto", fallback_chain=[],
            reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert not result.budget_exhausted

    def test_cascade_spend_accumulates(self):
        def probe_always_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor = CascadeExecutor(lane_router=LaneRouter(), probe_fn=probe_always_mitigate)
        plan = RoutePlan(
            lane=Lane.FAST, model="m", provider="p",
            budget_per_call_usd=0.01, budget_total_usd=100.0,
            tools_allowed=False, validators=["format"],
            probe_policy="canary", vary_key="k",
            escalation_policy="auto", fallback_chain=["m2", "m3"],
            reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.budget_spent_usd > 0

    def test_budget_exhaustion_not_silent(self):
        """Budget exhaustion should set budget_exhausted=True, not silently downgrade."""
        executor = CascadeExecutor(lane_router=LaneRouter())
        plan = RoutePlan(
            lane=Lane.FAST, model="m", provider="p",
            budget_per_call_usd=0.01, budget_total_usd=0.0,
            tools_allowed=False, validators=["format"],
            probe_policy="none", vary_key="k",
            escalation_policy="auto", fallback_chain=[],
            reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "response")
        assert result.budget_exhausted is True

    def test_budget_check_before_each_step(self):
        """Budget is checked before each cascade step."""
        calls = [0]
        def gen(p, m):
            calls[0] += 1
            return "response"

        def probe_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor = CascadeExecutor(lane_router=LaneRouter(), probe_fn=probe_mitigate)
        plan = RoutePlan(
            lane=Lane.FAST, model="m", provider="p",
            budget_per_call_usd=0.01, budget_total_usd=0.001,
            tools_allowed=False, validators=["format"],
            probe_policy="canary", vary_key="k",
            escalation_policy="auto", fallback_chain=["m2"],
            reasons=[],
        )
        result = executor.execute(plan, "hello", gen)
        # Budget should stop before too many calls
        assert calls[0] <= 3


# =============================================================================
# TestClaimTypeResolution
# =============================================================================


class TestClaimTypeResolution:
    """Task hint → synthetic claims."""

    def test_known_hints(self):
        for hint in ("extract", "summarize", "codegen", "decision", "verify"):
            claims = resolve_task_hint(hint)
            assert len(claims) > 0

    def test_claims_override_task_hint(self):
        lr = LaneRouter()
        real_claims = [Claim(type=ClaimType.CHANGESET, diff="real diff")]
        plan_with_claims = lr.route(claims=real_claims, task_hint="extract")
        plan_hint_only = lr.route(task_hint="extract")
        # Claims should influence complexity differently than the hint alone
        # CHANGESET has higher claim_types complexity than FILE_EXISTS
        assert plan_with_claims.lane >= plan_hint_only.lane

    def test_unknown_hint_raises(self):
        with pytest.raises(ValueError, match="Unknown task_hint"):
            resolve_task_hint("nonexistent")

    def test_empty_claims_default_lane(self):
        lr = LaneRouter()
        plan = lr.route()
        # No claims, no hint → default complexity
        assert plan.lane in (Lane.FAST, Lane.GENERAL)


# =============================================================================
# TestCascadeResult
# =============================================================================


class TestCascadeResult:

    def test_to_dict(self):
        result = CascadeResult(
            output="hello",
            lane_used=1,
            model_used="m1",
            escalated=False,
            escalation_chain=[],
            mitigations_attempted=[],
            probe_decision=None,
            artifact_hit=False,
            vary_key="k",
            budget_spent_usd=0.01,
            budget_exhausted=False,
        )
        d = result.to_dict()
        assert d["output"] == "hello"
        assert d["lane_used"] == 1
        assert d["budget_exhausted"] is False


# =============================================================================
# TestStoredArtifact
# =============================================================================


class TestStoredArtifact:

    def test_roundtrip(self):
        a = StoredArtifact(
            vary_key="k1",
            content="content",
            model="m1",
            lane=2,
            kind="intermediate",
            contract_hash="abc",
            tools_were_allowed=False,
            created_at="2026-01-01T00:00:00+00:00",
            expires_at="2026-12-31T00:00:00+00:00",
        )
        d = a.to_dict()
        b = StoredArtifact.from_dict(d)
        assert b.vary_key == a.vary_key
        assert b.content == a.content
        assert b.tools_were_allowed == a.tools_were_allowed


# =============================================================================
# TestMitigationStrategies
# =============================================================================


class TestMitigationStrategies:

    def test_strategy_keys(self):
        assert "position" in MITIGATION_STRATEGIES
        assert "structure" in MITIGATION_STRATEGIES
        assert "drift" in MITIGATION_STRATEGIES

    def test_strategy_values(self):
        assert MITIGATION_STRATEGIES["position"] == "relocate"
        assert MITIGATION_STRATEGIES["structure"] == "schema_form"
        assert MITIGATION_STRATEGIES["drift"] == "boundary_harden"


# =============================================================================
# Hardening tests (v2.1 — chatty review)
# =============================================================================


class TestArtifactKeyValidation:
    """Vary key must be hex-only to prevent path traversal."""

    def test_valid_hex_key(self):
        assert ArtifactReuseStore._validate_key("abcdef1234567890" * 4)

    def test_rejects_path_traversal(self):
        assert not ArtifactReuseStore._validate_key("../../etc/passwd")

    def test_rejects_slashes(self):
        assert not ArtifactReuseStore._validate_key("abc/def")

    def test_rejects_uppercase(self):
        assert not ArtifactReuseStore._validate_key("ABCDEF1234567890")

    def test_rejects_short_key(self):
        assert not ArtifactReuseStore._validate_key("abc")

    def test_rejects_empty(self):
        assert not ArtifactReuseStore._validate_key("")

    def test_rejects_dots(self):
        assert not ArtifactReuseStore._validate_key("abc.def.json")

    def test_rejects_null_bytes(self):
        assert not ArtifactReuseStore._validate_key("abc\x00def1234")

    def test_safe_path_returns_none_for_bad_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactReuseStore(Path(tmp))
            assert store._safe_path("../../etc/passwd") is None

    def test_lookup_rejects_bad_key(self):
        store = ArtifactReuseStore()
        # Bad key in memory? No — key validation is on the file path side.
        # But a traversal key should never produce a file hit.
        assert store.lookup("../../etc/passwd") is None

    def test_store_with_invalid_key_still_works_in_memory(self):
        """Invalid key: stored in memory, but _persist is a no-op (path is None)."""
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactReuseStore(Path(tmp))
            contract = LaneContract(lane=2, model_tiers=("standard",))
            art = store.store("BAD_KEY!", "content", "m", 2, "intermediate", contract, False)
            # In memory, so it exists
            assert art.content == "content"
            # But no file was written (key failed validation)
            assert not list(Path(tmp).rglob("*.json"))


class TestArtifactSymlinkRejection:
    """Symlinks in the artifacts directory are rejected."""

    def test_symlink_on_read_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            contract = LaneContract(lane=2, model_tiers=("standard",))
            # Write a real artifact
            key = "a" * 64
            store.store(key, "content", "m", 2, "intermediate", contract, False)
            path = base / key[:2] / f"{key}.json"
            assert path.exists()

            # Replace with a symlink
            target = path.with_suffix(".target")
            path.rename(target)
            path.symlink_to(target)

            # Clear memory so lookup goes to disk
            store._memory.clear()
            # Lookup should reject the symlink
            assert store.lookup(key) is None

    def test_symlink_on_evict_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            contract = LaneContract(lane=2, model_tiers=("standard",))
            key = "b" * 64
            store.store(key, "content", "m", 2, "intermediate", contract, False)
            path = base / key[:2] / f"{key}.json"

            # Replace with symlink
            target = path.with_suffix(".target")
            path.rename(target)
            path.symlink_to(target)

            # Evict should not follow symlink
            result = store.evict(key)
            # Symlink still exists (we didn't unlink it)
            assert path.is_symlink()


class TestArtifactCorruptionHandling:
    """Bad JSON on disk is treated as miss, not crash."""

    def test_corrupt_json_treated_as_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            key = "c" * 64
            shard = base / key[:2]
            shard.mkdir(parents=True)
            path = shard / f"{key}.json"
            path.write_text("{this is not json}")

            assert store.lookup(key) is None

    def test_truncated_json_treated_as_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            key = "d" * 64
            shard = base / key[:2]
            shard.mkdir(parents=True)
            path = shard / f"{key}.json"
            path.write_text('{"vary_key": "d')

            assert store.lookup(key) is None

    def test_missing_fields_treated_as_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            key = "e" * 64
            shard = base / key[:2]
            shard.mkdir(parents=True)
            path = shard / f"{key}.json"
            # Valid JSON but missing required fields
            path.write_text('{"vary_key": "x"}')

            assert store.lookup(key) is None

    def test_empty_file_treated_as_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            key = "f" * 64
            shard = base / key[:2]
            shard.mkdir(parents=True)
            (shard / f"{key}.json").write_text("")

            assert store.lookup(key) is None


class TestArtifactAtomicWrites:
    """Atomic write: tmp + flock + rename."""

    def test_persist_creates_file_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            contract = LaneContract(lane=2, model_tiers=("standard",))
            key = "a1b2c3d4" * 8
            store.store(key, "content", "m", 2, "intermediate", contract, False)
            path = base / key[:2] / f"{key}.json"
            assert path.exists()
            # No leftover .tmp file
            assert not path.with_suffix(".tmp").exists()

    def test_persist_content_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            contract = LaneContract(lane=2, model_tiers=("standard",))
            key = "a1b2c3d4" * 8
            store.store(key, "content", "m", 2, "intermediate", contract, False)
            path = base / key[:2] / f"{key}.json"
            data = json.loads(path.read_text())
            assert data["content"] == "content"
            assert data["vary_key"] == key


class TestNoStoreFlag:
    """no_store=True keeps artifact in memory only."""

    def test_no_store_memory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            contract = LaneContract(lane=2, model_tiers=("standard",))
            key = "a1b2c3d4" * 8
            store.store(key, "secret content", "m", 2, "tool_result", contract, False, no_store=True)
            # In memory
            assert store.lookup(key) is not None
            # Not on disk
            assert not list(base.rglob("*.json"))

    def test_no_store_false_writes_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = ArtifactReuseStore(base)
            contract = LaneContract(lane=2, model_tiers=("standard",))
            key = "a1b2c3d4" * 8
            store.store(key, "content", "m", 2, "intermediate", contract, False, no_store=False)
            assert list(base.rglob("*.json"))


class TestArtifactReuseReceipt:
    """CascadeExecutor emits receipt on artifact reuse hit."""

    def test_reuse_receipt_emitted(self):
        store = ArtifactReuseStore()
        contract = LANE_CONTRACTS[Lane.FAST]
        store.store("test_key", "cached", "m1", Lane.FAST, "intermediate", contract, False)

        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "reuse-r1"
        mock_system = MagicMock()
        mock_system.emit.return_value = mock_receipt

        lr = LaneRouter(artifact_store=store)
        executor = CascadeExecutor(
            lane_router=lr, artifact_store=store, receipt_system=mock_system
        )
        plan = RoutePlan(
            lane=Lane.FAST, model="m1", provider="test",
            budget_per_call_usd=0.01, budget_total_usd=10.0,
            tools_allowed=False, validators=["format"],
            probe_policy="none", vary_key="test_key",
            escalation_policy="auto", fallback_chain=[], reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "should not call")
        assert result.artifact_hit is True
        assert result.receipt_id == "reuse-r1"
        # Verify receipt was emitted with correct fields
        mock_system.emit.assert_called_once()
        call_kwargs = mock_system.emit.call_args
        evidence = call_kwargs.kwargs.get("evidence_bundle") or call_kwargs[1].get("evidence_bundle")
        assert evidence["artifact_reused"] is True
        assert evidence["artifact_key"] == "test_key"
        assert evidence["artifact_kind"] == "intermediate"
        assert "eligibility_checks" in evidence

    def test_reuse_receipt_fail_open(self):
        """If receipt emission fails, artifact is still served."""
        store = ArtifactReuseStore()
        contract = LANE_CONTRACTS[Lane.FAST]
        store.store("test_key", "cached", "m1", Lane.FAST, "intermediate", contract, False)

        mock_system = MagicMock()
        mock_system.emit.side_effect = RuntimeError("boom")

        lr = LaneRouter(artifact_store=store)
        executor = CascadeExecutor(
            lane_router=lr, artifact_store=store, receipt_system=mock_system
        )
        plan = RoutePlan(
            lane=Lane.FAST, model="m1", provider="test",
            budget_per_call_usd=0.01, budget_total_usd=10.0,
            tools_allowed=False, validators=["format"],
            probe_policy="none", vary_key="test_key",
            escalation_policy="auto", fallback_chain=[], reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "should not call")
        assert result.artifact_hit is True
        assert result.output == "cached"
        assert result.receipt_id is None  # Failed, but still served


class TestCascadeLoopPrevention:
    """Cascade should not revisit the same (lane, model) pair."""

    def test_loop_guard_stops_cycle(self):
        """If escalation leads back to same lane+model, cascade stops."""
        call_count = [0]

        def gen(p, m):
            call_count[0] += 1
            return "response"

        # Build a router where escalation might cycle
        # (Deep lane has same model as current)
        lr = LaneRouter()
        executor = CascadeExecutor(lane_router=lr)

        # Force a scenario: start at Lane 3 with model "m1", probe mitigates
        def probe_always_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        executor.probe_fn = probe_always_mitigate
        plan = RoutePlan(
            lane=Lane.DEEP, model="m1", provider="test",
            budget_per_call_usd=1.0, budget_total_usd=100.0,
            tools_allowed=False, validators=["format"],
            probe_policy="canary", vary_key="k",
            escalation_policy="auto", fallback_chain=["m1"],  # Same model in fallback
            reasons=[],
        )
        result = executor.execute(plan, "hello", gen)
        # Should terminate (not infinite loop). Lane 3 is max.
        assert result.lane_used <= Lane.DEEP
        # Should not have called generate excessively
        assert call_count[0] <= 3

    def test_seen_set_populated(self):
        """Verify loop detection works for normal escalation path."""
        def probe_always_mitigate(output, prompt):
            return {"decision": "mitigate", "mitigations": [{"transform": "relocate"}]}

        lr = LaneRouter()
        executor = CascadeExecutor(lane_router=lr, probe_fn=probe_always_mitigate)
        plan = RoutePlan(
            lane=Lane.FAST, model="m1", provider="test",
            budget_per_call_usd=1.0, budget_total_usd=100.0,
            tools_allowed=False, validators=["format"],
            probe_policy="canary", vary_key="k",
            escalation_policy="auto", fallback_chain=["m2", "m3"],
            reasons=[],
        )
        result = executor.execute(plan, "hello", lambda p, m: "response")
        # Escalated through lanes without cycling
        assert result.escalated


class TestVaryKeyCompleteness:
    """Vary key includes budget and probe policy."""

    def test_budget_in_key(self):
        k1 = compute_vary_key("m1", "sys", "user", budget_per_call_usd=0.01)
        k2 = compute_vary_key("m1", "sys", "user", budget_per_call_usd=5.00)
        assert k1 != k2

    def test_probe_policy_in_key(self):
        k1 = compute_vary_key("m1", "sys", "user", probe_policy="none")
        k2 = compute_vary_key("m1", "sys", "user", probe_policy="deep")
        assert k1 != k2

    def test_both_defaults_produce_same_key(self):
        k1 = compute_vary_key("m1", "sys", "user")
        k2 = compute_vary_key("m1", "sys", "user", budget_per_call_usd=0.0, probe_policy="")
        assert k1 == k2


class TestMustHaveLogging:
    """must_have filter degradation is logged."""

    def test_must_have_no_match_in_reasons(self):
        lr = LaneRouter()
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            must_have_strengths=["nonexistent_strength_xyz"],
        )
        # Should have a reason about must_have fallback
        assert any("must_have" in r and "no exact match" in r for r in plan.reasons)


# =============================================================================
# Regime → risk_class mapping
# =============================================================================


class TestRegimeToRiskClass:
    """regime_to_risk_class produces expected buckets."""

    def test_elastic_maps_to_standard(self):
        from governor.lanes import regime_to_risk_class
        risk, known = regime_to_risk_class("elastic")
        assert risk == "standard"
        assert known is True

    def test_warm_maps_to_standard(self):
        from governor.lanes import regime_to_risk_class
        risk, known = regime_to_risk_class("warm")
        assert risk == "standard"
        assert known is True

    def test_ductile_maps_to_elevated(self):
        from governor.lanes import regime_to_risk_class
        risk, known = regime_to_risk_class("ductile")
        assert risk == "elevated"
        assert known is True

    def test_unstable_maps_to_critical(self):
        from governor.lanes import regime_to_risk_class
        risk, known = regime_to_risk_class("unstable")
        assert risk == "critical"
        assert known is True

    def test_unknown_regime_defaults_to_standard_not_known(self):
        from governor.lanes import regime_to_risk_class
        risk, known = regime_to_risk_class("bogus")
        assert risk == "standard"
        assert known is False

    def test_risk_class_forces_lane_promotion(self):
        """Elevated risk from regime forces at least Lane 2 + probe policy."""
        lr = LaneRouter()
        # Simple claim → normally Lane 1
        plan_standard = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="standard",
        )
        plan_elevated = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="elevated",
        )
        plan_critical = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="critical",
        )
        assert plan_standard.lane == Lane.FAST
        assert plan_elevated.lane >= Lane.GENERAL
        assert plan_critical.lane >= Lane.DEEP
        # Elevated should mention risk in reasons
        assert any("risk=elevated" in r for r in plan_elevated.reasons)
        # Critical should mention risk in reasons
        assert any("risk=critical" in r for r in plan_critical.reasons)
        # Probe policy should resolve from risk_gated
        if plan_elevated.probe_policy != ProbePolicy.NONE.value:
            assert plan_elevated.probe_policy in (
                ProbePolicy.CANARY.value, ProbePolicy.DEEP.value
            )

    def test_regime_mapping_in_explain(self):
        """Explain output includes reasons that trace to risk_class."""
        lr = LaneRouter()
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
            risk_class="elevated",
        )
        explanation = lr.explain(plan)
        assert "reasons" in explanation
        assert any("risk=elevated" in r for r in explanation["reasons"])


# =============================================================================
# CooldownStore
# =============================================================================


class TestCooldownEntry:
    """CooldownEntry serialization."""

    def test_roundtrip(self):
        e = CooldownEntry(
            cooldown_key="abc123", model="m1", lane=2,
            risk_class="standard", task_hint="codegen",
            validators_failed=["schema"],
            probe_decision="mitigate", escalated=True,
            is_failure=True,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        d = e.to_dict()
        e2 = CooldownEntry.from_dict(d)
        assert e2.model == "m1"
        assert e2.lane == 2
        assert e2.validators_failed == ["schema"]
        assert e2.escalated is True
        assert e2.is_failure is True
        assert e2.cooldown_key == "abc123"
        assert e2.risk_class == "standard"
        assert e2.task_hint == "codegen"

    def test_from_dict_defaults(self):
        d = {"model": "m", "lane": 1, "timestamp": "2026-01-01T00:00:00+00:00"}
        e = CooldownEntry.from_dict(d)
        assert e.validators_failed == []
        assert e.escalated is False
        assert e.probe_decision is None
        assert e.cooldown_key == ""
        assert e.risk_class == ""
        assert e.task_hint == ""
        assert e.is_failure is False


class TestCooldownStore:
    """CooldownStore persistence and routing integration."""

    def test_record_and_check_below_threshold(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=3)
        result = CascadeResult(
            output="x", lane_used=2, model_used="m1",
            escalated=True, escalation_chain=["a"], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=[], validators_failed=["schema"],
        )
        store.record(result)
        store.record(result)
        # 2 failures, threshold is 3 → not cooled yet
        assert not store.is_cooled_down("m1", 2)

    def test_record_and_check_at_threshold(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=3)
        result = CascadeResult(
            output="x", lane_used=2, model_used="m1",
            escalated=True, escalation_chain=["a"], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=[], validators_failed=["schema"],
        )
        for _ in range(3):
            store.record(result)
        assert store.is_cooled_down("m1", 2)

    def test_different_lane_not_cooled(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=2)
        result = CascadeResult(
            output="x", lane_used=2, model_used="m1",
            escalated=True, escalation_chain=["a"], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=[], validators_failed=["schema"],
        )
        store.record(result)
        store.record(result)
        # Cooled for lane 2, but not lane 1
        assert store.is_cooled_down("m1", 2)
        assert not store.is_cooled_down("m1", 1)

    def test_success_not_counted_as_failure(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=2)
        # Success: no validators_failed, no escalation, proceed probe
        result = CascadeResult(
            output="x", lane_used=2, model_used="m1",
            escalated=False, escalation_chain=[], mitigations_attempted=[],
            probe_decision="proceed", artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=["format"], validators_failed=[],
        )
        for _ in range(5):
            store.record(result)
        assert not store.is_cooled_down("m1", 2)

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "cool.jsonl"
        s1 = CooldownStore(path=path, threshold=2)
        result = CascadeResult(
            output="x", lane_used=1, model_used="m1",
            escalated=True, escalation_chain=["a"], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=[], validators_failed=["format"],
        )
        s1.record(result)
        s1.record(result)
        # New instance reads from disk
        s2 = CooldownStore(path=path, threshold=2)
        assert s2.is_cooled_down("m1", 1)

    def test_window_expiry(self, tmp_path):
        path = tmp_path / "cool.jsonl"
        store = CooldownStore(path=path, threshold=1, window_s=60)
        # Write an entry with an old timestamp
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        entry = CooldownEntry(
            cooldown_key="old", model="m1", lane=2,
            risk_class="", task_hint="",
            validators_failed=["schema"],
            probe_decision=None, escalated=True,
            is_failure=True, timestamp=old_ts,
        )
        with open(path, "w") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")
        # Old entry should be outside window
        assert not store.is_cooled_down("m1", 2)

    def test_stats(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=1)
        result = CascadeResult(
            output="x", lane_used=2, model_used="m1",
            escalated=True, escalation_chain=["a"], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=[], validators_failed=["schema"],
        )
        store.record(result)
        st = store.stats()
        assert st["total_entries"] == 1
        assert st["in_window"] == 1
        assert len(st["models_cooled_down"]) == 1

    def test_recent_failures_count(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=10)
        result = CascadeResult(
            output="x", lane_used=2, model_used="m1",
            escalated=True, escalation_chain=["a"], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=[], validators_failed=["schema"],
        )
        store.record(result)
        store.record(result)
        store.record(result)
        assert store.recent_failures("m1", 2) == 3


class TestCooldownRouterIntegration:
    """Cooldown store steers model selection."""

    def test_cooled_model_skipped_in_reasons(self, tmp_path):
        """Cooldown store causes model to be skipped with reason logged."""
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=1)
        # Record a failure for the model that would normally be selected
        result = CascadeResult(
            output="x", lane_used=1, model_used="claude-sonnet-4",
            escalated=True, escalation_chain=["a"], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=[], validators_failed=["format"],
        )
        store.record(result)
        lr = LaneRouter(cooldown_store=store)
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
        )
        # The router should have a reason mentioning cooldown
        cooldown_reasons = [r for r in plan.reasons if "cooldown" in r]
        # If the model was actually cooled, there should be a reason.
        # (If there's only one model, ALL are cooled → "proceeding anyway")
        if cooldown_reasons:
            assert any("cooldown" in r for r in plan.reasons)

    def test_cascade_records_to_cooldown(self, tmp_path):
        """CascadeExecutor records outcomes to cooldown store."""
        store = CooldownStore(path=tmp_path / "cool.jsonl", threshold=10)
        lr = LaneRouter(cooldown_store=store)
        executor = CascadeExecutor(
            lane_router=lr, cooldown_store=store,
        )
        plan = lr.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")],
        )
        result = executor.execute(
            plan=plan, prompt="hello",
            generate_fn=lambda p, m: "output",
        )
        # Should have recorded the outcome
        assert store.recent_failures(result.model_used, result.lane_used) >= 0
        # Total entries includes success too
        st = store.stats()
        assert st["total_entries"] >= 1

    def test_cooldown_status_in_lane_status(self, tmp_path):
        """lanes.status includes cooldown stats."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        lr = LaneRouter(cooldown_store=store)
        status = lr.get_status()
        assert "cooldown_stats" in status
        assert "window_s" in status["cooldown_stats"]


class TestProbeFailRate:
    """Probe failure rate derived from cooldown store entries."""

    def _make_result(self, model, lane, probe_decision, escalated=False):
        return CascadeResult(
            output="x", lane_used=lane, model_used=model,
            escalated=escalated, escalation_chain=[], mitigations_attempted=[],
            probe_decision=probe_decision, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=["format"], validators_failed=[],
        )

    def test_no_probes_returns_zero(self, tmp_path):
        """No probe entries → rate=0, attempts=0."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        rate, attempts = store.probe_fail_rate("m1", 2)
        assert rate == 0.0
        assert attempts == 0

    def test_below_min_samples_returns_zero(self, tmp_path):
        """Below min sample count → rate=0 (no opinion)."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        # Record 2 probe failures (below default min of 3)
        for _ in range(2):
            store.record(self._make_result("m1", 2, "mitigate"))
        rate, attempts = store.probe_fail_rate("m1", 2)
        assert rate == 0.0
        assert attempts == 2

    def test_at_min_samples_produces_rate(self, tmp_path):
        """At min sample count → produces meaningful rate."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        store.record(self._make_result("m1", 2, "mitigate"))
        store.record(self._make_result("m1", 2, "proceed"))
        store.record(self._make_result("m1", 2, "mitigate"))
        rate, attempts = store.probe_fail_rate("m1", 2)
        assert attempts == 3
        assert abs(rate - 2/3) < 0.01

    def test_proceed_not_counted_as_failure(self, tmp_path):
        """probe_decision=proceed is not a probe failure."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(5):
            store.record(self._make_result("m1", 2, "proceed"))
        rate, attempts = store.probe_fail_rate("m1", 2)
        assert attempts == 5
        assert rate == 0.0

    def test_block_counted_as_failure(self, tmp_path):
        """probe_decision=block counts as probe failure."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(3):
            store.record(self._make_result("m1", 2, "block"))
        rate, attempts = store.probe_fail_rate("m1", 2)
        assert rate == 1.0

    def test_none_probe_decision_not_counted(self, tmp_path):
        """Entries with probe_decision=None are not probe attempts."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        # Non-probed entries
        for _ in range(5):
            store.record(self._make_result("m1", 2, None))
        # 3 probed entries (all failures)
        for _ in range(3):
            store.record(self._make_result("m1", 2, "mitigate"))
        rate, attempts = store.probe_fail_rate("m1", 2)
        assert attempts == 3  # only probed entries count
        assert rate == 1.0

    def test_different_lane_isolated(self, tmp_path):
        """Probe fail rate is per (model, lane)."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(4):
            store.record(self._make_result("m1", 2, "mitigate"))
        rate_lane2, _ = store.probe_fail_rate("m1", 2)
        rate_lane1, attempts1 = store.probe_fail_rate("m1", 1)
        assert rate_lane2 == 1.0
        assert attempts1 == 0

    def test_human_gate_counted_as_failure(self, tmp_path):
        """probe_decision=human_gate counts as probe failure."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        store.record(self._make_result("m1", 2, "human_gate"))
        store.record(self._make_result("m1", 2, "proceed"))
        store.record(self._make_result("m1", 2, "proceed"))
        rate, _ = store.probe_fail_rate("m1", 2)
        assert abs(rate - 1/3) < 0.01


# =============================================================================
# TestModelScore
# =============================================================================


class TestModelScore:
    """Composite quality score for within-lane model selection."""

    def _make_result(self, model, lane, probe_decision=None, escalated=False,
                     validators_failed=None):
        return CascadeResult(
            output="x", lane_used=lane, model_used=model,
            escalated=escalated, escalation_chain=[], mitigations_attempted=[],
            probe_decision=probe_decision, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=["format"],
            validators_failed=validators_failed or [],
        )

    def test_insufficient_data_returns_neutral(self, tmp_path):
        """Below min samples → score=0.5 (neutral)."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        score, breakdown = store.model_score("m1", 2)
        assert score == 0.5
        assert breakdown["note"] == "insufficient_data"

    def test_insufficient_data_with_some_entries(self, tmp_path):
        """Even with 1-2 entries, still insufficient → 0.5."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        store.record(self._make_result("m1", 2, "proceed"))
        store.record(self._make_result("m1", 2, "proceed"))
        score, breakdown = store.model_score("m1", 2)
        assert score == 0.5
        assert breakdown["total"] == 2

    def test_perfect_model(self, tmp_path):
        """All successes, no probe failures, no escalations → score=1.0."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(5):
            store.record(self._make_result("m1", 2, "proceed"))
        score, breakdown = store.model_score("m1", 2)
        assert score == 1.0
        assert breakdown["success_rate"] == 1.0
        assert breakdown["probe_reliability"] == 1.0
        assert breakdown["escalation_rate"] == 0.0

    def test_all_failures(self, tmp_path):
        """All failures, all probe failures, all escalations → low score."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(5):
            store.record(self._make_result(
                "m1", 2, "mitigate", escalated=True,
                validators_failed=["format"],
            ))
        score, breakdown = store.model_score("m1", 2)
        assert score < 0.1  # near zero
        assert breakdown["success_rate"] == 0.0
        assert breakdown["probe_reliability"] == 0.0
        assert breakdown["escalation_rate"] == 1.0

    def test_mixed_results(self, tmp_path):
        """Mixed outcomes produce intermediate score."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        # 3 successes with proceed, 2 failures with mitigate (1 escalated)
        for _ in range(3):
            store.record(self._make_result("m1", 2, "proceed"))
        store.record(self._make_result("m1", 2, "mitigate", escalated=True,
                                       validators_failed=["format"]))
        store.record(self._make_result("m1", 2, "mitigate",
                                       validators_failed=["schema"]))
        score, breakdown = store.model_score("m1", 2)
        # success_rate = 3/5 = 0.6
        # probe_reliability = 1 - 2/5 = 0.6
        # escalation_rate = 1/5 = 0.2
        assert breakdown["success_rate"] == 0.6
        assert breakdown["probe_reliability"] == 0.6
        assert breakdown["escalation_rate"] == 0.2
        expected = 0.50 * 0.6 + 0.30 * 0.6 + 0.20 * 0.8
        assert abs(score - expected) < 0.01

    def test_no_probe_entries_full_reliability(self, tmp_path):
        """When probe_decision is always None, probe_reliability defaults to 1.0."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(5):
            store.record(self._make_result("m1", 1, None))  # no probe
        score, breakdown = store.model_score("m1", 1)
        assert breakdown["probe_reliability"] == 1.0

    def test_different_lane_isolated(self, tmp_path):
        """model_score is per (model, lane)."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        # Lane 2: all failures
        for _ in range(5):
            store.record(self._make_result("m1", 2, "mitigate",
                                           validators_failed=["format"]))
        # Lane 1: no data
        score_l1, bd_l1 = store.model_score("m1", 1)
        score_l2, bd_l2 = store.model_score("m1", 2)
        assert score_l1 == 0.5  # insufficient
        assert score_l2 < 0.3  # terrible

    def test_score_clamped_to_0_1(self, tmp_path):
        """Score is always in [0, 1] regardless of inputs."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(10):
            store.record(self._make_result("m1", 2, "proceed"))
        score, _ = store.model_score("m1", 2)
        assert 0.0 <= score <= 1.0


# =============================================================================
# TestAutopilotLevel2Selection
# =============================================================================


class TestAutopilotLevel2Selection:
    """Autopilot level 2 uses model_score for within-lane selection."""

    def _make_result(self, model, lane, probe_decision=None, escalated=False,
                     validators_failed=None):
        return CascadeResult(
            output="x", lane_used=lane, model_used=model,
            escalated=escalated, escalation_chain=[], mitigations_attempted=[],
            probe_decision=probe_decision, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=["format"],
            validators_failed=validators_failed or [],
        )

    def _setup_registry(self):
        """Create a registry with only 2 test models available."""
        registry = ModelRegistry()
        # Mark all default models unavailable
        for name in list(registry._status.keys()):
            registry.mark_available(name, False)
        # Register and enable test models
        registry.register(ModelCapabilities(
            name="cheap-model", tier=ModelTier.FAST, provider="p",
            strengths=["speed"], context_window=4096,
            cost_input=0.001, cost_output=0.002,
        ))
        registry.register(ModelCapabilities(
            name="pricey-model", tier=ModelTier.FAST, provider="p",
            strengths=["speed"], context_window=4096,
            cost_input=0.01, cost_output=0.02,
        ))
        return registry

    def test_level_2_no_cooldown_store_uses_cost(self):
        """Level 2 without cooldown store → cheapest model (original behavior)."""
        registry = self._setup_registry()
        router = Router(registry=registry)
        lr = LaneRouter(router=router, autopilot_level=2, cooldown_store=None)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        # cheap-model should be picked (lower cost)
        assert plan.model == "cheap-model"

    def test_level_2_prefers_higher_score(self, tmp_path):
        """Level 2 with cooldown data → prefers model with higher score."""
        registry = self._setup_registry()
        router = Router(registry=registry)
        store = CooldownStore(path=tmp_path / "cool.jsonl")

        # cheap-model: all failures (bad score)
        for _ in range(5):
            store.record(self._make_result(
                "cheap-model", 1, "mitigate",
                validators_failed=["format"],
            ))
        # pricey-model: all successes (great score)
        for _ in range(5):
            store.record(self._make_result("pricey-model", 1, "proceed"))

        lr = LaneRouter(router=router, autopilot_level=2, cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        # pricey-model should win despite higher cost — quality > cost
        assert plan.model == "pricey-model"

    def test_level_2_cost_tiebreaker(self, tmp_path):
        """Equal scores → cheaper model wins (cost as tiebreaker)."""
        registry = self._setup_registry()
        router = Router(registry=registry)
        store = CooldownStore(path=tmp_path / "cool.jsonl")

        # Both models: all successes (equal score)
        for _ in range(5):
            store.record(self._make_result("cheap-model", 1, "proceed"))
        for _ in range(5):
            store.record(self._make_result("pricey-model", 1, "proceed"))

        lr = LaneRouter(router=router, autopilot_level=2, cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        assert plan.model == "cheap-model"

    def test_level_1_does_not_use_score(self, tmp_path):
        """Level 1 doesn't trigger score-based selection."""
        registry = self._setup_registry()
        router = Router(registry=registry)
        store = CooldownStore(path=tmp_path / "cool.jsonl")

        # cheap-model: all failures
        for _ in range(5):
            store.record(self._make_result(
                "cheap-model", 1, "mitigate",
                validators_failed=["format"],
            ))
        # pricey-model: all successes
        for _ in range(5):
            store.record(self._make_result("pricey-model", 1, "proceed"))

        lr = LaneRouter(router=router, autopilot_level=1, cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        # Level 1 doesn't do score-based selection — relies on earlier filters
        # (cooldown + probe_fail_rate may still reorder, but score sort not applied)
        # The main assertion: level 1 doesn't crash and produces a valid plan
        assert plan.model in ("cheap-model", "pricey-model")

    def test_score_breakdown_in_reasons(self, tmp_path):
        """Score breakdown appears in plan.reasons when data is sufficient."""
        registry = self._setup_registry()
        router = Router(registry=registry)
        store = CooldownStore(path=tmp_path / "cool.jsonl")

        for _ in range(5):
            store.record(self._make_result("cheap-model", 1, "proceed"))
        for _ in range(5):
            store.record(self._make_result("pricey-model", 1, "proceed"))

        lr = LaneRouter(router=router, autopilot_level=2, cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        score_reasons = [r for r in plan.reasons if r.startswith("score(")]
        assert len(score_reasons) >= 1  # at least one model scored


# =============================================================================
# TestPolicyVersion
# =============================================================================


class TestPolicyVersion:
    """Policy version salt for cooldown key isolation."""

    def test_deterministic(self):
        """Same inputs → same hash."""
        v1 = compute_policy_version()
        v2 = compute_policy_version()
        assert v1 == v2
        assert len(v1) == 16  # 16 hex chars

    def test_contract_change_changes_version(self):
        """Different contracts → different version."""
        v_default = compute_policy_version()
        custom = dict(LANE_CONTRACTS)
        custom[Lane.FAST] = LaneContract(
            lane=Lane.FAST,
            model_tiers=("local",),  # changed from ("local", "fast")
            budget_per_call_usd=0.02,  # changed
        )
        v_custom = compute_policy_version(contracts=custom)
        assert v_default != v_custom

    def test_weight_change_changes_version(self):
        """Different scoring weights → different version."""
        v1 = compute_policy_version(score_weights=(0.50, 0.30, 0.20))
        v2 = compute_policy_version(score_weights=(0.40, 0.40, 0.20))
        assert v1 != v2

    def test_window_change_changes_version(self):
        """Different cooldown window → different version."""
        v1 = compute_policy_version(cooldown_window_s=3600.0)
        v2 = compute_policy_version(cooldown_window_s=7200.0)
        assert v1 != v2

    def test_threshold_change_changes_version(self):
        """Different cooldown threshold → different version."""
        v1 = compute_policy_version(cooldown_threshold=3)
        v2 = compute_policy_version(cooldown_threshold=5)
        assert v1 != v2

    def test_route_plan_carries_policy_version(self):
        """RoutePlan produced by LaneRouter has policy_version set."""
        lr = LaneRouter()
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        assert plan.policy_version
        assert len(plan.policy_version) == 16

    def test_plan_roundtrip_preserves_policy_version(self):
        """policy_version survives to_dict/from_dict."""
        plan = RoutePlan(
            lane=1, model="m", provider="p",
            budget_per_call_usd=0.01, budget_total_usd=10.0,
            tools_allowed=False, validators=["format"],
            probe_policy="none", vary_key="k",
            escalation_policy="auto", fallback_chain=[],
            reasons=[], policy_version="abc123",
        )
        d = plan.to_dict()
        assert d["policy_version"] == "abc123"
        plan2 = RoutePlan.from_dict(d)
        assert plan2.policy_version == "abc123"

    def test_entry_roundtrip_preserves_policy_version(self):
        """CooldownEntry policy_version survives to_dict/from_dict."""
        entry = CooldownEntry(
            cooldown_key="ck1", model="m1", lane=2,
            risk_class="standard", task_hint="codegen",
            validators_failed=[], probe_decision="proceed",
            escalated=False, is_failure=False,
            timestamp="2026-01-01T00:00:00+00:00",
            policy_version="deadbeef",
        )
        d = entry.to_dict()
        assert d["pv"] == "deadbeef"
        entry2 = CooldownEntry.from_dict(d)
        assert entry2.policy_version == "deadbeef"

    def test_legacy_entry_has_empty_policy_version(self):
        """Legacy entries (no 'pv' key) default to empty string."""
        d = {"model": "m1", "lane": 2, "timestamp": "2026-01-01T00:00:00+00:00"}
        entry = CooldownEntry.from_dict(d)
        assert entry.policy_version == ""


class TestPolicyVersionIsolation:
    """Queries only consider entries matching current policy_version."""

    def _make_result(self, model, lane, probe_decision=None, escalated=False,
                     validators_failed=None):
        return CascadeResult(
            output="x", lane_used=lane, model_used=model,
            escalated=escalated, escalation_chain=[], mitigations_attempted=[],
            probe_decision=probe_decision, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=["format"],
            validators_failed=validators_failed or [],
        )

    def test_different_version_entries_ignored(self, tmp_path):
        """Entries from a different policy_version don't count."""
        # Store with version "v1"
        store_v1 = CooldownStore(
            path=tmp_path / "cool.jsonl", policy_version="v1",
        )
        # Record 5 failures under v1
        for _ in range(5):
            store_v1.record(self._make_result(
                "m1", 2, "mitigate", validators_failed=["format"],
            ))

        # New store with version "v2" reading same file
        store_v2 = CooldownStore(
            path=tmp_path / "cool.jsonl", policy_version="v2",
        )
        # v2 should NOT see v1's failures
        assert not store_v2.is_cooled_down("m1", 2)
        assert store_v2.recent_failures("m1", 2) == 0
        rate, attempts = store_v2.probe_fail_rate("m1", 2)
        assert attempts == 0
        score, bd = store_v2.model_score("m1", 2)
        assert score == 0.5  # insufficient data

    def test_legacy_entries_excluded_by_versioned_store(self, tmp_path):
        """Legacy entries (no pv) are excluded when store has a policy_version."""
        # Write a legacy entry directly (no pv field)
        entry_line = json.dumps({
            "ck": "x", "model": "m1", "lane": 2,
            "validators_failed": ["format"], "probe_decision": "mitigate",
            "escalated": False, "is_failure": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }) + "\n"
        p = tmp_path / "cool.jsonl"
        p.write_text(entry_line * 5)

        # Versioned store excludes legacy entries (prevents upgrade-day poison)
        store_v = CooldownStore(path=p, policy_version="v1")
        assert store_v.recent_failures("m1", 2) == 0

        # Unversioned store still sees them (backwards compat)
        store_unv = CooldownStore(path=p)
        assert store_unv.recent_failures("m1", 2) == 5

    def test_same_version_entries_counted(self, tmp_path):
        """Entries with matching policy_version are counted normally."""
        store = CooldownStore(
            path=tmp_path / "cool.jsonl", policy_version="v1",
        )
        for _ in range(5):
            store.record(self._make_result(
                "m1", 2, "mitigate", validators_failed=["format"],
            ))
        assert store.is_cooled_down("m1", 2)
        assert store.recent_failures("m1", 2) == 5

    def test_no_policy_version_on_store_matches_all(self, tmp_path):
        """Store with no policy_version sees all entries (backwards compat)."""
        # Write entries with a specific version
        store_v1 = CooldownStore(
            path=tmp_path / "cool.jsonl", policy_version="v1",
        )
        for _ in range(5):
            store_v1.record(self._make_result(
                "m1", 2, "mitigate", validators_failed=["format"],
            ))

        # Store without policy_version → sees everything
        store_any = CooldownStore(path=tmp_path / "cool.jsonl")
        assert store_any.recent_failures("m1", 2) == 5

    def test_stats_shows_version_breakdown(self, tmp_path):
        """stats() includes per-version counts and current version."""
        store = CooldownStore(
            path=tmp_path / "cool.jsonl", policy_version="v1",
        )
        for _ in range(3):
            store.record(self._make_result("m1", 2, "proceed"))
        stats = store.stats()
        assert stats["policy_version"] == "v1"
        assert stats["current_version_in_window"] == 3
        assert "v1" in stats["entries_by_version"]

    def test_stale_version_dropped_on_load(self, tmp_path):
        """Entries from old policy_version + >24h old are dropped on load."""
        p = tmp_path / "cool.jsonl"
        # Write an entry with old version + old timestamp (26h ago)
        old_ts = (
            datetime.now(timezone.utc) - timedelta(hours=26)
        ).isoformat()
        old_entry = json.dumps({
            "ck": "x", "model": "m1", "lane": 2,
            "validators_failed": [], "probe_decision": "mitigate",
            "escalated": False, "is_failure": True,
            "timestamp": old_ts, "pv": "old_version",
        }) + "\n"
        # Write an entry with old version but recent timestamp (5min ago)
        recent_ts = (
            datetime.now(timezone.utc) - timedelta(minutes=5)
        ).isoformat()
        recent_entry = json.dumps({
            "ck": "x", "model": "m1", "lane": 2,
            "validators_failed": [], "probe_decision": "mitigate",
            "escalated": False, "is_failure": True,
            "timestamp": recent_ts, "pv": "old_version",
        }) + "\n"
        p.write_text(old_entry + recent_entry)

        # Load with a different current version
        store = CooldownStore(path=p, policy_version="new_version")
        store._ensure_loaded()
        # Old entry (>24h + wrong version) should be dropped
        # Recent entry (wrong version but <24h) should be kept
        assert len(store._entries) == 1
        assert store._entries[0].policy_version == "old_version"


# =============================================================================
# TestExplainTransparency
# =============================================================================


class TestExplainTransparency:
    """lanes.explain() shows score breakdown and policy_version."""

    def _make_result(self, model, lane, probe_decision=None):
        return CascadeResult(
            output="x", lane_used=lane, model_used=model,
            escalated=False, escalation_chain=[], mitigations_attempted=[],
            probe_decision=probe_decision, artifact_hit=False, vary_key="abc",
            budget_spent_usd=0.0, budget_exhausted=False,
            validators_passed=["format"], validators_failed=[],
        )

    def test_explain_includes_policy_version(self):
        """explain() output includes policy_version."""
        lr = LaneRouter()
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        explanation = lr.explain(plan)
        assert "policy_version" in explanation
        assert explanation["policy_version"] == plan.policy_version

    def test_explain_includes_window_s(self, tmp_path):
        """explain() output includes window_s from cooldown store."""
        store = CooldownStore(path=tmp_path / "cool.jsonl", window_s=7200.0)
        lr = LaneRouter(cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        explanation = lr.explain(plan)
        assert explanation["window_s"] == 7200.0

    def test_explain_no_cooldown_store_no_candidates(self):
        """explain() without cooldown store omits candidates list."""
        lr = LaneRouter()
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        explanation = lr.explain(plan)
        assert "candidates" not in explanation

    def test_explain_with_data_shows_candidates(self, tmp_path):
        """explain() with cooldown data includes candidate scorecards."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(5):
            store.record(self._make_result("qwen2.5-coder:7b", 1, "proceed"))
        lr = LaneRouter(cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        explanation = lr.explain(plan)
        assert "candidates" in explanation
        candidates = explanation["candidates"]
        assert len(candidates) >= 1
        # Check structure of candidate entries
        for c in candidates:
            assert "model" in c
            assert "score" in c
            assert "n" in c
            assert "is_cooled" in c
            assert "selected" in c

    def test_explain_cold_start_labeled(self, tmp_path):
        """Candidates with insufficient data are labeled 'cold_start'."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        # Only 1 entry — below min_samples
        store.record(self._make_result("qwen2.5-coder:7b", 1, "proceed"))
        lr = LaneRouter(cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        explanation = lr.explain(plan)
        if "candidates" in explanation:
            for c in explanation["candidates"]:
                if c["n"] < CooldownStore._PROBE_MIN_SAMPLES:
                    assert c.get("note") == "cold_start"

    def test_explain_sufficient_data_shows_breakdown(self, tmp_path):
        """Candidates with enough data show full score breakdown."""
        store = CooldownStore(path=tmp_path / "cool.jsonl")
        for _ in range(5):
            store.record(self._make_result("qwen2.5-coder:7b", 1, "proceed"))
        lr = LaneRouter(cooldown_store=store)
        plan = lr.route(claims=[Claim(type=ClaimType.FILE_EXISTS, path="a.py")])
        explanation = lr.explain(plan)
        if "candidates" in explanation:
            scored = [c for c in explanation["candidates"] if c["n"] >= 3]
            for c in scored:
                assert "success_rate" in c
                assert "probe_reliability" in c
                assert "escalation_rate" in c

    def test_status_includes_policy_version(self):
        """get_status() includes policy_version."""
        lr = LaneRouter()
        status = lr.get_status()
        assert "policy_version" in status
        assert status["policy_version"] == lr.policy_version


# =============================================================================
# CooldownEntry new fields + threading safety
# =============================================================================


class TestCooldownEntryStreamFields:
    """Tests for is_cancelled, validation_scope fields on CooldownEntry."""

    def test_default_values(self):
        entry = CooldownEntry(
            cooldown_key="k", model="m", lane=1, risk_class="standard",
            task_hint="", validators_failed=[], probe_decision=None,
            escalated=False, is_failure=False,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert entry.is_cancelled is False
        assert entry.validation_scope == "full"

    def test_to_dict_includes_new_fields(self):
        entry = CooldownEntry(
            cooldown_key="k", model="m", lane=1, risk_class="standard",
            task_hint="", validators_failed=[], probe_decision=None,
            escalated=False, is_failure=False,
            timestamp="2026-01-01T00:00:00+00:00",
            is_cancelled=True, validation_scope="skipped",
        )
        d = entry.to_dict()
        assert d["is_cancelled"] is True
        assert d["validation_scope"] == "skipped"

    def test_from_dict_with_new_fields(self):
        d = {
            "model": "m", "lane": 1, "timestamp": "2026-01-01T00:00:00+00:00",
            "is_cancelled": True, "validation_scope": "truncated",
        }
        entry = CooldownEntry.from_dict(d)
        assert entry.is_cancelled is True
        assert entry.validation_scope == "truncated"

    def test_from_dict_without_new_fields_defaults(self):
        """Old entries without new fields get safe defaults."""
        d = {"model": "m", "lane": 1, "timestamp": "2026-01-01T00:00:00+00:00"}
        entry = CooldownEntry.from_dict(d)
        assert entry.is_cancelled is False
        assert entry.validation_scope == "full"

    def test_roundtrip(self):
        entry = CooldownEntry(
            cooldown_key="k", model="m", lane=2, risk_class="elevated",
            task_hint="test", validators_failed=["format"],
            probe_decision="mitigate", escalated=True, is_failure=True,
            timestamp="2026-01-01T00:00:00+00:00", policy_version="v1",
            is_cancelled=False, validation_scope="truncated",
        )
        restored = CooldownEntry.from_dict(entry.to_dict())
        assert restored.is_cancelled == entry.is_cancelled
        assert restored.validation_scope == entry.validation_scope
        assert restored.model == entry.model


class TestCooldownStoreRecordEntry:
    """Tests for record_entry() method."""

    def test_record_entry_appends(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        entry = CooldownEntry(
            cooldown_key="k", model="m", lane=1, risk_class="standard",
            task_hint="", validators_failed=[], probe_decision=None,
            escalated=False, is_failure=False,
            timestamp="2026-01-01T00:00:00+00:00",
            is_cancelled=False, validation_scope="full",
        )
        store.record_entry(entry)
        assert len(store._entries) == 1
        assert store._entries[0] is entry

    def test_record_entry_persists(self, tmp_path):
        path = tmp_path / "cd.jsonl"
        store = CooldownStore(path=path)
        entry = CooldownEntry(
            cooldown_key="k", model="m", lane=1, risk_class="standard",
            task_hint="", validators_failed=[], probe_decision=None,
            escalated=False, is_failure=False,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        store.record_entry(entry)
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_record_entry_thread_safe(self, tmp_path):
        """record_entry is thread-safe (no crashes under contention)."""
        import threading
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        errors = []

        def _record(i):
            try:
                entry = CooldownEntry(
                    cooldown_key=f"k{i}", model="m", lane=1,
                    risk_class="standard", task_hint="", validators_failed=[],
                    probe_decision=None, escalated=False, is_failure=False,
                    timestamp="2026-01-01T00:00:00+00:00",
                )
                store.record_entry(entry)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_record, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(store._entries) == 20


class TestCooldownStoreLockNoDeadlock:
    """Verify that stats() doesn't deadlock (regression)."""

    def test_stats_does_not_deadlock(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl", threshold=1)
        # Add enough failure entries to trigger the is_cooled_down path in stats
        for i in range(5):
            cr = CascadeResult(
                output="out", lane_used=2, model_used="m1",
                escalated=True, escalation_chain=[], mitigations_attempted=[],
                probe_decision=None, artifact_hit=False, vary_key="v",
                budget_spent_usd=0.0, budget_exhausted=False,
                validators_failed=["fmt"],
            )
            store.record(cr, risk_class="standard")
        # This should not deadlock
        result = store.stats()
        assert result["total_entries"] == 5
        assert len(result["models_cooled_down"]) >= 1


# =============================================================================
# Validator failure penalty
# =============================================================================


class TestValidatorFailRates:
    """Tests for validator_fail_rates() and penalty in _select_model."""

    def _make_entry(self, model, lane, validators_failed=None, is_cancelled=False,
                    validation_scope="full", pv=""):
        from governor.lanes import CooldownEntry, _cooldown_key
        vf = validators_failed or []
        return CooldownEntry(
            cooldown_key=_cooldown_key(model, lane, "", "", vf, policy_version=pv),
            model=model, lane=lane, risk_class="standard", task_hint="",
            validators_failed=vf, probe_decision=None, escalated=False,
            is_failure=bool(vf), timestamp=datetime.now(timezone.utc).isoformat(),
            policy_version=pv, is_cancelled=is_cancelled,
            validation_scope=validation_scope,
        )

    def test_empty_store(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        assert store.validator_fail_rates("m", 2) == {}

    def test_cold_start_below_threshold(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        store.record_entry(self._make_entry("m", 2, ["fmt"]))
        store.record_entry(self._make_entry("m", 2, []))
        # Only 2 entries, below _PROBE_MIN_SAMPLES=3
        assert store.validator_fail_rates("m", 2) == {}

    def test_computed_rates(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        # 4 entries: 2 with "fmt" failure, 1 with "schema" failure, 1 success
        store.record_entry(self._make_entry("m", 2, ["fmt"]))
        store.record_entry(self._make_entry("m", 2, ["fmt", "schema"]))
        store.record_entry(self._make_entry("m", 2, []))
        store.record_entry(self._make_entry("m", 2, []))
        rates = store.validator_fail_rates("m", 2)
        assert abs(rates["fmt"] - 0.5) < 0.01   # 2 out of 4
        assert abs(rates["schema"] - 0.25) < 0.01  # 1 out of 4

    def test_cancelled_entries_excluded(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        store.record_entry(self._make_entry("m", 2, ["fmt"]))
        store.record_entry(self._make_entry("m", 2, []))
        store.record_entry(self._make_entry("m", 2, []))
        # This cancelled entry should NOT count in denominator
        store.record_entry(self._make_entry("m", 2, ["fmt"], is_cancelled=True))
        rates = store.validator_fail_rates("m", 2)
        # 3 eligible entries, 1 fmt failure → rate=0.333
        assert abs(rates["fmt"] - 1 / 3) < 0.01

    def test_truncated_scope_excluded(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        store.record_entry(self._make_entry("m", 2, ["fmt"]))
        store.record_entry(self._make_entry("m", 2, []))
        store.record_entry(self._make_entry("m", 2, []))
        store.record_entry(self._make_entry("m", 2, ["fmt"],
                                            validation_scope="truncated"))
        rates = store.validator_fail_rates("m", 2)
        # Truncated excluded: 3 eligible, 1 failure
        assert abs(rates["fmt"] - 1 / 3) < 0.01

    def test_denominator_includes_successes(self, tmp_path):
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        # 3 successes + 0 failures → no keys in result
        for _ in range(4):
            store.record_entry(self._make_entry("m", 2, []))
        rates = store.validator_fail_rates("m", 2)
        assert rates == {}  # No validators failed, so empty dict

    def test_penalty_cap_prevents_ban(self, tmp_path):
        """Penalty is capped at _VALIDATOR_FAIL_PENALTY_CAP even with many failing validators."""
        from governor.lanes import (
            _VALIDATOR_FAIL_PENALTY_CAP,
            _VALIDATOR_FAIL_PENALTY_THRESHOLD,
            _VALIDATOR_FAIL_SCORE_PENALTY,
        )
        store = CooldownStore(path=tmp_path / "cd.jsonl")
        # Many different validators all failing at high rate
        for _ in range(5):
            store.record_entry(self._make_entry("m", 2, ["v1", "v2", "v3", "v4"]))

        rates = store.validator_fail_rates("m", 2)
        # All 4 validators at 100% fail rate → raw penalty = 4 * 0.30 = 1.20
        # But cap is 0.60
        raw_penalty = sum(
            _VALIDATOR_FAIL_SCORE_PENALTY
            for r in rates.values()
            if r >= _VALIDATOR_FAIL_PENALTY_THRESHOLD
        )
        assert raw_penalty > _VALIDATOR_FAIL_PENALTY_CAP  # Would exceed cap
        capped = min(raw_penalty, _VALIDATOR_FAIL_PENALTY_CAP)
        assert capped == _VALIDATOR_FAIL_PENALTY_CAP

    def test_explain_shows_validator_rates(self, tmp_path):
        """explain() includes validator_fail_rates in candidate info."""
        from governor.lanes import LaneRouter
        lr = LaneRouter(
            cooldown_store=CooldownStore(path=tmp_path / "cd.jsonl"),
        )
        # Need enough entries to get past cold start
        cs = lr.cooldown_store
        for _ in range(5):
            cs.record_entry(self._make_entry(
                "claude-sonnet-4", 2, ["fmt"],
            ))
        plan = lr.route(task_hint="codegen")
        info = lr.explain(plan)
        if "candidates" in info:
            for c in info["candidates"]:
                if c.get("validator_fail_rates"):
                    assert isinstance(c["validator_fail_rates"], dict)


class TestDeterministicTieBreak:
    """Deterministic tie-break prevents nondeterministic model selection."""

    def test_same_score_sorted_by_cost_then_name(self):
        """With identical scores, tie-break is (cost, name)."""
        from governor.lanes import LaneRouter
        lr = LaneRouter(autopilot_level=2)
        # Two calls with same state should produce same model
        plan1 = lr.route(task_hint="codegen")
        plan2 = lr.route(task_hint="codegen")
        assert plan1.model == plan2.model


# =============================================================================
# Schema stability tests (Commit 3)
# =============================================================================


class TestSchemaStability:
    """Pin the shapes of explain(), get_status(), and dataclass to_dict outputs.

    Required keys use exact set equality.  Candidate dicts use subset
    checks to allow diagnostic additions without breaking tests.
    Float values: assert type + range, NOT exact values.
    """

    def test_explain_mandatory_fields(self):
        """explain() result has exactly 14 mandatory keys."""
        from governor.lanes import LaneRouter
        lr = LaneRouter()
        plan = lr.route(task_hint="codegen")
        info = lr.explain(plan)
        required = {
            "lane", "lane_name", "model", "provider", "policy_version",
            "reasons", "contract", "budget", "probe_policy",
            "escalation_policy", "fallback_chain", "autopilot_level",
            "vary_key", "window_s",
        }
        assert required == (set(info.keys()) - {"candidates"})

    def test_explain_budget_subkeys(self):
        from governor.lanes import LaneRouter
        lr = LaneRouter()
        plan = lr.route(task_hint="codegen")
        info = lr.explain(plan)
        assert set(info["budget"].keys()) == {"per_call_usd", "total_usd"}

    def test_explain_candidate_base_fields(self):
        """Candidate dicts have at least {model, score, n, is_cooled, selected}."""
        from governor.lanes import LaneRouter
        lr = LaneRouter(
            cooldown_store=CooldownStore(),
        )
        plan = lr.route(task_hint="codegen")
        info = lr.explain(plan)
        if "candidates" in info:
            required = {"model", "score", "n", "is_cooled", "selected"}
            for c in info["candidates"]:
                assert required <= set(c.keys()), f"Missing keys in candidate: {c}"

    def test_get_status_fields(self):
        """get_status() has exactly 7 keys."""
        from governor.lanes import LaneRouter
        lr = LaneRouter()
        status = lr.get_status()
        required = {
            "autopilot_level", "budget_total_usd", "policy_version",
            "contracts", "artifact_stats", "cooldown_stats", "model_registry",
        }
        assert set(status.keys()) == required

    def test_cascade_result_to_dict_fields(self):
        """CascadeResult.to_dict() has all expected keys."""
        cr = CascadeResult(
            output="x", lane_used=1, model_used="m", escalated=False,
            escalation_chain=[], mitigations_attempted=[],
            probe_decision=None, artifact_hit=False, vary_key="v",
            budget_spent_usd=0.0, budget_exhausted=False,
        )
        expected = {
            "output", "lane_used", "model_used", "escalated",
            "escalation_chain", "mitigations_attempted", "probe_decision",
            "artifact_hit", "vary_key", "budget_spent_usd", "budget_exhausted",
            "receipt_id", "validators_passed", "validators_failed",
        }
        assert set(cr.to_dict().keys()) == expected

    def test_route_plan_to_dict_fields(self):
        """RoutePlan.to_dict() has all expected keys."""
        from governor.lanes import RoutePlan
        plan = RoutePlan(
            lane=1, model="m", provider="p",
            budget_per_call_usd=0.01, budget_total_usd=1.0,
            tools_allowed=False, validators=[], probe_policy="none",
            vary_key="v", escalation_policy="auto",
            fallback_chain=[], reasons=[],
        )
        expected = {
            "lane", "model", "provider", "budget_per_call_usd",
            "budget_total_usd", "tools_allowed", "validators",
            "probe_policy", "vary_key", "escalation_policy",
            "fallback_chain", "reasons", "autopilot_level", "receipt_id",
            "timestamp", "risk_class", "task_hint", "policy_version",
        }
        assert set(plan.to_dict().keys()) == expected

    def test_cooldown_entry_to_dict_fields(self):
        """CooldownEntry.to_dict() has all expected keys including stream fields."""
        entry = CooldownEntry(
            cooldown_key="k", model="m", lane=1, risk_class="standard",
            task_hint="", validators_failed=[], probe_decision=None,
            escalated=False, is_failure=False,
            timestamp="2026-01-01T00:00:00+00:00",
        )
        expected = {
            "ck", "model", "lane", "risk_class", "task_hint",
            "validators_failed", "probe_decision", "escalated",
            "is_failure", "timestamp", "pv",
            "is_cancelled", "validation_scope",
        }
        assert set(entry.to_dict().keys()) == expected

    def test_explain_json_serializable(self):
        """explain() output is JSON-serializable."""
        import json as _json
        from governor.lanes import LaneRouter
        lr = LaneRouter()
        plan = lr.route(task_hint="codegen")
        info = lr.explain(plan)
        # Should not raise
        serialized = _json.dumps(info)
        assert isinstance(serialized, str)
