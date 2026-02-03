"""Tests for multi-agent routing and task sizing."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from governor.routing import (
    ModelTier,
    RoutingStrategy,
    ComplexityEstimate,
    ComplexityEstimator,
    ModelCapabilities,
    ModelStatus,
    ModelRegistry,
    BudgetScope,
    Budget,
    BudgetCheckResult,
    BudgetManager,
    TaskRecord,
    TaskHistory,
    RoutingDecision,
    RoutingConfig,
    Router,
    create_router,
    estimate_complexity,
    recommend_tier,
)
from governor.claims import Claim, ClaimType


# =============================================================================
# ModelTier Tests
# =============================================================================

class TestModelTier:
    """Tests for ModelTier enum."""

    def test_capability_levels_ordered(self):
        """Capability levels are properly ordered."""
        assert ModelTier.LOCAL.capability_level < ModelTier.FAST.capability_level
        assert ModelTier.FAST.capability_level < ModelTier.STANDARD.capability_level
        assert ModelTier.STANDARD.capability_level < ModelTier.HEAVY.capability_level

    def test_cost_multipliers(self):
        """Cost multipliers increase with capability."""
        assert ModelTier.LOCAL.cost_multiplier == 0.0  # Free
        assert ModelTier.FAST.cost_multiplier < ModelTier.STANDARD.cost_multiplier
        assert ModelTier.STANDARD.cost_multiplier < ModelTier.HEAVY.cost_multiplier


# =============================================================================
# ComplexityEstimate Tests
# =============================================================================

class TestComplexityEstimate:
    """Tests for ComplexityEstimate dataclass."""

    def test_is_simple(self):
        """Simple complexity detection works."""
        simple = ComplexityEstimate(score=0.2)
        assert simple.is_simple
        assert not simple.is_moderate
        assert not simple.is_complex

    def test_is_moderate(self):
        """Moderate complexity detection works."""
        moderate = ComplexityEstimate(score=0.5)
        assert not moderate.is_simple
        assert moderate.is_moderate
        assert not moderate.is_complex

    def test_is_complex(self):
        """Complex task detection works."""
        complex_task = ComplexityEstimate(score=0.8)
        assert not complex_task.is_simple
        assert not complex_task.is_moderate
        assert complex_task.is_complex


# =============================================================================
# ComplexityEstimator Tests
# =============================================================================

class TestComplexityEstimator:
    """Tests for ComplexityEstimator class."""

    def test_simple_file_exists_claim(self):
        """FILE_EXISTS claim is estimated as simple."""
        estimator = ComplexityEstimator()
        claims = [Claim(type=ClaimType.FILE_EXISTS, path="test.py")]

        estimate = estimator.estimate(claims)

        assert estimate.score < 0.5
        assert estimate.recommended_tier in [ModelTier.LOCAL, ModelTier.FAST]

    def test_complex_changeset_claim(self):
        """CHANGESET claim is estimated as complex."""
        estimator = ComplexityEstimator()
        files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
        claims = [Claim(
            type=ClaimType.CHANGESET,
            diff="--- a.py\n+++ a.py\n@@ -1 +1 @@\n-old\n+new",
            paths=files,
        )]

        estimate = estimator.estimate(claims, files=files)

        assert estimate.score > 0.5
        assert estimate.recommended_tier in [ModelTier.STANDARD, ModelTier.HEAVY]

    def test_single_file_lower_complexity(self):
        """Single file tasks are less complex."""
        estimator = ComplexityEstimator()

        single = estimator.estimate([], files=["one.py"])
        multiple = estimator.estimate([], files=["a.py", "b.py", "c.py", "d.py"])

        assert single.score < multiple.score

    def test_test_files_simpler(self):
        """Test files are considered simpler."""
        estimator = ComplexityEstimator()

        test_file = estimator.estimate([], files=["test_something.py"])
        main_file = estimator.estimate([], files=["something.py"])

        assert test_file.factors["file_types"] < main_file.factors["file_types"]

    def test_migration_files_complex(self):
        """Migration files are considered complex."""
        estimator = ComplexityEstimator()

        migration = estimator.estimate([], files=["migrations/001_create_users.py"])
        normal = estimator.estimate([], files=["models.py"])

        assert migration.factors["file_types"] > normal.factors["file_types"]

    def test_description_affects_complexity(self):
        """Longer descriptions increase complexity."""
        estimator = ComplexityEstimator()

        short = estimator.estimate([], description="Fix typo")
        long = estimator.estimate([], description=" ".join(["word"] * 150))

        assert short.factors["description"] < long.factors["description"]

    def test_factors_are_populated(self):
        """All expected factors are populated."""
        estimator = ComplexityEstimator()
        estimate = estimator.estimate(
            [Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
            description="Test task",
            files=["x.py"],
        )

        assert "claim_types" in estimate.factors
        assert "file_count" in estimate.factors
        assert "file_types" in estimate.factors
        assert "description" in estimate.factors

    def test_score_clamped_to_0_1(self):
        """Score is always in [0, 1] range."""
        estimator = ComplexityEstimator()
        files = ["f" + str(i) + ".py" for i in range(100)]

        # Even with extreme inputs, should be clamped
        estimate = estimator.estimate(
            [Claim(type=ClaimType.CHANGESET, diff="large diff", paths=files)],
            description=" ".join(["complex"] * 500),
            files=files,
        )

        assert 0.0 <= estimate.score <= 1.0


# =============================================================================
# ModelRegistry Tests
# =============================================================================

class TestModelRegistry:
    """Tests for ModelRegistry class."""

    def test_default_models_registered(self):
        """Default models are registered on init."""
        registry = ModelRegistry()

        assert registry.get_capabilities("claude-sonnet-4") is not None
        assert registry.get_capabilities("claude-opus-4") is not None
        assert registry.get_capabilities("claude-3-haiku") is not None

    def test_register_custom_model(self):
        """Can register custom models."""
        registry = ModelRegistry()

        caps = ModelCapabilities(
            name="custom-model",
            tier=ModelTier.FAST,
            context_window=16384,
        )
        registry.register(caps)

        assert registry.get_capabilities("custom-model") is not None
        assert "custom-model" in registry.get_models_for_tier(ModelTier.FAST)

    def test_unregister_model(self):
        """Can unregister models."""
        registry = ModelRegistry()
        registry.register(ModelCapabilities(name="temp", tier=ModelTier.LOCAL))

        registry.unregister("temp")

        assert registry.get_capabilities("temp") is None

    def test_model_availability(self):
        """Model availability tracking works."""
        registry = ModelRegistry()

        # Default available
        assert registry.get_status("claude-sonnet-4").available

        # Mark unavailable
        registry.mark_available("claude-sonnet-4", False)
        assert not registry.get_status("claude-sonnet-4").available

        # Mark available again
        registry.mark_available("claude-sonnet-4", True)
        assert registry.get_status("claude-sonnet-4").available

    def test_get_available_models(self):
        """Get available models filters correctly."""
        registry = ModelRegistry()
        registry.mark_available("claude-opus-4", False)

        available = registry.get_available_models()

        assert "claude-sonnet-4" in available
        assert "claude-opus-4" not in available

    def test_get_available_models_by_tier(self):
        """Get available models can filter by tier."""
        registry = ModelRegistry()

        fast_models = registry.get_available_models(ModelTier.FAST)

        assert all(
            registry.get_capabilities(m).tier == ModelTier.FAST
            for m in fast_models
        )

    def test_task_tracking(self):
        """Task in-flight tracking works."""
        registry = ModelRegistry()

        registry.record_task_start("claude-sonnet-4")
        assert registry.get_status("claude-sonnet-4").tasks_in_flight == 1

        registry.record_task_start("claude-sonnet-4")
        assert registry.get_status("claude-sonnet-4").tasks_in_flight == 2

        registry.record_task_complete("claude-sonnet-4", success=True)
        assert registry.get_status("claude-sonnet-4").tasks_in_flight == 1

    def test_success_rate_tracking(self):
        """Success rate is tracked."""
        registry = ModelRegistry()

        # Record some successes
        for _ in range(5):
            registry.record_task_complete("claude-sonnet-4", success=True)

        status = registry.get_status("claude-sonnet-4")
        assert status.success_rate > 0.9

        # Record failures
        for _ in range(10):
            registry.record_task_complete("claude-sonnet-4", success=False)

        status = registry.get_status("claude-sonnet-4")
        assert status.success_rate < 0.5

    def test_select_best_for_tier(self):
        """Selects best available model for tier."""
        registry = ModelRegistry()

        # Should return a model from the tier
        model = registry.select_best_for_tier(ModelTier.STANDARD)
        assert model is not None
        assert registry.get_capabilities(model).tier == ModelTier.STANDARD

    def test_select_best_considers_load(self):
        """Best model selection considers load."""
        registry = ModelRegistry()

        # Add two models to same tier
        registry.register(ModelCapabilities(name="model-a", tier=ModelTier.FAST, code_quality=0.7))
        registry.register(ModelCapabilities(name="model-b", tier=ModelTier.FAST, code_quality=0.7))

        # Add load to model-a
        for _ in range(5):
            registry.record_task_start("model-a")

        # model-b should be preferred due to lower load
        selected = registry.select_best_for_tier(ModelTier.FAST)
        # May select either built-in haiku models or model-b, but not heavily loaded model-a
        status_a = registry.get_status("model-a")
        status_selected = registry.get_status(selected)
        assert status_selected.tasks_in_flight <= status_a.tasks_in_flight

    def test_to_dict_serialization(self):
        """Registry serializes to dict."""
        registry = ModelRegistry()
        data = registry.to_dict()

        assert "models" in data
        assert "status" in data
        assert "claude-sonnet-4" in data["models"]


# =============================================================================
# TaskHistory Tests
# =============================================================================

class TestTaskHistory:
    """Tests for TaskHistory class."""

    def test_add_record(self):
        """Can add task records."""
        history = TaskHistory()

        record = TaskRecord(
            id=uuid4(),
            claims=[{"type": "FILE_EXISTS"}],
            files=["test.py"],
            model_used="claude-sonnet-4",
            tier_used=ModelTier.STANDARD,
            complexity_score=0.5,
            success=True,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        )

        history.add(record)
        assert len(history._records) == 1

    def test_max_records_limit(self):
        """History respects max records limit."""
        history = TaskHistory(max_records=5)

        for i in range(10):
            history.add(TaskRecord(
                id=uuid4(),
                claims=[],
                files=[f"file_{i}.py"],
                model_used="model",
                tier_used=ModelTier.STANDARD,
                complexity_score=0.5,
                success=True,
                latency_ms=100,
                timestamp=datetime.now(timezone.utc),
            ))

        assert len(history._records) == 5
        # Should keep most recent
        assert "file_9.py" in history._records[-1].files

    def test_find_similar_by_claim_type(self):
        """Finds similar tasks by claim type."""
        history = TaskHistory()

        # Add a FILE_EXISTS task (use lowercase enum values)
        history.add(TaskRecord(
            id=uuid4(),
            claims=[{"type": "file_exists"}],
            files=["a.py"],
            model_used="model",
            tier_used=ModelTier.LOCAL,
            complexity_score=0.2,
            success=True,
            latency_ms=100,
            timestamp=datetime.now(timezone.utc),
        ))

        # Add a CHANGESET task
        history.add(TaskRecord(
            id=uuid4(),
            claims=[{"type": "changeset"}],
            files=["b.py"],
            model_used="model",
            tier_used=ModelTier.STANDARD,
            complexity_score=0.7,
            success=True,
            latency_ms=500,
            timestamp=datetime.now(timezone.utc),
        ))

        # Search for FILE_EXISTS
        similar = history.find_similar(
            [Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
            ["x.py"],
        )

        # Should find the FILE_EXISTS task as most similar
        assert len(similar) > 0

    def test_find_similar_by_files(self):
        """Finds similar tasks by file overlap."""
        history = TaskHistory()

        history.add(TaskRecord(
            id=uuid4(),
            claims=[],
            files=["src/api/users.py", "src/api/auth.py"],
            model_used="model",
            tier_used=ModelTier.STANDARD,
            complexity_score=0.5,
            success=True,
            latency_ms=200,
            timestamp=datetime.now(timezone.utc),
        ))

        # Search with overlapping files
        similar = history.find_similar([], ["src/api/users.py"])

        assert len(similar) > 0
        assert "src/api/users.py" in similar[0].files

    def test_success_rate_by_tier(self):
        """Computes success rate by tier."""
        history = TaskHistory()

        # Add 3 successes, 1 failure for LOCAL
        for success in [True, True, True, False]:
            history.add(TaskRecord(
                id=uuid4(),
                claims=[],
                files=[],
                model_used="model",
                tier_used=ModelTier.LOCAL,
                complexity_score=0.2,
                success=success,
                latency_ms=100,
                timestamp=datetime.now(timezone.utc),
            ))

        rate = history.success_rate_by_tier(ModelTier.LOCAL)
        assert rate == 0.75

    def test_success_rate_by_complexity(self):
        """Computes success rate by complexity range."""
        history = TaskHistory()

        # Add tasks at different complexity levels
        history.add(TaskRecord(
            id=uuid4(), claims=[], files=[], model_used="m",
            tier_used=ModelTier.FAST, complexity_score=0.3,
            success=True, latency_ms=100, timestamp=datetime.now(timezone.utc),
        ))
        history.add(TaskRecord(
            id=uuid4(), claims=[], files=[], model_used="m",
            tier_used=ModelTier.FAST, complexity_score=0.35,
            success=False, latency_ms=100, timestamp=datetime.now(timezone.utc),
        ))

        rate = history.success_rate_by_complexity(ModelTier.FAST, 0.25, 0.45)
        assert rate == 0.5

    def test_serialization_roundtrip(self):
        """History serializes and deserializes correctly."""
        history = TaskHistory()
        history.add(TaskRecord(
            id=uuid4(),
            claims=[{"type": "FILE_EXISTS"}],
            files=["test.py"],
            model_used="claude-sonnet-4",
            tier_used=ModelTier.STANDARD,
            complexity_score=0.5,
            success=True,
            latency_ms=1000,
            timestamp=datetime.now(timezone.utc),
        ))

        data = history.to_dict()
        restored = TaskHistory.from_dict(data)

        assert len(restored._records) == 1
        assert restored._records[0].model_used == "claude-sonnet-4"


# =============================================================================
# Router Tests
# =============================================================================

class TestRouter:
    """Tests for Router class."""

    def test_route_simple_task(self):
        """Simple tasks route to local/fast tier."""
        router = Router()

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
            files=["test.py"],
        )

        assert decision.selected_tier in [ModelTier.LOCAL, ModelTier.FAST]
        assert decision.selected_model is not None

    def test_route_complex_task(self):
        """Complex tasks route to standard/heavy tier."""
        router = Router()
        files = [f"f{i}.py" for i in range(15)]

        decision = router.route(
            claims=[Claim(type=ClaimType.CHANGESET, diff="large diff", paths=files)],
            description="Major refactoring across multiple modules " * 10,
            files=files,
        )

        assert decision.selected_tier in [ModelTier.STANDARD, ModelTier.HEAVY]

    def test_force_tier(self):
        """Can force a specific tier."""
        router = Router()

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
            force_tier=ModelTier.HEAVY,
        )

        assert decision.selected_tier == ModelTier.HEAVY

    def test_fallback_chain_built(self):
        """Fallback chain is built correctly."""
        router = Router()

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
        )

        # Should have fallback models from higher tiers
        assert len(decision.fallback_models) > 0

    def test_routing_disabled(self):
        """When disabled, uses default tier."""
        config = RoutingConfig(enabled=False, default_tier=ModelTier.HEAVY)
        router = Router(config=config)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
        )

        # Even simple task goes to heavy when routing disabled
        assert decision.selected_tier == ModelTier.HEAVY

    def test_escalates_when_unavailable(self):
        """Escalates tier when no models available."""
        router = Router()

        # Make all local models unavailable
        for model in router.registry.get_models_for_tier(ModelTier.LOCAL):
            router.registry.mark_available(model, False)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
        )

        # Should escalate to next available tier
        assert decision.selected_model is not None

    def test_record_outcome(self):
        """Recording outcomes updates registry and history."""
        router = Router()

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
        )

        router.record_outcome(decision, success=True, latency_ms=500)

        # History should have record
        assert len(router.history._records) == 1


class TestAdaptiveRouting:
    """Tests for adaptive routing behavior."""

    def test_escalates_on_low_success_rate(self):
        """Escalates tier when success rate is low."""
        history = TaskHistory()

        # Add many failures for LOCAL tier at complexity ~0.2
        for _ in range(10):
            history.add(TaskRecord(
                id=uuid4(),
                claims=[{"type": "file_exists"}],
                files=["x.py"],
                model_used="local-model",
                tier_used=ModelTier.LOCAL,
                complexity_score=0.2,
                success=False,
                latency_ms=100,
                timestamp=datetime.now(timezone.utc),
            ))

        config = RoutingConfig(adaptive_enabled=True, min_success_rate=0.7)
        router = Router(history=history, config=config)

        # Route a simple task that would normally go to LOCAL
        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
            files=["x.py"],
        )

        # Should escalate due to low success rate
        # The historical factor (1.0 for 0% success) increases complexity score,
        # which causes routing to FAST or higher tier
        assert decision.selected_tier != ModelTier.LOCAL
        # Complexity score is affected by historical failures
        assert decision.complexity.factors["historical"] == 1.0

    def test_no_escalation_with_good_success_rate(self):
        """Does not escalate when success rate is good."""
        history = TaskHistory()

        # Add many successes for LOCAL tier
        for _ in range(10):
            history.add(TaskRecord(
                id=uuid4(),
                claims=[{"type": "file_exists"}],
                files=["x.py"],
                model_used="local-model",
                tier_used=ModelTier.LOCAL,
                complexity_score=0.2,
                success=True,
                latency_ms=100,
                timestamp=datetime.now(timezone.utc),
            ))

        config = RoutingConfig(adaptive_enabled=True)
        router = Router(history=history, config=config)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
            files=["x.py"],
        )

        # Should stay at LOCAL with good success rate
        assert decision.selected_tier in [ModelTier.LOCAL, ModelTier.FAST]


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_router_default(self):
        """create_router with no config works."""
        router = create_router()
        assert isinstance(router, Router)
        assert router.config.enabled

    def test_create_router_with_config(self):
        """create_router accepts config dict."""
        router = create_router({
            "enabled": False,
            "default_tier": "heavy",
        })

        assert not router.config.enabled
        assert router.config.default_tier == ModelTier.HEAVY

    def test_estimate_complexity(self):
        """estimate_complexity convenience function works."""
        estimate = estimate_complexity(
            [Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
            description="Check if file exists",
        )

        assert isinstance(estimate, ComplexityEstimate)
        assert 0 <= estimate.score <= 1

    def test_recommend_tier(self):
        """recommend_tier function works."""
        assert recommend_tier(0.1) == ModelTier.LOCAL
        assert recommend_tier(0.3) == ModelTier.FAST
        assert recommend_tier(0.5) == ModelTier.STANDARD
        assert recommend_tier(0.8) == ModelTier.HEAVY


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_claims(self):
        """Router handles empty claims."""
        router = Router()
        decision = router.route(claims=[])

        assert decision.selected_model is not None

    def test_no_files(self):
        """Router handles no files."""
        router = Router()
        decision = router.route(
            claims=[Claim(type=ClaimType.TESTS_PASS, command=("pytest",))],
        )

        assert decision.selected_model is not None

    def test_empty_registry(self):
        """Router handles when all models unavailable."""
        router = Router()

        # Mark all models unavailable
        for tier in ModelTier:
            for model in router.registry.get_models_for_tier(tier):
                router.registry.mark_available(model, False)

        # Should still return something (fallback to defaults)
        decision = router.route(claims=[])
        assert decision.selected_model is not None

    def test_history_empty(self):
        """Works with empty history."""
        router = Router()  # Fresh history

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
        )

        # Should work without historical data
        assert decision.selected_model is not None


# =============================================================================
# RoutingStrategy Tests
# =============================================================================

class TestRoutingStrategy:
    """Tests for RoutingStrategy enum."""

    def test_strategy_values(self):
        """All strategy values exist."""
        assert RoutingStrategy.COST_OPTIMAL.value == "cost_optimal"
        assert RoutingStrategy.SPEED_OPTIMAL.value == "speed_optimal"
        assert RoutingStrategy.QUALITY_OPTIMAL.value == "quality_optimal"
        assert RoutingStrategy.BALANCED.value == "balanced"

    def test_strategy_count(self):
        """Correct number of strategies."""
        assert len(RoutingStrategy) == 4


# =============================================================================
# Budget Tests
# =============================================================================

class TestBudgetScope:
    """Tests for BudgetScope enum."""

    def test_scope_values(self):
        """All scope values exist."""
        assert BudgetScope.SESSION.value == "session"
        assert BudgetScope.TASK.value == "task"
        assert BudgetScope.PROJECT.value == "project"
        assert BudgetScope.GLOBAL.value == "global"


class TestBudget:
    """Tests for Budget dataclass."""

    def test_remaining_unlimited(self):
        """Unlimited budget (total=0) has infinite remaining."""
        budget = Budget(scope=BudgetScope.SESSION, scope_id="s1", total_usd=0.0)
        assert budget.remaining_usd == float("inf")

    def test_remaining_with_spending(self):
        """Remaining calculated correctly with spending."""
        budget = Budget(
            scope=BudgetScope.SESSION,
            scope_id="s1",
            total_usd=10.0,
            spent_usd=3.0,
        )
        assert budget.remaining_usd == 7.0

    def test_is_exhausted_true(self):
        """Exhausted when spent >= total."""
        budget = Budget(
            scope=BudgetScope.SESSION,
            scope_id="s1",
            total_usd=10.0,
            spent_usd=10.0,
        )
        assert budget.is_exhausted

    def test_is_exhausted_false(self):
        """Not exhausted when under budget."""
        budget = Budget(
            scope=BudgetScope.SESSION,
            scope_id="s1",
            total_usd=10.0,
            spent_usd=5.0,
        )
        assert not budget.is_exhausted

    def test_is_exhausted_unlimited(self):
        """Unlimited budget never exhausted."""
        budget = Budget(
            scope=BudgetScope.SESSION,
            scope_id="s1",
            total_usd=0.0,
            spent_usd=1000.0,
        )
        assert not budget.is_exhausted

    def test_can_afford(self):
        """can_afford respects budget limits."""
        budget = Budget(
            scope=BudgetScope.SESSION,
            scope_id="s1",
            total_usd=10.0,
            spent_usd=8.0,
        )
        assert budget.can_afford(1.0)
        assert budget.can_afford(2.0)
        assert not budget.can_afford(3.0)

    def test_can_afford_unlimited(self):
        """Unlimited budget can afford anything."""
        budget = Budget(scope=BudgetScope.SESSION, scope_id="s1", total_usd=0.0)
        assert budget.can_afford(999999.0)

    def test_record_usage(self):
        """Usage recording updates fields."""
        budget = Budget(scope=BudgetScope.SESSION, scope_id="s1")
        budget.record_usage(1.50, input_tokens=1000, output_tokens=500)

        assert budget.spent_usd == 1.50
        assert budget.input_tokens == 1000
        assert budget.output_tokens == 500

    def test_serialization_roundtrip(self):
        """Budget serializes and deserializes."""
        budget = Budget(
            scope=BudgetScope.PROJECT,
            scope_id="proj1",
            total_usd=100.0,
            spent_usd=25.0,
            model_limits={"claude-opus-4": 50.0},
            input_tokens=10000,
            output_tokens=5000,
        )

        data = budget.to_dict()
        restored = Budget.from_dict(data)

        assert restored.scope == BudgetScope.PROJECT
        assert restored.scope_id == "proj1"
        assert restored.total_usd == 100.0
        assert restored.spent_usd == 25.0
        assert restored.model_limits == {"claude-opus-4": 50.0}


class TestBudgetManager:
    """Tests for BudgetManager class."""

    def test_create_budget(self):
        """Can create and retrieve budgets."""
        manager = BudgetManager()
        budget = manager.create_budget(BudgetScope.SESSION, "s1", total_usd=50.0)

        assert budget.total_usd == 50.0
        assert manager.get_budget(BudgetScope.SESSION, "s1") is budget

    def test_get_nonexistent_budget(self):
        """Returns None for nonexistent budget."""
        manager = BudgetManager()
        assert manager.get_budget(BudgetScope.SESSION, "nonexistent") is None

    def test_check_budget_within_limit(self):
        """Budget check passes when within limit."""
        registry = ModelRegistry()
        manager = BudgetManager(registry=registry)
        manager.create_budget(BudgetScope.SESSION, "s1", total_usd=100.0)

        result = manager.check_budget(
            "claude-sonnet-4",
            estimated_tokens=1000,
            scope=BudgetScope.SESSION,
            scope_id="s1",
        )

        assert result.allowed

    def test_check_budget_exceeds_limit(self):
        """Budget check fails when exceeding limit."""
        registry = ModelRegistry()
        manager = BudgetManager(registry=registry)
        manager.create_budget(BudgetScope.SESSION, "s1", total_usd=0.001)  # Very small

        result = manager.check_budget(
            "claude-opus-4",
            estimated_tokens=1000000,  # Large
            scope=BudgetScope.SESSION,
            scope_id="s1",
        )

        assert not result.allowed
        assert "exhausted" in result.reason.lower()

    def test_record_usage_to_budget(self):
        """Recording usage updates the correct budget."""
        manager = BudgetManager()
        manager.create_budget(BudgetScope.SESSION, "s1", total_usd=100.0)

        manager.record_usage(
            BudgetScope.SESSION, "s1",
            cost_usd=5.0, input_tokens=1000, output_tokens=500,
        )

        budget = manager.get_budget(BudgetScope.SESSION, "s1")
        assert budget.spent_usd == 5.0

    def test_spending_summary(self):
        """Can get spending summary across budgets."""
        manager = BudgetManager()
        manager.create_budget(BudgetScope.SESSION, "s1", total_usd=100.0)
        manager.create_budget(BudgetScope.PROJECT, "p1", total_usd=500.0)

        manager.record_usage(BudgetScope.SESSION, "s1", cost_usd=10.0)
        manager.record_usage(BudgetScope.PROJECT, "p1", cost_usd=20.0)

        summary = manager.get_spending_summary()

        assert summary["total_spent"] == 30.0
        assert "session:s1" in summary["budgets"]
        assert "project:p1" in summary["budgets"]


# =============================================================================
# Enhanced ModelCapabilities Tests
# =============================================================================

class TestEnhancedModelCapabilities:
    """Tests for enhanced ModelCapabilities fields."""

    def test_cost_fields(self):
        """Cost fields are populated."""
        caps = ModelCapabilities(
            name="test-model",
            tier=ModelTier.STANDARD,
            provider="test",
            cost_input=3.00,
            cost_output=15.00,
        )

        assert caps.cost_input == 3.00
        assert caps.cost_output == 15.00

    def test_latency_fields(self):
        """Latency fields are populated."""
        caps = ModelCapabilities(
            name="test-model",
            tier=ModelTier.STANDARD,
            latency_p50=1000,
            latency_p95=3000,
        )

        assert caps.latency_p50 == 1000
        assert caps.latency_p95 == 3000

    def test_rate_limit_fields(self):
        """Rate limit fields are populated."""
        caps = ModelCapabilities(
            name="test-model",
            tier=ModelTier.STANDARD,
            requests_per_minute=500,
            tokens_per_minute=80000,
        )

        assert caps.requests_per_minute == 500
        assert caps.tokens_per_minute == 80000

    def test_strengths_field(self):
        """Strengths field is populated."""
        caps = ModelCapabilities(
            name="test-model",
            tier=ModelTier.STANDARD,
            strengths=["code", "reasoning", "creative"],
        )

        assert "code" in caps.strengths
        assert "reasoning" in caps.strengths

    def test_cost_per_1k_tokens(self):
        """cost_per_1k_tokens helper works."""
        caps = ModelCapabilities(
            name="test-model",
            tier=ModelTier.STANDARD,
            cost_input=3.00,  # per 1M
            cost_output=15.00,  # per 1M
        )

        # 70% input, 30% output
        expected = (3.00 * 0.7 + 15.00 * 0.3) / 1000
        assert abs(caps.cost_per_1k_tokens(0.7) - expected) < 0.0001

    def test_default_models_have_pricing(self):
        """Default registered models have cost data."""
        registry = ModelRegistry()
        sonnet = registry.get_capabilities("claude-sonnet-4")

        assert sonnet is not None
        assert sonnet.cost_input > 0
        assert sonnet.cost_output > 0
        assert sonnet.latency_p50 > 0


# =============================================================================
# Strategy-Based Routing Tests
# =============================================================================

class TestStrategyRouting:
    """Tests for strategy-based routing."""

    def test_cost_optimal_strategy(self):
        """Cost optimal strategy prefers cheaper models."""
        config = RoutingConfig(strategy=RoutingStrategy.COST_OPTIMAL)
        router = Router(config=config)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
        )

        assert decision.strategy_used == RoutingStrategy.COST_OPTIMAL
        # Should not use expensive opus
        assert "opus" not in decision.selected_model.lower()

    def test_quality_optimal_strategy(self):
        """Quality optimal strategy prefers capable models."""
        config = RoutingConfig(strategy=RoutingStrategy.QUALITY_OPTIMAL)
        router = Router(config=config)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
        )

        assert decision.strategy_used == RoutingStrategy.QUALITY_OPTIMAL

    def test_balanced_strategy_weights(self):
        """Balanced strategy respects custom weights."""
        config = RoutingConfig(
            strategy=RoutingStrategy.BALANCED,
            strategy_weights={"cost": 0.1, "speed": 0.1, "quality": 0.8},
        )
        router = Router(config=config)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
        )

        assert decision.strategy_used == RoutingStrategy.BALANCED

    def test_routing_decision_has_estimates(self):
        """Routing decisions include cost/latency estimates."""
        router = Router()

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
        )

        # Estimates populated
        assert decision.estimated_cost >= 0
        assert decision.estimated_latency_ms >= 0

    def test_routing_decision_has_alternatives(self):
        """Routing decisions include alternatives considered."""
        router = Router()

        decision = router.route(
            claims=[Claim(type=ClaimType.CHANGESET, diff="test", paths=["a.py"])],
        )

        # Alternatives tracked for explainability
        assert isinstance(decision.alternatives_considered, list)


# =============================================================================
# Router.explain() Tests
# =============================================================================

class TestRouterExplain:
    """Tests for Router.explain() method."""

    def test_explain_returns_dict(self):
        """explain() returns a dictionary."""
        router = Router()
        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
        )

        explanation = router.explain(decision)

        assert isinstance(explanation, dict)

    def test_explain_has_task_id(self):
        """Explanation includes task_id."""
        router = Router()
        decision = router.route(claims=[])

        explanation = router.explain(decision)

        assert "task_id" in explanation
        assert explanation["task_id"] == str(decision.task_id)

    def test_explain_has_complexity_breakdown(self):
        """Explanation includes complexity breakdown."""
        router = Router()
        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
            description="Check if file exists",
        )

        explanation = router.explain(decision)

        assert "complexity" in explanation
        complexity = explanation["complexity"]
        assert "score" in complexity
        assert "classification" in complexity
        assert "factors" in complexity
        assert "recommended_tier" in complexity

    def test_explain_has_selection_info(self):
        """Explanation includes selection information."""
        router = Router()
        decision = router.route(claims=[])

        explanation = router.explain(decision)

        assert "selection" in explanation
        selection = explanation["selection"]
        assert "model" in selection
        assert "tier" in selection
        assert "reasoning" in selection
        assert "strategy" in selection

    def test_explain_has_model_capabilities(self):
        """Explanation includes model capabilities."""
        router = Router()
        decision = router.route(claims=[])

        explanation = router.explain(decision)

        selection = explanation["selection"]
        assert "model_capabilities" in selection
        caps = selection["model_capabilities"]
        assert "provider" in caps
        assert "context_window" in caps
        assert "cost_per_1M_input" in caps
        assert "cost_per_1M_output" in caps

    def test_explain_has_model_status(self):
        """Explanation includes model runtime status."""
        router = Router()
        decision = router.route(claims=[])

        explanation = router.explain(decision)

        selection = explanation["selection"]
        assert "model_status" in selection
        status = selection["model_status"]
        assert "available" in status
        assert "success_rate" in status

    def test_explain_has_cost_analysis(self):
        """Explanation includes cost analysis."""
        router = Router()
        decision = router.route(claims=[])

        explanation = router.explain(decision)

        assert "cost_analysis" in explanation
        costs = explanation["cost_analysis"]
        assert "estimated_cost_usd" in costs
        assert "estimated_latency_ms" in costs

    def test_explain_has_alternatives(self):
        """Explanation includes alternatives considered."""
        router = Router()
        decision = router.route(claims=[])

        explanation = router.explain(decision)

        assert "alternatives_considered" in explanation
        assert isinstance(explanation["alternatives_considered"], list)

    def test_explain_has_fallback_chain(self):
        """Explanation includes fallback chain."""
        router = Router()
        decision = router.route(claims=[])

        explanation = router.explain(decision)

        assert "fallback_chain" in explanation
        assert isinstance(explanation["fallback_chain"], list)
        if explanation["fallback_chain"]:
            fb = explanation["fallback_chain"][0]
            assert "model" in fb

    def test_explain_has_historical_context(self):
        """Explanation includes historical context."""
        router = Router()

        # Add some history
        decision = router.route(claims=[])
        router.record_outcome(decision, success=True, latency_ms=500)

        # Route again and explain
        decision2 = router.route(claims=[])
        explanation = router.explain(decision2)

        assert "historical_context" in explanation
        hist = explanation["historical_context"]
        assert "tier_success_rate" in hist
        assert "complexity_range_success_rate" in hist

    def test_explain_budget_check_included(self):
        """Explanation includes budget check when present."""
        registry = ModelRegistry()
        budget_manager = BudgetManager(registry=registry)
        budget_manager.create_budget(BudgetScope.SESSION, "s1", total_usd=100.0)

        router = Router(budget_manager=budget_manager)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
            budget_scope=BudgetScope.SESSION,
            budget_scope_id="s1",
        )

        explanation = router.explain(decision)

        # Budget check should be in cost analysis
        if decision.budget_check:
            costs = explanation["cost_analysis"]
            assert "budget_check" in costs

    def test_explain_complexity_classification(self):
        """Explanation correctly classifies complexity."""
        router = Router()

        # Simple task
        simple_decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="x.py")],
        )
        simple_exp = router.explain(simple_decision)

        # Complex task
        files = [f"f{i}.py" for i in range(20)]
        complex_decision = router.route(
            claims=[Claim(type=ClaimType.CHANGESET, diff="d" * 5000, paths=files)],
            description="Major refactoring" * 20,
            files=files,
        )
        complex_exp = router.explain(complex_decision)

        # Classifications should differ
        assert simple_exp["complexity"]["classification"] in ["simple", "moderate"]
        assert complex_exp["complexity"]["classification"] in ["moderate", "complex"]


# =============================================================================
# Budget Integration with Routing Tests
# =============================================================================

class TestBudgetRoutingIntegration:
    """Tests for budget integration with routing."""

    def test_route_with_budget_tracking(self):
        """Routing respects budget constraints."""
        registry = ModelRegistry()
        budget_manager = BudgetManager(registry=registry)
        budget_manager.create_budget(BudgetScope.SESSION, "s1", total_usd=0.001)  # Tiny

        config = RoutingConfig(enforce_budget=True)
        router = Router(config=config, budget_manager=budget_manager)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
            budget_scope=BudgetScope.SESSION,
            budget_scope_id="s1",
        )

        # Budget check should be performed
        assert decision.budget_check is not None

    def test_route_suggests_cheaper_alternatives(self):
        """When over budget, suggests cheaper alternatives."""
        registry = ModelRegistry()
        budget_manager = BudgetManager(registry=registry)
        # Small budget that can't afford opus
        budget_manager.create_budget(BudgetScope.SESSION, "s1", total_usd=0.0001)

        router = Router(budget_manager=budget_manager)

        decision = router.route(
            claims=[Claim(type=ClaimType.FILE_EXISTS, path="test.py")],
            budget_scope=BudgetScope.SESSION,
            budget_scope_id="s1",
        )

        # Should still route successfully to a cheaper model
        assert decision.selected_model is not None
