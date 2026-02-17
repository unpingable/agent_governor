# SPDX-License-Identifier: Apache-2.0
"""
Tests for Layer 3: Evidence Type Validation.

Gate claims by the KIND of evidence, not just quantity. MATH claims need
calculator output, CODE claims need test results, etc.

Covers:
- EvidenceType enum extensions (4 new values)
- EvidenceRef factory methods (4 new factories)
- PolicyEntry.required_evidence_kinds field
- WRONG_EVIDENCE_TYPE failure mode in audit pipeline
- QuorumPolicy.required_evidence_types field
- Quorum Gate 6 (evidence type enforcement)
- COLLECTING → STABILIZING transition gate
- Jurisdiction admissibility of new types
- Backward compatibility
"""

from datetime import datetime, timedelta

import pytest

from governor.epistemic import (
    EvidenceRef,
    EvidenceType,
)
from governor.audit import (
    AuditDecision,
    AuditPipeline,
    AssertionScope,
    ClaimRisk,
    DetectionSignals,
    FailureMode,
    GroundingStatus,
    PolicyEntry,
    PolicyStore,
    classify_failure_modes,
    determine_grounding_status,
)
from governor.quorum import (
    DEFAULT_POLICIES,
    ClaimType,
    QuorumManager,
    QuorumPolicy,
    QuorumStatus,
    VoteVerdict,
    create_quorum_manager,
)
from governor.dissent import EvidencePointer
from governor.jurisdictions import (
    EvidenceType as JEvidenceType,
    create_factual_jurisdiction,
    create_speculative_jurisdiction,
    create_adversarial_jurisdiction,
    create_forensic_jurisdiction,
    create_audit_jurisdiction,
    create_counterfactual_jurisdiction,
    create_narrative_jurisdiction,
    create_pedagogical_jurisdiction,
)


# =============================================================================
# TestEvidenceTypeEnum
# =============================================================================


class TestEvidenceTypeEnum:

    def test_calc_result_exists(self):
        assert EvidenceType.CALC_RESULT.value == "calc_result"

    def test_test_result_exists(self):
        assert EvidenceType.TEST_RESULT.value == "test_result"

    def test_web_source_exists(self):
        assert EvidenceType.WEB_SOURCE.value == "web_source"

    def test_live_retrieval_exists(self):
        assert EvidenceType.LIVE_RETRIEVAL.value == "live_retrieval"

    def test_total_count_is_15(self):
        """11 original + 4 new = 15."""
        assert len(EvidenceType) == 15

    def test_new_types_are_string_enum(self):
        assert isinstance(EvidenceType.CALC_RESULT, str)
        assert isinstance(EvidenceType.TEST_RESULT, str)
        assert isinstance(EvidenceType.WEB_SOURCE, str)
        assert isinstance(EvidenceType.LIVE_RETRIEVAL, str)

    def test_serialization_roundtrip(self):
        for et in [EvidenceType.CALC_RESULT, EvidenceType.TEST_RESULT,
                    EvidenceType.WEB_SOURCE, EvidenceType.LIVE_RETRIEVAL]:
            assert EvidenceType(et.value) == et


# =============================================================================
# TestEvidenceRefFactories
# =============================================================================


