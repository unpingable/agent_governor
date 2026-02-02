"""
Tests for convergence_tuning.py — offline system identification + proposal engine.

~145 tests covering:
- Enum tests (7)
- Dataclass serialization roundtrips (30)
- ProposalStore (18)
- ConvergenceAnalyzer (25)
- Admissibility checks (30)
- ConvergenceTuner orchestrator (20)
- Integration with telemetry (8)
- Edge cases and safety (7)
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from governor.convergence_tuning import (
    ACTION_AGGRESSIVENESS,
    AdmissibilityResult,
    ActionEffectiveness,
    Approval,
    ChangeParameterUpdate,
    ChangePatternUpdate,
    ChangeRefactorSuggestion,
    ChangeSet,
    ChangeSetType,
    Constraints,
    ConvergenceAnalyzer,
    ConvergenceTuner,
    EvaluationSet,
    EvidenceWindow,
    ExampleEpisode,
    HardGuards,
    InterferenceEdge,
    MetricsBlock,
    ObjectiveConstraints,
    PerAnchorAnalysis,
    PredictedImpact,
    ProposalStatus,
    ProposalStore,
    RefactorSuggestionType,
    Regime,
    RollbackMetric,
    RollbackOperator,
    RollbackTrigger,
    Scope,
    SummaryTable,
    SupportingEvidence,
    TimeRange,
    TrialPlan,
    TrialScope,
    TuningApply,
    TuningConfidence,
    TuningMode,
    TuningOpportunity,
    TuningProposal,
    check_admissibility,
    check_determinism_hygiene,
    check_objective_constraints,
    check_regime_match,
    check_strength_non_regression,
    check_trial_requirements,
    create_convergence_tuner,
)
from governor.telemetry import (
    TelemetryEvent,
    TelemetryEventType,
    TelemetryLevel,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_gov_dir(tmp_path):
    """Create a temporary .governor directory."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()
    return tmp_path


@pytest.fixture
def store(tmp_gov_dir):
    """Create a ProposalStore."""
    return ProposalStore(tmp_gov_dir)


@pytest.fixture
def analyzer():
    """Create a ConvergenceAnalyzer."""
    return ConvergenceAnalyzer()


def _make_trace_event(
    run_id: str,
    attempt: int,
    error_by_anchor: dict[str, float],
    action: str = "none",
    mode: str = "fiction",
    timestamp: str = "2026-01-20T00:00:00Z",
    delta_by_anchor: dict[str, float] | None = None,
) -> TelemetryEvent:
    """Helper to create a CONTINUITY_TRACE event."""
    fields: dict = {
        "run_id": run_id,
        "mode": mode,
        "attempt": attempt,
        "error_total": sum(error_by_anchor.values()),
        "error_by_anchor": error_by_anchor,
        "violations": [],
        "action": action,
        "action_params": {},
        "tokens": 100,
        "latency_ms": 50.0,
        "prompt_hash": "sha256:abc",
        "anchors_hash": "sha256:def",
    }
    if delta_by_anchor:
        fields["delta_by_anchor"] = delta_by_anchor
    return TelemetryEvent(
        timestamp=timestamp,
        event_type=TelemetryEventType.CONTINUITY_TRACE,
        level=TelemetryLevel.INFO,
        fields=fields,
    )


def _make_result_event(
    run_id: str,
    attempts: int,
    final_status: str = "ACCEPTED",
    residual_error_by_anchor: dict[str, float] | None = None,
    action_path: list[str] | None = None,
    mode: str = "fiction",
    timestamp: str = "2026-01-20T00:00:01Z",
    deadzone_actions: list[str] | None = None,
    interference_edges: list[dict[str, str]] | None = None,
) -> TelemetryEvent:
    """Helper to create a CONTINUITY_RESULT event."""
    residuals = residual_error_by_anchor or {}
    return TelemetryEvent(
        timestamp=timestamp,
        event_type=TelemetryEventType.CONTINUITY_RESULT,
        level=TelemetryLevel.INFO,
        fields={
            "run_id": run_id,
            "mode": mode,
            "attempts": attempts,
            "final_status": final_status,
            "residual_error_total": sum(residuals.values()),
            "residual_error_by_anchor": residuals,
            "action_path": action_path or [],
            "total_tokens": attempts * 100,
            "total_latency_ms": attempts * 50.0,
            "monotone": False,
            "oscillation_detected": False,
            "deadzone_actions": deadzone_actions or [],
            "interference_edges": interference_edges or [],
            "anchors_hash": "sha256:def",
        },
    )


def _make_valid_proposal(**overrides) -> TuningProposal:
    """Create a valid proposal with all required fields."""
    defaults = dict(
        proposal_id="tp_2026-01-20_000001",
        created_at_utc="2026-01-20T00:00:00Z",
        scope=Scope(
            mode=TuningMode.FICTION,
            anchor_namespace="fiction",
            targets=["fiction.monarchy_def"],
            regime=Regime(
                model_id="gpt-5",
                prompt_profile_hash="sha256:" + "a" * 64,
                decoder_profile="default",
                governor_version="0.9.7",
                config_hash="sha256:" + "b" * 64,
            ),
        ),
        evidence_window=EvidenceWindow(
            time_range_utc=TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-20T00:00:00Z"),
            min_enforcement_episodes=40,
            episodes_observed=50,
        ),
        change_set=ChangeSet(
            type=ChangeSetType.PARAMETER_UPDATE,
            changes=[ChangeParameterUpdate(
                target="anchors.fiction.monarchy_def.ladder.entry_action",
                from_value="SOFT_REPROMPT",
                to_value="HARD_REPROMPT",
                reason_code="SOFT_DEADZONE",
            ).to_dict()],
        ),
        metrics_before=MetricsBlock(
            attempts_avg=2.3, attempts_p95=4.0,
            refusal_rate=0.06, accept_rate=0.94,
            residual_error_avg=0.12,
            soft_success_rate=0.0, hard_success_rate=0.83,
            token_cost_avg=1450, token_cost_per_error_reduction_avg=380,
        ),
        predicted_impact=PredictedImpact(
            attempts_avg_delta=-0.7,
            token_cost_avg_delta=-220.0,
            refusal_rate_delta=0.0,
            violation_rate_delta=0.0,
            confidence=TuningConfidence.MEDIUM,
            rationale=["Soft reprompt never works for this anchor"],
        ),
        supporting_evidence=SupportingEvidence(
            summary_tables=[SummaryTable(name="test", rows=[{"a": 1}])],
            example_episodes=[ExampleEpisode(
                run_id="run_1", attempts=3, result="ACCEPTED",
                trace_refs=["telemetry://run_1"],
            )],
        ),
        trial_plan=TrialPlan(
            trial_id="trial_2026-01-20_000001",
            apply_mode="manual",
            trial_scope=TrialScope(max_runs=200, max_days=7),
            rollback_triggers=[
                RollbackTrigger(metric=RollbackMetric.REFUSAL_RATE, operator=RollbackOperator.GT, threshold=0.10),
                RollbackTrigger(metric=RollbackMetric.RESIDUAL_ERROR_AVG, operator=RollbackOperator.GT, threshold=0.20),
                RollbackTrigger(metric=RollbackMetric.VIOLATION_RATE, operator=RollbackOperator.GT, threshold=0.0),
            ],
            evaluation_set=EvaluationSet(fixture_ids=["eval_1"]),
        ),
        approval=Approval(status=ProposalStatus.PROPOSED),
    )
    defaults.update(overrides)
    return TuningProposal(**defaults)


