# SPDX-License-Identifier: Apache-2.0
"""
Property-based tests for governor invariants.

These test *properties that must always hold* regardless of input combination.
Focus areas from govtests.md:
1. Mode transitions + refusal + commit_level
2. Budget enforcement invariants (time/tokens/cost)
3. "Unknown outcome = fail closed" patterns
4. Premise invalidation cascades
5. Confidence bounds and provenance ordering

Strategy: use parameterized tests to fuzz the combinatorics that unit
tests don't enumerate. Not full Hypothesis — targeted property checks.
"""

import itertools
import pytest
from datetime import datetime, timedelta

from governor.epistemic import (
    EpistemicLedger,
    GroundedClaim,
    GroundedClaimStatus,
    Provenance,
    EvidenceRef,
    EvidenceType,
    ClaimStatus,
    TransitionReason,
    CascadeEvent,
    PremiseCheckResult,
    is_valid_transition,
    MAX_PEER_CONFIDENCE,
    HIGH_CONFIDENCE_THRESHOLD,
    DEFAULT_CONFIDENCE,
    VALID_TRANSITIONS,
)
from governor.execution import (
    ExecutionBudget,
    ExecutionUsage,
    ExecutionState,
    ExecutionStatus,
    StopReason,
)
from governor.invariants import (
    Invariant,
    InvariantType,
    InvariantResult,
    InvariantSet,
    InvariantLibrary,
)
from governor.executor import (
    AutonomousExecutor,
    ExecutorConfig,
    StepResult,
)
from governor.strict import ClaimCategory, CommitLevel


# =============================================================================
# 1. Confidence bounds: always [0, 1]
# =============================================================================


class TestConfidenceBounds:
    """Confidence must always be clamped to [0, 1]."""

    @pytest.mark.parametrize("raw_conf", [-1.0, -0.5, 0.0, 0.3, 0.5, 0.7, 1.0, 1.5, 100.0])
    def test_confidence_always_clamped(self, raw_conf):
        """No matter the input, confidence is in [0, 1]."""
        claim = GroundedClaim(
            claim_id="c_test",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=raw_conf,
        )
        assert 0.0 <= claim.confidence <= 1.0

    @pytest.mark.parametrize("raw_conf", [0.5, 0.9, 1.0, 1.5])
    def test_peer_asserted_always_capped(self, raw_conf):
        """PEER_ASSERTED confidence is always <= MAX_PEER_CONFIDENCE."""
        claim = GroundedClaim(
            claim_id="c_peer",
            content="peer says",
            provenance=Provenance.PEER_ASSERTED,
            confidence=raw_conf,
        )
        assert claim.confidence <= MAX_PEER_CONFIDENCE

    @pytest.mark.parametrize("prov", list(Provenance))
    def test_default_confidence_in_valid_range(self, prov):
        """Default confidence for every provenance is in [0, 1]."""
        default = DEFAULT_CONFIDENCE.get(prov, 0.5)
        assert 0.0 <= default <= 1.0


# =============================================================================
# 2. Provenance ordering and grounding invariant
# =============================================================================


class TestProvenanceProperties:
    """Provenance hierarchy invariants."""

    @pytest.mark.parametrize("prov", list(Provenance))
    def test_grounding_is_boolean(self, prov):
        """is_grounded is always a bool."""
        assert isinstance(prov.is_grounded, bool)

    def test_grounded_provenances_are_known(self):
        """Exactly these provenances are grounded."""
        grounded = {p for p in Provenance if p.is_grounded}
        # At minimum OBSERVED and RETRIEVED should be grounded
        assert Provenance.OBSERVED in grounded
        assert Provenance.RETRIEVED in grounded

    def test_ungrounded_provenances_are_known(self):
        """ASSUMED and PEER_ASSERTED are never grounded."""
        assert not Provenance.ASSUMED.is_grounded
        assert not Provenance.PEER_ASSERTED.is_grounded


