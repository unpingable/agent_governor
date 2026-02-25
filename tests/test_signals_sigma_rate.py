# SPDX-License-Identifier: Apache-2.0
"""Tests for SIGMA_RATE signal derivation (v2.4 Phase A3)."""

from __future__ import annotations

import pytest

from governor.signals.envelope import (
    QualityStatus,
    validate_envelope,
)
from governor.signals.sigma_rate import (
    ENDORSEMENT_VERDICTS,
    INVALIDATION_VERDICTS,
    MATCH_RULE_VERSION,
    SIGMA_FALLBACK_COMPLETENESS,
    ReceiptEvent,
    SigmaEvent,
    SigmaMatchResult,
    _compute_lag_stats,
    _parse_ts_ms,
    derive_sigma_rate,
    match_sigma_pairs,
)


import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "signals"


# ── Helpers ────────────────────────────────────────────────────────────────────

W_START = "2026-02-24T17:40:00Z"
W_END = "2026-02-24T17:45:00Z"
W_KIND = "rolling_5m"


def _evt(
    receipt_id: str,
    ts: str,
    verdict: str,
    subject_hash: str,
    gate: str = "evidence_gate",
) -> ReceiptEvent:
    return ReceiptEvent(
        receipt_id=receipt_id,
        timestamp=ts,
        verdict=verdict,
        subject_hash=subject_hash,
        gate=gate,
    )


def _endorse(receipt_id: str, ts: str, subject_hash: str) -> ReceiptEvent:
    return _evt(receipt_id, ts, "pass", subject_hash)


def _invalidate(receipt_id: str, ts: str, subject_hash: str) -> ReceiptEvent:
    return _evt(receipt_id, ts, "block", subject_hash)


def _derive(**kwargs):
    """Shortcut to derive_sigma_rate with default window params."""
    defaults = {
        "window_start": W_START,
        "window_end": W_END,
        "window_kind": W_KIND,
        "emitter_version": "test",
        "emitted_at": "2026-02-24T17:45:00Z",
    }
    defaults.update(kwargs)
    return derive_sigma_rate(**defaults)


# ── Constants ──────────────────────────────────────────────────────────────────


class TestConstants:
    def test_match_rule_version_format(self):
        assert MATCH_RULE_VERSION == "sigma-match-v1"

    def test_endorsement_verdicts(self):
        assert "pass" in ENDORSEMENT_VERDICTS

    def test_invalidation_verdicts(self):
        assert "block" in INVALIDATION_VERDICTS

    def test_warn_is_neither(self):
        """warn verdict should not match endorsement or invalidation."""
        assert "warn" not in ENDORSEMENT_VERDICTS
        assert "warn" not in INVALIDATION_VERDICTS


# ── ReceiptEvent ───────────────────────────────────────────────────────────────


class TestReceiptEvent:
    def test_frozen(self):
        e = _endorse("r1", "2026-01-01T00:00:00Z", "h1")
        with pytest.raises(AttributeError):
            e.verdict = "block"  # type: ignore[misc]

    def test_default_gate(self):
        e = ReceiptEvent(receipt_id="r1", timestamp="t", verdict="pass", subject_hash="h")
        assert e.gate == ""

    def test_explicit_gate(self):
        e = _evt("r1", "t", "pass", "h", gate="chain_composition")
        assert e.gate == "chain_composition"


# ── Timestamp parsing ──────────────────────────────────────────────────────────


class TestTimestampParsing:
    def test_z_suffix(self):
        ms = _parse_ts_ms("2026-02-24T17:40:00Z")
        assert ms is not None
        assert ms > 0

    def test_plus_suffix(self):
        ms = _parse_ts_ms("2026-02-24T17:40:00+00:00")
        assert ms is not None

    def test_z_equals_plus(self):
        a = _parse_ts_ms("2026-02-24T17:40:00Z")
        b = _parse_ts_ms("2026-02-24T17:40:00+00:00")
        assert a == b

    def test_invalid_returns_none(self):
        assert _parse_ts_ms("not-a-timestamp") is None

    def test_none_returns_none(self):
        assert _parse_ts_ms(None) is None  # type: ignore[arg-type]

    def test_empty_returns_none(self):
        assert _parse_ts_ms("") is None


# ── SigmaEvent ─────────────────────────────────────────────────────────────────


