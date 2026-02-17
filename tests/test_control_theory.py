# SPDX-License-Identifier: Apache-2.0
"""Tests for control_theory.py — R_t = (P_t * D_t) / E_t.

~120 tests across 17 test classes.
"""

import math
import time

import pytest

from governor.control_theory import (
    # Enums
    Regime,
    GovernorDecision,
    RiskAggregation,
    # Dataclasses
    ToolPowerMetrics,
    FeedbackDelayComponents,
    EvidenceComponents,
    RiskCalculation,
    RiskWindow,
    PrivilegeTier,
    CapabilityEnvelope,
    ToolGateRequirements,
    OpenLoopMetrics,
    EpisodeRiskMetrics,
    ReceiptsCurrencyModel,
    GovernorCheckResult,
    # Events
    RiskIndexEvent,
    CapabilityChangeEvent,
    RegimeTransitionEvent,
    GovernorDecisionEvent,
    OpenLoopDetectedEvent,
    GlassCannonDetectedEvent,
    # Constants
    EPSILON,
    DEFAULT_REGIME_THRESHOLDS,
    DEFAULT_TOOL_POWER,
    DEFAULT_E_MIN,
    DEFAULT_TAU,
    DEFAULT_DELAY,
    DEFAULT_PRIVILEGE_TIERS,
    # Functions
    compute_power,
    compute_delay,
    compute_evidence,
    compute_risk,
    classify_regime,
    update_ema,
    compute_sma,
    compute_worst_case,
    compute_p_max,
    select_privilege_tier,
    detect_open_loop,
    compute_sensitivity,
    aggregate_episode_risk,
    governor_check,
    # Controller
    RiskController,
)


# ---------------------------------------------------------------------------
# TestRegime
# ---------------------------------------------------------------------------


class TestRegime:
    def test_enum_values(self):
        assert Regime.SAFE.value == "safe"
        assert Regime.ELASTIC.value == "elastic"
        assert Regime.DANGEROUS.value == "dangerous"
        assert Regime.RUNAWAY.value == "runaway"

    def test_severity_ordering(self):
        assert Regime.SAFE.severity < Regime.ELASTIC.severity
        assert Regime.ELASTIC.severity < Regime.DANGEROUS.severity
        assert Regime.DANGEROUS.severity < Regime.RUNAWAY.severity

    def test_severity_values(self):
        assert Regime.SAFE.severity == 0
        assert Regime.RUNAWAY.severity == 3

    def test_recommended_actions(self):
        assert Regime.SAFE.recommended_action == "CONTINUE"
        assert Regime.RUNAWAY.recommended_action == "HALT"

    def test_string_serialization(self):
        assert Regime("safe") == Regime.SAFE
        assert str(Regime.SAFE) == "Regime.SAFE"


# ---------------------------------------------------------------------------
# TestGovernorDecision
# ---------------------------------------------------------------------------


class TestGovernorDecision:
    def test_enum_values(self):
        assert GovernorDecision.ALLOW.value == "allow"
        assert GovernorDecision.DENY.value == "deny"
        assert GovernorDecision.DEMOTE.value == "demote"
        assert GovernorDecision.HALT.value == "halt"

    def test_string_construction(self):
        assert GovernorDecision("allow") == GovernorDecision.ALLOW

    def test_all_values_present(self):
        assert len(GovernorDecision) == 4


# ---------------------------------------------------------------------------
# TestRiskAggregation
# ---------------------------------------------------------------------------


class TestRiskAggregation:
    def test_enum_values(self):
        assert RiskAggregation.EMA.value == "ema"
        assert RiskAggregation.SMA.value == "sma"
        assert RiskAggregation.WORST_CASE.value == "worst_case"

    def test_all_values_present(self):
        assert len(RiskAggregation) == 3


# ---------------------------------------------------------------------------
# TestToolPowerMetrics
# ---------------------------------------------------------------------------


