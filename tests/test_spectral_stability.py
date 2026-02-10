"""Tests for Spectral Stability (AG2 Layer 2, Item #6)."""

import json
import math
from pathlib import Path

import pytest

from governor.spectral_stability import (
    KineticRegion,
    GateVerdict,
    GovernanceLayer,
    CouplingHotspot,
    AdjacencyViolation,
    CouplingMatrix,
    StabilityReport,
    StabilityGate,
    DEFAULT_LAYERS,
    PROFILE_OVERRIDES,
    ADJACENCY_LIMIT,
    build_coupling_matrix,
    check_adjacency,
    classify_region,
    determine_verdict,
    find_hotspots,
    compute_stability,
    make_stability_event,
    _power_iteration,
    _spectral_radius,
    _mat_vec_mul,
    _vec_norm,
    _vec_scale,
    _apply_profile,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestKineticRegion:
    def test_values(self):
        assert KineticRegion.COHERENT.value == "coherent"
        assert KineticRegion.STRAINED.value == "strained"
        assert KineticRegion.METASTABLE.value == "metastable"
        assert KineticRegion.FLICKER.value == "flicker"
        assert KineticRegion.DECOHERENT.value == "decoherent"

    def test_count(self):
        assert len(KineticRegion) == 5


class TestGateVerdict:
    def test_values(self):
        assert GateVerdict.PASS.value == "pass"
        assert GateVerdict.WARN.value == "warn"
        assert GateVerdict.BLOCK.value == "block"
        assert GateVerdict.HARD_BLOCK.value == "hard_block"

    def test_count(self):
        assert len(GateVerdict) == 4


# ---------------------------------------------------------------------------
# GovernanceLayer
# ---------------------------------------------------------------------------


class TestGovernanceLayer:
    def test_roundtrip(self):
        layer = GovernanceLayer(
            name="test_layer", rate=1.0, latency=0.5,
            capacity=10.0, feedback_up=0.3, feedback_down=0.2,
            self_feedback=0.1,
        )
        d = layer.to_dict()
        l2 = GovernanceLayer.from_dict(d)
        assert l2.name == "test_layer"
        assert l2.rate == 1.0
        assert l2.feedback_up == 0.3

    def test_defaults(self):
        layer = GovernanceLayer(name="minimal", rate=1.0, latency=0.5)
        assert layer.capacity == 0.0
        assert layer.feedback_up == 0.0
        assert layer.feedback_down == 0.0
        assert layer.self_feedback == 0.0


# ---------------------------------------------------------------------------
# CouplingHotspot
# ---------------------------------------------------------------------------


class TestCouplingHotspot:
    def test_roundtrip(self):
        h = CouplingHotspot(
            from_layer="agent", to_layer="verify",
            strength=0.5, sensitivity=0.3,
            mitigation="Reduce agent rate",
        )
        d = h.to_dict()
        h2 = CouplingHotspot.from_dict(d)
        assert h2.from_layer == "agent"
        assert h2.strength == 0.5
        assert h2.mitigation == "Reduce agent rate"


# ---------------------------------------------------------------------------
# AdjacencyViolation
# ---------------------------------------------------------------------------


class TestAdjacencyViolation:
    def test_to_dict(self):
        v = AdjacencyViolation(fast_layer="agent", slow_layer="policy", rate_ratio=500.0)
        d = v.to_dict()
        assert d["fast_layer"] == "agent"
        assert d["rate_ratio"] == 500.0


# ---------------------------------------------------------------------------
# Pure Python Linear Algebra
# ---------------------------------------------------------------------------


class TestLinearAlgebra:
    def test_mat_vec_mul(self):
        M = [[1, 2], [3, 4]]
        v = [1, 1]
        result = _mat_vec_mul(M, v)
        assert result == [3, 7]

    def test_vec_norm(self):
        assert _vec_norm([3, 4]) == 5.0
        assert _vec_norm([0, 0]) == 0.0

    def test_vec_scale(self):
        assert _vec_scale([1, 2], 3.0) == [3.0, 6.0]

    def test_power_iteration_identity(self):
        """Identity matrix has spectral radius 1."""
        M = [[1, 0], [0, 1]]
        rho = _power_iteration(M)
        assert abs(rho - 1.0) < 0.01

    def test_power_iteration_zero(self):
        """Zero matrix has spectral radius 0."""
        M = [[0, 0], [0, 0]]
        rho = _power_iteration(M)
        assert rho == 0.0

    def test_power_iteration_known(self):
        """Known matrix: [[2, 0], [0, 3]] has spectral radius 3."""
        M = [[2, 0], [0, 3]]
        rho = _power_iteration(M)
        assert abs(rho - 3.0) < 0.01

    def test_power_iteration_small(self):
        """Small coupling matrix should have small spectral radius."""
        M = [[0.1, 0.05], [0.05, 0.1]]
        rho = _power_iteration(M)
        assert rho < 0.2

    def test_spectral_radius_empty(self):
        assert _spectral_radius([]) == 0.0

    def test_spectral_radius_1x1(self):
        assert abs(_spectral_radius([[0.5]]) - 0.5) < 0.01

    def test_spectral_radius_symmetric(self):
        """Symmetric matrix: eigenvalues are real."""
        M = [[0.3, 0.1], [0.1, 0.4]]
        rho = _spectral_radius(M)
        # Eigenvalues: (0.3+0.4)/2 ± sqrt(((0.3-0.4)/2)^2 + 0.01)
        # = 0.35 ± sqrt(0.0025 + 0.01) = 0.35 ± 0.1118
        # = 0.4618, 0.2382
        assert abs(rho - 0.4618) < 0.02


# ---------------------------------------------------------------------------
# Matrix Construction
# ---------------------------------------------------------------------------


class TestBuildCouplingMatrix:
    def test_basic(self):
        layers = [
            GovernanceLayer("fast", rate=1.0, latency=0.5),
            GovernanceLayer("slow", rate=0.1, latency=5.0),
        ]
        coupling = build_coupling_matrix(layers)
        assert coupling.spectral_radius >= 0.0
        assert len(coupling.matrix) == 2
        assert len(coupling.matrix[0]) == 2

    def test_self_feedback(self):
        layers = [
            GovernanceLayer("layer", rate=1.0, latency=0.5, self_feedback=0.3),
        ]
        coupling = build_coupling_matrix(layers)
        assert coupling.matrix[0][0] == 0.3

    def test_inter_layer_coupling(self):
        layers = [
            GovernanceLayer("fast", rate=1.0, latency=0.5, feedback_up=0.5),
            GovernanceLayer("slow", rate=0.1, latency=5.0, feedback_down=0.4),
        ]
        coupling = build_coupling_matrix(layers)
        # M[1][0] should be > 0 (fast influences slow via feedback_up)
        assert coupling.matrix[1][0] > 0
        # M[0][1] should be > 0 (slow influences fast via feedback_down)
        assert coupling.matrix[0][1] > 0

    def test_sensitivity_computed(self):
        layers = [
            GovernanceLayer("a", rate=1.0, latency=0.5, feedback_up=0.3, self_feedback=0.2),
            GovernanceLayer("b", rate=0.5, latency=1.0, feedback_down=0.3, self_feedback=0.1),
        ]
        coupling = build_coupling_matrix(layers)
        assert len(coupling.sensitivity) > 0

    def test_default_layers(self):
        coupling = build_coupling_matrix(DEFAULT_LAYERS)
        assert coupling.spectral_radius < 1.0  # Default config should be stable
        assert len(coupling.matrix) == 4

    def test_capacity_pressure(self):
        """Layer near capacity should have increased self-feedback."""
        layers = [
            GovernanceLayer("stressed", rate=5.0, latency=0.5, capacity=3.0, self_feedback=0.1),
        ]
        coupling = build_coupling_matrix(layers)
        # Self-feedback should be > 0.1 due to capacity pressure
        assert coupling.matrix[0][0] > 0.1

    def test_roundtrip(self):
        coupling = build_coupling_matrix(DEFAULT_LAYERS)
        d = coupling.to_dict()
        c2 = CouplingMatrix.from_dict(d)
        assert c2.spectral_radius == coupling.spectral_radius
        assert len(c2.layers) == len(coupling.layers)


# ---------------------------------------------------------------------------
# Adjacency Checking
# ---------------------------------------------------------------------------


class TestCheckAdjacency:
    def test_no_violations(self):
        layers = [
            GovernanceLayer("fast", rate=10.0, latency=0.1),
            GovernanceLayer("slow", rate=1.0, latency=1.0),
        ]
        violations = check_adjacency(layers)
        assert len(violations) == 0

    def test_violation(self):
        layers = [
            GovernanceLayer("fast", rate=1000.0, latency=0.001),
            GovernanceLayer("slow", rate=0.001, latency=1000.0),
        ]
        violations = check_adjacency(layers)
        assert len(violations) == 1
        assert violations[0].rate_ratio > ADJACENCY_LIMIT

    def test_default_layers(self):
        violations = check_adjacency(DEFAULT_LAYERS)
        # Default layers should have some adjacency issues
        # (agent rate=1.0 vs policy rate=0.001 → κ=1000)
        # But they're not adjacent — the check is between consecutive pairs
        assert isinstance(violations, list)

    def test_zero_rate(self):
        layers = [
            GovernanceLayer("fast", rate=1.0, latency=0.5),
            GovernanceLayer("stopped", rate=0.0, latency=0.0),
        ]
        violations = check_adjacency(layers)
        assert len(violations) == 1
        assert violations[0].rate_ratio == float("inf")


# ---------------------------------------------------------------------------
# Region Classification
# ---------------------------------------------------------------------------


class TestClassifyRegion:
    def test_coherent(self):
        assert classify_region(0.3) == KineticRegion.COHERENT

    def test_strained(self):
        assert classify_region(0.75) == KineticRegion.STRAINED

    def test_metastable(self):
        assert classify_region(0.92) == KineticRegion.METASTABLE

    def test_flicker(self):
        assert classify_region(0.97) == KineticRegion.FLICKER

    def test_decoherent_high_rho(self):
        assert classify_region(1.2) == KineticRegion.DECOHERENT

    def test_decoherent_adjacency(self):
        violations = [AdjacencyViolation("fast", "slow", 500.0)]
        assert classify_region(0.3, violations) == KineticRegion.DECOHERENT

    def test_boundary_070(self):
        assert classify_region(0.7) == KineticRegion.STRAINED

    def test_boundary_090(self):
        assert classify_region(0.9) == KineticRegion.METASTABLE

    def test_boundary_095(self):
        assert classify_region(0.95) == KineticRegion.FLICKER

    def test_boundary_100(self):
        assert classify_region(1.0) == KineticRegion.DECOHERENT


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


class TestDetermineVerdict:
    def test_pass(self):
        assert determine_verdict(KineticRegion.COHERENT) == GateVerdict.PASS

    def test_warn(self):
        assert determine_verdict(KineticRegion.STRAINED) == GateVerdict.WARN

    def test_block(self):
        assert determine_verdict(KineticRegion.METASTABLE) == GateVerdict.BLOCK

    def test_hard_block_flicker(self):
        assert determine_verdict(KineticRegion.FLICKER) == GateVerdict.HARD_BLOCK

    def test_hard_block_decoherent(self):
        assert determine_verdict(KineticRegion.DECOHERENT) == GateVerdict.HARD_BLOCK


# ---------------------------------------------------------------------------
# Hotspot Detection
# ---------------------------------------------------------------------------


class TestFindHotspots:
    def test_basic(self):
        layers = [
            GovernanceLayer("a", rate=1.0, latency=0.5, feedback_up=0.5, self_feedback=0.3),
            GovernanceLayer("b", rate=0.5, latency=1.0, feedback_down=0.4, self_feedback=0.2),
        ]
        coupling = build_coupling_matrix(layers)
        hotspots = find_hotspots(coupling)
        assert len(hotspots) > 0
        for h in hotspots:
            assert h.strength > 0
            assert len(h.mitigation) > 0

    def test_top_n(self):
        coupling = build_coupling_matrix(DEFAULT_LAYERS)
        hotspots = find_hotspots(coupling, top_n=2)
        assert len(hotspots) <= 2

    def test_mitigation_text(self):
        layers = [
            GovernanceLayer("agent", rate=1.0, latency=0.5, self_feedback=0.3),
            GovernanceLayer("verify", rate=0.5, latency=1.0, feedback_down=0.4),
        ]
        coupling = build_coupling_matrix(layers)
        hotspots = find_hotspots(coupling)
        assert all(h.mitigation for h in hotspots)


# ---------------------------------------------------------------------------
# Stability Report
# ---------------------------------------------------------------------------


class TestStabilityReport:
    def test_roundtrip(self):
        report = compute_stability()
        d = report.to_dict()
        r2 = StabilityReport.from_dict(d)
        assert r2.report_id == report.report_id
        assert r2.spectral_radius == report.spectral_radius
        assert r2.region == report.region

    def test_summary(self):
        report = compute_stability()
        summary = report.to_summary()
        assert "ρ(M)" in summary
        assert report.region.value in summary

    def test_markdown(self):
        report = compute_stability()
        md = report.to_markdown()
        assert "# Stability Report" in md
        assert report.verdict.value.upper() in md

    def test_stable_defaults(self):
        report = compute_stability()
        assert report.stable  # Default topology should be stable

    def test_margin_positive(self):
        report = compute_stability()
        assert report.margin > 0


# ---------------------------------------------------------------------------
# compute_stability
# ---------------------------------------------------------------------------


class TestComputeStability:
    def test_default_stable(self):
        report = compute_stability()
        assert report.stable
        assert report.spectral_radius < 1.0
        assert report.region in (KineticRegion.COHERENT, KineticRegion.STRAINED)

    def test_with_profile(self):
        report = compute_stability(profile="production")
        assert report.stable

    def test_unstable_topology(self):
        """High feedback creates instability."""
        layers = [
            GovernanceLayer("fast", rate=10.0, latency=0.1, self_feedback=0.9,
                            feedback_up=0.9),
            GovernanceLayer("slow", rate=1.0, latency=1.0, self_feedback=0.9,
                            feedback_down=0.9),
        ]
        report = compute_stability(layers)
        assert report.spectral_radius > 0.5  # High coupling

    def test_very_unstable(self):
        """Extremely high feedback should produce instability."""
        layers = [
            GovernanceLayer("a", rate=1.0, latency=0.5, self_feedback=1.5),
        ]
        report = compute_stability(layers)
        assert report.spectral_radius >= 1.0
        assert not report.stable
        assert report.verdict == GateVerdict.HARD_BLOCK

    def test_single_layer(self):
        layers = [GovernanceLayer("single", rate=1.0, latency=0.5, self_feedback=0.1)]
        report = compute_stability(layers)
        assert report.stable
        assert abs(report.spectral_radius - 0.1) < 0.02

    def test_report_has_coupling(self):
        report = compute_stability()
        assert report.coupling is not None
        assert len(report.coupling.matrix) == len(DEFAULT_LAYERS)


# ---------------------------------------------------------------------------
# Profile Application
# ---------------------------------------------------------------------------


class TestApplyProfile:
    def test_no_profile(self):
        layers = _apply_profile(DEFAULT_LAYERS, None)
        assert layers[0].rate == DEFAULT_LAYERS[0].rate

    def test_greenfield(self):
        layers = _apply_profile(DEFAULT_LAYERS, "greenfield")
        # Greenfield increases agent rate
        assert layers[0].rate == 2.0

    def test_production(self):
        layers = _apply_profile(DEFAULT_LAYERS, "production")
        # Production decreases agent rate
        assert layers[0].rate == 0.2

    def test_unknown_profile(self):
        layers = _apply_profile(DEFAULT_LAYERS, "nonexistent")
        assert layers[0].rate == DEFAULT_LAYERS[0].rate


# ---------------------------------------------------------------------------
# StabilityGate
# ---------------------------------------------------------------------------


class TestStabilityGate:
    def test_check(self):
        gate = StabilityGate()
        report = gate.check()
        assert report.stable
        assert report.verdict in (GateVerdict.PASS, GateVerdict.WARN)

    def test_is_stable(self):
        gate = StabilityGate()
        assert gate.is_stable()

    def test_allows(self):
        gate = StabilityGate()
        assert gate.allows()

    def test_with_profile(self):
        gate = StabilityGate(profile="production")
        report = gate.check()
        assert report.stable

    def test_last_report(self):
        gate = StabilityGate()
        assert gate.last_report is None
        gate.check()
        assert gate.last_report is not None

    def test_status(self):
        gate = StabilityGate()
        status = gate.status()
        assert "spectral_radius" in status
        assert "region" in status
        assert "verdict" in status
        assert "stable" in status

    def test_unstable_gate(self):
        layers = [
            GovernanceLayer("a", rate=1.0, latency=0.5, self_feedback=1.5),
        ]
        gate = StabilityGate(layers=layers)
        assert not gate.is_stable()
        assert not gate.allows()

    def test_save_report(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        gate = StabilityGate(governor_dir=gov_dir)
        gate.check()
        stability_dir = gov_dir / "stability"
        assert stability_dir.exists()
        assert len(list(stability_dir.glob("*.json"))) == 1

    def test_profile_override(self):
        gate = StabilityGate(profile="greenfield")
        report = gate.check(profile="production")
        # Profile override should use production, not greenfield
        assert report.stable


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class TestMakeStabilityEvent:
    def test_basic(self):
        report = compute_stability()
        event = make_stability_event(report)
        assert event["type"] == "stability_check"
        assert "spectral_radius" in event
        assert "region" in event
        assert "timestamp" in event


# ---------------------------------------------------------------------------
# Golden Schema Tests
# ---------------------------------------------------------------------------


class TestGoldenSchemas:
    def test_governance_layer_schema(self):
        layer = GovernanceLayer("test", rate=1.0, latency=0.5)
        d = layer.to_dict()
        required = {"name", "rate", "latency", "capacity", "feedback_up", "feedback_down", "self_feedback"}
        assert required == set(d.keys())

    def test_coupling_hotspot_schema(self):
        h = CouplingHotspot("a", "b", 0.5, 0.3, "reduce")
        d = h.to_dict()
        required = {"from_layer", "to_layer", "strength", "sensitivity", "mitigation"}
        assert required == set(d.keys())

    def test_stability_report_schema(self):
        report = compute_stability()
        d = report.to_dict()
        required = {
            "report_id", "stable", "spectral_radius", "margin",
            "region", "verdict", "dominant_mode", "hotspots",
            "adjacency_violations", "recommendations", "created_at",
            "coupling",
        }
        assert required == set(d.keys())

    def test_coupling_matrix_schema(self):
        coupling = build_coupling_matrix(DEFAULT_LAYERS)
        d = coupling.to_dict()
        required = {"layers", "matrix", "spectral_radius", "dominant_eigenvalue", "sensitivity"}
        assert required == set(d.keys())

    def test_stability_event_schema(self):
        report = compute_stability()
        event = make_stability_event(report)
        required = {
            "type", "report_id", "spectral_radius", "margin",
            "region", "verdict", "stable", "dominant_mode",
            "hotspot_count", "adjacency_violation_count", "timestamp",
        }
        assert required == set(event.keys())


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_default_topology(self):
        """Default governance topology should be stable and coherent."""
        report = compute_stability()
        assert report.stable
        assert report.margin > 0
        assert report.region in (KineticRegion.COHERENT, KineticRegion.STRAINED)
        assert report.verdict in (GateVerdict.PASS, GateVerdict.WARN)

    def test_custom_topology(self):
        """Custom topology with known properties."""
        layers = [
            GovernanceLayer("agent", rate=1.0, latency=0.5, self_feedback=0.1,
                            feedback_up=0.2),
            GovernanceLayer("verify", rate=0.5, latency=1.0, self_feedback=0.05,
                            feedback_down=0.15, feedback_up=0.1),
            GovernanceLayer("review", rate=0.01, latency=60.0, self_feedback=0.0,
                            feedback_down=0.1),
        ]
        report = compute_stability(layers)
        assert report.stable
        assert len(report.coupling.matrix) == 3

    def test_gate_lifecycle(self, tmp_path):
        """Full gate lifecycle: check → save → query."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        gate = StabilityGate(governor_dir=gov_dir)

        # Initial check
        report = gate.check()
        assert report.stable

        # Check with different profile
        report2 = gate.check(profile="production")
        assert report2.stable

        # Status reflects latest
        status = gate.status()
        assert status["stable"]

        # Reports saved
        stability_dir = gov_dir / "stability"
        assert len(list(stability_dir.glob("*.json"))) >= 1

    def test_monotonic_instability(self):
        """Increasing feedback monotonically increases ρ(M)."""
        rho_values = []
        for fb in [0.0, 0.2, 0.5, 0.8, 1.0]:
            layers = [
                GovernanceLayer("a", rate=1.0, latency=0.5, self_feedback=fb),
            ]
            report = compute_stability(layers)
            rho_values.append(report.spectral_radius)

        # ρ should be monotonically non-decreasing
        for i in range(len(rho_values) - 1):
            assert rho_values[i + 1] >= rho_values[i] - 0.001  # Allow floating point tolerance
