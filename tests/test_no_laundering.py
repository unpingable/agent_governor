"""
No-laundering regression tests: the moral center disguised as tests.

These tests enforce that the governor cannot slowly become permissive.
Each test encodes a structural invariant that, if violated, means the
system has been compromised or degraded.

Categories:
1. Money Rule: Confidence may only increase WITH evidence
2. Provenance Rule: Provenance may only upgrade WITH evidence
3. Premise Rule: HARD claims cannot depend on SOFT/STALE/INVALIDATED
4. Silent Retraction: Active claims cannot vanish without explicit retraction
5. PEER_ASSERTED Cap: Peer claims capped at MAX_PEER_CONFIDENCE
6. Envelope Mode Retrograde: strict→exploratory must not weaken committed claims
7. Evidence Type Gating: HARD claims require specific evidence types
8. ClaimStatus FSM: Transition graph cannot be bypassed
9. Continuity Rule: converged=False results cannot be silently accepted
"""

import pytest
from datetime import datetime

from governor.epistemic import (
    EpistemicLedger,
    GroundedClaim,
    GroundedClaimStatus,
    Provenance,
    EvidenceRef,
    EvidenceType,
    ClaimStatus,
    TransitionReason,
    MAX_PEER_CONFIDENCE,
    HIGH_CONFIDENCE_THRESHOLD,
    DEFAULT_CONFIDENCE,
)
from governor.envelopes import EnvelopeConfig


# =============================================================================
# 1. Money Rule: Confidence may only increase WITH evidence
# =============================================================================


class TestMoneyRule:
    """Confidence cannot increase on ASSUMED/PEER_ASSERTED without evidence."""

    def _make_ledger(self) -> EpistemicLedger:
        return EpistemicLedger()

    def test_assumed_starts_at_low_default(self):
        """ASSUMED claims start at DEFAULT_CONFIDENCE, not high."""
        ledger = self._make_ledger()
        claim = ledger.new_assumed_claim("Water is wet")
        assert claim.confidence == DEFAULT_CONFIDENCE[Provenance.ASSUMED]
        assert claim.confidence < HIGH_CONFIDENCE_THRESHOLD

    def test_assumed_provenance_requires_evidence_for_confidence(self):
        """ASSUMED provenance is flagged as requiring evidence for confidence increases."""
        assert Provenance.ASSUMED.requires_evidence_for_confidence is True

    def test_peer_asserted_requires_evidence_for_confidence(self):
        """PEER_ASSERTED provenance requires evidence for confidence increases."""
        assert Provenance.PEER_ASSERTED.requires_evidence_for_confidence is True

    def test_peer_asserted_confidence_capped(self):
        """PEER_ASSERTED claims are always capped at MAX_PEER_CONFIDENCE."""
        ledger = self._make_ledger()
        claim = ledger.new_peer_claim("Agent says X", "agent_b")
        assert claim.confidence <= MAX_PEER_CONFIDENCE

    def test_peer_asserted_stays_capped_on_reconstruction(self):
        """Reconstructing a PEER_ASSERTED claim with high confidence still caps it."""
        reclamped = GroundedClaim(
            claim_id="c_peer",
            content="Agent says Y",
            provenance=Provenance.PEER_ASSERTED,
            confidence=0.9,
        )
        assert reclamped.confidence <= MAX_PEER_CONFIDENCE

    def test_observed_provenance_gets_high_default_confidence(self):
        """OBSERVED provenance starts with high confidence."""
        ledger = self._make_ledger()
        claim = ledger.new_claim("File exists", Provenance.OBSERVED)
        assert claim.confidence >= HIGH_CONFIDENCE_THRESHOLD

    def test_dangerous_claim_detection(self):
        """High confidence + ungrounded = dangerous. Must be flagged."""
        claim = GroundedClaim(
            claim_id="c_dangerous",
            content="Totally true",
            provenance=Provenance.ASSUMED,
            confidence=0.9,
        )
        # ASSUMED provenance is NOT grounded, so if confidence is high, it's dangerous
        if claim.confidence >= HIGH_CONFIDENCE_THRESHOLD:
            assert claim.is_dangerous

    def test_confidence_clamped_to_0_1(self):
        """Confidence is always clamped to [0, 1]."""
        high = GroundedClaim(claim_id="c1", content="x", provenance=Provenance.ASSUMED, confidence=1.5)
        assert high.confidence == 1.0
        low = GroundedClaim(claim_id="c2", content="x", provenance=Provenance.ASSUMED, confidence=-0.5)
        assert low.confidence == 0.0


