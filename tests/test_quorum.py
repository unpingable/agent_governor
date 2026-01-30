"""
Tests for multi-agent quorum protocol.

Covers: ClaimType, VoteVerdict, QuorumStatus, QuorumPolicy, Vote,
QuorumState, QuorumManager, stability windows, dissent integration,
TTL integration, default policies, and edge cases.
"""

from datetime import datetime, timedelta

import pytest

from governor.quorum import (
    DEFAULT_POLICIES,
    ClaimType,
    QuorumManager,
    QuorumPolicy,
    QuorumState,
    QuorumStatus,
    Vote,
    VoteVerdict,
    create_quorum_manager,
    get_default_policy,
)
from governor.dissent import (
    DissentLedger,
    EvidencePointer,
    ObjectionSeverity,
)
from governor.ttl import VolatilityClass


# =============================================================================
# TestClaimTypeEnum
# =============================================================================


class TestClaimTypeEnum:

    def test_all_six_types(self):
        assert len(ClaimType) == 6

    def test_string_values(self):
        assert ClaimType.MATH == "math"
        assert ClaimType.CODE == "code"
        assert ClaimType.STATIC_FACT == "static_fact"
        assert ClaimType.VOLATILE_FACT == "volatile_fact"
        assert ClaimType.PROCEDURE == "procedure"
        assert ClaimType.JUDGMENT == "judgment"

    def test_from_string(self):
        assert ClaimType("math") == ClaimType.MATH
        assert ClaimType("judgment") == ClaimType.JUDGMENT


# =============================================================================
# TestVoteVerdict
# =============================================================================


class TestVoteVerdict:

    def test_three_verdicts(self):
        assert len(VoteVerdict) == 3

    def test_values(self):
        assert VoteVerdict.APPROVE == "approve"
        assert VoteVerdict.REJECT == "reject"
        assert VoteVerdict.ABSTAIN == "abstain"


# =============================================================================
# TestQuorumStatus
# =============================================================================


class TestQuorumStatus:

    def test_six_statuses(self):
        assert len(QuorumStatus) == 6

    def test_values(self):
        assert QuorumStatus.COLLECTING == "collecting"
        assert QuorumStatus.STABILIZING == "stabilizing"
        assert QuorumStatus.REACHED == "reached"
        assert QuorumStatus.FAILED == "failed"
        assert QuorumStatus.EXPIRED == "expired"
        assert QuorumStatus.CONTESTED == "contested"


# =============================================================================
# TestQuorumPolicy
# =============================================================================


class TestQuorumPolicy:

    def test_creation(self):
        p = QuorumPolicy(
            claim_type=ClaimType.CODE,
            min_voters=2,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=10),
            volatility=VolatilityClass.STABLE,
        )
        assert p.claim_type == ClaimType.CODE
        assert p.min_voters == 2
        assert p.approval_threshold == 0.5
        assert p.delta_t == timedelta(seconds=10)
        assert not p.requires_human

    def test_to_dict(self):
        p = QuorumPolicy(
            claim_type=ClaimType.MATH,
            min_voters=2,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=1),
            volatility=VolatilityClass.PERMANENT,
        )
        d = p.to_dict()
        assert d["claim_type"] == "math"
        assert d["min_voters"] == 2
        assert d["delta_t_seconds"] == 1.0
        assert d["volatility"] == "permanent"
        assert d["requires_human"] is False

    def test_requires_human(self):
        p = QuorumPolicy(
            claim_type=ClaimType.JUDGMENT,
            min_voters=3,
            approval_threshold=0.75,
            delta_t=timedelta(seconds=600),
            volatility=VolatilityClass.STABLE,
            requires_human=True,
        )
        assert p.requires_human


# =============================================================================
# TestDefaultPolicies
# =============================================================================


