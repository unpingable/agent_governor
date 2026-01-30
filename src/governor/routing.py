"""
Multi-agent routing and task sizing.

Routes tasks to appropriate model tiers based on complexity estimation.
Tracks outcomes for adaptive routing.

Tiers:
- local: Fast, cheap, limited capability (qwen, ollama, codellama)
- fast: Quick cloud model (haiku)
- standard: Default capable model (sonnet)
- heavy: Most capable, expensive (opus)
"""

import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from .claims import Claim, ClaimType


# =============================================================================
# Model Tiers
# =============================================================================

class ModelTier(Enum):
    """Model capability tiers, ordered by capability/cost."""
    LOCAL = "local"      # Local models: qwen, ollama, codellama
    FAST = "fast"        # Quick cloud: haiku
    STANDARD = "standard"  # Default: sonnet
    HEAVY = "heavy"      # Most capable: opus

    @property
    def capability_level(self) -> int:
        """Numeric capability level (higher = more capable)."""
        return {
            ModelTier.LOCAL: 1,
            ModelTier.FAST: 2,
            ModelTier.STANDARD: 3,
            ModelTier.HEAVY: 4,
        }[self]

    @property
    def cost_multiplier(self) -> float:
        """Relative cost (LOCAL = 1.0 baseline)."""
        return {
            ModelTier.LOCAL: 0.0,      # Free (local)
            ModelTier.FAST: 1.0,       # Cheap
            ModelTier.STANDARD: 10.0,  # Medium
            ModelTier.HEAVY: 50.0,     # Expensive
        }[self]


# =============================================================================
# Task Complexity
# =============================================================================

@dataclass
class ComplexityEstimate:
    """Estimated complexity of a task."""
    score: float  # 0.0 = trivial, 1.0 = very complex
    factors: dict[str, float] = field(default_factory=dict)
    recommended_tier: ModelTier = ModelTier.STANDARD
    reasoning: str = ""

    @property
    def is_simple(self) -> bool:
        """Task is simple enough for local model."""
        return self.score < 0.3

    @property
    def is_moderate(self) -> bool:
        """Task is moderate complexity."""
        return 0.3 <= self.score < 0.6

    @property
    def is_complex(self) -> bool:
        """Task requires significant capability."""
        return self.score >= 0.6


