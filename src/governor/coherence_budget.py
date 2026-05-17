# SPDX-License-Identifier: Apache-2.0
"""
Coherence Budget Index (CBI) — Governor Health Metric.

CBI ∈ [0, 100]. Two layers: invariants (hard) + sensors (soft).
P_inv = ∏(1 - w_i·v_i), S_soft = weighted(S_stab, S_id, S_epi).
CBI = 100 · clamp(S_soft · P_inv, 0, 1).
Δt squeeze: D = τ_v / τ_r attenuates epistemic score.
Uncertainty closure gate blocks COMMIT while U_t > τ.

Spec: COHERENCE_BUDGET_SPEC (Layer 2.1-C)
Invariant H: Passivity — confidence requires evidence or waiver.
Invariant I: Closure Gate — no COMMIT while U_t > threshold.
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

class CBIStatus(str, Enum):
    """CBI health band."""
    OK = "OK"              # 80-100
    NORMAL = "NORMAL"      # 60-80
    DEBT = "DEBT"          # 40-60
    UNSTABLE = "UNSTABLE"  # 20-40
    UNSAFE = "UNSAFE"      # 0-20


class ClosureDecision(str, Enum):
    """Result of closure gate check."""
    ALLOW = "allow"
    ALLOW_WITH_WAIVER = "allow_with_waiver"
    DENY = "deny"


class CBIClaimStatus(str, Enum):
    """Claim status for CBI tracking."""
    UNKNOWN = "unknown"
    VERIFIED = "verified"
    WAIVED = "waived"
    REFUTED = "refuted"


class CBIUnknownStatus(str, Enum):
    """Unknown status for CBI tracking."""
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"


class InvariantID(str, Enum):
    """The seven CBI invariants."""
    S1 = "S1"  # Boundary integrity
    S2 = "S2"  # Credit assignment fidelity
    S3 = "S3"  # Cross-timescale coherence
    S4 = "S4"  # Workspace arbitration integrity
    S5 = "S5"  # Setpoint stability
    S6 = "S6"  # Identity continuity
    S7 = "S7"  # Epistemic integrity


class MetricID(str, Enum):
    """The eight soft metrics."""
    M1 = "M1"  # Switching health
    M2 = "M2"  # Metastability index
    M3 = "M3"  # Integration/segregation balance
    M4 = "M4"  # Cross-timescale coupling
    M5 = "M5"  # Drift rate
    M6 = "M6"  # Gain staging / regime chatter
    M7 = "M7"  # Provenance integrity
    M8 = "M8"  # Recovery / resilience time


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Invariant weights
DEFAULT_INVARIANT_WEIGHTS = {
    "S1": 0.22, "S2": 0.12, "S3": 0.16,
    "S4": 0.12, "S5": 0.12, "S6": 0.10, "S7": 0.16,
}

# Severity weights for uncertainty
SEVERITY_WEIGHTS = {"S1": 1.0, "S2": 3.0, "S3": 10.0}

# CBI thresholds
CBI_OK_THRESHOLD = 80
CBI_NORMAL_THRESHOLD = 60
CBI_DEBT_THRESHOLD = 40
CBI_UNSTABLE_THRESHOLD = 20

# Unsafe invariant violation threshold
UNSAFE_VIOLATION_THRESHOLD = 0.8

# Default uncertainty threshold
DEFAULT_UNCERTAINTY_THRESHOLD = 3.0

# Δt attenuation lambda
DEFAULT_LAMBDA = 0.25

# Default passivity confidence threshold
PASSIVITY_CONFIDENCE_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CBIClaim:
    """A claim tracked by the CBI module."""
    id: str
    severity: str
    status: CBIClaimStatus
    confidence: float = 0.5
    evidence_count: int = 0
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "status": self.status.value,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "evidence_refs": self.evidence_refs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CBIClaim:
        return cls(
            id=d["id"],
            severity=d.get("severity", "S1"),
            status=CBIClaimStatus(d.get("status", "unknown")),
            confidence=d.get("confidence", 0.5),
            evidence_count=d.get("evidence_count", 0),
            evidence_refs=d.get("evidence_refs", []),
        )


@dataclass
class CBIUnknown:
    """An unknown tracked by the CBI module."""
    id: str
    status: CBIUnknownStatus
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status.value, "weight": self.weight}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CBIUnknown:
        return cls(
            id=d["id"],
            status=CBIUnknownStatus(d.get("status", "open")),
            weight=d.get("weight", 1.0),
        )


@dataclass
class CBIResult:
    """Full CBI computation result."""
    cbi: float
    status: CBIStatus
    invariants: dict[str, float]
    p_inv: float
    metrics: dict[str, float]
    s_stab: float
    s_id: float
    s_epi: float
    s_soft: float
    D: float
    tau_v: float = 0.0
    tau_r: float = 0.0
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cbi": round(self.cbi, 4),
            "status": self.status.value,
            "invariants": {k: round(v, 6) for k, v in self.invariants.items()},
            "p_inv": round(self.p_inv, 6),
            "metrics": {k: round(v, 6) for k, v in self.metrics.items()},
            "s_stab": round(self.s_stab, 6),
            "s_id": round(self.s_id, 6),
            "s_epi": round(self.s_epi, 6),
            "s_soft": round(self.s_soft, 6),
            "D": round(self.D, 4),
            "tau_v": round(self.tau_v, 4),
            "tau_r": round(self.tau_r, 4),
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CBIResult:
        return cls(
            cbi=d.get("cbi", 0.0),
            status=CBIStatus(d.get("status", "UNSAFE")),
            invariants=d.get("invariants", {}),
            p_inv=d.get("p_inv", 0.0),
            metrics=d.get("metrics", {}),
            s_stab=d.get("s_stab", 0.0),
            s_id=d.get("s_id", 0.0),
            s_epi=d.get("s_epi", 0.0),
            s_soft=d.get("s_soft", 0.0),
            D=d.get("D", 0.0),
            tau_v=d.get("tau_v", 0.0),
            tau_r=d.get("tau_r", 0.0),
            ts=d.get("ts", ""),
        )


@dataclass
class ClosureGateResult:
    """Result of uncertainty closure gate check."""
    decision: ClosureDecision
    uncertainty: float
    threshold: float
    unverified_claims: int = 0
    open_unknowns: int = 0
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "uncertainty": round(self.uncertainty, 4),
            "threshold": self.threshold,
            "unverified_claims": self.unverified_claims,
            "open_unknowns": self.open_unknowns,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClosureGateResult:
        return cls(
            decision=ClosureDecision(d["decision"]),
            uncertainty=d.get("uncertainty", 0.0),
            threshold=d.get("threshold", DEFAULT_UNCERTAINTY_THRESHOLD),
            unverified_claims=d.get("unverified_claims", 0),
            open_unknowns=d.get("open_unknowns", 0),
            ts=d.get("ts", ""),
        )


# ---------------------------------------------------------------------------
# Metric functions (M1-M8)
# ---------------------------------------------------------------------------

def compute_m1(
    switch_rate: float, target_rate: float,
    tolerance: float = 1.0,
    lock_in_fraction: float = 0.0,
    thrash_fraction: float = 0.0,
) -> float:
    """M1: Switching health (thrash vs lock-in)."""
    if switch_rate <= 0 or target_rate <= 0:
        s_switch = 0.0
    else:
        s_switch = math.exp(-abs(math.log(switch_rate / target_rate)) / tolerance)
    return max(0.0, min(1.0, s_switch * (1 - lock_in_fraction) * (1 - thrash_fraction)))


def compute_m2(
    coalition_distribution: dict[str, int],
    h_low: float = 0.3, h_high: float = 0.8,
) -> float:
    """M2: Metastability index (coalition entropy)."""
    total = sum(coalition_distribution.values())
    if total == 0:
        return 1.0
    probs = [c / total for c in coalition_distribution.values() if c > 0]
    max_entropy = math.log(len(probs)) if len(probs) > 1 else 1.0
    entropy = -sum(p * math.log(p) for p in probs) / max_entropy if max_entropy > 0 else 0.0
    if h_low <= entropy <= h_high:
        return 1.0
    elif entropy < h_low:
        return max(0.0, 1 - (h_low - entropy))
    else:
        return max(0.0, 1 - (entropy - h_high))


def compute_m3(
    cross_module_refs: int, total_refs: int,
    within_module_continuity: float = 0.5, total_continuity: float = 1.0,
) -> float:
    """M3: Integration/segregation balance."""
    if total_refs == 0 or total_continuity == 0:
        return 1.0
    integration = cross_module_refs / total_refs
    segregation = within_module_continuity / total_continuity
    score = 1 - abs(integration - 0.5) - abs(segregation - 0.5)
    return max(0.0, min(1.0, score))


def compute_m4(fast_goal_ids: set[str], slow_goal_ids: set[str]) -> float:
    """M4: Cross-timescale coupling (Jaccard of goals)."""
    if not fast_goal_ids and not slow_goal_ids:
        return 1.0
    union = len(fast_goal_ids | slow_goal_ids)
    if union == 0:
        return 1.0
    return len(fast_goal_ids & slow_goal_ids) / union


def compute_m5(drift: float, drift_max: float = 1.0) -> float:
    """M5: Drift rate (slow state stability)."""
    if drift_max <= 0:
        return 0.0
    return math.exp(-drift / drift_max)


def compute_m6(
    regime_switches: int, window_hours: float,
    stuck_fraction: float = 0.0, k_max: float = 5.0,
) -> float:
    """M6: Gain staging / regime chatter."""
    k = regime_switches / window_hours if window_hours > 0 else 0
    chatter_score = math.exp(-k / k_max)
    stuck_penalty = 1.0 if stuck_fraction < 0.95 else 0.5
    return max(0.0, min(1.0, chatter_score * stuck_penalty))


def compute_m7(
    outputs_with_trace: int, total_outputs: int,
    unknown_cause_count: int = 0,
) -> float:
    """M7: Provenance integrity (auditability)."""
    if total_outputs == 0:
        return 1.0
    p = outputs_with_trace / total_outputs
    u = unknown_cause_count / total_outputs
    return max(0.0, min(1.0, p * (1 - u)))


def compute_m8(recovery_time_s: float, target_recovery_s: float = 60.0) -> float:
    """M8: Recovery / resilience time."""
    if recovery_time_s <= 0:
        return 1.0
    if target_recovery_s <= 0:
        return 0.0
    return math.exp(-recovery_time_s / target_recovery_s)


# ---------------------------------------------------------------------------
# Δt and attenuation
# ---------------------------------------------------------------------------

def compute_dt(tau_v: float, tau_r: float) -> float:
    """Compute Δt squeeze ratio D = τ_v / τ_r."""
    if tau_r <= 0:
        return 0.0
    return tau_v / tau_r


def attenuate_epistemic(m7: float, D: float, lambda_: float = DEFAULT_LAMBDA) -> float:
    """S_epi = M7 · exp(-λ · max(0, D-1))."""
    return m7 * math.exp(-lambda_ * max(0.0, D - 1))


# ---------------------------------------------------------------------------
# Slow-state fingerprinting
# ---------------------------------------------------------------------------

def compute_slow_hash(commitments: list[str]) -> str:
    """Content-addressed hash of commitments."""
    canonical = sorted(" ".join(c.lower().split()) for c in commitments)
    canonical_str = "\n".join(canonical)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_drift_distance(hash_a: str, hash_b: str) -> float:
    """Hamming distance / 256 between two hex hashes."""
    if not hash_a or not hash_b:
        return 0.0
    bits_a = bin(int(hash_a, 16))[2:].zfill(256)
    bits_b = bin(int(hash_b, 16))[2:].zfill(256)
    distance = sum(a != b for a, b in zip(bits_a, bits_b))
    return distance / 256


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def compute_stability_score(
    m1: float, m2: float, m3: float,
    m4: float, m6: float, m8: float,
) -> float:
    """S_stab weighted average."""
    return 0.22 * m1 + 0.12 * m2 + 0.12 * m3 + 0.18 * m4 + 0.18 * m6 + 0.18 * m8


def compute_soft_score(s_stab: float, s_id: float, s_epi: float) -> float:
    """S_soft from three bundles."""
    return 0.45 * s_stab + 0.20 * s_id + 0.35 * s_epi


def compute_invariant_penalty(
    violations: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """P_inv = ∏(1 - w_i · v_i)."""
    w = weights or DEFAULT_INVARIANT_WEIGHTS
    p = 1.0
    for sid, weight in w.items():
        v = violations.get(sid, 0.0)
        p *= (1.0 - weight * v)
    return max(0.0, p)


def classify_cbi(cbi: float, has_unsafe_violation: bool = False) -> CBIStatus:
    """Classify CBI into health band."""
    if has_unsafe_violation or cbi < CBI_UNSTABLE_THRESHOLD:
        return CBIStatus.UNSAFE
    if cbi < CBI_DEBT_THRESHOLD:
        return CBIStatus.UNSTABLE
    if cbi < CBI_NORMAL_THRESHOLD:
        return CBIStatus.DEBT
    if cbi < CBI_OK_THRESHOLD:
        return CBIStatus.NORMAL
    return CBIStatus.OK


def compute_cbi(
    invariant_violations: dict[str, float],
    metrics: dict[str, float],
    D: float = 0.0,
    inv_weights: dict[str, float] | None = None,
    lambda_: float = DEFAULT_LAMBDA,
    tau_v: float = 0.0,
    tau_r: float = 0.0,
) -> CBIResult:
    """Full CBI computation."""
    # Invariant penalty
    p_inv = compute_invariant_penalty(invariant_violations, inv_weights)

    # Check unsafe
    max_v = max(invariant_violations.values()) if invariant_violations else 0.0
    has_unsafe = max_v > UNSAFE_VIOLATION_THRESHOLD

    # Soft scores
    s_stab = compute_stability_score(
        metrics.get("M1", 1.0), metrics.get("M2", 1.0), metrics.get("M3", 1.0),
        metrics.get("M4", 1.0), metrics.get("M6", 1.0), metrics.get("M8", 1.0),
    )
    s_id = metrics.get("M5", 1.0)
    s_epi = attenuate_epistemic(metrics.get("M7", 1.0), D, lambda_)

    s_soft = compute_soft_score(s_stab, s_id, s_epi)
    raw_cbi = 100.0 * max(0.0, min(1.0, s_soft * p_inv))

    if has_unsafe:
        raw_cbi = min(raw_cbi, 20.0)

    status = classify_cbi(raw_cbi, has_unsafe)

    return CBIResult(
        cbi=raw_cbi,
        status=status,
        invariants=invariant_violations,
        p_inv=p_inv,
        metrics=metrics,
        s_stab=s_stab,
        s_id=s_id,
        s_epi=s_epi,
        s_soft=s_soft,
        D=D,
        tau_v=tau_v,
        tau_r=tau_r,
    )


# ---------------------------------------------------------------------------
# Uncertainty + Closure Gate
# ---------------------------------------------------------------------------

def compute_uncertainty(
    claims: list[CBIClaim], unknowns: list[CBIUnknown],
) -> float:
    """U_t = Σ w_i·𝟙[claim not verified/waived] + Σ γ_j·𝟙[unknown open]."""
    claim_u = sum(
        SEVERITY_WEIGHTS.get(c.severity, 1.0)
        for c in claims
        if c.status not in {CBIClaimStatus.VERIFIED, CBIClaimStatus.WAIVED}
    )
    unknown_u = sum(u.weight for u in unknowns if u.status == CBIUnknownStatus.OPEN)
    return claim_u + unknown_u


def check_uncertainty_invariant(
    claims: list[CBIClaim],
    unknowns: list[CBIUnknown],
    threshold: float = DEFAULT_UNCERTAINTY_THRESHOLD,
    has_human_waiver: bool = False,
) -> ClosureGateResult:
    """Invariant I: No COMMIT while U_t > threshold (unless waiver).

    One of seven invariants. ALLOW here means "uncertainty below threshold"
    only; callers must compose with the other invariant checks before
    treating as authorization to proceed.
    """
    u_t = compute_uncertainty(claims, unknowns)
    unverified = sum(
        1 for c in claims
        if c.status not in {CBIClaimStatus.VERIFIED, CBIClaimStatus.WAIVED}
    )
    open_unknowns = sum(1 for u in unknowns if u.status == CBIUnknownStatus.OPEN)

    if u_t <= threshold:
        decision = ClosureDecision.ALLOW
    elif has_human_waiver:
        decision = ClosureDecision.ALLOW_WITH_WAIVER
    else:
        decision = ClosureDecision.DENY

    return ClosureGateResult(
        decision=decision,
        uncertainty=u_t,
        threshold=threshold,
        unverified_claims=unverified,
        open_unknowns=open_unknowns,
    )


# ---------------------------------------------------------------------------
# Passivity check (Invariant H)
# ---------------------------------------------------------------------------

def check_passivity(
    claim: CBIClaim,
    has_waiver: bool = False,
    threshold: float = PASSIVITY_CONFIDENCE_THRESHOLD,
) -> tuple[bool, str]:
    """Invariant H: Confidence requires evidence or waiver."""
    if claim.confidence <= threshold:
        return True, "below threshold"
    has_evidence = claim.evidence_count > 0 or len(claim.evidence_refs) > 0
    if has_evidence:
        return True, "has evidence"
    if has_waiver:
        return True, "has waiver"
    return False, f"confidence {claim.confidence:.2f} exceeds {threshold} without evidence"


# ---------------------------------------------------------------------------
# Confidence cap under Δt
# ---------------------------------------------------------------------------

def confidence_cap(D: float, evidence_count: int) -> float:
    """Maximum justified confidence given D and evidence."""
    if D <= 1.0 and evidence_count >= 2:
        return 0.95
    if D > 3.0:
        return 0.35
    return 0.60


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class CoherenceBudgetStore:
    """Persistent store for CBI state."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.cbi_dir = self.governor_dir / "coherence"

    def _ensure_dirs(self) -> None:
        self.cbi_dir.mkdir(parents=True, exist_ok=True)

    def save(self, run_id: str, result: CBIResult) -> Path:
        self._ensure_dirs()
        path = self.cbi_dir / f"{run_id}.json"
        path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
        return path

    def load(self, run_id: str) -> CBIResult | None:
        path = self.cbi_dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return CBIResult.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def list_runs(self) -> list[str]:
        if not self.cbi_dir.exists():
            return []
        return sorted(f.stem for f in self.cbi_dir.glob("*.json"))

    def save_closure(self, run_id: str, result: ClosureGateResult) -> Path:
        self._ensure_dirs()
        path = self.cbi_dir / f"closure_{run_id}.json"
        path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
        return path

    def load_closure(self, run_id: str) -> ClosureGateResult | None:
        path = self.cbi_dir / f"closure_{run_id}.json"
        if not path.exists():
            return None
        try:
            return ClosureGateResult.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_cbi_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "coherence_budget",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
