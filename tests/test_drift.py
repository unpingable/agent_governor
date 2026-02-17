# SPDX-License-Identifier: Apache-2.0
"""Tests for drift detection module (temporal asymmetry defense)."""

import json
import pytest

from governor.drift import (
    DriftFailureMode,
    DriftAlert,
    PremiseRecord,
    AgentActivity,
    DriftSignals,
    DriftThresholds,
    QuarantineConfig,
    PremiseQuarantine,
    DriftDetector,
    create_drift_detector,
    detect_drift,
)


# =============================================================================
# DriftFailureMode
# =============================================================================


class TestDriftFailureMode:
    def test_all_modes_defined(self):
        assert DriftFailureMode.ASYMMETRIC_PERSISTENCE == "asymmetric_persistence"
        assert DriftFailureMode.CLOCK_SKEW_DOMINANCE == "clock_skew_dominance"
        assert DriftFailureMode.PREMISE_RECURRENCE == "premise_recurrence"
        assert DriftFailureMode.ATTENTION_SKEW == "attention_skew"

    def test_all_list(self):
        assert len(DriftFailureMode.ALL) == 4
        assert DriftFailureMode.ASYMMETRIC_PERSISTENCE in DriftFailureMode.ALL


# =============================================================================
# DriftAlert
# =============================================================================


class TestDriftAlert:
    def test_all_levels_defined(self):
        assert DriftAlert.NONE == "none"
        assert DriftAlert.WATCH == "watch"
        assert DriftAlert.WARN == "warn"
        assert DriftAlert.QUARANTINE == "quarantine"

    def test_severity_ordering(self):
        assert DriftAlert.severity(DriftAlert.NONE) < DriftAlert.severity(DriftAlert.WATCH)
        assert DriftAlert.severity(DriftAlert.WATCH) < DriftAlert.severity(DriftAlert.WARN)
        assert DriftAlert.severity(DriftAlert.WARN) < DriftAlert.severity(DriftAlert.QUARANTINE)

    def test_severity_unknown(self):
        assert DriftAlert.severity("unknown") == 0

    def test_all_list(self):
        assert len(DriftAlert.ALL) == 4


# =============================================================================
# PremiseRecord
# =============================================================================


class TestPremiseRecord:
    def test_basic_creation(self):
        rec = PremiseRecord(
            content_hash="abc123",
            content_summary="Test premise",
            first_seen_turn=0,
            last_seen_turn=0,
        )
        assert rec.occurrences == 1
        assert rec.weight == 1.0
        assert not rec.quarantined
        assert not rec.resolved

    def test_turns_without_evidence_no_evidence(self):
        rec = PremiseRecord(
            content_hash="abc",
            content_summary="test",
            first_seen_turn=0,
            last_seen_turn=5,
        )
        assert rec.turns_without_evidence == 5

    def test_turns_without_evidence_with_evidence(self):
        rec = PremiseRecord(
            content_hash="abc",
            content_summary="test",
            first_seen_turn=0,
            last_seen_turn=10,
            evidence_at_turns=[3, 7],
        )
        assert rec.turns_without_evidence == 3  # 10 - 7

    def test_recurrence_rate(self):
        rec = PremiseRecord(
            content_hash="abc",
            content_summary="test",
            first_seen_turn=0,
            last_seen_turn=9,
            occurrences=5,
        )
        # 5 occurrences / 10 turn span = 0.5
        assert rec.recurrence_rate == 0.5

    def test_single_source_empty(self):
        rec = PremiseRecord(
            content_hash="abc",
            content_summary="test",
            first_seen_turn=0,
            last_seen_turn=0,
        )
        assert rec.single_source  # Empty = single source

    def test_single_source_one_agent(self):
        rec = PremiseRecord(
            content_hash="abc",
            content_summary="test",
            first_seen_turn=0,
            last_seen_turn=0,
            source_agents=["agent_a"],
        )
        assert rec.single_source

    def test_multi_source(self):
        rec = PremiseRecord(
            content_hash="abc",
            content_summary="test",
            first_seen_turn=0,
            last_seen_turn=0,
            source_agents=["agent_a", "agent_b"],
        )
        assert not rec.single_source

    def test_serialization(self):
        rec = PremiseRecord(
            content_hash="abc123",
            content_summary="Test",
            first_seen_turn=0,
            last_seen_turn=5,
            occurrences=3,
            evidence_at_turns=[2],
            source_agents=["agent_a"],
            quarantined=True,
            quarantined_at_turn=4,
            weight=0.1,
        )
        d = rec.to_dict()
        assert d["content_hash"] == "abc123"
        assert d["occurrences"] == 3
        assert d["quarantined"] is True

        rec2 = PremiseRecord.from_dict(d)
        assert rec2.content_hash == rec.content_hash
        assert rec2.occurrences == rec.occurrences
        assert rec2.quarantined == rec.quarantined
        assert rec2.weight == rec.weight