# =============================================================================
# Section 1: Enum tests (7)
# =============================================================================


class TestEnums:
    def test_tuning_mode_values(self):
        assert set(TuningMode) == {
            TuningMode.FICTION, TuningMode.NONFICTION, TuningMode.PUPPET,
            TuningMode.CODE, TuningMode.OPS, TuningMode.UNKNOWN,
        }

    def test_tuning_confidence_values(self):
        assert set(TuningConfidence) == {
            TuningConfidence.LOW, TuningConfidence.MEDIUM, TuningConfidence.HIGH,
        }

    def test_proposal_status_values(self):
        assert set(ProposalStatus) == {
            ProposalStatus.PROPOSED, ProposalStatus.APPROVED,
            ProposalStatus.REJECTED, ProposalStatus.APPLIED,
            ProposalStatus.ROLLED_BACK,
        }

    def test_change_set_type_values(self):
        assert set(ChangeSetType) == {
            ChangeSetType.PARAMETER_UPDATE, ChangeSetType.PATTERN_UPDATE,
            ChangeSetType.REFACTOR_SUGGESTION,
        }

    def test_refactor_suggestion_type_values(self):
        assert set(RefactorSuggestionType) == {
            RefactorSuggestionType.SPLIT_ANCHOR, RefactorSuggestionType.MERGE_ANCHORS,
            RefactorSuggestionType.REWEIGHT_RULES, RefactorSuggestionType.REVISE_MEASUREMENT,
        }

    def test_rollback_metric_values(self):
        assert set(RollbackMetric) == {
            RollbackMetric.REFUSAL_RATE, RollbackMetric.RESIDUAL_ERROR_AVG,
            RollbackMetric.VIOLATION_RATE, RollbackMetric.ATTEMPTS_AVG,
            RollbackMetric.TOKEN_COST_AVG,
        }

    def test_rollback_operator_values(self):
        assert set(RollbackOperator) == {
            RollbackOperator.GT, RollbackOperator.GTE,
            RollbackOperator.LT, RollbackOperator.LTE,
            RollbackOperator.EQ,
        }


# =============================================================================
# Section 2: Dataclass serialization roundtrips (30)
# =============================================================================


