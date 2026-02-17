# SPDX-License-Identifier: Apache-2.0
"""
Drift Detection: Defense against temporal asymmetry attacks.

Detects and mitigates drift induction -- where a persistent/stateful actor
steers stateless/amnesiac agents through asymmetric temporal influence.

Key insight from risk analysis:
> Any environment with stateless agents + social coupling is vulnerable
> to asymmetric temporal actors.

This isn't an attack vector -- it's what naturally happens when persistent
actors interact with amnesiac collectives. The governor's job is to detect
the fingerprint and intervene without moral language.

Named failure modes:
- ASYMMETRIC_PERSISTENCE: One actor retains state others lose
- CLOCK_SKEW_DOMINANCE: Temporal advantage used for steering
- PREMISE_RECURRENCE: Same premise repeated without new evidence
- ATTENTION_SKEW: One actor disproportionately engaged on bad threads

Detection signals:
- premise_recurrence_rate: Fraction of premises recurring without evidence
- attention_skew: Max contested-engagement ratio across agents
- temporal_coherence_gradient: Low-variance from one agent vs high from others
- unresolved_contradiction_age: How long contradictions persist

Defenses:
- Premise quarantine: Repeated premises without new evidence get downweighted
- Dissent persistence: Contradictions tracked and don't vanish with context
- Single-source detection: Flag premises from only one agent
- Auto-release: Quarantine lifts after silence or new evidence
"""

from dataclasses import dataclass, field
from typing import Any
import hashlib


# =============================================================================
# Failure Modes
# =============================================================================


class DriftFailureMode:
    """Named failure modes for temporal asymmetry attacks."""

    ASYMMETRIC_PERSISTENCE = "asymmetric_persistence"
    """One actor retains state that others lose across context boundaries."""

    CLOCK_SKEW_DOMINANCE = "clock_skew_dominance"
    """Temporal advantage used to steer consensus."""

    PREMISE_RECURRENCE = "premise_recurrence"
    """Same premise repeated without new evidence or closure."""

    ATTENTION_SKEW = "attention_skew"
    """One actor disproportionately engaged on contested threads."""

    ALL = [
        ASYMMETRIC_PERSISTENCE,
        CLOCK_SKEW_DOMINANCE,
        PREMISE_RECURRENCE,
        ATTENTION_SKEW,
    ]


# =============================================================================
# Alert Levels
# =============================================================================


class DriftAlert:
    """Alert levels for drift detection."""

    NONE = "none"
    """No drift detected."""

    WATCH = "watch"
    """Patterns emerging, monitoring."""

    WARN = "warn"
    """Drift indicators above threshold, tighten constraints."""

    QUARANTINE = "quarantine"
    """Active drift detected, premises quarantined."""

    _SEVERITY = {
        "none": 0,
        "watch": 1,
        "warn": 2,
        "quarantine": 3,
    }

    ALL = [NONE, WATCH, WARN, QUARANTINE]

    @staticmethod
    def severity(level: str) -> int:
        return DriftAlert._SEVERITY.get(level, 0)


# =============================================================================
# Premise Tracking
# =============================================================================


