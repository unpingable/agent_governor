# SPDX-License-Identifier: Apache-2.0
"""P4.0b — the promotion mint: the slice where constitutional furniture moves.

Consumes prior authority ``85601bd`` (P4.0a-HIGH-prep). It does NOT amend doctrine;
it implements the ceremony specified in ``specs/governor/promotion-evidence.md``
§ "P4.0b-prep" and ``specs/core/SELF_GOVERNANCE_SPEC.md`` § "Checkpoint 3 / P4
Promotion". This module may consume that authority; it may not cite itself as authority.

The mint is the four-office act:

  * **admissibility** — ``evaluate_promotion_from_evidence`` (the P4.0a gate; refuse-only).
  * **act-standing** — the *strong* operator basis: ``derive_operator_basis_present``
    with ``consumed_bundle_hash = compute_basis_bundle_hash(bundle)``. This is the
    "replace the opaque hash" wiring. The bundle's weak ``OperatorBasisReceipt`` (which
    the gate assembler reads) is only a shadow; the structural deriver is the real gate,
    because only it binds the *reviewed bundle == consumed bundle* pre-state. (Two
    operator-basis representations is an implementation reality the spec anticipated —
    "the deriver is the real gate; the assembler's bool is its shadow" — not a doctrine
    seam; resolved here, in the mint, not by patching either spec.)
  * **exactly-once spend** — a single content-addressed ``PromotionReceipt``; identical
    inputs yield an identical receipt_id and baseline_id (idempotent), so re-running the
    mint does not produce a second baseline. A *distinct* mint requires a fresh ceremony.
  * **durable custody** — ``ControlBaseline`` (reused, untouched) admitted with
    ``supersedes`` lineage and ``creation_receipt_id = receipt_id``; any two baselines
    diffable from config hashes alone.

The fence (verbatim): operator basis **authorizes attribution; it does not legitimize
promotion and cannot cure missing evidence.** A failing predicate refuses regardless of
operator basis; a failing operator basis refuses regardless of a clean predicate. The two
never substitute for each other.

Scope (P4.0b): mint + revert-as-supersession + the 6 acceptance / 9 negative tests on
SYNTHETIC fixtures. No real ``max_slices=4`` promotion (zero evidence on disk), no second
profile, no kernel/fuse/ratification change, no config write to a live surface.

Two-operator-basis seam — RESOLVED 2026-06-15 (alignment, operator-present)
---------------------------------------------------------------------------
The P4.0b debt is discharged. Reduction proved the weak
``promotion_evidence.OperatorBasisReceipt`` has **zero fields absent** from the strong
``operator_basis.OperatorBasisFacts`` and that the canonical producer
(``OperatorBasisReceiptStore.load_for_trial``) already emits it only after the strong
derivation passes — i.e. the weak form is a pure lossy projection, not a second office.
So a bridge receipt would be ceremony. Resolution: **alignment by projection +
mismatch refusal.** ``OperatorBasisFacts.project()`` is the one canonical readout (the
store routes through it); the mint refuses with ``operator_basis_weak_strong_mismatch``
unless the bundle's weak shadow equals ``operator_basis_facts.project()``. The mint still
requires BOTH the gate's eligibility AND the strong derivation — neither alone admits —
and now the shadow cannot drift from the object casting it. *Weak operator basis is a
readout of strong; a hand-constructed weak receipt has no independent authority.*

``kernel_fuse_ratification_side_effect`` is deliberately OUTSIDE ``basis_bundle_hash``
(accepted at review): the bundle hash binds the *evidence* world; the fuse/ratification
flag is a separate gate predicate, refused independently. Not a custody-hash field.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .basis_bundle import compute_basis_bundle_hash
from .clock_witness import MonotonicReading
from .control_baseline import ControlBaseline, admit_baseline
from .gate_receipt import canonical_json, content_hash
from .operator_basis import OperatorBasisFacts, derive_operator_basis_present
from .promotion_evidence import (
    PromotionEvidenceBundle,
    evaluate_promotion_from_evidence,
)

# The mint-level refusal that closes the weak<->strong operator-basis seam: the bundle's
# weak shadow must be EXACTLY the projection of the strong facts the mint binds. A
# hand-constructed weak receipt that satisfies the gate's shadow but does not match the
# strong basis is a substitution attempt — refused. (Resolution of the P4.0b follow-up
# debt: weak operator basis is a readout of strong, never an independent authority.)
OPERATOR_BASIS_WEAK_STRONG_MISMATCH = "operator_basis_weak_strong_mismatch"


@dataclass(frozen=True)
class PromotionReceipt:
    """Content-addressed decision receipt for a baseline mint.

    ``receipt_id`` is content-addressed over the *justification* — prior baseline,
    activation, the in-bounds evidence refs, the basis-bundle hash, the operator id, and
    the candidate. It deliberately EXCLUDES ``new_baseline_id`` and ``minted_by`` (those
    are binding/metadata, like a ControlBaseline excludes ``creation_receipt_id`` from its
    identity) — so there is no hash cycle between receipt and baseline, and identical
    justifications mint identical receipts (exactly-once).
    """

    prior_baseline_id: str | None
    activation_hash: str
    evidence_observation_hashes: tuple[str, ...]
    evidence_count: int
    basis_bundle_hash: str
    operator_id: str
    candidate_trial_id: str
    candidate_tunable_name: str
    candidate_trial_value: Any
    new_baseline_id: str = ""  # binding, filled after baseline admission; NOT in identity
    minted_by: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_observation_hashes",
            tuple(sorted(self.evidence_observation_hashes)),
        )

    def identity_dict(self) -> dict[str, Any]:
        return {
            "schema": "promotion_receipt_v0",
            "prior_baseline_id": self.prior_baseline_id,
            "activation_hash": self.activation_hash,
            "evidence_observation_hashes": list(self.evidence_observation_hashes),
            "evidence_count": self.evidence_count,
            "basis_bundle_hash": self.basis_bundle_hash,
            "operator_id": self.operator_id,
            "candidate": {
                "trial_id": self.candidate_trial_id,
                "tunable_name": self.candidate_tunable_name,
                "trial_value": self.candidate_trial_value,
            },
        }

    @property
    def receipt_id(self) -> str:
        return content_hash(canonical_json(self.identity_dict()))

    def to_dict(self) -> dict[str, Any]:
        payload = self.identity_dict()
        payload["receipt_id"] = self.receipt_id
        payload["new_baseline_id"] = self.new_baseline_id
        payload["minted_by"] = self.minted_by
        return payload


@dataclass(frozen=True)
class PromotionResult:
    """Outcome of a mint attempt. Minted XOR refused — never both, never neither.

    On refusal, ``receipt`` and ``baseline`` are ``None`` and the prior baseline stays
    authoritative (the mint persists nothing). ``refusals`` carries every reason in
    canonical order: the gate/evidence refusals first, then the operator-basis reasons.
    """

    minted: bool
    refusals: tuple[str, ...] = field(default_factory=tuple)
    receipt: PromotionReceipt | None = None
    baseline: ControlBaseline | None = None


def _config_hashes_for(tunable_name: str, trial_value: Any) -> tuple[tuple[str, str], ...]:
    """The promoted config surface as content-addressed (key, hash) pairs. Single
    tunable this band — the scope fence.

    **Fixture-bound stand-in (accepted at P4.0b review).** These hashes represent the
    promoted config surface for SYNTHETIC fixtures only; they do NOT claim live config
    custody and MUST NOT be used to perform the real ``max_slices=4`` promotion. Wiring to
    the actual config surface is later, gated work.
    """
    value_hash = content_hash(canonical_json({"value": trial_value}))
    return ((tunable_name, value_hash),)


def mint_promotion(
    bundle: PromotionEvidenceBundle,
    operator_basis_facts: OperatorBasisFacts,
    *,
    promote_reading: MonotonicReading,
    operator_review_horizon_ns: int,
    baseline_name: str,
    minted_by: str,
    prior_baseline: ControlBaseline | None = None,
) -> PromotionResult:
    """Attempt the mint. Refuses unless BOTH the evidence predicate is eligible AND the
    operator basis structurally binds the consumed bundle. Pure except for the returned
    objects (no IO — the caller persists via the stores)."""
    refusals: list[str] = []

    # --- admissibility office: the evidence predicate (refuse-only gate) ---------
    eligibility = evaluate_promotion_from_evidence(bundle)
    refusals.extend(eligibility.refusals)

    # --- act-standing office: STRONG operator basis bound to the computed bundle ---
    prior_hash = prior_baseline.baseline_id if prior_baseline is not None else None
    consumed_bundle_hash = compute_basis_bundle_hash(bundle, prior_baseline_hash=prior_hash)
    ob = derive_operator_basis_present(
        operator_basis_facts,
        consumed_bundle_hash=consumed_bundle_hash,
        promote_reading=promote_reading,
        freshness_horizon_ns=operator_review_horizon_ns,
    )
    refusals.extend(ob.reasons)

    # weak<->strong consistency: the gate reads the bundle's weak operator-basis as a
    # shadow; the mint binds the strong facts. They must not float free — the shadow must
    # be exactly the projection of the strong facts, or it is a substitution. (No
    # independent authority for the weak form.)
    if (
        bundle.operator_basis is not None
        and bundle.operator_basis != operator_basis_facts.project()
    ):
        refusals.append(OPERATOR_BASIS_WEAK_STRONG_MISMATCH)

    if refusals:
        # Prior baseline stays authoritative; nothing minted (the fence: neither office
        # may substitute for the other — any refusal blocks).
        return PromotionResult(minted=False, refusals=tuple(refusals))

    # --- exactly-once spend: the content-addressed receipt -----------------------
    cand = bundle.candidate
    activation_hash = bundle.activation.content_hash  # eligible ⇒ activation present+matched
    in_bounds_obs = tuple(
        o.activation_receipt_hash for o in bundle.observations if o.is_in_bounds
    )  # evidence refs (the bound, in-bounds observations)
    receipt = PromotionReceipt(
        prior_baseline_id=prior_hash,
        activation_hash=activation_hash,
        evidence_observation_hashes=in_bounds_obs,
        evidence_count=eligibility_evidence_count(bundle),
        basis_bundle_hash=consumed_bundle_hash,
        operator_id=operator_basis_facts.operator_id,
        candidate_trial_id=cand.trial_id,
        candidate_tunable_name=cand.tunable_name,
        candidate_trial_value=cand.trial_value,
        minted_by=minted_by,
    )

    # --- durable custody: admit the ControlBaseline (reused, no auto-mint) --------
    baseline = admit_baseline(
        name=baseline_name,
        config_hashes=_config_hashes_for(cand.tunable_name, cand.trial_value),
        creation_receipt_id=receipt.receipt_id,
        admitted_by=minted_by,
        supersedes=prior_hash,
    )
    receipt = replace(receipt, new_baseline_id=baseline.baseline_id)
    return PromotionResult(minted=True, receipt=receipt, baseline=baseline)


def eligibility_evidence_count(bundle: PromotionEvidenceBundle) -> int:
    """The count of bound, in-bounds observations (the same number the gate counts as
    survival evidence; recomputed here for the receipt's record)."""
    if bundle.activation is None:
        return 0
    act_hash = bundle.activation.content_hash
    return sum(
        1
        for o in bundle.observations
        if o.trial_id == bundle.candidate.trial_id
        and o.activation_receipt_hash == act_hash
        and o.is_in_bounds
    )


def revert_promoted_baseline(
    promoted: ControlBaseline,
    revert_target: ControlBaseline,
    *,
    creation_receipt_id: str,
    admitted_by: str,
) -> ControlBaseline:
    """Reverting a PROMOTED baseline is itself a supersession — a NEW admitted baseline
    (back to the revert target's config) that ``supersedes`` the promoted one, NOT a
    silent undo. ``creation_receipt_id`` is mandatory (no auto-mint), and there is no
    delete path on the store: a revert can only be expressed as a new ceremony.
    """
    return admit_baseline(
        name=revert_target.name,
        config_hashes=revert_target.config_hashes,
        creation_receipt_id=creation_receipt_id,
        admitted_by=admitted_by,
        checkpoint_ref=revert_target.checkpoint_ref,
        supersedes=promoted.baseline_id,
    )


__all__ = [
    "OPERATOR_BASIS_WEAK_STRONG_MISMATCH",
    "PromotionReceipt",
    "PromotionResult",
    "mint_promotion",
    "eligibility_evidence_count",
    "revert_promoted_baseline",
]
