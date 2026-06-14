# SPDX-License-Identifier: Apache-2.0
"""P4.0d — observation admissibility tests: in_bounds is DERIVED, never stamped.

The headline test is structural: ``ObservationFacts`` has no ``in_bounds`` field, so
"observation says it survived → therefore it survived" is unrepresentable. The rest
pin the derivation (rollback tripped / metric unobserved / disqualified / clock
basis) refusal-first, then the single in-bounds path.
"""

from __future__ import annotations

import pytest

from governor.clock_witness import MonotonicReading
from governor.observation_admissibility import (
    NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE,
    NOT_IN_BOUNDS_DISQUALIFYING_EVENT,
    NOT_IN_BOUNDS_METRIC_UNOBSERVED,
    NOT_IN_BOUNDS_REASONS,
    NOT_IN_BOUNDS_ROLLBACK_TRIPPED,
    TRIP_GE,
    TRIP_GT,
    TRIP_LE,
    TRIP_LT,
    MalformedObservationError,
    ObservationFacts,
    SurvivalBound,
    SurvivalObservationInput,
    derive_in_bounds,
)

SRC = "process_monotonic"
EPOCH = "boot:demo-single-host"


def _reading(ns: int = 2_000, source: str = SRC, epoch: str = EPOCH) -> MonotonicReading:
    return MonotonicReading(source=source, epoch=epoch, ns=ns)


def _bound() -> SurvivalBound:
    # Trial holds in-bounds while refusal_rate <= 0.2; trips when refusal_rate > 0.2.
    return SurvivalBound(metric="refusal_rate", trip_comparator=TRIP_GT, threshold=0.2)


def _facts(**overrides) -> ObservationFacts:
    base = dict(
        trial_id="trial-1",
        observed_at=_reading(),
        metrics=(("refusal_rate", 0.1),),
        disqualifying_events=(),
    )
    base.update(overrides)
    return ObservationFacts(**base)


# --- The headline: in_bounds cannot be writer-stamped ------------------------


def test_observation_facts_has_no_in_bounds_field():
    """The classic bug ('observation says it survived → therefore it survived') is
    unrepresentable: there is no in_bounds slot to stamp."""
    with pytest.raises(TypeError):
        ObservationFacts(
            trial_id="trial-1",
            observed_at=_reading(),
            metrics=(("refusal_rate", 0.1),),
            in_bounds=True,  # no such field
        )


def test_evaluator_is_sole_authority_tripped_facts_are_not_in_bounds():
    """No caller intent can rescue a fact set that trips the bound — the deriver
    reads only facts + bound."""
    facts = _facts(metrics=(("refusal_rate", 0.95),))  # way over threshold
    verdict = derive_in_bounds(facts, _bound())
    assert verdict.in_bounds is False
    assert NOT_IN_BOUNDS_ROLLBACK_TRIPPED in verdict.reasons


# --- The single in-bounds path -----------------------------------------------


def test_within_bound_no_disqualifiers_is_in_bounds():
    verdict = derive_in_bounds(_facts(), _bound())
    assert verdict.in_bounds is True
    assert verdict.reasons == ()


def test_bundle_derive_matches_function():
    inp = SurvivalObservationInput(facts=_facts(), bound=_bound())
    assert inp.derive().in_bounds is True


# --- Rollback-trigger refusals (each comparator) -----------------------------


def test_gt_trips_above_threshold():
    v = derive_in_bounds(_facts(metrics=(("refusal_rate", 0.3),)), _bound())
    assert v.in_bounds is False
    assert NOT_IN_BOUNDS_ROLLBACK_TRIPPED in v.reasons


def test_gt_at_threshold_does_not_trip():
    # trip_comparator gt: observed == threshold is still in-bounds.
    v = derive_in_bounds(_facts(metrics=(("refusal_rate", 0.2),)), _bound())
    assert v.in_bounds is True


def test_ge_lt_le_comparators_trip_as_specified():
    ge = SurvivalBound(metric="m", trip_comparator=TRIP_GE, threshold=1.0)
    assert derive_in_bounds(_facts(metrics=(("m", 1.0),)), ge).in_bounds is False
    lt = SurvivalBound(metric="m", trip_comparator=TRIP_LT, threshold=1.0)
    assert derive_in_bounds(_facts(metrics=(("m", 0.5),)), lt).in_bounds is False
    assert derive_in_bounds(_facts(metrics=(("m", 1.0),)), lt).in_bounds is True
    le = SurvivalBound(metric="m", trip_comparator=TRIP_LE, threshold=1.0)
    assert derive_in_bounds(_facts(metrics=(("m", 1.0),)), le).in_bounds is False


# --- Cannot claim survival on an unmeasured metric ---------------------------


def test_bound_metric_unobserved_is_not_in_bounds():
    facts = _facts(metrics=(("some_other_metric", 0.0),))  # refusal_rate absent
    v = derive_in_bounds(facts, _bound())
    assert v.in_bounds is False
    assert NOT_IN_BOUNDS_METRIC_UNOBSERVED in v.reasons


# --- Disqualifying events ----------------------------------------------------


def test_disqualifying_event_is_not_in_bounds():
    facts = _facts(disqualifying_events=("manual_rollback",))
    v = derive_in_bounds(facts, _bound())
    assert v.in_bounds is False
    assert NOT_IN_BOUNDS_DISQUALIFYING_EVENT in v.reasons


# --- Clock-basis attribution -------------------------------------------------


def test_incompatible_clock_basis_is_not_in_bounds():
    facts = _facts(observed_at=_reading(epoch="boot:OTHER"))
    v = derive_in_bounds(facts, _bound(), expected_basis=(SRC, EPOCH))
    assert v.in_bounds is False
    assert NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE in v.reasons


def test_matching_clock_basis_is_fine():
    v = derive_in_bounds(_facts(), _bound(), expected_basis=(SRC, EPOCH))
    assert v.in_bounds is True


# --- Dual reasons never collapse ---------------------------------------------


def test_multiple_reasons_all_surface():
    facts = _facts(
        metrics=(("refusal_rate", 0.95),),  # tripped
        disqualifying_events=("crash",),  # disqualified
        observed_at=_reading(epoch="boot:OTHER"),  # wrong basis
    )
    v = derive_in_bounds(facts, _bound(), expected_basis=(SRC, EPOCH))
    assert v.in_bounds is False
    for r in (
        NOT_IN_BOUNDS_DISQUALIFYING_EVENT,
        NOT_IN_BOUNDS_ROLLBACK_TRIPPED,
        NOT_IN_BOUNDS_CLOCK_BASIS_INCOMPATIBLE,
    ):
        assert r in v.reasons
    assert len(v.reasons) == len(set(v.reasons))
    assert set(v.reasons) <= NOT_IN_BOUNDS_REASONS


# --- Construction discipline -------------------------------------------------


def test_unknown_comparator_refused():
    with pytest.raises(MalformedObservationError):
        SurvivalBound(metric="m", trip_comparator="approximately", threshold=0.0)


def test_empty_metric_refused():
    with pytest.raises(MalformedObservationError):
        SurvivalBound(metric="", trip_comparator=TRIP_GT, threshold=0.0)


def test_empty_trial_id_refused():
    with pytest.raises(MalformedObservationError):
        ObservationFacts(
            trial_id="", observed_at=_reading(), metrics=(("refusal_rate", 0.1),)
        )


def test_malformed_metric_pair_refused():
    with pytest.raises(MalformedObservationError):
        ObservationFacts(
            trial_id="t", observed_at=_reading(), metrics=(("refusal_rate", True),)
        )
