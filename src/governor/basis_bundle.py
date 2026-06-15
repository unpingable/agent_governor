# SPDX-License-Identifier: Apache-2.0
"""P4.0b — the canonical basis-bundle hash.

The operator reviews a *basis bundle*: the pre-state evidence world. Its canonical
hash lets the promotion mint prove ``consumed_bundle_hash == reviewed_bundle_hash``
(pre-state binding; ``operator_basis.derive_operator_basis_present``). P4.0g bound
with this hash *opaque*; this module is how it is computed.

Spec: ``specs/governor/promotion-evidence.md`` § "P4.0b-prep / Canonical basis-bundle
hash"; doctrine: ``specs/core/SELF_GOVERNANCE_SPEC.md`` § "Checkpoint 3 / P4 Promotion".

The ratified binding rules (each is a negative test in ``tests/test_promotion_mint.py``):

* **Excludes the operator basis** — it binds *to* the bundle; including it is circular.
* **Excludes live clocks** — clock witnesses are freshness/evaluation basis, a different
  object (clock-witness doctrine); in-content clocks make every evaluation a distinct
  reviewed object. (So ``evaluation_reading`` is NOT in the hash, even though it rides on
  the bundle.)
* **Observation hashes are sorted** — same set ⇒ same bundle hash regardless of order.
* **Prior baseline is lineage** — ``prior_baseline_hash`` binds the receipt when present;
  ``prior = 8`` alone is true-but-ungrounded.
* **Open-claims is frozen content** — the bundle binds the debt state at review time;
  later claims may change future eligibility but must not retroactively mutate the
  reviewed world-state.

> The basis bundle binds the reviewed promotion world-state, not the operator's later
> act and not the evaluation clock.

Implementation note (narrow, called out per the P4.0b fences): the hash is a raw
SHA-256 hex digest via ``gate_receipt.content_hash`` — the same canonicalizer and shape
as ``ActivationReceipt.content_hash`` and ``ControlBaseline.baseline_id``, so the bundle
hash is comparable to the chain hashes it is built from. (The spec text wrote
``"sha256:<hex>"``; the repo's promotion chain uses raw hex. No second canonicalization.)
"""

from __future__ import annotations

from typing import Any

from .gate_receipt import canonical_json, content_hash
from .promotion_evidence import (
    LiveSurvivalObservationReceipt,
    PromotionEvidenceBundle,
    ReplayHoldoutReceipt,
)

BASIS_BUNDLE_SCHEMA = "promotion-basis-bundle-v1"


def _reading_block(r: Any) -> dict[str, Any]:
    return {"source": r.source, "epoch": r.epoch, "ns": r.ns}


def _observation_hash(obs: LiveSurvivalObservationReceipt) -> str:
    """Content hash of one observation's identity (no live clock excluded here — an
    observation's own ``observed_at`` IS part of its content; what the *bundle* hash
    excludes is the bundle-level ``evaluation_reading``)."""
    return content_hash(
        canonical_json(
            {
                "schema": "promotion_observation_v0",
                "trial_id": obs.trial_id,
                "observation_id": obs.observation_id,
                "observed_at": _reading_block(obs.observed_at),
                "in_bounds": obs.in_bounds,
                "activation_receipt_hash": obs.activation_receipt_hash,
                "disqualifying_events": sorted(obs.disqualifying_events),
            }
        )
    )


def _replay_hash(replay: ReplayHoldoutReceipt) -> str:
    return content_hash(
        canonical_json(
            {
                "schema": "promotion_replay_holdout_v0",
                "trial_id": replay.trial_id,
                "replay_subject": replay.replay_subject,
                "passed": replay.passed,
                "corpus_hash": replay.corpus_hash,
                "frozen_corpus_hash": replay.frozen_corpus_hash,
                "harness_version": replay.harness_version,
                "comparator_baseline_id": replay.comparator_baseline_id,
                "falsification_basis": replay.falsification_basis,
            }
        )
    )


def basis_bundle_identity(
    bundle: PromotionEvidenceBundle,
    *,
    prior_baseline_hash: str | None = None,
) -> dict[str, Any]:
    """The canonical pre-state world-state dict the operator reviews.

    Deterministic and order-independent: observation hashes are sorted. Excludes the
    operator basis (binds *to* this) and the bundle's live ``evaluation_reading`` (a
    different object). ``open_non_discharge_claims`` is a frozen sorted snapshot of the
    debt ids at review time — content, not a live query pointer.
    """
    cand = bundle.candidate
    activation_hash = bundle.activation.content_hash if bundle.activation else None
    observation_hashes = sorted(_observation_hash(o) for o in bundle.observations)
    replay_hash = _replay_hash(bundle.replay) if bundle.replay else None
    return {
        "schema_version": BASIS_BUNDLE_SCHEMA,
        "candidate": {
            "trial_id": cand.trial_id,
            "tunable_name": cand.tunable_name,
            "trial_value": cand.trial_value,
            "prior_baseline_value": (
                bundle.activation.prior_baseline_value if bundle.activation else None
            ),
            "prior_baseline_hash": prior_baseline_hash,
        },
        "activation_hash": activation_hash,
        "observation_hashes": observation_hashes,
        "replay_holdout_hash": replay_hash,
        "required_count": bundle.required_count,
        "survival_horizon_ns": bundle.freshness_horizon_ns,
        "allowed_surface": sorted(bundle.allowed_tunable_surface),
        "open_non_discharge_claims": sorted(bundle.open_nondischarge_claim_ids),
    }


def compute_basis_bundle_hash(
    bundle: PromotionEvidenceBundle,
    *,
    prior_baseline_hash: str | None = None,
) -> str:
    """The canonical basis-bundle hash (raw sha-256 hex). Pure, total, deterministic."""
    return content_hash(canonical_json(basis_bundle_identity(bundle, prior_baseline_hash=prior_baseline_hash)))


__all__ = [
    "BASIS_BUNDLE_SCHEMA",
    "basis_bundle_identity",
    "compute_basis_bundle_hash",
]
