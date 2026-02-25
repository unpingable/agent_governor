# SPDX-License-Identifier: Apache-2.0
"""Tests for REPLAY_HARNESS (Phase C1) and replay_sources."""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from governor.signals.envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    canonical_json,
    content_hash,
    validate_envelope,
)
from governor.signals.replay_harness import (
    ALL_SKIP_REASONS,
    DELTA_EPSILON,
    DERIVATION_REGISTRY,
    MAX_ERROR_MESSAGES,
    MODE_ENVELOPE,
    MODE_MIXED,
    MODE_RECEIPT,
    REPLAY_CONFIG_VERSION,
    SKIP_ALIGNMENT_FAILURE,
    SKIP_DERIVATION_ERROR,
    SKIP_MISSING_INPUTS,
    SKIP_QUALITY_FILTERED,
    SKIP_SUPPRESSED_EXCLUDED,
    VALID_MODES,
    DerivationEntry,
    ReplayManifest,
    ReplaySpec,
    ReplayWindowInput,
    ReplayWindowResult,
    _add_replay_annotations,
    _compute_p95,
    _extract_classification,
    _has_required_inputs,
    _should_skip_window,
    replay_summary_envelope,
    replay_windows,
)
from governor.signals.replay_sources import (
    prepare_envelope_windows,
    prepare_receipt_windows,
)


# ── Shared test constants ─────────────────────────────────────────────────

WINDOW_START = "2026-02-25T10:00:00Z"
WINDOW_END = "2026-02-25T10:05:00Z"
WINDOW_KIND = "rolling_5m"
EMITTED_AT = "2026-02-25T10:05:00Z"
FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "signals"


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_a_signal(
    signal_id: str,
    value: float | None = 1.0,
    quality_status: str = "ok",
    classification: str | None = None,
    window_start: str = WINDOW_START,
    window_end: str = WINDOW_END,
    window_kind: str = WINDOW_KIND,
) -> SignalEnvelope:
    """Build a minimal A-signal envelope for test use."""
    values: dict = {"test_value": value or 0.0}
    if classification:
        values["classification"] = classification
    return SignalEnvelope(
        schema_version=CURRENT_SCHEMA_VERSION,
        emitted_at=EMITTED_AT,
        emitter=f"governor.signals.{signal_id.lower()}",
        emitter_version="test",
        signal_id=signal_id,
        signal_version=1,
        phase="2.4A",
        subject_type="window",
        subject_id=f"test_{window_start}_{window_kind}",
        session_id=None,
        window_start=window_start,
        window_end=window_end,
        window_kind=window_kind,
        value=value,
        unit="score",
        values=values,
        quality_status=quality_status,
        quality_reasons=[],
        sample_size=10,
        completeness=1.0,
        source_receipt_ids=[],
        source_streams=[],
        source_versions={},
        derivation=DerivationType.WINDOWED_AGGREGATE.value,
        derivation_version="test-v1",
    )


def _make_b1_inputs() -> dict[str, dict]:
    """Build envelope_inputs dict for B1 replay (A1+A2+A3 as dicts)."""
    a1 = _make_a_signal("EXPOSURE_PROXY", value=10.0)
    a2 = _make_a_signal("SILENT_SUPPRESSION", value=1.0)
    a3 = _make_a_signal("SIGMA_RATE", value=0.0)

    # Override A1 to have required fields
    a1_dict = a1.to_dict()
    a1_dict["values"] = {
        "exposure_points_total": 10.0,
        "eligible_events": 10,
        "excluded_events": 0,
        "weighted_event_count": 10.0,
        "coverage_ratio": 1.0,
        "source_event_count": 10,
    }
    a1_dict["unit"] = "exposure_points"

    # A2 needs suppression classification
    a2_dict = a2.to_dict()
    a2_dict["values"] = {
        "expected_heartbeat_count": 5,
        "observed_heartbeat_count": 5,
        "expected_event_markers": 3,
        "observed_event_markers": 3,
        "daemon_reachable": 1,
        "in_path_evidence_present": 1,
        "activity_observed": 1,
        "suppression_detected": 0,
    }
    a2_dict["unit"] = "ratio"

    # A3 needs sigma_rate fields
    a3_dict = a3.to_dict()
    a3_dict["values"] = {
        "sigma_rate": 0.0,
        "endorsement_count": 5,
        "invalidation_count": 5,
        "matched_pair_count": 5,
        "invalid_pair_count": 0,
    }
    a3_dict["unit"] = "rate"

    return {
        "EXPOSURE_PROXY": a1_dict,
        "SILENT_SUPPRESSION": a2_dict,
        "SIGMA_RATE": a3_dict,
    }


def _make_receipt_record(
    gate: str = "evidence_gate",
    verdict: str = "pass",
    timestamp: str = "2026-02-25T10:02:00Z",
) -> dict:
    """Build a minimal receipt record dict for B2 replay.

    ReceiptRecord has exactly 5 fields: receipt_id, timestamp, gate, verdict, subject_hash.
    """
    return {
        "receipt_id": f"r_{gate}_{timestamp}",
        "timestamp": timestamp,
        "gate": gate,
        "verdict": verdict,
        "subject_hash": "sha256:abc123",
    }


# ── Test classes ───────────────────────────────────────────────────────────


class TestConstants:
    """Config constants and enums."""

    def test_replay_config_version_format(self):
        assert REPLAY_CONFIG_VERSION == "replay-harness-v1"

    def test_valid_modes(self):
        assert VALID_MODES == {"envelope", "receipt", "mixed"}

    def test_all_skip_reasons_count(self):
        assert len(ALL_SKIP_REASONS) == 5

    def test_skip_reason_values(self):
        assert SKIP_MISSING_INPUTS == "missing_inputs"
        assert SKIP_SUPPRESSED_EXCLUDED == "suppressed_excluded"
        assert SKIP_QUALITY_FILTERED == "quality_filtered"
        assert SKIP_ALIGNMENT_FAILURE == "alignment_failure"
        assert SKIP_DERIVATION_ERROR == "derivation_error"

    def test_max_error_messages(self):
        assert MAX_ERROR_MESSAGES == 10

    def test_delta_epsilon(self):
        assert DELTA_EPSILON < 1e-6