class TestToolPowerMetrics:
    def test_creation(self):
        m = ToolPowerMetrics(privilege=0.5, blast=0.3, irreversibility=0.5)
        assert m.privilege == 0.5
        assert m.blast == 0.3
        assert m.irreversibility == 0.5

    def test_power_computation(self):
        m = ToolPowerMetrics(privilege=0.5, blast=0.3, irreversibility=0.5)
        assert m.power == pytest.approx(0.075)

    def test_validation_privilege(self):
        with pytest.raises(ValueError, match="privilege"):
            ToolPowerMetrics(privilege=1.5, blast=0.5, irreversibility=0.5)

    def test_validation_negative(self):
        with pytest.raises(ValueError, match="blast"):
            ToolPowerMetrics(privilege=0.5, blast=-0.1, irreversibility=0.5)

    def test_zero_power(self):
        m = ToolPowerMetrics(privilege=0.0, blast=0.5, irreversibility=0.5)
        assert m.power == 0.0

    def test_max_power(self):
        m = ToolPowerMetrics(privilege=1.0, blast=1.0, irreversibility=1.0)
        assert m.power == 1.0

    def test_serialization_roundtrip(self):
        m = ToolPowerMetrics(privilege=0.8, blast=0.7, irreversibility=0.6)
        d = m.to_dict()
        m2 = ToolPowerMetrics.from_dict(d)
        assert m2.privilege == m.privilege
        assert m2.blast == m.blast
        assert m2.irreversibility == m.irreversibility

    def test_spec_values(self):
        """Verify values match CONTROL_THEORY_SPEC table."""
        wf = DEFAULT_TOOL_POWER["write_file"]
        assert wf.power == pytest.approx(0.075)

        es = DEFAULT_TOOL_POWER["execute_shell"]
        assert es.power == pytest.approx(0.448)

        dp = DEFAULT_TOOL_POWER["deploy_production"]
        assert dp.power == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# TestFeedbackDelayComponents
# ---------------------------------------------------------------------------


class TestFeedbackDelayComponents:
    def test_creation(self):
        f = FeedbackDelayComponents(d_tool=0.1, d_telemetry=0.5, d_human=1.0)
        assert f.delay == 1.0

    def test_delay_is_max(self):
        f = FeedbackDelayComponents(d_tool=0.5, d_telemetry=0.1, d_human=0.3)
        assert f.delay == 0.5

    def test_validation_negative(self):
        with pytest.raises(ValueError, match="d_tool"):
            FeedbackDelayComponents(d_tool=-0.1, d_telemetry=0.5, d_human=0.0)

    def test_zero_delay(self):
        f = FeedbackDelayComponents(d_tool=0.0, d_telemetry=0.0, d_human=0.0)
        assert f.delay == 0.0

    def test_serialization_roundtrip(self):
        f = FeedbackDelayComponents(d_tool=0.2, d_telemetry=0.5, d_human=1.0)
        d = f.to_dict()
        f2 = FeedbackDelayComponents.from_dict(d)
        assert f2.d_tool == f.d_tool
        assert f2.delay == f.delay

    def test_dict_includes_delay(self):
        f = FeedbackDelayComponents(d_tool=0.3, d_telemetry=0.1, d_human=0.2)
        assert f.to_dict()["delay"] == 0.3


# ---------------------------------------------------------------------------
# TestEvidenceComponents
# ---------------------------------------------------------------------------


class TestEvidenceComponents:
    def test_creation(self):
        e = EvidenceComponents(receipts=0.8, provenance=0.6, verifiability=0.7, independence=0.5)
        assert e.evidence > 0

    def test_weighted_sum(self):
        e = EvidenceComponents(receipts=1.0, provenance=1.0, verifiability=1.0, independence=1.0)
        assert e.evidence == pytest.approx(1.0)

    def test_epsilon_clamp(self):
        e = EvidenceComponents(receipts=0.0, provenance=0.0, verifiability=0.0, independence=0.0)
        assert e.evidence == EPSILON

    def test_validation_out_of_range(self):
        with pytest.raises(ValueError, match="receipts"):
            EvidenceComponents(receipts=1.5, provenance=0.5, verifiability=0.5, independence=0.5)

    def test_validation_weights(self):
        with pytest.raises(ValueError, match="Weights must sum"):
            EvidenceComponents(
                receipts=0.5, provenance=0.5, verifiability=0.5, independence=0.5,
                w_receipts=0.5, w_provenance=0.5, w_verifiability=0.5, w_independence=0.5,
            )

    def test_serialization_roundtrip(self):
        e = EvidenceComponents(receipts=0.8, provenance=0.6, verifiability=0.7, independence=0.5)
        d = e.to_dict()
        e2 = EvidenceComponents.from_dict(d)
        assert e2.receipts == e.receipts
        assert e2.evidence == pytest.approx(e.evidence)


# ---------------------------------------------------------------------------
# TestCoreFunctions
# ---------------------------------------------------------------------------


