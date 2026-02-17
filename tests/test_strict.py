# SPDX-License-Identifier: Apache-2.0
"""Tests for strict programmer mode — fail-closed governance."""

import pytest

from governor.strict import (
    ClaimCategory,
    CommitLevel,
    RiskLevel,
    ClaimRequirement,
    DEFAULT_REQUIREMENTS,
    DependencyContext,
    StrictPolicy,
    ClaimEvaluation,
    StrictModeGate,
    create_strict_policy,
    create_strict_setpoints,
    create_strict_boil_preset,
    create_strict_s1_overrides,
    create_strict_gate,
    quick_evaluate,
)


# =====================================================================
# Enums
# =====================================================================

class TestClaimCategory:
    def test_all_members(self):
        assert set(ClaimCategory) == {
            ClaimCategory.STATIC_FACT,
            ClaimCategory.VOLATILE_FACT,
            ClaimCategory.CODE,
            ClaimCategory.PROCEDURE,
            ClaimCategory.JUDGMENT,
            ClaimCategory.PLAN,
        }

    def test_string_values(self):
        assert ClaimCategory.STATIC_FACT.value == "static_fact"
        assert ClaimCategory.VOLATILE_FACT.value == "volatile_fact"
        assert ClaimCategory.CODE.value == "code"
        assert ClaimCategory.PROCEDURE.value == "procedure"
        assert ClaimCategory.JUDGMENT.value == "judgment"
        assert ClaimCategory.PLAN.value == "plan"

    def test_is_str_enum(self):
        assert isinstance(ClaimCategory.CODE, str)
        assert ClaimCategory.CODE == "code"


class TestCommitLevel:
    def test_all_members(self):
        assert set(CommitLevel) == {
            CommitLevel.HARD,
            CommitLevel.SOFT,
            CommitLevel.REFUSED,
        }

    def test_string_values(self):
        assert CommitLevel.HARD.value == "hard"
        assert CommitLevel.SOFT.value == "soft"
        assert CommitLevel.REFUSED.value == "refused"


class TestRiskLevel:
    def test_all_members(self):
        assert set(RiskLevel) == {
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
        }

    def test_string_values(self):
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"


# =====================================================================
# ClaimRequirement
# =====================================================================