class TestEvidenceRefFactories:

    def test_from_calc_result(self):
        ref = EvidenceRef.from_calc_result("trace-123", "math_proof")
        assert ref.ref_type == EvidenceType.CALC_RESULT
        assert ref.locator == "trace-123"
        assert ref.scope == "math_proof"
        assert ref.ref_id.startswith("ev_")
        assert ref.retrieved_at is not None

    def test_from_test_result(self):
        ref = EvidenceRef.from_test_result("pytest-run-456", "test_suite")
        assert ref.ref_type == EvidenceType.TEST_RESULT
        assert ref.locator == "pytest-run-456"
        assert ref.scope == "test_suite"

    def test_from_web_source(self):
        ref = EvidenceRef.from_web_source("https://example.com/doc", "reference")
        assert ref.ref_type == EvidenceType.WEB_SOURCE
        assert ref.locator == "https://example.com/doc"
        assert ref.scope == "reference"

    def test_from_live_retrieval(self):
        ref = EvidenceRef.from_live_retrieval("api://data/endpoint", "live_data")
        assert ref.ref_type == EvidenceType.LIVE_RETRIEVAL
        assert ref.locator == "api://data/endpoint"
        assert ref.scope == "live_data"

    def test_unique_ref_ids(self):
        refs = [
            EvidenceRef.from_calc_result("t1", "s1"),
            EvidenceRef.from_calc_result("t1", "s1"),
            EvidenceRef.from_test_result("t2", "s2"),
            EvidenceRef.from_web_source("u1", "s3"),
            EvidenceRef.from_live_retrieval("l1", "s4"),
        ]
        ids = [r.ref_id for r in refs]
        assert len(set(ids)) == len(ids)

    def test_factory_timestamps_are_recent(self):
        before = datetime.now()
        ref = EvidenceRef.from_calc_result("t1", "s1")
        after = datetime.now()
        assert before <= ref.retrieved_at <= after

    def test_serialization_roundtrip(self):
        ref = EvidenceRef.from_test_result("trace-789", "compilation")
        d = ref.to_dict()
        assert d["ref_type"] == "test_result"
        ref2 = EvidenceRef.from_dict(d)
        assert ref2.ref_type == EvidenceType.TEST_RESULT
        assert ref2.locator == "trace-789"

    def test_content_hash(self):
        ref = EvidenceRef.from_web_source("https://example.com", "ref")
        h = ref.compute_content_hash()
        assert len(h) == 16
        # Same inputs → same hash
        ref2 = EvidenceRef.from_web_source("https://example.com", "ref")
        assert ref2.compute_content_hash() == h


# =============================================================================
# TestPolicyEntryRequirements
# =============================================================================


class TestPolicyEntryRequirements:

    def test_default_none(self):
        p = PolicyEntry(claim_type="test")
        assert p.required_evidence_kinds is None

    def test_explicit_set(self):
        p = PolicyEntry(claim_type="math", required_evidence_kinds={"calc_result", "cryptographic_proof"})
        assert "calc_result" in p.required_evidence_kinds
        assert "cryptographic_proof" in p.required_evidence_kinds

    def test_serialization_with_kinds(self):
        p = PolicyEntry(claim_type="code", required_evidence_kinds={"test_result", "receipt"})
        d = p.to_dict()
        assert d["required_evidence_kinds"] is not None
        assert set(d["required_evidence_kinds"]) == {"test_result", "receipt"}

    def test_serialization_none_kinds(self):
        p = PolicyEntry(claim_type="judgment", required_evidence_kinds=None)
        d = p.to_dict()
        assert d["required_evidence_kinds"] is None

    def test_from_dict_with_kinds(self):
        d = {"claim_type": "math", "required_evidence_kinds": ["calc_result", "cryptographic_proof"]}
        p = PolicyEntry.from_dict(d)
        assert p.required_evidence_kinds == {"calc_result", "cryptographic_proof"}

    def test_from_dict_none_kinds(self):
        d = {"claim_type": "judgment"}
        p = PolicyEntry.from_dict(d)
        assert p.required_evidence_kinds is None

    def test_default_static_fact_policy(self):
        store = PolicyStore()
        p = store.get("static_fact")
        assert p.required_evidence_kinds == {"web_source", "document", "url"}

    def test_default_volatile_fact_policy(self):
        store = PolicyStore()
        p = store.get("volatile_fact")
        assert p.required_evidence_kinds == {"live_retrieval", "web_source"}

    def test_default_code_policy(self):
        store = PolicyStore()
        p = store.get("code")
        assert p.required_evidence_kinds == {"test_result", "receipt"}

    def test_default_math_policy(self):
        store = PolicyStore()
        p = store.get("math")
        assert p.required_evidence_kinds == {"calc_result", "cryptographic_proof"}

    def test_default_procedure_policy(self):
        store = PolicyStore()
        p = store.get("procedure")
        assert p.required_evidence_kinds == {"tool_trace", "test_result", "receipt"}

    def test_default_judgment_policy(self):
        store = PolicyStore()
        p = store.get("judgment")
        assert p.required_evidence_kinds is None

    def test_roundtrip_serialization(self):
        store = PolicyStore()
        d = store.to_dict()
        store2 = PolicyStore.from_dict(d)
        for ct in ["static_fact", "volatile_fact", "code", "math", "procedure", "judgment"]:
            p1 = store.get(ct)
            p2 = store2.get(ct)
            assert p1.required_evidence_kinds == p2.required_evidence_kinds


