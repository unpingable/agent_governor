# SPDX-License-Identifier: Apache-2.0
"""
Research mode: non-convergent epistemic control.

Research is adversarial to its own premises. Unlike nonfiction mode (which
optimizes for communicability), research mode optimizes for epistemic
survivability under delayed evidence.

Key invariants:
1. Convergence is suspicious; ambiguity is signal
2. Every claim must expose what would falsify it
3. Mutually exclusive hypotheses coexist without pressure to resolve
4. Evidence disciplines claims (not decorates them)
5. Truth is provisional and time-indexed
6. Success = improved question topology, not answer confidence

Claim lifecycle: PROBE → TENTATIVE → SUPPORTED → ABANDONED
Entropy bounds: H_min ≤ H(t) ≤ H_max
Dominance cap: D_i < D_max for all i
Δt invariant: τ_c ≥ k · τ_e (claims harden slower than evidence arrives)

Control framing: bounded-entropy, decay-governed, non-convergent control
system whose objective is to maximize survivability under delayed evidence,
not to minimize error against a fixed reference.
"""

import math
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class HypothesisState(str, Enum):
    """Lifecycle states for research hypotheses."""

    PROBE = "probe"
    """Speculative; may be wrong; default state."""

    TENTATIVE = "tentative"
    """Weak support exists; still unstable."""

    SUPPORTED = "supported"
    """Multiple independent evidence; survives contradiction."""

    ABANDONED = "abandoned"
    """Dominated by contradiction or lack of refresh; retained historically."""


class TerminalStateType(str, Enum):
    """Types of honest research termination."""

    ILL_POSED = "ill_posed"
    """Question presupposes invalid construct or is non-identifiable."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    """Evidence cannot discriminate between hypotheses."""

    MULTIPLE_LIVE_HYPOTHESES = "multiple_live_hypotheses"
    """Several hypotheses survive without dominance."""


class PromotionBlockReason(str, Enum):
    """Reasons why hypothesis promotion is blocked."""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DOMINANCE_CAP = "dominance_cap"
    ENTROPY_FLOOR = "entropy_floor"
    DELTA_T_VIOLATION = "delta_t_violation"
    UNRESOLVED_CONTRADICTION = "unresolved_contradiction"
    CRYSTALLIZATION_TOO_FAST = "crystallization_too_fast"


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class ResearchConfig:
    """Policy profile for research mode."""

    default_lambda: float = 0.05
    """Default decay rate for hypothesis credence."""

    H_min: float = 0.5
    """Minimum epistemic entropy (below = dogma)."""

    H_max: float = 3.0
    """Maximum epistemic entropy (above = incoherent sprawl)."""

    D_max: float = 0.7
    """Maximum dominance ratio for any single hypothesis."""

    k_timescale: float = 1.5
    """τ_c ≥ k · τ_e (claim crystallization must be slower than evidence)."""

    epsilon: float = 0.05
    """Credence threshold below which hypotheses may be auto-archived."""

    W: int = 10
    """Window (in ticks) without reinforcement before auto-archive."""

    max_active: int = 20
    """Maximum active hypotheses (sprawl control)."""

    K_independent: int = 2
    """Minimum independent evidence impulses for SUPPORTED promotion."""

    maintenance_cost_rate: float = 0.01
    """Per-tick maintenance cost subtracted from credence."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_lambda": self.default_lambda,
            "H_min": self.H_min,
            "H_max": self.H_max,
            "D_max": self.D_max,
            "k_timescale": self.k_timescale,
            "epsilon": self.epsilon,
            "W": self.W,
            "max_active": self.max_active,
            "K_independent": self.K_independent,
            "maintenance_cost_rate": self.maintenance_cost_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchConfig":
        return cls(**{k: data[k] for k in data if k in cls.__dataclass_fields__})


