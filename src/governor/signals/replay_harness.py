# SPDX-License-Identifier: Apache-2.0
"""
REPLAY_HARNESS — deterministic offline replay of signal derivations.

Replay stored signal/receipt windows under alternative thresholds,
matching rules, or calibration parameters.  Two explicit modes:

  - envelope replay (for layered signals like B1 CAPTURE_SELF_DIAGNOSTIC)
  - receipt replay  (for parallel signals like B2 DECISION_EVIDENCE_LAG)

Key invariants:
  - Observe-only (no policy/gating changes, no mutation of source artifacts)
  - Deterministic (same inputs + same spec → same outputs)
  - Provenance closure (every output carries input hashes + spec hash)
  - Missing ≠ zero preserved through replay

Design authority: specs/gaps/V2_4C_SPINE.md §2
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    canonical_json,
    content_hash,
)

logger = logging.getLogger(__name__)


# ── Config ───────────────────────────────────────────────────────────────────

REPLAY_CONFIG_VERSION = "replay-harness-v1"
MAX_ERROR_MESSAGES = 10
DELTA_EPSILON = 1e-9  # below this, values are "unchanged"


# ── Replay modes ─────────────────────────────────────────────────────────────

MODE_ENVELOPE = "envelope"
MODE_RECEIPT = "receipt"
MODE_MIXED = "mixed"
VALID_MODES = frozenset({MODE_ENVELOPE, MODE_RECEIPT, MODE_MIXED})


# ── Skip reasons ─────────────────────────────────────────────────────────────

SKIP_MISSING_INPUTS = "missing_inputs"
SKIP_SUPPRESSED_EXCLUDED = "suppressed_excluded"
SKIP_QUALITY_FILTERED = "quality_filtered"
SKIP_ALIGNMENT_FAILURE = "alignment_failure"
SKIP_DERIVATION_ERROR = "derivation_error"

ALL_SKIP_REASONS = frozenset({
    SKIP_MISSING_INPUTS,
    SKIP_SUPPRESSED_EXCLUDED,
    SKIP_QUALITY_FILTERED,
    SKIP_ALIGNMENT_FAILURE,
    SKIP_DERIVATION_ERROR,
})


# ── Data models ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReplaySpec:
    """Frozen config object describing one replay run."""

    replay_spec_version: str = REPLAY_CONFIG_VERSION
    replay_run_label: str = ""
    target_signals: tuple[str, ...] = ()
    mode: str = MODE_ENVELOPE
    time_range_start: str | None = None
    time_range_end: str | None = None
    subject_filter: tuple[str, ...] | None = None
    threshold_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    derivation_version_overrides: dict[str, str] = field(default_factory=dict)
    include_quality_statuses: frozenset[str] = field(
        default_factory=lambda: frozenset({"ok", "partial"})
    )
    exclude_classifications: frozenset[str] = field(default_factory=frozenset)
    emit_per_window: bool = False
    emit_summary: bool = True
    notes: str = ""
    operator_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert frozensets to sorted lists for canonical JSON
        d["target_signals"] = sorted(self.target_signals)
        d["include_quality_statuses"] = sorted(self.include_quality_statuses)
        d["exclude_classifications"] = sorted(self.exclude_classifications)
        if self.subject_filter is not None:
            d["subject_filter"] = sorted(self.subject_filter)
        return d

    def spec_hash(self) -> str:
        return content_hash(canonical_json(self.to_dict()))


@dataclass(frozen=True)
class ReplayManifest:
    """Content-addressed inventory of inputs consumed by a replay run."""

    manifest_hash: str
    input_count: int
    input_hashes: tuple[str, ...]  # sorted content hashes
    source_mode: str
    source_path: str | None = None

    @classmethod
    def build(
        cls,
        input_hashes: list[str],
        source_mode: str,
        source_path: str | None = None,
    ) -> ReplayManifest:
        sorted_hashes = tuple(sorted(input_hashes))
        manifest_data = {
            "input_hashes": list(sorted_hashes),
            "source_mode": source_mode,
        }
        mhash = content_hash(canonical_json(manifest_data))
        return cls(
            manifest_hash=mhash,
            input_count=len(sorted_hashes),
            input_hashes=sorted_hashes,
            source_mode=source_mode,
            source_path=source_path,
        )


@dataclass(frozen=True)
class ReplayWindowInput:
    """Input data for one replay window."""

    window_start: str
    window_end: str
    window_kind: str
    signal_id: str
    signal_version: int
    # For envelope mode: signal_id → envelope dict
    envelope_inputs: dict[str, dict[str, Any]] | None = None
    # For receipt mode: receipt record dicts
    receipt_inputs: tuple[dict[str, Any], ...] | None = None
    # Original output for comparison (optional)
    original_output: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReplayWindowResult:
    """Result of replaying one window."""

    window_start: str
    window_end: str
    window_kind: str
    signal_id: str
    replayed: SignalEnvelope | None = None
    original_value: float | None = None
    replayed_value: float | None = None
    original_quality: str | None = None
    replayed_quality: str | None = None
    original_classification: str | None = None
    replayed_classification: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    error_message: str | None = None


# ── Derivation registry ─────────────────────────────────────────────────────

# Type for replay adapter functions:
#   (window_input, threshold_overrides, common_kwargs) → SignalEnvelope
ReplayAdapter = Callable[
    ["ReplayWindowInput", dict[str, Any], dict[str, Any]],
    SignalEnvelope,
]


@dataclass(frozen=True)
class DerivationEntry:
    """Registry entry for a replayable signal derivation."""

    signal_id: str
    signal_version: int
    mode: str  # "envelope" | "receipt"
    replay_fn: ReplayAdapter


def _replay_capture_self_diagnostic(
    window: ReplayWindowInput,
    overrides: dict[str, Any],
    common: dict[str, Any],
) -> SignalEnvelope:
    """Replay adapter for B1 CAPTURE_SELF_DIAGNOSTIC."""
    from .capture_self_diagnostic import DiagnosticInputs, derive_capture_self_diagnostic

    envelopes = window.envelope_inputs or {}
    inputs = DiagnosticInputs(
        a1_exposure_proxy=(
            SignalEnvelope.from_dict(envelopes["EXPOSURE_PROXY"])
            if "EXPOSURE_PROXY" in envelopes else None
        ),
        a2_silent_suppression=(
            SignalEnvelope.from_dict(envelopes["SILENT_SUPPRESSION"])
            if "SILENT_SUPPRESSION" in envelopes else None
        ),
        a3_sigma_rate=(
            SignalEnvelope.from_dict(envelopes["SIGMA_RATE"])
            if "SIGMA_RATE" in envelopes else None
        ),
    )
    return derive_capture_self_diagnostic(
        inputs,
        window.window_start,
        window.window_end,
        window.window_kind,
        emitter=common.get("emitter", "governor.signals.replay_harness"),
        emitter_version=common.get("emitter_version", ""),
        emitted_at=common.get("emitted_at"),
    )


def _replay_decision_evidence_lag(
    window: ReplayWindowInput,
    overrides: dict[str, Any],
    common: dict[str, Any],
) -> SignalEnvelope:
    """Replay adapter for B2 DECISION_EVIDENCE_LAG."""
    from .decision_evidence_lag import ReceiptRecord, derive_decision_evidence_lag

    receipts = [ReceiptRecord(**r) for r in (window.receipt_inputs or ())]

    kwargs: dict[str, Any] = {}
    if "decision_gates" in overrides:
        kwargs["decision_gates"] = frozenset(overrides["decision_gates"])
    if "policy_exempt_gates" in overrides:
        kwargs["policy_exempt_gates"] = frozenset(overrides["policy_exempt_gates"])

    return derive_decision_evidence_lag(
        receipts,
        window.window_start,
        window.window_end,
        window.window_kind,
        **kwargs,
        emitter=common.get("emitter", "governor.signals.replay_harness"),
        emitter_version=common.get("emitter_version", ""),
        emitted_at=common.get("emitted_at"),
    )


DERIVATION_REGISTRY: dict[tuple[str, int], DerivationEntry] = {
    ("CAPTURE_SELF_DIAGNOSTIC", 1): DerivationEntry(
        signal_id="CAPTURE_SELF_DIAGNOSTIC",
        signal_version=1,
        mode=MODE_ENVELOPE,
        replay_fn=_replay_capture_self_diagnostic,
    ),
    ("DECISION_EVIDENCE_LAG", 1): DerivationEntry(
        signal_id="DECISION_EVIDENCE_LAG",
        signal_version=1,
        mode=MODE_RECEIPT,
        replay_fn=_replay_decision_evidence_lag,
    ),
}


# ── Replay orchestrator ─────────────────────────────────────────────────────

def _extract_classification(env_dict: dict[str, Any]) -> str | None:
    """Extract classification label from an envelope's values dict."""
    values = env_dict.get("values", {})
    return values.get("classification")


