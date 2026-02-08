"""Tests for quorum_ext — severity-based quorum gating (AG2 Layer 2.1-D)."""

import json
from pathlib import Path

import pytest

from governor.quorum_ext import (
    Severity,
    QuorumCheckResult,
    AdjudicationAction,
    ConfirmerType,
    QuorumRequirement,
    Confirmation,
    Rejection,
    QuorumCheckDetail,
    AdjudicationRequest,
    QuorumExtState,
    S1_QUORUM,
    S2_QUORUM,
    S3_QUORUM,
    SEVERITY_REQUIREMENTS,
    EVIDENCE_DOMAINS,
    MODEL_FAMILIES,
    DEFAULT_FAULT_TOLERANCE,
    hash_action,
    get_requirement,
    check_quorum,
    check_two_man_rule,
    check_full_quorum,
    handle_disagreement,
    classify_severity,
    compute_fault_tolerance,
    make_quorum_ext_event,
    make_quorum_check_event,
    make_disagreement_event,
    make_two_man_event,
    QuorumExtStore,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_severity_tiers(self):
        assert len(Severity) == 3
        assert Severity.S1.value == "S1"
        assert Severity.S3.value == "S3"

    def test_check_results(self):
        assert len(QuorumCheckResult) == 6

    def test_adjudication_actions(self):
        assert len(AdjudicationAction) == 4

    def test_confirmer_types(self):
        assert len(ConfirmerType) == 3


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_severity_requirements_complete(self):
        for s in Severity:
            assert s in SEVERITY_REQUIREMENTS

    def test_s1_no_quorum(self):
        assert S1_QUORUM.min_confirmations == 0
        assert not S1_QUORUM.require_independence

    def test_s2_basic(self):
        assert S2_QUORUM.min_confirmations == 1
        assert not S2_QUORUM.require_independence

    def test_s3_full(self):
        assert S3_QUORUM.min_confirmations == 2
        assert S3_QUORUM.min_evidence_domains == 2
        assert S3_QUORUM.require_independence
        assert S3_QUORUM.require_two_man_rule

    def test_evidence_domains(self):
        assert "web" in EVIDENCE_DOMAINS
        assert "local_file" in EVIDENCE_DOMAINS

    def test_model_families(self):
        assert "claude" in MODEL_FAMILIES
        assert "human" in MODEL_FAMILIES

    def test_fault_tolerance(self):
        assert DEFAULT_FAULT_TOLERANCE == 1


# ---------------------------------------------------------------------------
# QuorumRequirement
# ---------------------------------------------------------------------------

class TestQuorumRequirement:
    def test_roundtrip(self):
        r = QuorumRequirement(2, 2, True, True)
        d = r.to_dict()
        r2 = QuorumRequirement.from_dict(d)
        assert r2.min_confirmations == 2
        assert r2.require_two_man_rule

    def test_schema(self):
        d = S3_QUORUM.to_dict()
        required = {"min_confirmations", "min_evidence_domains",
                     "require_independence", "require_two_man_rule"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------

class TestConfirmation:
    def test_create(self):
        c = Confirmation(
            claim_id="c1", confirmer="agent_a",
            confirmer_type=ConfirmerType.AGENT,
            model_family="claude", evidence_domain="web",
        )
        assert c.claim_id == "c1"
        assert c.ts

    def test_roundtrip(self):
        c = Confirmation(
            "c1", "agent_a", ConfirmerType.HUMAN,
            model_family="human", evidence_domain="local_file",
            confidence=0.9,
        )
        d = c.to_dict()
        c2 = Confirmation.from_dict(d)
        assert c2.confirmer_type == ConfirmerType.HUMAN
        assert c2.confidence == 0.9

    def test_schema(self):
        c = Confirmation("c1", "a", ConfirmerType.AGENT)
        d = c.to_dict()
        required = {"claim_id", "confirmer", "confirmer_type",
                     "model_family", "evidence_domain", "confidence", "ts"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# Rejection
# ---------------------------------------------------------------------------

class TestRejection:
    def test_create(self):
        r = Rejection("c1", "agent_b", ConfirmerType.AGENT, reason="insufficient evidence")
        assert r.reason == "insufficient evidence"

    def test_roundtrip(self):
        r = Rejection("c1", "human_1", ConfirmerType.HUMAN, "wrong")
        d = r.to_dict()
        r2 = Rejection.from_dict(d)
        assert r2.rejector_type == ConfirmerType.HUMAN

    def test_schema(self):
        r = Rejection("c1", "a", ConfirmerType.AGENT)
        d = r.to_dict()
        required = {"claim_id", "rejector", "rejector_type", "reason", "ts"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# QuorumCheckDetail
# ---------------------------------------------------------------------------

class TestQuorumCheckDetail:
    def test_roundtrip(self):
        c = QuorumCheckDetail(
            result=QuorumCheckResult.PASSED,
            severity=Severity.S3,
            requirement=S3_QUORUM,
            confirmations_count=3,
            domains_count=2,
        )
        d = c.to_dict()
        c2 = QuorumCheckDetail.from_dict(d)
        assert c2.result == QuorumCheckResult.PASSED
        assert c2.severity == Severity.S3
        assert c2.confirmations_count == 3

    def test_schema(self):
        c = QuorumCheckDetail(
            QuorumCheckResult.PASSED, Severity.S1, S1_QUORUM,
        )
        d = c.to_dict()
        required = {"result", "severity", "requirement", "confirmations_count",
                     "domains_count", "model_families_count",
                     "has_human_approval", "has_independent_confirmation", "details"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# AdjudicationRequest
# ---------------------------------------------------------------------------

class TestAdjudicationRequest:
    def test_create(self):
        a = AdjudicationRequest(
            claim_id="c1",
            action=AdjudicationAction.ADJUDICATION_REQUESTED,
            reason="dispute",
        )
        assert a.claim_id == "c1"
        assert not a.resolved

    def test_roundtrip(self):
        c = Confirmation("c1", "a", ConfirmerType.AGENT)
        r = Rejection("c1", "b", ConfirmerType.AGENT)
        a = AdjudicationRequest(
            "c1", AdjudicationAction.EVIDENCE_REVIEW,
            confirmations=[c], rejections=[r],
            reason="test", resolved=True, resolution="confirmed",
        )
        d = a.to_dict()
        a2 = AdjudicationRequest.from_dict(d)
        assert a2.resolved
        assert len(a2.confirmations) == 1
        assert len(a2.rejections) == 1

    def test_schema(self):
        a = AdjudicationRequest("c1", AdjudicationAction.ADJUDICATION_REQUESTED)
        d = a.to_dict()
        required = {"claim_id", "action", "confirmations", "rejections",
                     "reason", "resolved", "resolution", "ts"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# QuorumExtState
# ---------------------------------------------------------------------------

class TestQuorumExtState:
    def test_default(self):
        s = QuorumExtState()
        assert s.passed_count() == 0
        assert s.failed_count() == 0

    def test_record_check(self):
        s = QuorumExtState()
        c = QuorumCheckDetail(QuorumCheckResult.PASSED, Severity.S2, S2_QUORUM)
        s.record_check(c)
        assert s.passed_count() == 1

    def test_record_failure(self):
        s = QuorumExtState()
        c = QuorumCheckDetail(QuorumCheckResult.FAILED_CONFIRMATIONS, Severity.S3, S3_QUORUM)
        s.record_check(c)
        assert s.failed_count() == 1

    def test_not_required_not_counted_as_failure(self):
        s = QuorumExtState()
        c = QuorumCheckDetail(QuorumCheckResult.NOT_REQUIRED, Severity.S1, S1_QUORUM)
        s.record_check(c)
        assert s.failed_count() == 0

    def test_record_confirmation(self):
        s = QuorumExtState()
        s.record_confirmation(Confirmation("c1", "a", ConfirmerType.AGENT))
        assert len(s.confirmations) == 1

    def test_record_rejection(self):
        s = QuorumExtState()
        s.record_rejection(Rejection("c1", "b", ConfirmerType.AGENT))
        assert len(s.rejections) == 1

    def test_roundtrip(self):
        s = QuorumExtState()
        s.record_check(QuorumCheckDetail(QuorumCheckResult.PASSED, Severity.S2, S2_QUORUM))
        s.record_confirmation(Confirmation("c1", "a", ConfirmerType.AGENT))
        d = s.to_dict()
        s2 = QuorumExtState.from_dict(d)
        assert s2.passed_count() == 1
        assert len(s2.confirmations) == 1


# ---------------------------------------------------------------------------
# hash_action
# ---------------------------------------------------------------------------

class TestHashAction:
    def test_deterministic(self):
        h1 = hash_action("deploy to prod")
        h2 = hash_action("deploy to prod")
        assert h1 == h2

    def test_different(self):
        assert hash_action("a") != hash_action("b")

    def test_length(self):
        assert len(hash_action("test")) == 16


# ---------------------------------------------------------------------------
# check_quorum
# ---------------------------------------------------------------------------

class TestCheckQuorum:
    def test_s1_not_required(self):
        r = check_quorum(Severity.S1, [])
        assert r.result == QuorumCheckResult.NOT_REQUIRED

    def test_s2_no_confirmations(self):
        r = check_quorum(Severity.S2, [])
        assert r.result == QuorumCheckResult.FAILED_CONFIRMATIONS

    def test_s2_one_confirmation(self):
        confs = [Confirmation("c1", "a", ConfirmerType.AGENT, evidence_domain="web")]
        r = check_quorum(Severity.S2, confs)
        assert r.result == QuorumCheckResult.PASSED

    def test_s3_insufficient_confirmations(self):
        confs = [Confirmation("c1", "a", ConfirmerType.AGENT,
                              model_family="claude", evidence_domain="web")]
        r = check_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_CONFIRMATIONS

    def test_s3_insufficient_domains(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT,
                         model_family="claude", evidence_domain="web"),
            Confirmation("c1", "b", ConfirmerType.AGENT,
                         model_family="gpt", evidence_domain="web"),
        ]
        r = check_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_DOMAINS

    def test_s3_insufficient_independence(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT,
                         model_family="claude", evidence_domain="web"),
            Confirmation("c1", "b", ConfirmerType.AGENT,
                         model_family="claude", evidence_domain="local_file"),
        ]
        r = check_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_INDEPENDENCE

    def test_s3_all_requirements_met(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT,
                         model_family="claude", evidence_domain="web"),
            Confirmation("c1", "b", ConfirmerType.AGENT,
                         model_family="gpt", evidence_domain="local_file"),
        ]
        r = check_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.PASSED

    def test_custom_requirement(self):
        custom = QuorumRequirement(3, 1, False)
        confs = [Confirmation("c1", f"a{i}", ConfirmerType.AGENT,
                              evidence_domain="web") for i in range(3)]
        r = check_quorum(Severity.S2, confs, requirement=custom)
        assert r.result == QuorumCheckResult.PASSED


# ---------------------------------------------------------------------------
# check_two_man_rule
# ---------------------------------------------------------------------------

class TestTwoManRule:
    def test_s1_not_required(self):
        r = check_two_man_rule(Severity.S1, [])
        assert r.result == QuorumCheckResult.NOT_REQUIRED

    def test_s2_not_required(self):
        r = check_two_man_rule(Severity.S2, [])
        assert r.result == QuorumCheckResult.NOT_REQUIRED

    def test_s3_no_human(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT),
            Confirmation("c1", "b", ConfirmerType.INDEPENDENT),
        ]
        r = check_two_man_rule(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_TWO_MAN
        assert not r.has_human_approval
        assert r.has_independent_confirmation

    def test_s3_no_independent(self):
        confs = [
            Confirmation("c1", "h", ConfirmerType.HUMAN),
            Confirmation("c1", "a", ConfirmerType.AGENT),
        ]
        r = check_two_man_rule(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_TWO_MAN
        assert r.has_human_approval
        assert not r.has_independent_confirmation

    def test_s3_both_present(self):
        confs = [
            Confirmation("c1", "h", ConfirmerType.HUMAN),
            Confirmation("c1", "i", ConfirmerType.INDEPENDENT),
        ]
        r = check_two_man_rule(Severity.S3, confs)
        assert r.result == QuorumCheckResult.PASSED


# ---------------------------------------------------------------------------
# check_full_quorum
# ---------------------------------------------------------------------------

class TestFullQuorum:
    def test_s1_passes(self):
        r = check_full_quorum(Severity.S1, [])
        assert r.result == QuorumCheckResult.NOT_REQUIRED

    def test_s2_passes(self):
        confs = [Confirmation("c1", "a", ConfirmerType.AGENT, evidence_domain="web")]
        r = check_full_quorum(Severity.S2, confs)
        assert r.result == QuorumCheckResult.PASSED

    def test_s3_fails_quorum(self):
        r = check_full_quorum(Severity.S3, [])
        assert r.result == QuorumCheckResult.FAILED_CONFIRMATIONS

    def test_s3_passes_quorum_but_fails_two_man(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT,
                         model_family="claude", evidence_domain="web"),
            Confirmation("c1", "b", ConfirmerType.AGENT,
                         model_family="gpt", evidence_domain="local_file"),
        ]
        r = check_full_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_TWO_MAN

    def test_s3_full_pass(self):
        confs = [
            Confirmation("c1", "h", ConfirmerType.HUMAN,
                         model_family="human", evidence_domain="web"),
            Confirmation("c1", "i", ConfirmerType.INDEPENDENT,
                         model_family="gpt", evidence_domain="local_file"),
        ]
        r = check_full_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.PASSED


# ---------------------------------------------------------------------------
# handle_disagreement
# ---------------------------------------------------------------------------

class TestHandleDisagreement:
    def test_no_rejections(self):
        confs = [Confirmation("c1", "a", ConfirmerType.AGENT)]
        adj = handle_disagreement("c1", confs, [])
        assert adj.resolved
        assert adj.resolution == "no_dispute"

    def test_agent_disagreement(self):
        confs = [Confirmation("c1", "a", ConfirmerType.AGENT)]
        rejs = [Rejection("c1", "b", ConfirmerType.AGENT, "wrong")]
        adj = handle_disagreement("c1", confs, rejs)
        assert adj.action == AdjudicationAction.ESCALATED_TO_HUMAN
        assert not adj.resolved

    def test_more_confirmations(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT),
            Confirmation("c1", "b", ConfirmerType.AGENT),
        ]
        rejs = [Rejection("c1", "c", ConfirmerType.AGENT, "maybe")]
        adj = handle_disagreement("c1", confs, rejs)
        assert adj.action == AdjudicationAction.ADJUDICATION_REQUESTED

    def test_human_rejection(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT),
            Confirmation("c1", "b", ConfirmerType.AGENT),
        ]
        rejs = [Rejection("c1", "h", ConfirmerType.HUMAN, "no")]
        adj = handle_disagreement("c1", confs, rejs)
        assert adj.action == AdjudicationAction.EVIDENCE_REVIEW

    def test_equal_counts_escalate(self):
        confs = [Confirmation("c1", "a", ConfirmerType.AGENT)]
        rejs = [Rejection("c1", "b", ConfirmerType.AGENT)]
        adj = handle_disagreement("c1", confs, rejs)
        assert adj.action == AdjudicationAction.ESCALATED_TO_HUMAN


# ---------------------------------------------------------------------------
# classify_severity
# ---------------------------------------------------------------------------

class TestClassifySeverity:
    def test_default_s1(self):
        assert classify_severity() == Severity.S1

    def test_irreversible_s3(self):
        assert classify_severity(irreversible=True) == Severity.S3

    def test_high_risk_s3(self):
        assert classify_severity(risk_score=0.8) == Severity.S3

    def test_medium_scope_s2(self):
        assert classify_severity(scope_size=0.6) == Severity.S2

    def test_medium_risk_s2(self):
        assert classify_severity(risk_score=0.4) == Severity.S2

    def test_low_everything_s1(self):
        assert classify_severity(scope_size=0.1, risk_score=0.1) == Severity.S1


# ---------------------------------------------------------------------------
# compute_fault_tolerance
# ---------------------------------------------------------------------------

class TestFaultTolerance:
    def test_default(self):
        assert compute_fault_tolerance(5) == 2  # f=1, k=2

    def test_custom_f(self):
        assert compute_fault_tolerance(10, f=2) == 3


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_basic_event(self):
        e = make_quorum_ext_event("test", "c1", {"x": 1})
        assert e["type"] == "quorum_ext"
        assert e["action"] == "test"
        assert e["ts"]

    def test_minimal_event(self):
        e = make_quorum_ext_event("scan")
        assert e["details"] == {}

    def test_check_event(self):
        check = QuorumCheckDetail(
            QuorumCheckResult.PASSED, Severity.S2, S2_QUORUM,
            confirmations_count=1,
        )
        e = make_quorum_check_event(check)
        assert e["action"] == "quorum_check"

    def test_disagreement_event(self):
        adj = AdjudicationRequest(
            "c1", AdjudicationAction.ADJUDICATION_REQUESTED,
            confirmations=[Confirmation("c1", "a", ConfirmerType.AGENT)],
            rejections=[Rejection("c1", "b", ConfirmerType.AGENT)],
        )
        e = make_disagreement_event(adj)
        assert e["action"] == "quorum_disagreement"
        assert e["details"]["confirmations"] == 1
        assert e["details"]["rejections"] == 1

    def test_two_man_event(self):
        check = QuorumCheckDetail(
            QuorumCheckResult.PASSED, Severity.S3, S3_QUORUM,
            has_human_approval=True, has_independent_confirmation=True,
        )
        e = make_two_man_event(check)
        assert e["action"] == "two_man_rule_check"
        assert e["details"]["human_approval"]


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestStore:
    def test_save_load(self, tmp_path):
        store = QuorumExtStore(governor_dir=tmp_path)
        state = QuorumExtState()
        state.record_check(QuorumCheckDetail(
            QuorumCheckResult.PASSED, Severity.S2, S2_QUORUM,
        ))
        store.save(state, "run1")
        loaded = store.load("run1")
        assert loaded is not None
        assert loaded.passed_count() == 1

    def test_load_missing(self, tmp_path):
        store = QuorumExtStore(governor_dir=tmp_path)
        assert store.load("nope") is None

    def test_list_runs(self, tmp_path):
        store = QuorumExtStore(governor_dir=tmp_path)
        store.save(QuorumExtState(), "a")
        store.save(QuorumExtState(), "b")
        runs = store.list_runs()
        assert "a" in runs
        assert "b" in runs

    def test_default_dir(self):
        store = QuorumExtStore()
        assert store.quorum_ext_dir == Path(".governor") / "quorum_ext"


# ---------------------------------------------------------------------------
# Golden schemas
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_check_detail_schema(self):
        c = check_quorum(Severity.S2, [
            Confirmation("c1", "a", ConfirmerType.AGENT, evidence_domain="web"),
        ])
        d = c.to_dict()
        required = {"result", "severity", "requirement", "confirmations_count",
                     "domains_count", "model_families_count",
                     "has_human_approval", "has_independent_confirmation", "details"}
        assert required <= set(d.keys())

    def test_confirmation_schema(self):
        c = Confirmation("c1", "a", ConfirmerType.AGENT, "claude", "web", 0.9)
        d = c.to_dict()
        required = {"claim_id", "confirmer", "confirmer_type",
                     "model_family", "evidence_domain", "confidence", "ts"}
        assert required <= set(d.keys())

    def test_adjudication_schema(self):
        a = AdjudicationRequest("c1", AdjudicationAction.ADJUDICATION_REQUESTED)
        d = a.to_dict()
        required = {"claim_id", "action", "confirmations", "rejections",
                     "reason", "resolved", "resolution", "ts"}
        assert required <= set(d.keys())

    def test_state_schema(self):
        s = QuorumExtState()
        d = s.to_dict()
        required = {"checks", "adjudications", "confirmations", "rejections", "events"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        store = QuorumExtStore(governor_dir=tmp_path)
        state = QuorumExtState()

        # S1 claim — no quorum needed
        r1 = check_full_quorum(Severity.S1, [])
        state.record_check(r1)
        assert r1.result == QuorumCheckResult.NOT_REQUIRED

        # S2 claim — one confirmation needed
        conf_s2 = Confirmation("c2", "agent_a", ConfirmerType.AGENT,
                               evidence_domain="web")
        state.record_confirmation(conf_s2)
        r2 = check_full_quorum(Severity.S2, [conf_s2])
        state.record_check(r2)
        assert r2.result == QuorumCheckResult.PASSED

        # S3 claim — full quorum + two-man rule
        confs_s3 = [
            Confirmation("c3", "human_1", ConfirmerType.HUMAN,
                         model_family="human", evidence_domain="web"),
            Confirmation("c3", "verifier_1", ConfirmerType.INDEPENDENT,
                         model_family="gpt", evidence_domain="local_file"),
        ]
        for c in confs_s3:
            state.record_confirmation(c)
        r3 = check_full_quorum(Severity.S3, confs_s3)
        state.record_check(r3)
        assert r3.result == QuorumCheckResult.PASSED

        # Disagreement on another claim
        confs = [Confirmation("c4", "a", ConfirmerType.AGENT)]
        rejs = [Rejection("c4", "b", ConfirmerType.AGENT, "evidence weak")]
        state.record_rejection(rejs[0])
        adj = handle_disagreement("c4", confs, rejs)
        state.record_adjudication(adj)

        # Save and reload
        store.save(state, "lifecycle")
        loaded = store.load("lifecycle")
        assert loaded is not None
        assert loaded.passed_count() == 2  # S2 + S3
        assert len(loaded.adjudications) == 1
        assert len(loaded.confirmations) == 3  # 1 S2 + 2 S3

    def test_severity_classification_to_quorum(self):
        # Low risk → S1 → no quorum
        s1 = classify_severity(risk_score=0.1)
        assert s1 == Severity.S1
        r1 = check_full_quorum(s1, [])
        assert r1.result == QuorumCheckResult.NOT_REQUIRED

        # Medium risk → S2 → needs confirmation
        s2 = classify_severity(risk_score=0.4)
        assert s2 == Severity.S2
        r2 = check_full_quorum(s2, [])
        assert r2.result == QuorumCheckResult.FAILED_CONFIRMATIONS

        # Irreversible → S3 → needs full quorum
        s3 = classify_severity(irreversible=True)
        assert s3 == Severity.S3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_confirmations_s3(self):
        r = check_quorum(Severity.S3, [])
        assert r.result == QuorumCheckResult.FAILED_CONFIRMATIONS

    def test_empty_model_family(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT,
                         model_family="", evidence_domain="web"),
            Confirmation("c1", "b", ConfirmerType.AGENT,
                         model_family="", evidence_domain="local_file"),
        ]
        r = check_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_INDEPENDENCE

    def test_empty_evidence_domain(self):
        confs = [
            Confirmation("c1", "a", ConfirmerType.AGENT,
                         model_family="claude", evidence_domain=""),
            Confirmation("c1", "b", ConfirmerType.AGENT,
                         model_family="gpt", evidence_domain=""),
        ]
        r = check_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.FAILED_DOMAINS

    def test_many_confirmations(self):
        confs = [
            Confirmation("c1", f"a{i}", ConfirmerType.AGENT,
                         model_family=f"model_{i % 3}",
                         evidence_domain=f"domain_{i % 4}")
            for i in range(10)
        ]
        r = check_quorum(Severity.S3, confs)
        assert r.result == QuorumCheckResult.PASSED
        assert r.confirmations_count == 10

    def test_disagreement_empty_inputs(self):
        adj = handle_disagreement("c1", [], [])
        assert adj.resolved