# =============================================================================
# TestWrongEvidenceTypeFailureMode
# =============================================================================


class TestWrongEvidenceTypeFailureMode:

    def test_enum_exists(self):
        assert FailureMode.WRONG_EVIDENCE_TYPE.value == "wrong_evidence_type"

    def test_classify_with_correct_type(self):
        """Correct evidence type → no WRONG_EVIDENCE_TYPE."""
        policy = PolicyEntry(claim_type="math", required_evidence_kinds={"calc_result"})
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=1.0,
            evidence_kinds=["calc_result"],
            citation_coverage=0.9,
        )
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WRONG_EVIDENCE_TYPE not in modes

    def test_classify_with_wrong_type(self):
        """Wrong evidence type → WRONG_EVIDENCE_TYPE detected."""
        policy = PolicyEntry(claim_type="math", required_evidence_kinds={"calc_result", "cryptographic_proof"})
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            evidence_kinds=["tool_trace", "human_input"],
            citation_coverage=0.9,
        )
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WRONG_EVIDENCE_TYPE in modes

    def test_classify_no_requirement(self):
        """None requirement → no WRONG_EVIDENCE_TYPE (any type accepted)."""
        policy = PolicyEntry(claim_type="judgment", required_evidence_kinds=None)
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=1.0,
            evidence_kinds=["human_input"],
            citation_coverage=0.9,
        )
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WRONG_EVIDENCE_TYPE not in modes

    def test_classify_any_match_suffices(self):
        """One matching type among many → no WRONG_EVIDENCE_TYPE."""
        policy = PolicyEntry(claim_type="code", required_evidence_kinds={"test_result", "receipt"})
        signals = DetectionSignals(
            evidence_count=3,
            evidence_strength_sum=2.0,
            evidence_kinds=["tool_trace", "human_input", "receipt"],
            citation_coverage=0.9,
        )
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WRONG_EVIDENCE_TYPE not in modes

    def test_classify_empty_evidence_kinds(self):
        """Evidence count > 0 but empty kinds list → WRONG_EVIDENCE_TYPE."""
        policy = PolicyEntry(claim_type="math", required_evidence_kinds={"calc_result"})
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=1.0,
            evidence_kinds=[],
            citation_coverage=0.9,
        )
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WRONG_EVIDENCE_TYPE in modes

    def test_no_evidence_skips_wrong_type_check(self):
        """No evidence → NO_EVIDENCE, not WRONG_EVIDENCE_TYPE."""
        policy = PolicyEntry(claim_type="math", required_evidence_kinds={"calc_result"})
        signals = DetectionSignals(evidence_count=0)
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.NO_EVIDENCE in modes
        assert FailureMode.WRONG_EVIDENCE_TYPE not in modes

    def test_severity_is_severe(self):
        """WRONG_EVIDENCE_TYPE is in the severe set → UNGROUNDED."""
        modes = [FailureMode.WRONG_EVIDENCE_TYPE]
        status = determine_grounding_status(modes)
        assert status == GroundingStatus.UNGROUNDED

    def test_audit_decision_is_block(self):
        """WRONG_EVIDENCE_TYPE → UNGROUNDED → BLOCK."""
        pipeline = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            evidence_kinds=["tool_trace"],
            citation_coverage=0.9,
        )
        result = pipeline.audit("a1", signals, claim_type="math")
        assert FailureMode.WRONG_EVIDENCE_TYPE in result.failure_modes
        assert result.status == GroundingStatus.UNGROUNDED
        assert result.decision == AuditDecision.BLOCK

    def test_pipeline_clean_with_correct_types(self):
        """Full pipeline with correct evidence types passes cleanly."""
        pipeline = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=2.0,
            evidence_kinds=["calc_result"],
            independence_score=0.8,
            citation_coverage=0.9,
        )
        result = pipeline.audit("a1", signals, claim_type="math")
        assert result.status == GroundingStatus.GROUNDED
        assert result.decision == AuditDecision.ALLOW_HARD

    def test_pipeline_code_with_test_result(self):
        """CODE claim with test_result evidence passes."""
        pipeline = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=1.0,
            evidence_kinds=["test_result"],
            citation_coverage=0.9,
        )
        result = pipeline.audit("a1", signals, claim_type="code")
        assert FailureMode.WRONG_EVIDENCE_TYPE not in result.failure_modes

    def test_pipeline_static_fact_with_document(self):
        """STATIC_FACT with document evidence passes evidence type check."""
        pipeline = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=2,
            evidence_strength_sum=1.5,
            evidence_kinds=["document"],
            independence_score=0.8,
            citation_coverage=0.9,
        )
        result = pipeline.audit("a1", signals, claim_type="static_fact")
        assert FailureMode.WRONG_EVIDENCE_TYPE not in result.failure_modes