class TestClaimRequirement:
    def test_defaults(self):
        req = ClaimRequirement(category=ClaimCategory.CODE)
        assert req.min_evidence_count == 1
        assert req.min_independence == 0.5
        assert req.requires_source is False
        assert req.requires_version is False
        assert req.requires_ttl is False
        assert req.requires_prerequisites is False
        assert req.requires_runnable is False
        assert req.falsifier_required is False

    def test_check_all_satisfied(self):
        req = ClaimRequirement(
            category=ClaimCategory.STATIC_FACT,
            min_evidence_count=1,
            min_independence=0.5,
            requires_source=True,
            requires_version=True,
        )
        satisfied, unsatisfied = req.check(
            evidence_count=2,
            independence_score=0.6,
            has_source=True,
            has_version=True,
        )
        assert len(unsatisfied) == 0
        assert len(satisfied) > 0

    def test_check_evidence_unsatisfied(self):
        req = ClaimRequirement(
            category=ClaimCategory.STATIC_FACT,
            min_evidence_count=3,
            min_independence=0.0,
        )
        satisfied, unsatisfied = req.check(evidence_count=1)
        assert "evidence_count>=3" in unsatisfied

    def test_check_independence_unsatisfied(self):
        req = ClaimRequirement(
            category=ClaimCategory.STATIC_FACT,
            min_evidence_count=0,
            min_independence=0.8,
        )
        satisfied, unsatisfied = req.check(independence_score=0.5)
        assert "independence>=0.8" in unsatisfied

    def test_check_source_requirements(self):
        req = ClaimRequirement(
            category=ClaimCategory.STATIC_FACT,
            min_evidence_count=0,
            min_independence=0.0,
            requires_source=True,
            requires_version=True,
            requires_verification_date=True,
        )
        satisfied, unsatisfied = req.check(
            has_source=False,
            has_version=True,
            has_verification_date=False,
        )
        assert "requires_source" in unsatisfied
        assert "requires_version" in satisfied
        assert "requires_verification_date" in unsatisfied

    def test_check_ttl_requirements(self):
        req = ClaimRequirement(
            category=ClaimCategory.VOLATILE_FACT,
            min_evidence_count=0,
            min_independence=0.0,
            requires_ttl=True,
            max_ttl_hours=24.0,
        )
        # TTL present and within limit
        satisfied, unsatisfied = req.check(has_ttl=True, ttl_hours=12.0)
        assert "requires_ttl" in satisfied
        assert "ttl<=24.0h" in satisfied

    def test_check_ttl_exceeded(self):
        req = ClaimRequirement(
            category=ClaimCategory.VOLATILE_FACT,
            min_evidence_count=0,
            min_independence=0.0,
            requires_ttl=True,
            max_ttl_hours=24.0,
        )
        satisfied, unsatisfied = req.check(has_ttl=True, ttl_hours=48.0)
        assert "requires_ttl" in satisfied
        assert "ttl<=24.0h" in unsatisfied

    def test_check_procedure_requirements(self):
        req = ClaimRequirement(
            category=ClaimCategory.PROCEDURE,
            min_evidence_count=0,
            min_independence=0.0,
            requires_prerequisites=True,
            requires_failure_modes=True,
            requires_rollback=True,
            requires_platform_context=True,
            falsifier_required=True,
        )
        satisfied, unsatisfied = req.check(
            has_prerequisites=True,
            has_failure_modes=True,
            has_rollback=False,
            has_platform_context=True,
            falsifier_ran=False,
        )
        assert "requires_prerequisites" in satisfied
        assert "requires_failure_modes" in satisfied
        assert "requires_rollback" in unsatisfied
        assert "requires_platform_context" in satisfied
        assert "falsifier_required" in unsatisfied

    def test_check_code_runnable(self):
        req = ClaimRequirement(
            category=ClaimCategory.CODE,
            min_evidence_count=0,
            min_independence=0.0,
            requires_runnable=True,
        )
        # Runnable satisfies
        s, u = req.check(is_runnable=True)
        assert "runnable_or_pseudocode" in s

        # Pseudocode label satisfies
        s2, u2 = req.check(is_labeled_pseudocode=True)
        assert "runnable_or_pseudocode" in s2

        # Neither
        s3, u3 = req.check()
        assert "runnable_or_pseudocode" in u3

    def test_serialization_roundtrip(self):
        req = ClaimRequirement(
            category=ClaimCategory.PROCEDURE,
            min_evidence_count=3,
            min_independence=0.7,
            requires_prerequisites=True,
            requires_rollback=True,
        )
        d = req.to_dict()
        restored = ClaimRequirement.from_dict(d)
        assert restored.category == ClaimCategory.PROCEDURE
        assert restored.min_evidence_count == 3
        assert restored.min_independence == 0.7
        assert restored.requires_prerequisites is True
        assert restored.requires_rollback is True


# =====================================================================
# DEFAULT_REQUIREMENTS
# =====================================================================

class TestDefaultRequirements:
    def test_all_categories_present(self):
        for cat in ClaimCategory:
            assert cat in DEFAULT_REQUIREMENTS

    def test_static_fact_requirements(self):
        req = DEFAULT_REQUIREMENTS[ClaimCategory.STATIC_FACT]
        assert req.min_evidence_count == 2
        assert req.min_independence == 0.55
        assert req.requires_source is True
        assert req.requires_version is True
        assert req.requires_verification_date is True

    def test_volatile_fact_requirements(self):
        req = DEFAULT_REQUIREMENTS[ClaimCategory.VOLATILE_FACT]
        assert req.min_evidence_count == 2
        assert req.requires_source is True
        assert req.requires_ttl is True
        assert req.max_ttl_hours == 24.0

    def test_code_requirements(self):
        req = DEFAULT_REQUIREMENTS[ClaimCategory.CODE]
        assert req.min_evidence_count == 1
        assert req.requires_runnable is True
        assert req.requires_version is True

    def test_procedure_requirements(self):
        req = DEFAULT_REQUIREMENTS[ClaimCategory.PROCEDURE]
        assert req.min_evidence_count == 2
        assert req.min_independence == 0.6
        assert req.requires_prerequisites is True
        assert req.requires_failure_modes is True
        assert req.requires_rollback is True
        assert req.requires_platform_context is True
        assert req.falsifier_required is True

    def test_judgment_minimal(self):
        req = DEFAULT_REQUIREMENTS[ClaimCategory.JUDGMENT]
        assert req.min_evidence_count == 0
        assert req.min_independence == 0.0

    def test_plan_minimal(self):
        req = DEFAULT_REQUIREMENTS[ClaimCategory.PLAN]
        assert req.min_evidence_count == 0
        assert req.min_independence == 0.0


# =====================================================================
# DependencyContext
# =====================================================================

