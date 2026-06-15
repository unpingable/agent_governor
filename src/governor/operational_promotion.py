# SPDX-License-Identifier: Apache-2.0
"""P4 Slice 3c — operational promotion: the explicit operator-present act.

The trigger assembly. 3a *reported* (``discover_promotion_bundle``), 3b *prepared*
(``prepare_mint_input``); both are read-only and cannot move the constitution. 3c
*promotes*: it wires ``real producer stores → discover → prepare → explicit mint →
durable ControlBaseline supersession write`` as a single operator-present act.

> **3c does not make eligibility powerful. It makes a separately authorized act capable
> of consuming eligibility.**

The act inputs — ``baseline_name`` and ``minted_by`` — are the operator's, NOT the
evidence's. They are mandatory keyword arguments on :func:`operational_promote` and on
NOTHING in the discovery or prepare path. That is the structural guarantee:

> No ``ControlBaseline`` / ``PromotionReceipt`` byte reaches disk except through an
> :func:`operational_promote` call carrying operator act inputs AND a mint that
> independently re-derived eligibility + strong operator basis from real on-disk evidence.

Hard properties (each a test in ``tests/test_operational_promotion.py``):

* **Real on-disk evidence only.** The API takes a store ``root`` + a
  ``PromotionCandidate`` — never a hand-built bundle. Evidence is discovered from the real
  producer stores at the moment of the act (no stale ``MintInput`` replay).
* **No write without the act.** ``discover_promotion_bundle`` and ``prepare_mint_input``
  do not import this module and write no baseline/receipt. The write path is reached only
  after a successful :func:`mint_promotion`, which requires the act inputs.
* **No fiat over evidence.** There is no ``force`` / ``allow_missing`` / override
  parameter. Missing/stale/out-of-bounds/wrong-trial/off-surface evidence refuses, and the
  prior baseline stays authoritative — nothing is written.
* **Supersession, not mutation.** A promoted ``ControlBaseline`` is admitted with
  ``supersedes`` lineage; the prior baseline is never deleted (the store has no delete).
* **Idempotent.** Identical inputs yield identical content-addressed ids; re-persisting
  writes the same file, never a second baseline.

Consumes P4 authority (``85601bd`` / ``632414d`` / ``e8cb8e2`` / ``2e94dee`` / ``f449164``
/ ``bc1dc90``); it does not co-author it and may not cite itself as authority.

**Accepted bootstrap limits (carried forward, not introduced here):** ``_config_hashes_for``
in ``promotion_mint`` remains a fixture stand-in — 3c performs no live config custody and no
real ``max_slices=4`` promotion against a live surface. The "operational" claim is about the
real-evidence path + durable persistence, not live config wiring. No second profile, no
fuse/kernel enforcement, no CLI front door (the last would invite live minting; deferred
until a forcing case).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .clock_witness import MonotonicReading
from .control_baseline import ControlBaseline, ControlBaselineStore
from .gate_receipt import canonical_json, content_hash
from .promotion_evidence import PromotionCandidate
from .promotion_mint import PromotionReceipt, mint_promotion
from .promotion_mint_input import MintInputRefusal, prepare_mint_input

_EVIDENCE_DIRNAME = "promotion_evidence"
_RECEIPTS_DIRNAME = "promotion_receipts"


class PromotionReceiptTamperError(ValueError):
    """A persisted promotion receipt failed its integrity check on load: the declared
    ``receipt_id`` does not match the id recomputed from its justification fields. Refused,
    not repaired — a tampered spend record is not a spend record."""


class PromotionReceiptStore:
    """Durable spend-ledger for ``PromotionReceipt`` under
    ``<root>/promotion_evidence/promotion_receipts/<receipt_id>.json`` (file per receipt).

    Content-addressed (``receipt_id`` is the filename), atomic writes (temp+rename),
    integrity-checked loads. No delete — a mint is a spend, and a spend is not unspent by
    deleting its record (revert is a NEW ceremony, mirroring ``ControlBaselineStore``).
    """

    def __init__(self, root: Path | str):
        self._dir = Path(root) / _EVIDENCE_DIRNAME / _RECEIPTS_DIRNAME

    @property
    def directory(self) -> Path:
        return self._dir

    def put(self, receipt: PromotionReceipt) -> Path:
        """Persist a promotion receipt (atomic temp+rename). Returns its path. Keyed by
        the content-addressed ``receipt_id``, so re-persisting identical justification
        overwrites the same file — never a second record."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{receipt.receipt_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(receipt.to_dict(), sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def get(self, receipt_id: str) -> PromotionReceipt | None:
        """Load + integrity-check a promotion receipt. ``None`` on a clean miss. Raises
        :class:`PromotionReceiptTamperError` if the declared ``receipt_id`` disagrees with
        the id recomputed from the justification fields."""
        path = self._dir / f"{receipt_id}.json"
        if not path.exists():
            return None
        d = json.loads(path.read_text())
        receipt = PromotionReceipt(
            prior_baseline_id=d.get("prior_baseline_id"),
            activation_hash=d["activation_hash"],
            evidence_observation_hashes=tuple(d.get("evidence_observation_hashes", ())),
            evidence_count=d["evidence_count"],
            basis_bundle_hash=d["basis_bundle_hash"],
            operator_id=d["operator_id"],
            candidate_trial_id=d["candidate"]["trial_id"],
            candidate_tunable_name=d["candidate"]["tunable_name"],
            candidate_trial_value=d["candidate"]["trial_value"],
            new_baseline_id=d.get("new_baseline_id", ""),
            minted_by=d.get("minted_by", ""),
        )
        recomputed = content_hash(canonical_json(receipt.identity_dict()))
        if d.get("receipt_id") != recomputed:
            raise PromotionReceiptTamperError(
                f"promotion receipt {receipt_id!r} failed integrity check: declared "
                f"receipt_id {d.get('receipt_id')!r} != recomputed {recomputed!r}"
            )
        return receipt

    def list_ids(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.json"))


@dataclass(frozen=True)
class OperationalPromotionOutcome:
    """The outcome of an :func:`operational_promote` act. Promoted XOR refused — never
    both, never neither.

    On refusal, ``receipt`` / ``baseline`` / paths are ``None``, ``refusals`` carries the
    gate/operator-basis reasons in canonical order, and **nothing was written** (the prior
    baseline stays authoritative). On promotion, the receipt and baseline are persisted and
    their on-disk paths are recorded.
    """

    promoted: bool
    source_root: str
    refusals: tuple[str, ...] = ()
    receipt: PromotionReceipt | None = None
    baseline: ControlBaseline | None = None
    receipt_path: str | None = None
    baseline_path: str | None = None


def operational_promote(
    root: Path | str,
    candidate: PromotionCandidate,
    *,
    required_count: int,
    evaluation_reading: MonotonicReading,
    freshness_horizon_ns: int,
    allowed_tunable_surface: frozenset[str],
    promote_reading: MonotonicReading,
    operator_review_horizon_ns: int,
    baseline_name: str,
    minted_by: str,
    open_nondischarge_claim_ids: tuple[str, ...] = (),
    kernel_fuse_ratification_side_effect: bool = False,
    prior_baseline: ControlBaseline | None = None,
) -> OperationalPromotionOutcome:
    """Perform an operational promotion from real on-disk evidence.

    The single explicit operator-present act: discover the bundle from the real producer
    stores under ``root``, prepare the mint input (refuse unless eligible), run the
    four-office mint (which independently re-derives eligibility + the strong operator
    basis), and — only on a successful mint — persist the ``PromotionReceipt`` and the
    superseding ``ControlBaseline`` to their durable stores.

    ``baseline_name`` and ``minted_by`` are the operator's act inputs (not the evidence's)
    and are mandatory: an empty value is a caller error (you must say who is minting and
    what the baseline is called), raised as ``ValueError`` BEFORE any disk read — not an
    evidence refusal.

    Returns an :class:`OperationalPromotionOutcome`. On any refusal nothing is written.
    """
    # Act inputs are the operator's, supplied here and nowhere upstream. Missing them is a
    # caller error (no operator identity / no baseline name), not an evidence refusal.
    if not baseline_name:
        raise ValueError("baseline_name is mandatory — promotion is an explicit named act")
    if not minted_by:
        raise ValueError("minted_by is mandatory — promotion must attribute the operator")

    root = Path(root)

    # --- prepare: discover real evidence + gate eligibility (read-only) -----------
    mi = prepare_mint_input(
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
        prior_baseline=prior_baseline,
    )
    if isinstance(mi, MintInputRefusal):
        # Empty/ineligible chamber: refuse cleanly. Nothing written.
        return OperationalPromotionOutcome(
            promoted=False, source_root=mi.source_root, refusals=mi.refusals
        )

    # --- mint: the four-office act re-derives from the same inputs ----------------
    result = mint_promotion(
        mi.bundle,
        mi.operator_basis_facts,
        promote_reading=mi.promote_reading,
        operator_review_horizon_ns=mi.operator_review_horizon_ns,
        baseline_name=baseline_name,
        minted_by=minted_by,
        prior_baseline=mi.prior_baseline,
    )
    if not result.minted:
        # The mint refused (gate or operator-basis). Prior baseline stays authoritative.
        return OperationalPromotionOutcome(
            promoted=False, source_root=mi.source_root, refusals=result.refusals
        )

    # --- durable custody: the supersession write ----------------------------------
    # Receipt first so the baseline's creation_receipt_id always resolves on disk; then the
    # baseline (admitted with `supersedes` lineage; the store has no delete, so the prior
    # baseline survives — supersession, not mutation).
    assert result.receipt is not None and result.baseline is not None  # minted invariant
    receipt_path = PromotionReceiptStore(root).put(result.receipt)
    baseline_path = ControlBaselineStore(root).put(result.baseline)
    return OperationalPromotionOutcome(
        promoted=True,
        source_root=mi.source_root,
        receipt=result.receipt,
        baseline=result.baseline,
        receipt_path=str(receipt_path),
        baseline_path=str(baseline_path),
    )


__all__ = [
    "PromotionReceiptStore",
    "PromotionReceiptTamperError",
    "OperationalPromotionOutcome",
    "operational_promote",
]
