# SPDX-License-Identifier: Apache-2.0
"""Tests for Coverage and Efficiency Metrics.

Layer 2.1-A. Severity-weighted verification coverage and efficiency.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.metrics import (
    MetricSeverity,
    VerificationStatus,
    MetricClaim,
    ClaimCoverage,
    EfficiencyMetric,
    CoverageSnapshot,
    MetricsTracker,
    MetricsStore,
    compute_coverage,
    compute_coverage_by_severity,
    compute_efficiency,
    compute_claim_coverage,
    update_claim_status,
    make_metrics_event,
    SEVERITY_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------

class TestMetricSeverity:
    def test_values(self):
        assert MetricSeverity.S1.value == "S1"
        assert MetricSeverity.S2.value == "S2"
        assert MetricSeverity.S3.value == "S3"

    def test_count(self):
        assert len(MetricSeverity) == 3


class TestVerificationStatus:
    def test_values(self):
        assert VerificationStatus.UNKNOWN.value == "unknown"
        assert VerificationStatus.VERIFIED.value == "verified"
        assert VerificationStatus.WAIVED.value == "waived"
        assert VerificationStatus.REFUTED.value == "refuted"
        assert VerificationStatus.PENDING.value == "pending"

    def test_count(self):
        assert len(VerificationStatus) == 5


# ---------------------------------------------------------------------------
# MetricClaim Tests
# ---------------------------------------------------------------------------

class TestMetricClaim:
    def test_create(self):
        c = MetricClaim(claim_id="c1", description="Tests pass",
                        severity=MetricSeverity.S2)
        assert c.claim_id == "c1"
        assert c.status == VerificationStatus.UNKNOWN
        assert c.evidence_id == ""

    def test_weight(self):
        c1 = MetricClaim(claim_id="c1", description="x", severity=MetricSeverity.S1)
        c2 = MetricClaim(claim_id="c2", description="x", severity=MetricSeverity.S2)
        c3 = MetricClaim(claim_id="c3", description="x", severity=MetricSeverity.S3)
        assert c1.weight == 1.0
        assert c2.weight == 3.0
        assert c3.weight == 10.0

    def test_is_verified(self):
        c = MetricClaim(claim_id="c1", description="x", severity=MetricSeverity.S1,
                        status=VerificationStatus.VERIFIED)
        assert c.is_verified
        c2 = MetricClaim(claim_id="c2", description="x", severity=MetricSeverity.S1,
                         status=VerificationStatus.WAIVED)
        assert not c2.is_verified

    def test_is_resolved(self):
        for st in (VerificationStatus.VERIFIED, VerificationStatus.WAIVED, VerificationStatus.REFUTED):
            c = MetricClaim(claim_id="c", description="x", severity=MetricSeverity.S1, status=st)
            assert c.is_resolved
        for st in (VerificationStatus.UNKNOWN, VerificationStatus.PENDING):
            c = MetricClaim(claim_id="c", description="x", severity=MetricSeverity.S1, status=st)
            assert not c.is_resolved

    def test_to_dict(self):
        c = MetricClaim(claim_id="c1", description="Tests pass",
                        severity=MetricSeverity.S2, evidence_id="e1")
        d = c.to_dict()
        assert d["claim_id"] == "c1"
        assert d["severity"] == "S2"
        assert d["evidence_id"] == "e1"

    def test_to_dict_no_evidence(self):
        c = MetricClaim(claim_id="c1", description="x", severity=MetricSeverity.S1)
        d = c.to_dict()
        assert "evidence_id" not in d

    def test_roundtrip(self):
        c = MetricClaim(claim_id="c1", description="Tests pass",
                        severity=MetricSeverity.S3, status=VerificationStatus.VERIFIED,
                        evidence_id="e42")
        restored = MetricClaim.from_dict(c.to_dict())
        assert restored.claim_id == c.claim_id
        assert restored.severity == c.severity
        assert restored.status == c.status
        assert restored.evidence_id == c.evidence_id


# ---------------------------------------------------------------------------
# Coverage Computation Tests
# ---------------------------------------------------------------------------

class TestComputeCoverage:
    def test_empty_claims(self):
        assert compute_coverage([]) == 1.0

    def test_all_verified(self):
        claims = [
            MetricClaim("c1", "x", MetricSeverity.S1, VerificationStatus.VERIFIED),
            MetricClaim("c2", "y", MetricSeverity.S2, VerificationStatus.VERIFIED),
        ]
        assert compute_coverage(claims) == pytest.approx(1.0)

    def test_none_verified(self):
        claims = [
            MetricClaim("c1", "x", MetricSeverity.S1),
            MetricClaim("c2", "y", MetricSeverity.S2),
        ]
        assert compute_coverage(claims) == pytest.approx(0.0)

    def test_partial_coverage(self):
        claims = [
            MetricClaim("c1", "x", MetricSeverity.S1, VerificationStatus.VERIFIED),  # w=1
            MetricClaim("c2", "y", MetricSeverity.S2),  # w=3, not verified
        ]
        # Coverage = 1 / (1 + 3) = 0.25
        assert compute_coverage(claims) == pytest.approx(0.25)

    def test_severity_weighting(self):
        claims = [
            MetricClaim("c1", "minor", MetricSeverity.S1),  # w=1
            MetricClaim("c2", "critical", MetricSeverity.S3, VerificationStatus.VERIFIED),  # w=10
        ]
        # Coverage = 10 / (1 + 10) = 10/11 ≈ 0.909
        assert compute_coverage(claims) == pytest.approx(10.0 / 11.0)

    def test_waived_counts_as_covered(self):
        claims = [
            MetricClaim("c1", "x", MetricSeverity.S2, VerificationStatus.WAIVED),
        ]
        assert compute_coverage(claims) == pytest.approx(1.0)

    def test_refuted_not_covered(self):
        claims = [
            MetricClaim("c1", "x", MetricSeverity.S2, VerificationStatus.REFUTED),
        ]
        assert compute_coverage(claims) == pytest.approx(0.0)


class TestComputeCoverageBySeverity:
    def test_s3_coverage(self):
        claims = [
            MetricClaim("c1", "x", MetricSeverity.S1, VerificationStatus.VERIFIED),
            MetricClaim("c2", "y", MetricSeverity.S3),
            MetricClaim("c3", "z", MetricSeverity.S3, VerificationStatus.VERIFIED),
        ]
        assert compute_coverage_by_severity(claims, MetricSeverity.S3) == pytest.approx(0.5)

    def test_no_claims_for_severity(self):
        claims = [MetricClaim("c1", "x", MetricSeverity.S1)]
        assert compute_coverage_by_severity(claims, MetricSeverity.S3) == 1.0


# ---------------------------------------------------------------------------
# Efficiency Tests
# ---------------------------------------------------------------------------

class TestComputeEfficiency:
    def test_basic(self):
        # 20% coverage gain in 4 actions = 5% per action
        assert compute_efficiency(0.5, 0.7, 4) == pytest.approx(0.05)

    def test_zero_actions(self):
        assert compute_efficiency(0.5, 0.7, 0) == 0.0

    def test_no_gain(self):
        assert compute_efficiency(0.5, 0.5, 3) == pytest.approx(0.0)

    def test_negative_efficiency(self):
        # Coverage decreased (claim refuted)
        assert compute_efficiency(0.5, 0.4, 2) == pytest.approx(-0.05)


class TestEfficiencyMetric:
    def test_auto_compute(self):
        e = EfficiencyMetric(coverage_before=0.3, coverage_after=0.6, actions=3)
        assert e.efficiency == pytest.approx(0.1)

    def test_zero_actions(self):
        e = EfficiencyMetric(coverage_before=0.3, coverage_after=0.6, actions=0)
        assert e.efficiency == 0.0

    def test_to_dict(self):
        e = EfficiencyMetric(coverage_before=0.3, coverage_after=0.6, actions=3)
        d = e.to_dict()
        assert d["efficiency"] == pytest.approx(0.1)

    def test_roundtrip(self):
        e = EfficiencyMetric(coverage_before=0.2, coverage_after=0.8, actions=5)
        restored = EfficiencyMetric.from_dict(e.to_dict())
        assert restored.efficiency == pytest.approx(e.efficiency)


# ---------------------------------------------------------------------------
# ClaimCoverage Tests
# ---------------------------------------------------------------------------

class TestClaimCoverage:
    def test_s3_coverage_empty(self):
        cc = ClaimCoverage(total_claims=0)
        assert cc.s3_coverage() == 1.0

    def test_s3_coverage(self):
        cc = ClaimCoverage(
            total_claims=3,
            by_severity={"S3": {"verified": 1, "unknown": 2}},
        )
        assert cc.s3_coverage() == pytest.approx(1.0 / 3.0)

    def test_s2_coverage(self):
        cc = ClaimCoverage(
            total_claims=2,
            by_severity={"S2": {"verified": 1, "waived": 1}},
        )
        assert cc.s2_coverage() == pytest.approx(1.0)

    def test_summary(self):
        cc = ClaimCoverage(
            total_claims=5,
            weighted_coverage=0.73,
            by_severity={"S3": {"verified": 1, "unknown": 1}, "S2": {"verified": 2}},
        )
        s = cc.summary()
        assert "73.0%" in s
        assert "S3" in s
        assert "S2" in s

    def test_to_dict(self):
        cc = ClaimCoverage(total_claims=5, weighted_coverage=0.73)
        d = cc.to_dict()
        assert d["total_claims"] == 5
        assert d["weighted_coverage"] == 0.73

    def test_roundtrip(self):
        cc = ClaimCoverage(total_claims=3, by_status={"verified": 2},
                           by_severity={"S1": {"verified": 2}},
                           weighted_coverage=0.8)
        restored = ClaimCoverage.from_dict(cc.to_dict())
        assert restored.total_claims == 3
        assert restored.weighted_coverage == 0.8


class TestComputeClaimCoverage:
    def test_basic(self):
        claims = [
            MetricClaim("c1", "a", MetricSeverity.S1, VerificationStatus.VERIFIED),
            MetricClaim("c2", "b", MetricSeverity.S2),
            MetricClaim("c3", "c", MetricSeverity.S3, VerificationStatus.VERIFIED),
        ]
        cc = compute_claim_coverage(claims)
        assert cc.total_claims == 3
        assert cc.by_status["verified"] == 2
        assert cc.by_status["unknown"] == 1
        assert cc.by_severity["S1"]["verified"] == 1
        assert cc.weighted_coverage == pytest.approx(11.0 / 14.0)


# ---------------------------------------------------------------------------
# CoverageSnapshot Tests
# ---------------------------------------------------------------------------

class TestCoverageSnapshot:
    def test_create(self):
        s = CoverageSnapshot(
            ts="2025-01-01T00:00:00Z", coverage=0.5,
            total_claims=10, verified_claims=5,
        )
        assert s.coverage == 0.5
        assert s.actions_taken == 0

    def test_roundtrip(self):
        s = CoverageSnapshot(
            ts="2025-01-01", coverage=0.75,
            total_claims=8, verified_claims=6, actions_taken=3,
        )
        restored = CoverageSnapshot.from_dict(s.to_dict())
        assert restored.coverage == 0.75
        assert restored.actions_taken == 3


# ---------------------------------------------------------------------------
# MetricsTracker Tests
# ---------------------------------------------------------------------------

class TestMetricsTracker:
    def test_create(self):
        t = MetricsTracker(run_id="run1")
        assert t.claims == []
        assert t.coverage == 1.0  # vacuous

    def test_add_claim(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S2))
        assert len(t.claims) == 1
        assert t.coverage == 0.0

    def test_verify_claim(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S2))
        assert t.verify_claim("c1", "evidence_42")
        assert t.coverage == pytest.approx(1.0)
        assert t.claims[0].evidence_id == "evidence_42"

    def test_verify_claim_not_found(self):
        t = MetricsTracker(run_id="run1")
        assert not t.verify_claim("nonexistent")

    def test_waive_claim(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S1))
        assert t.waive_claim("c1")
        assert t.claims[0].status == VerificationStatus.WAIVED

    def test_refute_claim(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S1))
        assert t.refute_claim("c1", "e1")
        assert t.claims[0].status == VerificationStatus.REFUTED
        assert t.coverage == 0.0

    def test_take_snapshot(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S1))
        snap = t.take_snapshot(actions_taken=2)
        assert snap.coverage == 0.0
        assert snap.total_claims == 1
        assert snap.actions_taken == 2
        assert len(t.snapshots) == 1

    def test_latest_efficiency(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S1))
        t.take_snapshot(actions_taken=0)
        t.verify_claim("c1")
        t.take_snapshot(actions_taken=2)
        eff = t.latest_efficiency()
        assert eff == pytest.approx(0.5)  # 1.0 coverage gain / 2 actions

    def test_latest_efficiency_not_enough_snapshots(self):
        t = MetricsTracker(run_id="run1")
        assert t.latest_efficiency() == 0.0
        t.take_snapshot()
        assert t.latest_efficiency() == 0.0

    def test_claim_coverage_property(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S1, VerificationStatus.VERIFIED))
        t.add_claim(MetricClaim("c2", "y", MetricSeverity.S3))
        cc = t.claim_coverage
        assert cc.total_claims == 2
        assert "S1" in cc.by_severity

    def test_to_dict(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S2))
        d = t.to_dict()
        assert d["run_id"] == "run1"
        assert len(d["claims"]) == 1
        assert "coverage" in d

    def test_roundtrip(self):
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S2, VerificationStatus.VERIFIED))
        t.take_snapshot(actions_taken=1)
        restored = MetricsTracker.from_dict(t.to_dict())
        assert restored.run_id == "run1"
        assert len(restored.claims) == 1
        assert len(restored.snapshots) == 1
        assert restored.claims[0].is_verified


# ---------------------------------------------------------------------------
# Update Claim Status Tests
# ---------------------------------------------------------------------------

class TestUpdateClaimStatus:
    def test_basic(self):
        c = MetricClaim("c1", "x", MetricSeverity.S1)
        updated = update_claim_status(c, VerificationStatus.VERIFIED, "e1")
        assert updated.status == VerificationStatus.VERIFIED
        assert updated.evidence_id == "e1"
        # Original unchanged
        assert c.status == VerificationStatus.UNKNOWN

    def test_preserves_evidence(self):
        c = MetricClaim("c1", "x", MetricSeverity.S1, evidence_id="old")
        updated = update_claim_status(c, VerificationStatus.REFUTED)
        assert updated.evidence_id == "old"


# ---------------------------------------------------------------------------
# Store Tests
# ---------------------------------------------------------------------------

class TestMetricsStore:
    def test_create(self, tmp_path):
        store = MetricsStore(governor_dir=tmp_path / ".governor")
        assert store.metrics_dir == tmp_path / ".governor" / "metrics"

    def test_save_load(self, tmp_path):
        store = MetricsStore(governor_dir=tmp_path / ".governor")
        t = MetricsTracker(run_id="run1")
        t.add_claim(MetricClaim("c1", "x", MetricSeverity.S2))
        store.save_tracker(t)
        loaded = store.load_tracker("run1")
        assert loaded is not None
        assert loaded.run_id == "run1"
        assert len(loaded.claims) == 1

    def test_load_missing(self, tmp_path):
        store = MetricsStore(governor_dir=tmp_path / ".governor")
        assert store.load_tracker("nonexistent") is None

    def test_list_runs(self, tmp_path):
        store = MetricsStore(governor_dir=tmp_path / ".governor")
        store.save_tracker(MetricsTracker(run_id="a"))
        store.save_tracker(MetricsTracker(run_id="b"))
        runs = store.list_runs()
        assert "a" in runs
        assert "b" in runs

    def test_list_runs_empty(self, tmp_path):
        store = MetricsStore(governor_dir=tmp_path / ".governor")
        assert store.list_runs() == []

    def test_corrupt_file(self, tmp_path):
        store = MetricsStore(governor_dir=tmp_path / ".governor")
        store._ensure_dirs()
        (store.metrics_dir / "bad.json").write_text("not json{{{")
        assert store.load_tracker("bad") is None


# ---------------------------------------------------------------------------
# Telemetry Event Tests
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create_event(self):
        evt = make_metrics_event("coverage_update", "run1", {"coverage": 0.73})
        assert evt["type"] == "metrics"
        assert evt["action"] == "coverage_update"
        assert evt["details"]["coverage"] == 0.73

    def test_create_event_minimal(self):
        evt = make_metrics_event("check")
        assert evt["run_id"] == ""
        assert evt["details"] == {}


# ---------------------------------------------------------------------------
# Golden Schema Tests
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_metric_claim_schema(self):
        c = MetricClaim("c1", "x", MetricSeverity.S2)
        d = c.to_dict()
        assert "claim_id" in d
        assert "severity" in d
        assert "status" in d

    def test_claim_coverage_schema(self):
        cc = ClaimCoverage(total_claims=0)
        d = cc.to_dict()
        assert set(d.keys()) == {"total_claims", "by_status", "by_severity", "weighted_coverage"}

    def test_efficiency_schema(self):
        e = EfficiencyMetric(coverage_before=0.3, coverage_after=0.5, actions=2)
        d = e.to_dict()
        assert set(d.keys()) == {"coverage_before", "coverage_after", "actions", "efficiency"}

    def test_snapshot_schema(self):
        s = CoverageSnapshot(ts="now", coverage=0.5, total_claims=5, verified_claims=3)
        d = s.to_dict()
        assert set(d.keys()) == {"ts", "coverage", "total_claims", "verified_claims", "actions_taken"}

    def test_event_schema(self):
        evt = make_metrics_event("test")
        assert set(evt.keys()) == {"type", "action", "run_id", "details", "ts"}


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        """Track claims → verify → snapshot → compute efficiency → persist."""
        store = MetricsStore(governor_dir=tmp_path / ".governor")
        tracker = MetricsTracker(run_id="lifecycle")

        # Add claims
        tracker.add_claim(MetricClaim("c1", "Tests pass", MetricSeverity.S3))
        tracker.add_claim(MetricClaim("c2", "Lint clean", MetricSeverity.S1))
        tracker.add_claim(MetricClaim("c3", "No secrets", MetricSeverity.S2))
        assert tracker.coverage == 0.0

        # Initial snapshot
        tracker.take_snapshot(actions_taken=0)

        # Verify the critical one
        tracker.verify_claim("c1", "evidence_pytest")
        assert tracker.coverage > 0.5  # S3 has weight 10

        # Snapshot after verification
        tracker.take_snapshot(actions_taken=1)
        eff = tracker.latest_efficiency()
        assert eff > 0  # Coverage gained

        # Verify remaining
        tracker.verify_claim("c2")
        tracker.waive_claim("c3")
        assert tracker.coverage == pytest.approx(1.0)

        # Persist
        store.save_tracker(tracker)
        loaded = store.load_tracker("lifecycle")
        assert loaded is not None
        assert loaded.coverage == pytest.approx(1.0)
        assert len(loaded.snapshots) == 2

    def test_coverage_summary(self):
        tracker = MetricsTracker(run_id="summary")
        tracker.add_claim(MetricClaim("c1", "x", MetricSeverity.S3, VerificationStatus.VERIFIED))
        tracker.add_claim(MetricClaim("c2", "y", MetricSeverity.S3))
        cc = tracker.claim_coverage
        s = cc.summary()
        assert "S3: 50.0%" in s


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_all_refuted(self):
        claims = [
            MetricClaim("c1", "x", MetricSeverity.S1, VerificationStatus.REFUTED),
            MetricClaim("c2", "y", MetricSeverity.S2, VerificationStatus.REFUTED),
        ]
        assert compute_coverage(claims) == 0.0

    def test_mixed_statuses(self):
        claims = [
            MetricClaim("c1", "a", MetricSeverity.S1, VerificationStatus.VERIFIED),
            MetricClaim("c2", "b", MetricSeverity.S1, VerificationStatus.WAIVED),
            MetricClaim("c3", "c", MetricSeverity.S1, VerificationStatus.REFUTED),
            MetricClaim("c4", "d", MetricSeverity.S1, VerificationStatus.UNKNOWN),
            MetricClaim("c5", "e", MetricSeverity.S1, VerificationStatus.PENDING),
        ]
        # 2/5 covered (verified + waived)
        assert compute_coverage(claims) == pytest.approx(2.0 / 5.0)

    def test_store_default_dir(self):
        store = MetricsStore()
        assert store.governor_dir == Path(".governor")

    def test_severity_weights_config(self):
        assert SEVERITY_WEIGHTS[MetricSeverity.S1] < SEVERITY_WEIGHTS[MetricSeverity.S2]
        assert SEVERITY_WEIGHTS[MetricSeverity.S2] < SEVERITY_WEIGHTS[MetricSeverity.S3]
