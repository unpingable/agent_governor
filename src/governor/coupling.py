"""
Governor Coupling: Homeostat → Ultrastability one-way protocol.

The meta-todo identified the key architectural risk: if both the Homeostat
(E7) and the UltrastabilityController (E6) can independently mutate S₁
parameters, we get a two-headed governor.  The fix:

    **Homeostat produces recommendations; Ultrastability decides.**

Contract:
  1. Homeostat outputs a TuningDelta (desired adjustments).
  2. The coupling layer translates it into a TuningIntent.
  3. The UltrastabilityController evaluates the intent against
     S₀/S₁ bounds, freeze state, and pathology, then accepts
     or rejects each proposed change.
  4. The result is an IntentOutcome with per-parameter verdicts.

No S₁ mutation happens outside UltrastabilityController.apply_adaptation().

Anti-oscillation measures (meta-todo #2-#5):
  - **Deadband**: per-mapping threshold below which intent is ignored (jitter).
  - **Accumulator**: fractional intent carried across submissions until it
    crosses a step boundary (prevents "screaming into the void").
  - **Remaining intent**: clipped deltas are explicitly *discarded*, not
    remembered.  Homeostat re-derives from vitals each epoch, so carrying
    residuals would create a second integrator.  Logged deterministically.
  - **Freeze feedback**: FROZEN verdict is a first-class signal; callers
    should switch Homeostat to OBSERVE_ONLY.

Usage:
    coupling = GovernorCoupling(controller)
    intent = TuningIntent.from_tuning_delta(tuning_delta, context="brainstorm")
    outcome = coupling.submit(intent)
    # outcome.verdict tells you ACCEPTED / PARTIAL / REJECTED / FROZEN
    # outcome.frozen_signal → True when upstream should stop tuning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .homeostat import TuningDelta, ExplorationContext
from .ultrastability import (
    UltrastabilityController,
    AdaptationVerdict,
    AdaptationRecord,
    ParameterDirection,
    Pathology,
)


# =============================================================================
# Enums
# =============================================================================

class IntentVerdict(str, Enum):
    """Outcome of submitting a TuningIntent."""

    ACCEPTED = "accepted"
    """All proposed changes were applied."""

    PARTIAL = "partial"
    """Some changes applied, some rejected (bounds/frozen/etc)."""

    REJECTED = "rejected"
    """No changes applied — all proposals outside bounds or no-ops."""

    FROZEN = "frozen"
    """Controller is frozen — no changes possible until human unfreeze."""

    NO_MAPPINGS = "no_mappings"
    """No parameter mappings matched the tuning delta."""


# =============================================================================
# Parameter Mapping
# =============================================================================

@dataclass
class ParameterMapping:
    """
    Maps a TuningDelta field to an S₁ regulatory parameter.

    The `gain` controls how the delta field is translated:
      proposed_delta = (tuning_value - neutral) * gain

    For multipliers (neutral=1.0):  gain maps deviation-from-1 to S₁ delta.
    For biases (neutral=0.0):       gain maps the bias directly to S₁ delta.

    Anti-oscillation:
      `deadband` — ignore |delta| below this threshold (jitter suppression).
      Defaults to 0.0 (no deadband) for backward compat.
    """
    tuning_field: str            # field on TuningDelta
    parameter_name: str          # S₁ parameter name
    gain: float                  # translation multiplier
    neutral: float = 0.0        # the "no change" value for the tuning field
    deadband: float = 0.0       # ignore |delta| below this threshold
    description: str = ""

    def compute_delta(self, tuning: TuningDelta) -> float:
        """Compute the S₁ delta from a TuningDelta, applying deadband."""
        value = getattr(tuning, self.tuning_field, self.neutral)
        raw = (value - self.neutral) * self.gain
        if abs(raw) < self.deadband:
            return 0.0
        return raw

    def to_dict(self) -> dict[str, Any]:
        return {
            "tuning_field": self.tuning_field,
            "parameter_name": self.parameter_name,
            "gain": self.gain,
            "neutral": self.neutral,
            "deadband": self.deadband,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParameterMapping:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


# Default mappings: TuningDelta fields → S₁ parameters
#
# Semantic axis: each mapping is monotone in "tighten vs loosen".
#   - "tighten" means: raise evidence bar, raise independence, lower tolerance
#   - "loosen" means: lower evidence bar, lower independence, raise tolerance
#
# Deadbands: suppress jitter.  Larger deadband on high-impact knobs (#5).
DEFAULT_MAPPINGS: list[ParameterMapping] = [
    ParameterMapping(
        tuning_field="confidence_ceiling_mult",
        parameter_name="evidence_threshold",
        gain=-0.1,             # lower confidence → raise evidence threshold
        neutral=1.0,
        deadband=0.005,
        description="Lower confidence ceiling → demand more evidence (tighten)",
    ),
    ParameterMapping(
        tuning_field="require_support_bias",
        parameter_name="independence_threshold",
        gain=0.1,              # more support needed → raise independence
        neutral=0.0,
        deadband=0.005,
        description="Higher support requirement → demand more independence (tighten)",
    ),
    ParameterMapping(
        tuning_field="revision_cost_mult",
        parameter_name="resolution_cost",
        gain=5.0,              # higher cost mult → higher resolution cost
        neutral=1.0,
        deadband=0.01,
        description="Expensive revisions → increase resolution cost (tighten)",
    ),
    ParameterMapping(
        tuning_field="hedge_preference",
        parameter_name="glass_threshold",
        gain=-5.0,             # more hedging → lower glass threshold (tighter)
        neutral=0.0,
        deadband=0.01,
        description="More hedging preferred → lower contradiction tolerance (tighten)",
    ),
    ParameterMapping(
        tuning_field="horizon_mult",
        parameter_name="claim_timeout_ms",
        gain=2000.0,           # shorter horizon → shorter timeout (reduced from 5000)
        neutral=1.0,
        deadband=0.02,         # high-impact knob — stronger deadband
        description="Shorter horizon → reduce claim timeout (high-impact, dampened)",
    ),
]


# =============================================================================
# TuningIntent
# =============================================================================

@dataclass
class ParameterProposal:
    """A single proposed S₁ parameter change."""
    parameter_name: str
    delta: float
    source_field: str          # which TuningDelta field produced this
    source_value: float        # the raw TuningDelta field value

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "delta": self.delta,
            "source_field": self.source_field,
            "source_value": self.source_value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParameterProposal:
        return cls(**d)


@dataclass
class TuningIntent:
    """
    A request from the Homeostat to adjust S₁ parameters.

    This is the Homeostat's *recommendation*. The UltrastabilityController
    decides whether to honour it.
    """
    proposals: list[ParameterProposal]
    source_urgency: float = 0.0
    source_context: str = "standard"
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @classmethod
    def from_tuning_delta(
        cls,
        tuning: TuningDelta,
        mappings: list[ParameterMapping] | None = None,
        context: str = "standard",
    ) -> TuningIntent:
        """Build a TuningIntent from a Homeostat TuningDelta."""
        if mappings is None:
            mappings = DEFAULT_MAPPINGS

        proposals = []
        for m in mappings:
            delta = m.compute_delta(tuning)
            if abs(delta) < 1e-9:
                continue  # skip no-ops
            proposals.append(ParameterProposal(
                parameter_name=m.parameter_name,
                delta=delta,
                source_field=m.tuning_field,
                source_value=getattr(tuning, m.tuning_field, 0.0),
            ))

        return cls(
            proposals=proposals,
            source_urgency=tuning.source_urgency,
            source_context=context,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposals": [p.to_dict() for p in self.proposals],
            "source_urgency": self.source_urgency,
            "source_context": self.source_context,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuningIntent:
        return cls(
            proposals=[ParameterProposal.from_dict(p) for p in d.get("proposals", [])],
            source_urgency=d.get("source_urgency", 0.0),
            source_context=d.get("source_context", "standard"),
            timestamp=d.get("timestamp", ""),
        )


# =============================================================================
# Intent Outcome
# =============================================================================

@dataclass
class ChangeResult:
    """Result of a single parameter change proposal."""
    parameter_name: str
    accepted: bool
    old_value: float | None = None
    new_value: float | None = None
    proposed_delta: float = 0.0
    actual_delta: float = 0.0
    was_clamped: bool = False
    reject_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_name": self.parameter_name,
            "accepted": self.accepted,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "proposed_delta": self.proposed_delta,
            "actual_delta": self.actual_delta,
            "was_clamped": self.was_clamped,
            "reject_reason": self.reject_reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeResult:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


@dataclass
class IntentOutcome:
    """Full result of submitting a TuningIntent."""
    verdict: IntentVerdict
    changes: list[ChangeResult] = field(default_factory=list)
    accepted_count: int = 0
    rejected_count: int = 0
    freeze_reason: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    # Remaining intent: how much delta was discarded due to clamping.
    # Logged deterministically per meta-todo #3.  Always discarded (not carried).
    discarded_delta: dict[str, float] = field(default_factory=dict)

    # Freeze feedback: True when upstream (Homeostat) should switch to OBSERVE_ONLY.
    # Set when verdict is FROZEN or consecutive freeze count exceeds threshold.
    frozen_signal: bool = False

    # Count of consecutive FROZEN verdicts (for escalation tracking)
    consecutive_freezes: int = 0

    @property
    def any_accepted(self) -> bool:
        return self.accepted_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "changes": [c.to_dict() for c in self.changes],
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "freeze_reason": self.freeze_reason,
            "timestamp": self.timestamp,
            "discarded_delta": self.discarded_delta,
            "frozen_signal": self.frozen_signal,
            "consecutive_freezes": self.consecutive_freezes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IntentOutcome:
        return cls(
            verdict=IntentVerdict(d["verdict"]),
            changes=[ChangeResult.from_dict(c) for c in d.get("changes", [])],
            accepted_count=d.get("accepted_count", 0),
            rejected_count=d.get("rejected_count", 0),
            freeze_reason=d.get("freeze_reason", ""),
            timestamp=d.get("timestamp", ""),
            discarded_delta=d.get("discarded_delta", {}),
            frozen_signal=d.get("frozen_signal", False),
            consecutive_freezes=d.get("consecutive_freezes", 0),
        )


# =============================================================================
# Coupling Configuration
# =============================================================================

@dataclass
class CouplingConfig:
    """Configuration for anti-oscillation measures."""

    # Accumulator: carry fractional intent until it crosses a step
    accumulator_enabled: bool = True

    # Remaining intent policy: DISCARD or CARRY
    # DISCARD (default): clipped deltas are thrown away each submission.
    #   Rationale: Homeostat re-derives urgency from vitals each epoch,
    #   so carrying residuals would create a second integrator.
    # CARRY: residuals are added back to the accumulator.
    carry_residuals: bool = False

    # Consecutive freeze count before emitting observe_only_recommended
    freeze_escalation_threshold: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "accumulator_enabled": self.accumulator_enabled,
            "carry_residuals": self.carry_residuals,
            "freeze_escalation_threshold": self.freeze_escalation_threshold,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CouplingConfig:
        return cls(**{k: d[k] for k in d if k in cls.__dataclass_fields__})


# =============================================================================
# Governor Coupling
# =============================================================================

class GovernorCoupling:
    """
    One-way bridge: Homeostat → Ultrastability.

    Translates TuningIntents into S₁ parameter changes, routing
    every mutation through the UltrastabilityController so that
    S₀/S₁ bounds and pathology state are always enforced.

    Design rules:
    1. Homeostat RECOMMENDS — it never touches S₁ directly.
    2. Ultrastability DECIDES — it is the sole mutator of S₁.
    3. Every submission is logged for audit.
    4. Frozen controller → all intents rejected.
    """

    def __init__(
        self,
        controller: UltrastabilityController,
        mappings: list[ParameterMapping] | None = None,
        max_history: int = 200,
        config: CouplingConfig | None = None,
    ) -> None:
        self.controller = controller
        self.mappings = mappings or list(DEFAULT_MAPPINGS)
        self.max_history = max_history
        self.config = config or CouplingConfig()
        self._history: list[tuple[TuningIntent, IntentOutcome]] = []

        # Accumulators: carry fractional intent per parameter (meta-todo #2)
        self._accumulators: dict[str, float] = {}

        # Consecutive freeze counter (meta-todo #4)
        self._consecutive_freezes: int = 0

    def submit(self, intent: TuningIntent) -> IntentOutcome:
        """
        Submit a TuningIntent for evaluation by the UltrastabilityController.

        The controller checks each proposal against S₁ bounds and
        applies if admissible.  Frozen controllers reject everything.

        Anti-oscillation:
        - Accumulators carry fractional deltas across submissions.
        - Clipped deltas are discarded (not carried) to prevent double-integration.
        - Consecutive FROZEN verdicts escalate a frozen_signal to upstream.
        """
        # 1. Frozen check
        if self.controller.frozen:
            self._consecutive_freezes += 1
            escalated = (
                self._consecutive_freezes
                >= self.config.freeze_escalation_threshold
            )
            outcome = IntentOutcome(
                verdict=IntentVerdict.FROZEN,
                freeze_reason=self.controller.freeze_reason or "controller frozen",
                frozen_signal=True,
                consecutive_freezes=self._consecutive_freezes,
            )
            self._record(intent, outcome)
            return outcome

        # Not frozen — reset consecutive freeze counter
        self._consecutive_freezes = 0

        # 2. No proposals?
        if not intent.proposals:
            outcome = IntentOutcome(verdict=IntentVerdict.NO_MAPPINGS)
            self._record(intent, outcome)
            return outcome

        # 3. Apply accumulators and evaluate each proposal
        changes: list[ChangeResult] = []
        accepted = 0
        rejected = 0
        discarded: dict[str, float] = {}

        for proposal in intent.proposals:
            effective_proposal = self._apply_accumulator(proposal)
            result = self._evaluate_proposal(effective_proposal)
            changes.append(result)
            if result.accepted:
                accepted += 1
                # Clear the accumulator for this parameter — intent was realized
                self._accumulators.pop(result.parameter_name, None)
            else:
                rejected += 1

            # Track discarded delta (meta-todo #3)
            if result.was_clamped and not self.config.carry_residuals:
                residual = result.proposed_delta - result.actual_delta
                if abs(residual) > 1e-9:
                    discarded[result.parameter_name] = residual
                    # Explicitly discard — do NOT add back to accumulator
                    # (Homeostat re-derives from vitals; carrying creates double integrator)

        # 4. Determine overall verdict
        if accepted == 0:
            verdict = IntentVerdict.REJECTED
        elif rejected == 0:
            verdict = IntentVerdict.ACCEPTED
        else:
            verdict = IntentVerdict.PARTIAL

        outcome = IntentOutcome(
            verdict=verdict,
            changes=changes,
            accepted_count=accepted,
            rejected_count=rejected,
            discarded_delta=discarded,
        )
        self._record(intent, outcome)
        return outcome

    def submit_tuning_delta(
        self,
        tuning: TuningDelta,
        context: str = "standard",
    ) -> IntentOutcome:
        """Convenience: build intent from TuningDelta and submit."""
        intent = TuningIntent.from_tuning_delta(
            tuning, mappings=self.mappings, context=context,
        )
        return self.submit(intent)

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    def _apply_accumulator(self, proposal: ParameterProposal) -> ParameterProposal:
        """Add accumulated fractional intent to this proposal's delta."""
        if not self.config.accumulator_enabled:
            return proposal

        name = proposal.parameter_name
        accumulated = self._accumulators.get(name, 0.0)
        effective_delta = proposal.delta + accumulated

        # Store the new accumulated value (will be cleared if accepted)
        self._accumulators[name] = effective_delta

        return ParameterProposal(
            parameter_name=proposal.parameter_name,
            delta=effective_delta,
            source_field=proposal.source_field,
            source_value=proposal.source_value,
        )

    def _evaluate_proposal(self, proposal: ParameterProposal) -> ChangeResult:
        """Evaluate and (if admissible) apply a single parameter proposal."""
        params = self.controller.parameters

        # Unknown parameter?
        if proposal.parameter_name not in params.names:
            return ChangeResult(
                parameter_name=proposal.parameter_name,
                accepted=False,
                proposed_delta=proposal.delta,
                reject_reason=f"unknown parameter: {proposal.parameter_name}",
            )

        spec = params.get(proposal.parameter_name)
        old_value = spec.current

        # Propose the change through ParameterSpec bounds
        new_value, was_clamped = spec.propose_change(proposal.delta)

        # Skip if no effective change
        actual_delta = new_value - old_value
        if abs(actual_delta) < 1e-9:
            return ChangeResult(
                parameter_name=proposal.parameter_name,
                accepted=False,
                old_value=old_value,
                new_value=old_value,
                proposed_delta=proposal.delta,
                actual_delta=0.0,
                was_clamped=was_clamped,
                reject_reason="no effective change (at bounds or delta too small)",
            )

        # Apply through the controller's parameters
        spec.apply(new_value)

        # Log the adaptation record
        direction = (
            ParameterDirection.INCREASE if actual_delta > 0
            else ParameterDirection.DECREASE
        )
        record = AdaptationRecord(
            epoch_id=self.controller.current_epoch,
            timestamp=datetime.now(timezone.utc),
            parameter=proposal.parameter_name,
            old_value=old_value,
            new_value=new_value,
            delta=actual_delta,
            was_clamped=was_clamped,
            reason=f"coupling: {proposal.source_field}={proposal.source_value:.3f}",
            direction=direction,
        )
        self.controller.history.add_record(record)

        return ChangeResult(
            parameter_name=proposal.parameter_name,
            accepted=True,
            old_value=old_value,
            new_value=new_value,
            proposed_delta=proposal.delta,
            actual_delta=actual_delta,
            was_clamped=was_clamped,
        )

    def _record(self, intent: TuningIntent, outcome: IntentOutcome) -> None:
        """Record submission for audit."""
        self._history.append((intent, outcome))
        if len(self._history) > self.max_history:
            self._history = self._history[-self.max_history:]

    # -----------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------

    @property
    def history(self) -> list[tuple[TuningIntent, IntentOutcome]]:
        return list(self._history)

    @property
    def total_submissions(self) -> int:
        return len(self._history)

    def acceptance_rate(self, window: int = 50) -> float:
        """Fraction of submissions with any accepted changes."""
        recent = self._history[-window:]
        if not recent:
            return 0.0
        return sum(1 for _, o in recent if o.any_accepted) / len(recent)

    @property
    def accumulators(self) -> dict[str, float]:
        """Current accumulator state (fractional intent per parameter)."""
        return dict(self._accumulators)

    @property
    def consecutive_freezes(self) -> int:
        """How many consecutive submissions hit a frozen controller."""
        return self._consecutive_freezes

    def get_diagnostics(self) -> dict[str, Any]:
        """Diagnostic snapshot."""
        return {
            "total_submissions": self.total_submissions,
            "acceptance_rate": self.acceptance_rate(),
            "controller_frozen": self.controller.frozen,
            "mapping_count": len(self.mappings),
            "recent_verdicts": [
                o.verdict.value for _, o in self._history[-10:]
            ],
            "accumulators": dict(self._accumulators),
            "consecutive_freezes": self._consecutive_freezes,
            "accumulator_enabled": self.config.accumulator_enabled,
            "carry_residuals": self.config.carry_residuals,
        }

    # -----------------------------------------------------------------
    # Serialisation
    # -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "mappings": [m.to_dict() for m in self.mappings],
            "max_history": self.max_history,
            "config": self.config.to_dict(),
            "accumulators": dict(self._accumulators),
            "consecutive_freezes": self._consecutive_freezes,
            "history": [
                {"intent": i.to_dict(), "outcome": o.to_dict()}
                for i, o in self._history
            ],
        }

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        controller: UltrastabilityController,
    ) -> GovernorCoupling:
        mappings = [ParameterMapping.from_dict(m) for m in d.get("mappings", [])]
        config = CouplingConfig.from_dict(d["config"]) if "config" in d else None
        gc = cls(
            controller=controller,
            mappings=mappings or None,
            max_history=d.get("max_history", 200),
            config=config,
        )
        gc._accumulators = dict(d.get("accumulators", {}))
        gc._consecutive_freezes = d.get("consecutive_freezes", 0)
        gc._history = [
            (
                TuningIntent.from_dict(entry["intent"]),
                IntentOutcome.from_dict(entry["outcome"]),
            )
            for entry in d.get("history", [])
        ]
        return gc


# =============================================================================
# Convenience
# =============================================================================

def create_coupling(
    controller: UltrastabilityController | None = None,
    config: CouplingConfig | None = None,
) -> GovernorCoupling:
    """Create a coupling bridge with default mappings."""
    if controller is None:
        controller = UltrastabilityController()
    return GovernorCoupling(controller, config=config)