# =============================================================================
# TestQuorumPolicyRequirements
# =============================================================================


class TestQuorumPolicyRequirements:

    def test_field_exists_none(self):
        from governor.ttl import VolatilityClass
        p = QuorumPolicy(
            claim_type=ClaimType.JUDGMENT,
            min_voters=2,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=10),
            volatility=VolatilityClass.STABLE,
        )
        assert p.required_evidence_types is None

    def test_field_exists_with_set(self):
        from governor.ttl import VolatilityClass
        p = QuorumPolicy(
            claim_type=ClaimType.MATH,
            min_voters=2,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=10),
            volatility=VolatilityClass.PERMANENT,
            required_evidence_types={"calc_result", "cryptographic_proof"},
        )
        assert "calc_result" in p.required_evidence_types

    def test_default_math_policy(self):
        p = DEFAULT_POLICIES[ClaimType.MATH]
        assert p.required_evidence_types == {"calc_result", "cryptographic_proof"}

    def test_default_code_policy(self):
        p = DEFAULT_POLICIES[ClaimType.CODE]
        assert p.required_evidence_types == {"test_result", "receipt"}

    def test_default_static_fact_policy(self):
        p = DEFAULT_POLICIES[ClaimType.STATIC_FACT]
        assert p.required_evidence_types == {"web_source", "document", "url"}

    def test_default_volatile_fact_policy(self):
        p = DEFAULT_POLICIES[ClaimType.VOLATILE_FACT]
        assert p.required_evidence_types == {"live_retrieval", "web_source"}

    def test_default_procedure_policy(self):
        p = DEFAULT_POLICIES[ClaimType.PROCEDURE]
        assert p.required_evidence_types == {"tool_trace", "test_result", "receipt"}

    def test_default_judgment_policy(self):
        p = DEFAULT_POLICIES[ClaimType.JUDGMENT]
        assert p.required_evidence_types is None

    def test_to_dict_includes_types(self):
        p = DEFAULT_POLICIES[ClaimType.MATH]
        d = p.to_dict()
        assert "required_evidence_types" in d
        assert set(d["required_evidence_types"]) == {"calc_result", "cryptographic_proof"}

    def test_to_dict_none_types(self):
        p = DEFAULT_POLICIES[ClaimType.JUDGMENT]
        d = p.to_dict()
        assert d["required_evidence_types"] is None


