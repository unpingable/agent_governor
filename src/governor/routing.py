# SPDX-License-Identifier: Apache-2.0
"""
Multi-agent routing and task sizing.

Routes tasks to appropriate model tiers based on complexity estimation.
Tracks outcomes for adaptive routing.

Tiers:
- local: Fast, cheap, limited capability (qwen, ollama, codellama)
- fast: Quick cloud model (haiku)
- standard: Default capable model (sonnet)
- heavy: Most capable, expensive (opus)

Enhanced features (Phase B1):
- LLM capability profiles with cost/latency data
- Routing strategies: cost_optimal, speed_optimal, quality_optimal, balanced
- Budget management with session/task/project scopes
- Routing explainability
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


class RoutingStrategy(Enum):
    """Routing optimization strategies."""
    COST_OPTIMAL = "cost_optimal"      # Cheapest model that can handle complexity
    SPEED_OPTIMAL = "speed_optimal"    # Fastest model that can handle complexity
    QUALITY_OPTIMAL = "quality_optimal"  # Best model regardless of cost
    BALANCED = "balanced"              # Weighted sum of cost/speed/quality


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
    """Capabilities of a specific model.

    Enhanced with cost/latency data for routing strategies.
    """
    name: str
    tier: ModelTier
    provider: str = "anthropic"
    context_window: int = 8192
    supports_tools: bool = True
    supports_vision: bool = False
    code_quality: float = 0.5  # 0-1, estimated code generation quality
    speed_factor: float = 1.0  # Relative speed (higher = faster)

    # Cost data (per 1M tokens, USD)
    cost_input: float = 0.0   # Input token cost
    cost_output: float = 0.0  # Output token cost

    # Latency data (milliseconds)
    latency_p50: float = 0.0  # Median latency
    latency_p95: float = 0.0  # 95th percentile latency

    # Rate limits
    requests_per_minute: int = 0  # 0 = unlimited
    tokens_per_minute: int = 0    # 0 = unlimited

    # Strengths for routing
    strengths: list[str] = field(default_factory=list)  # e.g., ["code", "reasoning", "creative"]

    def cost_per_1k_tokens(self, input_ratio: float = 0.7) -> float:
        """Estimate cost per 1K tokens with given input/output ratio."""
        return (self.cost_input * input_ratio + self.cost_output * (1 - input_ratio)) / 1000


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
        """Register default model configurations with cost/latency data."""
        defaults = [
            # Local models (free, fast)
            ModelCapabilities(
                name="qwen2.5-coder:7b",
                tier=ModelTier.LOCAL,
                provider="ollama",
                context_window=32768,
                code_quality=0.6,
                speed_factor=2.0,
                cost_input=0.0,
                cost_output=0.0,
                latency_p50=500,
                latency_p95=2000,
                strengths=["code"],
            ),
            ModelCapabilities(
                name="ollama/codellama",
                tier=ModelTier.LOCAL,
                provider="ollama",
                context_window=16384,
                code_quality=0.5,
                speed_factor=1.5,
                cost_input=0.0,
                cost_output=0.0,
                latency_p50=800,
                latency_p95=3000,
                strengths=["code"],
            ),
            # Fast cloud - Claude Haiku
            ModelCapabilities(
                name="claude-3-haiku",
                tier=ModelTier.FAST,
                provider="anthropic",
                context_window=200000,
                code_quality=0.7,
                speed_factor=3.0,
                cost_input=0.25,   # $0.25 per 1M input
                cost_output=1.25,  # $1.25 per 1M output
                latency_p50=300,
                latency_p95=800,
                requests_per_minute=1000,
                tokens_per_minute=100000,
                strengths=["speed", "code"],
            ),
            ModelCapabilities(
                name="claude-3-5-haiku",
                tier=ModelTier.FAST,
                provider="anthropic",
                context_window=200000,
                code_quality=0.75,
                speed_factor=2.5,
                cost_input=1.00,   # $1.00 per 1M input
                cost_output=5.00,  # $5.00 per 1M output
                latency_p50=400,
                latency_p95=1000,
                requests_per_minute=1000,
                tokens_per_minute=100000,
                strengths=["speed", "code", "reasoning"],
            ),
            # Standard - Claude Sonnet
            ModelCapabilities(
                name="claude-sonnet-4",
                tier=ModelTier.STANDARD,
                provider="anthropic",
                context_window=200000,
                supports_vision=True,
                code_quality=0.9,
                speed_factor=1.5,
                cost_input=3.00,   # $3.00 per 1M input
                cost_output=15.00, # $15.00 per 1M output
                latency_p50=1000,
                latency_p95=3000,
                requests_per_minute=500,
                tokens_per_minute=80000,
                strengths=["code", "reasoning", "creative"],
            ),
            # Heavy - Claude Opus
            ModelCapabilities(
                name="claude-opus-4",
                tier=ModelTier.HEAVY,
                provider="anthropic",
                context_window=200000,
                supports_vision=True,
                code_quality=0.95,
                speed_factor=1.0,
                cost_input=15.00,  # $15.00 per 1M input
                cost_output=75.00, # $75.00 per 1M output
                latency_p50=2000,
                latency_p95=6000,
                requests_per_minute=200,
                tokens_per_minute=40000,
                strengths=["code", "reasoning", "creative", "complex"],
            ),
            # OpenAI models for comparison
            ModelCapabilities(
                name="gpt-4o-mini",
                tier=ModelTier.FAST,
                provider="openai",
                context_window=128000,
                code_quality=0.7,
                speed_factor=2.5,
                cost_input=0.15,   # $0.15 per 1M input
                cost_output=0.60,  # $0.60 per 1M output
                latency_p50=350,
                latency_p95=900,
                requests_per_minute=500,
                tokens_per_minute=200000,
                strengths=["speed", "code"],
            ),
            ModelCapabilities(
                name="gpt-4o",
                tier=ModelTier.STANDARD,
                provider="openai",
                context_window=128000,
                supports_vision=True,
                code_quality=0.85,
                speed_factor=1.3,
                cost_input=2.50,   # $2.50 per 1M input
                cost_output=10.00, # $10.00 per 1M output
                latency_p50=1200,
                latency_p95=3500,
                requests_per_minute=500,
                tokens_per_minute=150000,
                strengths=["code", "reasoning", "creative"],
            ),
            # DeepSeek for cost-effective coding
            ModelCapabilities(
                name="deepseek-coder",
                tier=ModelTier.FAST,
                provider="deepseek",
                context_window=64000,
                code_quality=0.75,
                speed_factor=2.0,
                cost_input=0.14,   # $0.14 per 1M input
                cost_output=0.28,  # $0.28 per 1M output
                latency_p50=600,
                latency_p95=1500,
                strengths=["code"],
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
# Budget Management
# =============================================================================


class BudgetScope(Enum):
    """Scope for budget tracking."""
    SESSION = "session"  # Single session
    TASK = "task"        # Single task
    PROJECT = "project"  # Entire project
    GLOBAL = "global"    # All usage


@dataclass
class Budget:
    """Budget configuration and tracking.

    Tracks cost limits and spending across different scopes.
    """
    scope: BudgetScope
    scope_id: str  # e.g., session_id, task_id, project_name
    total_usd: float = 0.0  # Total budget (0 = unlimited)
    spent_usd: float = 0.0
    model_limits: dict[str, float] = field(default_factory=dict)  # Per-model limits

    # Token tracking
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def remaining_usd(self) -> float:
        """Remaining budget."""
        if self.total_usd <= 0:
            return float("inf")
        return max(0.0, self.total_usd - self.spent_usd)

    @property
    def is_exhausted(self) -> bool:
        """Check if budget is exhausted."""
        if self.total_usd <= 0:
            return False
        return self.spent_usd >= self.total_usd

    def can_afford(self, estimated_cost: float) -> bool:
        """Check if we can afford an estimated cost."""
        if self.total_usd <= 0:
            return True
        return self.spent_usd + estimated_cost <= self.total_usd

    def can_use_model(self, model_name: str, estimated_cost: float) -> bool:
        """Check if we can use a specific model within its limit."""
        if model_name not in self.model_limits:
            return self.can_afford(estimated_cost)
        model_limit = self.model_limits[model_name]
        # Would need per-model tracking for full implementation
        return self.can_afford(estimated_cost)

    def record_usage(
        self,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record usage against budget."""
        self.spent_usd += cost_usd
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "scope_id": self.scope_id,
            "total_usd": self.total_usd,
            "spent_usd": self.spent_usd,
            "remaining_usd": self.remaining_usd,
            "model_limits": self.model_limits,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "is_exhausted": self.is_exhausted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Budget":
        return cls(
            scope=BudgetScope(data["scope"]),
            scope_id=data["scope_id"],
            total_usd=data.get("total_usd", 0.0),
            spent_usd=data.get("spent_usd", 0.0),
            model_limits=data.get("model_limits", {}),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
        )