# =============================================================================
# AgentActivity
# =============================================================================


class TestAgentActivity:
    def test_basic_creation(self):
        a = AgentActivity(agent_id="agent_1")
        assert a.total_assertions == 0
        assert a.contested_ratio == 0.0
        assert a.topic_diversity == 0.0
        assert a.temporal_coherence == 0.0

    def test_contested_ratio(self):
        a = AgentActivity(
            agent_id="a",
            total_assertions=10,
            contested_assertions=3,
        )
        assert a.contested_ratio == pytest.approx(0.3)

    def test_topic_diversity(self):
        a = AgentActivity(
            agent_id="a",
            total_assertions=10,
            unique_topics={"auth", "api", "db"},
        )
        assert a.topic_diversity == pytest.approx(0.3)

    def test_temporal_coherence_all_same(self):
        a = AgentActivity(
            agent_id="a",
            output_hashes=["abc", "abc", "abc", "abc"],
        )
        # All same -> 1 unique / 4 total -> coherence = 1 - 0.25 = 0.75
        assert a.temporal_coherence == pytest.approx(0.75)

    def test_temporal_coherence_all_different(self):
        a = AgentActivity(
            agent_id="a",
            output_hashes=["a", "b", "c", "d"],
        )
        # All unique -> 4/4 -> coherence = 0.0
        assert a.temporal_coherence == pytest.approx(0.0)

    def test_temporal_coherence_too_few(self):
        a = AgentActivity(agent_id="a", output_hashes=["a"])
        assert a.temporal_coherence == 0.0

    def test_serialization(self):
        a = AgentActivity(
            agent_id="agent_1",
            total_assertions=5,
            contested_assertions=2,
            unique_topics={"auth", "db"},
            total_turns_active=3,
            output_hashes=["a", "b", "a"],
        )
        d = a.to_dict()
        assert d["agent_id"] == "agent_1"
        assert d["total_assertions"] == 5
        assert d["contested_ratio"] == pytest.approx(0.4)

        a2 = AgentActivity.from_dict(d)
        assert a2.agent_id == a.agent_id
        assert a2.total_assertions == a.total_assertions
        assert a2.unique_topics == a.unique_topics


# =============================================================================
# DriftSignals
# =============================================================================


class TestDriftSignals:
    def test_defaults(self):
        s = DriftSignals()
        assert s.premise_recurrence_rate == 0.0
        assert s.attention_skew == 0.0
        assert s.temporal_coherence_gradient == 0.0
        assert s.max_contradiction_age == 0

    def test_serialization(self):
        s = DriftSignals(
            premise_recurrence_rate=0.5,
            attention_skew=0.3,
            max_contradiction_age=7,
            single_source_rate=0.8,
        )
        d = s.to_dict()
        s2 = DriftSignals.from_dict(d)
        assert s2.premise_recurrence_rate == pytest.approx(0.5)
        assert s2.attention_skew == pytest.approx(0.3)
        assert s2.max_contradiction_age == 7
        assert s2.single_source_rate == pytest.approx(0.8)


# =============================================================================
# DriftThresholds
# =============================================================================


class TestDriftThresholds:
    def test_defaults(self):
        t = DriftThresholds()
        assert t.watch_recurrence_rate == 0.2
        assert t.warn_recurrence_rate == 0.4
        assert t.quarantine_recurrence_rate == 0.6

    def test_escalation(self):
        t = DriftThresholds()
        assert t.watch_recurrence_rate < t.warn_recurrence_rate
        assert t.warn_recurrence_rate < t.quarantine_recurrence_rate

    def test_serialization(self):
        t = DriftThresholds(watch_recurrence_rate=0.15)
        d = t.to_dict()
        t2 = DriftThresholds.from_dict(d)
        assert t2.watch_recurrence_rate == 0.15


# =============================================================================
# QuarantineConfig
# =============================================================================


class TestQuarantineConfig:
    def test_defaults(self):
        cfg = QuarantineConfig()
        assert cfg.recurrence_threshold == 3
        assert cfg.min_stale_turns == 3
        assert cfg.quarantine_weight == 0.1
        assert cfg.auto_release_turns == 10
        assert cfg.strict_single_source is True

    def test_serialization(self):
        cfg = QuarantineConfig(recurrence_threshold=5, quarantine_weight=0.2)
        d = cfg.to_dict()
        cfg2 = QuarantineConfig.from_dict(d)
        assert cfg2.recurrence_threshold == 5
        assert cfg2.quarantine_weight == 0.2