class TestCoreFunctions:
    def test_compute_power(self):
        m = ToolPowerMetrics(privilege=0.5, blast=0.3, irreversibility=0.5)
        assert compute_power(m) == pytest.approx(0.075)

    def test_compute_delay_no_backlog(self):
        f = FeedbackDelayComponents(d_tool=0.1, d_telemetry=0.5, d_human=0.0)
        assert compute_delay(f) == 0.5

    def test_compute_delay_with_backlog(self):
        f = FeedbackDelayComponents(d_tool=0.5, d_telemetry=0.0, d_human=0.0)
        result = compute_delay(f, backlog=10, backlog_weight=0.1)
        assert result == pytest.approx(1.5)  # 0.5 + 0.1*10

    def test_compute_evidence(self):
        e = EvidenceComponents(receipts=0.8, provenance=0.6, verifiability=0.7, independence=0.5)
        result = compute_evidence(e)
        assert result > 0
        assert result <= 1.0

    def test_compute_risk_basic(self):
        r = compute_risk(power=0.5, delay=1.0, evidence=0.5)
        assert r == pytest.approx(1.0)

    def test_compute_risk_zero_power(self):
        assert compute_risk(power=0.0, delay=1.0, evidence=0.5) == 0.0

    def test_compute_risk_epsilon_evidence(self):
        r = compute_risk(power=0.5, delay=1.0, evidence=0.0)
        assert r > 0  # clamped to epsilon, not division by zero

    def test_classify_regime_safe(self):
        assert classify_regime(0.05) == Regime.SAFE

    def test_classify_regime_elastic(self):
        assert classify_regime(0.2) == Regime.ELASTIC

    def test_classify_regime_dangerous(self):
        assert classify_regime(0.5) == Regime.DANGEROUS

    def test_classify_regime_runaway(self):
        assert classify_regime(0.9) == Regime.RUNAWAY

    def test_classify_regime_boundary_t1(self):
        assert classify_regime(0.1) == Regime.ELASTIC

    def test_classify_regime_boundary_t2(self):
        assert classify_regime(0.4) == Regime.DANGEROUS

    def test_classify_regime_boundary_t3(self):
        assert classify_regime(0.8) == Regime.RUNAWAY

    def test_update_ema(self):
        r_bar = update_ema(1.0, 0.0, alpha=0.3)
        assert r_bar == pytest.approx(0.3)

    def test_compute_sma(self):
        assert compute_sma([0.1, 0.2, 0.3]) == pytest.approx(0.2)

    def test_compute_sma_empty(self):
        assert compute_sma([]) == 0.0

    def test_compute_worst_case(self):
        assert compute_worst_case([0.1, 0.5, 0.3]) == 0.5

    def test_compute_worst_case_empty(self):
        assert compute_worst_case([]) == 0.0

    def test_compute_p_max(self):
        p_max = compute_p_max(tau=0.5, evidence=0.8, delay=1.0)
        assert p_max == pytest.approx(0.4)

    def test_compute_p_max_zero_delay(self):
        p_max = compute_p_max(tau=0.5, evidence=0.8, delay=0.0)
        assert p_max > 0  # clamped to epsilon

    def test_select_privilege_tier_low(self):
        tier = select_privilege_tier(0.005)
        assert tier.level == 0

    def test_select_privilege_tier_high(self):
        tier = select_privilege_tier(1.0)
        assert tier.level == 5

    def test_select_privilege_tier_mid(self):
        tier = select_privilege_tier(0.35)
        assert tier.level == 2

    def test_detect_open_loop_true(self):
        assert detect_open_loop(actuation_rate=5.0, verification_rate=2.0) is True

    def test_detect_open_loop_false(self):
        assert detect_open_loop(actuation_rate=1.0, verification_rate=2.0) is False

    def test_detect_open_loop_zero_verification(self):
        assert detect_open_loop(actuation_rate=1.0, verification_rate=0.0) is True

    def test_detect_open_loop_both_zero(self):
        assert detect_open_loop(actuation_rate=0.0, verification_rate=0.0) is False

    def test_compute_sensitivity(self):
        s = compute_sensitivity(power=0.5, delay=1.0, evidence=0.8)
        assert "dr_dd" in s
        assert "dr_de" in s
        assert "risk" in s
        assert s["dr_dd"] == pytest.approx(0.5 / 0.8)
        assert s["dr_de"] == pytest.approx(-(0.5 * 1.0) / (0.8 * 0.8))


# ---------------------------------------------------------------------------
# TestAggregateEpisodeRisk
# ---------------------------------------------------------------------------


class TestAggregateEpisodeRisk:
    def test_additive(self):
        result = aggregate_episode_risk([0.1, 0.2, 0.3], mode="additive")
        assert result == pytest.approx(0.6)

    def test_discounted(self):
        result = aggregate_episode_risk([0.1, 0.2, 0.3], mode="discounted", gamma=0.5)
        # 0.1 + 0.5*0.2 + 0.25*0.3 = 0.1 + 0.1 + 0.075 = 0.275
        assert result == pytest.approx(0.275)

    def test_worst_step(self):
        result = aggregate_episode_risk([0.1, 0.5, 0.3], mode="worst_step")
        assert result == 0.5

    def test_empty(self):
        assert aggregate_episode_risk([], mode="additive") == 0.0

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Unknown aggregation mode"):
            aggregate_episode_risk([0.1], mode="invalid")