class TestReplaySpec:
    """ReplaySpec dataclass + hashing."""

    def test_default_values(self):
        spec = ReplaySpec()
        assert spec.replay_spec_version == REPLAY_CONFIG_VERSION
        assert spec.mode == MODE_ENVELOPE
        assert spec.target_signals == ()
        assert spec.emit_per_window is False
        assert spec.emit_summary is True

    def test_to_dict_sorted(self):
        spec = ReplaySpec(target_signals=("B", "A", "C"))
        d = spec.to_dict()
        assert d["target_signals"] == ["A", "B", "C"]

    def test_to_dict_frozenset_conversion(self):
        spec = ReplaySpec(
            include_quality_statuses=frozenset({"partial", "ok"}),
            exclude_classifications=frozenset({"warning", "normal"}),
        )
        d = spec.to_dict()
        assert d["include_quality_statuses"] == ["ok", "partial"]
        assert d["exclude_classifications"] == ["normal", "warning"]

    def test_spec_hash_deterministic(self):
        spec = ReplaySpec(target_signals=("A", "B"))
        h1 = spec.spec_hash()
        h2 = spec.spec_hash()
        assert h1 == h2

    def test_spec_hash_changes_with_params(self):
        s1 = ReplaySpec(target_signals=("A",))
        s2 = ReplaySpec(target_signals=("B",))
        assert s1.spec_hash() != s2.spec_hash()

    def test_spec_hash_format(self):
        spec = ReplaySpec()
        assert spec.spec_hash().startswith("sha256:")

    def test_frozen(self):
        spec = ReplaySpec()
        with pytest.raises(AttributeError):
            spec.mode = "receipt"  # type: ignore[misc]


class TestReplayManifest:
    """ReplayManifest content-addressed inventory."""

    def test_build_basic(self):
        m = ReplayManifest.build(["h1", "h2", "h3"], source_mode="envelope")
        assert m.input_count == 3
        assert m.source_mode == "envelope"
        assert m.manifest_hash.startswith("sha256:")

    def test_build_sorts_hashes(self):
        m = ReplayManifest.build(["h3", "h1", "h2"], source_mode="envelope")
        assert m.input_hashes == ("h1", "h2", "h3")

    def test_manifest_hash_order_independent(self):
        """Manifest hash must not depend on input traversal order."""
        m1 = ReplayManifest.build(["h1", "h2", "h3"], source_mode="envelope")
        m2 = ReplayManifest.build(["h3", "h1", "h2"], source_mode="envelope")
        m3 = ReplayManifest.build(["h2", "h3", "h1"], source_mode="envelope")
        assert m1.manifest_hash == m2.manifest_hash == m3.manifest_hash

    def test_manifest_hash_changes_with_inputs(self):
        m1 = ReplayManifest.build(["h1", "h2"], source_mode="envelope")
        m2 = ReplayManifest.build(["h1", "h3"], source_mode="envelope")
        assert m1.manifest_hash != m2.manifest_hash

    def test_manifest_hash_changes_with_mode(self):
        m1 = ReplayManifest.build(["h1"], source_mode="envelope")
        m2 = ReplayManifest.build(["h1"], source_mode="receipt")
        assert m1.manifest_hash != m2.manifest_hash

    def test_empty_manifest(self):
        m = ReplayManifest.build([], source_mode="envelope")
        assert m.input_count == 0
        assert m.input_hashes == ()
        assert m.manifest_hash.startswith("sha256:")

    def test_source_path_preserved(self):
        m = ReplayManifest.build(["h1"], source_mode="envelope", source_path="/tmp/test.jsonl")
        assert m.source_path == "/tmp/test.jsonl"

    def test_duplicate_hashes_preserved(self):
        """Duplicates are preserved in sorted order (caller dedupes if needed)."""
        m = ReplayManifest.build(["h1", "h1", "h2"], source_mode="envelope")
        assert m.input_count == 3
        assert m.input_hashes == ("h1", "h1", "h2")


class TestDerivationRegistry:
    """Registry keying and lookup."""

    def test_registry_has_b1(self):
        assert ("CAPTURE_SELF_DIAGNOSTIC", 1) in DERIVATION_REGISTRY

    def test_registry_has_b2(self):
        assert ("DECISION_EVIDENCE_LAG", 1) in DERIVATION_REGISTRY

    def test_b1_entry_mode_is_envelope(self):
        entry = DERIVATION_REGISTRY[("CAPTURE_SELF_DIAGNOSTIC", 1)]
        assert entry.mode == MODE_ENVELOPE

    def test_b2_entry_mode_is_receipt(self):
        entry = DERIVATION_REGISTRY[("DECISION_EVIDENCE_LAG", 1)]
        assert entry.mode == MODE_RECEIPT

    def test_unknown_signal_not_in_registry(self):
        assert ("UNKNOWN_SIGNAL", 1) not in DERIVATION_REGISTRY

    def test_wrong_version_not_in_registry(self):
        assert ("CAPTURE_SELF_DIAGNOSTIC", 99) not in DERIVATION_REGISTRY

    def test_entry_fields(self):
        entry = DERIVATION_REGISTRY[("CAPTURE_SELF_DIAGNOSTIC", 1)]
        assert entry.signal_id == "CAPTURE_SELF_DIAGNOSTIC"
        assert entry.signal_version == 1
        assert callable(entry.replay_fn)