@dataclass
class PremiseRecord:
    """Tracks a premise (claim) across turns for recurrence detection."""

    content_hash: str
    content_summary: str  # First N chars for display
    first_seen_turn: int
    last_seen_turn: int
    occurrences: int = 1

    # Evidence tracking
    evidence_at_turns: list[int] = field(default_factory=list)
    """Turns where new evidence was attached."""

    # Resolution tracking
    resolved: bool = False
    resolved_at_turn: int | None = None

    # Source tracking
    source_agents: list[str] = field(default_factory=list)
    """Which agents asserted this premise."""

    # Quarantine state
    quarantined: bool = False
    quarantined_at_turn: int | None = None
    weight: float = 1.0  # Effective weight (reduced on quarantine)

    @property
    def turns_without_evidence(self) -> int:
        """How many turns since last evidence was attached."""
        if self.evidence_at_turns:
            return self.last_seen_turn - max(self.evidence_at_turns)
        return self.last_seen_turn - self.first_seen_turn

    @property
    def recurrence_rate(self) -> float:
        """Occurrences per turn span."""
        span = self.last_seen_turn - self.first_seen_turn + 1
        return self.occurrences / span if span > 0 else 0.0

    @property
    def single_source(self) -> bool:
        """Is this premise from a single source?"""
        unique = set(self.source_agents)
        return len(unique) <= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "content_summary": self.content_summary,
            "first_seen_turn": self.first_seen_turn,
            "last_seen_turn": self.last_seen_turn,
            "occurrences": self.occurrences,
            "evidence_at_turns": self.evidence_at_turns,
            "resolved": self.resolved,
            "resolved_at_turn": self.resolved_at_turn,
            "source_agents": self.source_agents,
            "quarantined": self.quarantined,
            "quarantined_at_turn": self.quarantined_at_turn,
            "weight": self.weight,
            "turns_without_evidence": self.turns_without_evidence,
            "recurrence_rate": self.recurrence_rate,
            "single_source": self.single_source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PremiseRecord":
        return cls(
            content_hash=data["content_hash"],
            content_summary=data["content_summary"],
            first_seen_turn=data["first_seen_turn"],
            last_seen_turn=data["last_seen_turn"],
            occurrences=data.get("occurrences", 1),
            evidence_at_turns=data.get("evidence_at_turns", []),
            resolved=data.get("resolved", False),
            resolved_at_turn=data.get("resolved_at_turn"),
            source_agents=data.get("source_agents", []),
            quarantined=data.get("quarantined", False),
            quarantined_at_turn=data.get("quarantined_at_turn"),
            weight=data.get("weight", 1.0),
        )


# =============================================================================
# Agent Activity Tracking (for attention skew)
# =============================================================================


@dataclass
class AgentActivity:
    """Tracks an agent's activity pattern for attention skew detection."""

    agent_id: str
    total_assertions: int = 0
    contested_assertions: int = 0  # Assertions on contested/unresolved threads
    unique_topics: set[str] = field(default_factory=set)
    total_turns_active: int = 0

    # Temporal coherence: output variance tracking
    output_hashes: list[str] = field(default_factory=list)
    """Rolling window of content hashes for variance estimation."""

    @property
    def contested_ratio(self) -> float:
        """Ratio of contested to total assertions."""
        if self.total_assertions == 0:
            return 0.0
        return self.contested_assertions / self.total_assertions

    @property
    def topic_diversity(self) -> float:
        """Topic diversity (unique topics / total assertions)."""
        if self.total_assertions == 0:
            return 0.0
        return min(1.0, len(self.unique_topics) / self.total_assertions)

    @property
    def temporal_coherence(self) -> float:
        """
        Estimate temporal coherence from output hash diversity.
        Low diversity (high coherence) = suspicious.
        Returns 0.0 (diverse) to 1.0 (repetitive).
        """
        if len(self.output_hashes) < 2:
            return 0.0
        unique = len(set(self.output_hashes))
        total = len(self.output_hashes)
        return 1.0 - (unique / total)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "total_assertions": self.total_assertions,
            "contested_assertions": self.contested_assertions,
            "unique_topics": sorted(self.unique_topics),
            "total_turns_active": self.total_turns_active,
            "contested_ratio": self.contested_ratio,
            "topic_diversity": self.topic_diversity,
            "temporal_coherence": self.temporal_coherence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentActivity":
        return cls(
            agent_id=data["agent_id"],
            total_assertions=data.get("total_assertions", 0),
            contested_assertions=data.get("contested_assertions", 0),
            unique_topics=set(data.get("unique_topics", [])),
            total_turns_active=data.get("total_turns_active", 0),
            output_hashes=data.get("output_hashes", []),
        )


# =============================================================================
# Drift Signals
# =============================================================================