# ---------------------------------------------------------------------------
# TestRiskWindow
# ---------------------------------------------------------------------------


class TestRiskWindow:
    def test_add_and_ema(self):
        w = RiskWindow(ema_alpha=0.5)
        w.add(1.0)
        assert w.ema == pytest.approx(0.5)  # 0.5*1.0 + 0.5*0.0

    def test_sma(self):
        w = RiskWindow()
        w.add(0.2)
        w.add(0.4)
        w.add(0.6)
        assert w.sma == pytest.approx(0.4)

    def test_worst_case(self):
        w = RiskWindow()
        w.add(0.1)
        w.add(0.5)
        w.add(0.3)
        assert w.worst_case == 0.5

    def test_overflow(self):
        w = RiskWindow(max_size=3)
        for i in range(10):
            w.add(float(i))
        assert len(w.values) == 3

    def test_get_r_bar_modes(self):
        w = RiskWindow()
        w.add(0.1)
        w.add(0.5)
        w.add(0.3)
        assert w.get_r_bar(RiskAggregation.SMA) == pytest.approx(0.3)
        assert w.get_r_bar(RiskAggregation.WORST_CASE) == 0.5
        assert w.get_r_bar(RiskAggregation.EMA) == w.ema

    def test_empty_window(self):
        w = RiskWindow()
        assert w.sma == 0.0
        assert w.worst_case == 0.0
        assert w.ema == 0.0

    def test_serialization_roundtrip(self):
        w = RiskWindow(max_size=50, ema_alpha=0.4)
        w.add(0.2)
        w.add(0.5)
        d = w.to_dict()
        w2 = RiskWindow.from_dict(d)
        assert w2.max_size == 50
        assert w2.ema_alpha == 0.4
        assert w2.values == w.values
        assert w2.ema == pytest.approx(w.ema)

    def test_single_value(self):
        w = RiskWindow(ema_alpha=1.0)
        w.add(0.7)
        assert w.ema == pytest.approx(0.7)
        assert w.sma == pytest.approx(0.7)
        assert w.worst_case == 0.7


# ---------------------------------------------------------------------------
# TestLookupTables
# ---------------------------------------------------------------------------


class TestLookupTables:
    def test_tool_power_ordering(self):
        """Tool power should increase with tool severity."""
        rf = DEFAULT_TOOL_POWER["read_file"].power
        wf = DEFAULT_TOOL_POWER["write_file"].power
        es = DEFAULT_TOOL_POWER["execute_shell"].power
        dr = DEFAULT_TOOL_POWER["delete_recursive"].power
        dp = DEFAULT_TOOL_POWER["deploy_production"].power
        assert rf < wf < es < dr < dp

    def test_e_min_ordering(self):
        """Higher-risk tools should require more evidence."""
        assert DEFAULT_E_MIN["read_file"] < DEFAULT_E_MIN["write_file"]
        assert DEFAULT_E_MIN["write_file"] < DEFAULT_E_MIN["execute_shell"]

    def test_tau_ordering(self):
        """Higher-risk tools should have lower risk caps."""
        assert DEFAULT_TAU["deploy_production"] < DEFAULT_TAU["execute_shell"]
        assert DEFAULT_TAU["execute_shell"] < DEFAULT_TAU["read_file"]

    def test_delay_ordering(self):
        """Higher-risk tools should have higher typical delays."""
        assert DEFAULT_DELAY["read_file"] < DEFAULT_DELAY["write_file"]
        assert DEFAULT_DELAY["write_file"] < DEFAULT_DELAY["execute_shell"]

    def test_privilege_tier_ordering(self):
        """Tiers should be ordered by level."""
        for i in range(len(DEFAULT_PRIVILEGE_TIERS) - 1):
            assert DEFAULT_PRIVILEGE_TIERS[i].level < DEFAULT_PRIVILEGE_TIERS[i + 1].level
            assert DEFAULT_PRIVILEGE_TIERS[i].p_threshold < DEFAULT_PRIVILEGE_TIERS[i + 1].p_threshold


# ---------------------------------------------------------------------------
# TestOpenLoopMetrics
# ---------------------------------------------------------------------------