@dataclass
class BudgetCheckResult:
    """Result of a budget check."""
    allowed: bool
    reason: str = ""
    estimated_cost: float = 0.0
    remaining_budget: float = 0.0
    cheaper_alternatives: list[str] = field(default_factory=list)


class BudgetManager:
    """Manages budgets across multiple scopes.

    Supports session, task, and project level budgets.
    All budgets are checked before routing decisions.
    """

    def __init__(self, registry: "ModelRegistry | None" = None):
        self._budgets: dict[str, Budget] = {}
        self._registry = registry

    def create_budget(
        self,
        scope: BudgetScope,
        scope_id: str,
        total_usd: float = 0.0,
        model_limits: dict[str, float] | None = None,
    ) -> Budget:
        """Create a new budget."""
        budget = Budget(
            scope=scope,
            scope_id=scope_id,
            total_usd=total_usd,
            model_limits=model_limits or {},
        )
        key = f"{scope.value}:{scope_id}"
        self._budgets[key] = budget
        return budget

    def get_budget(self, scope: BudgetScope, scope_id: str) -> Budget | None:
        """Get a budget by scope."""
        key = f"{scope.value}:{scope_id}"
        return self._budgets.get(key)

    def check_budget(
        self,
        model_name: str,
        estimated_tokens: int,
        scope: BudgetScope | None = None,
        scope_id: str | None = None,
    ) -> BudgetCheckResult:
        """Check if a model usage fits within budget.

        Args:
            model_name: Model to use
            estimated_tokens: Estimated total tokens
            scope: Specific scope to check (or None for all)
            scope_id: Scope identifier

        Returns:
            BudgetCheckResult with allowed status and alternatives
        """
        # Estimate cost
        estimated_cost = 0.0
        if self._registry:
            caps = self._registry.get_capabilities(model_name)
            if caps:
                # Assume 70% input, 30% output
                input_tokens = int(estimated_tokens * 0.7)
                output_tokens = estimated_tokens - input_tokens
                estimated_cost = (
                    (caps.cost_input * input_tokens / 1_000_000) +
                    (caps.cost_output * output_tokens / 1_000_000)
                )

        # Find budgets to check
        budgets_to_check = []
        if scope and scope_id:
            key = f"{scope.value}:{scope_id}"
            if key in self._budgets:
                budgets_to_check.append(self._budgets[key])
        else:
            budgets_to_check = list(self._budgets.values())

        # Check all relevant budgets
        for budget in budgets_to_check:
            if not budget.can_afford(estimated_cost):
                # Find cheaper alternatives
                cheaper = self._find_cheaper_alternatives(
                    model_name, estimated_tokens, budget.remaining_usd
                )
                return BudgetCheckResult(
                    allowed=False,
                    reason=f"Budget exhausted in {budget.scope.value}:{budget.scope_id}",
                    estimated_cost=estimated_cost,
                    remaining_budget=budget.remaining_usd,
                    cheaper_alternatives=cheaper,
                )

        return BudgetCheckResult(
            allowed=True,
            estimated_cost=estimated_cost,
            remaining_budget=min(
                (b.remaining_usd for b in budgets_to_check),
                default=float("inf")
            ),
        )

    def _find_cheaper_alternatives(
        self,
        current_model: str,
        estimated_tokens: int,
        max_cost: float,
    ) -> list[str]:
        """Find models that fit within budget."""
        if not self._registry:
            return []

        alternatives = []
        for name, caps in self._registry._models.items():
            if name == current_model:
                continue
            input_tokens = int(estimated_tokens * 0.7)
            output_tokens = estimated_tokens - input_tokens
            cost = (
                (caps.cost_input * input_tokens / 1_000_000) +
                (caps.cost_output * output_tokens / 1_000_000)
            )
            if cost <= max_cost:
                alternatives.append(name)

        # Sort by cost (cheapest first)
        alternatives.sort(
            key=lambda n: self._registry._models[n].cost_input
        )
        return alternatives[:5]  # Top 5

    def record_usage(
        self,
        scope: BudgetScope,
        scope_id: str,
        cost_usd: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record usage against a budget."""
        budget = self.get_budget(scope, scope_id)
        if budget:
            budget.record_usage(cost_usd, input_tokens, output_tokens)

    def get_spending_summary(self) -> dict[str, Any]:
        """Get spending summary across all budgets."""
        return {
            "budgets": {
                f"{b.scope.value}:{b.scope_id}": b.to_dict()
                for b in self._budgets.values()
            },
            "total_spent": sum(b.spent_usd for b in self._budgets.values()),
            "total_input_tokens": sum(b.input_tokens for b in self._budgets.values()),
            "total_output_tokens": sum(b.output_tokens for b in self._budgets.values()),
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

    # Enhanced fields for explainability
    estimated_cost: float = 0.0  # USD
    estimated_latency_ms: float = 0.0
    strategy_used: RoutingStrategy = RoutingStrategy.BALANCED
    alternatives_considered: list[dict[str, Any]] = field(default_factory=list)
    budget_check: "BudgetCheckResult | None" = None


@dataclass
class RoutingConfig:
    """Configuration for the router."""
    enabled: bool = True
    default_tier: ModelTier = ModelTier.STANDARD

    # Routing strategy
    strategy: RoutingStrategy = RoutingStrategy.BALANCED
    strategy_weights: dict[str, float] = field(default_factory=lambda: {
        "cost": 0.3,
        "speed": 0.3,
        "quality": 0.4,
    })

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

    # Budget enforcement
    enforce_budget: bool = True


class Router:
    """
    Routes tasks to appropriate models based on complexity.

    Considers:
    - Task complexity
    - Model capabilities
    - Model availability and load
    - Historical success rates
    - Routing strategy (cost/speed/quality/balanced)
    - Budget constraints
    """

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        history: TaskHistory | None = None,
        config: RoutingConfig | None = None,
        budget_manager: BudgetManager | None = None,
    ):
        self.registry = registry or ModelRegistry()
        self.history = history or TaskHistory()
        self.config = config or RoutingConfig()
        self.budget_manager = budget_manager
        self.estimator = ComplexityEstimator(history=self.history)

    def route(
        self,
        claims: list[Claim],
        description: str = "",
        files: list[str] | None = None,
        force_tier: ModelTier | None = None,
        force_model: str | None = None,
        estimated_tokens: int = 1000,
        budget_scope: BudgetScope | None = None,
        budget_scope_id: str | None = None,
    ) -> RoutingDecision:
        """
        Route a task to an appropriate model.

        Args:
            claims: Claims being made
            description: Task description
            files: Files involved
            force_tier: Override automatic tier selection
            force_model: Override model selection entirely
            estimated_tokens: Estimated total tokens for cost calculation
            budget_scope: Budget scope to check (optional)
            budget_scope_id: Budget scope identifier

        Returns:
            RoutingDecision with selected model and fallbacks
        """
        task_id = uuid4()
        files = files or []

        # Estimate complexity
        complexity = self.estimator.estimate(claims, description, files)

        # Collect alternatives for explainability
        alternatives: list[dict[str, Any]] = []

        # Determine tier
        if force_model:
            caps = self.registry.get_capabilities(force_model)
            tier = caps.tier if caps else self.config.default_tier
            selected_model = force_model
            reasoning = f"Forced to model {force_model}"
        elif force_tier:
            tier = force_tier
            reasoning = f"Forced to tier {tier.value}"
            selected_model = self._select_model_for_tier(tier, estimated_tokens, alternatives)
        elif not self.config.enabled:
            tier = self.config.default_tier
            reasoning = "Routing disabled, using default tier"
            selected_model = self._select_model_for_tier(tier, estimated_tokens, alternatives)
        else:
            tier, reasoning = self._select_tier(claims, files, complexity)

            # Apply adaptive adjustments
            if self.config.adaptive_enabled:
                tier, reasoning = self._apply_adaptive(tier, complexity, reasoning)

            # Apply strategy-based model selection
            selected_model = self._select_model_by_strategy(
                tier, complexity, estimated_tokens, alternatives
            )

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

        # Calculate estimated cost and latency
        estimated_cost = 0.0
        estimated_latency = 0.0
        if selected_model:
            caps = self.registry.get_capabilities(selected_model)
            if caps:
                input_tokens = int(estimated_tokens * 0.7)
                output_tokens = estimated_tokens - input_tokens
                estimated_cost = (
                    (caps.cost_input * input_tokens / 1_000_000) +
                    (caps.cost_output * output_tokens / 1_000_000)
                )
                estimated_latency = caps.latency_p50

        # Check budget if configured
        budget_check = None
        if self.budget_manager and self.config.enforce_budget:
            budget_check = self.budget_manager.check_budget(
                selected_model or "",
                estimated_tokens,
                budget_scope,
                budget_scope_id,
            )
            if not budget_check.allowed and budget_check.cheaper_alternatives:
                # Switch to a cheaper alternative
                old_model = selected_model
                selected_model = budget_check.cheaper_alternatives[0]
                reasoning += f" (switched to {selected_model} due to budget)"
                # Recalculate cost
                caps = self.registry.get_capabilities(selected_model)
                if caps:
                    tier = caps.tier
                    input_tokens = int(estimated_tokens * 0.7)
                    output_tokens = estimated_tokens - input_tokens
                    estimated_cost = (
                        (caps.cost_input * input_tokens / 1_000_000) +
                        (caps.cost_output * output_tokens / 1_000_000)
                    )
                    estimated_latency = caps.latency_p50

        return RoutingDecision(
            task_id=task_id,
            selected_model=selected_model or "claude-sonnet-4",
            selected_tier=tier,
            complexity=complexity,
            fallback_models=fallbacks,
            reasoning=reasoning,
            estimated_cost=estimated_cost,
            estimated_latency_ms=estimated_latency,
            strategy_used=self.config.strategy,
            alternatives_considered=alternatives,
            budget_check=budget_check,
        )

    def _select_model_for_tier(
        self,
        tier: ModelTier,
        estimated_tokens: int,
        alternatives: list[dict[str, Any]],
    ) -> str | None:
        """Select best model for a tier, recording alternatives."""
        available = self.registry.get_available_models(tier)
        if not available:
            return None

        for name in available:
            caps = self.registry.get_capabilities(name)
            if caps:
                input_tokens = int(estimated_tokens * 0.7)
                output_tokens = estimated_tokens - input_tokens
                cost = (
                    (caps.cost_input * input_tokens / 1_000_000) +
                    (caps.cost_output * output_tokens / 1_000_000)
                )
                alternatives.append({
                    "model": name,
                    "tier": tier.value,
                    "cost_usd": cost,
                    "latency_p50": caps.latency_p50,
                    "quality": caps.code_quality,
                })

        return self.registry.select_best_for_tier(tier)

    def _select_model_by_strategy(
        self,
        tier: ModelTier,
        complexity: ComplexityEstimate,
        estimated_tokens: int,
        alternatives: list[dict[str, Any]],
        must_have_strengths: list[str] | None = None,
        nice_to_have_strengths: list[str] | None = None,
        min_context_window: int = 0,
    ) -> str | None:
        """Select model based on configured strategy.

        Strategies:
        - COST_OPTIMAL: Cheapest model that can handle complexity
        - SPEED_OPTIMAL: Fastest model that can handle complexity
        - QUALITY_OPTIMAL: Best model regardless of cost
        - BALANCED: Weighted combination

        Capability filters (from lane contracts):
        - must_have_strengths: hard filter — model.strengths must contain ALL
        - nice_to_have_strengths: soft preference — rank by overlap count
        - min_context_window: hard filter — model.context_window >= threshold
        """
        # Get all capable models (tier and above)
        capable_models: list[tuple[str, ModelCapabilities]] = []
        for t in ModelTier:
            if t.capability_level >= tier.capability_level:
                for name in self.registry.get_available_models(t):
                    caps = self.registry.get_capabilities(name)
                    if caps:
                        capable_models.append((name, caps))

        if not capable_models:
            return None

        # --- Capability filters ---
        if must_have_strengths:
            required = set(must_have_strengths)
            filtered = [
                (n, c) for n, c in capable_models
                if required <= set(c.strengths)
            ]
            if filtered:
                capable_models = filtered
            # If no match, keep all candidates (degrade gracefully)

        if min_context_window > 0:
            filtered = [
                (n, c) for n, c in capable_models
                if c.context_window >= min_context_window
            ]
            if filtered:
                capable_models = filtered

        # Calculate scores for each model
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for name, caps in capable_models:
            input_tokens = int(estimated_tokens * 0.7)
            output_tokens = estimated_tokens - input_tokens
            cost = (
                (caps.cost_input * input_tokens / 1_000_000) +
                (caps.cost_output * output_tokens / 1_000_000)
            )

            # Normalize metrics (lower is better for cost/latency, higher for quality)
            # Use simple scoring (0-1 range approximations)
            cost_score = 1.0 - min(cost / 0.10, 1.0)  # $0.10 = max cost considered
            speed_score = 1.0 - min(caps.latency_p50 / 5000, 1.0)  # 5000ms = slowest
            quality_score = caps.code_quality

            # Calculate final score based on strategy
            if self.config.strategy == RoutingStrategy.COST_OPTIMAL:
                final_score = cost_score
            elif self.config.strategy == RoutingStrategy.SPEED_OPTIMAL:
                final_score = speed_score
            elif self.config.strategy == RoutingStrategy.QUALITY_OPTIMAL:
                final_score = quality_score
            else:  # BALANCED
                weights = self.config.strategy_weights
                final_score = (
                    weights.get("cost", 0.3) * cost_score +
                    weights.get("speed", 0.3) * speed_score +
                    weights.get("quality", 0.4) * quality_score
                )

            alt_entry = {
                "model": name,
                "tier": caps.tier.value,
                "cost_usd": cost,
                "latency_p50": caps.latency_p50,
                "quality": quality_score,
                "score": final_score,
            }
            alternatives.append(alt_entry)
            scored.append((final_score, name, alt_entry))

        # Sort by score (highest first), with nice_to_have as tiebreaker
        if nice_to_have_strengths:
            preferred = set(nice_to_have_strengths)
            scored.sort(
                key=lambda x: (
                    x[0],
                    len(preferred & set(
                        self.registry.get_capabilities(x[1]).strengths
                        if self.registry.get_capabilities(x[1]) else []
                    )),
                ),
                reverse=True,
            )
        else:
            scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

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

    def explain(self, decision: RoutingDecision) -> dict[str, Any]:
        """Generate a detailed explanation of a routing decision.

        This is used by `governor task route <id> --explain` to show:
        - Complexity analysis breakdown
        - Selected model and tier justification
        - Alternatives considered with cost/latency tradeoffs
        - Budget impact

        Args:
            decision: The routing decision to explain

        Returns:
            Dict with explanation sections
        """
        # Get model capabilities
        selected_caps = self.registry.get_capabilities(decision.selected_model)
        selected_status = self.registry.get_status(decision.selected_model)

        # Build complexity breakdown
        complexity_breakdown = {
            "score": decision.complexity.score,
            "classification": (
                "simple" if decision.complexity.is_simple
                else "moderate" if decision.complexity.is_moderate
                else "complex"
            ),
            "factors": decision.complexity.factors,
            "recommended_tier": decision.complexity.recommended_tier.value,
        }

        # Build selection reasoning
        selection = {
            "model": decision.selected_model,
            "tier": decision.selected_tier.value,
            "reasoning": decision.reasoning,
            "strategy": decision.strategy_used.value,
        }

        if selected_caps:
            selection["model_capabilities"] = {
                "provider": selected_caps.provider,
                "context_window": selected_caps.context_window,
                "code_quality": selected_caps.code_quality,
                "supports_vision": selected_caps.supports_vision,
                "cost_per_1M_input": f"${selected_caps.cost_input:.2f}",
                "cost_per_1M_output": f"${selected_caps.cost_output:.2f}",
                "latency_p50_ms": selected_caps.latency_p50,
                "latency_p95_ms": selected_caps.latency_p95,
                "strengths": selected_caps.strengths,
            }

        if selected_status:
            selection["model_status"] = {
                "available": selected_status.available,
                "tasks_in_flight": selected_status.tasks_in_flight,
                "success_rate": f"{selected_status.success_rate:.1%}",
                "avg_latency_ms": selected_status.avg_latency_ms,
            }

        # Build cost analysis
        cost_analysis = {
            "estimated_cost_usd": f"${decision.estimated_cost:.6f}",
            "estimated_latency_ms": decision.estimated_latency_ms,
        }

        if decision.budget_check:
            cost_analysis["budget_check"] = {
                "allowed": decision.budget_check.allowed,
                "reason": decision.budget_check.reason,
                "remaining_budget": f"${decision.budget_check.remaining_budget:.2f}",
                "cheaper_alternatives": decision.budget_check.cheaper_alternatives,
            }

        # Build alternatives comparison
        alternatives = []
        for alt in decision.alternatives_considered:
            alt_entry = {
                "model": alt.get("model", "unknown"),
                "tier": alt.get("tier", "unknown"),
                "score": alt.get("score", 0.0),
            }
            alt_caps = self.registry.get_capabilities(alt.get("model", ""))
            if alt_caps:
                alt_entry["cost_per_1M_input"] = f"${alt_caps.cost_input:.2f}"
                alt_entry["cost_per_1M_output"] = f"${alt_caps.cost_output:.2f}"
                alt_entry["latency_p50_ms"] = alt_caps.latency_p50
                alt_entry["code_quality"] = alt_caps.code_quality
            if "reason_rejected" in alt:
                alt_entry["reason_rejected"] = alt["reason_rejected"]
            alternatives.append(alt_entry)

        # Build fallback chain
        fallback_chain = []
        for fallback_model in decision.fallback_models:
            fb_caps = self.registry.get_capabilities(fallback_model)
            fb_entry = {"model": fallback_model}
            if fb_caps:
                fb_entry["tier"] = fb_caps.tier.value
                fb_entry["cost_per_1M_input"] = f"${fb_caps.cost_input:.2f}"
            fallback_chain.append(fb_entry)

        # Get historical context
        historical_context = {}
        success_rate = self.history.success_rate_by_tier(decision.selected_tier)
        historical_context["tier_success_rate"] = f"{success_rate:.1%}"

        complexity_success = self.history.success_rate_by_complexity(
            decision.selected_tier,
            decision.complexity.score - 0.1,
            decision.complexity.score + 0.1,
        )
        historical_context["complexity_range_success_rate"] = f"{complexity_success:.1%}"

        return {
            "task_id": str(decision.task_id),
            "complexity": complexity_breakdown,
            "selection": selection,
            "cost_analysis": cost_analysis,
            "alternatives_considered": alternatives,
            "fallback_chain": fallback_chain,
            "historical_context": historical_context,
        }

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
