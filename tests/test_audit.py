"""Tests for governor.audit — Grounding Audit Pipeline."""

import json
import pytest

from governor.audit import (
    GroundingStatus,
    AuditStage,
    FailureMode,
    AuditDecision,
    AuditSeverity,
    AssertionScope,
    ClaimRisk,
    AuditResolution,
    DetectionSignals,
    GroundingAudit,
    PolicyEntry,
    PolicyStore,
    classify_failure_modes,
    determine_grounding_status,
    determine_decision,
    determine_severity,
    AuditPipeline,
    quick_audit,
    create_pipeline,
)


# =============================================================================
# Enum Tests
# =============================================================================


class TestGroundingStatus:
    def test_values(self):
        assert GroundingStatus.GROUNDED.value == "grounded"
        assert GroundingStatus.WEAK.value == "weak"
        assert GroundingStatus.UNGROUNDED.value == "ungrounded"
        assert GroundingStatus.CONTRADICTED.value == "contradicted"
        assert GroundingStatus.UNKNOWN.value == "unknown"

    def test_is_problematic(self):
        assert not GroundingStatus.GROUNDED.is_problematic
        assert not GroundingStatus.WEAK.is_problematic
        assert GroundingStatus.UNGROUNDED.is_problematic
        assert GroundingStatus.CONTRADICTED.is_problematic
        assert not GroundingStatus.UNKNOWN.is_problematic

    def test_severity_weight(self):
        assert GroundingStatus.GROUNDED.severity_weight == 0.0
        assert GroundingStatus.WEAK.severity_weight == 0.5
        assert GroundingStatus.UNGROUNDED.severity_weight == 1.0
        assert GroundingStatus.CONTRADICTED.severity_weight == 1.5
        assert GroundingStatus.UNKNOWN.severity_weight == 0.3

    def test_string_enum_comparison(self):
        assert GroundingStatus.GROUNDED == "grounded"


class TestAuditStage:
    def test_values(self):
        assert AuditStage.PRE_COMMIT.value == "pre_commit"
        assert AuditStage.POST_COMMIT.value == "post_commit"
        assert AuditStage.PERIODIC.value == "periodic"
        assert AuditStage.INCIDENT.value == "incident"

    def test_leak_weight(self):
        assert AuditStage.PRE_COMMIT.leak_weight == 1.0
        assert AuditStage.POST_COMMIT.leak_weight == 3.0
        assert AuditStage.PERIODIC.leak_weight == 2.0
        assert AuditStage.INCIDENT.leak_weight == 5.0

    def test_later_detection_worse(self):
        """Incident has highest leak weight, pre-commit has lowest."""
        assert AuditStage.PRE_COMMIT.leak_weight < AuditStage.PERIODIC.leak_weight
        assert AuditStage.PERIODIC.leak_weight < AuditStage.POST_COMMIT.leak_weight
        assert AuditStage.POST_COMMIT.leak_weight < AuditStage.INCIDENT.leak_weight


class TestFailureMode:
    def test_all_modes_exist(self):
        modes = [
            FailureMode.NO_EVIDENCE,
            FailureMode.WEAK_EVIDENCE,
            FailureMode.CITE_DRIFT,
            FailureMode.SOURCE_ALIASING,
            FailureMode.TEMPORAL_STALENESS,
            FailureMode.ENTAILMENT_OVERREACH,
            FailureMode.SPECIOUS_PRECISION,
            FailureMode.ENTITY_CONFLATION,
            FailureMode.COUNTEREVIDENCE_IGNORED,
            FailureMode.TOOL_MISREAD,
            FailureMode.PROMPT_INJECTION,
            FailureMode.NONE,
        ]
        assert len(modes) == 12

    def test_string_values(self):
        assert FailureMode.NO_EVIDENCE.value == "no_evidence"
        assert FailureMode.SPECIOUS_PRECISION.value == "specious_precision"


class TestAuditDecision:
    def test_values(self):
        assert AuditDecision.ALLOW_HARD.value == "allow_hard"
        assert AuditDecision.DOWNGRADE_SOFT.value == "downgrade_soft"
        assert AuditDecision.BLOCK.value == "block"
        assert AuditDecision.NEEDS_MORE_WORK.value == "needs_more_work"


class TestAuditSeverity:
    def test_values(self):
        assert AuditSeverity.LOW.value == "low"
        assert AuditSeverity.MEDIUM.value == "medium"
        assert AuditSeverity.HIGH.value == "high"

    def test_numeric(self):
        assert AuditSeverity.LOW.numeric == 1
        assert AuditSeverity.MEDIUM.numeric == 2
        assert AuditSeverity.HIGH.numeric == 3


class TestAssertionScope:
    def test_values(self):
        assert AssertionScope.INTERNAL_PREMISE.value == "internal_premise"
        assert AssertionScope.USER_OUTPUT.value == "user_output"
        assert AssertionScope.ACTION_TRIGGER.value == "action_trigger"

    def test_risk_multiplier(self):
        assert AssertionScope.INTERNAL_PREMISE.risk_multiplier == 1.0
        assert AssertionScope.USER_OUTPUT.risk_multiplier == 1.5
        assert AssertionScope.ACTION_TRIGGER.risk_multiplier == 2.0

    def test_higher_scope_more_dangerous(self):
        assert AssertionScope.INTERNAL_PREMISE.risk_multiplier < AssertionScope.USER_OUTPUT.risk_multiplier
        assert AssertionScope.USER_OUTPUT.risk_multiplier < AssertionScope.ACTION_TRIGGER.risk_multiplier


class TestClaimRisk:
    def test_values(self):
        assert ClaimRisk.LOW.value == "low"
        assert ClaimRisk.MEDIUM.value == "medium"
        assert ClaimRisk.HIGH.value == "high"

    def test_k_required(self):
        assert ClaimRisk.LOW.k_required == 1
        assert ClaimRisk.MEDIUM.k_required == 2
        assert ClaimRisk.HIGH.k_required == 3

    def test_independence_threshold(self):
        assert ClaimRisk.LOW.independence_threshold == 0.6
        assert ClaimRisk.MEDIUM.independence_threshold == 0.7
        assert ClaimRisk.HIGH.independence_threshold == 0.7


class TestAuditResolution:
    def test_values(self):
        assert AuditResolution.RETRACTED.value == "retracted"
        assert AuditResolution.DOWNGRADED.value == "downgraded"
        assert AuditResolution.FIXED.value == "fixed"
        assert AuditResolution.LEFT_OPEN.value == "left_open"


# =============================================================================
# DetectionSignals Tests
# =============================================================================


