# SPDX-License-Identifier: Apache-2.0
"""P4.0b-prep — the promotion evidence substrate (receipt chain + walkability).

The P4.0a gate (``promotion_gate.evaluate_promotion_eligibility``) is pure and
honest, but it *trusts* three booleans the caller hands it:
``walkable_from_activation``, ``fresh``, and ``operator_basis_present``, plus a raw
``evidence_count``. That is fine for a gate ("witnesses expose; policy decides"),
but it means the gate can only refuse — it can never legitimately pass until
something *produces* those facts from real receipts. This module is that producer.

**The move is "checked, not typed."** Walkability is not a field a caller asserts;
it is a hash chain that either binds or does not (NLAI — an agent's say-so is a
pointer, the binding is the receipt). Freshness is not a vibe; it is
``clock_witness.elapsed_ns`` over compatible monotonic readings, which *refuses*
incompatible bases rather than subtracting confidently. Evidence count is not a
number a caller picks; it is the count of observations that (a) bind to the
activation, (b) are in-bounds, and (c) are fresh.

Pipeline::

    PromotionEvidenceBundle  --assemble_promotion_inputs-->  PromotionInputs
                                                                   |
                                              evaluate_promotion_eligibility (P4.0a, untouched)
                                                                   |
                            evaluate_promotion_from_evidence  -->  PromotionEligibility

The evidence layer adds exactly ONE refusal the gate cannot express
(``promotion_operator_basis_claims_auto`` — the red-line fence: an operator basis
that asserts auto-promotion is not a valid promotion basis). Everything else maps
onto the gate's existing closed vocabulary, now *computed* instead of asserted.

**Scope discipline (P4.0b-prep):** this models and validates evidence; it mints no
``ControlBaseline``, promotes nothing, persists nothing (no IO), ratifies no
threshold ``N`` (``required_count`` stays a caller-supplied input), and does not
weaken ``promotion_gate``. With an empty bundle the cold-start behavior is
preserved: ``evidence_count=0`` → refused. See
``working/P4-promotion-plan-2026-06-13.md`` and
``working/EXIT_2026-06-14_p4-cold-start-promotion-refused.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .clock_witness import (
    GapBasisMismatch,
    MonotonicEpochMismatch,
    MonotonicReading,
    elapsed_ns,
)
from .gate_receipt import canonical_json, content_hash
from .promotion_gate import (
    PROMOTION_EVIDENCE_INSUFFICIENT,
    PROMOTION_EVIDENCE_NOT_WALKABLE,
    PROMOTION_EVIDENCE_STALE,
    PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT,
    PROMOTION_OFF_SURFACE_TUNABLE,
    PROMOTION_OPEN_NONDISCHARGE_CLAIM,
    PROMOTION_OPERATOR_BASIS_ABSENT,
    PROMOTION_REPLAY_CORPUS_HASH_MISMATCH,
    PROMOTION_REPLAY_HARNESS_NOT_WALKABLE,
    PROMOTION_REPLAY_HOLDOUT_FAILED,
    PROMOTION_REPLAY_HOLDOUT_MISSING,
    PROMOTION_VERDICT_ELIGIBLE,
    PROMOTION_VERDICT_REFUSED,
    LiveSurvivalWitness,
    MalformedPromotionInputsError,
    PromotionEligibility,
    PromotionInputs,
    ReplayHoldoutVerdict,
    evaluate_promotion_eligibility,
)

# --- The one refusal the gate cannot express (red-line fence) -----------------
# An operator basis that asserts auto-promotion is not a valid promotion basis:
# promotion is a separate, classed act, never a session/auto side effect.
PROMOTION_OPERATOR_BASIS_CLAIMS_AUTO = "promotion_operator_basis_claims_auto"

EVIDENCE_REFUSAL_KINDS = frozenset({PROMOTION_OPERATOR_BASIS_CLAIMS_AUTO})

# Combined canonical ordering: the gate's order, then the evidence-native kind.
_COMBINED_REFUSAL_ORDER = (
    PROMOTION_EVIDENCE_INSUFFICIENT,
    PROMOTION_EVIDENCE_STALE,
    PROMOTION_EVIDENCE_NOT_WALKABLE,
    PROMOTION_REPLAY_HOLDOUT_MISSING,
    PROMOTION_REPLAY_HOLDOUT_FAILED,
    PROMOTION_REPLAY_CORPUS_HASH_MISMATCH,
    PROMOTION_REPLAY_HARNESS_NOT_WALKABLE,
    PROMOTION_OPEN_NONDISCHARGE_CLAIM,
    PROMOTION_OFF_SURFACE_TUNABLE,
    PROMOTION_KERNEL_FUSE_RATIFICATION_SIDE_EFFECT,
    PROMOTION_OPERATOR_BASIS_ABSENT,
    PROMOTION_OPERATOR_BASIS_CLAIMS_AUTO,
)


def _reading_block(r: MonotonicReading) -> dict[str, Any]:
    return {"source": r.source, "epoch": r.epoch, "ns": r.ns}


# --- Receipt types ------------------------------------------------------------


@dataclass(frozen=True)
class ActivationReceipt:
    """The root of the chain: the P3.1 activation that put the trial value in
    effect. Its ``content_hash`` is what every downstream observation must bind to
    — that binding is the walkability proof, not a caller-set flag."""

    trial_id: str
    tunable_name: str
    trial_value: Any
    prior_baseline_value: Any
    activated_at: MonotonicReading

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise MalformedPromotionInputsError("activation trial_id must be non-empty")
        if not self.tunable_name:
            raise MalformedPromotionInputsError("activation tunable_name must be non-empty")

    def identity_dict(self) -> dict[str, Any]:
        return {
            "schema": "promotion_activation_v0",
            "trial_id": self.trial_id,
            "tunable_name": self.tunable_name,
            "trial_value": self.trial_value,
            "prior_baseline_value": self.prior_baseline_value,
            "activated_at": _reading_block(self.activated_at),
        }

    @property
    def content_hash(self) -> str:
        return content_hash(canonical_json(self.identity_dict()))


@dataclass(frozen=True)
class LiveSurvivalObservationReceipt:
    """One in-bounds (or not) observation of the trial after activation. Counts
    toward survival evidence only if it binds to the activation, is in-bounds, and
    is fresh. ``activation_receipt_hash`` is the binding claim — checked against the
    activation's computed ``content_hash``, never trusted."""

    trial_id: str
    observation_id: str
    observed_at: MonotonicReading
    in_bounds: bool
    activation_receipt_hash: str
    disqualifying_events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise MalformedPromotionInputsError("observation trial_id must be non-empty")
        if not self.observation_id:
            raise MalformedPromotionInputsError("observation_id must be non-empty")
        if not self.activation_receipt_hash:
            raise MalformedPromotionInputsError(
                "observation activation_receipt_hash must be non-empty — an "
                "observation that binds to nothing is not walkable evidence"
            )
        if not isinstance(self.disqualifying_events, tuple):
            raise MalformedPromotionInputsError("disqualifying_events must be a tuple")

    @property
    def is_in_bounds(self) -> bool:
        return self.in_bounds and not self.disqualifying_events


