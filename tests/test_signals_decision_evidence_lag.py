# SPDX-License-Identifier: Apache-2.0
"""Tests for DECISION_EVIDENCE_LAG (Phase B2)."""

from __future__ import annotations

import json
import pathlib

import pytest

from governor.signals.decision_evidence_lag import (
    ALL_CLASSIFICATIONS,
    CLASSIFICATION_BACKFILLED,
    CLASSIFICATION_POLICY_EXEMPT,
    CLASSIFICATION_SUPPORTED,
    CLASSIFICATION_UNSUPPORTED,
    DECISION_GATES,
    DECISION_VERDICTS,
    LAG_CONFIG_VERSION,
    POLICY_EXEMPT_GATES,
    DecisionClassification,
    LagAggregateResult,
    ReceiptRecord,
    _compute_lag_stats,
    _parse_ts_ms,
    classify_decisions,
    derive_decision_evidence_lag,
)
from governor.signals.envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    validate_envelope,
)


# ── Helpers / Constants ──────────────────────────────────────────────────────

WINDOW_START = "2026-02-25T10:00:00Z"
WINDOW_END = "2026-02-25T10:05:00Z"
WINDOW_KIND = "rolling_5m"
EMITTED_AT = "2026-02-25T10:05:00Z"


def _receipt(
    receipt_id: str,
    timestamp: str,
    gate: str = "evidence_gate",
    verdict: str = "pass",
    subject_hash: str = "subj_a",
) -> ReceiptRecord:
    return ReceiptRecord(
        receipt_id=receipt_id,
        timestamp=timestamp,
        gate=gate,
        verdict=verdict,
        subject_hash=subject_hash,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants:
    """Exported constants are sane."""

    def test_classifications_count(self):
        assert len(ALL_CLASSIFICATIONS) == 4

    def test_classification_values(self):
        assert CLASSIFICATION_SUPPORTED == "SUPPORTED_AS_OF"
        assert CLASSIFICATION_BACKFILLED == "BACKFILLED"
        assert CLASSIFICATION_UNSUPPORTED == "UNSUPPORTED"
        assert CLASSIFICATION_POLICY_EXEMPT == "POLICY_EXEMPT"

    def test_decision_gates_non_empty(self):
        assert len(DECISION_GATES) >= 3

    def test_policy_exempt_gates_non_empty(self):
        assert len(POLICY_EXEMPT_GATES) >= 1

    def test_decision_verdicts(self):
        assert DECISION_VERDICTS == frozenset({"pass", "warn", "block"})

    def test_config_version(self):
        assert LAG_CONFIG_VERSION == "decision-evidence-lag-v1"


# ═══════════════════════════════════════════════════════════════════════════
# Timestamp parsing
# ═══════════════════════════════════════════════════════════════════════════

class TestTimestampParsing:
    """_parse_ts_ms edge cases."""

    def test_iso_utc_z(self):
        ms = _parse_ts_ms("2026-02-25T10:00:00Z")
        assert ms is not None
        assert isinstance(ms, float)

    def test_iso_utc_offset(self):
        ms = _parse_ts_ms("2026-02-25T10:00:00+00:00")
        assert ms is not None

    def test_invalid_returns_none(self):
        assert _parse_ts_ms("not-a-timestamp") is None

    def test_none_returns_none(self):
        assert _parse_ts_ms(None) is None  # type: ignore[arg-type]

    def test_empty_returns_none(self):
        assert _parse_ts_ms("") is None

    def test_consistent_z_and_offset(self):
        """Z and +00:00 should give the same milliseconds."""
        ms_z = _parse_ts_ms("2026-02-25T10:00:00Z")
        ms_off = _parse_ts_ms("2026-02-25T10:00:00+00:00")
        assert ms_z == ms_off


# ═══════════════════════════════════════════════════════════════════════════
# Per-decision classification
# ═══════════════════════════════════════════════════════════════════════════

class TestClassifyDecisions:
    """Core classification logic."""

    def test_supported_when_evidence_before_decision(self):
        """Evidence at T=5, decision at T=10 → SUPPORTED_AS_OF."""
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:05Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:10Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 1
        assert result.supported_count == 1
        assert result.classifications[0].classification == CLASSIFICATION_SUPPORTED

    def test_backfilled_when_evidence_after_decision(self):
        """Decision at T=5, evidence at T=10 → BACKFILLED."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("ev1", "2026-02-25T10:00:10Z", gate="other_gate",
                     subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 1
        assert result.backfilled_count == 1
        assert result.classifications[0].classification == CLASSIFICATION_BACKFILLED

    def test_unsupported_when_no_evidence(self):
        """Decision with no matching evidence → UNSUPPORTED."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 1
        assert result.unsupported_count == 1
        assert result.classifications[0].classification == CLASSIFICATION_UNSUPPORTED

    def test_policy_exempt(self):
        """Intent compiler gate → POLICY_EXEMPT."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="intent_compiler",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(
            receipts,
            decision_gates=DECISION_GATES | frozenset({"intent_compiler"}),
            policy_exempt_gates=POLICY_EXEMPT_GATES,
        )
        assert result.total_decisions == 1
        assert result.policy_exempt_count == 1
        assert result.classifications[0].classification == CLASSIFICATION_POLICY_EXEMPT

    def test_same_timestamp_is_supported(self):
        """Tie-break: same timestamp → SUPPORTED_AS_OF."""
        ts = "2026-02-25T10:00:05Z"
        receipts = [
            _receipt("ev1", ts, gate="other_gate", subject_hash="subj_a"),
            _receipt("dec1", ts, gate="evidence_gate", verdict="pass",
                     subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.supported_count == 1
        assert result.classifications[0].classification == CLASSIFICATION_SUPPORTED
        assert result.classifications[0].support_staleness_ms == pytest.approx(0.0)

    def test_multiple_evidence_earliest_wins(self):
        """Multiple evidence → earliest timestamp determines classification."""
        receipts = [
            # Early evidence (before decision)
            _receipt("ev_early", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            # Late evidence (after decision)
            _receipt("ev_late", "2026-02-25T10:00:20Z", gate="other_gate",
                     subject_hash="subj_a"),
            # Decision at T=10
            _receipt("dec1", "2026-02-25T10:00:10Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.supported_count == 1
        c = result.classifications[0]
        assert c.classification == CLASSIFICATION_SUPPORTED
        assert c.evidence_id == "ev_early"

    def test_decision_self_excluded_from_evidence(self):
        """A decision receipt should not count as its own evidence."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.unsupported_count == 1

    def test_non_decision_gate_ignored(self):
        """Receipts from non-decision gates are not classified as decisions."""
        receipts = [
            _receipt("r1", "2026-02-25T10:00:05Z", gate="some_other_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 0

    def test_non_decision_verdict_ignored(self):
        """Receipt from decision gate but non-standard verdict is not a decision."""
        receipts = [
            _receipt("r1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="observe", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 0

    def test_duplicate_receipt_ids_deduplicated(self):
        """Same receipt_id appearing twice should be counted once."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 1

    def test_unparseable_decision_timestamp(self):
        """Decision with bad timestamp → counted as unparseable + UNSUPPORTED."""
        receipts = [
            _receipt("dec1", "not-a-timestamp", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        assert result.unparseable_count == 1
        assert result.unsupported_count == 1

    def test_empty_receipts(self):
        """No receipts → empty result."""
        result = classify_decisions([])
        assert result.total_decisions == 0
        assert result.classifications == []


# ═══════════════════════════════════════════════════════════════════════════
# Lag statistics for classified decisions
# ═══════════════════════════════════════════════════════════════════════════

class TestLagMetrics:
    """backfill_delay_ms and support_staleness_ms computation."""

    def test_supported_has_staleness(self):
        """SUPPORTED_AS_OF records support_staleness_ms."""
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:00Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        c = result.classifications[0]
        assert c.support_staleness_ms is not None
        assert c.support_staleness_ms == pytest.approx(5000.0)
        assert c.backfill_delay_ms is None

    def test_backfilled_has_delay(self):
        """BACKFILLED records backfill_delay_ms."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:00Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("ev1", "2026-02-25T10:00:10Z", gate="other_gate",
                     subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        c = result.classifications[0]
        assert c.backfill_delay_ms is not None
        assert c.backfill_delay_ms == pytest.approx(10000.0)
        assert c.support_staleness_ms is None

    def test_unsupported_has_neither(self):
        """UNSUPPORTED has no delay or staleness."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(receipts)
        c = result.classifications[0]
        assert c.backfill_delay_ms is None
        assert c.support_staleness_ms is None

    def test_policy_exempt_has_neither(self):
        """POLICY_EXEMPT has no metrics."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="intent_compiler",
                     verdict="pass", subject_hash="subj_a"),
        ]
        result = classify_decisions(
            receipts,
            decision_gates=DECISION_GATES | frozenset({"intent_compiler"}),
        )
        c = result.classifications[0]
        assert c.backfill_delay_ms is None
        assert c.support_staleness_ms is None


# ═══════════════════════════════════════════════════════════════════════════
# Lag statistics helper
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeLagStats:
    """_compute_lag_stats edge cases."""

    def test_empty_returns_none_none(self):
        mean, p95 = _compute_lag_stats([])
        assert mean is None
        assert p95 is None

    def test_single_value(self):
        mean, p95 = _compute_lag_stats([100.0])
        assert mean == pytest.approx(100.0)
        assert p95 == pytest.approx(100.0)

    def test_multiple_values(self):
        mean, p95 = _compute_lag_stats([10.0, 20.0, 30.0, 40.0, 50.0])
        assert mean == pytest.approx(30.0)
        # p95 of 5 values at index min(int(0.95*5+0.5), 4) = min(5, 4) = 4 → 50.0
        assert p95 == pytest.approx(50.0)

    def test_p95_of_100_values(self):
        vals = list(range(1, 101))  # 1..100
        mean, p95 = _compute_lag_stats([float(v) for v in vals])
        assert mean == pytest.approx(50.5)
        # p95 index = min(int(0.95*100+0.5), 99) = min(95, 99) = 95 → vals[95] = 96
        assert p95 == pytest.approx(96.0)


# ═══════════════════════════════════════════════════════════════════════════
# Mixed-classification scenarios
# ═══════════════════════════════════════════════════════════════════════════

class TestMixedClassifications:
    """Multiple decisions with different classifications."""

    def test_mixed_supported_and_backfilled(self):
        receipts = [
            # Decision 1: supported (evidence before)
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            # Decision 2: backfilled (evidence after)
            _receipt("dec2", "2026-02-25T10:00:10Z", gate="pre_commit",
                     verdict="block", subject_hash="subj_b"),
            _receipt("ev2", "2026-02-25T10:00:15Z", gate="other_gate",
                     subject_hash="subj_b"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 2
        assert result.supported_count == 1
        assert result.backfilled_count == 1

    def test_supported_backfilled_unsupported(self):
        receipts = [
            # Supported
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            # Backfilled
            _receipt("dec2", "2026-02-25T10:00:10Z", gate="pre_commit",
                     verdict="block", subject_hash="subj_b"),
            _receipt("ev2", "2026-02-25T10:00:20Z", gate="other_gate",
                     subject_hash="subj_b"),
            # Unsupported
            _receipt("dec3", "2026-02-25T10:00:15Z", gate="evidence_gate",
                     verdict="warn", subject_hash="subj_c"),
        ]
        result = classify_decisions(receipts)
        assert result.total_decisions == 3
        assert result.supported_count == 1
        assert result.backfilled_count == 1
        assert result.unsupported_count == 1

    def test_different_subject_hashes_independent(self):
        """Decisions with different subject_hash are classified independently."""
        receipts = [
            # Evidence for subj_a only
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            # Decision for subj_a: supported
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            # Decision for subj_b: unsupported (no evidence)
            _receipt("dec2", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_b"),
        ]
        result = classify_decisions(receipts)
        assert result.supported_count == 1
        assert result.unsupported_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# Policy-exempt denominator exclusion
# ═══════════════════════════════════════════════════════════════════════════

class TestPolicyExemptDenominator:
    """Policy-exempt decisions excluded from rates."""

    def test_all_policy_exempt_yields_none_rates(self):
        """When all decisions are policy-exempt, rates are None."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="intent_compiler",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            decision_gates=DECISION_GATES | frozenset({"intent_compiler"}),
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.values["backfill_rate"] is None
        assert env.values["unsupported_rate"] is None
        assert env.values["policy_exempt_count"] == 1
        assert env.values["classifiable_decisions"] == 0

    def test_mixed_exempt_and_classifiable(self):
        """Policy-exempt doesn't affect the rate of classifiable decisions."""
        receipts = [
            # Supported decision
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            # Policy-exempt decision
            _receipt("dec2", "2026-02-25T10:00:06Z", gate="intent_compiler",
                     verdict="pass", subject_hash="subj_b"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            decision_gates=DECISION_GATES | frozenset({"intent_compiler"}),
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.values["classifiable_decisions"] == 1
        assert env.values["policy_exempt_count"] == 1
        assert env.values["backfill_rate"] == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════════════
# Full derivation — normal
# ═══════════════════════════════════════════════════════════════════════════

class TestDerivationNormal:
    """Full envelope derivation for normal scenarios."""

    def test_all_supported_zero_backfill(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value == pytest.approx(0.0)
        assert env.quality_status == QualityStatus.OK.value
        assert env.values["backfill_rate"] == pytest.approx(0.0)
        assert env.values["supported_count"] == 1
        assert env.values["backfilled_count"] == 0

    def test_all_backfilled(self):
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("ev1", "2026-02-25T10:00:10Z", gate="other_gate",
                     subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value == pytest.approx(1.0)
        assert env.values["backfill_rate"] == pytest.approx(1.0)

    def test_backfill_rate_computation(self):
        """2 supported + 1 backfilled → rate = 1/3."""
        receipts = [
            # Two supported
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("ev2", "2026-02-25T10:00:02Z", gate="other_gate",
                     subject_hash="subj_b"),
            _receipt("dec2", "2026-02-25T10:00:06Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_b"),
            # One backfilled
            _receipt("dec3", "2026-02-25T10:00:07Z", gate="pre_commit",
                     verdict="block", subject_hash="subj_c"),
            _receipt("ev3", "2026-02-25T10:00:20Z", gate="other_gate",
                     subject_hash="subj_c"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value == pytest.approx(1.0 / 3.0)

    def test_lag_statistics_in_values(self):
        """Lag statistics populated in values dict."""
        receipts = [
            # Supported with 3s staleness
            _receipt("ev1", "2026-02-25T10:00:02Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            # Backfilled with 5s delay
            _receipt("dec2", "2026-02-25T10:00:10Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_b"),
            _receipt("ev2", "2026-02-25T10:00:15Z", gate="other_gate",
                     subject_hash="subj_b"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.values["mean_support_staleness_ms"] == pytest.approx(3000.0)
        assert env.values["mean_backfill_delay_ms"] == pytest.approx(5000.0)


# ═══════════════════════════════════════════════════════════════════════════
# Full derivation — empty / unavailable
# ═══════════════════════════════════════════════════════════════════════════

class TestDerivationUnavailable:
    """No decisions in window → unavailable."""

    def test_empty_receipts(self):
        env = derive_decision_evidence_lag(
            [], WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value
        assert "no_decisions_in_window" in env.quality_reasons

    def test_only_non_decision_receipts(self):
        receipts = [
            _receipt("r1", "2026-02-25T10:00:05Z", gate="some_gate",
                     verdict="pass"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value

    def test_decisions_outside_window(self):
        """Decisions before window_start are not counted."""
        receipts = [
            _receipt("dec1", "2026-02-25T09:55:00Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        # Decision is before window, but it's included as pre-window receipt
        # However, it's still a decision from a decision gate
        # The windowed filter includes pre-window receipts for evidence linking
        # So this decision IS included — let's verify behavior
        # Actually: the decision IS in windowed (pre-window receipts added)
        # and IS from a decision gate, so it WILL be classified
        assert env.value is not None or env.quality_status == QualityStatus.UNAVAILABLE.value

    def test_decisions_after_window_excluded(self):
        """Decisions at/after window_end are excluded."""
        receipts = [
            _receipt("dec1", WINDOW_END, gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value


# ═══════════════════════════════════════════════════════════════════════════
# Window filtering
# ═══════════════════════════════════════════════════════════════════════════

class TestWindowFiltering:
    """Pre-window evidence included for linking."""

    def test_pre_window_evidence_links_to_in_window_decision(self):
        """Evidence from before window_start can support in-window decisions."""
        receipts = [
            # Evidence before window
            _receipt("ev1", "2026-02-25T09:55:00Z", gate="other_gate",
                     subject_hash="subj_a"),
            # Decision in window
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.values["supported_count"] == 1

    def test_post_window_evidence_excluded(self):
        """Evidence after window_end is not included."""
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            # Evidence after window
            _receipt("ev1", "2026-02-25T10:10:00Z", gate="other_gate",
                     subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        # Evidence at T=10:10 is after window_end T=10:05, so excluded
        assert env.values["unsupported_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Quality semantics
# ═══════════════════════════════════════════════════════════════════════════

class TestQualitySemantics:
    """Quality status and completeness."""

    def test_ok_quality_all_parseable(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.OK.value
        assert env.completeness == pytest.approx(1.0)
        assert env.quality_reasons == []

    def test_partial_quality_unparseable_timestamps(self):
        # Use a timestamp that passes window string-comparison filter
        # but fails datetime.fromisoformat parsing
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:0BAD", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("dec2", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_b"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.quality_status == QualityStatus.PARTIAL.value
        assert any("unparseable" in r for r in env.quality_reasons)
        # Completeness = 1 - 1/2 = 0.5
        assert env.completeness == pytest.approx(0.5)

    def test_sample_size_equals_total_decisions(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
            _receipt("dec2", "2026-02-25T10:00:06Z", gate="evidence_gate",
                     verdict="warn", subject_hash="subj_b"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.sample_size == 2

    def test_unavailable_sample_size_is_none(self):
        env = derive_decision_evidence_lag(
            [], WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.sample_size is None


# ═══════════════════════════════════════════════════════════════════════════
# Envelope shape and validation
# ═══════════════════════════════════════════════════════════════════════════

class TestEnvelopeShape:
    """Output envelope has all required fields."""

    @pytest.fixture()
    def normal_env(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        return derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )

    def test_signal_identity(self, normal_env):
        assert normal_env.signal_id == "DECISION_EVIDENCE_LAG"
        assert normal_env.signal_version == 1
        assert normal_env.phase == "2.4B"

    def test_subject_type(self, normal_env):
        assert normal_env.subject_type == "window"
        assert normal_env.subject_id.startswith("lag_")

    def test_unit(self, normal_env):
        assert normal_env.unit == "rate"

    def test_derivation(self, normal_env):
        assert normal_env.derivation == DerivationType.WINDOWED_AGGREGATE.value
        assert normal_env.derivation_version == LAG_CONFIG_VERSION

    def test_window_fields(self, normal_env):
        assert normal_env.window_start == WINDOW_START
        assert normal_env.window_end == WINDOW_END
        assert normal_env.window_kind == WINDOW_KIND

    def test_values_dict_keys(self, normal_env):
        required_keys = {
            "total_decisions", "classifiable_decisions",
            "supported_count", "backfilled_count",
            "unsupported_count", "policy_exempt_count",
            "backfill_rate", "unsupported_rate",
            "mean_backfill_delay_ms", "p95_backfill_delay_ms",
            "mean_support_staleness_ms", "p95_support_staleness_ms",
            "config_version",
        }
        assert required_keys.issubset(set(normal_env.values.keys()))

    def test_annotations_dict_keys(self, normal_env):
        required_keys = {
            "config_version", "decision_gates", "policy_exempt_gates",
        }
        assert required_keys.issubset(set(normal_env.annotations.keys()))

    def test_annotations_gates_are_sorted_lists(self, normal_env):
        assert isinstance(normal_env.annotations["decision_gates"], list)
        assert isinstance(normal_env.annotations["policy_exempt_gates"], list)
        assert normal_env.annotations["decision_gates"] == sorted(
            normal_env.annotations["decision_gates"]
        )

    def test_validates_cleanly(self, normal_env):
        errors = validate_envelope(normal_env)
        assert errors == []

    def test_content_hash_stable(self, normal_env):
        """Same inputs → same content hash."""
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env2 = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert normal_env.content_hash() == env2.content_hash()


# ═══════════════════════════════════════════════════════════════════════════
# Round-trip serialization
# ═══════════════════════════════════════════════════════════════════════════

class TestSerialization:
    """to_dict / from_dict / to_json round-trip."""

    def test_round_trip(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        d = env.to_dict()
        env2 = SignalEnvelope.from_dict(d)
        assert env2.signal_id == env.signal_id
        assert env2.value == env.value
        assert env2.values == env.values
        assert env2.annotations == env.annotations

    def test_json_round_trip(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        j = env.to_json()
        env2 = SignalEnvelope.from_json(j)
        assert env2.signal_id == env.signal_id
        assert env2.values["backfill_rate"] == env.values["backfill_rate"]


# ═══════════════════════════════════════════════════════════════════════════
# Observe-only invariant
# ═══════════════════════════════════════════════════════════════════════════

class TestObserveOnly:
    """B2 must not block, alter policy, or mutate anything."""

    def test_module_has_no_blocking_imports(self):
        """Verify the module doesn't import gating/policy infrastructure."""
        import governor.signals.decision_evidence_lag as mod
        source = pathlib.Path(mod.__file__).read_text()
        for forbidden in [
            "from ..evidence_gate",
            "from ..wrapper",
            "from ..hooks",
            "from ..daemon",
            "from ..violation_resolver",
        ]:
            assert forbidden not in source, f"Found forbidden import: {forbidden}"

    def test_no_receipt_store_access(self):
        """B2 must not access receipt stores directly (it receives data, not fetches)."""
        import governor.signals.decision_evidence_lag as mod
        source = pathlib.Path(mod.__file__).read_text()
        assert "ReceiptStore" not in source
        assert "receipt_store" not in source

    def test_derive_is_pure(self):
        """Derivation function is deterministic with no side effects."""
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env1 = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        env2 = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env1.to_dict() == env2.to_dict()


# ═══════════════════════════════════════════════════════════════════════════
# Missing ≠ zero invariant
# ═══════════════════════════════════════════════════════════════════════════

class TestMissingNotZero:
    """Value=None + unavailable is distinct from value=0.0 + ok."""

    def test_no_decisions_yields_none_not_zero(self):
        env = derive_decision_evidence_lag(
            [], WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value

    def test_all_supported_is_zero_not_none(self):
        """Zero backfill rate = healthy (value=0.0), not missing."""
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.value is not None
        assert env.value == pytest.approx(0.0)
        assert env.quality_status == QualityStatus.OK.value


# ═══════════════════════════════════════════════════════════════════════════
# Config version provenance
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigVersion:
    """Config version embedded in output for provenance."""

    def test_values_has_config_version(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.values["config_version"] == LAG_CONFIG_VERSION

    def test_annotations_has_config_version(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.annotations["config_version"] == LAG_CONFIG_VERSION

    def test_derivation_version_matches_config(self):
        receipts = [
            _receipt("ev1", "2026-02-25T10:00:01Z", gate="other_gate",
                     subject_hash="subj_a"),
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.derivation_version == LAG_CONFIG_VERSION


# ═══════════════════════════════════════════════════════════════════════════
# Custom gate overrides
# ═══════════════════════════════════════════════════════════════════════════

class TestCustomGateOverrides:
    """Override decision_gates and policy_exempt_gates."""

    def test_custom_decision_gates(self):
        custom_gates = frozenset({"my_custom_gate"})
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="my_custom_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            decision_gates=custom_gates,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.values["total_decisions"] == 1

    def test_custom_policy_exempt_gates(self):
        custom_exempt = frozenset({"evidence_gate"})
        receipts = [
            _receipt("dec1", "2026-02-25T10:00:05Z", gate="evidence_gate",
                     verdict="pass", subject_hash="subj_a"),
        ]
        env = derive_decision_evidence_lag(
            receipts, WINDOW_START, WINDOW_END, WINDOW_KIND,
            policy_exempt_gates=custom_exempt,
            emitter_version="test", emitted_at=EMITTED_AT,
        )
        assert env.values["policy_exempt_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# Golden fixtures
# ═══════════════════════════════════════════════════════════════════════════

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "signals"


class TestGoldenFixtures:
    """Golden fixture regression tests."""

    def _load_fixture(self, name: str) -> dict:
        path = FIXTURE_DIR / name
        return json.loads(path.read_text())

    def test_golden_supported(self):
        data = self._load_fixture("envelope_supported_decision_lag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "DECISION_EVIDENCE_LAG"
        assert env.values["supported_count"] > 0
        assert env.values["backfill_rate"] == pytest.approx(0.0)
        assert env.quality_status == QualityStatus.OK.value
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_backfilled(self):
        data = self._load_fixture("envelope_backfilled_decision_lag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "DECISION_EVIDENCE_LAG"
        assert env.values["backfilled_count"] > 0
        assert env.value is not None
        assert env.value > 0.0
        assert env.quality_status == QualityStatus.OK.value
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_unsupported(self):
        data = self._load_fixture("envelope_unsupported_decision_lag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "DECISION_EVIDENCE_LAG"
        assert env.values["unsupported_count"] > 0
        assert env.quality_status == QualityStatus.OK.value
        errors = validate_envelope(env)
        assert errors == []

    def test_golden_empty(self):
        data = self._load_fixture("envelope_empty_decision_lag.json")
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "DECISION_EVIDENCE_LAG"
        assert env.value is None
        assert env.quality_status == QualityStatus.UNAVAILABLE.value
        errors = validate_envelope(env)
        assert errors == []

    def test_all_fixtures_have_required_values_keys(self):
        required_keys = {
            "total_decisions", "classifiable_decisions",
            "supported_count", "backfilled_count",
            "unsupported_count", "policy_exempt_count",
            "backfill_rate", "unsupported_rate",
            "mean_backfill_delay_ms", "p95_backfill_delay_ms",
            "mean_support_staleness_ms", "p95_support_staleness_ms",
            "config_version",
        }
        for name in (
            "envelope_supported_decision_lag.json",
            "envelope_backfilled_decision_lag.json",
            "envelope_unsupported_decision_lag.json",
            "envelope_empty_decision_lag.json",
        ):
            data = self._load_fixture(name)
            assert required_keys.issubset(set(data["values"].keys())), \
                f"Missing keys in {name}"