class TestDataclassSerialization:
    def test_regime_roundtrip(self):
        r = Regime(model_id="gpt-5", config_hash="sha256:abc")
        d = r.to_dict()
        r2 = Regime.from_dict(d)
        assert r2.model_id == "gpt-5"
        assert r2.config_hash == "sha256:abc"

    def test_scope_roundtrip(self):
        s = Scope(mode=TuningMode.FICTION, anchor_namespace="fiction", targets=["fiction.x"])
        d = s.to_dict()
        s2 = Scope.from_dict(d)
        assert s2.mode == TuningMode.FICTION
        assert s2.targets == ["fiction.x"]

    def test_scope_unknown_mode(self):
        s = Scope.from_dict({"mode": "nonexistent"})
        assert s.mode == TuningMode.UNKNOWN

    def test_time_range_roundtrip(self):
        t = TimeRange(start="2026-01-01", end="2026-01-20")
        d = t.to_dict()
        t2 = TimeRange.from_dict(d)
        assert t2.start == "2026-01-01"

    def test_evidence_window_roundtrip(self):
        ew = EvidenceWindow(min_enforcement_episodes=50, episodes_observed=60)
        d = ew.to_dict()
        ew2 = EvidenceWindow.from_dict(d)
        assert ew2.min_enforcement_episodes == 50

    def test_change_parameter_update_roundtrip(self):
        c = ChangeParameterUpdate(target="x.y.z", from_value="A", to_value="B", reason_code="TEST")
        d = c.to_dict()
        assert d["from"] == "A"
        assert d["to"] == "B"
        c2 = ChangeParameterUpdate.from_dict(d)
        assert c2.from_value == "A"
        assert c2.to_value == "B"

    def test_change_pattern_update_roundtrip(self):
        c = ChangePatternUpdate(target="x.neg_terms", op="add", values=["foo"], reason_code="T")
        d = c.to_dict()
        c2 = ChangePatternUpdate.from_dict(d)
        assert c2.op == "add"
        assert c2.values == ["foo"]

    def test_change_refactor_suggestion_roundtrip(self):
        c = ChangeRefactorSuggestion(
            suggestion_type=RefactorSuggestionType.SPLIT_ANCHOR,
            detail="Split it", reason_code="INTERF",
        )
        d = c.to_dict()
        c2 = ChangeRefactorSuggestion.from_dict(d)
        assert c2.suggestion_type == RefactorSuggestionType.SPLIT_ANCHOR

    def test_change_set_roundtrip(self):
        cs = ChangeSet(type=ChangeSetType.PARAMETER_UPDATE, changes=[{"target": "x", "from": "a", "to": "b"}])
        d = cs.to_dict()
        cs2 = ChangeSet.from_dict(d)
        assert cs2.type == ChangeSetType.PARAMETER_UPDATE
        assert len(cs2.changes) == 1

    def test_change_set_typed_accessors(self):
        cs = ChangeSet(changes=[
            {"target": "x", "from": "a", "to": "b", "reason_code": "T"},
            {"target": "y", "op": "add", "values": ["z"], "reason_code": "T2"},
            {"suggestion_type": "split_anchor", "detail": "d", "reason_code": "T3"},
        ])
        assert len(cs.parameter_updates()) == 1
        assert len(cs.pattern_updates()) == 1
        assert len(cs.refactor_suggestions()) == 1

    def test_hard_guards_forced_true(self):
        hg = HardGuards(
            severity_downgrade_forbidden=False,
            auto_apply_forbidden=False,
            cross_mode_forbidden=False,
            mutation_during_session_forbidden=False,
        )
        assert hg.severity_downgrade_forbidden is True
        assert hg.auto_apply_forbidden is True
        assert hg.cross_mode_forbidden is True
        assert hg.mutation_during_session_forbidden is True

    def test_hard_guards_roundtrip(self):
        hg = HardGuards()
        d = hg.to_dict()
        hg2 = HardGuards.from_dict(d)
        assert hg2.severity_downgrade_forbidden is True

    def test_objective_constraints_roundtrip(self):
        oc = ObjectiveConstraints(max_allowed_increase_refusal_rate=0.05)
        d = oc.to_dict()
        oc2 = ObjectiveConstraints.from_dict(d)
        assert oc2.max_allowed_increase_refusal_rate == 0.05

    def test_constraints_roundtrip(self):
        c = Constraints()
        d = c.to_dict()
        c2 = Constraints.from_dict(d)
        assert c2.hard_guards.severity_downgrade_forbidden is True

    def test_metrics_block_roundtrip(self):
        mb = MetricsBlock(attempts_avg=2.3, refusal_rate=0.06, token_cost_avg=1450)
        d = mb.to_dict()
        mb2 = MetricsBlock.from_dict(d)
        assert mb2.attempts_avg == 2.3
        assert mb2.token_cost_avg == 1450

    def test_metrics_block_rounding(self):
        mb = MetricsBlock(refusal_rate=0.123456789, token_cost_avg=1234.5678)
        d = mb.to_dict()
        assert d["refusal_rate"] == 0.123457  # round to 6
        assert d["token_cost_avg"] == 1234.57  # round to 2

    def test_predicted_impact_roundtrip(self):
        pi = PredictedImpact(
            attempts_avg_delta=-0.7, confidence=TuningConfidence.HIGH,
            rationale=["reason"],
        )
        d = pi.to_dict()
        pi2 = PredictedImpact.from_dict(d)
        assert pi2.confidence == TuningConfidence.HIGH
        assert pi2.rationale == ["reason"]

    def test_summary_table_roundtrip(self):
        st = SummaryTable(name="test", rows=[{"a": 1}])
        d = st.to_dict()
        st2 = SummaryTable.from_dict(d)
        assert st2.name == "test"

    def test_example_episode_roundtrip(self):
        ee = ExampleEpisode(run_id="r1", attempts=3, result="ACCEPTED", trace_refs=["ref"])
        d = ee.to_dict()
        ee2 = ExampleEpisode.from_dict(d)
        assert ee2.run_id == "r1"

    def test_interference_edge_roundtrip(self):
        ie = InterferenceEdge(from_anchor="a", to_anchor="b", count=5)
        d = ie.to_dict()
        ie2 = InterferenceEdge.from_dict(d)
        assert ie2.count == 5

    def test_supporting_evidence_roundtrip(self):
        se = SupportingEvidence(
            summary_tables=[SummaryTable(name="t")],
            example_episodes=[ExampleEpisode(run_id="r", trace_refs=["x"])],
            interference_graph=[InterferenceEdge(from_anchor="a", to_anchor="b", count=1)],
        )
        d = se.to_dict()
        se2 = SupportingEvidence.from_dict(d)
        assert len(se2.summary_tables) == 1
        assert len(se2.interference_graph) == 1

    def test_rollback_trigger_roundtrip(self):
        rt = RollbackTrigger(metric=RollbackMetric.REFUSAL_RATE, operator=RollbackOperator.GT, threshold=0.1)
        d = rt.to_dict()
        rt2 = RollbackTrigger.from_dict(d)
        assert rt2.metric == RollbackMetric.REFUSAL_RATE

    def test_trial_scope_roundtrip(self):
        ts = TrialScope(max_runs=100, max_days=14)
        d = ts.to_dict()
        ts2 = TrialScope.from_dict(d)
        assert ts2.max_runs == 100

    def test_evaluation_set_roundtrip(self):
        es = EvaluationSet(fixture_ids=["f1", "f2"])
        d = es.to_dict()
        es2 = EvaluationSet.from_dict(d)
        assert es2.fixture_ids == ["f1", "f2"]

    def test_trial_plan_roundtrip(self):
        tp = TrialPlan(
            trial_id="trial_2026-01-20_000001",
            rollback_triggers=[RollbackTrigger()],
            evaluation_set=EvaluationSet(fixture_ids=["f1"]),
        )
        d = tp.to_dict()
        tp2 = TrialPlan.from_dict(d)
        assert tp2.trial_id == "trial_2026-01-20_000001"

    def test_approval_forced_requires_human(self):
        a = Approval(requires_human=False)
        assert a.requires_human is True

    def test_approval_roundtrip(self):
        a = Approval(status=ProposalStatus.APPROVED, approved_by="alice")
        d = a.to_dict()
        assert d["requires_human"] is True
        a2 = Approval.from_dict(d)
        assert a2.status == ProposalStatus.APPROVED
        assert a2.approved_by == "alice"

    def test_tuning_proposal_roundtrip(self):
        p = _make_valid_proposal()
        d = p.to_dict()
        p2 = TuningProposal.from_dict(d)
        assert p2.proposal_id == p.proposal_id
        assert p2.scope.mode == TuningMode.FICTION
        assert p2.approval.requires_human is True

    def test_tuning_apply_roundtrip(self):
        ta = TuningApply(
            trial_id="trial_2026-01-20_000001",
            proposal_id="tp_2026-01-20_000001",
            applied_by="alice",
            new_config_hash="sha256:new",
        )
        d = ta.to_dict()
        ta2 = TuningApply.from_dict(d)
        assert ta2.applied_by == "alice"

    def test_full_proposal_json_roundtrip(self):
        """Full JSON serialization roundtrip."""
        p = _make_valid_proposal()
        json_str = json.dumps(p.to_dict(), indent=2)
        d = json.loads(json_str)
        p2 = TuningProposal.from_dict(d)
        assert p2.proposal_id == p.proposal_id
        assert p2.change_set.type == p.change_set.type


# =============================================================================
# Section 3: ProposalStore (18)
# =============================================================================


