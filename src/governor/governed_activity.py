# SPDX-License-Identifier: Apache-2.0
"""
Governed Activity Foundation — drift-gated retry substrate.

Receipted side-effect capsules for workflow orchestration. Deterministic
orchestration calls non-deterministic actions through a governed gate.

v2 foundation: receipts + a lookup + a rule. No new engine.

Key types:
  - FactObservation: ops-native observation of external system state
  - PreconditionBundle: sorted tuple of FactObservations with stable fingerprint
  - AttemptRecord: per-attempt record with precondition fingerprint + etag snapshot
  - DriftCheckResult: tiered drift verdict with receipt hash

Pure functions:
  - drift_check: tiered drift detection (etag overlap → fingerprint fallback)
  - drift_check_stored: same logic with stored fingerprint + etags
  - on_attempt: drift-gate algorithm (verdict authoritative regardless of receipt)
  - record_attempt: post-execution recording to JSONL store

Design authority: specs/gaps/GOVERNED_ACTIVITIES.md
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from governor.gate_receipt import (
    GateReceiptSystem,
    canonical_json,
    content_hash,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

DIVERGENCE_DETECTED = "DivergenceDetected"


# =============================================================================
# Enums
# =============================================================================


class ActivityOutcome(str, Enum):
    """What happened when the activity executed."""

    SUCCESS = "success"
    BUSINESS_FAILURE = "business_failure"
    SYSTEM_FAILURE = "system_failure"


class RetryClass(str, Enum):
    """Classification for retry safety."""

    NONE = "none"
    SAFE_TRANSIENT = "safe_transient"
    UNSAFE = "unsafe"
    OPERATOR_REQUIRED = "operator_required"
    UNKNOWN = "unknown"


class DriftVerdict(str, Enum):
    """Result of tiered drift detection."""

    NO_DRIFT = "no_drift"
    ETAG_DIVERGED = "etag_diverged"
    FINGERPRINT_DIVERGED = "fingerprint_diverged"
    NO_PRIOR = "no_prior"
    CONTINUITY_LOST = "continuity_lost"


class IdempotencyStrategy(str, Enum):
    """How idempotency is ensured for this activity."""

    CALLER_PROVIDED = "caller_provided"
    CAS_BINDING = "cas_binding"
    RECORD_ID_BASED = "record_id_based"
    NONE = "none"


# =============================================================================
# Verdict → gate receipt mapping
# =============================================================================

_VERDICT_TO_GATE: dict[DriftVerdict, str] = {
    DriftVerdict.NO_DRIFT: "pass",
    DriftVerdict.ETAG_DIVERGED: "block",
    DriftVerdict.FINGERPRINT_DIVERGED: "block",
    DriftVerdict.NO_PRIOR: "observe",
    DriftVerdict.CONTINUITY_LOST: "warn",
}

ACTIVITY_DRIFT_GATE = "activity_drift"


# =============================================================================
# FactObservation
# =============================================================================

# Fields excluded from fingerprint (volatile / policy, not world state)
_FINGERPRINT_EXCLUDED = frozenset({"observed_at", "confidence", "freshness_s"})

# Fields included in fingerprint (world state) — always present, never dropped
_FINGERPRINT_FIELDS = (
    "fact_type", "subject", "source",
    "request_fingerprint", "response_fingerprint", "etag_or_version",
)

# Sort key fields for PreconditionBundle ordering
_SORT_KEY_FIELDS = (
    "fact_type", "subject", "request_fingerprint",
    "response_fingerprint", "etag_or_version", "source",
)


@dataclass(frozen=True)
class FactObservation:
    """Ops-native observation of external system state.

    NOT a general facts type — ops observations only. Cross-cutting:
    ops_governor can import this.

    Fingerprint excludes volatile fields (observed_at, confidence, freshness_s).
    Optional strings normalize to "" in fingerprint_dict().
    etag_or_version is a single normalized string — if the provider gives
    multiple tokens (etag + version + generation), caller concatenates/hashes
    them before constructing.
    """

    fact_type: str
    observed_at: str  # ISO 8601 UTC
    subject: str | None = None
    request_fingerprint: str | None = None
    response_fingerprint: str | None = None
    etag_or_version: str | None = None
    freshness_s: int | None = None
    confidence: str | None = None
    source: str | None = None

    def fingerprint_dict(self) -> dict[str, str]:
        """Fingerprint-relevant fields, optional strings normalized to ''.

        Unicode normalization (NFC/NFD): not performed. canonical_json uses
        ensure_ascii=True, which escapes all non-ASCII codepoints to \\uXXXX.
        This makes fingerprints byte-stable across platforms but does NOT
        normalize visually-identical Unicode strings (e.g., e+combining-accent
        vs precomposed-e). Callers producing fingerprint input from
        human-authored text should NFC-normalize before construction if they
        care about visual equivalence. For machine-generated identifiers
        (API keys, etags, hashes), this is a non-issue.

        response_fingerprint stability: the drift gate assumes this value is
        semantically stable across observations of the same logical state.
        It must be computed from a canonical subset of the provider response
        (sorted keys, deterministic serialization). If the upstream response
        contains non-deterministic fields (request IDs, timestamps, unordered
        collections), those must be excluded before hashing. False drift from
        unstable response_fingerprint is a caller bug, not a gate bug.
        """
        return {
            "fact_type": self.fact_type,
            "subject": self.subject or "",
            "source": self.source or "",
            "request_fingerprint": self.request_fingerprint or "",
            "response_fingerprint": self.response_fingerprint or "",
            "etag_or_version": self.etag_or_version or "",
        }

    def fingerprint(self) -> str:
        """Content hash of the fingerprint dict."""
        return content_hash(canonical_json(self.fingerprint_dict()))

    def etag_key(self) -> str:
        """Key for etag comparison: 'fact_type:subject:source'.

        Includes source so the same subject observed from two different
        providers doesn't collide.

        Does NOT include request_fingerprint. Rationale: etag_or_version is
        a provider-assigned concurrency token for a specific resource, not a
        specific query against it. If the same resource (fact_type + subject +
        source) returns different etags for different request parameters
        (filters, regions, credentials), the caller should encode that
        distinction into ``subject`` or ``source`` — not silently overload
        the same etag key. Folding request_fingerprint in would split a
        single provider token across multiple keys, defeating the "did the
        resource change?" question etags answer.
        """
        return f"{self.fact_type}:{self.subject or ''}:{self.source or ''}"

    def sort_key(self) -> tuple[str, ...]:
        """Deterministic sort key for PreconditionBundle ordering."""
        fp = self.fingerprint_dict()
        return tuple(fp.get(f, "") for f in _SORT_KEY_FIELDS)

    def to_dict(self) -> dict[str, Any]:
        """Full serialization (all fields)."""
        d: dict[str, Any] = {"fact_type": self.fact_type, "observed_at": self.observed_at}
        if self.subject is not None:
            d["subject"] = self.subject
        if self.request_fingerprint is not None:
            d["request_fingerprint"] = self.request_fingerprint
        if self.response_fingerprint is not None:
            d["response_fingerprint"] = self.response_fingerprint
        if self.etag_or_version is not None:
            d["etag_or_version"] = self.etag_or_version
        if self.freshness_s is not None:
            d["freshness_s"] = self.freshness_s
        if self.confidence is not None:
            d["confidence"] = self.confidence
        if self.source is not None:
            d["source"] = self.source
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FactObservation:
        return cls(
            fact_type=d["fact_type"],
            observed_at=d["observed_at"],
            subject=d.get("subject"),
            request_fingerprint=d.get("request_fingerprint"),
            response_fingerprint=d.get("response_fingerprint"),
            etag_or_version=d.get("etag_or_version"),
            freshness_s=d.get("freshness_s"),
            confidence=d.get("confidence"),
            source=d.get("source"),
        )


# =============================================================================
# PreconditionBundle
# =============================================================================


@dataclass(frozen=True)
class PreconditionBundle:
    """Sorted tuple of FactObservations with stable fingerprint.

    Sort key: (fact_type, subject, request_fingerprint, response_fingerprint,
               etag_or_version, source) — full deterministic tie-breaker.
    All optional strings normalized to "" for sort comparison.
    """

    observations: tuple[FactObservation, ...] = ()

    def __init__(self, observations: list[FactObservation] | tuple[FactObservation, ...] = ()):
        # Sort and store as tuple (frozen dataclass)
        sorted_obs = tuple(sorted(observations, key=lambda o: o.sort_key()))
        object.__setattr__(self, "observations", sorted_obs)

    def fingerprint(self) -> str:
        """Stable fingerprint of the entire bundle."""
        dicts = [o.fingerprint_dict() for o in self.observations]
        return content_hash(canonical_json({"observations": dicts}))

    def etag_snapshot(self) -> dict[str, str]:
        """Map of etag_key → etag_or_version for facts that have etags.

        Only includes facts where etag_or_version is non-empty.
        """
        result: dict[str, str] = {}
        for obs in self.observations:
            etag = obs.etag_or_version
            if etag:
                result[obs.etag_key()] = etag
        return result

    def has_etags(self) -> bool:
        """Whether any observation in this bundle has an etag."""
        return bool(self.etag_snapshot())

    def to_dict(self) -> dict[str, Any]:
        return {"observations": [o.to_dict() for o in self.observations]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PreconditionBundle:
        return cls([FactObservation.from_dict(o) for o in d.get("observations", [])])


# =============================================================================
# AttemptRecord
# =============================================================================


@dataclass(frozen=True)
class AttemptRecord:
    """Per-attempt record with precondition fingerprint and etag snapshot.

    created_at is for debugging/queries, not identity or fingerprinting.
    """

    call_id: str
    attempt: int
    precondition_fingerprint: str
    etag_snapshot: dict[str, str]  # etag_key → etag value
    outcome: ActivityOutcome
    retry_class: RetryClass
    error_class: str | None = None
    error_message: str | None = None
    receipt_hash: str | None = None
    idempotency_strategy: IdempotencyStrategy = IdempotencyStrategy.NONE
    receipt_emission_ok: bool | None = None
    receipt_emission_error: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "call_id": self.call_id,
            "attempt": self.attempt,
            "precondition_fingerprint": self.precondition_fingerprint,
            "etag_snapshot": self.etag_snapshot,
            "outcome": self.outcome.value,
            "retry_class": self.retry_class.value,
        }
        if self.error_class is not None:
            d["error_class"] = self.error_class
        if self.error_message is not None:
            d["error_message"] = self.error_message
        if self.receipt_hash is not None:
            d["receipt_hash"] = self.receipt_hash
        if self.idempotency_strategy != IdempotencyStrategy.NONE:
            d["idempotency_strategy"] = self.idempotency_strategy.value
        if self.receipt_emission_ok is not None:
            d["receipt_emission_ok"] = self.receipt_emission_ok
        if self.receipt_emission_error is not None:
            d["receipt_emission_error"] = self.receipt_emission_error
        if self.created_at is not None:
            d["created_at"] = self.created_at
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AttemptRecord:
        return cls(
            call_id=d["call_id"],
            attempt=d["attempt"],
            precondition_fingerprint=d["precondition_fingerprint"],
            etag_snapshot=d.get("etag_snapshot", {}),
            outcome=ActivityOutcome(d["outcome"]),
            retry_class=RetryClass(d["retry_class"]),
            error_class=d.get("error_class"),
            error_message=d.get("error_message"),
            receipt_hash=d.get("receipt_hash"),
            idempotency_strategy=IdempotencyStrategy(
                d.get("idempotency_strategy", "none")
            ),
            receipt_emission_ok=d.get("receipt_emission_ok"),
            receipt_emission_error=d.get("receipt_emission_error"),
            created_at=d.get("created_at"),
        )


# =============================================================================
# DriftCheckResult
# =============================================================================


@dataclass(frozen=True)
class DriftCheckResult:
    """Result of a tiered drift check."""

    verdict: DriftVerdict
    retry_class: RetryClass
    prior_fingerprint: str | None = None
    current_fingerprint: str | None = None
    etag_tier_used: bool = False
    receipt_hash: str | None = None
    receipt_emission_ok: bool | None = None
    receipt_emission_error: str | None = None


# =============================================================================
# Pure drift detection functions
# =============================================================================


def _etag_drift(
    prior_etags: dict[str, str],
    current_etags: dict[str, str],
) -> DriftVerdict | None:
    """Tiered etag comparison. Returns verdict or None to fall through.

    Decision tree:
    1. Compute overlap of etag key sets
    2. If overlap non-empty:
       - Any overlapping token differs → ETAG_DIVERGED
       - All match → fall through to fingerprint (return None)
    3. If one side has etags but the other doesn't → CONTINUITY_LOST
    4. If neither has etags → fall through (return None)
    """
    prior_has = bool(prior_etags)
    current_has = bool(current_etags)

    if not prior_has and not current_has:
        # Neither has etags — fall through to fingerprint
        return None

    if prior_has != current_has:
        # One side has etags, the other doesn't — continuity break
        return DriftVerdict.CONTINUITY_LOST

    # Both have etags — check overlap
    overlap = set(prior_etags) & set(current_etags)

    if not overlap:
        # No overlapping keys — continuity lost (completely different key sets)
        return DriftVerdict.CONTINUITY_LOST

    # Check overlapping keys for divergence
    for key in overlap:
        if prior_etags[key] != current_etags[key]:
            return DriftVerdict.ETAG_DIVERGED

    # All overlapping etags match — fall through to fingerprint
    return None


def drift_check(
    prior_bundle: PreconditionBundle,
    current_bundle: PreconditionBundle,
) -> DriftVerdict:
    """Tiered drift detection: etag overlap first, fingerprint fallback.

    Pure function — no IO, no side effects.
    """
    # Tier 1: etag comparison
    etag_verdict = _etag_drift(
        prior_bundle.etag_snapshot(),
        current_bundle.etag_snapshot(),
    )
    if etag_verdict is not None:
        return etag_verdict

    # Tier 2: fingerprint comparison
    if prior_bundle.fingerprint() != current_bundle.fingerprint():
        return DriftVerdict.FINGERPRINT_DIVERGED

    return DriftVerdict.NO_DRIFT


def drift_check_stored(
    prior_fingerprint: str,
    prior_etags: dict[str, str],
    current_bundle: PreconditionBundle,
) -> DriftVerdict:
    """Drift check using stored fingerprint + etags from a prior AttemptRecord.

    Same tiered logic as drift_check, but works with stored data instead
    of a full PreconditionBundle.
    """
    # Tier 1: etag comparison
    etag_verdict = _etag_drift(prior_etags, current_bundle.etag_snapshot())
    if etag_verdict is not None:
        return etag_verdict

    # Tier 2: fingerprint comparison
    if prior_fingerprint != current_bundle.fingerprint():
        return DriftVerdict.FINGERPRINT_DIVERGED

    return DriftVerdict.NO_DRIFT


# =============================================================================
# Drift verdict → retry class mapping
# =============================================================================

_VERDICT_TO_RETRY: dict[DriftVerdict, RetryClass] = {
    DriftVerdict.NO_DRIFT: RetryClass.SAFE_TRANSIENT,
    DriftVerdict.ETAG_DIVERGED: RetryClass.UNSAFE,
    DriftVerdict.FINGERPRINT_DIVERGED: RetryClass.UNSAFE,
    DriftVerdict.NO_PRIOR: RetryClass.SAFE_TRANSIENT,
    DriftVerdict.CONTINUITY_LOST: RetryClass.OPERATOR_REQUIRED,
}


# =============================================================================
# on_attempt — the drift-gate algorithm
# =============================================================================


def on_attempt(
    call_id: str,
    attempt: int,
    current_bundle: PreconditionBundle,
    store: AttemptStore | None = None,
    receipt_system: GateReceiptSystem | None = None,
) -> DriftCheckResult:
    """The drift-gate algorithm.

    Drift verdict is authoritative regardless of receipt emission success.
    Receipt emission is fail-open (best-effort).

    Algorithm:
    1. If attempt == 1 → NO_PRIOR
    2. Fetch prior attempt record from store
    3. If no prior found → NO_PRIOR
    4. Run tiered drift check against stored fingerprint + etags
    5. Emit receipt (best-effort)
    6. Return result
    """
    current_fp = current_bundle.fingerprint()

    # First attempt — no prior to compare against
    if attempt <= 1 or store is None:
        verdict = DriftVerdict.NO_PRIOR
        emission = _try_emit_receipt(
            verdict, call_id, attempt, current_fp, receipt_system,
        )
        return DriftCheckResult(
            verdict=verdict,
            retry_class=_VERDICT_TO_RETRY[verdict],
            prior_fingerprint=None,
            current_fingerprint=current_fp,
            etag_tier_used=False,
            receipt_hash=emission.receipt_hash,
            receipt_emission_ok=emission.ok,
            receipt_emission_error=emission.error,
        )

    # Look up prior attempt
    prior = store.get_prior(call_id, attempt)
    if prior is None:
        verdict = DriftVerdict.NO_PRIOR
        emission = _try_emit_receipt(
            verdict, call_id, attempt, current_fp, receipt_system,
        )
        return DriftCheckResult(
            verdict=verdict,
            retry_class=_VERDICT_TO_RETRY[verdict],
            prior_fingerprint=None,
            current_fingerprint=current_fp,
            etag_tier_used=False,
            receipt_hash=emission.receipt_hash,
            receipt_emission_ok=emission.ok,
            receipt_emission_error=emission.error,
        )

    # Run tiered drift check with stored data
    verdict = drift_check_stored(
        prior.precondition_fingerprint,
        prior.etag_snapshot,
        current_bundle,
    )

    # Determine if etag tier was used
    etag_used = verdict in (DriftVerdict.ETAG_DIVERGED, DriftVerdict.CONTINUITY_LOST)

    emission = _try_emit_receipt(
        verdict, call_id, attempt, current_fp, receipt_system,
    )

    return DriftCheckResult(
        verdict=verdict,
        retry_class=_VERDICT_TO_RETRY[verdict],
        prior_fingerprint=prior.precondition_fingerprint,
        current_fingerprint=current_fp,
        etag_tier_used=etag_used,
        receipt_hash=emission.receipt_hash,
        receipt_emission_ok=emission.ok,
        receipt_emission_error=emission.error,
    )


@dataclass(frozen=True)
class _ReceiptEmissionResult:
    """Internal: result of best-effort receipt emission."""

    receipt_hash: str | None
    ok: bool | None  # None = no receipt system configured
    error: str | None = None


def _try_emit_receipt(
    verdict: DriftVerdict,
    call_id: str,
    attempt: int,
    current_fp: str,
    receipt_system: GateReceiptSystem | None,
) -> _ReceiptEmissionResult:
    """Best-effort receipt emission. Returns structured result."""
    if receipt_system is None:
        return _ReceiptEmissionResult(receipt_hash=None, ok=None)
    try:
        gate_verdict = _VERDICT_TO_GATE[verdict]
        evidence = {
            "call_id": call_id,
            "attempt": attempt,
            "drift_verdict": verdict.value,
            "precondition_fingerprint": current_fp,
        }
        receipt = receipt_system.emit(
            gate=ACTIVITY_DRIFT_GATE,
            verdict=gate_verdict,
            subject_kind="activity_precondition",
            subject_bytes=current_fp.encode("utf-8"),
            evidence_bundle=evidence,
            gate_config={"gate": ACTIVITY_DRIFT_GATE, "version": 1},
        )
        return _ReceiptEmissionResult(receipt_hash=receipt.receipt_id, ok=True)
    except Exception as exc:
        error_str = f"{type(exc).__name__}: {exc}"
        logger.warning("Failed to emit activity_drift receipt: %s", error_str, exc_info=True)
        return _ReceiptEmissionResult(receipt_hash=None, ok=False, error=error_str)


# =============================================================================
# record_attempt — post-execution recording
# =============================================================================


def record_attempt(
    call_id: str,
    attempt: int,
    precondition_bundle: PreconditionBundle,
    outcome: ActivityOutcome,
    retry_class: RetryClass,
    store: AttemptStore,
    error_class: str | None = None,
    error_message: str | None = None,
    receipt_hash: str | None = None,
    idempotency_strategy: IdempotencyStrategy = IdempotencyStrategy.NONE,
) -> AttemptRecord:
    """Record an attempt to the JSONL store."""
    record = AttemptRecord(
        call_id=call_id,
        attempt=attempt,
        precondition_fingerprint=precondition_bundle.fingerprint(),
        etag_snapshot=precondition_bundle.etag_snapshot(),
        outcome=outcome,
        retry_class=retry_class,
        error_class=error_class,
        error_message=error_message,
        receipt_hash=receipt_hash,
        idempotency_strategy=idempotency_strategy,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.append(record)
    return record


# =============================================================================
# AttemptStore — JSONL persistence
# =============================================================================


class AttemptStore:
    """Append-only JSONL store for attempt records.

    Layout: {root}/activity/activity_attempts.jsonl

    Malformed trailing lines are skipped (partial write from crash) with a
    warning so filesystem-level write failures are visible.

    Performance: all queries do a full JSONL scan — O(n) in total records.
    Acceptable for v2 foundation (not wired to production paths). Production
    wiring requires an index or in-memory cache to avoid linear scans.
    """

    def __init__(self, root: Path):
        self.dir = root / "activity"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "activity_attempts.jsonl"

    def append(self, record: AttemptRecord) -> None:
        """Append an attempt record to the log."""
        with open(self.path, "a") as f:
            f.write(record.to_json() + "\n")

    def all(self) -> list[AttemptRecord]:
        """Read all attempt records (oldest first), skipping malformed lines."""
        if not self.path.exists():
            return []
        records: list[AttemptRecord] = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(AttemptRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                # Skip malformed lines (partial write from crash) but warn
                logger.warning(
                    "Skipping malformed attempt record line in %s: %s",
                    self.path, exc,
                )
                continue
        return records

    def get_prior(self, call_id: str, attempt: int) -> AttemptRecord | None:
        """Get the latest record with attempt < N for the given call_id.

        Gap-tolerant: finds the most recent prior, not necessarily attempt-1.
        """
        candidates = [
            r for r in self.all()
            if r.call_id == call_id and r.attempt < attempt
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.attempt)

    def get_latest(self, call_id: str) -> AttemptRecord | None:
        """Get the most recent record for a call_id."""
        candidates = [r for r in self.all() if r.call_id == call_id]
        if not candidates:
            return None
        return max(candidates, key=lambda r: r.attempt)

    def query(self, call_id: str) -> list[AttemptRecord]:
        """All records for a call_id, oldest first."""
        return [r for r in self.all() if r.call_id == call_id]
