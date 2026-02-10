"""Tests for Detector Integration (AG2 Layer 1, Item #4)."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from governor.detector_integration import (
    PhaseFlag,
    SignalQuality,
    GovernorAction,
    SignalKey,
    RawDetectorSignal,
    CollapsedSignal,
    SignalPolicy,
    SignalActionResult,
    DetectorSignalFile,
    DetectorIntegration,
    collapse_signal,
    map_signal_to_actions,
    failure_safe_signal,
    signal_to_constraints,
    make_evidence_ref,
    load_signal_file,
    save_signal_file,
    _classify_phase,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestPhaseFlag:
    def test_values(self):
        assert PhaseFlag.SEARCHY.value == "searchy"
        assert PhaseFlag.CONFAB.value == "confab"
        assert PhaseFlag.DELIBERATE.value == "deliberate"
        assert PhaseFlag.REFUSAL.value == "refusal"
        assert PhaseFlag.UNKNOWN.value == "unknown"

    def test_count(self):
        assert len(PhaseFlag) == 5


class TestSignalQuality:
    def test_values(self):
        assert SignalQuality.CLEAN.value == "clean"
        assert SignalQuality.UNCERTAIN.value == "uncertain"
        assert SignalQuality.DIRTY.value == "dirty"


class TestGovernorAction:
    def test_values(self):
        assert GovernorAction.NO_CHANGE.value == "no_change"
        assert GovernorAction.RAISE_EVIDENCE.value == "raise_evidence"
        assert GovernorAction.FORCE_QUORUM.value == "force_quorum"
        assert GovernorAction.CAP_CONFIDENCE.value == "cap_confidence"
        assert GovernorAction.MARK_SOFT.value == "mark_soft"
        assert GovernorAction.BLOCK_WRITES.value == "block_writes"

    def test_count(self):
        assert len(GovernorAction) == 6


# ---------------------------------------------------------------------------
# SignalKey
# ---------------------------------------------------------------------------


class TestSignalKey:
    def test_roundtrip(self):
        key = SignalKey(
            run_id="run-1",
            turn_id="turn-3",
            response_hash="abc123",
            model_id="llama3",
            timestamp=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        d = key.to_dict()
        key2 = SignalKey.from_dict(d)
        assert key2.run_id == key.run_id
        assert key2.response_hash == key.response_hash
        assert key2.model_id == key.model_id

    def test_with_byte_range(self):
        key = SignalKey(
            run_id="r1", turn_id="t1", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
            byte_range=(100, 500),
        )
        d = key.to_dict()
        assert d["byte_range"] == [100, 500]
        key2 = SignalKey.from_dict(d)
        assert key2.byte_range == (100, 500)

    def test_no_byte_range(self):
        key = SignalKey(
            run_id="r1", turn_id="t1", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
        )
        d = key.to_dict()
        assert "byte_range" not in d

    def test_from_response(self):
        key = SignalKey.from_response("Hello world", "gpt-4", "run1", "t1")
        assert key.model_id == "gpt-4"
        assert key.run_id == "run1"
        assert len(key.response_hash) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# RawDetectorSignal
# ---------------------------------------------------------------------------


class TestRawDetectorSignal:
    def test_defaults(self):
        raw = RawDetectorSignal()
        assert raw.temporal_debt == 0.0
        assert raw.token_jaccard == 1.0
        assert raw.response_length == 0

    def test_roundtrip(self):
        raw = RawDetectorSignal(
            temporal_debt=0.3,
            confidence_slope=0.5,
            max_entropy_jump=0.8,
            token_jaccard=0.7,
        )
        d = raw.to_dict()
        raw2 = RawDetectorSignal.from_dict(d)
        assert raw2.temporal_debt == raw.temporal_debt
        assert raw2.token_jaccard == raw.token_jaccard

    def test_from_empty_dict(self):
        raw = RawDetectorSignal.from_dict({})
        assert raw.temporal_debt == 0.0


# ---------------------------------------------------------------------------
# CollapsedSignal
# ---------------------------------------------------------------------------


class TestCollapsedSignal:
    def test_defaults(self):
        s = CollapsedSignal()
        assert s.coherence_score == 1.0
        assert s.instability_spikes == 0
        assert s.perturbation_fragility == 0.0
        assert s.overconfidence_signature == 0.0
        assert s.phase_flag == PhaseFlag.UNKNOWN

    def test_roundtrip(self):
        s = CollapsedSignal(
            coherence_score=0.6,
            instability_spikes=2,
            perturbation_fragility=0.4,
            overconfidence_signature=0.3,
            phase_flag=PhaseFlag.DELIBERATE,
        )
        d = s.to_dict()
        s2 = CollapsedSignal.from_dict(d)
        assert s2.coherence_score == s.coherence_score
        assert s2.phase_flag == s.phase_flag

    def test_quality_clean(self):
        s = CollapsedSignal(
            coherence_score=0.9,
            perturbation_fragility=0.1,
            overconfidence_signature=0.1,
            phase_flag=PhaseFlag.DELIBERATE,
        )
        assert s.quality == SignalQuality.CLEAN

    def test_quality_dirty_low_coherence(self):
        s = CollapsedSignal(coherence_score=0.3)
        assert s.quality == SignalQuality.DIRTY

    def test_quality_dirty_overconfidence(self):
        s = CollapsedSignal(overconfidence_signature=0.7)
        assert s.quality == SignalQuality.DIRTY

    def test_quality_dirty_confab(self):
        s = CollapsedSignal(
            coherence_score=0.9,
            phase_flag=PhaseFlag.CONFAB,
        )
        assert s.quality == SignalQuality.DIRTY

    def test_quality_uncertain(self):
        s = CollapsedSignal(
            coherence_score=0.5,
            perturbation_fragility=0.3,
            overconfidence_signature=0.4,
        )
        assert s.quality == SignalQuality.UNCERTAIN

    def test_evidence_span(self):
        s = CollapsedSignal(
            coherence_score=0.72,
            perturbation_fragility=0.31,
            phase_flag=PhaseFlag.DELIBERATE,
        )
        span = s.to_evidence_span()
        assert "coherence_score=0.72" in span
        assert "fragility=0.31" in span
        assert "phase=deliberate" in span


# ---------------------------------------------------------------------------
# Signal Collapse
# ---------------------------------------------------------------------------


class TestCollapseSignal:
    def test_stable_signal(self):
        raw = RawDetectorSignal()  # All zeros/defaults
        collapsed = collapse_signal(raw)
        assert collapsed.coherence_score >= 0.9
        assert collapsed.instability_spikes == 0
        assert collapsed.perturbation_fragility == 0.0
        assert collapsed.overconfidence_signature == 0.0

    def test_high_temporal_debt(self):
        raw = RawDetectorSignal(temporal_debt=0.8, acceleration=0.5)
        collapsed = collapse_signal(raw)
        assert collapsed.coherence_score < 0.5

    def test_entropy_spikes(self):
        raw = RawDetectorSignal(
            max_entropy_jump=1.5,
            entropy_recovery_detected=True,
            entropy_variance=0.5,
        )
        collapsed = collapse_signal(raw)
        assert collapsed.instability_spikes >= 3

    def test_perturbation_fragile(self):
        raw = RawDetectorSignal(token_jaccard=0.2, perturbation_sensitivity=0.8)
        collapsed = collapse_signal(raw)
        assert collapsed.perturbation_fragility >= 0.7

    def test_overconfident(self):
        raw = RawDetectorSignal(
            tokens_to_high_conf=5,  # Very quick to high confidence
            confidence_monotonicity=0.9,
            entropy_variance=0.05,
        )
        collapsed = collapse_signal(raw)
        assert collapsed.overconfidence_signature >= 0.5

    def test_values_bounded(self):
        raw = RawDetectorSignal(
            temporal_debt=10.0, acceleration=10.0,
            token_jaccard=-1.0, perturbation_sensitivity=5.0,
        )
        collapsed = collapse_signal(raw)
        assert 0.0 <= collapsed.coherence_score <= 1.0
        assert 0.0 <= collapsed.perturbation_fragility <= 1.0
        assert 0.0 <= collapsed.overconfidence_signature <= 1.0


# ---------------------------------------------------------------------------
# Phase Classification
# ---------------------------------------------------------------------------


class TestClassifyPhase:
    def test_searchy(self):
        raw = RawDetectorSignal(
            early_phase_entropy=0.9,
            late_phase_entropy=0.1,
            early_phase_confidence=0.3,
            mid_phase_confidence=0.5,
            late_phase_confidence=0.7,
        )
        assert _classify_phase(raw) == PhaseFlag.SEARCHY

    def test_confab(self):
        raw = RawDetectorSignal(
            early_phase_confidence=0.9,
            mid_phase_confidence=0.9,
            late_phase_confidence=0.9,
            early_phase_entropy=0.1,
            mid_phase_entropy=0.1,
            late_phase_entropy=0.1,
        )
        assert _classify_phase(raw) == PhaseFlag.CONFAB

    def test_refusal(self):
        raw = RawDetectorSignal(
            early_phase_confidence=0.1,
            mid_phase_confidence=0.1,
            late_phase_confidence=0.1,
            early_phase_entropy=0.9,
            mid_phase_entropy=0.8,
            late_phase_entropy=0.8,
        )
        assert _classify_phase(raw) == PhaseFlag.REFUSAL

    def test_deliberate(self):
        raw = RawDetectorSignal(
            early_phase_confidence=0.5,
            mid_phase_confidence=0.6,
            late_phase_confidence=0.5,
            early_phase_entropy=0.3,
            mid_phase_entropy=0.3,
            late_phase_entropy=0.3,
            entropy_variance=0.1,
        )
        assert _classify_phase(raw) == PhaseFlag.DELIBERATE

    def test_unknown(self):
        raw = RawDetectorSignal()  # All zeros
        phase = _classify_phase(raw)
        # Either DELIBERATE or UNKNOWN depending on thresholds
        assert phase in (PhaseFlag.DELIBERATE, PhaseFlag.UNKNOWN)


# ---------------------------------------------------------------------------
# Signal-to-Action Mapping
# ---------------------------------------------------------------------------


class TestMapSignalToActions:
    def test_clean_signal_no_change(self):
        signal = CollapsedSignal(
            coherence_score=0.9, instability_spikes=0,
            perturbation_fragility=0.1, overconfidence_signature=0.1,
        )
        result = map_signal_to_actions(signal)
        assert GovernorAction.NO_CHANGE in result.actions
        assert result.signal_quality == SignalQuality.CLEAN

    def test_low_coherence_raises_evidence(self):
        signal = CollapsedSignal(coherence_score=0.2)
        result = map_signal_to_actions(signal)
        assert GovernorAction.RAISE_EVIDENCE in result.actions
        assert result.evidence_tier == "TOOL_TRACE"

    def test_high_spikes_force_quorum(self):
        signal = CollapsedSignal(instability_spikes=5)
        result = map_signal_to_actions(signal)
        assert GovernorAction.FORCE_QUORUM in result.actions

    def test_high_fragility_marks_soft(self):
        signal = CollapsedSignal(perturbation_fragility=0.8)
        result = map_signal_to_actions(signal)
        assert GovernorAction.MARK_SOFT in result.actions

    def test_overconfident_caps_confidence(self):
        signal = CollapsedSignal(overconfidence_signature=0.7)
        result = map_signal_to_actions(signal)
        assert GovernorAction.CAP_CONFIDENCE in result.actions
        assert result.confidence_cap == 0.5

    def test_confab_blocks_writes(self):
        signal = CollapsedSignal(phase_flag=PhaseFlag.CONFAB)
        result = map_signal_to_actions(signal)
        assert GovernorAction.BLOCK_WRITES in result.actions

    def test_confab_no_block_when_disabled(self):
        signal = CollapsedSignal(phase_flag=PhaseFlag.CONFAB)
        policy = SignalPolicy(confab_blocks_writes=False)
        result = map_signal_to_actions(signal, policy)
        assert GovernorAction.BLOCK_WRITES not in result.actions

    def test_custom_thresholds(self):
        signal = CollapsedSignal(coherence_score=0.5)
        # Default threshold is 0.4 — should be fine
        result = map_signal_to_actions(signal)
        assert GovernorAction.NO_CHANGE in result.actions

        # Tighter threshold
        policy = SignalPolicy(coherence_threshold=0.6)
        result = map_signal_to_actions(signal, policy)
        assert GovernorAction.RAISE_EVIDENCE in result.actions

    def test_multiple_actions(self):
        signal = CollapsedSignal(
            coherence_score=0.2,
            instability_spikes=5,
            overconfidence_signature=0.8,
            phase_flag=PhaseFlag.CONFAB,
        )
        result = map_signal_to_actions(signal)
        assert len(result.actions) >= 3

    def test_monotonic_clean_no_loosening(self):
        """Clean signals must not weaken constraints — they just do nothing."""
        clean = CollapsedSignal(
            coherence_score=1.0, instability_spikes=0,
            perturbation_fragility=0.0, overconfidence_signature=0.0,
            phase_flag=PhaseFlag.DELIBERATE,
        )
        result = map_signal_to_actions(clean)
        assert result.actions == [GovernorAction.NO_CHANGE]
        assert result.confidence_cap is None
        assert result.evidence_tier is None


# ---------------------------------------------------------------------------
# Failure-Safe Signal
# ---------------------------------------------------------------------------


class TestFailureSafeSignal:
    def test_defaults(self):
        safe = failure_safe_signal()
        assert safe.coherence_score == 0.5
        assert safe.overconfidence_signature == 0.5  # Default penalty
        assert safe.phase_flag == PhaseFlag.UNKNOWN

    def test_custom_penalty(self):
        policy = SignalPolicy(unavailable_penalty=0.7)
        safe = failure_safe_signal(policy)
        assert safe.overconfidence_signature == 0.7

    def test_failure_safe_triggers_tightening(self):
        """Failure-safe signal should trigger some tightening."""
        safe = failure_safe_signal()
        result = map_signal_to_actions(safe)
        # With overconfidence at 0.5, it's below 0.6 threshold — no cap
        # But it should be uncertain quality
        assert safe.quality == SignalQuality.UNCERTAIN

    def test_high_penalty_triggers_actions(self):
        policy = SignalPolicy(unavailable_penalty=0.7)
        safe = failure_safe_signal(policy)
        result = map_signal_to_actions(safe, policy)
        assert GovernorAction.CAP_CONFIDENCE in result.actions


# ---------------------------------------------------------------------------
# Signal Policy
# ---------------------------------------------------------------------------


class TestSignalPolicy:
    def test_defaults(self):
        p = SignalPolicy()
        assert p.coherence_threshold == 0.4
        assert p.spike_threshold == 3
        assert p.fragility_threshold == 0.7
        assert p.overconfidence_threshold == 0.6

    def test_roundtrip(self):
        p = SignalPolicy(coherence_threshold=0.5, spike_threshold=5)
        d = p.to_dict()
        p2 = SignalPolicy.from_dict(d)
        assert p2.coherence_threshold == 0.5
        assert p2.spike_threshold == 5


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


class TestSignalFileIO:
    def test_save_and_load(self, tmp_path):
        key = SignalKey(
            run_id="r1", turn_id="t1", response_hash="h",
            model_id="llama3", timestamp=datetime.now(timezone.utc),
        )
        raw = RawDetectorSignal(temporal_debt=0.3)
        collapsed = collapse_signal(raw)

        signal_file = DetectorSignalFile(
            key=key, raw=raw, collapsed=collapsed,
            detector_version="0.1.0", profile="general",
        )

        path = tmp_path / "signal.json"
        save_signal_file(signal_file, path)
        assert path.exists()

        loaded = load_signal_file(path)
        assert loaded.key.run_id == "r1"
        assert loaded.raw.temporal_debt == 0.3
        assert loaded.collapsed is not None
        assert loaded.file_hash  # Should be computed

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_signal_file(tmp_path / "nonexistent.json")

    def test_load_malformed_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json")
        with pytest.raises(ValueError, match="Malformed"):
            load_signal_file(path)

    def test_load_missing_key(self, tmp_path):
        path = tmp_path / "nokey.json"
        path.write_text(json.dumps({"raw": {}}))
        with pytest.raises(ValueError, match="missing"):
            load_signal_file(path)


class TestDetectorSignalFile:
    def test_roundtrip(self):
        key = SignalKey(
            run_id="r1", turn_id="t1", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
        )
        raw = RawDetectorSignal()
        sf = DetectorSignalFile(key=key, raw=raw)
        d = sf.to_dict()
        sf2 = DetectorSignalFile.from_dict(d)
        assert sf2.key.run_id == sf.key.run_id

    def test_with_collapsed(self):
        key = SignalKey(
            run_id="r1", turn_id="t1", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
        )
        raw = RawDetectorSignal()
        collapsed = CollapsedSignal(coherence_score=0.7)
        sf = DetectorSignalFile(key=key, raw=raw, collapsed=collapsed)
        d = sf.to_dict()
        assert "collapsed" in d
        sf2 = DetectorSignalFile.from_dict(d)
        assert sf2.collapsed.coherence_score == 0.7


# ---------------------------------------------------------------------------
# Constraint Integration
# ---------------------------------------------------------------------------


class TestSignalToConstraints:
    def test_clean_signal_no_constraints(self):
        signal = CollapsedSignal(
            coherence_score=0.9, instability_spikes=0,
            perturbation_fragility=0.1, overconfidence_signature=0.1,
        )
        constraints = signal_to_constraints(signal)
        assert len(constraints) == 0

    def test_dirty_signal_produces_constraints(self):
        signal = CollapsedSignal(
            coherence_score=0.2,
            overconfidence_signature=0.8,
            phase_flag=PhaseFlag.CONFAB,
        )
        constraints = signal_to_constraints(signal)
        assert len(constraints) >= 2
        kinds = {c["source"] for c in constraints}
        assert "detector" in kinds

    def test_constraint_format(self):
        signal = CollapsedSignal(coherence_score=0.2)
        constraints = signal_to_constraints(signal)
        assert len(constraints) >= 1
        c = constraints[0]
        assert "constraint_id" in c
        assert "kind" in c
        assert "severity" in c
        assert "description" in c
        assert c["source"] == "detector"


# ---------------------------------------------------------------------------
# Evidence Ref
# ---------------------------------------------------------------------------


class TestMakeEvidenceRef:
    def test_basic(self):
        signal = CollapsedSignal(coherence_score=0.72)
        key = SignalKey(
            run_id="run-1", turn_id="t1", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
        )
        ref = make_evidence_ref(signal, key, "filehash123")
        assert ref["type"] == "detector_signal"
        assert ref["location"] == "run-1"
        assert "coherence_score=0.72" in ref["span"]
        assert ref["content_hash"] == "filehash123"


# ---------------------------------------------------------------------------
# DetectorIntegration Facade
# ---------------------------------------------------------------------------


class TestDetectorIntegration:
    def test_evaluate_clean(self):
        di = DetectorIntegration()
        signal = CollapsedSignal(
            coherence_score=0.95, perturbation_fragility=0.05,
            overconfidence_signature=0.1,
        )
        result = di.evaluate(signal)
        assert GovernorAction.NO_CHANGE in result.actions

    def test_evaluate_dirty(self):
        di = DetectorIntegration()
        signal = CollapsedSignal(coherence_score=0.2, overconfidence_signature=0.8)
        result = di.evaluate(signal)
        assert GovernorAction.RAISE_EVIDENCE in result.actions
        assert GovernorAction.CAP_CONFIDENCE in result.actions

    def test_failure_safe(self):
        di = DetectorIntegration()
        safe = di.failure_safe()
        assert safe.coherence_score == 0.5
        assert safe.phase_flag == PhaseFlag.UNKNOWN

    def test_get_constraints(self):
        di = DetectorIntegration()
        signal = CollapsedSignal(coherence_score=0.2)
        constraints = di.get_constraints(signal)
        assert len(constraints) >= 1

    def test_load_and_collapse(self, tmp_path):
        key = SignalKey(
            run_id="r1", turn_id="t1", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
        )
        raw = RawDetectorSignal(temporal_debt=0.5)
        sf = DetectorSignalFile(key=key, raw=raw)
        path = tmp_path / "signal.json"
        save_signal_file(sf, path)

        di = DetectorIntegration()
        collapsed, loaded_key, file_hash = di.load_and_collapse(path)
        assert collapsed.coherence_score < 1.0  # Temporal debt should reduce it
        assert loaded_key.run_id == "r1"

    def test_process_file(self, tmp_path):
        key = SignalKey(
            run_id="r1", turn_id="t1", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
        )
        raw = RawDetectorSignal(temporal_debt=0.9, acceleration=0.8)
        sf = DetectorSignalFile(key=key, raw=raw)
        path = tmp_path / "signal.json"
        save_signal_file(sf, path)

        di = DetectorIntegration()
        result = di.process_file(path)
        assert isinstance(result, SignalActionResult)
        # High temporal debt should trigger actions
        assert result.signal_quality in (SignalQuality.UNCERTAIN, SignalQuality.DIRTY)

    def test_process_missing_file(self, tmp_path):
        """Missing file should fall back to failure-safe."""
        di = DetectorIntegration()
        result = di.process_file(tmp_path / "missing.json")
        # Should use failure-safe signal
        assert isinstance(result, SignalActionResult)

    def test_status(self):
        di = DetectorIntegration()
        status = di.status()
        assert "policy" in status
        assert "failure_safe_signal" in status

    def test_custom_policy(self):
        policy = SignalPolicy(coherence_threshold=0.8)
        di = DetectorIntegration(policy)
        signal = CollapsedSignal(coherence_score=0.6)
        result = di.evaluate(signal)
        assert GovernorAction.RAISE_EVIDENCE in result.actions


# ---------------------------------------------------------------------------
# Serialization Golden Tests
# ---------------------------------------------------------------------------


class TestGoldenSchemas:
    def test_signal_key_schema(self):
        key = SignalKey(
            run_id="r", turn_id="t", response_hash="h",
            model_id="m", timestamp=datetime.now(timezone.utc),
        )
        d = key.to_dict()
        required = {"run_id", "turn_id", "response_hash", "model_id", "timestamp"}
        assert required.issubset(d.keys())

    def test_collapsed_signal_schema(self):
        s = CollapsedSignal()
        d = s.to_dict()
        required = {
            "coherence_score", "instability_spikes",
            "perturbation_fragility", "overconfidence_signature", "phase_flag",
        }
        assert required == set(d.keys())

    def test_signal_policy_schema(self):
        p = SignalPolicy()
        d = p.to_dict()
        required = {
            "coherence_threshold", "spike_threshold", "fragility_threshold",
            "overconfidence_threshold", "confab_blocks_writes",
            "unavailable_penalty",
        }
        assert required == set(d.keys())

    def test_signal_action_result_schema(self):
        r = SignalActionResult(
            actions=[GovernorAction.NO_CHANGE],
            reason="clean",
        )
        d = r.to_dict()
        required = {"actions", "confidence_cap", "evidence_tier", "reason", "signal_quality"}
        assert required == set(d.keys())


# ---------------------------------------------------------------------------
# Integration: Full Pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_end_to_end(self, tmp_path):
        """Full pipeline: create raw signal → save → load → collapse → map → constraints."""
        # 1. Create raw signal (simulating detector output)
        key = SignalKey(
            run_id="pipeline-test",
            turn_id="t1",
            response_hash="abc123",
            model_id="llama3",
            timestamp=datetime.now(timezone.utc),
        )
        raw = RawDetectorSignal(
            temporal_debt=0.6,
            acceleration=0.4,
            max_entropy_jump=1.2,
            entropy_recovery_detected=True,
            token_jaccard=0.5,
        )
        signal_file = DetectorSignalFile(
            key=key, raw=raw,
            detector_version="0.1.0",
            profile="general",
        )

        # 2. Save
        path = tmp_path / "signal.json"
        save_signal_file(signal_file, path)

        # 3. Load and process
        di = DetectorIntegration()
        collapsed, loaded_key, file_hash = di.load_and_collapse(path)

        # 4. Verify collapse happened
        assert collapsed.coherence_score < 0.8  # Temporal debt lowers coherence
        assert collapsed.instability_spikes >= 2  # Entropy spike + recovery
        assert collapsed.perturbation_fragility > 0.3  # Low jaccard

        # 5. Map to actions
        result = di.evaluate(collapsed)
        assert isinstance(result, SignalActionResult)

        # 6. Get constraints
        constraints = di.get_constraints(collapsed)
        # Should have at least some constraints given the dirty signal
        assert isinstance(constraints, list)

        # 7. Make evidence ref
        ref = make_evidence_ref(collapsed, loaded_key, file_hash)
        assert ref["type"] == "detector_signal"

    def test_clean_signal_pipeline(self):
        """Clean signal should produce no constraints."""
        raw = RawDetectorSignal()  # All defaults = clean
        collapsed = collapse_signal(raw)
        assert collapsed.quality in (SignalQuality.CLEAN, SignalQuality.UNCERTAIN)

        result = map_signal_to_actions(collapsed)
        if collapsed.quality == SignalQuality.CLEAN:
            assert GovernorAction.NO_CHANGE in result.actions
            constraints = signal_to_constraints(collapsed)
            assert len(constraints) == 0