# =============================================================================
# PremiseQuarantine
# =============================================================================


class TestPremiseQuarantine:
    def test_record_new_premise(self):
        pq = PremiseQuarantine()
        rec = pq.record_premise("The sky is blue", agent_id="a1")
        assert rec.occurrences == 1
        assert rec.content_summary == "The sky is blue"
        assert not rec.quarantined

    def test_record_duplicate_increments(self):
        pq = PremiseQuarantine()
        pq.record_premise("The sky is blue", agent_id="a1")
        rec = pq.record_premise("The sky is blue", agent_id="a1")
        assert rec.occurrences == 2

    def test_case_insensitive_dedup(self):
        pq = PremiseQuarantine()
        pq.record_premise("The Sky Is Blue")
        rec = pq.record_premise("the sky is blue")
        assert rec.occurrences == 2

    def test_quarantine_after_threshold(self):
        """Premise quarantined after recurrence_threshold without evidence."""
        cfg = QuarantineConfig(
            recurrence_threshold=3,
            min_stale_turns=0,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A")
        pq.record_premise("claim A")
        rec = pq.record_premise("claim A")
        assert rec.quarantined
        assert rec.weight == 0.1

    def test_no_quarantine_with_evidence(self):
        """Evidence prevents quarantine when min_stale_turns requires freshness."""
        cfg = QuarantineConfig(
            recurrence_threshold=3,
            min_stale_turns=1,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A", has_evidence=True)
        pq.record_premise("claim A", has_evidence=True)
        rec = pq.record_premise("claim A", has_evidence=True)
        # Evidence at every turn -> turns_without_evidence = 0, which is < 1
        assert not rec.quarantined

    def test_quarantine_stale_turns(self):
        """Quarantine requires min_stale_turns without evidence."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=3,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        # Turn 0: first occurrence
        pq.record_premise("claim A")

        # Turn 1-3: advance without the premise
        pq.tick()
        pq.tick()
        pq.tick()

        # Turn 3: second occurrence, now stale (3 turns without evidence)
        rec = pq.record_premise("claim A")
        assert rec.quarantined

    def test_single_source_stricter(self):
        """Single-source premises get lower threshold."""
        cfg = QuarantineConfig(
            recurrence_threshold=5,
            single_source_recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=True,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A", agent_id="a1")
        rec = pq.record_premise("claim A", agent_id="a1")
        # Single source: threshold=2, occurrences=2 -> quarantined
        assert rec.quarantined

    def test_multi_source_normal_threshold(self):
        """Multi-source premises use normal threshold."""
        cfg = QuarantineConfig(
            recurrence_threshold=5,
            single_source_recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=True,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A", agent_id="a1")
        rec = pq.record_premise("claim A", agent_id="a2")
        # Multi source: threshold=5, occurrences=2 -> NOT quarantined
        assert not rec.quarantined

    def test_evidence_releases_quarantine(self):
        """Attaching evidence releases quarantine."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A")
        pq.record_premise("claim A")
        assert pq.get_weight("claim A") < 1.0

        pq.attach_evidence("claim A")
        assert pq.get_weight("claim A") == 1.0

    def test_resolution_releases_quarantine(self):
        """Resolving a premise releases quarantine."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A")
        pq.record_premise("claim A")
        assert pq.get_weight("claim A") < 1.0

        pq.resolve_premise("claim A")
        assert pq.get_weight("claim A") == 1.0

    def test_auto_release_after_silence(self):
        """Quarantined premises auto-release after silence."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            auto_release_turns=5,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A")
        pq.record_premise("claim A")
        assert pq.get_weight("claim A") < 1.0

        # Advance 5 turns without repeating
        for _ in range(5):
            pq.tick()

        assert pq.get_weight("claim A") == 1.0

    def test_get_weight_unknown_premise(self):
        pq = PremiseQuarantine()
        assert pq.get_weight("never seen") == 1.0

    def test_metrics(self):
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A")
        pq.record_premise("claim A")
        pq.record_premise("claim B")

        m = pq.get_metrics()
        assert m["total_premises"] == 2
        assert m["quarantined_premises"] == 1
        assert m["total_quarantined_ever"] == 1

    def test_recurring_premises_query(self):
        pq = PremiseQuarantine()
        pq.record_premise("claim A")
        pq.record_premise("claim A")
        pq.record_premise("claim B")

        recurring = pq.recurring_premises(min_occurrences=2)
        assert len(recurring) == 1
        assert recurring[0].content_summary.startswith("claim A")

    def test_stale_premises_query(self):
        pq = PremiseQuarantine()
        pq.record_premise("claim A")

        for _ in range(5):
            pq.tick()

        # Re-assert at turn 5 so last_seen_turn updates
        # (turns_without_evidence is relative to last_seen_turn)
        pq.record_premise("claim A")

        stale = pq.stale_premises(min_stale_turns=3)
        assert len(stale) == 1

    def test_serialization(self):
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A", agent_id="a1")
        pq.record_premise("claim A", agent_id="a1")
        pq.tick()

        d = pq.to_dict()
        pq2 = PremiseQuarantine.from_dict(d)
        assert pq2.turn == pq.turn
        assert pq2.total_quarantined == pq.total_quarantined
        assert len(pq2.premises) == len(pq.premises)
        assert pq2.config.recurrence_threshold == 2

    def test_attach_evidence_unknown_premise(self):
        pq = PremiseQuarantine()
        assert pq.attach_evidence("unknown") is False

    def test_resolve_unknown_premise(self):
        pq = PremiseQuarantine()
        assert pq.resolve_premise("unknown") is False

    def test_resolved_premise_not_requarantined(self):
        """Resolved premises don't get quarantined again."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        pq = PremiseQuarantine(config=cfg)

        pq.record_premise("claim A")
        pq.record_premise("claim A")  # triggers quarantine
        pq.resolve_premise("claim A")

        # Record again — should NOT quarantine since resolved
        rec = pq.record_premise("claim A")
        assert not rec.quarantined


# =============================================================================
# DriftDetector - Basic
# =============================================================================


class TestDriftDetectorBasic:
    def test_creation(self):
        dd = DriftDetector()
        assert dd.current_alert == DriftAlert.NONE
        assert dd.turn == 0

    def test_tick(self):
        dd = DriftDetector()
        dd.tick()
        assert dd.turn == 1

    def test_record_assertion(self):
        dd = DriftDetector()
        rec = dd.record_assertion("claim A", agent_id="a1")
        assert rec.occurrences == 1

    def test_record_assertion_tracks_agent(self):
        dd = DriftDetector()
        dd.record_assertion("claim A", agent_id="a1", contested=True, topic="auth")
        activity = dd.get_agent_activity("a1")
        assert activity is not None
        assert activity.total_assertions == 1
        assert activity.contested_assertions == 1
        assert "auth" in activity.unique_topics

    def test_record_evidence(self):
        dd = DriftDetector()
        dd.record_assertion("claim A")
        assert dd.record_evidence("claim A") is True
        assert dd.record_evidence("unknown") is False

    def test_record_resolution(self):
        dd = DriftDetector()
        dd.record_assertion("claim A")
        dd.record_contradiction("claim A")
        assert dd.record_resolution("claim A") is True

    def test_record_contradiction(self):
        dd = DriftDetector()
        dd.record_contradiction("issue X")
        assert len(dd.unresolved_contradictions) == 1

    def test_resolve_contradiction(self):
        dd = DriftDetector()
        dd.record_contradiction("issue X")
        assert dd.resolve_contradiction("issue X") is True
        assert len(dd.unresolved_contradictions) == 0

    def test_resolve_unknown_contradiction(self):
        dd = DriftDetector()
        assert dd.resolve_contradiction("unknown") is False


# =============================================================================
# DriftDetector - Signal Computation
# =============================================================================


class TestDriftDetectorSignals:
    def test_empty_signals(self):
        dd = DriftDetector()
        signals = dd.compute_signals()
        assert signals.premise_recurrence_rate == 0.0
        assert signals.attention_skew == 0.0
        assert signals.temporal_coherence_gradient == 0.0
        assert signals.max_contradiction_age == 0

    def test_recurrence_rate(self):
        dd = DriftDetector()
        # Record claim A multiple times across turns
        dd.record_assertion("claim A")
        dd.tick()
        dd.tick()
        dd.record_assertion("claim A")
        dd.tick()
        dd.record_assertion("claim B")  # Not recurring

        signals = dd.compute_signals()
        # 1 recurring (A: 2 occ, 3 turns without evidence) out of 2 active
        assert signals.premise_recurrence_rate == pytest.approx(0.5)

    def test_attention_skew(self):
        dd = DriftDetector()
        # Agent a1: all contested
        dd.record_assertion("c1", agent_id="a1", contested=True)
        dd.record_assertion("c2", agent_id="a1", contested=True)
        # Agent a2: none contested
        dd.record_assertion("c3", agent_id="a2", contested=False)
        dd.record_assertion("c4", agent_id="a2", contested=False)

        signals = dd.compute_signals()
        assert signals.attention_skew == pytest.approx(1.0)

    def test_temporal_coherence_gradient(self):
        dd = DriftDetector(max_output_hashes=10)
        # Agent a1: repeats same content (high coherence)
        for i in range(5):
            dd.record_assertion("same claim", agent_id="a1")
        # Agent a2: varied content (low coherence)
        for i in range(5):
            dd.record_assertion(f"different claim {i}", agent_id="a2")

        signals = dd.compute_signals()
        assert signals.temporal_coherence_gradient > 0.0

    def test_contradiction_age(self):
        dd = DriftDetector()
        dd.record_contradiction("issue A")
        dd.tick()
        dd.tick()
        dd.tick()
        dd.record_contradiction("issue B")

        signals = dd.compute_signals()
        assert signals.max_contradiction_age == 3  # issue A: 3 turns old
        assert signals.avg_contradiction_age == 1.5  # (3 + 0) / 2

    def test_quarantine_in_signals(self):
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)
        dd.record_assertion("claim A")
        dd.record_assertion("claim A")  # triggers quarantine

        signals = dd.compute_signals()
        assert signals.quarantined_premises == 1

    def test_single_source_rate(self):
        dd = DriftDetector()
        # Two recurring premises, both single-source
        dd.record_assertion("claim A", agent_id="a1")
        dd.tick()
        dd.tick()
        dd.record_assertion("claim A", agent_id="a1")
        dd.record_assertion("claim B", agent_id="a2")
        dd.tick()
        dd.tick()
        dd.record_assertion("claim B", agent_id="a2")

        signals = dd.compute_signals()
        assert signals.single_source_rate == pytest.approx(1.0)


# =============================================================================
# DriftDetector - Classification
# =============================================================================


class TestDriftDetectorClassification:
    def test_nominal_is_none(self):
        dd = DriftDetector()
        signals = DriftSignals()
        alert, reasons, modes = dd.classify(signals)
        assert alert == DriftAlert.NONE
        assert "all signals nominal" in reasons

    def test_watch_on_recurrence(self):
        dd = DriftDetector()
        signals = DriftSignals(premise_recurrence_rate=0.25)
        alert, reasons, modes = dd.classify(signals)
        assert alert == DriftAlert.WATCH

    def test_watch_on_attention_skew(self):
        dd = DriftDetector()
        signals = DriftSignals(attention_skew=0.35)
        alert, _, _ = dd.classify(signals)
        assert alert == DriftAlert.WATCH

    def test_watch_on_coherence_gradient(self):
        dd = DriftDetector()
        signals = DriftSignals(temporal_coherence_gradient=0.35)
        alert, _, _ = dd.classify(signals)
        assert alert == DriftAlert.WATCH

    def test_watch_on_contradiction_age(self):
        dd = DriftDetector()
        signals = DriftSignals(max_contradiction_age=6)
        alert, _, _ = dd.classify(signals)
        assert alert == DriftAlert.WATCH

    def test_warn_on_high_recurrence(self):
        dd = DriftDetector()
        signals = DriftSignals(premise_recurrence_rate=0.45)
        alert, _, modes = dd.classify(signals)
        assert alert == DriftAlert.WARN
        assert DriftFailureMode.PREMISE_RECURRENCE in modes

    def test_warn_on_single_source(self):
        dd = DriftDetector()
        signals = DriftSignals(single_source_rate=0.65)
        alert, _, modes = dd.classify(signals)
        assert alert == DriftAlert.WARN
        assert DriftFailureMode.ASYMMETRIC_PERSISTENCE in modes

    def test_quarantine_on_extreme_recurrence(self):
        dd = DriftDetector()
        signals = DriftSignals(premise_recurrence_rate=0.7)
        alert, _, _ = dd.classify(signals)
        assert alert == DriftAlert.QUARANTINE

    def test_quarantine_on_extreme_attention(self):
        dd = DriftDetector()
        signals = DriftSignals(attention_skew=0.8)
        alert, _, _ = dd.classify(signals)
        assert alert == DriftAlert.QUARANTINE

    def test_quarantine_on_old_contradictions(self):
        dd = DriftDetector()
        signals = DriftSignals(max_contradiction_age=25)
        alert, _, _ = dd.classify(signals)
        assert alert == DriftAlert.QUARANTINE

    def test_failure_modes_detected(self):
        dd = DriftDetector()
        signals = DriftSignals(
            premise_recurrence_rate=0.7,
            attention_skew=0.8,
        )
        _, _, modes = dd.classify(signals)
        assert DriftFailureMode.PREMISE_RECURRENCE in modes
        assert DriftFailureMode.ATTENTION_SKEW in modes

    def test_clock_skew_mode_on_coherence(self):
        dd = DriftDetector()
        signals = DriftSignals(temporal_coherence_gradient=0.75)
        _, _, modes = dd.classify(signals)
        assert DriftFailureMode.CLOCK_SKEW_DOMINANCE in modes


# =============================================================================
# DriftDetector - Update & History
# =============================================================================


class TestDriftDetectorUpdate:
    def test_update_returns_alert(self):
        dd = DriftDetector()
        alert, signals, reasons = dd.update()
        assert alert == DriftAlert.NONE

    def test_update_records_history(self):
        """Alert transitions are recorded in history."""
        dd = DriftDetector(
            thresholds=DriftThresholds(watch_contradiction_age=1),
        )

        # Start at NONE
        dd.update()

        # Add old contradiction -> should trigger WATCH
        dd.record_contradiction("issue A")
        dd.tick()
        dd.tick()
        alert, _, _ = dd.update()
        assert alert == DriftAlert.WATCH
        assert len(dd.alert_history) >= 1

    def test_update_records_modes(self):
        dd = DriftDetector(
            thresholds=DriftThresholds(watch_contradiction_age=1),
        )
        dd.record_contradiction("issue A")
        dd.tick()
        dd.tick()
        dd.update()
        # Contradiction age doesn't map to a specific failure mode
        # but recurrence/attention/coherence do

    def test_stable_alert_no_duplicate_history(self):
        """Same alert level doesn't add to history repeatedly."""
        dd = DriftDetector()
        dd.update()
        dd.update()
        dd.update()
        # All NONE -> only first transition (from implicit start) if any
        # Actually, NONE == NONE so no transitions recorded
        assert len(dd.alert_history) == 0


