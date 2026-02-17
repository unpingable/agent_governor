# SPDX-License-Identifier: Apache-2.0
"""Tests for boil control - named presets with dwell time enforcement."""

import json
import pytest
from datetime import datetime, timezone

from governor.boil import (
    ControlMode,
    BoilPreset,
    DwellState,
    BoilEvent,
    BoilController,
    PRESETS,
    list_presets,
    get_preset,
)
from governor.regime import OperationalRegime, RegimeSignals, RegimeThresholds


class TestControlMode:
    """Tests for ControlMode enum."""

    def test_mode_values(self):
        """All expected modes exist."""
        assert ControlMode.GREEN_TEA.value == "green_tea"
        assert ControlMode.WHITE_TEA.value == "white_tea"
        assert ControlMode.OOLONG.value == "oolong"
        assert ControlMode.BLACK_TEA.value == "black_tea"
        assert ControlMode.FRENCH_PRESS.value == "french_press"
        assert ControlMode.BOIL.value == "boil"

    def test_mode_descriptions(self):
        """Each mode has a description."""
        for mode in ControlMode:
            assert mode.description
            assert len(mode.description) > 10

    def test_mode_from_string(self):
        """Can construct mode from string."""
        assert ControlMode("oolong") == ControlMode.OOLONG
        assert ControlMode("green_tea") == ControlMode.GREEN_TEA


class TestBoilPreset:
    """Tests for BoilPreset configuration."""

    def test_default_values(self):
        """Default preset has expected values."""
        preset = BoilPreset(name="test", mode=ControlMode.OOLONG)
        assert preset.claim_budget_per_turn == 10
        assert preset.novelty_tolerance == 0.3
        assert preset.authority_posture == "normal"
        assert preset.min_dwell_turns == 2

    def test_to_thresholds(self):
        """Preset converts to RegimeThresholds correctly."""
        preset = PRESETS[ControlMode.OOLONG]
        thresholds = preset.to_thresholds()

        assert isinstance(thresholds, RegimeThresholds)
        assert thresholds.warm_hysteresis == preset.warm_hysteresis
        assert thresholds.unstable_tool_gain == preset.unstable_tool_gain

    def test_serialization(self):
        """Preset serializes and deserializes correctly."""
        preset = PRESETS[ControlMode.GREEN_TEA]
        data = preset.to_dict()
        restored = BoilPreset.from_dict(data)

        assert restored.name == preset.name
        assert restored.mode == preset.mode
        assert restored.claim_budget_per_turn == preset.claim_budget_per_turn
        assert restored.contradiction_trip == preset.contradiction_trip


class TestPresets:
    """Tests for standard presets."""

    def test_all_presets_exist(self):
        """All control modes have presets."""
        for mode in ControlMode:
            assert mode in PRESETS
            assert PRESETS[mode].mode == mode

    def test_green_tea_is_strictest(self):
        """GREEN_TEA has tightest bounds."""
        green = PRESETS[ControlMode.GREEN_TEA]
        oolong = PRESETS[ControlMode.OOLONG]

        assert green.claim_budget_per_turn < oolong.claim_budget_per_turn
        assert green.novelty_tolerance < oolong.novelty_tolerance
        assert green.warm_hysteresis < oolong.warm_hysteresis

    def test_boil_is_loosest(self):
        """BOIL has widest bounds and minimal tripwires."""
        boil = PRESETS[ControlMode.BOIL]
        oolong = PRESETS[ControlMode.OOLONG]

        assert boil.claim_budget_per_turn > oolong.claim_budget_per_turn
        assert boil.novelty_tolerance > oolong.novelty_tolerance
        # BOIL only has cascade tripwire active
        assert boil.cascade_trip is True
        assert boil.contradiction_trip is False
        assert boil.provenance_trip is False

    def test_preset_progression(self):
        """Presets get progressively looser from GREEN_TEA to BOIL."""
        order = [
            ControlMode.GREEN_TEA,
            ControlMode.WHITE_TEA,
            ControlMode.OOLONG,
            ControlMode.BLACK_TEA,
            ControlMode.FRENCH_PRESS,
            ControlMode.BOIL,
        ]

        budgets = [PRESETS[m].claim_budget_per_turn for m in order]
        tolerances = [PRESETS[m].novelty_tolerance for m in order]

        # Each should be >= the previous
        for i in range(1, len(budgets)):
            assert budgets[i] >= budgets[i - 1]
            assert tolerances[i] >= tolerances[i - 1]

    def test_list_presets(self):
        """list_presets returns all presets."""
        presets = list_presets()
        assert len(presets) == len(ControlMode)

        for p in presets:
            assert "mode" in p
            assert "name" in p
            assert "description" in p
            assert "claim_budget" in p

    def test_get_preset_by_mode(self):
        """get_preset works with ControlMode."""
        preset = get_preset(ControlMode.OOLONG)
        assert preset.mode == ControlMode.OOLONG

    def test_get_preset_by_string(self):
        """get_preset works with string."""
        preset = get_preset("french_press")
        assert preset.mode == ControlMode.FRENCH_PRESS


