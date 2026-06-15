# SPDX-License-Identifier: Apache-2.0
"""P4 Slice 3b — discovery-backed mint INPUT path.

Wires ``real stores → discovery report → mint input``. Gathers the read-only evidence
inputs the mint needs (the discovered bundle + the strong ``OperatorBasisFacts``) and
refuses unless discovery is eligible. It is the holster, not the trigger.

> **Discovery may FEED mint eligibility. Discovery may NOT trigger promotion. Minting
> remains an explicit operator-present act.**

Hard properties (each a test in ``tests/test_promotion_mint_input.py``):

* **Never mints, never writes, never mutates.** ``prepare_mint_input`` does NOT import or
  call ``mint_promotion``; it returns inputs. A ``MintInput`` carries no minting capability.
* **Gather, don't decide.** ``prepare`` packages the *evidence* inputs; the mint
  independently re-derives the gate AND the strong operator-basis binding (prepare cannot
  smuggle eligibility past it). The mint is the authority; prepare is plumbing.
* **The act inputs are not pre-decided.** ``baseline_name`` and ``minted_by`` are NOT on
  ``MintInput`` — they are supplied at the separate, explicit, operator-present mint call.
  Prepare cannot name the baseline or claim who minted it.
* **Refuses unless eligible.** A non-eligible discovery yields a ``MintInputRefusal``
  carrying the gate's existing refusal vocabulary — no mint input is produced.

Consumes P4 authority (``…/e8cb8e2``/``2e94dee``/``f449164``); does not co-author it. No
real ``max_slices=4`` promotion, no second profile, no fuse, no live baseline mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .clock_witness import MonotonicReading
from .control_baseline import ControlBaseline
from .operator_basis import OperatorBasisFacts
from .promotion_discovery import discover_promotion_bundle
from .promotion_evidence import PromotionCandidate, PromotionEvidenceBundle
from .promotion_evidence_store import OperatorBasisReceiptStore


@dataclass(frozen=True)
class MintInput:
    """The read-only evidence inputs an explicit, operator-present mint call consumes.

    Deliberately carries NO act inputs (``baseline_name`` / ``minted_by``) and NO minting
    capability — it is what ``mint_promotion`` reads, not a mint. The strong
    ``operator_basis_facts`` are surfaced so the mint can run its OWN derivation; the
    discovered ``bundle`` already carries the matching weak projection.
    """

    bundle: PromotionEvidenceBundle
    operator_basis_facts: OperatorBasisFacts
    promote_reading: MonotonicReading
    operator_review_horizon_ns: int
    prior_baseline: ControlBaseline | None
    basis_bundle_hash: str
    source_root: str


@dataclass(frozen=True)
class MintInputRefusal:
    """Discovery was not eligible — no mint input is produced. Carries the gate's existing
    refusal vocabulary (found/fresh/in-bounds/walkable/operator-basis/…). Not a mint."""

    refusals: tuple[str, ...]
    source_root: str


def prepare_mint_input(
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
    prior_baseline: ControlBaseline | None = None,
) -> MintInput | MintInputRefusal:
    """Read-only: discover real on-disk evidence and, IFF the gate finds it eligible,
    package the inputs an explicit mint call would consume. Performs NO mint, NO write,
    NO mutation. Returns :class:`MintInputRefusal` (with the gate's refusals) otherwise.

    The mint remains a separate operator-present act that independently re-derives the
    gate and the strong operator-basis binding from these same inputs.
    """
    prior_hash = prior_baseline.baseline_id if prior_baseline is not None else None
    discovered = discover_promotion_bundle(
        root,
        candidate,
        required_count=required_count,
        evaluation_reading=evaluation_reading,
        freshness_horizon_ns=freshness_horizon_ns,
        allowed_tunable_surface=allowed_tunable_surface,
        promote_reading=promote_reading,
        operator_review_horizon_ns=operator_review_horizon_ns,
        open_nondischarge_claim_ids=open_nondischarge_claim_ids,
        kernel_fuse_ratification_side_effect=kernel_fuse_ratification_side_effect,
        prior_baseline_hash=prior_hash,
    )
    if not discovered.eligible:
        return MintInputRefusal(refusals=discovered.refusals, source_root=discovered.source_root)

    # Eligible discovery implies operator basis present, which the store emits only after
    # the strong facts derive — so the strong facts are on disk. Surface them for the mint
    # (read-only). A None here would mean the store was corrupted between the two reads
    # (TOCTOU); that is an invariant violation, raised loudly, never a soft refusal.
    facts = OperatorBasisReceiptStore(Path(root)).load_facts_for_trial(candidate.trial_id)
    if facts is None:  # pragma: no cover - unreachable when discovery is eligible
        raise RuntimeError(
            f"eligible discovery for trial {candidate.trial_id!r} but operator-basis facts "
            f"absent on disk — store corrupted between reads"
        )

    return MintInput(
        bundle=discovered.bundle,
        operator_basis_facts=facts,
        promote_reading=promote_reading,
        operator_review_horizon_ns=operator_review_horizon_ns,
        prior_baseline=prior_baseline,
        basis_bundle_hash=discovered.basis_bundle_hash,
        source_root=discovered.source_root,
    )


__all__ = [
    "MintInput",
    "MintInputRefusal",
    "prepare_mint_input",
]
