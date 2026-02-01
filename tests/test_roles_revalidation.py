"""
Tests for Layer 5: Roles & Scheduling + Periodic Revalidation.

Covers:
- AgentRole enum
- RoleBudget dataclass
- Vote.agent_role field + serialization
- QuorumPolicy.required_roles + role_budgets
- QuorumState.roles_filled / missing_roles
- Gate 8 (role requirements) in can_proceed()
- Role enforcement on create_quorum with HIGH risk
- DEFAULT_ROLE_BUDGETS
- RevalidationResult / RevalidationRun dataclasses
- RevalidationOrchestrator (TTL → Audit pipeline wiring)
- Backward compatibility (no roles = passes)
"""

from datetime import datetime, timedelta

import pytest

from governor.quorum import (
    AgentRole,
    ClaimType,
    DEFAULT_ROLE_BUDGETS,
    QuorumManager,
    QuorumPolicy,
    QuorumState,
    QuorumStatus,
    RiskLevel,
    RoleBudget,
    Vote,
    VoteVerdict,
)
from governor.dissent import EvidencePointer
from governor.ttl import (
    DecayAction,
    RevalidationEntry,
    RevalidationOrchestrator,
    RevalidationResult,
    RevalidationRun,
    TTLManager,
    VolatilityClass,
    create_revalidation_orchestrator,
)


# =============================================================================
# Helpers
# =============================================================================


def _ep(etype: str = "web_source") -> list[EvidencePointer]:
    return [EvidencePointer(description="auto", evidence_type=etype)]


def _make_mgr(**kw) -> QuorumManager:
    return QuorumManager(**kw)


# =============================================================================
# TestAgentRoleEnum
# =============================================================================


class TestAgentRoleEnum:

    def test_four_roles(self):
        assert len(AgentRole) == 4

    def test_string_values(self):
        assert AgentRole.PROPOSER == "proposer"
        assert AgentRole.RETRIEVER == "retriever"
        assert AgentRole.FALSIFIER == "falsifier"
        assert AgentRole.SYNTHESIZER == "synthesizer"

    def test_from_string(self):
        assert AgentRole("proposer") == AgentRole.PROPOSER
        assert AgentRole("falsifier") == AgentRole.FALSIFIER

    def test_invalid_role(self):
        with pytest.raises(ValueError):
            AgentRole("invalid")


# =============================================================================
# TestRoleBudget
# =============================================================================


class TestRoleBudget:

    def test_defaults(self):
        rb = RoleBudget()
        assert rb.max_tool_calls == 4
        assert rb.max_rounds == 1

    def test_custom(self):
        rb = RoleBudget(max_tool_calls=12, max_rounds=3)
        assert rb.max_tool_calls == 12
        assert rb.max_rounds == 3

    def test_to_dict(self):
        rb = RoleBudget(max_tool_calls=8, max_rounds=2)
        d = rb.to_dict()
        assert d == {"max_tool_calls": 8, "max_rounds": 2}

    def test_from_dict(self):
        rb = RoleBudget.from_dict({"max_tool_calls": 12, "max_rounds": 3})
        assert rb.max_tool_calls == 12
        assert rb.max_rounds == 3

    def test_from_dict_defaults(self):
        rb = RoleBudget.from_dict({})
        assert rb.max_tool_calls == 4
        assert rb.max_rounds == 1

    def test_default_budgets(self):
        assert RiskLevel.LOW in DEFAULT_ROLE_BUDGETS
        assert RiskLevel.MEDIUM in DEFAULT_ROLE_BUDGETS
        assert RiskLevel.HIGH in DEFAULT_ROLE_BUDGETS
        assert DEFAULT_ROLE_BUDGETS[RiskLevel.LOW].max_tool_calls == 4
        assert DEFAULT_ROLE_BUDGETS[RiskLevel.MEDIUM].max_tool_calls == 8
        assert DEFAULT_ROLE_BUDGETS[RiskLevel.HIGH].max_tool_calls == 12


# =============================================================================
# TestVoteRoleField
# =============================================================================


