# SPDX-License-Identifier: Apache-2.0
"""
Tests for the Scars module: Failure Provenance & Constraint Hysteresis.

Tests cover:
- FailureProvenance enum
- Scar dataclass (creation, stiffness, annealing, retighten)
- Shield dataclass (creation, permeability, tighten/relax/release)
- FailureEvent (creation, serialization)
- ScarConfig (defaults, custom, serialization)
- ScarLedger (classify, record, admissibility, annealing, shielding, metrics)
- Convenience functions
- Edge cases
"""

import json
import math
from pathlib import Path

import pytest
from datetime import datetime, timezone

from governor.scars import (
    FailureProvenance,
    Scar,
    Shield,
    FailureEvent,
    ScarConfig,
    ScarLedger,
    MAX_STIFFNESS,
    MIN_STIFFNESS,
    DEFAULT_ANNEAL_FLOOR,
    create_scar_ledger,
    classify_failure,
)


# =============================================================================
# FailureProvenance
# =============================================================================


class TestFailureProvenance:
    def test_values(self):
        assert FailureProvenance.INTERNAL.value == "internal"
        assert FailureProvenance.EXTERNAL.value == "external"
        assert FailureProvenance.AMBIGUOUS.value == "ambiguous"

    def test_from_string(self):
        assert FailureProvenance("internal") == FailureProvenance.INTERNAL
        assert FailureProvenance("external") == FailureProvenance.EXTERNAL
        assert FailureProvenance("ambiguous") == FailureProvenance.AMBIGUOUS

    def test_is_str_enum(self):
        assert isinstance(FailureProvenance.INTERNAL, str)
        assert FailureProvenance.INTERNAL == "internal"


# =============================================================================
# Scar
# =============================================================================


class TestScar:
    def test_default_creation(self):
        scar = Scar(scar_id="sc_001", region="src/api/users.py")
        assert scar.stiffness == MAX_STIFFNESS
        assert scar.is_hard
        assert not scar.is_soft
        assert scar.provenance == FailureProvenance.INTERNAL

    def test_stiffness_clamping(self):
        scar = Scar(scar_id="sc_001", region="r", stiffness=5.0)
        assert scar.stiffness == MAX_STIFFNESS

        scar2 = Scar(scar_id="sc_002", region="r", stiffness=-1.0)
        assert scar2.stiffness == MIN_STIFFNESS

    def test_is_hard_vs_soft(self):
        hard = Scar(scar_id="sc_001", region="r", stiffness=1.0)
        assert hard.is_hard
        assert not hard.is_soft

        soft = Scar(scar_id="sc_002", region="r", stiffness=0.5)
        assert not soft.is_hard
        assert soft.is_soft

    def test_effective_cost(self):
        # Stiffness 1.0 -> cost 10.0
        scar = Scar(scar_id="sc_001", region="r", stiffness=1.0)
        assert abs(scar.effective_cost - 10.0) < 0.01

        # Stiffness 0.0 -> cost 1.0 (but stiffness clamped to MIN_STIFFNESS)
        scar2 = Scar(scar_id="sc_002", region="r", stiffness=MIN_STIFFNESS)
        assert scar2.effective_cost > 1.0
        assert scar2.effective_cost < 2.0

    def test_can_anneal_needs_evidence(self):
        scar = Scar(scar_id="sc_001", region="r", required_evidence=3)
        assert not scar.can_anneal()

        # Add evidence
        for _ in range(3):
            scar.record_evidence()
        assert scar.can_anneal()

    def test_can_anneal_at_floor(self):
        scar = Scar(
            scar_id="sc_001",
            region="r",
            stiffness=DEFAULT_ANNEAL_FLOOR,
            evidence_count=10,
            required_evidence=5,
        )
        assert not scar.can_anneal()  # Already at floor

    def test_anneal_reduces_stiffness(self):
        scar = Scar(
            scar_id="sc_001",
            region="r",
            stiffness=1.0,
            evidence_count=10,
            required_evidence=5,
        )

        old = scar.stiffness
        amount = scar.anneal(decay_rate=0.1)
        assert amount > 0
        assert scar.stiffness < old
        assert scar.stiffness > scar.anneal_floor
        assert scar.last_evidence_at is not None

    def test_anneal_approaches_floor_asymptotically(self):
        scar = Scar(
            scar_id="sc_001",
            region="r",
            stiffness=1.0,
            evidence_count=100,
            required_evidence=5,
            anneal_floor=0.1,
        )

        # Anneal many times
        for _ in range(100):
            scar.anneal(decay_rate=0.1)

        # Should approach but not go below floor
        assert scar.stiffness >= scar.anneal_floor
        assert scar.stiffness < 0.2  # Close to floor

    def test_anneal_without_evidence_returns_zero(self):
        scar = Scar(scar_id="sc_001", region="r", evidence_count=0, required_evidence=5)
        assert scar.anneal() == 0.0

    def test_retighten(self):
        scar = Scar(
            scar_id="sc_001",
            region="r",
            stiffness=0.5,
            evidence_count=10,
        )
        scar.retighten(amount=0.3)
        assert scar.stiffness == 0.8
        assert scar.evidence_count == 0  # Reset
        assert scar.last_tightened_at is not None

    def test_retighten_clamps_to_max(self):
        scar = Scar(scar_id="sc_001", region="r", stiffness=0.9)
        scar.retighten(amount=0.5)
        assert scar.stiffness == MAX_STIFFNESS

    def test_record_evidence(self):
        scar = Scar(scar_id="sc_001", region="r")
        assert scar.evidence_count == 0
        scar.record_evidence()
        assert scar.evidence_count == 1
        assert scar.last_evidence_at is not None

    def test_serialization_roundtrip(self):
        scar = Scar(
            scar_id="sc_001",
            region="src/api/users.py",
            stiffness=0.7,
            description="Failed validation",
            provenance=FailureProvenance.INTERNAL,
            evidence_count=3,
            failure_event_id="fe_abc",
            failure_surprise_ratio=0.15,
        )
        data = scar.to_dict()
        restored = Scar.from_dict(data)

        assert restored.scar_id == scar.scar_id
        assert restored.region == scar.region
        assert restored.stiffness == scar.stiffness
        assert restored.description == scar.description
        assert restored.provenance == scar.provenance
        assert restored.evidence_count == scar.evidence_count
        assert restored.failure_event_id == scar.failure_event_id
        assert abs(restored.failure_surprise_ratio - scar.failure_surprise_ratio) < 0.001


# =============================================================================
# Shield
# =============================================================================