@dataclass
class EvidenceImpulse:
    """A discrete evidence event attached to a hypothesis."""

    hypothesis_id: str
    evidence_ref_id: str
    base_strength: float
    independence_score: float = 1.0
    novelty_score: float = 1.0
    is_contradiction: bool = False
    tick: int = 0

    @property
    def alpha(self) -> float:
        """Effective impulse strength: base × independence × novelty."""
        return self.base_strength * self.independence_score * self.novelty_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "evidence_ref_id": self.evidence_ref_id,
            "base_strength": self.base_strength,
            "independence_score": self.independence_score,
            "novelty_score": self.novelty_score,
            "alpha": self.alpha,
            "is_contradiction": self.is_contradiction,
            "tick": self.tick,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceImpulse":
        return cls(
            hypothesis_id=data["hypothesis_id"],
            evidence_ref_id=data["evidence_ref_id"],
            base_strength=data["base_strength"],
            independence_score=data.get("independence_score", 1.0),
            novelty_score=data.get("novelty_score", 1.0),
            is_contradiction=data.get("is_contradiction", False),
            tick=data.get("tick", 0),
        )


@dataclass
class Hypothesis:
    """Core research unit: a falsifiable conjecture with evidence trail."""

    hypothesis_id: str
    content: str
    state: HypothesisState = HypothesisState.PROBE
    credence: float = 0.3
    falsifier: str = ""
    parent_id: str | None = None
    claim_id: str | None = None
    competitors: list[str] = field(default_factory=list)
    evidence_impulses: list[EvidenceImpulse] = field(default_factory=list)
    lambda_decay: float = 0.05
    maintenance_cost_rate: float = 0.01
    last_reinforced_at: int = 0
    created_at: int = 0
    archived: bool = False

    @property
    def positive_impulses(self) -> list[EvidenceImpulse]:
        return [e for e in self.evidence_impulses if not e.is_contradiction]

    @property
    def negative_impulses(self) -> list[EvidenceImpulse]:
        return [e for e in self.evidence_impulses if e.is_contradiction]

    @property
    def net_evidence_count(self) -> int:
        return len(self.positive_impulses) - len(self.negative_impulses)

    @property
    def independent_evidence_count(self) -> int:
        """Count of positive impulses with independence_score > 0.5."""
        return sum(
            1 for e in self.positive_impulses
            if e.independence_score > 0.5
        )

    @property
    def is_active(self) -> bool:
        return self.state in {HypothesisState.PROBE, HypothesisState.TENTATIVE, HypothesisState.SUPPORTED} and not self.archived

    @property
    def is_stale(self) -> bool:
        """Whether hypothesis has no recent reinforcement."""
        if not self.positive_impulses:
            return True
        latest = max(e.tick for e in self.positive_impulses)
        return (self.last_reinforced_at - latest) > 0  # This is always False with correct usage

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "content": self.content,
            "state": self.state.value,
            "credence": self.credence,
            "falsifier": self.falsifier,
            "parent_id": self.parent_id,
            "claim_id": self.claim_id,
            "competitors": self.competitors,
            "evidence_impulses": [e.to_dict() for e in self.evidence_impulses],
            "lambda_decay": self.lambda_decay,
            "maintenance_cost_rate": self.maintenance_cost_rate,
            "last_reinforced_at": self.last_reinforced_at,
            "created_at": self.created_at,
            "archived": self.archived,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hypothesis":
        return cls(
            hypothesis_id=data["hypothesis_id"],
            content=data["content"],
            state=HypothesisState(data["state"]),
            credence=data.get("credence", 0.3),
            falsifier=data.get("falsifier", ""),
            parent_id=data.get("parent_id"),
            claim_id=data.get("claim_id"),
            competitors=data.get("competitors", []),
            evidence_impulses=[
                EvidenceImpulse.from_dict(e)
                for e in data.get("evidence_impulses", [])
            ],
            lambda_decay=data.get("lambda_decay", 0.05),
            maintenance_cost_rate=data.get("maintenance_cost_rate", 0.01),
            last_reinforced_at=data.get("last_reinforced_at", 0),
            created_at=data.get("created_at", 0),
            archived=data.get("archived", False),
        )


