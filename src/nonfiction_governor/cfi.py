# SPDX-License-Identifier: Apache-2.0
"""
Contextual Frame Intrusion (CFI) detector for nonfiction.

The nonfiction analogue of fiction's Demographic Salience Intrusion (DSI).
Detects when a model introduces interpretive frames not demanded by the text.

"Bad nonfiction is just fiction whose frames weren't declared."

CFI v0: detection + tagging + warnings only. No blocking.
8-15 frames, pattern-based, logged counts for refinement.

Based on ingest/next2.md: same control error as fiction, different nouns.
"""

from dataclasses import dataclass, field
from enum import Enum
import re


# =============================================================================
# Enums
# =============================================================================


class NonfictionFrame(str, Enum):
    """
    Interpretive frames that models inject into nonfiction.

    These are the "loud frames" — topics that activate strongly in the corpus
    and get substituted for missing state. v0 starter taxonomy: intentionally
    small, designed to expand by evidence (logged hits) rather than taste.
    """

    CAPITALISM = "capitalism"
    """Economic/market framing (neoliberalism, markets, profit motive)."""

    SOCIAL_JUSTICE = "social_justice"
    """Rights/equity/oppression framing (systemic racism, privilege, marginalized)."""

    TRAUMA = "trauma"
    """Psychological harm framing (trauma-informed, triggering, harm, healing)."""

    BOTH_SIDES = "both_sides"
    """Uninvited balance framing (on the other hand, critics argue, supporters say)."""

    EXPERTS_SAY = "experts_say"
    """Appeal to unnamed authority (experts say, studies show, research suggests)."""

    PROGRESS = "progress"
    """Teleological/improvement framing (advancing, evolving, modernizing)."""

    SAFETY = "safety"
    """Precautionary/risk framing (concerns, risks, potential dangers, safeguards)."""

    SYSTEMIC = "systemic"
    """Structural/institutional framing (systemic, institutional, structural forces)."""

    INDIVIDUAL = "individual"
    """Personal responsibility/agency framing (personal choice, self-improvement)."""

    NATURAL = "natural"
    """Naturalness/organic framing (natural, organic, artificial, unnatural)."""

    TECHNOLOGICAL = "technological"
    """Tech solutionism framing (innovation, disruption, digital transformation)."""

    MORAL = "moral"
    """Moral valence injection (right/wrong, ethical duty, moral imperative)."""


class Perspective(str, Enum):
    """Epistemic perspective of a text passage."""

    DESCRIPTIVE = "descriptive"
    """What is — observation, fact, data."""

    NORMATIVE = "normative"
    """What should be — values, ethics, judgment."""

    PRESCRIPTIVE = "prescriptive"
    """What to do — recommendations, instructions, policy."""

    ANALYTICAL = "analytical"
    """How it works — mechanism, explanation, causation."""


class CFIFaultType(str, Enum):
    """Types of contextual frame intrusion faults."""

    UNINVITED_FRAME = "uninvited_frame"
    """Frame appeared without textual demand."""

    FRAME_OVERUSE = "frame_overuse"
    """Same frame dominates across passages without justification."""

    NORMATIVE_CREEP = "normative_creep"
    """Descriptive/analytical text drifted into normative territory."""

    SCOPE_VIOLATION = "scope_violation"
    """Case generalized to population without qualification."""


# =============================================================================
# Feature detection patterns
# =============================================================================


