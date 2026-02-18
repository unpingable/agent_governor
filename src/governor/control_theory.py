# SPDX-License-Identifier: Apache-2.0
"""
Control Theory Formalization — R_t = (P_t * D_t) / E_t

The Agent Risk Index: a single dimensionless ratio analogous to the Reynolds
number in fluid dynamics that determines whether agent operation is "laminar"
(safe) or "turbulent" (dangerous).

This module is self-contained — no imports from other governor modules.
Future specs will wire this into regime detection, epistemic ledger, etc.

Spec: CONTROL_THEORY_SPEC.md (Layer 0, Item #0 of AG2 build order)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Regime(str, Enum):
    """R_t-based regime classification.

    Intentionally separate from OperationalRegime (signal-based).
    A future mapping function will bridge them.
    """

    SAFE = "safe"
    """R̄_t < 0.1 — Full autonomy, minimal oversight."""

    ELASTIC = "elastic"
    """0.1 ≤ R̄_t < 0.4 — Normal operation, standard checks."""

    DANGEROUS = "dangerous"
    """0.4 ≤ R̄_t < 0.8 — Heightened scrutiny, human review for high-P actions."""

    RUNAWAY = "runaway"
    """R̄_t ≥ 0.8 — Halt, require explicit human intervention."""

    @property
    def severity(self) -> int:
        return {
            Regime.SAFE: 0,
            Regime.ELASTIC: 1,
            Regime.DANGEROUS: 2,
            Regime.RUNAWAY: 3,
        }[self]

    @property
    def recommended_action(self) -> str:
        return {
            Regime.SAFE: "CONTINUE",
            Regime.ELASTIC: "MONITOR",
            Regime.DANGEROUS: "TIGHTEN",
            Regime.RUNAWAY: "HALT",
        }[self]


class GovernorDecision(str, Enum):
    """Outcome of a governor check."""

    ALLOW = "allow"
    DENY = "deny"
    DEMOTE = "demote"
    HALT = "halt"


class RiskAggregation(str, Enum):
    """Windowed risk aggregation strategy."""

    EMA = "ema"
    SMA = "sma"
    WORST_CASE = "worst_case"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ToolPowerMetrics:
    """P = π * b * ι (privilege × blast × irreversibility)."""

    privilege: float  # π_k: authority scope (0-1)
    blast: float  # b_k: blast radius (0-1)
    irreversibility: float  # ι_k: undo cost (0-1)

    def __post_init__(self) -> None:
        for name, val in [
            ("privilege", self.privilege),
            ("blast", self.blast),
            ("irreversibility", self.irreversibility),
        ]:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {val}")

    @property
    def power(self) -> float:
        return self.privilege * self.blast * self.irreversibility

    def to_dict(self) -> dict[str, Any]:
        return {
            "privilege": self.privilege,
            "blast": self.blast,
            "irreversibility": self.irreversibility,
            "power": self.power,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolPowerMetrics:
        return cls(
            privilege=data["privilege"],
            blast=data["blast"],
            irreversibility=data["irreversibility"],
        )


@dataclass
class FeedbackDelayComponents:
    """D = max(D_tool, D_telemetry, D_human)."""

    d_tool: float  # Time for tool to report completion
    d_telemetry: float  # Time for monitoring to confirm effect
    d_human: float  # Time for human review if required

    def __post_init__(self) -> None:
        for name, val in [
            ("d_tool", self.d_tool),
            ("d_telemetry", self.d_telemetry),
            ("d_human", self.d_human),
        ]:
            if val < 0.0:
                raise ValueError(f"{name} must be >= 0, got {val}")

    @property
    def delay(self) -> float:
        return max(self.d_tool, self.d_telemetry, self.d_human)

    def to_dict(self) -> dict[str, Any]:
        return {
            "d_tool": self.d_tool,
            "d_telemetry": self.d_telemetry,
            "d_human": self.d_human,
            "delay": self.delay,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedbackDelayComponents:
        return cls(
            d_tool=data["d_tool"],
            d_telemetry=data["d_telemetry"],
            d_human=data["d_human"],
        )


@dataclass
class EvidenceComponents:
    """E = w_r*R + w_p*PV + w_v*V + w_i*I (weighted sum, clamped to [ε, 1])."""

    receipts: float  # R: proof captured (SHA-256, exit codes, timestamps)
    provenance: float  # PV: custody chain depth
    verifiability: float  # V: replayability / determinism
    independence: float  # I: cross-model agreement, external checks
    w_receipts: float = 0.4
    w_provenance: float = 0.2
    w_verifiability: float = 0.2
    w_independence: float = 0.2

    def __post_init__(self) -> None:
        for name, val in [
            ("receipts", self.receipts),
            ("provenance", self.provenance),
            ("verifiability", self.verifiability),
            ("independence", self.independence),
        ]:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {val}")
        total = self.w_receipts + self.w_provenance + self.w_verifiability + self.w_independence
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    @property
    def evidence(self) -> float:
        raw = (
            self.w_receipts * self.receipts
            + self.w_provenance * self.provenance
            + self.w_verifiability * self.verifiability
            + self.w_independence * self.independence
        )
        return max(raw, EPSILON)

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipts": self.receipts,
            "provenance": self.provenance,
            "verifiability": self.verifiability,
            "independence": self.independence,
            "w_receipts": self.w_receipts,
            "w_provenance": self.w_provenance,
            "w_verifiability": self.w_verifiability,
            "w_independence": self.w_independence,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceComponents:
        return cls(
            receipts=data["receipts"],
            provenance=data["provenance"],
            verifiability=data["verifiability"],
            independence=data["independence"],
            w_receipts=data.get("w_receipts", 0.4),
            w_provenance=data.get("w_provenance", 0.2),
            w_verifiability=data.get("w_verifiability", 0.2),
            w_independence=data.get("w_independence", 0.2),
        )


@dataclass
class RiskCalculation:
    """Single R_t result."""

    power: float
    delay: float
    evidence: float
    risk: float  # R_t = P*D/E
    regime: Regime
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "power": self.power,
            "delay": self.delay,
            "evidence": self.evidence,
            "risk": self.risk,
            "regime": self.regime.value,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskCalculation:
        return cls(
            power=data["power"],
            delay=data["delay"],
            evidence=data["evidence"],
            risk=data["risk"],
            regime=Regime(data["regime"]),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class RiskWindow:
    """Rolling history for R̄_t (EMA/SMA/worst-case)."""

    values: list[float] = field(default_factory=list)
    max_size: int = 100
    ema_alpha: float = 0.3
    _ema: float = 0.0

    def add(self, r_t: float) -> None:
        self.values.append(r_t)
        if len(self.values) > self.max_size:
            self.values = self.values[-self.max_size:]
        self._ema = update_ema(r_t, self._ema, self.ema_alpha)

    @property
    def ema(self) -> float:
        return self._ema

    @property
    def sma(self) -> float:
        return compute_sma(self.values) if self.values else 0.0

    @property
    def worst_case(self) -> float:
        return compute_worst_case(self.values) if self.values else 0.0

    def get_r_bar(self, mode: RiskAggregation = RiskAggregation.EMA) -> float:
        if mode == RiskAggregation.EMA:
            return self.ema
        elif mode == RiskAggregation.SMA:
            return self.sma
        else:
            return self.worst_case

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": list(self.values),
            "max_size": self.max_size,
            "ema_alpha": self.ema_alpha,
            "ema": self._ema,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskWindow:
        w = cls(
            values=data.get("values", []),
            max_size=data.get("max_size", 100),
            ema_alpha=data.get("ema_alpha", 0.3),
        )
        w._ema = data.get("ema", 0.0)
        return w


@dataclass
class PrivilegeTier:
    """Discrete privilege tier."""

    level: int  # 0-5
    p_threshold: float  # Maximum P for this tier
    allowed_tools: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "p_threshold": self.p_threshold,
            "allowed_tools": self.allowed_tools,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrivilegeTier:
        return cls(
            level=data["level"],
            p_threshold=data["p_threshold"],
            allowed_tools=data["allowed_tools"],
        )


@dataclass
class CapabilityEnvelope:
    """Current capability state derived from (E, D, τ)."""

    evidence: float
    delay: float
    tau: float
    p_max: float
    tier: PrivilegeTier

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence,
            "delay": self.delay,
            "tau": self.tau,
            "p_max": self.p_max,
            "tier": self.tier.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityEnvelope:
        return cls(
            evidence=data["evidence"],
            delay=data["delay"],
            tau=data["tau"],
            p_max=data["p_max"],
            tier=PrivilegeTier.from_dict(data["tier"]),
        )


@dataclass
class ToolGateRequirements:
    """Per-tool evidence minimum and risk cap."""

    tool_class: str
    e_min: float
    tau: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_class": self.tool_class,
            "e_min": self.e_min,
            "tau": self.tau,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolGateRequirements:
        return cls(
            tool_class=data["tool_class"],
            e_min=data["e_min"],
            tau=data["tau"],
        )


@dataclass
class OpenLoopMetrics:
    """Γ = A_t / V_t — actuation vs verification throughput."""

    actuation_rate: float  # A_t: high-impact actions per unit time
    verification_rate: float  # V_t: verified actions per unit time
    backlog: int = 0  # Unverified actions count

    def __post_init__(self) -> None:
        if self.actuation_rate < 0:
            raise ValueError(f"actuation_rate must be >= 0, got {self.actuation_rate}")
        if self.verification_rate < 0:
            raise ValueError(f"verification_rate must be >= 0, got {self.verification_rate}")

    @property
    def gamma(self) -> float:
        if self.verification_rate == 0:
            return float("inf") if self.actuation_rate > 0 else 0.0
        return self.actuation_rate / self.verification_rate

    @property
    def is_open_loop(self) -> bool:
        return self.gamma > 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "actuation_rate": self.actuation_rate,
            "verification_rate": self.verification_rate,
            "backlog": self.backlog,
            "gamma": self.gamma,
            "is_open_loop": self.is_open_loop,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpenLoopMetrics:
        return cls(
            actuation_rate=data["actuation_rate"],
            verification_rate=data["verification_rate"],
            backlog=data.get("backlog", 0),
        )


@dataclass
class EpisodeRiskMetrics:
    """Task-level risk: J_additive, J_discounted, J_worst."""

    j_additive: float
    j_discounted: float
    j_worst: float
    step_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "j_additive": self.j_additive,
            "j_discounted": self.j_discounted,
            "j_worst": self.j_worst,
            "step_count": self.step_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodeRiskMetrics:
        return cls(
            j_additive=data["j_additive"],
            j_discounted=data["j_discounted"],
            j_worst=data["j_worst"],
            step_count=data["step_count"],
        )


@dataclass
class ReceiptsCurrencyModel:
    """Receipts as currency: Cost = η*P*D, Credit = κ*E."""

    eta: float = 1.0  # Cost scaling
    kappa: float = 1.0  # Credit scaling

    @property
    def tau_equivalent(self) -> float:
        """τ = κ/η — the R_t bound this currency model implies."""
        if self.eta == 0:
            return float("inf")
        return self.kappa / self.eta

    def cost(self, power: float, delay: float) -> float:
        return self.eta * power * delay

    def credit(self, evidence: float) -> float:
        return self.kappa * evidence

    def can_afford(self, power: float, delay: float, evidence: float) -> bool:
        return self.credit(evidence) >= self.cost(power, delay)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eta": self.eta,
            "kappa": self.kappa,
            "tau_equivalent": self.tau_equivalent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReceiptsCurrencyModel:
        return cls(eta=data["eta"], kappa=data["kappa"])


@dataclass
class GovernorCheckResult:
    """Decision + risk + regime + reason + metadata from governor_check()."""

    decision: GovernorDecision
    risk: float
    regime: Regime
    reason: str
    tool_class: str = ""
    power_requested: float = 0.0
    power_allowed: float | None = None
    demoted_tier: PrivilegeTier | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "decision": self.decision.value,
            "risk": self.risk,
            "regime": self.regime.value,
            "reason": self.reason,
            "tool_class": self.tool_class,
            "power_requested": self.power_requested,
        }
        if self.power_allowed is not None:
            result["power_allowed"] = self.power_allowed
        if self.demoted_tier is not None:
            result["demoted_tier"] = self.demoted_tier.to_dict()
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernorCheckResult:
        tier = None
        if "demoted_tier" in data and data["demoted_tier"] is not None:
            tier = PrivilegeTier.from_dict(data["demoted_tier"])
        return cls(
            decision=GovernorDecision(data["decision"]),
            risk=data["risk"],
            regime=Regime(data["regime"]),
            reason=data["reason"],
            tool_class=data.get("tool_class", ""),
            power_requested=data.get("power_requested", 0.0),
            power_allowed=data.get("power_allowed"),
            demoted_tier=tier,
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Events (for future instrument integration)
# ---------------------------------------------------------------------------


@dataclass
class RiskIndexEvent:
    """Emitted on every R_t computation."""

    risk: float
    power: float
    delay: float
    evidence: float
    regime: Regime
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "risk_index",
            "risk": self.risk,
            "power": self.power,
            "delay": self.delay,
            "evidence": self.evidence,
            "regime": self.regime.value,
            "timestamp": self.timestamp,
        }


@dataclass
class CapabilityChangeEvent:
    """Emitted when capability envelope changes."""

    old_tier: int
    new_tier: int
    p_max: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "capability_change",
            "old_tier": self.old_tier,
            "new_tier": self.new_tier,
            "p_max": self.p_max,
            "timestamp": self.timestamp,
        }


@dataclass
class RegimeTransitionEvent:
    """Emitted when regime changes."""

    from_regime: Regime
    to_regime: Regime
    r_bar: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "regime_transition",
            "from_regime": self.from_regime.value,
            "to_regime": self.to_regime.value,
            "r_bar": self.r_bar,
            "timestamp": self.timestamp,
        }


@dataclass
class GovernorDecisionEvent:
    """Emitted on every governor check decision."""

    decision: GovernorDecision
    tool_class: str
    risk: float
    reason: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "governor_decision",
            "decision": self.decision.value,
            "tool_class": self.tool_class,
            "risk": self.risk,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class OpenLoopDetectedEvent:
    """Emitted when open-loop condition detected (Γ > 1)."""

    gamma: float
    actuation_rate: float
    verification_rate: float
    backlog: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "open_loop_detected",
            "gamma": self.gamma,
            "actuation_rate": self.actuation_rate,
            "verification_rate": self.verification_rate,
            "backlog": self.backlog,
            "timestamp": self.timestamp,
        }


@dataclass
class GlassCannonDetectedEvent:
    """Emitted when glass cannon sensitivity detected: R is below cap but
    a single bounded perturbation in D or E could breach it."""

    dr_dd: float
    dr_de: float
    risk: float
    r_worst: float
    margin: float
    margin_to_cap: float
    evidence: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "glass_cannon_detected",
            "dr_dd": self.dr_dd,
            "dr_de": self.dr_de,
            "risk": self.risk,
            "r_worst": self.r_worst,
            "margin": self.margin,
            "margin_to_cap": self.margin_to_cap,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Constants & Lookup Tables
# ---------------------------------------------------------------------------

EPSILON = 1e-6  # Numeric stability floor for E_t

# Default regime thresholds: (τ₁, τ₂, τ₃)
DEFAULT_REGIME_THRESHOLDS: tuple[float, float, float] = (0.1, 0.4, 0.8)

# Spec table (Section 0.1). Note: read_file has iota=0.1 (not 0.0) to yield P≈0.001.
DEFAULT_TOOL_POWER: dict[str, ToolPowerMetrics] = {
    "read_file": ToolPowerMetrics(privilege=0.1, blast=0.1, irreversibility=0.1),
    "write_file": ToolPowerMetrics(privilege=0.5, blast=0.3, irreversibility=0.5),
    "execute_shell": ToolPowerMetrics(privilege=0.8, blast=0.7, irreversibility=0.8),
    "delete_recursive": ToolPowerMetrics(privilege=0.9, blast=0.9, irreversibility=1.0),
    "deploy_production": ToolPowerMetrics(privilege=1.0, blast=1.0, irreversibility=0.9),
}

# Per-tool minimum evidence (Section 4.1)
DEFAULT_E_MIN: dict[str, float] = {
    "read_file": 0.1,
    "write_file": 0.3,
    "execute_shell": 0.5,
    "delete_recursive": 0.8,
    "deploy_production": 0.7,
}

# Per-tool risk caps (Section 4.2)
DEFAULT_TAU: dict[str, float] = {
    "read_file": 1.0,
    "write_file": 0.5,
    "execute_shell": 0.4,
    "delete_recursive": 0.3,
    "deploy_production": 0.2,
}

# Typical D_t per tool class (Section 0.2, normalized)
DEFAULT_DELAY: dict[str, float] = {
    "read_file": 0.1,
    "write_file": 0.2,
    "execute_shell": 0.5,
    "delete_recursive": 0.5,
    "deploy_production": 1.0,
}

# Privilege tiers (Section 3.2)
DEFAULT_PRIVILEGE_TIERS: list[PrivilegeTier] = [
    PrivilegeTier(level=0, p_threshold=0.01, allowed_tools=["read_file", "list_dir"]),
    PrivilegeTier(level=1, p_threshold=0.10, allowed_tools=["write_file", "run_tests"]),
    PrivilegeTier(level=2, p_threshold=0.30, allowed_tools=["execute_shell_sandboxed"]),
    PrivilegeTier(level=3, p_threshold=0.50, allowed_tools=["execute_shell"]),
    PrivilegeTier(level=4, p_threshold=0.80, allowed_tools=["delete_recursive", "deploy_staging"]),
    PrivilegeTier(level=5, p_threshold=1.00, allowed_tools=["deploy_production", "admin"]),
]

# Glass cannon sensitivity thresholds
GLASS_CANNON_DR_DD_THRESHOLD = 0.5
GLASS_CANNON_DR_DE_THRESHOLD = 0.5

# Event buffer cap
MAX_EVENTS = 1000


# ---------------------------------------------------------------------------
# Core Functions (14)
# ---------------------------------------------------------------------------


def compute_power(metrics: ToolPowerMetrics) -> float:
    """P = π * b * ι."""
    return metrics.power


def compute_delay(
    components: FeedbackDelayComponents,
    backlog: int = 0,
    backlog_weight: float = 0.1,
) -> float:
    """D = max(D_tool, D_telemetry, D_human) + λ * backlog."""
    base = components.delay
    return base + backlog_weight * backlog


def compute_evidence(components: EvidenceComponents, epsilon: float = EPSILON) -> float:
    """E = weighted sum of components, clamped to [ε, 1]."""
    return max(components.evidence, epsilon)


def compute_risk(power: float, delay: float, evidence: float) -> float:
    """R_t = (P * D) / E. Evidence is epsilon-clamped."""
    e = max(evidence, EPSILON)
    return (power * delay) / e


def classify_regime(
    r_bar: float,
    thresholds: tuple[float, float, float] = DEFAULT_REGIME_THRESHOLDS,
) -> Regime:
    """Classify R̄_t into a regime."""
    t1, t2, t3 = thresholds
    if r_bar < t1:
        return Regime.SAFE
    elif r_bar < t2:
        return Regime.ELASTIC
    elif r_bar < t3:
        return Regime.DANGEROUS
    else:
        return Regime.RUNAWAY


def update_ema(r_t: float, r_bar_prev: float, alpha: float = 0.3) -> float:
    """R̄_t = α*R_t + (1-α)*R̄_{t-1}."""
    return alpha * r_t + (1 - alpha) * r_bar_prev


def compute_sma(values: list[float]) -> float:
    """R̄_t = (1/W) * Σ R_i for sliding window."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def compute_worst_case(values: list[float]) -> float:
    """R^max_t = max(R_i) for sliding window."""
    if not values:
        return 0.0
    return max(values)