# =============================================================================
# 3. ClaimStatus FSM: transition properties
# =============================================================================


class TestClaimStatusFSMProperties:
    """Properties that must hold across ALL state transitions."""

    @pytest.mark.parametrize("from_status", [None] + list(ClaimStatus))
    @pytest.mark.parametrize("to_status", list(ClaimStatus))
    def test_human_always_valid(self, from_status, to_status):
        """HUMAN reason allows any transition."""
        valid, _ = is_valid_transition(from_status, to_status, TransitionReason.HUMAN)
        assert valid

    @pytest.mark.parametrize("status", list(ClaimStatus))
    def test_same_status_always_valid(self, status):
        """Transitioning to the same status is always allowed."""
        for reason in TransitionReason:
            valid, _ = is_valid_transition(status, status, reason)
            assert valid, f"Same-status {status}→{status} with {reason} should be valid"

    def test_terminal_states_block_non_human(self):
        """Terminal states (INVALIDATED, EXPIRED, REFUSED) only go to PROPOSED via HUMAN."""
        terminal = [ClaimStatus.INVALIDATED, ClaimStatus.EXPIRED, ClaimStatus.REFUSED]
        non_human_reasons = [r for r in TransitionReason if r != TransitionReason.HUMAN]

        for from_s in terminal:
            for to_s in ClaimStatus:
                if from_s == to_s:
                    continue  # Same-status always valid
                for reason in non_human_reasons:
                    valid, _ = is_valid_transition(from_s, to_s, reason)
                    if valid:
                        # If valid, it must be in the explicit VALID_TRANSITIONS table
                        key = (from_s, to_s)
                        assert key in VALID_TRANSITIONS

    def test_all_valid_transitions_have_at_least_one_reason(self):
        """Every defined transition has at least one allowed reason."""
        for (from_s, to_s), reasons in VALID_TRANSITIONS.items():
            assert len(reasons) > 0, f"Transition {from_s}→{to_s} has no allowed reasons"


# =============================================================================
# 4. Budget enforcement: exhaustion is deterministic
# =============================================================================


class TestBudgetEnforcementProperties:
    """Budget limits are always enforced consistently."""

    @pytest.mark.parametrize("dim,field,limit,used_val", [
        ("tokens", "tokens", 100, 100),
        ("tokens", "tokens", 100, 200),
        ("iterations", "iterations", 5, 5),
        ("iterations", "iterations", 5, 10),
        ("cost_usd", "cost_usd", 1.0, 1.0),
        ("cost_usd", "cost_usd", 1.0, 2.0),
    ])
    def test_at_or_over_limit_is_exhausted(self, dim, field, limit, used_val):
        """Budget is exhausted when usage meets or exceeds limit."""
        budget_kwargs = {f"max_{dim}": limit}
        budget = ExecutionBudget(**budget_kwargs)
        usage = ExecutionUsage(**{field: used_val})
        exhausted, _ = budget.is_exhausted(usage)
        assert exhausted is True

    @pytest.mark.parametrize("dim,field,limit,used_val", [
        ("tokens", "tokens", 100, 0),
        ("tokens", "tokens", 100, 99),
        ("iterations", "iterations", 5, 0),
        ("iterations", "iterations", 5, 4),
        ("cost_usd", "cost_usd", 1.0, 0.0),
        ("cost_usd", "cost_usd", 1.0, 0.99),
    ])
    def test_under_limit_is_not_exhausted(self, dim, field, limit, used_val):
        """Budget is not exhausted when usage is below limit."""
        budget_kwargs = {f"max_{dim}": limit}
        budget = ExecutionBudget(**budget_kwargs)
        usage = ExecutionUsage(**{field: used_val})
        exhausted, _ = budget.is_exhausted(usage)
        assert exhausted is False

    def test_none_limits_never_exhaust(self):
        """Unlimited dimensions (None) are never exhausted."""
        budget = ExecutionBudget()  # All None
        usage = ExecutionUsage(tokens=999999, iterations=999999, cost_usd=999999.0)
        exhausted, _ = budget.is_exhausted(usage)
        assert exhausted is False

    def test_remaining_never_negative(self):
        """Remaining budget is never negative."""
        budget = ExecutionBudget(max_tokens=10, max_iterations=5)
        usage = ExecutionUsage(tokens=100, iterations=50)  # Way over
        remaining = budget.remaining(usage)
        for v in remaining.values():
            assert v >= 0


