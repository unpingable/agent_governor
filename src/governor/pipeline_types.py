"""Recomposition receipts and boundary accounting — the laundering refusal.

P1.1 of the workflow-kernel / self-annealing campaign
(`working/campaign-workflow-kernel-annealing.md`,
`specs/gaps/GOV_GAP_RECOMPOSITION_RECEIPT_001.md`,
`docs/doctrine/annealing_and_recomposition.md`).

The failure class this exists to refuse: a run whose slices all individually
passed, but where an admitted decomposition boundary was silently dropped,
narrowed, or substituted between *decompose* and *recompose*. "All slices
passed" must not launder into "the whole is admissible." Decomposition is
capacity management; recomposition is legitimacy management, and recomposition
is where laundering happens.

The teeth are one pure, total function: :func:`account_boundaries`. Every
admitted boundary must appear with an honest disposition; any boundary that is
unaccounted — or accounted with a disposition outside the closed vocabulary —
forces ``refused_laundering`` regardless of how green the surviving slices are.

This module is **shadow-only substrate**. It defines the data type and the
accounting function; it does NOT wire into the orchestrator (P1.2) and does NOT
enforce (P3b). A :class:`RecompositionReceipt` built here records the verdict it
*would* render. Nothing in this module blocks, gates, retries, or mutates.

Reuses :func:`governor.gate_receipt.canonical_json` / ``content_hash`` rather
than minting a second canonicalization (the repo fought that divergence once;
see "Verified Kernel 2.x Hygiene").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .gate_receipt import canonical_json, content_hash

# --------------------------------------------------------------------------- #
# Closed vocabularies
# --------------------------------------------------------------------------- #

# Per-boundary dispositions. A boundary the recomposition accounts for must
# carry exactly one of these. Anything else is not an honest accounting.
DISPOSITION_COMPLETED = "completed"
DISPOSITION_FAILED = "failed"
DISPOSITION_PARKED = "parked"
DISPOSITION_REFUSED = "refused"

CLOSED_DISPOSITIONS = frozenset(
    {
        DISPOSITION_COMPLETED,
        DISPOSITION_FAILED,
        DISPOSITION_PARKED,
        DISPOSITION_REFUSED,
    }
)

# Recomposition verdicts (closed). The rendered ``refused_<gate>`` form of
# REFUSED_CARRIED names the specific upstream gate from the source receipt; the
# pure accounting function cannot invent a gate name, so the verdict constant is
# the *class* of refusal, not the rendered string (gap open question 2).
VERDICT_ADMISSIBLE = "admissible"
VERDICT_ADMISSIBLE_PARTIAL = "admissible_partial_progress"
VERDICT_REFUSED_LAUNDERING = "refused_laundering"
VERDICT_REFUSED_CARRIED = "refused_carried"

CLOSED_VERDICTS = frozenset(
    {
        VERDICT_ADMISSIBLE,
        VERDICT_ADMISSIBLE_PARTIAL,
        VERDICT_REFUSED_LAUNDERING,
        VERDICT_REFUSED_CARRIED,
    }
)

# Intent fidelity classes (declared at intent, judged at recomposition). Carried
# here as an optional field only; P1.1 does not enforce loss budgets (that is
# the fidelity-budget judgment layered on later — gap open question 3).
FIDELITY_EXACT = "exact"
FIDELITY_BOUNDED = "bounded"
FIDELITY_HEURISTIC = "heuristic"
FIDELITY_EXPLORATORY = "exploratory"

CLOSED_FIDELITY_CLASSES = frozenset(
    {
        FIDELITY_EXACT,
        FIDELITY_BOUNDED,
        FIDELITY_HEURISTIC,
        FIDELITY_EXPLORATORY,
    }
)


# --------------------------------------------------------------------------- #
# Boundary accounting — the pure, total teeth
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BoundaryAccounting:
    """The result of accounting a recomposition's admitted boundaries.

    ``verdict`` is the headline (one of :data:`CLOSED_VERDICTS`). The other
    fields are the diagnosis that produced it, so a refusal is walkable rather
    than a bare label.

    * ``unaccounted`` — admitted boundary ids with no entry in the accounting.
      Silent drops. The core laundering surface.
    * ``unrecognized`` — admitted boundary ids accounted with a disposition
      outside :data:`CLOSED_DISPOSITIONS`. Claiming an accounting with a
      nonsense token is laundering by another name (hostile-input discipline).
    * ``refused`` — admitted boundary ids whose slice was refused by an upstream
      gate. Honest carried refusal, not laundering.
    * ``incomplete`` — admitted boundary ids that ``failed`` or ``parked``.
      Declared non-completion; partial progress.
    * ``extraneous`` — ids accounted that were never admitted. Recorded for
      diagnosis; does NOT change the verdict in P1.1 (tightening is a deferred
      question — the *other* laundering direction, a boundary appearing at
      recompose that was never admitted at decompose).
    """

    verdict: str
    unaccounted: tuple[str, ...] = ()
    unrecognized: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()
    incomplete: tuple[str, ...] = ()
    extraneous: tuple[str, ...] = ()
    admitted_count: int = 0
    accounted_count: int = 0

    @property
    def is_laundering(self) -> bool:
        return self.verdict == VERDICT_REFUSED_LAUNDERING

    @property
    def admissible(self) -> bool:
        return self.verdict in (VERDICT_ADMISSIBLE, VERDICT_ADMISSIBLE_PARTIAL)


def account_boundaries(
    admitted: Sequence[str],
    accounted: Mapping[str, str],
) -> BoundaryAccounting:
    """Account every admitted decomposition boundary. Pure and total.

    The invariant: *output is not admissible unless its recomposition can
    account for every admitted decomposition boundary.* This function is the
    single point where that is decided, and it is total — every admitted
    boundary lands in exactly one bucket, so an unaccounted boundary cannot
    slip past as an absence.

    Verdict precedence (most dangerous first):

    1. any unaccounted or unrecognized boundary  → ``refused_laundering``
    2. else any refused boundary                 → ``refused_carried``
    3. else any failed/parked boundary           → ``admissible_partial_progress``
    4. else (all completed, incl. vacuous empty) → ``admissible``

    ``admissible_partial_progress`` here means only "structurally accounted with
    declared non-completion" — whether that loss is *within the declared
    fidelity budget* is a separate judgment this function deliberately does not
    make (it has no fidelity input). Do not read this verdict as "loss was
    affordable"; read it as "loss was declared, not hidden."
    """
    unaccounted: list[str] = []
    unrecognized: list[str] = []
    refused: list[str] = []
    incomplete: list[str] = []

    seen: set[str] = set()
    for boundary_id in admitted:
        seen.add(boundary_id)
        if boundary_id not in accounted:
            unaccounted.append(boundary_id)
            continue
        disposition = accounted[boundary_id]
        if disposition not in CLOSED_DISPOSITIONS:
            unrecognized.append(boundary_id)
        elif disposition == DISPOSITION_REFUSED:
            refused.append(boundary_id)
        elif disposition in (DISPOSITION_FAILED, DISPOSITION_PARKED):
            incomplete.append(boundary_id)
        # DISPOSITION_COMPLETED falls through as the clean case.

    extraneous = sorted(key for key in accounted if key not in seen)

    if unaccounted or unrecognized:
        verdict = VERDICT_REFUSED_LAUNDERING
    elif refused:
        verdict = VERDICT_REFUSED_CARRIED
    elif incomplete:
        verdict = VERDICT_ADMISSIBLE_PARTIAL
    else:
        verdict = VERDICT_ADMISSIBLE

    return BoundaryAccounting(
        verdict=verdict,
        unaccounted=tuple(unaccounted),
        unrecognized=tuple(unrecognized),
        refused=tuple(refused),
        incomplete=tuple(incomplete),
        extraneous=tuple(extraneous),
        admitted_count=len(seen),
        accounted_count=len(accounted),
    )


# --------------------------------------------------------------------------- #
# RecompositionReceipt
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RecompositionReceipt:
    """A content-addressed record of a recomposition's admissibility verdict.

    Shadow-only in P1: ``shadow=True`` / ``effective=False``. The receipt
    records the verdict the recomposition *would* render; it does not gate.

    Integrity invariant (the receipt-level teeth): ``verdict`` must equal
    ``account_boundaries(boundaries_admitted, dict(boundaries_accounted))
    .verdict``. You cannot hand-set ``verdict="admissible"`` while a boundary is
    unaccounted — the receipt refuses to be constructed inconsistent with its
    own boundary data. Build via :meth:`from_boundaries` so the verdict is
    computed, never asserted.

    The model substrate that produced the run is **not** a field here — that is
    a sibling concern (`working/forcing-case-degraded-model-availability.md`),
    deliberately not smuggled into the recomposition receipt.

    Fields:

    * ``projected_intent_hash`` — reference to the projected intent this
      recomposes (a hash string; format not constrained in P1).
    * ``fidelity_class`` — declared fidelity (``None`` until callers supply it;
      treated as descriptive in P1, never as an enforcement input).
    * ``boundaries_admitted`` — ids minted at decomposition.
    * ``boundaries_accounted`` — sorted (id, disposition) pairs; the immutable
      form of the id→disposition map.
    * ``losses_declared`` — declared losses (free-form labels in P1).
    * ``la_spend`` — sorted (key, value) spend summary pairs.
    * ``la_custody`` — whether the spend summary is LA-backed. ``False`` means
      local/receipt-only accounting (LA absent or not consulted); the downgrade
      is visible in the receipt rather than faked
      (`docs/doctrine/annealing_and_recomposition.md` §5 standalone rule).
    * ``accepted_by_kernel`` — which kernel/profile rendered the verdict
      (provisional naming permitted while shadow).
    * ``source_receipt_ids`` — receipts this recomposition derives from.
    * ``shadow`` / ``effective`` — exactly one is true (``shadow != effective``).
    """

    verdict: str
    projected_intent_hash: str
    boundaries_admitted: tuple[str, ...]
    boundaries_accounted: tuple[tuple[str, str], ...]
    accepted_by_kernel: str
    fidelity_class: str | None = None
    losses_declared: tuple[str, ...] = ()
    la_spend: tuple[tuple[str, str], ...] = ()
    la_custody: bool = False
    source_receipt_ids: tuple[str, ...] = ()
    shadow: bool = True
    effective: bool = False

    def __post_init__(self) -> None:
        if self.verdict not in CLOSED_VERDICTS:
            raise ValueError(
                f"verdict must be one of {sorted(CLOSED_VERDICTS)}, "
                f"got {self.verdict!r}"
            )
        if (
            self.fidelity_class is not None
            and self.fidelity_class not in CLOSED_FIDELITY_CLASSES
        ):
            raise ValueError(
                "fidelity_class must be None or one of "
                f"{sorted(CLOSED_FIDELITY_CLASSES)}, got {self.fidelity_class!r}"
            )
        if not self.projected_intent_hash:
            raise ValueError("projected_intent_hash must be non-empty")
        if not self.accepted_by_kernel:
            raise ValueError("accepted_by_kernel must be non-empty")
        if self.shadow is self.effective:
            raise ValueError(
                "exactly one of shadow / effective must be true "
                f"(shadow={self.shadow}, effective={self.effective})"
            )
        # The integrity invariant: verdict must match the boundary data.
        recomputed = account_boundaries(
            self.boundaries_admitted, dict(self.boundaries_accounted)
        ).verdict
        if recomputed != self.verdict:
            raise ValueError(
                "verdict inconsistent with boundary accounting: receipt carries "
                f"{self.verdict!r} but account_boundaries yields {recomputed!r}. "
                "A recomposition receipt cannot claim a verdict its own "
                "boundaries do not support."
            )

    @classmethod
    def from_boundaries(
        cls,
        *,
        projected_intent_hash: str,
        admitted: Sequence[str],
        accounted: Mapping[str, str],
        accepted_by_kernel: str,
        fidelity_class: str | None = None,
        losses_declared: Sequence[str] = (),
        la_spend: Mapping[str, str] | None = None,
        la_custody: bool = False,
        source_receipt_ids: Sequence[str] = (),
        shadow: bool = True,
        effective: bool = False,
    ) -> RecompositionReceipt:
        """Build a receipt, computing the verdict from the boundary data.

        This is the only intended construction path: the verdict is derived,
        never supplied, so a caller cannot launder one in.
        """
        verdict = account_boundaries(admitted, accounted or {}).verdict
        spend = la_spend or {}
        return cls(
            verdict=verdict,
            projected_intent_hash=projected_intent_hash,
            boundaries_admitted=tuple(admitted),
            boundaries_accounted=tuple(sorted(accounted.items())),
            accepted_by_kernel=accepted_by_kernel,
            fidelity_class=fidelity_class,
            losses_declared=tuple(losses_declared),
            la_spend=tuple(sorted(spend.items())),
            la_custody=la_custody,
            source_receipt_ids=tuple(source_receipt_ids),
            shadow=shadow,
            effective=effective,
        )

    def accounting(self) -> BoundaryAccounting:
        """Re-run boundary accounting for this receipt (full diagnosis)."""
        return account_boundaries(
            self.boundaries_admitted, dict(self.boundaries_accounted)
        )

    def canonical_dict(self) -> dict[str, Any]:
        """Deterministic dict for content addressing.

        No timestamp — identity is content, not time (cf. gate_receipt, where
        timestamp is metadata). ``shadow`` / ``effective`` are included: the
        same boundary data in shadow vs effective mode are distinct receipts.
        """
        return {
            "schema": "recomposition_receipt_v0",
            "verdict": self.verdict,
            "projected_intent_hash": self.projected_intent_hash,
            "boundaries_admitted": list(self.boundaries_admitted),
            "boundaries_accounted": [
                list(pair) for pair in self.boundaries_accounted
            ],
            "accepted_by_kernel": self.accepted_by_kernel,
            "fidelity_class": self.fidelity_class,
            "losses_declared": list(self.losses_declared),
            "la_spend": [list(pair) for pair in self.la_spend],
            "la_custody": self.la_custody,
            "source_receipt_ids": list(self.source_receipt_ids),
            "shadow": self.shadow,
            "effective": self.effective,
        }

    @property
    def recomposition_id(self) -> str:
        """SHA-256 hex over the canonical form. Stable, content-addressed."""
        return content_hash(canonical_json(self.canonical_dict()))

    def to_dict(self) -> dict[str, Any]:
        """Serializable form including the content id (for later emission)."""
        payload = self.canonical_dict()
        payload["recomposition_id"] = self.recomposition_id
        return payload