class TestDependencyContext:
    def test_empty_context(self):
        ctx = DependencyContext()
        assert ctx.is_specified is False
        assert ctx.completeness == 0.0

    def test_partial_context(self):
        ctx = DependencyContext(os="linux", language="python")
        assert ctx.is_specified is True
        assert ctx.completeness == 2 / 5  # 2 of 5 fields

    def test_full_context(self):
        ctx = DependencyContext(
            os="linux",
            distro="ubuntu",
            language="python",
            language_version="3.12",
            runtime="cpython",
        )
        assert ctx.completeness == 1.0

    def test_permissions(self):
        ctx = DependencyContext(os="linux", permissions=["root", "docker"])
        assert ctx.permissions == ["root", "docker"]

    def test_serialization_roundtrip(self):
        ctx = DependencyContext(
            os="linux", distro="ubuntu", language="python",
            language_version="3.12", runtime="cpython",
            permissions=["root"],
        )
        d = ctx.to_dict()
        restored = DependencyContext.from_dict(d)
        assert restored.os == "linux"
        assert restored.distro == "ubuntu"
        assert restored.language_version == "3.12"
        assert restored.permissions == ["root"]


# =====================================================================
# StrictPolicy
# =====================================================================

class TestStrictPolicy:
    def test_defaults(self):
        policy = StrictPolicy()
        assert policy.k_increase == 1
        assert policy.independence_boost == 0.05
        assert policy.speculative_facts_allowed is False
        assert policy.hard_threshold == 1.0
        assert policy.soft_threshold == 0.5
        assert ClaimCategory.JUDGMENT in policy.soft_only
        assert ClaimCategory.PLAN in policy.soft_only

    def test_get_requirement_known_category(self):
        policy = StrictPolicy()
        req = policy.get_requirement(ClaimCategory.CODE)
        assert req.category == ClaimCategory.CODE
        assert req.requires_runnable is True

    def test_get_requirement_uses_defaults(self):
        policy = StrictPolicy()
        req = policy.get_requirement(ClaimCategory.STATIC_FACT)
        assert req.min_evidence_count == 2
        assert req.requires_source is True

    def test_risk_adjusted_low_no_change(self):
        policy = StrictPolicy()
        base = policy.get_requirement(ClaimCategory.CODE)
        adjusted = policy.get_risk_adjusted(ClaimCategory.CODE, RiskLevel.LOW)
        assert adjusted.min_evidence_count == base.min_evidence_count
        assert adjusted.min_independence == base.min_independence

    def test_risk_adjusted_medium(self):
        policy = StrictPolicy()
        base = policy.get_requirement(ClaimCategory.CODE)
        adjusted = policy.get_risk_adjusted(ClaimCategory.CODE, RiskLevel.MEDIUM)
        assert adjusted.min_evidence_count == base.min_evidence_count + 1
        assert adjusted.min_independence == base.min_independence + 0.05

    def test_risk_adjusted_high_requires_falsifier(self):
        policy = StrictPolicy()
        adjusted = policy.get_risk_adjusted(ClaimCategory.CODE, RiskLevel.HIGH)
        assert adjusted.falsifier_required is True
        assert adjusted.min_evidence_count == DEFAULT_REQUIREMENTS[ClaimCategory.CODE].min_evidence_count + 1

    def test_independence_boost_clamped_to_1(self):
        policy = StrictPolicy(independence_boost=0.6)
        adjusted = policy.get_risk_adjusted(ClaimCategory.PROCEDURE, RiskLevel.MEDIUM)
        # Procedure has 0.6 + 0.6 = 1.2, clamped to 1.0
        assert adjusted.min_independence == 1.0

    def test_serialization_roundtrip(self):
        policy = StrictPolicy(
            k_increase=2,
            independence_boost=0.1,
            speculative_facts_allowed=True,
            hard_threshold=0.95,
        )
        d = policy.to_dict()
        restored = StrictPolicy.from_dict(d)
        assert restored.k_increase == 2
        assert restored.independence_boost == 0.1
        assert restored.speculative_facts_allowed is True
        assert restored.hard_threshold == 0.95

    def test_serialization_preserves_soft_only(self):
        policy = StrictPolicy()
        d = policy.to_dict()
        restored = StrictPolicy.from_dict(d)
        assert ClaimCategory.JUDGMENT in restored.soft_only
        assert ClaimCategory.PLAN in restored.soft_only


# =====================================================================
# ClaimEvaluation
# =====================================================================