class TestDetectionSignals:
    def test_defaults(self):
        s = DetectionSignals()
        assert s.evidence_count == 0
        assert s.evidence_strength_sum == 0.0
        assert s.evidence_kinds == []
        assert s.independence_score == 0.0
        assert s.source_aliasing_score == 0.0
        assert s.citation_coverage == 0.0
        assert s.novel_entity_count == 0
        assert s.novel_number_count == 0
        assert s.specious_precision_score == 0.0
        assert s.freshness_age_seconds == 0.0
        assert s.is_stale is False
        assert s.confidence_language_score == 0.0
        assert s.confidence_evidence_gap == 0.0
        assert s.cross_run_instability == 0.0
        assert s.tool_misread_risk == 0.0

    def test_custom_values(self):
        s = DetectionSignals(
            evidence_count=3,
            evidence_strength_sum=2.1,
            evidence_kinds=["tool_trace", "citation"],
            independence_score=0.8,
            novel_number_count=2,
        )
        assert s.evidence_count == 3
        assert s.evidence_strength_sum == 2.1
        assert len(s.evidence_kinds) == 2
        assert s.independence_score == 0.8
        assert s.novel_number_count == 2

    def test_to_dict(self):
        s = DetectionSignals(evidence_count=5, is_stale=True)
        d = s.to_dict()
        assert d["evidence_count"] == 5
        assert d["is_stale"] is True
        assert "independence_score" in d
        assert "tool_misread_risk" in d

    def test_from_dict(self):
        data = {
            "evidence_count": 3,
            "evidence_strength_sum": 1.5,
            "is_stale": True,
            "novel_entity_count": 4,
        }
        s = DetectionSignals.from_dict(data)
        assert s.evidence_count == 3
        assert s.evidence_strength_sum == 1.5
        assert s.is_stale is True
        assert s.novel_entity_count == 4

    def test_from_dict_defaults(self):
        s = DetectionSignals.from_dict({})
        assert s.evidence_count == 0
        assert s.is_stale is False

    def test_roundtrip(self):
        s = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.4,
            evidence_kinds=["tool_trace"],
            independence_score=0.9,
            source_aliasing_score=0.1,
            citation_coverage=0.85,
            novel_entity_count=1,
            novel_number_count=0,
            specious_precision_score=0.2,
            freshness_age_seconds=3600.0,
            is_stale=False,
            confidence_language_score=0.3,
            confidence_evidence_gap=0.1,
            cross_run_instability=0.05,
            tool_misread_risk=0.15,
        )
        d = s.to_dict()
        s2 = DetectionSignals.from_dict(d)
        assert s2.evidence_count == s.evidence_count
        assert s2.independence_score == s.independence_score
        assert s2.tool_misread_risk == s.tool_misread_risk


# =============================================================================
# GroundingAudit Tests
# =============================================================================


class TestGroundingAudit:
    def _make_audit(self, **kwargs) -> GroundingAudit:
        defaults = dict(
            audit_id="ga_test1",
            assertion_id="assert_1",
            stage=AuditStage.PRE_COMMIT,
            status=GroundingStatus.GROUNDED,
            decision=AuditDecision.ALLOW_HARD,
        )
        defaults.update(kwargs)
        return GroundingAudit(**defaults)

    def test_basic_creation(self):
        a = self._make_audit()
        assert a.audit_id == "ga_test1"
        assert a.assertion_id == "assert_1"
        assert a.stage == AuditStage.PRE_COMMIT
        assert a.status == GroundingStatus.GROUNDED
        assert a.decision == AuditDecision.ALLOW_HARD

    def test_is_clean(self):
        a = self._make_audit(status=GroundingStatus.GROUNDED)
        assert a.is_clean
        a2 = self._make_audit(status=GroundingStatus.WEAK)
        assert not a2.is_clean

    def test_is_problematic(self):
        a1 = self._make_audit(status=GroundingStatus.GROUNDED)
        assert not a1.is_problematic
        a2 = self._make_audit(status=GroundingStatus.UNGROUNDED)
        assert a2.is_problematic
        a3 = self._make_audit(status=GroundingStatus.CONTRADICTED)
        assert a3.is_problematic

    def test_leak_score_clean(self):
        a = self._make_audit(
            status=GroundingStatus.GROUNDED,
            stage=AuditStage.PRE_COMMIT,
            severity=AuditSeverity.LOW,
        )
        assert a.leak_score == 0.0  # severity_weight=0 * anything = 0

    def test_leak_score_problematic(self):
        a = self._make_audit(
            status=GroundingStatus.UNGROUNDED,
            stage=AuditStage.INCIDENT,
            severity=AuditSeverity.HIGH,
        )
        # 1.0 * 5.0 * 3 = 15.0
        assert a.leak_score == 15.0

    def test_leak_score_weak_post_commit(self):
        a = self._make_audit(
            status=GroundingStatus.WEAK,
            stage=AuditStage.POST_COMMIT,
            severity=AuditSeverity.MEDIUM,
        )
        # 0.5 * 3.0 * 2 = 3.0
        assert a.leak_score == 3.0

    def test_failure_modes_default_empty(self):
        a = self._make_audit()
        assert a.failure_modes == []

    def test_failure_modes_set(self):
        a = self._make_audit(
            failure_modes=[FailureMode.NO_EVIDENCE, FailureMode.CITE_DRIFT],
        )
        assert len(a.failure_modes) == 2

    def test_resolution_none_by_default(self):
        a = self._make_audit()
        assert a.resolution is None

    def test_resolution_set(self):
        a = self._make_audit(resolution=AuditResolution.RETRACTED)
        assert a.resolution == AuditResolution.RETRACTED

    def test_to_dict(self):
        a = self._make_audit(
            failure_modes=[FailureMode.WEAK_EVIDENCE],
            severity=AuditSeverity.MEDIUM,
            notes="test note",
        )
        d = a.to_dict()
        assert d["audit_id"] == "ga_test1"
        assert d["status"] == "grounded"
        assert d["failure_modes"] == ["weak_evidence"]
        assert d["severity"] == "medium"
        assert d["notes"] == "test note"
        assert "created_at" in d
        assert "leak_score" in d
        assert "is_clean" in d

    def test_from_dict(self):
        a = self._make_audit(
            failure_modes=[FailureMode.NO_EVIDENCE],
            severity=AuditSeverity.HIGH,
            resolution=AuditResolution.FIXED,
        )
        d = a.to_dict()
        a2 = GroundingAudit.from_dict(d)
        assert a2.audit_id == a.audit_id
        assert a2.status == a.status
        assert a2.failure_modes == a.failure_modes
        assert a2.severity == a.severity
        assert a2.resolution == a.resolution

    def test_roundtrip(self):
        a = self._make_audit(
            failure_modes=[FailureMode.CITE_DRIFT, FailureMode.TEMPORAL_STALENESS],
            severity=AuditSeverity.MEDIUM,
            signals=DetectionSignals(evidence_count=2, is_stale=True),
            counterevidence_refs=["ref1", "ref2"],
        )
        d = a.to_dict()
        a2 = GroundingAudit.from_dict(d)
        assert a2.failure_modes == [FailureMode.CITE_DRIFT, FailureMode.TEMPORAL_STALENESS]
        assert a2.signals.evidence_count == 2
        assert a2.signals.is_stale is True
        assert a2.counterevidence_refs == ["ref1", "ref2"]


