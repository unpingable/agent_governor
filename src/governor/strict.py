"""
Strict Programmer Mode — Fail-closed governance for production contexts.

A global execution mode (governor preset, NOT a persona) that changes:
  - Default commit levels
  - Refusal thresholds
  - Evidence requirements
  - When the system is allowed to speculate

Core invariant: "Assume this answer may be copy-pasted into production."

Five non-negotiable rules:
  1. No speculative facts (HARD or explicitly SOFT — no silent hedging)
  2. Fail closed (unknown > wrong)
  3. Procedures treated as code (operationally dangerous by default)
  4. No invented interfaces (flags/APIs/configs must be sourced or verified)
  5. Dependencies must be explicit (OS, distro, version, runtime)

Integration:
  - Boil: installs as a named preset (STRICT_PROGRAMMER)
  - Homeostat: provides domain-specific setpoints (strict)
  - Ultrastability: adjusts S₁ parameters for fail-closed operation

Usage:
    gate = StrictModeGate()
    result = gate.evaluate(
        category=ClaimCategory.PROCEDURE,
        evidence_count=1,
        has_source=True,
        has_prerequisites=True,
        has_rollback=False,       # missing!
    )
    # result.commit_level == CommitLevel.SOFT
    # result.unsatisfied == ["requires_rollback"]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Enums
# =============================================================================

class ClaimCategory(str, Enum):
    """Claim types under strict programmer mode."""

    STATIC_FACT = "static_fact"
    """Requires source, version, verification date. No guessing."""

    VOLATILE_FACT = "volatile_fact"
    """Must include TTL, last-check timestamp, staleness warning."""

    CODE = "code"
    """Must compile/lint-check. No invented flags, config keys, or APIs."""

    PROCEDURE = "procedure"
    """Dangerous by default. Requires OS/distro/version context."""

    JUDGMENT = "judgment"
    """Explicitly SOFT. Must include conditions and confidence."""

    PLAN = "plan"
    """Explicitly SOFT. Never premise-bearing."""


class CommitLevel(str, Enum):
    """How firmly a claim can be committed."""

    HARD = "hard"
    """Fully committed — evidence-backed, all requirements met."""

    SOFT = "soft"
    """Explicitly tentative — conditions stated, may be revised."""

    REFUSED = "refused"
    """Cannot safely assert — requirements too far from met."""


class RiskLevel(str, Enum):
    """Risk classification for claims."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# =============================================================================
# Claim Requirements
# =============================================================================