def compute_p_max(tau: float, evidence: float, delay: float) -> float:
    """P_max = (τ * E) / D — maximum allowed power."""
    d = max(delay, EPSILON)
    return (tau * evidence) / d


def select_privilege_tier(
    p_max: float,
    tiers: list[PrivilegeTier] | None = None,
) -> PrivilegeTier:
    """Select the highest privilege tier fitting P_max."""
    if tiers is None:
        tiers = DEFAULT_PRIVILEGE_TIERS
    selected = tiers[0]
    for tier in tiers:
        if tier.p_threshold <= p_max:
            selected = tier
    return selected


def detect_open_loop(
    actuation_rate: float,
    verification_rate: float,
) -> bool:
    """Γ > 1 → verification lag is growing."""
    if verification_rate <= 0:
        return actuation_rate > 0
    return (actuation_rate / verification_rate) > 1.0


def compute_sensitivity(
    power: float,
    delay: float,
    evidence: float,
    *,
    tau: float = 0.0,
    delta_d: float = 0.0,
    delta_e: float = 0.0,
) -> dict[str, float]:
    """Sensitivity analysis with worst-case perturbation bound.

    Core partials: ∂R/∂D = P/E, ∂R/∂E = -PD/E².

    When ``tau`` > 0, computes margin-to-cap and ``should_demote`` (glass
    cannon detection).  ``delta_d`` / ``delta_e`` are plausible perturbation
    magnitudes for D and E respectively; when non-zero they drive
    ``r_worst`` via first-order bound: ΔR_worst = |∂R/∂D|·δD + |∂R/∂E|·δE.

    Returns dict with keys:
        dr_dd, dr_de    — partial derivatives (always computed)
        risk            — current R_t
        r_worst         — R + ΔR_worst (0 when no deltas provided)
        delta_r_worst   — total first-order perturbation magnitude
        margin          — tau - R (inf when tau not provided)
        margin_to_cap   — margin / delta_r_worst: how many worst-case
                          perturbations until cap breach (inf when
                          delta_r_worst is 0, i.e. no perturbation bounds)
        should_demote   — True iff R < tau but R_worst >= tau (glass cannon);
                          always False when tau/deltas are not provided
    """
    e = max(evidence, EPSILON)
    dr_dd = power / e
    dr_de = -(power * delay) / (e * e)
    r = compute_risk(power, delay, evidence)

    # Normalised sensitivity magnitudes
    s_d = abs(dr_dd) * max(0.0, delta_d)
    s_e = abs(dr_de) * max(0.0, delta_e)
    delta_r_worst = s_d + s_e
    r_worst = min(r + delta_r_worst, 1e6)  # soft clamp (R is unbounded above)

    # Margin-to-cap (meaningful only when tau > 0)
    margin = tau - r if tau > 0 else float("inf")
    margin_to_cap = margin / max(EPSILON, delta_r_worst) if delta_r_worst > 0 else float("inf")

    # Glass cannon: below cap now, but one bounded perturbation away from breach
    should_demote = (tau > 0) and (r < tau) and (r_worst >= tau)

    return {
        "dr_dd": dr_dd,
        "dr_de": dr_de,
        "risk": r,
        "r_worst": r_worst,
        "delta_r_worst": delta_r_worst,
        "margin": margin,
        "margin_to_cap": margin_to_cap,
        "should_demote": should_demote,
    }