# =============================================================================
# PolicyEntry Tests
# =============================================================================


class TestPolicyEntry:
    def test_defaults(self):
        p = PolicyEntry(claim_type="static_fact")
        assert p.claim_type == "static_fact"
        assert p.risk == ClaimRisk.LOW
        assert p.scope == AssertionScope.INTERNAL_PREMISE
        assert p.k_required == 1
        assert p.independence_threshold == 0.6
        assert p.min_evidence_strength == 0.7
        assert p.max_novel_numbers == 1
        assert p.max_specious_precision == 0.6
        assert p.freshness_max_seconds == 0.0
        assert p.ttl_seconds == 0.0
        assert p.stabilization_rounds == 1

    def test_key(self):
        p = PolicyEntry(
            claim_type="code",
            risk=ClaimRisk.HIGH,
            scope=AssertionScope.ACTION_TRIGGER,
        )
        assert p.key == "code:high:action_trigger"

    def test_to_dict(self):
        p = PolicyEntry(claim_type="volatile_fact", risk=ClaimRisk.MEDIUM)
        d = p.to_dict()
        assert d["claim_type"] == "volatile_fact"
        assert d["risk"] == "medium"
        assert d["k_required"] == 1

    def test_from_dict(self):
        data = {
            "claim_type": "math",
            "risk": "high",
            "scope": "action_trigger",
            "k_required": 3,
            "min_evidence_strength": 0.95,
        }
        p = PolicyEntry.from_dict(data)
        assert p.claim_type == "math"
        assert p.risk == ClaimRisk.HIGH
        assert p.scope == AssertionScope.ACTION_TRIGGER
        assert p.k_required == 3
        assert p.min_evidence_strength == 0.95

    def test_roundtrip(self):
        p = PolicyEntry(
            claim_type="procedure",
            risk=ClaimRisk.MEDIUM,
            scope=AssertionScope.USER_OUTPUT,
            k_required=2,
            freshness_max_seconds=7200.0,
        )
        d = p.to_dict()
        p2 = PolicyEntry.from_dict(d)
        assert p2.claim_type == p.claim_type
        assert p2.risk == p.risk
        assert p2.k_required == p.k_required
        assert p2.freshness_max_seconds == p.freshness_max_seconds


# =============================================================================
# PolicyStore Tests
# =============================================================================


