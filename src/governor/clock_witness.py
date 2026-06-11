# SPDX-License-Identifier: Apache-2.0
"""Clock witness — make bad subtraction annoying.

Bare integer seconds are how the clock costume gets on stage: a gap computed as
``exercise_at - standing_observed_at`` looks fine, but the type says "number," so
the goblin says "math" — when the two numbers could be wall time, two unrelated
clocks, different boot epochs, two hosts, or a value the claim smuggled in.

This module is NOT time infrastructure. It is the minimum needed to make the
illegal subtraction refuse itself:

> **A gap is not a difference between numbers. It is a difference between
> compatible clock witnesses.** Time is not ambient; it is a witnessed input.

The gap (elapsed bound) is computed only over **monotonic** readings from the same
source and the same epoch — wall clocks step backward under NTP correction, so a
gap across a step is garbage with an ISO 8601 smile. Wall time is a *different
object* (:class:`WallWitness`), display-only or a freshness basis, never the gap
basis. No shared ``int``; no "timestamp" alias — that is where laundering sneaks in.

Scope here (matches the operator's concrete patch): the monotonic gap basis. The
fuller clock-witness surface (three-valued freshness over wall + uncertainty, the
timestamp-laundering / self-attested-freshness refusals) is spec'd in
``working/clock-witness-spec.md`` as follow-on — the hero's predicate is the gap,
which runs on monotonic and does not consult wall freshness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


class GapBasisMismatch(ValueError):
    """Two monotonic readings are not subtractable: different sources, or one
    went backwards. Refuse to subtract rather than subtract confidently."""


class MonotonicEpochMismatch(ValueError):
    """Two monotonic readings come from different epochs (e.g. a reboot between
    them). The classic cross-reboot garbage gap — refused, not computed."""


@dataclass(frozen=True)
class MonotonicReading:
    """A reading from a monotonic clock. ``source`` identifies the clock;
    ``epoch`` pins the continuity domain (a boot-id / process start) so readings
    across a reset cannot be silently subtracted. Subtraction is licensed only
    between readings sharing both."""

    source: str
    epoch: str
    ns: int

    def __post_init__(self) -> None:
        if not self.source or not isinstance(self.source, str):
            raise GapBasisMismatch("monotonic source must be a non-empty string")
        if not self.epoch or not isinstance(self.epoch, str):
            raise MonotonicEpochMismatch("monotonic epoch must be a non-empty string")
        if not isinstance(self.ns, int) or isinstance(self.ns, bool):
            raise GapBasisMismatch(
                f"monotonic ns must be an int, got {type(self.ns).__name__}"
            )


@dataclass(frozen=True)
class WallWitness:
    """A civil/absolute time observation. A DIFFERENT object from a monotonic
    reading on purpose — wall time may serve freshness (validity intervals) or
    just human display, but it is NEVER the gap basis. ``uncertainty_ms`` is
    measured or ``None`` (honestly unknown) — never fiat precision.

    ``observed_at`` is an ISO-8601 string (JSON-safe and deterministic for the
    golden corpus; a datetime would break byte-frozen fixtures)."""

    observed_at: str
    uncertainty_ms: int | None  # measured, or None = honestly unknown
    source: str  # e.g. "ntp_tracked" | "system_clock_unsynced"
    role: Literal["freshness_basis", "display_only"]

    def __post_init__(self) -> None:
        if self.role not in ("freshness_basis", "display_only"):
            raise ValueError(
                f"wall witness role must be freshness_basis|display_only, "
                f"got {self.role!r}"
            )
        if self.uncertainty_ms is not None and (
            not isinstance(self.uncertainty_ms, int)
            or isinstance(self.uncertainty_ms, bool)
        ):
            raise ValueError("uncertainty_ms must be an int (measured) or None")

    def to_block(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at,
            "uncertainty_ms": self.uncertainty_ms,
            "source": self.source,
            "role": self.role,
        }


def elapsed_ns(start: MonotonicReading, end: MonotonicReading) -> int:
    """Elapsed nanoseconds between two monotonic readings — the ONLY licensed
    subtraction. Refuses incompatible bases rather than producing a confident
    garbage number.

    Raises :class:`GapBasisMismatch` on differing sources or a backwards reading,
    :class:`MonotonicEpochMismatch` on differing epochs.
    """
    if start.source != end.source:
        raise GapBasisMismatch(
            f"monotonic source mismatch: {start.source!r} vs {end.source!r} — "
            f"a gap is a difference between compatible clock witnesses, not numbers"
        )
    if start.epoch != end.epoch:
        raise MonotonicEpochMismatch(
            f"monotonic epoch mismatch: {start.epoch!r} vs {end.epoch!r} — "
            f"readings span a clock reset; refusing to subtract"
        )
    if end.ns < start.ns:
        raise GapBasisMismatch(
            f"monotonic reading went backwards: end {end.ns} < start {start.ns}"
        )
    return end.ns - start.ns


def gap_basis_block(start: MonotonicReading, end: MonotonicReading) -> dict[str, Any]:
    """The receipt's ``gap_basis`` block — names the clock witnesses the gap was
    computed over (so a reader can re-check soundness), not just the difference."""
    return {
        "kind": "monotonic",
        "source": start.source,
        "epoch": start.epoch,
        "start_ns": start.ns,
        "end_ns": end.ns,
    }