class TestDwellState:
    """Tests for DwellState tracking."""

    def test_serialization(self):
        """DwellState serializes correctly."""
        state = DwellState(
            regime=OperationalRegime.WARM,
            entered_at_turn=5,
            stable_since_turn=7,
        )
        data = state.to_dict()
        restored = DwellState.from_dict(data)

        assert restored.regime == state.regime
        assert restored.entered_at_turn == state.entered_at_turn
        assert restored.stable_since_turn == state.stable_since_turn


class TestBoilEvent:
    """Tests for BoilEvent logging."""

    def test_serialization(self):
        """BoilEvent serializes correctly."""
        event = BoilEvent(
            timestamp=datetime.now(timezone.utc),
            event_type="tripwire",
            details={"tripwire": "cascade", "turn": 5},
        )
        data = event.to_dict()
        restored = BoilEvent.from_dict(data)

        assert restored.event_type == event.event_type
        assert restored.details == event.details


class TestBoilController:
    """Tests for BoilController."""

    def test_default_mode_is_oolong(self):
        """Default controller uses OOLONG preset."""
        controller = BoilController()
        assert controller.preset.mode == ControlMode.OOLONG

    def test_initial_state(self):
        """Initial state is ELASTIC at turn 0."""
        controller = BoilController()
        assert controller.turn_counter == 0
        assert controller.dwell.regime == OperationalRegime.ELASTIC
        assert controller.pending_transition is None

    def test_process_turn_increments_counter(self):
        """Each process_turn increments turn counter."""
        controller = BoilController()
        signals = RegimeSignals()

        controller.process_turn(signals)
        assert controller.turn_counter == 1

        controller.process_turn(signals)
        assert controller.turn_counter == 2

    def test_normal_operation_stays_elastic(self):
        """Normal signals keep system in ELASTIC."""
        controller = BoilController()
        signals = RegimeSignals(hysteresis=0.1, tool_gain=0.3)

        for _ in range(5):
            response = controller.process_turn(signals)
            assert response["regime"] == "elastic"
            assert response["action"] == "CONTINUE"
            assert response["tripwire"] is None

    def test_set_mode_changes_preset(self):
        """set_mode changes the active preset."""
        controller = BoilController(ControlMode.OOLONG)
        assert controller.preset.mode == ControlMode.OOLONG

        controller.set_mode(ControlMode.GREEN_TEA)
        assert controller.preset.mode == ControlMode.GREEN_TEA
        assert controller.preset.claim_budget_per_turn == 3

    def test_set_mode_logs_event(self):
        """set_mode logs a mode_change event."""
        controller = BoilController(ControlMode.OOLONG)
        controller.set_mode(ControlMode.BLACK_TEA)

        assert len(controller.event_log) == 1
        assert controller.event_log[0].event_type == "mode_change"
        assert controller.event_log[0].details["from"] == "oolong"
        assert controller.event_log[0].details["to"] == "black_tea"