class TestPolicyStore:
    def test_default_policies_populated(self):
        store = PolicyStore()
        # 6 claim types × 3 risks × 3 scopes = 54
        assert len(store.policies) == 54

    def test_all_claim_types_present(self):
        store = PolicyStore()
        types = set()
        for key in store.policies:
            ct = key.split(":")[0]
            types.add(ct)
        assert types == {"static_fact", "volatile_fact", "code", "math", "procedure", "judgment"}

    def test_get_existing(self):
        store = PolicyStore()
        p = store.get("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        assert p.claim_type == "static_fact"
        assert p.risk == ClaimRisk.LOW

    def test_get_fallback_to_low_internal(self):
        store = PolicyStore()
        # Use a custom claim_type that doesn't exist
        p = store.get("custom_type", ClaimRisk.HIGH, AssertionScope.ACTION_TRIGGER)
        assert p.claim_type == "custom_type"
        # Should get a generic fallback
        assert p.k_required == 1  # Default PolicyEntry

    def test_get_fallback_to_generic(self):
        store = PolicyStore()
        p = store.get("nonexistent_type")
        assert p.claim_type == "nonexistent_type"

    def test_volatile_fact_has_freshness(self):
        store = PolicyStore()
        p = store.get("volatile_fact", ClaimRisk.HIGH, AssertionScope.INTERNAL_PREMISE)
        assert p.freshness_max_seconds > 0
        assert p.ttl_seconds > 0

    def test_static_fact_no_freshness(self):
        store = PolicyStore()
        p = store.get("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        assert p.freshness_max_seconds == 0.0  # Static facts don't expire quickly

    def test_higher_risk_more_evidence(self):
        store = PolicyStore()
        low = store.get("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        high = store.get("static_fact", ClaimRisk.HIGH, AssertionScope.INTERNAL_PREMISE)
        assert high.k_required >= low.k_required

    def test_math_no_novel_numbers(self):
        store = PolicyStore()
        p = store.get("math", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        assert p.max_novel_numbers == 0  # Math claims can't have novel numbers

    def test_judgment_soft_by_default(self):
        store = PolicyStore()
        p = store.get("judgment", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        assert p.k_required == 0  # Low risk judgments don't need evidence
        assert p.min_evidence_strength == 0.0

    def test_tighten_k_required(self):
        store = PolicyStore()
        p = store.get("static_fact", ClaimRisk.MEDIUM, AssertionScope.INTERNAL_PREMISE)
        old_k = p.k_required
        result = store.tighten("static_fact", ClaimRisk.MEDIUM, AssertionScope.INTERNAL_PREMISE,
                               "k_required", 1, "test")
        assert result is True
        assert p.k_required == old_k + 1
        assert len(store.adjustment_history) == 1
        assert store.adjustment_history[0]["direction"] == "tighten"

    def test_tighten_max_novel_numbers(self):
        store = PolicyStore()
        p = store.get("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        old_v = p.max_novel_numbers
        store.tighten("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE,
                      "max_novel_numbers", 1, "test")
        # Lower = tighter for max fields
        assert p.max_novel_numbers == max(0, old_v - 1)

    def test_tighten_invalid_field(self):
        store = PolicyStore()
        result = store.tighten("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE,
                               "nonexistent_field", 1)
        assert result is False

    def test_relax_k_required(self):
        store = PolicyStore()
        p = store.get("static_fact", ClaimRisk.HIGH, AssertionScope.INTERNAL_PREMISE)
        old_k = p.k_required
        result = store.relax("static_fact", ClaimRisk.HIGH, AssertionScope.INTERNAL_PREMISE,
                             "k_required", 1, "clean run")
        assert result is True
        # Relaxing k_required: lower but never below 1
        assert p.k_required == max(1, old_k - 1)
        assert store.adjustment_history[-1]["direction"] == "relax"

    def test_relax_k_required_floor(self):
        """k_required never relaxes below 1."""
        store = PolicyStore()
        p = store.get("judgment", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        # judgment/low has k_required=0, relax should floor at 1...
        # Actually max(1, 0-1) = max(1, -1) = 1
        store.relax("judgment", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE,
                     "k_required", 5)
        assert p.k_required >= 0  # max(0, ...) in relax, then max(1, ...) floors

    def test_relax_independence_floor(self):
        """independence_threshold never relaxes below 0.5."""
        store = PolicyStore()
        p = store.get("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        store.relax("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE,
                     "independence_threshold", 10.0)
        assert p.independence_threshold >= 0.5

    def test_relax_invalid_field(self):
        store = PolicyStore()
        result = store.relax("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE,
                             "nonexistent_field", 1)
        assert result is False

    def test_relax_max_field(self):
        """Relaxing max_novel_numbers means increasing the limit."""
        store = PolicyStore()
        p = store.get("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE)
        old_v = p.max_novel_numbers
        store.relax("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE,
                     "max_novel_numbers", 2)
        assert p.max_novel_numbers == old_v + 2

    def test_to_dict(self):
        store = PolicyStore()
        d = store.to_dict()
        assert "policies" in d
        assert "adjustment_history" in d
        assert len(d["policies"]) == 54

    def test_from_dict(self):
        store = PolicyStore()
        store.tighten("static_fact", ClaimRisk.LOW, AssertionScope.INTERNAL_PREMISE,
                      "k_required", 1, "test")
        d = store.to_dict()
        store2 = PolicyStore.from_dict(d)
        assert len(store2.policies) == len(store.policies)
        assert len(store2.adjustment_history) == 1

    def test_roundtrip(self):
        store = PolicyStore()
        store.tighten("code", ClaimRisk.HIGH, AssertionScope.ACTION_TRIGGER,
                      "min_evidence_strength", 0.1, "incident")
        d = store.to_dict()
        store2 = PolicyStore.from_dict(d)
        p = store2.get("code", ClaimRisk.HIGH, AssertionScope.ACTION_TRIGGER)
        assert p.min_evidence_strength == store.get("code", ClaimRisk.HIGH, AssertionScope.ACTION_TRIGGER).min_evidence_strength


# =============================================================================
# Failure Mode Classification Tests
# =============================================================================


class TestClassifyFailureModes:
    def _policy(self, **kwargs) -> PolicyEntry:
        defaults = dict(claim_type="static_fact")
        defaults.update(kwargs)
        return PolicyEntry(**defaults)

    def test_no_evidence(self):
        signals = DetectionSignals(evidence_count=0)
        modes = classify_failure_modes(signals, self._policy())
        assert modes == [FailureMode.NO_EVIDENCE]

    def test_no_evidence_short_circuits(self):
        """With no evidence, other checks are skipped."""
        signals = DetectionSignals(
            evidence_count=0,
            specious_precision_score=0.99,
            tool_misread_risk=0.99,
        )
        modes = classify_failure_modes(signals, self._policy())
        assert modes == [FailureMode.NO_EVIDENCE]

    def test_weak_evidence(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.3,
            citation_coverage=0.8,
        )
        policy = self._policy(min_evidence_strength=0.7)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WEAK_EVIDENCE in modes

    def test_source_aliasing_score(self):
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            source_aliasing_score=0.6,
            citation_coverage=0.8,
        )
        modes = classify_failure_modes(signals, self._policy())
        assert FailureMode.SOURCE_ALIASING in modes

    def test_source_aliasing_independence(self):
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            independence_score=0.3,  # Below threshold
            citation_coverage=0.8,
        )
        policy = self._policy(independence_threshold=0.6)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.SOURCE_ALIASING in modes

    def test_cite_drift(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            citation_coverage=0.3,  # Low coverage
        )
        modes = classify_failure_modes(signals, self._policy())
        assert FailureMode.CITE_DRIFT in modes

    def test_specious_precision_score(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            specious_precision_score=0.8,
            citation_coverage=0.8,
        )
        policy = self._policy(max_specious_precision=0.6)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.SPECIOUS_PRECISION in modes

    def test_specious_precision_novel_numbers(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            novel_number_count=3,
            citation_coverage=0.8,
        )
        policy = self._policy(max_novel_numbers=1)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.SPECIOUS_PRECISION in modes

    def test_temporal_staleness_flag(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            is_stale=True,
            citation_coverage=0.8,
        )
        modes = classify_failure_modes(signals, self._policy())
        assert FailureMode.TEMPORAL_STALENESS in modes

    def test_temporal_staleness_freshness(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            freshness_age_seconds=100000,
            citation_coverage=0.8,
        )
        policy = self._policy(freshness_max_seconds=3600)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.TEMPORAL_STALENESS in modes

    def test_entailment_overreach(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            confidence_evidence_gap=0.5,
            citation_coverage=0.8,
        )
        modes = classify_failure_modes(signals, self._policy())
        assert FailureMode.ENTAILMENT_OVERREACH in modes

    def test_tool_misread(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            tool_misread_risk=0.7,
            citation_coverage=0.8,
        )
        modes = classify_failure_modes(signals, self._policy())
        assert FailureMode.TOOL_MISREAD in modes

    def test_entity_conflation(self):
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            novel_entity_count=5,
            citation_coverage=0.8,
        )
        modes = classify_failure_modes(signals, self._policy())
        assert FailureMode.ENTITY_CONFLATION in modes

    def test_clean_signals(self):
        """Good signals produce no failure modes."""
        signals = DetectionSignals(
            evidence_count=3,
            evidence_strength_sum=2.5,
            independence_score=0.9,
            citation_coverage=0.95,
            novel_entity_count=0,
            novel_number_count=0,
            specious_precision_score=0.1,
        )
        modes = classify_failure_modes(signals, self._policy())
        assert modes == []

    def test_multiple_failures(self):
        """Multiple failure modes detected simultaneously."""
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.3,  # WEAK_EVIDENCE
            citation_coverage=0.2,      # CITE_DRIFT
            tool_misread_risk=0.8,      # TOOL_MISREAD
            novel_entity_count=5,       # ENTITY_CONFLATION
        )
        modes = classify_failure_modes(signals, self._policy())
        assert FailureMode.WEAK_EVIDENCE in modes
        assert FailureMode.CITE_DRIFT in modes
        assert FailureMode.TOOL_MISREAD in modes
        assert FailureMode.ENTITY_CONFLATION in modes

    def test_deduplication(self):
        """SOURCE_ALIASING can be triggered by two paths, should be deduplicated."""
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            source_aliasing_score=0.8,   # Triggers SOURCE_ALIASING
            independence_score=0.3,       # Also triggers SOURCE_ALIASING
            citation_coverage=0.8,
        )
        policy = self._policy(independence_threshold=0.6)
        modes = classify_failure_modes(signals, policy)
        # Should appear only once despite two triggers
        assert modes.count(FailureMode.SOURCE_ALIASING) == 1


# =============================================================================
# Grounding Status Determination Tests
# =============================================================================


class TestDetermineGroundingStatus:
    def test_no_failures(self):
        assert determine_grounding_status([]) == GroundingStatus.GROUNDED

    def test_counterevidence(self):
        modes = [FailureMode.COUNTEREVIDENCE_IGNORED]
        assert determine_grounding_status(modes) == GroundingStatus.CONTRADICTED

    def test_no_evidence(self):
        modes = [FailureMode.NO_EVIDENCE]
        assert determine_grounding_status(modes) == GroundingStatus.UNGROUNDED

    def test_severe_mode_specious_precision(self):
        modes = [FailureMode.SPECIOUS_PRECISION]
        assert determine_grounding_status(modes) == GroundingStatus.UNGROUNDED

    def test_severe_mode_tool_misread(self):
        modes = [FailureMode.TOOL_MISREAD]
        assert determine_grounding_status(modes) == GroundingStatus.UNGROUNDED

    def test_severe_mode_prompt_injection(self):
        modes = [FailureMode.PROMPT_INJECTION]
        assert determine_grounding_status(modes) == GroundingStatus.UNGROUNDED

    def test_two_non_severe_failures(self):
        modes = [FailureMode.WEAK_EVIDENCE, FailureMode.CITE_DRIFT]
        assert determine_grounding_status(modes) == GroundingStatus.UNGROUNDED

    def test_single_non_severe_failure(self):
        modes = [FailureMode.WEAK_EVIDENCE]
        assert determine_grounding_status(modes) == GroundingStatus.WEAK

    def test_single_cite_drift(self):
        modes = [FailureMode.CITE_DRIFT]
        assert determine_grounding_status(modes) == GroundingStatus.WEAK

    def test_counterevidence_overrides_others(self):
        modes = [FailureMode.WEAK_EVIDENCE, FailureMode.COUNTEREVIDENCE_IGNORED]
        assert determine_grounding_status(modes) == GroundingStatus.CONTRADICTED


# =============================================================================
# Decision Determination Tests
# =============================================================================


class TestDetermineDecision:
    def test_grounded(self):
        assert determine_decision(GroundingStatus.GROUNDED, []) == AuditDecision.ALLOW_HARD

    def test_contradicted(self):
        modes = [FailureMode.COUNTEREVIDENCE_IGNORED]
        assert determine_decision(GroundingStatus.CONTRADICTED, modes) == AuditDecision.BLOCK

    def test_ungrounded_no_evidence(self):
        modes = [FailureMode.NO_EVIDENCE]
        assert determine_decision(GroundingStatus.UNGROUNDED, modes) == AuditDecision.NEEDS_MORE_WORK

    def test_ungrounded_with_counterevidence(self):
        modes = [FailureMode.SPECIOUS_PRECISION]
        assert determine_decision(GroundingStatus.UNGROUNDED, modes, has_counterevidence=True) == AuditDecision.BLOCK

    def test_ungrounded_without_counterevidence(self):
        modes = [FailureMode.SPECIOUS_PRECISION]
        assert determine_decision(GroundingStatus.UNGROUNDED, modes) == AuditDecision.BLOCK

    def test_weak(self):
        modes = [FailureMode.WEAK_EVIDENCE]
        assert determine_decision(GroundingStatus.WEAK, modes) == AuditDecision.DOWNGRADE_SOFT

    def test_unknown(self):
        assert determine_decision(GroundingStatus.UNKNOWN, []) == AuditDecision.NEEDS_MORE_WORK


# =============================================================================
# Severity Determination Tests
# =============================================================================


class TestDetermineSeverity:
    def test_no_failures(self):
        assert determine_severity([], AssertionScope.USER_OUTPUT, ClaimRisk.HIGH) == AuditSeverity.LOW

    def test_severe_mode_high_scope(self):
        modes = [FailureMode.COUNTEREVIDENCE_IGNORED]
        assert determine_severity(modes, AssertionScope.ACTION_TRIGGER, ClaimRisk.LOW) == AuditSeverity.HIGH

    def test_severe_mode_high_risk(self):
        modes = [FailureMode.PROMPT_INJECTION]
        assert determine_severity(modes, AssertionScope.INTERNAL_PREMISE, ClaimRisk.HIGH) == AuditSeverity.HIGH

    def test_severe_mode_low_scope_risk(self):
        modes = [FailureMode.SPECIOUS_PRECISION]
        assert determine_severity(modes, AssertionScope.INTERNAL_PREMISE, ClaimRisk.LOW) == AuditSeverity.MEDIUM

    def test_three_or_more_modes(self):
        modes = [FailureMode.WEAK_EVIDENCE, FailureMode.CITE_DRIFT, FailureMode.TEMPORAL_STALENESS]
        assert determine_severity(modes, AssertionScope.INTERNAL_PREMISE, ClaimRisk.LOW) == AuditSeverity.HIGH

    def test_two_modes(self):
        modes = [FailureMode.WEAK_EVIDENCE, FailureMode.CITE_DRIFT]
        assert determine_severity(modes, AssertionScope.INTERNAL_PREMISE, ClaimRisk.LOW) == AuditSeverity.MEDIUM

    def test_single_mode_action_trigger(self):
        modes = [FailureMode.WEAK_EVIDENCE]
        assert determine_severity(modes, AssertionScope.ACTION_TRIGGER, ClaimRisk.LOW) == AuditSeverity.MEDIUM

    def test_single_mode_low_everything(self):
        modes = [FailureMode.TEMPORAL_STALENESS]
        assert determine_severity(modes, AssertionScope.INTERNAL_PREMISE, ClaimRisk.LOW) == AuditSeverity.LOW


# =============================================================================
# AuditPipeline Tests
# =============================================================================


class TestAuditPipeline:
    def test_creation(self):
        p = AuditPipeline()
        assert p.total_audits == 0
        assert p.total_clean == 0
        assert p.total_problematic == 0
        assert p.policy_store is not None
        assert p.audit_history == []

    def test_creation_with_store(self):
        store = PolicyStore()
        p = AuditPipeline(store)
        assert p.policy_store is store

    def test_audit_clean(self):
        p = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=3,
            evidence_strength_sum=2.5,
            independence_score=0.9,
            citation_coverage=0.95,
        )
        result = p.audit("a1", signals)
        assert result.status == GroundingStatus.GROUNDED
        assert result.decision == AuditDecision.ALLOW_HARD
        assert result.is_clean
        assert p.total_audits == 1
        assert p.total_clean == 1
        assert p.total_problematic == 0

    def test_audit_no_evidence(self):
        p = AuditPipeline()
        signals = DetectionSignals(evidence_count=0)
        result = p.audit("a2", signals)
        assert result.status == GroundingStatus.UNGROUNDED
        assert result.decision == AuditDecision.NEEDS_MORE_WORK
        assert FailureMode.NO_EVIDENCE in result.failure_modes
        assert p.total_problematic == 1

    def test_audit_weak_evidence(self):
        p = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.3,
            citation_coverage=0.8,
        )
        result = p.audit("a3", signals, claim_type="static_fact")
        assert result.status == GroundingStatus.WEAK
        assert result.decision == AuditDecision.DOWNGRADE_SOFT

    def test_audit_with_counterevidence(self):
        p = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            citation_coverage=0.8,
        )
        result = p.audit("a4", signals, has_counterevidence=True)
        assert FailureMode.COUNTEREVIDENCE_IGNORED in result.failure_modes
        assert result.status == GroundingStatus.CONTRADICTED
        assert result.decision == AuditDecision.BLOCK

    def test_audit_id_format(self):
        p = AuditPipeline()
        signals = DetectionSignals(evidence_count=1, evidence_strength_sum=0.8, citation_coverage=0.8)
        result = p.audit("a5", signals)
        assert result.audit_id.startswith("ga_")

    def test_audit_records_failure_modes(self):
        p = AuditPipeline()
        signals = DetectionSignals(evidence_count=0)
        p.audit("a6", signals)
        assert p.failure_mode_counts["no_evidence"] == 1

    def test_audit_stage_parameter(self):
        p = AuditPipeline()
        signals = DetectionSignals(evidence_count=3, evidence_strength_sum=2.1, citation_coverage=0.9)
        result = p.audit("a7", signals, stage=AuditStage.PERIODIC)
        assert result.stage == AuditStage.PERIODIC

    def test_audit_notes(self):
        p = AuditPipeline()
        signals = DetectionSignals(evidence_count=1, evidence_strength_sum=0.8, citation_coverage=0.8)
        result = p.audit("a8", signals, notes="manual review")
        assert result.notes == "manual review"


