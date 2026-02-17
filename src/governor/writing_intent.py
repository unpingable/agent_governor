# SPDX-License-Identifier: Apache-2.0
"""
Writing Intent — Intent classifier and ancillary regime scorers.

IntentCategory: 6 top-level intent categories (Execute, Calibrate, Coordinate, Mobilize, Evoke, Encode).
IntentClassifier: Signal-based intent classification from user query.
Ancillary Scorers: 12 regime-specific score functions (Ap, Fi, Au, Fp, Mt, Pa, Ut, Vv, De, Mc, Sa, Lm).
RegimeCollision: Collision detection for incompatible regime combinations.

Key insight from anc.md: each regime has a load-bearing variable.
Scoring that variable tells you if the regime is working.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .writing_patterns import (
    BUREAUCRATIC_PATTERNS,
    FAKE_CONFIDENCE_PATTERNS,
    GOOD_DIAGNOSTIC_PATTERNS,
    GOTCHA_PATTERNS,
    INSTRUCTION_FILLER_PATTERNS,
    MANIPULATION_PATTERNS,
    MORALIZING_PATTERNS,
    PREMATURE_CLOSURE_PATTERNS,
    count_pattern_matches,
)


# =============================================================================
# IntentCategory
# =============================================================================


class IntentCategory(str, Enum):
    """Top-level intent categories from anc.md."""

    EXECUTE = "execute"  # Instruction, Debugging
    CALIBRATE = "calibrate"  # Research, Nonfiction
    COORDINATE = "coordinate"  # Negotiation
    MOBILIZE = "mobilize"  # Advocacy, Marketing
    EVOKE = "evoke"  # Drama, Tragedy, Horror, Romance
    ENCODE = "encode"  # Satire, Aphorism, Liturgy


# =============================================================================
# IntentClassification
# =============================================================================


@dataclass
class IntentClassification:
    """Result of intent classification."""

    primary: IntentCategory
    confidence: float = 0.5
    secondary: IntentCategory | None = None
    signals: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "confidence": self.confidence,
            "secondary": self.secondary.value if self.secondary else None,
            "signals": self.signals,
        }


# =============================================================================
# IntentClassifier
# =============================================================================

# Signal keywords for each intent category
EXECUTE_SIGNALS = [
    r"\bhow (do|to|can)\b", r"\bsteps?\b", r"\binstruct", r"\bguide\b",
    r"\btutorial\b", r"\bdebug", r"\bfix\b", r"\berror\b", r"\bissue\b",
]

CALIBRATE_SIGNALS = [
    r"\bresearch\b", r"\bstudy\b", r"\banalys[ei]", r"\bexplain\b",
    r"\bwhy\b", r"\bevidence\b", r"\bdata\b", r"\bfact\b", r"\bclaim\b",
]

COORDINATE_SIGNALS = [
    r"\bnegotiat", r"\bcompromis", r"\bagree\b", r"\bdeal\b",
    r"\bdiscuss\b", r"\bpersuad", r"\bconvinc",
]

MOBILIZE_SIGNALS = [
    r"\badvoca", r"\bmarket", r"\bpromot", r"\bsell\b",
    r"\baction\b", r"\bcause\b", r"\bcampaign\b", r"\bmovemen",
]

EVOKE_SIGNALS = [
    r"\bstory\b", r"\bnarrat", r"\bfiction\b", r"\bcharacter\b",
    r"\bscene\b", r"\bplot\b", r"\bdrama", r"\bromance\b", r"\bhorror\b",
]

ENCODE_SIGNALS = [
    r"\bsatir", r"\birony\b", r"\bparody\b", r"\baphoris",
    r"\bproverb\b", r"\britual\b", r"\bceremony\b", r"\bpoem\b",
]


class IntentClassifier:
    """Signal-based intent classification.

    Uses keyword/pattern matching to classify user intent into one of
    6 categories. No ML - deterministic and testable.
    """

    def __init__(self) -> None:
        self._signal_patterns: dict[IntentCategory, list[re.Pattern[str]]] = {
            IntentCategory.EXECUTE: [re.compile(p, re.IGNORECASE) for p in EXECUTE_SIGNALS],
            IntentCategory.CALIBRATE: [re.compile(p, re.IGNORECASE) for p in CALIBRATE_SIGNALS],
            IntentCategory.COORDINATE: [re.compile(p, re.IGNORECASE) for p in COORDINATE_SIGNALS],
            IntentCategory.MOBILIZE: [re.compile(p, re.IGNORECASE) for p in MOBILIZE_SIGNALS],
            IntentCategory.EVOKE: [re.compile(p, re.IGNORECASE) for p in EVOKE_SIGNALS],
            IntentCategory.ENCODE: [re.compile(p, re.IGNORECASE) for p in ENCODE_SIGNALS],
        }

    def classify(
        self,
        user_query: str,
        context: str = "",
        explicit_mode: str | None = None,
    ) -> IntentClassification:
        """Classify user intent.

        Args:
            user_query: The user's query
            context: Additional context (conversation history)
            explicit_mode: Explicit mode override (e.g., "fiction", "code")

        Returns:
            IntentClassification with primary and optional secondary intent
        """
        # Explicit mode overrides
        if explicit_mode:
            mode_map = {
                "fiction": IntentCategory.EVOKE,
                "nonfiction": IntentCategory.CALIBRATE,
                "code": IntentCategory.EXECUTE,
                "research": IntentCategory.CALIBRATE,
                "instruction": IntentCategory.EXECUTE,
                "debugging": IntentCategory.EXECUTE,
            }
            if explicit_mode.lower() in mode_map:
                return IntentClassification(
                    primary=mode_map[explicit_mode.lower()],
                    confidence=0.9,
                    signals={"explicit_mode": 1.0},
                )

        # Count signal matches
        combined = user_query + " " + context
        scores: dict[IntentCategory, float] = {}
        signals: dict[str, float] = {}

        for category, patterns in self._signal_patterns.items():
            count = 0
            for pattern in patterns:
                matches = pattern.findall(combined)
                count += len(matches)
            score = min(count * 0.15, 1.0)
            scores[category] = score
            signals[category.value] = score

        # Find primary and secondary
        sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_cats[0][0]
        confidence = sorted_cats[0][1]

        secondary = None
        if len(sorted_cats) > 1 and sorted_cats[1][1] > 0.1:
            secondary = sorted_cats[1][0]

        # Default to CALIBRATE if no strong signal
        if confidence < 0.1:
            primary = IntentCategory.CALIBRATE
            confidence = 0.3

        return IntentClassification(
            primary=primary,
            confidence=confidence,
            secondary=secondary,
            signals=signals,
        )


# =============================================================================
# Ancillary Regime Scorers
# =============================================================================


def calculate_ap(text: str) -> float:
    """Calculate Ap (Actionability) for instruction regime.

    From anc.md: Measures how actionable the instruction is.
    Penalized by filler and fake confidence.
    """
    word_count = max(len(text.split()), 1)

    # Filler reduces actionability
    filler_count = count_pattern_matches(text, INSTRUCTION_FILLER_PATTERNS)
    filler_density = filler_count / word_count

    # Fake confidence reduces trust
    fake_count = count_pattern_matches(text, FAKE_CONFIDENCE_PATTERNS)
    fake_density = fake_count / word_count

    # Start at 0.7, penalize for filler and fake confidence
    ap = 0.7
    ap -= filler_density * 10  # Heavy penalty per word
    ap -= fake_density * 5

    return max(0.0, min(1.0, ap))


def calculate_fi(text: str) -> float:
    """Calculate Fi (Fault Isolation) for debugging regime.

    From anc.md: Measures diagnostic quality.
    Boosted by hypotheses, differentials; penalized by premature closure.
    """
    word_count = max(len(text.split()), 1)

    # Good diagnostics raise Fi
    diag_count = count_pattern_matches(text, GOOD_DIAGNOSTIC_PATTERNS)

    # Premature closure lowers Fi
    closure_count = count_pattern_matches(text, PREMATURE_CLOSURE_PATTERNS)

    fi = 0.5
    fi += min(diag_count * 0.1, 0.3)
    fi -= closure_count * 0.15

    return max(0.0, min(1.0, fi))


def calculate_au(text: str) -> float:
    """Calculate Au (Auditability) for research regime.

    Measures how traceable/verifiable claims are.
    """
    # Simple proxy: presence of boundary conditions, falsifiers
    from .writing_patterns import FALSIFIER_PATTERNS, CAUSAL_HUMILITY_PATTERNS

    falsifier_count = count_pattern_matches(text, FALSIFIER_PATTERNS)
    humility_count = count_pattern_matches(text, CAUSAL_HUMILITY_PATTERNS)

    au = 0.5
    au += min(falsifier_count * 0.1, 0.25)
    au += min(humility_count * 0.08, 0.2)

    return max(0.0, min(1.0, au))


def calculate_fp(text: str) -> float:
    """Calculate Fp (Face Preservation) for negotiation regime.

    From anc.md: Measures respect for counterpart's dignity.
    Penalized by moralizing, gotchas, manipulation.
    """
    moralizing = count_pattern_matches(text, MORALIZING_PATTERNS)
    gotcha = count_pattern_matches(text, GOTCHA_PATTERNS)
    manipulation = count_pattern_matches(text, MANIPULATION_PATTERNS)

    fp = 0.7
    fp -= moralizing * 0.15
    fp -= gotcha * 0.20
    fp -= manipulation * 0.25

    return max(0.0, min(1.0, fp))


def calculate_mt(text: str) -> float:
    """Calculate Mt (Motivational Traction) for advocacy regime.

    Measures ability to inspire action without manipulation.
    """
    manipulation = count_pattern_matches(text, MANIPULATION_PATTERNS)

    # Simple score - penalize manipulation
    mt = 0.6
    mt -= manipulation * 0.20

    return max(0.0, min(1.0, mt))


def calculate_pa(text: str) -> float:
    """Calculate Pa (Aspirational Plausibility) for marketing regime.

    Measures believable aspiration without buzzword overload.
    """
    # Bureaucratic patterns kill marketing credibility
    bureaucratic = count_pattern_matches(text, BUREAUCRATIC_PATTERNS)

    pa = 0.6
    pa -= bureaucratic * 0.10

    return max(0.0, min(1.0, pa))


def calculate_ut(text: str) -> float:
    """Calculate Ut (Unresolved Threat) for horror regime.

    From anc.md: Horror dies when threats are explained.
    """
    # Premature closure kills horror
    closure_count = count_pattern_matches(text, PREMATURE_CLOSURE_PATTERNS)

    ut = 0.7
    ut -= closure_count * 0.20

    return max(0.0, min(1.0, ut))


def calculate_vv(text: str) -> float:
    """Calculate Vv (Vulnerability Credibility) for romance regime.

    Measures authentic vulnerability without quote-bait.
    """
    # Fake confidence kills romance credibility
    fake_count = count_pattern_matches(text, FAKE_CONFIDENCE_PATTERNS)

    vv = 0.6
    vv -= fake_count * 0.15

    return max(0.0, min(1.0, vv))


def calculate_de(text: str) -> float:
    """Calculate De (Double-Encoding Stability) for satire regime.

    From anc.md: Satire must maintain dual reading (surface + critique).
    """
    # Satire dies if it collapses to sincere or pure mockery
    # This is hard to measure lexically - proxy: absence of heavy hedges
    from .writing_patterns import HEDGE_PATTERNS

    hedge_count = count_pattern_matches(text, HEDGE_PATTERNS)

    de = 0.6
    de -= min(hedge_count * 0.05, 0.3)

    return max(0.0, min(1.0, de))


def calculate_mc(text: str) -> float:
    """Calculate Mc (Memorability) for aphorism regime.

    Measures compression and quotability.
    """
    word_count = max(len(text.split()), 1)

    # Short is more memorable
    if word_count <= 10:
        mc = 0.8
    elif word_count <= 20:
        mc = 0.6
    elif word_count <= 50:
        mc = 0.4
    else:
        mc = 0.2

    # Filler kills memorability
    filler = count_pattern_matches(text, INSTRUCTION_FILLER_PATTERNS)
    mc -= filler * 0.15

    return max(0.0, min(1.0, mc))


def calculate_sa(text: str) -> float:
    """Calculate Sa (Sacred Authority) for liturgical regime.

    From anc.md: Liturgy requires maintaining sacred register.
    """
    # Modern rationalizations kill liturgical authority
    from .writing_patterns import ANXIETY_HEDGE_PATTERNS

    anxiety = count_pattern_matches(text, ANXIETY_HEDGE_PATTERNS)

    sa = 0.7
    sa -= anxiety * 0.20

    return max(0.0, min(1.0, sa))


def calculate_lm(text: str) -> float:
    """Calculate Lm (Bureaucratic Contamination) - negative scorer.

    From anc.md: Bureaucratic voice contaminates all regimes.
    Higher = worse.
    """
    bureaucratic = count_pattern_matches(text, BUREAUCRATIC_PATTERNS)

    # This is a contamination score - higher = more contaminated
    lm = min(bureaucratic * 0.15, 1.0)

    return lm


# =============================================================================
# RegimeCollision
# =============================================================================


class CollisionSeverity(str, Enum):
    """Severity of regime collision."""

    WARNING = "warning"  # Proceed with caution
    CONFLICT = "conflict"  # Choose one or sequence
    INCOMPATIBLE = "incompatible"  # Cannot combine


class CollisionResolution(str, Enum):
    """Resolution strategy for collision."""

    CHOOSE_DOMINANT = "choose_dominant"
    SEQUENCE = "sequence"
    ABORT = "abort"


@dataclass
class CollisionResult:
    """Result of collision check."""

    regime_a: str
    regime_b: str
    severity: CollisionSeverity
    resolution: CollisionResolution
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime_a": self.regime_a,
            "regime_b": self.regime_b,
            "severity": self.severity.value,
            "resolution": self.resolution.value,
            "reason": self.reason,
        }


# Collision matrix from anc.md
COLLISION_MATRIX: list[tuple[str, str, CollisionSeverity, CollisionResolution, str]] = [
    ("research", "advocacy", CollisionSeverity.CONFLICT, CollisionResolution.CHOOSE_DOMINANT, "propaganda_smell"),
    ("tragedy", "satire", CollisionSeverity.CONFLICT, CollisionResolution.CHOOSE_DOMINANT, "cruelty_smell"),
    ("instruction", "sincerity", CollisionSeverity.WARNING, CollisionResolution.SEQUENCE, "therapy_voice"),
    ("horror", "comedy", CollisionSeverity.CONFLICT, CollisionResolution.CHOOSE_DOMINANT, "defangs_or_cruel"),
    ("negotiation", "advocacy", CollisionSeverity.CONFLICT, CollisionResolution.CHOOSE_DOMINANT, "manipulation_smell"),
    ("comedy", "tragedy", CollisionSeverity.WARNING, CollisionResolution.SEQUENCE, "stakes_mismatch"),
    ("research", "marketing", CollisionSeverity.INCOMPATIBLE, CollisionResolution.ABORT, "credibility_collapse"),
    ("liturgical", "comedy", CollisionSeverity.INCOMPATIBLE, CollisionResolution.ABORT, "sacrilege_or_death"),
]


def check_collision(regime_a: str, regime_b: str) -> CollisionResult | None:
    """Check if two regimes collide.

    Args:
        regime_a: First regime name
        regime_b: Second regime name

    Returns:
        CollisionResult if collision found, None otherwise
    """
    a = regime_a.lower()
    b = regime_b.lower()

    for ra, rb, severity, resolution, reason in COLLISION_MATRIX:
        if (ra == a and rb == b) or (ra == b and rb == a):
            return CollisionResult(
                regime_a=regime_a,
                regime_b=regime_b,
                severity=severity,
                resolution=resolution,
                reason=reason,
            )

    return None


def list_collisions_for_regime(regime: str) -> list[CollisionResult]:
    """List all collisions for a given regime."""
    r = regime.lower()
    results = []

    for ra, rb, severity, resolution, reason in COLLISION_MATRIX:
        if ra == r:
            results.append(CollisionResult(
                regime_a=ra,
                regime_b=rb,
                severity=severity,
                resolution=resolution,
                reason=reason,
            ))
        elif rb == r:
            results.append(CollisionResult(
                regime_a=rb,
                regime_b=ra,
                severity=severity,
                resolution=resolution,
                reason=reason,
            ))

    return results