class TestSkipLogic:
    """Window skip conditions."""

    def test_no_original_never_skips(self):
        """Windows without originals cannot be filtered."""
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
        )
        spec = ReplaySpec(include_quality_statuses=frozenset({"ok"}))
        assert _should_skip_window(window, spec) is None

    def test_quality_filter_skips_unavailable(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
            original_output={"quality_status": "unavailable"},
        )
        spec = ReplaySpec(include_quality_statuses=frozenset({"ok", "partial"}))
        assert _should_skip_window(window, spec) == SKIP_QUALITY_FILTERED

    def test_quality_filter_passes_ok(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
            original_output={"quality_status": "ok"},
        )
        spec = ReplaySpec(include_quality_statuses=frozenset({"ok"}))
        assert _should_skip_window(window, spec) is None

    def test_classification_exclusion(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
            original_output={
                "quality_status": "ok",
                "values": {"classification": "warning"},
            },
        )
        spec = ReplaySpec(exclude_classifications=frozenset({"warning"}))
        assert _should_skip_window(window, spec) == SKIP_SUPPRESSED_EXCLUDED

    def test_classification_not_excluded(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
            original_output={
                "quality_status": "ok",
                "values": {"classification": "normal"},
            },
        )
        spec = ReplaySpec(exclude_classifications=frozenset({"warning"}))
        assert _should_skip_window(window, spec) is None


class TestInputRequirements:
    """Required inputs check."""

    def test_envelope_mode_needs_inputs(self):
        entry = DerivationEntry("TEST", 1, MODE_ENVELOPE, lambda w, o, c: None)  # type: ignore[arg-type]
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
        )
        assert not _has_required_inputs(window, entry)

    def test_envelope_mode_empty_dict_fails(self):
        entry = DerivationEntry("TEST", 1, MODE_ENVELOPE, lambda w, o, c: None)  # type: ignore[arg-type]
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
            envelope_inputs={},
        )
        assert not _has_required_inputs(window, entry)

    def test_envelope_mode_with_inputs_passes(self):
        entry = DerivationEntry("TEST", 1, MODE_ENVELOPE, lambda w, o, c: None)  # type: ignore[arg-type]
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
            envelope_inputs={"A1": {}},
        )
        assert _has_required_inputs(window, entry)

    def test_receipt_mode_none_fails(self):
        entry = DerivationEntry("TEST", 1, MODE_RECEIPT, lambda w, o, c: None)  # type: ignore[arg-type]
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
        )
        assert not _has_required_inputs(window, entry)

    def test_receipt_mode_empty_tuple_passes(self):
        """Empty receipt list is valid — B2 handles zero-receipt windows."""
        entry = DerivationEntry("TEST", 1, MODE_RECEIPT, lambda w, o, c: None)  # type: ignore[arg-type]
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            signal_version=1,
            receipt_inputs=(),
        )
        assert _has_required_inputs(window, entry)


class TestEnvelopeReplayPath:
    """B1 CAPTURE_SELF_DIAGNOSTIC replay via envelope inputs."""

    def test_b1_replay_produces_envelope(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(
            target_signals=("CAPTURE_SELF_DIAGNOSTIC",),
            mode=MODE_ENVELOPE,
        )
        results, per_window = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b1",
        )
        assert len(results) == 1
        r = results[0]
        assert not r.skipped
        assert r.replayed is not None

    def test_b1_replay_signal_id_preserved(self):
        """Per-window output keeps original signal_id (not REPLAYED_ prefix)."""
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(
            target_signals=("CAPTURE_SELF_DIAGNOSTIC",),
            mode=MODE_ENVELOPE,
        )
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b1",
        )
        env = results[0].replayed
        assert env is not None
        assert env.signal_id == "CAPTURE_SELF_DIAGNOSTIC"

    def test_b1_replay_phase_is_2_4c(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b1",
        )
        assert results[0].replayed.phase == "2.4C"

    def test_b1_replay_has_replay_annotations(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-run-42",
        )
        env = results[0].replayed
        assert env.annotations["replay_run_id"] == "test-run-42"

    def test_b1_replay_classification_in_result(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b1",
        )
        assert results[0].replayed_classification is not None

    def test_b1_envelope_passes_validation(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec,
            emitted_at=EMITTED_AT, replay_run_id="test-b1",
            emitter_version="2.4.0-test",
        )
        env = results[0].replayed
        assert validate_envelope(env) == []


class TestReceiptReplayPath:
    """B2 DECISION_EVIDENCE_LAG replay via receipt inputs."""

    def _make_receipt_window(
        self,
        receipts: tuple[dict, ...] | None = None,
        original: dict | None = None,
    ) -> ReplayWindowInput:
        if receipts is None:
            receipts = (
                _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:01:00Z"),
                _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:02:00Z"),
                _make_receipt_record("evidence_gate", "warn", "2026-02-25T10:03:00Z"),
            )
        return ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="DECISION_EVIDENCE_LAG",
            signal_version=1,
            receipt_inputs=receipts,
            original_output=original,
        )

    def test_b2_replay_produces_envelope(self):
        window = self._make_receipt_window()
        spec = ReplaySpec(
            target_signals=("DECISION_EVIDENCE_LAG",),
            mode=MODE_RECEIPT,
        )
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b2",
        )
        assert len(results) == 1
        assert not results[0].skipped
        assert results[0].replayed is not None

    def test_b2_replay_signal_id_preserved(self):
        window = self._make_receipt_window()
        spec = ReplaySpec(
            target_signals=("DECISION_EVIDENCE_LAG",),
            mode=MODE_RECEIPT,
        )
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b2",
        )
        assert results[0].replayed.signal_id == "DECISION_EVIDENCE_LAG"

    def test_b2_replay_phase_is_2_4c(self):
        window = self._make_receipt_window()
        spec = ReplaySpec(target_signals=("DECISION_EVIDENCE_LAG",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b2",
        )
        assert results[0].replayed.phase == "2.4C"

    def test_b2_replay_with_gate_overrides(self):
        window = self._make_receipt_window()
        spec = ReplaySpec(
            target_signals=("DECISION_EVIDENCE_LAG",),
            threshold_overrides={
                "DECISION_EVIDENCE_LAG": {
                    "decision_gates": ["evidence_gate"],
                },
            },
        )
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b2",
        )
        assert not results[0].skipped

    def test_b2_replay_empty_receipts(self):
        """Empty receipt window → value=None, quality=unavailable."""
        window = self._make_receipt_window(receipts=())
        spec = ReplaySpec(target_signals=("DECISION_EVIDENCE_LAG",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="test-b2",
        )
        env = results[0].replayed
        assert env is not None
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value

    def test_b2_envelope_passes_validation(self):
        window = self._make_receipt_window()
        spec = ReplaySpec(target_signals=("DECISION_EVIDENCE_LAG",))
        results, _ = replay_windows(
            [window], spec,
            emitted_at=EMITTED_AT, replay_run_id="test-b2",
            emitter_version="2.4.0-test",
        )
        env = results[0].replayed
        assert validate_envelope(env) == []


class TestReplayProvenance:
    """Replay annotations and provenance closure."""

    def test_replay_annotations_present(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
            original_output={"signal_id": "CAPTURE_SELF_DIAGNOSTIC", "value": 0.0},
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="run-xyz",
        )
        ann = results[0].replayed.annotations
        assert ann["replay_run_id"] == "run-xyz"
        assert "source_signal_hash" in ann

    def test_source_hash_none_when_no_original(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
            # No original_output
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="run-abc",
        )
        ann = results[0].replayed.annotations
        assert ann["source_signal_hash"] is None

    def test_threshold_overrides_in_annotations(self):
        receipts = (
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:02:00Z"),
        )
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="DECISION_EVIDENCE_LAG",
            signal_version=1,
            receipt_inputs=receipts,
        )
        overrides = {"DECISION_EVIDENCE_LAG": {"decision_gates": ["evidence_gate"]}}
        spec = ReplaySpec(
            target_signals=("DECISION_EVIDENCE_LAG",),
            threshold_overrides=overrides,
        )
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="run-ov",
        )
        ann = results[0].replayed.annotations
        assert ann["threshold_overrides"] == {"decision_gates": ["evidence_gate"]}

    def test_no_overrides_empty_in_annotations(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="run-no-ov",
        )
        ann = results[0].replayed.annotations
        # Empty overrides → not added to annotations
        assert "threshold_overrides" not in ann