class TestClaimEvaluation:
    def test_is_hard(self):
        ev = ClaimEvaluation(
            category=ClaimCategory.CODE,
            risk=RiskLevel.LOW,
            commit_level=CommitLevel.HARD,
            satisfied=["a", "b"],
            unsatisfied=[],
            satisfaction_ratio=1.0,
            recommendation="ok",
        )
        assert ev.is_hard is True
        assert ev.is_refused is False

    def test_is_refused(self):
        ev = ClaimEvaluation(
            category=ClaimCategory.PROCEDURE,
            risk=RiskLevel.HIGH,
            commit_level=CommitLevel.REFUSED,
            satisfied=[],
            unsatisfied=["a", "b"],
            satisfaction_ratio=0.0,
            recommendation="no",
            refusal_message="can't do it",
        )
        assert ev.is_refused is True
        assert ev.is_hard is False

    def test_serialization_roundtrip(self):
        ev = ClaimEvaluation(
            category=ClaimCategory.VOLATILE_FACT,
            risk=RiskLevel.MEDIUM,
            commit_level=CommitLevel.SOFT,
            satisfied=["evidence_count>=2"],
            unsatisfied=["requires_ttl"],
            satisfaction_ratio=0.5,
            recommendation="soft",
            refusal_message="needs TTL",
        )
        d = ev.to_dict()
        restored = ClaimEvaluation.from_dict(d)
        assert restored.category == ClaimCategory.VOLATILE_FACT
        assert restored.risk == RiskLevel.MEDIUM
        assert restored.commit_level == CommitLevel.SOFT
        assert restored.satisfied == ["evidence_count>=2"]
        assert restored.unsatisfied == ["requires_ttl"]
        assert restored.refusal_message == "needs TTL"


# =====================================================================
# StrictModeGate — Soft-only categories
# =====================================================================

class TestGateSoftOnly:
    def test_judgment_always_soft(self):
        gate = StrictModeGate()
        result = gate.evaluate(ClaimCategory.JUDGMENT)
        assert result.commit_level == CommitLevel.SOFT
        assert result.satisfaction_ratio == 1.0

    def test_plan_always_soft(self):
        gate = StrictModeGate()
        result = gate.evaluate(ClaimCategory.PLAN)
        assert result.commit_level == CommitLevel.SOFT

    def test_judgment_soft_regardless_of_evidence(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.JUDGMENT,
            evidence_count=100,
            independence_score=1.0,
            has_source=True,
        )
        assert result.commit_level == CommitLevel.SOFT

    def test_plan_soft_at_high_risk(self):
        gate = StrictModeGate()
        result = gate.evaluate(ClaimCategory.PLAN, RiskLevel.HIGH)
        assert result.commit_level == CommitLevel.SOFT


# =====================================================================
# StrictModeGate — HARD commit
# =====================================================================

class TestGateHardCommit:
    def test_static_fact_hard(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.STATIC_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=True,
            has_version=True,
            has_verification_date=True,
        )
        assert result.commit_level == CommitLevel.HARD
        assert len(result.unsatisfied) == 0
        assert result.satisfaction_ratio == 1.0

    def test_code_hard(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        assert result.commit_level == CommitLevel.HARD

    def test_code_hard_with_pseudocode(self):
        """Pseudocode label is an alternative to runnable."""
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
            is_labeled_pseudocode=True,
            has_version=True,
        )
        assert result.commit_level == CommitLevel.HARD

    def test_volatile_fact_hard(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.VOLATILE_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=True,
            has_ttl=True,
            ttl_hours=12.0,
        )
        assert result.commit_level == CommitLevel.HARD

    def test_procedure_hard(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.PROCEDURE,
            evidence_count=2,
            independence_score=0.6,
            has_prerequisites=True,
            has_failure_modes=True,
            has_rollback=True,
            has_platform_context=True,
            falsifier_ran=True,
        )
        assert result.commit_level == CommitLevel.HARD


# =====================================================================
# StrictModeGate — SOFT commit
# =====================================================================

class TestGateSoftCommit:
    def test_static_fact_missing_source(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.STATIC_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=False,
            has_version=True,
            has_verification_date=True,
        )
        # 4/5 = 0.8, above soft_threshold=0.5
        assert result.commit_level == CommitLevel.SOFT
        assert "requires_source" in result.unsatisfied
        assert result.refusal_message != ""

    def test_code_not_runnable(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=False,
            has_version=True,
        )
        # 3/4 = 0.75, above 0.5
        assert result.commit_level == CommitLevel.SOFT

    def test_procedure_missing_rollback(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.PROCEDURE,
            evidence_count=2,
            independence_score=0.6,
            has_prerequisites=True,
            has_failure_modes=True,
            has_rollback=False,
            has_platform_context=True,
            falsifier_ran=True,
        )
        # 6/7 ≈ 0.857 — above soft threshold
        assert result.commit_level == CommitLevel.SOFT
        assert "requires_rollback" in result.unsatisfied

    def test_volatile_fact_ttl_exceeded(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.VOLATILE_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=True,
            has_ttl=True,
            ttl_hours=48.0,  # exceeds 24h max
        )
        # TTL present but too long — one requirement unsatisfied
        assert result.commit_level == CommitLevel.SOFT