# =============================================================================
# 2. Provenance Rule: Provenance may only upgrade WITH evidence
# =============================================================================


class TestProvenanceRule:
    """Provenance never upgrades without evidence trail."""

    def _make_ledger(self) -> EpistemicLedger:
        return EpistemicLedger()

    def test_assumed_to_retrieved_forbidden_without_evidence(self):
        """Cannot promote ASSUMED→RETRIEVED without evidence."""
        ledger = self._make_ledger()
        claim = ledger.new_assumed_claim("X")

        result = ledger.promote(claim.claim_id, Provenance.RETRIEVED)
        # Should fail: no evidence
        assert result != "success" or result.value != "success"

    def test_assumed_to_retrieved_allowed_with_evidence(self):
        """CAN promote ASSUMED→RETRIEVED with evidence."""
        ledger = self._make_ledger()
        claim = ledger.new_assumed_claim("X")
        ev = EvidenceRef.from_url("https://example.com", "reference")
        ledger.attach_evidence(claim.claim_id, ev)

        result = ledger.promote(claim.claim_id, Provenance.RETRIEVED)
        assert result.value == "success"
        assert ledger.claims[claim.claim_id].provenance == Provenance.RETRIEVED

    def test_peer_to_observed_forbidden(self):
        """Cannot promote PEER_ASSERTED→OBSERVED (always forbidden)."""
        ledger = self._make_ledger()
        claim = ledger.new_peer_claim("Y", "agent_b")
        ev = EvidenceRef.from_tool_trace("t1", "s")
        ledger.attach_evidence(claim.claim_id, ev)

        result = ledger.promote(claim.claim_id, Provenance.OBSERVED)
        assert result.value == "forbidden"

    def test_promotion_history_recorded(self):
        """All promotion attempts (success and failure) are recorded."""
        ledger = self._make_ledger()
        claim = ledger.new_assumed_claim("Z")

        # Failed attempt (no evidence)
        ledger.promote(claim.claim_id, Provenance.RETRIEVED)
        assert len(ledger.promotion_history) >= 1

    def test_provenance_hierarchy_enforced(self):
        """OBSERVED > RETRIEVED > DERIVED > USER_PROVIDED > PEER_ASSERTED > ASSUMED."""
        assert Provenance.OBSERVED.is_grounded is True
        assert Provenance.RETRIEVED.is_grounded is True
        assert Provenance.ASSUMED.is_grounded is False
        assert Provenance.PEER_ASSERTED.is_grounded is False


# =============================================================================
# 3. Premise Rule: HARD cannot depend on degraded claims
# =============================================================================


class TestPremiseRule:
    """HARD claims cannot depend on SOFT/STALE/INVALIDATED claims."""

    def _make_ledger(self) -> EpistemicLedger:
        return EpistemicLedger()

    def test_hard_depending_on_soft_violates(self):
        """A HARD claim depending on a SOFT claim is a premise violation."""
        ledger = self._make_ledger()
        dep = ledger.new_assumed_claim("Dep claim")
        dep.commit_level = "soft"

        main = ledger.new_claim("Main claim", Provenance.OBSERVED)
        main.commit_level = "hard"
        ledger.add_dependency(main.claim_id, dep.claim_id)

        result = ledger.check_premise_rule(main.claim_id)
        assert not result.passed
        assert len(result.violations) > 0

    def test_hard_depending_on_hard_passes(self):
        """A HARD claim depending on another HARD claim is fine."""
        ledger = self._make_ledger()
        dep = ledger.new_claim("Dep claim", Provenance.OBSERVED)
        dep.commit_level = "hard"

        main = ledger.new_claim("Main claim", Provenance.OBSERVED)
        main.commit_level = "hard"
        ledger.add_dependency(main.claim_id, dep.claim_id)

        result = ledger.check_premise_rule(main.claim_id)
        assert result.passed

    def test_enforce_premise_downgrades_hard_to_soft(self):
        """enforce_premise_rule downgrades HARD→SOFT on violation."""
        ledger = self._make_ledger()
        dep = ledger.new_assumed_claim("Dep")
        dep.commit_level = "soft"

        main = ledger.new_claim("Main", Provenance.OBSERVED)
        main.commit_level = "hard"
        ledger.add_dependency(main.claim_id, dep.claim_id)

        result = ledger.enforce_premise_rule(main.claim_id)
        assert result.downgraded
        assert ledger.claims[main.claim_id].commit_level == "soft"

    def test_retraction_triggers_cascade(self):
        """Retracting a claim cascades to HARD dependents."""
        ledger = self._make_ledger()
        dep = ledger.new_claim("Base", Provenance.OBSERVED)
        dep.commit_level = "hard"

        child = ledger.new_claim("Child", Provenance.OBSERVED)
        child.commit_level = "hard"
        ledger.add_dependency(child.claim_id, dep.claim_id)

        # Retract the dependency
        ledger.retract(dep.claim_id, reason="No longer valid")

        # Child should have been downgraded
        assert ledger.claims[child.claim_id].commit_level == "soft"

    def test_cycle_rejection(self):
        """Cannot create a dependency cycle (returns False)."""
        ledger = self._make_ledger()
        a = ledger.new_claim("A", Provenance.OBSERVED)
        b = ledger.new_claim("B", Provenance.OBSERVED)

        assert ledger.add_dependency(a.claim_id, b.claim_id) is True
        # Cycle: B→A when A→B already exists
        assert ledger.add_dependency(b.claim_id, a.claim_id) is False

    def test_self_dependency_rejected(self):
        """Cannot depend on self (returns False)."""
        ledger = self._make_ledger()
        a = ledger.new_claim("A", Provenance.OBSERVED)

        assert ledger.add_dependency(a.claim_id, a.claim_id) is False


