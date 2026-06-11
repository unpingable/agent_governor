# SPDX-License-Identifier: Apache-2.0
"""Standing-before-spendability gate — the two-clock temporal-lapse seam.

Pins the three ratified checks (2026-06-12):
  * gap-exceeds-bound refuses with the full receipt block;
  * within-bound twin passes;
  * the negative — a window without an attested clock_basis is unrepresentable
    (construction refuses it), so no gap check ever runs on numbers-not-time.

Plus the gate's teeth: closed-vocab emission, receipt on both paths, block
fields, purity of the evaluator.
"""

from __future__ import annotations

from typing import Any

import pytest

from governor.standing_spendability import (
    LAPSE_EXCEEDED_HORIZON,
    LAPSE_WITHIN_HORIZON,
    REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED,
    MalformedStandingWindowError,
    SpendabilityRefusal,
    SpendabilityVerdict,
    StandingSpendabilityGate,
    StandingWindow,
    build_spendability_block,
    evaluate_spendability_window,
)

BASIS = "single_host_monotonic"


def _window(exercise_at: int, *, clock_basis: str = BASIS) -> StandingWindow:
    # t=40 observed, horizon t=50; exercise time is the variable.
    return StandingWindow(
        standing_observed_at=40,
        capacity_commit_at=50,
        horizon_expires_at=50,
        exercise_at=exercise_at,
        clock_basis=clock_basis,
    )


class _RecordingSink:
    def __init__(self) -> None:
        self.emits: list[dict[str, Any]] = []

    def emit(self, *, gate, verdict, subject_kind, subject_bytes,
             evidence_bundle, gate_config, **kwargs):
        rec = {"gate": gate, "verdict": verdict, "evidence_bundle": evidence_bundle,
               "receipt_id": f"rcpt-{len(self.emits)}"}
        self.emits.append(rec)
        return type("R", (), rec)()


# --- the three ratified pins -------------------------------------------------


class TestRatifiedPins:
    def test_gap_exceeds_bound_refuses_with_full_block(self):
        sink = _RecordingSink()
        gate = StandingSpendabilityGate(receipt_sink=sink)
        out = gate.check(_window(exercise_at=51))  # 1s past horizon
        assert isinstance(out, SpendabilityRefusal)
        assert out.kind == REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED
        # Full murder-hallway block, both clocks + the gap + the basis.
        b = out.block
        assert b["standing_observed_at"] == 40
        assert b["horizon_expires_at"] == 50
        assert b["exercise_at"] == 51
        assert b["gap"] == 1
        assert b["standing_observed_model_age"] == 11
        assert b["lapse_coverage"] == LAPSE_EXCEEDED_HORIZON
        assert b["clock_basis"] == BASIS
        # A real receipt was minted, verdict=block, carrying the block.
        assert len(sink.emits) == 1
        assert sink.emits[0]["verdict"] == "block"
        assert sink.emits[0]["evidence_bundle"]["clock_basis"] == BASIS
        assert out.receipt_id == "rcpt-0"

    def test_within_bound_twin_passes(self):
        sink = _RecordingSink()
        gate = StandingSpendabilityGate(receipt_sink=sink)
        out = gate.check(_window(exercise_at=45))  # within horizon
        assert isinstance(out, SpendabilityVerdict)
        assert out.bounded is True
        assert out.reason is None
        assert out.block["lapse_coverage"] == LAPSE_WITHIN_HORIZON
        # The twin still emits a receipt (the witness exposes the hallway even
        # on the pass), verdict=pass, carrying the same block shape + basis.
        assert len(sink.emits) == 1
        assert sink.emits[0]["verdict"] == "pass"
        assert sink.emits[0]["evidence_bundle"]["clock_basis"] == BASIS

    def test_missing_clock_basis_is_unrepresentable(self):
        # The negative: a window without an attested clock basis cannot be
        # constructed at all -- so no gap check ever runs on numbers-not-time.
        with pytest.raises(MalformedStandingWindowError):
            _window(exercise_at=51, clock_basis="")
        with pytest.raises(MalformedStandingWindowError):
            StandingWindow(
                standing_observed_at=40,
                capacity_commit_at=50,
                horizon_expires_at=50,
                exercise_at=51,
                clock_basis=None,  # type: ignore[arg-type]
            )


# --- boundary + purity -------------------------------------------------------


class TestBoundaryAndPurity:
    def test_exactly_at_horizon_is_bounded(self):
        # exercise == horizon is within bound (<=). One second later is not.
        assert evaluate_spendability_window(_window(50)).bounded is True
        assert evaluate_spendability_window(_window(51)).bounded is False

    def test_evaluator_is_pure_no_sink_no_receipt(self):
        v = evaluate_spendability_window(_window(51))
        assert v.refused is True
        assert v.reason == REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED
        assert v.receipt_id is None  # pure path mints nothing

    def test_block_builder_is_deterministic(self):
        w = _window(51)
        assert build_spendability_block(w) == build_spendability_block(w)

    def test_gate_without_sink_returns_verdict_no_emit(self):
        gate = StandingSpendabilityGate(receipt_sink=None)
        out = gate.check(_window(51))
        assert isinstance(out, SpendabilityRefusal)
        assert out.receipt_id is None

    def test_non_int_clock_value_refused(self):
        with pytest.raises(MalformedStandingWindowError):
            StandingWindow(
                standing_observed_at=40,
                capacity_commit_at=50,
                horizon_expires_at=50,
                exercise_at="51",  # type: ignore[arg-type]
                clock_basis=BASIS,
            )