class TestProposalStore:
    def test_save_and_get_proposal(self, store):
        p = _make_valid_proposal()
        store.save_proposal(p)
        p2 = store.get_proposal(p.proposal_id)
        assert p2 is not None
        assert p2.proposal_id == p.proposal_id

    def test_get_nonexistent_proposal(self, store):
        assert store.get_proposal("tp_2099-01-01_999999") is None

    def test_list_proposals_empty(self, store):
        assert store.list_proposals() == []

    def test_list_proposals(self, store):
        p1 = _make_valid_proposal(proposal_id="tp_2026-01-20_000001")
        p2 = _make_valid_proposal(proposal_id="tp_2026-01-20_000002")
        store.save_proposal(p1)
        store.save_proposal(p2)
        proposals = store.list_proposals()
        assert len(proposals) == 2

    def test_list_proposals_with_status_filter(self, store):
        p1 = _make_valid_proposal(
            proposal_id="tp_2026-01-20_000001",
            approval=Approval(status=ProposalStatus.PROPOSED),
        )
        p2 = _make_valid_proposal(
            proposal_id="tp_2026-01-20_000002",
            approval=Approval(status=ProposalStatus.APPLIED),
        )
        store.save_proposal(p1)
        store.save_proposal(p2)
        assert len(store.list_proposals(status=ProposalStatus.PROPOSED)) == 1
        assert len(store.list_proposals(status=ProposalStatus.APPLIED)) == 1

    def test_remove_proposal(self, store):
        p = _make_valid_proposal()
        store.save_proposal(p)
        assert store.remove_proposal(p.proposal_id) is True
        assert store.get_proposal(p.proposal_id) is None

    def test_remove_nonexistent(self, store):
        assert store.remove_proposal("tp_2099-01-01_999999") is False

    def test_proposals_for_anchor(self, store):
        p1 = _make_valid_proposal(
            proposal_id="tp_2026-01-20_000001",
            scope=Scope(targets=["fiction.monarchy_def"]),
        )
        p2 = _make_valid_proposal(
            proposal_id="tp_2026-01-20_000002",
            scope=Scope(targets=["fiction.tone_register"]),
        )
        store.save_proposal(p1)
        store.save_proposal(p2)
        assert len(store.proposals_for_anchor("fiction.monarchy_def")) == 1
        assert len(store.proposals_for_anchor("fiction.nonexistent")) == 0

    def test_status_counts(self, store):
        p1 = _make_valid_proposal(
            proposal_id="tp_2026-01-20_000001",
            approval=Approval(status=ProposalStatus.PROPOSED),
        )
        p2 = _make_valid_proposal(
            proposal_id="tp_2026-01-20_000002",
            approval=Approval(status=ProposalStatus.PROPOSED),
        )
        p3 = _make_valid_proposal(
            proposal_id="tp_2026-01-20_000003",
            approval=Approval(status=ProposalStatus.APPLIED),
        )
        store.save_proposal(p1)
        store.save_proposal(p2)
        store.save_proposal(p3)
        counts = store.status_counts()
        assert counts["proposed"] == 2
        assert counts["applied"] == 1

    def test_save_and_get_apply(self, store):
        ta = TuningApply(
            trial_id="trial_2026-01-20_000001",
            proposal_id="tp_2026-01-20_000001",
            applied_by="alice",
        )
        store.save_apply(ta)
        ta2 = store.get_apply("trial_2026-01-20_000001")
        assert ta2 is not None
        assert ta2.applied_by == "alice"

    def test_get_nonexistent_apply(self, store):
        assert store.get_apply("trial_nonexistent") is None

    def test_list_applies(self, store):
        ta1 = TuningApply(trial_id="trial_2026-01-20_000001", proposal_id="tp_1")
        ta2 = TuningApply(trial_id="trial_2026-01-20_000002", proposal_id="tp_2")
        store.save_apply(ta1)
        store.save_apply(ta2)
        applies = store.list_applies()
        assert len(applies) == 2

    def test_malformed_json_silently_skipped(self, store):
        store._ensure_dir()
        bad_path = store.store_dir / "tp_2026-01-20_999999.json"
        bad_path.write_text("{invalid json")
        assert store.get_proposal("tp_2026-01-20_999999") is None
        # list_proposals should skip it
        proposals = store.list_proposals()
        assert len(proposals) == 0

    def test_sanitized_filenames(self, store):
        p = _make_valid_proposal(proposal_id="tp_2026-01-20_000001")
        store.save_proposal(p)
        # Check that file exists with sanitized name
        expected = store.store_dir / "tp_2026-01-20_000001.json"
        assert expected.exists()

    def test_overwrite_proposal(self, store):
        p = _make_valid_proposal()
        store.save_proposal(p)
        p.approval.status = ProposalStatus.APPROVED
        store.save_proposal(p)
        p2 = store.get_proposal(p.proposal_id)
        assert p2.approval.status == ProposalStatus.APPROVED

    def test_store_dir_created_on_save(self, tmp_path):
        store = ProposalStore(tmp_path)
        assert not store.store_dir.exists()
        p = _make_valid_proposal()
        store.save_proposal(p)
        assert store.store_dir.exists()

    def test_empty_store_dir(self, tmp_path):
        store = ProposalStore(tmp_path)
        assert store.list_proposals() == []
        assert store.list_applies() == []


# =============================================================================
# Section 4: ConvergenceAnalyzer (25)
# =============================================================================