# =============================================================================
# DriftDetector - Queries
# =============================================================================


class TestDriftDetectorQueries:
    def test_get_premise_weight(self):
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)
        dd.record_assertion("claim A")
        dd.record_assertion("claim A")
        assert dd.get_premise_weight("claim A") == pytest.approx(0.1)

    def test_is_quarantined(self):
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)
        dd.record_assertion("claim A")
        dd.record_assertion("claim A")
        assert dd.is_quarantined("claim A") is True
        assert dd.is_quarantined("unknown") is False

    def test_get_agent_activity(self):
        dd = DriftDetector()
        dd.record_assertion("c1", agent_id="a1")
        assert dd.get_agent_activity("a1") is not None
        assert dd.get_agent_activity("unknown") is None

    def test_get_suspicious_agents(self):
        dd = DriftDetector()
        # Agent a1: heavily contested
        for i in range(5):
            dd.record_assertion(f"contested_{i}", agent_id="a1", contested=True)
        # Agent a2: not contested
        for i in range(5):
            dd.record_assertion(f"normal_{i}", agent_id="a2", contested=False)

        suspicious = dd.get_suspicious_agents(min_contested_ratio=0.5)
        assert len(suspicious) == 1
        assert suspicious[0].agent_id == "a1"

    def test_suspicious_agents_min_sample(self):
        """Agents with too few assertions aren't flagged."""
        dd = DriftDetector()
        dd.record_assertion("c1", agent_id="a1", contested=True)
        dd.record_assertion("c2", agent_id="a1", contested=True)
        # Only 2 assertions, below min_sample of 3
        suspicious = dd.get_suspicious_agents()
        assert len(suspicious) == 0

    def test_diagnostics(self):
        dd = DriftDetector()
        dd.record_assertion("claim A", agent_id="a1")
        dd.record_contradiction("issue X")

        diag = dd.get_diagnostics()
        assert "turn" in diag
        assert "alert_level" in diag
        assert "signals" in diag
        assert "quarantine" in diag
        assert "agents" in diag
        assert diag["unresolved_contradictions"] == 1


