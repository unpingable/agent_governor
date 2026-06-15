# SPDX-License-Identifier: Apache-2.0
"""P4 Slice 3a — real evidence substrate, READ-ONLY.

Moves promotion-evidence sourcing from hand-built fixtures toward real on-disk
receipt discovery. Reads the four producer stores (activation / observation /
replay-holdout / operator-basis), assembles a ``PromotionEvidenceBundle``, computes
its ``basis_bundle_hash``, and runs the *existing* gate
(``evaluate_promotion_from_evidence``) to report a verdict.

> **Real evidence substrate increases CUSTODY, not PERMISSION.** Discovery is not
> admissibility. Finding receipts on disk does not make them admissible — the gate still
> derives admissibility (found · fresh · in-bounds · bundle-bound · operator-basis-
> consistent · supersession-safe). This module adds provenance (which real store the
> receipts came from), never a new way to say yes.

Hard properties (each a test in ``tests/test_promotion_discovery.py``):

* **Read-only.** No write, no mint, no baseline mutation. Stores are read via their
  ``get`` / ``load_for_trial`` only. ``DiscoveredEvidence`` carries no minting capability.
* **Disk-only input.** The API takes a store ``root`` + a ``PromotionCandidate`` — never a
  hand-built bundle or receipt. A synthetic in-memory fixture has **no path into
  discovery**, so it cannot masquerade as live evidence.
* **No operator-fiat over presence.** Missing evidence is missing; there is no parameter
  that makes unavailable evidence "okay". Missing → the gate refuses.
* **Operator-basis-consistent by construction.** The operator-basis store emits the weak
  receipt only as the projection of the strong facts after structural derivation against
  the computed ``basis_bundle_hash`` (slice-2 alignment) — so a discovered bundle's weak
  shadow is already the projection of the strong basis on disk.

Consumes P4 authority (``85601bd`` / ``632414d`` / ``e8cb8e2`` / ``2e94dee``); it does not
co-author it. No real ``max_slices=4`` promotion, no second profile, no fuse enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .basis_bundle import compute_basis_bundle_hash
from .clock_witness import MonotonicReading
from .promotion_evidence import (
    PromotionCandidate,
    PromotionEvidenceBundle,
    evaluate_promotion_from_evidence,
)
from .promotion_evidence_store import (
    ActivationReceiptStore,
    ObservationReceiptStore,
    OperatorBasisReceiptStore,
    ReplayHoldoutReceiptStore,
)
from .promotion_gate import PromotionEligibility


@dataclass(frozen=True)
class DiscoveredEvidence:
    """A bundle assembled from real on-disk receipts, plus its computed bundle hash,
    its provenance (the store root it was read from), and the gate's verdict.

    Carries **no minting capability** — discovery is read-only. ``eligibility`` is the
    gate's derivation, not a promotion: an ``eligible`` discovery still does not promote.
    ``source_root`` is the custody provenance: these receipts came from this real store,
    not from an in-memory fixture.
    """

    bundle: PromotionEvidenceBundle
    basis_bundle_hash: str
    source_root: str
    eligibility: PromotionEligibility

    @property
    def eligible(self) -> bool:
        return self.eligibility.eligible

    @property
    def refusals(self) -> tuple[str, ...]:
        return self.eligibility.refusals


def discover_promotion_bundle(
    root: Path | str,
    candidate: PromotionCandidate,
    *,
    required_count: int,
    evaluation_reading: MonotonicReading,
    freshness_horizon_ns: int,
    allowed_tunable_surface: frozenset[str],
    promote_reading: MonotonicReading,
    operator_review_horizon_ns: int,
    open_nondischarge_claim_ids: tuple[str, ...] = (),
    kernel_fuse_ratification_side_effect: bool = False,
    prior_baseline_hash: str | None = None,
) -> DiscoveredEvidence:
    """Read-only assembly + gate evaluation of a promotion-evidence bundle from the real
    on-disk stores under ``root``. Performs NO write and NO mint.

    The operator-basis store is consume-relative, so the bundle is assembled WITHOUT
    operator basis first to compute ``basis_bundle_hash``; the operator basis is then
    loaded against that hash (the store derives + projects). Operator basis is excluded
    from the bundle hash, so the hash is identical with or without it.
    """
    root = Path(root)
    activation = ActivationReceiptStore(root).get(candidate.trial_id)
    observations = tuple(ObservationReceiptStore(root).load_for_trial(candidate.trial_id))
    replay = ReplayHoldoutReceiptStore(root).load_for_trial(candidate.trial_id)

    pre = PromotionEvidenceBundle(
        candidate=candidate,
        activation=activation,
        observations=observations,
        replay=replay,
        operator_basis=None,
        required_count=required_count,
        evaluation_reading=evaluation_reading,
        freshness_horizon_ns=freshness_horizon_ns,
        allowed_tunable_surface=allowed_tunable_surface,
        open_nondischarge_claim_ids=open_nondischarge_claim_ids,
        kernel_fuse_ratification_side_effect=kernel_fuse_ratification_side_effect,
    )
    basis_bundle_hash = compute_basis_bundle_hash(pre, prior_baseline_hash=prior_baseline_hash)

    operator_basis = OperatorBasisReceiptStore(root).load_for_trial(
        candidate.trial_id,
        consumed_bundle_hash=basis_bundle_hash,
        promote_reading=promote_reading,
        freshness_horizon_ns=operator_review_horizon_ns,
    )
    bundle = replace(pre, operator_basis=operator_basis)
    eligibility = evaluate_promotion_from_evidence(bundle)
    return DiscoveredEvidence(
        bundle=bundle,
        basis_bundle_hash=basis_bundle_hash,
        source_root=str(root),
        eligibility=eligibility,
    )


__all__ = [
    "DiscoveredEvidence",
    "discover_promotion_bundle",
]