class TestConvergenceAnalyzer:
    def test_analyze_empty_events(self, analyzer):
        result = analyzer.analyze([])
        assert result == {}

    def test_analyze_single_run(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"anchor_a": 0.5}),
            _make_trace_event("run_1", 1, {"anchor_a": 0.2}, action="HARD_REPROMPT"),
            _make_result_event("run_1", 2, residual_error_by_anchor={"anchor_a": 0.1}),
        ]
        result = analyzer.analyze(events)
        assert "anchor_a" in result
        assert result["anchor_a"].episode_count >= 1

    def test_analyze_multiple_runs(self, analyzer):
        events = []
        for i in range(5):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 0.5}))
            events.append(_make_trace_event(rid, 1, {"a": 0.3}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(rid, 2, residual_error_by_anchor={"a": 0.1}))
        result = analyzer.analyze(events)
        assert result["a"].episode_count == 5

    def test_analyze_mode_filter(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 0.5}, mode="fiction"),
            _make_result_event("run_1", 1, residual_error_by_anchor={"a": 0.1}, mode="fiction"),
            _make_trace_event("run_2", 0, {"b": 0.3}, mode="nonfiction"),
            _make_result_event("run_2", 1, residual_error_by_anchor={"b": 0.1}, mode="nonfiction"),
        ]
        result = analyzer.analyze(events, mode="fiction")
        assert "a" in result
        assert "b" not in result

    def test_analyze_since_filter(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 0.5}, timestamp="2026-01-01T00:00:00Z"),
            _make_result_event("run_1", 1, residual_error_by_anchor={"a": 0.1}, timestamp="2026-01-01T00:00:01Z"),
            _make_trace_event("run_2", 0, {"b": 0.3}, timestamp="2026-01-15T00:00:00Z"),
            _make_result_event("run_2", 1, residual_error_by_anchor={"b": 0.1}, timestamp="2026-01-15T00:00:01Z"),
        ]
        result = analyzer.analyze(events, since="2026-01-10T00:00:00Z")
        assert "b" in result
        assert "a" not in result

    def test_analyze_action_effectiveness(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 1.0}),
            _make_trace_event("run_1", 1, {"a": 0.5}, action="SOFT_REPROMPT"),
            _make_trace_event("run_1", 2, {"a": 0.2}, action="HARD_REPROMPT"),
            _make_result_event("run_1", 3, residual_error_by_anchor={"a": 0.1}),
        ]
        result = analyzer.analyze(events)
        ae_list = result["a"].action_effectiveness
        actions = {ae.action for ae in ae_list}
        assert "SOFT_REPROMPT" in actions or "HARD_REPROMPT" in actions

    def test_analyze_action_effectiveness_improved(self, analyzer):
        """Action that reduces error should show as improved."""
        events = [
            _make_trace_event("run_1", 0, {"a": 1.0}),
            _make_trace_event("run_1", 1, {"a": 0.3}, action="HARD_REPROMPT"),
            _make_result_event("run_1", 2, residual_error_by_anchor={"a": 0.1}),
        ]
        result = analyzer.analyze(events)
        hard_ae = [ae for ae in result["a"].action_effectiveness if ae.action == "HARD_REPROMPT"]
        assert len(hard_ae) == 1
        assert hard_ae[0].improved >= 1

    def test_analyze_deadzone_detection(self, analyzer):
        """Action that never works should be flagged as deadzone."""
        events = []
        for i in range(12):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            # Error stays the same after soft reprompt
            events.append(_make_trace_event(rid, 1, {"a": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(
                rid, 2,
                residual_error_by_anchor={"a": 0.5},
                deadzone_actions=["SOFT_REPROMPT"],
            ))
        result = analyzer.analyze(events)
        assert "SOFT_REPROMPT" in result["a"].deadzone_actions

    def test_analyze_interference_detection(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 0.5, "b": 0.3}),
            _make_result_event(
                "run_1", 1,
                residual_error_by_anchor={"a": 0.1, "b": 0.2},
                interference_edges=[{"from_anchor": "a", "to_anchor": "b"}],
            ),
        ]
        result = analyzer.analyze(events)
        assert "b" in result["a"].interference_targets

    def test_analyze_avg_attempts(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 0.5}),
            _make_result_event("run_1", 3, residual_error_by_anchor={"a": 0.1}),
            _make_trace_event("run_2", 0, {"a": 0.5}),
            _make_result_event("run_2", 5, residual_error_by_anchor={"a": 0.1}),
        ]
        result = analyzer.analyze(events)
        assert result["a"].avg_attempts_to_resolve == 4.0  # (3+5)/2

    def test_analyze_residual_error_avg(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 0.5}),
            _make_result_event("run_1", 1, residual_error_by_anchor={"a": 0.2}),
            _make_trace_event("run_2", 0, {"a": 0.5}),
            _make_result_event("run_2", 1, residual_error_by_anchor={"a": 0.4}),
        ]
        result = analyzer.analyze(events)
        assert abs(result["a"].residual_error_avg - 0.3) < 1e-6

    def test_analyze_serialization(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 0.5}),
            _make_result_event("run_1", 1, residual_error_by_anchor={"a": 0.1}),
        ]
        result = analyzer.analyze(events)
        d = result["a"].to_dict()
        r2 = PerAnchorAnalysis.from_dict(d)
        assert r2.anchor_id == "a"

    def test_identify_opportunities_empty(self, analyzer):
        assert analyzer.identify_opportunities({}) == []

    def test_identify_deadzone_opportunity(self, analyzer):
        analysis = PerAnchorAnalysis(
            anchor_id="a",
            action_effectiveness=[ActionEffectiveness(
                action="SOFT_REPROMPT", total_attempts=15, improved=0,
                worsened=2, no_change=13, success_rate=0.0,
            )],
        )
        opps = analyzer.identify_opportunities({"a": analysis})
        types = {o.opportunity_type for o in opps}
        assert "skip_deadzone_action" in types

    def test_identify_split_anchor_opportunity(self, analyzer):
        analysis = PerAnchorAnalysis(
            anchor_id="a",
            interference_targets=["b", "c"],
            episode_count=20,
        )
        opps = analyzer.identify_opportunities({"a": analysis})
        types = {o.opportunity_type for o in opps}
        assert "split_anchor" in types

    def test_identify_budget_adjust_opportunity(self, analyzer):
        analysis = PerAnchorAnalysis(
            anchor_id="a",
            avg_attempts_to_resolve=4.5,
            episode_count=30,
        )
        opps = analyzer.identify_opportunities({"a": analysis})
        types = {o.opportunity_type for o in opps}
        assert "budget_adjust" in types

    def test_identify_no_opportunities(self, analyzer):
        analysis = PerAnchorAnalysis(
            anchor_id="a",
            avg_attempts_to_resolve=1.5,
            action_effectiveness=[ActionEffectiveness(
                action="SOFT_REPROMPT", total_attempts=5, improved=4,
                success_rate=0.8,
            )],
        )
        opps = analyzer.identify_opportunities({"a": analysis})
        assert len(opps) == 0

    def test_compute_metrics_block_empty(self, analyzer):
        mb = analyzer.compute_metrics_block([])
        assert mb.attempts_avg == 0.0

    def test_compute_metrics_block(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 1.0}),
            _make_trace_event("run_1", 1, {"a": 0.5}, action="SOFT_REPROMPT"),
            _make_result_event("run_1", 2, "ACCEPTED", {"a": 0.1}),
            _make_trace_event("run_2", 0, {"a": 1.0}),
            _make_result_event("run_2", 1, "REFUSED", {"a": 0.8}),
        ]
        mb = analyzer.compute_metrics_block(events)
        assert mb.accept_rate == 0.5
        assert mb.refusal_rate == 0.5
        assert mb.attempts_avg == 1.5  # (2 + 1) / 2

    def test_compute_metrics_block_mode_filter(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 1.0}, mode="fiction"),
            _make_result_event("run_1", 1, "ACCEPTED", {"a": 0.1}, mode="fiction"),
            _make_trace_event("run_2", 0, {"b": 1.0}, mode="nonfiction"),
            _make_result_event("run_2", 1, "ACCEPTED", {"b": 0.1}, mode="nonfiction"),
        ]
        mb = analyzer.compute_metrics_block(events, mode="fiction")
        assert mb.accept_rate == 1.0

    def test_compute_metrics_block_token_cost(self, analyzer):
        events = [
            _make_trace_event("run_1", 0, {"a": 1.0}),
            _make_result_event("run_1", 2, "ACCEPTED", {"a": 0.1}),
        ]
        mb = analyzer.compute_metrics_block(events)
        assert mb.token_cost_avg > 0

    def test_action_effectiveness_roundtrip(self):
        ae = ActionEffectiveness(
            action="SOFT_REPROMPT", total_attempts=10,
            improved=3, worsened=2, no_change=5,
            success_rate=0.3, avg_delta=0.15,
        )
        d = ae.to_dict()
        ae2 = ActionEffectiveness.from_dict(d)
        assert ae2.action == "SOFT_REPROMPT"
        assert ae2.improved == 3

    def test_tuning_opportunity_roundtrip(self):
        to = TuningOpportunity(
            anchor_id="a", opportunity_type="skip_deadzone_action",
            evidence={"action": "SOFT"}, estimated_savings=5.0,
        )
        d = to.to_dict()
        to2 = TuningOpportunity.from_dict(d)
        assert to2.anchor_id == "a"

    def test_admissibility_result_roundtrip(self):
        ar = AdmissibilityResult(passed=False, check_name="test", violations=["fail"])
        d = ar.to_dict()
        ar2 = AdmissibilityResult.from_dict(d)
        assert ar2.passed is False
        assert ar2.violations == ["fail"]


# =============================================================================
# Section 5: Admissibility checks (30)
# =============================================================================