class TestVoteRoleField:

    def test_default_none(self):
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="ok",
        )
        assert v.agent_role is None

    def test_set_role(self):
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="ok",
            agent_role=AgentRole.FALSIFIER,
        )
        assert v.agent_role == AgentRole.FALSIFIER

    def test_to_dict_includes_role(self):
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="ok",
            agent_role=AgentRole.RETRIEVER,
        )
        d = v.to_dict()
        assert d["agent_role"] == "retriever"

    def test_to_dict_omits_none_role(self):
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="ok",
        )
        d = v.to_dict()
        assert "agent_role" not in d

    def test_from_dict_with_role(self):
        d = {
            "vote_id": "v1", "proposal_id": "p1", "agent_id": "a1",
            "verdict": "approve", "reason": "ok",
            "timestamp": datetime.now().isoformat(),
            "agent_role": "synthesizer",
        }
        v = Vote.from_dict(d)
        assert v.agent_role == AgentRole.SYNTHESIZER

    def test_from_dict_without_role(self):
        d = {
            "vote_id": "v1", "proposal_id": "p1", "agent_id": "a1",
            "verdict": "approve", "reason": "ok",
            "timestamp": datetime.now().isoformat(),
        }
        v = Vote.from_dict(d)
        assert v.agent_role is None


# =============================================================================
# TestQuorumPolicyRoles
# =============================================================================


class TestQuorumPolicyRoles:

    def test_default_policy_math_no_roles(self):
        from governor.quorum import DEFAULT_POLICIES
        assert DEFAULT_POLICIES[ClaimType.MATH].required_roles is None

    def test_default_policy_code_no_roles(self):
        from governor.quorum import DEFAULT_POLICIES
        assert DEFAULT_POLICIES[ClaimType.CODE].required_roles is None

    def test_default_policy_static_fact_requires_retriever(self):
        from governor.quorum import DEFAULT_POLICIES
        p = DEFAULT_POLICIES[ClaimType.STATIC_FACT]
        assert p.required_roles == {AgentRole.RETRIEVER}

    def test_default_policy_volatile_fact_requires_retriever_falsifier(self):
        from governor.quorum import DEFAULT_POLICIES
        p = DEFAULT_POLICIES[ClaimType.VOLATILE_FACT]
        assert p.required_roles == {AgentRole.RETRIEVER, AgentRole.FALSIFIER}

    def test_default_policy_procedure_requires_retriever_falsifier(self):
        from governor.quorum import DEFAULT_POLICIES
        p = DEFAULT_POLICIES[ClaimType.PROCEDURE]
        assert p.required_roles == {AgentRole.RETRIEVER, AgentRole.FALSIFIER}

    def test_default_policy_judgment_requires_three_roles(self):
        from governor.quorum import DEFAULT_POLICIES
        p = DEFAULT_POLICIES[ClaimType.JUDGMENT]
        assert p.required_roles == {AgentRole.RETRIEVER, AgentRole.FALSIFIER, AgentRole.SYNTHESIZER}

    def test_policy_to_dict_includes_roles(self):
        p = QuorumPolicy(
            claim_type=ClaimType.MATH,
            min_voters=2,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=1),
            volatility=VolatilityClass.PERMANENT,
            required_roles={AgentRole.PROPOSER, AgentRole.FALSIFIER},
        )
        d = p.to_dict()
        assert d["required_roles"] == ["falsifier", "proposer"]

    def test_policy_to_dict_none_roles(self):
        p = QuorumPolicy(
            claim_type=ClaimType.MATH,
            min_voters=2,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=1),
            volatility=VolatilityClass.PERMANENT,
        )
        d = p.to_dict()
        assert d["required_roles"] is None


# =============================================================================
# TestQuorumStateRoles
# =============================================================================