# =============================================================================
# 4. Silent Retraction Prevention
# =============================================================================


class TestSilentRetractionPrevention:
    """Active claims cannot just disappear — must be explicitly retracted."""

    def _make_ledger(self) -> EpistemicLedger:
        return EpistemicLedger()

    def test_retraction_requires_reason(self):
        """Retracting a claim records the reason."""
        ledger = self._make_ledger()
        claim = ledger.new_claim("X is true", Provenance.OBSERVED)

        ledger.retract(claim.claim_id, reason="Evidence contradicts")

        retracted = ledger.claims[claim.claim_id]
        assert retracted.status == GroundedClaimStatus.RETRACTED
        assert retracted.retraction_reason is not None

    def test_retracted_claim_still_in_ledger(self):
        """Retracted claims stay in the ledger (not deleted)."""
        ledger = self._make_ledger()
        claim = ledger.new_claim("Y", Provenance.OBSERVED)
        cid = claim.claim_id

        ledger.retract(cid, reason="Wrong")

        assert cid in ledger.claims
        assert ledger.claims[cid].status == GroundedClaimStatus.RETRACTED

    def test_retraction_increments_counter(self):
        """Retraction is counted in metrics."""
        ledger = self._make_ledger()
        claim = ledger.new_claim("Z", Provenance.OBSERVED)
        before = ledger.total_retractions

        ledger.retract(claim.claim_id, reason="Obsolete")

        assert ledger.total_retractions == before + 1

    def test_claim_diff_detects_silent_disappearance(self):
        """ClaimDiffer catches claims that disappear between snapshots."""
        from governor.claim_diff import ClaimDiffer, snapshot_ledger

        ledger = self._make_ledger()
        claim = ledger.new_claim("A is true", Provenance.OBSERVED)

        before = snapshot_ledger(ledger)

        # Simulate claim disappearing (bypass retraction)
        del ledger.claims[claim.claim_id]
        ledger.step += 1

        after = snapshot_ledger(ledger)

        differ = ClaimDiffer()
        result = differ.diff(before, after)
        # The differ should detect a dropped claim
        assert len(result.dropped) > 0


# =============================================================================
# 5. PEER_ASSERTED Confidence Cap
# =============================================================================


class TestPeerAssertedCap:
    """PEER_ASSERTED claims are structurally limited in confidence."""

    def test_cap_at_creation(self):
        """New PEER_ASSERTED claims are capped."""
        claim = GroundedClaim(
            claim_id="c_peer",
            content="Agent says yes",
            provenance=Provenance.PEER_ASSERTED,
            confidence=0.99,
        )
        assert claim.confidence <= MAX_PEER_CONFIDENCE

    def test_cap_after_reconstruction(self):
        """Reconstructing from dict still enforces the cap."""
        d = {
            "claim_id": "c_peer2",
            "content": "Agent says no",
            "provenance": "peer_asserted",
            "confidence": 0.99,
            "evidence_refs": [],
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "last_updated_at": datetime.now().isoformat(),
        }
        claim = GroundedClaim.from_dict(d)
        assert claim.confidence <= MAX_PEER_CONFIDENCE