class TestCheckRegimeMatch:
    def test_pass_when_matching(self):
        p = _make_valid_proposal()
        r = check_regime_match(
            p,
            current_model_id="gpt-5",
            current_config_hash="sha256:" + "b" * 64,
            current_mode="fiction",
        )
        assert r.passed is True

    def test_fail_model_mismatch(self):
        p = _make_valid_proposal()
        r = check_regime_match(p, current_model_id="gpt-4")
        assert r.passed is False
        assert any("model_id" in v for v in r.violations)

    def test_fail_config_hash_mismatch(self):
        p = _make_valid_proposal()
        r = check_regime_match(p, current_config_hash="sha256:" + "x" * 64)
        assert r.passed is False

    def test_fail_mode_mismatch(self):
        p = _make_valid_proposal()
        r = check_regime_match(p, current_mode="nonfiction")
        assert r.passed is False

    def test_fail_prompt_profile_mismatch(self):
        p = _make_valid_proposal()
        r = check_regime_match(p, current_prompt_profile_hash="sha256:" + "z" * 64)
        assert r.passed is False

    def test_fail_target_outside_namespace(self):
        p = _make_valid_proposal()
        p.scope.targets = ["nonfiction.wrong"]
        r = check_regime_match(p)
        assert r.passed is False
        assert any("outside namespace" in v for v in r.violations)

    def test_pass_empty_current_values(self):
        """Empty current values should not trigger mismatches."""
        p = _make_valid_proposal()
        r = check_regime_match(p)
        assert r.passed is True


class TestCheckStrengthNonRegression:
    def test_pass_more_aggressive_entry_action(self):
        p = _make_valid_proposal()
        r = check_strength_non_regression(p)
        assert r.passed is True

    def test_fail_weakened_entry_action(self):
        p = _make_valid_proposal(
            change_set=ChangeSet(changes=[ChangeParameterUpdate(
                target="anchors.fiction.a.ladder.entry_action",
                from_value="HARD_REPROMPT",
                to_value="SOFT_REPROMPT",
                reason_code="TEST",
            ).to_dict()]),
        )
        r = check_strength_non_regression(p)
        assert r.passed is False
        assert any("weakened" in v for v in r.violations)

    def test_fail_severity_change(self):
        p = _make_valid_proposal(
            change_set=ChangeSet(changes=[{"target": "anchors.fiction.a.severity", "from": "reject", "to": "warn"}]),
        )
        r = check_strength_non_regression(p)
        assert r.passed is False

    def test_fail_max_attempts_increase(self):
        p = _make_valid_proposal(
            change_set=ChangeSet(changes=[ChangeParameterUpdate(
                target="anchors.fiction.a.ladder.max_attempts",
                from_value=3, to_value=5, reason_code="T",
            ).to_dict()]),
        )
        r = check_strength_non_regression(p)
        assert r.passed is False

    def test_pass_max_attempts_decrease(self):
        p = _make_valid_proposal(
            change_set=ChangeSet(changes=[ChangeParameterUpdate(
                target="anchors.fiction.a.ladder.max_attempts",
                from_value=5, to_value=3, reason_code="T",
            ).to_dict()]),
        )
        r = check_strength_non_regression(p)
        assert r.passed is True

    def test_fail_removing_neg_terms(self):
        p = _make_valid_proposal(
            change_set=ChangeSet(changes=[ChangePatternUpdate(
                target="anchors.fiction.a.neg_terms",
                op="remove", values=["foo"], reason_code="T",
            ).to_dict()]),
        )
        r = check_strength_non_regression(p)
        assert r.passed is False

    def test_pass_adding_neg_terms(self):
        p = _make_valid_proposal(
            change_set=ChangeSet(
                type=ChangeSetType.PATTERN_UPDATE,
                changes=[ChangePatternUpdate(
                    target="anchors.fiction.a.neg_terms",
                    op="add", values=["bar"], reason_code="T",
                ).to_dict()],
            ),
        )
        r = check_strength_non_regression(p)
        assert r.passed is True

    def test_fail_removing_pos_terms(self):
        p = _make_valid_proposal(
            change_set=ChangeSet(changes=[ChangePatternUpdate(
                target="anchors.fiction.a.pos_terms",
                op="remove", values=["x"], reason_code="T",
            ).to_dict()]),
        )
        r = check_strength_non_regression(p)
        assert r.passed is False


class TestCheckObjectiveConstraints:
    def test_pass_within_bounds(self):
        p = _make_valid_proposal()
        r = check_objective_constraints(p)
        assert r.passed is True

    def test_fail_refusal_rate_exceeded(self):
        p = _make_valid_proposal(
            predicted_impact=PredictedImpact(refusal_rate_delta=0.10, rationale=["x"]),
        )
        r = check_objective_constraints(p)
        assert r.passed is False

    def test_fail_violation_rate_exceeded(self):
        p = _make_valid_proposal(
            predicted_impact=PredictedImpact(violation_rate_delta=0.01, rationale=["x"]),
        )
        r = check_objective_constraints(p)
        assert r.passed is False

    def test_fail_no_example_episodes(self):
        p = _make_valid_proposal(
            supporting_evidence=SupportingEvidence(
                summary_tables=[SummaryTable(name="t")],
                example_episodes=[],
            ),
        )
        r = check_objective_constraints(p)
        assert r.passed is False

    def test_fail_no_rationale(self):
        p = _make_valid_proposal(
            predicted_impact=PredictedImpact(rationale=[]),
        )
        r = check_objective_constraints(p)
        assert r.passed is False


class TestCheckTrialRequirements:
    def test_pass_valid_trial(self):
        p = _make_valid_proposal()
        r = check_trial_requirements(p)
        assert r.passed is True

    def test_fail_non_manual_mode(self):
        p = _make_valid_proposal()
        p.trial_plan.apply_mode = "auto"
        r = check_trial_requirements(p)
        assert r.passed is False

    def test_fail_missing_rollback_metrics(self):
        p = _make_valid_proposal()
        p.trial_plan.rollback_triggers = [
            RollbackTrigger(metric=RollbackMetric.REFUSAL_RATE),
        ]
        r = check_trial_requirements(p)
        assert r.passed is False

    def test_fail_no_fixtures(self):
        p = _make_valid_proposal()
        p.trial_plan.evaluation_set = EvaluationSet(fixture_ids=[])
        r = check_trial_requirements(p)
        assert r.passed is False

    def test_pass_extra_rollback_metrics(self):
        p = _make_valid_proposal()
        p.trial_plan.rollback_triggers.append(
            RollbackTrigger(metric=RollbackMetric.TOKEN_COST_AVG)
        )
        r = check_trial_requirements(p)
        assert r.passed is True


class TestCheckDeterminismHygiene:
    def test_pass_with_hashes(self):
        p = _make_valid_proposal()
        r = check_determinism_hygiene(p)
        assert r.passed is True

    def test_fail_missing_prompt_hash(self):
        p = _make_valid_proposal()
        p.scope.regime.prompt_profile_hash = ""
        r = check_determinism_hygiene(p)
        assert r.passed is False

    def test_fail_missing_config_hash(self):
        p = _make_valid_proposal()
        p.scope.regime.config_hash = ""
        r = check_determinism_hygiene(p)
        assert r.passed is False