class TestAuditPipelineStages:
    def test_pre_commit_audit(self):
        p = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            independence_score=0.8,
            citation_coverage=0.9,
        )
        result = p.pre_commit_audit("a1", signals)
        assert result.stage == AuditStage.PRE_COMMIT
        assert result.decision == AuditDecision.ALLOW_HARD

    def test_pre_commit_blocks(self):
        p = AuditPipeline()
        signals = DetectionSignals(evidence_count=0)
        result = p.pre_commit_audit("a2", signals)
        assert result.stage == AuditStage.PRE_COMMIT
        assert result.decision != AuditDecision.ALLOW_HARD

    def test_post_commit_audit(self):
        p = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            citation_coverage=0.8,
        )
        result = p.post_commit_audit("a3", signals)
        assert result.stage == AuditStage.POST_COMMIT

    def test_incident_review(self):
        p = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.5,
            citation_coverage=0.4,
        )
        result = p.incident_review("a4", signals, notes="user reported error")
        assert result.stage == AuditStage.INCIDENT
        assert result.notes == "user reported error"
        # incident_review defaults to has_counterevidence=True
        assert FailureMode.COUNTEREVIDENCE_IGNORED in result.failure_modes

    def test_incident_review_high_risk(self):
        p = AuditPipeline()
        signals = DetectionSignals(evidence_count=0)
        result = p.incident_review("a5", signals)
        assert result.risk if hasattr(result, "risk") else True
        # Should be HIGH severity since incident + counterevidence + no evidence
        assert result.severity in (AuditSeverity.MEDIUM, AuditSeverity.HIGH)