# =====================================================================
# StrictModeGate — REFUSED
# =====================================================================

class TestGateRefused:
    def test_static_fact_no_evidence(self):
        gate = StrictModeGate()
        result = gate.evaluate(ClaimCategory.STATIC_FACT)
        # Nothing provided → all unsatisfied → ratio 0 < 0.5
        assert result.commit_level == CommitLevel.REFUSED
        assert result.refusal_message != ""

    def test_procedure_nothing_provided(self):
        gate = StrictModeGate()
        result = gate.evaluate(ClaimCategory.PROCEDURE)
        assert result.commit_level == CommitLevel.REFUSED

    def test_code_nothing_provided(self):
        gate = StrictModeGate()
        result = gate.evaluate(ClaimCategory.CODE)
        # 0 evidence, 0 independence, not runnable, no version → 0/4
        assert result.commit_level == CommitLevel.REFUSED

    def test_volatile_fact_nothing_provided(self):
        gate = StrictModeGate()
        result = gate.evaluate(ClaimCategory.VOLATILE_FACT)
        assert result.commit_level == CommitLevel.REFUSED


# =====================================================================
# StrictModeGate — Risk adjustment
# =====================================================================

class TestGateRiskAdjustment:
    def test_medium_risk_raises_bar(self):
        gate = StrictModeGate()
        # CODE at LOW: needs 1 evidence, 0.5 independence
        r_low = gate.evaluate(
            ClaimCategory.CODE,
            RiskLevel.LOW,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        assert r_low.commit_level == CommitLevel.HARD

        # Same evidence at MEDIUM: needs 2 evidence, 0.55 independence
        r_med = gate.evaluate(
            ClaimCategory.CODE,
            RiskLevel.MEDIUM,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        # Fails on evidence_count>=2 and independence>=0.55
        assert r_med.commit_level != CommitLevel.HARD

    def test_high_risk_requires_falsifier(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.CODE,
            RiskLevel.HIGH,
            evidence_count=2,
            independence_score=0.55,
            is_runnable=True,
            has_version=True,
            falsifier_ran=False,
        )
        assert "falsifier_required" in result.unsatisfied
        assert result.commit_level != CommitLevel.HARD

    def test_high_risk_with_falsifier(self):
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.CODE,
            RiskLevel.HIGH,
            evidence_count=2,
            independence_score=0.55,
            is_runnable=True,
            has_version=True,
            falsifier_ran=True,
        )
        assert result.commit_level == CommitLevel.HARD


# =====================================================================
# StrictModeGate — format_refusal
# =====================================================================

class TestFormatRefusal:
    def test_hard_returns_empty(self):
        gate = StrictModeGate()
        ev = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        assert gate.format_refusal(ev) == ""

    def test_soft_returns_refusal_message(self):
        gate = StrictModeGate()
        ev = gate.evaluate(ClaimCategory.STATIC_FACT)
        msg = gate.format_refusal(ev)
        assert msg != ""

    def test_soft_only_returns_generic(self):
        gate = StrictModeGate()
        ev = gate.evaluate(ClaimCategory.JUDGMENT)
        # JUDGMENT is SOFT but has no refusal_message
        msg = gate.format_refusal(ev)
        assert "judgment" in msg.lower()


# =====================================================================
# StrictModeGate — Query methods
# =====================================================================

class TestGateQuery:
    def test_history_starts_empty(self):
        gate = StrictModeGate()
        assert gate.total_evaluations == 0
        assert gate.history == []

    def test_history_accumulates(self):
        gate = StrictModeGate()
        gate.evaluate(ClaimCategory.JUDGMENT)
        gate.evaluate(ClaimCategory.PLAN)
        gate.evaluate(ClaimCategory.CODE)
        assert gate.total_evaluations == 3
        assert len(gate.history) == 3

    def test_history_is_copy(self):
        gate = StrictModeGate()
        gate.evaluate(ClaimCategory.JUDGMENT)
        h = gate.history
        h.clear()
        assert gate.total_evaluations == 1

    def test_refusal_rate_empty(self):
        gate = StrictModeGate()
        assert gate.refusal_rate() == 0.0

    def test_refusal_rate(self):
        gate = StrictModeGate()
        # 2 refusals
        gate.evaluate(ClaimCategory.STATIC_FACT)
        gate.evaluate(ClaimCategory.CODE)
        # 1 soft
        gate.evaluate(ClaimCategory.JUDGMENT)
        assert gate.refusal_rate() == pytest.approx(2 / 3)

    def test_hard_rate(self):
        gate = StrictModeGate()
        gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        gate.evaluate(ClaimCategory.JUDGMENT)
        assert gate.hard_rate() == pytest.approx(1 / 2)

    def test_stats_empty(self):
        gate = StrictModeGate()
        s = gate.stats()
        assert s == {"total": 0, "hard": 0, "soft": 0, "refused": 0}

    def test_stats_counts(self):
        gate = StrictModeGate()
        # HARD
        gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        # SOFT (judgment)
        gate.evaluate(ClaimCategory.JUDGMENT)
        # REFUSED (no evidence)
        gate.evaluate(ClaimCategory.STATIC_FACT)
        s = gate.stats()
        assert s["total"] == 3
        assert s["hard"] == 1
        assert s["soft"] == 1
        assert s["refused"] == 1
        assert s["hard_rate"] == pytest.approx(1 / 3)
        assert s["soft_rate"] == pytest.approx(1 / 3)
        assert s["refusal_rate"] == pytest.approx(1 / 3)


# =====================================================================
# StrictModeGate — Diagnostics
# =====================================================================

class TestGateDiagnostics:
    def test_diagnostics_structure(self):
        gate = StrictModeGate()
        gate.evaluate(ClaimCategory.CODE)
        diag = gate.get_diagnostics()
        assert "policy" in diag
        assert "stats" in diag
        assert "recent_evaluations" in diag
        assert len(diag["recent_evaluations"]) == 1

    def test_diagnostics_recent_capped(self):
        gate = StrictModeGate()
        for _ in range(15):
            gate.evaluate(ClaimCategory.JUDGMENT)
        diag = gate.get_diagnostics()
        assert len(diag["recent_evaluations"]) == 10  # capped at 10


# =====================================================================
# StrictModeGate — Serialization
# =====================================================================

class TestGateSerialization:
    def test_roundtrip(self):
        gate = StrictModeGate()
        gate.evaluate(ClaimCategory.CODE)
        gate.evaluate(ClaimCategory.JUDGMENT)
        d = gate.to_dict()
        restored = StrictModeGate.from_dict(d)
        assert restored.total_evaluations == 2
        assert restored.policy.hard_threshold == 1.0

    def test_roundtrip_preserves_evaluations(self):
        gate = StrictModeGate()
        gate.evaluate(
            ClaimCategory.STATIC_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=True,
            has_version=True,
            has_verification_date=True,
        )
        d = gate.to_dict()
        restored = StrictModeGate.from_dict(d)
        ev = restored.history[0]
        assert ev.category == ClaimCategory.STATIC_FACT
        assert ev.commit_level == CommitLevel.HARD

    def test_roundtrip_custom_policy(self):
        policy = StrictPolicy(k_increase=3, hard_threshold=0.9)
        gate = StrictModeGate(policy=policy)
        d = gate.to_dict()
        restored = StrictModeGate.from_dict(d)
        assert restored.policy.k_increase == 3
        assert restored.policy.hard_threshold == 0.9


# =====================================================================
# StrictModeGate — Reset
# =====================================================================

class TestGateReset:
    def test_reset_clears_history(self):
        gate = StrictModeGate()
        gate.evaluate(ClaimCategory.CODE)
        gate.evaluate(ClaimCategory.JUDGMENT)
        assert gate.total_evaluations == 2
        gate.reset()
        assert gate.total_evaluations == 0
        assert gate.history == []


# =====================================================================
# StrictModeGate — Custom policy
# =====================================================================

class TestGateCustomPolicy:
    def test_lower_hard_threshold(self):
        """With 0.8 hard_threshold, 4/5 is enough for HARD."""
        policy = StrictPolicy(hard_threshold=0.8)
        gate = StrictModeGate(policy=policy)
        result = gate.evaluate(
            ClaimCategory.STATIC_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=True,
            has_version=True,
            has_verification_date=False,  # 1 missing out of 5
        )
        # 4/5 = 0.8 >= 0.8
        assert result.commit_level == CommitLevel.HARD

    def test_higher_soft_threshold(self):
        """With higher soft_threshold, fewer things qualify even as SOFT."""
        policy = StrictPolicy(soft_threshold=0.9)
        gate = StrictModeGate(policy=policy)
        result = gate.evaluate(
            ClaimCategory.STATIC_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=False,
            has_version=False,
            has_verification_date=False,
        )
        # 2/5 = 0.4 < 0.9 → REFUSED
        assert result.commit_level == CommitLevel.REFUSED

    def test_custom_soft_only(self):
        """CODE can be made soft-only."""
        policy = StrictPolicy(
            soft_only={ClaimCategory.CODE, ClaimCategory.JUDGMENT, ClaimCategory.PLAN},
        )
        gate = StrictModeGate(policy=policy)
        result = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=100,
            independence_score=1.0,
            is_runnable=True,
            has_version=True,
        )
        assert result.commit_level == CommitLevel.SOFT


