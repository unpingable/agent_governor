# SPDX-License-Identifier: Apache-2.0
"""Tests for jurisdictions - context-aware epistemic governance."""

import pytest

from governor.jurisdictions import (
    SpilloverPolicy,
    ContradictionPolicy,
    BudgetProfile,
    Jurisdiction,
    JurisdictionState,
    JurisdictionManager,
    create_factual_jurisdiction,
    create_speculative_jurisdiction,
    create_counterfactual_jurisdiction,
    create_adversarial_jurisdiction,
    create_narrative_jurisdiction,
    create_forensic_jurisdiction,
    create_pedagogical_jurisdiction,
    create_audit_jurisdiction,
    register_jurisdiction,
    get_jurisdiction,
    list_jurisdictions,
    get_all_jurisdictions,
    clear_jurisdictions,
    reset_to_defaults,
)
from governor.epistemic import EvidenceType


class TestSpilloverPolicy:
    """Tests for SpilloverPolicy enum."""

    def test_policy_values(self):
        """All expected policies exist."""
        assert SpilloverPolicy.BLOCKED.value == "blocked"
        assert SpilloverPolicy.PROMOTED_WITH_EVIDENCE.value == "promoted_with_evidence"
        assert SpilloverPolicy.FLAGGED_EXPORT.value == "flagged_export"
        assert SpilloverPolicy.FREE.value == "free"

    def test_policy_from_string(self):
        """Can construct policy from string."""
        assert SpilloverPolicy("blocked") == SpilloverPolicy.BLOCKED
        assert SpilloverPolicy("free") == SpilloverPolicy.FREE


class TestContradictionPolicy:
    """Tests for ContradictionPolicy enum."""

    def test_policy_values(self):
        """All expected policies exist."""
        assert ContradictionPolicy.STRICT.value == "strict"
        assert ContradictionPolicy.TOLERANT.value == "tolerant"
        assert ContradictionPolicy.EXPECTED.value == "expected"
        assert ContradictionPolicy.SCOPED.value == "scoped"


class TestBudgetProfile:
    """Tests for BudgetProfile."""

    def test_default_values(self):
        """Default profile has expected values."""
        budget = BudgetProfile()
        assert budget.claim_cost == 1.0
        assert budget.contradiction_cost == 2.0
        assert budget.refill_rate == 1.0

    def test_effective_claim_cost_no_discount(self):
        """Effective cost without discounts."""
        budget = BudgetProfile(claim_cost=2.0)
        assert budget.effective_claim_cost() == 2.0

    def test_effective_claim_cost_speculative_discount(self):
        """Speculative discount applied correctly."""
        budget = BudgetProfile(claim_cost=2.0, speculative_discount=0.5)
        assert budget.effective_claim_cost(is_speculative=True) == 1.0

    def test_effective_claim_cost_adversarial_discount(self):
        """Adversarial discount applied correctly."""
        budget = BudgetProfile(claim_cost=2.0, adversarial_discount=0.1)
        assert budget.effective_claim_cost(is_adversarial=True) == 0.2

    def test_effective_claim_cost_both_discounts(self):
        """Both discounts stack."""
        budget = BudgetProfile(claim_cost=2.0, speculative_discount=0.5, adversarial_discount=0.5)
        assert budget.effective_claim_cost(is_speculative=True, is_adversarial=True) == 0.5

    def test_serialization(self):
        """BudgetProfile serializes and deserializes correctly."""
        budget = BudgetProfile(
            claim_cost=1.5,
            contradiction_cost=3.0,
            refill_rate=2.0,
        )
        data = budget.to_dict()
        restored = BudgetProfile.from_dict(data)
        assert restored.claim_cost == budget.claim_cost
        assert restored.contradiction_cost == budget.contradiction_cost
        assert restored.refill_rate == budget.refill_rate


