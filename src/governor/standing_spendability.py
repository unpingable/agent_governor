# SPDX-License-Identifier: Apache-2.0
"""Standing-before-spendability gate — the two-clock temporal-lapse seam.

Ratified 2026-06-12 (operator decision-grade, the demo's hero specimen).

The directional kernel orders the chain ``standing -> wicket -> spendability``.
This gate sits at the standing->spendability edge (post-admission, pre-spend) and
answers one question: **is the standing observation still fresh enough, at
exercise time, to spend on?** Standing can be valid when observed (t=40) and void
by the time it is exercised (t=51) because its horizon expired in the gap
(t=50) — naive auth says yes, custody says no.

Two doctrine commitments shape this module:

  * **Witnesses expose the murder hallway; policy decides the gap**
    (`docs/constellation-zoning.md` §Standing). The standing *witness* exposes
    the clocks; this *gate* is the policy that evaluates them. So the check is
    NOT folded into ``StandingClient.verify()`` (which checks existence, not
    freshness) — bundling witness and policy is the exact collapse the
    constellation evicts. This is its own seam with its own receipt.

  * **A gap is a difference between compatible clock witnesses, not numbers.**
    The gap runs on :class:`~governor.clock_witness.MonotonicReading` values
    (same source + same epoch); ``elapsed_ns`` REFUSES incompatible bases rather
    than subtracting confidently. The mandatory-basis discipline is enforced by
    type — a :class:`StandingWindow` cannot be built from bare integer seconds
    (the clock costume). Wall time, if present, rides along ``display_only`` and
    is never the gap basis (wall steps backward under NTP; a gap across a step is
    garbage with an ISO 8601 smile). For the single-host demo, one process /
    one monotonic epoch makes the gap *sound*, and the receipt can prove it.

The gate emits a receipt on BOTH paths (refusal on lapse, pass within horizon),
and the receipt always carries the full two-clock block — the witness exposes the
hallway whether or not the spend is admitted. Following the seam pattern of the
standing / wicket / LA clients, the GATE emits; the orchestrator composes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from governor.clock_witness import (
    MonotonicReading,
    WallWitness,
    elapsed_ns,
    gap_basis_block,
)
from governor.linear_accountant_client import (
    REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED,
    ReceiptSink,
)

# Seam / gate identity.
STANDING_SPENDABILITY_SEAM = "standing_spendability_seam"
STANDING_SPENDABILITY_GATE = STANDING_SPENDABILITY_SEAM

# Verdicts (drawn from GateReceiptSystem's existing VALID_VERDICTS; no new
# verdict name invented).
SPENDABILITY_VERDICT_BOUNDED = "pass"
SPENDABILITY_VERDICT_REFUSED = "block"

# Lapse coverage tags — the honest state of the standing across the gap.
LAPSE_WITHIN_HORIZON = "within_horizon"
LAPSE_EXCEEDED_HORIZON = "exceeded_horizon"

# The gate's closed refusal vocabulary (a single kind — it owns exactly one
# refusal). The kind itself lives in the canonical S4-lite set in
# linear_accountant_client; this is the per-seam closed subset the gate is
# allowed to emit, mirroring _STANDING_SEAM_REFUSAL_KINDS / _LA_SEAM_*.
_SPENDABILITY_SEAM_REFUSAL_KINDS = frozenset(
    {REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED}
)


class MalformedStandingWindowError(ValueError):
    """A :class:`StandingWindow` was constructed with a malformed gap basis —
    e.g. a bare number where a :class:`MonotonicReading` is required. A gap check
    without an attested monotonic basis is a bound on numbers, not on time; it is
    refused at construction, never coerced into an advisory pass. (Incompatible
    but well-typed readings refuse later, at subtraction, via
    ``GapBasisMismatch`` / ``MonotonicEpochMismatch``.)"""


@dataclass(frozen=True)
class StandingWindow:
    """The window the gate evaluates. The GAP runs on monotonic readings (same
    source + epoch); wall time, if present, is display-only and is NEVER the gap
    basis.

      * ``standing_observed`` (MonotonicReading) — gap start (standing witnessed valid).
      * ``exercise``          (MonotonicReading) — gap end (spend attempted).
      * ``bound_ns``          (int) — the standing's freshness budget in ns: the most
                                      stale the standing may be at exercise. The gap
                                      (``elapsed_ns(observed, exercise)``) exceeding
                                      ``bound_ns`` is the lapse.
      * ``wall``              (WallWitness | None) — display_only / freshness; NOT
                                                     load-bearing for the gap.
      * ``capacity_commit``   (MonotonicReading | None) — optional; for the block's
                                                          capacity-commit model age.

    The mandatory-clock-basis discipline is now enforced BY TYPE: a
    ``MonotonicReading`` carries its source + epoch, so a gap without an attested
    basis is unrepresentable, and a subtraction across incompatible readings
    refuses (``GapBasisMismatch`` / ``MonotonicEpochMismatch``) rather than
    producing a confident garbage number. Bare integer seconds — the clock costume
    — are gone.
    """

    standing_observed: MonotonicReading
    exercise: MonotonicReading
    bound_ns: int
    wall: Optional[WallWitness] = None
    capacity_commit: Optional[MonotonicReading] = None

    def __post_init__(self) -> None:
        if not isinstance(self.standing_observed, MonotonicReading):
            raise MalformedStandingWindowError(
                "standing_observed must be a MonotonicReading (the gap basis), "
                "not a bare number — a gap is a difference between compatible "
                "clock witnesses, not numbers."
            )
        if not isinstance(self.exercise, MonotonicReading):
            raise MalformedStandingWindowError(
                "exercise must be a MonotonicReading (the gap basis), not a number."
            )
        if (
            not isinstance(self.bound_ns, int)
            or isinstance(self.bound_ns, bool)
            or self.bound_ns < 0
        ):
            raise MalformedStandingWindowError(
                f"bound_ns must be a non-negative int (ns), got {self.bound_ns!r}"
            )
        if self.wall is not None and not isinstance(self.wall, WallWitness):
            raise MalformedStandingWindowError("wall must be a WallWitness or None")
        if self.capacity_commit is not None and not isinstance(
            self.capacity_commit, MonotonicReading
        ):
            raise MalformedStandingWindowError(
                "capacity_commit must be a MonotonicReading or None"
            )


@dataclass(frozen=True)
class SpendabilityVerdict:
    """The gate's verdict. ``bounded`` is the decision; ``block`` is the full
    two-clock 'murder hallway' the witness exposes (always populated, on both
    the pass and refusal paths). ``reason`` is the typed refusal kind when not
    bounded, else ``None``. ``receipt_id`` is the gate receipt minted."""

    bounded: bool
    reason: Optional[str]
    block: dict[str, Any]
    receipt_id: Optional[str] = None

    @property
    def refused(self) -> bool:
        return not self.bounded


@dataclass(frozen=True)
class SpendabilityRefusal:
    """Chain outcome when the standing-spendability gate refuses. Carries the
    typed ``kind``, the two-clock ``block``, and the emitted ``receipt_id`` so
    the orchestrator can return it verbatim and a renderer can show both clocks
    and the gap."""

    kind: str
    block: dict[str, Any]
    receipt_id: Optional[str] = None
    detail: str = ""


def build_spendability_block(window: StandingWindow) -> dict[str, Any]:
    """Compute the murder-hallway block — the witnesses the gap was computed over,
    not just the difference.

    The gap is ``elapsed_ns(standing_observed, exercise)`` — which REFUSES
    (``GapBasisMismatch`` / ``MonotonicEpochMismatch``) when the two readings are
    not subtractable, rather than producing a number. ``overage_ns`` is how far
    past the bound the gap fell (0 when within). Wall time, if present, rides
    along ``display_only`` and is never part of the gap.
    """
    gap_ns = elapsed_ns(window.standing_observed, window.exercise)
    exceeded = gap_ns > window.bound_ns
    block: dict[str, Any] = {
        "gap_basis": gap_basis_block(window.standing_observed, window.exercise),
        "gap_ns": gap_ns,
        "bound_ns": window.bound_ns,
        "overage_ns": max(0, gap_ns - window.bound_ns),
        "lapse_coverage": (
            LAPSE_EXCEEDED_HORIZON if exceeded else LAPSE_WITHIN_HORIZON
        ),
    }
    if window.capacity_commit is not None:
        # Capacity-commit staleness at exercise, computed on the same basis.
        block["capacity_commit_model_age_ns"] = elapsed_ns(
            window.capacity_commit, window.exercise
        )
    if window.wall is not None:
        block["wall"] = window.wall.to_block()
    return block


def evaluate_spendability_window(window: StandingWindow) -> SpendabilityVerdict:
    """Pure decision: is the monotonic gap (observed→exercise) within the
    standing's freshness bound? Bounded iff ``gap_ns <= bound_ns``. Raises on an
    incompatible clock basis (refusing to subtract) rather than guessing.
    Receipt-less (no sink); :class:`StandingSpendabilityGate` wraps with emission.
    """
    block = build_spendability_block(window)
    bounded = block["gap_ns"] <= window.bound_ns
    reason = None if bounded else REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED
    return SpendabilityVerdict(bounded=bounded, reason=reason, block=block)


class StandingSpendabilityGate:
    """The standing-before-spendability seam. Constructed with a
    ``ReceiptSink`` (the same wrapped sink the chain's other seams use, so the
    gate receipt is origin-mode stamped like the rest). ``check(window)``
    evaluates the window, emits a receipt carrying the two-clock block on both
    paths, and returns either a bounded :class:`SpendabilityVerdict` (caller
    proceeds to spend) or a :class:`SpendabilityRefusal` (caller short-circuits).
    """

    def __init__(self, receipt_sink: Optional[ReceiptSink] = None):
        self._receipt_sink = receipt_sink

    def check(self, window: StandingWindow) -> SpendabilityVerdict | SpendabilityRefusal:
        verdict = evaluate_spendability_window(window)
        receipt_id = self._emit(window, verdict)
        if verdict.bounded:
            return SpendabilityVerdict(
                bounded=True,
                reason=None,
                block=verdict.block,
                receipt_id=receipt_id,
            )
        return SpendabilityRefusal(
            kind=REFUSAL_STANDING_BEFORE_SPENDABILITY_NOT_BOUNDED,
            block=verdict.block,
            receipt_id=receipt_id,
            detail=(
                f"monotonic gap {verdict.block['gap_ns']}ns "
                f"(source {window.standing_observed.source!r}, epoch "
                f"{window.standing_observed.epoch!r}) exceeds bound "
                f"{window.bound_ns}ns by {verdict.block['overage_ns']}ns"
            ),
        )

    def _emit(
        self, window: StandingWindow, verdict: SpendabilityVerdict
    ) -> Optional[str]:
        if self._receipt_sink is None:
            return None
        if (not verdict.bounded) and (
            verdict.reason not in _SPENDABILITY_SEAM_REFUSAL_KINDS
        ):
            # Closed-vocab guard — the seam refuses to mint a kind it does not
            # own. A bug in the gate, not a runtime data error.
            raise AssertionError(
                f"standing_spendability gate attempted to emit refusal kind "
                f"{verdict.reason!r}, not in {sorted(_SPENDABILITY_SEAM_REFUSAL_KINDS)}"
            )
        evidence_bundle: dict[str, Any] = dict(verdict.block)
        evidence_bundle["bounded"] = verdict.bounded
        if not verdict.bounded:
            evidence_bundle["refusal_kind"] = verdict.reason
        # Standing-spendability sits after admission; it is the chain origin
        # from this seam's own vantage (the orchestrator threads parents at the
        # chain level), so no parent here.
        evidence_bundle["parent_receipt_ids"] = []
        # Subject bytes encode the window (monotonic basis + readings + bound) so
        # identical windows content-address to the same receipt id.
        so = window.standing_observed
        subject_bytes = (
            f"{so.source}:{so.epoch}:{so.ns}|{window.exercise.ns}|{window.bound_ns}"
        ).encode("utf-8")
        receipt = self._receipt_sink.emit(
            gate=STANDING_SPENDABILITY_GATE,
            verdict=(
                SPENDABILITY_VERDICT_BOUNDED
                if verdict.bounded
                else SPENDABILITY_VERDICT_REFUSED
            ),
            subject_kind="standing_spendability_window",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "standing_spendability", "refusal_vocabulary": "S4_lite_v1"},
        )
        return receipt.receipt_id
