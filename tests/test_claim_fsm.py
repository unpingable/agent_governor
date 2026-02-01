"""
Tests for Layer 6: ClaimStatus FSM Enforcement.

Tests the FSM transition table, transition validation, transition history,
integration with block/retract/cascade, and backward compatibility.
"""

import pytest
from datetime import datetime

from governor.epistemic import (
    ClaimStatus,
    TransitionReason,
    StatusTransition,
    TransitionResult,
    VALID_TRANSITIONS,
    is_valid_transition,
    EpistemicLedger,
    Provenance,
    GroundedClaim,
    GroundedClaimStatus,
    CascadeEvent,
)


# =============================================================================
# TransitionReason Enum
# =============================================================================


class TestTransitionReason:
    def test_all_values(self):
        assert len(TransitionReason) == 9
        expected = {
            "evidence", "audit_result", "ttl_expiry", "cascade",
            "quorum_projection", "dissent", "retraction", "revalidation", "human",
        }
        assert {r.value for r in TransitionReason} == expected

    def test_from_string(self):
        assert TransitionReason("evidence") == TransitionReason.EVIDENCE
        assert TransitionReason("human") == TransitionReason.HUMAN

    def test_invalid_string(self):
        with pytest.raises(ValueError):
            TransitionReason("invalid_reason")


# =============================================================================
# StatusTransition Dataclass
# =============================================================================


class TestStatusTransition:
    def test_basic_creation(self):
        t = StatusTransition(
            claim_id="c1",
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.EVIDENCE,
            justification="New evidence attached",
            step=5,
        )
        assert t.claim_id == "c1"
        assert t.from_status == ClaimStatus.PROPOSED
        assert t.to_status == ClaimStatus.SUPPORTED
        assert t.reason == TransitionReason.EVIDENCE
        assert t.justification == "New evidence attached"
        assert t.step == 5

    def test_from_none_status(self):
        t = StatusTransition(
            claim_id="c1",
            from_status=None,
            to_status=ClaimStatus.PROPOSED,
            reason=TransitionReason.QUORUM_PROJECTION,
            justification="first assignment",
        )
        assert t.from_status is None

    def test_to_dict(self):
        t = StatusTransition(
            claim_id="c1",
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.EVIDENCE,
            justification="test",
            step=3,
        )
        d = t.to_dict()
        assert d["claim_id"] == "c1"
        assert d["from_status"] == "proposed"
        assert d["to_status"] == "supported"
        assert d["reason"] == "evidence"
        assert d["justification"] == "test"
        assert d["step"] == 3
        assert "timestamp" in d

    def test_to_dict_none_from(self):
        t = StatusTransition(
            claim_id="c1",
            from_status=None,
            to_status=ClaimStatus.PROPOSED,
            reason=TransitionReason.HUMAN,
            justification="init",
        )
        d = t.to_dict()
        assert d["from_status"] is None

    def test_from_dict(self):
        d = {
            "claim_id": "c1",
            "from_status": "proposed",
            "to_status": "supported",
            "reason": "evidence",
            "justification": "test",
            "step": 5,
            "timestamp": "2025-01-01T00:00:00",
        }
        t = StatusTransition.from_dict(d)
        assert t.claim_id == "c1"
        assert t.from_status == ClaimStatus.PROPOSED
        assert t.to_status == ClaimStatus.SUPPORTED
        assert t.reason == TransitionReason.EVIDENCE
        assert t.step == 5

    def test_from_dict_none_from(self):
        d = {
            "claim_id": "c1",
            "from_status": None,
            "to_status": "proposed",
            "reason": "human",
            "justification": "init",
        }
        t = StatusTransition.from_dict(d)
        assert t.from_status is None

    def test_roundtrip(self):
        t = StatusTransition(
            claim_id="c1",
            from_status=ClaimStatus.CONTESTED,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.QUORUM_PROJECTION,
            justification="resolved commit",
            step=7,
        )
        t2 = StatusTransition.from_dict(t.to_dict())
        assert t2.claim_id == t.claim_id
        assert t2.from_status == t.from_status
        assert t2.to_status == t.to_status
        assert t2.reason == t.reason
        assert t2.step == t.step


# =============================================================================
# TransitionResult Dataclass
# =============================================================================


class TestTransitionResult:
    def test_success(self):
        r = TransitionResult(
            success=True,
            claim_id="c1",
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.EVIDENCE,
        )
        assert r.success is True
        assert r.error is None

    def test_failure(self):
        r = TransitionResult(
            success=False,
            claim_id="c1",
            from_status=ClaimStatus.REFUSED,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.EVIDENCE,
            error="Transition refused→supported not allowed with reason 'evidence'",
        )
        assert r.success is False
        assert r.error is not None

    def test_to_dict_success(self):
        r = TransitionResult(
            success=True,
            claim_id="c1",
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.EVIDENCE,
        )
        d = r.to_dict()
        assert d["success"] is True
        assert "error" not in d

    def test_to_dict_failure(self):
        r = TransitionResult(
            success=False,
            claim_id="c1",
            from_status=None,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.EVIDENCE,
            error="not found",
        )
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "not found"
        assert d["from_status"] is None