# =============================================================================
# TestQuorumGate6
# =============================================================================


class TestQuorumGate6:

    def _make_evidence(self, evidence_type: str) -> list[EvidencePointer]:
        return [EvidencePointer(description="auto", evidence_type=evidence_type)]

    def test_no_requirement_passthrough(self):
        """JUDGMENT has no evidence type requirement — always passes."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.JUDGMENT, created_at=now)
        # Cast 3 votes with random evidence (k=3 for JUDGMENT)
        ev = self._make_evidence("human_input")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "human:admin", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_matching_evidence_passes(self):
        """CODE quorum with test_result evidence enters STABILIZING."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = self._make_evidence("test_result")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_non_matching_evidence_blocks(self):
        """CODE quorum with human_input evidence stays COLLECTING."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = self._make_evidence("human_input")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.COLLECTING

    def test_no_evidence_blocks(self):
        """CODE quorum without any evidence stays COLLECTING."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.COLLECTING

    def test_multiple_votes_any_match(self):
        """One correct evidence type among multiple votes suffices."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        # First vote: wrong type
        ev_wrong = self._make_evidence("tool_trace")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_wrong)
        assert mgr.check_status("p1") == QuorumStatus.COLLECTING  # Need k=2
        # Second vote: correct type
        ev_right = self._make_evidence("calc_result")
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_right)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_approve_only_filter(self):
        """Only APPROVE votes' evidence counts for the evidence type gate."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        # REJECT vote with correct evidence
        ev = self._make_evidence("test_result")
        mgr.cast_vote("p1", "a1", VoteVerdict.REJECT, "no", timestamp=now, evidence=ev)
        # APPROVE vote without evidence
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.COLLECTING

    def test_can_proceed_gate6_blocks(self):
        """can_proceed fails if evidence type gate not met."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev_wrong = self._make_evidence("human_input")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_wrong)
        # Force to REACHED for can_proceed test
        qs = mgr.get_quorum("p1")
        qs.status = QuorumStatus.REACHED
        qs.reached_at = now
        can, reasons = mgr.can_proceed("p1", now=now)
        assert not can
        assert any("Evidence type gate" in r for r in reasons)

    def test_can_proceed_gate6_passes(self):
        """can_proceed passes with correct evidence types."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = self._make_evidence("test_result")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.update("p1", now=now + timedelta(seconds=15))
        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=15))
        assert can, f"Unexpected block: {reasons}"

    def test_math_calc_result(self):
        """MATH claim with calc_result passes."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        ev = self._make_evidence("calc_result")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_math_cryptographic_proof(self):
        """MATH claim with cryptographic_proof passes."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        ev = self._make_evidence("cryptographic_proof")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_static_fact_web_source(self):
        """STATIC_FACT with web_source passes."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.STATIC_FACT, created_at=now)
        ev = self._make_evidence("web_source")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_volatile_fact_live_retrieval(self):
        """VOLATILE_FACT with live_retrieval passes."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.VOLATILE_FACT, created_at=now)
        ev = self._make_evidence("live_retrieval")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_procedure_tool_trace(self):
        """PROCEDURE with tool_trace passes."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.PROCEDURE, created_at=now)
        ev = self._make_evidence("tool_trace")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_combined_gates(self):
        """Evidence type gate works alongside other gates (dissent, independence)."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = self._make_evidence("test_result")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.update("p1", now=now + timedelta(seconds=15))
        assert mgr.check_status("p1") == QuorumStatus.REACHED
        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=15))
        assert can


# =============================================================================
# TestStabilizingTransitionGate
# =============================================================================