@dataclass
class TerminalState:
    """Typed honest refusal with certificate."""

    terminal_type: TerminalStateType
    reason: str
    live_hypotheses: list[str] = field(default_factory=list)
    missing_evidence_types: list[str] = field(default_factory=list)
    competing_hypothesis_ids: list[str] = field(default_factory=list)
    minimal_missing_spec: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "terminal_type": self.terminal_type.value,
            "reason": self.reason,
            "live_hypotheses": self.live_hypotheses,
            "missing_evidence_types": self.missing_evidence_types,
            "competing_hypothesis_ids": self.competing_hypothesis_ids,
            "minimal_missing_spec": self.minimal_missing_spec,
        }


# =============================================================================
# Monitor Results
# =============================================================================


@dataclass
class EntropyCheckResult:
    """Result of entropy bounds check."""

    entropy: float
    within_bounds: bool
    violation_type: str | None = None  # "below_min" or "above_max"
    corrective_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entropy": self.entropy,
            "within_bounds": self.within_bounds,
            "violation_type": self.violation_type,
            "corrective_actions": self.corrective_actions,
        }


@dataclass
class DominanceCheckResult:
    """Result of dominance cap check."""

    violations: list[str]
    max_dominance: float
    dominant_hypothesis_id: str | None = None
    within_bounds: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "violations": self.violations,
            "max_dominance": self.max_dominance,
            "dominant_hypothesis_id": self.dominant_hypothesis_id,
            "within_bounds": self.within_bounds,
        }


@dataclass
class DeltaTCheckResult:
    """Result of timescale separation check."""

    tau_e: float
    tau_c: float
    ratio: float
    required_ratio: float
    within_bounds: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "tau_e": self.tau_e,
            "tau_c": self.tau_c,
            "ratio": self.ratio,
            "required_ratio": self.required_ratio,
            "within_bounds": self.within_bounds,
        }


# =============================================================================
# Monitors
# =============================================================================


class EntropyMonitor:
    """Monitors epistemic entropy over hypothesis credences."""

    def __init__(self, h_min: float = 0.5, h_max: float = 3.0):
        self.h_min = h_min
        self.h_max = h_max

    def compute_entropy(self, hypotheses: list[Hypothesis]) -> float:
        """Compute Shannon entropy over active hypothesis credences."""
        active = [h for h in hypotheses if h.is_active and h.credence > 0]
        if not active:
            return 0.0

        total = sum(h.credence for h in active)
        if total <= 0:
            return 0.0

        entropy = 0.0
        for h in active:
            p = h.credence / total
            if p > 0:
                entropy -= p * math.log(p)

        return entropy

    def check(self, hypotheses: list[Hypothesis]) -> EntropyCheckResult:
        """Check if entropy is within bounds."""
        entropy = self.compute_entropy(hypotheses)
        actions: list[str] = []

        if entropy < self.h_min:
            actions.extend([
                "Increase adversarial probing",
                "Require new independent evidence for dominant hypothesis",
                "Spawn competing hypotheses",
            ])
            return EntropyCheckResult(
                entropy=entropy,
                within_bounds=False,
                violation_type="below_min",
                corrective_actions=actions,
            )

        if entropy > self.h_max:
            actions.extend([
                "Prune low-credence hypotheses",
                "Increase decay for unsupported hypotheses",
                "Enforce maintenance cost",
            ])
            return EntropyCheckResult(
                entropy=entropy,
                within_bounds=False,
                violation_type="above_max",
                corrective_actions=actions,
            )

        return EntropyCheckResult(
            entropy=entropy,
            within_bounds=True,
        )


