"""
Sybil resistance: bloc detection, effective voter count (Neff), per-origin budget coupling.

Extends independence scoring with structural Sybil defenses. Identity is cheap
and adversarial; influence must be bounded by conserved resources.

Key invariants:
1. Weight is a function of independence evidence, not identity count
2. Correlated agents collapse into blocs; quorum uses Neff, not N
3. Per-origin budgets prevent identity-reset attacks
4. Escalation triggers when Neff collapses below threshold
5. ProvenanceVector is a superset of MethodSignature (backward compat)

Control-theory framing:
- Sybils are gain hacking: attacker multiplies influence via fake identities
- Conservation law: total influence bounded by scarce resource
- Bloc detection: cluster agents by common-mode similarity
- Neff: effective voter count after discounting correlated blocs
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from .independence import MethodSignature


# =============================================================================
# Enums
# =============================================================================


class SybilEventType(str, Enum):
    """Types of sybil-related events."""

    BLOC_DETECTED = "bloc_detected"
    """A correlated agent cluster was identified."""

    NEFF_COLLAPSE = "neff_collapse"
    """Effective voter count dropped below threshold."""

    BUDGET_EXHAUSTED = "budget_exhausted"
    """An origin exceeded its vote budget for the current window."""

    ESCALATION_TRIGGERED = "escalation_triggered"
    """Neff too low; requires external verification."""

    BLOC_DISSOLVED = "bloc_dissolved"
    """A previously detected bloc is no longer correlated."""


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class ProvenanceVector:
    """
    Extended method signature for sybil detection.

    Superset of MethodSignature with additional features for detecting
    correlated agents: provider identity, response timing, error patterns.
    """

    agent_id: str
    tool_path_hash: str
    sources_hash: str
    prompt_hash: str
    model_tier: str = "standard"
    source_urls: frozenset[str] = frozenset()
    provider_id: str | None = None
    response_time_ms: float | None = None
    error_hash: str | None = None

    @property
    def feature_set(self) -> frozenset[str]:
        """Feature set for extended Jaccard similarity."""
        features = {
            f"tool:{self.tool_path_hash}",
            f"sources:{self.sources_hash}",
            f"prompt:{self.prompt_hash}",
            f"tier:{self.model_tier}",
        }
        if self.provider_id is not None:
            features.add(f"provider:{self.provider_id}")
        if self.error_hash is not None:
            features.add(f"error:{self.error_hash}")
        return frozenset(features)

    def to_method_signature(self) -> MethodSignature:
        """Convert to base MethodSignature for backward compatibility."""
        return MethodSignature(
            agent_id=self.agent_id,
            tool_path_hash=self.tool_path_hash,
            sources_hash=self.sources_hash,
            prompt_hash=self.prompt_hash,
            model_tier=self.model_tier,
            source_urls=self.source_urls,
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "agent_id": self.agent_id,
            "tool_path_hash": self.tool_path_hash,
            "sources_hash": self.sources_hash,
            "prompt_hash": self.prompt_hash,
            "model_tier": self.model_tier,
            "source_urls": sorted(self.source_urls),
        }
        if self.provider_id is not None:
            d["provider_id"] = self.provider_id
        if self.response_time_ms is not None:
            d["response_time_ms"] = self.response_time_ms
        if self.error_hash is not None:
            d["error_hash"] = self.error_hash
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceVector":
        return cls(
            agent_id=data["agent_id"],
            tool_path_hash=data["tool_path_hash"],
            sources_hash=data["sources_hash"],
            prompt_hash=data["prompt_hash"],
            model_tier=data.get("model_tier", "standard"),
            source_urls=frozenset(data.get("source_urls", [])),
            provider_id=data.get("provider_id"),
            response_time_ms=data.get("response_time_ms"),
            error_hash=data.get("error_hash"),
        )

    @classmethod
    def from_vote(cls, vote: Any) -> "ProvenanceVector | None":
        """
        Create a ProvenanceVector from a Vote object.

        Returns None if the vote lacks the required hash fields.
        """
        if (vote.tool_path_hash is None
                or vote.sources_hash is None
                or vote.prompt_hash is None):
            return None
        return cls(
            agent_id=vote.agent_id,
            tool_path_hash=vote.tool_path_hash,
            sources_hash=vote.sources_hash,
            prompt_hash=vote.prompt_hash,
            model_tier=getattr(vote, "model_id", None) or "standard",
            source_urls=frozenset(getattr(vote, "source_urls", frozenset())),
            provider_id=getattr(vote, "provider_id", None),
            response_time_ms=getattr(vote, "response_time_ms", None),
            error_hash=getattr(vote, "error_hash", None),
        )


@dataclass
class Bloc:
    """A cluster of correlated agents detected by similarity analysis."""

    bloc_id: str
    member_agent_ids: list[str]
    max_internal_similarity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "bloc_id": self.bloc_id,
            "member_agent_ids": self.member_agent_ids,
            "max_internal_similarity": self.max_internal_similarity,
        }


@dataclass
class NeffResult:
    """Result of effective voter count computation."""

    neff: float
    total_agents: int
    blocs: list[Bloc]
    singleton_count: int
    reduction_ratio: float
    passes_threshold: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "neff": self.neff,
            "total_agents": self.total_agents,
            "blocs": [b.to_dict() for b in self.blocs],
            "singleton_count": self.singleton_count,
            "reduction_ratio": self.reduction_ratio,
            "passes_threshold": self.passes_threshold,
        }


@dataclass
class OriginBudget:
    """Per-origin rate limit for vote casting."""

    origin_id: str
    max_votes_per_window: int
    votes_cast: int = 0
    window_start: datetime = field(default_factory=datetime.now)
    window_duration: timedelta = field(default_factory=lambda: timedelta(hours=1))

    @property
    def votes_remaining(self) -> int:
        return max(0, self.max_votes_per_window - self.votes_cast)

    @property
    def is_exhausted(self) -> bool:
        return self.votes_cast >= self.max_votes_per_window

    def is_window_expired(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        return (now - self.window_start) >= self.window_duration

    def reset_window(self, now: datetime | None = None) -> None:
        now = now or datetime.now()
        self.window_start = now
        self.votes_cast = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin_id": self.origin_id,
            "max_votes_per_window": self.max_votes_per_window,
            "votes_cast": self.votes_cast,
            "window_start": self.window_start.isoformat(),
            "window_duration_seconds": self.window_duration.total_seconds(),
        }


@dataclass
class SybilEvent:
    """Audit log entry for sybil-related events."""

    event_type: SybilEventType
    proposal_id: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "proposal_id": self.proposal_id,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SybilConfig:
    """Configuration for sybil detection."""

    bloc_similarity_threshold: float = 0.75
    min_independent_blocs: int = 2
    neff_escalation_threshold: float = 1.0
    default_votes_per_window: int = 10
    budget_window_hours: float = 1.0
    timing_similarity_ms: float = 100.0
    error_hash_weight: float = 1.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "bloc_similarity_threshold": self.bloc_similarity_threshold,
            "min_independent_blocs": self.min_independent_blocs,
            "neff_escalation_threshold": self.neff_escalation_threshold,
            "default_votes_per_window": self.default_votes_per_window,
            "budget_window_hours": self.budget_window_hours,
            "timing_similarity_ms": self.timing_similarity_ms,
            "error_hash_weight": self.error_hash_weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SybilConfig":
        return cls(
            bloc_similarity_threshold=data.get("bloc_similarity_threshold", 0.75),
            min_independent_blocs=data.get("min_independent_blocs", 2),
            neff_escalation_threshold=data.get("neff_escalation_threshold", 1.0),
            default_votes_per_window=data.get("default_votes_per_window", 10),
            budget_window_hours=data.get("budget_window_hours", 1.0),
            timing_similarity_ms=data.get("timing_similarity_ms", 100.0),
            error_hash_weight=data.get("error_hash_weight", 1.5),
        )


# =============================================================================
# Bloc Detector
# =============================================================================


class BlocDetector:
    """
    Detects correlated agent clusters (blocs) via provenance similarity.

    Uses extended Jaccard with timing and error-hash bonuses to identify
    agents that are likely controlled by the same operator or pipeline.
    """

    def __init__(self, config: SybilConfig | None = None):
        self.config = config or SybilConfig()

    def compute_similarity(self, a: ProvenanceVector, b: ProvenanceVector) -> float:
        """
        Compute extended similarity between two provenance vectors.

        Base: Jaccard over feature sets.
        Bonus: timing similarity and shared error patterns.
        """
        feat_a = a.feature_set
        feat_b = b.feature_set
        union = feat_a | feat_b
        if not union:
            return 0.0

        base_jaccard = len(feat_a & feat_b) / len(union)

        # Timing similarity bonus
        timing_bonus = 0.0
        if a.response_time_ms is not None and b.response_time_ms is not None:
            diff = abs(a.response_time_ms - b.response_time_ms)
            if diff <= self.config.timing_similarity_ms:
                timing_bonus = 0.1 * (1.0 - diff / self.config.timing_similarity_ms)

        # Error hash bonus (same errors = likely same pipeline)
        error_bonus = 0.0
        if a.error_hash is not None and b.error_hash is not None:
            if a.error_hash == b.error_hash:
                error_bonus = 0.15 * self.config.error_hash_weight

        # Clamp to [0, 1]
        return min(1.0, base_jaccard + timing_bonus + error_bonus)

    def detect_blocs(
        self, vectors: list[ProvenanceVector]
    ) -> list[Bloc]:
        """
        Detect correlated agent blocs via connected-components clustering.

        Two agents are in the same bloc if their similarity exceeds
        the bloc_similarity_threshold. Uses union-find for clustering.
        """
        n = len(vectors)
        if n < 2:
            return []

        # Build adjacency via threshold
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        # Pairwise similarity and union
        sim_matrix: dict[tuple[int, int], float] = {}
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.compute_similarity(vectors[i], vectors[j])
                sim_matrix[(i, j)] = sim
                if sim >= self.config.bloc_similarity_threshold:
                    union(i, j)

        # Collect components with >1 member
        components: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            components.setdefault(root, []).append(i)

        blocs: list[Bloc] = []
        for members in components.values():
            if len(members) < 2:
                continue

            # Compute max internal similarity
            max_sim = 0.0
            for i_idx in range(len(members)):
                for j_idx in range(i_idx + 1, len(members)):
                    pair = (min(members[i_idx], members[j_idx]),
                            max(members[i_idx], members[j_idx]))
                    sim = sim_matrix.get(pair, 0.0)
                    if sim > max_sim:
                        max_sim = sim

            agent_ids = [vectors[m].agent_id for m in members]
            blocs.append(Bloc(
                bloc_id=f"bloc_{uuid.uuid4().hex[:8]}",
                member_agent_ids=agent_ids,
                max_internal_similarity=max_sim,
            ))

        return blocs

    def compute_neff(
        self,
        vectors: list[ProvenanceVector],
        required_k: int = 2,
    ) -> NeffResult:
        """
        Compute effective voter count (Neff).

        Each bloc counts as 1 effective voter regardless of size.
        Singletons each count as 1.
        Neff = number_of_blocs + number_of_singletons.
        """
        if not vectors:
            return NeffResult(
                neff=0.0,
                total_agents=0,
                blocs=[],
                singleton_count=0,
                reduction_ratio=0.0,
                passes_threshold=False,
            )

        blocs = self.detect_blocs(vectors)

        # Find agents in blocs
        agents_in_blocs: set[str] = set()
        for bloc in blocs:
            agents_in_blocs.update(bloc.member_agent_ids)

        singleton_count = sum(
            1 for v in vectors if v.agent_id not in agents_in_blocs
        )

        neff = float(len(blocs) + singleton_count)
        total = len(vectors)
        reduction = 1.0 - (neff / total) if total > 0 else 0.0

        return NeffResult(
            neff=neff,
            total_agents=total,
            blocs=blocs,
            singleton_count=singleton_count,
            reduction_ratio=reduction,
            passes_threshold=neff >= required_k,
        )


# =============================================================================
# Origin Budget Tracker
# =============================================================================


class OriginBudgetTracker:
    """
    Tracks per-origin vote budgets to prevent identity-reset attacks.

    Each origin (API key, operator, host) gets a fixed vote budget
    per time window. Creating new identities doesn't reset the budget.
    """

    def __init__(self, config: SybilConfig | None = None):
        self.config = config or SybilConfig()
        self.budgets: dict[str, OriginBudget] = {}

    def register_origin(self, origin_id: str) -> OriginBudget:
        """Register an origin with default budget."""
        if origin_id not in self.budgets:
            self.budgets[origin_id] = OriginBudget(
                origin_id=origin_id,
                max_votes_per_window=self.config.default_votes_per_window,
                window_duration=timedelta(hours=self.config.budget_window_hours),
            )
        return self.budgets[origin_id]

    def can_vote(
        self, origin_id: str, now: datetime | None = None
    ) -> tuple[bool, str]:
        """
        Check if an origin can cast a vote.

        Returns (can_vote, reason).
        """
        budget = self.budgets.get(origin_id)
        if budget is None:
            return True, "Origin not tracked"

        now = now or datetime.now()

        # Check window expiry
        if budget.is_window_expired(now):
            budget.reset_window(now)

        if budget.is_exhausted:
            return False, f"Budget exhausted: {budget.votes_cast}/{budget.max_votes_per_window}"

        return True, "OK"

    def record_vote(self, origin_id: str, now: datetime | None = None) -> bool:
        """
        Record a vote against an origin's budget.

        Returns True if the vote was accepted, False if budget exhausted.
        """
        budget = self.budgets.get(origin_id)
        if budget is None:
            budget = self.register_origin(origin_id)

        now = now or datetime.now()

        if budget.is_window_expired(now):
            budget.reset_window(now)

        if budget.is_exhausted:
            return False

        budget.votes_cast += 1
        return True

    def get_metrics(self) -> dict[str, Any]:
        """Get budget tracker statistics."""
        return {
            "tracked_origins": len(self.budgets),
            "budgets": {
                oid: b.to_dict() for oid, b in self.budgets.items()
            },
        }


# =============================================================================
# Sybil Detector
# =============================================================================


class SybilDetector:
    """
    Top-level sybil detection that integrates bloc detection,
    Neff computation, and origin budget enforcement.
    """

    def __init__(self, config: SybilConfig | None = None):
        self.config = config or SybilConfig()
        self.bloc_detector = BlocDetector(self.config)
        self.budget_tracker = OriginBudgetTracker(self.config)
        self.events: list[SybilEvent] = []

    def check_votes(
        self,
        votes: list[Any],
        proposal_id: str,
        required_k: int = 2,
    ) -> tuple[bool, NeffResult, list[str]]:
        """
        Check a set of votes for sybil resistance.

        Returns (passes, neff_result, reasons).
        """
        reasons: list[str] = []

        # Extract provenance vectors from votes
        vectors: list[ProvenanceVector] = []
        for v in votes:
            pv = ProvenanceVector.from_vote(v)
            if pv is not None:
                vectors.append(pv)

        if not vectors:
            neff_result = NeffResult(
                neff=0.0,
                total_agents=0,
                blocs=[],
                singleton_count=0,
                reduction_ratio=0.0,
                passes_threshold=False,
            )
            reasons.append("No provenance vectors available for sybil check")
            return False, neff_result, reasons

        # Compute Neff
        neff_result = self.bloc_detector.compute_neff(vectors, required_k)

        if not neff_result.passes_threshold:
            reasons.append(
                f"Neff={neff_result.neff:.1f} below required k={required_k}"
            )
            self._emit(SybilEventType.NEFF_COLLAPSE, proposal_id, {
                "neff": neff_result.neff,
                "required_k": required_k,
                "total_agents": neff_result.total_agents,
            })

        # Log bloc detections
        for bloc in neff_result.blocs:
            self._emit(SybilEventType.BLOC_DETECTED, proposal_id, {
                "bloc_id": bloc.bloc_id,
                "members": bloc.member_agent_ids,
                "max_similarity": bloc.max_internal_similarity,
            })

        # Check escalation
        if self.should_escalate(neff_result):
            reasons.append(
                f"Neff={neff_result.neff:.1f} at or below escalation threshold "
                f"{self.config.neff_escalation_threshold}"
            )
            self._emit(SybilEventType.ESCALATION_TRIGGERED, proposal_id, {
                "neff": neff_result.neff,
                "threshold": self.config.neff_escalation_threshold,
            })

        passes = len(reasons) == 0
        return passes, neff_result, reasons

    def check_origin_budget(
        self, agent_id: str, origin_id: str, now: datetime | None = None
    ) -> tuple[bool, str]:
        """Check if an agent's origin has budget remaining."""
        can, reason = self.budget_tracker.can_vote(origin_id, now)
        if not can:
            self._emit(SybilEventType.BUDGET_EXHAUSTED, "", {
                "agent_id": agent_id,
                "origin_id": origin_id,
                "reason": reason,
            })
        return can, reason

    def record_origin_vote(
        self, origin_id: str, now: datetime | None = None
    ) -> bool:
        """Record a vote against an origin's budget."""
        return self.budget_tracker.record_vote(origin_id, now)

    def should_escalate(self, neff_result: NeffResult) -> bool:
        """Check if Neff collapse requires escalation."""
        return neff_result.neff <= self.config.neff_escalation_threshold

    def get_metrics(self) -> dict[str, Any]:
        """Get sybil detector statistics."""
        return {
            "total_events": len(self.events),
            "events_by_type": {
                et.value: sum(1 for e in self.events if e.event_type == et)
                for et in SybilEventType
            },
            "budget_tracker": self.budget_tracker.get_metrics(),
            "config": self.config.to_dict(),
        }

    def _emit(
        self,
        event_type: SybilEventType,
        proposal_id: str,
        details: dict[str, Any],
    ) -> None:
        """Emit a sybil event."""
        self.events.append(SybilEvent(
            event_type=event_type,
            proposal_id=proposal_id,
            details=details,
        ))


# =============================================================================
# Convenience
# =============================================================================


def create_sybil_detector(config: SybilConfig | None = None) -> SybilDetector:
    """Create a SybilDetector with optional custom config."""
    return SybilDetector(config)


def compute_neff(
    votes: list[Any],
    config: SybilConfig | None = None,
    required_k: int = 2,
) -> NeffResult:
    """Convenience: compute Neff for a list of votes."""
    detector = BlocDetector(config)
    vectors: list[ProvenanceVector] = []
    for v in votes:
        pv = ProvenanceVector.from_vote(v)
        if pv is not None:
            vectors.append(pv)
    return detector.compute_neff(vectors, required_k)