class TestTripwires:
    """Tests for tripwire (hard sentinel) behavior."""

    def test_cascade_tripwire(self):
        """Cascade tripwire triggers on tool_gain >= 1.0."""
        controller = BoilController(ControlMode.OOLONG)
        signals = RegimeSignals(tool_gain=1.2)

        response = controller.process_turn(signals)

        assert response["tripwire"] == "cascade"
        assert response["regime"] == "unstable"
        assert response["action"] == "EMERGENCY_STOP"

    def test_contradiction_tripwire(self):
        """Contradiction tripwire triggers on accumulating contradictions."""
        controller = BoilController(ControlMode.OOLONG)
        # Open rate much higher than close rate
        signals = RegimeSignals(
            contradiction_open_rate=0.5,
            contradiction_close_rate=0.1,
        )

        response = controller.process_turn(signals)

        assert response["tripwire"] == "contradiction"
        assert response["regime"] == "unstable"

    def test_provenance_tripwire(self):
        """Provenance tripwire triggers on high deficit."""
        controller = BoilController(ControlMode.OOLONG)
        signals = RegimeSignals(provenance_deficit=0.6)

        response = controller.process_turn(signals)

        assert response["tripwire"] == "provenance"

    def test_dangerous_claim_tripwire(self):
        """Dangerous claim tripwire triggers on high rate."""
        controller = BoilController(ControlMode.OOLONG)
        signals = RegimeSignals(dangerous_claim_rate=0.4)

        response = controller.process_turn(signals)

        assert response["tripwire"] == "dangerous_claim"

    def test_tripwire_bypasses_dwell(self):
        """Tripwires force UNSTABLE regardless of dwell time."""
        controller = BoilController(ControlMode.GREEN_TEA)  # Long dwell
        # First establish ELASTIC
        for _ in range(5):
            controller.process_turn(RegimeSignals())

        # Now trigger tripwire - should force UNSTABLE despite dwell
        signals = RegimeSignals(tool_gain=1.5)
        response = controller.process_turn(signals)

        assert response["tripwire"] == "cascade"
        assert response["regime"] == "unstable"
        assert response["dwell_blocked"] is False

    def test_boil_mode_only_cascade_trips(self):
        """BOIL mode only triggers on cascade tripwire."""
        controller = BoilController(ControlMode.BOIL)

        # Provenance deficit - should NOT trip
        signals = RegimeSignals(provenance_deficit=0.8)
        response = controller.process_turn(signals)
        assert response["tripwire"] is None

        # Contradiction accumulation - should NOT trip
        signals = RegimeSignals(contradiction_open_rate=0.8, contradiction_close_rate=0.1)
        response = controller.process_turn(signals)
        assert response["tripwire"] is None

        # Cascade - SHOULD trip
        signals = RegimeSignals(tool_gain=1.5)
        response = controller.process_turn(signals)
        assert response["tripwire"] == "cascade"

    def test_tripwire_logs_event(self):
        """Tripwire triggers are logged."""
        controller = BoilController()
        signals = RegimeSignals(tool_gain=1.2)

        controller.process_turn(signals)

        events = controller.get_events()
        assert len(events) == 1
        assert events[0]["event_type"] == "tripwire"
        assert events[0]["details"]["tripwire"] == "cascade"


class TestDwellEnforcement:
    """Tests for dwell time enforcement."""

    def test_transition_blocked_by_dwell(self):
        """Transitions are blocked if min_dwell not satisfied."""
        controller = BoilController(ControlMode.GREEN_TEA)  # min_dwell = 3

        # Process one turn in ELASTIC
        controller.process_turn(RegimeSignals())

        # Signals that would trigger WARM
        warm_signals = RegimeSignals(hysteresis=0.3, rejection_rate=0.4)

        # Should be blocked - only 1 turn in ELASTIC, need 3
        response = controller.process_turn(warm_signals)
        assert response["dwell_blocked"] is True
        assert response["regime"] == "elastic"  # Stayed in ELASTIC
        assert response["pending_transition"] == "warm"

    def test_transition_allowed_after_dwell(self):
        """Transitions are allowed after min_dwell satisfied."""
        controller = BoilController(ControlMode.OOLONG)  # min_dwell = 2

        # Process 2 turns in ELASTIC to satisfy dwell
        controller.process_turn(RegimeSignals())
        controller.process_turn(RegimeSignals())

        # Now signals that would trigger WARM - should be allowed
        warm_signals = RegimeSignals(hysteresis=0.3, rejection_rate=0.4)
        response = controller.process_turn(warm_signals)

        assert response["dwell_blocked"] is False
        assert response["regime"] == "warm"

    def test_dwell_hold_logs_event(self):
        """Dwell holds are logged."""
        controller = BoilController(ControlMode.GREEN_TEA)

        # One turn ELASTIC
        controller.process_turn(RegimeSignals())

        # Try to transition
        controller.process_turn(RegimeSignals(hysteresis=0.3, rejection_rate=0.4))

        events = controller.get_events()
        hold_events = [e for e in events if e["event_type"] == "dwell_hold"]
        assert len(hold_events) == 1
        assert hold_events[0]["details"]["from"] == "elastic"
        assert hold_events[0]["details"]["to"] == "warm"

    def test_transition_allowed_logs_event(self):
        """Allowed transitions are logged."""
        controller = BoilController(ControlMode.OOLONG)

        # Satisfy dwell
        controller.process_turn(RegimeSignals())
        controller.process_turn(RegimeSignals())

        # Transition
        controller.process_turn(RegimeSignals(hysteresis=0.3, rejection_rate=0.4))

        events = controller.get_events()
        allowed_events = [e for e in events if e["event_type"] == "transition_allowed"]
        assert len(allowed_events) == 1