@dataclass(frozen=True)
class ReplayHoldoutReceipt:
    """The separate falsification witness — a frozen-corpus non-regression replay.
    Richer than the gate's ``ReplayHoldoutVerdict`` (carries ``trial_id`` and a
    ``falsification_basis``); the assembler maps it down to the gate's verdict only
    when it is for the candidate's trial."""

    trial_id: str
    replay_subject: str
    passed: bool
    corpus_hash: str
    frozen_corpus_hash: str
    harness_version: str
    comparator_baseline_id: str
    falsification_basis: str = ""

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise MalformedPromotionInputsError("replay trial_id must be non-empty")

    def to_verdict(self) -> ReplayHoldoutVerdict:
        return ReplayHoldoutVerdict(
            passed=self.passed,
            corpus_hash=self.corpus_hash,
            frozen_corpus_hash=self.frozen_corpus_hash,
            harness_version=self.harness_version,
            comparator_baseline_id=self.comparator_baseline_id,
        )


@dataclass(frozen=True)
class OperatorBasisReceipt:
    """The operator's explicit promotion basis. ``explicitly_not_auto_baseline``
    must be True — an operator basis that claims auto-promotion is refused
    (the red line: promotion is a separate, classed act, never an auto side
    effect)."""

    trial_id: str
    operator_actor: str
    promotion_basis: str
    scope: str
    explicitly_not_auto_baseline: bool

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise MalformedPromotionInputsError("operator basis trial_id must be non-empty")
        if not self.operator_actor:
            raise MalformedPromotionInputsError("operator_actor must be non-empty")