class TestShield:
    def test_default_creation(self):
        shield = Shield(shield_id="sh_001", source="external_api")
        assert shield.permeability == 1.0
        assert not shield.is_blocking
        assert not shield.is_fully_blocked

    def test_permeability_clamping(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=2.0)
        assert shield.permeability == 1.0

        shield2 = Shield(shield_id="sh_002", source="s", permeability=-0.5)
        assert shield2.permeability == 0.0

    def test_is_blocking(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=0.5)
        assert shield.is_blocking
        assert not shield.is_fully_blocked

    def test_is_fully_blocked(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=0.0)
        assert shield.is_fully_blocked

    def test_tighten(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=0.8)
        shield.tighten(0.3)
        assert abs(shield.permeability - 0.5) < 0.01
        assert shield.stable_cycles_observed == 0  # Reset on tighten

    def test_tighten_clamps_to_zero(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=0.1)
        shield.tighten(0.5)
        assert shield.permeability == 0.0

    def test_relax(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=0.5)
        shield.relax(0.2)
        assert abs(shield.permeability - 0.7) < 0.01

    def test_relax_clamps_to_one(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=0.9)
        shield.relax(0.5)
        assert shield.permeability == 1.0

    def test_can_release(self):
        shield = Shield(
            shield_id="sh_001",
            source="s",
            permeability=0.5,
            stable_cycles_required=3,
        )
        assert not shield.can_release

        for _ in range(3):
            shield.record_stable_cycle()
        assert shield.can_release

    def test_release(self):
        shield = Shield(shield_id="sh_001", source="s", permeability=0.3)
        shield.release()
        assert shield.permeability == 1.0
        assert shield.last_relaxed_at is not None

    def test_record_attack_resets_stability(self):
        shield = Shield(shield_id="sh_001", source="s", stable_cycles_observed=5)
        shield.record_attack()
        assert shield.stable_cycles_observed == 0

    def test_serialization_roundtrip(self):
        shield = Shield(
            shield_id="sh_001",
            source="external_api",
            permeability=0.6,
            severity=0.8,
            stable_cycles_required=5,
            stable_cycles_observed=2,
            failure_event_id="fe_xyz",
            failure_surprise_ratio=0.9,
        )
        data = shield.to_dict()
        restored = Shield.from_dict(data)

        assert restored.shield_id == shield.shield_id
        assert restored.source == shield.source
        assert abs(restored.permeability - shield.permeability) < 0.01
        assert abs(restored.severity - shield.severity) < 0.01
        assert restored.stable_cycles_required == shield.stable_cycles_required
        assert restored.stable_cycles_observed == shield.stable_cycles_observed


# =============================================================================
# FailureEvent
# =============================================================================


class TestFailureEvent:
    def test_creation(self):
        event = FailureEvent(
            event_id="fe_001",
            region="src/api/users.py",
            description="Validation failed",
            error_magnitude=0.8,
            observation_shift=0.1,
            prediction_error=0.5,
        )
        assert event.event_id == "fe_001"
        assert event.provenance is None  # Not yet classified

    def test_serialization_roundtrip(self):
        event = FailureEvent(
            event_id="fe_001",
            region="test",
            description="test failure",
            error_magnitude=1.0,
            observation_shift=0.2,
            prediction_error=0.8,
            surprise_ratio=0.25,
            provenance=FailureProvenance.INTERNAL,
            response_type="scar",
            scar_id="sc_001",
        )
        data = event.to_dict()
        restored = FailureEvent.from_dict(data)

        assert restored.event_id == event.event_id
        assert restored.provenance == FailureProvenance.INTERNAL
        assert restored.response_type == "scar"
        assert restored.scar_id == "sc_001"
        assert abs(restored.surprise_ratio - 0.25) < 0.01


# =============================================================================
# ScarConfig
# =============================================================================


class TestScarConfig:
    def test_defaults(self):
        config = ScarConfig()
        assert config.rho_lo == 0.3
        assert config.rho_hi == 0.7
        assert config.regularity_bound == 1.0

    def test_custom(self):
        config = ScarConfig(rho_lo=0.2, rho_hi=0.8)
        assert config.rho_lo == 0.2
        assert config.rho_hi == 0.8

    def test_serialization_roundtrip(self):
        config = ScarConfig(rho_lo=0.1, rho_hi=0.9, evidence_required=10)
        data = config.to_dict()
        restored = ScarConfig.from_dict(data)
        assert restored.rho_lo == config.rho_lo
        assert restored.rho_hi == config.rho_hi
        assert restored.evidence_required == config.evidence_required


# =============================================================================
# ScarLedger - Failure Classification
# =============================================================================


class TestScarLedgerClassification:
    def test_low_rho_is_internal(self):
        """Low surprise ratio = world calm, agent failed = INTERNAL."""
        ledger = ScarLedger()
        prov, rho = ledger.classify_failure(
            observation_shift=0.1,
            prediction_error=1.0,
        )
        assert prov == FailureProvenance.INTERNAL
        assert rho < ledger.config.rho_lo

    def test_high_rho_is_external(self):
        """High surprise ratio = world jumped = EXTERNAL."""
        ledger = ScarLedger()
        prov, rho = ledger.classify_failure(
            observation_shift=0.8,
            prediction_error=1.0,
        )
        assert prov == FailureProvenance.EXTERNAL
        assert rho >= ledger.config.rho_hi

    def test_mid_rho_is_ambiguous(self):
        """Middle surprise ratio = unclear = AMBIGUOUS."""
        ledger = ScarLedger()
        prov, rho = ledger.classify_failure(
            observation_shift=0.5,
            prediction_error=1.0,
        )
        assert prov == FailureProvenance.AMBIGUOUS
        assert ledger.config.rho_lo <= rho < ledger.config.rho_hi

    def test_zero_prediction_error_with_shift_is_external(self):
        """If pred_err is 0 but world shifted, it's external."""
        ledger = ScarLedger()
        prov, rho = ledger.classify_failure(
            observation_shift=1.0,
            prediction_error=0.0,
        )
        assert prov == FailureProvenance.EXTERNAL
        assert rho == float("inf")

    def test_zero_both_is_internal(self):
        """If nothing happened and agent failed, it's internal."""
        ledger = ScarLedger()
        prov, rho = ledger.classify_failure(
            observation_shift=0.0,
            prediction_error=0.0,
        )
        assert prov == FailureProvenance.INTERNAL
        assert rho == 0.0

    def test_custom_thresholds(self):
        """Custom rho thresholds change classification."""
        config = ScarConfig(rho_lo=0.1, rho_hi=0.9)
        ledger = ScarLedger(config)

        # 0.5 would be ambiguous with defaults, but internal with low rho_lo
        prov, rho = ledger.classify_failure(0.5, 1.0)
        assert prov == FailureProvenance.AMBIGUOUS  # 0.1 <= 0.5 < 0.9

        # Very low is still internal
        prov2, _ = ledger.classify_failure(0.05, 1.0)
        assert prov2 == FailureProvenance.INTERNAL

    def test_hysteresis_band(self):
        """rho_lo < rho_hi creates a hysteresis band to prevent chatter."""
        ledger = ScarLedger()
        # Values at boundaries
        prov_lo, _ = ledger.classify_failure(0.29, 1.0)  # Just below rho_lo
        assert prov_lo == FailureProvenance.INTERNAL

        prov_hi, _ = ledger.classify_failure(0.7, 1.0)  # At rho_hi
        assert prov_hi == FailureProvenance.EXTERNAL

        prov_mid, _ = ledger.classify_failure(0.5, 1.0)  # In the band
        assert prov_mid == FailureProvenance.AMBIGUOUS


# =============================================================================
# ScarLedger - Failure Recording
# =============================================================================


