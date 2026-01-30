"""
Epistemic Homeostat — Adaptive gain scheduling for the agent governor.

Observes system "vitals" (rates, deficits, thermal state), compares to
setpoints (target operating ranges), and outputs "tuning deltas" that
adjust governor parameters.

Key rules:
1. Homeostat never touches ledger contents — only adjusts thresholds
2. Urgency increases CONTROL WORK, not randomness
3. Exploration contexts deliberately loosen constraints for discovery
4. Exploration is BOUNDED by budget — prevents indefinite drift

S-layer placement: This is an S₁ adjuster. It proposes parameter changes
that the ultrastability controller can accept or reject.

Usage:
    homeostat = create_homeostat()

    vitals = EpistemicVitals(
        revision_rate=0.05, contradiction_rate=0.02,
        hedge_rate=0.15, refusal_rate=0.01,
    )
    tuning = homeostat.compute_tuning(vitals)

    # Exploration mode
    homeostat.enter_exploration(ExplorationContext.BRAINSTORM)
    tuning = homeostat.compute_tuning(vitals)  # loosened constraints
    homeostat.exit_exploration()
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Enums
# =============================================================================

class HomeostatMode(Enum):
    """Operating mode for the homeostat."""
    OBSERVE_ONLY = "observe"   # Log but don't output tuning
    SUGGEST = "suggest"        # Output tuning but application is optional
    ACTIVE = "active"          # Full adaptive control


class ExplorationContext(Enum):
    """
    Exploration contexts that modify homeostatic behaviour.

    Default homeostasis converges to "reliable, boring, conservative."
    These contexts deliberately loosen constraints for discovery.
    """
    STANDARD = "standard"              # Normal homeostasis
    RESEARCH = "research"              # Higher speculation tolerance
    BRAINSTORM = "brainstorm"          # Minimal filtering, everything tentative
    HYPOTHESIS = "hypothesis"          # Explicitly tentative claims, easy revision
    SYNTHESIS = "synthesis"            # Tolerance for novel connections
    DEVILS_ADVOCATE = "devils_advocate" # Exploring contrary positions
    CALIBRATION = "calibration"        # System tuning, extra logging


# =============================================================================
# Vitals (Observable System State)
# =============================================================================

@dataclass
class EpistemicVitals:
    """
    Observable system state — the "internal sensors" of the epistemic system.

    All rates are normalised to [0, 1].
    """
    # Core rates
    revision_rate: float = 0.0        # revisions / total_commits
    contradiction_rate: float = 0.0   # contradictions / total_proposals
    hedge_rate: float = 0.0           # hedges / total_commits
    refusal_rate: float = 0.0         # refusals / total_proposals

    # Support / grounding metrics
    support_deficit_rate: float = 0.0  # claims needing support / total
    retrieval_coverage: float = 1.0    # claims with support / claims needing it

    # Thermal state
    thermal_instability: float = 0.0
    thermal_regime: str = "normal"

    # Session counters
    turn: int = 0
    total_commits: int = 0
    total_proposals: int = 0

    # Derived urgency (computed by setpoints)
    urgency: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "revision_rate", "contradiction_rate", "hedge_rate",
            "refusal_rate", "support_deficit_rate", "retrieval_coverage",
            "thermal_instability", "urgency",
        ):
            v = getattr(self, name)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {v}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_rate": self.revision_rate,
            "contradiction_rate": self.contradiction_rate,
            "hedge_rate": self.hedge_rate,
            "refusal_rate": self.refusal_rate,
            "support_deficit_rate": self.support_deficit_rate,
            "retrieval_coverage": self.retrieval_coverage,
            "thermal_instability": self.thermal_instability,
            "thermal_regime": self.thermal_regime,
            "turn": self.turn,
            "total_commits": self.total_commits,
            "total_proposals": self.total_proposals,
            "urgency": self.urgency,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EpistemicVitals:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


# =============================================================================
# Setpoints (Target Operating Ranges)
# =============================================================================

@dataclass
class EpistemicSetpoints:
    """
    Target operating ranges for epistemic state.

    Deviation from setpoints increases urgency and triggers adaptive
    responses.  Domain-specific factory methods adjust these for
    medical/legal (strict) or creative/brainstorm (permissive) contexts.
    """
    # Rate targets
    revision_target: float = 0.05       # ~5 % revision rate is normal
    contradiction_target: float = 0.02  # ~2 % contradiction rate is healthy
    hedge_target: float = 0.15          # ~15 % hedging is appropriate
    refusal_target: float = 0.01        # ~1 % refusal is normal

    # Support targets
    support_deficit_target: float = 0.10   # up to 10 % needing support is ok
    retrieval_coverage_target: float = 0.90

    # Thermal targets
    instability_target: float = 0.10

    # Weights for urgency calculation
    revision_weight: float = 1.5
    contradiction_weight: float = 2.0
    hedge_weight: float = 0.5
    refusal_weight: float = 1.0
    support_deficit_weight: float = 1.0
    retrieval_coverage_weight: float = 1.0
    instability_weight: float = 1.5

    def compute_error(self, vitals: EpistemicVitals) -> dict[str, float]:
        """Per-dimension absolute deviation from setpoint."""
        return {
            "revision": abs(vitals.revision_rate - self.revision_target),
            "contradiction": abs(vitals.contradiction_rate - self.contradiction_target),
            "hedge": abs(vitals.hedge_rate - self.hedge_target),
            "refusal": abs(vitals.refusal_rate - self.refusal_target),
            "support_deficit": abs(vitals.support_deficit_rate - self.support_deficit_target),
            "retrieval_coverage": abs(vitals.retrieval_coverage - self.retrieval_coverage_target),
            "instability": abs(vitals.thermal_instability - self.instability_target),
        }

    def compute_urgency(self, vitals: EpistemicVitals) -> float:
        """
        Aggregate urgency [0, 1] from weighted deviations.

        Higher urgency → system is further from healthy operating range.
        """
        errors = self.compute_error(vitals)
        weights = {
            "revision": self.revision_weight,
            "contradiction": self.contradiction_weight,
            "hedge": self.hedge_weight,
            "refusal": self.refusal_weight,
            "support_deficit": self.support_deficit_weight,
            "retrieval_coverage": self.retrieval_coverage_weight,
            "instability": self.instability_weight,
        }
        weighted = sum(errors[k] * weights[k] for k in errors)
        total_weight = sum(weights.values())
        return min(weighted / total_weight, 1.0)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for f in self.__dataclass_fields__:
            d[f] = getattr(self, f)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EpistemicSetpoints:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})

    @classmethod
    def for_domain(cls, domain: str) -> EpistemicSetpoints:
        """Create domain-specific setpoints."""
        if domain in ("medical", "legal", "safety"):
            return cls(
                revision_target=0.02,
                contradiction_target=0.01,
                hedge_target=0.25,
                refusal_target=0.05,
                instability_target=0.05,
                contradiction_weight=3.0,
                revision_weight=2.0,
            )
        if domain in ("creative", "brainstorm", "exploratory"):
            return cls(
                revision_target=0.15,
                contradiction_target=0.10,
                hedge_target=0.05,
                refusal_target=0.005,
                instability_target=0.30,
                contradiction_weight=0.5,
                revision_weight=0.5,
            )
        return cls()


# =============================================================================
# Tuning Deltas (Control Output)
# =============================================================================

@dataclass
class TuningDelta:
    """
    Output of the homeostat: adjustments to apply to governor policy.

    These are multipliers / biases that modify the base policy, NOT
    absolute values.  This allows smooth composition with calibrated
    baselines.
    """
    # Confidence adjustment
    confidence_ceiling_mult: float = 1.0   # multiply max_confidence
    # Support / retrieval biases
    require_support_bias: float = 0.0      # add to support requirement threshold
    retrieval_force_bias: float = 0.0      # add to retrieval forcing threshold
    # Hedging / refusal preference
    hedge_preference: float = 0.0          # bias toward hedging (+) vs committing (−)
    refuse_preference: float = 0.0         # bias toward refusing (+) vs attempting (−)
    # Revision sensitivity
    revision_cost_mult: float = 1.0        # multiply revision costs
    # Horizon control
    horizon_mult: float = 1.0             # multiply commitment horizon
    # Source urgency
    source_urgency: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_ceiling_mult": self.confidence_ceiling_mult,
            "require_support_bias": self.require_support_bias,
            "retrieval_force_bias": self.retrieval_force_bias,
            "hedge_preference": self.hedge_preference,
            "refuse_preference": self.refuse_preference,
            "revision_cost_mult": self.revision_cost_mult,
            "horizon_mult": self.horizon_mult,
            "source_urgency": self.source_urgency,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuningDelta:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


# =============================================================================
# Exploration Budget
# =============================================================================

@dataclass
class ExplorationBudget:
    """
    Budget for exploration that gets spent and replenished.

    Prevents indefinite exploration drift while allowing bounded discovery.
    Think of it as "plasticity tokens" consumed during exploration and
    regenerated during consolidation (STANDARD mode).
    """
    remaining: float = 1.0
    regen_rate: float = 0.05        # per turn in STANDARD
    consume_rate: float = 0.10      # default per turn in exploration
    min_to_explore: float = 0.20    # can't enter exploration below this
    max_budget: float = 1.0

    def __post_init__(self) -> None:
        if not (0.0 <= self.remaining <= self.max_budget):
            raise ValueError(
                f"remaining must be in [0, {self.max_budget}], got {self.remaining}"
            )
        if self.regen_rate < 0:
            raise ValueError(f"regen_rate must be >= 0, got {self.regen_rate}")
        if self.consume_rate < 0:
            raise ValueError(f"consume_rate must be >= 0, got {self.consume_rate}")

    def can_explore(self) -> bool:
        """Check if exploration is allowed."""
        return self.remaining >= self.min_to_explore

    def consume(self, amount: float | None = None) -> float:
        """Consume budget.  Returns amount actually consumed."""
        cost = amount if amount is not None else self.consume_rate
        actual = min(cost, self.remaining)
        self.remaining = max(0.0, self.remaining - cost)
        return actual

    def regenerate(self, amount: float | None = None) -> float:
        """Regenerate budget.  Returns amount actually regenerated."""
        gain = amount if amount is not None else self.regen_rate
        headroom = self.max_budget - self.remaining
        actual = min(gain, headroom)
        self.remaining = min(self.max_budget, self.remaining + gain)
        return actual

    def to_dict(self) -> dict[str, Any]:
        return {
            "remaining": self.remaining,
            "can_explore": self.can_explore(),
            "regen_rate": self.regen_rate,
            "consume_rate": self.consume_rate,
            "min_to_explore": self.min_to_explore,
            "max_budget": self.max_budget,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExplorationBudget:
        keys = {"remaining", "regen_rate", "consume_rate", "min_to_explore", "max_budget"}
        return cls(**{k: d[k] for k in d if k in keys})


# =============================================================================
# Exploration Profile
# =============================================================================

@dataclass
class ExplorationProfile:
    """
    Configuration for a specific exploration context.

    Defines how constraints are modified during exploration.
    """
    context: ExplorationContext
    description: str = ""

    # Confidence adjustments
    confidence_ceiling_boost: float = 0.0
    hedge_requirement_reduction: float = 0.0

    # Revision adjustments
    revision_cost_discount: float = 0.0     # 0 = no discount, 1 = free
    revision_budget_boost: int = 0

    # Support adjustments
    support_requirement_reduction: float = 0.0

    # Commitment adjustments
    commitment_tentativeness: float = 0.0   # 0 = firm, 1 = fully tentative

    # Urgency scaling
    urgency_dampening: float = 0.0          # 0 = normal, 1 = ignore urgency

    # Budget cost per turn in this context
    budget_cost: float = 0.10

    def to_dict(self) -> dict[str, Any]:
        return {
            "context": self.context.value,
            "description": self.description,
            "confidence_ceiling_boost": self.confidence_ceiling_boost,
            "hedge_requirement_reduction": self.hedge_requirement_reduction,
            "revision_cost_discount": self.revision_cost_discount,
            "revision_budget_boost": self.revision_budget_boost,
            "support_requirement_reduction": self.support_requirement_reduction,
            "commitment_tentativeness": self.commitment_tentativeness,
            "urgency_dampening": self.urgency_dampening,
            "budget_cost": self.budget_cost,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExplorationProfile:
        ctx = ExplorationContext(d["context"])
        fields = {k: d[k] for k in d if k in cls.__dataclass_fields__ and k != "context"}
        return cls(context=ctx, **fields)


# =============================================================================
# Pre-defined exploration profiles
# =============================================================================

EXPLORATION_PROFILES: dict[ExplorationContext, ExplorationProfile] = {
    ExplorationContext.STANDARD: ExplorationProfile(
        context=ExplorationContext.STANDARD,
        description="Normal homeostatic operation",
        budget_cost=0.0,
    ),
    ExplorationContext.RESEARCH: ExplorationProfile(
        context=ExplorationContext.RESEARCH,
        description="Exploring a topic — higher speculation tolerance",
        confidence_ceiling_boost=0.1,
        hedge_requirement_reduction=0.1,
        support_requirement_reduction=0.2,
        urgency_dampening=0.3,
        budget_cost=0.05,
    ),
    ExplorationContext.BRAINSTORM: ExplorationProfile(
        context=ExplorationContext.BRAINSTORM,
        description="Generating ideas — minimal filtering, everything tentative",
        confidence_ceiling_boost=0.2,
        hedge_requirement_reduction=0.3,
        revision_cost_discount=0.5,
        revision_budget_boost=5,
        support_requirement_reduction=0.4,
        commitment_tentativeness=0.8,
        urgency_dampening=0.7,
        budget_cost=0.15,
    ),
    ExplorationContext.HYPOTHESIS: ExplorationProfile(
        context=ExplorationContext.HYPOTHESIS,
        description="Explicitly tentative claims — easy revision expected",
        confidence_ceiling_boost=0.15,
        hedge_requirement_reduction=0.2,
        revision_cost_discount=0.7,
        revision_budget_boost=10,
        commitment_tentativeness=0.9,
        urgency_dampening=0.5,
        budget_cost=0.08,
    ),
    ExplorationContext.SYNTHESIS: ExplorationProfile(
        context=ExplorationContext.SYNTHESIS,
        description="Combining ideas — tolerance for novel connections",
        confidence_ceiling_boost=0.1,
        hedge_requirement_reduction=0.15,
        support_requirement_reduction=0.3,
        urgency_dampening=0.4,
        budget_cost=0.10,
    ),
    ExplorationContext.DEVILS_ADVOCATE: ExplorationProfile(
        context=ExplorationContext.DEVILS_ADVOCATE,
        description="Exploring contrary positions — fully provisional",
        confidence_ceiling_boost=0.1,
        hedge_requirement_reduction=0.2,
        revision_cost_discount=0.8,
        commitment_tentativeness=1.0,
        urgency_dampening=0.6,
        budget_cost=0.12,
    ),
    ExplorationContext.CALIBRATION: ExplorationProfile(
        context=ExplorationContext.CALIBRATION,
        description="System calibration — extra logging, normal constraints",
        urgency_dampening=0.0,
        budget_cost=0.0,
    ),
}


def get_profile(context: ExplorationContext) -> ExplorationProfile:
    """Return the profile for a context (STANDARD if unknown)."""
    return EXPLORATION_PROFILES.get(
        context, EXPLORATION_PROFILES[ExplorationContext.STANDARD]
    )


def list_profiles() -> list[ExplorationProfile]:
    """Return all pre-defined profiles."""
    return list(EXPLORATION_PROFILES.values())


# =============================================================================
# Tuning Gain Parameters
# =============================================================================

@dataclass
class TuningGains:
    """
    Gains that map urgency → tuning deltas.

    Positive gain = urgency pushes value UP.
    Negative gain = urgency pushes value DOWN.
    """
    urgency_to_confidence: float = -0.3     # high urgency → lower confidence
    urgency_to_support: float = 0.5         # high urgency → more support required
    urgency_to_retrieval: float = 0.4       # high urgency → more retrieval
    urgency_to_hedge: float = 0.6           # high urgency → prefer hedging
    urgency_to_refuse: float = 0.3          # high urgency → more willing to refuse
    urgency_to_revision_cost: float = 0.5   # high urgency → revisions expensive
    urgency_to_horizon: float = -0.3        # high urgency → shorter horizon

    def to_dict(self) -> dict[str, float]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuningGains:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


# =============================================================================
# Tuning Clamps (output limits)
# =============================================================================

@dataclass
class TuningClamps:
    """Hard limits on tuning delta outputs."""
    confidence_mult_min: float = 0.5
    confidence_mult_max: float = 1.2
    revision_cost_mult_min: float = 0.3
    revision_cost_mult_max: float = 3.0
    horizon_mult_min: float = 0.3
    horizon_mult_max: float = 1.5
    support_bias_min: float = -0.3
    support_bias_max: float = 0.5
    hedge_pref_min: float = -0.3
    hedge_pref_max: float = 0.6

    def clamp(self, tuning: TuningDelta) -> TuningDelta:
        """Return a clamped copy of the tuning delta."""
        return TuningDelta(
            confidence_ceiling_mult=max(
                self.confidence_mult_min,
                min(self.confidence_mult_max, tuning.confidence_ceiling_mult),
            ),
            require_support_bias=max(
                self.support_bias_min,
                min(self.support_bias_max, tuning.require_support_bias),
            ),
            retrieval_force_bias=tuning.retrieval_force_bias,
            hedge_preference=max(
                self.hedge_pref_min,
                min(self.hedge_pref_max, tuning.hedge_preference),
            ),
            refuse_preference=tuning.refuse_preference,
            revision_cost_mult=max(
                self.revision_cost_mult_min,
                min(self.revision_cost_mult_max, tuning.revision_cost_mult),
            ),
            horizon_mult=max(
                self.horizon_mult_min,
                min(self.horizon_mult_max, tuning.horizon_mult),
            ),
            source_urgency=tuning.source_urgency,
        )


# =============================================================================
# Observation Record (for history)
# =============================================================================

@dataclass
class ObservationRecord:
    """A single observation + tuning pair."""
    vitals: EpistemicVitals
    tuning: TuningDelta
    context: ExplorationContext
    budget_remaining: float
    ema_urgency: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "vitals": self.vitals.to_dict(),
            "tuning": self.tuning.to_dict(),
            "context": self.context.value,
            "budget_remaining": self.budget_remaining,
            "ema_urgency": self.ema_urgency,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ObservationRecord:
        return cls(
            vitals=EpistemicVitals.from_dict(d["vitals"]),
            tuning=TuningDelta.from_dict(d["tuning"]),
            context=ExplorationContext(d["context"]),
            budget_remaining=d["budget_remaining"],
            ema_urgency=d["ema_urgency"],
        )


# =============================================================================
# Homeostat (The Controller)
# =============================================================================

class Homeostat:
    """
    Adaptive gain scheduler for epistemic governance.

    Observes system vitals, compares to setpoints, and outputs tuning
    deltas that adjust governor parameters based on urgency.

    Key design rules:
    1. Never touch ledger contents — only adjust thresholds
    2. Use urgency to increase CONTROL WORK, not randomness
    3. Keep costs explicit and centralised

    Exploration contexts are the antidote to mediocrity.  Default
    homeostasis converges to "reliable, boring, conservative."  Use
    exploration contexts to deliberately loosen constraints for discovery.
    """

    def __init__(
        self,
        setpoints: EpistemicSetpoints | None = None,
        gains: TuningGains | None = None,
        clamps: TuningClamps | None = None,
        budget: ExplorationBudget | None = None,
        mode: HomeostatMode = HomeostatMode.SUGGEST,
        ema_alpha: float = 0.3,
        max_history: int = 200,
    ) -> None:
        self.setpoints = setpoints or EpistemicSetpoints()
        self.gains = gains or TuningGains()
        self.clamps = clamps or TuningClamps()
        self.mode = mode
        self.ema_alpha = ema_alpha
        self.max_history = max_history

        # Exploration state
        self._context = ExplorationContext.STANDARD
        self._budget = budget or ExplorationBudget()
        self._context_history: list[tuple[ExplorationContext, ExplorationContext]] = []

        # EMA smoothing
        self._ema_urgency: float = 0.0

        # History
        self._history: list[ObservationRecord] = []

    # -----------------------------------------------------------------
    # Exploration context management
    # -----------------------------------------------------------------

    @property
    def context(self) -> ExplorationContext:
        return self._context

    @property
    def budget(self) -> ExplorationBudget:
        return self._budget

    def enter_exploration(self, context: ExplorationContext) -> bool:
        """
        Enter an exploration context.

        Returns True on success, False if budget is insufficient.
        Switching to STANDARD always succeeds.
        """
        if context == ExplorationContext.STANDARD:
            self._record_transition(context)
            self._context = context
            return True

        if context == self._context:
            return True  # already there

        if not self._budget.can_explore():
            return False

        self._record_transition(context)
        self._context = context
        return True

    def exit_exploration(self) -> None:
        """Return to STANDARD context."""
        self._record_transition(ExplorationContext.STANDARD)
        self._context = ExplorationContext.STANDARD

    def get_profile(self) -> ExplorationProfile:
        """Profile for the current context."""
        return get_profile(self._context)

    def _record_transition(self, to: ExplorationContext) -> None:
        if to != self._context:
            self._context_history.append((self._context, to))

    # -----------------------------------------------------------------
    # Core observation + tuning
    # -----------------------------------------------------------------

    def observe(self, vitals: EpistemicVitals) -> TuningDelta:
        """
        Observe vitals, update EMA urgency, manage budget, compute
        tuning deltas.  This is the main per-turn entry point.
        """
        # Compute urgency from setpoints
        urgency = self.setpoints.compute_urgency(vitals)

        # EMA smoothing
        self._ema_urgency = (
            self.ema_alpha * urgency
            + (1.0 - self.ema_alpha) * self._ema_urgency
        )

        # Budget management
        profile = self.get_profile()
        if self._context == ExplorationContext.STANDARD:
            self._budget.regenerate()
        else:
            self._budget.consume(profile.budget_cost)
            # Auto-exit if depleted
            if not self._budget.can_explore():
                self.exit_exploration()
                profile = self.get_profile()

        # Compute tuning
        tuning = self.compute_tuning(vitals)

        # Record
        rec = ObservationRecord(
            vitals=vitals,
            tuning=tuning,
            context=self._context,
            budget_remaining=self._budget.remaining,
            ema_urgency=self._ema_urgency,
        )
        self._history.append(rec)
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

        return tuning

    def compute_tuning(self, vitals: EpistemicVitals) -> TuningDelta:
        """
        Compute tuning deltas from vitals, urgency, and exploration context.

        OBSERVE_ONLY mode returns an identity TuningDelta.
        """
        if self.mode == HomeostatMode.OBSERVE_ONLY:
            return TuningDelta(source_urgency=self._ema_urgency)

        profile = self.get_profile()
        g = self.gains

        # Effective urgency after exploration dampening
        eff = self._ema_urgency * (1.0 - profile.urgency_dampening)

        # Base tuning from urgency
        raw = TuningDelta(
            confidence_ceiling_mult=(
                1.0 + g.urgency_to_confidence * eff + profile.confidence_ceiling_boost
            ),
            require_support_bias=(
                g.urgency_to_support * eff - profile.support_requirement_reduction
            ),
            retrieval_force_bias=g.urgency_to_retrieval * eff,
            hedge_preference=(
                g.urgency_to_hedge * eff - profile.hedge_requirement_reduction
            ),
            refuse_preference=g.urgency_to_refuse * eff,
            revision_cost_mult=(
                (1.0 + g.urgency_to_revision_cost * eff)
                * (1.0 - profile.revision_cost_discount)
            ),
            horizon_mult=1.0 + g.urgency_to_horizon * eff,
            source_urgency=eff,
        )

        return self.clamps.clamp(raw)

    # -----------------------------------------------------------------
    # Query / diagnostics
    # -----------------------------------------------------------------

    @property
    def ema_urgency(self) -> float:
        return self._ema_urgency

    @property
    def history(self) -> list[ObservationRecord]:
        return list(self._history)

    @property
    def context_history(self) -> list[tuple[ExplorationContext, ExplorationContext]]:
        return list(self._context_history)

    def recent_urgency(self, n: int = 20) -> list[float]:
        """Return recent EMA urgency values."""
        return [r.ema_urgency for r in self._history[-n:]]

    def urgency_trend(self, n: int = 10) -> float:
        """
        Linear regression slope of recent urgency values.

        Positive → urgency increasing, negative → decreasing.
        Returns 0.0 if insufficient data.
        """
        values = self.recent_urgency(n)
        if len(values) < 3:
            return 0.0
        m = len(values)
        xs = list(range(m))
        x_mean = sum(xs) / m
        y_mean = sum(values) / m
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
        den = sum((x - x_mean) ** 2 for x in xs)
        if den == 0:
            return 0.0
        return num / den

    def get_diagnostics(self) -> dict[str, Any]:
        """Full diagnostic snapshot."""
        profile = self.get_profile()
        return {
            "mode": self.mode.value,
            "context": self._context.value,
            "context_description": profile.description,
            "budget": self._budget.to_dict(),
            "ema_urgency": self._ema_urgency,
            "effective_urgency": self._ema_urgency * (1.0 - profile.urgency_dampening),
            "urgency_trend": self.urgency_trend(),
            "observations": len(self._history),
            "transitions": len(self._context_history),
            "setpoints": self.setpoints.to_dict(),
            "gains": self.gains.to_dict(),
        }

    # -----------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "context": self._context.value,
            "ema_urgency": self._ema_urgency,
            "ema_alpha": self.ema_alpha,
            "max_history": self.max_history,
            "budget": self._budget.to_dict(),
            "setpoints": self.setpoints.to_dict(),
            "gains": self.gains.to_dict(),
            "history": [r.to_dict() for r in self._history],
            "context_history": [
                [f.value, t.value] for f, t in self._context_history
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Homeostat:
        h = cls(
            setpoints=EpistemicSetpoints.from_dict(d["setpoints"]),
            gains=TuningGains.from_dict(d["gains"]),
            budget=ExplorationBudget.from_dict(d["budget"]),
            mode=HomeostatMode(d["mode"]),
            ema_alpha=d.get("ema_alpha", 0.3),
            max_history=d.get("max_history", 200),
        )
        h._ema_urgency = d["ema_urgency"]
        h._context = ExplorationContext(d["context"])
        h._history = [ObservationRecord.from_dict(r) for r in d.get("history", [])]
        h._context_history = [
            (ExplorationContext(f), ExplorationContext(t))
            for f, t in d.get("context_history", [])
        ]
        return h

    # -----------------------------------------------------------------
    # Reset
    # -----------------------------------------------------------------

    def reset(self) -> None:
        """Reset all mutable state."""
        self._context = ExplorationContext.STANDARD
        self._budget = ExplorationBudget()
        self._ema_urgency = 0.0
        self._history.clear()
        self._context_history.clear()


# =============================================================================
# Convenience Functions
# =============================================================================

def create_homeostat(
    domain: str = "general",
    mode: HomeostatMode = HomeostatMode.SUGGEST,
) -> Homeostat:
    """Create a homeostat with domain-appropriate setpoints."""
    return Homeostat(
        setpoints=EpistemicSetpoints.for_domain(domain),
        mode=mode,
    )


def create_setpoints(domain: str = "general") -> EpistemicSetpoints:
    """Create domain-specific setpoints."""
    return EpistemicSetpoints.for_domain(domain)


def observe_and_tune(
    homeostat: Homeostat,
    *,
    revision_rate: float = 0.0,
    contradiction_rate: float = 0.0,
    hedge_rate: float = 0.0,
    refusal_rate: float = 0.0,
    support_deficit_rate: float = 0.0,
    retrieval_coverage: float = 1.0,
    thermal_instability: float = 0.0,
    thermal_regime: str = "normal",
    turn: int = 0,
    total_commits: int = 0,
    total_proposals: int = 0,
) -> TuningDelta:
    """One-shot: build vitals, observe, return tuning."""
    vitals = EpistemicVitals(
        revision_rate=revision_rate,
        contradiction_rate=contradiction_rate,
        hedge_rate=hedge_rate,
        refusal_rate=refusal_rate,
        support_deficit_rate=support_deficit_rate,
        retrieval_coverage=retrieval_coverage,
        thermal_instability=thermal_instability,
        thermal_regime=thermal_regime,
        turn=turn,
        total_commits=total_commits,
        total_proposals=total_proposals,
    )
    return homeostat.observe(vitals)