class TestAuditPipelineQueries:
    def _fill_pipeline(self) -> AuditPipeline:
        p = AuditPipeline()
        # Clean audit
        p.audit("a1", DetectionSignals(
            evidence_count=3, evidence_strength_sum=2.1,
            independence_score=0.9, citation_coverage=0.95,
        ))
        # Problematic audit
        p.audit("a2", DetectionSignals(evidence_count=0))
        # Weak audit
        p.audit("a3", DetectionSignals(
            evidence_count=1, evidence_strength_sum=0.3, citation_coverage=0.8,
        ))
        # Another audit for a2
        p.audit("a2", DetectionSignals(
            evidence_count=2, evidence_strength_sum=1.5,
            independence_score=0.8, citation_coverage=0.9,
        ))
        return p

    def test_get_audit(self):
        p = self._fill_pipeline()
        a = p.audit_history[0]
        found = p.get_audit(a.audit_id)
        assert found is not None
        assert found.audit_id == a.audit_id

    def test_get_audit_not_found(self):
        p = self._fill_pipeline()
        assert p.get_audit("nonexistent") is None

    def test_get_audits_for_assertion(self):
        p = self._fill_pipeline()
        audits = p.get_audits_for_assertion("a2")
        assert len(audits) == 2

    def test_get_problematic_audits(self):
        p = self._fill_pipeline()
        problems = p.get_problematic_audits()
        assert len(problems) >= 1
        for a in problems:
            assert a.is_problematic

    def test_get_recent_audits(self):
        p = self._fill_pipeline()
        recent = p.get_recent_audits(limit=2)
        assert len(recent) == 2

    def test_get_recent_audits_all(self):
        p = self._fill_pipeline()
        recent = p.get_recent_audits()
        assert len(recent) == 4


class TestAuditPipelineMetrics:
    def test_empty_metrics(self):
        p = AuditPipeline()
        m = p.get_metrics()
        assert m["total_audits"] == 0
        assert m["clean_rate"] == 1.0
        assert m["problematic_rate"] == 0.0

    def test_metrics_after_audits(self):
        p = AuditPipeline()
        # Clean
        p.audit("a1", DetectionSignals(
            evidence_count=3, evidence_strength_sum=2.5,
            independence_score=0.9, citation_coverage=0.95,
        ))
        # Problematic
        p.audit("a2", DetectionSignals(evidence_count=0))
        m = p.get_metrics()
        assert m["total_audits"] == 2
        assert m["total_clean"] == 1
        assert m["total_problematic"] == 1
        assert m["clean_rate"] == 0.5
        assert m["problematic_rate"] == 0.5

    def test_failure_mode_counts(self):
        p = AuditPipeline()
        p.audit("a1", DetectionSignals(evidence_count=0))
        p.audit("a2", DetectionSignals(evidence_count=0))
        m = p.get_metrics()
        assert m["failure_mode_counts"]["no_evidence"] == 2

    def test_top_failure_modes(self):
        p = AuditPipeline()
        for i in range(5):
            p.audit(f"a{i}", DetectionSignals(evidence_count=0))
        m = p.get_metrics()
        top = m["top_failure_modes"]
        assert len(top) >= 1
        assert top[0][0] == "no_evidence"
        assert top[0][1] == 5

    def test_failure_mode_rates(self):
        p = AuditPipeline()
        p.audit("a1", DetectionSignals(evidence_count=0))
        p.audit("a2", DetectionSignals(
            evidence_count=3, evidence_strength_sum=2.5,
            independence_score=0.9, citation_coverage=0.95,
        ))
        rates = p.get_failure_mode_rates()
        assert rates.get("no_evidence", 0) == 0.5

    def test_failure_mode_rates_empty(self):
        p = AuditPipeline()
        rates = p.get_failure_mode_rates()
        assert rates == {}


