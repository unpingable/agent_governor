# SPDX-License-Identifier: Apache-2.0
"""Standing-before-spendability gate — the two-clock temporal-lapse seam.

Pins the three ratified checks (2026-06-12), now on the monotonic clock basis:
  * gap-exceeds-bound refuses with the full receipt block;
  * within-bound twin passes;
  * the negative — a window cannot be built from bare integer seconds (the clock
    costume); the gap basis is a typed MonotonicReading, so a gap on
    numbers-not-time is unrepresentable, and an incompatible subtraction refuses.

Plus the gate's teeth: closed-vocab emission, receipt on both paths, block
fields, purity of the evaluator.
"""

from __future__ import annotations

from typing import Any

import pytest

from governor.clock_witness import (
    GapBasisMismatch,
    MonotonicEpochMismatch,
    MonotonicReading,
    WallWitness,
)
from governor.standing_spendability import (
    FRESHNESS_SUBCASE_EXPIRED,
    FRESHNESS_SUBCASES,
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

_S = 1_000_000_000  # ns per second
SOURCE = "process_monotonic"
EPOCH = "boot:demo-single-host"
OBSERVED_NS = 40 * _S
BOUND_NS = 10 * _S  # horizon - observed = the standing's freshness budget


def _mono(ns: int, *, source: str = SOURCE, epoch: str = EPOCH) -> MonotonicReading:
    return MonotonicReading(source=source, epoch=epoch, ns=ns)


def _window(exercise_s: int, *, wall: WallWitness | None = None) -> StandingWindow:
    # t=40 observed, horizon t=50 (bound 10s); exercise time is the variable.
    return StandingWindow(
        standing_observed=_mono(OBSERVED_NS),
        exercise=_mono(exercise_s * _S),
        bound_ns=BOUND_NS,
        wall=wall,
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
        out = gate.check(_window(exercise_s=51))  # 1s past horizon
        assert isinstance(out, SpendabilityRefusal)
        assert out.kind == REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED
        # Full murder-hallway block: the monotonic gap + bound + the named basis.
        b = out.block
        assert b["gap_ns"] == 11 * _S  # observed→exercise
        assert b["bound_ns"] == 10 * _S
        assert b["overage_ns"] == 1 * _S  # one second past the horizon
        assert b["lapse_coverage"] == LAPSE_EXCEEDED_HORIZON
        # Freshness subcase (ruling 2026-07-03): the refusal block carries the
        # machine-readable Lean-aligned diagnostic. The current two-clock gate
        # reaches exactly `expired`. Bound to the closed vocab (not a bare
        # string): structured + tested, never prose-only.
        assert b["freshness_subcase"] == FRESHNESS_SUBCASE_EXPIRED
        assert b["freshness_subcase"] in FRESHNESS_SUBCASES
        gb = b["gap_basis"]
        assert gb["kind"] == "monotonic"
        assert gb["source"] == SOURCE
        assert gb["epoch"] == EPOCH
        assert gb["start_ns"] == OBSERVED_NS
        assert gb["end_ns"] == 51 * _S
        # A real receipt was minted, verdict=block, carrying the gap basis.
        assert len(sink.emits) == 1
        assert sink.emits[0]["verdict"] == "block"
        assert sink.emits[0]["evidence_bundle"]["gap_basis"]["kind"] == "monotonic"
        assert out.receipt_id == "rcpt-0"

    def test_lineage_threaded_at_emission(self):
        # Lineage at emission or never: parents supplied to check() land in
        # the emitted bundle verbatim; default is empty (no fabricated lineage).
        sink = _RecordingSink()
        gate = StandingSpendabilityGate(receipt_sink=sink)
        gate.check(_window(exercise_s=51), parent_receipt_ids=("wicket-rcpt-abc",))
        assert sink.emits[0]["evidence_bundle"]["parent_receipt_ids"] == [
            "wicket-rcpt-abc"
        ]
        sink2 = _RecordingSink()
        StandingSpendabilityGate(receipt_sink=sink2).check(_window(exercise_s=51))
        assert sink2.emits[0]["evidence_bundle"]["parent_receipt_ids"] == []

    def test_within_bound_twin_passes(self):
        sink = _RecordingSink()
        gate = StandingSpendabilityGate(receipt_sink=sink)
        out = gate.check(_window(exercise_s=45))  # within horizon
        assert isinstance(out, SpendabilityVerdict)
        assert out.bounded is True
        assert out.reason is None
        assert out.block["lapse_coverage"] == LAPSE_WITHIN_HORIZON
        assert out.block["gap_ns"] == 5 * _S
        # The pass path carries NO freshness_subcase — there is nothing to
        # diagnose when spendability was bounded.
        assert "freshness_subcase" not in out.block
        # The twin still emits a receipt (the witness exposes the hallway even
        # on the pass), verdict=pass, carrying the same block shape + basis.
        assert len(sink.emits) == 1
        assert sink.emits[0]["verdict"] == "pass"
        assert sink.emits[0]["evidence_bundle"]["gap_basis"]["source"] == SOURCE

    def test_bare_int_clock_costume_is_unrepresentable(self):
        # The negative: a window cannot be built from bare integer seconds. The
        # gap basis is a typed MonotonicReading; a number where a reading is
        # required refuses at construction, so no gap ever runs on numbers.
        with pytest.raises(MalformedStandingWindowError):
            StandingWindow(
                standing_observed=40,  # type: ignore[arg-type]
                exercise=_mono(51 * _S),
                bound_ns=BOUND_NS,
            )
        with pytest.raises(MalformedStandingWindowError):
            StandingWindow(
                standing_observed=_mono(OBSERVED_NS),
                exercise=51 * _S,  # type: ignore[arg-type]
                bound_ns=BOUND_NS,
            )


# --- the two ugly clock tests (operator's ask) -------------------------------


class TestIncompatibleBasisRefusesAtSubtraction:
    def test_same_ns_different_epoch_refuses(self):
        # Same numeric ns, different epoch (a reboot between observation and
        # exercise) → the cross-reset garbage gap is refused, not computed.
        w = StandingWindow(
            standing_observed=_mono(OBSERVED_NS, epoch="boot:A"),
            exercise=_mono(51 * _S, epoch="boot:B"),
            bound_ns=BOUND_NS,
        )
        with pytest.raises(MonotonicEpochMismatch):
            evaluate_spendability_window(w)

    def test_different_sources_refuses(self):
        # Two unrelated clocks → a gap between them is meaningless; refuse.
        w = StandingWindow(
            standing_observed=_mono(OBSERVED_NS, source="clock_a"),
            exercise=_mono(51 * _S, source="clock_b"),
            bound_ns=BOUND_NS,
        )
        with pytest.raises(GapBasisMismatch):
            evaluate_spendability_window(w)

    def test_backwards_reading_refuses(self):
        # end < start on the same basis → a backwards monotonic reading is a
        # contradiction; refuse rather than produce a negative gap.
        w = StandingWindow(
            standing_observed=_mono(51 * _S),
            exercise=_mono(OBSERVED_NS),
            bound_ns=BOUND_NS,
        )
        with pytest.raises(GapBasisMismatch):
            build_spendability_block(w)


# --- boundary + purity -------------------------------------------------------


class TestBoundaryAndPurity:
    def test_exactly_at_horizon_is_bounded(self):
        # gap == bound is within bound (<=). One second later is not.
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

    def test_wall_rides_along_display_only_never_the_gap(self):
        wall = WallWitness(
            observed_at="2026-06-09T00:00:40Z",
            uncertainty_ms=None,
            source="system_clock_unsynced",
            role="display_only",
        )
        b = build_spendability_block(_window(51, wall=wall))
        # The wall is present for display, but the gap basis is monotonic.
        assert b["wall"]["role"] == "display_only"
        assert b["gap_basis"]["kind"] == "monotonic"

    def test_negative_bound_refused(self):
        with pytest.raises(MalformedStandingWindowError):
            StandingWindow(
                standing_observed=_mono(OBSERVED_NS),
                exercise=_mono(51 * _S),
                bound_ns=-1,
            )