@dataclass(frozen=True)
class PromotionCandidate:
    """What we are asking to promote: the tunable + value, identified by trial."""

    trial_id: str
    tunable_name: str
    trial_value: Any

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise MalformedPromotionInputsError("candidate trial_id must be non-empty")
        if not self.tunable_name:
            raise MalformedPromotionInputsError("candidate tunable_name must be non-empty")


@dataclass(frozen=True)
class PromotionEvidenceBundle:
    """The full evidence set, as receipts. The assembler walks this into a
    ``PromotionInputs`` (or a faithfully-degraded one) — it does not trust the
    bundle's contents, it checks them.

    ``evaluation_reading`` is the monotonic "now" used to compute freshness;
    ``freshness_horizon_ns`` is the staleness bound. ``required_count`` is N —
    supplied, NOT ratified here.
    """

    candidate: PromotionCandidate
    activation: Optional[ActivationReceipt]
    observations: tuple[LiveSurvivalObservationReceipt, ...]
    replay: Optional[ReplayHoldoutReceipt]
    operator_basis: Optional[OperatorBasisReceipt]
    required_count: int
    evaluation_reading: MonotonicReading
    freshness_horizon_ns: int
    allowed_tunable_surface: frozenset[str]
    open_nondischarge_claim_ids: tuple[str, ...] = ()
    kernel_fuse_ratification_side_effect: bool = False

    def __post_init__(self) -> None:
        if self.required_count < 1:
            raise MalformedPromotionInputsError(
                f"required_count (N) must be >= 1, got {self.required_count}"
            )
        if self.freshness_horizon_ns < 0:
            raise MalformedPromotionInputsError(
                f"freshness_horizon_ns must be >= 0, got {self.freshness_horizon_ns}"
            )
        if not isinstance(self.observations, tuple):
            raise MalformedPromotionInputsError("observations must be a tuple")


@dataclass(frozen=True)
class EvidenceAssembly:
    """The result of walking a bundle: the gate inputs it produced, plus any
    evidence-native refusals the gate cannot express."""

    inputs: PromotionInputs
    evidence_refusals: tuple[str, ...] = field(default_factory=tuple)


def _is_fresh(
    observed: MonotonicReading, now: MonotonicReading, horizon_ns: int
) -> bool:
    """Fresh iff the gap from observation to now is within the horizon, on a
    COMPATIBLE monotonic basis. Incompatible bases (different source/epoch, or a
    backwards reading) cannot witness freshness → not fresh (conservative)."""
    try:
        gap = elapsed_ns(observed, now)
    except (GapBasisMismatch, MonotonicEpochMismatch):
        return False
    return gap <= horizon_ns