class TestSigmaEvent:
    def test_frozen(self):
        se = SigmaEvent(
            subject_hash="h1",
            endorsement_id="r1",
            invalidation_id="r2",
            endorsement_ts="2026-01-01T00:00:00Z",
            invalidation_ts="2026-01-01T00:01:00Z",
            lag_ms=60000.0,
        )
        with pytest.raises(AttributeError):
            se.lag_ms = 0.0  # type: ignore[misc]

    def test_lag_ms_positive(self):
        se = SigmaEvent(
            subject_hash="h1",
            endorsement_id="r1",
            invalidation_id="r2",
            endorsement_ts="2026-01-01T00:00:00Z",
            invalidation_ts="2026-01-01T00:01:00Z",
            lag_ms=60000.0,
        )
        assert se.lag_ms == 60000.0


# ── SigmaMatchResult ──────────────────────────────────────────────────────────


class TestSigmaMatchResult:
    def test_defaults(self):
        r = SigmaMatchResult()
        assert r.pairs == []
        assert r.eligible_events == 0
        assert r.dropped_endorsements == 0
        assert r.dropped_invalidations == 0
        assert r.invalid_pairs == 0

    def test_frozen(self):
        r = SigmaMatchResult()
        with pytest.raises(AttributeError):
            r.eligible_events = 5  # type: ignore[misc]


# ── Pair matching ──────────────────────────────────────────────────────────────