def _should_skip_window(
    window: ReplayWindowInput,
    spec: ReplaySpec,
) -> str | None:
    """Check if a window should be skipped. Returns skip reason or None."""
    orig = window.original_output
    if orig is None:
        return None  # No original to filter on

    # Quality filter
    quality = orig.get("quality_status", "")
    if quality and quality not in spec.include_quality_statuses:
        return SKIP_QUALITY_FILTERED

    # Classification exclusion
    classification = _extract_classification(orig)
    if classification and classification in spec.exclude_classifications:
        return SKIP_SUPPRESSED_EXCLUDED

    return None


def _has_required_inputs(window: ReplayWindowInput, entry: DerivationEntry) -> bool:
    """Check if window has minimum required inputs for derivation."""
    if entry.mode == MODE_ENVELOPE:
        return window.envelope_inputs is not None and len(window.envelope_inputs) > 0
    elif entry.mode == MODE_RECEIPT:
        return window.receipt_inputs is not None
    return False


def _add_replay_annotations(
    env: SignalEnvelope,
    replay_run_id: str,
    source_hash: str | None,
    threshold_overrides: dict[str, Any],
) -> SignalEnvelope:
    """Add replay provenance annotations to an envelope."""
    annotations = dict(env.annotations)
    annotations["replay_run_id"] = replay_run_id
    annotations["source_signal_hash"] = source_hash
    if threshold_overrides:
        annotations["threshold_overrides"] = threshold_overrides

    # Replace phase with 2.4C
    return SignalEnvelope(
        schema_version=env.schema_version,
        emitted_at=env.emitted_at,
        emitter=env.emitter,
        emitter_version=env.emitter_version,
        signal_id=env.signal_id,
        signal_version=env.signal_version,
        phase="2.4C",
        subject_type=env.subject_type,
        subject_id=env.subject_id,
        correlation_id=env.correlation_id,
        session_id=env.session_id,
        window_start=env.window_start,
        window_end=env.window_end,
        window_kind=env.window_kind,
        value=env.value,
        unit=env.unit,
        values=env.values,
        quality_status=env.quality_status,
        quality_reasons=env.quality_reasons,
        sample_size=env.sample_size,
        completeness=env.completeness,
        source_receipt_ids=env.source_receipt_ids,
        source_streams=env.source_streams,
        source_versions=env.source_versions,
        derivation=env.derivation,
        derivation_version=env.derivation_version,
        annotations=annotations,
    )