class TestJurisdiction:
    """Tests for Jurisdiction base class."""

    def test_default_values(self):
        """Default jurisdiction has expected values."""
        j = Jurisdiction(name="test", description="Test jurisdiction")
        assert j.name == "test"
        assert j.spillover == SpilloverPolicy.BLOCKED
        assert j.contradiction_policy == ContradictionPolicy.STRICT

    def test_admits_evidence(self):
        """admits() checks evidence type correctly."""
        j = Jurisdiction(
            name="test",
            description="Test",
            admissible_evidence={EvidenceType.TOOL_TRACE, EvidenceType.RECEIPT},
        )
        assert j.admits(EvidenceType.TOOL_TRACE)
        assert j.admits(EvidenceType.RECEIPT)
        assert not j.admits(EvidenceType.URL)

    def test_can_close_with_evidence(self):
        """can_close() works with evidence requirement."""
        j = Jurisdiction(
            name="test",
            description="Test",
            closure_allowed=True,
            closure_requires_evidence=True,
        )
        assert j.can_close(has_evidence=True)
        assert not j.can_close(has_evidence=False)

    def test_can_close_without_evidence_requirement(self):
        """can_close() works without evidence requirement."""
        j = Jurisdiction(
            name="test",
            description="Test",
            closure_allowed=True,
            closure_requires_evidence=False,
        )
        assert j.can_close(has_evidence=True)
        assert j.can_close(has_evidence=False)

    def test_can_close_not_allowed(self):
        """can_close() returns False when closure not allowed."""
        j = Jurisdiction(
            name="test",
            description="Test",
            closure_allowed=False,
        )
        assert not j.can_close(has_evidence=True)
        assert not j.can_close(has_evidence=False)

    def test_can_export(self):
        """can_export() checks export rules."""
        j = Jurisdiction(
            name="test",
            description="Test",
            export_to_factual_allowed=True,
            export_requires_promotion=True,
        )
        assert j.can_export(has_promotion_evidence=True)
        assert not j.can_export(has_promotion_evidence=False)

    def test_can_export_not_allowed(self):
        """can_export() returns False when export not allowed."""
        j = Jurisdiction(
            name="test",
            description="Test",
            export_to_factual_allowed=False,
        )
        assert not j.can_export(has_promotion_evidence=True)

    def test_tolerates_contradiction(self):
        """tolerates_contradiction() works correctly."""
        strict = Jurisdiction(
            name="strict",
            description="Strict",
            contradiction_policy=ContradictionPolicy.STRICT,
        )
        tolerant = Jurisdiction(
            name="tolerant",
            description="Tolerant",
            contradiction_policy=ContradictionPolicy.TOLERANT,
        )
        expected = Jurisdiction(
            name="expected",
            description="Expected",
            contradiction_policy=ContradictionPolicy.EXPECTED,
        )
        assert not strict.tolerates_contradiction()
        assert tolerant.tolerates_contradiction()
        assert expected.tolerates_contradiction()

    def test_serialization(self):
        """Jurisdiction serializes and deserializes correctly."""
        j = Jurisdiction(
            name="test",
            description="Test jurisdiction",
            admissible_evidence={EvidenceType.TOOL_TRACE, EvidenceType.RECEIPT},
            spillover=SpilloverPolicy.FLAGGED_EXPORT,
            contradiction_policy=ContradictionPolicy.TOLERANT,
            output_label="[TEST]",
        )
        data = j.to_dict()
        restored = Jurisdiction.from_dict(data)

        assert restored.name == j.name
        assert restored.description == j.description
        assert restored.admissible_evidence == j.admissible_evidence
        assert restored.spillover == j.spillover
        assert restored.contradiction_policy == j.contradiction_policy
        assert restored.output_label == j.output_label