class TestQuorumStateRoles:

    def test_roles_filled_empty(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        assert qs.roles_filled == set()

    def test_roles_filled_after_vote(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"), agent_role=AgentRole.PROPOSER)
        qs = mgr.get_quorum("p1")
        assert qs.roles_filled == {AgentRole.PROPOSER}

    def test_multiple_roles(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"), agent_role=AgentRole.PROPOSER)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"), agent_role=AgentRole.FALSIFIER)
        qs = mgr.get_quorum("p1")
        assert qs.roles_filled == {AgentRole.PROPOSER, AgentRole.FALSIFIER}

    def test_missing_roles_none_required(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        assert qs.missing_roles == set()

    def test_missing_roles_some_filled(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.STATIC_FACT, created_at=now)
        qs = mgr.get_quorum("p1")
        assert qs.missing_roles == {AgentRole.RETRIEVER}

    def test_missing_roles_all_filled(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.STATIC_FACT, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("web_source"), agent_role=AgentRole.RETRIEVER)
        qs = mgr.get_quorum("p1")
        assert qs.missing_roles == set()

    def test_to_dict_includes_roles(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"), agent_role=AgentRole.PROPOSER)
        qs = mgr.get_quorum("p1")
        d = qs.to_dict()
        assert d["role_assignments"] == {"a1": "proposer"}
        assert "proposer" in d["roles_filled"]

    def test_role_assignment_tracked(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"), agent_role=AgentRole.RETRIEVER)
        qs = mgr.get_quorum("p1")
        assert qs.role_assignments["a1"] == "retriever"

    def test_no_role_no_assignment(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"))
        qs = mgr.get_quorum("p1")
        assert "a1" not in qs.role_assignments


# =============================================================================
# TestGate8RoleRequirements
# =============================================================================


class TestGate8RoleRequirements:

    def test_no_required_roles_passes(self):
        """MATH has no required_roles, so gate 8 passes."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"))
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"))
        mgr.update("p1", now=now + timedelta(seconds=5))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=5))
        assert can

    def test_missing_role_blocks(self):
        """STATIC_FACT requires RETRIEVER — blocks if not filled."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.STATIC_FACT, created_at=now)
        # Vote without assigning role
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("web_source"))
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("web_source"))
        mgr.update("p1", now=now + timedelta(seconds=125))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=125))
        assert not can
        assert any("Role requirement" in r for r in reasons)
        assert any("retriever" in r for r in reasons)

    def test_filled_role_passes(self):
        """STATIC_FACT passes when RETRIEVER role is filled."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.STATIC_FACT, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("web_source"), agent_role=AgentRole.RETRIEVER)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("web_source"))
        mgr.update("p1", now=now + timedelta(seconds=125))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=125))
        assert can

    def test_volatile_fact_requires_both(self):
        """VOLATILE_FACT requires RETRIEVER + FALSIFIER."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.VOLATILE_FACT, created_at=now)
        # Only provide retriever
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("live_retrieval"), agent_role=AgentRole.RETRIEVER)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("live_retrieval"))
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("live_retrieval"))
        mgr.update("p1", now=now + timedelta(seconds=310))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=310))
        assert not can
        assert any("falsifier" in r for r in reasons)

    def test_volatile_fact_both_roles_passes(self):
        """VOLATILE_FACT passes when both roles filled."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.VOLATILE_FACT, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("live_retrieval"), agent_role=AgentRole.RETRIEVER)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("live_retrieval"), agent_role=AgentRole.FALSIFIER)
        mgr.cast_vote("p1", "a3", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("live_retrieval"))
        mgr.update("p1", now=now + timedelta(seconds=310))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=310))
        assert can

    def test_high_risk_adds_falsifier_requirement(self):
        """HIGH risk on MATH (normally no roles) requires FALSIFIER."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.MATH, created_at=now, risk_level=RiskLevel.HIGH)
        assert qs.policy.required_roles == {AgentRole.FALSIFIER}

    def test_high_risk_falsifier_blocks(self):
        """HIGH risk blocks if falsifier not filled."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now, risk_level=RiskLevel.HIGH)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"))
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"))
        # HIGH risk Δt = 1s × 2.0 = 2s
        mgr.update("p1", now=now + timedelta(seconds=5))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=5))
        assert not can
        assert any("falsifier" in r for r in reasons)

    def test_high_risk_falsifier_passes(self):
        """HIGH risk passes when falsifier is filled."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now, risk_level=RiskLevel.HIGH)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"), agent_role=AgentRole.FALSIFIER)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       evidence=_ep("calc_result"))
        mgr.update("p1", now=now + timedelta(seconds=5))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=5))
        assert can

    def test_medium_risk_no_extra_roles(self):
        """MEDIUM risk on MATH doesn't add roles (only HIGH does)."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.MATH, created_at=now, risk_level=RiskLevel.MEDIUM)
        assert qs.policy.required_roles is None

    def test_custom_policy_no_roles(self):
        """Custom policy with no roles works fine."""
        policies = {
            ClaimType.MATH: QuorumPolicy(
                claim_type=ClaimType.MATH,
                min_voters=1,
                approval_threshold=0.5,
                delta_t=timedelta(seconds=0),
                volatility=VolatilityClass.PERMANENT,
            ),
        }
        mgr = QuorumManager(policies=policies)
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now)
        can, reasons = mgr.can_proceed("p1", now=now)
        assert can


# =============================================================================
# TestGetRoleBudget
# =============================================================================


class TestGetRoleBudget:

    def test_returns_budget_for_proposal(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        budget = mgr.get_role_budget("p1", "a1")
        assert budget is not None
        assert budget.max_tool_calls == 4  # LOW risk default

    def test_returns_none_for_missing_proposal(self):
        mgr = _make_mgr()
        assert mgr.get_role_budget("nonexistent", "a1") is None

    def test_high_risk_budget(self):
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now, risk_level=RiskLevel.HIGH)
        budget = mgr.get_role_budget("p1", "a1")
        assert budget.max_tool_calls == 12
        assert budget.max_rounds == 3


# =============================================================================
# TestRevalidationResult
# =============================================================================


class TestRevalidationResult:

    def test_basic(self):
        r = RevalidationResult(
            claim_id="c1", urgency=0.8,
            audit_passed=True, audit_decision="allow_hard",
        )
        assert r.claim_id == "c1"
        assert r.audit_passed

    def test_to_dict(self):
        r = RevalidationResult(
            claim_id="c1", urgency=0.8,
            audit_passed=True, audit_decision="allow_hard",
            new_status="revalidated",
        )
        d = r.to_dict()
        assert d["claim_id"] == "c1"
        assert d["new_status"] == "revalidated"

    def test_to_dict_error(self):
        r = RevalidationResult(
            claim_id="c1", urgency=0.8,
            audit_passed=False, audit_decision="error",
            error="Something broke",
        )
        d = r.to_dict()
        assert d["error"] == "Something broke"


# =============================================================================
# TestRevalidationRun
# =============================================================================


class TestRevalidationRun:

    def test_basic(self):
        run = RevalidationRun(
            timestamp=datetime(2024, 6, 1),
            claims_checked=5,
            claims_passed=3,
            claims_degraded=1,
            claims_blocked=1,
            decay_events=[],
            results=[],
        )
        assert run.claims_checked == 5

    def test_to_dict(self):
        run = RevalidationRun(
            timestamp=datetime(2024, 6, 1),
            claims_checked=2,
            claims_passed=1,
            claims_degraded=1,
            claims_blocked=0,
            decay_events=[],
            results=[],
            errors=0,
        )
        d = run.to_dict()
        assert d["claims_checked"] == 2
        assert d["claims_passed"] == 1


# =============================================================================
# TestRevalidationOrchestrator
# =============================================================================


class TestRevalidationOrchestrator:

    def test_no_pipeline_returns_errors(self):
        """Without audit pipeline, claims get error results."""
        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        ttl.track("c1", VolatilityClass.MODERATE, 0.8, created_at=now)
        # 80% through TTL → should appear in schedule
        later = now + timedelta(hours=20)

        orch = RevalidationOrchestrator(ttl)
        run = orch.run(now=later)
        assert run.claims_checked == 1
        assert run.errors == 1
        assert run.results[0].error == "No audit pipeline configured"

    def test_empty_schedule(self):
        """No claims needing revalidation → empty run."""
        ttl = TTLManager()
        orch = RevalidationOrchestrator(ttl)
        run = orch.run()
        assert run.claims_checked == 0
        assert run.claims_passed == 0

    def test_decay_events_captured(self):
        """Decay events from enforce() are captured in run."""
        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        ttl.track("c1", VolatilityClass.VOLATILE, 0.9, created_at=now)
        # Past TTL (1h) + past retract_after (24h)
        very_late = now + timedelta(hours=30)

        orch = RevalidationOrchestrator(ttl)
        run = orch.run(now=very_late)
        # Should have decay events (retraction)
        assert len(run.decay_events) >= 1

    def test_max_per_run_cap(self):
        """Orchestrator caps claims checked per run."""
        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        for i in range(10):
            ttl.track(f"c{i}", VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(hours=20)

        orch = RevalidationOrchestrator(ttl, max_per_run=3)
        run = orch.run(now=later)
        assert run.claims_checked == 3

    def test_metrics_accumulate(self):
        """Metrics accumulate across runs."""
        ttl = TTLManager()
        orch = RevalidationOrchestrator(ttl)

        orch.run()
        orch.run()

        metrics = orch.get_metrics()
        assert metrics["total_runs"] == 2

    def test_history_tracked(self):
        ttl = TTLManager()
        orch = RevalidationOrchestrator(ttl)
        orch.run()
        assert len(orch.history) == 1

    def test_create_convenience(self):
        ttl = TTLManager()
        orch = create_revalidation_orchestrator(ttl, max_per_run=25)
        assert orch.max_per_run == 25
        assert orch.ttl_manager is ttl


class TestRevalidationWithMockAudit:
    """Test revalidation with a mock audit pipeline."""

    def _mock_pipeline(self, decision_value="allow_hard"):
        """Create a minimal mock audit pipeline."""

        class MockDecision:
            def __init__(self, val):
                self.value = val

        class MockAudit:
            def __init__(self, decision_val):
                self.decision = MockDecision(decision_val)

        class MockPipeline:
            def __init__(self, d):
                self._d = d

            def audit(self, **kwargs):
                return MockAudit(self._d)

        # Patch AuditDecision for comparison
        return MockPipeline(decision_value)

    def test_allow_hard_revalidates(self):
        """allow_hard decision revalidates the claim."""
        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        ttl.track("c1", VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(hours=20)

        # We need the actual audit module to work
        from governor.audit import AuditDecision

        class FakePipeline:
            def audit(self, **kwargs):
                class FakeResult:
                    decision = AuditDecision.ALLOW_HARD
                return FakeResult()

        orch = RevalidationOrchestrator(ttl, audit_pipeline=FakePipeline())
        run = orch.run(now=later)
        assert run.claims_checked == 1
        assert run.claims_passed == 1
        assert run.results[0].audit_passed
        assert run.results[0].new_status == "revalidated"

    def test_downgrade_soft_degrades(self):
        """downgrade_soft marks claim as degraded."""
        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        ttl.track("c1", VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(hours=20)

        from governor.audit import AuditDecision

        class FakePipeline:
            def audit(self, **kwargs):
                class FakeResult:
                    decision = AuditDecision.DOWNGRADE_SOFT
                return FakeResult()

        orch = RevalidationOrchestrator(ttl, audit_pipeline=FakePipeline())
        run = orch.run(now=later)
        assert run.claims_degraded == 1
        assert not run.results[0].audit_passed
        assert run.results[0].new_status == "degraded"

    def test_block_blocks(self):
        """block decision blocks the claim."""
        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        ttl.track("c1", VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(hours=20)

        from governor.audit import AuditDecision

        class FakePipeline:
            def audit(self, **kwargs):
                class FakeResult:
                    decision = AuditDecision.BLOCK
                return FakeResult()

        orch = RevalidationOrchestrator(ttl, audit_pipeline=FakePipeline())
        run = orch.run(now=later)
        assert run.claims_blocked == 1
        assert run.results[0].new_status == "blocked"

    def test_with_epistemic_ledger(self):
        """Orchestrator enriches signals from epistemic ledger."""
        from governor.epistemic import EpistemicLedger, Provenance
        from governor.audit import AuditDecision

        ledger = EpistemicLedger()
        claim = ledger.new_claim("test claim", Provenance.RETRIEVED, confidence=0.85)
        cid = claim.claim_id

        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        ttl.track(cid, VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(hours=20)

        class FakePipeline:
            def __init__(self):
                self.last_signals = None

            def audit(self, **kwargs):
                self.last_signals = kwargs.get("signals")
                class FakeResult:
                    decision = AuditDecision.ALLOW_HARD
                return FakeResult()

        pipeline = FakePipeline()
        orch = RevalidationOrchestrator(
            ttl, audit_pipeline=pipeline, epistemic_ledger=ledger
        )
        run = orch.run(now=later)
        assert run.claims_passed == 1
        # Signals should be enriched from ledger
        assert pipeline.last_signals is not None
        assert pipeline.last_signals.confidence == 0.85

    def test_pipeline_error_handled(self):
        """Exceptions in audit pipeline are caught and reported."""
        ttl = TTLManager()
        now = datetime(2024, 6, 1)
        ttl.track("c1", VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(hours=20)

        class BrokenPipeline:
            def audit(self, **kwargs):
                raise RuntimeError("Pipeline exploded")

        orch = RevalidationOrchestrator(ttl, audit_pipeline=BrokenPipeline())
        run = orch.run(now=later)
        assert run.errors == 1
        assert "Pipeline exploded" in run.results[0].error


# =============================================================================
# TestBackwardCompat
# =============================================================================


class TestBackwardCompat:

    def test_vote_without_role_still_works(self):
        """Existing code that doesn't pass agent_role still works."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        v = mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        assert v is not None
        assert v.agent_role is None

    def test_no_required_roles_backward_compat(self):
        """Policies without required_roles (None) don't block."""
        policy = QuorumPolicy(
            claim_type=ClaimType.MATH,
            min_voters=1,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=0),
            volatility=VolatilityClass.PERMANENT,
        )
        assert policy.required_roles is None

    def test_quorum_state_empty_role_assignments(self):
        """QuorumState starts with empty role_assignments."""
        mgr = _make_mgr()
        now = datetime(2024, 6, 1)
        qs = mgr.create_quorum("p1", ClaimType.MATH, created_at=now)
        assert qs.role_assignments == {}

    def test_old_vote_dict_without_role(self):
        """Vote.from_dict works with old dicts missing agent_role."""
        d = {
            "vote_id": "v1", "proposal_id": "p1", "agent_id": "a1",
            "verdict": "approve", "reason": "ok",
            "timestamp": datetime(2024, 6, 1).isoformat(),
        }
        v = Vote.from_dict(d)
        assert v.agent_role is None