# =====================================================================
# Integration helpers
# =====================================================================

class TestIntegrationHelpers:
    def test_create_strict_policy(self):
        policy = create_strict_policy()
        assert isinstance(policy, StrictPolicy)
        assert policy.hard_threshold == 1.0

    def test_create_strict_setpoints(self):
        sp = create_strict_setpoints()
        from governor.homeostat import EpistemicSetpoints
        assert isinstance(sp, EpistemicSetpoints)
        assert sp.revision_target == 0.02
        assert sp.contradiction_target == 0.01
        assert sp.hedge_target == 0.25
        assert sp.refusal_target == 0.05

    def test_create_strict_boil_preset(self):
        preset = create_strict_boil_preset()
        assert isinstance(preset, dict)
        assert preset["claim_budget_per_turn"] == 5
        assert preset["novelty_tolerance"] == 0.1
        assert preset["authority_posture"] == "strict"

    def test_create_strict_s1_overrides(self):
        overrides = create_strict_s1_overrides()
        assert isinstance(overrides, dict)
        assert overrides["evidence_threshold"] == 0.85
        assert overrides["independence_threshold"] == 0.7
        assert overrides["glass_threshold"] == 10.0
        assert "repair_budget" in overrides
        assert "refill_rate" in overrides

    def test_create_strict_gate(self):
        gate = create_strict_gate()
        assert isinstance(gate, StrictModeGate)
        assert gate.total_evaluations == 0

    def test_quick_evaluate(self):
        result = quick_evaluate(
            ClaimCategory.CODE,
            RiskLevel.LOW,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        assert result.commit_level == CommitLevel.HARD

    def test_quick_evaluate_refused(self):
        result = quick_evaluate(ClaimCategory.PROCEDURE)
        assert result.commit_level == CommitLevel.REFUSED


# =====================================================================
# End-to-end scenarios
# =====================================================================

class TestE2E:
    def test_production_command_evaluation(self):
        """Simulate evaluating a production command (procedure)."""
        gate = StrictModeGate()
        # First attempt: missing rollback and falsifier
        r1 = gate.evaluate(
            ClaimCategory.PROCEDURE,
            RiskLevel.HIGH,
            evidence_count=3,
            independence_score=0.65,
            has_prerequisites=True,
            has_failure_modes=True,
            has_rollback=False,
            has_platform_context=True,
            falsifier_ran=False,
        )
        assert r1.commit_level != CommitLevel.HARD
        assert "requires_rollback" in r1.unsatisfied

        # Second attempt: all requirements met
        r2 = gate.evaluate(
            ClaimCategory.PROCEDURE,
            RiskLevel.HIGH,
            evidence_count=3,
            independence_score=0.65,
            has_prerequisites=True,
            has_failure_modes=True,
            has_rollback=True,
            has_platform_context=True,
            falsifier_ran=True,
        )
        assert r2.commit_level == CommitLevel.HARD

    def test_stale_api_fact(self):
        """Volatile fact with expired TTL can't be HARD."""
        gate = StrictModeGate()
        result = gate.evaluate(
            ClaimCategory.VOLATILE_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=True,
            has_ttl=True,
            ttl_hours=72.0,  # way past 24h limit
        )
        assert result.commit_level == CommitLevel.SOFT
        assert any("ttl" in u for u in result.unsatisfied)

    def test_judgment_chain(self):
        """Multiple judgments are always SOFT."""
        gate = StrictModeGate()
        for _ in range(5):
            r = gate.evaluate(ClaimCategory.JUDGMENT)
            assert r.commit_level == CommitLevel.SOFT
        assert gate.total_evaluations == 5
        assert gate.hard_rate() == 0.0

    def test_mixed_evaluation_flow(self):
        """Real workflow: code claim, then judgment, then fact."""
        gate = StrictModeGate()

        # Code: HARD
        r1 = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
            is_runnable=True,
            has_version=True,
        )
        assert r1.commit_level == CommitLevel.HARD

        # Judgment: SOFT (always)
        r2 = gate.evaluate(ClaimCategory.JUDGMENT)
        assert r2.commit_level == CommitLevel.SOFT

        # Static fact: REFUSED (no evidence)
        r3 = gate.evaluate(ClaimCategory.STATIC_FACT)
        assert r3.commit_level == CommitLevel.REFUSED

        # Stats
        s = gate.stats()
        assert s["total"] == 3
        assert s["hard"] == 1
        assert s["soft"] == 1
        assert s["refused"] == 1

    def test_escalating_risk(self):
        """Same claim at LOW/MED/HIGH shows escalating requirements."""
        gate = StrictModeGate()
        levels = []
        for risk in [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]:
            result = gate.evaluate(
                ClaimCategory.CODE,
                risk,
                evidence_count=1,
                independence_score=0.5,
                is_runnable=True,
                has_version=True,
            )
            levels.append(result.commit_level)

        # LOW: HARD, MEDIUM: not HARD (needs 2 evidence, 0.55 independence)
        assert levels[0] == CommitLevel.HARD
        assert levels[1] != CommitLevel.HARD
        # HIGH: also not HARD (needs falsifier)
        assert levels[2] != CommitLevel.HARD

    def test_serialization_full_session(self):
        """Serialize and restore a full session."""
        gate = StrictModeGate()
        gate.evaluate(ClaimCategory.CODE, evidence_count=1,
                      independence_score=0.5, is_runnable=True, has_version=True)
        gate.evaluate(ClaimCategory.JUDGMENT)
        gate.evaluate(ClaimCategory.STATIC_FACT)

        d = gate.to_dict()
        restored = StrictModeGate.from_dict(d)

        assert restored.total_evaluations == 3
        assert restored.stats() == gate.stats()
        # Verify each evaluation preserved
        for orig, rest in zip(gate.history, restored.history):
            assert orig.commit_level == rest.commit_level
            assert orig.category == rest.category