# =============================================================================
# 5. Execution state: status transitions are monotonic
# =============================================================================


class TestExecutionStateProperties:
    """ExecutionState status transitions follow expected patterns."""

    def test_stop_sets_stopped_status(self):
        """Calling stop() always sets status to STOPPED."""
        for reason in StopReason:
            state = ExecutionState()
            state.stop(reason)
            assert state.status == ExecutionStatus.STOPPED
            assert state.stop_reason == reason

    def test_complete_sets_completed_status(self):
        """Calling complete() always sets COMPLETED + AGENT_COMPLETION."""
        state = ExecutionState()
        state.complete()
        assert state.status == ExecutionStatus.COMPLETED
        assert state.stop_reason == StopReason.AGENT_COMPLETION

    def test_pause_resume_cycle(self):
        """pause → resume returns to RUNNING."""
        state = ExecutionState()
        assert state.status == ExecutionStatus.RUNNING

        state.pause()
        assert state.status == ExecutionStatus.PAUSED

        state.resume()
        assert state.status == ExecutionStatus.RUNNING

    def test_resume_only_from_paused(self):
        """resume() only works from PAUSED status."""
        for status in ExecutionStatus:
            state = ExecutionState()
            state.status = status
            state.resume()
            if status == ExecutionStatus.PAUSED:
                assert state.status == ExecutionStatus.RUNNING
            else:
                assert state.status == status  # Unchanged

    @pytest.mark.parametrize("status", [ExecutionStatus.RUNNING, ExecutionStatus.PAUSED])
    def test_active_states(self, status):
        """RUNNING and PAUSED are active."""
        state = ExecutionState()
        state.status = status
        assert state.is_active is True

    @pytest.mark.parametrize("status", [ExecutionStatus.STOPPED, ExecutionStatus.COMPLETED])
    def test_inactive_states(self, status):
        """STOPPED and COMPLETED are not active."""
        state = ExecutionState()
        state.status = status
        assert state.is_active is False


# =============================================================================
# 6. Executor: fail-closed property
# =============================================================================


class TestFailClosedProperty:
    """Unknown outcomes must result in fail-closed behavior."""

    def test_exception_in_step_counted_as_failure(self):
        """Any exception type in step_fn counts toward failure limit."""
        exceptions = [
            ValueError("bad value"),
            TypeError("wrong type"),
            RuntimeError("runtime error"),
            TimeoutError("timeout"),
            OSError("io error"),
            KeyError("missing key"),
        ]
        for exc in exceptions:
            def step_raising(state, iteration, e=exc):
                raise e

            executor = AutonomousExecutor(
                config=ExecutorConfig(max_consecutive_failures=1),
            )
            state = executor.execute(
                step_fn=step_raising,
                task="Exception test",
                budget=ExecutionBudget(max_iterations=10),
            )
            assert state.status == ExecutionStatus.STOPPED
            assert state.stop_reason == StopReason.ERROR

    def test_blocking_invariant_stops_execution(self):
        """A blocking invariant violation always stops execution."""
        def always_fail(**kwargs):
            return InvariantResult(
                passed=False, message="Block", invariant_id="blocker",
            )

        inv_set = InvariantSet()
        inv_set.add(Invariant(
            id="blocker", type=InvariantType.FORBIDDEN,
            rule="Always blocks", verify=always_fail,
            on_violation="block",
        ))

        executor = AutonomousExecutor(
            invariants=inv_set,
            config=ExecutorConfig(stop_on_violation=True),
        )
        state = executor.execute(
            step_fn=lambda s, i: StepResult(success=True, message="ok"),
            task="Block test",
            budget=ExecutionBudget(max_iterations=10),
        )
        assert state.status == ExecutionStatus.STOPPED
        assert state.stop_reason == StopReason.CONSTRAINT_VIOLATION