class TestStandardJurisdictions:
    """Tests for standard jurisdiction factories."""

    def test_factual_jurisdiction(self):
        """Factual jurisdiction has correct properties."""
        j = create_factual_jurisdiction()
        assert j.name == "factual"
        assert j.contradiction_policy == ContradictionPolicy.STRICT
        assert j.spillover == SpilloverPolicy.FREE
        assert j.closure_allowed
        assert j.closure_requires_evidence
        assert j.output_label is None

    def test_speculative_jurisdiction(self):
        """Speculative jurisdiction has correct properties."""
        j = create_speculative_jurisdiction()
        assert j.name == "speculative"
        assert j.contradiction_policy == ContradictionPolicy.TOLERANT
        assert not j.closure_allowed  # KEY: cannot commit
        assert j.export_to_factual_allowed
        assert j.export_requires_promotion
        assert j.output_label == "[SPECULATIVE]"

    def test_adversarial_jurisdiction(self):
        """Adversarial jurisdiction has correct properties."""
        j = create_adversarial_jurisdiction()
        assert j.name == "adversarial"
        assert j.contradiction_policy == ContradictionPolicy.EXPECTED
        assert j.contradiction_tolerance == 1.0
        assert not j.closure_allowed
        assert not j.export_to_factual_allowed
        assert j.budget.resolution_cost == 100.0  # Blocked by cost
        assert j.output_label == "[ADVERSARIAL - NOT ENDORSED]"

    def test_narrative_jurisdiction(self):
        """Narrative jurisdiction has correct properties."""
        j = create_narrative_jurisdiction()
        assert j.name == "narrative"
        assert EvidenceType.NARRATIVE_CONSISTENCY in j.admissible_evidence
        assert j.contradiction_policy == ContradictionPolicy.STRICT  # Plot consistency
        assert j.closure_allowed  # Canon can be established
        assert j.output_label == "[FICTION]"

    def test_forensic_jurisdiction(self):
        """Forensic jurisdiction has correct properties."""
        j = create_forensic_jurisdiction()
        assert j.name == "forensic"
        assert EvidenceType.CROSS_SOURCE in j.admissible_evidence
        assert j.contradiction_policy == ContradictionPolicy.TOLERANT
        assert j.spillover == SpilloverPolicy.FLAGGED_EXPORT

    def test_pedagogical_jurisdiction(self):
        """Pedagogical jurisdiction has correct properties."""
        j = create_pedagogical_jurisdiction()
        assert j.name == "pedagogical"
        assert EvidenceType.PEDAGOGICAL_FRAME in j.admissible_evidence
        assert j.output_label == "[PEDAGOGICAL - SIMPLIFIED]"

    def test_counterfactual_jurisdiction(self):
        """Counterfactual jurisdiction has correct properties."""
        j = create_counterfactual_jurisdiction()
        assert j.name == "counterfactual"
        assert j.contradiction_policy == ContradictionPolicy.SCOPED
        assert j.closure_allowed
        assert not j.closure_requires_evidence  # Premise is evidence
        assert not j.export_to_factual_allowed

    def test_audit_jurisdiction(self):
        """Audit jurisdiction has correct properties."""
        j = create_audit_jurisdiction()
        assert j.name == "audit"
        assert j.spillover == SpilloverPolicy.FREE
        assert len(j.admissible_evidence) >= 6  # Many types
        assert j.output_label == "[AUDIT TRAIL]"