class TestScarLedgerRecording:
    def test_record_internal_failure_creates_scar(self):
        """Internal failure should create a scar."""
        ledger = ScarLedger()
        event = ledger.record_failure(
            region="src/api/users.py",
            observation_shift=0.1,
            prediction_error=1.0,
            description="Validation failed",
        )

        assert event.provenance == FailureProvenance.INTERNAL
        assert event.response_type == "scar"
        assert event.scar_id is not None
        assert event.shield_id is None
        assert len(ledger.scars) == 1
        assert ledger.internal_failures == 1

    def test_record_external_failure_creates_shield(self):
        """External failure should create a shield."""
        ledger = ScarLedger()
        event = ledger.record_failure(
            region="external_api",
            observation_shift=0.9,
            prediction_error=1.0,
            source="external_api",
        )

        assert event.provenance == FailureProvenance.EXTERNAL
        assert event.response_type == "shield"
        assert event.shield_id is not None
        assert event.scar_id is None
        assert len(ledger.shields) == 1
        assert ledger.external_failures == 1

    def test_record_ambiguous_failure_prefers_shielding(self):
        """Ambiguous failure defaults to shielding (DoC-safe)."""
        ledger = ScarLedger()
        event = ledger.record_failure(
            region="uncertain_source",
            observation_shift=0.5,
            prediction_error=1.0,
        )

        assert event.provenance == FailureProvenance.AMBIGUOUS
        assert event.response_type == "ambiguous"
        assert event.shield_id is not None
        assert ledger.ambiguous_failures == 1

    def test_repeated_internal_failure_retightens_scar(self):
        """Same region failing again should retighten, not create new scar."""
        ledger = ScarLedger()

        # First failure
        event1 = ledger.record_failure(
            region="src/api/users.py",
            observation_shift=0.1,
            prediction_error=1.0,
        )

        # Partially anneal the scar
        scar = ledger.scars[event1.scar_id]
        scar.stiffness = 0.5
        scar.evidence_count = 10

        # Second failure in same region
        event2 = ledger.record_failure(
            region="src/api/users.py",
            observation_shift=0.05,
            prediction_error=1.0,
        )

        # Should reuse scar and retighten
        assert len(ledger.scars) == 1
        assert event2.scar_id == event1.scar_id
        assert scar.stiffness == MAX_STIFFNESS  # Retightened to max
        assert scar.evidence_count == 0  # Evidence reset

    def test_repeated_external_failure_tightens_shield(self):
        """Same source under repeated attack should tighten existing shield."""
        ledger = ScarLedger()

        event1 = ledger.record_failure(
            region="api",
            observation_shift=0.9,
            prediction_error=1.0,
            source="hostile_input",
        )

        shield = ledger.shields[event1.shield_id]
        initial_perm = shield.permeability

        event2 = ledger.record_failure(
            region="api",
            observation_shift=0.8,
            prediction_error=1.0,
            source="hostile_input",
        )

        assert len(ledger.shields) == 1
        assert shield.permeability < initial_perm

    def test_failure_history_recorded(self):
        ledger = ScarLedger()
        ledger.record_failure("r1", 0.1, 1.0)
        ledger.record_failure("r2", 0.9, 1.0)
        ledger.record_failure("r3", 0.5, 1.0)

        assert len(ledger.failure_history) == 3
        assert ledger.total_failures == 3

    def test_mutual_exclusivity_internal(self):
        """Internal failure creates scar but NOT shield."""
        ledger = ScarLedger()
        event = ledger.record_failure("r", 0.1, 1.0)
        assert event.scar_id is not None
        assert event.shield_id is None
        assert len(ledger.scars) == 1
        assert len(ledger.shields) == 0

    def test_mutual_exclusivity_external(self):
        """External failure creates shield but NOT scar."""
        ledger = ScarLedger()
        event = ledger.record_failure("r", 0.9, 1.0)
        assert event.shield_id is not None
        assert event.scar_id is None
        assert len(ledger.shields) == 1
        assert len(ledger.scars) == 0


# =============================================================================
# ScarLedger - Admissibility Checks
# =============================================================================


class TestScarLedgerAdmissibility:
    def test_unscarred_region_is_admissible(self):
        ledger = ScarLedger()
        admissible, cost, scar = ledger.check_admissible("src/clean.py")
        assert admissible
        assert cost == 1.0
        assert scar is None

    def test_hard_scar_blocks(self):
        """Hard scar (stiffness >= 0.95) blocks the action."""
        ledger = ScarLedger()
        ledger.record_failure("src/broken.py", 0.1, 1.0)

        admissible, cost, scar = ledger.check_admissible("src/broken.py")
        assert not admissible
        assert cost > 1.0
        assert scar is not None
        assert scar.is_hard

    def test_soft_scar_allows_with_cost(self):
        """Soft scar allows action but with increased cost."""
        ledger = ScarLedger()
        event = ledger.record_failure("src/risky.py", 0.1, 1.0)

        # Manually soften the scar
        scar = ledger.scars[event.scar_id]
        scar.stiffness = 0.5

        admissible, cost, found_scar = ledger.check_admissible("src/risky.py")
        assert admissible
        assert cost > 1.0
        assert found_scar is not None
        assert found_scar.is_soft

    def test_input_check_no_shield(self):
        ledger = ScarLedger()
        passable, perm, shield = ledger.check_input("clean_source")
        assert passable
        assert perm == 1.0
        assert shield is None

    def test_input_check_with_shield(self):
        ledger = ScarLedger()
        ledger.record_failure("api", 0.9, 1.0, source="hostile")

        passable, perm, shield = ledger.check_input("hostile")
        assert passable  # Not fully blocked yet
        assert perm < 1.0
        assert shield is not None

    def test_input_check_fully_blocked(self):
        """Repeated attacks can fully block input."""
        ledger = ScarLedger()
        # Hammer the source
        for _ in range(10):
            ledger.record_failure("api", 0.9, 1.0, source="attacker")

        passable, perm, shield = ledger.check_input("attacker")
        assert not passable
        assert perm <= 0.01


# =============================================================================
# ScarLedger - Annealing
# =============================================================================


class TestScarLedgerAnnealing:
    def test_anneal_with_evidence(self):
        """Scars relax when given enough stability evidence."""
        ledger = ScarLedger(ScarConfig(evidence_required=3))
        event = ledger.record_failure("src/api.py", 0.1, 1.0)
        scar = ledger.scars[event.scar_id]
        scar.required_evidence = 3

        # Not enough evidence yet
        results = ledger.anneal_scars()
        assert len(results) == 0

        # Add evidence
        for _ in range(3):
            ledger.record_stability_evidence("src/api.py")

        # Now annealing should work
        results = ledger.anneal_scars()
        assert len(results) == 1
        assert scar.stiffness < MAX_STIFFNESS

    def test_anneal_preserves_floor(self):
        """Annealing never goes below the floor (permanent margin)."""
        config = ScarConfig(evidence_required=1, anneal_decay_rate=0.5)
        ledger = ScarLedger(config)
        event = ledger.record_failure("r", 0.1, 1.0)
        scar = ledger.scars[event.scar_id]
        scar.required_evidence = 1

        # Add evidence and anneal many times
        for _ in range(50):
            ledger.record_stability_evidence("r")
            ledger.anneal_scars()

        assert scar.stiffness >= scar.anneal_floor

    def test_record_stability_evidence(self):
        ledger = ScarLedger()
        # No scar -> no evidence recorded
        assert not ledger.record_stability_evidence("clean")

        ledger.record_failure("scarred", 0.1, 1.0)
        assert ledger.record_stability_evidence("scarred")


# =============================================================================
# ScarLedger - Shield Relaxation
# =============================================================================