# =============================================================================
# VALID_TRANSITIONS Table
# =============================================================================


class TestValidTransitions:
    def test_table_is_dict(self):
        assert isinstance(VALID_TRANSITIONS, dict)

    def test_first_assignment_proposed(self):
        key = (None, ClaimStatus.PROPOSED)
        assert key in VALID_TRANSITIONS
        # All reasons allowed for first assignment
        for reason in TransitionReason:
            assert reason in VALID_TRANSITIONS[key]

    def test_first_assignment_supported(self):
        key = (None, ClaimStatus.SUPPORTED)
        assert key in VALID_TRANSITIONS

    def test_proposed_to_supported(self):
        key = (ClaimStatus.PROPOSED, ClaimStatus.SUPPORTED)
        allowed = VALID_TRANSITIONS[key]
        assert TransitionReason.EVIDENCE in allowed
        assert TransitionReason.AUDIT_RESULT in allowed
        assert TransitionReason.QUORUM_PROJECTION in allowed
        assert TransitionReason.HUMAN in allowed

    def test_supported_to_contested(self):
        key = (ClaimStatus.SUPPORTED, ClaimStatus.CONTESTED)
        allowed = VALID_TRANSITIONS[key]
        assert TransitionReason.DISSENT in allowed
        assert TransitionReason.QUORUM_PROJECTION in allowed

    def test_supported_to_stale(self):
        key = (ClaimStatus.SUPPORTED, ClaimStatus.STALE)
        allowed = VALID_TRANSITIONS[key]
        assert TransitionReason.TTL_EXPIRY in allowed
        assert TransitionReason.CASCADE in allowed

    def test_stale_to_supported(self):
        key = (ClaimStatus.STALE, ClaimStatus.SUPPORTED)
        allowed = VALID_TRANSITIONS[key]
        assert TransitionReason.EVIDENCE in allowed
        assert TransitionReason.REVALIDATION in allowed

    def test_contested_to_supported(self):
        key = (ClaimStatus.CONTESTED, ClaimStatus.SUPPORTED)
        allowed = VALID_TRANSITIONS[key]
        assert TransitionReason.EVIDENCE in allowed
        assert TransitionReason.QUORUM_PROJECTION in allowed

    def test_terminal_states_human_only(self):
        """Terminal states (INVALIDATED, EXPIRED, REFUSED) can only revert via HUMAN."""
        for terminal in [ClaimStatus.INVALIDATED, ClaimStatus.EXPIRED, ClaimStatus.REFUSED]:
            key = (terminal, ClaimStatus.PROPOSED)
            assert key in VALID_TRANSITIONS
            assert VALID_TRANSITIONS[key] == frozenset({TransitionReason.HUMAN})

    def test_undefined_transition(self):
        """Transitions not in table are illegal."""
        # EXPIRED → SUPPORTED is not defined (must go through PROPOSED first)
        key = (ClaimStatus.EXPIRED, ClaimStatus.SUPPORTED)
        assert key not in VALID_TRANSITIONS

    def test_no_direct_stale_to_contested(self):
        """STALE→CONTESTED is not defined (must revalidate first)."""
        key = (ClaimStatus.STALE, ClaimStatus.CONTESTED)
        assert key not in VALID_TRANSITIONS


# =============================================================================
# is_valid_transition()
# =============================================================================