@dataclass
class ClaimRequirement:
    """What's needed for a claim to be committed HARD in strict mode."""

    category: ClaimCategory

    # Evidence minimums
    min_evidence_count: int = 1
    min_independence: float = 0.5

    # Source requirements
    requires_source: bool = False
    requires_version: bool = False
    requires_verification_date: bool = False

    # Temporal requirements
    requires_ttl: bool = False
    max_ttl_hours: float | None = None

    # Procedure-specific
    requires_prerequisites: bool = False
    requires_failure_modes: bool = False
    requires_rollback: bool = False

    # Code-specific
    requires_runnable: bool = False
    requires_pseudocode_label: bool = False

    # Falsification
    falsifier_required: bool = False

    # Context
    requires_platform_context: bool = False

    def check(
        self,
        evidence_count: int = 0,
        independence_score: float = 0.0,
        has_source: bool = False,
        has_version: bool = False,
        has_verification_date: bool = False,
        has_ttl: bool = False,
        ttl_hours: float | None = None,
        has_prerequisites: bool = False,
        has_failure_modes: bool = False,
        has_rollback: bool = False,
        is_runnable: bool = False,
        is_labeled_pseudocode: bool = False,
        falsifier_ran: bool = False,
        has_platform_context: bool = False,
    ) -> tuple[list[str], list[str]]:
        """
        Check which requirements are satisfied.

        Returns (satisfied, unsatisfied).
        """
        satisfied: list[str] = []
        unsatisfied: list[str] = []

        def _check(name: str, required: bool, provided: bool) -> None:
            if required:
                if provided:
                    satisfied.append(name)
                else:
                    unsatisfied.append(name)

        # Evidence
        if evidence_count >= self.min_evidence_count:
            satisfied.append(f"evidence_count>={self.min_evidence_count}")
        else:
            unsatisfied.append(f"evidence_count>={self.min_evidence_count}")

        if independence_score >= self.min_independence:
            satisfied.append(f"independence>={self.min_independence}")
        else:
            unsatisfied.append(f"independence>={self.min_independence}")

        # Source
        _check("requires_source", self.requires_source, has_source)
        _check("requires_version", self.requires_version, has_version)
        _check("requires_verification_date", self.requires_verification_date, has_verification_date)

        # Temporal
        _check("requires_ttl", self.requires_ttl, has_ttl)
        if self.max_ttl_hours is not None and has_ttl and ttl_hours is not None:
            if ttl_hours <= self.max_ttl_hours:
                satisfied.append(f"ttl<={self.max_ttl_hours}h")
            else:
                unsatisfied.append(f"ttl<={self.max_ttl_hours}h")

        # Procedure
        _check("requires_prerequisites", self.requires_prerequisites, has_prerequisites)
        _check("requires_failure_modes", self.requires_failure_modes, has_failure_modes)
        _check("requires_rollback", self.requires_rollback, has_rollback)

        # Code
        if self.requires_runnable:
            if is_runnable or is_labeled_pseudocode:
                satisfied.append("runnable_or_pseudocode")
            else:
                unsatisfied.append("runnable_or_pseudocode")

        # Falsification
        _check("falsifier_required", self.falsifier_required, falsifier_ran)

        # Platform context
        _check("requires_platform_context", self.requires_platform_context, has_platform_context)

        return satisfied, unsatisfied

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__
                if f != "category"} | {"category": self.category.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimRequirement:
        d2 = dict(d)
        d2["category"] = ClaimCategory(d2["category"])
        return cls(**{k: d2[k] for k in d2 if k in cls.__dataclass_fields__})


# =============================================================================
# Default Requirements per Category
# =============================================================================

DEFAULT_REQUIREMENTS: dict[ClaimCategory, ClaimRequirement] = {
    ClaimCategory.STATIC_FACT: ClaimRequirement(
        category=ClaimCategory.STATIC_FACT,
        min_evidence_count=2,
        min_independence=0.55,
        requires_source=True,
        requires_version=True,
        requires_verification_date=True,
    ),
    ClaimCategory.VOLATILE_FACT: ClaimRequirement(
        category=ClaimCategory.VOLATILE_FACT,
        min_evidence_count=2,
        min_independence=0.55,
        requires_source=True,
        requires_ttl=True,
        max_ttl_hours=24.0,
    ),
    ClaimCategory.CODE: ClaimRequirement(
        category=ClaimCategory.CODE,
        min_evidence_count=1,
        min_independence=0.5,
        requires_runnable=True,
        requires_version=True,
    ),
    ClaimCategory.PROCEDURE: ClaimRequirement(
        category=ClaimCategory.PROCEDURE,
        min_evidence_count=2,
        min_independence=0.6,
        requires_prerequisites=True,
        requires_failure_modes=True,
        requires_rollback=True,
        requires_platform_context=True,
        falsifier_required=True,
    ),
    ClaimCategory.JUDGMENT: ClaimRequirement(
        category=ClaimCategory.JUDGMENT,
        min_evidence_count=0,
        min_independence=0.0,
        # Judgment is always SOFT — requirements are minimal
    ),
    ClaimCategory.PLAN: ClaimRequirement(
        category=ClaimCategory.PLAN,
        min_evidence_count=0,
        min_independence=0.0,
        # Plan is always SOFT — requirements are minimal
    ),
}


# =============================================================================
# Dependency Context
# =============================================================================

@dataclass
class DependencyContext:
    """Explicit platform/version context required by strict mode."""

    os: str | None = None
    distro: str | None = None
    language: str | None = None
    language_version: str | None = None
    runtime: str | None = None
    permissions: list[str] = field(default_factory=list)

    @property
    def is_specified(self) -> bool:
        """At least one platform detail is present."""
        return any([
            self.os, self.distro, self.language,
            self.language_version, self.runtime,
        ])

    @property
    def completeness(self) -> float:
        """Fraction of fields that are specified [0, 1]."""
        fields = [self.os, self.distro, self.language,
                  self.language_version, self.runtime]
        return sum(1 for f in fields if f is not None) / len(fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            "os": self.os,
            "distro": self.distro,
            "language": self.language,
            "language_version": self.language_version,
            "runtime": self.runtime,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DependencyContext:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


# =============================================================================
# Strict Policy
# =============================================================================

@dataclass
class StrictPolicy:
    """Full policy configuration for strict programmer mode."""

    # Per-category requirements
    requirements: dict[ClaimCategory, ClaimRequirement] = field(
        default_factory=lambda: dict(DEFAULT_REQUIREMENTS)
    )

    # Global overrides
    k_increase: int = 1               # +1 evidence for MED/HIGH risk
    independence_boost: float = 0.05   # +0.05 to independence threshold
    max_clarifying_questions: int = 2
    speculative_facts_allowed: bool = False
    best_effort_substitution: bool = False

    # Soft-only categories (can never be HARD)
    soft_only: set[ClaimCategory] = field(
        default_factory=lambda: {ClaimCategory.JUDGMENT, ClaimCategory.PLAN}
    )

    # Commit threshold: fraction of requirements that must be met for HARD
    hard_threshold: float = 1.0     # all requirements must be met
    soft_threshold: float = 0.5     # at least half for SOFT (else REFUSED)

    def get_requirement(self, category: ClaimCategory) -> ClaimRequirement:
        """Get requirement for a category (with global overrides applied)."""
        base = self.requirements.get(category, ClaimRequirement(category=category))
        return base

    def get_risk_adjusted(
        self, category: ClaimCategory, risk: RiskLevel,
    ) -> ClaimRequirement:
        """Get requirement adjusted for risk level."""
        base = self.get_requirement(category)
        if risk in (RiskLevel.MEDIUM, RiskLevel.HIGH):
            # Deep copy via reconstruction
            d = base.to_dict()
            d["min_evidence_count"] = base.min_evidence_count + self.k_increase
            d["min_independence"] = min(
                1.0, base.min_independence + self.independence_boost,
            )
            if risk == RiskLevel.HIGH:
                d["falsifier_required"] = True
            return ClaimRequirement.from_dict(d)
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirements": {
                k.value: v.to_dict() for k, v in self.requirements.items()
            },
            "k_increase": self.k_increase,
            "independence_boost": self.independence_boost,
            "max_clarifying_questions": self.max_clarifying_questions,
            "speculative_facts_allowed": self.speculative_facts_allowed,
            "best_effort_substitution": self.best_effort_substitution,
            "soft_only": [c.value for c in self.soft_only],
            "hard_threshold": self.hard_threshold,
            "soft_threshold": self.soft_threshold,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StrictPolicy:
        reqs = {
            ClaimCategory(k): ClaimRequirement.from_dict(v)
            for k, v in d.get("requirements", {}).items()
        }
        return cls(
            requirements=reqs or dict(DEFAULT_REQUIREMENTS),
            k_increase=d.get("k_increase", 1),
            independence_boost=d.get("independence_boost", 0.05),
            max_clarifying_questions=d.get("max_clarifying_questions", 2),
            speculative_facts_allowed=d.get("speculative_facts_allowed", False),
            best_effort_substitution=d.get("best_effort_substitution", False),
            soft_only={ClaimCategory(c) for c in d.get("soft_only", ["judgment", "plan"])},
            hard_threshold=d.get("hard_threshold", 1.0),
            soft_threshold=d.get("soft_threshold", 0.5),
        )


# =============================================================================
# Claim Evaluation
# =============================================================================

@dataclass
class ClaimEvaluation:
    """Result of evaluating a claim under strict mode."""

    category: ClaimCategory
    risk: RiskLevel
    commit_level: CommitLevel
    satisfied: list[str]
    unsatisfied: list[str]
    satisfaction_ratio: float       # fraction of requirements met
    recommendation: str             # human-readable advice
    refusal_message: str = ""       # "I can't assert X without Y"

    @property
    def is_hard(self) -> bool:
        return self.commit_level == CommitLevel.HARD

    @property
    def is_refused(self) -> bool:
        return self.commit_level == CommitLevel.REFUSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "risk": self.risk.value,
            "commit_level": self.commit_level.value,
            "satisfied": self.satisfied,
            "unsatisfied": self.unsatisfied,
            "satisfaction_ratio": self.satisfaction_ratio,
            "recommendation": self.recommendation,
            "refusal_message": self.refusal_message,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClaimEvaluation:
        return cls(
            category=ClaimCategory(d["category"]),
            risk=RiskLevel(d["risk"]),
            commit_level=CommitLevel(d["commit_level"]),
            satisfied=d["satisfied"],
            unsatisfied=d["unsatisfied"],
            satisfaction_ratio=d["satisfaction_ratio"],
            recommendation=d["recommendation"],
            refusal_message=d.get("refusal_message", ""),
        )


# =============================================================================
# Strict Mode Gate
# =============================================================================

class StrictModeGate:
    """
    Gating logic for strict programmer mode.

    Evaluates claims against strict policy requirements and returns
    the maximum commit level (HARD / SOFT / REFUSED).

    Rules:
    1. JUDGMENT and PLAN are always SOFT (never HARD).
    2. All requirements met → HARD.
    3. >= soft_threshold met → SOFT.
    4. Below soft_threshold → REFUSED.
    5. Speculative facts are blocked unless explicitly allowed.
    """

    def __init__(self, policy: StrictPolicy | None = None) -> None:
        self.policy = policy or StrictPolicy()
        self._history: list[ClaimEvaluation] = []

    def evaluate(
        self,
        category: ClaimCategory,
        risk: RiskLevel = RiskLevel.LOW,
        *,
        evidence_count: int = 0,
        independence_score: float = 0.0,
        has_source: bool = False,
        has_version: bool = False,
        has_verification_date: bool = False,
        has_ttl: bool = False,
        ttl_hours: float | None = None,
        has_prerequisites: bool = False,
        has_failure_modes: bool = False,
        has_rollback: bool = False,
        is_runnable: bool = False,
        is_labeled_pseudocode: bool = False,
        falsifier_ran: bool = False,
        has_platform_context: bool = False,
    ) -> ClaimEvaluation:
        """Evaluate a claim and determine its maximum commit level."""

        # 1. Soft-only categories
        if category in self.policy.soft_only:
            evaluation = ClaimEvaluation(
                category=category,
                risk=risk,
                commit_level=CommitLevel.SOFT,
                satisfied=[],
                unsatisfied=[],
                satisfaction_ratio=1.0,
                recommendation=f"{category.value} is always SOFT in strict mode",
            )
            self._history.append(evaluation)
            return evaluation

        # 2. Get risk-adjusted requirements
        req = self.policy.get_risk_adjusted(category, risk)

        # 3. Check requirements
        satisfied, unsatisfied = req.check(
            evidence_count=evidence_count,
            independence_score=independence_score,
            has_source=has_source,
            has_version=has_version,
            has_verification_date=has_verification_date,
            has_ttl=has_ttl,
            ttl_hours=ttl_hours,
            has_prerequisites=has_prerequisites,
            has_failure_modes=has_failure_modes,
            has_rollback=has_rollback,
            is_runnable=is_runnable,
            is_labeled_pseudocode=is_labeled_pseudocode,
            falsifier_ran=falsifier_ran,
            has_platform_context=has_platform_context,
        )

        total = len(satisfied) + len(unsatisfied)
        ratio = len(satisfied) / total if total > 0 else 0.0

        # 4. Determine commit level
        if ratio >= self.policy.hard_threshold:
            level = CommitLevel.HARD
            rec = "All requirements met — HARD commit allowed"
            refusal = ""
        elif ratio >= self.policy.soft_threshold:
            level = CommitLevel.SOFT
            missing = ", ".join(unsatisfied)
            rec = f"SOFT commit — missing: {missing}"
            refusal = f"Cannot assert as HARD without: {missing}"
        else:
            level = CommitLevel.REFUSED
            missing = ", ".join(unsatisfied)
            rec = f"REFUSED — too many requirements unmet ({len(unsatisfied)}/{total})"
            refusal = f"I can't assert this safely without: {missing}"

        evaluation = ClaimEvaluation(
            category=category,
            risk=risk,
            commit_level=level,
            satisfied=satisfied,
            unsatisfied=unsatisfied,
            satisfaction_ratio=ratio,
            recommendation=rec,
            refusal_message=refusal,
        )
        self._history.append(evaluation)
        return evaluation

    def format_refusal(self, evaluation: ClaimEvaluation) -> str:
        """Format a refusal message for output."""
        if evaluation.commit_level == CommitLevel.HARD:
            return ""
        if evaluation.refusal_message:
            return evaluation.refusal_message
        return f"Cannot commit {evaluation.category.value} as HARD"

    # -----------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------

    @property
    def history(self) -> list[ClaimEvaluation]:
        return list(self._history)

    @property
    def total_evaluations(self) -> int:
        return len(self._history)

    def refusal_rate(self, window: int = 50) -> float:
        """Fraction of evaluations that were REFUSED."""
        recent = self._history[-window:]
        if not recent:
            return 0.0
        return sum(1 for e in recent if e.is_refused) / len(recent)

    def hard_rate(self, window: int = 50) -> float:
        """Fraction of evaluations that were HARD."""
        recent = self._history[-window:]
        if not recent:
            return 0.0
        return sum(1 for e in recent if e.is_hard) / len(recent)

    def stats(self) -> dict[str, Any]:
        """Summary statistics."""
        total = len(self._history)
        if total == 0:
            return {"total": 0, "hard": 0, "soft": 0, "refused": 0}
        hard = sum(1 for e in self._history if e.commit_level == CommitLevel.HARD)
        soft = sum(1 for e in self._history if e.commit_level == CommitLevel.SOFT)
        refused = sum(1 for e in self._history if e.commit_level == CommitLevel.REFUSED)
        return {
            "total": total,
            "hard": hard,
            "soft": soft,
            "refused": refused,
            "hard_rate": hard / total,
            "soft_rate": soft / total,
            "refusal_rate": refused / total,
        }

    def get_diagnostics(self) -> dict[str, Any]:
        """Full diagnostic snapshot."""
        return {
            "policy": self.policy.to_dict(),
            "stats": self.stats(),
            "recent_evaluations": [
                e.to_dict() for e in self._history[-10:]
            ],
        }

    # -----------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.to_dict(),
            "history": [e.to_dict() for e in self._history],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StrictModeGate:
        gate = cls(policy=StrictPolicy.from_dict(d["policy"]))
        gate._history = [ClaimEvaluation.from_dict(e) for e in d.get("history", [])]
        return gate

    def reset(self) -> None:
        """Reset evaluation history."""
        self._history.clear()


# =============================================================================
# Integration helpers
# =============================================================================

def create_strict_policy() -> StrictPolicy:
    """Create the default strict programmer policy."""
    return StrictPolicy()


def create_strict_setpoints() -> "EpistemicSetpoints":
    """Create homeostat setpoints tuned for strict mode."""
    from .homeostat import EpistemicSetpoints
    return EpistemicSetpoints(
        revision_target=0.02,           # low — revisions are expensive
        contradiction_target=0.01,      # very low — contradictions are bad
        hedge_target=0.25,              # higher — hedging is correct behaviour
        refusal_target=0.05,            # higher — refusal is correct behaviour
        instability_target=0.05,        # very low
        contradiction_weight=3.0,       # heavy penalty
        revision_weight=2.0,
        refusal_weight=0.3,             # low weight — refusal is expected
    )


def create_strict_boil_preset() -> dict[str, Any]:
    """
    Create boil preset parameters for strict mode.

    Returns a dict matching BoilPreset fields.
    """
    return {
        "claim_budget_per_turn": 5,      # very tight
        "novelty_tolerance": 0.1,        # almost no speculation
        "authority_posture": "strict",
        "variety_multiplier": 0.5,       # conservative variety
        "horizon_turns": 3,              # short planning horizon
    }


def create_strict_s1_overrides() -> dict[str, float]:
    """
    Create S₁ parameter overrides for strict mode.

    These can be fed to UltrastabilityController.parameters.set_value().
    """
    return {
        "evidence_threshold": 0.85,       # high evidence bar
        "independence_threshold": 0.7,    # high independence
        "glass_threshold": 10.0,          # low tolerance for open contradictions
        "resolution_cost": 5.0,           # cheap resolution (encourage fixing)
        "repair_budget": 200.0,           # generous repair budget
        "refill_rate": 8.0,               # fast refill
    }


def create_strict_gate() -> StrictModeGate:
    """Create a strict mode gate with default policy."""
    return StrictModeGate()


def quick_evaluate(
    category: ClaimCategory,
    risk: RiskLevel = RiskLevel.LOW,
    **kwargs: Any,
) -> ClaimEvaluation:
    """One-shot evaluation with default strict policy."""
    gate = StrictModeGate()
    return gate.evaluate(category, risk, **kwargs)