class TestScarLedgerShieldRelaxation:
    def test_shield_relaxes_over_stable_cycles(self):
        config = ScarConfig(shield_release_cycles=3)
        ledger = ScarLedger(config)
        event = ledger.record_failure("api", 0.9, 1.0, source="src")
        shield = ledger.shields[event.shield_id]
        shield.stable_cycles_required = 3

        initial_perm = shield.permeability

        # Record stable cycles
        for _ in range(3):
            ledger.record_stable_input_cycle("src")

        # Should be releasable now
        results = ledger.relax_shields()
        assert len(results) > 0
        # Shield fully released and removed
        assert len(ledger.shields) == 0

    def test_shield_gradual_relax(self):
        """Shields with some stable cycles but not enough for release get partial relax."""
        config = ScarConfig(shield_release_cycles=10, shield_relax_rate=0.1)
        ledger = ScarLedger(config)
        event = ledger.record_failure("api", 0.9, 1.0, source="src")
        shield = ledger.shields[event.shield_id]

        # Record a few stable cycles (not enough for full release)
        for _ in range(3):
            shield.record_stable_cycle()

        initial_perm = shield.permeability
        results = ledger.relax_shields()
        assert shield.permeability > initial_perm

    def test_attack_resets_shield_stability(self):
        ledger = ScarLedger()
        ledger.record_failure("api", 0.9, 1.0, source="src")

        # Build up stability
        for _ in range(5):
            ledger.record_stable_input_cycle("src")

        # Attack resets it
        ledger.record_attack("src")
        shield = ledger._find_shield_by_source("src")
        assert shield.stable_cycles_observed == 0

    def test_record_stable_cycle_no_shield(self):
        ledger = ScarLedger()
        assert not ledger.record_stable_input_cycle("clean")

    def test_record_attack_no_shield(self):
        ledger = ScarLedger()
        assert not ledger.record_attack("clean")


# =============================================================================
# ScarLedger - Queries
# =============================================================================


class TestScarLedgerQueries:
    def test_get_active_scars(self):
        ledger = ScarLedger()
        ledger.record_failure("r1", 0.1, 1.0)
        ledger.record_failure("r2", 0.05, 1.0)
        assert len(ledger.get_active_scars()) == 2

    def test_get_hard_vs_soft_scars(self):
        ledger = ScarLedger()
        e1 = ledger.record_failure("r1", 0.1, 1.0)
        e2 = ledger.record_failure("r2", 0.05, 1.0)

        # Soften one
        ledger.scars[e2.scar_id].stiffness = 0.5

        assert len(ledger.get_hard_scars()) == 1
        assert len(ledger.get_soft_scars()) == 1

    def test_get_active_shields(self):
        ledger = ScarLedger()
        ledger.record_failure("r1", 0.9, 1.0, source="s1")
        ledger.record_failure("r2", 0.8, 1.0, source="s2")

        shields = ledger.get_active_shields()
        assert len(shields) == 2

    def test_get_scar_by_id(self):
        ledger = ScarLedger()
        event = ledger.record_failure("r", 0.1, 1.0)
        scar = ledger.get_scar(event.scar_id)
        assert scar is not None
        assert scar.region == "r"

    def test_get_shield_by_id(self):
        ledger = ScarLedger()
        event = ledger.record_failure("r", 0.9, 1.0, source="s")
        shield = ledger.get_shield(event.shield_id)
        assert shield is not None
        assert shield.source == "s"

    def test_get_failure_history(self):
        ledger = ScarLedger()
        for i in range(10):
            ledger.record_failure(f"r{i}", 0.1, 1.0)

        history = ledger.get_failure_history(limit=5)
        assert len(history) == 5

    def test_get_failures_by_region(self):
        ledger = ScarLedger()
        ledger.record_failure("api", 0.1, 1.0)
        ledger.record_failure("db", 0.1, 1.0)
        ledger.record_failure("api", 0.05, 1.0)

        api_failures = ledger.get_failures_by_region("api")
        assert len(api_failures) == 2

    def test_get_scarred_regions(self):
        ledger = ScarLedger()
        ledger.record_failure("r1", 0.1, 1.0)
        ledger.record_failure("r2", 0.05, 1.0)

        regions = ledger.get_scarred_regions()
        assert "r1" in regions
        assert "r2" in regions

    def test_get_shielded_sources(self):
        ledger = ScarLedger()
        ledger.record_failure("r1", 0.9, 1.0, source="s1")
        ledger.record_failure("r2", 0.8, 1.0, source="s2")

        sources = ledger.get_shielded_sources()
        assert "s1" in sources
        assert "s2" in sources


# =============================================================================
# ScarLedger - Metrics
# =============================================================================


class TestScarLedgerMetrics:
    def test_metrics(self):
        ledger = ScarLedger()
        ledger.record_failure("r1", 0.1, 1.0)
        ledger.record_failure("r2", 0.9, 1.0, source="s2")
        ledger.record_failure("r3", 0.5, 1.0)

        metrics = ledger.get_metrics()
        assert metrics["total_failures"] == 3
        assert metrics["internal_failures"] == 1
        assert metrics["external_failures"] == 1
        assert metrics["ambiguous_failures"] == 1
        assert metrics["total_scars"] == 1
        assert metrics["total_shields"] == 2  # external + ambiguous both create shields

    def test_summary(self):
        ledger = ScarLedger()
        summary = ledger.get_summary()
        assert summary["health"] == "NOMINAL"

        ledger.record_failure("r", 0.1, 1.0)
        summary = ledger.get_summary()
        assert summary["health"] == "CONSTRAINED"

    def test_summary_cautious(self):
        ledger = ScarLedger()
        event = ledger.record_failure("r", 0.1, 1.0)
        # Soften the scar
        ledger.scars[event.scar_id].stiffness = 0.5
        summary = ledger.get_summary()
        assert summary["health"] == "CAUTIOUS"


# =============================================================================
# ScarLedger - Serialization
# =============================================================================


class TestScarLedgerSerialization:
    def test_roundtrip(self):
        ledger = ScarLedger(ScarConfig(rho_lo=0.2, rho_hi=0.8))
        ledger.record_failure("r1", 0.1, 1.0, description="internal fail")
        ledger.record_failure("r2", 0.9, 1.0, source="s2", description="external attack")
        ledger.record_failure("r3", 0.5, 1.0, description="ambiguous")

        data = ledger.to_dict()
        restored = ScarLedger.from_dict(data)

        assert restored.config.rho_lo == 0.2
        assert restored.config.rho_hi == 0.8
        assert len(restored.scars) == len(ledger.scars)
        assert len(restored.shields) == len(ledger.shields)
        assert len(restored.failure_history) == 3
        assert restored.total_failures == 3
        assert restored.internal_failures == 1
        assert restored.external_failures == 1
        assert restored.ambiguous_failures == 1

    def test_to_json(self):
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0)
        json_str = ledger.to_json()
        assert '"scars"' in json_str
        assert '"shields"' in json_str
        assert '"failure_history"' in json_str


# =============================================================================
# ScarLedger - Ambiguous Handling
# =============================================================================