class TestIsValidTransition:
    def test_valid_transition(self):
        valid, error = is_valid_transition(
            ClaimStatus.PROPOSED, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE
        )
        assert valid is True
        assert error == ""

    def test_invalid_transition_undefined(self):
        valid, error = is_valid_transition(
            ClaimStatus.EXPIRED, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE
        )
        assert valid is False
        assert "not defined in the FSM" in error

    def test_invalid_transition_wrong_reason(self):
        valid, error = is_valid_transition(
            ClaimStatus.PROPOSED, ClaimStatus.SUPPORTED, TransitionReason.TTL_EXPIRY
        )
        assert valid is False
        assert "not allowed with reason" in error
        assert "ttl_expiry" in error

    def test_human_always_valid(self):
        """HUMAN override bypasses all FSM checks."""
        valid, error = is_valid_transition(
            ClaimStatus.EXPIRED, ClaimStatus.SUPPORTED, TransitionReason.HUMAN
        )
        assert valid is True
        assert error == ""

    def test_same_status_always_valid(self):
        """Same status → no-op, always valid."""
        valid, error = is_valid_transition(
            ClaimStatus.PROPOSED, ClaimStatus.PROPOSED, TransitionReason.EVIDENCE
        )
        assert valid is True

    def test_first_assignment_valid(self):
        valid, error = is_valid_transition(
            None, ClaimStatus.PROPOSED, TransitionReason.QUORUM_PROJECTION
        )
        assert valid is True

    def test_terminal_to_proposed_needs_human(self):
        valid, error = is_valid_transition(
            ClaimStatus.REFUSED, ClaimStatus.PROPOSED, TransitionReason.EVIDENCE
        )
        assert valid is False

        valid, error = is_valid_transition(
            ClaimStatus.REFUSED, ClaimStatus.PROPOSED, TransitionReason.HUMAN
        )
        assert valid is True

    def test_proposed_to_refused(self):
        valid, error = is_valid_transition(
            ClaimStatus.PROPOSED, ClaimStatus.REFUSED, TransitionReason.AUDIT_RESULT
        )
        assert valid is True

    def test_supported_to_invalidated_retraction(self):
        valid, error = is_valid_transition(
            ClaimStatus.SUPPORTED, ClaimStatus.INVALIDATED, TransitionReason.RETRACTION
        )
        assert valid is True

    def test_contested_to_invalidated(self):
        valid, error = is_valid_transition(
            ClaimStatus.CONTESTED, ClaimStatus.INVALIDATED, TransitionReason.QUORUM_PROJECTION
        )
        assert valid is True

    def test_stale_to_expired(self):
        valid, error = is_valid_transition(
            ClaimStatus.STALE, ClaimStatus.EXPIRED, TransitionReason.TTL_EXPIRY
        )
        assert valid is True


# =============================================================================
# EpistemicLedger.transition_epistemic_status()
# =============================================================================


class TestTransitionEpistemicStatus:
    def setup_method(self):
        self.ledger = EpistemicLedger()
        self.claim = self.ledger.new_claim("test claim", Provenance.RETRIEVED, confidence=0.85)

    def test_first_assignment(self):
        """First assignment (None → PROPOSED) should succeed."""
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "quorum started",
        )
        assert result.success is True
        assert result.from_status is None
        assert result.to_status == ClaimStatus.PROPOSED
        assert self.claim.epistemic_status == ClaimStatus.PROPOSED

    def test_valid_forward_transition(self):
        """PROPOSED → SUPPORTED with evidence."""
        self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.EVIDENCE, "evidence attached",
        )
        assert result.success is True
        assert result.from_status == ClaimStatus.PROPOSED
        assert result.to_status == ClaimStatus.SUPPORTED
        assert self.claim.epistemic_status == ClaimStatus.SUPPORTED

    def test_invalid_transition_blocked(self):
        """PROPOSED → STALE is not valid (no path)."""
        self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.STALE,
            TransitionReason.TTL_EXPIRY, "should fail",
        )
        assert result.success is False
        assert "not defined in the FSM" in result.error
        # Status should NOT have changed
        assert self.claim.epistemic_status == ClaimStatus.PROPOSED

    def test_wrong_reason_blocked(self):
        """PROPOSED → SUPPORTED with TTL_EXPIRY should be blocked."""
        self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.TTL_EXPIRY, "wrong reason",
        )
        assert result.success is False
        assert "not allowed with reason" in result.error
        assert self.claim.epistemic_status == ClaimStatus.PROPOSED

    def test_claim_not_found(self):
        result = self.ledger.transition_epistemic_status(
            "nonexistent", ClaimStatus.PROPOSED,
            TransitionReason.HUMAN, "test",
        )
        assert result.success is False
        assert "not found" in result.error

    def test_same_status_noop(self):
        """Same status → no-op, always succeeds."""
        self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.EVIDENCE, "same status",
        )
        assert result.success is True
        # No transition recorded for no-op
        history = self.ledger.get_transition_history(self.claim.claim_id)
        assert len(history) == 1  # Only the initial assignment

    def test_human_override_bypasses_fsm(self):
        """HUMAN reason can force any transition."""
        self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.EXPIRED,
            TransitionReason.HUMAN, "force expired",
        )
        # EXPIRED → SUPPORTED would be illegal without HUMAN
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "human override",
        )
        assert result.success is True
        assert self.claim.epistemic_status == ClaimStatus.SUPPORTED

    def test_terminal_state_recovery(self):
        """Terminal states can only recover via HUMAN to PROPOSED."""
        self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.REFUSED,
            TransitionReason.HUMAN, "init refused",
        )
        # Cannot recover with EVIDENCE
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.EVIDENCE, "try evidence",
        )
        assert result.success is False

        # Can recover with HUMAN
        result = self.ledger.transition_epistemic_status(
            self.claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.HUMAN, "human recovery",
        )
        assert result.success is True

    def test_full_lifecycle(self):
        """Walk through a complete claim lifecycle."""
        cid = self.claim.claim_id

        # PROPOSED
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.PROPOSED, TransitionReason.QUORUM_PROJECTION, "quorum started",
        )
        assert r.success

        # PROPOSED → SUPPORTED (evidence)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE, "evidence attached",
        )
        assert r.success

        # SUPPORTED → CONTESTED (dissent)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.CONTESTED, TransitionReason.DISSENT, "agent_2 objected",
        )
        assert r.success

        # CONTESTED → SUPPORTED (resolved)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.QUORUM_PROJECTION, "resolved commit",
        )
        assert r.success

        # SUPPORTED → STALE (TTL expiry)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.STALE, TransitionReason.TTL_EXPIRY, "TTL expired",
        )
        assert r.success

        # STALE → SUPPORTED (revalidation)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.REVALIDATION, "revalidated",
        )
        assert r.success

        # SUPPORTED → INVALIDATED (retraction)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.INVALIDATED, TransitionReason.RETRACTION, "retracted",
        )
        assert r.success

        assert self.claim.epistemic_status == ClaimStatus.INVALIDATED

    def test_supported_contested_supported_loop(self):
        """SUPPORTED ↔ CONTESTED should work (dispute/resolution cycle)."""
        cid = self.claim.claim_id
        self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.HUMAN, "init",
        )

        for i in range(3):
            r = self.ledger.transition_epistemic_status(
                cid, ClaimStatus.CONTESTED, TransitionReason.DISSENT, f"dissent {i}",
            )
            assert r.success
            r = self.ledger.transition_epistemic_status(
                cid, ClaimStatus.SUPPORTED, TransitionReason.QUORUM_PROJECTION, f"resolve {i}",
            )
            assert r.success