class TestOpenLoopMetrics:
    def test_gamma_normal(self):
        m = OpenLoopMetrics(actuation_rate=2.0, verification_rate=4.0)
        assert m.gamma == pytest.approx(0.5)
        assert m.is_open_loop is False

    def test_gamma_open_loop(self):
        m = OpenLoopMetrics(actuation_rate=5.0, verification_rate=2.0)
        assert m.gamma == pytest.approx(2.5)
        assert m.is_open_loop is True

    def test_gamma_zero_verification(self):
        m = OpenLoopMetrics(actuation_rate=1.0, verification_rate=0.0)
        assert m.gamma == float("inf")
        assert m.is_open_loop is True

    def test_gamma_both_zero(self):
        m = OpenLoopMetrics(actuation_rate=0.0, verification_rate=0.0)
        assert m.gamma == 0.0
        assert m.is_open_loop is False

    def test_serialization_roundtrip(self):
        m = OpenLoopMetrics(actuation_rate=3.0, verification_rate=2.0, backlog=5)
        d = m.to_dict()
        m2 = OpenLoopMetrics.from_dict(d)
        assert m2.actuation_rate == m.actuation_rate
        assert m2.backlog == 5


# ---------------------------------------------------------------------------
# TestReceiptsCurrencyModel
# ---------------------------------------------------------------------------


class TestReceiptsCurrencyModel:
    def test_tau_equivalence(self):
        m = ReceiptsCurrencyModel(eta=2.0, kappa=1.0)
        assert m.tau_equivalent == pytest.approx(0.5)

    def test_can_afford_true(self):
        m = ReceiptsCurrencyModel(eta=1.0, kappa=1.0)
        assert m.can_afford(power=0.3, delay=0.5, evidence=0.8) is True

    def test_can_afford_false(self):
        m = ReceiptsCurrencyModel(eta=1.0, kappa=1.0)
        assert m.can_afford(power=0.8, delay=1.0, evidence=0.5) is False

    def test_r_t_equivalence(self):
        """Currency model should be equivalent to R_t ≤ τ."""
        m = ReceiptsCurrencyModel(eta=1.0, kappa=1.0)
        P, D, E = 0.3, 0.5, 0.8
        r_t = compute_risk(P, D, E)
        can_afford = m.can_afford(P, D, E)
        bounded = r_t <= m.tau_equivalent
        assert can_afford == bounded


# ---------------------------------------------------------------------------
# TestGovernorCheck
# ---------------------------------------------------------------------------


class TestGovernorCheck:
    def test_allow_low_risk(self):
        result = governor_check(p_req=0.001, d_t=0.1, e_t=0.8, tool_class="read_file")
        assert result.decision == GovernorDecision.ALLOW

    def test_deny_insufficient_evidence(self):
        result = governor_check(p_req=0.5, d_t=0.5, e_t=0.2, tool_class="execute_shell")
        assert result.decision == GovernorDecision.DENY
        assert result.reason == "insufficient_evidence"

    def test_deny_risk_too_high(self):
        """deploy_production with low E, high D → risk exceeds tau, no viable demotion."""
        result = governor_check(
            p_req=0.9, d_t=1.0, e_t=0.7, tool_class="deploy_production",
        )
        # R_t = 0.9*1.0/0.7 ≈ 1.286, tau=0.2 → risk too high
        # P_max = 0.2*0.7/1.0 = 0.14
        # Highest tier fitting 0.14 → tier 1 (0.10)
        assert result.decision in (GovernorDecision.DENY, GovernorDecision.DEMOTE)

    def test_demote_risk_capped(self):
        """Tool risk exceeds tau, but demotion is possible."""
        result = governor_check(
            p_req=0.5, d_t=1.0, e_t=0.5, tool_class="execute_shell",
        )
        # R_t = 0.5*1.0/0.5 = 1.0, tau=0.4 → exceeds
        # P_max = 0.4*0.5/1.0 = 0.2
        # Tier 1 (0.10) fits
        assert result.decision == GovernorDecision.DEMOTE
        assert result.reason == "risk_capped"
        assert result.demoted_tier is not None

    def test_halt_runaway_regime(self):
        """When r_bar indicates RUNAWAY, should halt."""
        result = governor_check(
            p_req=0.001, d_t=0.1, e_t=0.8, tool_class="read_file",
            r_bar=0.9,
        )
        assert result.decision == GovernorDecision.HALT
        assert result.reason == "runaway_regime"

    def test_allow_with_custom_tables(self):
        result = governor_check(
            p_req=0.1, d_t=0.1, e_t=0.5, tool_class="custom_tool",
            e_min_table={"custom_tool": 0.1},
            tau_table={"custom_tool": 1.0},
        )
        assert result.decision == GovernorDecision.ALLOW

    def test_result_serialization(self):
        result = governor_check(p_req=0.001, d_t=0.1, e_t=0.8, tool_class="read_file")
        d = result.to_dict()
        r2 = GovernorCheckResult.from_dict(d)
        assert r2.decision == result.decision
        assert r2.regime == result.regime

    def test_result_has_risk(self):
        result = governor_check(p_req=0.075, d_t=0.2, e_t=0.5, tool_class="write_file")
        assert result.risk > 0

    def test_regime_in_result(self):
        result = governor_check(
            p_req=0.001, d_t=0.1, e_t=0.8, tool_class="read_file", r_bar=0.05,
        )
        assert result.regime == Regime.SAFE

    def test_deny_no_viable_tier(self):
        """When P_max is too low for any tier, deny outright."""
        result = governor_check(
            p_req=0.9, d_t=10.0, e_t=0.7, tool_class="deploy_production",
            tau_table={"deploy_production": 0.001},
        )
        # R_t huge, tau very low → P_max tiny → no tier fits
        assert result.decision == GovernorDecision.DENY
        assert result.reason == "risk_too_high"

    def test_e_min_boundary(self):
        """Evidence exactly at E_min should pass the gate."""
        result = governor_check(
            p_req=0.001, d_t=0.1, e_t=0.1, tool_class="read_file",
        )
        # E_min for read_file is 0.1, evidence is exactly 0.1
        assert result.decision != GovernorDecision.DENY or result.reason != "insufficient_evidence"

    def test_evidence_just_below_e_min(self):
        result = governor_check(
            p_req=0.001, d_t=0.1, e_t=0.09, tool_class="read_file",
        )
        assert result.decision == GovernorDecision.DENY
        assert result.reason == "insufficient_evidence"


