# SPDX-License-Identifier: Apache-2.0
"""Tests for coherence_budget — CBI composite index (AG2 Layer 2.1-C)."""

import json
import math
from pathlib import Path

import pytest

from governor.coherence_budget import (
    CBIStatus,
    ClosureDecision,
    CBIClaimStatus,
    CBIUnknownStatus,
    InvariantID,
    MetricID,
    CBIClaim,
    CBIUnknown,
    CBIResult,
    ClosureGateResult,
    CoherenceBudgetStore,
    compute_m1,
    compute_m2,
    compute_m3,
    compute_m4,
    compute_m5,
    compute_m6,
    compute_m7,
    compute_m8,
    compute_dt,
    attenuate_epistemic,
    compute_slow_hash,
    compute_drift_distance,
    compute_stability_score,
    compute_soft_score,
    compute_invariant_penalty,
    classify_cbi,
    compute_cbi,
    compute_uncertainty,
    check_uncertainty_invariant,
    check_passivity,
    confidence_cap,
    make_cbi_event,
    DEFAULT_INVARIANT_WEIGHTS,
    SEVERITY_WEIGHTS,
    DEFAULT_UNCERTAINTY_THRESHOLD,
    UNSAFE_VIOLATION_THRESHOLD,
    PASSIVITY_CONFIDENCE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_cbi_status_values(self):
        assert len(CBIStatus) == 5
        assert CBIStatus.OK.value == "OK"
        assert CBIStatus.UNSAFE.value == "UNSAFE"

    def test_closure_decision(self):
        assert len(ClosureDecision) == 3

    def test_claim_status(self):
        assert len(CBIClaimStatus) == 4

    def test_unknown_status(self):
        assert len(CBIUnknownStatus) == 3

    def test_invariant_ids(self):
        assert len(InvariantID) == 7
        assert InvariantID.S1.value == "S1"
        assert InvariantID.S7.value == "S7"

    def test_metric_ids(self):
        assert len(MetricID) == 8
        assert MetricID.M1.value == "M1"
        assert MetricID.M8.value == "M8"


# ---------------------------------------------------------------------------
# M1: Switching health
# ---------------------------------------------------------------------------

class TestM1:
    def test_perfect(self):
        v = compute_m1(1.0, 1.0)
        assert abs(v - 1.0) < 1e-6

    def test_zero_rate(self):
        assert compute_m1(0.0, 1.0) == 0.0

    def test_lock_in(self):
        v = compute_m1(1.0, 1.0, lock_in_fraction=0.5)
        assert v < 1.0

    def test_thrash(self):
        v = compute_m1(1.0, 1.0, thrash_fraction=0.5)
        assert v < 1.0

    def test_high_ratio(self):
        v = compute_m1(10.0, 1.0)
        assert 0.0 < v < 1.0


# ---------------------------------------------------------------------------
# M2: Metastability index
# ---------------------------------------------------------------------------

class TestM2:
    def test_empty(self):
        assert compute_m2({}) == 1.0

    def test_single_coalition(self):
        v = compute_m2({"a": 10})
        # entropy = 0, below h_low → penalty
        assert v < 1.0

    def test_balanced(self):
        v = compute_m2({"a": 5, "b": 5, "c": 5})
        assert v > 0.5

    def test_high_entropy(self):
        d = {f"c{i}": 1 for i in range(100)}
        v = compute_m2(d, h_low=0.3, h_high=0.8)
        # Very high entropy, above h_high
        assert v < 1.0


# ---------------------------------------------------------------------------
# M3: Integration/segregation
# ---------------------------------------------------------------------------

class TestM3:
    def test_balanced(self):
        v = compute_m3(5, 10, 0.5, 1.0)
        assert abs(v - 1.0) < 1e-6

    def test_no_refs(self):
        assert compute_m3(0, 0) == 1.0

    def test_all_cross(self):
        v = compute_m3(10, 10, 0.5, 1.0)
        assert v < 1.0  # integration = 1.0, far from 0.5


# ---------------------------------------------------------------------------
# M4: Cross-timescale coupling
# ---------------------------------------------------------------------------

class TestM4:
    def test_identical(self):
        assert compute_m4({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        assert compute_m4({"a"}, {"b"}) == 0.0

    def test_empty(self):
        assert compute_m4(set(), set()) == 1.0

    def test_partial(self):
        v = compute_m4({"a", "b"}, {"b", "c"})
        assert abs(v - 1/3) < 1e-9


# ---------------------------------------------------------------------------
# M5: Drift rate
# ---------------------------------------------------------------------------

class TestM5:
    def test_zero_drift(self):
        assert abs(compute_m5(0.0) - 1.0) < 1e-6

    def test_high_drift(self):
        v = compute_m5(5.0)
        assert v < 0.01


# ---------------------------------------------------------------------------
# M6: Regime chatter
# ---------------------------------------------------------------------------

class TestM6:
    def test_no_switches(self):
        v = compute_m6(0, 1.0)
        assert abs(v - 1.0) < 1e-6

    def test_many_switches(self):
        v = compute_m6(50, 1.0)
        assert v < 0.1

    def test_stuck(self):
        v = compute_m6(0, 1.0, stuck_fraction=0.96)
        assert abs(v - 0.5) < 1e-6

    def test_zero_hours(self):
        v = compute_m6(5, 0.0)
        assert abs(v - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# M7: Provenance integrity
# ---------------------------------------------------------------------------

class TestM7:
    def test_perfect(self):
        assert abs(compute_m7(10, 10) - 1.0) < 1e-6

    def test_no_trace(self):
        assert compute_m7(0, 10) == 0.0

    def test_unknown_causes(self):
        v = compute_m7(10, 10, unknown_cause_count=5)
        assert abs(v - 0.5) < 1e-6

    def test_empty(self):
        assert compute_m7(0, 0) == 1.0


# ---------------------------------------------------------------------------
# M8: Recovery time
# ---------------------------------------------------------------------------

class TestM8:
    def test_instant(self):
        assert compute_m8(0.0) == 1.0

    def test_slow_recovery(self):
        v = compute_m8(300.0, 60.0)
        assert v < 0.01

    def test_target(self):
        v = compute_m8(60.0, 60.0)
        assert abs(v - math.exp(-1)) < 1e-6


# ---------------------------------------------------------------------------
# Δt and attenuation
# ---------------------------------------------------------------------------

class TestDeltaT:
    def test_dt_ratio(self):
        assert abs(compute_dt(2.0, 1.0) - 2.0) < 1e-6

    def test_dt_zero_refresh(self):
        assert compute_dt(1.0, 0.0) == 0.0

    def test_attenuate_no_debt(self):
        assert abs(attenuate_epistemic(1.0, 0.5) - 1.0) < 1e-6

    def test_attenuate_debt(self):
        v = attenuate_epistemic(1.0, 3.0)
        assert v < 1.0
        assert v > 0.0

    def test_attenuate_high_debt(self):
        v = attenuate_epistemic(1.0, 10.0)
        assert v < 0.2


# ---------------------------------------------------------------------------
# Slow hash + drift
# ---------------------------------------------------------------------------

class TestSlowHash:
    def test_deterministic(self):
        h1 = compute_slow_hash(["Use React", "Prefer TypeScript"])
        h2 = compute_slow_hash(["Use React", "Prefer TypeScript"])
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_slow_hash(["Use React"])
        h2 = compute_slow_hash(["use react"])
        assert h1 == h2

    def test_order_independent(self):
        h1 = compute_slow_hash(["A", "B"])
        h2 = compute_slow_hash(["B", "A"])
        assert h1 == h2

    def test_drift_same(self):
        h = compute_slow_hash(["A"])
        assert compute_drift_distance(h, h) == 0.0

    def test_drift_different(self):
        h1 = compute_slow_hash(["A"])
        h2 = compute_slow_hash(["B"])
        d = compute_drift_distance(h1, h2)
        assert 0.0 < d <= 1.0

    def test_drift_empty(self):
        assert compute_drift_distance("", "abc") == 0.0


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_stability_score_all_one(self):
        v = compute_stability_score(1, 1, 1, 1, 1, 1)
        assert abs(v - 1.0) < 1e-6

    def test_stability_score_all_zero(self):
        assert compute_stability_score(0, 0, 0, 0, 0, 0) == 0.0

    def test_soft_score_all_one(self):
        v = compute_soft_score(1.0, 1.0, 1.0)
        assert abs(v - 1.0) < 1e-6

    def test_invariant_penalty_clean(self):
        violations = {"S1": 0, "S2": 0, "S3": 0, "S4": 0, "S5": 0, "S6": 0, "S7": 0}
        assert abs(compute_invariant_penalty(violations) - 1.0) < 1e-6

    def test_invariant_penalty_full(self):
        violations = {"S1": 1, "S2": 1, "S3": 1, "S4": 1, "S5": 1, "S6": 1, "S7": 1}
        p = compute_invariant_penalty(violations)
        assert p < 0.5

    def test_invariant_weights_sum(self):
        total = sum(DEFAULT_INVARIANT_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# classify_cbi
# ---------------------------------------------------------------------------

class TestClassifyCBI:
    def test_ok(self):
        assert classify_cbi(85) == CBIStatus.OK

    def test_normal(self):
        assert classify_cbi(70) == CBIStatus.NORMAL

    def test_debt(self):
        assert classify_cbi(50) == CBIStatus.DEBT

    def test_unstable(self):
        assert classify_cbi(30) == CBIStatus.UNSTABLE

    def test_unsafe(self):
        assert classify_cbi(10) == CBIStatus.UNSAFE

    def test_unsafe_override(self):
        assert classify_cbi(90, has_unsafe_violation=True) == CBIStatus.UNSAFE


# ---------------------------------------------------------------------------
# compute_cbi (full)
# ---------------------------------------------------------------------------

class TestComputeCBI:
    def test_perfect(self):
        violations = {f"S{i}": 0.0 for i in range(1, 8)}
        metrics = {f"M{i}": 1.0 for i in range(1, 9)}
        result = compute_cbi(violations, metrics, D=0.0)
        assert result.cbi > 90
        assert result.status == CBIStatus.OK

    def test_all_broken(self):
        violations = {f"S{i}": 1.0 for i in range(1, 8)}
        metrics = {f"M{i}": 0.0 for i in range(1, 9)}
        result = compute_cbi(violations, metrics, D=5.0)
        assert result.cbi < 20
        assert result.status == CBIStatus.UNSAFE

    def test_unsafe_violation_caps(self):
        violations = {"S1": 0.0, "S2": 0.0, "S3": 0.0, "S4": 0.0,
                       "S5": 0.0, "S6": 0.0, "S7": 0.9}
        metrics = {f"M{i}": 1.0 for i in range(1, 9)}
        result = compute_cbi(violations, metrics, D=0.0)
        assert result.cbi <= 20
        assert result.status == CBIStatus.UNSAFE

    def test_dt_attenuates(self):
        violations = {f"S{i}": 0.0 for i in range(1, 8)}
        metrics = {f"M{i}": 1.0 for i in range(1, 9)}
        r_low = compute_cbi(violations, metrics, D=0.0)
        r_high = compute_cbi(violations, metrics, D=5.0)
        assert r_high.cbi < r_low.cbi

    def test_roundtrip(self):
        violations = {f"S{i}": 0.1 for i in range(1, 8)}
        metrics = {f"M{i}": 0.8 for i in range(1, 9)}
        r = compute_cbi(violations, metrics, D=1.5)
        d = r.to_dict()
        r2 = CBIResult.from_dict(d)
        assert abs(r2.cbi - r.cbi) < 0.01
        assert r2.status == r.status

    def test_has_timestamp(self):
        r = compute_cbi({}, {}, D=0.0)
        assert r.ts


# ---------------------------------------------------------------------------
# Uncertainty + Closure Gate
# ---------------------------------------------------------------------------

class TestUncertainty:
    def test_all_verified(self):
        claims = [CBIClaim("c1", "S1", CBIClaimStatus.VERIFIED)]
        u = compute_uncertainty(claims, [])
        assert u == 0.0

    def test_unverified(self):
        claims = [CBIClaim("c1", "S1", CBIClaimStatus.UNKNOWN)]
        u = compute_uncertainty(claims, [])
        assert u == 1.0

    def test_severity_weighted(self):
        claims = [CBIClaim("c1", "S3", CBIClaimStatus.UNKNOWN)]
        u = compute_uncertainty(claims, [])
        assert u == 10.0

    def test_open_unknowns(self):
        unknowns = [CBIUnknown("u1", CBIUnknownStatus.OPEN, weight=2.0)]
        u = compute_uncertainty([], unknowns)
        assert u == 2.0

    def test_mixed(self):
        claims = [
            CBIClaim("c1", "S2", CBIClaimStatus.UNKNOWN),
            CBIClaim("c2", "S1", CBIClaimStatus.VERIFIED),
        ]
        unknowns = [CBIUnknown("u1", CBIUnknownStatus.OPEN, weight=1.5)]
        u = compute_uncertainty(claims, unknowns)
        assert abs(u - 4.5) < 1e-9  # 3.0 (S2) + 1.5 (unknown)


class TestClosureGate:
    def test_allow(self):
        claims = [CBIClaim("c1", "S1", CBIClaimStatus.VERIFIED)]
        r = check_uncertainty_invariant(claims, [])
        assert r.decision == ClosureDecision.ALLOW

    def test_deny(self):
        claims = [CBIClaim("c1", "S3", CBIClaimStatus.UNKNOWN)]
        r = check_uncertainty_invariant(claims, [], threshold=3.0)
        assert r.decision == ClosureDecision.DENY
        assert r.uncertainty == 10.0

    def test_waiver(self):
        claims = [CBIClaim("c1", "S3", CBIClaimStatus.UNKNOWN)]
        r = check_uncertainty_invariant(claims, [], threshold=3.0, has_human_waiver=True)
        assert r.decision == ClosureDecision.ALLOW_WITH_WAIVER

    def test_counts(self):
        claims = [
            CBIClaim("c1", "S1", CBIClaimStatus.UNKNOWN),
            CBIClaim("c2", "S1", CBIClaimStatus.VERIFIED),
        ]
        unknowns = [CBIUnknown("u1", CBIUnknownStatus.OPEN)]
        r = check_uncertainty_invariant(claims, unknowns, threshold=100)
        assert r.unverified_claims == 1
        assert r.open_unknowns == 1

    def test_roundtrip(self):
        r = check_uncertainty_invariant([], [])
        d = r.to_dict()
        r2 = ClosureGateResult.from_dict(d)
        assert r2.decision == r.decision


# ---------------------------------------------------------------------------
# Passivity (Invariant H)
# ---------------------------------------------------------------------------

class TestPassivity:
    def test_low_confidence(self):
        c = CBIClaim("c1", "S1", CBIClaimStatus.UNKNOWN, confidence=0.3)
        ok, _ = check_passivity(c)
        assert ok

    def test_high_confidence_with_evidence(self):
        c = CBIClaim("c1", "S1", CBIClaimStatus.UNKNOWN, confidence=0.9, evidence_count=1)
        ok, _ = check_passivity(c)
        assert ok

    def test_high_confidence_no_evidence(self):
        c = CBIClaim("c1", "S1", CBIClaimStatus.UNKNOWN, confidence=0.9)
        ok, reason = check_passivity(c)
        assert not ok
        assert "evidence" in reason

    def test_waiver(self):
        c = CBIClaim("c1", "S1", CBIClaimStatus.UNKNOWN, confidence=0.9)
        ok, _ = check_passivity(c, has_waiver=True)
        assert ok

    def test_evidence_refs(self):
        c = CBIClaim("c1", "S1", CBIClaimStatus.UNKNOWN, confidence=0.9,
                     evidence_refs=["ref1"])
        ok, _ = check_passivity(c)
        assert ok


# ---------------------------------------------------------------------------
# Confidence cap
# ---------------------------------------------------------------------------

class TestConfidenceCap:
    def test_low_d_good_evidence(self):
        assert confidence_cap(0.5, 3) == 0.95

    def test_high_d(self):
        assert confidence_cap(5.0, 0) == 0.35

    def test_moderate(self):
        assert confidence_cap(2.0, 1) == 0.60


# ---------------------------------------------------------------------------
# CBIClaim / CBIUnknown
# ---------------------------------------------------------------------------

class TestCBIClaim:
    def test_roundtrip(self):
        c = CBIClaim("c1", "S2", CBIClaimStatus.VERIFIED, 0.8, 2, ["r1"])
        d = c.to_dict()
        c2 = CBIClaim.from_dict(d)
        assert c2.id == "c1"
        assert c2.severity == "S2"
        assert c2.evidence_count == 2


class TestCBIUnknown:
    def test_roundtrip(self):
        u = CBIUnknown("u1", CBIUnknownStatus.OPEN, 2.5)
        d = u.to_dict()
        u2 = CBIUnknown.from_dict(d)
        assert u2.weight == 2.5


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestCoherenceBudgetStore:
    def test_save_load(self, tmp_path):
        store = CoherenceBudgetStore(governor_dir=tmp_path)
        violations = {f"S{i}": 0.1 for i in range(1, 8)}
        metrics = {f"M{i}": 0.8 for i in range(1, 9)}
        r = compute_cbi(violations, metrics, D=1.0)
        store.save("run1", r)
        loaded = store.load("run1")
        assert loaded is not None
        assert abs(loaded.cbi - r.cbi) < 0.01

    def test_list_runs(self, tmp_path):
        store = CoherenceBudgetStore(governor_dir=tmp_path)
        r = compute_cbi({}, {})
        store.save("a", r)
        store.save("b", r)
        assert "a" in store.list_runs()
        assert "b" in store.list_runs()

    def test_load_missing(self, tmp_path):
        store = CoherenceBudgetStore(governor_dir=tmp_path)
        assert store.load("nope") is None

    def test_closure_save_load(self, tmp_path):
        store = CoherenceBudgetStore(governor_dir=tmp_path)
        r = check_uncertainty_invariant([], [])
        store.save_closure("run1", r)
        loaded = store.load_closure("run1")
        assert loaded is not None
        assert loaded.decision == ClosureDecision.ALLOW

    def test_default_dir(self):
        store = CoherenceBudgetStore()
        assert store.cbi_dir == Path(".governor") / "coherence"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create(self):
        e = make_cbi_event("cbi_update", "r1", {"cbi": 72.3})
        assert e["type"] == "coherence_budget"
        assert e["action"] == "cbi_update"
        assert e["ts"]

    def test_minimal(self):
        e = make_cbi_event("compute")
        assert e["details"] == {}


# ---------------------------------------------------------------------------
# Golden schemas
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_cbi_result_schema(self):
        r = compute_cbi({f"S{i}": 0.1 for i in range(1, 8)},
                        {f"M{i}": 0.8 for i in range(1, 9)}, D=1.0)
        d = r.to_dict()
        required = {"cbi", "status", "invariants", "p_inv", "metrics",
                     "s_stab", "s_id", "s_epi", "s_soft", "D", "tau_v", "tau_r", "ts"}
        assert required <= set(d.keys())

    def test_closure_schema(self):
        r = check_uncertainty_invariant([], [])
        d = r.to_dict()
        required = {"decision", "uncertainty", "threshold",
                     "unverified_claims", "open_unknowns", "ts"}
        assert required <= set(d.keys())

    def test_event_schema(self):
        e = make_cbi_event("update")
        required = {"type", "action", "run_id", "details", "ts"}
        assert required <= set(e.keys())


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        """Full CBI lifecycle: compute → store → closure check."""
        store = CoherenceBudgetStore(governor_dir=tmp_path)

        # Compute CBI
        violations = {"S1": 0.05, "S2": 0.0, "S3": 0.1, "S4": 0.0,
                       "S5": 0.02, "S6": 0.0, "S7": 0.15}
        metrics = {"M1": 0.9, "M2": 0.85, "M3": 0.9, "M4": 0.8,
                   "M5": 0.95, "M6": 0.85, "M7": 0.8, "M8": 0.9}
        result = compute_cbi(violations, metrics, D=1.2)

        assert result.status in (CBIStatus.OK, CBIStatus.NORMAL)
        store.save("run1", result)

        # Closure gate
        claims = [
            CBIClaim("c1", "S1", CBIClaimStatus.VERIFIED),
            CBIClaim("c2", "S2", CBIClaimStatus.UNKNOWN),
        ]
        unknowns = [CBIUnknown("u1", CBIUnknownStatus.RESOLVED)]
        gate = check_uncertainty_invariant(claims, unknowns)
        assert gate.decision == ClosureDecision.ALLOW
        store.save_closure("run1", gate)

        # Reload
        loaded = store.load("run1")
        assert loaded is not None
        loaded_gate = store.load_closure("run1")
        assert loaded_gate is not None
        assert loaded_gate.decision == ClosureDecision.ALLOW

    def test_degraded_system(self):
        """High violations + high D → UNSAFE."""
        violations = {"S1": 0.3, "S2": 0.2, "S3": 0.4, "S4": 0.3,
                       "S5": 0.5, "S6": 0.4, "S7": 0.85}
        metrics = {"M1": 0.3, "M2": 0.4, "M3": 0.5, "M4": 0.3,
                   "M5": 0.4, "M6": 0.3, "M7": 0.2, "M8": 0.5}
        result = compute_cbi(violations, metrics, D=4.0)
        assert result.status == CBIStatus.UNSAFE
        assert result.cbi <= 20


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_inputs(self):
        r = compute_cbi({}, {}, D=0.0)
        assert r.cbi > 0  # defaults to 1.0 metrics

    def test_constants(self):
        assert sum(DEFAULT_INVARIANT_WEIGHTS.values()) > 0.99
        assert SEVERITY_WEIGHTS["S3"] > SEVERITY_WEIGHTS["S1"]
        assert UNSAFE_VIOLATION_THRESHOLD == 0.8
        assert DEFAULT_UNCERTAINTY_THRESHOLD > 0

    def test_passivity_threshold(self):
        assert PASSIVITY_CONFIDENCE_THRESHOLD > 0
        assert PASSIVITY_CONFIDENCE_THRESHOLD < 1.0