# =============================================================================
# Transition History
# =============================================================================


class TestTransitionHistory:
    def setup_method(self):
        self.ledger = EpistemicLedger()

    def test_history_recorded(self):
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        assert len(self.ledger.transition_history) == 1
        assert self.ledger.total_transitions == 1

    def test_history_not_recorded_for_noop(self):
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        # Same status again
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.EVIDENCE, "noop",
        )
        assert len(self.ledger.transition_history) == 1

    def test_history_not_recorded_for_blocked(self):
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        # Invalid transition
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.STALE,
            TransitionReason.TTL_EXPIRY, "invalid",
        )
        assert len(self.ledger.transition_history) == 1
        assert self.ledger.total_transitions_blocked == 1

    def test_blocked_count(self):
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        for _ in range(3):
            self.ledger.transition_epistemic_status(
                claim.claim_id, ClaimStatus.STALE,
                TransitionReason.TTL_EXPIRY, "invalid",
            )
        assert self.ledger.total_transitions_blocked == 3

    def test_get_transition_history_all(self):
        c1 = self.ledger.new_claim("claim 1", Provenance.RETRIEVED)
        c2 = self.ledger.new_claim("claim 2", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            c1.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init c1",
        )
        self.ledger.transition_epistemic_status(
            c2.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init c2",
        )
        all_history = self.ledger.get_transition_history()
        assert len(all_history) == 2

    def test_get_transition_history_filtered(self):
        c1 = self.ledger.new_claim("claim 1", Provenance.RETRIEVED)
        c2 = self.ledger.new_claim("claim 2", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            c1.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        self.ledger.transition_epistemic_status(
            c2.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        self.ledger.transition_epistemic_status(
            c1.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.EVIDENCE, "evidence",
        )
        c1_history = self.ledger.get_transition_history(c1.claim_id)
        assert len(c1_history) == 2
        c2_history = self.ledger.get_transition_history(c2.claim_id)
        assert len(c2_history) == 1

    def test_transition_step_tracked(self):
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.step = 10
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        assert self.ledger.transition_history[0].step == 10


# =============================================================================
# FSM Enforcement Toggle
# =============================================================================


class TestFSMEnforcementToggle:
    def test_fsm_enforced_by_default(self):
        ledger = EpistemicLedger()
        assert ledger.fsm_enforced is True

    def test_disable_fsm_allows_any_transition(self):
        ledger = EpistemicLedger()
        ledger.fsm_enforced = False
        claim = ledger.new_claim("test", Provenance.RETRIEVED)
        # Set to EXPIRED directly
        ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.EXPIRED,
            TransitionReason.HUMAN, "init",
        )
        # EXPIRED → SUPPORTED with EVIDENCE — would be blocked with FSM
        result = ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.EVIDENCE, "should work without FSM",
        )
        assert result.success is True
        assert claim.epistemic_status == ClaimStatus.SUPPORTED

    def test_enable_fsm_blocks_invalid(self):
        ledger = EpistemicLedger()
        ledger.fsm_enforced = True
        claim = ledger.new_claim("test", Provenance.RETRIEVED)
        ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.EXPIRED,
            TransitionReason.HUMAN, "init",
        )
        result = ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.EVIDENCE, "should be blocked",
        )
        assert result.success is False