# ---------------------------------------------------------------------------
# TestRiskController
# ---------------------------------------------------------------------------


class TestRiskController:
    def test_check_allow(self):
        ctrl = RiskController()
        result = ctrl.check("read_file")
        assert result.decision == GovernorDecision.ALLOW

    def test_check_deny_low_evidence(self):
        ctrl = RiskController()
        ctrl.current_evidence = 0.1
        result = ctrl.check("execute_shell")
        assert result.decision == GovernorDecision.DENY

    def test_check_updates_regime(self):
        ctrl = RiskController()
        ctrl.check("read_file", e_t=0.8)
        assert ctrl.current_regime in list(Regime)

    def test_update_manual(self):
        ctrl = RiskController()
        calc = ctrl.update(p_t=0.5, d_t=0.5, e_t=0.8)
        assert calc.risk > 0
        assert len(ctrl.window.values) == 1

    def test_capability_envelope(self):
        ctrl = RiskController()
        ctrl.current_evidence = 0.8
        ctrl.current_delay = 0.5
        env = ctrl.get_capability_envelope()
        assert env.p_max > 0
        assert env.tier.level >= 0

    def test_sensitivity(self):
        ctrl = RiskController()
        ctrl.current_power = 0.5
        ctrl.current_delay = 1.0
        ctrl.current_evidence = 0.8
        s = ctrl.get_sensitivity()
        assert "dr_dd" in s
        assert "dr_de" in s

    def test_episode_risk(self):
        ctrl = RiskController()
        ctrl.check("read_file", e_t=0.8)
        ctrl.check("write_file", e_t=0.5)
        metrics = ctrl.get_episode_risk()
        assert metrics.step_count == 2
        assert metrics.j_additive > 0

    def test_reset_episode(self):
        ctrl = RiskController()
        ctrl.check("read_file", e_t=0.8)
        metrics = ctrl.reset_episode()
        assert metrics.step_count == 1
        assert len(ctrl.episode_risks) == 0

    def test_open_loop_detection(self):
        ctrl = RiskController()
        m = ctrl.update_open_loop(actuation_rate=5.0, verification_rate=2.0)
        assert m.is_open_loop is True

    def test_backlog_affects_check(self):
        ctrl = RiskController()
        ctrl.update_open_loop(actuation_rate=1.0, verification_rate=1.0, backlog=10)
        result = ctrl.check("write_file", e_t=0.5, d_t=0.2)
        # d_t gets backlog added: 0.2 + 0.1*10 = 1.2
        assert result.risk > compute_risk(0.075, 0.2, 0.5)

    def test_events_buffer(self):
        ctrl = RiskController()
        ctrl.check("read_file", e_t=0.8)
        assert len(ctrl.events) > 0

    def test_events_capped(self):
        ctrl = RiskController()
        for _ in range(200):
            ctrl.check("read_file", e_t=0.8)
        assert len(ctrl.events) <= 1000

    def test_serialization_roundtrip(self):
        ctrl = RiskController(regime_thresholds=(0.15, 0.45, 0.85))
        ctrl.check("read_file", e_t=0.8)
        ctrl.check("write_file", e_t=0.5)
        d = ctrl.to_dict()
        ctrl2 = RiskController.from_dict(d)
        assert ctrl2.current_regime == ctrl.current_regime
        assert ctrl2.regime_thresholds == ctrl.regime_thresholds
        assert len(ctrl2.window.values) == len(ctrl.window.values)
        assert len(ctrl2.history) == len(ctrl.history)

    def test_history_tracked(self):
        ctrl = RiskController()
        ctrl.check("read_file", e_t=0.8)
        ctrl.check("write_file", e_t=0.5)
        assert len(ctrl.history) == 2

    def test_multi_step_escalation(self):
        """Repeated high-risk actions should escalate regime."""
        ctrl = RiskController(ema_alpha=0.5)
        for _ in range(20):
            ctrl.update(p_t=0.8, d_t=1.0, e_t=0.3)
        # R_t = 0.8*1.0/0.3 ≈ 2.67, EMA should converge high
        assert ctrl.current_regime.severity >= Regime.DANGEROUS.severity