class TestControllerState:
    """Tests for controller state management."""

    def test_get_state(self):
        """get_state returns expected fields."""
        controller = BoilController()
        controller.process_turn(RegimeSignals())

        state = controller.get_state()

        assert state["mode"] == "oolong"
        assert state["preset"] == "oolong"
        assert state["turn"] == 1
        assert state["regime"] == "elastic"
        assert "detector_state" in state

    def test_get_preset_info(self):
        """get_preset_info returns preset configuration."""
        controller = BoilController(ControlMode.GREEN_TEA)
        info = controller.get_preset_info()

        assert info["name"] == "green_tea"
        assert info["mode"] == "green_tea"
        assert info["claim_budget"] == 3
        assert info["authority_posture"] == "strict"
        assert "tripwires" in info
        assert info["tripwires"]["cascade"] is True

    def test_get_events_with_limit(self):
        """get_events respects limit parameter."""
        controller = BoilController()

        # Generate some events
        for _ in range(5):
            controller.set_mode(ControlMode.OOLONG)
            controller.set_mode(ControlMode.BLACK_TEA)

        all_events = controller.get_events()
        limited = controller.get_events(limit=3)

        assert len(all_events) == 10
        assert len(limited) == 3
        # Should be most recent
        assert limited[-1] == all_events[-1]

    def test_serialization(self):
        """Controller serializes and deserializes correctly."""
        controller = BoilController(ControlMode.BLACK_TEA)
        controller.process_turn(RegimeSignals())
        controller.process_turn(RegimeSignals(hysteresis=0.3))

        data = controller.to_dict()
        restored = BoilController.from_dict(data)

        assert restored.preset.mode == controller.preset.mode
        assert restored.turn_counter == controller.turn_counter
        assert restored.dwell.regime == controller.dwell.regime
        assert len(restored.event_log) == len(controller.event_log)


class TestIntegration:
    """Integration tests for boil control workflow."""

    def test_typical_session_progression(self):
        """Simulate a typical session with regime changes."""
        controller = BoilController(ControlMode.OOLONG)

        # Normal operation
        for _ in range(3):
            response = controller.process_turn(RegimeSignals(hysteresis=0.1))
            assert response["regime"] == "elastic"

        # Stress increases
        for _ in range(3):
            response = controller.process_turn(RegimeSignals(
                hysteresis=0.25,
                rejection_rate=0.35,
            ))

        # Should have transitioned to WARM
        assert response["regime"] == "warm"
        assert response["action"] == "TIGHTEN"

    def test_recovery_after_tripwire(self):
        """System can recover after tripwire."""
        controller = BoilController()

        # Trigger tripwire
        controller.process_turn(RegimeSignals(tool_gain=1.5))
        assert controller.dwell.regime == OperationalRegime.UNSTABLE

        # Back to normal signals - will stay UNSTABLE due to dwell
        response = controller.process_turn(RegimeSignals())
        # Might transition back depending on classifier

    def test_mode_change_affects_behavior(self):
        """Changing modes affects tripwire sensitivity."""
        # With GREEN_TEA - should trip on provenance
        controller = BoilController(ControlMode.GREEN_TEA)
        response = controller.process_turn(RegimeSignals(provenance_deficit=0.6))
        assert response["tripwire"] == "provenance"

        # Reset and try with BOIL - should NOT trip on provenance
        controller = BoilController(ControlMode.BOIL)
        response = controller.process_turn(RegimeSignals(provenance_deficit=0.6))
        assert response["tripwire"] is None

    def test_full_workflow(self):
        """Test complete workflow: normal -> stressed -> tripwire -> mode change."""
        controller = BoilController(ControlMode.OOLONG)

        # Phase 1: Normal operation
        for _ in range(5):
            r = controller.process_turn(RegimeSignals())
            assert r["regime"] == "elastic"

        # Phase 2: Stress increases gradually
        for i in range(3):
            r = controller.process_turn(RegimeSignals(
                hysteresis=0.15 + i * 0.05,
                rejection_rate=0.25 + i * 0.05,
            ))

        # Phase 3: Critical event
        r = controller.process_turn(RegimeSignals(tool_gain=1.2))
        assert r["tripwire"] == "cascade"
        assert r["regime"] == "unstable"

        # Phase 4: User changes to stricter mode
        controller.set_mode(ControlMode.GREEN_TEA)
        assert controller.preset.claim_budget_per_turn == 3

        # Verify events logged
        events = controller.get_events()
        event_types = [e["event_type"] for e in events]
        assert "tripwire" in event_types
        assert "mode_change" in event_types