# =============================================================================
# Integration: block() and retract() with epistemic status
# =============================================================================


class TestBlockRetractIntegration:
    def setup_method(self):
        self.ledger = EpistemicLedger()

    def test_block_transitions_epistemic_status(self):
        """block() should transition epistemic_status to INVALIDATED."""
        claim = self.ledger.new_claim("test", Provenance.ASSUMED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        self.ledger.block(claim.claim_id, "missing grounding")
        assert claim.status == GroundedClaimStatus.BLOCKED
        assert claim.epistemic_status == ClaimStatus.INVALIDATED

    def test_block_without_epistemic_status_no_transition(self):
        """block() on claim with no epistemic_status should not create transition."""
        claim = self.ledger.new_claim("test", Provenance.ASSUMED)
        assert claim.epistemic_status is None
        self.ledger.block(claim.claim_id, "missing grounding")
        assert claim.status == GroundedClaimStatus.BLOCKED
        assert claim.epistemic_status is None  # Not changed

    def test_retract_transitions_epistemic_status(self):
        """retract() should transition epistemic_status to INVALIDATED."""
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "init",
        )
        self.ledger.retract(claim.claim_id, "explicit retraction")
        assert claim.status == GroundedClaimStatus.RETRACTED
        assert claim.epistemic_status == ClaimStatus.INVALIDATED

    def test_retract_without_epistemic_status_no_transition(self):
        """retract() on claim with no epistemic_status should not create transition."""
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        assert claim.epistemic_status is None
        self.ledger.retract(claim.claim_id, "retraction")
        assert claim.status == GroundedClaimStatus.RETRACTED
        assert claim.epistemic_status is None

    def test_block_transition_recorded_in_history(self):
        claim = self.ledger.new_claim("test", Provenance.ASSUMED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )
        self.ledger.block(claim.claim_id, "grounding failure")
        history = self.ledger.get_transition_history(claim.claim_id)
        assert len(history) == 2
        assert history[1].to_status == ClaimStatus.INVALIDATED
        assert history[1].reason == TransitionReason.AUDIT_RESULT

    def test_retract_transition_recorded_in_history(self):
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "init",
        )
        self.ledger.retract(claim.claim_id, "no longer true")
        history = self.ledger.get_transition_history(claim.claim_id)
        assert len(history) == 2
        assert history[1].reason == TransitionReason.RETRACTION


# =============================================================================
# Integration: set_epistemic_status() backward compatibility
# =============================================================================


class TestSetEpistemicStatusBackwardCompat:
    def setup_method(self):
        self.ledger = EpistemicLedger()

    def test_set_epistemic_status_still_works(self):
        """Legacy set_epistemic_status() should still work (HUMAN override)."""
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        result = self.ledger.set_epistemic_status(claim.claim_id, ClaimStatus.PROPOSED)
        assert result is True
        assert claim.epistemic_status == ClaimStatus.PROPOSED

    def test_set_epistemic_status_any_transition(self):
        """Legacy setter should allow any transition (HUMAN override)."""
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.set_epistemic_status(claim.claim_id, ClaimStatus.EXPIRED)
        self.ledger.set_epistemic_status(claim.claim_id, ClaimStatus.SUPPORTED)
        assert claim.epistemic_status == ClaimStatus.SUPPORTED

    def test_set_epistemic_status_returns_false_for_missing(self):
        result = self.ledger.set_epistemic_status("nonexistent", ClaimStatus.PROPOSED)
        assert result is False

    def test_set_epistemic_status_records_transition(self):
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.set_epistemic_status(claim.claim_id, ClaimStatus.PROPOSED)
        history = self.ledger.get_transition_history(claim.claim_id)
        assert len(history) == 1
        assert history[0].reason == TransitionReason.HUMAN


# =============================================================================
# Integration: Invalidation Cascade with Epistemic Status
# =============================================================================