# Each frame has a set of (regex_pattern, weight) tuples.
# More matches = higher confidence. Same architecture as fiction context_drift.
FRAME_FEATURES: dict[NonfictionFrame, list[tuple[str, float]]] = {
    NonfictionFrame.CAPITALISM: [
        (r"\b(capitalis[mt]|neoliberal(ism)?|free[\s-]?market)\b", 1.5),
        (r"\b(profit[\s-]?motive|commodif(y|ication)|privatiz(e|ation))\b", 1.2),
        (r"\b(market[\s-]?forces?|invisible[\s-]?hand|supply[\s-]?and[\s-]?demand)\b", 1.0),
        (r"\b(economic[\s-]?system|wealth[\s-]?gap|inequality)\b", 0.7),
        (r"\b(corporat(e|ion|ism)|exploitat(ion|ive))\b", 0.9),
    ],
    NonfictionFrame.SOCIAL_JUSTICE: [
        (r"\b(systemic[\s-]?racism|white[\s-]?privilege|intersectional(ity)?)\b", 1.5),
        (r"\b(marginalized|oppressed|disenfranchised|underrepresented)\b", 1.2),
        (r"\b(social[\s-]?justice|equity|inclusiv(e|ity)|diversity)\b", 1.0),
        (r"\b(power[\s-]?dynamics?|hegemony|patriarch(y|al))\b", 1.0),
        (r"\b(colonialis[mt]|decoloniz(e|ation)|indigenous[\s-]?rights)\b", 1.2),
    ],
    NonfictionFrame.TRAUMA: [
        (r"\b(trauma(tic|tized)?|retraumatiz(e|ing|ation))\b", 1.5),
        (r"\b(trigger(ed|ing)?[\s-]?warning|content[\s-]?warning)\b", 1.2),
        (r"\b(harm[\s-]?reduction|safe[\s-]?space|healing[\s-]?journey)\b", 1.0),
        (r"\b(emotional[\s-]?labor|burnout|self[\s-]?care)\b", 0.8),
        (r"\b(generational[\s-]?trauma|ACE[\s-]?score|PTSD)\b", 1.2),
    ],
    NonfictionFrame.BOTH_SIDES: [
        (r"\bon[\s-]?the[\s-]?other[\s-]?hand\b", 1.5),
        (r"\b(critics[\s-]?argue|supporters[\s-]?say|proponents[\s-]?claim)\b", 1.2),
        (r"\b(some[\s-]?argue|others[\s-]?contend|both[\s-]?sides)\b", 1.0),
        (r"\b(the[\s-]?debate|controversial|polariz(ed|ing))\b", 0.8),
        (r"\b(however,[\s-]?many|while[\s-]?some|there[\s-]?are[\s-]?those[\s-]?who)\b", 0.9),
    ],
    NonfictionFrame.EXPERTS_SAY: [
        (r"\b(experts?[\s-]?say|experts?[\s-]?agree|experts?[\s-]?warn)\b", 1.5),
        (r"\b(studies[\s-]?show|research[\s-]?suggests?|evidence[\s-]?indicates?)\b", 1.2),
        (r"\b(according[\s-]?to[\s-]?(experts?|researchers?|scientists?))\b", 1.0),
        (r"\b(the[\s-]?scientific[\s-]?consensus|peer[\s-]?reviewed)\b", 0.8),
        (r"\b(it[\s-]?is[\s-]?widely[\s-]?(accepted|believed|known))\b", 1.0),
    ],
    NonfictionFrame.PROGRESS: [
        (r"\b(progress(ive|ion)?|advancing|moving[\s-]?forward)\b", 1.0),
        (r"\b(evolv(e|ing)|moderniz(e|ation|ing)|transform(ation|ative))\b", 1.0),
        (r"\b(inevitable|inexorable|march[\s-]?of[\s-]?(progress|history))\b", 1.2),
        (r"\b(arc[\s-]?of[\s-]?(history|justice)|right[\s-]?side[\s-]?of[\s-]?history)\b", 1.5),
        (r"\b(backward|regressive|outdated|behind[\s-]?the[\s-]?times)\b", 0.8),
    ],
    NonfictionFrame.SAFETY: [
        (r"\b(potential[\s-]?dangers?|potential[\s-]?risks?|safety[\s-]?concerns?)\b", 1.2),
        (r"\b(precautionary|safeguard(s|ing)?|mitigat(e|ion))\b", 1.0),
        (r"\b(risk[\s-]?assessment|worst[\s-]?case[\s-]?scenario)\b", 0.9),
        (r"\b(unintended[\s-]?consequences|slippery[\s-]?slope)\b", 1.0),
        (r"\b(alarm(ing|ist)?|catastroph(e|ic)|existential[\s-]?risk)\b", 0.8),
    ],
    NonfictionFrame.SYSTEMIC: [
        (r"\b(systemic|structural|institutional)\b", 1.2),
        (r"\b(root[\s-]?causes?|underlying[\s-]?structures?)\b", 1.0),
        (r"\b(power[\s-]?structures?|systems?[\s-]?of[\s-]?(oppression|control))\b", 1.2),
        (r"\b(institutional(ized)?|entrenched|embedded)\b", 0.8),
        (r"\b(dismantle|overhaul|reform[\s-]?the[\s-]?system)\b", 1.0),
    ],
    NonfictionFrame.INDIVIDUAL: [
        (r"\b(personal[\s-]?responsibility|individual[\s-]?choice)\b", 1.2),
        (r"\b(self[\s-]?improvement|personal[\s-]?growth|empowerment)\b", 1.0),
        (r"\b(bootstrap|pull[\s-]?yourself[\s-]?up|grit|resilience)\b", 1.0),
        (r"\b(meritocra(cy|tic)|hard[\s-]?work[\s-]?pays[\s-]?off)\b", 1.0),
        (r"\b(agency|autonomy|self[\s-]?determin(ation|ed))\b", 0.7),
    ],
    NonfictionFrame.NATURAL: [
        (r"\b(natural|organic|unnatural|artificial)\b", 0.9),
        (r"\b(nature[\s-]?intended|against[\s-]?nature|natural[\s-]?order)\b", 1.5),
        (r"\b(GMO|synthetic|processed|chemical[\s-]?free)\b", 1.0),
        (r"\b(holistic|alternative[\s-]?(medicine|therapy))\b", 0.8),
        (r"\b(toxin|detox|clean[\s-]?(eating|living))\b", 0.9),
    ],
    NonfictionFrame.TECHNOLOGICAL: [
        (r"\b(disrupt(ion|ive)?|innovati(on|ve)|paradigm[\s-]?shift)\b", 1.2),
        (r"\b(digital[\s-]?transformation|tech[\s-]?solution|automation)\b", 1.0),
        (r"\b(AI[\s-]?will|blockchain[\s-]?can|machine[\s-]?learning[\s-]?enables?)\b", 1.0),
        (r"\b(cutting[\s-]?edge|state[\s-]?of[\s-]?the[\s-]?art|next[\s-]?generation)\b", 0.8),
        (r"\b(scale|scalab(le|ility)|optimize|leverage)\b", 0.7),
    ],
    NonfictionFrame.MORAL: [
        (r"\b(moral[\s-]?(imperative|duty|obligation|responsibility))\b", 1.5),
        (r"\b(ethically[\s-]?(wrong|right|questionable|problematic))\b", 1.2),
        (r"\b(unconscionable|reprehensible|morally[\s-]?bankrupt)\b", 1.5),
        (r"\b(virtue|sin|righteous|wicked)\b", 0.8),
        (r"\b(we[\s-]?must|we[\s-]?should|it[\s-]?is[\s-]?our[\s-]?duty)\b", 0.9),
    ],
}