def replay_windows(
    windows: list[ReplayWindowInput],
    spec: ReplaySpec,
    *,
    emitter: str = "governor.signals.replay_harness",
    emitter_version: str = "",
    emitted_at: str | None = None,
    replay_run_id: str | None = None,
) -> tuple[list[ReplayWindowResult], list[SignalEnvelope]]:
    """Replay derivations for a list of windows.

    Returns (results, per_window_envelopes).
    per_window_envelopes is populated only if spec.emit_per_window is True.
    """
    if replay_run_id is None:
        replay_run_id = hashlib.sha256(
            (spec.spec_hash() + (emitted_at or "")).encode()
        ).hexdigest()[:16]

    common = {
        "emitter": emitter,
        "emitter_version": emitter_version,
        "emitted_at": emitted_at,
    }

    # Sort windows deterministically: (window_start, signal_id)
    sorted_windows = sorted(windows, key=lambda w: (w.window_start, w.signal_id))

    results: list[ReplayWindowResult] = []
    per_window: list[SignalEnvelope] = []

    for window in sorted_windows:
        key = (window.signal_id, window.signal_version)
        entry = DERIVATION_REGISTRY.get(key)

        if entry is None:
            results.append(ReplayWindowResult(
                window_start=window.window_start,
                window_end=window.window_end,
                window_kind=window.window_kind,
                signal_id=window.signal_id,
                skipped=True,
                skip_reason=SKIP_MISSING_INPUTS,
                error_message=f"No registry entry for ({window.signal_id}, {window.signal_version})",
            ))
            continue

        # Check skip conditions
        skip_reason = _should_skip_window(window, spec)
        if skip_reason:
            orig = window.original_output or {}
            results.append(ReplayWindowResult(
                window_start=window.window_start,
                window_end=window.window_end,
                window_kind=window.window_kind,
                signal_id=window.signal_id,
                original_value=orig.get("value"),
                original_quality=orig.get("quality_status"),
                original_classification=_extract_classification(orig),
                skipped=True,
                skip_reason=skip_reason,
            ))
            continue

        # Check inputs
        if not _has_required_inputs(window, entry):
            results.append(ReplayWindowResult(
                window_start=window.window_start,
                window_end=window.window_end,
                window_kind=window.window_kind,
                signal_id=window.signal_id,
                skipped=True,
                skip_reason=SKIP_MISSING_INPUTS,
            ))
            continue

        # Run derivation
        overrides = spec.threshold_overrides.get(window.signal_id, {})
        try:
            replayed_env = entry.replay_fn(window, overrides, common)
        except Exception as exc:
            logger.warning(
                "Derivation error for %s at %s: %s",
                window.signal_id, window.window_start, exc,
            )
            results.append(ReplayWindowResult(
                window_start=window.window_start,
                window_end=window.window_end,
                window_kind=window.window_kind,
                signal_id=window.signal_id,
                skipped=True,
                skip_reason=SKIP_DERIVATION_ERROR,
                error_message=str(exc)[:500],
            ))
            continue

        # Compute source hash for provenance
        source_hash: str | None = None
        if window.original_output:
            source_hash = content_hash(canonical_json(window.original_output))

        # Add replay annotations
        replayed_env = _add_replay_annotations(
            replayed_env, replay_run_id, source_hash, overrides,
        )

        # Extract comparison values
        orig = window.original_output or {}
        orig_class = _extract_classification(orig)
        replayed_class = _extract_classification(replayed_env.to_dict())

        result = ReplayWindowResult(
            window_start=window.window_start,
            window_end=window.window_end,
            window_kind=window.window_kind,
            signal_id=window.signal_id,
            replayed=replayed_env,
            original_value=orig.get("value"),
            replayed_value=replayed_env.value,
            original_quality=orig.get("quality_status"),
            replayed_quality=replayed_env.quality_status,
            original_classification=orig_class,
            replayed_classification=replayed_class,
        )
        results.append(result)

        if spec.emit_per_window:
            per_window.append(replayed_env)

    return results, per_window


