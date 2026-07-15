# SPDX-License-Identifier: Apache-2.0
"""Epistemic backoff for governed loops — loop-protocol §11.1, mechanized.

Classic backoff answers contention ("busy → wait → retry"). This answers
confusion ("my action model is failing → stop mutating → observe"). The
ratified rule (`docs/loop-protocol.md` §11.1; reasoning in
`working/pipeline-doctrine-2026-06-12.md` §1):

> When retries stop producing new evidence, retry is forbidden. When
> failures produce too many kinds of evidence, mutation is forbidden.

Four mechanized pieces (backlog `epistemic-backoff-mechanization`):

1. **Failure classes, never strings.** Matching is by :class:`FailureClass` —
   a closed starter vocabulary with an honest ``UNCLASSIFIED`` member.
   Exact-string matching rots immediately and is not offered.
2. **The backoff verdict.** :func:`evaluate_backoff` walks the ratified
   ladder ``retry → probe → escalate-once → park → halt``. Same class twice
   kills the transient hypothesis (a third try is superstition); distinct
   classes across attempts is a model-mismatch signature; burn-per-progress
   thresholds catch flailing that class-analysis misses. Tier escalation is
   ILLEGAL until after a probe pass, and is single-use.
3. **The confusion receipt.** :func:`build_confusion_bundle` produces the §1
   schema verbatim; :func:`emit_confusion_receipt` gives it custody as a
   ``loop_backoff`` gate receipt (verdict ``observe``) with the bundle in the
   content-addressed evidence store — one canonical home, receipt as proof.
4. **The probe wall audits itself.** PROBE forbids mutation; since everything
   is receipted, :func:`probe_wall_audit` checks *afterwards* that a probe
   window emitted zero mutation events. The invariant is a test, not a vibe.

Burn thresholds default to pre-calibration heuristics (same posture as the
2.4 signal configs); they are parameters, not policy claims.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from governor.gate_receipt import (
    EvidenceStore,
    GateReceipt,
    ReceiptStore,
    create_receipt,
)

PROTOCOL_REF = "docs/loop-protocol.md §11.1"
GATE_NAME = "loop_backoff"


class FailureClass(str, Enum):
    """Closed starter vocabulary for failure classification.

    Matching is by class membership only. ``UNCLASSIFIED`` is the honest
    unknown — it participates in repeat/distinct counting like any class
    (two unclassified failures in a row are still "the same thing keeps
    happening"). Extend by commit with a forcing case, never ad hoc.
    """

    TEST_FAILURE = "test_failure"
    BUILD_ERROR = "build_error"
    TOOL_ERROR = "tool_error"
    PERMISSION_DENIED = "permission_denied"
    MISSING_DEPENDENCY = "missing_dependency"
    SPEC_CONTRADICTION = "spec_contradiction"
    TIMEOUT = "timeout"
    ENVIRONMENT = "environment"
    UNCLASSIFIED = "unclassified"


class Mode(str, Enum):
    """The ratified ladder. RETRY is only ever prescribed for a single

    not-yet-repeated failure; everything past it is a mode switch."""

    RETRY = "retry"
    PROBE = "probe"
    ESCALATE_ONCE = "escalate_once"
    PARK = "park"
    HALT = "halt"


@dataclass(frozen=True)
class Attempt:
    """One failed attempt on a slice, as the loop records it."""

    slice_id: str
    failure_class: FailureClass
    capacity_spent: float = 0.0
    slice_advancing_receipts: int = 0
    at: str = ""  # ISO timestamp, informational


@dataclass(frozen=True)
class BackoffThresholds:
    """Burn-per-progress thresholds. Pre-calibration heuristics."""

    burn_soft: float = 3.0  # → mandatory PROBE downshift + confusion receipt
    burn_hard: float = 10.0  # → capacity checkpoint + halt for morning audit


@dataclass(frozen=True)
class BackoffVerdict:
    """The mechanical §11.1 verdict over a slice's attempt history."""

    prescribed_next_mode: Mode
    reason: str
    inferred_signature: str
    repeated_count: int
    distinct_count: int
    burn_per_progress: float | None
    confusion_receipt_required: bool


def burn_per_progress(attempts: Iterable[Attempt]) -> float | None:
    """capacity consumed / slice-advancing receipts emitted.

    ``None`` when nothing was spent (no signal). Division by zero progress is
    the signal working as designed: spend with zero admissible progress is
    represented as ``float('inf')`` — the flail detector's loudest reading.
    """

    spent = 0.0
    receipts = 0
    for attempt in attempts:
        spent += attempt.capacity_spent
        receipts += attempt.slice_advancing_receipts
    if spent == 0.0:
        return None
    if receipts == 0:
        return float("inf")
    return spent / receipts


def evaluate_backoff(
    attempts: list[Attempt],
    *,
    thresholds: BackoffThresholds | None = None,
    probe_completed: bool = False,
    escalation_used: bool = False,
) -> BackoffVerdict:
    """Walk §11.1 over a slice's failure history.

    ``probe_completed`` asserts a PROBE pass has already run for this
    confusion episode (tier escalation is illegal until then).
    ``escalation_used`` asserts the single escalation was already spent.
    Precedence: burn-hard halts over everything; then the post-probe ladder;
    then class analysis; burn-soft catches flailing the classes missed.
    """

    if not attempts:
        raise ValueError("evaluate_backoff requires at least one failed attempt")
    thresholds = thresholds or BackoffThresholds()

    classes = [a.failure_class for a in attempts]
    distinct = len(set(classes))
    repeated = max(classes.count(c) for c in set(classes))
    burn = burn_per_progress(attempts)
    burn_is_hard = burn is not None and burn >= thresholds.burn_hard
    burn_is_soft = burn is not None and burn >= thresholds.burn_soft

    if burn_is_hard:
        return BackoffVerdict(
            Mode.HALT,
            f"burn-per-progress {burn:.1f} >= hard threshold "
            f"{thresholds.burn_hard} — capacity checkpoint; morning audit",
            "capacity_flail_hard",
            repeated, distinct, burn,
            confusion_receipt_required=True,
        )

    if probe_completed:
        # Post-probe ladder: escalate once (baseline+1, recorded reason),
        # then park. Escalation is never a retry substitute.
        if not escalation_used:
            return BackoffVerdict(
                Mode.ESCALATE_ONCE,
                "probe pass complete and action still fails — one escalation "
                "(baseline+1) with recorded reason",
                "post_probe_escalation",
                repeated, distinct, burn,
                confusion_receipt_required=False,
            )
        return BackoffVerdict(
            Mode.PARK,
            "escalation already spent — park for batched clarification",
            "ladder_exhausted_to_park",
            repeated, distinct, burn,
            confusion_receipt_required=False,
        )

    if repeated >= 2:
        return BackoffVerdict(
            Mode.PROBE,
            f"failure class {max(set(classes), key=classes.count).value!r} "
            f"repeated {repeated}x — transient hypothesis dead; further "
            f"retries forbidden (a third try is superstition)",
            "dead_transient_hypothesis",
            repeated, distinct, burn,
            confusion_receipt_required=True,
        )

    if distinct >= 2:
        return BackoffVerdict(
            Mode.PROBE,
            f"{distinct} distinct failure classes across {len(attempts)} "
            f"attempts — model-mismatch signature; mutation forbidden",
            "model_mismatch",
            repeated, distinct, burn,
            confusion_receipt_required=True,
        )

    if burn_is_soft:
        return BackoffVerdict(
            Mode.PROBE,
            f"burn-per-progress {burn:.1f} >= soft threshold "
            f"{thresholds.burn_soft} — mandatory PROBE downshift",
            "capacity_flail_soft",
            repeated, distinct, burn,
            confusion_receipt_required=True,
        )

    return BackoffVerdict(
        Mode.RETRY,
        "single unrepeated failure class within burn budget — one retry "
        "under the transient hypothesis",
        "transient_hypothesis_live",
        repeated, distinct, burn,
        confusion_receipt_required=False,
    )


# ---------------------------------------------------------------------------
# Confusion receipt — the §1 schema, with gate-receipt custody
# ---------------------------------------------------------------------------


def build_confusion_bundle(
    slice_id: str,
    attempts: list[Attempt],
    verdict: BackoffVerdict,
) -> dict[str, Any]:
    """The §1 confusion-receipt schema, verbatim field-for-field."""

    return {
        "schema": "confusion-receipt/v1",
        "protocol_ref": PROTOCOL_REF,
        "slice_id": slice_id,
        "attempt_count": len(attempts),
        "failure_classes_seen": sorted({a.failure_class.value for a in attempts}),
        "repeated_count": verdict.repeated_count,
        "distinct_count": verdict.distinct_count,
        "capacity_spent": sum(a.capacity_spent for a in attempts),
        "slice_advancing_receipts": sum(a.slice_advancing_receipts for a in attempts),
        "burn_per_progress": (
            None if verdict.burn_per_progress is None
            else ("inf" if verdict.burn_per_progress == float("inf")
                  else verdict.burn_per_progress)
        ),
        "inferred_signature": verdict.inferred_signature,
        "prescribed_next_mode": verdict.prescribed_next_mode.value,
    }


def emit_confusion_receipt(
    bundle: dict[str, Any],
    *,
    receipt_store: ReceiptStore,
    evidence_store: EvidenceStore,
    principal_id: str = "loop",
    timestamp: str | None = None,
) -> GateReceipt:
    """Give a confusion bundle custody: evidence store + gate receipt.

    The bundle is the canonical record (content-addressed in the evidence
    store); the ``loop_backoff`` gate receipt is the proof it was recorded,
    ``verdict="observe"`` — a confusion receipt authorizes nothing.
    """

    evidence_store.put(bundle)
    receipt = create_receipt(
        gate=GATE_NAME,
        verdict="observe",
        subject_kind="loop_slice",
        subject_bytes=bundle["slice_id"].encode(),
        evidence_bundle=bundle,
        gate_config={"protocol_ref": PROTOCOL_REF, "schema": bundle["schema"]},
        principal_id=principal_id,
        timestamp=timestamp,
    )
    receipt_store.append(receipt)
    return receipt


# ---------------------------------------------------------------------------
# The probe wall audits itself
# ---------------------------------------------------------------------------

#: Runtime event kinds/action classes that constitute mutation evidence.
#: A probe session emitting ANY of these has breached the wall.
_MUTATING_ACTION_CLASSES = frozenset({"write", "communicate"})


@dataclass(frozen=True)
class ProbeWallResult:
    """Outcome of the after-the-fact probe-wall check."""

    clean: bool
    mutation_events: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def breach_count(self) -> int:
        return len(self.mutation_events)


def probe_wall_audit(
    events: Iterable[dict[str, Any]],
    *,
    window_start: str,
    window_end: str,
) -> ProbeWallResult:
    """Check that a probe window emitted zero mutation receipts.

    ``events`` are canonical runtime events (dicts, as persisted in the
    ``.governor/runtime/*_events.jsonl`` ledgers). Mutation evidence is a
    ``tool_call_allowed`` event whose ``action_class`` is write/communicate
    with ``ts`` inside ``[window_start, window_end)`` (ISO-8601 strings —
    lexicographic comparison is chronological for a shared format). A probe
    that patched something is evidenced after the fact; the wall audits
    itself from the trail it cannot avoid leaving.
    """

    breaches: list[dict[str, Any]] = []
    for event in events:
        if event.get("kind") != "tool_call_allowed":
            continue
        ts = str(event.get("ts", ""))
        if not (window_start <= ts < window_end):
            continue
        payload = event.get("payload") or {}
        if payload.get("action_class") in _MUTATING_ACTION_CLASSES:
            breaches.append(event)
    return ProbeWallResult(clean=not breaches, mutation_events=tuple(breaches))


# ---------------------------------------------------------------------------
# Correlated confusion — the morning-audit obligation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrelatedConfusion:
    """N≥2 principals confused on unrelated slices in one window."""

    window_start: str
    window_end: str
    principal_ids: tuple[str, ...]
    slice_ids: tuple[str, ...]
    receipt_ids: tuple[str, ...]

    def describe(self) -> str:
        return (
            f"confusion receipts from {len(self.principal_ids)} principals on "
            f"{len(self.slice_ids)} unrelated slices within one window — "
            f"environment-level failure, not slice-level; escalate to "
            f"environment diagnosis before any recomposition, and before any "
            f"quorum counts agreement as evidence"
        )


def correlated_confusion_audit(
    receipts_path: Path,
    store_root: Path,
    *,
    window_seconds: int = 3600,
    min_principals: int = 2,
) -> list[CorrelatedConfusion]:
    """Scan the receipt trail for correlated confusion (§11.1 morning audit).

    ``store_root`` is the store root (e.g. ``.governor``) — ``EvidenceStore``
    nests its own ``evidence/`` under it. Reads ``loop_backoff`` gate
    receipts, resolves their bundles from the evidence store, and windows
    them by timestamp: two or more distinct principals emitting confusion on
    distinct slices inside one window flags environment-level diagnosis.
    Missing/unresolvable bundles are skipped — absence of evidence is not
    correlation evidence.
    """

    from datetime import datetime, timedelta

    store = EvidenceStore(store_root)
    entries: list[tuple[datetime, str, str, str]] = []  # (ts, principal, slice, rid)
    if not receipts_path.is_file():
        return []
    for line in receipts_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("gate") != GATE_NAME:
            continue
        bundle = store.get(rec.get("evidence_hash", ""))
        if not isinstance(bundle, dict) or "slice_id" not in bundle:
            continue
        try:
            ts = datetime.fromisoformat(rec["timestamp"])
        except (KeyError, ValueError):
            continue
        entries.append(
            (ts, rec.get("principal_id", "unknown"), str(bundle["slice_id"]),
             rec.get("receipt_id", ""))
        )

    entries.sort(key=lambda e: e[0])
    findings: list[CorrelatedConfusion] = []
    window = timedelta(seconds=window_seconds)
    used: set[int] = set()
    for i, (ts_i, _, _, _) in enumerate(entries):
        if i in used:
            continue
        group = [j for j in range(i, len(entries)) if entries[j][0] - ts_i <= window]
        principals = {entries[j][1] for j in group}
        slices = {entries[j][2] for j in group}
        if len(principals) >= min_principals and len(slices) >= 2:
            used.update(group)
            findings.append(
                CorrelatedConfusion(
                    window_start=ts_i.isoformat(),
                    window_end=(ts_i + window).isoformat(),
                    principal_ids=tuple(sorted(principals)),
                    slice_ids=tuple(sorted(slices)),
                    receipt_ids=tuple(entries[j][3] for j in group),
                )
            )
    return findings