class TestMatchSigmaPairs:
    """Core sigma-match-v1 algorithm tests."""

    def test_empty_events(self):
        result = match_sigma_pairs([])
        assert result.pairs == []
        assert result.eligible_events == 0

    def test_single_pair(self):
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
            _invalidate("r2", "2026-01-01T00:01:00Z", "h1"),
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 1
        assert result.pairs[0].subject_hash == "h1"
        assert result.pairs[0].endorsement_id == "r1"
        assert result.pairs[0].invalidation_id == "r2"
        assert result.pairs[0].lag_ms == pytest.approx(60000.0, abs=100)
        assert result.eligible_events == 2

    def test_multiple_subjects(self):
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
            _endorse("r2", "2026-01-01T00:00:01Z", "h2"),
            _invalidate("r3", "2026-01-01T00:01:00Z", "h1"),
            _invalidate("r4", "2026-01-01T00:01:01Z", "h2"),
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 2
        subjects = {p.subject_hash for p in result.pairs}
        assert subjects == {"h1", "h2"}

    def test_first_invalidation_wins(self):
        """Multiple invalidations for same subject: first subsequent wins."""
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
            _invalidate("r2", "2026-01-01T00:01:00Z", "h1"),
            _invalidate("r3", "2026-01-01T00:02:00Z", "h1"),  # too late
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 1
        assert result.pairs[0].invalidation_id == "r2"
        assert result.dropped_invalidations == 1

    def test_duplicate_endorsements_collapse(self):
        """Duplicate endorsements for same subject: first counts."""
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
            _endorse("r2", "2026-01-01T00:00:30Z", "h1"),  # duplicate, ignored
            _invalidate("r3", "2026-01-01T00:01:00Z", "h1"),
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 1
        assert result.pairs[0].endorsement_id == "r1"
        # r2 was a dropped endorsement (duplicate, never consumed)
        assert result.dropped_endorsements == 1

    def test_endorsement_only_no_match(self):
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 0
        assert result.dropped_endorsements == 1
        assert result.eligible_events == 1

    def test_invalidation_only_no_match(self):
        events = [
            _invalidate("r1", "2026-01-01T00:00:00Z", "h1"),
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 0
        assert result.dropped_invalidations == 1

    def test_negative_lag_invalid(self):
        """Invalidation before endorsement by timestamp → invalid pair, dropped."""
        events = [
            _endorse("r1", "2026-01-01T00:01:00Z", "h1"),
            _invalidate("r2", "2026-01-01T00:00:00Z", "h1"),
        ]
        # Sort by timestamp puts invalidation first, so no pending endorsement
        # when invalidation arrives — this is a dropped invalidation, not invalid pair.
        # Actually: sorted by ts → r2 (00:00) comes first (invalidation, no pending),
        # then r1 (01:00) endorsement with no subsequent invalidation.
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 0
        assert result.dropped_invalidations == 1
        assert result.dropped_endorsements == 1

    def test_warn_verdict_ignored(self):
        """warn is neither endorsement nor invalidation."""
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
            _evt("r2", "2026-01-01T00:00:30Z", "warn", "h1"),
            _invalidate("r3", "2026-01-01T00:01:00Z", "h1"),
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 1
        # warn counted in eligible but not as endorsement/invalidation
        assert result.eligible_events == 3

    def test_corrupt_timestamp_invalid(self):
        """Unparseable timestamp → invalid pair."""
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
            _invalidate("r2", "not-a-date", "h1"),
        ]
        result = match_sigma_pairs(events)
        # After sort, "2026..." < "not-a-date" lexicographically
        # So endorsement first, then invalidation matched → but ts parse fails → invalid
        assert result.invalid_pairs == 1
        assert len(result.pairs) == 0

    def test_stable_sort_preserves_order(self):
        """Events with same timestamp: stable sort preserves input order."""
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),
            _invalidate("r2", "2026-01-01T00:00:00Z", "h1"),
        ]
        result = match_sigma_pairs(events)
        # Same timestamp: stable sort keeps r1 (endorse) before r2 (invalidate)
        # lag = 0 ms which is valid (not negative)
        assert len(result.pairs) == 1
        assert result.pairs[0].lag_ms == pytest.approx(0.0, abs=1)

    def test_zero_lag_valid(self):
        """lag=0 is valid (same timestamp endorsement and invalidation)."""
        events = [
            _endorse("r1", "2026-01-01T12:00:00Z", "h1"),
            _invalidate("r2", "2026-01-01T12:00:00Z", "h1"),
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 1
        assert result.pairs[0].lag_ms == pytest.approx(0.0, abs=1)
        assert result.invalid_pairs == 0

    def test_audit_counts_add_up(self):
        """Audit invariant: dropped + matched + invalid accounts for all events."""
        events = [
            _endorse("r1", "2026-01-01T00:00:00Z", "h1"),  # matched
            _endorse("r2", "2026-01-01T00:00:01Z", "h2"),  # dropped (no invalidation)
            _invalidate("r3", "2026-01-01T00:01:00Z", "h1"),  # matched
            _invalidate("r4", "2026-01-01T00:01:01Z", "h3"),  # dropped (no endorsement)
        ]
        result = match_sigma_pairs(events)
        assert len(result.pairs) == 1
        assert result.dropped_endorsements == 1
        assert result.dropped_invalidations == 1
        assert result.eligible_events == 4


# ── Lag statistics ─────────────────────────────────────────────────────────────


class TestLagStatistics:
    def test_empty_pairs(self):
        stats = _compute_lag_stats([])
        assert stats["mean_lag_ms"] is None
        assert stats["p95_lag_ms"] is None

    def test_single_pair(self):
        pair = SigmaEvent(
            subject_hash="h1",
            endorsement_id="r1",
            invalidation_id="r2",
            endorsement_ts="t1",
            invalidation_ts="t2",
            lag_ms=5000.0,
        )
        stats = _compute_lag_stats([pair])
        assert stats["mean_lag_ms"] == 5000.0
        assert stats["p95_lag_ms"] == 5000.0

    def test_multiple_pairs(self):
        pairs = [
            SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=1000.0),
            SigmaEvent("h2", "r3", "r4", "t3", "t4", lag_ms=2000.0),
            SigmaEvent("h3", "r5", "r6", "t5", "t6", lag_ms=3000.0),
        ]
        stats = _compute_lag_stats(pairs)
        assert stats["mean_lag_ms"] == pytest.approx(2000.0)
        assert stats["p95_lag_ms"] is not None
        # p95 of [1000, 2000, 3000] should be 3000
        assert stats["p95_lag_ms"] == 3000.0

    def test_p95_with_20_values(self):
        """p95 of 20 values: index should be ~19th value."""
        pairs = [
            SigmaEvent(f"h{i}", f"e{i}", f"i{i}", "t", "t", lag_ms=float(i * 100))
            for i in range(1, 21)
        ]
        stats = _compute_lag_stats(pairs)
        assert stats["mean_lag_ms"] == pytest.approx(1050.0)
        # p95 of [100..2000]: idx = min(int(0.95*20+0.5), 19) = min(19, 19) = 19
        assert stats["p95_lag_ms"] == 2000.0


# ── Derivation: valid sigma pairs ─────────────────────────────────────────────