class TestScarLedgerAmbiguous:
    def test_ambiguous_creates_light_shield(self):
        """Ambiguous failure creates a lighter shield than external."""
        ledger = ScarLedger()

        # External failure
        ext_event = ledger.record_failure("r1", 0.9, 1.0, source="s1")
        ext_shield = ledger.shields[ext_event.shield_id]

        # Ambiguous failure
        amb_event = ledger.record_failure("r2", 0.5, 1.0, source="s2")
        amb_shield = ledger.shields[amb_event.shield_id]

        # Ambiguous shield should be lighter (higher permeability)
        assert amb_shield.permeability > ext_shield.permeability

    def test_ambiguous_bumps_existing_scar_stiffness(self):
        """Ambiguous failure bumps stiffness on existing scar without new topology."""
        ledger = ScarLedger()

        # Create a scar first (internal failure)
        int_event = ledger.record_failure("r", 0.1, 1.0)
        scar = ledger.scars[int_event.scar_id]
        scar.stiffness = 0.5  # Soften it

        # Ambiguous failure in same region should bump stiffness
        ledger.record_failure("r", 0.5, 1.0)
        assert scar.stiffness > 0.5  # Bumped


# =============================================================================
# Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    def test_create_scar_ledger(self):
        ledger = create_scar_ledger(rho_lo=0.2, rho_hi=0.8)
        assert ledger.config.rho_lo == 0.2
        assert ledger.config.rho_hi == 0.8

    def test_classify_failure_standalone(self):
        prov, rho = classify_failure(0.1, 1.0)
        assert prov == FailureProvenance.INTERNAL

        prov2, rho2 = classify_failure(0.9, 1.0)
        assert prov2 == FailureProvenance.EXTERNAL

        prov3, rho3 = classify_failure(0.5, 1.0)
        assert prov3 == FailureProvenance.AMBIGUOUS

    def test_classify_with_custom_thresholds(self):
        prov, rho = classify_failure(0.5, 1.0, rho_lo=0.6, rho_hi=0.9)
        assert prov == FailureProvenance.INTERNAL  # Below new rho_lo


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_many_failures_same_region(self):
        """Multiple failures on same region should accumulate, not multiply scars."""
        ledger = ScarLedger()
        for _ in range(10):
            ledger.record_failure("src/fragile.py", 0.1, 1.0)

        assert len(ledger.scars) == 1
        assert ledger.total_failures == 10
        assert ledger.internal_failures == 10

    def test_many_attacks_same_source(self):
        """Multiple attacks on same source should tighten existing shield."""
        ledger = ScarLedger()
        for _ in range(10):
            ledger.record_failure("api", 0.9, 1.0, source="attacker")

        assert len(ledger.shields) == 1
        shield = list(ledger.shields.values())[0]
        assert shield.permeability < 0.1  # Very tight

    def test_mixed_failure_types(self):
        """Different regions can have different failure types."""
        ledger = ScarLedger()
        ledger.record_failure("internal_bug", 0.1, 1.0)
        ledger.record_failure("external_attack", 0.9, 1.0, source="evil")
        ledger.record_failure("unclear", 0.5, 1.0)

        assert len(ledger.scars) == 1
        assert len(ledger.shields) == 2

    def test_empty_ledger_metrics(self):
        ledger = ScarLedger()
        metrics = ledger.get_metrics()
        assert metrics["total_failures"] == 0
        assert metrics["avg_stiffness"] == 0.0
        assert metrics["avg_permeability"] == 1.0

    def test_scar_anneal_then_retighten_cycle(self):
        """Full lifecycle: scar -> evidence -> anneal -> re-fail -> retighten."""
        config = ScarConfig(evidence_required=2)
        ledger = ScarLedger(config)

        # 1. Initial failure
        event = ledger.record_failure("r", 0.1, 1.0)
        scar = ledger.scars[event.scar_id]
        scar.required_evidence = 2
        assert scar.stiffness == MAX_STIFFNESS

        # 2. Evidence and anneal
        ledger.record_stability_evidence("r")
        ledger.record_stability_evidence("r")
        ledger.anneal_scars()
        assert scar.stiffness < MAX_STIFFNESS

        # 3. Re-failure retightens
        ledger.record_failure("r", 0.05, 1.0)
        assert scar.stiffness == MAX_STIFFNESS
        assert scar.evidence_count == 0  # Reset

    def test_large_observation_shift(self):
        """Very large observation shift should classify as external."""
        ledger = ScarLedger()
        prov, rho = ledger.classify_failure(100.0, 1.0)
        assert prov == FailureProvenance.EXTERNAL
        assert rho == 100.0

    def test_tiny_prediction_error(self):
        """Very small prediction error with shift should classify as external."""
        ledger = ScarLedger()
        prov, rho = ledger.classify_failure(0.5, 0.001)
        assert prov == FailureProvenance.EXTERNAL
        assert rho > 100

    def test_negative_values_handled(self):
        """Negative observation_shift treated as magnitude."""
        ledger = ScarLedger()
        # negative shift / positive error -> negative rho -> below rho_lo -> internal
        prov, rho = ledger.classify_failure(-0.5, 1.0)
        assert prov == FailureProvenance.INTERNAL


# =============================================================================
# Scar Fingerprint (region + failure_kind + action_type)
# =============================================================================