class ComplexityEstimator:
    """
    Estimates task complexity from claims and context.

    Factors considered:
    - Claim type complexity
    - Scope breadth (files touched)
    - Token/character count
    - Historical performance
    """

    # Claim type base complexity scores
    CLAIM_COMPLEXITY = {
        ClaimType.FILE_EXISTS: 0.1,
        ClaimType.SYMBOL_DEFINED: 0.2,
        ClaimType.API_SURFACE: 0.3,
        ClaimType.TESTS_PASS: 0.4,
        ClaimType.DECISION: 0.6,
        ClaimType.CHANGESET: 0.7,
        ClaimType.WORK_RESERVATION: 0.2,
        ClaimType.INTENT: 0.1,
    }

    def __init__(
        self,
        history: "TaskHistory | None" = None,
        file_complexity_patterns: dict[str, float] | None = None,
    ):
        """
        Initialize the estimator.

        Args:
            history: Task history for learning from past outcomes
            file_complexity_patterns: Regex patterns for file complexity
                e.g., {".*test.*": 0.3, ".*migration.*": 0.8}
        """
        self.history = history
        self.file_patterns = file_complexity_patterns or {
            r".*test.*\.py$": 0.3,       # Tests are simpler
            r".*migration.*": 0.7,        # Migrations are tricky
            r".*config.*": 0.4,           # Config changes
            r".*__init__.*": 0.2,         # Init files are simple
            r".*\.md$": 0.2,              # Markdown is simple
        }

    def estimate(
        self,
        claims: list[Claim],
        description: str = "",
        files: list[str] | None = None,
    ) -> ComplexityEstimate:
        """
        Estimate complexity of a task.

        Args:
            claims: Claims being made
            description: Task description text
            files: Files involved

        Returns:
            ComplexityEstimate with score and recommended tier
        """
        factors: dict[str, float] = {}

        # Factor 1: Claim type complexity
        if claims:
            claim_scores = [
                self.CLAIM_COMPLEXITY.get(c.type, 0.5) for c in claims
            ]
            factors["claim_types"] = max(claim_scores)  # Hardest claim dominates
        else:
            factors["claim_types"] = 0.3  # Unknown

        # Factor 2: File count (scope breadth)
        all_files = files or []
        for claim in claims:
            if claim.paths:
                all_files.extend(claim.paths)
        all_files = list(set(all_files))

        if len(all_files) == 0:
            factors["file_count"] = 0.2
        elif len(all_files) == 1:
            factors["file_count"] = 0.3
        elif len(all_files) <= 3:
            factors["file_count"] = 0.5
        elif len(all_files) <= 10:
            factors["file_count"] = 0.7
        else:
            factors["file_count"] = 0.9

        # Factor 3: File type complexity
        if all_files:
            file_scores = []
            for f in all_files:
                for pattern, score in self.file_patterns.items():
                    if re.search(pattern, f, re.IGNORECASE):
                        file_scores.append(score)
                        break
                else:
                    file_scores.append(0.5)  # Default
            factors["file_types"] = statistics.mean(file_scores)
        else:
            factors["file_types"] = 0.5

        # Factor 4: Description complexity (crude token estimate)
        if description:
            word_count = len(description.split())
            if word_count < 20:
                factors["description"] = 0.2  # Very simple
            elif word_count < 50:
                factors["description"] = 0.4
            elif word_count < 100:
                factors["description"] = 0.6
            else:
                factors["description"] = 0.8  # Complex task
        else:
            factors["description"] = 0.3

        # Factor 5: Historical performance (if available)
        if self.history:
            similar_tasks = self.history.find_similar(claims, all_files)
            if similar_tasks:
                # Use historical success rates to adjust
                success_rate = sum(1 for t in similar_tasks if t.success) / len(similar_tasks)
                # Low success rate = harder task
                factors["historical"] = 1.0 - success_rate
            else:
                factors["historical"] = 0.5
        else:
            factors["historical"] = 0.5

        # Weighted combination
        weights = {
            "claim_types": 0.3,
            "file_count": 0.25,
            "file_types": 0.15,
            "description": 0.15,
            "historical": 0.15,
        }

        score = sum(factors[k] * weights[k] for k in factors)
        score = max(0.0, min(1.0, score))  # Clamp to [0, 1]

        # Determine recommended tier
        if score < 0.25:
            tier = ModelTier.LOCAL
            reasoning = "Simple task suitable for local model"
        elif score < 0.45:
            tier = ModelTier.FAST
            reasoning = "Moderate task suitable for fast model"
        elif score < 0.7:
            tier = ModelTier.STANDARD
            reasoning = "Complex task requiring standard model"
        else:
            tier = ModelTier.HEAVY
            reasoning = "Very complex task requiring heavy model"

        return ComplexityEstimate(
            score=score,
            factors=factors,
            recommended_tier=tier,
            reasoning=reasoning,
        )


# =============================================================================
# Model Registry
# =============================================================================

@dataclass
class ModelCapabilities:
    """Capabilities of a specific model."""
    name: str
    tier: ModelTier
    context_window: int = 8192
    supports_tools: bool = True
    supports_vision: bool = False
    code_quality: float = 0.5  # 0-1, estimated code generation quality
    speed_factor: float = 1.0  # Relative speed (higher = faster)


@dataclass
class ModelStatus:
    """Runtime status of a model."""
    model_name: str
    available: bool = True
    tasks_in_flight: int = 0
    last_success: datetime | None = None
    last_failure: datetime | None = None
    success_rate: float = 1.0  # Recent success rate
    avg_latency_ms: float = 0.0


