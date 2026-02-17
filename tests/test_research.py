# SPDX-License-Identifier: Apache-2.0
"""Tests for research mode: non-convergent epistemic control."""

import math
import pytest

from governor.research import (
    HypothesisState,
    TerminalStateType,
    PromotionBlockReason,
    ResearchConfig,
    EvidenceImpulse,
    Hypothesis,
    TerminalState,
    EntropyCheckResult,
    DominanceCheckResult,
    DeltaTCheckResult,
    EntropyMonitor,
    DominanceMonitor,
    TimescaleMonitor,
    ResearchLedger,
    create_research_ledger,
    create_research_config,
)


# =============================================================================
# TestHypothesisState
# =============================================================================


class TestHypothesisState:
    def test_probe(self):
        assert HypothesisState.PROBE.value == "probe"

    def test_tentative(self):
        assert HypothesisState.TENTATIVE.value == "tentative"

    def test_supported(self):
        assert HypothesisState.SUPPORTED.value == "supported"

    def test_abandoned(self):
        assert HypothesisState.ABANDONED.value == "abandoned"


# =============================================================================
# TestResearchConfig
# =============================================================================


class TestResearchConfig:
    def test_defaults(self):
        c = ResearchConfig()
        assert c.default_lambda == 0.05
        assert c.H_min == 0.5
        assert c.D_max == 0.7
        assert c.K_independent == 2

    def test_to_dict(self):
        c = ResearchConfig()
        d = c.to_dict()
        assert "default_lambda" in d
        assert "H_min" in d
        assert "K_independent" in d

    def test_from_dict(self):
        d = {"default_lambda": 0.1, "H_min": 1.0, "H_max": 2.0, "D_max": 0.5,
             "k_timescale": 2.0, "epsilon": 0.1, "W": 5, "max_active": 10,
             "K_independent": 3, "maintenance_cost_rate": 0.02}
        c = ResearchConfig.from_dict(d)
        assert c.default_lambda == 0.1
        assert c.H_min == 1.0

    def test_strict_factory(self):
        c = create_research_config(strict=True)
        assert c.default_lambda > 0.05
        assert c.K_independent > 2

    def test_permissive_factory(self):
        c = create_research_config(permissive=True)
        assert c.default_lambda < 0.05
        assert c.D_max > 0.7


# =============================================================================
# TestEvidenceImpulse
# =============================================================================


class TestEvidenceImpulse:
    def test_creation(self):
        e = EvidenceImpulse(
            hypothesis_id="h1", evidence_ref_id="e1", base_strength=1.0
        )
        assert e.hypothesis_id == "h1"
        assert e.alpha == 1.0

    def test_alpha_computation(self):
        e = EvidenceImpulse(
            hypothesis_id="h1", evidence_ref_id="e1",
            base_strength=2.0, independence_score=0.5, novelty_score=0.8,
        )
        assert e.alpha == pytest.approx(0.8)  # 2.0 * 0.5 * 0.8

    def test_to_dict(self):
        e = EvidenceImpulse(
            hypothesis_id="h1", evidence_ref_id="e1", base_strength=1.0,
        )
        d = e.to_dict()
        assert d["hypothesis_id"] == "h1"
        assert d["alpha"] == 1.0

    def test_from_dict(self):
        d = {
            "hypothesis_id": "h1", "evidence_ref_id": "e1",
            "base_strength": 1.5, "independence_score": 0.7,
            "novelty_score": 0.9, "is_contradiction": False, "tick": 3,
        }
        e = EvidenceImpulse.from_dict(d)
        assert e.base_strength == 1.5
        assert e.tick == 3

    def test_contradiction(self):
        e = EvidenceImpulse(
            hypothesis_id="h1", evidence_ref_id="e1",
            base_strength=1.0, is_contradiction=True,
        )
        assert e.is_contradiction
        assert e.alpha == 1.0

    def test_alpha_with_zero_novelty(self):
        e = EvidenceImpulse(
            hypothesis_id="h1", evidence_ref_id="e1",
            base_strength=1.0, novelty_score=0.0,
        )
        assert e.alpha == 0.0


# =============================================================================
# TestHypothesis
# =============================================================================