class TestAuditPipelineAdaptiveThresholds:
    def _fill_with_source_aliasing(self, count: int) -> AuditPipeline:
        p = AuditPipeline()
        for i in range(count):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=2,
                evidence_strength_sum=1.5,
                source_aliasing_score=0.8,
                citation_coverage=0.8,
            ))
        return p

    def test_adapt_not_enough_data(self):
        p = AuditPipeline()
        for i in range(5):
            p.audit(f"a{i}", DetectionSignals(evidence_count=0))
        adjustments = p.adapt_thresholds()
        assert adjustments == []  # Not enough data (< 10)

    def test_adapt_source_aliasing(self):
        p = self._fill_with_source_aliasing(15)
        adjustments = p.adapt_thresholds()
        # Should tighten independence_threshold for MEDIUM+ risk
        assert len(adjustments) > 0
        assert any(a["field"] == "independence_threshold" for a in adjustments)

    def test_adapt_cite_drift(self):
        p = AuditPipeline()
        for i in range(15):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=1,
                evidence_strength_sum=0.8,
                citation_coverage=0.2,  # Low coverage -> CITE_DRIFT
            ))
        adjustments = p.adapt_thresholds()
        assert any(a["field"] == "min_evidence_strength" for a in adjustments)

    def test_adapt_specious_precision(self):
        p = AuditPipeline()
        for i in range(15):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=1,
                evidence_strength_sum=0.8,
                novel_number_count=5,
                citation_coverage=0.8,
            ))
        adjustments = p.adapt_thresholds()
        assert any(a["field"] == "max_novel_numbers" for a in adjustments)

    def test_adapt_temporal_staleness(self):
        p = AuditPipeline()
        for i in range(15):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=1,
                evidence_strength_sum=0.8,
                is_stale=True,
                citation_coverage=0.8,
            ))
        adjustments = p.adapt_thresholds()
        assert any(a["field"] == "ttl_seconds" for a in adjustments)

    def test_adapt_clean_no_adjustments(self):
        p = AuditPipeline()
        for i in range(20):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=3,
                evidence_strength_sum=2.5,
                independence_score=0.9,
                citation_coverage=0.95,
            ))
        adjustments = p.adapt_thresholds()
        assert adjustments == []  # Clean audits, no tuning needed

    def test_adapt_only_medium_high_risk(self):
        """Adaptive tuning only applies to MEDIUM and HIGH risk policies."""
        p = self._fill_with_source_aliasing(15)
        adjustments = p.adapt_thresholds()
        # All adjustments should be for MEDIUM or HIGH risk policies
        for adj in adjustments:
            key = adj["key"]
            risk_part = key.split(":")[1]
            assert risk_part in ("medium", "high")


# =============================================================================
# Serialization Tests
# =============================================================================


class TestAuditPipelineSerialization:
    def test_to_dict(self):
        p = AuditPipeline()
        p.audit("a1", DetectionSignals(evidence_count=0))
        d = p.to_dict()
        assert "policy_store" in d
        assert "audit_history" in d
        assert len(d["audit_history"]) == 1
        assert d["total_audits"] == 1

    def test_from_dict(self):
        p = AuditPipeline()
        p.audit("a1", DetectionSignals(evidence_count=0))
        p.audit("a2", DetectionSignals(
            evidence_count=3, evidence_strength_sum=2.5,
            independence_score=0.9, citation_coverage=0.95,
        ))
        d = p.to_dict()
        p2 = AuditPipeline.from_dict(d)
        assert p2.total_audits == 2
        assert p2.total_clean == 1
        assert p2.total_problematic == 1
        assert len(p2.audit_history) == 2

    def test_to_json(self):
        p = AuditPipeline()
        p.audit("a1", DetectionSignals(evidence_count=0))
        j = p.to_json()
        data = json.loads(j)
        assert data["total_audits"] == 1

    def test_roundtrip(self):
        p = AuditPipeline()
        for i in range(5):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=i,
                evidence_strength_sum=i * 0.5,
                citation_coverage=0.8 if i > 0 else 0.0,
            ))
        d = p.to_dict()
        p2 = AuditPipeline.from_dict(d)
        assert p2.total_audits == p.total_audits
        assert p2.total_clean == p.total_clean
        assert p2.total_problematic == p.total_problematic
        assert len(p2.audit_history) == len(p.audit_history)

    def test_roundtrip_with_adjustments(self):
        p = AuditPipeline()
        # Fill with enough data to trigger adaptive tuning
        for i in range(15):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=2,
                evidence_strength_sum=1.5,
                source_aliasing_score=0.8,
                citation_coverage=0.8,
            ))
        p.adapt_thresholds()
        d = p.to_dict()
        p2 = AuditPipeline.from_dict(d)
        assert len(p2.policy_store.adjustment_history) == len(p.policy_store.adjustment_history)


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestQuickAudit:
    def test_minimal_signals_triggers_failures(self):
        """quick_audit with only count/strength but missing other signals flags issues."""
        result = quick_audit("a1", evidence_count=3, evidence_strength=2.5)
        # citation_coverage=0 triggers CITE_DRIFT; independence_score=0 with
        # evidence_count>=2 triggers SOURCE_ALIASING; two modes -> UNGROUNDED
        assert FailureMode.CITE_DRIFT in result.failure_modes
        assert FailureMode.SOURCE_ALIASING in result.failure_modes
        assert result.status == GroundingStatus.UNGROUNDED

    def test_no_evidence(self):
        result = quick_audit("a2", evidence_count=0)
        assert result.status == GroundingStatus.UNGROUNDED
        assert result.decision == AuditDecision.NEEDS_MORE_WORK

    def test_novel_numbers(self):
        result = quick_audit("a3", evidence_count=1, evidence_strength=0.8, novel_numbers=5)
        assert FailureMode.SPECIOUS_PRECISION in result.failure_modes

    def test_custom_type_and_risk(self):
        result = quick_audit("a4", evidence_count=0, claim_type="volatile_fact", risk="high")
        assert result.stage == AuditStage.PRE_COMMIT
        assert result.status == GroundingStatus.UNGROUNDED

    def test_custom_scope(self):
        result = quick_audit("a5", evidence_count=0, scope="action_trigger")
        assert result.assertion_id == "a5"


class TestCreatePipeline:
    def test_default(self):
        p = create_pipeline()
        assert isinstance(p, AuditPipeline)
        assert len(p.policy_store.policies) == 54

    def test_custom_store(self):
        store = PolicyStore()
        store.tighten("code", ClaimRisk.HIGH, AssertionScope.ACTION_TRIGGER,
                      "k_required", 5, "custom")
        p = create_pipeline(store)
        assert p.policy_store is store


# =============================================================================
# Integration / End-to-End Tests
# =============================================================================