class DominanceMonitor:
    """Monitors dominance ratios to prevent winner-take-all collapse."""

    def __init__(self, d_max: float = 0.7):
        self.d_max = d_max

    def compute_dominance(
        self, hypotheses: list[Hypothesis]
    ) -> dict[str, float]:
        """Compute dominance ratio D_i = C_i / Σ C_j for active hypotheses."""
        active = [h for h in hypotheses if h.is_active and h.credence > 0]
        total = sum(h.credence for h in active)
        if total <= 0:
            return {}
        return {h.hypothesis_id: h.credence / total for h in active}

    def check(self, hypotheses: list[Hypothesis]) -> DominanceCheckResult:
        """Check if any hypothesis exceeds dominance cap."""
        dom = self.compute_dominance(hypotheses)
        violations: list[str] = []
        max_d = 0.0
        dominant_id: str | None = None

        for hid, d in dom.items():
            if d > max_d:
                max_d = d
                dominant_id = hid
            if d >= self.d_max:
                violations.append(
                    f"Hypothesis {hid} dominance {d:.3f} >= cap {self.d_max}"
                )

        return DominanceCheckResult(
            violations=violations,
            max_dominance=max_d,
            dominant_hypothesis_id=dominant_id,
            within_bounds=len(violations) == 0,
        )


class TimescaleMonitor:
    """Monitors Δt invariant: τ_c ≥ k · τ_e."""

    def __init__(self, k_timescale: float = 1.5):
        self.k_timescale = k_timescale
        self._evidence_ticks: list[int] = []
        self._promotion_ticks: list[int] = []

    def record_evidence_arrival(self, tick: int) -> None:
        """Record when evidence arrived."""
        self._evidence_ticks.append(tick)

    def record_promotion(self, tick: int) -> None:
        """Record when a promotion occurred."""
        self._promotion_ticks.append(tick)

    def check(self) -> DeltaTCheckResult:
        """Check if timescale separation holds."""
        tau_e = self._compute_tau(self._evidence_ticks)
        tau_c = self._compute_tau(self._promotion_ticks)

        if tau_e == 0:
            # No evidence cadence (< 2 events) → can't violate
            return DeltaTCheckResult(
                tau_e=0.0,
                tau_c=tau_c,
                ratio=float("inf") if tau_c > 0 else 0.0,
                required_ratio=self.k_timescale,
                within_bounds=True,
            )

        if tau_c == 0:
            # No promotion cadence (< 2 events) → can't violate yet
            return DeltaTCheckResult(
                tau_e=tau_e,
                tau_c=0.0,
                ratio=float("inf"),
                required_ratio=self.k_timescale,
                within_bounds=True,
            )

        ratio = tau_c / tau_e
        within = ratio >= self.k_timescale

        return DeltaTCheckResult(
            tau_e=tau_e,
            tau_c=tau_c,
            ratio=ratio,
            required_ratio=self.k_timescale,
            within_bounds=within,
        )

    def _compute_tau(self, ticks: list[int]) -> float:
        """Compute characteristic timescale from inter-event intervals."""
        if len(ticks) < 2:
            return 0.0
        sorted_t = sorted(ticks)
        intervals = [sorted_t[i+1] - sorted_t[i] for i in range(len(sorted_t) - 1)]
        return sum(intervals) / len(intervals)


# =============================================================================
# Research Ledger
# =============================================================================