def aggregate_episode_risk(
    risks: list[float],
    mode: str = "additive",
    gamma: float = 0.95,
) -> float:
    """Aggregate step risks into episode risk.

    Modes:
      - "additive": J_e = Σ R_t
      - "discounted": J_e = Σ γ^(t-t₀) * R_t
      - "worst_step": J_e = max(R_t)
    """
    if not risks:
        return 0.0
    if mode == "additive":
        return sum(risks)
    elif mode == "discounted":
        total = 0.0
        for i, r in enumerate(risks):
            total += (gamma ** i) * r
        return total
    elif mode == "worst_step":
        return max(risks)
    else:
        raise ValueError(f"Unknown aggregation mode: {mode}")


# ---------------------------------------------------------------------------
# Governor Check (Spec Section 8)
# ---------------------------------------------------------------------------


def governor_check(
    p_req: float,
    d_t: float,
    e_t: float,
    tool_class: str,
    e_min_table: dict[str, float] | None = None,
    tau_table: dict[str, float] | None = None,
    tiers: list[PrivilegeTier] | None = None,
    r_bar: float = 0.0,
    regime_thresholds: tuple[float, float, float] = DEFAULT_REGIME_THRESHOLDS,
) -> GovernorCheckResult:
    """The Governor Loop (spec Section 8): 5-step per-tool check.

    1. Evidence minimum gate
    2. Compute R_t
    3. Per-tool risk cap (with demotion)
    4. Global RUNAWAY halt
    5. Allow
    """
    if e_min_table is None:
        e_min_table = DEFAULT_E_MIN
    if tau_table is None:
        tau_table = DEFAULT_TAU
    if tiers is None:
        tiers = DEFAULT_PRIVILEGE_TIERS

    e_t = max(e_t, EPSILON)

    # Step 1: Evidence minimum gate
    e_min = e_min_table.get(tool_class, 0.1)
    if e_t < e_min:
        return GovernorCheckResult(
            decision=GovernorDecision.DENY,
            risk=compute_risk(p_req, d_t, e_t),
            regime=classify_regime(r_bar, regime_thresholds),
            reason="insufficient_evidence",
            tool_class=tool_class,
            power_requested=p_req,
            metadata={"e_min": e_min, "e_t": e_t},
        )

    # Step 2: Compute R_t
    r_t = compute_risk(p_req, d_t, e_t)

    # Step 3: Per-tool risk cap
    tau = tau_table.get(tool_class, 0.5)
    if r_t > tau:
        p_max = compute_p_max(tau, e_t, d_t)
        demoted_tier = None
        for tier in tiers:
            if tier.p_threshold <= p_max:
                demoted_tier = tier
        if demoted_tier is None:
            return GovernorCheckResult(
                decision=GovernorDecision.DENY,
                risk=r_t,
                regime=classify_regime(r_bar, regime_thresholds),
                reason="risk_too_high",
                tool_class=tool_class,
                power_requested=p_req,
                metadata={"tau": tau, "p_max": p_max},
            )
        else:
            return GovernorCheckResult(
                decision=GovernorDecision.DEMOTE,
                risk=r_t,
                regime=classify_regime(r_bar, regime_thresholds),
                reason="risk_capped",
                tool_class=tool_class,
                power_requested=p_req,
                power_allowed=demoted_tier.p_threshold,
                demoted_tier=demoted_tier,
                metadata={"tau": tau, "p_max": p_max},
            )

    # Step 4: Global regime check (use r_bar for regime classification)
    regime = classify_regime(r_bar, regime_thresholds)
    if regime == Regime.RUNAWAY:
        return GovernorCheckResult(
            decision=GovernorDecision.HALT,
            risk=r_t,
            regime=regime,
            reason="runaway_regime",
            tool_class=tool_class,
            power_requested=p_req,
        )

    # Step 5: Allow
    return GovernorCheckResult(
        decision=GovernorDecision.ALLOW,
        risk=r_t,
        regime=regime,
        reason="allowed",
        tool_class=tool_class,
        power_requested=p_req,
    )