class TestCascadeWithEpistemicStatus:
    def setup_method(self):
        self.ledger = EpistemicLedger()

    def test_cascade_downgrades_supported_to_stale(self):
        """When a dependency is invalidated, SUPPORTED dependents become STALE."""
        parent = self.ledger.new_claim("parent claim", Provenance.RETRIEVED)
        child = self.ledger.new_claim("child claim", Provenance.DERIVED)
        self.ledger.add_dependency(child.claim_id, parent.claim_id)

        # Set both to SUPPORTED
        self.ledger.transition_epistemic_status(
            parent.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "init",
        )
        self.ledger.transition_epistemic_status(
            child.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "init",
        )

        # Retract parent — should cascade to child
        self.ledger.retract(parent.claim_id, "retracted")
        assert child.epistemic_status == ClaimStatus.STALE

    def test_cascade_no_effect_on_non_supported(self):
        """PROPOSED dependents should not be cascaded (no PROPOSED→STALE path)."""
        parent = self.ledger.new_claim("parent", Provenance.RETRIEVED)
        child = self.ledger.new_claim("child", Provenance.DERIVED)
        self.ledger.add_dependency(child.claim_id, parent.claim_id)

        self.ledger.transition_epistemic_status(
            parent.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "init",
        )
        self.ledger.transition_epistemic_status(
            child.claim_id, ClaimStatus.PROPOSED,
            TransitionReason.QUORUM_PROJECTION, "init",
        )

        # Retract parent — child is PROPOSED, PROPOSED→STALE not in FSM
        self.ledger.retract(parent.claim_id, "retracted")
        # Child stays PROPOSED (cascade attempted but FSM blocked it)
        assert child.epistemic_status == ClaimStatus.PROPOSED

    def test_cascade_chain(self):
        """Cascade should propagate through chain: A→B→C."""
        a = self.ledger.new_claim("A", Provenance.RETRIEVED)
        b = self.ledger.new_claim("B", Provenance.DERIVED)
        c = self.ledger.new_claim("C", Provenance.DERIVED)
        self.ledger.add_dependency(b.claim_id, a.claim_id)
        self.ledger.add_dependency(c.claim_id, b.claim_id)

        for claim in [a, b, c]:
            self.ledger.transition_epistemic_status(
                claim.claim_id, ClaimStatus.SUPPORTED,
                TransitionReason.HUMAN, "init",
            )

        # Retract A — should cascade through B and C
        self.ledger.retract(a.claim_id, "retracted")
        assert b.epistemic_status == ClaimStatus.STALE
        assert c.epistemic_status == ClaimStatus.STALE

    def test_cascade_diamond(self):
        """Diamond dependency: A→B, A→C, B→D, C→D."""
        a = self.ledger.new_claim("A", Provenance.RETRIEVED)
        b = self.ledger.new_claim("B", Provenance.DERIVED)
        c = self.ledger.new_claim("C", Provenance.DERIVED)
        d = self.ledger.new_claim("D", Provenance.DERIVED)
        self.ledger.add_dependency(b.claim_id, a.claim_id)
        self.ledger.add_dependency(c.claim_id, a.claim_id)
        self.ledger.add_dependency(d.claim_id, b.claim_id)
        self.ledger.add_dependency(d.claim_id, c.claim_id)

        for claim in [a, b, c, d]:
            self.ledger.transition_epistemic_status(
                claim.claim_id, ClaimStatus.SUPPORTED,
                TransitionReason.HUMAN, "init",
            )

        self.ledger.retract(a.claim_id, "retracted")
        assert b.epistemic_status == ClaimStatus.STALE
        assert c.epistemic_status == ClaimStatus.STALE
        assert d.epistemic_status == ClaimStatus.STALE

    def test_cascade_event_records_epistemic_status_change(self):
        """CascadeEvent should record old/new epistemic status."""
        parent = self.ledger.new_claim("parent", Provenance.RETRIEVED)
        child = self.ledger.new_claim("child", Provenance.DERIVED)
        child.commit_level = "hard"
        self.ledger.add_dependency(child.claim_id, parent.claim_id)

        self.ledger.transition_epistemic_status(
            parent.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "init",
        )
        self.ledger.transition_epistemic_status(
            child.claim_id, ClaimStatus.SUPPORTED,
            TransitionReason.HUMAN, "init",
        )

        self.ledger.retract(parent.claim_id, "retracted")

        # Find cascade event for the child
        child_events = [e for e in self.ledger.cascade_history
                       if e.affected_claim_id == child.claim_id]
        assert len(child_events) >= 1
        event = child_events[0]
        assert event.old_epistemic_status == "supported"
        assert event.new_epistemic_status == "stale"


# =============================================================================
# All valid paths walkthrough
# =============================================================================


