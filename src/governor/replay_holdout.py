# SPDX-License-Identifier: Apache-2.0
"""P4.0f — replay/holdout falsification witness: DERIVE the verdict, never stamp it.

The second promotion witness (Checkpoint 1) asks one question only::

    Did this specific trial/candidate non-regress against this specific prior
    baseline on this frozen replay/holdout corpus, using this witnessed harness run?

This module is the **receipting/attestation layer** for that witness. It records raw
FACTS about a harness run and derives an admissibility verdict from them — it does NOT
run replay, define replay semantics, or judge promotion.

**Design call (resolved 2026-06-14):** the C1 `signals/replay_harness.py`
(`REPLAY_HARNESS`) is a *semantic mismatch* — it replays SIGNAL derivations under
alternative thresholds (drift statistics), not a trial-vs-baseline non-regression over a
frozen corpus. A thin adapter over it would answer the wrong question. So P4.0f does not
wrap C1 and does not invent a second replay semantics either: it stays agnostic about
*which* harness ran (named by `replay_harness_id`/`version`) and only ATTESTS + BINDS the
witnessed run. Live invocation of a real non-regression harness is a later wiring
concern; this slice is the receipt + derivation + refusals, like P4.0e was for
observations.

Doctrine carried from P4.0e: **producer-derived ≠ producer-trusted.** The verdict is
derived from facts here, persisted by the store, and **re-derived on load** — the stored
verdict is an accusation against the facts, re-tried at the border.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .clock_witness import (
    GapBasisMismatch,
    MonotonicEpochMismatch,
    MonotonicReading,
    elapsed_ns,
)

# --- Verdicts ----------------------------------------------------------------
REPLAY_VERDICT_PASSED = "non_regression_passed"
REPLAY_VERDICT_REFUSED = "refused"

# --- Closed refusal vocabulary (why a replay run is not an admissible pass) ---
REPLAY_MISSING_TRIAL_BINDING = "replay_missing_trial_binding"
REPLAY_MISSING_CANDIDATE_BINDING = "replay_missing_candidate_binding"
REPLAY_MISSING_COMPARATOR_BASELINE = "replay_missing_comparator_baseline"
REPLAY_MISSING_CORPUS_HASH = "replay_missing_corpus_hash"
REPLAY_CORPUS_NOT_FROZEN = "replay_corpus_not_frozen"
REPLAY_MISSING_HARNESS_IDENTITY = "replay_missing_harness_identity"
REPLAY_CHILD_EXIT_NOT_OBSERVED = "replay_child_exit_not_observed"
REPLAY_HARNESS_RUN_FAILED = "replay_harness_run_failed"
REPLAY_MISSING_RAW_RESULT = "replay_missing_raw_result"
REPLAY_REGRESSION_DETECTED = "replay_regression_detected"

REPLAY_REFUSAL_REASONS = frozenset(
    {
        REPLAY_MISSING_TRIAL_BINDING,
        REPLAY_MISSING_CANDIDATE_BINDING,
        REPLAY_MISSING_COMPARATOR_BASELINE,
        REPLAY_MISSING_CORPUS_HASH,
        REPLAY_CORPUS_NOT_FROZEN,
        REPLAY_MISSING_HARNESS_IDENTITY,
        REPLAY_CHILD_EXIT_NOT_OBSERVED,
        REPLAY_HARNESS_RUN_FAILED,
        REPLAY_MISSING_RAW_RESULT,
        REPLAY_REGRESSION_DETECTED,
    }
)

# Canonical ordering — bindings, then run-integrity, then the regression verdict.
_REASON_ORDER = (
    REPLAY_MISSING_TRIAL_BINDING,
    REPLAY_MISSING_CANDIDATE_BINDING,
    REPLAY_MISSING_COMPARATOR_BASELINE,
    REPLAY_MISSING_CORPUS_HASH,
    REPLAY_CORPUS_NOT_FROZEN,
    REPLAY_MISSING_HARNESS_IDENTITY,
    REPLAY_MISSING_RAW_RESULT,
    REPLAY_CHILD_EXIT_NOT_OBSERVED,
    REPLAY_HARNESS_RUN_FAILED,
    REPLAY_REGRESSION_DETECTED,
)


class MalformedReplayFactsError(ValueError):
    """Replay facts were structurally malformed (wrong types). A verdict cannot be
    derived from a shape that cannot be read; refused at construction, never coerced
    into a permissive pass."""


def _reading_block(r: MonotonicReading) -> dict[str, Any]:
    return {"source": r.source, "epoch": r.epoch, "ns": r.ns}


@dataclass(frozen=True)
class ReplayHoldoutFacts:
    """Raw facts about a witnessed non-regression harness run. **No verdict field is
    trusted** — `result_non_regression` is the *harness's own* result on its artifact;
    the admissible verdict is DERIVED here (and re-derived on load) from these facts
    plus the structural gates. Timing is monotonic-witnessed so P4.0g's freshness scar
    (operator-review window vs replay duration) can be enforced later.
    """

    trial_id: str
    candidate_id: str
    comparator_baseline_id: str
    replay_subject: str
    replay_harness_id: str
    harness_version: str
    corpus_id: str
    corpus_hash: str
    frozen_corpus_hash: str
    corpus_frozen_at: str  # ISO provenance (frozen BEFORE the run); display-only
    started_at: MonotonicReading
    completed_at: MonotonicReading
    child_exit: int
    exit_observed: bool
    raw_result_hash: str
    result_non_regression: bool  # the harness's OWN verdict on its result artifact

    def __post_init__(self) -> None:
        if not isinstance(self.child_exit, int) or isinstance(self.child_exit, bool):
            raise MalformedReplayFactsError("child_exit must be an int")
        if not isinstance(self.exit_observed, bool):
            raise MalformedReplayFactsError("exit_observed must be a bool")
        if not isinstance(self.result_non_regression, bool):
            raise MalformedReplayFactsError("result_non_regression must be a bool")
        for r in (self.started_at, self.completed_at):
            if not isinstance(r, MonotonicReading):
                raise MalformedReplayFactsError(
                    "started_at/completed_at must be MonotonicReading"
                )

    def duration_ns(self) -> int | None:
        """Run duration on the licensed monotonic subtraction; None if the two
        readings are on incompatible bases (cannot be honestly differenced)."""
        try:
            return elapsed_ns(self.started_at, self.completed_at)
        except (GapBasisMismatch, MonotonicEpochMismatch):
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "candidate_id": self.candidate_id,
            "comparator_baseline_id": self.comparator_baseline_id,
            "replay_subject": self.replay_subject,
            "replay_harness_id": self.replay_harness_id,
            "harness_version": self.harness_version,
            "corpus_id": self.corpus_id,
            "corpus_hash": self.corpus_hash,
            "frozen_corpus_hash": self.frozen_corpus_hash,
            "corpus_frozen_at": self.corpus_frozen_at,
            "started_at": _reading_block(self.started_at),
            "completed_at": _reading_block(self.completed_at),
            "child_exit": self.child_exit,
            "exit_observed": self.exit_observed,
            "raw_result_hash": self.raw_result_hash,
            "result_non_regression": self.result_non_regression,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReplayHoldoutFacts":
        def _reading(b: dict[str, Any]) -> MonotonicReading:
            return MonotonicReading(source=b["source"], epoch=b["epoch"], ns=b["ns"])

        return cls(
            trial_id=d["trial_id"],
            candidate_id=d["candidate_id"],
            comparator_baseline_id=d["comparator_baseline_id"],
            replay_subject=d["replay_subject"],
            replay_harness_id=d["replay_harness_id"],
            harness_version=d["harness_version"],
            corpus_id=d["corpus_id"],
            corpus_hash=d["corpus_hash"],
            frozen_corpus_hash=d["frozen_corpus_hash"],
            corpus_frozen_at=d["corpus_frozen_at"],
            started_at=_reading(d["started_at"]),
            completed_at=_reading(d["completed_at"]),
            child_exit=d["child_exit"],
            exit_observed=d["exit_observed"],
            raw_result_hash=d["raw_result_hash"],
            result_non_regression=d["result_non_regression"],
        )


@dataclass(frozen=True)
class ReplayVerdict:
    """Derived verdict. ``passed`` iff ``reasons`` is empty; ``reasons`` carries every
    failing reason in canonical order (never collapses)."""

    verdict: str
    reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.verdict == REPLAY_VERDICT_PASSED


def derive_replay_verdict(facts: ReplayHoldoutFacts) -> ReplayVerdict:
    """Pure, total derivation. ``non_regression_passed`` requires ALL of: every binding
    present (trial / candidate / comparator-baseline / corpus / harness identity / raw
    result), the corpus frozen-and-matching (`corpus_hash == frozen_corpus_hash`), the
    child exit observed and zero, and the harness's own non-regression result True. Any
    failure → ``refused`` with all reasons. The harness's `result_non_regression` is one
    input among the gates, not the authority — a "pass" with an unobserved exit, a
    floating corpus, or a missing baseline is still refused."""
    reasons: set[str] = set()

    if not facts.trial_id:
        reasons.add(REPLAY_MISSING_TRIAL_BINDING)
    if not facts.candidate_id:
        reasons.add(REPLAY_MISSING_CANDIDATE_BINDING)
    if not facts.comparator_baseline_id:
        reasons.add(REPLAY_MISSING_COMPARATOR_BASELINE)
    if not facts.corpus_hash:
        reasons.add(REPLAY_MISSING_CORPUS_HASH)
    # Frozen-and-matching: the evaluated corpus must be the corpus frozen before the run.
    if not facts.frozen_corpus_hash or facts.corpus_hash != facts.frozen_corpus_hash:
        reasons.add(REPLAY_CORPUS_NOT_FROZEN)
    if not facts.replay_harness_id or not facts.harness_version:
        reasons.add(REPLAY_MISSING_HARNESS_IDENTITY)
    if not facts.raw_result_hash:
        reasons.add(REPLAY_MISSING_RAW_RESULT)
    if not facts.exit_observed:
        reasons.add(REPLAY_CHILD_EXIT_NOT_OBSERVED)
    elif facts.child_exit != 0:
        reasons.add(REPLAY_HARNESS_RUN_FAILED)
    if not facts.result_non_regression:
        reasons.add(REPLAY_REGRESSION_DETECTED)

    ordered = tuple(r for r in _REASON_ORDER if r in reasons)
    verdict = REPLAY_VERDICT_PASSED if not ordered else REPLAY_VERDICT_REFUSED
    return ReplayVerdict(verdict=verdict, reasons=ordered)


__all__ = [
    "REPLAY_VERDICT_PASSED",
    "REPLAY_VERDICT_REFUSED",
    "REPLAY_MISSING_TRIAL_BINDING",
    "REPLAY_MISSING_CANDIDATE_BINDING",
    "REPLAY_MISSING_COMPARATOR_BASELINE",
    "REPLAY_MISSING_CORPUS_HASH",
    "REPLAY_CORPUS_NOT_FROZEN",
    "REPLAY_MISSING_HARNESS_IDENTITY",
    "REPLAY_CHILD_EXIT_NOT_OBSERVED",
    "REPLAY_HARNESS_RUN_FAILED",
    "REPLAY_MISSING_RAW_RESULT",
    "REPLAY_REGRESSION_DETECTED",
    "REPLAY_REFUSAL_REASONS",
    "MalformedReplayFactsError",
    "ReplayHoldoutFacts",
    "ReplayVerdict",
    "derive_replay_verdict",
]