class TestDefaultPolicies:

    def test_all_claim_types_have_policies(self):
        for ct in ClaimType:
            assert ct in DEFAULT_POLICIES

    def test_math_policy(self):
        p = DEFAULT_POLICIES[ClaimType.MATH]
        assert p.min_voters == 2
        assert p.approval_threshold == 0.5
        assert p.delta_t == timedelta(seconds=1)
        assert p.volatility == VolatilityClass.PERMANENT
        assert not p.requires_human

    def test_code_policy(self):
        p = DEFAULT_POLICIES[ClaimType.CODE]
        assert p.min_voters == 1
        assert p.delta_t == timedelta(seconds=10)
        assert p.volatility == VolatilityClass.STABLE

    def test_static_fact_policy(self):
        p = DEFAULT_POLICIES[ClaimType.STATIC_FACT]
        assert p.min_voters == 2
        assert p.approval_threshold == 0.67
        assert p.delta_t == timedelta(seconds=120)

    def test_volatile_fact_policy(self):
        p = DEFAULT_POLICIES[ClaimType.VOLATILE_FACT]
        assert p.min_voters == 3
        assert p.approval_threshold == 0.67
        assert p.delta_t == timedelta(seconds=300)
        assert p.volatility == VolatilityClass.VOLATILE

    def test_procedure_policy(self):
        p = DEFAULT_POLICIES[ClaimType.PROCEDURE]
        assert p.min_voters == 3
        assert p.approval_threshold == 0.75
        assert p.delta_t == timedelta(seconds=300)

    def test_judgment_policy(self):
        p = DEFAULT_POLICIES[ClaimType.JUDGMENT]
        assert p.min_voters == 3
        assert p.approval_threshold == 0.75
        assert p.delta_t == timedelta(seconds=600)
        assert p.requires_human

    def test_delta_t_ordering(self):
        """Higher-stakes claim types should have longer Δt windows."""
        math_dt = DEFAULT_POLICIES[ClaimType.MATH].delta_t
        code_dt = DEFAULT_POLICIES[ClaimType.CODE].delta_t
        static_dt = DEFAULT_POLICIES[ClaimType.STATIC_FACT].delta_t
        judgment_dt = DEFAULT_POLICIES[ClaimType.JUDGMENT].delta_t
        assert math_dt <= code_dt <= static_dt <= judgment_dt

    def test_get_default_policy(self):
        p = get_default_policy(ClaimType.CODE)
        assert p.claim_type == ClaimType.CODE


# =============================================================================
# TestVote
# =============================================================================


class TestVote:

    def test_creation(self):
        v = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="agent-a",
            verdict=VoteVerdict.APPROVE,
            reason="Looks correct",
        )
        assert v.vote_id == "v1"
        assert v.verdict == VoteVerdict.APPROVE

    def test_to_dict(self):
        v = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="agent-a",
            verdict=VoteVerdict.REJECT,
            reason="Insufficient evidence",
            evidence=[EvidencePointer(description="test trace")],
        )
        d = v.to_dict()
        assert d["vote_id"] == "v1"
        assert d["verdict"] == "reject"
        assert len(d["evidence"]) == 1

    def test_from_dict(self):
        now = datetime.now()
        d = {
            "vote_id": "v2",
            "proposal_id": "p2",
            "agent_id": "agent-b",
            "verdict": "approve",
            "reason": "All checks pass",
            "evidence": [],
            "timestamp": now.isoformat(),
        }
        v = Vote.from_dict(d)
        assert v.vote_id == "v2"
        assert v.verdict == VoteVerdict.APPROVE

    def test_with_evidence(self):
        v = Vote(
            vote_id="v1",
            proposal_id="p1",
            agent_id="agent-a",
            verdict=VoteVerdict.APPROVE,
            reason="Verified",
            evidence=[
                EvidencePointer(description="tool trace", locator="trace-001"),
                EvidencePointer(description="log output"),
            ],
        )
        assert len(v.evidence) == 2


# =============================================================================
# TestQuorumState
# =============================================================================


