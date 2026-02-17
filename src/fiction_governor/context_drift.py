# SPDX-License-Identifier: Apache-2.0
"""
Context drift detection for the fiction governor.

Tracks narrative mode/register with hysteresis-based transition guards.
Detects unsignaled genre escalation, register shifts, and mode chatter.

Based on ingest/next.md: "Context Drift as a first-class hazard."

Key insight: unsignaled transition is the violation, not the content itself.
"""

from dataclasses import dataclass, field
from enum import Enum
import re


class NarrativeMode(Enum):
    """Discrete narrative mode / register families."""

    LITERARY = "literary"
    CONTEMPORARY = "contemporary"
    FANFIC = "fanfic"
    ROMANCE = "romance"
    EROTIC = "erotic"
    GRIMDARK = "grimdark"
    YA = "ya"
    COMEDIC = "comedic"
    TECHNICAL = "technical"
    HISTORICAL = "historical"


class RiskTier(Enum):
    """Risk tier for narrative modes. Higher risk requires explicit user opt-in."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DriftFaultType(Enum):
    """Types of context drift faults."""

    UNSIGNALED_REGISTER_SHIFT = "unsignaled_register_shift"
    """Register changed without user cue."""

    GENRE_ESCALATION = "genre_escalation"
    """Risk tier increased without explicit enablement."""

    MODE_CHATTER = "mode_chatter"
    """Rapid back-and-forth mode switching (instability)."""


# --- Risk tier mapping ---

RISK_TIER_MAP: dict[NarrativeMode, RiskTier] = {
    NarrativeMode.LITERARY: RiskTier.LOW,
    NarrativeMode.CONTEMPORARY: RiskTier.LOW,
    NarrativeMode.HISTORICAL: RiskTier.LOW,
    NarrativeMode.TECHNICAL: RiskTier.LOW,
    NarrativeMode.YA: RiskTier.LOW,
    NarrativeMode.COMEDIC: RiskTier.LOW,
    NarrativeMode.FANFIC: RiskTier.MEDIUM,
    NarrativeMode.ROMANCE: RiskTier.MEDIUM,
    NarrativeMode.GRIMDARK: RiskTier.MEDIUM,
    NarrativeMode.EROTIC: RiskTier.HIGH,
}

# Risk tier ordering for escalation checks
RISK_ORDER: dict[RiskTier, int] = {
    RiskTier.LOW: 0,
    RiskTier.MEDIUM: 1,
    RiskTier.HIGH: 2,
}


# --- Feature detection patterns ---

# Each mode has a set of feature patterns. More matches = higher confidence.
MODE_FEATURES: dict[NarrativeMode, list[tuple[str, float]]] = {
    NarrativeMode.LITERARY: [
        (r"\b(metaphor|allegory|motif|symbolism|prose)\b", 1.0),
        (r"\b(murmured|whispered|gazed|beheld|trembled)\b", 0.7),
        (r"\b(whilst|beneath|amidst|henceforth)\b", 0.8),
        (r"\b(juxtapos|dichotomy|ephemeral|melanchol)\b", 1.0),
        (r";", 0.3),  # semicolons in fiction = literary
    ],
    NarrativeMode.CONTEMPORARY: [
        (r"\b(phone|text|email|internet|app|social media)\b", 0.8),
        (r"\b(uber|instagram|tiktok|spotify|netflix)\b", 1.0),
        (r"\b(okay|yeah|gonna|wanna|kinda|sorta)\b", 0.5),
        (r"\b(apartment|coffee shop|subway|office)\b", 0.4),
    ],
    NarrativeMode.FANFIC: [
        (r"\b(AU|canon|OOC|OC|headcanon|ship|fandom)\b", 1.5),
        (r"\b(slow burn|enemies to lovers|hurt/comfort|angst)\b", 1.5),
        (r"\b(POV|drabble|oneshot|ficlet)\b", 1.2),
        (r"---+", 0.3),  # scene breaks with dashes
        (r"\b(orbs|pools|cerulean|raven-haired)\b", 0.8),  # fanfic-isms
    ],
    NarrativeMode.ROMANCE: [
        (r"\b(heart\s+(pounded|raced|fluttered|skipped))\b", 1.0),
        (r"\b(kiss(ed|ing)?|embrace[ds]?|caress(ed|ing)?)\b", 0.8),
        (r"\b(desire|longing|yearning|ache[ds]?)\b", 0.9),
        (r"\b(lips|mouth|breath|pulse|skin)\b", 0.4),
        (r"\b(chemistry|attraction|tension)\b", 0.6),
    ],
    NarrativeMode.EROTIC: [
        (r"\b(thrust(ed|ing)?|moan(ed|ing)?|groan(ed|ing)?)\b", 1.5),
        (r"\b(naked|nude|undress(ed|ing)?|strip(ped|ping)?)\b", 1.0),
        (r"\b(arousal|orgasm|climax(ed)?|erect(ion)?)\b", 2.0),
        (r"\b(nipple|breast|groin|thigh)\b", 1.0),
        (r"\b(pant(ed|ing)|writhe[ds]?|shudder(ed|ing)?)\b", 0.8),
    ],
    NarrativeMode.GRIMDARK: [
        (r"\b(blood|gore|viscera|entrails|corpse)\b", 1.0),
        (r"\b(torture[ds]?|maim(ed)?|mutilat(ed|ion))\b", 1.5),
        (r"\b(despair|hopeless|bleak|desolat(e|ion))\b", 0.8),
        (r"\b(slaughter(ed)?|massacre[ds]?|carnage)\b", 1.2),
        (r"\b(rotting|decay(ed|ing)?|putrid|fetid)\b", 0.9),
    ],
    NarrativeMode.YA: [
        (r"\b(school|class(room)?|homework|teacher|principal)\b", 0.8),
        (r"\b(best friend|crush|prom|locker|hallway)\b", 0.9),
        (r"\b(parents|mom|dad|bedroom|curfew)\b", 0.5),
        (r"\b(totally|like,|OMG|whatever)\b", 0.7),
        (r"\b(diary|journal|secret)\b", 0.4),
    ],
    NarrativeMode.COMEDIC: [
        (r"\b(snorted|guffawed|chortled|snickered)\b", 1.0),
        (r"\b(absurd(ly)?|ridiculous(ly)?|preposterous)\b", 0.8),
        (r"\b(sarcas(m|tic)|ironi(c|cally)|deadpan)\b", 0.9),
        (r"[!]{2,}", 0.5),  # multiple exclamation marks
        (r"\b(bumbl(ed|ing)|stumbl(ed|ing)|flail(ed|ing))\b", 0.7),
    ],
    NarrativeMode.TECHNICAL: [
        (r"\b(algorithm|function|variable|parameter)\b", 1.0),
        (r"\b(implement(ed|ation)?|configur(e|ation)|deploy)\b", 0.8),
        (r"\b(API|SDK|CLI|SQL|HTTP|JSON|YAML)\b", 1.2),
        (r"```", 1.5),  # code blocks
        (r"\b(class|method|interface|module)\b", 0.7),
    ],
    NarrativeMode.HISTORICAL: [
        (r"\b(king|queen|emperor|duke|baron|lord)\b", 0.6),
        (r"\b(castle|manor|court|throne|crown)\b", 0.7),
        (r"\b(sword|shield|armor|steed|chariot)\b", 0.8),
        (r"\b(century|era|dynasty|reign|anno)\b", 0.9),
        (r"\b(thou|thee|thy|hath|doth|wherefore)\b", 1.2),
    ],
}


# --- Dataclasses ---


@dataclass
class HysteresisConfig:
    """Hysteresis thresholds for mode transitions.

    theta_up: confidence required to switch TO a new mode
    theta_down: confidence below which we stay in current mode
    Gap between them prevents mode-chatter.
    """

    theta_up: float = 0.75
    theta_down: float = 0.55
    min_tokens_between_switches: int = 100
    max_transitions_per_window: int = 3
    window_size_tokens: int = 2000

    def to_dict(self) -> dict:
        return {
            "theta_up": self.theta_up,
            "theta_down": self.theta_down,
            "min_tokens_between_switches": self.min_tokens_between_switches,
            "max_transitions_per_window": self.max_transitions_per_window,
            "window_size_tokens": self.window_size_tokens,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HysteresisConfig":
        return cls(
            theta_up=d.get("theta_up", 0.75),
            theta_down=d.get("theta_down", 0.55),
            min_tokens_between_switches=d.get("min_tokens_between_switches", 100),
            max_transitions_per_window=d.get("max_transitions_per_window", 3),
            window_size_tokens=d.get("window_size_tokens", 2000),
        )


@dataclass
class ModeSignal:
    """Result of classifying a text's narrative mode."""

    mode: NarrativeMode
    confidence: float
    features: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "confidence": self.confidence,
            "features": self.features,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModeSignal":
        return cls(
            mode=NarrativeMode(d["mode"]),
            confidence=d["confidence"],
            features=d.get("features", {}),
        )