# =====================================================================
# Edge cases
# =====================================================================

class TestEdgeCases:
    def test_zero_total_requirements(self):
        """Category with 0 evidence and 0 independence → ratio 0/0 handled."""
        # JUDGMENT and PLAN have min_evidence_count=0, min_independence=0.0
        # But they're soft-only so they skip the check.
        # Let's use a custom category with all zeros.
        policy = StrictPolicy(
            requirements={
                ClaimCategory.CODE: ClaimRequirement(
                    category=ClaimCategory.CODE,
                    min_evidence_count=0,
                    min_independence=0.0,
                ),
            },
        )
        gate = StrictModeGate(policy=policy)
        result = gate.evaluate(ClaimCategory.CODE)
        # Evidence count >=0 is satisfied (0>=0), independence >=0 is satisfied
        assert result.commit_level == CommitLevel.HARD

    def test_satisfaction_ratio_boundary(self):
        """Exactly at thresholds."""
        policy = StrictPolicy(hard_threshold=0.5, soft_threshold=0.25)
        gate = StrictModeGate(policy=policy)
        result = gate.evaluate(
            ClaimCategory.STATIC_FACT,
            evidence_count=2,
            independence_score=0.55,
            has_source=True,
            has_version=False,
            has_verification_date=False,
        )
        # 3 satisfied, 2 unsatisfied → 3/5 = 0.6 >= 0.5 → HARD
        assert result.commit_level == CommitLevel.HARD

    def test_custom_requirements_override_defaults(self):
        """Custom requirements completely replace defaults."""
        policy = StrictPolicy(
            requirements={
                ClaimCategory.CODE: ClaimRequirement(
                    category=ClaimCategory.CODE,
                    min_evidence_count=5,
                    min_independence=0.9,
                ),
            },
        )
        gate = StrictModeGate(policy=policy)
        result = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
        )
        assert result.commit_level == CommitLevel.REFUSED

    def test_unknown_category_in_policy_uses_default_requirement(self):
        """Querying a category not in policy.requirements returns default."""
        policy = StrictPolicy(requirements={})
        gate = StrictModeGate(policy=policy)
        # CODE not in empty requirements → get_requirement returns bare default
        result = gate.evaluate(
            ClaimCategory.CODE,
            evidence_count=1,
            independence_score=0.5,
        )
        # Bare default: evidence>=1 ✓, independence>=0.5 ✓ → 2/2 → HARD
        assert result.commit_level == CommitLevel.HARD

    def test_window_parameter_for_rates(self):
        """Rate methods respect window parameter."""
        gate = StrictModeGate()
        for _ in range(10):
            gate.evaluate(ClaimCategory.JUDGMENT)  # SOFT
        for _ in range(5):
            gate.evaluate(ClaimCategory.STATIC_FACT)  # REFUSED
        # Last 5 are all REFUSED
        assert gate.refusal_rate(window=5) == 1.0
        # All 15: 5/15 refused
        assert gate.refusal_rate(window=15) == pytest.approx(5 / 15)