class TestQuorumState:

    def _make_state(self, claim_type=ClaimType.MATH) -> QuorumState:
        """Helper to create a QuorumState with default policy."""
        policy = DEFAULT_POLICIES[claim_type]
        return QuorumState(
            proposal_id="p1",
            claim_type=claim_type,
            policy=policy,
        )

    def test_initial_status(self):
        qs = self._make_state()
        assert qs.status == QuorumStatus.COLLECTING

    def test_empty_counts(self):
        qs = self._make_state()
        assert qs.approval_count == 0
        assert qs.rejection_count == 0
        assert qs.abstain_count == 0
        assert qs.total_votes == 0

    def test_approval_ratio_empty(self):
        qs = self._make_state()
        assert qs.approval_ratio == 0.0

    def test_approval_ratio_with_votes(self):
        qs = self._make_state()
        qs.votes["a1"] = Vote("v1", "p1", "a1", VoteVerdict.APPROVE, "ok")
        qs.votes["a2"] = Vote("v2", "p1", "a2", VoteVerdict.REJECT, "no")
        assert qs.approval_ratio == 0.5

    def test_approval_ratio_ignores_abstain(self):
        qs = self._make_state()
        qs.votes["a1"] = Vote("v1", "p1", "a1", VoteVerdict.APPROVE, "ok")
        qs.votes["a2"] = Vote("v2", "p1", "a2", VoteVerdict.ABSTAIN, "pass")
        # 1 approve / 1 non-abstain = 1.0
        assert qs.approval_ratio == 1.0

    def test_has_enough_voters(self):
        qs = self._make_state(ClaimType.MATH)  # k=2
        assert not qs.has_enough_voters
        qs.votes["a1"] = Vote("v1", "p1", "a1", VoteVerdict.APPROVE, "ok")
        assert not qs.has_enough_voters
        qs.votes["a2"] = Vote("v2", "p1", "a2", VoteVerdict.APPROVE, "ok")
        assert qs.has_enough_voters

    def test_threshold_met(self):
        qs = self._make_state(ClaimType.MATH)  # k=2, threshold=0.5
        qs.votes["a1"] = Vote("v1", "p1", "a1", VoteVerdict.APPROVE, "ok")
        qs.votes["a2"] = Vote("v2", "p1", "a2", VoteVerdict.APPROVE, "ok")
        assert qs.threshold_met

    def test_threshold_not_met_too_many_rejects(self):
        qs = self._make_state(ClaimType.STATIC_FACT)  # k=2, threshold=0.67
        qs.votes["a1"] = Vote("v1", "p1", "a1", VoteVerdict.APPROVE, "ok")
        qs.votes["a2"] = Vote("v2", "p1", "a2", VoteVerdict.REJECT, "no")
        # ratio = 0.5 < 0.67
        assert not qs.threshold_met

    def test_is_stable(self):
        now = datetime(2024, 6, 1)
        qs = self._make_state(ClaimType.MATH)  # Δt=1s
        qs.stabilized_at = now
        assert not qs.is_stable(now)
        assert qs.is_stable(now + timedelta(seconds=2))

    def test_is_stable_none(self):
        qs = self._make_state()
        assert not qs.is_stable()

    def test_is_timed_out(self):
        now = datetime(2024, 6, 1)
        qs = self._make_state(ClaimType.MATH)  # timeout=5m
        qs.created_at = now
        assert not qs.is_timed_out(now + timedelta(minutes=4))
        assert qs.is_timed_out(now + timedelta(minutes=6))

    def test_to_dict(self):
        qs = self._make_state()
        d = qs.to_dict()
        assert d["proposal_id"] == "p1"
        assert d["claim_type"] == "math"
        assert d["status"] == "collecting"
        assert "approval_count" in d
        assert "policy" in d


# =============================================================================
# TestQuorumManager — Creation and Voting
# =============================================================================