def assemble_promotion_inputs(bundle: PromotionEvidenceBundle) -> EvidenceAssembly:
    """Walk a receipt bundle into ``PromotionInputs`` — the checked-not-typed step.

    Produces a faithfully-degraded ``PromotionInputs`` (walkable/fresh/count all
    *computed* from the chain) so the existing gate decides eligibility, plus the
    one evidence-native refusal (auto-promote basis). Never raises on a
    well-formed-but-failing bundle — it refuses by producing inputs the gate
    blocks.
    """
    cand = bundle.candidate
    evidence_refusals: set[str] = set()

    # --- Activation must exist AND match the candidate (else nothing walks) ---
    act = bundle.activation
    activation_matches = (
        act is not None
        and act.trial_id == cand.trial_id
        and act.tunable_name == cand.tunable_name
        and act.trial_value == cand.trial_value
    )
    act_hash = act.content_hash if (act is not None and activation_matches) else None

    # --- Walk observations: each must bind (computed hash), right trial -------
    walkable = activation_matches
    bound_in_bounds: list[LiveSurvivalObservationReceipt] = []
    for obs in bundle.observations:
        binds = (
            activation_matches
            and obs.trial_id == cand.trial_id
            and obs.activation_receipt_hash == act_hash
        )
        if not binds:
            # An orphan or wrong-trial observation breaks the chain's walkability.
            walkable = False
            continue
        if obs.is_in_bounds:
            bound_in_bounds.append(obs)

    # --- Freshness over the bound, in-bounds observations ---------------------
    fresh_count = 0
    any_stale = False
    for obs in bound_in_bounds:
        if _is_fresh(obs.observed_at, bundle.evaluation_reading, bundle.freshness_horizon_ns):
            fresh_count += 1
        else:
            any_stale = True
    # Vacuously fresh when there is nothing in-bounds to be stale about: with zero
    # observations the refusal is INSUFFICIENT, not STALE (preserves cold-start).
    witness_fresh = not any_stale

    live = LiveSurvivalWitness(
        evidence_count=fresh_count,
        required_count=bundle.required_count,
        fresh=witness_fresh,
        walkable_from_activation=walkable,
    )

    # --- Replay/holdout: only counts when it is for the candidate's trial -----
    replay_verdict: Optional[ReplayHoldoutVerdict] = None
    if bundle.replay is not None and bundle.replay.trial_id == cand.trial_id:
        replay_verdict = bundle.replay.to_verdict()
    # replay None or wrong-trial → verdict stays None → gate fires MISSING.

    # --- Operator basis: must be present, for this trial, and NOT auto ---------
    operator_basis_present = False
    ob = bundle.operator_basis
    if ob is not None and ob.trial_id == cand.trial_id:
        if ob.explicitly_not_auto_baseline:
            operator_basis_present = True
        else:
            # Present but invalid: the red-line fence. Not a valid basis.
            evidence_refusals.add(PROMOTION_OPERATOR_BASIS_CLAIMS_AUTO)

    inputs = PromotionInputs(
        live=live,
        replay=replay_verdict,
        open_nondischarge_claim_ids=bundle.open_nondischarge_claim_ids,
        promoted_tunables=(cand.tunable_name,),
        allowed_tunable_surface=bundle.allowed_tunable_surface,
        kernel_fuse_ratification_side_effect=bundle.kernel_fuse_ratification_side_effect,
        operator_basis_present=operator_basis_present,
    )
    return EvidenceAssembly(
        inputs=inputs,
        evidence_refusals=tuple(
            k for k in _COMBINED_REFUSAL_ORDER if k in evidence_refusals
        ),
    )


def evaluate_promotion_from_evidence(
    bundle: PromotionEvidenceBundle,
) -> PromotionEligibility:
    """End-to-end: walk the receipt chain, run the P4.0a gate, union the refusals.

    The gate is untouched; this composes the evidence-native refusal with the
    gate's verdict in one canonical-ordered ``PromotionEligibility``. ``eligible``
    iff zero combined refusals.
    """
    assembly = assemble_promotion_inputs(bundle)
    gate = evaluate_promotion_eligibility(assembly.inputs)
    combined = set(gate.refusals) | set(assembly.evidence_refusals)
    ordered = tuple(k for k in _COMBINED_REFUSAL_ORDER if k in combined)
    return PromotionEligibility(eligible=not ordered, refusals=ordered)


__all__ = [
    "PROMOTION_OPERATOR_BASIS_CLAIMS_AUTO",
    "EVIDENCE_REFUSAL_KINDS",
    "PROMOTION_VERDICT_ELIGIBLE",
    "PROMOTION_VERDICT_REFUSED",
    "ActivationReceipt",
    "LiveSurvivalObservationReceipt",
    "ReplayHoldoutReceipt",
    "OperatorBasisReceipt",
    "PromotionCandidate",
    "PromotionEvidenceBundle",
    "EvidenceAssembly",
    "assemble_promotion_inputs",
    "evaluate_promotion_from_evidence",
]