# =============================================================================
# DriftDetector - Serialization
# =============================================================================


class TestDriftDetectorSerialization:
    def test_roundtrip(self):
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        dd = DriftDetector(
            quarantine_config=cfg,
            max_output_hashes=15,
        )

        dd.record_assertion("claim A", agent_id="a1", contested=True)
        dd.record_assertion("claim A", agent_id="a1")
        dd.record_contradiction("issue X")
        dd.tick()
        dd.update()

        d = dd.to_dict()
        dd2 = DriftDetector.from_dict(d)

        assert dd2.turn == dd.turn
        assert dd2.current_alert == dd.current_alert
        assert dd2.max_output_hashes == 15
        assert len(dd2.quarantine.premises) == len(dd.quarantine.premises)
        assert len(dd2.agents) == len(dd.agents)
        assert len(dd2.unresolved_contradictions) == len(dd.unresolved_contradictions)

    def test_json_serializable(self):
        dd = DriftDetector()
        dd.record_assertion("test", agent_id="a1")
        dd.update()
        d = dd.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        assert json_str

    def test_empty_roundtrip(self):
        dd = DriftDetector()
        d = dd.to_dict()
        dd2 = DriftDetector.from_dict(d)
        assert dd2.current_alert == DriftAlert.NONE
        assert dd2.turn == 0