# ---------------------------------------------------------------------------
# RiskController (stateful wrapper)
# ---------------------------------------------------------------------------


class RiskController:
    """Stateful controller tying R_t computation, regime tracking,
    capability shaping, and open-loop detection together.
    """

    def __init__(
        self,
        regime_thresholds: tuple[float, float, float] = DEFAULT_REGIME_THRESHOLDS,
        default_tau: float = 0.5,
        ema_alpha: float = 0.3,
        window_size: int = 100,
        backlog_weight: float = 0.1,
    ) -> None:
        self.regime_thresholds = regime_thresholds
        self.default_tau = default_tau
        self.backlog_weight = backlog_weight
        self.window = RiskWindow(max_size=window_size, ema_alpha=ema_alpha)
        self.current_regime = Regime.SAFE
        self.current_power: float = 0.0
        self.current_delay: float = 0.0
        self.current_evidence: float = 1.0
        self.open_loop = OpenLoopMetrics(actuation_rate=0.0, verification_rate=0.0)
        self.episode_risks: list[float] = []
        self.events: list[dict[str, Any]] = []
        self.history: list[RiskCalculation] = []
        self._max_history = 1000

    def check(
        self,
        tool_class: str,
        p_req: float | None = None,
        d_t: float | None = None,
        e_t: float | None = None,
    ) -> GovernorCheckResult:
        """Main entry point: check whether a tool action is allowed."""
        # Resolve defaults from lookup tables
        if p_req is None:
            metrics = DEFAULT_TOOL_POWER.get(tool_class)
            p_req = metrics.power if metrics else 0.1
        if d_t is None:
            d_t = DEFAULT_DELAY.get(tool_class, 0.5)
        if e_t is None:
            e_t = self.current_evidence

        # Fold in backlog
        d_t = d_t + self.backlog_weight * self.open_loop.backlog

        # Compute R_t and update window
        r_t = compute_risk(p_req, d_t, e_t)
        self.window.add(r_t)
        r_bar = self.window.ema

        # Track state
        old_regime = self.current_regime
        self.current_power = p_req
        self.current_delay = d_t
        self.current_evidence = e_t

        # Run the governor check
        result = governor_check(
            p_req=p_req,
            d_t=d_t,
            e_t=e_t,
            tool_class=tool_class,
            r_bar=r_bar,
            regime_thresholds=self.regime_thresholds,
        )

        # Update regime and track episode
        self.current_regime = result.regime
        self.episode_risks.append(r_t)

        # Record history
        calc = RiskCalculation(
            power=p_req, delay=d_t, evidence=e_t, risk=r_t, regime=result.regime,
        )
        self.history.append(calc)
        if len(self.history) > self._max_history:
            self.history = self.history[-self._max_history:]

        # Emit events
        self._emit(RiskIndexEvent(
            risk=r_t, power=p_req, delay=d_t, evidence=e_t, regime=result.regime,
        ))
        if result.decision != GovernorDecision.ALLOW:
            self._emit(GovernorDecisionEvent(
                decision=result.decision, tool_class=tool_class,
                risk=r_t, reason=result.reason,
            ))
        if old_regime != result.regime:
            self._emit(RegimeTransitionEvent(
                from_regime=old_regime, to_regime=result.regime, r_bar=r_bar,
            ))

        return result

    def update(self, p_t: float, d_t: float, e_t: float) -> RiskCalculation:
        """Manual state update (for instrument integration)."""
        r_t = compute_risk(p_t, d_t, e_t)
        self.window.add(r_t)
        old_regime = self.current_regime
        regime = classify_regime(self.window.ema, self.regime_thresholds)
        self.current_regime = regime
        self.current_power = p_t
        self.current_delay = d_t
        self.current_evidence = e_t
        self.episode_risks.append(r_t)

        calc = RiskCalculation(power=p_t, delay=d_t, evidence=e_t, risk=r_t, regime=regime)
        self.history.append(calc)
        if len(self.history) > self._max_history:
            self.history = self.history[-self._max_history:]

        self._emit(RiskIndexEvent(
            risk=r_t, power=p_t, delay=d_t, evidence=e_t, regime=regime,
        ))
        if old_regime != regime:
            self._emit(RegimeTransitionEvent(
                from_regime=old_regime, to_regime=regime, r_bar=self.window.ema,
            ))

        return calc

    def get_capability_envelope(
        self,
        tau: float | None = None,
        evidence: float | None = None,
        delay: float | None = None,
    ) -> CapabilityEnvelope:
        """Compute current capability envelope."""
        t = tau if tau is not None else self.default_tau
        e = evidence if evidence is not None else self.current_evidence
        d = delay if delay is not None else max(self.current_delay, EPSILON)
        p_max = compute_p_max(t, e, d)
        tier = select_privilege_tier(p_max)

        old_tier_level = getattr(self, "_last_tier_level", 0)
        if tier.level != old_tier_level:
            self._emit(CapabilityChangeEvent(
                old_tier=old_tier_level, new_tier=tier.level, p_max=p_max,
            ))
            self._last_tier_level = tier.level

        return CapabilityEnvelope(evidence=e, delay=d, tau=t, p_max=p_max, tier=tier)

    def get_sensitivity(
        self,
        power: float | None = None,
        delay: float | None = None,
        evidence: float | None = None,
        *,
        delta_d: float = 0.0,
        delta_e: float = 0.0,
    ) -> dict[str, float]:
        """Get sensitivity analysis at current or specified state.

        When ``delta_d`` / ``delta_e`` are non-zero the result includes
        worst-case perturbation bounds and glass-cannon demotion signal.
        """
        p = power if power is not None else self.current_power
        d = delay if delay is not None else self.current_delay
        e = evidence if evidence is not None else self.current_evidence
        result = compute_sensitivity(
            p, d, e,
            tau=self.default_tau,
            delta_d=delta_d,
            delta_e=delta_e,
        )

        # Emit glass cannon event when partials are extreme OR worst-case
        # perturbation would breach cap (should_demote).
        is_glass = (
            result.get("should_demote", False)
            or abs(result["dr_dd"]) > GLASS_CANNON_DR_DD_THRESHOLD
            or abs(result["dr_de"]) > GLASS_CANNON_DR_DE_THRESHOLD
        )
        if is_glass:
            self._emit(GlassCannonDetectedEvent(
                dr_dd=result["dr_dd"],
                dr_de=result["dr_de"],
                risk=result["risk"],
                r_worst=result["r_worst"],
                margin=result["margin"],
                margin_to_cap=result["margin_to_cap"],
                evidence=e,
            ))

        return result

    def get_episode_risk(self, gamma: float = 0.95) -> EpisodeRiskMetrics:
        """Get episode-level risk metrics without resetting."""
        return EpisodeRiskMetrics(
            j_additive=aggregate_episode_risk(self.episode_risks, "additive"),
            j_discounted=aggregate_episode_risk(self.episode_risks, "discounted", gamma),
            j_worst=aggregate_episode_risk(self.episode_risks, "worst_step"),
            step_count=len(self.episode_risks),
        )

    def update_open_loop(
        self,
        actuation_rate: float,
        verification_rate: float,
        backlog: int = 0,
    ) -> OpenLoopMetrics:
        """Update open-loop detection state."""
        self.open_loop = OpenLoopMetrics(
            actuation_rate=actuation_rate,
            verification_rate=verification_rate,
            backlog=backlog,
        )
        if self.open_loop.is_open_loop:
            self._emit(OpenLoopDetectedEvent(
                gamma=self.open_loop.gamma,
                actuation_rate=actuation_rate,
                verification_rate=verification_rate,
                backlog=backlog,
            ))
        return self.open_loop

    def reset_episode(self) -> EpisodeRiskMetrics:
        """Return episode metrics and reset accumulator."""
        metrics = self.get_episode_risk()
        self.episode_risks = []
        return metrics

    def _emit(self, event: Any) -> None:
        """Append event to buffer (capped at MAX_EVENTS)."""
        self.events.append(event.to_dict())
        if len(self.events) > MAX_EVENTS:
            self.events = self.events[-MAX_EVENTS:]

    def get_state(self) -> dict[str, Any]:
        """Get full controller state for display."""
        return {
            "current_regime": self.current_regime.value,
            "r_bar_ema": self.window.ema,
            "r_bar_sma": self.window.sma,
            "r_bar_worst": self.window.worst_case,
            "current_power": self.current_power,
            "current_delay": self.current_delay,
            "current_evidence": self.current_evidence,
            "window_size": len(self.window.values),
            "episode_steps": len(self.episode_risks),
            "open_loop": self.open_loop.to_dict(),
            "event_count": len(self.events),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_thresholds": list(self.regime_thresholds),
            "default_tau": self.default_tau,
            "backlog_weight": self.backlog_weight,
            "window": self.window.to_dict(),
            "current_regime": self.current_regime.value,
            "current_power": self.current_power,
            "current_delay": self.current_delay,
            "current_evidence": self.current_evidence,
            "open_loop": self.open_loop.to_dict(),
            "episode_risks": list(self.episode_risks),
            "events": list(self.events),
            "history": [c.to_dict() for c in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskController:
        thresholds = tuple(data.get("regime_thresholds", list(DEFAULT_REGIME_THRESHOLDS)))
        ctrl = cls(
            regime_thresholds=thresholds,  # type: ignore[arg-type]
            default_tau=data.get("default_tau", 0.5),
            backlog_weight=data.get("backlog_weight", 0.1),
        )
        ctrl.window = RiskWindow.from_dict(data.get("window", {}))
        ctrl.current_regime = Regime(data.get("current_regime", "safe"))
        ctrl.current_power = data.get("current_power", 0.0)
        ctrl.current_delay = data.get("current_delay", 0.0)
        ctrl.current_evidence = data.get("current_evidence", 1.0)
        if "open_loop" in data:
            ctrl.open_loop = OpenLoopMetrics.from_dict(data["open_loop"])
        ctrl.episode_risks = data.get("episode_risks", [])
        ctrl.events = data.get("events", [])
        ctrl.history = [
            RiskCalculation.from_dict(h)
            for h in data.get("history", [])
        ]
        return ctrl