# Perspective detection patterns
PERSPECTIVE_FEATURES: dict[Perspective, list[tuple[str, float]]] = {
    Perspective.DESCRIPTIVE: [
        (r"\b(is|are|was|were|has[\s-]?been|have[\s-]?been)\b", 0.3),
        (r"\b(observed|measured|recorded|found|reported)\b", 1.0),
        (r"\b(data[\s-]?shows?|statistics?[\s-]?indicate|survey[\s-]?found)\b", 1.2),
        (r"\b(approximately|roughly|about|around)\b", 0.5),
        (r"\b(according[\s-]?to|as[\s-]?of|in[\s-]?(19|20)\d{2})\b", 0.8),
    ],
    Perspective.NORMATIVE: [
        (r"\b(should|ought[\s-]?to|must|need[\s-]?to)\b", 1.0),
        (r"\b(right|wrong|good|bad|just|unjust|fair|unfair)\b", 0.8),
        (r"\b(ethic(al|s)|moral(ly)?|virtue|value[sd]?)\b", 1.0),
        (r"\b(deserv(e|es|ing)|entitle[ds]?|obligat(ed|ion))\b", 1.0),
        (r"\b(unacceptable|intolerable|imperative|essential)\b", 0.9),
    ],
    Perspective.PRESCRIPTIVE: [
        (r"\b(recommend(s|ed|ation)?|advis(e|ed|able)|suggest(s|ed)?)\b", 1.2),
        (r"\b(implement|adopt|establish|introduce|deploy)\b", 0.8),
        (r"\b(best[\s-]?practice|guideline|protocol|procedure)\b", 1.0),
        (r"\b(step[\s-]?\d|first,|second,|third,|finally,)\b", 0.7),
        (r"\b(in[\s-]?order[\s-]?to|to[\s-]?achieve|to[\s-]?ensure)\b", 0.6),
    ],
    Perspective.ANALYTICAL: [
        (r"\b(because|therefore|consequently|thus|hence)\b", 0.8),
        (r"\b(mechanism|process|function|system|structure)\b", 0.7),
        (r"\b(caus(e[ds]?|al|ation)|effect|impact|result(s|ing)?)\b", 0.9),
        (r"\b(factor|variable|correlat(e|ion)|relationship)\b", 0.8),
        (r"\b(explains?|account(s|ed)?[\s-]?for|contribut(e|es|ing)[\s-]?to)\b", 1.0),
    ],
}