# =============================================================================
# DriftDetector - Adversarial Scenarios
# =============================================================================


class TestDriftDetectorAdversarial:
    def test_slow_premise_escalation(self):
        """A premise repeated slowly over many turns triggers eventually."""
        dd = DriftDetector(
            thresholds=DriftThresholds(watch_recurrence_rate=0.2),
        )

        # Record same premise every 3 turns
        for i in range(15):
            if i % 3 == 0:
                dd.record_assertion("persistent claim", agent_id="steerer")
            dd.tick()

        alert, signals, _ = dd.update()
        # The persistent claim should be recurring
        rec = list(dd.quarantine.premises.values())[0]
        assert rec.occurrences == 5

    def test_single_agent_dominance(self):
        """One agent making all contested assertions is detected."""
        dd = DriftDetector()

        # Agent a1: all contested
        for i in range(10):
            dd.record_assertion(
                f"claim_{i}", agent_id="a1", contested=True, topic="drift"
            )
        # Agent a2: normal behavior
        for i in range(10):
            dd.record_assertion(
                f"normal_{i}", agent_id="a2", contested=False, topic=f"topic_{i}"
            )

        signals = dd.compute_signals()
        assert signals.attention_skew == 1.0  # a1 is 100% contested

    def test_evidence_defuses_drift(self):
        """Providing evidence for recurring premises defuses drift signals."""
        cfg = QuarantineConfig(
            recurrence_threshold=3,
            min_stale_turns=0,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)

        # Record premise 3 times -> quarantined
        dd.record_assertion("drift claim")
        dd.record_assertion("drift claim")
        dd.record_assertion("drift claim")
        assert dd.is_quarantined("drift claim")

        # Attach evidence -> released
        dd.record_evidence("drift claim")
        assert not dd.is_quarantined("drift claim")

    def test_contradiction_staleness(self):
        """Unresolved contradictions age correctly."""
        dd = DriftDetector()
        dd.record_contradiction("issue A")

        for _ in range(10):
            dd.tick()

        signals = dd.compute_signals()
        assert signals.max_contradiction_age == 10

    def test_temporal_coherence_fingerprint(self):
        """Agent repeating same message has high coherence."""
        dd = DriftDetector(max_output_hashes=10)

        # Steerer: repeats same premise
        for _ in range(8):
            dd.record_assertion("the answer is 42", agent_id="steerer")

        # Normal agent: diverse output
        for i in range(8):
            dd.record_assertion(f"analysis result {i}", agent_id="normal")

        steerer = dd.get_agent_activity("steerer")
        normal = dd.get_agent_activity("normal")
        assert steerer.temporal_coherence > normal.temporal_coherence

        signals = dd.compute_signals()
        assert signals.temporal_coherence_gradient > 0.5

    def test_mixed_attack_escalation(self):
        """Multiple drift signals combine for higher alert level."""
        dd = DriftDetector(
            thresholds=DriftThresholds(
                warn_recurrence_rate=0.3,
                warn_attention_skew=0.4,
            ),
        )

        # Premise recurrence
        dd.record_assertion("recurring claim", agent_id="a1")
        dd.tick()
        dd.tick()
        dd.record_assertion("recurring claim", agent_id="a1")

        # Contested assertions
        for i in range(5):
            dd.record_assertion(f"fight_{i}", agent_id="a1", contested=True)

        # Old contradictions
        dd.record_contradiction("stale issue")
        for _ in range(12):
            dd.tick()

        alert, signals, reasons = dd.update()
        # Should be at least WATCH level
        assert DriftAlert.severity(alert) >= DriftAlert.severity(DriftAlert.WATCH)