# ---------------------------------------------------------------------------
# TestEvents
# ---------------------------------------------------------------------------


class TestEvents:
    def test_risk_index_event(self):
        e = RiskIndexEvent(risk=0.5, power=0.3, delay=0.5, evidence=0.8, regime=Regime.ELASTIC)
        d = e.to_dict()
        assert d["type"] == "risk_index"
        assert d["regime"] == "elastic"

    def test_capability_change_event(self):
        e = CapabilityChangeEvent(old_tier=1, new_tier=3, p_max=0.5)
        d = e.to_dict()
        assert d["type"] == "capability_change"

    def test_regime_transition_event(self):
        e = RegimeTransitionEvent(from_regime=Regime.SAFE, to_regime=Regime.ELASTIC, r_bar=0.15)
        d = e.to_dict()
        assert d["from_regime"] == "safe"
        assert d["to_regime"] == "elastic"

    def test_governor_decision_event(self):
        e = GovernorDecisionEvent(
            decision=GovernorDecision.DENY, tool_class="execute_shell",
            risk=0.9, reason="insufficient_evidence",
        )
        d = e.to_dict()
        assert d["decision"] == "deny"

    def test_open_loop_detected_event(self):
        e = OpenLoopDetectedEvent(gamma=2.5, actuation_rate=5.0, verification_rate=2.0, backlog=3)
        d = e.to_dict()
        assert d["type"] == "open_loop_detected"

    def test_glass_cannon_detected_event(self):
        e = GlassCannonDetectedEvent(dr_dd=1.5, dr_de=-2.0, risk=0.3, evidence=0.2)
        d = e.to_dict()
        assert d["type"] == "glass_cannon_detected"


# ---------------------------------------------------------------------------
# TestEdgeCases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_epsilon_clamping(self):
        """Zero evidence should be clamped, not cause division by zero."""
        r = compute_risk(power=0.5, delay=1.0, evidence=0.0)
        assert math.isfinite(r)
        assert r > 0

    def test_glass_cannon_4x(self):
        """Evidence degradation from 0.8→0.2 = 4x risk increase (spec Section 11)."""
        r1 = compute_risk(power=0.5, delay=1.0, evidence=0.8)
        r2 = compute_risk(power=0.5, delay=1.0, evidence=0.2)
        assert r2 == pytest.approx(r1 * 4.0)

    def test_glass_cannon_100x(self):
        """E/10 + D*10 = 100x risk (spec Section 2.1)."""
        P, D, E = 0.5, 1.0, 0.8
        r1 = compute_risk(P, D, E)
        r2 = compute_risk(P, D * 10, E / 10)
        assert r2 == pytest.approx(r1 * 100.0)

    def test_zero_power_risk(self):
        r = compute_risk(power=0.0, delay=1.0, evidence=0.5)
        assert r == 0.0

    def test_sensitivity_high_power(self):
        """With high power, sensitivity should be large."""
        s = compute_sensitivity(power=0.9, delay=1.0, evidence=0.5)
        assert abs(s["dr_dd"]) > 1.0
        assert abs(s["dr_de"]) > 1.0


# ---------------------------------------------------------------------------
# TestIntegrationScenarios
# ---------------------------------------------------------------------------


