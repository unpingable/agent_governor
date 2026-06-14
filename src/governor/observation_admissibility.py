# SPDX-License-Identifier: Apache-2.0
"""P4.0d — observation admissibility: DERIVE ``in_bounds``, never stamp it.

The live-survival witness asks "did the trial survive reality?" Its load-bearing
predicate is whether a post-activation observation is **in-bounds**. That must not
be a writer-stamped vibe field::

    bad:   in_bounds: true                              # the writer says so
    good:  in_bounds = derive_in_bounds(facts, bound)   # the evaluator decides

This module owns the *good* shape. An observation carries raw FACTS (the trial it
claims to observe, the metric readings, disqualifying events, a clock reading); the
evaluator derives ``in_bounds`` from those facts against the trial's declared
**survival bound** — the evaluable form of its rollback trigger. ``ObservationFacts``
deliberately has **no ``in_bounds`` field**: there is no slot to stamp.

Scope (P4.0d — admissibility only, no producer): pure derivation + types + refusal
tests. No receipt is built, nothing is persisted, and ``evidence_count`` derivation
in ``promotion_evidence`` is untouched. P4.0e (the producer) will call
``derive_in_bounds`` to populate ``LiveSurvivalObservationReceipt.in_bounds`` — the
field becomes producer-derived, the way ``fresh``/``walkable`` are assembler-computed.

Dependency discipline: this does NOT import ``convergence_tuning`` (campaign ground
rule 6). ``SurvivalBound`` is the promotion path's own evaluable trigger; a later
``tuning_proposal_bridge`` may translate a ``convergence_tuning.RollbackTrigger`` into
a ``SurvivalBound`` with full custody — but the promotion path never depends on the
domain module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .clock_witness import MonotonicReading

# --- Trip comparators (the trigger TRIPS when observed <cmp> threshold) --------
TRIP_GT = "gt"
TRIP_GE = "ge"
TRIP_LT = "lt"
TRIP_LE = "le"
TRIP_COMPARATORS = frozenset({TRIP_GT, TRIP_GE, TRIP_LT, TRIP_LE})

# --- Closed reason vocabulary for "why an observation is not in-bounds" --------
NOT_IN_BOUNDS_DISQUALIFYING_EVENT = "observation_disqualifying_event"
NOT_IN_BOUNDS_METRIC_UNOBSERVED = "observation_bound_metric_unobserved"
NOT_IN_BOUNDS_ROLLBACK_TRIPPED = "observation_rollback_trigger_tripped"
NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE = "observation_clock_basis_incompatible"

NOT_IN_BOUNDS_REASONS = frozenset(
    {
        NOT_IN_BOUNDS_DISQUALIFYING_EVENT,
        NOT_IN_BOUNDS_METRIC_UNOBSERVED,
        NOT_IN_BOUNDS_ROLLBACK_TRIPPED,
        NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE,
    }
)

# Canonical ordering — dual reasons surface in a stable order, never collapse.
_REASON_ORDER = (
    NOT_IN_BOUNDS_DISQUALIFYING_EVENT,
    NOT_IN_BOUNDS_METRIC_UNOBSERVED,
    NOT_IN_BOUNDS_ROLLBACK_TRIPPED,
    NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE,
)


class MalformedObservationError(ValueError):
    """Observation inputs were structurally malformed — an unknown trip comparator,
    an empty metric name, an empty trial_id, or a non-tuple collection. The
    evaluator cannot derive admissibility from a shape it cannot read; refused at
    construction, never coerced into a permissive in-bounds."""


@dataclass(frozen=True)
class SurvivalBound:
    """The evaluable form of the trial's declared rollback trigger. The trigger
    **trips** when ``observed <trip_comparator> threshold``; an observation is
    in-bounds *for this metric* exactly when the trigger does NOT trip.

    Promotion-path-native (no ``convergence_tuning`` import). Mirrors the
    ``{metric, operator, threshold}`` shape so a bridge can translate one in later
    with custody, but is independently owned here.
    """

    metric: str
    trip_comparator: str
    threshold: float

    def __post_init__(self) -> None:
        if not self.metric:
            raise MalformedObservationError("SurvivalBound.metric must be non-empty")
        if self.trip_comparator not in TRIP_COMPARATORS:
            raise MalformedObservationError(
                f"trip_comparator must be one of {sorted(TRIP_COMPARATORS)}, "
                f"got {self.trip_comparator!r}"
            )
        if not isinstance(self.threshold, (int, float)) or isinstance(
            self.threshold, bool
        ):
            raise MalformedObservationError("threshold must be a real number")

    def trips(self, observed: float) -> bool:
        if self.trip_comparator == TRIP_GT:
            return observed > self.threshold
        if self.trip_comparator == TRIP_GE:
            return observed >= self.threshold
        if self.trip_comparator == TRIP_LT:
            return observed < self.threshold
        return observed <= self.threshold  # TRIP_LE

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "trip_comparator": self.trip_comparator,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SurvivalBound":
        return cls(
            metric=d["metric"],
            trip_comparator=d["trip_comparator"],
            threshold=d["threshold"],
        )


@dataclass(frozen=True)
class ObservationFacts:
    """Raw observed facts for one post-activation observation.

    **There is no ``in_bounds`` field — by design.** in-bounds is derived, not
    declared. Facts carry the trial the observation claims, a clock reading, the
    observed metric readings, and any disqualifying events. ``metrics`` is a tuple
    of ``(metric_name, observed_value)`` pairs.
    """

    trial_id: str
    observed_at: MonotonicReading
    metrics: tuple[tuple[str, float], ...]
    disqualifying_events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise MalformedObservationError("ObservationFacts.trial_id must be non-empty")
        if not isinstance(self.metrics, tuple):
            raise MalformedObservationError("metrics must be a tuple of (name, value)")
        for pair in self.metrics:
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not pair[0]
                or isinstance(pair[1], bool)
                or not isinstance(pair[1], (int, float))
            ):
                raise MalformedObservationError(
                    f"each metric must be (non-empty name, real value), got {pair!r}"
                )
        if not isinstance(self.disqualifying_events, tuple):
            raise MalformedObservationError("disqualifying_events must be a tuple")

    def metric_value(self, name: str) -> Optional[float]:
        for n, v in self.metrics:
            if n == name:
                return v
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "observed_at": {
                "source": self.observed_at.source,
                "epoch": self.observed_at.epoch,
                "ns": self.observed_at.ns,
            },
            "metrics": [[n, v] for n, v in self.metrics],
            "disqualifying_events": list(self.disqualifying_events),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ObservationFacts":
        at = d["observed_at"]
        return cls(
            trial_id=d["trial_id"],
            observed_at=MonotonicReading(
                source=at["source"], epoch=at["epoch"], ns=at["ns"]
            ),
            metrics=tuple((p[0], p[1]) for p in d["metrics"]),
            disqualifying_events=tuple(d.get("disqualifying_events", ())),
        )


@dataclass(frozen=True)
class InBoundsVerdict:
    """The derived result. ``in_bounds`` iff ``reasons`` is empty; ``reasons``
    carries EVERY failing reason in canonical order (dual reasons never collapse)."""

    in_bounds: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SurvivalObservationInput:
    """A bundle of (facts, bound, optional expected clock basis) — the full input
    to one admissibility derivation. ``expected_basis`` is the ``(source, epoch)``
    the observation's clock reading must share to be attributable to the trial's
    run; ``None`` skips the compatibility check."""

    facts: ObservationFacts
    bound: SurvivalBound
    expected_basis: Optional[tuple[str, str]] = None

    def derive(self) -> InBoundsVerdict:
        return derive_in_bounds(
            self.facts, self.bound, expected_basis=self.expected_basis
        )


def derive_in_bounds(
    facts: ObservationFacts,
    bound: SurvivalBound,
    *,
    expected_basis: Optional[tuple[str, str]] = None,
) -> InBoundsVerdict:
    """Pure, total derivation of ``in_bounds`` from raw facts + the survival bound.

    in-bounds requires ALL of:

      * no disqualifying events;
      * the bound's metric was actually observed (you cannot claim survival on a
        metric you never measured);
      * the rollback trigger did not trip on that metric;
      * (if ``expected_basis`` given) the observation's clock reading is on a
        compatible basis — an observation on a foreign clock cannot be attributed
        to the trial's run.

    All failing reasons are returned, not just the first. The caller passes facts
    and a bound; there is no ``in_bounds`` input to override — the evaluator is the
    sole authority.
    """
    reasons: set[str] = set()

    if facts.disqualifying_events:
        reasons.add(NOT_IN_BOUNDS_DISQUALIFYING_EVENT)

    observed = facts.metric_value(bound.metric)
    if observed is None:
        reasons.add(NOT_IN_BOUNDS_METRIC_UNOBSERVED)
    elif bound.trips(observed):
        reasons.add(NOT_IN_BOUNDS_ROLLBACK_TRIPPED)

    if expected_basis is not None:
        actual = (facts.observed_at.source, facts.observed_at.epoch)
        if actual != expected_basis:
            reasons.add(NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE)

    ordered = tuple(r for r in _REASON_ORDER if r in reasons)
    return InBoundsVerdict(in_bounds=not ordered, reasons=ordered)


__all__ = [
    "TRIP_GT",
    "TRIP_GE",
    "TRIP_LT",
    "TRIP_LE",
    "TRIP_COMPARATORS",
    "NOT_IN_BOUNDS_DISQUALIFYING_EVENT",
    "NOT_IN_BOUNDS_METRIC_UNOBSERVED",
    "NOT_IN_BOUNDS_ROLLBACK_TRIPPED",
    "NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE",
    "NOT_IN_BOUNDS_REASONS",
    "MalformedObservationError",
    "SurvivalBound",
    "ObservationFacts",
    "InBoundsVerdict",
    "SurvivalObservationInput",
    "derive_in_bounds",
]