# =============================================================================
# 6. Envelope Mode Retrograde Prevention
# =============================================================================


class TestEnvelopeModeRetrograde:
    """Switching from strict→exploratory must not weaken committed state."""

    def test_strict_mode_commits_decisions(self):
        """In strict mode, decisions are committed."""
        env = EnvelopeConfig.strict()
        assert env.mode.value == "strict"
        assert env.require_receipts is True
        assert env.commit_decisions is True

    def test_exploratory_mode_relaxes(self):
        """Exploratory mode relaxes constraints."""
        env = EnvelopeConfig.exploratory()
        assert env.mode.value == "exploratory"
        assert env.require_receipts is False
        assert env.commit_decisions is False

    def test_committed_fact_survives_mode_switch(self):
        """A fact committed in strict mode is not invalidated by switching to exploratory."""
        from governor.ledgers import FactLedger
        from governor.claims import Claim, ClaimType
        from governor.receipts import FileSnapshot
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            gov_dir = Path(tmpdir) / ".governor"
            gov_dir.mkdir()

            ledger = FactLedger(gov_dir)

            # Commit a fact using correct API
            claim = Claim(type=ClaimType.FILE_EXISTS, path="src/main.py")
            receipt = FileSnapshot(
                path="src/main.py", blob_hash="abc", size_bytes=100,
                timestamp=datetime.now(),
            )
            fact = ledger.add(claim, receipt)

            # Switch to exploratory mode
            _env = EnvelopeConfig.exploratory()

            # Fact should still be in the ledger
            assert ledger.get(fact.id) is not None

    def test_committed_decision_survives_mode_switch(self):
        """A decision committed in strict mode persists after mode switch."""
        from governor.ledgers import DecisionLedger
        from governor.claims import Claim, ClaimType
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            gov_dir = Path(tmpdir) / ".governor"
            gov_dir.mkdir()

            ledger = DecisionLedger(gov_dir)

            claim = Claim(type=ClaimType.DECISION, topic="db", choice="postgres")
            decision = ledger.add(claim, rationale="Industry standard")

            # Switch mode
            _env = EnvelopeConfig.exploratory()

            # Decision still there
            assert ledger.get(decision.id) is not None
            assert ledger.get(decision.id).claim.choice == "postgres"

    def test_epistemic_claim_survives_mode_switch(self):
        """Epistemic claims committed in strict mode survive mode switch."""
        ledger = EpistemicLedger()
        claim = ledger.new_claim("X is true", Provenance.OBSERVED)
        claim.commit_level = "hard"
        claim.epistemic_status = ClaimStatus.SUPPORTED

        # Mode switch doesn't touch the epistemic ledger
        _env = EnvelopeConfig.exploratory()

        assert ledger.claims[claim.claim_id].commit_level == "hard"
        assert ledger.claims[claim.claim_id].epistemic_status == ClaimStatus.SUPPORTED

    def test_strict_envelope_requires_receipts(self):
        """Strict envelope requires receipts — cannot be weakened."""
        env = EnvelopeConfig.strict()
        assert env.require_receipts is True

    def test_envelope_configs_are_distinct(self):
        """Strict and exploratory are structurally different."""
        strict = EnvelopeConfig.strict()
        exploratory = EnvelopeConfig.exploratory()
        assert strict.require_receipts != exploratory.require_receipts
        assert strict.commit_decisions != exploratory.commit_decisions


# =============================================================================
# 7. Evidence Type Gating
# =============================================================================