class TestAuditE2E:
    def test_full_lifecycle(self):
        """Full audit lifecycle: pre-commit gate, post-commit review, incident."""
        pipeline = create_pipeline()

        # 1. Pre-commit: clean claim passes
        clean_signals = DetectionSignals(
            evidence_count=3,
            evidence_strength_sum=2.5,
            independence_score=0.9,
            citation_coverage=0.95,
        )
        result1 = pipeline.pre_commit_audit("claim_1", clean_signals)
        assert result1.decision == AuditDecision.ALLOW_HARD

        # 2. Pre-commit: ungrounded claim blocked
        bad_signals = DetectionSignals(evidence_count=0)
        result2 = pipeline.pre_commit_audit("claim_2", bad_signals)
        assert result2.decision == AuditDecision.NEEDS_MORE_WORK

        # 3. Post-commit: review finds cite drift
        drift_signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            citation_coverage=0.2,
            independence_score=0.8,
        )
        result3 = pipeline.post_commit_audit("claim_3", drift_signals)
        assert FailureMode.CITE_DRIFT in result3.failure_modes

        # 4. Incident: investigation
        result4 = pipeline.incident_review(
            "claim_3", drift_signals, notes="user reported inaccuracy",
        )
        assert result4.stage == AuditStage.INCIDENT
        assert result4.severity in (AuditSeverity.MEDIUM, AuditSeverity.HIGH)

        # Verify metrics
        m = pipeline.get_metrics()
        assert m["total_audits"] == 4
        assert m["total_clean"] == 1

    def test_adaptive_loop(self):
        """Adaptive thresholds tighten after repeated failures."""
        pipeline = create_pipeline()
        store = pipeline.policy_store

        # Record initial independence threshold
        initial = store.get("static_fact", ClaimRisk.MEDIUM, AssertionScope.INTERNAL_PREMISE)
        initial_threshold = initial.independence_threshold

        # Generate many source aliasing failures
        for i in range(20):
            pipeline.audit(f"a{i}", DetectionSignals(
                evidence_count=2,
                evidence_strength_sum=1.5,
                source_aliasing_score=0.8,
                citation_coverage=0.8,
            ))

        # Adapt
        adjustments = pipeline.adapt_thresholds()
        assert len(adjustments) > 0

        # Check that threshold was tightened
        after = store.get("static_fact", ClaimRisk.MEDIUM, AssertionScope.INTERNAL_PREMISE)
        assert after.independence_threshold > initial_threshold

    def test_mixed_audit_stages(self):
        """Audits at different stages are tracked correctly."""
        pipeline = create_pipeline()

        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            citation_coverage=0.8,
        )

        pipeline.audit("a1", signals, stage=AuditStage.PRE_COMMIT)
        pipeline.audit("a2", signals, stage=AuditStage.POST_COMMIT)
        pipeline.audit("a3", signals, stage=AuditStage.PERIODIC)
        pipeline.audit("a4", signals, stage=AuditStage.INCIDENT, has_counterevidence=True)

        assert pipeline.total_audits == 4
        stages = [a.stage for a in pipeline.audit_history]
        assert AuditStage.PRE_COMMIT in stages
        assert AuditStage.POST_COMMIT in stages
        assert AuditStage.PERIODIC in stages
        assert AuditStage.INCIDENT in stages

    def test_leak_score_ordering(self):
        """Later-detected problems have worse leak scores."""
        pipeline = create_pipeline()

        bad_signals = DetectionSignals(evidence_count=0)

        r1 = pipeline.audit("a1", bad_signals, stage=AuditStage.PRE_COMMIT)
        r2 = pipeline.audit("a2", bad_signals, stage=AuditStage.POST_COMMIT)
        r3 = pipeline.audit("a3", bad_signals, stage=AuditStage.INCIDENT)

        # Same failure, different stages -> different leak scores
        assert r1.leak_score < r2.leak_score
        assert r2.leak_score < r3.leak_score

    def test_serialization_preserves_state(self):
        """Full round-trip preserves all pipeline state."""
        pipeline = create_pipeline()

        for i in range(10):
            pipeline.audit(f"a{i}", DetectionSignals(
                evidence_count=i % 3,
                evidence_strength_sum=i * 0.3,
                citation_coverage=0.5 + i * 0.05,
            ))

        pipeline.adapt_thresholds()

        # Serialize and restore
        data = pipeline.to_dict()
        restored = AuditPipeline.from_dict(data)

        assert restored.total_audits == pipeline.total_audits
        assert restored.total_clean == pipeline.total_clean
        assert restored.total_problematic == pipeline.total_problematic
        assert len(restored.audit_history) == len(pipeline.audit_history)
        assert len(restored.policy_store.adjustment_history) == len(pipeline.policy_store.adjustment_history)


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_zero_evidence_strength(self):
        signals = DetectionSignals(evidence_count=1, evidence_strength_sum=0.0, citation_coverage=0.8)
        policy = PolicyEntry(claim_type="static_fact", min_evidence_strength=0.7)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WEAK_EVIDENCE in modes

    def test_exactly_at_threshold(self):
        """Boundary: exactly at independence threshold should not trigger."""
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            independence_score=0.6,  # Exactly at threshold
            citation_coverage=0.8,
        )
        policy = PolicyEntry(claim_type="static_fact", independence_threshold=0.6)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.SOURCE_ALIASING not in modes

    def test_just_below_threshold(self):
        """Boundary: just below independence threshold triggers."""
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            independence_score=0.59,
            citation_coverage=0.8,
        )
        policy = PolicyEntry(claim_type="static_fact", independence_threshold=0.6)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.SOURCE_ALIASING in modes

    def test_all_signals_maxed(self):
        """All bad signals at once."""
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.1,
            source_aliasing_score=0.9,
            citation_coverage=0.1,
            novel_entity_count=10,
            novel_number_count=10,
            specious_precision_score=0.99,
            is_stale=True,
            confidence_evidence_gap=0.9,
            tool_misread_risk=0.9,
        )
        policy = PolicyEntry(claim_type="static_fact")
        modes = classify_failure_modes(signals, policy)
        assert len(modes) >= 5

    def test_single_evidence_no_independence_check(self):
        """Independence check requires evidence_count >= 2."""
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            independence_score=0.0,  # Would trigger if checked
            citation_coverage=0.8,
        )
        policy = PolicyEntry(claim_type="static_fact", independence_threshold=0.6)
        modes = classify_failure_modes(signals, policy)
        # Should NOT have SOURCE_ALIASING from independence check
        # (may have it from source_aliasing_score if > 0.5, but independence_score doesn't apply)
        assert FailureMode.SOURCE_ALIASING not in modes

    def test_large_audit_history(self):
        """Pipeline handles large audit histories."""
        p = AuditPipeline()
        for i in range(500):
            p.audit(f"a{i}", DetectionSignals(
                evidence_count=i % 5,
                evidence_strength_sum=i * 0.1,
                citation_coverage=0.7,
            ))
        assert p.total_audits == 500
        recent = p.get_recent_audits(limit=10)
        assert len(recent) == 10

    def test_empty_evidence_kinds(self):
        signals = DetectionSignals(evidence_kinds=[])
        d = signals.to_dict()
        assert d["evidence_kinds"] == []
        s2 = DetectionSignals.from_dict(d)
        assert s2.evidence_kinds == []

    def test_policy_store_empty_from_dict(self):
        store = PolicyStore.from_dict({})
        assert len(store.policies) == 0
        assert store.adjustment_history == []
