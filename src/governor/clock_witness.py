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

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol


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


# ---------------------------------------------------------------------------
# Layer A — wall-clock freshness (three-valued) + anti-laundering custody.
#
# The gap above runs on monotonic readings. Freshness/expiry is a DIFFERENT
# surface: a claim carries a validity interval [valid_from, valid_until); the
# EVALUATOR observes "now" as [t-e, t+e] and asks whether the claim is current.
# Two doctrines are load-bearing here (spec: working/clock-witness-spec.md):
#   1. `unknown` uncertainty is OUTSIDE the trichotomy — it refuses
#      (blocked_clock_uncertain), it does not render a freshness verdict.
#      `indeterminate` is reserved for a MEASURED, admissible interval that
#      straddles a boundary.
#   2. The claim is not its own clock. The evaluator observation is a distinct
#      type minted ONLY by an evaluator-owned ClockSampler (token-gated, no
#      deserialization path), so untrusted claim data has no route to become the
#      clock the evaluator judges it by. (Custody closes the untrusted path and
#      accidental construction; it does NOT stop the trusted evaluator from
#      deliberately importing the token — that is out of the threat model. No
#      compile-time impossibility is claimed.)
# ---------------------------------------------------------------------------

#: Closed verdict set of ``freshness_verdict`` (Ruling 1 names authoritative;
#: pre-ruling ``blocked_expired`` is superseded by ``expired_under_clock_policy``).
FRESH_CURRENT = "current_under_clock_policy"
FRESH_EXPIRED = "expired_under_clock_policy"
FRESH_NOT_YET_VALID = "blocked_not_yet_valid"
FRESH_INDETERMINATE = "indeterminate_under_clock_policy"
FRESH_CLOCK_UNCERTAIN = "blocked_clock_uncertain"
FRESH_MISSING_WITNESS = "blocked_missing_clock_witness"

#: ``reason`` values carried ONLY on ``blocked_clock_uncertain``.
REASON_UNCERTAINTY_UNKNOWN = "uncertainty_unknown"
REASON_UNCERTAINTY_EXCEEDS_POLICY = "uncertainty_exceeds_policy"

#: Module-private capability token. Only a ClockSampler holds it; it is what
#: makes ``EvaluatorWallObservation`` un-mintable from claim data.
_SAMPLER_TOKEN = object()


def _iso_to_epoch_ms(iso: str) -> int:
    """Parse ISO-8601 → epoch milliseconds (int). One unit throughout Layer A
    (the wall/civil side); the monotonic gap stays in ns and is untouched."""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


@dataclass(frozen=True)
class ClaimInterval:
    """The claim's validity window ``[valid_from_ms, valid_until_ms)`` — from
    inclusive, until exclusive. This is the ONLY freshness input derived from
    claim data. Both bounds are mandatory (open-ended validity is not Layer A —
    pass a far-future ``valid_until`` if you need it)."""

    valid_from_ms: int
    valid_until_ms: int

    @classmethod
    def from_iso(cls, valid_from: str, valid_until: str) -> ClaimInterval:
        return cls(_iso_to_epoch_ms(valid_from), _iso_to_epoch_ms(valid_until))


class EvaluatorWallObservation:
    """An EVALUATOR-SIDE reading of "now" as ``[observed_at_ms ± uncertainty_ms]``.

    Minted ONLY by a :class:`ClockSampler` (the ``_token`` gate); there is no
    ``from_dict``/deserialization path, so a claim — which arrives as data — can
    never become one. ``uncertainty_ms=None`` means honestly *unknown* (a system
    clock cannot testify to its own uncertainty without an external reference)."""

    __slots__ = ("observed_at_ms", "uncertainty_ms", "source")

    def __init__(
        self,
        observed_at_ms: int,
        uncertainty_ms: int | None,
        source: str,
        *,
        _token: object,
    ) -> None:
        if _token is not _SAMPLER_TOKEN:
            raise TypeError(
                "EvaluatorWallObservation is minted only by a ClockSampler — the "
                "claim is not its own clock (custody: no evaluator observation may "
                "be built from claim-supplied data)"
            )
        if uncertainty_ms is not None:
            if not isinstance(uncertainty_ms, int) or isinstance(uncertainty_ms, bool):
                raise ValueError("uncertainty_ms must be an int (measured ms) or None (unknown)")
            if uncertainty_ms < 0:
                # The module refuses backwards monotonic readings (elapsed_ns); the
                # analogous invariant here: a negative ε would invert [t-e, t+e].
                raise ValueError("uncertainty_ms must be non-negative measured ms")
        object.__setattr__(self, "observed_at_ms", int(observed_at_ms))
        object.__setattr__(self, "uncertainty_ms", uncertainty_ms)
        object.__setattr__(self, "source", source)