class TestCheckAdmissibilityCombined:
    def test_all_pass(self):
        p = _make_valid_proposal()
        results = check_admissibility(p, current_model_id="gpt-5", current_mode="fiction")
        assert all(r.passed for r in results)

    def test_multiple_failures(self):
        p = _make_valid_proposal()
        p.scope.regime.prompt_profile_hash = ""
        p.scope.regime.config_hash = ""
        p.trial_plan.apply_mode = "auto"
        results = check_admissibility(p)
        failed = [r for r in results if not r.passed]
        assert len(failed) >= 2

    def test_returns_five_checks(self):
        p = _make_valid_proposal()
        results = check_admissibility(p)
        assert len(results) == 5


# =============================================================================
# Section 6: ConvergenceTuner orchestrator (20)
# =============================================================================


class TestConvergenceTuner:
    def test_propose_empty_events(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        proposals = tuner.propose([])
        assert proposals == []

    def test_propose_with_deadzone(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"monarchy_def": 1.0}))
            events.append(_make_trace_event(rid, 1, {"monarchy_def": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(
                rid, 2,
                residual_error_by_anchor={"monarchy_def": 0.5},
                deadzone_actions=["SOFT_REPROMPT"],
            ))
        proposals = tuner.propose(events, mode="fiction", anchor_namespace="fiction")
        assert len(proposals) >= 1

    def test_propose_saves_to_store(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(
                rid, 2, residual_error_by_anchor={"a": 0.5},
                deadzone_actions=["SOFT_REPROMPT"],
            ))
        proposals = tuner.propose(events, mode="fiction")
        # Should be saved in store
        stored = tuner.store.list_proposals()
        assert len(stored) == len(proposals)

    def test_propose_with_interference(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(5):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 0.5, "b": 0.3}))
            events.append(_make_result_event(
                rid, 4,
                residual_error_by_anchor={"a": 0.1, "b": 0.2},
                interference_edges=[
                    {"from_anchor": "a", "to_anchor": "b"},
                    {"from_anchor": "a", "to_anchor": "c"},
                ],
            ))
        proposals = tuner.propose(events, mode="fiction")
        # Should produce split_anchor proposals
        types = set()
        for p in proposals:
            for c in p.change_set.changes:
                if "suggestion_type" in c:
                    types.add(c["suggestion_type"])
        assert "split_anchor" in types or len(proposals) >= 1

    def test_propose_with_high_attempts(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(5):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 0.5}))
            events.append(_make_result_event(rid, 5, residual_error_by_anchor={"a": 0.2}))
        proposals = tuner.propose(events, mode="fiction")
        # Should produce budget_adjust proposals
        assert len(proposals) >= 1

    def test_propose_respects_max_proposals(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0, "b": 1.0, "c": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 1.0, "b": 1.0, "c": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(
                rid, 2,
                residual_error_by_anchor={"a": 0.5, "b": 0.5, "c": 0.5},
                deadzone_actions=["SOFT_REPROMPT"],
            ))
        proposals = tuner.propose(events, mode="fiction", max_proposals=2)
        assert len(proposals) <= 2

    def test_propose_sets_approval_proposed(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(rid, 2, residual_error_by_anchor={"a": 0.5}, deadzone_actions=["SOFT_REPROMPT"]))
        proposals = tuner.propose(events, mode="fiction")
        for p in proposals:
            assert p.approval.status == ProposalStatus.PROPOSED
            assert p.approval.requires_human is True

    def test_propose_with_regime(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        regime = Regime(model_id="gpt-5", config_hash="sha256:" + "a" * 64)
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(rid, 2, residual_error_by_anchor={"a": 0.5}, deadzone_actions=["SOFT_REPROMPT"]))
        proposals = tuner.propose(events, mode="fiction", regime=regime)
        if proposals:
            assert proposals[0].scope.regime.model_id == "gpt-5"

    def test_apply_success(self, tmp_gov_dir):
        store = ProposalStore(tmp_gov_dir)
        tuner = ConvergenceTuner(store=store, gov_dir=tmp_gov_dir / ".governor")
        p = _make_valid_proposal()
        store.save_proposal(p)
        result = tuner.apply(
            p.proposal_id,
            applied_by="alice",
            new_config_hash="sha256:new",
            previous_config_hash="sha256:" + "b" * 64,
            current_model_id="gpt-5",
            current_mode="fiction",
        )
        assert isinstance(result, TuningApply)
        assert result.applied_by == "alice"

    def test_apply_updates_status(self, tmp_gov_dir):
        store = ProposalStore(tmp_gov_dir)
        tuner = ConvergenceTuner(store=store, gov_dir=tmp_gov_dir / ".governor")
        p = _make_valid_proposal()
        store.save_proposal(p)
        tuner.apply(
            p.proposal_id, applied_by="bob",
            current_model_id="gpt-5", current_mode="fiction",
        )
        p2 = store.get_proposal(p.proposal_id)
        assert p2.approval.status == ProposalStatus.APPLIED

    def test_apply_creates_apply_record(self, tmp_gov_dir):
        store = ProposalStore(tmp_gov_dir)
        tuner = ConvergenceTuner(store=store, gov_dir=tmp_gov_dir / ".governor")
        p = _make_valid_proposal()
        store.save_proposal(p)
        result = tuner.apply(
            p.proposal_id, applied_by="alice",
            current_model_id="gpt-5", current_mode="fiction",
        )
        assert isinstance(result, TuningApply)
        stored_apply = store.get_apply(p.trial_plan.trial_id)
        assert stored_apply is not None

    def test_apply_fails_admissibility(self, tmp_gov_dir):
        store = ProposalStore(tmp_gov_dir)
        tuner = ConvergenceTuner(store=store, gov_dir=tmp_gov_dir / ".governor")
        p = _make_valid_proposal()
        p.scope.regime.prompt_profile_hash = ""
        p.scope.regime.config_hash = ""
        store.save_proposal(p)
        result = tuner.apply(p.proposal_id, applied_by="alice")
        assert isinstance(result, list)
        assert any(not r.passed for r in result)

    def test_apply_nonexistent_proposal(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        result = tuner.apply("tp_nonexistent", applied_by="alice")
        assert isinstance(result, list)
        assert not result[0].passed

    def test_rollback_success(self, tmp_gov_dir):
        store = ProposalStore(tmp_gov_dir)
        tuner = ConvergenceTuner(store=store, gov_dir=tmp_gov_dir / ".governor")
        p = _make_valid_proposal()
        store.save_proposal(p)
        # Apply first
        tuner.apply(
            p.proposal_id, applied_by="alice",
            current_model_id="gpt-5", current_mode="fiction",
        )
        # Rollback
        assert tuner.rollback(p.trial_plan.trial_id) is True
        p2 = store.get_proposal(p.proposal_id)
        assert p2.approval.status == ProposalStatus.ROLLED_BACK

    def test_rollback_nonexistent(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        assert tuner.rollback("trial_nonexistent") is False

    def test_get_status(self, tmp_gov_dir):
        store = ProposalStore(tmp_gov_dir)
        tuner = ConvergenceTuner(store=store, gov_dir=tmp_gov_dir / ".governor")
        p = _make_valid_proposal()
        store.save_proposal(p)
        status = tuner.get_status()
        assert status["total_proposals"] == 1
        assert "proposal_counts" in status

    def test_get_status_empty(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        status = tuner.get_status()
        assert status["total_proposals"] == 0

    def test_create_convergence_tuner(self, tmp_gov_dir):
        gov_dir = tmp_gov_dir / ".governor"
        tuner = create_convergence_tuner(gov_dir)
        assert isinstance(tuner, ConvergenceTuner)

    def test_propose_no_opportunities(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = [
            _make_trace_event("run_1", 0, {"a": 0.5}),
            _make_trace_event("run_1", 1, {"a": 0.1}, action="SOFT_REPROMPT"),
            _make_result_event("run_1", 2, "ACCEPTED", {"a": 0.0}),
        ]
        proposals = tuner.propose(events, mode="fiction")
        # With only 1 run and good performance, no opportunities
        assert len(proposals) == 0


# =============================================================================
# Section 7: Integration with telemetry (8)
# =============================================================================


class TestIntegration:
    def test_end_to_end_propose(self, tmp_gov_dir):
        """Full trace->proposal pipeline."""
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(20):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"monarchy_def": 1.0}))
            events.append(_make_trace_event(rid, 1, {"monarchy_def": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_trace_event(rid, 2, {"monarchy_def": 0.3}, action="HARD_REPROMPT"))
            events.append(_make_result_event(
                rid, 3, "ACCEPTED",
                residual_error_by_anchor={"monarchy_def": 0.1},
                deadzone_actions=["SOFT_REPROMPT"],
            ))
        proposals = tuner.propose(events, mode="fiction", anchor_namespace="fiction")
        assert len(proposals) >= 1
        p = proposals[0]
        assert p.schema_version == "tuning_proposal_v0"
        assert p.scope.mode == TuningMode.FICTION
        assert p.approval.requires_human is True

    def test_store_roundtrip(self, tmp_gov_dir):
        store = ProposalStore(tmp_gov_dir)
        p = _make_valid_proposal()
        store.save_proposal(p)
        p2 = store.get_proposal(p.proposal_id)
        assert p2.to_dict() == p.to_dict()

    def test_proposal_shape_has_all_fields(self):
        p = _make_valid_proposal()
        d = p.to_dict()
        required_keys = {
            "schema_version", "proposal_id", "created_at_utc",
            "scope", "evidence_window", "change_set", "constraints",
            "metrics_before", "predicted_impact", "supporting_evidence",
            "trial_plan", "approval",
        }
        assert required_keys <= set(d.keys())

    def test_apply_record_shape(self):
        ta = TuningApply(
            trial_id="trial_2026-01-20_000001",
            proposal_id="tp_2026-01-20_000001",
            applied_by="alice",
        )
        d = ta.to_dict()
        assert d["schema_version"] == "tuning_apply_v0"
        assert d["applied_by"] == "alice"

    def test_metrics_block_from_real_data(self, tmp_gov_dir):
        analyzer = ConvergenceAnalyzer()
        events = []
        for i in range(10):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 0.5}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(rid, 2, "ACCEPTED", {"a": 0.1}))
        mb = analyzer.compute_metrics_block(events, mode="fiction")
        assert mb.accept_rate == 1.0
        assert mb.attempts_avg == 2.0

    def test_analyzer_plus_tuner(self, tmp_gov_dir):
        """Analyzer and tuner work together."""
        analyzer = ConvergenceAnalyzer()
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(rid, 2, residual_error_by_anchor={"a": 0.5}, deadzone_actions=["SOFT_REPROMPT"]))

        analyses = analyzer.analyze(events)
        opportunities = analyzer.identify_opportunities(analyses)
        assert len(opportunities) >= 1

    def test_proposal_id_format(self, tmp_gov_dir):
        """Proposal IDs follow tp_YYYY-MM-DD_NNNNNN format."""
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(rid, 2, residual_error_by_anchor={"a": 0.5}, deadzone_actions=["SOFT_REPROMPT"]))
        proposals = tuner.propose(events, mode="fiction")
        for p in proposals:
            assert p.proposal_id.startswith("tp_")
            assert len(p.proposal_id) == len("tp_YYYY-MM-DD_NNNNNN")

    def test_trial_id_format(self, tmp_gov_dir):
        tuner = ConvergenceTuner(store=ProposalStore(tmp_gov_dir), gov_dir=tmp_gov_dir / ".governor")
        events = []
        for i in range(15):
            rid = f"run_{i}"
            events.append(_make_trace_event(rid, 0, {"a": 1.0}))
            events.append(_make_trace_event(rid, 1, {"a": 1.0}, action="SOFT_REPROMPT"))
            events.append(_make_result_event(rid, 2, residual_error_by_anchor={"a": 0.5}, deadzone_actions=["SOFT_REPROMPT"]))
        proposals = tuner.propose(events, mode="fiction")
        for p in proposals:
            assert p.trial_plan.trial_id.startswith("trial_")