# ── Summary envelope ─────────────────────────────────────────────────────────

def _compute_p95(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(int(0.95 * len(s) + 0.5), len(s) - 1)
    return s[idx]


def replay_summary_envelope(
    results: list[ReplayWindowResult],
    spec: ReplaySpec,
    manifest: ReplayManifest,
    *,
    emitter: str = "governor.signals.replay_harness",
    emitter_version: str = "",
    emitted_at: str | None = None,
    replay_run_id: str | None = None,
) -> SignalEnvelope:
    """Build the REPLAY_HARNESS summary SignalEnvelope."""
    total = len(results)
    skipped = [r for r in results if r.skipped]
    replayed = [r for r in results if not r.skipped]

    # Skip reason counts
    skip_reasons: dict[str, int] = {}
    for r in skipped:
        reason = r.skip_reason or "unknown"
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    # Drift statistics (only where both original and replayed values exist)
    deltas: list[float] = []
    classification_changes = 0
    quality_changes = 0
    value_increase = 0
    value_decrease = 0
    value_unchanged = 0
    derivation_error_count = skip_reasons.get(SKIP_DERIVATION_ERROR, 0)

    for r in replayed:
        if r.original_value is not None and r.replayed_value is not None:
            delta = abs(r.replayed_value - r.original_value)
            deltas.append(delta)
            if delta < DELTA_EPSILON:
                value_unchanged += 1
            elif r.replayed_value > r.original_value:
                value_increase += 1
            else:
                value_decrease += 1

        if (r.original_classification is not None
                and r.replayed_classification is not None
                and r.original_classification != r.replayed_classification):
            classification_changes += 1

        if (r.original_quality is not None
                and r.replayed_quality is not None
                and r.original_quality != r.replayed_quality):
            quality_changes += 1

    mean_delta = sum(deltas) / len(deltas) if deltas else None
    p95_delta = _compute_p95(deltas)
    max_delta = max(deltas) if deltas else None

    # Collect error messages (first N)
    error_messages: list[str] = []
    for r in skipped:
        if r.skip_reason == SKIP_DERIVATION_ERROR and r.error_message:
            if len(error_messages) < MAX_ERROR_MESSAGES:
                error_messages.append(r.error_message)

    values: dict[str, Any] = {
        "window_count_total": total,
        "window_count_replayed": len(replayed),
        "window_count_skipped": len(skipped),
        "skip_reasons": skip_reasons,
        "mean_abs_delta": mean_delta,
        "p95_abs_delta": p95_delta,
        "max_abs_delta": max_delta,
        "classification_change_count": classification_changes,
        "quality_status_change_count": quality_changes,
        "value_increase_count": value_increase,
        "value_decrease_count": value_decrease,
        "value_unchanged_count": value_unchanged,
        "source_mode": spec.mode,
        "target_signals": sorted(spec.target_signals),
        "target_signal_count": len(spec.target_signals),
        "derivation_error_count": derivation_error_count,
        "config_version": REPLAY_CONFIG_VERSION,
    }

    annotations: dict[str, Any] = {
        "config_version": REPLAY_CONFIG_VERSION,
        "replay_spec_hash": spec.spec_hash(),
        "manifest_hash": manifest.manifest_hash,
        "threshold_overrides": spec.threshold_overrides,
        "derivation_version_overrides": spec.derivation_version_overrides,
        "include_quality_statuses": sorted(spec.include_quality_statuses),
        "exclude_classifications": sorted(spec.exclude_classifications),
        "derivation_errors": error_messages,
    }

    if replay_run_id:
        annotations["replay_run_id"] = replay_run_id

    # Primary value: mean_abs_delta if available (drift score), else None
    primary_value = mean_delta

    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=emitted_at or datetime.now(timezone.utc).isoformat(),
        emitter=emitter,
        emitter_version=emitter_version,
        signal_id="REPLAY_HARNESS",
        signal_version=1,
        phase="2.4C",
        subject_type="replay_run",
        subject_id=f"replay_{manifest.manifest_hash[:12]}",
        session_id=None,
        window_start=None,
        window_end=None,
        window_kind=None,
        value=primary_value,
        unit="score" if primary_value is not None else None,
        values=values,
        quality_status=(
            QualityStatus.OK.value if len(replayed) > 0
            else QualityStatus.UNAVAILABLE.value
        ),
        quality_reasons=(
            ["no_windows_replayed"] if len(replayed) == 0 else []
        ),
        sample_size=len(replayed) if len(replayed) > 0 else None,
        completeness=(
            len(replayed) / total if total > 0 else None
        ),
        source_receipt_ids=[],
        source_streams=sorted(spec.target_signals),
        source_versions={},
        derivation=DerivationType.DERIVED.value,
        derivation_version=REPLAY_CONFIG_VERSION,
        annotations=annotations,
    )