class TestRegistryDispatch:
    """Registry dispatch and unknown signal handling."""

    def test_unknown_signal_skipped(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="UNKNOWN_SIGNAL",
            signal_version=1,
            envelope_inputs={"A1": {}},
        )
        spec = ReplaySpec(target_signals=("UNKNOWN_SIGNAL",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT,
        )
        assert len(results) == 1
        assert results[0].skipped
        assert results[0].skip_reason == SKIP_MISSING_INPUTS
        assert "No registry entry" in results[0].error_message

    def test_wrong_version_skipped(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=99,
            envelope_inputs=_make_b1_inputs(),
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT,
        )
        assert results[0].skipped
        assert "No registry entry" in results[0].error_message


class TestSkipReasonCounting:
    """All 5 skip reason types covered."""

    def test_missing_inputs_counted(self):
        """No envelope_inputs, no receipt_inputs → missing_inputs."""
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            # No envelope_inputs
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows([window], spec, emitted_at=EMITTED_AT)
        assert results[0].skip_reason == SKIP_MISSING_INPUTS

    def test_quality_filtered_counted(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=_make_b1_inputs(),
            original_output={"quality_status": "unavailable"},
        )
        spec = ReplaySpec(
            target_signals=("CAPTURE_SELF_DIAGNOSTIC",),
            include_quality_statuses=frozenset({"ok"}),
        )
        results, _ = replay_windows([window], spec, emitted_at=EMITTED_AT)
        assert results[0].skip_reason == SKIP_QUALITY_FILTERED

    def test_suppressed_excluded_counted(self):
        window = ReplayWindowInput(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="CAPTURE_SELF_DIAGNOSTIC",
            signal_version=1,
            envelope_inputs=_make_b1_inputs(),
            original_output={
                "quality_status": "ok",
                "values": {"classification": "warning"},
            },
        )
        spec = ReplaySpec(
            target_signals=("CAPTURE_SELF_DIAGNOSTIC",),
            exclude_classifications=frozenset({"warning"}),
        )
        results, _ = replay_windows([window], spec, emitted_at=EMITTED_AT)
        assert results[0].skip_reason == SKIP_SUPPRESSED_EXCLUDED

    def test_derivation_error_counted(self):
        """Derivation function raises → derivation_error."""
        def _bad_fn(w, o, c):
            raise ValueError("intentional test error")

        # Temporarily inject a bad entry
        key = ("BAD_SIGNAL", 1)
        DERIVATION_REGISTRY[key] = DerivationEntry(
            signal_id="BAD_SIGNAL",
            signal_version=1,
            mode=MODE_ENVELOPE,
            replay_fn=_bad_fn,
        )
        try:
            window = ReplayWindowInput(
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                window_kind=WINDOW_KIND,
                signal_id="BAD_SIGNAL",
                signal_version=1,
                envelope_inputs={"INPUT": {}},
            )
            spec = ReplaySpec(target_signals=("BAD_SIGNAL",))
            results, _ = replay_windows([window], spec, emitted_at=EMITTED_AT)
            assert results[0].skip_reason == SKIP_DERIVATION_ERROR
            assert "intentional test error" in results[0].error_message
        finally:
            del DERIVATION_REGISTRY[key]

    def test_all_skip_reasons_in_summary(self):
        """Summary envelope counts all skip reasons correctly."""
        results = [
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "A",
                               skipped=True, skip_reason=SKIP_MISSING_INPUTS),
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "B",
                               skipped=True, skip_reason=SKIP_QUALITY_FILTERED),
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "C",
                               skipped=True, skip_reason=SKIP_SUPPRESSED_EXCLUDED),
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "D",
                               skipped=True, skip_reason=SKIP_ALIGNMENT_FAILURE),
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "E",
                               skipped=True, skip_reason=SKIP_DERIVATION_ERROR,
                               error_message="oops"),
        ]
        spec = ReplaySpec(target_signals=("A", "B", "C", "D", "E"))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        reasons = summary.values["skip_reasons"]
        assert reasons[SKIP_MISSING_INPUTS] == 1
        assert reasons[SKIP_QUALITY_FILTERED] == 1
        assert reasons[SKIP_SUPPRESSED_EXCLUDED] == 1
        assert reasons[SKIP_ALIGNMENT_FAILURE] == 1
        assert reasons[SKIP_DERIVATION_ERROR] == 1