class TestStabilizingTransitionGate:

    def _make_evidence(self, evidence_type: str) -> list[EvidencePointer]:
        return [EvidencePointer(description="auto", evidence_type=evidence_type)]

    def test_blocked_without_correct_evidence(self):
        """COLLECTING stays COLLECTING without correct evidence type."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        ev = self._make_evidence("human_input")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        # Threshold met (k=2, ratio=1.0) but evidence type wrong
        qs = mgr.get_quorum("p1")
        assert qs.threshold_met
        assert qs.status == QuorumStatus.COLLECTING

    def test_passes_with_correct_evidence(self):
        """COLLECTING → STABILIZING with correct evidence type."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        ev = self._make_evidence("calc_result")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_unblocked_by_later_correct_vote(self):
        """Initially blocked, then unblocked by a vote with correct evidence."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        ev_wrong = self._make_evidence("human_input")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_wrong)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_wrong)
        assert mgr.check_status("p1") == QuorumStatus.COLLECTING

        # Third vote with correct evidence
        ev_right = self._make_evidence("calc_result")
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_right)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_full_vote_to_reached(self):
        """Full flow: vote with correct evidence → STABILIZING → REACHED."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = self._make_evidence("test_result")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        later = now + timedelta(seconds=15)
        mgr.update("p1", now=later)
        assert mgr.check_status("p1") == QuorumStatus.REACHED

    def test_full_vote_to_can_proceed(self):
        """Full flow: correct evidence → REACHED → can_proceed."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = self._make_evidence("receipt")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        later = now + timedelta(seconds=15)
        mgr.update("p1", now=later)
        can, reasons = mgr.can_proceed("p1", now=later)
        assert can, f"Unexpected block: {reasons}"

    def test_helper_method_directly(self):
        """Test _check_evidence_types helper directly."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.MATH, created_at=now)

        # No votes → passes (empty intersection check)
        passes, reason = mgr._check_evidence_types(qs)
        assert not passes
        assert "Evidence type gate" in reason

        # Add vote with wrong evidence
        ev_wrong = self._make_evidence("tool_trace")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_wrong)
        passes, reason = mgr._check_evidence_types(qs)
        assert not passes

        # Add vote with correct evidence
        ev_right = self._make_evidence("calc_result")
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev_right)
        passes, reason = mgr._check_evidence_types(qs)
        assert passes

    def test_judgment_no_gate(self):
        """JUDGMENT has no evidence type requirement."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.JUDGMENT, created_at=now)
        passes, reason = mgr._check_evidence_types(qs)
        assert passes
        assert reason == ""

    def test_check_evidence_types_reason_format(self):
        """Verify reason message format."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = self._make_evidence("human_input")
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        passes, reason = mgr._check_evidence_types(qs)
        assert not passes
        assert "receipt" in reason or "test_result" in reason
        assert "human_input" in reason

    def test_no_evidence_reason_says_none(self):
        """No evidence at all → reason says 'none'."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        passes, reason = mgr._check_evidence_types(qs)
        assert not passes
        assert "none" in reason


# =============================================================================
# TestJurisdictionAdmissibility
# =============================================================================


class TestJurisdictionAdmissibility:

    def test_factual_admits_all_new_types(self):
        j = create_factual_jurisdiction()
        assert j.admits(JEvidenceType.CALC_RESULT)
        assert j.admits(JEvidenceType.TEST_RESULT)
        assert j.admits(JEvidenceType.WEB_SOURCE)
        assert j.admits(JEvidenceType.LIVE_RETRIEVAL)

    def test_speculative_admits_web_source(self):
        j = create_speculative_jurisdiction()
        assert j.admits(JEvidenceType.WEB_SOURCE)
        assert not j.admits(JEvidenceType.CALC_RESULT)

    def test_adversarial_admits_subset(self):
        j = create_adversarial_jurisdiction()
        assert j.admits(JEvidenceType.WEB_SOURCE)
        assert j.admits(JEvidenceType.CALC_RESULT)
        assert j.admits(JEvidenceType.TEST_RESULT)
        assert not j.admits(JEvidenceType.LIVE_RETRIEVAL)

    def test_forensic_admits_web_and_live(self):
        j = create_forensic_jurisdiction()
        assert j.admits(JEvidenceType.WEB_SOURCE)
        assert j.admits(JEvidenceType.LIVE_RETRIEVAL)
        assert not j.admits(JEvidenceType.CALC_RESULT)

    def test_audit_admits_all_new_types(self):
        j = create_audit_jurisdiction()
        assert j.admits(JEvidenceType.CALC_RESULT)
        assert j.admits(JEvidenceType.TEST_RESULT)
        assert j.admits(JEvidenceType.WEB_SOURCE)
        assert j.admits(JEvidenceType.LIVE_RETRIEVAL)

    def test_narrative_no_new_types(self):
        j = create_narrative_jurisdiction()
        assert not j.admits(JEvidenceType.CALC_RESULT)
        assert not j.admits(JEvidenceType.TEST_RESULT)
        assert not j.admits(JEvidenceType.WEB_SOURCE)
        assert not j.admits(JEvidenceType.LIVE_RETRIEVAL)

    def test_counterfactual_no_new_types(self):
        j = create_counterfactual_jurisdiction()
        assert not j.admits(JEvidenceType.CALC_RESULT)
        assert not j.admits(JEvidenceType.WEB_SOURCE)

    def test_pedagogical_no_new_types(self):
        j = create_pedagogical_jurisdiction()
        assert not j.admits(JEvidenceType.CALC_RESULT)
        assert not j.admits(JEvidenceType.WEB_SOURCE)


# =============================================================================
# TestBackwardCompatibility
# =============================================================================


class TestBackwardCompatibility:

    def test_existing_evidence_types_unchanged(self):
        """Original 11 evidence types still exist."""
        originals = [
            EvidenceType.TOOL_TRACE, EvidenceType.URL, EvidenceType.DOCUMENT,
            EvidenceType.HUMAN_INPUT, EvidenceType.RECEIPT,
            EvidenceType.SENSOR_DATA, EvidenceType.CRYPTOGRAPHIC_PROOF,
            EvidenceType.SUBJECTIVE_REPORT, EvidenceType.NARRATIVE_CONSISTENCY,
            EvidenceType.PEDAGOGICAL_FRAME, EvidenceType.CROSS_SOURCE,
        ]
        assert len(originals) == 11

    def test_none_defaults_work(self):
        """PolicyEntry with no required_evidence_kinds → no failure mode."""
        policy = PolicyEntry(claim_type="custom")
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=1.0,
            evidence_kinds=["tool_trace"],
            citation_coverage=0.9,
        )
        modes = classify_failure_modes(signals, policy)
        assert FailureMode.WRONG_EVIDENCE_TYPE not in modes

    def test_quorum_none_defaults_work(self):
        """QuorumPolicy with no required_evidence_types → no gate."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.JUDGMENT, created_at=now)
        ev = [EvidencePointer(description="auto", evidence_type="human_input")]
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.cast_vote("p1", "human:admin", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_existing_factory_methods_still_work(self):
        """Original factory methods produce correct types."""
        assert EvidenceRef.from_tool_trace("t", "s").ref_type == EvidenceType.TOOL_TRACE
        assert EvidenceRef.from_url("u", "s").ref_type == EvidenceType.URL
        assert EvidenceRef.from_receipt("r", "s").ref_type == EvidenceType.RECEIPT
        assert EvidenceRef.from_human("h", "s").ref_type == EvidenceType.HUMAN_INPUT

    def test_existing_behavior_preserved(self):
        """Audit pipeline still works for judgment claims (no type requirement)."""
        pipeline = AuditPipeline()
        signals = DetectionSignals(
            evidence_count=1,
            evidence_strength_sum=0.8,
            evidence_kinds=["human_input"],
            citation_coverage=0.9,
        )
        result = pipeline.audit("a1", signals, claim_type="judgment")
        assert FailureMode.WRONG_EVIDENCE_TYPE not in result.failure_modes