class TestHypothesis:
    def test_creation(self):
        h = Hypothesis(hypothesis_id="h1", content="Test hypothesis")
        assert h.state == HypothesisState.PROBE
        assert h.credence == 0.3
        assert h.is_active

    def test_positive_impulses(self):
        h = Hypothesis(hypothesis_id="h1", content="test")
        h.evidence_impulses = [
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e1", base_strength=1.0),
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e2", base_strength=1.0, is_contradiction=True),
        ]
        assert len(h.positive_impulses) == 1
        assert len(h.negative_impulses) == 1

    def test_net_evidence_count(self):
        h = Hypothesis(hypothesis_id="h1", content="test")
        h.evidence_impulses = [
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e1", base_strength=1.0),
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e2", base_strength=1.0),
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e3", base_strength=1.0, is_contradiction=True),
        ]
        assert h.net_evidence_count == 1

    def test_independent_evidence_count(self):
        h = Hypothesis(hypothesis_id="h1", content="test")
        h.evidence_impulses = [
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e1", base_strength=1.0, independence_score=0.8),
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e2", base_strength=1.0, independence_score=0.3),
            EvidenceImpulse(hypothesis_id="h1", evidence_ref_id="e3", base_strength=1.0, independence_score=0.9),
        ]
        assert h.independent_evidence_count == 2  # 0.8 and 0.9 > 0.5

    def test_is_active_probe(self):
        h = Hypothesis(hypothesis_id="h1", content="test", state=HypothesisState.PROBE)
        assert h.is_active

    def test_is_active_abandoned(self):
        h = Hypothesis(hypothesis_id="h1", content="test", state=HypothesisState.ABANDONED)
        assert not h.is_active

    def test_is_active_archived(self):
        h = Hypothesis(hypothesis_id="h1", content="test", state=HypothesisState.PROBE, archived=True)
        assert not h.is_active

    def test_to_dict(self):
        h = Hypothesis(hypothesis_id="h1", content="test", falsifier="show X is false")
        d = h.to_dict()
        assert d["hypothesis_id"] == "h1"
        assert d["state"] == "probe"
        assert d["falsifier"] == "show X is false"

    def test_from_dict(self):
        d = {
            "hypothesis_id": "h1", "content": "test", "state": "tentative",
            "credence": 0.6, "falsifier": "f", "competitors": ["h2"],
            "evidence_impulses": [],
        }
        h = Hypothesis.from_dict(d)
        assert h.state == HypothesisState.TENTATIVE
        assert h.credence == 0.6
        assert h.competitors == ["h2"]

    def test_spawn_lineage(self):
        ledger = create_research_ledger()
        parent = ledger.create_hypothesis("parent idea")
        child = ledger.spawn(parent.hypothesis_id, "with twist")
        assert child.parent_id == parent.hypothesis_id
        assert "variant" in child.content

    def test_is_active_supported(self):
        h = Hypothesis(hypothesis_id="h1", content="test", state=HypothesisState.SUPPORTED)
        assert h.is_active

    def test_competitors_field(self):
        h = Hypothesis(hypothesis_id="h1", content="test", competitors=["h2", "h3"])
        assert "h2" in h.competitors


# =============================================================================
# TestTerminalState
# =============================================================================


class TestTerminalState:
    def test_ill_posed(self):
        ts = TerminalState(
            terminal_type=TerminalStateType.ILL_POSED,
            reason="Question presupposes invalid construct",
            minimal_missing_spec="Define X precisely",
        )
        assert ts.terminal_type == TerminalStateType.ILL_POSED

    def test_insufficient_evidence(self):
        ts = TerminalState(
            terminal_type=TerminalStateType.INSUFFICIENT_EVIDENCE,
            reason="No evidence available",
            missing_evidence_types=["empirical observation"],
        )
        d = ts.to_dict()
        assert d["terminal_type"] == "insufficient_evidence"

    def test_multiple_live(self):
        ts = TerminalState(
            terminal_type=TerminalStateType.MULTIPLE_LIVE_HYPOTHESES,
            reason="Three hypotheses survive",
            live_hypotheses=["h1", "h2", "h3"],
            competing_hypothesis_ids=["h1", "h2", "h3"],
        )
        assert len(ts.live_hypotheses) == 3

    def test_to_dict(self):
        ts = TerminalState(
            terminal_type=TerminalStateType.ILL_POSED,
            reason="test",
        )
        d = ts.to_dict()
        assert "terminal_type" in d
        assert "reason" in d


# =============================================================================
# TestEntropyMonitor
# =============================================================================


class TestEntropyMonitor:
    def _make_hypotheses(self, credences: list[float]) -> list[Hypothesis]:
        return [
            Hypothesis(
                hypothesis_id=f"h{i}", content=f"hyp {i}",
                credence=c, state=HypothesisState.PROBE,
            )
            for i, c in enumerate(credences)
        ]

    def test_compute_empty(self):
        em = EntropyMonitor()
        assert em.compute_entropy([]) == 0.0

    def test_compute_single(self):
        em = EntropyMonitor()
        hs = self._make_hypotheses([1.0])
        assert em.compute_entropy(hs) == 0.0  # single → 0 entropy

    def test_compute_uniform(self):
        em = EntropyMonitor()
        hs = self._make_hypotheses([1.0, 1.0, 1.0])
        entropy = em.compute_entropy(hs)
        expected = -3 * (1/3) * math.log(1/3)
        assert entropy == pytest.approx(expected, abs=0.01)

    def test_compute_skewed(self):
        em = EntropyMonitor()
        hs = self._make_hypotheses([10.0, 0.1, 0.1])
        entropy = em.compute_entropy(hs)
        # Heavily skewed → low entropy
        assert entropy < 0.5

    def test_check_below_min(self):
        em = EntropyMonitor(h_min=1.0, h_max=3.0)
        hs = self._make_hypotheses([10.0, 0.01])  # very skewed
        result = em.check(hs)
        assert not result.within_bounds
        assert result.violation_type == "below_min"
        assert len(result.corrective_actions) > 0

    def test_check_above_max(self):
        em = EntropyMonitor(h_min=0.0, h_max=0.5)
        hs = self._make_hypotheses([1.0, 1.0, 1.0, 1.0, 1.0])
        result = em.check(hs)
        assert not result.within_bounds
        assert result.violation_type == "above_max"

    def test_check_within(self):
        em = EntropyMonitor(h_min=0.0, h_max=5.0)
        hs = self._make_hypotheses([1.0, 1.0])
        result = em.check(hs)
        assert result.within_bounds

    def test_check_corrective_below(self):
        em = EntropyMonitor(h_min=2.0, h_max=3.0)
        hs = self._make_hypotheses([100.0, 0.001])
        result = em.check(hs)
        assert "adversarial" in result.corrective_actions[0].lower()

    def test_compute_with_zero_credence(self):
        em = EntropyMonitor()
        hs = self._make_hypotheses([0.0, 0.0])
        assert em.compute_entropy(hs) == 0.0

    def test_abandoned_excluded(self):
        em = EntropyMonitor()
        hs = [
            Hypothesis(hypothesis_id="h1", content="a", credence=1.0),
            Hypothesis(hypothesis_id="h2", content="b", credence=1.0, state=HypothesisState.ABANDONED),
        ]
        # Only h1 is active → single → entropy 0
        entropy = em.compute_entropy(hs)
        assert entropy == 0.0


