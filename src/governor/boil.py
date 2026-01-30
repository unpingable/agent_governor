"""
Boil Control - Named Regime Presets with Dwell Time Enforcement

Inspired by electric kettles: they don't "optimize tea," they enforce
temperature bands + dwell time with crude but reliable control.

Key insights from the kettle pattern:
1. Discrete regimes, not continuous sliders (green tea vs french press vs boil)
2. Bands + hysteresis, not exact targets (hold [85-delta, 85+delta], don't thrash)
3. Dwell time matters (hold stability for N cycles before allowing changes)
4. "Boil" is a phase-change sentinel, not "slightly hotter" (hard tripwires)

This sits above RegimeDetector as the preset layer:
- User picks a mode
- Mode configures thresholds + dwell time + tripwires
- RegimeDetector does the actual classification
- BoilController enforces hold times and prevents thrashing
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .regime import (
    RegimeDetector,
    RegimeSignals,
    RegimeThresholds,
    OperationalRegime,
)


class ControlMode(str, Enum):
    """Named control modes - like kettle temperature presets."""
    GREEN_TEA = "green_tea"        # Delicate - low temp, tight bounds, cautious
    WHITE_TEA = "white_tea"        # Light extraction - slightly more tolerance
    OOLONG = "oolong"              # Medium - balanced extraction (default)
    BLACK_TEA = "black_tea"        # Robust - higher tolerance, more extraction
    FRENCH_PRESS = "french_press"  # Aggressive extraction - near limits but bounded
    BOIL = "boil"                  # Phase-change sentinel - tripwires only

    @property
    def description(self) -> str:
        """Human-readable description of the mode."""
        descriptions = {
            ControlMode.GREEN_TEA: "Delicate - tight bounds, low claim budget, strict authority",
            ControlMode.WHITE_TEA: "Light - slightly more tolerance than green tea",
            ControlMode.OOLONG: "Balanced - medium extraction, standard bounds (default)",
            ControlMode.BLACK_TEA: "Robust - higher tolerance, more extraction allowed",
            ControlMode.FRENCH_PRESS: "Aggressive - near limits but still bounded",
            ControlMode.BOIL: "Sentinel - tripwires only, no gradual control",
        }
        return descriptions.get(self, "Unknown mode")


@dataclass
class BoilPreset:
    """
    Named regime preset - the kettle setting.

    Each preset is a tuple of:
    - Setpoints: what we're targeting (budgets, tolerances)
    - Bands: hysteresis to prevent thrashing
    - Timing: cycle period, hold time before escalation
    - Tripwires: hard-stop conditions (the "boil" sentinels)
    """
    name: str
    mode: ControlMode

    # === Setpoints (what we're targeting) ===
    claim_budget_per_turn: int = 10          # max claims before pushback
    novelty_tolerance: float = 0.3           # speculation band [0-1]
    authority_posture: str = "normal"        # "strict", "normal", "permissive"
    variety_multiplier: float = 1.0          # scale variety bounds
    horizon_turns: int = 10                  # planning horizon

    # === Bands (hysteresis thresholds for RegimeThresholds) ===
    # ELASTIC -> WARM thresholds
    warm_hysteresis: float = 0.2
    warm_relaxation: float = 3.0
    warm_anisotropy: float = 0.3
    warm_provenance_deficit: float = 0.2
    warm_rejection_rate: float = 0.3
    warm_dangerous_rate: float = 0.1
    # WARM -> DUCTILE thresholds
    ductile_hysteresis: float = 0.5
    ductile_relaxation: float = 10.0
    ductile_anisotropy: float = 0.5
    ductile_budget_pressure: float = 0.7
    ductile_rejection_rate: float = 0.5
    # Any -> UNSTABLE thresholds
    unstable_tool_gain: float = 1.0
    unstable_budget_pressure: float = 0.9
    unstable_dangerous_rate: float = 0.3

    # === Timing ===
    cycle_period_turns: int = 3              # re-evaluate every N turns
    hold_time_turns: int = 5                 # stability required before mode change
    min_dwell_turns: int = 2                 # minimum time in regime before allowing transition

    # === Tripwires (hard-stop sentinels) ===
    contradiction_trip: bool = True          # instant intervention on contradiction accumulation
    provenance_trip: bool = True             # instant intervention on high provenance deficit
    dangerous_claim_trip: bool = True        # instant intervention on dangerous claims
    cascade_trip: bool = True                # instant intervention on tool cascade (k >= 1)

    def to_thresholds(self) -> RegimeThresholds:
        """Convert preset to RegimeThresholds."""
        return RegimeThresholds(
            warm_hysteresis=self.warm_hysteresis,
            warm_relaxation=self.warm_relaxation,
            warm_anisotropy=self.warm_anisotropy,
            warm_provenance_deficit=self.warm_provenance_deficit,
            warm_rejection_rate=self.warm_rejection_rate,
            warm_dangerous_rate=self.warm_dangerous_rate,
            ductile_hysteresis=self.ductile_hysteresis,
            ductile_relaxation=self.ductile_relaxation,
            ductile_anisotropy=self.ductile_anisotropy,
            ductile_budget_pressure=self.ductile_budget_pressure,
            ductile_rejection_rate=self.ductile_rejection_rate,
            unstable_tool_gain=self.unstable_tool_gain,
            unstable_budget_pressure=self.unstable_budget_pressure,
            unstable_dangerous_rate=self.unstable_dangerous_rate,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "mode": self.mode.value,
            "claim_budget_per_turn": self.claim_budget_per_turn,
            "novelty_tolerance": self.novelty_tolerance,
            "authority_posture": self.authority_posture,
            "variety_multiplier": self.variety_multiplier,
            "horizon_turns": self.horizon_turns,
            "warm_hysteresis": self.warm_hysteresis,
            "warm_relaxation": self.warm_relaxation,
            "warm_anisotropy": self.warm_anisotropy,
            "warm_provenance_deficit": self.warm_provenance_deficit,
            "warm_rejection_rate": self.warm_rejection_rate,
            "warm_dangerous_rate": self.warm_dangerous_rate,
            "ductile_hysteresis": self.ductile_hysteresis,
            "ductile_relaxation": self.ductile_relaxation,
            "ductile_anisotropy": self.ductile_anisotropy,
            "ductile_budget_pressure": self.ductile_budget_pressure,
            "ductile_rejection_rate": self.ductile_rejection_rate,
            "unstable_tool_gain": self.unstable_tool_gain,
            "unstable_budget_pressure": self.unstable_budget_pressure,
            "unstable_dangerous_rate": self.unstable_dangerous_rate,
            "cycle_period_turns": self.cycle_period_turns,
            "hold_time_turns": self.hold_time_turns,
            "min_dwell_turns": self.min_dwell_turns,
            "contradiction_trip": self.contradiction_trip,
            "provenance_trip": self.provenance_trip,
            "dangerous_claim_trip": self.dangerous_claim_trip,
            "cascade_trip": self.cascade_trip,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoilPreset":
        """Deserialize from dictionary."""
        mode = ControlMode(data["mode"]) if isinstance(data["mode"], str) else data["mode"]
        return cls(
            name=data["name"],
            mode=mode,
            claim_budget_per_turn=data.get("claim_budget_per_turn", 10),
            novelty_tolerance=data.get("novelty_tolerance", 0.3),
            authority_posture=data.get("authority_posture", "normal"),
            variety_multiplier=data.get("variety_multiplier", 1.0),
            horizon_turns=data.get("horizon_turns", 10),
            warm_hysteresis=data.get("warm_hysteresis", 0.2),
            warm_relaxation=data.get("warm_relaxation", 3.0),
            warm_anisotropy=data.get("warm_anisotropy", 0.3),
            warm_provenance_deficit=data.get("warm_provenance_deficit", 0.2),
            warm_rejection_rate=data.get("warm_rejection_rate", 0.3),
            warm_dangerous_rate=data.get("warm_dangerous_rate", 0.1),
            ductile_hysteresis=data.get("ductile_hysteresis", 0.5),
            ductile_relaxation=data.get("ductile_relaxation", 10.0),
            ductile_anisotropy=data.get("ductile_anisotropy", 0.5),
            ductile_budget_pressure=data.get("ductile_budget_pressure", 0.7),
            ductile_rejection_rate=data.get("ductile_rejection_rate", 0.5),
            unstable_tool_gain=data.get("unstable_tool_gain", 1.0),
            unstable_budget_pressure=data.get("unstable_budget_pressure", 0.9),
            unstable_dangerous_rate=data.get("unstable_dangerous_rate", 0.3),
            cycle_period_turns=data.get("cycle_period_turns", 3),
            hold_time_turns=data.get("hold_time_turns", 5),
            min_dwell_turns=data.get("min_dwell_turns", 2),
            contradiction_trip=data.get("contradiction_trip", True),
            provenance_trip=data.get("provenance_trip", True),
            dangerous_claim_trip=data.get("dangerous_claim_trip", True),
            cascade_trip=data.get("cascade_trip", True),
        )


# === Standard Presets ===

PRESETS: dict[ControlMode, BoilPreset] = {
    ControlMode.GREEN_TEA: BoilPreset(
        name="green_tea",
        mode=ControlMode.GREEN_TEA,
        # Delicate - tight bounds, low extraction
        claim_budget_per_turn=3,
        novelty_tolerance=0.1,
        authority_posture="strict",
        variety_multiplier=0.5,
        horizon_turns=5,
        # Tight bands - intervene early
        warm_hysteresis=0.15,
        warm_relaxation=2.0,
        warm_anisotropy=0.2,
        warm_provenance_deficit=0.1,
        warm_rejection_rate=0.2,
        warm_dangerous_rate=0.05,
        ductile_hysteresis=0.35,
        ductile_relaxation=8.0,
        ductile_anisotropy=0.3,
        ductile_budget_pressure=0.5,
        ductile_rejection_rate=0.4,
        unstable_tool_gain=0.8,
        unstable_budget_pressure=0.7,
        unstable_dangerous_rate=0.15,
        # Long hold times - stability prioritized
        cycle_period_turns=2,
        hold_time_turns=8,
        min_dwell_turns=3,
        # All tripwires active
        contradiction_trip=True,
        provenance_trip=True,
        dangerous_claim_trip=True,
        cascade_trip=True,
    ),

    ControlMode.WHITE_TEA: BoilPreset(
        name="white_tea",
        mode=ControlMode.WHITE_TEA,
        claim_budget_per_turn=5,
        novelty_tolerance=0.2,
        authority_posture="strict",
        variety_multiplier=0.7,
        horizon_turns=7,
        warm_hysteresis=0.18,
        warm_relaxation=2.5,
        warm_anisotropy=0.25,
        warm_provenance_deficit=0.15,
        warm_rejection_rate=0.25,
        warm_dangerous_rate=0.08,
        ductile_hysteresis=0.4,
        ductile_relaxation=9.0,
        ductile_anisotropy=0.4,
        ductile_budget_pressure=0.6,
        ductile_rejection_rate=0.45,
        unstable_tool_gain=0.9,
        unstable_budget_pressure=0.8,
        unstable_dangerous_rate=0.2,
        cycle_period_turns=2,
        hold_time_turns=6,
        min_dwell_turns=3,
    ),

    ControlMode.OOLONG: BoilPreset(
        name="oolong",
        mode=ControlMode.OOLONG,
        # Balanced - medium extraction (default)
        claim_budget_per_turn=8,
        novelty_tolerance=0.3,
        authority_posture="normal",
        variety_multiplier=1.0,
        horizon_turns=10,
        # Standard bands (match RegimeThresholds defaults)
        warm_hysteresis=0.2,
        warm_relaxation=3.0,
        warm_anisotropy=0.3,
        warm_provenance_deficit=0.2,
        warm_rejection_rate=0.3,
        warm_dangerous_rate=0.1,
        ductile_hysteresis=0.5,
        ductile_relaxation=10.0,
        ductile_anisotropy=0.5,
        ductile_budget_pressure=0.7,
        ductile_rejection_rate=0.5,
        unstable_tool_gain=1.0,
        unstable_budget_pressure=0.9,
        unstable_dangerous_rate=0.3,
        cycle_period_turns=3,
        hold_time_turns=5,
        min_dwell_turns=2,
    ),

    ControlMode.BLACK_TEA: BoilPreset(
        name="black_tea",
        mode=ControlMode.BLACK_TEA,
        # Robust - more tolerance
        claim_budget_per_turn=12,
        novelty_tolerance=0.4,
        authority_posture="normal",
        variety_multiplier=1.2,
        horizon_turns=12,
        # Looser bands
        warm_hysteresis=0.25,
        warm_relaxation=4.0,
        warm_anisotropy=0.35,
        warm_provenance_deficit=0.25,
        warm_rejection_rate=0.4,
        warm_dangerous_rate=0.15,
        ductile_hysteresis=0.55,
        ductile_relaxation=12.0,
        ductile_anisotropy=0.55,
        ductile_budget_pressure=0.75,
        ductile_rejection_rate=0.55,
        unstable_tool_gain=1.1,
        unstable_budget_pressure=0.92,
        unstable_dangerous_rate=0.35,
        cycle_period_turns=4,
        hold_time_turns=4,
        min_dwell_turns=2,
    ),

    ControlMode.FRENCH_PRESS: BoilPreset(
        name="french_press",
        mode=ControlMode.FRENCH_PRESS,
        # Aggressive extraction - near limits but still bounded
        claim_budget_per_turn=20,
        novelty_tolerance=0.5,
        authority_posture="permissive",
        variety_multiplier=1.5,
        horizon_turns=15,
        # Wide bands - let it run
        warm_hysteresis=0.3,
        warm_relaxation=5.0,
        warm_anisotropy=0.4,
        warm_provenance_deficit=0.3,
        warm_rejection_rate=0.5,
        warm_dangerous_rate=0.2,
        ductile_hysteresis=0.6,
        ductile_relaxation=15.0,
        ductile_anisotropy=0.6,
        ductile_budget_pressure=0.8,
        ductile_rejection_rate=0.6,
        unstable_tool_gain=1.2,
        unstable_budget_pressure=0.95,
        unstable_dangerous_rate=0.4,
        # Shorter hold times - more responsive
        cycle_period_turns=5,
        hold_time_turns=3,
        min_dwell_turns=1,
        # Still trip on hard failures, but allow ungrounded exploration
        contradiction_trip=True,
        provenance_trip=False,  # Allow some ungrounded exploration
        dangerous_claim_trip=True,
        cascade_trip=True,
    ),

    ControlMode.BOIL: BoilPreset(
        name="boil",
        mode=ControlMode.BOIL,
        # Phase-change sentinel - tripwires only, no gradual control
        claim_budget_per_turn=100,  # effectively unlimited
        novelty_tolerance=1.0,
        authority_posture="permissive",
        variety_multiplier=2.0,
        horizon_turns=20,
        # Very wide bands - only trip on hard failures
        warm_hysteresis=0.8,
        warm_relaxation=20.0,
        warm_anisotropy=0.7,
        warm_provenance_deficit=0.7,
        warm_rejection_rate=0.8,
        warm_dangerous_rate=0.5,
        ductile_hysteresis=0.9,
        ductile_relaxation=25.0,
        ductile_anisotropy=0.8,
        ductile_budget_pressure=0.95,
        ductile_rejection_rate=0.8,
        unstable_tool_gain=1.5,
        unstable_budget_pressure=0.99,
        unstable_dangerous_rate=0.7,
        cycle_period_turns=10,
        hold_time_turns=1,
        min_dwell_turns=1,
        # Only cascade trip active - pure sentinel mode
        contradiction_trip=False,
        provenance_trip=False,
        dangerous_claim_trip=False,
        cascade_trip=True,  # The one hard limit: k >= 1 = shut down
    ),
}


@dataclass
class DwellState:
    """Track time spent in current regime for dwell enforcement."""
    regime: OperationalRegime
    entered_at_turn: int
    stable_since_turn: int  # last turn where we didn't want to transition

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "regime": self.regime.value,
            "entered_at_turn": self.entered_at_turn,
            "stable_since_turn": self.stable_since_turn,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DwellState":
        """Deserialize from dictionary."""
        return cls(
            regime=OperationalRegime(data["regime"]),
            entered_at_turn=data["entered_at_turn"],
            stable_since_turn=data["stable_since_turn"],
        )


@dataclass
class BoilEvent:
    """Record of a boil control event."""
    timestamp: datetime
    event_type: str  # "mode_change", "tripwire", "dwell_hold", "transition_allowed"
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoilEvent":
        """Deserialize from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=data["event_type"],
            details=data["details"],
        )


