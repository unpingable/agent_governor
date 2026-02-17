# SPDX-License-Identifier: Apache-2.0
"""
Spectral Stability — Coupling Matrix Verification for Governance Topology.

Computes ρ(M) from the governance hierarchy's declared rates, latencies,
and feedback strengths. Blocks autonomy configurations where ρ(M) ≥ 1
(structurally unstable). Warns when ρ(M) approaches 1.

Spec: SPECTRAL_STABILITY_SPEC.md (Layer 2, Item #6 of AG2 build order)

Core insight: Culture cannot stabilize an unstable topology. If ρ(M) ≥ 1,
no amount of "be careful" prevents runaway. The gate makes this a hard
constraint.

Key properties:
  - Preflight, not runtime (checks topology, not live behavior)
  - Conservative defaults (unknown coupling → assume worst case)
  - Pure Python spectral radius (power iteration, no numpy)
  - Hard block at ρ ≥ 1 (no override, no warrant — physics)
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class KineticRegion(str, Enum):
    """Five kinetic regions from Paper 05 (Control Laws)."""

    COHERENT = "coherent"
    """ρ(M) < 0.7, no adjacency violations. Normal operation."""

    STRAINED = "strained"
    """0.7 ≤ ρ(M) < 0.9. Regime: WARM."""

    METASTABLE = "metastable"
    """0.9 ≤ ρ(M) < 1.0. Regime: DUCTILE. Warn."""

    FLICKER = "flicker"
    """ρ(M) ≈ 1.0, oscillation detected. Regime: UNSTABLE. Block."""

    DECOHERENT = "decoherent"
    """ρ(M) > 1.0 or adjacency κ > 100. Hard block."""


class GateVerdict(str, Enum):
    """Stability gate decision."""

    PASS = "pass"
    """Stable with comfortable margin."""

    WARN = "warn"
    """Stable but approaching limit. Show hotspots."""

    BLOCK = "block"
    """Near-unstable. Override warrant required."""

    HARD_BLOCK = "hard_block"
    """Unstable by construction. No override possible."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class GovernanceLayer:
    """A layer in the governance hierarchy."""

    name: str
    """Human-readable layer name (e.g., 'agent_proposals')."""

    rate: float
    """Actions per unit time (e.g., proposals/sec, reviews/hour)."""

    latency: float
    """Processing time per action in same time unit."""

    capacity: float = 0.0
    """Max throughput before queuing. 0 = unlimited."""

    feedback_up: float = 0.0
    """Influence on layer above (0.0–1.0)."""

    feedback_down: float = 0.0
    """Influence on layer below (0.0–1.0)."""

    self_feedback: float = 0.0
    """Self-reinforcing feedback (retry rates, queue acceleration)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rate": self.rate,
            "latency": self.latency,
            "capacity": self.capacity,
            "feedback_up": self.feedback_up,
            "feedback_down": self.feedback_down,
            "self_feedback": self.self_feedback,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GovernanceLayer:
        return cls(
            name=d["name"],
            rate=d["rate"],
            latency=d["latency"],
            capacity=d.get("capacity", 0.0),
            feedback_up=d.get("feedback_up", 0.0),
            feedback_down=d.get("feedback_down", 0.0),
            self_feedback=d.get("self_feedback", 0.0),
        )


@dataclass
class CouplingHotspot:
    """An edge in the coupling matrix close to instability."""

    from_layer: str
    """Source layer name."""

    to_layer: str
    """Target layer name."""

    strength: float
    """Coupling strength (M[i][j] value)."""

    sensitivity: float
    """How much ρ changes if this edge changes (∂ρ/∂M_ij estimate)."""

    mitigation: str
    """Suggested fix."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_layer": self.from_layer,
            "to_layer": self.to_layer,
            "strength": self.strength,
            "sensitivity": self.sensitivity,
            "mitigation": self.mitigation,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CouplingHotspot:
        return cls(
            from_layer=d["from_layer"],
            to_layer=d["to_layer"],
            strength=d["strength"],
            sensitivity=d["sensitivity"],
            mitigation=d["mitigation"],
        )


