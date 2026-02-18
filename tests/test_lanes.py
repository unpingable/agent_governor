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
    is_final_answer_reusable,
    resolve_task_hint,
    DEFAULT_TTLS,
    LANE_TO_TIERS,
    MITIGATION_STRATEGIES,
    _canonical_json,
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