class TestIntegrationScenarios:
    def test_escalation_scenario(self):
        """Agent starts safe, evidence degrades, regime escalates."""
        ctrl = RiskController(ema_alpha=0.5)
        # Start with good evidence
        r1 = ctrl.check("write_file", e_t=0.9)
        assert r1.decision == GovernorDecision.ALLOW

        # Evidence degrades
        for _ in range(10):
            ctrl.update(p_t=0.5, d_t=0.5, e_t=0.1)

        # Now check — should be in worse regime
        assert ctrl.current_regime.severity >= Regime.ELASTIC.severity

    def test_evidence_improvement(self):
        """Good evidence should keep system safe."""
        ctrl = RiskController()
        for _ in range(10):
            ctrl.update(p_t=0.1, d_t=0.1, e_t=0.9)
        assert ctrl.current_regime == Regime.SAFE

    def test_self_regulation_via_backlog(self):
        """Growing backlog should automatically restrict capability via check()."""
        ctrl = RiskController()
        ctrl.update_open_loop(actuation_rate=3.0, verification_rate=1.0, backlog=20)

        # check() folds backlog into delay: effective D = 0.2 + 0.1*20 = 2.2
        result = ctrl.check("write_file", e_t=0.5, d_t=0.2)
        # R_t = 0.075 * 2.2 / 0.5 = 0.33, tau=0.5 → ALLOW but risky
        assert result.risk > compute_risk(0.075, 0.2, 0.5)  # Higher than without backlog

        # The effective delay restricts the capability envelope
        effective_delay = 0.2 + 0.1 * 20  # 2.2
        env = ctrl.get_capability_envelope(evidence=0.5, delay=effective_delay)
        # P_max = 0.5*0.5/2.2 ≈ 0.114
        assert env.p_max < 0.5  # Significantly restricted

    def test_currency_equivalence(self):
        """Currency model and R_t bound should agree."""
        model = ReceiptsCurrencyModel(eta=2.0, kappa=1.0)
        tau = model.tau_equivalent  # 0.5

        P, D, E = 0.3, 0.5, 0.8
        r_t = compute_risk(P, D, E)
        can_afford = model.can_afford(P, D, E)
        bounded = r_t <= tau
        assert can_afford == bounded


# ---------------------------------------------------------------------------
# TestRiskCalculation
# ---------------------------------------------------------------------------


class TestRiskCalculation:
    def test_creation(self):
        rc = RiskCalculation(power=0.5, delay=1.0, evidence=0.8, risk=0.625, regime=Regime.DANGEROUS)
        assert rc.power == 0.5
        assert rc.regime == Regime.DANGEROUS

    def test_serialization_roundtrip(self):
        rc = RiskCalculation(power=0.5, delay=1.0, evidence=0.8, risk=0.625, regime=Regime.ELASTIC)
        d = rc.to_dict()
        rc2 = RiskCalculation.from_dict(d)
        assert rc2.power == rc.power
        assert rc2.regime == rc.regime
        assert rc2.risk == rc.risk


# ---------------------------------------------------------------------------
# TestToolGateRequirements
# ---------------------------------------------------------------------------


class TestToolGateRequirements:
    def test_creation(self):
        tg = ToolGateRequirements(tool_class="write_file", e_min=0.3, tau=0.5)
        assert tg.tool_class == "write_file"

    def test_serialization_roundtrip(self):
        tg = ToolGateRequirements(tool_class="execute_shell", e_min=0.5, tau=0.4)
        d = tg.to_dict()
        tg2 = ToolGateRequirements.from_dict(d)
        assert tg2.tool_class == tg.tool_class
        assert tg2.e_min == tg.e_min


# ---------------------------------------------------------------------------
# TestCapabilityEnvelope
# ---------------------------------------------------------------------------


class TestCapabilityEnvelope:
    def test_creation(self):
        tier = PrivilegeTier(level=2, p_threshold=0.3, allowed_tools=["execute_shell_sandboxed"])
        env = CapabilityEnvelope(evidence=0.8, delay=0.5, tau=0.5, p_max=0.8, tier=tier)
        assert env.p_max == 0.8

    def test_serialization_roundtrip(self):
        tier = PrivilegeTier(level=1, p_threshold=0.1, allowed_tools=["write_file"])
        env = CapabilityEnvelope(evidence=0.5, delay=1.0, tau=0.5, p_max=0.25, tier=tier)
        d = env.to_dict()
        env2 = CapabilityEnvelope.from_dict(d)
        assert env2.p_max == env.p_max
        assert env2.tier.level == env.tier.level


# ---------------------------------------------------------------------------
# TestEpisodeRiskMetrics
# ---------------------------------------------------------------------------


class TestEpisodeRiskMetrics:
    def test_creation(self):
        m = EpisodeRiskMetrics(j_additive=1.0, j_discounted=0.8, j_worst=0.5, step_count=3)
        assert m.step_count == 3

    def test_serialization_roundtrip(self):
        m = EpisodeRiskMetrics(j_additive=1.5, j_discounted=1.2, j_worst=0.7, step_count=5)
        d = m.to_dict()
        m2 = EpisodeRiskMetrics.from_dict(d)
        assert m2.j_additive == m.j_additive
        assert m2.step_count == m.step_count