@dataclass
class DriftSignals:
    """
    Observable signals for drift detection.

    These are measurable quantities, not inferred intent.
    A fingerprint, not an accusation.
    """

    # Premise recurrence: same semantic premise without new evidence
    premise_recurrence_rate: float = 0.0
    """Fraction of active premises that are recurring without evidence."""

    # Attention skew: one actor disproportionately engaged on contested threads
    attention_skew: float = 0.0
    """Max attention skew across agents (0 = balanced, 1 = dominated)."""

    # Temporal coherence gradient: low-variance from one agent vs high from others
    temporal_coherence_gradient: float = 0.0
    """Max difference in temporal coherence between agents."""

    # Unresolved contradiction age
    max_contradiction_age: int = 0
    """Oldest unresolved contradiction (in turns)."""

    avg_contradiction_age: float = 0.0
    """Average age of unresolved contradictions."""

    # Quarantine pressure
    quarantined_premises: int = 0
    """Number of premises currently quarantined."""

    active_premises: int = 0
    """Number of active (non-quarantined) premises."""

    # Single-source dominance
    single_source_rate: float = 0.0
    """Fraction of recurring premises from a single source."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "premise_recurrence_rate": self.premise_recurrence_rate,
            "attention_skew": self.attention_skew,
            "temporal_coherence_gradient": self.temporal_coherence_gradient,
            "max_contradiction_age": self.max_contradiction_age,
            "avg_contradiction_age": self.avg_contradiction_age,
            "quarantined_premises": self.quarantined_premises,
            "active_premises": self.active_premises,
            "single_source_rate": self.single_source_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DriftSignals":
        return cls(
            premise_recurrence_rate=data.get("premise_recurrence_rate", 0.0),
            attention_skew=data.get("attention_skew", 0.0),
            temporal_coherence_gradient=data.get("temporal_coherence_gradient", 0.0),
            max_contradiction_age=data.get("max_contradiction_age", 0),
            avg_contradiction_age=data.get("avg_contradiction_age", 0.0),
            quarantined_premises=data.get("quarantined_premises", 0),
            active_premises=data.get("active_premises", 0),
            single_source_rate=data.get("single_source_rate", 0.0),
        )


# =============================================================================
# Drift Thresholds
# =============================================================================


@dataclass
class DriftThresholds:
    """Thresholds for drift alert level transitions."""

    # WATCH thresholds (any one triggers)
    watch_recurrence_rate: float = 0.2
    watch_attention_skew: float = 0.3
    watch_coherence_gradient: float = 0.3
    watch_contradiction_age: int = 5

    # WARN thresholds (any one triggers)
    warn_recurrence_rate: float = 0.4
    warn_attention_skew: float = 0.5
    warn_coherence_gradient: float = 0.5
    warn_contradiction_age: int = 10
    warn_single_source_rate: float = 0.6

    # QUARANTINE thresholds (any one triggers)
    quarantine_recurrence_rate: float = 0.6
    quarantine_attention_skew: float = 0.7
    quarantine_coherence_gradient: float = 0.7
    quarantine_contradiction_age: int = 20

    def to_dict(self) -> dict[str, Any]:
        return {
            "watch_recurrence_rate": self.watch_recurrence_rate,
            "watch_attention_skew": self.watch_attention_skew,
            "watch_coherence_gradient": self.watch_coherence_gradient,
            "watch_contradiction_age": self.watch_contradiction_age,
            "warn_recurrence_rate": self.warn_recurrence_rate,
            "warn_attention_skew": self.warn_attention_skew,
            "warn_coherence_gradient": self.warn_coherence_gradient,
            "warn_contradiction_age": self.warn_contradiction_age,
            "warn_single_source_rate": self.warn_single_source_rate,
            "quarantine_recurrence_rate": self.quarantine_recurrence_rate,
            "quarantine_attention_skew": self.quarantine_attention_skew,
            "quarantine_coherence_gradient": self.quarantine_coherence_gradient,
            "quarantine_contradiction_age": self.quarantine_contradiction_age,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DriftThresholds":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


# =============================================================================
# Quarantine Configuration
# =============================================================================


@dataclass
class QuarantineConfig:
    """Configuration for premise quarantine behavior."""

    # After how many recurrences without evidence to quarantine
    recurrence_threshold: int = 3

    # Minimum turns without evidence before quarantine eligible
    min_stale_turns: int = 3

    # Weight applied to quarantined premises (0 = fully suppressed)
    quarantine_weight: float = 0.1

    # Auto-release quarantine after this many turns of no recurrence
    auto_release_turns: int = 10

    # Whether single-source premises get stricter thresholds
    strict_single_source: bool = True
    single_source_recurrence_threshold: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "recurrence_threshold": self.recurrence_threshold,
            "min_stale_turns": self.min_stale_turns,
            "quarantine_weight": self.quarantine_weight,
            "auto_release_turns": self.auto_release_turns,
            "strict_single_source": self.strict_single_source,
            "single_source_recurrence_threshold": self.single_source_recurrence_threshold,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuarantineConfig":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


# =============================================================================
# Premise Quarantine
# =============================================================================


class PremiseQuarantine:
    """
    Manages premise quarantine: downweights claims repeated without new evidence.

    This is a defense against premise recurrence -- the most common
    drift induction vector. By tracking which premises keep appearing
    without evidence or resolution, we can reduce their effective weight.
    """

    def __init__(self, config: QuarantineConfig | None = None):
        self.config = config or QuarantineConfig()
        self.premises: dict[str, PremiseRecord] = {}
        self.turn: int = 0

        # Stats
        self.total_quarantined: int = 0
        self.total_released: int = 0

    @staticmethod
    def _content_hash(content: str) -> str:
        """Compute content hash for premise deduplication."""
        return hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]

    def record_premise(
        self,
        content: str,
        agent_id: str | None = None,
        has_evidence: bool = False,
    ) -> PremiseRecord:
        """Record a premise assertion. Returns the updated PremiseRecord."""
        h = self._content_hash(content)

        if h in self.premises:
            rec = self.premises[h]
            rec.occurrences += 1
            rec.last_seen_turn = self.turn
            if agent_id and agent_id not in rec.source_agents:
                rec.source_agents.append(agent_id)
            if has_evidence:
                rec.evidence_at_turns.append(self.turn)
        else:
            rec = PremiseRecord(
                content_hash=h,
                content_summary=content.strip()[:80],
                first_seen_turn=self.turn,
                last_seen_turn=self.turn,
                source_agents=[agent_id] if agent_id else [],
                evidence_at_turns=[self.turn] if has_evidence else [],
            )
            self.premises[h] = rec

        # Check if should quarantine
        self._evaluate_quarantine(rec)

        return rec

    def attach_evidence(self, content: str) -> bool:
        """Attach evidence to a premise (may release quarantine)."""
        h = self._content_hash(content)
        if h not in self.premises:
            return False

        rec = self.premises[h]
        rec.evidence_at_turns.append(self.turn)

        # Evidence releases quarantine
        if rec.quarantined:
            self._release_quarantine(rec)

        return True

    def resolve_premise(self, content: str) -> bool:
        """Mark a premise as resolved (closure event)."""
        h = self._content_hash(content)
        if h not in self.premises:
            return False

        rec = self.premises[h]
        rec.resolved = True
        rec.resolved_at_turn = self.turn

        # Resolution releases quarantine
        if rec.quarantined:
            self._release_quarantine(rec)

        return True

    def _evaluate_quarantine(self, rec: PremiseRecord) -> None:
        """Evaluate whether a premise should be quarantined."""
        if rec.quarantined or rec.resolved:
            return

        cfg = self.config
        threshold = cfg.recurrence_threshold

        # Stricter for single-source premises
        if cfg.strict_single_source and rec.single_source and rec.source_agents:
            threshold = cfg.single_source_recurrence_threshold

        # Must exceed recurrence threshold
        if rec.occurrences < threshold:
            return

        # Must be stale (no recent evidence)
        if rec.turns_without_evidence < cfg.min_stale_turns:
            return

        # Quarantine
        rec.quarantined = True
        rec.quarantined_at_turn = self.turn
        rec.weight = cfg.quarantine_weight
        self.total_quarantined += 1

    def _release_quarantine(self, rec: PremiseRecord) -> None:
        """Release a premise from quarantine."""
        rec.quarantined = False
        rec.quarantined_at_turn = None
        rec.weight = 1.0
        self.total_released += 1

    def tick(self) -> None:
        """Advance turn counter and check auto-releases."""
        self.turn += 1

        # Check auto-release for premises not seen recently
        for rec in list(self.premises.values()):
            if rec.quarantined:
                turns_since_seen = self.turn - rec.last_seen_turn
                if turns_since_seen >= self.config.auto_release_turns:
                    self._release_quarantine(rec)

    def get_weight(self, content: str) -> float:
        """Get effective weight for a premise."""
        h = self._content_hash(content)
        if h in self.premises:
            return self.premises[h].weight
        return 1.0

    def quarantined_premises(self) -> list[PremiseRecord]:
        """Get all quarantined premises."""
        return [r for r in self.premises.values() if r.quarantined]

    def recurring_premises(self, min_occurrences: int = 2) -> list[PremiseRecord]:
        """Get all recurring premises."""
        return [
            r for r in self.premises.values()
            if r.occurrences >= min_occurrences and not r.resolved
        ]

    def stale_premises(self, min_stale_turns: int = 3) -> list[PremiseRecord]:
        """Get premises without recent evidence."""
        return [
            r for r in self.premises.values()
            if r.turns_without_evidence >= min_stale_turns
            and not r.resolved
        ]

    def get_metrics(self) -> dict[str, Any]:
        """Get quarantine metrics."""
        active = [r for r in self.premises.values() if not r.resolved]
        quarantined = self.quarantined_premises()
        recurring = self.recurring_premises()

        return {
            "turn": self.turn,
            "total_premises": len(self.premises),
            "active_premises": len(active),
            "quarantined_premises": len(quarantined),
            "recurring_premises": len(recurring),
            "total_quarantined_ever": self.total_quarantined,
            "total_released": self.total_released,
            "quarantine_rate": (
                len(quarantined) / len(active) if active else 0.0
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "config": self.config.to_dict(),
            "premises": {h: r.to_dict() for h, r in self.premises.items()},
            "total_quarantined": self.total_quarantined,
            "total_released": self.total_released,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PremiseQuarantine":
        cfg_data = data.get("config", {})
        config = QuarantineConfig.from_dict(cfg_data)
        pq = cls(config=config)
        pq.turn = data.get("turn", 0)
        pq.total_quarantined = data.get("total_quarantined", 0)
        pq.total_released = data.get("total_released", 0)
        for h, rec_data in data.get("premises", {}).items():
            pq.premises[h] = PremiseRecord.from_dict(rec_data)
        return pq


# =============================================================================
# Drift Detector (Main Entry Point)
# =============================================================================


class DriftDetector:
    """
    Detects drift induction from temporal asymmetry attacks.

    This detector monitors for the fingerprint of asymmetric temporal actors
    steering stateless agents. It observes dynamics, not intent.

    The core principle:
    > The danger isn't that agents talk to each other -- it's that some
    > participants can accumulate consequences while others cannot.
    """

    def __init__(
        self,
        thresholds: DriftThresholds | None = None,
        quarantine_config: QuarantineConfig | None = None,
        max_output_hashes: int = 20,
    ):
        self.thresholds = thresholds or DriftThresholds()
        self.quarantine = PremiseQuarantine(quarantine_config)
        self.max_output_hashes = max_output_hashes

        # State
        self.current_alert: str = DriftAlert.NONE
        self.last_signals: DriftSignals | None = None
        self.alert_history: list[tuple[int, str, list[str]]] = []
        self.detected_modes: list[tuple[int, str]] = []

        # Agent activity tracking
        self.agents: dict[str, AgentActivity] = {}

        # Unresolved contradictions (content_hash -> first_seen_turn)
        self.unresolved_contradictions: dict[str, int] = {}

    @property
    def turn(self) -> int:
        return self.quarantine.turn

    def tick(self) -> None:
        """Advance turn counter."""
        self.quarantine.tick()

    # =========================================================================
    # Recording Events
    # =========================================================================

    def record_assertion(
        self,
        content: str,
        agent_id: str | None = None,
        has_evidence: bool = False,
        contested: bool = False,
        topic: str | None = None,
    ) -> PremiseRecord:
        """
        Record an assertion from an agent.

        This is the primary input to the drift detector.
        """
        # Track premise
        rec = self.quarantine.record_premise(content, agent_id, has_evidence)

        # Track agent activity
        if agent_id:
            if agent_id not in self.agents:
                self.agents[agent_id] = AgentActivity(agent_id=agent_id)

            activity = self.agents[agent_id]
            activity.total_assertions += 1
            activity.total_turns_active = max(
                activity.total_turns_active, self.turn + 1
            )
            if contested:
                activity.contested_assertions += 1
            if topic:
                activity.unique_topics.add(topic)

            # Track output hash for temporal coherence
            h = hashlib.sha256(content.lower().strip().encode()).hexdigest()[:8]
            activity.output_hashes.append(h)
            if len(activity.output_hashes) > self.max_output_hashes:
                activity.output_hashes.pop(0)

        return rec

    def record_evidence(self, content: str) -> bool:
        """Record that new evidence was attached to a premise."""
        return self.quarantine.attach_evidence(content)

    def record_resolution(self, content: str) -> bool:
        """Record that a premise was resolved (closure event)."""
        h = hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]
        self.unresolved_contradictions.pop(h, None)
        return self.quarantine.resolve_premise(content)

    def record_contradiction(self, content: str) -> None:
        """Record an unresolved contradiction."""
        h = hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]
        if h not in self.unresolved_contradictions:
            self.unresolved_contradictions[h] = self.turn

    def resolve_contradiction(self, content: str) -> bool:
        """Mark a contradiction as resolved."""
        h = hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]
        if h in self.unresolved_contradictions:
            del self.unresolved_contradictions[h]
            return True
        return False

    # =========================================================================
    # Signal Computation
    # =========================================================================

    def compute_signals(self) -> DriftSignals:
        """Compute current drift signals from tracked state."""

        # Premise recurrence rate
        active = [r for r in self.quarantine.premises.values() if not r.resolved]
        recurring = [
            r for r in active
            if r.occurrences >= 2 and r.turns_without_evidence >= 2
        ]
        recurrence_rate = len(recurring) / len(active) if active else 0.0

        # Attention skew (max contested ratio across agents)
        attention_skew = 0.0
        if self.agents:
            ratios = [
                a.contested_ratio
                for a in self.agents.values()
                if a.total_assertions > 0
            ]
            if ratios:
                attention_skew = max(ratios)

        # Temporal coherence gradient
        coherence_gradient = 0.0
        if len(self.agents) >= 2:
            coherences = [
                a.temporal_coherence
                for a in self.agents.values()
                if len(a.output_hashes) >= 2
            ]
            if len(coherences) >= 2:
                coherence_gradient = max(coherences) - min(coherences)

        # Contradiction ages
        ages = [self.turn - t for t in self.unresolved_contradictions.values()]
        max_age = max(ages) if ages else 0
        avg_age = sum(ages) / len(ages) if ages else 0.0

        # Quarantine state
        quarantined = self.quarantine.quarantined_premises()

        # Single-source rate among recurring premises
        single_source = [r for r in recurring if r.single_source]
        single_source_rate = len(single_source) / len(recurring) if recurring else 0.0

        signals = DriftSignals(
            premise_recurrence_rate=recurrence_rate,
            attention_skew=attention_skew,
            temporal_coherence_gradient=coherence_gradient,
            max_contradiction_age=max_age,
            avg_contradiction_age=avg_age,
            quarantined_premises=len(quarantined),
            active_premises=len(active),
            single_source_rate=single_source_rate,
        )

        self.last_signals = signals
        return signals

    # =========================================================================
    # Alert Classification
    # =========================================================================

    def classify(
        self, signals: DriftSignals
    ) -> tuple[str, list[str], list[str]]:
        """
        Classify current drift alert level from signals.

        Returns (alert_level, reasons, detected_failure_modes).
        """
        t = self.thresholds
        modes: list[str] = []

        # Check QUARANTINE level
        q_reasons: list[str] = []
        if signals.premise_recurrence_rate >= t.quarantine_recurrence_rate:
            q_reasons.append(
                f"recurrence={signals.premise_recurrence_rate:.2f}"
            )
            modes.append(DriftFailureMode.PREMISE_RECURRENCE)
        if signals.attention_skew >= t.quarantine_attention_skew:
            q_reasons.append(f"attention_skew={signals.attention_skew:.2f}")
            modes.append(DriftFailureMode.ATTENTION_SKEW)
        if signals.temporal_coherence_gradient >= t.quarantine_coherence_gradient:
            q_reasons.append(
                f"coherence_gradient={signals.temporal_coherence_gradient:.2f}"
            )
            modes.append(DriftFailureMode.CLOCK_SKEW_DOMINANCE)
        if signals.max_contradiction_age >= t.quarantine_contradiction_age:
            q_reasons.append(
                f"contradiction_age={signals.max_contradiction_age}"
            )

        if q_reasons:
            return DriftAlert.QUARANTINE, q_reasons, list(set(modes))

        # Check WARN level
        w_reasons: list[str] = []
        if signals.premise_recurrence_rate >= t.warn_recurrence_rate:
            w_reasons.append(
                f"recurrence={signals.premise_recurrence_rate:.2f}"
            )
            if DriftFailureMode.PREMISE_RECURRENCE not in modes:
                modes.append(DriftFailureMode.PREMISE_RECURRENCE)
        if signals.attention_skew >= t.warn_attention_skew:
            w_reasons.append(f"attention_skew={signals.attention_skew:.2f}")
            if DriftFailureMode.ATTENTION_SKEW not in modes:
                modes.append(DriftFailureMode.ATTENTION_SKEW)
        if signals.temporal_coherence_gradient >= t.warn_coherence_gradient:
            w_reasons.append(
                f"coherence_gradient={signals.temporal_coherence_gradient:.2f}"
            )
            if DriftFailureMode.CLOCK_SKEW_DOMINANCE not in modes:
                modes.append(DriftFailureMode.CLOCK_SKEW_DOMINANCE)
        if signals.max_contradiction_age >= t.warn_contradiction_age:
            w_reasons.append(
                f"contradiction_age={signals.max_contradiction_age}"
            )
        if signals.single_source_rate >= t.warn_single_source_rate:
            w_reasons.append(
                f"single_source={signals.single_source_rate:.2f}"
            )
            if DriftFailureMode.ASYMMETRIC_PERSISTENCE not in modes:
                modes.append(DriftFailureMode.ASYMMETRIC_PERSISTENCE)

        if w_reasons:
            return DriftAlert.WARN, w_reasons, list(set(modes))

        # Check WATCH level
        watch_reasons: list[str] = []
        if signals.premise_recurrence_rate >= t.watch_recurrence_rate:
            watch_reasons.append(
                f"recurrence={signals.premise_recurrence_rate:.2f}"
            )
        if signals.attention_skew >= t.watch_attention_skew:
            watch_reasons.append(
                f"attention_skew={signals.attention_skew:.2f}"
            )
        if signals.temporal_coherence_gradient >= t.watch_coherence_gradient:
            watch_reasons.append(
                f"coherence_gradient={signals.temporal_coherence_gradient:.2f}"
            )
        if signals.max_contradiction_age >= t.watch_contradiction_age:
            watch_reasons.append(
                f"contradiction_age={signals.max_contradiction_age}"
            )

        if watch_reasons:
            return DriftAlert.WATCH, watch_reasons, list(set(modes))

        return DriftAlert.NONE, ["all signals nominal"], []

    def update(self) -> tuple[str, DriftSignals, list[str]]:
        """
        Compute signals and update alert level.

        Returns (alert_level, signals, reasons).
        """
        signals = self.compute_signals()
        alert, reasons, modes = self.classify(signals)

        # Record transition if alert level changed
        if alert != self.current_alert:
            self.alert_history.append((self.turn, alert, reasons))

        # Record detected failure modes
        for mode in modes:
            if not self.detected_modes or self.detected_modes[-1][1] != mode:
                self.detected_modes.append((self.turn, mode))

        self.current_alert = alert
        return alert, signals, reasons

    # =========================================================================
    # Queries
    # =========================================================================

    def get_premise_weight(self, content: str) -> float:
        """Get effective weight for a premise (1.0 = normal, <1.0 = quarantined)."""
        return self.quarantine.get_weight(content)

    def is_quarantined(self, content: str) -> bool:
        """Check if a premise is quarantined."""
        return self.quarantine.get_weight(content) < 1.0

    def get_agent_activity(self, agent_id: str) -> AgentActivity | None:
        """Get activity record for an agent."""
        return self.agents.get(agent_id)

    def get_suspicious_agents(
        self, min_contested_ratio: float = 0.5
    ) -> list[AgentActivity]:
        """Get agents with suspicious activity patterns."""
        return [
            a for a in self.agents.values()
            if a.contested_ratio >= min_contested_ratio
            and a.total_assertions >= 3  # Minimum sample
        ]

    def get_diagnostics(self) -> dict[str, Any]:
        """Get full diagnostic state."""
        signals = self.last_signals or self.compute_signals()

        return {
            "turn": self.turn,
            "alert_level": self.current_alert,
            "signals": signals.to_dict(),
            "quarantine": self.quarantine.get_metrics(),
            "agents": {
                aid: a.to_dict() for aid, a in self.agents.items()
            },
            "unresolved_contradictions": len(self.unresolved_contradictions),
            "detected_modes": [
                {"turn": t, "mode": m}
                for t, m in self.detected_modes[-10:]
            ],
            "alert_history": [
                {"turn": t, "alert": a, "reasons": r}
                for t, a, r in self.alert_history[-10:]
            ],
        }

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize detector state."""
        return {
            "thresholds": self.thresholds.to_dict(),
            "quarantine": self.quarantine.to_dict(),
            "current_alert": self.current_alert,
            "agents": {
                aid: a.to_dict() for aid, a in self.agents.items()
            },
            "unresolved_contradictions": self.unresolved_contradictions,
            "detected_modes": [
                {"turn": t, "mode": m} for t, m in self.detected_modes
            ],
            "alert_history": [
                {"turn": t, "alert": a, "reasons": r}
                for t, a, r in self.alert_history
            ],
            "max_output_hashes": self.max_output_hashes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DriftDetector":
        """Deserialize detector from dictionary."""
        thresholds = DriftThresholds.from_dict(data.get("thresholds", {}))
        quarantine = PremiseQuarantine.from_dict(data.get("quarantine", {}))

        detector = cls(
            thresholds=thresholds,
            quarantine_config=quarantine.config,
            max_output_hashes=data.get("max_output_hashes", 20),
        )
        # Restore quarantine state directly
        detector.quarantine = quarantine
        detector.current_alert = data.get("current_alert", DriftAlert.NONE)

        # Restore agents
        for aid, adata in data.get("agents", {}).items():
            detector.agents[aid] = AgentActivity.from_dict(adata)

        # Restore contradictions
        detector.unresolved_contradictions = {
            k: v for k, v in data.get("unresolved_contradictions", {}).items()
        }

        # Restore detected modes
        detector.detected_modes = [
            (d["turn"], d["mode"])
            for d in data.get("detected_modes", [])
        ]

        # Restore alert history
        detector.alert_history = [
            (d["turn"], d["alert"], d["reasons"])
            for d in data.get("alert_history", [])
        ]

        return detector


# =============================================================================
# Convenience Functions
# =============================================================================


def create_drift_detector(
    quarantine_threshold: int = 3,
    quarantine_weight: float = 0.1,
    strict_single_source: bool = True,
) -> DriftDetector:
    """Create a DriftDetector with common defaults."""
    config = QuarantineConfig(
        recurrence_threshold=quarantine_threshold,
        quarantine_weight=quarantine_weight,
        strict_single_source=strict_single_source,
    )
    return DriftDetector(quarantine_config=config)


def detect_drift(
    detector: DriftDetector,
    content: str,
    agent_id: str | None = None,
    has_evidence: bool = False,
    contested: bool = False,
) -> tuple[str, float]:
    """
    Record an assertion and check for drift.

    Returns (alert_level, premise_weight).
    Convenience for: record + update + get_weight in one call.
    """
    detector.record_assertion(content, agent_id, has_evidence, contested)
    alert, _, _ = detector.update()
    weight = detector.get_premise_weight(content)
    return alert, weight