# =============================================================================
# 7. Invariant set: blocking vs warning partitioning
# =============================================================================


class TestInvariantSetProperties:
    """InvariantSet correctly partitions blocking vs warning violations."""

    def _make_invariant(self, inv_id, passes, on_violation="block"):
        def verify(**kwargs):
            return InvariantResult(
                passed=passes, message=f"{'pass' if passes else 'fail'}",
                invariant_id=inv_id,
            )
        return Invariant(
            id=inv_id, type=InvariantType.CONSISTENCY,
            rule=f"Test rule {inv_id}", verify=verify,
            on_violation=on_violation,
        )

    def test_all_pass_means_no_blocking(self):
        """When all invariants pass, blocking_violations returns empty."""
        iset = InvariantSet()
        for i in range(5):
            iset.add(self._make_invariant(f"inv_{i}", passes=True))
        assert len(iset.blocking_violations()) == 0

    def test_warning_failures_not_in_blocking(self):
        """Warning-level failures never appear in blocking_violations."""
        iset = InvariantSet()
        iset.add(self._make_invariant("warn_fail", passes=False, on_violation="warn"))
        assert len(iset.blocking_violations()) == 0

    def test_block_failures_in_blocking(self):
        """Block-level failures appear in blocking_violations."""
        iset = InvariantSet()
        iset.add(self._make_invariant("block_fail", passes=False, on_violation="block"))
        blocking = iset.blocking_violations()
        assert len(blocking) == 1
        assert blocking[0].invariant_id == "block_fail"

    def test_disabled_invariants_skipped(self):
        """Disabled invariants are never checked."""
        iset = InvariantSet()
        inv = self._make_invariant("disabled", passes=False, on_violation="block")
        inv.enabled = False
        iset.add(inv)
        assert len(iset.check_all()) == 0

    @pytest.mark.parametrize("n_pass,n_fail_block,n_fail_warn", [
        (5, 0, 0),
        (3, 2, 0),
        (3, 0, 2),
        (1, 2, 3),
        (0, 5, 0),
    ])
    def test_blocking_count_matches(self, n_pass, n_fail_block, n_fail_warn):
        """Number of blocking violations equals number of failed block invariants."""
        iset = InvariantSet()
        for i in range(n_pass):
            iset.add(self._make_invariant(f"pass_{i}", passes=True))
        for i in range(n_fail_block):
            iset.add(self._make_invariant(f"block_{i}", passes=False, on_violation="block"))
        for i in range(n_fail_warn):
            iset.add(self._make_invariant(f"warn_{i}", passes=False, on_violation="warn"))

        blocking = iset.blocking_violations()
        assert len(blocking) == n_fail_block


# =============================================================================
# 8. Premise rule: cascade depth property
# =============================================================================