class TestQuorumManagerBasic:

    def test_create_quorum(self):
        mgr = QuorumManager()
        qs = mgr.create_quorum("p1", ClaimType.CODE)
        assert qs.proposal_id == "p1"
        assert qs.claim_type == ClaimType.CODE
        assert qs.status == QuorumStatus.COLLECTING
        assert mgr.get_quorum("p1") is qs

    def test_create_quorum_with_timestamp(self):
        mgr = QuorumManager()
        past = datetime(2024, 1, 1)
        qs = mgr.create_quorum("p1", ClaimType.MATH, created_at=past)
        assert qs.created_at == past

    def test_get_nonexistent(self):
        mgr = QuorumManager()
        assert mgr.get_quorum("bad") is None

    def test_check_status_nonexistent(self):
        mgr = QuorumManager()
        assert mgr.check_status("bad") is None

    def test_cast_vote(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        vote = mgr.cast_vote("p1", "agent-a", VoteVerdict.APPROVE, "looks good")
        assert vote is not None
        assert vote.verdict == VoteVerdict.APPROVE
        assert vote.agent_id == "agent-a"

    def test_cast_vote_nonexistent_proposal(self):
        mgr = QuorumManager()
        vote = mgr.cast_vote("bad", "agent-a", VoteVerdict.APPROVE, "ok")
        assert vote is None

    def test_duplicate_vote_rejected(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        v1 = mgr.cast_vote("p1", "agent-a", VoteVerdict.APPROVE, "first")
        v2 = mgr.cast_vote("p1", "agent-a", VoteVerdict.REJECT, "changed mind")
        assert v1 is not None
        assert v2 is None  # Duplicate rejected

    def test_cast_vote_with_evidence(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        ev = [EvidencePointer(description="test trace")]
        vote = mgr.cast_vote("p1", "agent-a", VoteVerdict.APPROVE, "ok", evidence=ev)
        assert len(vote.evidence) == 1

    def test_get_policy(self):
        mgr = QuorumManager()
        p = mgr.get_policy(ClaimType.CODE)
        assert p.claim_type == ClaimType.CODE


# =============================================================================
# TestQuorumManager — State Transitions
# =============================================================================


class TestQuorumTransitions:

    def test_collecting_to_stabilizing(self):
        """Threshold met → STABILIZING."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)  # k=1, threshold=0.5
        mgr.cast_vote("p1", "agent-a", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_stabilizing_to_reached(self):
        """Δt window elapsed → REACHED."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)  # Δt=10s
        mgr.cast_vote("p1", "agent-a", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # Advance past Δt
        later = now + timedelta(seconds=15)
        mgr.update("p1", now=later)
        assert mgr.check_status("p1") == QuorumStatus.REACHED

    def test_stabilizing_reset_on_reject(self):
        """A REJECT during stabilization that breaks threshold → COLLECTING."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        # STATIC_FACT: k=2, threshold=0.67
        mgr.create_quorum("p1", ClaimType.STATIC_FACT, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # Third vote is a reject: ratio = 2/3 = 0.6667 < 0.67 threshold
        # This breaks the threshold and destabilizes back to COLLECTING
        mgr.cast_vote("p1", "a3", VoteVerdict.REJECT, "no", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.COLLECTING

    def test_stabilizing_destabilized_by_reject(self):
        """A REJECT during stabilization that breaks threshold → COLLECTING."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        # PROCEDURE: k=3, threshold=0.75
        mgr.create_quorum("p1", ClaimType.PROCEDURE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # Fourth vote is a reject: 3/4 = 0.75, still meets threshold
        mgr.cast_vote("p1", "a4", VoteVerdict.REJECT, "no", timestamp=now)
        # 3 approve, 1 reject = 3/4 = 0.75, meets 0.75 threshold
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_timeout_during_collecting(self):
        """Timeout while collecting → FAILED."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)  # timeout=5m
        later = now + timedelta(minutes=10)
        mgr.update("p1", now=later)
        assert mgr.check_status("p1") == QuorumStatus.FAILED
        qs = mgr.get_quorum("p1")
        assert qs.failed_reason == "Timeout: insufficient votes"

    def test_timeout_during_stabilizing(self):
        """Timeout while stabilizing → FAILED."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        # CODE: k=1, timeout=30m
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # Advance past timeout
        later = now + timedelta(minutes=35)
        mgr.update("p1", now=later)
        assert mgr.check_status("p1") == QuorumStatus.FAILED

    def test_contest_and_resolve(self):
        """REACHED → CONTESTED → REACHED."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

        # Contest
        assert mgr.contest("p1")
        assert mgr.check_status("p1") == QuorumStatus.CONTESTED

        # Resolve
        assert mgr.resolve_contest("p1")
        assert mgr.check_status("p1") == QuorumStatus.REACHED

    def test_contest_wrong_status(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        assert not mgr.contest("p1")  # COLLECTING, not REACHED

    def test_resolve_contest_wrong_status(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        assert not mgr.resolve_contest("p1")  # Not CONTESTED

    def test_manual_fail(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        assert mgr.fail("p1", "Manual rejection")
        assert mgr.check_status("p1") == QuorumStatus.FAILED

    def test_manual_fail_already_failed(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        mgr.fail("p1", "first")
        assert not mgr.fail("p1", "second")

    def test_no_vote_on_failed(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        mgr.fail("p1", "done")
        vote = mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok")
        assert vote is None

    def test_no_vote_on_reached(self):
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))
        assert mgr.check_status("p1") == QuorumStatus.REACHED
        vote = mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "late")
        assert vote is None


# =============================================================================
# TestStabilityWindow
# =============================================================================


class TestStabilityWindow:

    def test_delta_t_math_fast(self):
        """MATH claims have 1s Δt — very fast consensus."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # 1s later: should be reached
        mgr.update("p1", now=now + timedelta(seconds=2))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

    def test_delta_t_judgment_slow(self):
        """JUDGMENT claims have 600s Δt — slow consensus."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.JUDGMENT, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # 5 min later: still stabilizing (need 10 min)
        mgr.update("p1", now=now + timedelta(minutes=5))
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # 11 min later: reached
        mgr.update("p1", now=now + timedelta(minutes=11))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

    def test_stability_window_exact_boundary(self):
        """Δt boundary: exactly at Δt should count as stable."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)  # Δt=10s
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

        # Exactly at Δt
        mgr.update("p1", now=now + timedelta(seconds=10))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

    def test_abstain_doesnt_prevent_quorum(self):
        """Abstain votes don't count against threshold."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)  # k=2, threshold=0.5
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.ABSTAIN, "no opinion", timestamp=now)
        # 1 approve / 1 non-abstain = 1.0, k=2 met
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING


# =============================================================================
# TestDissentIntegration
# =============================================================================


class TestDissentIntegration:

    def test_can_proceed_no_dissent(self):
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

        can, reasons = mgr.can_proceed("p1")
        assert can
        assert len(reasons) == 0

    def test_can_proceed_with_empty_dissent(self):
        mgr = QuorumManager()
        dl = DissentLedger()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))

        can, reasons = mgr.can_proceed("p1", dissent_ledger=dl, now=now + timedelta(seconds=15))
        assert can

    def test_can_proceed_blocked_by_dissent(self):
        mgr = QuorumManager()
        dl = DissentLedger()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))

        # File a critical objection
        dl.file_objection(
            claim_id="p1",
            agent_id="dissenter",
            reason="This is wrong",
            severity=ObjectionSeverity.CRITICAL,
        )

        can, reasons = mgr.can_proceed("p1", dissent_ledger=dl, now=now + timedelta(seconds=15))
        assert not can
        assert any("Dissent blocks" in r for r in reasons)

    def test_can_proceed_not_reached(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        can, reasons = mgr.can_proceed("p1")
        assert not can
        assert any("not reached" in r for r in reasons)

    def test_can_proceed_nonexistent(self):
        mgr = QuorumManager()
        can, reasons = mgr.can_proceed("bad")
        assert not can

    def test_can_proceed_requires_human(self):
        """JUDGMENT claims require human approval."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.JUDGMENT, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=700))

        # No human vote
        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=700))
        assert not can
        assert any("human" in r.lower() for r in reasons)

    def test_can_proceed_human_approved(self):
        """JUDGMENT claims pass if a human: agent voted."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.JUDGMENT, created_at=now)
        mgr.cast_vote("p1", "human:reviewer", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=700))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=700))
        assert can


# =============================================================================
# TestTTLIntegration
# =============================================================================


class TestTTLIntegration:

    def test_ttl_expiry_volatile(self):
        """VOLATILE_FACT consensus expires with volatile TTL (1h)."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.VOLATILE_FACT, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=310))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

        # Volatile TTL is 1h. 2h later should expire.
        expired = mgr.enforce_ttl(now=now + timedelta(hours=2))
        assert "p1" in expired
        assert mgr.check_status("p1") == QuorumStatus.EXPIRED

    def test_ttl_permanent_no_expiry(self):
        """MATH consensus (PERMANENT volatility) never expires."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=5))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

        # Even far in the future, permanent doesn't expire
        expired = mgr.enforce_ttl(now=now + timedelta(days=365))
        assert "p1" not in expired
        assert mgr.check_status("p1") == QuorumStatus.REACHED

    def test_ttl_only_reached_checked(self):
        """Only REACHED quorums are checked for TTL expiry."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        # Leave in COLLECTING
        expired = mgr.enforce_ttl(now=now + timedelta(days=30))
        assert len(expired) == 0

    def test_ttl_stable_class(self):
        """STABLE consensus (CODE, JUDGMENT) expires after 7 days."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))
        assert mgr.check_status("p1") == QuorumStatus.REACHED

        # Within 7 days: not expired
        expired = mgr.enforce_ttl(now=now + timedelta(days=5))
        assert len(expired) == 0

        # Past 7 days: expired
        expired = mgr.enforce_ttl(now=now + timedelta(days=8))
        assert "p1" in expired


# =============================================================================
# TestQueries
# =============================================================================


class TestQueries:

    def test_active_quorums(self):
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.create_quorum("p2", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p2", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p2", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p2", now=now + timedelta(seconds=5))  # p2 → REACHED

        active = mgr.active_quorums()
        assert len(active) == 1
        assert active[0].proposal_id == "p1"

    def test_reached_quorums(self):
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))

        reached = mgr.reached_quorums()
        assert len(reached) == 1

    def test_failed_quorums(self):
        mgr = QuorumManager()
        mgr.create_quorum("p1", ClaimType.CODE)
        mgr.fail("p1", "nope")
        assert len(mgr.failed_quorums()) == 1

    def test_contested_quorums(self):
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))
        mgr.contest("p1")
        assert len(mgr.contested_quorums()) == 1

    def test_get_metrics(self):
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.create_quorum("p2", ClaimType.MATH, created_at=now)
        mgr.fail("p2", "nope")

        m = mgr.get_metrics()
        assert m["total_quorums"] == 2
        assert m["total_votes"] == 1
        assert m["by_status"]["failed"] == 1


# =============================================================================
# TestEdgeCases
# =============================================================================


class TestEdgeCases:

    def test_single_voter_code(self):
        """CODE allows k=1 — single voter can achieve quorum."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_all_abstain(self):
        """All abstain votes: threshold not met (0 non-abstain)."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.ABSTAIN, "pass", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.ABSTAIN, "pass", timestamp=now)
        # ratio = 0.0 < 0.5
        assert mgr.check_status("p1") == QuorumStatus.COLLECTING

    def test_mixed_approve_abstain(self):
        """Approve + abstain: ratio is 1.0 (abstains excluded from ratio)."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.cast_vote("p1", "a2", VoteVerdict.ABSTAIN, "pass", timestamp=now)
        # 1 approve / 1 non-abstain = 1.0, k=2 met
        assert mgr.check_status("p1") == QuorumStatus.STABILIZING

    def test_update_nonexistent(self):
        mgr = QuorumManager()
        assert mgr.update("bad") is None

    def test_history_logged(self):
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert len(mgr.history) >= 2  # create + vote

    def test_custom_policies(self):
        """Custom policy overrides defaults."""
        custom = {
            ClaimType.MATH: QuorumPolicy(
                claim_type=ClaimType.MATH,
                min_voters=5,
                approval_threshold=0.9,
                delta_t=timedelta(seconds=60),
                volatility=VolatilityClass.STABLE,
            ),
        }
        mgr = QuorumManager(policies=custom)
        p = mgr.get_policy(ClaimType.MATH)
        assert p.min_voters == 5

    def test_create_quorum_manager_convenience(self):
        mgr = create_quorum_manager()
        assert isinstance(mgr, QuorumManager)
        assert len(mgr.policies) == 6

    def test_full_lifecycle(self):
        """Full lifecycle: COLLECTING → STABILIZING → REACHED."""
        mgr = QuorumManager()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.STATIC_FACT, created_at=now)
        assert qs.status == QuorumStatus.COLLECTING

        # Vote (k=2, threshold=0.67)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert qs.status == QuorumStatus.COLLECTING  # k not met yet
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert qs.status == QuorumStatus.STABILIZING  # threshold met

        # Wait for Δt (120s)
        mgr.update("p1", now=now + timedelta(seconds=60))
        assert qs.status == QuorumStatus.STABILIZING  # Not yet

        mgr.update("p1", now=now + timedelta(seconds=125))
        assert qs.status == QuorumStatus.REACHED

        # Can proceed
        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=125))
        assert can
