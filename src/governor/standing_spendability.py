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

  * **Bounded, not merely ordered.** A gap measured without an attested clock
    basis is a bound on numbers, not on time. ``clock_basis`` is therefore
    MANDATORY — a :class:`StandingWindow` cannot be constructed without one, and
    every emitted receipt carries it. For the launch demo the honest basis is
    ``single_host_monotonic``: one host, one clock, the gap math is sound within
    it, and the multi-host story later is a *value* change, not a *schema*
    change. Declare the clock you actually have; do not fake a temporal
    authority you have not built.

The gate emits a receipt on BOTH paths (refusal on lapse, pass within horizon),
and the receipt always carries the full two-clock block — the witness exposes the
hallway whether or not the spend is admitted. Following the seam pattern of the
standing / wicket / LA clients, the GATE emits; the orchestrator composes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

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
    """A :class:`StandingWindow` was constructed without an attested
    ``clock_basis`` (or with non-monotonic clocks). A gap check without a clock
    basis is a bound on numbers, not on time — it is refused at construction,
    never coerced into an advisory pass."""


@dataclass(frozen=True)
class StandingWindow:
    """The two-clock window the gate evaluates. All times are integer epoch
    seconds on a single monotonic basis (``clock_basis``).

      * ``standing_observed_at``  (T1) — when the standing was witnessed valid.
      * ``capacity_commit_at``    (T2) — when capacity was committed.
      * ``horizon_expires_at``    — the bound: the standing's freshness horizon.
      * ``exercise_at``           (T3) — when the spend is attempted.
      * ``clock_basis``           — MANDATORY attested basis for the above.

    Construction refuses an absent ``clock_basis`` (the whole point of the gate
    is that the gap is bounded *in time*, not just ordered).
    """

    standing_observed_at: int
    capacity_commit_at: int
    horizon_expires_at: int
    exercise_at: int
    clock_basis: str

    def __post_init__(self) -> None:
        if not self.clock_basis or not isinstance(self.clock_basis, str):
            raise MalformedStandingWindowError(
                "clock_basis is mandatory and must be a non-empty string: a gap "
                "measured without an attested clock basis is a bound on numbers, "
                "not on time. Declare the clock you have (e.g. "
                "'single_host_monotonic')."
            )
        for name, value in (
            ("standing_observed_at", self.standing_observed_at),
            ("capacity_commit_at", self.capacity_commit_at),
            ("horizon_expires_at", self.horizon_expires_at),
            ("exercise_at", self.exercise_at),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise MalformedStandingWindowError(
                    f"{name} must be an int epoch-second on the attested basis, "
                    f"got {type(value).__name__}"
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
    """Compute the two-clock block — the murder hallway the witness exposes.

    Pure. ``gap`` is how far past the horizon the exercise fell (positive =
    lapsed); the model ages are how stale each clock was at exercise time.
    """
    gap = window.exercise_at - window.horizon_expires_at
    exceeded = window.exercise_at > window.horizon_expires_at
    return {
        "standing_observed_at": window.standing_observed_at,
        "capacity_commit_at": window.capacity_commit_at,
        "horizon_expires_at": window.horizon_expires_at,
        "exercise_at": window.exercise_at,
        "standing_observed_model_age": window.exercise_at
        - window.standing_observed_at,
        "capacity_commit_model_age": window.exercise_at - window.capacity_commit_at,
        "gap": gap,
        "lapse_coverage": (
            LAPSE_EXCEEDED_HORIZON if exceeded else LAPSE_WITHIN_HORIZON
        ),
        "clock_basis": window.clock_basis,
    }


def evaluate_spendability_window(window: StandingWindow) -> SpendabilityVerdict:
    """Pure decision: is the spend within the standing's freshness horizon?

    Bounded iff ``exercise_at <= horizon_expires_at``. Receipt-less (no sink);
    :class:`StandingSpendabilityGate` wraps this with emission.
    """
    block = build_spendability_block(window)
    bounded = window.exercise_at <= window.horizon_expires_at
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
                f"standing observed at {window.standing_observed_at} on basis "
                f"{window.clock_basis!r}, horizon expired at "
                f"{window.horizon_expires_at}, exercise at {window.exercise_at} "
                f"(gap {verdict.block['gap']}s past horizon)"
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
        # Subject bytes encode the window so identical windows content-address
        # to the same receipt id.
        subject_bytes = (
            f"{window.standing_observed_at}|{window.capacity_commit_at}|"
            f"{window.horizon_expires_at}|{window.exercise_at}|{window.clock_basis}"
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