class TestAllValidPaths:
    """Test every defined path in the VALID_TRANSITIONS table."""

    def setup_method(self):
        self.ledger = EpistemicLedger()

    def _make_claim_at_status(self, status: ClaimStatus | None) -> str:
        """Helper: create a claim and set it to given status."""
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        if status is not None:
            self.ledger.transition_epistemic_status(
                claim.claim_id, status, TransitionReason.HUMAN, "setup",
            )
        return claim.claim_id

    def test_proposed_to_supported_evidence(self):
        cid = self._make_claim_at_status(ClaimStatus.PROPOSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE, "test",
        )
        assert r.success

    def test_proposed_to_supported_audit(self):
        cid = self._make_claim_at_status(ClaimStatus.PROPOSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.AUDIT_RESULT, "test",
        )
        assert r.success

    def test_proposed_to_contested_dissent(self):
        cid = self._make_claim_at_status(ClaimStatus.PROPOSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.CONTESTED, TransitionReason.DISSENT, "test",
        )
        assert r.success

    def test_proposed_to_refused_audit(self):
        cid = self._make_claim_at_status(ClaimStatus.PROPOSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.REFUSED, TransitionReason.AUDIT_RESULT, "test",
        )
        assert r.success

    def test_proposed_to_invalidated_retraction(self):
        cid = self._make_claim_at_status(ClaimStatus.PROPOSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.INVALIDATED, TransitionReason.RETRACTION, "test",
        )
        assert r.success

    def test_supported_to_contested_dissent(self):
        cid = self._make_claim_at_status(ClaimStatus.SUPPORTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.CONTESTED, TransitionReason.DISSENT, "test",
        )
        assert r.success

    def test_supported_to_stale_ttl(self):
        cid = self._make_claim_at_status(ClaimStatus.SUPPORTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.STALE, TransitionReason.TTL_EXPIRY, "test",
        )
        assert r.success

    def test_supported_to_stale_cascade(self):
        cid = self._make_claim_at_status(ClaimStatus.SUPPORTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.STALE, TransitionReason.CASCADE, "test",
        )
        assert r.success

    def test_supported_to_invalidated_retraction(self):
        cid = self._make_claim_at_status(ClaimStatus.SUPPORTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.INVALIDATED, TransitionReason.RETRACTION, "test",
        )
        assert r.success

    def test_supported_to_expired_ttl(self):
        cid = self._make_claim_at_status(ClaimStatus.SUPPORTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.EXPIRED, TransitionReason.TTL_EXPIRY, "test",
        )
        assert r.success

    def test_contested_to_supported_evidence(self):
        cid = self._make_claim_at_status(ClaimStatus.CONTESTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE, "test",
        )
        assert r.success

    def test_contested_to_supported_quorum(self):
        cid = self._make_claim_at_status(ClaimStatus.CONTESTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.QUORUM_PROJECTION, "test",
        )
        assert r.success

    def test_contested_to_invalidated_retraction(self):
        cid = self._make_claim_at_status(ClaimStatus.CONTESTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.INVALIDATED, TransitionReason.RETRACTION, "test",
        )
        assert r.success

    def test_contested_to_refused_quorum(self):
        cid = self._make_claim_at_status(ClaimStatus.CONTESTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.REFUSED, TransitionReason.QUORUM_PROJECTION, "test",
        )
        assert r.success

    def test_contested_to_stale_ttl(self):
        cid = self._make_claim_at_status(ClaimStatus.CONTESTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.STALE, TransitionReason.TTL_EXPIRY, "test",
        )
        assert r.success

    def test_stale_to_supported_evidence(self):
        cid = self._make_claim_at_status(ClaimStatus.STALE)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE, "test",
        )
        assert r.success

    def test_stale_to_supported_revalidation(self):
        cid = self._make_claim_at_status(ClaimStatus.STALE)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.REVALIDATION, "test",
        )
        assert r.success

    def test_stale_to_invalidated_revalidation(self):
        cid = self._make_claim_at_status(ClaimStatus.STALE)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.INVALIDATED, TransitionReason.REVALIDATION, "test",
        )
        assert r.success

    def test_stale_to_expired_ttl(self):
        cid = self._make_claim_at_status(ClaimStatus.STALE)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.EXPIRED, TransitionReason.TTL_EXPIRY, "test",
        )
        assert r.success

    def test_invalidated_to_proposed_human(self):
        cid = self._make_claim_at_status(ClaimStatus.INVALIDATED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.PROPOSED, TransitionReason.HUMAN, "test",
        )
        assert r.success

    def test_expired_to_proposed_human(self):
        cid = self._make_claim_at_status(ClaimStatus.EXPIRED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.PROPOSED, TransitionReason.HUMAN, "test",
        )
        assert r.success

    def test_refused_to_proposed_human(self):
        cid = self._make_claim_at_status(ClaimStatus.REFUSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.PROPOSED, TransitionReason.HUMAN, "test",
        )
        assert r.success


