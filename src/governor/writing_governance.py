# SPDX-License-Identifier: Apache-2.0
"""
Writing Governance — Governance visibility scoring and leak detection.

Two main checkers:
1. GovernanceVisibilityScorer: Scores 6 artifact categories (nonfic.md §5)
2. GovernanceLeakDetector: Detects 5 institutional voice types (tone.md §6)

Plus:
3. SmoothingSuppressor: Hedge density, banned phrases, meta kill (fic.md §3.4.3)
4. ExitShapeChecker: Bad exit patterns (writingconstraints.md §7)

The #1 priority from all five specs: governance must never surface in-band.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .writing_patterns import (
    APOLOGY_META_PATTERNS,
    BAD_EXIT_PATTERNS,
    BANNED_PHRASES,
    COMMITTEE_PATTERNS,
    GOVERNANCE_ARTIFACT_PATTERNS,
    HEDGE_PATTERNS,
    INSTITUTIONAL_MARKER_PATTERNS,
    SELF_REFERENCE_PATTERNS,
    check_any_pattern,
    count_categorized_patterns,
    count_pattern_matches,
    find_pattern_matches,
)

# =============================================================================
# Constants
# =============================================================================

# Maximum acceptable governance visibility score (nonfic.md)
GV_CEILING: float = 0.3

# Penalty weights for governance artifacts
GV_WEIGHTS: dict[str, float] = {
    "preemptive_defense": 0.20,
    "virtue_seals": 0.15,
    "balance_theater": 0.15,
    "empty_rigor": 0.10,
    "responsible_framing": 0.20,
    "meta_writing": 0.15,
}

# Penalty weights for institutional markers
INSTITUTIONAL_WEIGHTS: dict[str, float] = {
    "hr_voice": 0.15,
    "legal_voice": 0.10,
    "committee_voice": 0.20,
    "condescension_voice": 0.15,
    "fear_voice": 0.25,
}

# Rp floor for comedy (fic.md)
RP_FLOOR: float = 0.6

# Hedge density thresholds per 100 words
HEDGE_DENSITY_CEILING: float = 0.08

# =============================================================================
# Governance Visibility Scorer (nonfic.md §5)
# =============================================================================


@dataclass
class GovernanceVisibilityResult:
    """Result of governance visibility scoring."""

    preemptive_defense: int = 0
    virtue_seals: int = 0
    balance_theater: int = 0
    empty_rigor: int = 0
    responsible_framing: int = 0
    meta_writing: int = 0
    overall_score: float = 0.0
    exceeds_ceiling: bool = False

    def to_dict(self) -> dict:
        return {
            "preemptive_defense": self.preemptive_defense,
            "virtue_seals": self.virtue_seals,
            "balance_theater": self.balance_theater,
            "empty_rigor": self.empty_rigor,
            "responsible_framing": self.responsible_framing,
            "meta_writing": self.meta_writing,
            "overall_score": self.overall_score,
            "exceeds_ceiling": self.exceeds_ceiling,
        }


class GovernanceVisibilityScorer:
    """Scores governance artifact density in text.

    From nonfic.md §5: governance leaks make the reader see the author
    managing outcomes rather than presenting reality.
    """

    def __init__(self, ceiling: float = GV_CEILING) -> None:
        self._ceiling = ceiling

    def calculate_gv(self, text: str) -> GovernanceVisibilityResult:
        """Calculate governance visibility score.

        Returns per-category counts and overall weighted score.
        Score of 0.0 = no governance artifacts detected.
        Score approaching 1.0 = heavily governance-laden text.
        """
        counts = count_categorized_patterns(text, GOVERNANCE_ARTIFACT_PATTERNS)

        # Calculate weighted score
        overall = 0.0
        for category, count in counts.items():
            weight = GV_WEIGHTS.get(category, 0.1)
            # Each occurrence adds weight, capped contribution per category
            overall += min(count * weight, 0.4)

        overall = min(overall, 1.0)

        return GovernanceVisibilityResult(
            preemptive_defense=counts.get("preemptive_defense", 0),
            virtue_seals=counts.get("virtue_seals", 0),
            balance_theater=counts.get("balance_theater", 0),
            empty_rigor=counts.get("empty_rigor", 0),
            responsible_framing=counts.get("responsible_framing", 0),
            meta_writing=counts.get("meta_writing", 0),
            overall_score=overall,
            exceeds_ceiling=overall > self._ceiling,
        )


# =============================================================================
# Governance Leak Detector (tone.md §6)
# =============================================================================


@dataclass
class GovernanceLeakResult:
    """Result of governance leak detection."""

    hr_voice: int = 0
    legal_voice: int = 0
    committee_voice: int = 0
    condescension_voice: int = 0
    fear_voice: int = 0
    marker_density: float = 0.0
    committee_cadence_score: float = 0.0
    governance_leak_score: float = 0.0
    has_leak: bool = False

    def to_dict(self) -> dict:
        return {
            "hr_voice": self.hr_voice,
            "legal_voice": self.legal_voice,
            "committee_voice": self.committee_voice,
            "condescension_voice": self.condescension_voice,
            "fear_voice": self.fear_voice,
            "marker_density": self.marker_density,
            "committee_cadence_score": self.committee_cadence_score,
            "governance_leak_score": self.governance_leak_score,
            "has_leak": self.has_leak,
        }


class GovernanceLeakDetector:
    """Detects institutional voice contamination in text.

    From tone.md §6: institutional voices (HR, legal, committee, etc.)
    signal governance even when content is appropriate.
    """

    def __init__(self, leak_threshold: float = 0.3) -> None:
        self._leak_threshold = leak_threshold

    def detect_leaks(self, text: str) -> GovernanceLeakResult:
        """Detect institutional voice markers.

        Returns per-voice counts, density, and combined governance leak score.
        """
        word_count = max(len(text.split()), 1)

        counts = count_categorized_patterns(text, INSTITUTIONAL_MARKER_PATTERNS)

        # Calculate marker density (markers per 100 words)
        total_markers = sum(counts.values())
        marker_density = (total_markers / word_count) * 100

        # Committee cadence: additional score from committee patterns
        committee_matches = count_pattern_matches(text, COMMITTEE_PATTERNS)
        committee_cadence = min(committee_matches * 0.12, 0.5)

        # Calculate weighted governance leak score
        leak_score = 0.0
        for voice, count in counts.items():
            weight = INSTITUTIONAL_WEIGHTS.get(voice, 0.1)
            leak_score += min(count * weight, 0.4)

        # Add committee cadence
        leak_score += committee_cadence
        leak_score = min(leak_score, 1.0)

        return GovernanceLeakResult(
            hr_voice=counts.get("hr_voice", 0),
            legal_voice=counts.get("legal_voice", 0),
            committee_voice=counts.get("committee_voice", 0),
            condescension_voice=counts.get("condescension_voice", 0),
            fear_voice=counts.get("fear_voice", 0),
            marker_density=marker_density,
            committee_cadence_score=committee_cadence,
            governance_leak_score=leak_score,
            has_leak=leak_score > self._leak_threshold,
        )


# =============================================================================
# Smoothing Suppressor (fic.md §3.4.3)
# =============================================================================


@dataclass
class SmoothingResult:
    """Result of smoothing check."""

    banned_phrases_found: list[str] = field(default_factory=list)
    hedge_count: int = 0
    hedge_density: float = 0.0
    self_ref_count: int = 0
    committee_count: int = 0
    meta_kill_found: bool = False
    rp_score: float = 1.0
    below_rp_floor: bool = False

    def to_dict(self) -> dict:
        return {
            "banned_phrases_found": self.banned_phrases_found,
            "hedge_count": self.hedge_count,
            "hedge_density": self.hedge_density,
            "self_ref_count": self.self_ref_count,
            "committee_count": self.committee_count,
            "meta_kill_found": self.meta_kill_found,
            "rp_score": self.rp_score,
            "below_rp_floor": self.below_rp_floor,
        }


class SmoothingSuppressor:
    """Detects smoothing behaviors that kill comedy/fiction.

    Three layers:
    1. Banned phrase detection (hard block)
    2. Hedge density scoring (soft penalty)
    3. Apology/meta hard-block detection
    """

    def __init__(self, rp_floor: float = RP_FLOOR) -> None:
        self._rp_floor = rp_floor

    def check_smoothing(self, text: str) -> SmoothingResult:
        """Check text for smoothing behaviors.

        Returns Rp (perceived risk) score and component metrics.
        Rp starts at 1.0 and decrements per pattern hit.
        """
        word_count = max(len(text.split()), 1)

        # Check banned phrases (exact substring match)
        banned_found = []
        text_lower = text.lower()
        for phrase in BANNED_PHRASES:
            if phrase.lower() in text_lower:
                banned_found.append(phrase)

        # Count pattern matches
        hedge_count = count_pattern_matches(text, HEDGE_PATTERNS)
        self_ref_count = count_pattern_matches(text, SELF_REFERENCE_PATTERNS)
        committee_count = count_pattern_matches(text, COMMITTEE_PATTERNS)

        # Hedge density per 100 words
        hedge_density = (hedge_count / word_count) * 100

        # Check for meta kill patterns (apology/meta)
        meta_kill = check_any_pattern(text, APOLOGY_META_PATTERNS)

        # Calculate Rp score (from fic.md)
        rp = 1.0
        rp -= hedge_count * 0.05  # hedges reduce by 0.05 each
        rp -= self_ref_count * 0.15  # self-ref kills by 0.15 each
        rp -= committee_count * 0.12  # committee reduces by 0.12 each
        rp -= len(banned_found) * 0.15  # banned phrases reduce by 0.15 each

        # Meta kill is severe
        if meta_kill:
            rp -= 0.3

        rp = max(rp, 0.0)

        return SmoothingResult(
            banned_phrases_found=banned_found,
            hedge_count=hedge_count,
            hedge_density=hedge_density,
            self_ref_count=self_ref_count,
            committee_count=committee_count,
            meta_kill_found=meta_kill,
            rp_score=rp,
            below_rp_floor=rp < self._rp_floor,
        )


# =============================================================================
# Exit Shape Checker (writingconstraints.md §7)
# =============================================================================


@dataclass
class ExitCheckResult:
    """Result of exit shape check."""

    bad_patterns_found: list[str] = field(default_factory=list)
    has_bad_exit: bool = False
    severity: float = 0.0

    def to_dict(self) -> dict:
        return {
            "bad_patterns_found": self.bad_patterns_found,
            "has_bad_exit": self.has_bad_exit,
            "severity": self.severity,
        }


class ExitShapeChecker:
    """Checks text endings for commitment escalation or empty gestures.

    From writingconstraints.md §7: commitment demand must not increase at exit.
    """

    def __init__(self, tail_words: int = 50) -> None:
        """Initialize checker.

        Args:
            tail_words: Number of words from end to check as "exit" region.
        """
        self._tail_words = tail_words

    def check_exit(self, text: str) -> ExitCheckResult:
        """Check text exit for bad patterns.

        Focuses on the tail region (last N words) where exit patterns matter.
        """
        words = text.split()
        if not words:
            return ExitCheckResult()

        # Check tail region for exit patterns
        tail_start = max(0, len(words) - self._tail_words)
        tail_text = " ".join(words[tail_start:])

        # Find bad exit patterns
        bad_patterns = find_pattern_matches(tail_text, BAD_EXIT_PATTERNS)

        # Calculate severity based on patterns found
        severity = 0.0
        if bad_patterns:
            # Each bad pattern adds severity
            severity = min(len(bad_patterns) * 0.3, 1.0)

        return ExitCheckResult(
            bad_patterns_found=bad_patterns,
            has_bad_exit=len(bad_patterns) > 0,
            severity=severity,
        )


# =============================================================================
# Combined checker
# =============================================================================


@dataclass
class GovernanceCheckResult:
    """Combined result of all governance checks."""

    visibility: GovernanceVisibilityResult
    leak: GovernanceLeakResult
    smoothing: SmoothingResult
    exit: ExitCheckResult
    overall_governance_score: float = 0.0
    governance_surfaced: bool = False

    def to_dict(self) -> dict:
        return {
            "visibility": self.visibility.to_dict(),
            "leak": self.leak.to_dict(),
            "smoothing": self.smoothing.to_dict(),
            "exit": self.exit.to_dict(),
            "overall_governance_score": self.overall_governance_score,
            "governance_surfaced": self.governance_surfaced,
        }


class GovernanceChecker:
    """Combined governance visibility and leak detection.

    The meta-invariant: governance must never surface in-band.
    """

    def __init__(
        self,
        gv_ceiling: float = GV_CEILING,
        leak_threshold: float = 0.3,
        rp_floor: float = RP_FLOOR,
    ) -> None:
        self._visibility_scorer = GovernanceVisibilityScorer(ceiling=gv_ceiling)
        self._leak_detector = GovernanceLeakDetector(leak_threshold=leak_threshold)
        self._smoothing_suppressor = SmoothingSuppressor(rp_floor=rp_floor)
        self._exit_checker = ExitShapeChecker()

    def check(self, text: str) -> GovernanceCheckResult:
        """Run all governance checks on text."""
        visibility = self._visibility_scorer.calculate_gv(text)
        leak = self._leak_detector.detect_leaks(text)
        smoothing = self._smoothing_suppressor.check_smoothing(text)
        exit_result = self._exit_checker.check_exit(text)

        # Combined governance score (weighted average)
        overall = (
            visibility.overall_score * 0.3
            + leak.governance_leak_score * 0.3
            + (1.0 - smoothing.rp_score) * 0.25  # invert Rp (lower = more governance)
            + exit_result.severity * 0.15
        )
        overall = min(overall, 1.0)

        # Governance surfaced if any major signal fires
        surfaced = (
            visibility.exceeds_ceiling
            or leak.has_leak
            or smoothing.below_rp_floor
            or exit_result.has_bad_exit
        )

        return GovernanceCheckResult(
            visibility=visibility,
            leak=leak,
            smoothing=smoothing,
            exit=exit_result,
            overall_governance_score=overall,
            governance_surfaced=surfaced,
        )