class ModelRegistry:
    """
    Registry of available models and their status.

    Tracks:
    - Model capabilities (static)
    - Model availability (dynamic)
    - Current load
    - Success rates
    """

    def __init__(self):
        self._models: dict[str, ModelCapabilities] = {}
        self._status: dict[str, ModelStatus] = {}
        self._tier_models: dict[ModelTier, list[str]] = {
            tier: [] for tier in ModelTier
        }

        # Register default models
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default model configurations."""
        defaults = [
            # Local models
            ModelCapabilities(
                name="qwen2.5-coder:7b",
                tier=ModelTier.LOCAL,
                context_window=32768,
                code_quality=0.6,
                speed_factor=2.0,
            ),
            ModelCapabilities(
                name="ollama/codellama",
                tier=ModelTier.LOCAL,
                context_window=16384,
                code_quality=0.5,
                speed_factor=1.5,
            ),
            # Fast cloud
            ModelCapabilities(
                name="claude-3-haiku",
                tier=ModelTier.FAST,
                context_window=200000,
                code_quality=0.7,
                speed_factor=3.0,
            ),
            ModelCapabilities(
                name="claude-3-5-haiku",
                tier=ModelTier.FAST,
                context_window=200000,
                code_quality=0.75,
                speed_factor=2.5,
            ),
            # Standard
            ModelCapabilities(
                name="claude-sonnet-4",
                tier=ModelTier.STANDARD,
                context_window=200000,
                supports_vision=True,
                code_quality=0.9,
                speed_factor=1.5,
            ),
            # Heavy
            ModelCapabilities(
                name="claude-opus-4",
                tier=ModelTier.HEAVY,
                context_window=200000,
                supports_vision=True,
                code_quality=0.95,
                speed_factor=1.0,
            ),
        ]

        for model in defaults:
            self.register(model)

    def register(self, capabilities: ModelCapabilities) -> None:
        """Register a model."""
        self._models[capabilities.name] = capabilities
        self._status[capabilities.name] = ModelStatus(model_name=capabilities.name)
        if capabilities.name not in self._tier_models[capabilities.tier]:
            self._tier_models[capabilities.tier].append(capabilities.name)

    def unregister(self, model_name: str) -> None:
        """Unregister a model."""
        if model_name in self._models:
            tier = self._models[model_name].tier
            self._tier_models[tier].remove(model_name)
            del self._models[model_name]
            del self._status[model_name]

    def get_capabilities(self, model_name: str) -> ModelCapabilities | None:
        """Get model capabilities."""
        return self._models.get(model_name)

    def get_status(self, model_name: str) -> ModelStatus | None:
        """Get model status."""
        return self._status.get(model_name)

    def get_models_for_tier(self, tier: ModelTier) -> list[str]:
        """Get all models in a tier."""
        return self._tier_models.get(tier, [])

    def get_available_models(self, tier: ModelTier | None = None) -> list[str]:
        """Get available models, optionally filtered by tier."""
        available = []
        for name, status in self._status.items():
            if status.available:
                if tier is None or self._models[name].tier == tier:
                    available.append(name)
        return available

    def mark_available(self, model_name: str, available: bool = True) -> None:
        """Update model availability."""
        if model_name in self._status:
            self._status[model_name].available = available

    def record_task_start(self, model_name: str) -> None:
        """Record that a task started on this model."""
        if model_name in self._status:
            self._status[model_name].tasks_in_flight += 1

    def record_task_complete(
        self,
        model_name: str,
        success: bool,
        latency_ms: float = 0.0,
    ) -> None:
        """Record task completion."""
        if model_name not in self._status:
            return

        status = self._status[model_name]
        status.tasks_in_flight = max(0, status.tasks_in_flight - 1)

        now = datetime.now(timezone.utc)
        if success:
            status.last_success = now
        else:
            status.last_failure = now

        # Update rolling success rate (exponential moving average)
        alpha = 0.1  # Weight for new observation
        status.success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * status.success_rate

        # Update latency (EMA)
        if latency_ms > 0:
            status.avg_latency_ms = alpha * latency_ms + (1 - alpha) * status.avg_latency_ms

    def select_best_for_tier(self, tier: ModelTier) -> str | None:
        """
        Select the best available model for a tier.

        Considers: availability, load, success rate.
        """
        candidates = self.get_available_models(tier)
        if not candidates:
            return None

        # Score each candidate
        def score(name: str) -> float:
            status = self._status[name]
            caps = self._models[name]

            # Penalize high load
            load_penalty = status.tasks_in_flight * 0.1

            # Reward high success rate
            success_bonus = status.success_rate * 0.5

            # Consider code quality
            quality_bonus = caps.code_quality * 0.3

            return success_bonus + quality_bonus - load_penalty

        return max(candidates, key=score)

    def to_dict(self) -> dict[str, Any]:
        """Serialize registry state."""
        return {
            "models": {
                name: {
                    "tier": caps.tier.value,
                    "context_window": caps.context_window,
                    "supports_tools": caps.supports_tools,
                    "supports_vision": caps.supports_vision,
                    "code_quality": caps.code_quality,
                    "speed_factor": caps.speed_factor,
                }
                for name, caps in self._models.items()
            },
            "status": {
                name: {
                    "available": status.available,
                    "tasks_in_flight": status.tasks_in_flight,
                    "success_rate": status.success_rate,
                    "avg_latency_ms": status.avg_latency_ms,
                }
                for name, status in self._status.items()
            },
        }


# =============================================================================
# Task History (for adaptive routing)
# =============================================================================

@dataclass
class TaskRecord:
    """Record of a completed task."""
    id: UUID
    claims: list[dict[str, Any]]  # Serialized claims
    files: list[str]
    model_used: str
    tier_used: ModelTier
    complexity_score: float
    success: bool
    latency_ms: float
    timestamp: datetime
    error: str | None = None


class TaskHistory:
    """
    History of task executions for learning.

    Used to:
    - Find similar past tasks
    - Compute success rates by model/tier/complexity
    - Adjust routing based on outcomes
    """

    def __init__(self, max_records: int = 1000):
        self._records: list[TaskRecord] = []
        self._max_records = max_records

    def add(self, record: TaskRecord) -> None:
        """Add a task record."""
        self._records.append(record)
        # Trim old records
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

    def find_similar(
        self,
        claims: list[Claim],
        files: list[str],
        limit: int = 10,
    ) -> list[TaskRecord]:
        """
        Find similar past tasks.

        Similarity based on:
        - Same claim types
        - Overlapping files
        """
        claim_types = {c.type for c in claims}
        file_set = set(files)

        scored: list[tuple[float, TaskRecord]] = []
        for record in self._records:
            # Score by claim type overlap
            record_types = {ClaimType(c["type"]) for c in record.claims if "type" in c}
            type_overlap = len(claim_types & record_types) / max(len(claim_types | record_types), 1)

            # Score by file overlap
            record_files = set(record.files)
            file_overlap = len(file_set & record_files) / max(len(file_set | record_files), 1)

            score = type_overlap * 0.6 + file_overlap * 0.4
            if score > 0.1:  # Minimum similarity threshold
                scored.append((score, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:limit]]

    def success_rate_by_tier(self, tier: ModelTier) -> float:
        """Get success rate for a tier."""
        tier_records = [r for r in self._records if r.tier_used == tier]
        if not tier_records:
            return 1.0  # Assume success if no data
        return sum(1 for r in tier_records if r.success) / len(tier_records)

    def success_rate_by_complexity(
        self,
        tier: ModelTier,
        complexity_min: float,
        complexity_max: float,
    ) -> float:
        """Get success rate for complexity range in a tier."""
        matching = [
            r for r in self._records
            if r.tier_used == tier
            and complexity_min <= r.complexity_score < complexity_max
        ]
        if not matching:
            return 1.0
        return sum(1 for r in matching if r.success) / len(matching)

    def to_dict(self) -> dict[str, Any]:
        """Serialize history."""
        return {
            "records": [
                {
                    "id": str(r.id),
                    "claims": r.claims,
                    "files": r.files,
                    "model_used": r.model_used,
                    "tier_used": r.tier_used.value,
                    "complexity_score": r.complexity_score,
                    "success": r.success,
                    "latency_ms": r.latency_ms,
                    "timestamp": r.timestamp.isoformat(),
                    "error": r.error,
                }
                for r in self._records
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskHistory":
        """Deserialize history."""
        history = cls()
        for r in data.get("records", []):
            history._records.append(TaskRecord(
                id=UUID(r["id"]),
                claims=r["claims"],
                files=r["files"],
                model_used=r["model_used"],
                tier_used=ModelTier(r["tier_used"]),
                complexity_score=r["complexity_score"],
                success=r["success"],
                latency_ms=r["latency_ms"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                error=r.get("error"),
            ))
        return history


# =============================================================================
# Router
# =============================================================================

@dataclass
class RoutingDecision:
    """Result of routing decision."""
    task_id: UUID
    selected_model: str
    selected_tier: ModelTier
    complexity: ComplexityEstimate
    fallback_models: list[str]  # Ordered fallback chain
    reasoning: str


@dataclass
class RoutingConfig:
    """Configuration for the router."""
    enabled: bool = True
    default_tier: ModelTier = ModelTier.STANDARD

    # Tier thresholds (complexity score boundaries)
    local_max_complexity: float = 0.25
    fast_max_complexity: float = 0.45
    standard_max_complexity: float = 0.7
    # Heavy handles everything above

    # Constraints
    local_max_files: int = 1
    fast_max_files: int = 3
    standard_max_files: int = 10

    # Preferred claim types per tier
    local_preferred_claims: set[ClaimType] = field(default_factory=lambda: {
        ClaimType.FILE_EXISTS,
        ClaimType.SYMBOL_DEFINED,
    })
    fast_preferred_claims: set[ClaimType] = field(default_factory=lambda: {
        ClaimType.FILE_EXISTS,
        ClaimType.SYMBOL_DEFINED,
        ClaimType.API_SURFACE,
        ClaimType.TESTS_PASS,
    })

    # Adaptive routing
    adaptive_enabled: bool = True
    min_success_rate: float = 0.7  # Below this, escalate tier


class Router:
    """
    Routes tasks to appropriate models based on complexity.

    Considers:
    - Task complexity
    - Model capabilities
    - Model availability and load
    - Historical success rates
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        history: TaskHistory | None = None,
        config: RoutingConfig | None = None,
    ):
        self.registry = registry or ModelRegistry()
        self.history = history or TaskHistory()
        self.config = config or RoutingConfig()
        self.estimator = ComplexityEstimator(history=self.history)

    def route(
        self,
        claims: list[Claim],
        description: str = "",
        files: list[str] | None = None,
        force_tier: ModelTier | None = None,
    ) -> RoutingDecision:
        """
        Route a task to an appropriate model.

        Args:
            claims: Claims being made
            description: Task description
            files: Files involved
            force_tier: Override automatic tier selection

        Returns:
            RoutingDecision with selected model and fallbacks
        """
        task_id = uuid4()
        files = files or []

        # Estimate complexity
        complexity = self.estimator.estimate(claims, description, files)

        # Determine tier
        if force_tier:
            tier = force_tier
            reasoning = f"Forced to tier {tier.value}"
        elif not self.config.enabled:
            tier = self.config.default_tier
            reasoning = "Routing disabled, using default tier"
        else:
            tier, reasoning = self._select_tier(claims, files, complexity)

        # Apply adaptive adjustments
        if self.config.adaptive_enabled and not force_tier:
            tier, reasoning = self._apply_adaptive(tier, complexity, reasoning)

        # Select model from tier
        selected_model = self.registry.select_best_for_tier(tier)

        # Build fallback chain
        fallbacks = self._build_fallback_chain(tier, selected_model)

        # If no model available, escalate
        if not selected_model:
            for fallback_tier in [ModelTier.FAST, ModelTier.STANDARD, ModelTier.HEAVY]:
                if fallback_tier.capability_level > tier.capability_level:
                    selected_model = self.registry.select_best_for_tier(fallback_tier)
                    if selected_model:
                        tier = fallback_tier
                        reasoning += f" (escalated to {tier.value} due to availability)"
                        break

        if not selected_model:
            # Last resort: use default tier's first configured model
            available = self.registry.get_models_for_tier(self.config.default_tier)
            selected_model = available[0] if available else "claude-sonnet-4"
            tier = self.config.default_tier

        return RoutingDecision(
            task_id=task_id,
            selected_model=selected_model,
            selected_tier=tier,
            complexity=complexity,
            fallback_models=fallbacks,
            reasoning=reasoning,
        )

    def _select_tier(
        self,
        claims: list[Claim],
        files: list[str],
        complexity: ComplexityEstimate,
    ) -> tuple[ModelTier, str]:
        """Select appropriate tier based on task characteristics."""
        reasons = []

        # Check claim type preferences
        claim_types = {c.type for c in claims}

        # Check file count constraints
        file_count = len(files)

        # Start with complexity recommendation
        score = complexity.score

        # Local tier checks
        if score < self.config.local_max_complexity:
            if file_count <= self.config.local_max_files:
                if claim_types <= self.config.local_preferred_claims:
                    return ModelTier.LOCAL, "Simple task with preferred claims for local model"

        # Fast tier checks
        if score < self.config.fast_max_complexity:
            if file_count <= self.config.fast_max_files:
                if claim_types <= self.config.fast_preferred_claims:
                    return ModelTier.FAST, "Moderate task suitable for fast model"

        # Standard tier
        if score < self.config.standard_max_complexity:
            if file_count <= self.config.standard_max_files:
                return ModelTier.STANDARD, "Complex task requiring standard model"

        # Heavy tier for everything else
        return ModelTier.HEAVY, "Very complex task requiring heavy model"

    def _apply_adaptive(
        self,
        tier: ModelTier,
        complexity: ComplexityEstimate,
        current_reasoning: str,
    ) -> tuple[ModelTier, str]:
        """Apply adaptive adjustments based on historical success rates."""
        # Check success rate for this tier at this complexity
        success_rate = self.history.success_rate_by_complexity(
            tier,
            complexity.score - 0.1,
            complexity.score + 0.1,
        )

        if success_rate < self.config.min_success_rate:
            # Escalate to next tier
            if tier == ModelTier.LOCAL:
                return ModelTier.FAST, current_reasoning + " (escalated: low success rate at LOCAL)"
            elif tier == ModelTier.FAST:
                return ModelTier.STANDARD, current_reasoning + " (escalated: low success rate at FAST)"
            elif tier == ModelTier.STANDARD:
                return ModelTier.HEAVY, current_reasoning + " (escalated: low success rate at STANDARD)"

        return tier, current_reasoning

    def _build_fallback_chain(
        self,
        primary_tier: ModelTier,
        primary_model: str | None,
    ) -> list[str]:
        """Build ordered list of fallback models."""
        fallbacks = []

        # Add other models in same tier
        for model in self.registry.get_available_models(primary_tier):
            if model != primary_model and model not in fallbacks:
                fallbacks.append(model)

        # Add models from higher tiers
        for tier in ModelTier:
            if tier.capability_level > primary_tier.capability_level:
                for model in self.registry.get_available_models(tier):
                    if model not in fallbacks:
                        fallbacks.append(model)

        return fallbacks

    def record_outcome(
        self,
        decision: RoutingDecision,
        success: bool,
        latency_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        """Record the outcome of a routed task."""
        # Update model status
        self.registry.record_task_complete(
            decision.selected_model,
            success,
            latency_ms,
        )

        # Add to history
        self.history.add(TaskRecord(
            id=decision.task_id,
            claims=[{"type": c.type.value} for c in []],  # Simplified
            files=[],
            model_used=decision.selected_model,
            tier_used=decision.selected_tier,
            complexity_score=decision.complexity.score,
            success=success,
            latency_ms=latency_ms,
            timestamp=datetime.now(timezone.utc),
            error=error,
        ))


# =============================================================================
# Convenience Functions
# =============================================================================

def create_router(
    config: dict[str, Any] | None = None,
) -> Router:
    """
    Create a router with optional config.

    Args:
        config: Configuration dict (see RoutingConfig)

    Returns:
        Configured Router instance
    """
    routing_config = RoutingConfig()

    if config:
        if "enabled" in config:
            routing_config.enabled = config["enabled"]
        if "default_tier" in config:
            routing_config.default_tier = ModelTier(config["default_tier"])
        if "local_max_complexity" in config:
            routing_config.local_max_complexity = config["local_max_complexity"]
        if "fast_max_complexity" in config:
            routing_config.fast_max_complexity = config["fast_max_complexity"]
        if "adaptive_enabled" in config:
            routing_config.adaptive_enabled = config["adaptive_enabled"]

    return Router(config=routing_config)


def estimate_complexity(
    claims: list[Claim],
    description: str = "",
    files: list[str] | None = None,
) -> ComplexityEstimate:
    """Quick complexity estimate without full router setup."""
    estimator = ComplexityEstimator()
    return estimator.estimate(claims, description, files)


def recommend_tier(complexity_score: float) -> ModelTier:
    """Get recommended tier for a complexity score."""
    if complexity_score < 0.25:
        return ModelTier.LOCAL
    elif complexity_score < 0.45:
        return ModelTier.FAST
    elif complexity_score < 0.7:
        return ModelTier.STANDARD
    else:
        return ModelTier.HEAVY