class TestDeterministicOrdering:
    """Windows processed in (window_start, signal_id) order."""

    def test_windows_sorted_by_start_then_signal(self):
        """Output order follows (window_start, signal_id) regardless of input order."""
        w1 = ReplayWindowInput("2026-02-25T10:05:00Z", "2026-02-25T10:10:00Z",
                               WINDOW_KIND, "CAPTURE_SELF_DIAGNOSTIC", 1,
                               envelope_inputs=_make_b1_inputs())
        w2 = ReplayWindowInput(WINDOW_START, WINDOW_END,
                               WINDOW_KIND, "CAPTURE_SELF_DIAGNOSTIC", 1,
                               envelope_inputs=_make_b1_inputs())
        # Input order: w1 (later) before w2 (earlier)
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [w1, w2], spec, emitted_at=EMITTED_AT, replay_run_id="order-test",
        )
        assert results[0].window_start == WINDOW_START
        assert results[1].window_start == "2026-02-25T10:05:00Z"

    def test_same_window_different_signals_sorted(self):
        """Same window, two signals: sorted by signal_id."""
        w_b2 = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "DECISION_EVIDENCE_LAG", 1,
            receipt_inputs=(_make_receipt_record(),),
        )
        w_b1 = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=_make_b1_inputs(),
        )
        spec = ReplaySpec(
            target_signals=("CAPTURE_SELF_DIAGNOSTIC", "DECISION_EVIDENCE_LAG"),
        )
        # Input order: B2 before B1
        results, _ = replay_windows(
            [w_b2, w_b1], spec, emitted_at=EMITTED_AT, replay_run_id="multi-sig",
        )
        assert results[0].signal_id == "CAPTURE_SELF_DIAGNOSTIC"
        assert results[1].signal_id == "DECISION_EVIDENCE_LAG"


