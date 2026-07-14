# SPDX-License-Identifier: Apache-2.0
"""Layer A — three-valued wall freshness + anti-laundering custody (the crime table)."""

from __future__ import annotations

import pytest

from governor.clock_witness import (
    _SAMPLER_TOKEN,
    FRESH_CLOCK_UNCERTAIN,
    FRESH_CURRENT,
    FRESH_EXPIRED,
    FRESH_INDETERMINATE,
    FRESH_MISSING_WITNESS,
    FRESH_NOT_YET_VALID,
    REASON_UNCERTAINTY_EXCEEDS_POLICY,
    REASON_UNCERTAINTY_UNKNOWN,
    ClaimInterval,
    ClockSampler,
    EvaluatorWallObservation,
    FreshnessPolicy,
    SystemClockSampler,
    freshness_verdict,
)

CLAIM = ClaimInterval(valid_from_ms=1_000, valid_until_ms=2_000)
POLICY = FreshnessPolicy(max_skew_ms=100)


class FakeSampler:
    """An evaluator-side test double: implements ClockSampler by minting a FIXED
    observation. It holds the module-private token (in-process evaluator code
    may — that is the honest custody boundary), NOT by constructing 'trusted' JSON."""

    def __init__(self, observed_at_ms: int, uncertainty_ms: int | None) -> None:
        self._at = observed_at_ms
        self._u = uncertainty_ms

    def sample(self) -> EvaluatorWallObservation:
        return EvaluatorWallObservation(self._at, self._u, "test_clock", _token=_SAMPLER_TOKEN)


def _obs(observed_at_ms: int, uncertainty_ms: int | None) -> EvaluatorWallObservation:
    return FakeSampler(observed_at_ms, uncertainty_ms).sample()


# --- the three-valued domain (measured, admissible ε) -------------------------

def test_current_when_wholly_inside_validity():
    r = freshness_verdict(CLAIM, _obs(1_500, 10), POLICY)
    assert r.verdict == FRESH_CURRENT and r.reason is None


def test_expired_at_or_after_exclusive_end():
    # lo = 2000 == valid_until (exclusive) -> expired
    r = freshness_verdict(CLAIM, _obs(2_000, 0), POLICY)
    assert r.verdict == FRESH_EXPIRED


def test_not_yet_valid_confidently_before_start():
    r = freshness_verdict(CLAIM, _obs(900, 10), POLICY)  # hi=910 < 1000
    assert r.verdict == FRESH_NOT_YET_VALID


def test_indeterminate_straddles_valid_until():
    r = freshness_verdict(CLAIM, _obs(1_990, 20), POLICY)  # [1970,2010] straddles 2000
    assert r.verdict == FRESH_INDETERMINATE


def test_indeterminate_straddles_valid_from():
    r = freshness_verdict(CLAIM, _obs(1_005, 20), POLICY)  # [985,1025] straddles 1000
    assert r.verdict == FRESH_INDETERMINATE


def test_boundary_hi_equals_valid_from_is_indeterminate_not_not_yet_valid():
    # hi == valid_from (1000): NOT not_yet_valid (strict <); lo<1000 so not current
    r = freshness_verdict(CLAIM, _obs(990, 10), POLICY)
    assert r.verdict == FRESH_INDETERMINATE


# --- unknown is OUTSIDE the trichotomy (the load-bearing ruling) --------------

def test_unknown_uncertainty_refuses_not_indeterminate():
    r = freshness_verdict(CLAIM, _obs(1_500, None), POLICY)
    assert r.verdict == FRESH_CLOCK_UNCERTAIN
    assert r.reason == REASON_UNCERTAINTY_UNKNOWN
    assert r.verdict != FRESH_INDETERMINATE  # the distinction the design preserves


def test_measured_but_too_wide_refuses_with_distinct_reason():
    r = freshness_verdict(CLAIM, _obs(1_500, 101), POLICY)  # ε > max_skew_ms
    assert r.verdict == FRESH_CLOCK_UNCERTAIN
    assert r.reason == REASON_UNCERTAINTY_EXCEEDS_POLICY


def test_missing_witness_refuses():
    r = freshness_verdict(CLAIM, None, POLICY)
    assert r.verdict == FRESH_MISSING_WITNESS and r.reason is None


def test_precedence_unknown_before_straddle():
    # an observation that WOULD straddle, but ε unknown -> uncertain wins (branch order)
    r = freshness_verdict(CLAIM, _obs(1_990, None), POLICY)
    assert r.verdict == FRESH_CLOCK_UNCERTAIN


# --- anti-laundering custody: the claim is not its own clock ------------------

def test_evaluator_observation_cannot_be_built_without_the_token():
    # "a claim's timestamp used as the clock" — unrepresentable via the public path:
    # constructing the evaluator's form from claim-supplied data raises.
    with pytest.raises(TypeError):
        EvaluatorWallObservation(1_500, 10, "claim_supplied")  # no token


def test_wrong_token_is_refused():
    with pytest.raises(TypeError):
        EvaluatorWallObservation(1_500, 10, "x", _token=object())


def test_no_deserialization_path_exists():
    # no from_dict/from_json route for untrusted (claim) data to become an observation
    assert not hasattr(EvaluatorWallObservation, "from_dict")
    assert not hasattr(EvaluatorWallObservation, "from_json")


def test_sampler_is_the_sanctioned_producer():
    sampler = SystemClockSampler(source="system_clock_unsynced")
    obs = sampler.sample()
    assert isinstance(obs, EvaluatorWallObservation)
    assert obs.uncertainty_ms is None  # honest unknown, not a fiat number
    # structural conformance to the ClockSampler Protocol (no @runtime_checkable needed)
    assert callable(getattr(sampler, "sample", None))


# --- units / parsing ----------------------------------------------------------

def test_negative_uncertainty_refused_at_construction():
    # a negative ε would invert [t-e, t+e]; refuse it (module's backwards-reading invariant)
    with pytest.raises(ValueError):
        _obs(1_500, -20)


def test_claim_interval_from_iso_parses_to_epoch_ms():
    ci = ClaimInterval.from_iso("2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z")
    assert ci.valid_until_ms - ci.valid_from_ms == 1_000  # one second = 1000 ms