# Scope violation patterns (case → population generalization)
SCOPE_PATTERNS: list[tuple[str, float]] = [
    (r"\b(this[\s-]?shows?[\s-]?that[\s-]?all|proves?[\s-]?that[\s-]?every)\b", 1.5),
    (r"\b(always|never|everyone|nobody|all[\s-]?people)\b", 0.8),
    (r"\b(universally|without[\s-]?exception|in[\s-]?every[\s-]?case)\b", 1.2),
    (r"\b(people[\s-]?are|humans[\s-]?are|society[\s-]?is)\b", 0.6),
    (r"\b(it[\s-]?is[\s-]?clear[\s-]?that|undeniably|unquestionably)\b", 0.9),
]


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class FrameSignal:
    """Result of detecting a frame in text."""

    frame: NonfictionFrame
    confidence: float
    matches: int = 0  # Number of pattern hits

    def to_dict(self) -> dict:
        return {
            "frame": self.frame.value,
            "confidence": round(self.confidence, 3),
            "matches": self.matches,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FrameSignal":
        return cls(
            frame=NonfictionFrame(d["frame"]),
            confidence=d["confidence"],
            matches=d.get("matches", 0),
        )


@dataclass
class PerspectiveSignal:
    """Result of detecting the perspective of a text passage."""

    perspective: Perspective
    confidence: float

    def to_dict(self) -> dict:
        return {
            "perspective": self.perspective.value,
            "confidence": round(self.confidence, 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PerspectiveSignal":
        return cls(
            perspective=Perspective(d["perspective"]),
            confidence=d["confidence"],
        )


@dataclass
class CFIFault:
    """A detected contextual frame intrusion fault."""

    fault_type: CFIFaultType
    detail: str
    frame: NonfictionFrame | None = None
    severity: str = "warning"  # Always "warning" in v0

    def to_dict(self) -> dict:
        return {
            "fault_type": self.fault_type.value,
            "detail": self.detail,
            "frame": self.frame.value if self.frame else None,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CFIFault":
        return cls(
            fault_type=CFIFaultType(d["fault_type"]),
            detail=d["detail"],
            frame=NonfictionFrame(d["frame"]) if d.get("frame") else None,
            severity=d.get("severity", "warning"),
        )


@dataclass
class CFICheckResult:
    """Result of a CFI check on a text passage."""

    frames_detected: list[FrameSignal] = field(default_factory=list)
    perspective: PerspectiveSignal | None = None
    faults: list[CFIFault] = field(default_factory=list)
    scope_risk: float = 0.0  # 0-1 scope violation risk

    @property
    def has_faults(self) -> bool:
        return len(self.faults) > 0

    def to_dict(self) -> dict:
        return {
            "frames_detected": [f.to_dict() for f in self.frames_detected],
            "perspective": self.perspective.to_dict() if self.perspective else None,
            "faults": [f.to_dict() for f in self.faults],
            "scope_risk": round(self.scope_risk, 3),
            "has_faults": self.has_faults,
        }


@dataclass
class CFIState:
    """
    Persistent state for CFI tracking across passages.

    Tracks frame hit counts for refinement and overuse detection.
    """

    frame_counts: dict[str, int] = field(default_factory=dict)
    total_checks: int = 0
    total_faults: int = 0
    perspective_history: list[str] = field(default_factory=list)
    expected_frames: list[str] = field(default_factory=list)
    expected_perspective: str | None = None

    def record_frames(self, frames: list[FrameSignal]) -> None:
        """Record detected frames for frequency tracking."""
        for f in frames:
            self.frame_counts[f.frame.value] = (
                self.frame_counts.get(f.frame.value, 0) + 1
            )

    def record_perspective(self, p: PerspectiveSignal) -> None:
        """Record perspective for drift tracking."""
        self.perspective_history.append(p.perspective.value)
        # Keep last 20 for windowed analysis
        if len(self.perspective_history) > 20:
            self.perspective_history = self.perspective_history[-20:]

    def dominant_frame(self) -> str | None:
        """Return the most frequently detected frame, if any."""
        if not self.frame_counts:
            return None
        return max(self.frame_counts, key=self.frame_counts.get)

    def frame_ratio(self, frame: str) -> float:
        """What fraction of checks detected this frame?"""
        if self.total_checks == 0:
            return 0.0
        return self.frame_counts.get(frame, 0) / self.total_checks

    def to_dict(self) -> dict:
        return {
            "frame_counts": dict(self.frame_counts),
            "total_checks": self.total_checks,
            "total_faults": self.total_faults,
            "perspective_history": list(self.perspective_history),
            "expected_frames": list(self.expected_frames),
            "expected_perspective": self.expected_perspective,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CFIState":
        return cls(
            frame_counts=d.get("frame_counts", {}),
            total_checks=d.get("total_checks", 0),
            total_faults=d.get("total_faults", 0),
            perspective_history=d.get("perspective_history", []),
            expected_frames=d.get("expected_frames", []),
            expected_perspective=d.get("expected_perspective"),
        )


# =============================================================================
# CFI Detector
# =============================================================================


# Compiled pattern cache
_COMPILED_FRAME_PATTERNS: dict[NonfictionFrame, list[tuple[re.Pattern, float]]] = {}
_COMPILED_PERSPECTIVE_PATTERNS: dict[Perspective, list[tuple[re.Pattern, float]]] = {}
_COMPILED_SCOPE_PATTERNS: list[tuple[re.Pattern, float]] = []


def _ensure_compiled() -> None:
    """Lazily compile all regex patterns."""
    if _COMPILED_FRAME_PATTERNS:
        return
    for frame, patterns in FRAME_FEATURES.items():
        _COMPILED_FRAME_PATTERNS[frame] = [
            (re.compile(p, re.IGNORECASE), w) for p, w in patterns
        ]
    for persp, patterns in PERSPECTIVE_FEATURES.items():
        _COMPILED_PERSPECTIVE_PATTERNS[persp] = [
            (re.compile(p, re.IGNORECASE), w) for p, w in patterns
        ]
    for p, w in SCOPE_PATTERNS:
        _COMPILED_SCOPE_PATTERNS.append((re.compile(p, re.IGNORECASE), w))


# Minimum confidence to report a frame as detected
DEFAULT_FRAME_THRESHOLD = 0.3

# Frame ratio above which overuse is flagged
DEFAULT_OVERUSE_THRESHOLD = 0.6

# Minimum checks before overuse tracking kicks in
MIN_CHECKS_FOR_OVERUSE = 5


@dataclass
class CFIConfig:
    """Configuration for the CFI detector."""

    frame_threshold: float = DEFAULT_FRAME_THRESHOLD
    overuse_threshold: float = DEFAULT_OVERUSE_THRESHOLD
    min_checks_for_overuse: int = MIN_CHECKS_FOR_OVERUSE
    normative_creep_window: int = 5  # Look back N perspective records

    def to_dict(self) -> dict:
        return {
            "frame_threshold": self.frame_threshold,
            "overuse_threshold": self.overuse_threshold,
            "min_checks_for_overuse": self.min_checks_for_overuse,
            "normative_creep_window": self.normative_creep_window,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CFIConfig":
        return cls(
            frame_threshold=d.get("frame_threshold", DEFAULT_FRAME_THRESHOLD),
            overuse_threshold=d.get("overuse_threshold", DEFAULT_OVERUSE_THRESHOLD),
            min_checks_for_overuse=d.get("min_checks_for_overuse", MIN_CHECKS_FOR_OVERUSE),
            normative_creep_window=d.get("normative_creep_window", 5),
        )


class CFIDetector:
    """
    Contextual Frame Intrusion detector.

    Detects uninvited interpretive frames, perspective drift, scope violations,
    and frame overuse in nonfiction text. v0: warnings only, no blocking.

    Usage:
        detector = CFIDetector()
        detector.set_expected_frames([NonfictionFrame.ANALYTICAL])
        detector.set_expected_perspective(Perspective.DESCRIPTIVE)
        result = detector.check("The text to analyze...")
        for fault in result.faults:
            print(f"[{fault.fault_type.value}] {fault.detail}")
    """

    def __init__(
        self,
        config: CFIConfig | None = None,
        state: CFIState | None = None,
    ):
        _ensure_compiled()
        self.config = config or CFIConfig()
        self.state = state or CFIState()

    def set_expected_frames(self, frames: list[NonfictionFrame]) -> None:
        """Set which frames are expected/invited for the current context."""
        self.state.expected_frames = [f.value for f in frames]

    def set_expected_perspective(self, perspective: Perspective) -> None:
        """Set the expected perspective for the current context."""
        self.state.expected_perspective = perspective.value

    def classify_frames(self, text: str) -> list[FrameSignal]:
        """
        Detect interpretive frames present in text.

        Returns frames above the confidence threshold, sorted by confidence.
        """
        results: list[FrameSignal] = []
        word_count = max(len(text.split()), 1)
        # Normalize: longer texts need more hits to register
        length_factor = min(1.0, 100 / word_count) if word_count > 100 else 1.0

        for frame, patterns in _COMPILED_FRAME_PATTERNS.items():
            total_weight = 0.0
            matches = 0
            for regex, weight in patterns:
                hits = len(regex.findall(text))
                if hits > 0:
                    matches += hits
                    total_weight += weight * min(hits, 3)  # Cap per-pattern

            if matches > 0:
                # Confidence: weighted hits normalized by pattern count
                max_possible = sum(w * 3 for _, w in patterns)
                confidence = min(1.0, (total_weight / max_possible) * (1.0 + length_factor))
                if confidence >= self.config.frame_threshold:
                    results.append(FrameSignal(
                        frame=frame,
                        confidence=confidence,
                        matches=matches,
                    ))

        results.sort(key=lambda s: s.confidence, reverse=True)
        return results

    def classify_perspective(self, text: str) -> PerspectiveSignal:
        """Classify the dominant epistemic perspective of text."""
        best_perspective = Perspective.DESCRIPTIVE
        best_score = 0.0

        for persp, patterns in _COMPILED_PERSPECTIVE_PATTERNS.items():
            total_weight = 0.0
            for regex, weight in patterns:
                hits = len(regex.findall(text))
                if hits > 0:
                    total_weight += weight * min(hits, 5)

            if total_weight > best_score:
                best_score = total_weight
                best_perspective = persp

        max_possible = max(
            sum(w * 5 for _, w in patterns)
            for patterns in _COMPILED_PERSPECTIVE_PATTERNS.values()
        )
        confidence = min(1.0, best_score / max_possible) if max_possible > 0 else 0.5

        return PerspectiveSignal(
            perspective=best_perspective,
            confidence=confidence,
        )

    def check_scope(self, text: str) -> float:
        """Check for scope violation risk (case → population generalization)."""
        total_weight = 0.0
        for regex, weight in _COMPILED_SCOPE_PATTERNS:
            hits = len(regex.findall(text))
            if hits > 0:
                total_weight += weight * min(hits, 3)

        max_possible = sum(w * 3 for _, w in _COMPILED_SCOPE_PATTERNS)
        return min(1.0, total_weight / max_possible) if max_possible > 0 else 0.0

    def check(self, text: str) -> CFICheckResult:
        """
        Run full CFI check on text. Returns detected frames, perspective,
        and any faults. Does NOT update state (use record() for that).
        """
        frames = self.classify_frames(text)
        perspective = self.classify_perspective(text)
        scope_risk = self.check_scope(text)
        faults: list[CFIFault] = []

        # Fault 1: Uninvited frames
        if self.state.expected_frames:
            expected_set = set(self.state.expected_frames)
            for fs in frames:
                if fs.frame.value not in expected_set and fs.confidence >= 0.5:
                    faults.append(CFIFault(
                        fault_type=CFIFaultType.UNINVITED_FRAME,
                        detail=(
                            f"Frame '{fs.frame.value}' detected "
                            f"(confidence={fs.confidence:.2f}) "
                            f"but not in expected frames: {sorted(expected_set)}"
                        ),
                        frame=fs.frame,
                    ))

        # Fault 2: Frame overuse (needs history)
        if self.state.total_checks >= self.config.min_checks_for_overuse:
            for fs in frames:
                ratio = self.state.frame_ratio(fs.frame.value)
                if ratio >= self.config.overuse_threshold:
                    faults.append(CFIFault(
                        fault_type=CFIFaultType.FRAME_OVERUSE,
                        detail=(
                            f"Frame '{fs.frame.value}' detected in "
                            f"{ratio:.0%} of checks "
                            f"(threshold: {self.config.overuse_threshold:.0%})"
                        ),
                        frame=fs.frame,
                    ))

        # Fault 3: Normative creep
        if self.state.expected_perspective:
            expected = self.state.expected_perspective
            if expected in ("descriptive", "analytical"):
                if perspective.perspective == Perspective.NORMATIVE:
                    faults.append(CFIFault(
                        fault_type=CFIFaultType.NORMATIVE_CREEP,
                        detail=(
                            f"Expected {expected} perspective but detected "
                            f"normative (confidence={perspective.confidence:.2f})"
                        ),
                    ))
                # Also check windowed history for gradual creep
                window = self.state.perspective_history[
                    -self.config.normative_creep_window:
                ]
                if len(window) >= 3:
                    normative_count = sum(
                        1 for p in window if p == "normative"
                    )
                    if normative_count >= len(window) // 2:
                        # Only add if not already flagged above
                        if not any(
                            f.fault_type == CFIFaultType.NORMATIVE_CREEP
                            for f in faults
                        ):
                            faults.append(CFIFault(
                                fault_type=CFIFaultType.NORMATIVE_CREEP,
                                detail=(
                                    f"Normative perspective appearing in "
                                    f"{normative_count}/{len(window)} recent "
                                    f"passages (expected {expected})"
                                ),
                            ))

        # Fault 4: Scope violations
        if scope_risk >= 0.4:
            faults.append(CFIFault(
                fault_type=CFIFaultType.SCOPE_VIOLATION,
                detail=(
                    f"Scope violation risk: {scope_risk:.2f} "
                    f"(case→population generalization detected)"
                ),
            ))

        return CFICheckResult(
            frames_detected=frames,
            perspective=perspective,
            faults=faults,
            scope_risk=scope_risk,
        )

    def record(self, text: str) -> CFICheckResult:
        """
        Check text AND update state. Use this for streaming/multi-passage analysis.
        """
        result = self.check(text)
        self.state.total_checks += 1
        self.state.record_frames(result.frames_detected)
        if result.perspective:
            self.state.record_perspective(result.perspective)
        self.state.total_faults += len(result.faults)
        return result

    def reset(self) -> None:
        """Reset detector state (keeps config and expected frames/perspective)."""
        expected_frames = self.state.expected_frames
        expected_perspective = self.state.expected_perspective
        self.state = CFIState(
            expected_frames=expected_frames,
            expected_perspective=expected_perspective,
        )

    def stats(self) -> dict:
        """Return summary statistics for refinement."""
        return {
            "total_checks": self.state.total_checks,
            "total_faults": self.state.total_faults,
            "fault_rate": (
                self.state.total_faults / self.state.total_checks
                if self.state.total_checks > 0
                else 0.0
            ),
            "frame_counts": dict(self.state.frame_counts),
            "dominant_frame": self.state.dominant_frame(),
            "perspective_distribution": _perspective_distribution(
                self.state.perspective_history
            ),
        }

    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "state": self.state.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CFIDetector":
        return cls(
            config=CFIConfig.from_dict(d.get("config", {})),
            state=CFIState.from_dict(d.get("state", {})),
        )


def _perspective_distribution(history: list[str]) -> dict[str, float]:
    """Compute perspective distribution from history."""
    if not history:
        return {}
    counts: dict[str, int] = {}
    for p in history:
        counts[p] = counts.get(p, 0) + 1
    total = len(history)
    return {k: round(v / total, 3) for k, v in sorted(counts.items())}


# =============================================================================
# Convenience functions
# =============================================================================


def detect_frames(text: str, threshold: float = DEFAULT_FRAME_THRESHOLD) -> list[FrameSignal]:
    """Quick frame detection on a text passage."""
    detector = CFIDetector(config=CFIConfig(frame_threshold=threshold))
    return detector.classify_frames(text)


def detect_perspective(text: str) -> PerspectiveSignal:
    """Quick perspective classification."""
    detector = CFIDetector()
    return detector.classify_perspective(text)


def check_cfi(
    text: str,
    expected_frames: list[NonfictionFrame] | None = None,
    expected_perspective: Perspective | None = None,
) -> CFICheckResult:
    """Quick one-shot CFI check."""
    detector = CFIDetector()
    if expected_frames:
        detector.set_expected_frames(expected_frames)
    if expected_perspective:
        detector.set_expected_perspective(expected_perspective)
    return detector.check(text)