class TestScarFingerprint:
    """Test composite fingerprint matching on Scar objects."""

    def test_fingerprint_property(self):
        scar = Scar(scar_id="s1", region="src/auth.py",
                     failure_kind="timeout", action_type="write")
        assert scar.fingerprint == "src/auth.py::timeout::write"

    def test_fingerprint_empty_fields(self):
        scar = Scar(scar_id="s1", region="src/auth.py")
        assert scar.fingerprint == "src/auth.py::::"

    def test_matches_same_region_broad_scar(self):
        """Region-only scar matches any query in that region."""
        scar = Scar(scar_id="s1", region="src/auth.py")
        assert scar.matches_fingerprint("src/auth.py")
        assert scar.matches_fingerprint("src/auth.py", "timeout")
        assert scar.matches_fingerprint("src/auth.py", "timeout", "write")
        assert scar.matches_fingerprint("src/auth.py", "validation", "read")

    def test_no_match_different_region(self):
        scar = Scar(scar_id="s1", region="src/auth.py")
        assert not scar.matches_fingerprint("src/db.py")

    def test_narrow_scar_only_matches_exact(self):
        """Scar with failure_kind only matches that kind (or broad queries)."""
        scar = Scar(scar_id="s1", region="src/auth.py",
                     failure_kind="timeout")
        # Exact match
        assert scar.matches_fingerprint("src/auth.py", "timeout")
        # Broad query (no failure_kind) matches any scar in region
        assert scar.matches_fingerprint("src/auth.py")
        # Different failure_kind does NOT match
        assert not scar.matches_fingerprint("src/auth.py", "validation")

    def test_full_fingerprint_match(self):
        scar = Scar(scar_id="s1", region="src/auth.py",
                     failure_kind="timeout", action_type="write")
        assert scar.matches_fingerprint("src/auth.py", "timeout", "write")
        assert scar.matches_fingerprint("src/auth.py", "timeout")
        assert scar.matches_fingerprint("src/auth.py")
        assert not scar.matches_fingerprint("src/auth.py", "timeout", "read")
        assert not scar.matches_fingerprint("src/auth.py", "validation", "write")

    def test_serialization_roundtrip(self):
        scar = Scar(scar_id="s1", region="r",
                     failure_kind="timeout", action_type="write")
        data = scar.to_dict()
        assert data["failure_kind"] == "timeout"
        assert data["action_type"] == "write"
        restored = Scar.from_dict(data)
        assert restored.failure_kind == "timeout"
        assert restored.action_type == "write"
        assert restored.fingerprint == scar.fingerprint

    def test_from_dict_backward_compat(self):
        """Old serialized scars without fingerprint fields get empty strings."""
        data = {
            "scar_id": "s1",
            "region": "r",
            "stiffness": 0.8,
            "provenance": "internal",
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        scar = Scar.from_dict(data)
        assert scar.failure_kind == ""
        assert scar.action_type == ""


class TestFailureEventFingerprint:
    """Test failure_kind/action_type on FailureEvent."""

    def test_fields_present(self):
        event = FailureEvent(event_id="e1", region="r",
                             failure_kind="timeout", action_type="write")
        assert event.failure_kind == "timeout"
        assert event.action_type == "write"

    def test_defaults_empty(self):
        event = FailureEvent(event_id="e1", region="r")
        assert event.failure_kind == ""
        assert event.action_type == ""

    def test_serialization_roundtrip(self):
        event = FailureEvent(event_id="e1", region="r",
                             failure_kind="auth", action_type="execute")
        data = event.to_dict()
        assert data["failure_kind"] == "auth"
        assert data["action_type"] == "execute"
        restored = FailureEvent.from_dict(data)
        assert restored.failure_kind == "auth"
        assert restored.action_type == "execute"

    def test_from_dict_backward_compat(self):
        data = {
            "event_id": "e1",
            "timestamp": "2025-01-01T00:00:00+00:00",
            "region": "r",
        }
        event = FailureEvent.from_dict(data)
        assert event.failure_kind == ""
        assert event.action_type == ""


class TestLedgerFingerprintRecording:
    """Test that record_failure creates separate scars per fingerprint."""

    def test_same_region_different_failure_kind_separate_scars(self):
        """Same region, different failure_kind → separate scars."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("src/auth.py", 0.1, 1.0,
                                     failure_kind="timeout")
        ev2 = ledger.record_failure("src/auth.py", 0.1, 1.0,
                                     failure_kind="validation")
        assert ev1.scar_id != ev2.scar_id
        assert len(ledger.scars) == 2

    def test_same_fingerprint_retightens(self):
        """Same fingerprint → retighten existing scar, not new scar."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("src/auth.py", 0.1, 1.0,
                                     failure_kind="timeout")
        scar = ledger.scars[ev1.scar_id]
        scar.stiffness = 0.5  # Soften

        ev2 = ledger.record_failure("src/auth.py", 0.1, 1.0,
                                     failure_kind="timeout")
        assert ev2.scar_id == ev1.scar_id
        assert len(ledger.scars) == 1
        assert scar.stiffness == MAX_STIFFNESS  # Retightened

    def test_region_only_vs_fingerprinted(self):
        """Region-only scar and fingerprinted scar coexist."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("src/auth.py", 0.1, 1.0)  # region-only
        ev2 = ledger.record_failure("src/auth.py", 0.1, 1.0,
                                     failure_kind="timeout")
        assert ev1.scar_id != ev2.scar_id
        assert len(ledger.scars) == 2

    def test_failure_event_carries_fingerprint(self):
        ledger = ScarLedger()
        event = ledger.record_failure("r", 0.1, 1.0,
                                       failure_kind="auth", action_type="execute")
        assert event.failure_kind == "auth"
        assert event.action_type == "execute"


class TestLedgerFingerprintAdmissibility:
    """Test check_admissible with fingerprint params."""

    def test_region_only_check_returns_most_restrictive(self):
        """Region-only check returns most restrictive scar in that region."""
        ledger = ScarLedger()
        # Create two scars: one hard (timeout), one soft (validation)
        ev1 = ledger.record_failure("src/auth.py", 0.1, 1.0,
                                     failure_kind="timeout")
        ev2 = ledger.record_failure("src/auth.py", 0.1, 1.0,
                                     failure_kind="validation")
        # Soften the validation scar
        ledger.scars[ev2.scar_id].stiffness = 0.3

        admissible, cost, scar = ledger.check_admissible("src/auth.py")
        assert not admissible  # Hard scar blocks
        assert scar.failure_kind == "timeout"

    def test_specific_kind_check_avoids_unrelated_scar(self):
        """Checking specific failure_kind only sees matching scars."""
        ledger = ScarLedger()
        ledger.record_failure("src/auth.py", 0.1, 1.0,
                              failure_kind="timeout")
        # Validation check: no matching scar (timeout scar doesn't match)
        admissible, cost, scar = ledger.check_admissible(
            "src/auth.py", failure_kind="validation")
        assert admissible
        assert scar is None

    def test_broad_scar_blocks_specific_query(self):
        """Region-level scar (no failure_kind) blocks specific queries."""
        ledger = ScarLedger()
        ledger.record_failure("src/auth.py", 0.1, 1.0)  # region-only scar

        # Specific query still blocked by broad scar
        admissible, cost, scar = ledger.check_admissible(
            "src/auth.py", failure_kind="timeout")
        assert not admissible

    def test_hard_scar_on_one_kind_allows_other_kind(self):
        """Hard scar on timeout doesn't block validation (different kind)."""
        ledger = ScarLedger()
        ledger.record_failure("src/auth.py", 0.1, 1.0,
                              failure_kind="timeout")

        # Timeout blocked
        admissible, _, _ = ledger.check_admissible(
            "src/auth.py", failure_kind="timeout")
        assert not admissible

        # Validation not blocked
        admissible, _, _ = ledger.check_admissible(
            "src/auth.py", failure_kind="validation")
        assert admissible

    def test_no_scar_region(self):
        """Region with no scars is always admissible."""
        ledger = ScarLedger()
        ledger.record_failure("src/auth.py", 0.1, 1.0,
                              failure_kind="timeout")
        admissible, cost, scar = ledger.check_admissible("src/db.py")
        assert admissible
        assert scar is None

    def test_backward_compat_no_fingerprint(self):
        """Old-style check_admissible(region) still works."""
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0)
        admissible, cost, scar = ledger.check_admissible("r")
        assert not admissible
        assert scar is not None


class TestLedgerFingerprintEvidence:
    """Test record_stability_evidence with fingerprint params."""

    def test_evidence_targets_matching_scar(self):
        """Evidence with failure_kind targets only matching scar."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="validation")
        scar1 = ledger.scars[ev1.scar_id]
        scar2 = ledger.scars[ev2.scar_id]

        ledger.record_stability_evidence("r", failure_kind="timeout")
        assert scar1.evidence_count == 1
        assert scar2.evidence_count == 0

    def test_evidence_without_kind_hits_all(self):
        """Evidence without failure_kind applies to ALL scars in region."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="validation")
        scar1 = ledger.scars[ev1.scar_id]
        scar2 = ledger.scars[ev2.scar_id]

        ledger.record_stability_evidence("r")
        assert scar1.evidence_count == 1
        assert scar2.evidence_count == 1

    def test_evidence_returns_false_no_scar(self):
        ledger = ScarLedger()
        assert ledger.record_stability_evidence("unknown") is False

    def test_evidence_anneals_only_matching(self):
        """After enough evidence, anneal only targets correct fingerprint."""
        config = ScarConfig(evidence_required=2)
        ledger = ScarLedger(config)
        ev1 = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="validation")
        scar1 = ledger.scars[ev1.scar_id]
        scar2 = ledger.scars[ev2.scar_id]
        scar1.required_evidence = 2
        scar2.required_evidence = 2

        # Only give timeout evidence
        ledger.record_stability_evidence("r", failure_kind="timeout")
        ledger.record_stability_evidence("r", failure_kind="timeout")
        results = ledger.anneal_scars()

        assert scar1.stiffness < MAX_STIFFNESS  # Annealed
        assert scar2.stiffness == MAX_STIFFNESS  # Still hard