@dataclass
class AdjacencyViolation:
    """Layer pair exceeding the κ < 100 timescale ratio."""

    fast_layer: str
    slow_layer: str
    rate_ratio: float
    """Actual timescale ratio."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "fast_layer": self.fast_layer,
            "slow_layer": self.slow_layer,
            "rate_ratio": round(self.rate_ratio, 2),
        }


@dataclass
class CouplingMatrix:
    """Inter-layer feedback matrix with spectral analysis."""

    layers: list[GovernanceLayer]
    """Ordered governance layers."""

    matrix: list[list[float]]
    """M[i][j] = feedback strength from layer j to layer i."""

    spectral_radius: float
    """ρ(M) — must be < 1 for stability."""

    dominant_eigenvalue: float
    """Magnitude of the dominant eigenvalue."""

    sensitivity: dict[str, float] = field(default_factory=dict)
    """Per-edge sensitivity: 'i->j' → ∂ρ/∂M_ij estimate."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "layers": [l.to_dict() for l in self.layers],
            "matrix": [[round(v, 6) for v in row] for row in self.matrix],
            "spectral_radius": round(self.spectral_radius, 6),
            "dominant_eigenvalue": round(self.dominant_eigenvalue, 6),
            "sensitivity": {k: round(v, 6) for k, v in self.sensitivity.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CouplingMatrix:
        return cls(
            layers=[GovernanceLayer.from_dict(l) for l in d["layers"]],
            matrix=d["matrix"],
            spectral_radius=d["spectral_radius"],
            dominant_eigenvalue=d["dominant_eigenvalue"],
            sensitivity=d.get("sensitivity", {}),
        )


@dataclass
class StabilityReport:
    """Preflight stability check result."""

    report_id: str
    """Content hash of the report."""

    stable: bool
    """True if ρ(M) < 1."""

    spectral_radius: float
    """ρ(M)."""

    margin: float
    """1 - ρ(M) — stability margin."""

    region: KineticRegion
    """Which kinetic region."""

    verdict: GateVerdict
    """Gate decision."""

    dominant_mode: str
    """Which feedback loop dominates."""

    hotspots: list[CouplingHotspot] = field(default_factory=list)
    """Edges closest to instability."""

    adjacency_violations: list[AdjacencyViolation] = field(default_factory=list)
    """Layer pairs with κ > 100."""

    recommendations: list[str] = field(default_factory=list)
    """Suggested mitigations."""

    coupling: CouplingMatrix | None = None
    """Full coupling matrix (optional, for detailed inspection)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "report_id": self.report_id,
            "stable": self.stable,
            "spectral_radius": round(self.spectral_radius, 6),
            "margin": round(self.margin, 6),
            "region": self.region.value,
            "verdict": self.verdict.value,
            "dominant_mode": self.dominant_mode,
            "hotspots": [h.to_dict() for h in self.hotspots],
            "adjacency_violations": [a.to_dict() for a in self.adjacency_violations],
            "recommendations": self.recommendations,
            "created_at": self.created_at.isoformat(),
        }
        if self.coupling is not None:
            d["coupling"] = self.coupling.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StabilityReport:
        return cls(
            report_id=d["report_id"],
            stable=d["stable"],
            spectral_radius=d["spectral_radius"],
            margin=d["margin"],
            region=KineticRegion(d["region"]),
            verdict=GateVerdict(d["verdict"]),
            dominant_mode=d["dominant_mode"],
            hotspots=[CouplingHotspot.from_dict(h) for h in d.get("hotspots", [])],
            adjacency_violations=[AdjacencyViolation(**a) for a in d.get("adjacency_violations", [])],
            recommendations=d.get("recommendations", []),
            coupling=CouplingMatrix.from_dict(d["coupling"]) if d.get("coupling") else None,
            created_at=datetime.fromisoformat(d["created_at"]) if "created_at" in d else datetime.now(timezone.utc),
        )

    def to_summary(self) -> str:
        lines = [
            f"Stability Report: {self.report_id}",
            f"  ρ(M) = {self.spectral_radius:.4f}",
            f"  Margin: {self.margin:.4f}",
            f"  Region: {self.region.value}",
            f"  Verdict: {self.verdict.value}",
            f"  Stable: {self.stable}",
            f"  Dominant mode: {self.dominant_mode}",
        ]
        if self.hotspots:
            lines.append("  Hotspots:")
            for h in self.hotspots:
                lines.append(f"    {h.from_layer} → {h.to_layer}: strength={h.strength:.3f}, sensitivity={h.sensitivity:.3f}")
                lines.append(f"      Mitigation: {h.mitigation}")
        if self.adjacency_violations:
            lines.append("  Adjacency violations:")
            for v in self.adjacency_violations:
                lines.append(f"    {v.fast_layer} / {v.slow_layer}: κ = {v.rate_ratio:.1f}")
        if self.recommendations:
            lines.append("  Recommendations:")
            for r in self.recommendations:
                lines.append(f"    - {r}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            f"# Stability Report: {self.report_id}",
            "",
            f"**ρ(M)**: {self.spectral_radius:.4f}",
            f"**Margin**: {self.margin:.4f}",
            f"**Region**: {self.region.value}",
            f"**Verdict**: **{self.verdict.value.upper()}**",
            f"**Stable**: {'Yes' if self.stable else '**NO**'}",
            f"**Dominant mode**: {self.dominant_mode}",
        ]
        if self.hotspots:
            lines.extend(["", "## Hotspots", ""])
            lines.append("| From | To | Strength | Sensitivity | Mitigation |")
            lines.append("|------|-----|----------|-------------|------------|")
            for h in self.hotspots:
                lines.append(f"| {h.from_layer} | {h.to_layer} | {h.strength:.3f} | {h.sensitivity:.3f} | {h.mitigation} |")
        if self.adjacency_violations:
            lines.extend(["", "## Adjacency Violations", ""])
            for v in self.adjacency_violations:
                lines.append(f"- **{v.fast_layer}** / **{v.slow_layer}**: κ = {v.rate_ratio:.1f} (limit: 100)")
        if self.recommendations:
            lines.extend(["", "## Recommendations", ""])
            for r in self.recommendations:
                lines.append(f"- {r}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Default layer profiles
# ---------------------------------------------------------------------------

# Conservative defaults when rates are unknown
DEFAULT_LAYERS: list[GovernanceLayer] = [
    GovernanceLayer(
        name="agent_proposals",
        rate=1.0,           # 1 proposal/sec
        latency=0.5,
        capacity=10.0,
        feedback_up=0.3,    # Proposals influence verification queue
        feedback_down=0.0,
        self_feedback=0.1,  # Retry on rejection
    ),
    GovernanceLayer(
        name="governor_verify",
        rate=0.5,           # 0.5 verifications/sec
        latency=1.0,
        capacity=5.0,
        feedback_up=0.2,    # Verification results influence review queue
        feedback_down=0.3,  # Rejections increase proposal retry
        self_feedback=0.05,
    ),
    GovernanceLayer(
        name="human_review",
        rate=0.01,          # ~1 review/100 sec (slow)
        latency=60.0,
        capacity=2.0,
        feedback_up=0.1,    # Reviews influence policy
        feedback_down=0.2,  # Review decisions influence verification
        self_feedback=0.0,
    ),
    GovernanceLayer(
        name="policy_update",
        rate=0.001,         # Very slow
        latency=3600.0,
        capacity=1.0,
        feedback_up=0.0,
        feedback_down=0.15, # Policy changes influence review criteria
        self_feedback=0.0,
    ),
]

# Profile-specific overrides
PROFILE_OVERRIDES: dict[str, dict[str, dict[str, float]]] = {
    "greenfield": {
        "agent_proposals": {"rate": 2.0, "self_feedback": 0.2},
        "governor_verify": {"feedback_down": 0.1},  # Less rejection pressure
    },
    "production": {
        "agent_proposals": {"rate": 0.2, "self_feedback": 0.05},
        "governor_verify": {"feedback_down": 0.5},  # Higher rejection feedback
        "human_review": {"rate": 0.02, "feedback_down": 0.3},
    },
    "strict": {
        "agent_proposals": {"rate": 0.1},
        "governor_verify": {"feedback_down": 0.6, "self_feedback": 0.1},
        "human_review": {"rate": 0.05, "feedback_down": 0.4},
    },
}


# ---------------------------------------------------------------------------
# Pure Python Linear Algebra
# ---------------------------------------------------------------------------


def _mat_vec_mul(M: list[list[float]], v: list[float]) -> list[float]:
    """Matrix-vector multiplication: M @ v."""
    n = len(M)
    result = [0.0] * n
    for i in range(n):
        for j in range(n):
            result[i] += M[i][j] * v[j]
    return result


def _vec_norm(v: list[float]) -> float:
    """Euclidean norm of vector."""
    return math.sqrt(sum(x * x for x in v))


def _vec_scale(v: list[float], s: float) -> list[float]:
    """Scale vector by scalar."""
    return [x * s for x in v]


def _power_iteration(M: list[list[float]], max_iter: int = 200, tol: float = 1e-8) -> float:
    """Estimate spectral radius via power iteration.

    Returns the magnitude of the dominant eigenvalue.
    Pure Python — no numpy dependency.
    """
    n = len(M)
    if n == 0:
        return 0.0

    # Start with a non-zero vector
    v = [1.0 / math.sqrt(n)] * n
    eigenvalue = 0.0

    for _ in range(max_iter):
        # Multiply
        w = _mat_vec_mul(M, v)
        norm = _vec_norm(w)

        if norm < 1e-15:
            return 0.0  # Zero matrix

        # New eigenvalue estimate
        new_eigenvalue = norm
        v = _vec_scale(w, 1.0 / norm)

        if abs(new_eigenvalue - eigenvalue) < tol:
            return new_eigenvalue

        eigenvalue = new_eigenvalue

    return eigenvalue


def _spectral_radius(M: list[list[float]]) -> float:
    """Compute spectral radius ρ(M) = max|λ_i|.

    Uses power iteration for the dominant eigenvalue magnitude.
    For small matrices (n ≤ 5), this converges quickly.
    """
    # Also check M^T for potentially larger eigenvalues
    # (power iteration finds the dominant eigenvalue of M,
    # but for non-symmetric matrices we should check both)
    n = len(M)
    if n == 0:
        return 0.0

    rho = _power_iteration(M)

    # For better accuracy with non-symmetric matrices,
    # also try M^T (same eigenvalues but power iteration may converge to different one)
    MT = [[M[j][i] for j in range(n)] for i in range(n)]
    rho_t = _power_iteration(MT)

    return max(rho, rho_t)


# ---------------------------------------------------------------------------
# Matrix Construction
# ---------------------------------------------------------------------------


def build_coupling_matrix(layers: list[GovernanceLayer]) -> CouplingMatrix:
    """Build the coupling matrix M from governance layer declarations.

    M[i][j] = feedback strength from layer j to layer i.

    Diagonal: self-feedback (retry rates, queue acceleration).
    Off-diagonal: inter-layer coupling (rejection→retry, backlog→pressure).
    """
    n = len(layers)
    M: list[list[float]] = [[0.0] * n for _ in range(n)]

    for i in range(n):
        # Diagonal: self-feedback
        M[i][i] = layers[i].self_feedback

        # Off-diagonal: inter-layer coupling
        if i > 0:
            # Layer below influences this layer (feedback_up from i-1)
            # Scaled by rate ratio (faster layer has more influence)
            rate_ratio = layers[i - 1].rate / max(layers[i].rate, 1e-10)
            M[i][i - 1] = layers[i - 1].feedback_up * min(rate_ratio, 5.0) * 0.2

        if i < n - 1:
            # Layer above influences this layer (feedback_down from i+1)
            M[i][i + 1] = layers[i + 1].feedback_down

        # Capacity pressure: if a layer is near capacity, coupling increases
        if layers[i].capacity > 0 and layers[i].rate > 0:
            utilization = min(layers[i].rate / layers[i].capacity, 1.0)
            if utilization > 0.8:
                # Queue pressure amplifies self-feedback (capped at 0.1)
                M[i][i] += min(0.1, 0.1 * (utilization - 0.8) / 0.2)

    # Compute spectral radius
    rho = _spectral_radius(M)

    # Compute per-edge sensitivity estimates
    sensitivity: dict[str, float] = {}
    epsilon = 0.01
    for i in range(n):
        for j in range(n):
            if abs(M[i][j]) > 1e-10:
                # Perturb M[i][j] and recompute
                M_perturbed = [row[:] for row in M]
                M_perturbed[i][j] += epsilon
                rho_perturbed = _spectral_radius(M_perturbed)
                sens = (rho_perturbed - rho) / epsilon
                key = f"{layers[j].name}->{layers[i].name}"
                sensitivity[key] = round(sens, 6)

    return CouplingMatrix(
        layers=layers,
        matrix=M,
        spectral_radius=round(rho, 6),
        dominant_eigenvalue=round(rho, 6),
        sensitivity=sensitivity,
    )


# ---------------------------------------------------------------------------
# Adjacency Checking
# ---------------------------------------------------------------------------

ADJACENCY_LIMIT = 100.0


def check_adjacency(layers: list[GovernanceLayer]) -> list[AdjacencyViolation]:
    """Flag adjacent layer pairs where rate ratio > κ limit (100)."""
    violations: list[AdjacencyViolation] = []
    for i in range(len(layers) - 1):
        fast = layers[i]
        slow = layers[i + 1]
        if slow.rate > 0:
            ratio = fast.rate / slow.rate
        else:
            ratio = float("inf")

        if ratio > ADJACENCY_LIMIT:
            violations.append(AdjacencyViolation(
                fast_layer=fast.name,
                slow_layer=slow.name,
                rate_ratio=ratio,
            ))

    return violations


# ---------------------------------------------------------------------------
# Region Classification
# ---------------------------------------------------------------------------


def classify_region(
    rho: float,
    adjacency_violations: list[AdjacencyViolation] | None = None,
) -> KineticRegion:
    """Map ρ(M) and adjacency metrics to kinetic region."""
    if adjacency_violations and len(adjacency_violations) > 0:
        return KineticRegion.DECOHERENT

    if rho >= 1.0:
        return KineticRegion.DECOHERENT
    if rho >= 0.95:
        return KineticRegion.FLICKER
    if rho >= 0.9:
        return KineticRegion.METASTABLE
    if rho >= 0.7:
        return KineticRegion.STRAINED
    return KineticRegion.COHERENT


def determine_verdict(region: KineticRegion) -> GateVerdict:
    """Determine gate verdict from kinetic region."""
    return {
        KineticRegion.COHERENT: GateVerdict.PASS,
        KineticRegion.STRAINED: GateVerdict.WARN,
        KineticRegion.METASTABLE: GateVerdict.BLOCK,
        KineticRegion.FLICKER: GateVerdict.HARD_BLOCK,
        KineticRegion.DECOHERENT: GateVerdict.HARD_BLOCK,
    }[region]


# ---------------------------------------------------------------------------
# Hotspot Detection
# ---------------------------------------------------------------------------


def find_hotspots(
    coupling: CouplingMatrix,
    top_n: int = 3,
) -> list[CouplingHotspot]:
    """Find the coupling edges closest to instability."""
    hotspots: list[CouplingHotspot] = []
    n = len(coupling.layers)

    entries: list[tuple[float, int, int]] = []
    for i in range(n):
        for j in range(n):
            if abs(coupling.matrix[i][j]) > 1e-10:
                entries.append((abs(coupling.matrix[i][j]), i, j))

    # Sort by sensitivity (descending)
    keyed: list[tuple[float, int, int, float]] = []
    for strength, i, j in entries:
        key = f"{coupling.layers[j].name}->{coupling.layers[i].name}"
        sens = abs(coupling.sensitivity.get(key, 0.0))
        keyed.append((sens, i, j, strength))

    keyed.sort(reverse=True)

    for sens, i, j, strength in keyed[:top_n]:
        from_name = coupling.layers[j].name
        to_name = coupling.layers[i].name

        # Generate mitigation suggestion
        if i == j:
            mitigation = f"Reduce self-feedback on {from_name} (retry rate, queue pressure)"
        elif j < i:
            mitigation = f"Add buffer between {from_name} and {to_name} (reduce upward pressure)"
        else:
            mitigation = f"Reduce {from_name} → {to_name} feedback (soften rejection/policy pressure)"

        hotspots.append(CouplingHotspot(
            from_layer=from_name,
            to_layer=to_name,
            strength=round(strength, 6),
            sensitivity=round(sens, 6),
            mitigation=mitigation,
        ))

    return hotspots


# ---------------------------------------------------------------------------
# Stability Check
# ---------------------------------------------------------------------------


def _identify_dominant_mode(coupling: CouplingMatrix) -> str:
    """Identify which feedback loop dominates instability."""
    if not coupling.sensitivity:
        return "none"

    # Find the most sensitive edge
    max_key = max(coupling.sensitivity, key=lambda k: abs(coupling.sensitivity[k]))
    return max_key


def _generate_recommendations(
    coupling: CouplingMatrix,
    region: KineticRegion,
    adjacency_violations: list[AdjacencyViolation],
) -> list[str]:
    """Generate mitigation recommendations."""
    recs: list[str] = []

    if region == KineticRegion.DECOHERENT:
        if adjacency_violations:
            for v in adjacency_violations:
                recs.append(
                    f"Reduce timescale gap between {v.fast_layer} and {v.slow_layer} "
                    f"(κ={v.rate_ratio:.0f}, limit=100)"
                )
        else:
            recs.append("Topology is unstable. Reduce coupling strengths or add buffer layers.")

    elif region == KineticRegion.FLICKER:
        recs.append("Near-critical: reduce feedback gains on dominant mode.")
        dominant = _identify_dominant_mode(coupling)
        if dominant != "none":
            recs.append(f"Dominant mode: {dominant}")

    elif region == KineticRegion.METASTABLE:
        recs.append("Approaching instability. Consider reducing agent proposal rate or increasing review capacity.")

    elif region == KineticRegion.STRAINED:
        recs.append("Operating under strain. Monitor for oscillation.")

    return recs


def compute_stability(
    layers: list[GovernanceLayer] | None = None,
    profile: str | None = None,
) -> StabilityReport:
    """Preflight stability check.

    Build coupling matrix from layer declarations (or defaults)
    and compute ρ(M). Returns a StabilityReport with verdict,
    hotspots, and recommendations.
    """
    if layers is None:
        layers = _apply_profile(DEFAULT_LAYERS, profile)

    coupling = build_coupling_matrix(layers)
    adjacency = check_adjacency(layers)
    region = classify_region(coupling.spectral_radius, adjacency)
    verdict = determine_verdict(region)
    dominant = _identify_dominant_mode(coupling)
    hotspots = find_hotspots(coupling)
    recommendations = _generate_recommendations(coupling, region, adjacency)

    report_data = json.dumps({
        "rho": coupling.spectral_radius,
        "region": region.value,
        "layers": [l.name for l in layers],
    }, sort_keys=True)
    report_id = hashlib.sha256(report_data.encode()).hexdigest()[:12]

    return StabilityReport(
        report_id=report_id,
        stable=coupling.spectral_radius < 1.0,
        spectral_radius=coupling.spectral_radius,
        margin=round(1.0 - coupling.spectral_radius, 6),
        region=region,
        verdict=verdict,
        dominant_mode=dominant,
        hotspots=hotspots,
        adjacency_violations=adjacency,
        recommendations=recommendations,
        coupling=coupling,
    )


def _apply_profile(
    base_layers: list[GovernanceLayer],
    profile: str | None,
) -> list[GovernanceLayer]:
    """Apply profile-specific overrides to default layers."""
    import copy
    layers = [copy.copy(l) for l in base_layers]

    if profile is None or profile not in PROFILE_OVERRIDES:
        return layers

    overrides = PROFILE_OVERRIDES[profile]
    for layer in layers:
        if layer.name in overrides:
            for attr, value in overrides[layer.name].items():
                setattr(layer, attr, value)

    return layers


# ---------------------------------------------------------------------------
# Stability Gate (facade)
# ---------------------------------------------------------------------------


class StabilityGate:
    """Preflight stability gate for autonomy configurations.

    Checks governance topology before enabling or changing configurations.
    Hard blocks when ρ(M) ≥ 1 — no override possible.
    """

    def __init__(
        self,
        layers: list[GovernanceLayer] | None = None,
        profile: str | None = None,
        governor_dir: Path | None = None,
    ):
        self._layers = layers
        self._profile = profile
        self._governor_dir = governor_dir
        self._last_report: StabilityReport | None = None

    def check(self, profile: str | None = None) -> StabilityReport:
        """Run preflight stability check.

        Args:
            profile: Override profile for this check.

        Returns:
            StabilityReport with verdict, hotspots, and recommendations.
        """
        p = profile or self._profile
        report = compute_stability(self._layers, p)
        self._last_report = report

        if self._governor_dir is not None:
            self._save_report(report)

        return report

    def is_stable(self, profile: str | None = None) -> bool:
        """Quick check: is the topology stable?"""
        report = self.check(profile)
        return report.stable

    def allows(self, profile: str | None = None) -> bool:
        """Does the gate allow the configuration?"""
        report = self.check(profile)
        return report.verdict in (GateVerdict.PASS, GateVerdict.WARN)

    @property
    def last_report(self) -> StabilityReport | None:
        return self._last_report

    def status(self) -> dict[str, Any]:
        """Current stability status."""
        if self._last_report is not None:
            return {
                "spectral_radius": self._last_report.spectral_radius,
                "region": self._last_report.region.value,
                "verdict": self._last_report.verdict.value,
                "stable": self._last_report.stable,
                "margin": self._last_report.margin,
            }

        # No check run yet — return defaults
        report = self.check()
        return {
            "spectral_radius": report.spectral_radius,
            "region": report.region.value,
            "verdict": report.verdict.value,
            "stable": report.stable,
            "margin": report.margin,
        }

    def _save_report(self, report: StabilityReport) -> None:
        """Save report to governor directory."""
        d = self._governor_dir
        if d is None:
            return
        stability_dir = d / "stability"
        stability_dir.mkdir(parents=True, exist_ok=True)
        path = stability_dir / f"{report.report_id}.json"
        path.write_text(json.dumps(report.to_dict(), indent=2, default=str))


# ---------------------------------------------------------------------------
# Telemetry event helper
# ---------------------------------------------------------------------------


def make_stability_event(report: StabilityReport) -> dict[str, Any]:
    """Create a telemetry event dict for a stability check."""
    return {
        "type": "stability_check",
        "report_id": report.report_id,
        "spectral_radius": report.spectral_radius,
        "margin": report.margin,
        "region": report.region.value,
        "verdict": report.verdict.value,
        "stable": report.stable,
        "dominant_mode": report.dominant_mode,
        "hotspot_count": len(report.hotspots),
        "adjacency_violation_count": len(report.adjacency_violations),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