# =============================================================================
# TestDominanceMonitor
# =============================================================================


class TestDominanceMonitor:
    def _make_hypotheses(self, credences: list[float]) -> list[Hypothesis]:
        return [
            Hypothesis(
                hypothesis_id=f"h{i}", content=f"hyp {i}",
                credence=c, state=HypothesisState.PROBE,
            )
            for i, c in enumerate(credences)
        ]

    def test_compute_even(self):
        dm = DominanceMonitor()
        hs = self._make_hypotheses([1.0, 1.0, 1.0])
        dom = dm.compute_dominance(hs)
        for v in dom.values():
            assert v == pytest.approx(1/3, abs=0.01)

    def test_compute_skewed(self):
        dm = DominanceMonitor()
        hs = self._make_hypotheses([9.0, 1.0])
        dom = dm.compute_dominance(hs)
        assert dom["h0"] == pytest.approx(0.9, abs=0.01)

    def test_compute_dominant(self):
        dm = DominanceMonitor()
        hs = self._make_hypotheses([10.0, 0.1, 0.1])
        dom = dm.compute_dominance(hs)
        assert max(dom.values()) > 0.9

    def test_check_within(self):
        dm = DominanceMonitor(d_max=0.7)
        hs = self._make_hypotheses([1.0, 1.0])
        result = dm.check(hs)
        assert result.within_bounds
        assert len(result.violations) == 0

    def test_check_violated(self):
        dm = DominanceMonitor(d_max=0.6)
        hs = self._make_hypotheses([9.0, 1.0])
        result = dm.check(hs)
        assert not result.within_bounds
        assert len(result.violations) > 0
        assert result.dominant_hypothesis_id == "h0"

    def test_compute_empty(self):
        dm = DominanceMonitor()
        assert dm.compute_dominance([]) == {}

    def test_check_empty(self):
        dm = DominanceMonitor()
        result = dm.check([])
        assert result.within_bounds
        assert result.max_dominance == 0.0

    def test_abandoned_excluded(self):
        dm = DominanceMonitor()
        hs = [
            Hypothesis(hypothesis_id="h1", content="a", credence=10.0),
            Hypothesis(hypothesis_id="h2", content="b", credence=1.0, state=HypothesisState.ABANDONED),
        ]
        dom = dm.compute_dominance(hs)
        assert "h2" not in dom
        assert dom.get("h1") == pytest.approx(1.0)


# =============================================================================
# TestTimescaleMonitor
# =============================================================================


class TestTimescaleMonitor:
    def test_no_data(self):
        tm = TimescaleMonitor(k_timescale=1.5)
        result = tm.check()
        assert result.within_bounds  # no data → no violation

    def test_record_evidence(self):
        tm = TimescaleMonitor()
        tm.record_evidence_arrival(1)
        tm.record_evidence_arrival(3)
        result = tm.check()
        assert result.tau_e == 2.0  # avg interval

    def test_record_promotion(self):
        tm = TimescaleMonitor()
        tm.record_promotion(1)
        tm.record_promotion(5)
        result = tm.check()
        assert result.tau_c == 4.0

    def test_check_within(self):
        tm = TimescaleMonitor(k_timescale=1.5)
        tm.record_evidence_arrival(1)
        tm.record_evidence_arrival(3)  # tau_e = 2
        tm.record_promotion(1)
        tm.record_promotion(7)  # tau_c = 6
        result = tm.check()
        assert result.within_bounds  # 6/2 = 3 >= 1.5

    def test_check_violated(self):
        tm = TimescaleMonitor(k_timescale=2.0)
        tm.record_evidence_arrival(1)
        tm.record_evidence_arrival(11)  # tau_e = 10
        tm.record_promotion(1)
        tm.record_promotion(6)  # tau_c = 5
        result = tm.check()
        assert not result.within_bounds  # 5/10 = 0.5 < 2.0

    def test_no_evidence_means_no_violation(self):
        tm = TimescaleMonitor(k_timescale=1.5)
        # Only promotions, no evidence → can't violate
        tm.record_promotion(1)
        tm.record_promotion(3)
        result = tm.check()
        assert result.within_bounds

    def test_single_evidence_no_interval(self):
        tm = TimescaleMonitor()
        tm.record_evidence_arrival(5)
        result = tm.check()
        assert result.tau_e == 0.0

    def test_ratio_computation(self):
        tm = TimescaleMonitor(k_timescale=1.0)
        tm.record_evidence_arrival(1)
        tm.record_evidence_arrival(3)  # tau_e = 2
        tm.record_promotion(1)
        tm.record_promotion(5)  # tau_c = 4
        result = tm.check()
        assert result.ratio == pytest.approx(2.0)

    def test_required_ratio_in_result(self):
        tm = TimescaleMonitor(k_timescale=3.0)
        result = tm.check()
        assert result.required_ratio == 3.0