class TestLedgerFingerprintSerialization:
    """Test that fingerprinted scars survive serialization roundtrip."""

    def test_roundtrip_with_fingerprinted_scars(self):
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout",
                              action_type="write")
        ledger.record_failure("r", 0.1, 1.0, failure_kind="validation",
                              action_type="read")

        data = ledger.to_dict()
        restored = ScarLedger.from_dict(data)

        assert len(restored.scars) == 2
        scars = list(restored.scars.values())
        fingerprints = {s.fingerprint for s in scars}
        assert "r::timeout::write" in fingerprints
        assert "r::validation::read" in fingerprints

    def test_roundtrip_failure_events_with_fingerprint(self):
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0, failure_kind="auth",
                              action_type="execute")
        data = ledger.to_dict()
        restored = ScarLedger.from_dict(data)
        event = restored.failure_history[0]
        assert event.failure_kind == "auth"
        assert event.action_type == "execute"


class TestLedgerFingerprintRetighten:
    """Test retighten only fires for matching fingerprint."""

    def test_retighten_matching_fingerprint(self):
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        scar = ledger.scars[ev1.scar_id]
        scar.stiffness = 0.3  # Soften

        # Same fingerprint → retighten (0.3 + 0.5 default = 0.8)
        ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        assert scar.stiffness > 0.3  # Retightened
        assert scar.evidence_count == 0  # Evidence reset

    def test_different_fingerprint_no_retighten(self):
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        scar = ledger.scars[ev1.scar_id]
        scar.stiffness = 0.3

        # Different fingerprint → new scar, not retighten
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="validation")
        assert scar.stiffness == 0.3  # Unchanged
        assert len(ledger.scars) == 2


class TestLedgerFingerprintTieBreaking:
    """Test deterministic tie-breaking in most-restrictive selection."""

    def test_same_stiffness_prefers_specific(self):
        """When stiffness is equal, prefer the more specific scar."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0)  # broad
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        scar1 = ledger.scars[ev1.scar_id]
        scar2 = ledger.scars[ev2.scar_id]
        scar1.stiffness = 0.5
        scar2.stiffness = 0.5

        _, _, winner = ledger.check_admissible("r", failure_kind="timeout")
        # Both match; same stiffness; specific scar (longer fingerprint) wins
        assert winner.failure_kind == "timeout"

    def test_higher_stiffness_always_wins(self):
        """Higher stiffness beats higher specificity."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0)  # broad
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        scar1 = ledger.scars[ev1.scar_id]
        scar2 = ledger.scars[ev2.scar_id]
        scar1.stiffness = 0.8
        scar2.stiffness = 0.3

        _, _, winner = ledger.check_admissible("r", failure_kind="timeout")
        assert winner.stiffness == 0.8
        assert winner.failure_kind == ""  # The broad scar won

    def test_tiebreak_is_deterministic(self):
        """Same inputs always produce same winner."""
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0, failure_kind="a")
        ledger.record_failure("r", 0.1, 1.0, failure_kind="b")
        for s in ledger.scars.values():
            s.stiffness = 0.5

        results = set()
        for _ in range(10):
            _, _, winner = ledger.check_admissible("r")
            results.add(winner.scar_id)
        # Always the same winner
        assert len(results) == 1


class TestBroadcastEvidenceExplicit:
    """Explicit tests for the broadcast behavior of unspecified kind/type."""

    def test_broadcast_evidence_documented(self):
        """Unspecified kind == broadcast: evidence hits ALL scars in region.

        This is intentional behavior. Callers who want targeted evidence
        MUST pass failure_kind and/or action_type.
        """
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0, failure_kind="a")
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="b")
        ev3 = ledger.record_failure("r", 0.1, 1.0, failure_kind="c")

        # Broadcast: hits all 3
        ledger.record_stability_evidence("r")
        for sid in [ev1.scar_id, ev2.scar_id, ev3.scar_id]:
            assert ledger.scars[sid].evidence_count == 1

    def test_targeted_evidence_does_not_broadcast(self):
        """Specifying failure_kind targets only that scar."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0, failure_kind="a")
        ev2 = ledger.record_failure("r", 0.1, 1.0, failure_kind="b")

        ledger.record_stability_evidence("r", failure_kind="a")
        assert ledger.scars[ev1.scar_id].evidence_count == 1
        assert ledger.scars[ev2.scar_id].evidence_count == 0


# =============================================================================
# Strict Wrappers
# =============================================================================


class TestStrictWrappers:
    """Test strict API that requires fingerprint fields."""

    def test_record_failure_strict_requires_kind(self):
        ledger = ScarLedger()
        with pytest.raises(ValueError, match="failure_kind is required"):
            ledger.record_failure_strict("r", failure_kind="", action_type="write")

    def test_record_failure_strict_works(self):
        ledger = ScarLedger()
        event = ledger.record_failure_strict("r", failure_kind="timeout", action_type="write")
        assert event.failure_kind == "timeout"
        assert event.action_type == "write"

    def test_check_admissible_strict_requires_kind(self):
        ledger = ScarLedger()
        with pytest.raises(ValueError, match="failure_kind is required"):
            ledger.check_admissible_strict("r", failure_kind="")

    def test_check_admissible_strict_works(self):
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        admissible, cost, scar = ledger.check_admissible_strict(
            "r", failure_kind="timeout")
        assert not admissible
        assert scar.failure_kind == "timeout"

    def test_record_stability_evidence_strict_requires_kind(self):
        ledger = ScarLedger()
        with pytest.raises(ValueError, match="failure_kind is required"):
            ledger.record_stability_evidence_strict("r", failure_kind="")

    def test_record_stability_evidence_strict_works(self):
        ledger = ScarLedger()
        ev = ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        result = ledger.record_stability_evidence_strict("r", failure_kind="timeout")
        assert result is True
        assert ledger.scars[ev.scar_id].evidence_count == 1


# =============================================================================
# Retry Novelty Gate (3-tier: exact → similar → new)
# =============================================================================


class TestRetryNoveltyGate:
    """Test the three-tier novelty gate in _apply_scar."""

    def test_tier1_exact_retighten(self):
        """Exact fingerprint match → retighten existing scar."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="write")
        scar = ledger.scars[ev1.scar_id]
        scar.stiffness = 0.3

        ev2 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="write")
        assert ev2.scar_id == ev1.scar_id  # Same scar
        assert scar.stiffness > 0.3  # Retightened
        assert len(ledger.scars) == 1

    def test_tier2_similar_kind_retightens(self):
        """Same region + kind, different action → similar → retighten."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="write")
        scar = ledger.scars[ev1.scar_id]
        scar.stiffness = 0.3

        # Same kind, different action → similar class
        ev2 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="read")
        assert ev2.scar_id == ev1.scar_id  # Retightened existing
        assert scar.stiffness > 0.3
        assert len(ledger.scars) == 1  # No new scar

    def test_tier2_similar_action_retightens(self):
        """Same region + action, different kind → similar → retighten."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="write")
        scar = ledger.scars[ev1.scar_id]
        scar.stiffness = 0.3

        # Same action, different kind → similar class
        ev2 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="validation", action_type="write")
        assert ev2.scar_id == ev1.scar_id  # Retightened existing
        assert scar.stiffness > 0.3
        assert len(ledger.scars) == 1

    def test_tier3_different_class_creates_new(self):
        """Different kind AND different action → different class → new scar."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="write")
        ev2 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="validation", action_type="read")
        assert ev1.scar_id != ev2.scar_id  # New scar
        assert len(ledger.scars) == 2

    def test_tier3_no_fingerprint_creates_new(self):
        """Region-only failure always creates new (no similarity check)."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="write")
        # Region-only event can't trigger Tier 2 (needs specificity to compare)
        ev2 = ledger.record_failure("r", 0.1, 1.0)
        assert ev1.scar_id != ev2.scar_id
        assert len(ledger.scars) == 2

    def test_similar_does_not_match_broad_scar(self):
        """Broad scars (no fingerprint) are NOT similar — they're a different class."""
        ledger = ScarLedger()
        ev1 = ledger.record_failure("r", 0.1, 1.0)  # broad scar
        ev2 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="write")
        # Broad scar has no fingerprint dimensions → not "similar"
        assert ev1.scar_id != ev2.scar_id
        assert len(ledger.scars) == 2

    def test_similar_picks_most_restrictive(self):
        """When multiple similar scars exist, retighten the most restrictive."""
        ledger = ScarLedger()
        # Create two scars manually (different class: different kind AND action)
        scar1 = Scar(scar_id="sc_1", region="r",
                      failure_kind="timeout", action_type="write", stiffness=0.8)
        scar2 = Scar(scar_id="sc_2", region="r",
                      failure_kind="timeout", action_type="read", stiffness=0.3)
        ledger.scars["sc_1"] = scar1
        ledger.scars["sc_2"] = scar2

        # New failure same kind, different action → similar to both
        ev3 = ledger.record_failure("r", 0.1, 1.0,
                                     failure_kind="timeout", action_type="execute")
        # Should retighten the more restrictive one (scar1)
        assert ev3.scar_id == "sc_1"
        assert scar1.stiffness > 0.8
        assert len(ledger.scars) == 2  # No new scar

    def test_novelty_gate_prevents_self_bricking(self):
        """Rapidly varying action_type doesn't create a scar per retry."""
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0,
                              failure_kind="timeout", action_type="write")
        # 10 retries with different action_type but same kind
        for action in ["read", "execute", "delete", "list", "stat",
                       "create", "update", "move", "copy", "chmod"]:
            ledger.record_failure("r", 0.1, 1.0,
                                  failure_kind="timeout", action_type=action)
        # Should NOT have 11 scars — similar retries retighten
        assert len(ledger.scars) == 1