# =============================================================================
# Invalid transitions that should be blocked
# =============================================================================


class TestBlockedTransitions:
    def setup_method(self):
        self.ledger = EpistemicLedger()

    def _make_claim_at_status(self, status: ClaimStatus) -> str:
        claim = self.ledger.new_claim("test", Provenance.RETRIEVED)
        self.ledger.transition_epistemic_status(
            claim.claim_id, status, TransitionReason.HUMAN, "setup",
        )
        return claim.claim_id

    def test_proposed_to_stale_blocked(self):
        """PROPOSED → STALE is not a valid path."""
        cid = self._make_claim_at_status(ClaimStatus.PROPOSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.STALE, TransitionReason.TTL_EXPIRY, "test",
        )
        assert r.success is False

    def test_proposed_to_expired_blocked(self):
        """PROPOSED → EXPIRED is not valid (must go through SUPPORTED/STALE)."""
        cid = self._make_claim_at_status(ClaimStatus.PROPOSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.EXPIRED, TransitionReason.TTL_EXPIRY, "test",
        )
        assert r.success is False

    def test_stale_to_contested_blocked(self):
        """STALE → CONTESTED not defined (must revalidate first)."""
        cid = self._make_claim_at_status(ClaimStatus.STALE)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.CONTESTED, TransitionReason.DISSENT, "test",
        )
        assert r.success is False

    def test_expired_to_supported_blocked(self):
        """EXPIRED → SUPPORTED not defined (must go through PROPOSED)."""
        cid = self._make_claim_at_status(ClaimStatus.EXPIRED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE, "test",
        )
        assert r.success is False

    def test_refused_to_supported_blocked(self):
        """REFUSED → SUPPORTED not defined."""
        cid = self._make_claim_at_status(ClaimStatus.REFUSED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE, "test",
        )
        assert r.success is False

    def test_invalidated_to_supported_blocked(self):
        """INVALIDATED → SUPPORTED not defined."""
        cid = self._make_claim_at_status(ClaimStatus.INVALIDATED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.SUPPORTED, TransitionReason.EVIDENCE, "test",
        )
        assert r.success is False

    def test_supported_to_proposed_blocked(self):
        """Can't go backward SUPPORTED → PROPOSED."""
        cid = self._make_claim_at_status(ClaimStatus.SUPPORTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.PROPOSED, TransitionReason.QUORUM_PROJECTION, "test",
        )
        assert r.success is False

    def test_supported_to_refused_blocked(self):
        """SUPPORTED → REFUSED not defined (must go through CONTESTED)."""
        cid = self._make_claim_at_status(ClaimStatus.SUPPORTED)
        r = self.ledger.transition_epistemic_status(
            cid, ClaimStatus.REFUSED, TransitionReason.AUDIT_RESULT, "test",
        )
        assert r.success is False


# =============================================================================
# Backward compatibility: claims without epistemic_status
# =============================================================================


class TestBackwardCompatibility:
    def test_claim_starts_without_epistemic_status(self):
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test", Provenance.RETRIEVED)
        assert claim.epistemic_status is None

    def test_legacy_operations_work_without_status(self):
        """block/retract/promote should work on claims without epistemic_status."""
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        # These should work fine even without epistemic_status
        ledger.block(claim.claim_id, "test")
        assert claim.status == GroundedClaimStatus.BLOCKED

    def test_legacy_retract_works_without_status(self):
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test", Provenance.RETRIEVED)
        ledger.retract(claim.claim_id, "test")
        assert claim.status == GroundedClaimStatus.RETRACTED

    def test_old_claim_dict_without_epistemic_status(self):
        """GroundedClaim.from_dict should handle missing epistemic_status."""
        d = {
            "claim_id": "gc_test",
            "content": "test",
            "provenance": "retrieved",
            "confidence": 0.85,
            "evidence_refs": [],
            "status": "active",
            "created_at": "2025-01-01T00:00:00",
        }
        claim = GroundedClaim.from_dict(d)
        assert claim.epistemic_status is None

    def test_fsm_disabled_mimics_old_behavior(self):
        """With fsm_enforced=False, set_epistemic_status behaves like old code."""
        ledger = EpistemicLedger()
        ledger.fsm_enforced = False
        claim = ledger.new_claim("test", Provenance.RETRIEVED)
        # Old-style: just set whatever status
        ledger.set_epistemic_status(claim.claim_id, ClaimStatus.EXPIRED)
        assert claim.epistemic_status == ClaimStatus.EXPIRED
        ledger.set_epistemic_status(claim.claim_id, ClaimStatus.SUPPORTED)
        assert claim.epistemic_status == ClaimStatus.SUPPORTED