class TestJurisdictionRegistry:
    """Tests for jurisdiction registry functions."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_to_defaults()

    def test_list_jurisdictions(self):
        """list_jurisdictions returns all defaults."""
        names = list_jurisdictions()
        assert "factual" in names
        assert "speculative" in names
        assert "adversarial" in names
        assert len(names) == 8

    def test_get_jurisdiction(self):
        """get_jurisdiction returns correct jurisdiction."""
        j = get_jurisdiction("factual")
        assert j is not None
        assert j.name == "factual"

    def test_get_jurisdiction_unknown(self):
        """get_jurisdiction returns None for unknown name."""
        j = get_jurisdiction("unknown")
        assert j is None

    def test_register_custom_jurisdiction(self):
        """Can register custom jurisdictions."""
        custom = Jurisdiction(
            name="custom",
            description="Custom jurisdiction",
        )
        register_jurisdiction(custom)
        assert "custom" in list_jurisdictions()
        assert get_jurisdiction("custom") is not None

    def test_clear_jurisdictions(self):
        """clear_jurisdictions removes all."""
        clear_jurisdictions()
        assert len(list_jurisdictions()) == 0

    def test_reset_to_defaults(self):
        """reset_to_defaults restores all defaults."""
        clear_jurisdictions()
        reset_to_defaults()
        assert len(list_jurisdictions()) == 8

    def test_get_all_jurisdictions(self):
        """get_all_jurisdictions returns dict."""
        all_j = get_all_jurisdictions()
        assert isinstance(all_j, dict)
        assert "factual" in all_j
        assert all_j["factual"].name == "factual"


class TestJurisdictionState:
    """Tests for JurisdictionState."""

    def test_initial_state(self):
        """Initial state has expected values."""
        j = create_factual_jurisdiction()
        state = JurisdictionState(jurisdiction=j)
        assert state.current_budget == 100.0
        assert state.claims_made == 0

    def test_consume_budget_success(self):
        """consume_budget works when budget available."""
        j = create_factual_jurisdiction()
        state = JurisdictionState(jurisdiction=j, current_budget=50.0)
        assert state.consume_budget(10.0)
        assert state.current_budget == 40.0

    def test_consume_budget_insufficient(self):
        """consume_budget fails when insufficient."""
        j = create_factual_jurisdiction()
        state = JurisdictionState(jurisdiction=j, current_budget=5.0)
        assert not state.consume_budget(10.0)
        assert state.current_budget == 5.0  # Unchanged

    def test_refill_budget(self):
        """refill_budget increases by refill_rate."""
        j = create_speculative_jurisdiction()  # refill_rate = 2.0
        state = JurisdictionState(jurisdiction=j, current_budget=50.0)
        new_budget = state.refill_budget()
        assert new_budget == 52.0
        assert state.current_budget == 52.0

    def test_refill_budget_capped(self):
        """refill_budget is capped at 200."""
        j = create_factual_jurisdiction()
        state = JurisdictionState(jurisdiction=j, current_budget=199.5)
        state.refill_budget()
        assert state.current_budget == 200.0

    def test_record_operations(self):
        """Record functions increment counters."""
        j = create_factual_jurisdiction()
        state = JurisdictionState(jurisdiction=j)

        state.record_claim()
        assert state.claims_made == 1

        state.record_contradiction_opened()
        assert state.contradictions_opened == 1

        state.record_contradiction_resolved()
        assert state.contradictions_resolved == 1

        state.record_export()
        assert state.exports_made == 1

    def test_serialization(self):
        """JurisdictionState serializes correctly."""
        j = create_factual_jurisdiction()
        state = JurisdictionState(
            jurisdiction=j,
            current_budget=75.0,
            claims_made=5,
        )
        data = state.to_dict()
        assert data["jurisdiction"] == "factual"
        assert data["current_budget"] == 75.0
        assert data["claims_made"] == 5


class TestJurisdictionManager:
    """Tests for JurisdictionManager."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_to_defaults()

    def test_initial_state(self):
        """Manager starts in factual by default."""
        manager = JurisdictionManager()
        assert manager.current_jurisdiction.name == "factual"

    def test_initial_state_custom(self):
        """Manager can start in custom jurisdiction."""
        manager = JurisdictionManager("speculative")
        assert manager.current_jurisdiction.name == "speculative"

    def test_switch_jurisdiction(self):
        """Can switch jurisdictions."""
        manager = JurisdictionManager("factual")
        success, msg = manager.switch_jurisdiction("speculative")
        assert success
        assert manager.current_jurisdiction.name == "speculative"
        assert "[SPECULATIVE]" == manager.current_jurisdiction.output_label

    def test_switch_jurisdiction_unknown(self):
        """Switching to unknown jurisdiction fails."""
        manager = JurisdictionManager()
        success, msg = manager.switch_jurisdiction("unknown")
        assert not success
        assert "Unknown" in msg

    def test_switch_jurisdiction_same(self):
        """Switching to same jurisdiction succeeds."""
        manager = JurisdictionManager("factual")
        success, msg = manager.switch_jurisdiction("factual")
        assert success
        assert "Already" in msg

    def test_switch_preserves_some_budget(self):
        """Switching preserves 50% budget."""
        manager = JurisdictionManager("factual")
        manager.current_state.current_budget = 80.0
        manager.switch_jurisdiction("speculative")
        # 50% of 80 = 40, but speculative has min 10 * refill_rate = 20
        assert manager.current_budget >= 40.0

    def test_switch_records_history(self):
        """Switching records transition history."""
        manager = JurisdictionManager("factual")
        manager.switch_jurisdiction("speculative")
        manager.switch_jurisdiction("adversarial")
        assert len(manager.history) == 2
        assert manager.history[0]["from"] == "factual"
        assert manager.history[0]["to"] == "speculative"

    def test_can_make_claim(self):
        """can_make_claim checks budget."""
        manager = JurisdictionManager("factual")
        can, msg = manager.can_make_claim()
        assert can

        manager.current_state.current_budget = 0.5
        can, msg = manager.can_make_claim()
        assert not can

    def test_make_claim_consumes_budget(self):
        """make_claim consumes budget and records."""
        manager = JurisdictionManager("factual")
        initial = manager.current_budget
        success, msg = manager.make_claim()
        assert success
        assert manager.current_budget < initial
        assert manager.current_state.claims_made == 1

    def test_speculative_claims_cheaper(self):
        """Speculative claims are cheaper in speculative mode."""
        manager = JurisdictionManager("speculative")
        initial = manager.current_budget
        manager.make_claim(is_speculative=True)
        cost = initial - manager.current_budget
        # Speculative has claim_cost=0.5 and speculative_discount=0.5 = 0.25
        assert cost == 0.25

    def test_can_open_contradiction_strict(self):
        """Strict jurisdiction blocks contradictions."""
        manager = JurisdictionManager("factual")
        # Factual has STRICT policy - contradictions are blocked
        can, msg = manager.can_open_contradiction()
        assert not can
        assert "block" in msg.lower()

    def test_can_open_contradiction_tolerant(self):
        """Tolerant jurisdiction allows contradictions."""
        manager = JurisdictionManager("speculative")
        can, msg = manager.can_open_contradiction()
        assert can

    def test_can_resolve_contradiction_adversarial(self):
        """Adversarial blocks resolution by high cost."""
        manager = JurisdictionManager("adversarial")
        can, msg = manager.can_resolve_contradiction()
        assert not can
        assert "blocked by cost" in msg.lower() or "not allowed" in msg.lower()

    def test_can_export_to_factual(self):
        """Export rules work correctly."""
        # From speculative - needs evidence
        manager = JurisdictionManager("speculative")
        can, _ = manager.can_export_to_factual(has_evidence=False)
        assert not can
        can, _ = manager.can_export_to_factual(has_evidence=True)
        assert can

        # From adversarial - blocked entirely
        manager = JurisdictionManager("adversarial")
        can, _ = manager.can_export_to_factual(has_evidence=True)
        assert not can

    def test_tick_refills_budget(self):
        """tick() refills budget."""
        manager = JurisdictionManager("speculative")
        manager.current_state.current_budget = 50.0
        new_budget = manager.tick()
        assert new_budget > 50.0

    def test_get_status(self):
        """get_status returns expected fields."""
        manager = JurisdictionManager("factual")
        manager.make_claim()
        status = manager.get_status()

        assert status["jurisdiction"] == "factual"
        assert "budget" in status
        assert status["stats"]["claims_made"] == 1

    def test_serialization(self):
        """Manager serializes and deserializes correctly."""
        manager = JurisdictionManager("speculative")
        manager.make_claim()
        manager.make_claim()
        manager.switch_jurisdiction("adversarial")

        data = manager.to_dict()
        restored = JurisdictionManager.from_dict(data)

        assert restored.current_jurisdiction.name == "adversarial"
        assert len(restored.history) == 1