class ClockSampler(Protocol):
    """Evaluator-owned clock. The ONLY sanctioned producer of an
    :class:`EvaluatorWallObservation`. Test doubles implement this Protocol to
    inject a fixed/fake clock — never by constructing "trusted" JSON."""

    def sample(self) -> EvaluatorWallObservation: ...


class SystemClockSampler:
    """Reads the host wall clock. ``uncertainty_ms=None`` unless an external
    reference (NTP/chrony tracking) supplies a measured value — never a
    flattering fiat number."""

    def __init__(self, source: str = "system_clock_unsynced", uncertainty_ms: int | None = None) -> None:
        self._source = source
        self._uncertainty_ms = uncertainty_ms

    def sample(self) -> EvaluatorWallObservation:
        return EvaluatorWallObservation(
            int(time.time() * 1000), self._uncertainty_ms, self._source, _token=_SAMPLER_TOKEN,
        )


@dataclass(frozen=True)
class FreshnessPolicy:
    """``max_skew_ms``: a MEASURED uncertainty wider than this refuses as
    ``blocked_clock_uncertain`` / ``uncertainty_exceeds_policy``."""

    max_skew_ms: int


@dataclass(frozen=True)
class FreshnessResult:
    """The verdict layer preserves the trichotomy: this RETURNS one of the closed
    verdicts (never raises), so a later reader can distinguish "refused because
    stale" from "refused because the witness couldn't tell". The GATE decides
    which verdicts refuse. ``reason`` is set only for ``blocked_clock_uncertain``."""

    verdict: str
    reason: str | None = None


def freshness_verdict(
    claim: ClaimInterval,
    observation: EvaluatorWallObservation | None,
    policy: FreshnessPolicy,
) -> FreshnessResult:
    """Three-valued freshness over an evaluator-side wall observation. Total;
    first match wins (spec Ruling 1). Never raises."""
    # --- prerequisites (outside the freshness trichotomy) ---
    if observation is None:
        return FreshnessResult(FRESH_MISSING_WITNESS)
    if observation.uncertainty_ms is None:
        return FreshnessResult(FRESH_CLOCK_UNCERTAIN, REASON_UNCERTAINTY_UNKNOWN)
    if observation.uncertainty_ms > policy.max_skew_ms:
        return FreshnessResult(FRESH_CLOCK_UNCERTAIN, REASON_UNCERTAINTY_EXCEEDS_POLICY)

    # --- measured, admissible ε: the ONLY domain that yields a freshness verdict ---
    eps = observation.uncertainty_ms
    lo = observation.observed_at_ms - eps          # [t-e, t+e], closed
    hi = observation.observed_at_ms + eps
    if lo >= claim.valid_until_ms:                  # confidently at/after exclusive end
        return FreshnessResult(FRESH_EXPIRED)
    if hi < claim.valid_from_ms:                    # confidently before inclusive start
        return FreshnessResult(FRESH_NOT_YET_VALID)
    if claim.valid_from_ms <= lo and hi < claim.valid_until_ms:  # wholly inside validity
        return FreshnessResult(FRESH_CURRENT)
    return FreshnessResult(FRESH_INDETERMINATE)     # straddles valid_from or valid_until