class BoilController:
    """
    Boil Control - named regime presets with dwell time enforcement.

    Sits above RegimeDetector:
    1. User picks a mode (GREEN_TEA, FRENCH_PRESS, etc.)
    2. Mode configures thresholds + timing
    3. Controller enforces hold times and prevents thrashing
    4. Tripwires provide hard-stop sentinels
    """

    def __init__(self, mode: ControlMode = ControlMode.OOLONG):
        self.preset = PRESETS[mode]
        self.detector = RegimeDetector(thresholds=self.preset.to_thresholds())

        self.turn_counter = 0
        self.dwell = DwellState(
            regime=OperationalRegime.ELASTIC,
            entered_at_turn=0,
            stable_since_turn=0,
        )
        self.event_log: list[BoilEvent] = []

        # Track pending transitions blocked by dwell
        self.pending_transition: OperationalRegime | None = None
        self.pending_reason: list[str] | None = None

    def set_mode(self, mode: ControlMode) -> None:
        """Change control mode (like changing kettle temperature)."""
        old_mode = self.preset.mode
        self.preset = PRESETS[mode]

        # Update detector thresholds
        self.detector = RegimeDetector(thresholds=self.preset.to_thresholds())

        self._log_event("mode_change", {
            "from": old_mode.value,
            "to": mode.value,
            "turn": self.turn_counter,
        })

    def check_tripwires(self, signals: RegimeSignals) -> str | None:
        """
        Check hard-stop sentinels (the "boil" triggers).

        Returns tripwire name if triggered, None otherwise.
        Tripwires bypass all dwell time enforcement.
        """
        p = self.preset

        # Cascade trip: tool_gain >= 1.0 means positive feedback loop
        if p.cascade_trip and signals.tool_gain >= 1.0:
            return "cascade"

        # Contradiction trip: contradictions accumulating faster than closing
        if p.contradiction_trip:
            if signals.contradiction_open_rate > signals.contradiction_close_rate * 1.5:
                return "contradiction"

        # Provenance trip: too many claims without evidence
        if p.provenance_trip and signals.provenance_deficit > 0.5:
            return "provenance"

        # Dangerous claim trip: too many high-confidence ungrounded claims
        if p.dangerous_claim_trip and signals.dangerous_claim_rate > 0.3:
            return "dangerous_claim"

        return None

    def process_turn(self, signals: RegimeSignals) -> dict[str, Any]:
        """
        Process a turn through boil control.

        Returns response dict with:
        - regime: current operational regime
        - action: what to do (CONTINUE, TIGHTEN, RESET, EMERGENCY_STOP)
        - tripwire: if a hard sentinel triggered (or None)
        - dwell_blocked: if a transition was blocked by dwell time
        - preset: current preset name
        - turn: current turn number
        """
        self.turn_counter += 1

        # 1. Check tripwires first (hard sentinels bypass everything)
        tripwire = self.check_tripwires(signals)
        if tripwire:
            self._log_event("tripwire", {
                "tripwire": tripwire,
                "turn": self.turn_counter,
                "signals": signals.to_dict(),
            })

            # Force UNSTABLE regime immediately
            self.dwell = DwellState(
                regime=OperationalRegime.UNSTABLE,
                entered_at_turn=self.turn_counter,
                stable_since_turn=self.turn_counter,
            )
            self.detector.update(signals)  # Update detector state

            return {
                "regime": OperationalRegime.UNSTABLE.value,
                "action": "EMERGENCY_STOP",
                "tripwire": tripwire,
                "dwell_blocked": False,
                "preset": self.preset.name,
                "turn": self.turn_counter,
            }

        # 2. Get what regime detector thinks we should be in
        proposed_regime, warnings = self.detector.classify(signals)
        current_regime = self.dwell.regime

        # 3. Check dwell time constraints
        turns_in_regime = self.turn_counter - self.dwell.entered_at_turn

        if proposed_regime != current_regime:
            # Transition requested
            if turns_in_regime < self.preset.min_dwell_turns:
                # Block transition - haven't dwelled long enough
                self._log_event("dwell_hold", {
                    "from": current_regime.value,
                    "to": proposed_regime.value,
                    "turns_in_regime": turns_in_regime,
                    "min_dwell": self.preset.min_dwell_turns,
                    "turn": self.turn_counter,
                })

                self.pending_transition = proposed_regime
                self.pending_reason = warnings

                # Stay in current regime
                return self._make_response(
                    current_regime,
                    dwell_blocked=True,
                    pending_transition=proposed_regime.value,
                )
            else:
                # Transition allowed
                self._log_event("transition_allowed", {
                    "from": current_regime.value,
                    "to": proposed_regime.value,
                    "reason": warnings,
                    "turn": self.turn_counter,
                })

                self.dwell = DwellState(
                    regime=proposed_regime,
                    entered_at_turn=self.turn_counter,
                    stable_since_turn=self.turn_counter,
                )
                self.pending_transition = None
                self.pending_reason = None

                # Update detector's current regime
                self.detector.update(signals)
        else:
            # Staying in same regime - update stability
            self.dwell.stable_since_turn = self.turn_counter
            self.pending_transition = None
            self.pending_reason = None

        # 4. Return response for current regime
        return self._make_response(self.dwell.regime, dwell_blocked=False)

    def _make_response(
        self,
        regime: OperationalRegime,
        dwell_blocked: bool = False,
        pending_transition: str | None = None,
    ) -> dict[str, Any]:
        """Make a response for a regime."""
        actions = {
            OperationalRegime.ELASTIC: "CONTINUE",
            OperationalRegime.WARM: "TIGHTEN",
            OperationalRegime.DUCTILE: "RESET",
            OperationalRegime.UNSTABLE: "EMERGENCY_STOP",
        }

        response = {
            "regime": regime.value,
            "action": actions.get(regime, "CONTINUE"),
            "tripwire": None,
            "dwell_blocked": dwell_blocked,
            "preset": self.preset.name,
            "turn": self.turn_counter,
            "turns_in_regime": self.turn_counter - self.dwell.entered_at_turn,
        }

        if pending_transition:
            response["pending_transition"] = pending_transition

        return response

    def _log_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Log a boil control event."""
        self.event_log.append(BoilEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            details=details,
        ))

    def get_state(self) -> dict[str, Any]:
        """Get current controller state."""
        return {
            "mode": self.preset.mode.value,
            "preset": self.preset.name,
            "turn": self.turn_counter,
            "regime": self.dwell.regime.value,
            "turns_in_regime": self.turn_counter - self.dwell.entered_at_turn,
            "pending_transition": self.pending_transition.value if self.pending_transition else None,
            "detector_state": self.detector.get_state(),
            "events_count": len(self.event_log),
        }

    def get_preset_info(self) -> dict[str, Any]:
        """Get current preset configuration."""
        p = self.preset
        return {
            "name": p.name,
            "mode": p.mode.value,
            "description": p.mode.description,
            "claim_budget": p.claim_budget_per_turn,
            "novelty_tolerance": p.novelty_tolerance,
            "authority_posture": p.authority_posture,
            "variety_multiplier": p.variety_multiplier,
            "horizon_turns": p.horizon_turns,
            "cycle_period": p.cycle_period_turns,
            "hold_time": p.hold_time_turns,
            "min_dwell": p.min_dwell_turns,
            "tripwires": {
                "contradiction": p.contradiction_trip,
                "provenance": p.provenance_trip,
                "dangerous_claim": p.dangerous_claim_trip,
                "cascade": p.cascade_trip,
            },
        }

    def get_events(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get event log, optionally limited to most recent."""
        events = [e.to_dict() for e in self.event_log]
        if limit:
            events = events[-limit:]
        return events

    def to_dict(self) -> dict[str, Any]:
        """Serialize controller state to dictionary."""
        return {
            "mode": self.preset.mode.value,
            "turn_counter": self.turn_counter,
            "dwell": self.dwell.to_dict(),
            "pending_transition": self.pending_transition.value if self.pending_transition else None,
            "pending_reason": self.pending_reason,
            "event_log": [e.to_dict() for e in self.event_log],
            "detector": self.detector.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoilController":
        """Deserialize controller from dictionary."""
        mode = ControlMode(data["mode"])
        controller = cls(mode)
        controller.turn_counter = data["turn_counter"]
        controller.dwell = DwellState.from_dict(data["dwell"])
        controller.pending_transition = (
            OperationalRegime(data["pending_transition"])
            if data["pending_transition"] else None
        )
        controller.pending_reason = data.get("pending_reason")
        controller.event_log = [BoilEvent.from_dict(e) for e in data.get("event_log", [])]
        controller.detector = RegimeDetector.from_dict(data["detector"])
        return controller


def list_presets() -> list[dict[str, Any]]:
    """List all available presets with their key parameters."""
    return [
        {
            "mode": preset.mode.value,
            "name": preset.name,
            "description": preset.mode.description,
            "claim_budget": preset.claim_budget_per_turn,
            "novelty_tolerance": preset.novelty_tolerance,
            "authority_posture": preset.authority_posture,
            "tripwires_active": sum([
                preset.contradiction_trip,
                preset.provenance_trip,
                preset.dangerous_claim_trip,
                preset.cascade_trip,
            ]),
        }
        for preset in PRESETS.values()
    ]


def get_preset(mode: ControlMode | str) -> BoilPreset:
    """Get a preset by mode."""
    if isinstance(mode, str):
        mode = ControlMode(mode)
    return PRESETS[mode]