# =============================================================================
# Explain Admissibility
# =============================================================================


class TestExplainAdmissibility:
    """Test the explain_admissibility debug path."""

    def test_no_scars(self):
        ledger = ScarLedger()
        info = ledger.explain_admissibility("r")
        assert info["admissible"] is True
        assert info["winner"] is None
        assert info["candidates"] == 0

    def test_blocked_with_explanation(self):
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        info = ledger.explain_admissibility("r", failure_kind="timeout")
        assert info["admissible"] is False
        assert info["winner"] is not None
        assert info["winner_fingerprint"] == "r::timeout::"
        assert info["candidates"] == 1

    def test_multiple_matches_listed(self):
        ledger = ScarLedger()
        ledger.record_failure("r", 0.1, 1.0)  # broad
        ledger.record_failure("r", 0.1, 1.0, failure_kind="timeout")
        info = ledger.explain_admissibility("r", failure_kind="timeout")
        assert info["candidates"] == 2
        assert len(info["all_matches"]) == 2

    def test_query_fields_in_output(self):
        ledger = ScarLedger()
        info = ledger.explain_admissibility("r", failure_kind="timeout", action_type="write")
        assert info["query"]["region"] == "r"
        assert info["query"]["failure_kind"] == "timeout"
        assert info["query"]["action_type"] == "write"

    def test_unspecified_shows_placeholder(self):
        ledger = ScarLedger()
        info = ledger.explain_admissibility("r")
        assert info["query"]["failure_kind"] == "(unspecified)"
        assert info["query"]["action_type"] == "(unspecified)"


# =============================================================================
# CLI --json output
# =============================================================================


class TestScarCliJson:
    """Tests for --json flags on scar list, scar history, scar stats."""

    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    @pytest.fixture
    def initialized(self, tmp_path, runner):
        from governor.cli import cli
        with runner.isolated_filesystem(temp_dir=tmp_path) as td:
            runner.invoke(cli, ["--root", td, "init"])
            yield Path(td)

    @pytest.fixture
    def with_scars(self, initialized, runner):
        """Initialize a scar ledger with a failure event."""
        from governor.cli import cli
        root = str(initialized)
        runner.invoke(cli, ["--root", root, "scar", "record", "src/api",
                            "--obs-shift", "0.1", "--pred-error", "1.0",
                            "--description", "test failure",
                            "--failure-kind", "timeout", "--action-type", "write"])
        return initialized

    def test_scar_list_json_empty(self, runner, initialized):
        from governor.cli import cli
        result = runner.invoke(cli, ["--root", str(initialized), "scar", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["scars"] == []
        assert data["shields"] == []
        assert data["stats"]["health"] == "NOMINAL"
        assert data["stats"]["total_scars"] == 0

    def test_scar_list_json_with_data(self, runner, with_scars):
        from governor.cli import cli
        result = runner.invoke(cli, ["--root", str(with_scars), "scar", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["scars"]) >= 1
        assert "scar_id" in data["scars"][0]
        assert "region" in data["scars"][0]
        assert "stiffness" in data["scars"][0]
        assert isinstance(data["stats"]["total_scars"], int)
        assert isinstance(data["stats"]["hard_scars"], int)
        assert data["stats"]["health"] in ("NOMINAL", "CAUTIOUS", "CONSTRAINED")

    def test_scar_history_json_empty(self, runner, initialized):
        from governor.cli import cli
        result = runner.invoke(cli, ["--root", str(initialized), "scar", "history", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_scar_history_json_with_data(self, runner, with_scars):
        from governor.cli import cli
        result = runner.invoke(cli, ["--root", str(with_scars), "scar", "history", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1
        assert "event_id" in data[0]
        assert "region" in data[0]
        assert "provenance" in data[0]
        assert "surprise_ratio" in data[0]

    def test_scar_stats_json_empty(self, runner, initialized):
        from governor.cli import cli
        result = runner.invoke(cli, ["--root", str(initialized), "scar", "stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["health"] == "NOMINAL"

    def test_scar_stats_json_with_data(self, runner, with_scars):
        from governor.cli import cli
        result = runner.invoke(cli, ["--root", str(with_scars), "scar", "stats", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "health" in data
        assert "total_failures" in data
        assert isinstance(data["total_failures"], int)