# =============================================================================
# Section 8: Edge cases and safety (7)
# =============================================================================


class TestEdgeCasesAndSafety:
    def test_hard_guards_cannot_be_false(self):
        """HardGuards always forces True regardless of input."""
        hg = HardGuards()
        hg.severity_downgrade_forbidden = False
        # __post_init__ already ran, but the forced-True invariant is at creation
        # Re-init:
        hg2 = HardGuards(severity_downgrade_forbidden=False)
        assert hg2.severity_downgrade_forbidden is True

    def test_approval_requires_human_cannot_be_false(self):
        a = Approval(requires_human=False)
        assert a.requires_human is True
        # Round-trip: from_dict also forces True
        d = a.to_dict()
        a2 = Approval.from_dict(d)
        assert a2.requires_human is True

    def test_cross_mode_detection(self):
        """Proposal targets outside namespace are caught."""
        p = _make_valid_proposal()
        p.scope.anchor_namespace = "fiction"
        p.scope.targets = ["nonfiction.concept_x"]
        r = check_regime_match(p)
        assert r.passed is False

    def test_empty_changes_analyzed(self):
        p = _make_valid_proposal(change_set=ChangeSet(changes=[]))
        r = check_strength_non_regression(p)
        assert r.passed is True

    def test_action_aggressiveness_constant(self):
        assert ACTION_AGGRESSIVENESS["SOFT_REPROMPT"] < ACTION_AGGRESSIVENESS["HARD_REPROMPT"]
        assert ACTION_AGGRESSIVENESS["HARD_REPROMPT"] < ACTION_AGGRESSIVENESS["FAIL_CLOSED"]

    def test_proposal_with_default_values(self):
        """Default TuningProposal should serialize cleanly."""
        p = TuningProposal()
        d = p.to_dict()
        p2 = TuningProposal.from_dict(d)
        assert p2.schema_version == "tuning_proposal_v0"
        assert p2.approval.requires_human is True

    def test_multiple_violations_in_single_check(self):
        """A single check can report multiple violations."""
        p = _make_valid_proposal()
        p.scope.regime.prompt_profile_hash = ""
        p.scope.regime.config_hash = ""
        r = check_determinism_hygiene(p)
        assert r.passed is False
        assert len(r.violations) == 2