class ResearchLedger:
    """
    Non-convergent epistemic control ledger.

    Manages hypotheses, evidence, promotion gates, decay, and monitors.
    Receives dependencies externally (follows QuorumManager pattern).
    """

    def __init__(
        self,
        config: ResearchConfig | None = None,
        epistemic_ledger: Any | None = None,
        ttl_manager: Any | None = None,
        independence_scorer: Any | None = None,
    ):
        self.config = config or ResearchConfig()
        self.epistemic_ledger = epistemic_ledger
        self.ttl_manager = ttl_manager
        self.independence_scorer = independence_scorer

        self.hypotheses: dict[str, Hypothesis] = {}
        self.tick_count: int = 0

        # Monitors
        self.entropy_monitor = EntropyMonitor(self.config.H_min, self.config.H_max)
        self.dominance_monitor = DominanceMonitor(self.config.D_max)
        self.timescale_monitor = TimescaleMonitor(self.config.k_timescale)

    # =========================================================================
    # Hypothesis Management
    # =========================================================================

    def create_hypothesis(
        self,
        content: str,
        falsifier: str = "",
        parent_id: str | None = None,
        claim_id: str | None = None,
    ) -> Hypothesis:
        """Create a new hypothesis in PROBE state."""
        active = self.active_hypotheses()
        if len(active) >= self.config.max_active:
            raise ValueError(
                f"Max active hypotheses ({self.config.max_active}) reached"
            )

        hid = f"hyp_{uuid.uuid4().hex[:12]}"
        h = Hypothesis(
            hypothesis_id=hid,
            content=content,
            state=HypothesisState.PROBE,
            credence=0.3,
            falsifier=falsifier,
            parent_id=parent_id,
            claim_id=claim_id,
            lambda_decay=self.config.default_lambda,
            maintenance_cost_rate=self.config.maintenance_cost_rate,
            last_reinforced_at=self.tick_count,
            created_at=self.tick_count,
        )
        self.hypotheses[hid] = h
        return h

    def spawn(self, parent_id: str, delta: str) -> Hypothesis:
        """Spawn a child hypothesis from an existing one."""
        parent = self.hypotheses.get(parent_id)
        if parent is None:
            raise KeyError(f"Parent hypothesis not found: {parent_id}")

        content = f"{parent.content} [variant: {delta}]"
        child = self.create_hypothesis(
            content=content,
            falsifier=parent.falsifier,
            parent_id=parent_id,
        )
        return child

    def mark_competitors(self, a_id: str, b_id: str) -> None:
        """Mark two hypotheses as mutually exclusive competitors."""
        a = self.hypotheses.get(a_id)
        b = self.hypotheses.get(b_id)
        if a is None or b is None:
            raise KeyError("Hypothesis not found")
        if b_id not in a.competitors:
            a.competitors.append(b_id)
        if a_id not in b.competitors:
            b.competitors.append(a_id)

    # =========================================================================
    # Evidence
    # =========================================================================

    def attach_evidence(
        self,
        hypothesis_id: str,
        evidence_ref_id: str,
        base_strength: float = 1.0,
        independence_score: float = 1.0,
        novelty_score: float = 1.0,
    ) -> EvidenceImpulse:
        """Attach positive evidence to a hypothesis."""
        h = self.hypotheses.get(hypothesis_id)
        if h is None:
            raise KeyError(f"Hypothesis not found: {hypothesis_id}")

        impulse = EvidenceImpulse(
            hypothesis_id=hypothesis_id,
            evidence_ref_id=evidence_ref_id,
            base_strength=base_strength,
            independence_score=independence_score,
            novelty_score=novelty_score,
            is_contradiction=False,
            tick=self.tick_count,
        )
        h.evidence_impulses.append(impulse)
        h.credence += impulse.alpha
        h.last_reinforced_at = self.tick_count
        self.timescale_monitor.record_evidence_arrival(self.tick_count)
        return impulse

    def file_contradiction(
        self,
        hypothesis_id: str,
        evidence_ref_id: str,
        severity: float = 1.0,
    ) -> EvidenceImpulse:
        """File a contradiction against a hypothesis."""
        h = self.hypotheses.get(hypothesis_id)
        if h is None:
            raise KeyError(f"Hypothesis not found: {hypothesis_id}")

        impulse = EvidenceImpulse(
            hypothesis_id=hypothesis_id,
            evidence_ref_id=evidence_ref_id,
            base_strength=severity,
            independence_score=1.0,
            novelty_score=1.0,
            is_contradiction=True,
            tick=self.tick_count,
        )
        h.evidence_impulses.append(impulse)
        h.credence = max(0.0, h.credence - impulse.alpha)
        return impulse

    # =========================================================================
    # Promotion
    # =========================================================================

    def can_promote(
        self, hypothesis_id: str
    ) -> tuple[bool, list[PromotionBlockReason]]:
        """
        Check if a hypothesis can be promoted to the next state.

        PROBE→TENTATIVE: ≥1 evidence impulse with provenance
        TENTATIVE→SUPPORTED: ≥K independent evidence, dominance cap,
                              entropy floor, Δt invariant
        """
        h = self.hypotheses.get(hypothesis_id)
        if h is None:
            return False, []

        blocks: list[PromotionBlockReason] = []

        if h.state == HypothesisState.PROBE:
            # PROBE → TENTATIVE: need ≥1 evidence
            if len(h.positive_impulses) < 1:
                blocks.append(PromotionBlockReason.INSUFFICIENT_EVIDENCE)

        elif h.state == HypothesisState.TENTATIVE:
            # TENTATIVE → SUPPORTED: multiple gates

            # Gate 1: K independent evidence
            if h.independent_evidence_count < self.config.K_independent:
                blocks.append(PromotionBlockReason.INSUFFICIENT_EVIDENCE)

            # Gate 2: Dominance cap
            dom_check = self.dominance_monitor.check(list(self.hypotheses.values()))
            if not dom_check.within_bounds and dom_check.dominant_hypothesis_id == hypothesis_id:
                blocks.append(PromotionBlockReason.DOMINANCE_CAP)

            # Gate 3: Entropy floor
            entropy_check = self.entropy_monitor.check(list(self.hypotheses.values()))
            if not entropy_check.within_bounds and entropy_check.violation_type == "below_min":
                blocks.append(PromotionBlockReason.ENTROPY_FLOOR)

            # Gate 4: Δt invariant
            dt_check = self.timescale_monitor.check()
            if not dt_check.within_bounds:
                blocks.append(PromotionBlockReason.DELTA_T_VIOLATION)

            # Gate 5: Unresolved contradictions
            if len(h.negative_impulses) > 0:
                recent_contradictions = [
                    e for e in h.negative_impulses
                    if (self.tick_count - e.tick) < self.config.W
                ]
                if recent_contradictions:
                    blocks.append(PromotionBlockReason.UNRESOLVED_CONTRADICTION)

        else:
            # SUPPORTED and ABANDONED can't promote further
            return False, []

        return len(blocks) == 0, blocks

    def promote(self, hypothesis_id: str) -> tuple[bool, list[str]]:
        """
        Attempt to promote a hypothesis.

        Returns (success, reasons).
        """
        can, blocks = self.can_promote(hypothesis_id)
        if not can:
            return False, [b.value for b in blocks]

        h = self.hypotheses[hypothesis_id]
        if h.state == HypothesisState.PROBE:
            h.state = HypothesisState.TENTATIVE
            self.timescale_monitor.record_promotion(self.tick_count)
            return True, ["Promoted to TENTATIVE"]
        elif h.state == HypothesisState.TENTATIVE:
            h.state = HypothesisState.SUPPORTED
            self.timescale_monitor.record_promotion(self.tick_count)
            return True, ["Promoted to SUPPORTED"]

        return False, ["No valid promotion path"]

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def abandon(self, hypothesis_id: str, reason: str = "") -> bool:
        """Abandon a hypothesis. Retained historically."""
        h = self.hypotheses.get(hypothesis_id)
        if h is None:
            return False
        if h.state == HypothesisState.ABANDONED:
            return False
        h.state = HypothesisState.ABANDONED
        return True

    def archive(self, hypothesis_id: str) -> bool:
        """Archive a hypothesis (remove from active set, preserve history)."""
        h = self.hypotheses.get(hypothesis_id)
        if h is None:
            return False
        h.archived = True
        return True

    # =========================================================================
    # Time / Decay
    # =========================================================================

    def tick(self) -> dict[str, Any]:
        """
        Advance time by one tick.

        Ordering: (1) decay, (2) maintenance cost, (3) auto-archive, (4) summary.
        """
        self.tick_count += 1
        summary: dict[str, Any] = {
            "tick": self.tick_count,
            "decayed": [],
            "maintenance_charged": [],
            "auto_archived": [],
            "auto_abandoned": [],
        }

        for h in list(self.hypotheses.values()):
            if not h.is_active:
                continue

            # (1) Exponential decay: C(t) = C(t-1) * exp(-λ)
            old_credence = h.credence
            h.credence *= math.exp(-h.lambda_decay)
            if h.credence != old_credence:
                summary["decayed"].append(h.hypothesis_id)

            # (2) Maintenance cost
            h.credence = max(0.0, h.credence - h.maintenance_cost_rate)
            summary["maintenance_charged"].append(h.hypothesis_id)

            # (3) Auto-abandon if credence below epsilon for W ticks
            ticks_since_reinforcement = self.tick_count - h.last_reinforced_at
            if h.credence < self.config.epsilon and ticks_since_reinforcement >= self.config.W:
                h.state = HypothesisState.ABANDONED
                summary["auto_abandoned"].append(h.hypothesis_id)

            # (4) Auto-archive abandoned
            if h.state == HypothesisState.ABANDONED and not h.archived:
                h.archived = True
                summary["auto_archived"].append(h.hypothesis_id)

        return summary

    # =========================================================================
    # Monitors (delegation)
    # =========================================================================

    def check_entropy(self) -> EntropyCheckResult:
        """Check entropy bounds on current hypothesis set."""
        return self.entropy_monitor.check(list(self.hypotheses.values()))

    def check_dominance(self) -> DominanceCheckResult:
        """Check dominance cap on current hypothesis set."""
        return self.dominance_monitor.check(list(self.hypotheses.values()))

    def check_delta_t(self) -> DeltaTCheckResult:
        """Check Δt invariant."""
        return self.timescale_monitor.check()

    # =========================================================================
    # Terminal State
    # =========================================================================

    def assess_terminal(self) -> TerminalState | None:
        """
        Assess whether the research has reached a terminal state.

        Returns None if research should continue.
        """
        active = self.active_hypotheses()

        # No active hypotheses = insufficient evidence
        if not active:
            abandoned = self.abandoned_hypotheses()
            if abandoned:
                return TerminalState(
                    terminal_type=TerminalStateType.INSUFFICIENT_EVIDENCE,
                    reason="All hypotheses abandoned",
                    live_hypotheses=[],
                    missing_evidence_types=["any supporting evidence"],
                )
            return None

        # Multiple live hypotheses with no dominant one
        dom = self.dominance_monitor.compute_dominance(list(self.hypotheses.values()))
        if len(active) >= 2:
            max_d = max(dom.values()) if dom else 0.0
            if max_d < self.config.D_max:
                # Multiple live, no dominant → valid terminal state
                competitors = [h.hypothesis_id for h in active]
                return TerminalState(
                    terminal_type=TerminalStateType.MULTIPLE_LIVE_HYPOTHESES,
                    reason="Multiple hypotheses survive without dominance",
                    live_hypotheses=competitors,
                    competing_hypothesis_ids=competitors,
                )

        return None

    # =========================================================================
    # Queries
    # =========================================================================

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        """Get a hypothesis by ID."""
        return self.hypotheses.get(hypothesis_id)

    def active_hypotheses(self) -> list[Hypothesis]:
        """Get all active (non-archived, non-abandoned) hypotheses."""
        return [h for h in self.hypotheses.values() if h.is_active]

    def archived_hypotheses(self) -> list[Hypothesis]:
        """Get all archived hypotheses."""
        return [h for h in self.hypotheses.values() if h.archived]

    def abandoned_hypotheses(self) -> list[Hypothesis]:
        """Get all abandoned hypotheses."""
        return [
            h for h in self.hypotheses.values()
            if h.state == HypothesisState.ABANDONED
        ]

    def hypotheses_by_state(self) -> dict[str, list[Hypothesis]]:
        """Group hypotheses by state."""
        result: dict[str, list[Hypothesis]] = {}
        for s in HypothesisState:
            result[s.value] = [
                h for h in self.hypotheses.values() if h.state == s
            ]
        return result

    def competitors_of(self, hypothesis_id: str) -> list[Hypothesis]:
        """Get competitors of a hypothesis."""
        h = self.hypotheses.get(hypothesis_id)
        if h is None:
            return []
        return [
            self.hypotheses[cid]
            for cid in h.competitors
            if cid in self.hypotheses
        ]

    def lineage(self, hypothesis_id: str) -> list[Hypothesis]:
        """Get lineage (ancestors) of a hypothesis."""
        result: list[Hypothesis] = []
        current = self.hypotheses.get(hypothesis_id)
        visited: set[str] = set()
        while current and current.parent_id and current.parent_id not in visited:
            visited.add(current.hypothesis_id)
            parent = self.hypotheses.get(current.parent_id)
            if parent:
                result.append(parent)
            current = parent
        return result

    def dominant_hypothesis(self) -> Hypothesis | None:
        """Get the hypothesis with highest credence."""
        active = self.active_hypotheses()
        if not active:
            return None
        return max(active, key=lambda h: h.credence)

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> dict[str, Any]:
        """Get ledger statistics."""
        active = self.active_hypotheses()
        dom = self.dominance_monitor.compute_dominance(list(self.hypotheses.values()))
        entropy = self.entropy_monitor.compute_entropy(list(self.hypotheses.values()))

        return {
            "tick": self.tick_count,
            "total_hypotheses": len(self.hypotheses),
            "active_count": len(active),
            "abandoned_count": len(self.abandoned_hypotheses()),
            "archived_count": len(self.archived_hypotheses()),
            "entropy": entropy,
            "max_dominance": max(dom.values()) if dom else 0.0,
            "dominant_hypothesis": max(dom, key=dom.get) if dom else None,
            "delta_t": self.timescale_monitor.check().to_dict(),
            "by_state": {
                s.value: len(hs) for s, hs in
                [(HypothesisState(sv), hsl) for sv, hsl in self.hypotheses_by_state().items()]
            },
        }

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "tick_count": self.tick_count,
            "hypotheses": {
                hid: h.to_dict() for hid, h in self.hypotheses.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        epistemic_ledger: Any | None = None,
        ttl_manager: Any | None = None,
        independence_scorer: Any | None = None,
    ) -> "ResearchLedger":
        config = ResearchConfig.from_dict(data["config"])
        ledger = cls(
            config=config,
            epistemic_ledger=epistemic_ledger,
            ttl_manager=ttl_manager,
            independence_scorer=independence_scorer,
        )
        ledger.tick_count = data.get("tick_count", 0)
        for hid, hdata in data.get("hypotheses", {}).items():
            ledger.hypotheses[hid] = Hypothesis.from_dict(hdata)
        return ledger


# =============================================================================
# Convenience
# =============================================================================


def create_research_ledger(
    config: ResearchConfig | None = None,
    epistemic_ledger: Any | None = None,
    ttl_manager: Any | None = None,
    independence_scorer: Any | None = None,
) -> ResearchLedger:
    """Create a ResearchLedger with optional dependencies."""
    return ResearchLedger(config, epistemic_ledger, ttl_manager, independence_scorer)


def create_research_config(
    strict: bool = False,
    permissive: bool = False,
) -> ResearchConfig:
    """Create a ResearchConfig with preset defaults."""
    if strict:
        return ResearchConfig(
            default_lambda=0.08,
            H_min=0.8,
            H_max=2.5,
            D_max=0.5,
            k_timescale=2.0,
            epsilon=0.1,
            W=5,
            max_active=10,
            K_independent=3,
            maintenance_cost_rate=0.02,
        )
    if permissive:
        return ResearchConfig(
            default_lambda=0.02,
            H_min=0.2,
            H_max=4.0,
            D_max=0.9,
            k_timescale=1.0,
            epsilon=0.02,
            W=20,
            max_active=50,
            K_independent=1,
            maintenance_cost_rate=0.005,
        )
    return ResearchConfig()