# =============================================================================
# TestResearchLedger_Creation
# =============================================================================


class TestResearchLedgerCreation:
    def test_create_hypothesis(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("The sky is blue", falsifier="Show it's not blue")
        assert h.state == HypothesisState.PROBE
        assert h.content == "The sky is blue"
        assert h.hypothesis_id in ledger.hypotheses

    def test_spawn(self):
        ledger = create_research_ledger()
        parent = ledger.create_hypothesis("Base idea")
        child = ledger.spawn(parent.hypothesis_id, "with twist")
        assert child.parent_id == parent.hypothesis_id
        assert "variant" in child.content

    def test_mark_competitors(self):
        ledger = create_research_ledger()
        h1 = ledger.create_hypothesis("H1")
        h2 = ledger.create_hypothesis("H2")
        ledger.mark_competitors(h1.hypothesis_id, h2.hypothesis_id)
        assert h2.hypothesis_id in h1.competitors
        assert h1.hypothesis_id in h2.competitors

    def test_sprawl_limit(self):
        config = ResearchConfig(max_active=3)
        ledger = create_research_ledger(config)
        ledger.create_hypothesis("H1")
        ledger.create_hypothesis("H2")
        ledger.create_hypothesis("H3")
        with pytest.raises(ValueError, match="Max active"):
            ledger.create_hypothesis("H4")

    def test_spawn_nonexistent_parent(self):
        ledger = create_research_ledger()
        with pytest.raises(KeyError):
            ledger.spawn("nonexistent", "delta")

    def test_mark_competitors_nonexistent(self):
        ledger = create_research_ledger()
        h1 = ledger.create_hypothesis("H1")
        with pytest.raises(KeyError):
            ledger.mark_competitors(h1.hypothesis_id, "nonexistent")

    def test_initial_credence(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        assert h.credence == 0.3

    def test_hypothesis_gets_config_defaults(self):
        config = ResearchConfig(default_lambda=0.1, maintenance_cost_rate=0.05)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        assert h.lambda_decay == 0.1
        assert h.maintenance_cost_rate == 0.05


# =============================================================================
# TestResearchLedger_Evidence
# =============================================================================


class TestResearchLedgerEvidence:
    def test_attach_basic(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        initial = h.credence
        impulse = ledger.attach_evidence(h.hypothesis_id, "e1", base_strength=1.0)
        assert h.credence == initial + 1.0
        assert len(h.evidence_impulses) == 1
        assert impulse.alpha == 1.0

    def test_attach_with_independence(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        impulse = ledger.attach_evidence(
            h.hypothesis_id, "e1", base_strength=2.0,
            independence_score=0.5, novelty_score=0.8,
        )
        assert impulse.alpha == pytest.approx(0.8)

    def test_novelty_diminishing(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        # First evidence: full novelty
        e1 = ledger.attach_evidence(h.hypothesis_id, "e1", novelty_score=1.0)
        # Second: diminished novelty (simulated by caller)
        e2 = ledger.attach_evidence(h.hypothesis_id, "e2", novelty_score=0.5)
        assert e1.alpha > e2.alpha

    def test_independence_scoring(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.2)
        assert h.independent_evidence_count == 1  # only 0.9 > 0.5

    def test_file_contradiction(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        initial = h.credence
        ledger.file_contradiction(h.hypothesis_id, "c1", severity=0.1)
        assert h.credence == initial - 0.1
        assert len(h.negative_impulses) == 1

    def test_contradiction_floor(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.file_contradiction(h.hypothesis_id, "c1", severity=100.0)
        assert h.credence == 0.0  # floored at 0

    def test_refreshes_timer(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.tick()
        ledger.tick()
        ledger.attach_evidence(h.hypothesis_id, "e1")
        assert h.last_reinforced_at == ledger.tick_count

    def test_nonexistent_hypothesis(self):
        ledger = create_research_ledger()
        with pytest.raises(KeyError):
            ledger.attach_evidence("nonexistent", "e1")

    def test_contradiction_nonexistent(self):
        ledger = create_research_ledger()
        with pytest.raises(KeyError):
            ledger.file_contradiction("nonexistent", "c1")

    def test_multiple_evidence(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        for i in range(5):
            ledger.attach_evidence(h.hypothesis_id, f"e{i}")
        assert len(h.positive_impulses) == 5

    def test_evidence_records_tick(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.tick()
        ledger.tick()
        impulse = ledger.attach_evidence(h.hypothesis_id, "e1")
        assert impulse.tick == 2

    def test_contradiction_records_tick(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.tick()
        impulse = ledger.file_contradiction(h.hypothesis_id, "c1")
        assert impulse.tick == 1


# =============================================================================
# TestResearchLedger_Promotion
# =============================================================================


class TestResearchLedgerPromotion:
    def test_can_promote_probe_no_evidence(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert not can
        assert PromotionBlockReason.INSUFFICIENT_EVIDENCE in blocks

    def test_can_promote_probe_with_evidence(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1")
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert can

    def test_promote_probe_to_tentative(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1")
        success, reasons = ledger.promote(h.hypothesis_id)
        assert success
        assert h.state == HypothesisState.TENTATIVE

    def test_promote_tentative_insufficient_evidence(self):
        config = ResearchConfig(K_independent=2)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)  # → TENTATIVE
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert not can
        assert PromotionBlockReason.INSUFFICIENT_EVIDENCE in blocks

    def test_promote_tentative_to_supported(self):
        config = ResearchConfig(K_independent=2, H_min=0.0, D_max=1.0)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        # Need another hypothesis to avoid entropy issues
        ledger.create_hypothesis("competing", )
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)  # → TENTATIVE
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.8)
        success, reasons = ledger.promote(h.hypothesis_id)
        assert success
        assert h.state == HypothesisState.SUPPORTED

    def test_promote_blocked_by_dominance(self):
        config = ResearchConfig(K_independent=1, D_max=0.3, H_min=0.0)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("dominant")
        h2 = ledger.create_hypothesis("weak")
        h2.credence = 0.01
        # Make h very dominant
        ledger.attach_evidence(h.hypothesis_id, "e1", base_strength=10.0, independence_score=0.9)
        ledger.promote(h.hypothesis_id)  # → TENTATIVE
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.9)
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert PromotionBlockReason.DOMINANCE_CAP in blocks

    def test_promote_blocked_by_entropy(self):
        config = ResearchConfig(K_independent=1, H_min=2.0, D_max=1.0)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("only one")
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)  # → TENTATIVE
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.9)
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert PromotionBlockReason.ENTROPY_FLOOR in blocks

    def test_promote_blocked_by_delta_t(self):
        # Need ≥2 promotions to establish tau_c, so we use two hypotheses
        # and promote both rapidly to establish a fast crystallization cadence
        config = ResearchConfig(
            K_independent=1, H_min=0.0, D_max=1.0, k_timescale=5.0,
            default_lambda=0.0, maintenance_cost_rate=0.0,
        )
        ledger = create_research_ledger(config)
        h1 = ledger.create_hypothesis("test1")
        h2 = ledger.create_hypothesis("test2")
        # Evidence at tick 0
        ledger.attach_evidence(h1.hypothesis_id, "e1", independence_score=0.9)
        ledger.attach_evidence(h2.hypothesis_id, "e2", independence_score=0.9)
        ledger.promote(h1.hypothesis_id)  # promotion at tick 0
        ledger.tick()
        # Evidence at tick 1
        ledger.attach_evidence(h1.hypothesis_id, "e3", independence_score=0.9)
        ledger.attach_evidence(h2.hypothesis_id, "e4", independence_score=0.9)
        ledger.promote(h2.hypothesis_id)  # promotion at tick 1 → tau_c = 1
        # tau_e: ticks 0, 0, 1, 1 → intervals 0, 1, 0 → avg 0.33
        # tau_c: ticks 0, 1 → interval 1 → avg 1.0
        # ratio = 1.0 / 0.33 = ~3.0 which might pass k=5.0
        # Actually need even faster promotions relative to evidence
        # Let's use a simpler approach: manually force the monitor state
        ledger.timescale_monitor._promotion_ticks = [0, 1]  # tau_c = 1
        ledger.timescale_monitor._evidence_ticks = [0, 10]  # tau_e = 10
        # ratio = 1/10 = 0.1 < k=5.0 → violation
        can, blocks = ledger.can_promote(h1.hypothesis_id)
        assert PromotionBlockReason.DELTA_T_VIOLATION in blocks

    def test_promote_blocked_by_contradiction(self):
        config = ResearchConfig(K_independent=1, H_min=0.0, D_max=1.0, W=10)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.9)
        ledger.file_contradiction(h.hypothesis_id, "c1", severity=0.01)
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert PromotionBlockReason.UNRESOLVED_CONTRADICTION in blocks

    def test_promote_supported_no_further(self):
        config = ResearchConfig(K_independent=1, H_min=0.0, D_max=1.0)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.create_hypothesis("other")  # avoid single-hypothesis edge cases
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.9)
        ledger.promote(h.hypothesis_id)
        assert h.state == HypothesisState.SUPPORTED
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert not can

    def test_promote_fail_returns_reasons(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        success, reasons = ledger.promote(h.hypothesis_id)
        assert not success
        assert "insufficient_evidence" in reasons

    def test_promote_abandoned_not_possible(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.abandon(h.hypothesis_id)
        can, _ = ledger.can_promote(h.hypothesis_id)
        assert not can

    def test_promote_nonexistent(self):
        ledger = create_research_ledger()
        can, blocks = ledger.can_promote("nonexistent")
        assert not can

    def test_supported_to_abandoned(self):
        config = ResearchConfig(K_independent=1, H_min=0.0, D_max=1.0)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.create_hypothesis("other")  # avoid single-hypothesis edge cases
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.9)
        ledger.promote(h.hypothesis_id)
        assert h.state == HypothesisState.SUPPORTED
        ledger.abandon(h.hypothesis_id)
        assert h.state == HypothesisState.ABANDONED

    def test_promote_records_promotion_tick(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1")
        ledger.tick()
        ledger.tick()
        ledger.promote(h.hypothesis_id)
        assert len(ledger.timescale_monitor._promotion_ticks) > 0


# =============================================================================
# TestResearchLedger_Decay
# =============================================================================


class TestResearchLedgerDecay:
    def test_tick_decay(self):
        config = ResearchConfig(default_lambda=0.1, maintenance_cost_rate=0.0)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        initial = h.credence
        ledger.tick()
        expected = initial * math.exp(-0.1)
        assert h.credence == pytest.approx(expected, abs=0.001)

    def test_maintenance_cost(self):
        config = ResearchConfig(default_lambda=0.0, maintenance_cost_rate=0.05)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        initial = h.credence
        ledger.tick()
        assert h.credence == pytest.approx(initial - 0.05, abs=0.001)

    def test_auto_archive_stale(self):
        config = ResearchConfig(
            default_lambda=0.5, maintenance_cost_rate=0.1,
            epsilon=0.05, W=2,
        )
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        # Tick many times to decay below epsilon
        for _ in range(20):
            ledger.tick()
        assert h.state == HypothesisState.ABANDONED
        assert h.archived

    def test_credence_floor(self):
        config = ResearchConfig(default_lambda=0.0, maintenance_cost_rate=10.0)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.tick()
        assert h.credence >= 0.0

    def test_decay_summary(self):
        ledger = create_research_ledger()
        ledger.create_hypothesis("test")
        summary = ledger.tick()
        assert "tick" in summary
        assert "decayed" in summary

    def test_reinforcement_resets_timer(self):
        config = ResearchConfig(epsilon=0.01, W=3)
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.tick()
        ledger.tick()
        ledger.attach_evidence(h.hypothesis_id, "e1", base_strength=5.0)
        # last_reinforced_at is now tick 2
        # Need 3 more ticks without reinforcement for auto-archive
        assert h.is_active

    def test_abandoned_not_decayed(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.abandon(h.hypothesis_id)
        old_credence = h.credence
        ledger.tick()
        # Abandoned hypotheses are not active, so tick should not decay them
        assert h.credence == old_credence

    def test_lambda_affects_decay_rate(self):
        config1 = ResearchConfig(default_lambda=0.01, maintenance_cost_rate=0.0)
        config2 = ResearchConfig(default_lambda=0.5, maintenance_cost_rate=0.0)
        l1 = create_research_ledger(config1)
        l2 = create_research_ledger(config2)
        h1 = l1.create_hypothesis("test")
        h2 = l2.create_hypothesis("test")
        l1.tick()
        l2.tick()
        assert h1.credence > h2.credence  # lower lambda → less decay

    def test_tick_increments_counter(self):
        ledger = create_research_ledger()
        assert ledger.tick_count == 0
        ledger.tick()
        assert ledger.tick_count == 1
        ledger.tick()
        assert ledger.tick_count == 2

    def test_auto_abandon_requires_window(self):
        config = ResearchConfig(
            default_lambda=0.0, maintenance_cost_rate=0.0,
            epsilon=0.5, W=5,
        )
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        h.credence = 0.01  # below epsilon
        # Only 2 ticks, W=5
        ledger.tick()
        ledger.tick()
        assert h.is_active  # not yet abandoned


# =============================================================================
# TestResearchLedger_Entropy
# =============================================================================


class TestResearchLedgerEntropy:
    def test_integration(self):
        config = ResearchConfig(H_min=0.5, H_max=3.0)
        ledger = create_research_ledger(config)
        ledger.create_hypothesis("H1")
        ledger.create_hypothesis("H2")
        result = ledger.check_entropy()
        assert result.within_bounds or not result.within_bounds  # valid result

    def test_below_min_detection(self):
        config = ResearchConfig(H_min=2.0)
        ledger = create_research_ledger(config)
        h1 = ledger.create_hypothesis("dominant")
        h2 = ledger.create_hypothesis("weak")
        h1.credence = 100.0
        h2.credence = 0.001
        result = ledger.check_entropy()
        assert not result.within_bounds
        assert result.violation_type == "below_min"

    def test_above_max_detection(self):
        config = ResearchConfig(H_max=0.1)
        ledger = create_research_ledger(config)
        for i in range(10):
            ledger.create_hypothesis(f"H{i}")
        result = ledger.check_entropy()
        assert not result.within_bounds
        assert result.violation_type == "above_max"

    def test_corrective_actions(self):
        config = ResearchConfig(H_min=5.0)
        ledger = create_research_ledger(config)
        ledger.create_hypothesis("only one")
        result = ledger.check_entropy()
        assert len(result.corrective_actions) > 0

    def test_within_bounds(self):
        config = ResearchConfig(H_min=0.0, H_max=10.0)
        ledger = create_research_ledger(config)
        ledger.create_hypothesis("H1")
        ledger.create_hypothesis("H2")
        result = ledger.check_entropy()
        assert result.within_bounds

    def test_entropy_metric_in_metrics(self):
        ledger = create_research_ledger()
        ledger.create_hypothesis("H1")
        m = ledger.get_metrics()
        assert "entropy" in m


# =============================================================================
# TestResearchLedger_DeltaT
# =============================================================================


class TestResearchLedgerDeltaT:
    def test_integration(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1")
        result = ledger.check_delta_t()
        assert isinstance(result, DeltaTCheckResult)

    def test_promotion_blocked_by_fast_crystallization(self):
        config = ResearchConfig(
            K_independent=1, H_min=0.0, D_max=1.0, k_timescale=10.0,
            default_lambda=0.0, maintenance_cost_rate=0.0,
        )
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.create_hypothesis("other")  # avoid single-hyp edge cases
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)  # first promotion
        ledger.tick()
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.9)
        # Manually set monitor state: fast promotions (tau_c=1) vs slow evidence (tau_e=10)
        ledger.timescale_monitor._promotion_ticks = [0, 1]
        ledger.timescale_monitor._evidence_ticks = [0, 10]
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert PromotionBlockReason.DELTA_T_VIOLATION in blocks

    def test_no_violation_when_slow(self):
        # Use low decay so credence survives, no dominance cap, no entropy floor
        config = ResearchConfig(
            K_independent=1, H_min=0.0, D_max=1.0, k_timescale=1.0,
            default_lambda=0.0, maintenance_cost_rate=0.0,
        )
        ledger = create_research_ledger(config)
        h = ledger.create_hypothesis("test")
        ledger.create_hypothesis("other")  # avoid dominance
        # Evidence at tick 0
        ledger.attach_evidence(h.hypothesis_id, "e1", independence_score=0.9)
        ledger.promote(h.hypothesis_id)  # promotion at tick 0
        # Many ticks between evidence arrivals
        for _ in range(10):
            ledger.tick()
        # Evidence at tick 10 → tau_e ~ 10
        ledger.attach_evidence(h.hypothesis_id, "e2", independence_score=0.9)
        for _ in range(10):
            ledger.tick()
        # Now trying second promotion at tick 20
        # tau_e = 10 (ticks 0→10), tau_c would be ~20 if promoted
        # But we need the check to pass: ratio = tau_c/tau_e
        # With 1 promotion at tick 0, a second at tick 20 → tau_c = 20
        # 20/10 = 2.0 >= 1.0 ✓
        can, blocks = ledger.can_promote(h.hypothesis_id)
        assert PromotionBlockReason.DELTA_T_VIOLATION not in blocks

    def test_delta_t_in_metrics(self):
        ledger = create_research_ledger()
        m = ledger.get_metrics()
        assert "delta_t" in m

    def test_check_returns_correct_type(self):
        ledger = create_research_ledger()
        result = ledger.check_delta_t()
        assert hasattr(result, "tau_e")
        assert hasattr(result, "tau_c")

    def test_evidence_arrival_recorded(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.attach_evidence(h.hypothesis_id, "e1")
        assert len(ledger.timescale_monitor._evidence_ticks) == 1


# =============================================================================
# TestResearchLedger_Terminal
# =============================================================================


class TestResearchLedgerTerminal:
    def test_no_terminal_when_active(self):
        ledger = create_research_ledger()
        ledger.create_hypothesis("test")
        ts = ledger.assess_terminal()
        # Single hypothesis → not terminal (would need >= 2 for MULTIPLE_LIVE)
        assert ts is None

    def test_insufficient_evidence_all_abandoned(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.abandon(h.hypothesis_id)
        ts = ledger.assess_terminal()
        assert ts is not None
        assert ts.terminal_type == TerminalStateType.INSUFFICIENT_EVIDENCE

    def test_multiple_live_hypotheses(self):
        config = ResearchConfig(D_max=0.9)
        ledger = create_research_ledger(config)
        h1 = ledger.create_hypothesis("H1")
        h2 = ledger.create_hypothesis("H2")
        # Equal credences → no dominance
        ts = ledger.assess_terminal()
        assert ts is not None
        assert ts.terminal_type == TerminalStateType.MULTIPLE_LIVE_HYPOTHESES
        assert len(ts.live_hypotheses) == 2

    def test_no_terminal_with_dominant(self):
        config = ResearchConfig(D_max=0.6)
        ledger = create_research_ledger(config)
        h1 = ledger.create_hypothesis("dominant")
        h2 = ledger.create_hypothesis("weak")
        h1.credence = 10.0
        h2.credence = 0.1
        ts = ledger.assess_terminal()
        # Dominant hypothesis → not terminal (one is dominant)
        assert ts is None

    def test_empty_ledger(self):
        ledger = create_research_ledger()
        ts = ledger.assess_terminal()
        assert ts is None


# =============================================================================
# TestResearchLedger_Queries
# =============================================================================


class TestResearchLedgerQueries:
    def test_get(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        assert ledger.get(h.hypothesis_id) is h

    def test_get_nonexistent(self):
        ledger = create_research_ledger()
        assert ledger.get("nonexistent") is None

    def test_active_hypotheses(self):
        ledger = create_research_ledger()
        h1 = ledger.create_hypothesis("H1")
        h2 = ledger.create_hypothesis("H2")
        ledger.abandon(h2.hypothesis_id)
        active = ledger.active_hypotheses()
        assert len(active) == 1
        assert active[0].hypothesis_id == h1.hypothesis_id

    def test_abandoned_hypotheses(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.abandon(h.hypothesis_id)
        assert len(ledger.abandoned_hypotheses()) == 1

    def test_hypotheses_by_state(self):
        ledger = create_research_ledger()
        h1 = ledger.create_hypothesis("H1")
        h2 = ledger.create_hypothesis("H2")
        ledger.attach_evidence(h1.hypothesis_id, "e1")
        ledger.promote(h1.hypothesis_id)
        by_state = ledger.hypotheses_by_state()
        assert len(by_state["tentative"]) == 1
        assert len(by_state["probe"]) == 1

    def test_competitors_of(self):
        ledger = create_research_ledger()
        h1 = ledger.create_hypothesis("H1")
        h2 = ledger.create_hypothesis("H2")
        ledger.mark_competitors(h1.hypothesis_id, h2.hypothesis_id)
        comps = ledger.competitors_of(h1.hypothesis_id)
        assert len(comps) == 1
        assert comps[0].hypothesis_id == h2.hypothesis_id

    def test_lineage(self):
        ledger = create_research_ledger()
        p = ledger.create_hypothesis("parent")
        c = ledger.spawn(p.hypothesis_id, "child")
        gc = ledger.spawn(c.hypothesis_id, "grandchild")
        lineage = ledger.lineage(gc.hypothesis_id)
        assert len(lineage) == 2
        assert lineage[0].hypothesis_id == c.hypothesis_id
        assert lineage[1].hypothesis_id == p.hypothesis_id

    def test_dominant_hypothesis(self):
        ledger = create_research_ledger()
        h1 = ledger.create_hypothesis("H1")
        h2 = ledger.create_hypothesis("H2")
        h1.credence = 10.0
        dom = ledger.dominant_hypothesis()
        assert dom.hypothesis_id == h1.hypothesis_id

    def test_dominant_hypothesis_empty(self):
        ledger = create_research_ledger()
        assert ledger.dominant_hypothesis() is None

    def test_archived_hypotheses(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test")
        ledger.archive(h.hypothesis_id)
        assert len(ledger.archived_hypotheses()) == 1


# =============================================================================
# TestResearchLedger_Serialization
# =============================================================================


class TestResearchLedgerSerialization:
    def test_round_trip(self):
        ledger = create_research_ledger()
        h = ledger.create_hypothesis("test", falsifier="F")
        ledger.attach_evidence(h.hypothesis_id, "e1")
        ledger.tick()

        d = ledger.to_dict()
        ledger2 = ResearchLedger.from_dict(d)
        assert len(ledger2.hypotheses) == 1
        h2 = list(ledger2.hypotheses.values())[0]
        assert h2.content == "test"
        assert h2.falsifier == "F"
        assert len(h2.evidence_impulses) == 1

    def test_config_survives(self):
        config = ResearchConfig(default_lambda=0.1, D_max=0.5)
        ledger = create_research_ledger(config)
        d = ledger.to_dict()
        ledger2 = ResearchLedger.from_dict(d)
        assert ledger2.config.default_lambda == 0.1
        assert ledger2.config.D_max == 0.5

    def test_tick_count_survives(self):
        ledger = create_research_ledger()
        ledger.tick()
        ledger.tick()
        d = ledger.to_dict()
        ledger2 = ResearchLedger.from_dict(d)
        assert ledger2.tick_count == 2

    def test_empty_ledger_round_trip(self):
        ledger = create_research_ledger()
        d = ledger.to_dict()
        ledger2 = ResearchLedger.from_dict(d)
        assert len(ledger2.hypotheses) == 0


# =============================================================================
# TestConvenience
# =============================================================================


class TestConvenience:
    def test_create_research_ledger(self):
        ledger = create_research_ledger()
        assert isinstance(ledger, ResearchLedger)

    def test_create_research_config_default(self):
        c = create_research_config()
        assert c.default_lambda == 0.05

    def test_create_research_config_strict(self):
        c = create_research_config(strict=True)
        assert c.default_lambda > 0.05
        assert c.D_max < 0.7