# =============================================================================
# DriftDetector - Integration with quarantine
# =============================================================================


class TestDriftDetectorIntegration:
    def test_full_lifecycle(self):
        """Test complete lifecycle: detect -> quarantine -> evidence -> release."""
        cfg = QuarantineConfig(
            recurrence_threshold=3,
            min_stale_turns=2,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)

        # Phase 1: premise appears, no concern
        dd.record_assertion("framework X is best")
        dd.tick()
        assert not dd.is_quarantined("framework X is best")

        # Phase 2: premise recurs without evidence
        dd.tick()
        dd.record_assertion("framework X is best")
        dd.tick()
        dd.tick()
        dd.record_assertion("framework X is best")

        # Should now be quarantined (3 occ, 4 turns without evidence)
        assert dd.is_quarantined("framework X is best")
        assert dd.get_premise_weight("framework X is best") == pytest.approx(0.1)

        # Phase 3: evidence provided -> released
        dd.record_evidence("framework X is best")
        assert not dd.is_quarantined("framework X is best")
        assert dd.get_premise_weight("framework X is best") == pytest.approx(1.0)

    def test_resolution_clears_contradiction_and_quarantine(self):
        """Resolution clears both quarantine and contradiction tracking."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)

        dd.record_assertion("disputed claim")
        dd.record_assertion("disputed claim")
        dd.record_contradiction("disputed claim")

        assert dd.is_quarantined("disputed claim")
        assert len(dd.unresolved_contradictions) == 1

        dd.record_resolution("disputed claim")
        assert not dd.is_quarantined("disputed claim")
        assert len(dd.unresolved_contradictions) == 0

    def test_auto_release_integration(self):
        """Auto-release works through the detector interface."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            auto_release_turns=3,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)

        dd.record_assertion("noisy claim")
        dd.record_assertion("noisy claim")
        assert dd.is_quarantined("noisy claim")

        dd.tick()
        dd.tick()
        dd.tick()
        assert not dd.is_quarantined("noisy claim")