class TestDeriveSigmaRate:
    """Core derive_sigma_rate tests."""

    def test_valid_pair_with_exposure_proxy(self):
        """1 sigma pair, exposure_proxy denominator → rate = 1/23."""
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=2)
        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.signal_id == "SIGMA_RATE"
        assert env.value == pytest.approx(1 / 23.0)
        assert env.quality_status == "ok"
        assert env.values["denominator_type"] == "exposure_proxy"
        assert env.values["denominator_value"] == 23.0
        assert env.values["sigma_events"] == 1

    def test_valid_pair_eligible_events_fallback(self):
        """No exposure_proxy → fall back to eligible_events, quality=partial."""
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        env = _derive(match_result=match_result)
        assert env.value == pytest.approx(1 / 10.0)
        assert env.quality_status == "partial"
        assert "fallback_denominator_used" in env.quality_reasons
        assert env.values["denominator_type"] == "eligible_events"
        assert env.annotations.get("denominator_fallback") is True

    def test_multiple_pairs_rate(self):
        """3 sigma pairs / 50 exposure → rate = 0.06."""
        pairs = [
            SigmaEvent(f"h{i}", f"e{i}", f"i{i}", "t", "t", lag_ms=1000.0)
            for i in range(3)
        ]
        match_result = SigmaMatchResult(pairs=pairs, eligible_events=20)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        assert env.value == pytest.approx(3 / 50.0)
        assert env.quality_status == "ok"


# ── Derivation: zero sigma events ─────────────────────────────────────────────


class TestZeroSigmaEvents:
    """Zero sigma events with valid denominator → value=0.0, not None."""

    def test_zero_with_exposure_proxy(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.value == 0.0
        assert env.quality_status == "ok"
        assert env.values["sigma_events"] == 0

    def test_zero_with_eligible_events(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result)
        assert env.value == 0.0
        assert env.quality_status == "partial"  # fallback denominator
        assert env.values["sigma_events"] == 0

    def test_zero_is_not_unavailable(self):
        """Zero sigma events is not the same as unavailable."""
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.value == 0.0
        assert env.quality_status != "unavailable"


# ── Derivation: missing denominator ───────────────────────────────────────────


class TestMissingDenominator:
    """No denominator → unavailable, value=None (missing != zero)."""

    def test_no_events_no_proxy(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=0)
        env = _derive(match_result=match_result)
        assert env.value is None
        assert env.quality_status == "unavailable"
        assert "no_denominator" in env.quality_reasons

    def test_unavailable_not_zero(self):
        """Unavailable is not zero — the invariant."""
        match_result = SigmaMatchResult(pairs=[], eligible_events=0)
        env = _derive(match_result=match_result)
        assert env.value is not None or env.quality_status == "unavailable"
        # Validate envelope: no missing!=zero violation
        errors = validate_envelope(env)
        assert not any("unavailable" in e and "0.0" in e for e in errors)

    def test_zero_proxy_still_checks_eligible(self):
        """exposure_proxy_value=0.0 is not > 0, falls back to eligible_events."""
        match_result = SigmaMatchResult(pairs=[], eligible_events=5)
        env = _derive(match_result=match_result, exposure_proxy_value=0.0)
        assert env.value == 0.0
        assert env.values["denominator_type"] == "eligible_events"

    def test_negative_proxy_falls_back(self):
        """Negative proxy is not > 0, falls back to eligible_events."""
        match_result = SigmaMatchResult(pairs=[], eligible_events=5)
        env = _derive(match_result=match_result, exposure_proxy_value=-1.0)
        assert env.values["denominator_type"] == "eligible_events"


# ── Derivation: invalid pairs ─────────────────────────────────────────────────


class TestInvalidPairs:
    """Invalid pairs detected → quality=invalid, value=None."""

    def test_invalid_pairs_detected(self):
        match_result = SigmaMatchResult(
            pairs=[], eligible_events=5, invalid_pairs=2,
        )
        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.value is None
        assert env.quality_status == "invalid"
        assert any("invalid_pairs_detected" in r for r in env.quality_reasons)

    def test_invalid_includes_count(self):
        match_result = SigmaMatchResult(
            pairs=[], eligible_events=5, invalid_pairs=3,
        )
        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        reason = env.quality_reasons[0]
        assert "3 pairs" in reason

    def test_invalid_with_valid_pairs_still_invalid(self):
        """Even if some pairs are valid, any invalid → quality=invalid."""
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(
            pairs=[pair], eligible_events=10, invalid_pairs=1,
        )
        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.value is None
        assert env.quality_status == "invalid"


# ── Derivation: EXPOSURE_PROXY preference ─────────────────────────────────────


class TestExposureProxyPreference:
    """exposure_proxy_value is preferred over eligible_events."""

    def test_proxy_preferred_when_both_available(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=100)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        assert env.values["denominator_type"] == "exposure_proxy"
        assert env.values["denominator_value"] == 50.0
        assert env.quality_status == "ok"

    def test_proxy_none_falls_back(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=100)
        env = _derive(match_result=match_result, exposure_proxy_value=None)
        assert env.values["denominator_type"] == "eligible_events"
        assert env.quality_status == "partial"

    def test_fallback_annotated(self):
        """Fallback to eligible_events is annotated in both quality and annotations."""
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result)
        assert "fallback_denominator_used" in env.quality_reasons
        assert env.annotations.get("denominator_fallback") is True
        assert env.completeness == pytest.approx(SIGMA_FALLBACK_COMPLETENESS)

    def test_proxy_no_fallback_annotation(self):
        """When proxy is used, no fallback annotation."""
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        assert "fallback_denominator_used" not in env.quality_reasons
        assert "denominator_fallback" not in env.annotations