class TestJurisdictionIntegration:
    """Integration tests for jurisdiction workflows."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_to_defaults()

    def test_speculative_to_factual_workflow(self):
        """Test promoting speculative claims to factual."""
        manager = JurisdictionManager("speculative")

        # Make some speculative claims
        for _ in range(5):
            manager.make_claim(is_speculative=True)

        # Try to export without evidence - should fail
        can, _ = manager.can_export_to_factual(has_evidence=False)
        assert not can

        # Export with evidence - should succeed
        success, _ = manager.export_to_factual(has_evidence=True)
        assert success
        assert manager.current_state.exports_made == 1

    def test_adversarial_stress_test(self):
        """Test adversarial mode for stress testing."""
        manager = JurisdictionManager("adversarial")

        # Claims are very cheap in adversarial
        initial = manager.current_budget
        for _ in range(20):
            manager.make_claim(is_adversarial=True)

        # Should have consumed very little budget
        consumed = initial - manager.current_budget
        assert consumed < 5.0  # 20 * 0.1 * 0.1 = 0.2

        # Contradictions are expected
        assert manager.current_jurisdiction.tolerates_contradiction()

        # Cannot resolve (blocked by cost)
        can, _ = manager.can_resolve_contradiction()
        assert not can

        # Cannot export to factual
        can, _ = manager.can_export_to_factual(has_evidence=True)
        assert not can

    def test_forensic_investigation(self):
        """Test forensic mode requiring cross-source evidence."""
        manager = JurisdictionManager("forensic")
        j = manager.current_jurisdiction

        # Cross-source evidence is admissible
        assert j.admits(EvidenceType.CROSS_SOURCE)

        # Contradictions are tolerated (they're clues)
        assert j.tolerates_contradiction()

        # Can export findings (flagged)
        assert j.spillover == SpilloverPolicy.FLAGGED_EXPORT

    def test_budget_pressure_across_jurisdictions(self):
        """Test that budget creates natural limits."""
        manager = JurisdictionManager("factual")

        # Drain budget
        while manager.current_budget >= 1.0:
            manager.make_claim()

        # Can't make more claims
        can, msg = manager.can_make_claim()
        assert not can
        assert "Insufficient" in msg

        # Tick refills
        manager.tick()
        can, _ = manager.can_make_claim()
        assert can

    def test_output_labels_applied(self):
        """Test that output labels are correctly set."""
        assert create_factual_jurisdiction().output_label is None
        assert create_speculative_jurisdiction().output_label == "[SPECULATIVE]"
        assert create_adversarial_jurisdiction().output_label == "[ADVERSARIAL - NOT ENDORSED]"
        assert create_narrative_jurisdiction().output_label == "[FICTION]"
        assert create_pedagogical_jurisdiction().output_label == "[PEDAGOGICAL - SIMPLIFIED]"