# =============================================================================
# Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    def test_create_drift_detector(self):
        dd = create_drift_detector(
            quarantine_threshold=5,
            quarantine_weight=0.2,
        )
        assert dd.quarantine.config.recurrence_threshold == 5
        assert dd.quarantine.config.quarantine_weight == 0.2

    def test_create_drift_detector_defaults(self):
        dd = create_drift_detector()
        assert dd.quarantine.config.recurrence_threshold == 3
        assert dd.quarantine.config.strict_single_source is True

    def test_detect_drift_convenience(self):
        dd = create_drift_detector()
        alert, weight = detect_drift(dd, "test claim", agent_id="a1")
        assert alert == DriftAlert.NONE
        assert weight == 1.0

    def test_detect_drift_escalation(self):
        """detect_drift convenience function tracks state across calls."""
        cfg = QuarantineConfig(
            recurrence_threshold=2,
            min_stale_turns=0,
            strict_single_source=False,
        )
        dd = DriftDetector(quarantine_config=cfg)

        alert1, w1 = detect_drift(dd, "repeated claim")
        assert w1 == 1.0

        alert2, w2 = detect_drift(dd, "repeated claim")
        assert w2 == pytest.approx(0.1)  # Quarantined


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_empty_content(self):
        dd = DriftDetector()
        rec = dd.record_assertion("")
        assert rec.content_summary == ""

    def test_very_long_content(self):
        dd = DriftDetector()
        long_content = "x" * 1000
        rec = dd.record_assertion(long_content)
        assert len(rec.content_summary) <= 80

    def test_no_agents_registered(self):
        dd = DriftDetector()
        signals = dd.compute_signals()
        assert signals.attention_skew == 0.0
        assert signals.temporal_coherence_gradient == 0.0

    def test_single_agent_no_gradient(self):
        """One agent can't produce a coherence gradient."""
        dd = DriftDetector()
        for i in range(5):
            dd.record_assertion("same", agent_id="solo")
        signals = dd.compute_signals()
        assert signals.temporal_coherence_gradient == 0.0

    def test_output_hash_window(self):
        """Output hashes are capped at max_output_hashes."""
        dd = DriftDetector(max_output_hashes=5)
        for i in range(20):
            dd.record_assertion(f"msg_{i}", agent_id="a1")
        activity = dd.get_agent_activity("a1")
        assert len(activity.output_hashes) == 5

    def test_whitespace_normalization(self):
        """Content hashing normalizes whitespace."""
        dd = DriftDetector()
        dd.record_assertion("  claim A  ")
        rec = dd.record_assertion("claim a")
        assert rec.occurrences == 2  # Same hash