# ── Raw counts always present ──────────────────────────────────────────────────


class TestRawCountsAlwaysPresent:
    """Raw counts must be emitted alongside rate (never rate-only)."""

    def _check_all_values(self, env):
        v = env.values
        required_keys = {
            "sigma_events", "eligible_events",
            "denominator_value", "denominator_type",
            "match_rule_version",
            "mean_lag_ms", "p95_lag_ms",
            "matched_pairs_count",
            "dropped_endorsements", "dropped_invalidations",
            "invalid_pairs_count",
        }
        assert required_keys <= set(v.keys()), f"Missing: {required_keys - set(v.keys())}"

    def test_ok_envelope_has_all_values(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        self._check_all_values(env)

    def test_unavailable_envelope_has_all_values(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=0)
        env = _derive(match_result=match_result)
        self._check_all_values(env)

    def test_invalid_envelope_has_all_values(self):
        match_result = SigmaMatchResult(
            pairs=[], eligible_events=5, invalid_pairs=1,
        )
        env = _derive(match_result=match_result)
        self._check_all_values(env)

    def test_partial_envelope_has_all_values(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result)
        self._check_all_values(env)

    def test_match_rule_version_in_values(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        assert env.values["match_rule_version"] == MATCH_RULE_VERSION


# ── Lag stats in values ────────────────────────────────────────────────────────


class TestLagStatsInEnvelope:
    def test_lag_present_when_pairs_exist(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=2)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        assert env.values["mean_lag_ms"] == pytest.approx(5000.0)
        assert env.values["p95_lag_ms"] == pytest.approx(5000.0)

    def test_lag_null_when_no_pairs(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        assert env.values["mean_lag_ms"] is None
        assert env.values["p95_lag_ms"] is None


# ── Envelope shape ─────────────────────────────────────────────────────────────


class TestEnvelopeShape:
    """Structural invariants on the emitted envelope."""

    def _make_env(self, **kwargs):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        return _derive(match_result=match_result, exposure_proxy_value=50.0, **kwargs)

    def test_signal_id(self):
        assert self._make_env().signal_id == "SIGMA_RATE"

    def test_signal_version(self):
        assert self._make_env().signal_version == 1

    def test_phase(self):
        assert self._make_env().phase == "2.4A"

    def test_unit(self):
        assert self._make_env().unit == "rate"

    def test_derivation(self):
        assert self._make_env().derivation == "windowed_aggregate"

    def test_derivation_version(self):
        assert self._make_env().derivation_version == "sigma-rate-v1"

    def test_subject_type(self):
        assert self._make_env().subject_type == "window"

    def test_subject_id_format(self):
        env = self._make_env()
        assert env.subject_id == f"win_{W_START}_{W_KIND}"

    def test_window_fields(self):
        env = self._make_env()
        assert env.window_start == W_START
        assert env.window_end == W_END
        assert env.window_kind == W_KIND

    def test_match_rule_in_annotations(self):
        env = self._make_env()
        assert env.annotations["match_rule_version"] == MATCH_RULE_VERSION

    def test_session_id_passthrough(self):
        env = self._make_env(session_id="sess_42")
        assert env.session_id == "sess_42"

    def test_source_receipt_ids_passthrough(self):
        env = self._make_env(source_receipt_ids=["r1", "r2"])
        assert env.source_receipt_ids == ["r1", "r2"]

    def test_source_streams_passthrough(self):
        env = self._make_env(source_streams=["evidence", "chain"])
        assert env.source_streams == ["evidence", "chain"]

    def test_emitted_at_override(self):
        env = self._make_env(emitted_at="2026-02-24T18:00:00Z")
        assert env.emitted_at == "2026-02-24T18:00:00Z"


# ── Envelope validation ───────────────────────────────────────────────────────


class TestEnvelopeValidation:
    """All derived envelopes pass validate_envelope()."""

    def test_ok_validates(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_partial_validates(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_unavailable_validates(self):
        match_result = SigmaMatchResult(pairs=[], eligible_events=0)
        env = _derive(match_result=match_result)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_invalid_validates(self):
        match_result = SigmaMatchResult(
            pairs=[], eligible_events=5, invalid_pairs=1,
        )
        env = _derive(match_result=match_result)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"


# ── Round-trip serialization ───────────────────────────────────────────────────


class TestRoundTrip:
    def test_to_dict_from_dict(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        d = env.to_dict()
        env2 = type(env).from_dict(d)
        assert env2.signal_id == env.signal_id
        assert env2.value == env.value
        assert env2.values == env.values
        assert env2.annotations == env.annotations

    def test_to_json_from_json(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        j = env.to_json()
        env2 = type(env).from_json(j)
        assert env2.signal_id == env.signal_id
        assert env2.value == env.value

    def test_content_hash_deterministic(self):
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        h1 = env.content_hash()
        h2 = env.content_hash()
        assert h1 == h2
        assert h1.startswith("sha256:")


# ── Integration: match + derive ────────────────────────────────────────────────


class TestMatchThenDerive:
    """End-to-end: receipt events → match → derive → envelope."""

    def test_full_pipeline(self):
        events = [
            _endorse("r1", "2026-02-24T17:40:10Z", "h1"),
            _endorse("r2", "2026-02-24T17:40:20Z", "h2"),
            _invalidate("r3", "2026-02-24T17:41:00Z", "h1"),
            _endorse("r4", "2026-02-24T17:42:00Z", "h3"),  # no invalidation
        ]
        match_result = match_sigma_pairs(events)
        assert len(match_result.pairs) == 1
        assert match_result.eligible_events == 4

        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.value == pytest.approx(1 / 23.0)
        assert env.quality_status == "ok"
        assert env.values["sigma_events"] == 1
        assert env.values["dropped_endorsements"] == 2  # h2 + h3
        assert env.values["dropped_invalidations"] == 0
        assert env.values["mean_lag_ms"] is not None

    def test_no_sigma_pipeline(self):
        """All endorsements, no invalidations → rate=0.0."""
        events = [
            _endorse("r1", "2026-02-24T17:40:10Z", "h1"),
            _endorse("r2", "2026-02-24T17:40:20Z", "h2"),
        ]
        match_result = match_sigma_pairs(events)
        assert len(match_result.pairs) == 0

        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.value == 0.0
        assert env.quality_status == "ok"

    def test_all_invalidations_no_endorsements(self):
        """All invalidations, no endorsements → rate=0.0 (no pairs formed)."""
        events = [
            _invalidate("r1", "2026-02-24T17:40:10Z", "h1"),
            _invalidate("r2", "2026-02-24T17:40:20Z", "h2"),
        ]
        match_result = match_sigma_pairs(events)
        assert len(match_result.pairs) == 0
        assert match_result.dropped_invalidations == 2

        env = _derive(match_result=match_result, exposure_proxy_value=23.0)
        assert env.value == 0.0


# ── Observe-only invariant ─────────────────────────────────────────────────────


class TestObserveOnly:
    """SIGMA_RATE is observe-only: no gating, no policy changes."""

    def test_no_gate_field(self):
        """Envelope has no gate/verdict field — it's a signal, not a gate."""
        pair = SigmaEvent("h1", "r1", "r2", "t1", "t2", lag_ms=5000.0)
        match_result = SigmaMatchResult(pairs=[pair], eligible_events=10)
        env = _derive(match_result=match_result, exposure_proxy_value=50.0)
        d = env.to_dict()
        assert "gate" not in d
        assert "verdict" not in d

    def test_high_rate_still_ok_quality(self):
        """Even a high sigma rate doesn't trigger quality degradation."""
        pairs = [
            SigmaEvent(f"h{i}", f"e{i}", f"i{i}", "t", "t", lag_ms=1000.0)
            for i in range(50)
        ]
        match_result = SigmaMatchResult(pairs=pairs, eligible_events=100)
        env = _derive(match_result=match_result, exposure_proxy_value=100.0)
        # Rate = 0.5 which is very high, but quality is about data quality
        assert env.value == pytest.approx(0.5)
        assert env.quality_status == "ok"


# ── Golden fixtures ────────────────────────────────────────────────────────────


class TestGoldenFixtures:
    """Golden fixtures lock the envelope shape against refactoring drift."""

    def _load(self, name: str) -> dict:
        path = FIXTURES / name
        return json.loads(path.read_text())

    def test_ok_fixture_parses(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_ok_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        assert env.signal_id == "SIGMA_RATE"
        assert env.quality_status == "ok"
        assert env.value is not None
        assert env.value > 0

    def test_ok_fixture_validates(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_ok_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_ok_fixture_uses_exposure_proxy(self):
        data = self._load("envelope_ok_sigma_rate.json")
        assert data["values"]["denominator_type"] == "exposure_proxy"
        assert "denominator_fallback" not in data["annotations"] or not data["annotations"]["denominator_fallback"]

    def test_partial_fixture_parses(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_partial_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == "partial"
        assert env.completeness == pytest.approx(SIGMA_FALLBACK_COMPLETENESS)

    def test_partial_fixture_validates(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_partial_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_partial_fixture_has_fallback_annotation(self):
        data = self._load("envelope_partial_sigma_rate.json")
        assert data["values"]["denominator_type"] == "eligible_events"
        assert data["annotations"]["denominator_fallback"] is True
        assert "fallback_denominator_used" in data["quality_reasons"]

    def test_unavailable_fixture_parses(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_unavailable_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == "unavailable"
        assert env.value is None

    def test_unavailable_fixture_validates(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_unavailable_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_unavailable_fixture_missing_not_zero(self):
        data = self._load("envelope_unavailable_sigma_rate.json")
        assert data["value"] is None
        assert data["quality_status"] == "unavailable"
        # Not zero — the invariant
        assert data["value"] != 0.0

    def test_invalid_fixture_parses(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_invalid_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        assert env.quality_status == "invalid"
        assert env.value is None

    def test_invalid_fixture_validates(self):
        from governor.signals.envelope import SignalEnvelope
        data = self._load("envelope_invalid_sigma_rate.json")
        env = SignalEnvelope.from_dict(data)
        errors = validate_envelope(env)
        assert errors == [], f"Validation errors: {errors}"

    def test_invalid_fixture_has_invalid_pairs(self):
        data = self._load("envelope_invalid_sigma_rate.json")
        assert data["values"]["invalid_pairs_count"] > 0
        assert any("invalid_pairs_detected" in r for r in data["quality_reasons"])

    def test_all_fixtures_share_schema_version(self):
        for name in [
            "envelope_ok_sigma_rate.json",
            "envelope_partial_sigma_rate.json",
            "envelope_unavailable_sigma_rate.json",
            "envelope_invalid_sigma_rate.json",
        ]:
            data = self._load(name)
            assert data["schema_version"] == "0.4.0", f"{name}: wrong schema_version"

    def test_all_fixtures_have_match_rule_version(self):
        for name in [
            "envelope_ok_sigma_rate.json",
            "envelope_partial_sigma_rate.json",
            "envelope_unavailable_sigma_rate.json",
            "envelope_invalid_sigma_rate.json",
        ]:
            data = self._load(name)
            assert data["values"]["match_rule_version"] == MATCH_RULE_VERSION, \
                f"{name}: wrong match_rule_version"


# ── Named constant contract ───────────────────────────────────────────────────


class TestNamedConstants:
    """Verify named constants are used, not magic numbers."""

    def test_fallback_completeness_constant_exists(self):
        assert SIGMA_FALLBACK_COMPLETENESS == 0.8

    def test_fallback_completeness_used_in_derivation(self):
        """Derivation with fallback denominator uses the named constant."""
        match_result = SigmaMatchResult(pairs=[], eligible_events=10)
        env = _derive(match_result=match_result)
        assert env.completeness == pytest.approx(SIGMA_FALLBACK_COMPLETENESS)
