# SPDX-License-Identifier: Apache-2.0
"""Clock witness — the minimum that makes a bad subtraction refuse itself.

> A gap is not a difference between numbers. It is a difference between
> compatible clock witnesses.

These are the "two ugly tests" the operator asked for, plus the type guards:
elapsed_ns is the ONLY licensed subtraction and it refuses incompatible bases
(different source, different epoch, backwards) rather than returning a confident
garbage number; WallWitness is a DIFFERENT object that can never be the gap basis.
"""

from __future__ import annotations

import pytest

from governor.clock_witness import (
    GapBasisMismatch,
    MonotonicEpochMismatch,
    MonotonicReading,
    WallWitness,
    elapsed_ns,
    gap_basis_block,
)

SOURCE = "process_monotonic"
EPOCH = "boot:demo-single-host"


def _r(ns: int, *, source: str = SOURCE, epoch: str = EPOCH) -> MonotonicReading:
    return MonotonicReading(source=source, epoch=epoch, ns=ns)


class TestElapsedRefusesIncompatibleBases:
    def test_compatible_readings_subtract(self):
        assert elapsed_ns(_r(40), _r(51)) == 11

    def test_same_ns_different_epoch_refuses(self):
        # Identical numeric ns, different epoch (a reboot between the two) — the
        # classic cross-reset garbage gap. Refused, not computed.
        with pytest.raises(MonotonicEpochMismatch):
            elapsed_ns(_r(40, epoch="boot:A"), _r(40, epoch="boot:B"))

    def test_different_source_refuses(self):
        with pytest.raises(GapBasisMismatch):
            elapsed_ns(_r(40, source="clock_a"), _r(51, source="clock_b"))

    def test_backwards_reading_refuses(self):
        with pytest.raises(GapBasisMismatch):
            elapsed_ns(_r(51), _r(40))

    def test_zero_gap_is_legal(self):
        assert elapsed_ns(_r(40), _r(40)) == 0


class TestMonotonicReadingConstruction:
    def test_empty_source_refused(self):
        with pytest.raises(GapBasisMismatch):
            MonotonicReading(source="", epoch=EPOCH, ns=40)

    def test_empty_epoch_refused(self):
        with pytest.raises(MonotonicEpochMismatch):
            MonotonicReading(source=SOURCE, epoch="", ns=40)

    def test_non_int_ns_refused(self):
        with pytest.raises(GapBasisMismatch):
            MonotonicReading(source=SOURCE, epoch=EPOCH, ns="40")  # type: ignore[arg-type]

    def test_bool_ns_refused(self):
        # bool is an int subclass — a True smuggled as ns is a costume.
        with pytest.raises(GapBasisMismatch):
            MonotonicReading(source=SOURCE, epoch=EPOCH, ns=True)  # type: ignore[arg-type]


class TestWallWitnessIsADifferentObject:
    def test_valid_wall_witness(self):
        w = WallWitness(
            observed_at="2026-06-09T00:00:40Z",
            uncertainty_ms=None,
            source="system_clock_unsynced",
            role="display_only",
        )
        assert w.to_block()["role"] == "display_only"

    def test_bad_role_refused(self):
        with pytest.raises(ValueError):
            WallWitness(
                observed_at="2026-06-09T00:00:40Z",
                uncertainty_ms=None,
                source="ntp_tracked",
                role="gap_basis",  # type: ignore[arg-type]
            )

    def test_fiat_uncertainty_must_be_int_or_none(self):
        with pytest.raises(ValueError):
            WallWitness(
                observed_at="2026-06-09T00:00:40Z",
                uncertainty_ms="5",  # type: ignore[arg-type]
                source="ntp_tracked",
                role="freshness_basis",
            )

    def test_wall_cannot_be_passed_to_elapsed_ns(self):
        # The whole point: wall time is not subtractable as a gap. It is not a
        # MonotonicReading, so elapsed_ns refuses it (AttributeError on .source
        # access path is acceptable; what matters is it does not compute a gap).
        w = WallWitness(
            observed_at="2026-06-09T00:00:40Z",
            uncertainty_ms=None,
            source="ntp_tracked",
            role="freshness_basis",
        )
        with pytest.raises((AttributeError, GapBasisMismatch, TypeError)):
            elapsed_ns(w, _r(51))  # type: ignore[arg-type]


class TestGapBasisBlock:
    def test_block_names_the_witnesses(self):
        block = gap_basis_block(_r(40), _r(51))
        assert block == {
            "kind": "monotonic",
            "source": SOURCE,
            "epoch": EPOCH,
            "start_ns": 40,
            "end_ns": 51,
        }