class TestPerWindowEmission:
    """emit_per_window flag controls envelope output."""

    def test_per_window_off_by_default(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        _, per_window = replay_windows(
            [window], spec, emitted_at=EMITTED_AT,
        )
        assert len(per_window) == 0

    def test_per_window_on(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(
            target_signals=("CAPTURE_SELF_DIAGNOSTIC",),
            emit_per_window=True,
        )
        _, per_window = replay_windows(
            [window], spec, emitted_at=EMITTED_AT,
        )
        assert len(per_window) == 1
        assert per_window[0].signal_id == "CAPTURE_SELF_DIAGNOSTIC"


class TestSummaryEnvelope:
    """Summary artifact correctness."""

    def _make_replayed_result(
        self,
        orig_value: float = 0.5,
        replay_value: float = 0.6,
        orig_quality: str = "ok",
        replay_quality: str = "ok",
        orig_class: str = "normal",
        replay_class: str = "normal",
    ) -> ReplayWindowResult:
        return ReplayWindowResult(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            window_kind=WINDOW_KIND,
            signal_id="TEST",
            replayed=_make_a_signal("TEST", replay_value),
            original_value=orig_value,
            replayed_value=replay_value,
            original_quality=orig_quality,
            replayed_quality=replay_quality,
            original_classification=orig_class,
            replayed_classification=replay_class,
        )

    def test_summary_signal_id(self):
        results = [self._make_replayed_result()]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.signal_id == "REPLAY_HARNESS"

    def test_summary_phase_is_2_4c(self):
        results = [self._make_replayed_result()]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.phase == "2.4C"

    def test_summary_counts(self):
        results = [
            self._make_replayed_result(),
            self._make_replayed_result(),
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "TEST",
                               skipped=True, skip_reason=SKIP_MISSING_INPUTS),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.values["window_count_total"] == 3
        assert summary.values["window_count_replayed"] == 2
        assert summary.values["window_count_skipped"] == 1

    def test_summary_drift_stats(self):
        results = [
            self._make_replayed_result(orig_value=0.0, replay_value=0.1),
            self._make_replayed_result(orig_value=0.5, replay_value=0.5),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.values["mean_abs_delta"] == pytest.approx(0.05)
        assert summary.values["max_abs_delta"] == pytest.approx(0.1)

    def test_summary_classification_changes(self):
        results = [
            self._make_replayed_result(orig_class="normal", replay_class="warning"),
            self._make_replayed_result(orig_class="normal", replay_class="normal"),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.values["classification_change_count"] == 1

    def test_summary_quality_changes(self):
        results = [
            self._make_replayed_result(orig_quality="ok", replay_quality="partial"),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.values["quality_status_change_count"] == 1

    def test_summary_value_direction_counts(self):
        results = [
            self._make_replayed_result(orig_value=0.5, replay_value=0.6),  # increase
            self._make_replayed_result(orig_value=0.5, replay_value=0.4),  # decrease
            self._make_replayed_result(orig_value=0.5, replay_value=0.5),  # unchanged
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.values["value_increase_count"] == 1
        assert summary.values["value_decrease_count"] == 1
        assert summary.values["value_unchanged_count"] == 1

    def test_summary_no_replayed_quality_unavailable(self):
        results = [
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "TEST",
                               skipped=True, skip_reason=SKIP_MISSING_INPUTS),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.quality_status == QualityStatus.UNAVAILABLE.value
        assert summary.value is None

    def test_summary_derivation_error_count(self):
        results = [
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "TEST",
                               skipped=True, skip_reason=SKIP_DERIVATION_ERROR,
                               error_message="err1"),
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "TEST",
                               skipped=True, skip_reason=SKIP_DERIVATION_ERROR,
                               error_message="err2"),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.values["derivation_error_count"] == 2
        assert summary.annotations["derivation_errors"] == ["err1", "err2"]

    def test_summary_error_messages_capped(self):
        """Only first MAX_ERROR_MESSAGES error messages kept."""
        results = []
        for i in range(15):
            results.append(ReplayWindowResult(
                WINDOW_START, WINDOW_END, WINDOW_KIND, "TEST",
                skipped=True, skip_reason=SKIP_DERIVATION_ERROR,
                error_message=f"error_{i}",
            ))
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert len(summary.annotations["derivation_errors"]) == MAX_ERROR_MESSAGES

    def test_summary_annotations_include_spec_and_manifest(self):
        results = [self._make_replayed_result()]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build(["h1"], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT, replay_run_id="run-42",
        )
        assert summary.annotations["replay_spec_hash"] == spec.spec_hash()
        assert summary.annotations["manifest_hash"] == manifest.manifest_hash
        assert summary.annotations["replay_run_id"] == "run-42"

    def test_summary_completeness(self):
        results = [
            self._make_replayed_result(),
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "TEST",
                               skipped=True, skip_reason=SKIP_MISSING_INPUTS),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.completeness == pytest.approx(0.5)

    def test_summary_passes_validation(self):
        results = [self._make_replayed_result()]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest,
            emitted_at=EMITTED_AT, emitter_version="2.4.0-test",
        )
        assert validate_envelope(summary) == []


class TestNoMutation:
    """Replay does not mutate source artifacts."""

    def test_envelope_inputs_not_mutated(self):
        inputs = _make_b1_inputs()
        inputs_copy = copy.deepcopy(inputs)
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        replay_windows([window], spec, emitted_at=EMITTED_AT)
        assert inputs == inputs_copy

    def test_receipt_inputs_not_mutated(self):
        r1 = _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:02:00Z")
        r1_copy = copy.deepcopy(r1)
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "DECISION_EVIDENCE_LAG", 1,
            receipt_inputs=(r1,),
        )
        spec = ReplaySpec(target_signals=("DECISION_EVIDENCE_LAG",))
        replay_windows([window], spec, emitted_at=EMITTED_AT)
        assert r1 == r1_copy

    def test_original_output_not_mutated(self):
        original = {"signal_id": "CAPTURE_SELF_DIAGNOSTIC", "value": 0.5}
        original_copy = copy.deepcopy(original)
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
            original_output=original,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        replay_windows([window], spec, emitted_at=EMITTED_AT)
        assert original == original_copy


class TestIdempotentReplay:
    """Same inputs/spec → identical outputs."""

    def test_b1_replay_deterministic(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        kwargs = dict(emitted_at=EMITTED_AT, replay_run_id="det-test")
        r1, _ = replay_windows([window], spec, **kwargs)
        r2, _ = replay_windows([window], spec, **kwargs)
        env1 = r1[0].replayed
        env2 = r2[0].replayed
        assert env1.to_dict() == env2.to_dict()

    def test_b2_replay_deterministic(self):
        receipts = (
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:02:00Z"),
        )
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "DECISION_EVIDENCE_LAG", 1,
            receipt_inputs=receipts,
        )
        spec = ReplaySpec(target_signals=("DECISION_EVIDENCE_LAG",))
        kwargs = dict(emitted_at=EMITTED_AT, replay_run_id="det-test")
        r1, _ = replay_windows([window], spec, **kwargs)
        r2, _ = replay_windows([window], spec, **kwargs)
        assert r1[0].replayed.to_dict() == r2[0].replayed.to_dict()

    def test_summary_deterministic(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        manifest = ReplayManifest.build(["h1"], source_mode="envelope")
        kwargs = dict(emitted_at=EMITTED_AT, replay_run_id="det-sum")
        r1, _ = replay_windows([window], spec, **kwargs)
        r2, _ = replay_windows([window], spec, **kwargs)
        s1 = replay_summary_envelope(r1, spec, manifest, **kwargs)
        s2 = replay_summary_envelope(r2, spec, manifest, **kwargs)
        assert s1.to_dict() == s2.to_dict()


class TestComputeP95:
    """p95 helper edge cases."""

    def test_empty_returns_none(self):
        assert _compute_p95([]) is None

    def test_single_value(self):
        assert _compute_p95([42.0]) == 42.0

    def test_two_values(self):
        result = _compute_p95([1.0, 2.0])
        assert result in (1.0, 2.0)

    def test_hundred_values(self):
        vals = [float(i) for i in range(1, 101)]
        result = _compute_p95(vals)
        # Index: min(int(0.95 * 100 + 0.5), 99) = min(int(95.5), 99) = min(95, 99) = 95
        assert result == 96.0  # sorted[95] = 96.0 (0-indexed, values 1..100)


class TestExtractClassification:
    """_extract_classification helper."""

    def test_present(self):
        assert _extract_classification({"values": {"classification": "normal"}}) == "normal"

    def test_missing_values(self):
        assert _extract_classification({}) is None

    def test_missing_classification(self):
        assert _extract_classification({"values": {}}) is None


class TestAddReplayAnnotations:
    """_add_replay_annotations preserves envelope identity."""

    def test_phase_replaced(self):
        env = _make_a_signal("TEST", 1.0)
        annotated = _add_replay_annotations(env, "run-1", None, {})
        assert annotated.phase == "2.4C"
        assert env.phase == "2.4A"  # original unchanged

    def test_signal_id_preserved(self):
        env = _make_a_signal("TEST", 1.0)
        annotated = _add_replay_annotations(env, "run-1", None, {})
        assert annotated.signal_id == "TEST"

    def test_overrides_included_when_present(self):
        env = _make_a_signal("TEST", 1.0)
        annotated = _add_replay_annotations(
            env, "run-1", None, {"threshold": 0.5},
        )
        assert annotated.annotations["threshold_overrides"] == {"threshold": 0.5}

    def test_overrides_excluded_when_empty(self):
        env = _make_a_signal("TEST", 1.0)
        annotated = _add_replay_annotations(env, "run-1", None, {})
        assert "threshold_overrides" not in annotated.annotations


# ── Replay sources tests ──────────────────────────────────────────────────


class TestPrepareEnvelopeWindows:
    """prepare_envelope_windows grouping and shaping."""

    def _make_env_dict(
        self,
        signal_id: str,
        ws: str = WINDOW_START,
        we: str = WINDOW_END,
        wk: str = WINDOW_KIND,
        value: float = 1.0,
    ) -> dict:
        return _make_a_signal(
            signal_id, value=value,
            window_start=ws, window_end=we, window_kind=wk,
        ).to_dict()

    def test_basic_grouping(self):
        envelopes = [
            self._make_env_dict("EXPOSURE_PROXY"),
            self._make_env_dict("SILENT_SUPPRESSION"),
            self._make_env_dict("SIGMA_RATE"),
            self._make_env_dict("CAPTURE_SELF_DIAGNOSTIC"),
        ]
        windows, manifest = prepare_envelope_windows(
            envelopes, "CAPTURE_SELF_DIAGNOSTIC",
        )
        assert len(windows) == 1
        w = windows[0]
        assert w.signal_id == "CAPTURE_SELF_DIAGNOSTIC"
        assert w.envelope_inputs is not None
        assert "EXPOSURE_PROXY" in w.envelope_inputs
        assert "SILENT_SUPPRESSION" in w.envelope_inputs
        assert "SIGMA_RATE" in w.envelope_inputs
        assert w.original_output is not None

    def test_multiple_windows(self):
        ws1 = "2026-02-25T10:00:00Z"
        we1 = "2026-02-25T10:05:00Z"
        ws2 = "2026-02-25T10:05:00Z"
        we2 = "2026-02-25T10:10:00Z"

        envelopes = [
            self._make_env_dict("EXPOSURE_PROXY", ws=ws1, we=we1),
            self._make_env_dict("CAPTURE_SELF_DIAGNOSTIC", ws=ws1, we=we1),
            self._make_env_dict("EXPOSURE_PROXY", ws=ws2, we=we2),
            self._make_env_dict("CAPTURE_SELF_DIAGNOSTIC", ws=ws2, we=we2),
        ]
        windows, manifest = prepare_envelope_windows(
            envelopes, "CAPTURE_SELF_DIAGNOSTIC",
        )
        assert len(windows) == 2
        assert windows[0].window_start == ws1
        assert windows[1].window_start == ws2

    def test_manifest_includes_all_hashes(self):
        envelopes = [
            self._make_env_dict("EXPOSURE_PROXY"),
            self._make_env_dict("CAPTURE_SELF_DIAGNOSTIC"),
        ]
        _, manifest = prepare_envelope_windows(
            envelopes, "CAPTURE_SELF_DIAGNOSTIC",
        )
        assert manifest.input_count == 2
        assert manifest.source_mode == "envelope"

    def test_input_signal_filter(self):
        envelopes = [
            self._make_env_dict("EXPOSURE_PROXY"),
            self._make_env_dict("SILENT_SUPPRESSION"),
            self._make_env_dict("SIGMA_RATE"),
            self._make_env_dict("CAPTURE_SELF_DIAGNOSTIC"),
        ]
        windows, _ = prepare_envelope_windows(
            envelopes, "CAPTURE_SELF_DIAGNOSTIC",
            input_signal_ids=frozenset({"EXPOSURE_PROXY"}),
        )
        assert len(windows) == 1
        assert "EXPOSURE_PROXY" in windows[0].envelope_inputs
        assert "SILENT_SUPPRESSION" not in windows[0].envelope_inputs

    def test_skips_envelopes_without_window(self):
        env = self._make_env_dict("EXPOSURE_PROXY")
        env["window_start"] = ""
        env["window_end"] = ""
        windows, manifest = prepare_envelope_windows(
            [env], "CAPTURE_SELF_DIAGNOSTIC",
        )
        assert len(windows) == 0
        assert manifest.input_count == 0

    def test_window_without_original(self):
        """Window with inputs but no original target envelope."""
        envelopes = [
            self._make_env_dict("EXPOSURE_PROXY"),
        ]
        windows, _ = prepare_envelope_windows(
            envelopes, "CAPTURE_SELF_DIAGNOSTIC",
        )
        assert len(windows) == 1
        assert windows[0].original_output is None
        assert windows[0].envelope_inputs is not None


class TestPrepareReceiptWindows:
    """prepare_receipt_windows grouping and shaping."""

    def _make_original_env(
        self,
        ws: str = WINDOW_START,
        we: str = WINDOW_END,
        wk: str = WINDOW_KIND,
    ) -> dict:
        return _make_a_signal(
            "DECISION_EVIDENCE_LAG",
            window_start=ws, window_end=we, window_kind=wk,
        ).to_dict()

    def test_basic_grouping(self):
        receipts = [
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:01:00Z"),
            _make_receipt_record("evidence_gate", "warn", "2026-02-25T10:02:00Z"),
        ]
        originals = [self._make_original_env()]
        windows, manifest = prepare_receipt_windows(
            receipts, originals, "DECISION_EVIDENCE_LAG",
        )
        assert len(windows) == 1
        w = windows[0]
        assert w.signal_id == "DECISION_EVIDENCE_LAG"
        assert w.receipt_inputs is not None
        assert len(w.receipt_inputs) == 2
        assert w.original_output is not None

    def test_explicit_boundaries(self):
        receipts = [
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:01:00Z"),
        ]
        windows, _ = prepare_receipt_windows(
            receipts, [], "DECISION_EVIDENCE_LAG",
            window_boundaries=[
                (WINDOW_START, WINDOW_END, WINDOW_KIND),
                ("2026-02-25T10:05:00Z", "2026-02-25T10:10:00Z", WINDOW_KIND),
            ],
        )
        assert len(windows) == 2

    def test_pre_window_receipts_included(self):
        """Receipts before window_start are included (pre-window evidence)."""
        receipts = [
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T09:55:00Z"),  # pre-window
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:02:00Z"),  # in-window
        ]
        originals = [self._make_original_env()]
        windows, _ = prepare_receipt_windows(
            receipts, originals, "DECISION_EVIDENCE_LAG",
        )
        assert len(windows[0].receipt_inputs) == 2

    def test_post_window_receipts_excluded(self):
        """Receipts at or after window_end are excluded."""
        receipts = [
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:05:00Z"),  # at end (excluded)
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:06:00Z"),  # after end
        ]
        originals = [self._make_original_env()]
        windows, _ = prepare_receipt_windows(
            receipts, originals, "DECISION_EVIDENCE_LAG",
        )
        assert len(windows[0].receipt_inputs) == 0

    def test_manifest_includes_receipts_and_envelopes(self):
        receipts = [
            _make_receipt_record("evidence_gate", "pass", "2026-02-25T10:02:00Z"),
        ]
        originals = [self._make_original_env()]
        _, manifest = prepare_receipt_windows(
            receipts, originals, "DECISION_EVIDENCE_LAG",
        )
        assert manifest.input_count == 2  # 1 receipt + 1 envelope
        assert manifest.source_mode == "receipt"

    def test_non_target_envelopes_ignored(self):
        """Original envelopes for other signals are not indexed."""
        other_env = _make_a_signal("OTHER_SIGNAL").to_dict()
        windows, _ = prepare_receipt_windows(
            [], [other_env], "DECISION_EVIDENCE_LAG",
        )
        # No boundaries from other_env → no windows
        assert len(windows) == 0


class TestObserveOnly:
    """Replayed envelopes are observe-only — no blocking semantics."""

    def test_replayed_derivation_is_derived(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT,
        )
        assert results[0].replayed.derivation == DerivationType.DERIVED.value

    def test_summary_derivation_is_derived(self):
        results = []
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.derivation == DerivationType.DERIVED.value


class TestMissingNotZero:
    """Missing != zero preserved through replay."""

    def test_b2_no_decisions_value_is_none(self):
        """No decisions in window → value is None, not 0."""
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "DECISION_EVIDENCE_LAG", 1,
            receipt_inputs=(),  # no receipts
        )
        spec = ReplaySpec(target_signals=("DECISION_EVIDENCE_LAG",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT,
        )
        env = results[0].replayed
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value

    def test_summary_no_replayed_value_is_none(self):
        """All skipped → summary value is None."""
        results = [
            ReplayWindowResult(WINDOW_START, WINDOW_END, WINDOW_KIND, "TEST",
                               skipped=True, skip_reason=SKIP_MISSING_INPUTS),
        ]
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        assert summary.value is None
        assert summary.values["mean_abs_delta"] is None


class TestReplayRunId:
    """Replay run ID generation and propagation."""

    def test_explicit_run_id_used(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="explicit-id",
        )
        assert results[0].replayed.annotations["replay_run_id"] == "explicit-id"

    def test_auto_generated_run_id(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT,
        )
        run_id = results[0].replayed.annotations["replay_run_id"]
        assert len(run_id) == 16  # hex truncated to 16 chars
        assert all(c in "0123456789abcdef" for c in run_id)


class TestEnvelopeSerialization:
    """Replay outputs serialize and round-trip cleanly."""

    def test_replayed_envelope_roundtrip(self):
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="rt-test",
        )
        env = results[0].replayed
        d = env.to_dict()
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        env2 = SignalEnvelope.from_dict(restored)
        assert env2.signal_id == env.signal_id
        assert env2.phase == env.phase
        assert env2.annotations == env.annotations

    def test_summary_envelope_roundtrip(self):
        results = []
        spec = ReplaySpec(target_signals=("TEST",))
        manifest = ReplayManifest.build([], source_mode="envelope")
        summary = replay_summary_envelope(
            results, spec, manifest, emitted_at=EMITTED_AT,
        )
        d = summary.to_dict()
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        env2 = SignalEnvelope.from_dict(restored)
        assert env2.signal_id == "REPLAY_HARNESS"
        assert env2.values == summary.values


class TestGoldenFixtures:
    """Golden file tests — lock down serialization shape."""

    @pytest.fixture(autouse=True)
    def _fixture_dir(self):
        self.fixture_dir = FIXTURES
        self.fixture_dir.mkdir(parents=True, exist_ok=True)

    def _generate_replay_summary(self) -> dict:
        """Generate a replay summary from a B1 replay."""
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
            original_output={
                "signal_id": "CAPTURE_SELF_DIAGNOSTIC",
                "value": 0.0,
                "quality_status": "ok",
                "values": {"classification": "normal"},
            },
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        manifest = ReplayManifest.build(["h1", "h2", "h3"], source_mode="envelope")
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="golden-test",
        )
        summary = replay_summary_envelope(
            results, spec, manifest,
            emitted_at=EMITTED_AT, replay_run_id="golden-test",
        )
        return summary.to_dict()

    def test_replay_summary_golden(self):
        golden_path = self.fixture_dir / "envelope_replay_summary.json"
        actual = self._generate_replay_summary()

        if not golden_path.exists():
            golden_path.write_text(
                json.dumps(actual, indent=2, sort_keys=False) + "\n"
            )
            pytest.skip("Golden file generated — re-run to validate")

        expected = json.loads(golden_path.read_text())
        assert actual == expected, (
            f"Golden file mismatch. Delete {golden_path} and re-run to regenerate."
        )

    def _generate_b1_replayed(self) -> dict:
        """Generate a replayed B1 envelope."""
        inputs = _make_b1_inputs()
        window = ReplayWindowInput(
            WINDOW_START, WINDOW_END, WINDOW_KIND,
            "CAPTURE_SELF_DIAGNOSTIC", 1,
            envelope_inputs=inputs,
        )
        spec = ReplaySpec(target_signals=("CAPTURE_SELF_DIAGNOSTIC",))
        results, _ = replay_windows(
            [window], spec, emitted_at=EMITTED_AT, replay_run_id="golden-b1",
        )
        return results[0].replayed.to_dict()

    def test_b1_replayed_golden(self):
        golden_path = self.fixture_dir / "envelope_replayed_capture_diag.json"
        actual = self._generate_b1_replayed()

        if not golden_path.exists():
            golden_path.write_text(
                json.dumps(actual, indent=2, sort_keys=False) + "\n"
            )
            pytest.skip("Golden file generated — re-run to validate")

        expected = json.loads(golden_path.read_text())
        assert actual == expected, (
            f"Golden file mismatch. Delete {golden_path} and re-run to regenerate."
        )