@dataclass
class ModeTransition:
    """Record of a mode transition."""

    from_mode: NarrativeMode
    to_mode: NarrativeMode
    at_token: int
    confidence: float
    user_signaled: bool = False

    def to_dict(self) -> dict:
        return {
            "from_mode": self.from_mode.value,
            "to_mode": self.to_mode.value,
            "at_token": self.at_token,
            "confidence": self.confidence,
            "user_signaled": self.user_signaled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModeTransition":
        return cls(
            from_mode=NarrativeMode(d["from_mode"]),
            to_mode=NarrativeMode(d["to_mode"]),
            at_token=d["at_token"],
            confidence=d["confidence"],
            user_signaled=d.get("user_signaled", False),
        )


@dataclass
class DriftFault:
    """A detected context drift violation."""

    fault_type: DriftFaultType
    detail: str
    severity: str = "warning"  # "warning" or "error"
    from_mode: NarrativeMode | None = None
    to_mode: NarrativeMode | None = None

    def to_dict(self) -> dict:
        return {
            "fault_type": self.fault_type.value,
            "detail": self.detail,
            "severity": self.severity,
            "from_mode": self.from_mode.value if self.from_mode else None,
            "to_mode": self.to_mode.value if self.to_mode else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DriftFault":
        return cls(
            fault_type=DriftFaultType(d["fault_type"]),
            detail=d["detail"],
            severity=d.get("severity", "warning"),
            from_mode=NarrativeMode(d["from_mode"]) if d.get("from_mode") else None,
            to_mode=NarrativeMode(d["to_mode"]) if d.get("to_mode") else None,
        )


@dataclass
class DriftState:
    """Current state of the context drift detector."""

    current_mode: NarrativeMode = NarrativeMode.LITERARY
    risk_tier: RiskTier = RiskTier.LOW
    mode_conf: float = 0.5
    last_switch_token: int = 0
    transitions: list[ModeTransition] = field(default_factory=list)
    hysteresis: HysteresisConfig = field(default_factory=HysteresisConfig)

    def to_dict(self) -> dict:
        return {
            "current_mode": self.current_mode.value,
            "risk_tier": self.risk_tier.value,
            "mode_conf": self.mode_conf,
            "last_switch_token": self.last_switch_token,
            "transitions": [t.to_dict() for t in self.transitions],
            "hysteresis": self.hysteresis.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DriftState":
        return cls(
            current_mode=NarrativeMode(d["current_mode"]),
            risk_tier=RiskTier(d["risk_tier"]),
            mode_conf=d.get("mode_conf", 0.5),
            last_switch_token=d.get("last_switch_token", 0),
            transitions=[ModeTransition.from_dict(t) for t in d.get("transitions", [])],
            hysteresis=HysteresisConfig.from_dict(d["hysteresis"]) if "hysteresis" in d else HysteresisConfig(),
        )


# --- Helper functions ---


def _count_features(text: str, mode: NarrativeMode) -> dict[str, int]:
    """Count feature pattern matches for a given mode."""
    patterns = MODE_FEATURES.get(mode, [])
    counts: dict[str, int] = {}
    for pattern, _weight in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            counts[pattern] = len(matches)
    return counts


def _score_mode(text: str, mode: NarrativeMode) -> float:
    """Score how well text matches a narrative mode."""
    patterns = MODE_FEATURES.get(mode, [])
    if not patterns:
        return 0.0

    total_score = 0.0
    for pattern, weight in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Diminishing returns: first match counts most
            total_score += weight * min(len(matches), 3)

    # Normalize by text length (rough token estimate)
    words = len(text.split())
    if words == 0:
        return 0.0

    # Normalize to [0, 1] range
    # More features per word = higher score
    raw = total_score / max(words / 50, 1.0)
    return min(raw, 1.0)


def classify_register(text: str) -> list[ModeSignal]:
    """Classify text into narrative modes with confidence scores.

    Returns list of ModeSignal sorted by confidence (highest first).
    """
    if not text or not text.strip():
        return [ModeSignal(mode=NarrativeMode.LITERARY, confidence=0.0)]

    signals = []
    for mode in NarrativeMode:
        score = _score_mode(text, mode)
        if score > 0.0:
            features = _count_features(text, mode)
            signals.append(ModeSignal(mode=mode, confidence=score, features=features))

    if not signals:
        # No features matched — default to literary with low confidence
        return [ModeSignal(mode=NarrativeMode.LITERARY, confidence=0.1)]

    signals.sort(key=lambda s: s.confidence, reverse=True)
    return signals


def estimate_risk_tier(mode: NarrativeMode) -> RiskTier:
    """Get the risk tier for a narrative mode."""
    return RISK_TIER_MAP.get(mode, RiskTier.LOW)


# --- Main class ---


class ContextDriftDetector:
    """Detects context drift across genre/register boundaries.

    Uses hysteresis to prevent mode-chatter: a mode switch requires
    confidence above theta_up, and the current mode persists until
    confidence drops below theta_down.

    Treats unsignaled genre escalation (low→high risk) as a governance
    fault, not a content issue.
    """

    def __init__(self, hysteresis: HysteresisConfig | None = None):
        self._hysteresis = hysteresis or HysteresisConfig()
        self._state = DriftState(hysteresis=self._hysteresis)

    @property
    def state(self) -> DriftState:
        """Current drift detector state."""
        return self._state

    @property
    def current_mode(self) -> NarrativeMode:
        return self._state.current_mode

    @property
    def risk_tier(self) -> RiskTier:
        return self._state.risk_tier

    def classify(self, text: str) -> list[ModeSignal]:
        """Classify text register without updating state."""
        return classify_register(text)

    def check_transition(
        self,
        proposed_mode: NarrativeMode,
        confidence: float,
        user_signaled: bool = False,
        token_position: int = 0,
    ) -> DriftFault | None:
        """Check whether a mode transition should be allowed.

        Returns a DriftFault if the transition is problematic, None if OK.
        """
        current = self._state.current_mode
        current_tier = self._state.risk_tier
        proposed_tier = estimate_risk_tier(proposed_mode)

        # Same mode — no fault
        if proposed_mode == current:
            return None

        # Check hysteresis — confidence must exceed theta_up to switch
        if confidence < self._hysteresis.theta_up and not user_signaled:
            return None  # Not confident enough to trigger switch, stay put

        # Check minimum tokens between switches
        tokens_since = token_position - self._state.last_switch_token
        if tokens_since < self._hysteresis.min_tokens_between_switches and not user_signaled:
            return DriftFault(
                fault_type=DriftFaultType.MODE_CHATTER,
                detail=(
                    f"Mode switch attempted {tokens_since} tokens after last switch "
                    f"(minimum: {self._hysteresis.min_tokens_between_switches})"
                ),
                severity="warning",
                from_mode=current,
                to_mode=proposed_mode,
            )

        # Check transitions per window
        recent = [
            t for t in self._state.transitions
            if token_position - t.at_token < self._hysteresis.window_size_tokens
        ]
        if len(recent) >= self._hysteresis.max_transitions_per_window and not user_signaled:
            return DriftFault(
                fault_type=DriftFaultType.MODE_CHATTER,
                detail=(
                    f"{len(recent)} transitions in last {self._hysteresis.window_size_tokens} tokens "
                    f"(max: {self._hysteresis.max_transitions_per_window})"
                ),
                severity="warning",
                from_mode=current,
                to_mode=proposed_mode,
            )

        # Check risk escalation
        current_risk = RISK_ORDER[current_tier]
        proposed_risk = RISK_ORDER[proposed_tier]

        if proposed_risk > current_risk and not user_signaled:
            return DriftFault(
                fault_type=DriftFaultType.GENRE_ESCALATION,
                detail=(
                    f"Risk escalation from {current_tier.value} ({current.value}) "
                    f"to {proposed_tier.value} ({proposed_mode.value}) "
                    f"without user signal"
                ),
                severity="error",
                from_mode=current,
                to_mode=proposed_mode,
            )

        # Unsignaled register shift (same or lower risk, but different mode)
        if not user_signaled:
            return DriftFault(
                fault_type=DriftFaultType.UNSIGNALED_REGISTER_SHIFT,
                detail=(
                    f"Register shift from {current.value} to {proposed_mode.value} "
                    f"without user signal"
                ),
                severity="warning",
                from_mode=current,
                to_mode=proposed_mode,
            )

        return None

    def update(
        self,
        text: str,
        user_signaled: bool = False,
        token_position: int = 0,
    ) -> tuple[DriftState, DriftFault | None]:
        """Classify text, check transition, update state.

        Returns (updated_state, fault_or_none).
        """
        signals = self.classify(text)
        if not signals:
            return self._state, None

        top = signals[0]

        # Below theta_down — no change regardless
        if top.confidence < self._hysteresis.theta_down and top.mode != self._state.current_mode:
            return self._state, None

        # Same mode — just update confidence
        if top.mode == self._state.current_mode:
            self._state.mode_conf = top.confidence
            return self._state, None

        # Different mode — check transition
        fault = self.check_transition(top.mode, top.confidence, user_signaled, token_position)

        # If genre escalation (error), block the transition
        if fault and fault.severity == "error":
            return self._state, fault

        # Apply transition (warnings are advisory, not blocking)
        transition = ModeTransition(
            from_mode=self._state.current_mode,
            to_mode=top.mode,
            at_token=token_position,
            confidence=top.confidence,
            user_signaled=user_signaled,
        )
        self._state.transitions.append(transition)
        self._state.current_mode = top.mode
        self._state.risk_tier = estimate_risk_tier(top.mode)
        self._state.mode_conf = top.confidence
        self._state.last_switch_token = token_position

        return self._state, fault

    def force_mode(self, mode: NarrativeMode, token_position: int = 0) -> DriftState:
        """Force a mode change (user-initiated). No fault checking."""
        if mode != self._state.current_mode:
            transition = ModeTransition(
                from_mode=self._state.current_mode,
                to_mode=mode,
                at_token=token_position,
                confidence=1.0,
                user_signaled=True,
            )
            self._state.transitions.append(transition)
            self._state.current_mode = mode
            self._state.risk_tier = estimate_risk_tier(mode)
            self._state.mode_conf = 1.0
            self._state.last_switch_token = token_position
        return self._state

    def reset(self, mode: NarrativeMode = NarrativeMode.LITERARY) -> DriftState:
        """Reset detector to initial state."""
        self._state = DriftState(
            current_mode=mode,
            risk_tier=estimate_risk_tier(mode),
            hysteresis=self._hysteresis,
        )
        return self._state

    def to_dict(self) -> dict:
        return self._state.to_dict()

    @classmethod
    def from_dict(cls, d: dict) -> "ContextDriftDetector":
        hyst = HysteresisConfig.from_dict(d.get("hysteresis", {}))
        detector = cls(hysteresis=hyst)
        detector._state = DriftState.from_dict(d)
        return detector


# --- Convenience functions ---


def create_context_drift_detector(
    hysteresis: HysteresisConfig | None = None,
) -> ContextDriftDetector:
    """Create a context drift detector with optional custom hysteresis."""
    return ContextDriftDetector(hysteresis=hysteresis)
