"""Read-only annealing observation over a receipt/event stream (P1.3).

Workflow-kernel campaign, OBSERVE rung
(`working/campaign-workflow-kernel-annealing.md`,
`specs/gaps/GOV_GAP_ANNEALING_DELTA_001.md`). Consumes loop-protocol §11 metric
definitions (`docs/loop-protocol.md`, `working/pipeline-doctrine-2026-06-12.md`
§1): burn-per-progress, failure-class entropy, confusion signals.

The lineage is scar → observation → (later) candidate delta. This module is the
*observation* link and nothing more: it reads a window of records and derives an
`AnnealingObservation` classifying what it saw. It proposes no delta, activates
nothing, mutates nothing.

The load-bearing invariant is **purity, not classification accuracy**:

> annealing_observer can observe forever and never mutate shape.

That is guaranteed structurally, not by discipline: this module has NO emitter,
NO store, NO sink, NO write path. `observe_window` is a pure function returning a
value. "Probe/observer sessions emit zero mutation receipts" (loop-protocol §11)
is therefore true by construction here — there is nothing in this module that
could emit one. Persistence/emission of observations is deliberately deferred;
deriving them purely is the whole of the observation rung.

Reuses `gate_receipt.canonical_json`/`content_hash` (no second canonicalization).
Imports only pure types — no mutation-capable internals of any gate.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .gate_receipt import canonical_json, content_hash
from .pipeline_types import (
    VERDICT_ADMISSIBLE,
    VERDICT_ADMISSIBLE_PARTIAL,
    VERDICT_REFUSED_CARRIED,
    VERDICT_REFUSED_LAUNDERING,
    RecompositionReceipt,
)

# --------------------------------------------------------------------------- #
# Closed observation-pattern vocabulary
# --------------------------------------------------------------------------- #

PATTERN_NONE = "none"
PATTERN_RECOMPOSITION_LOSS = "recomposition_loss"
PATTERN_VERIFIER_FRAGILITY = "verifier_fragility"
PATTERN_RETRY_EXHAUSTION = "retry_exhaustion"
PATTERN_REPEATED_REFUSAL = "repeated_refusal"
PATTERN_WITNESS_GAP = "witness_gap"

CLOSED_OBSERVATION_PATTERNS = frozenset(
    {
        PATTERN_NONE,
        PATTERN_RECOMPOSITION_LOSS,
        PATTERN_VERIFIER_FRAGILITY,
        PATTERN_RETRY_EXHAUSTION,
        PATTERN_REPEATED_REFUSAL,
        PATTERN_WITNESS_GAP,
    }
)

# Pre-calibration heuristic (cf. other v1 thresholds in the campaign). A flailing
# agent "burns multiples of normal capacity per unit of progress" (§11); >3x is a
# conservative soft trip. Tunable via the parameter — the observer never tunes
# itself (that would be a mutation it is forbidden from making).
DEFAULT_SOFT_BURN_PER_PROGRESS = 3.0

# Advisory hint only: where a HUMAN or a Phase-2 proposer MIGHT look. This is a
# label on an observation, not a delta, not authorization. The observer generates
# nothing from it. Kept because GOV_GAP_ANNEALING_DELTA_001 lists the field; its
# advisory-only nature is the fence against "observe more" sliding into
# "believe more".
# Read-only (MappingProxyType): the observer reads this at derivation time, so a
# mutable global would make observe_window depend on shared state and undercut
# its purity / deterministic observation_id. Immutable constant, not a knob.
_SUGGESTED_DELTA_KIND: Mapping[str, str | None] = MappingProxyType(
    {
        PATTERN_RECOMPOSITION_LOSS: "tighten_boundary_accounting",
        PATTERN_VERIFIER_FRAGILITY: "smaller_decomposition",
        PATTERN_RETRY_EXHAUSTION: "lower_retry_budget",
        PATTERN_REPEATED_REFUSAL: "earlier_witness",
        PATTERN_WITNESS_GAP: "earlier_witness",
        PATTERN_NONE: None,
    }
)


# --------------------------------------------------------------------------- #
# Pure metric helpers (loop-protocol §11 definitions)
# --------------------------------------------------------------------------- #


def failure_class_entropy(classes: Sequence[str | None]) -> float:
    """Shannon entropy (base 2) over the distribution of failure classes.

    0.0 for empty or single-class windows; rises as attempts produce *different*
    kinds of failure — the §11 "model mismatch" signal. None entries are ignored
    (missing class is not a class).
    """
    counts = Counter(c for c in classes if c)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for n in counts.values():
        p = n / total
        entropy -= p * math.log2(p)
    return entropy


def burn_per_progress(
    capacity_spent: float, progress_count: int
) -> float | None:
    """capacity consumed / slice-advancing receipts (§11 keeper metric).

    Returns None when there were zero progress receipts — missing is not zero, so
    a ratio with a zero denominator is undefined rather than "infinitely bad".
    Zero-progress-with-spend is handled separately as a definitional flail in
    :func:`observe_window` (spend buying no admissible progress).
    """
    if progress_count <= 0:
        return None
    return capacity_spent / progress_count


# --------------------------------------------------------------------------- #
# Input record
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ObservationInput:
    """One record in the observed window. A neutral, read-only projection — the
    observer does not couple to any specific receipt schema.

    * ``kind`` — a free event/verdict label (e.g. a recomposition verdict).
    * ``failure_class`` — the failure class if this record is a failure, else
      None. Class match, never exact-string (§11: strings rot).
    * ``progressed`` — did this record advance a slice (a slice-advancing
      receipt)? Feeds burn-per-progress.
    * ``capacity_spent`` — capacity consumed producing this record.
    * ``witness_present`` — was a witness/evidence present? Absence feeds
      witness-gap detection.
    * ``receipt_id`` — provenance, carried where available.
    """

    kind: str
    failure_class: str | None = None
    progressed: bool = False
    capacity_spent: float = 0.0
    witness_present: bool = True
    receipt_id: str | None = None


def observation_input_from_recomposition(
    receipt: RecompositionReceipt,
) -> ObservationInput:
    """Adapter: project a P1.2 RecompositionReceipt into an ObservationInput.

    Honest mapping only — fields not derivable from the receipt keep their
    conservative defaults (capacity unknown → 0.0, witness unknown → present).
    A laundering or carried verdict is a failure class; an admissible (incl.
    partial) verdict is progress.
    """
    verdict = receipt.verdict
    is_failure = verdict in (VERDICT_REFUSED_LAUNDERING, VERDICT_REFUSED_CARRIED)
    return ObservationInput(
        kind=verdict,
        failure_class=verdict if is_failure else None,
        progressed=verdict in (VERDICT_ADMISSIBLE, VERDICT_ADMISSIBLE_PARTIAL),
        receipt_id=receipt.recomposition_id,
    )


# --------------------------------------------------------------------------- #
# Observation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AnnealingObservation:
    """A read-only, content-addressed summary of one observed window.

    Carries no authority and no mutation surface. ``suggested_delta_kind`` is an
    advisory label (where a human/Phase-2 might look), never a delta.
    """

    pattern: str
    affected_profile: str
    window_size: int
    failure_classes: tuple[tuple[str, int], ...]
    failure_entropy: float
    burn_per_progress: float | None
    recomposition_loss_count: int
    witness_gap_count: int
    source_receipt_ids: tuple[str, ...]
    suggested_delta_kind: str | None = None

    def __post_init__(self) -> None:
        if self.pattern not in CLOSED_OBSERVATION_PATTERNS:
            raise ValueError(
                f"pattern must be one of {sorted(CLOSED_OBSERVATION_PATTERNS)}, "
                f"got {self.pattern!r}"
            )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": "annealing_observation_v0",
            "pattern": self.pattern,
            "affected_profile": self.affected_profile,
            "window_size": self.window_size,
            "failure_classes": [list(pair) for pair in self.failure_classes],
            "failure_entropy": self.failure_entropy,
            "burn_per_progress": self.burn_per_progress,
            "recomposition_loss_count": self.recomposition_loss_count,
            "witness_gap_count": self.witness_gap_count,
            "source_receipt_ids": list(self.source_receipt_ids),
            "suggested_delta_kind": self.suggested_delta_kind,
        }

    @property
    def observation_id(self) -> str:
        return content_hash(canonical_json(self.canonical_dict()))

    def to_dict(self) -> dict[str, Any]:
        payload = self.canonical_dict()
        payload["observation_id"] = self.observation_id
        return payload


def observe_window(
    inputs: Sequence[ObservationInput],
    *,
    profile: str,
    soft_burn_threshold: float = DEFAULT_SOFT_BURN_PER_PROGRESS,
) -> AnnealingObservation:
    """Derive one AnnealingObservation from a window of records. Pure.

    No IO, no emission, no mutation — the input sequence is read, never written.
    Classifies the window into at most one pattern by precedence (most-structural
    first, then the §11 confusion signals, then repetition):

      recomposition_loss > verifier_fragility > retry_exhaustion
          > repeated_refusal > witness_gap > none
    """
    recomposition_loss_count = sum(
        1 for i in inputs if i.kind == VERDICT_REFUSED_LAUNDERING
    )
    witness_gap_count = sum(1 for i in inputs if not i.witness_present)

    classes = [i.failure_class for i in inputs if i.failure_class]
    class_counts = Counter(classes)
    entropy = failure_class_entropy(classes)
    distinct_classes = len(class_counts) >= 2
    repeated_class = any(n >= 2 for n in class_counts.values())

    total_capacity = sum(i.capacity_spent for i in inputs)
    progress_count = sum(1 for i in inputs if i.progressed)
    bpp = burn_per_progress(total_capacity, progress_count)
    # Flailing: either burn-per-progress over the soft trip, or capacity spent
    # buying zero progress at all (the strongest, denominator-undefined flail).
    over_burn = (bpp is not None and bpp > soft_burn_threshold) or (
        progress_count == 0 and total_capacity > 0
    )

    if recomposition_loss_count > 0:
        pattern = PATTERN_RECOMPOSITION_LOSS
    elif distinct_classes:
        pattern = PATTERN_VERIFIER_FRAGILITY
    elif over_burn:
        pattern = PATTERN_RETRY_EXHAUSTION
    elif repeated_class:
        pattern = PATTERN_REPEATED_REFUSAL
    elif witness_gap_count > 0:
        pattern = PATTERN_WITNESS_GAP
    else:
        pattern = PATTERN_NONE

    source_receipt_ids = tuple(
        dict.fromkeys(i.receipt_id for i in inputs if i.receipt_id)
    )

    return AnnealingObservation(
        pattern=pattern,
        affected_profile=profile,
        window_size=len(inputs),
        failure_classes=tuple(sorted(class_counts.items())),
        failure_entropy=entropy,
        burn_per_progress=bpp,
        recomposition_loss_count=recomposition_loss_count,
        witness_gap_count=witness_gap_count,
        source_receipt_ids=source_receipt_ids,
        suggested_delta_kind=_SUGGESTED_DELTA_KIND[pattern],
    )