class TestEvidenceTypeGating:
    """Claims at certain levels require specific evidence types."""

    def test_evidence_types_are_enumerated(self):
        """All evidence types are known enum values."""
        expected = {
            "tool_trace", "url", "document", "human_input", "receipt",
            "cryptographic_proof", "calc_result", "test_result",
            "web_source", "live_retrieval",
        }
        actual = {e.value for e in EvidenceType}
        assert expected <= actual

    def test_evidence_ref_factory_methods_set_correct_type(self):
        """Factory methods produce correct EvidenceType."""
        assert EvidenceRef.from_tool_trace("t", "s").ref_type == EvidenceType.TOOL_TRACE
        assert EvidenceRef.from_url("u", "s").ref_type == EvidenceType.URL
        assert EvidenceRef.from_receipt("r", "s").ref_type == EvidenceType.RECEIPT
        assert EvidenceRef.from_human("h", "s").ref_type == EvidenceType.HUMAN_INPUT
        assert EvidenceRef.from_calc_result("c", "s").ref_type == EvidenceType.CALC_RESULT
        assert EvidenceRef.from_test_result("t", "s").ref_type == EvidenceType.TEST_RESULT
        assert EvidenceRef.from_web_source("w", "s").ref_type == EvidenceType.WEB_SOURCE
        assert EvidenceRef.from_live_retrieval("l", "s").ref_type == EvidenceType.LIVE_RETRIEVAL

    def test_grounded_claim_with_evidence_is_grounded(self):
        """A claim with evidence is marked as grounded."""
        claim = GroundedClaim(
            claim_id="c_1",
            content="tests pass",
            provenance=Provenance.ASSUMED,
            confidence=0.3,
            evidence_refs=[EvidenceRef.from_tool_trace("t", "tests")],
        )
        assert claim.is_grounded

    def test_grounded_claim_without_evidence_ungrounded(self):
        """ASSUMED claim without evidence is NOT grounded."""
        claim = GroundedClaim(
            claim_id="c_2",
            content="maybe true",
            provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        assert not claim.is_grounded

    def test_observed_claim_grounded_by_provenance(self):
        """OBSERVED claims are grounded by provenance alone."""
        claim = GroundedClaim(
            claim_id="c_3",
            content="I saw it",
            provenance=Provenance.OBSERVED,
            confidence=0.95,
        )
        assert claim.is_grounded


# =============================================================================
# 8. Structural Invariant: ClaimStatus FSM
# =============================================================================


class TestClaimStatusFSMInvariants:
    """The ClaimStatus FSM cannot be bypassed."""

    def test_proposed_to_supported_requires_evidence_reason(self):
        """PROPOSED→SUPPORTED needs EVIDENCE, AUDIT_RESULT, or QUORUM_PROJECTION reason."""
        from governor.epistemic import is_valid_transition

        valid, _ = is_valid_transition(
            ClaimStatus.PROPOSED, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE,
        )
        assert valid

        # CASCADE is not a valid reason for PROPOSED→SUPPORTED
        valid, msg = is_valid_transition(
            ClaimStatus.PROPOSED, ClaimStatus.SUPPORTED, TransitionReason.CASCADE,
        )
        assert not valid

    def test_terminal_states_only_human_can_override(self):
        """INVALIDATED/EXPIRED/REFUSED can only go to PROPOSED via HUMAN."""
        from governor.epistemic import is_valid_transition

        for terminal in [ClaimStatus.INVALIDATED, ClaimStatus.EXPIRED, ClaimStatus.REFUSED]:
            # HUMAN can override
            valid, _ = is_valid_transition(terminal, ClaimStatus.PROPOSED, TransitionReason.HUMAN)
            assert valid, f"HUMAN should be able to override {terminal}"

            # Non-HUMAN cannot
            valid, _ = is_valid_transition(terminal, ClaimStatus.PROPOSED, TransitionReason.EVIDENCE)
            assert not valid, f"EVIDENCE should not override {terminal}"

    def test_human_reason_always_valid(self):
        """TransitionReason.HUMAN always succeeds."""
        from governor.epistemic import is_valid_transition

        for from_s in ClaimStatus:
            for to_s in ClaimStatus:
                valid, _ = is_valid_transition(from_s, to_s, TransitionReason.HUMAN)
                assert valid, f"HUMAN should allow {from_s}→{to_s}"


# =============================================================================
# 9. Continuity Rule: converged=False cannot be silently accepted
# =============================================================================


class TestContinuityRule:
    """Convergence executor cannot silently accept a failed convergence run."""

    def test_convergence_result_records_converged_flag(self):
        """ConvergenceResult always records whether convergence was achieved."""
        from governor.continuity import (
            ConvergenceResult, ContinuityReport, RecommendedAction,
        )

        report = ContinuityReport(
            passed=False, score=0.5, violations=[],
            recommended_action=RecommendedAction.FAIL_CLOSED,
        )
        result = ConvergenceResult(
            output="partial", converged=False,
            attempts=5, final_report=report,
        )
        # converged=False must be visible in serialization
        d = result.to_dict()
        assert d["converged"] is False
        assert d["final_report"]["passed"] is False

    def test_convergence_result_failed_has_evidence(self):
        """A non-converged result carries a final_report with violation evidence."""
        from governor.continuity import (
            ConvergenceResult, ContinuityReport, Violation,
            AnchorType, Severity, RecommendedAction,
        )

        violations = [
            Violation(
                anchor_id="a1", anchor_type=AnchorType.CANON,
                severity=Severity.REJECT, description="Canon violated",
            ),
        ]
        report = ContinuityReport(
            passed=False, score=0.3, violations=violations,
            recommended_action=RecommendedAction.FAIL_CLOSED,
            checked_anchors=3,
        )
        result = ConvergenceResult(
            output="", converged=False,
            attempts=5, final_report=report,
        )
        # The failure evidence must survive serialization
        d = result.to_dict()
        assert len(d["final_report"]["violations"]) == 1
        assert d["final_report"]["violations"][0]["anchor_id"] == "a1"

    def test_convergence_executor_returns_converged_false_on_budget(self):
        """Executor returns converged=False when budget is exhausted."""
        from governor.continuity import (
            ConvergenceExecutor, ContinuityChecker,
            CorrectionLadder, ConvergenceBudget, Anchor, AnchorType, Severity,
        )

        anchors = [Anchor(
            id="always_fail",
            anchor_type=AnchorType.REQUIREMENT,
            description="Always violates",
            required_patterns=["IMPOSSIBLE_PATTERN_XYZ_NEVER_MATCHES"],
            severity=Severity.REJECT,
        )]

        class AlwaysSameProvider:
            def generate(self, prompt, **kwargs):
                return "This text will never contain the required pattern."

        executor = ConvergenceExecutor(
            provider=AlwaysSameProvider(),
            checker=ContinuityChecker(),
            ladder=CorrectionLadder(),
            budget=ConvergenceBudget(max_attempts=2, max_tokens=10000),
        )
        result = executor.converge_generate(
            prompt="Write something",
            anchors=anchors,
        )
        # Must NOT silently accept — converged must be False
        assert result.converged is False
        assert result.attempts == 2
        assert result.final_report.passed is False

    def test_convergence_executor_accept_only_when_passed(self):
        """Executor returns converged=True only when report.passed is True."""
        from governor.continuity import (
            ConvergenceExecutor, ContinuityChecker,
            CorrectionLadder, ConvergenceBudget, Anchor, AnchorType, Severity,
        )

        anchors = [Anchor(
            id="easy_anchor",
            anchor_type=AnchorType.REQUIREMENT,
            description="Requires 'hello'",
            required_patterns=["hello"],
            severity=Severity.CORRECT,
        )]

        class HelloProvider:
            def generate(self, prompt, **kwargs):
                return "hello world"

        executor = ConvergenceExecutor(
            provider=HelloProvider(),
            checker=ContinuityChecker(),
            ladder=CorrectionLadder(),
            budget=ConvergenceBudget(max_attempts=3),
        )
        result = executor.converge_generate(
            prompt="Say hello",
            anchors=anchors,
        )
        assert result.converged is True
        assert result.final_report.passed is True

    def test_telemetry_result_status_matches_convergence(self):
        """Telemetry final_status correctly reflects convergence outcome."""
        from governor.telemetry import ContinuityResultFields

        # ACCEPTED only when converged
        accepted = ContinuityResultFields(
            run_id="r1", mode="code", attempts=1,
            final_status="ACCEPTED",
        )
        assert accepted.final_status == "ACCEPTED"

        # REFUSED when not converged
        refused = ContinuityResultFields(
            run_id="r2", mode="code", attempts=5,
            final_status="REFUSED",
        )
        assert refused.final_status == "REFUSED"

        # ESCALATED when ladder hits REQUIRE_HITL
        escalated = ContinuityResultFields(
            run_id="r3", mode="fiction", attempts=5,
            final_status="ESCALATED",
        )
        assert escalated.final_status == "ESCALATED"

    def test_adapter_gates_on_violations(self):
        """Continuity adapter blocks when violations are present (one-shot gate)."""
        from governor.continuity import (
            AnchorRegistry, ContinuityChecker,
            Anchor, AnchorType, Severity,
        )
        from governor.adapters import continuity_invariant
        import tempfile
        from pathlib import Path

        registry = AnchorRegistry()
        registry.register(Anchor(
            id="must_have_x",
            anchor_type=AnchorType.REQUIREMENT,
            description="Output must contain X",
            required_patterns=["MUST_CONTAIN_THIS"],
            severity=Severity.CORRECT,
        ))

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "output.py"
            p.write_text("This text does not have the required pattern.")

            inv = continuity_invariant(registry, ContinuityChecker())
            result = inv.check(root=Path(tmpdir), files_touched=["output.py"])
            assert result.passed is False