class TestCascadeProperties:
    """Dependency cascades must terminate and be bounded."""

    def test_cascade_terminates_on_chain(self):
        """Linear dependency chain: cascade terminates at the end."""
        ledger = EpistemicLedger()
        claims = []
        for i in range(10):
            c = ledger.new_claim(f"Claim {i}", Provenance.OBSERVED)
            c.commit_level = "hard"
            claims.append(c)

        # Chain: 0 ← 1 ← 2 ← ... ← 9
        for i in range(1, 10):
            ledger.add_dependency(claims[i].claim_id, claims[i-1].claim_id)

        # Retract the root
        ledger.retract(claims[0].claim_id, reason="Root invalidated")

        # All dependents should be downgraded to soft
        for c in claims[1:]:
            assert ledger.claims[c.claim_id].commit_level == "soft"

    def test_cascade_handles_diamond(self):
        """Diamond dependency graph: no double-processing."""
        ledger = EpistemicLedger()
        root = ledger.new_claim("Root", Provenance.OBSERVED)
        root.commit_level = "hard"

        left = ledger.new_claim("Left", Provenance.OBSERVED)
        left.commit_level = "hard"
        right = ledger.new_claim("Right", Provenance.OBSERVED)
        right.commit_level = "hard"

        bottom = ledger.new_claim("Bottom", Provenance.OBSERVED)
        bottom.commit_level = "hard"

        # Diamond: root → left → bottom, root → right → bottom
        ledger.add_dependency(left.claim_id, root.claim_id)
        ledger.add_dependency(right.claim_id, root.claim_id)
        ledger.add_dependency(bottom.claim_id, left.claim_id)
        ledger.add_dependency(bottom.claim_id, right.claim_id)

        ledger.retract(root.claim_id, reason="Root gone")

        # All should be downgraded
        assert ledger.claims[left.claim_id].commit_level == "soft"
        assert ledger.claims[right.claim_id].commit_level == "soft"
        assert ledger.claims[bottom.claim_id].commit_level == "soft"

    def test_soft_claims_not_affected_by_cascade(self):
        """SOFT claims are already at minimum — cascade doesn't touch them."""
        ledger = EpistemicLedger()
        root = ledger.new_claim("Root", Provenance.OBSERVED)
        root.commit_level = "hard"

        soft_child = ledger.new_claim("Soft child", Provenance.ASSUMED)
        soft_child.commit_level = "soft"

        ledger.add_dependency(soft_child.claim_id, root.claim_id)

        ledger.retract(root.claim_id, reason="Gone")

        # Soft child stays soft (was already at minimum)
        assert ledger.claims[soft_child.claim_id].commit_level == "soft"


# =============================================================================
# 9. Serialization roundtrip property
# =============================================================================


class TestSerializationRoundtrip:
    """to_dict → from_dict is lossless for critical fields."""

    @pytest.mark.parametrize("prov", list(Provenance))
    def test_grounded_claim_roundtrip_per_provenance(self, prov):
        """GroundedClaim roundtrips for every provenance type."""
        claim = GroundedClaim(
            claim_id=f"c_{prov.value}",
            content=f"Claim with {prov.value}",
            provenance=prov,
            confidence=DEFAULT_CONFIDENCE.get(prov, 0.5),
        )
        d = claim.to_dict()
        restored = GroundedClaim.from_dict(d)
        assert restored.claim_id == claim.claim_id
        assert restored.provenance == claim.provenance
        assert restored.confidence == claim.confidence

    @pytest.mark.parametrize("status", list(ExecutionStatus))
    def test_execution_state_roundtrip_per_status(self, status):
        """ExecutionState roundtrips for every status."""
        state = ExecutionState(
            session_id="test",
            task="test task",
            status=status,
        )
        d = state.to_dict()
        restored = ExecutionState.from_dict(d)
        assert restored.status == status

    @pytest.mark.parametrize("reason", list(StopReason))
    def test_execution_state_roundtrip_per_stop_reason(self, reason):
        """ExecutionState roundtrips for every stop reason."""
        state = ExecutionState(session_id="test", task="test")
        state.stop(reason)
        d = state.to_dict()
        restored = ExecutionState.from_dict(d)
        assert restored.stop_reason == reason

    @pytest.mark.parametrize("et", list(EvidenceType))
    def test_evidence_ref_roundtrip_per_type(self, et):
        """EvidenceRef roundtrips for every evidence type."""
        ref = EvidenceRef(
            ref_id=f"ev_{et.value}",
            ref_type=et,
            locator=f"locator_{et.value}",
            scope="test",
        )
        d = ref.to_dict()
        restored = EvidenceRef.from_dict(d)
        assert restored.ref_type == et
        assert restored.locator == ref.locator
