# SPDX-License-Identifier: Apache-2.0
"""
Tone profiling and style enforcement for nonfiction writing.

Voice/tone is canon for nonfiction. Fiction has character canon, code has architecture
decisions -- nonfiction needs enforceable style parameters. Without this, autonomous
writing produces generic AI prose instead of the author's voice.

Phase T1: ToneProfile dataclass, manual authoring, tone guidance generation.
Phase T2: Corpus analysis and automatic extraction (future).
Phase T3: StyleInvariant enforcement (future).
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re


# =============================================================================
# ToneProfile Dataclass
# =============================================================================


@dataclass
class ToneProfile:
    """
    Extracted or manually authored style parameters.

    Every field has a reasonable default so profiles can be partial.
    Fields map to observable, mechanically-checkable properties of text.
    """

    # Identity
    name: str = "default"
    description: str = ""

    # Sentence structure
    avg_sentence_length: int = 18  # words
    sentence_length_variance: float = 12.0
    uses_fragments: bool = False
    uses_colons_for_emphasis: bool = False

    # Paragraph structure
    avg_paragraph_length: int = 4  # sentences
    uses_single_sentence_paragraphs: bool = False

    # Voice patterns
    uses_second_person: bool = False
    uses_first_person: bool = False
    contractions_frequency: float = 0.5  # [0, 1]

    # Rhetorical devices
    uses_rhetorical_questions: bool = False
    uses_parentheticals: bool = False
    uses_em_dashes: bool = False
    uses_ellipses: bool = False

    # Framing patterns
    opening_patterns: list[str] = field(default_factory=list)
    transition_patterns: list[str] = field(default_factory=list)
    closing_patterns: list[str] = field(default_factory=list)

    # Vocabulary
    favorite_adjectives: list[str] = field(default_factory=list)
    favorite_verbs: list[str] = field(default_factory=list)
    technical_density: float = 0.3  # [0, 1]

    # Tone markers
    uses_profanity: bool = False
    sarcasm_frequency: float = 0.0  # [0, 1]
    uses_pop_culture_refs: bool = False

    # Structure preferences
    uses_headers: bool = True
    header_style: str = "statement"  # "statement" | "question" | "provocative"
    uses_lists: str = "moderate"  # "sparingly" | "moderate" | "frequent"
    uses_examples: bool = True
    example_placement: str = "inline"  # "inline" | "separate_section"

    # Custom guidance (free-form, appended to generated guidance)
    custom_guidance: str = ""

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        self.contractions_frequency = max(0.0, min(1.0, self.contractions_frequency))
        self.technical_density = max(0.0, min(1.0, self.technical_density))
        self.sarcasm_frequency = max(0.0, min(1.0, self.sarcasm_frequency))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "avg_sentence_length": self.avg_sentence_length,
            "sentence_length_variance": self.sentence_length_variance,
            "uses_fragments": self.uses_fragments,
            "uses_colons_for_emphasis": self.uses_colons_for_emphasis,
            "avg_paragraph_length": self.avg_paragraph_length,
            "uses_single_sentence_paragraphs": self.uses_single_sentence_paragraphs,
            "uses_second_person": self.uses_second_person,
            "uses_first_person": self.uses_first_person,
            "contractions_frequency": self.contractions_frequency,
            "uses_rhetorical_questions": self.uses_rhetorical_questions,
            "uses_parentheticals": self.uses_parentheticals,
            "uses_em_dashes": self.uses_em_dashes,
            "uses_ellipses": self.uses_ellipses,
            "opening_patterns": list(self.opening_patterns),
            "transition_patterns": list(self.transition_patterns),
            "closing_patterns": list(self.closing_patterns),
            "favorite_adjectives": list(self.favorite_adjectives),
            "favorite_verbs": list(self.favorite_verbs),
            "technical_density": self.technical_density,
            "uses_profanity": self.uses_profanity,
            "sarcasm_frequency": self.sarcasm_frequency,
            "uses_pop_culture_refs": self.uses_pop_culture_refs,
            "uses_headers": self.uses_headers,
            "header_style": self.header_style,
            "uses_lists": self.uses_lists,
            "uses_examples": self.uses_examples,
            "example_placement": self.example_placement,
            "custom_guidance": self.custom_guidance,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToneProfile":
        return cls(
            name=data.get("name", "default"),
            description=data.get("description", ""),
            avg_sentence_length=data.get("avg_sentence_length", 18),
            sentence_length_variance=data.get("sentence_length_variance", 12.0),
            uses_fragments=data.get("uses_fragments", False),
            uses_colons_for_emphasis=data.get("uses_colons_for_emphasis", False),
            avg_paragraph_length=data.get("avg_paragraph_length", 4),
            uses_single_sentence_paragraphs=data.get("uses_single_sentence_paragraphs", False),
            uses_second_person=data.get("uses_second_person", False),
            uses_first_person=data.get("uses_first_person", False),
            contractions_frequency=data.get("contractions_frequency", 0.5),
            uses_rhetorical_questions=data.get("uses_rhetorical_questions", False),
            uses_parentheticals=data.get("uses_parentheticals", False),
            uses_em_dashes=data.get("uses_em_dashes", False),
            uses_ellipses=data.get("uses_ellipses", False),
            opening_patterns=data.get("opening_patterns", []),
            transition_patterns=data.get("transition_patterns", []),
            closing_patterns=data.get("closing_patterns", []),
            favorite_adjectives=data.get("favorite_adjectives", []),
            favorite_verbs=data.get("favorite_verbs", []),
            technical_density=data.get("technical_density", 0.3),
            uses_profanity=data.get("uses_profanity", False),
            sarcasm_frequency=data.get("sarcasm_frequency", 0.0),
            uses_pop_culture_refs=data.get("uses_pop_culture_refs", False),
            uses_headers=data.get("uses_headers", True),
            header_style=data.get("header_style", "statement"),
            uses_lists=data.get("uses_lists", "moderate"),
            uses_examples=data.get("uses_examples", True),
            example_placement=data.get("example_placement", "inline"),
            custom_guidance=data.get("custom_guidance", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def save(self, path: Path) -> None:
        """Save profile to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = datetime.now().isoformat()
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: Path) -> "ToneProfile":
        """Load profile from JSON file."""
        data = json.loads(path.read_text())
        return cls.from_dict(data)


# =============================================================================
# ToneViolation
# =============================================================================


@dataclass
class ToneViolation:
    """A specific deviation from the tone profile."""

    dimension: str  # e.g., "sentence_length", "contractions", "fragments"
    message: str
    expected: str | float | bool
    actual: str | float | bool
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
            "suggestion": self.suggestion,
        }


@dataclass
class ToneCheckResult:
    """Result of checking text against a tone profile."""

    valid: bool
    violations: list[ToneViolation] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "violations": [v.to_dict() for v in self.violations],
            "metrics": self.metrics,
        }


# =============================================================================
# Text Analysis Helpers (Phase T1: basic mechanical checks)
# =============================================================================


_SENTENCE_PATTERN = re.compile(r'[^.!?]+[.!?]+')
_CONTRACTION_PATTERN = re.compile(
    r"\b(?:i'm|i'll|i'd|i've|it's|he's|she's|we're|they're|"
    r"you're|you'll|you've|you'd|we'll|we've|we'd|they'll|they've|they'd|"
    r"isn't|aren't|wasn't|weren't|hasn't|haven't|hadn't|"
    r"won't|wouldn't|can't|couldn't|shouldn't|don't|doesn't|didn't|"
    r"that's|there's|here's|who's|what's|let's|ain't)\b",
    re.IGNORECASE,
)
_EXPANDED_PATTERN = re.compile(
    r"\b(?:I am|I will|I would|I have|it is|he is|she is|we are|they are|"
    r"you are|you will|you have|you would|we will|we have|we would|"
    r"they will|they have|they would|"
    r"is not|are not|was not|were not|has not|have not|had not|"
    r"will not|would not|cannot|could not|should not|"
    r"do not|does not|did not|"
    r"that is|there is|here is|who is|what is|let us)\b",
    re.IGNORECASE,
)
def _is_fragment(sentence: str) -> bool:
    """Detect sentence fragments (short, typically missing subject-verb structure)."""
    s = sentence.strip().rstrip('.!?')
    words = s.split()
    if not words:
        return False
    # Very short "sentences" (1-3 words) are likely fragments
    if len(words) <= 3:
        return True
    # Short sentences starting with specific fragment markers
    if len(words) <= 6 and words[0].lower() in {
        "no", "not", "never", "none", "nothing", "nobody",
        "just", "only", "but", "and", "or", "yet", "so",
    }:
        return True
    return False
_EM_DASH_PATTERN = re.compile(r'\u2014|--')
_ELLIPSIS_PATTERN = re.compile(r'\.{3}|\u2026')
_SECOND_PERSON_PATTERN = re.compile(r'\byou(?:r|rs|rself|rselves)?\b', re.IGNORECASE)
_FIRST_PERSON_PATTERN = re.compile(r'\b(?:I|my|me|mine|myself|we|our|ours|ourselves)\b')
_RHETORICAL_Q_PATTERN = re.compile(r'[^?]*\?')
_PARENTHETICAL_PATTERN = re.compile(r'\([^)]+\)')
_COLON_EMPHASIS_PATTERN = re.compile(r':\s+[A-Z]')

# Common stop words for vocabulary analysis
_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "not", "no", "if", "then", "than",
    "so", "as", "up", "out", "about", "into", "over", "after", "before",
    "between", "under", "during", "through", "each", "every", "all",
    "both", "few", "more", "most", "other", "some", "such", "only",
    "very", "just", "also", "now", "here", "there", "when", "where",
    "how", "what", "which", "who", "whom", "why",
})


def _count_syllables(word: str) -> int:
    """Estimate syllable count using vowel group heuristic."""
    word = word.lower().strip()
    if not word:
        return 0
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in "aeiouy"
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Silent e adjustment
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _estimate_technical_density(words: list[str]) -> float:
    """
    Estimate technical density as proportion of complex words.

    Complex = 3+ syllables and not a common stop word.
    """
    if not words:
        return 0.0
    content_words = [w.lower().strip(".,!?;:\"'()[]") for w in words]
    content_words = [w for w in content_words if w and w not in _STOP_WORDS]
    if not content_words:
        return 0.0
    complex_count = sum(1 for w in content_words if _count_syllables(w) >= 3)
    return complex_count / len(content_words)


def analyze_text(text: str) -> dict[str, Any]:
    """
    Extract measurable style metrics from text.

    Returns a dict of the same dimensions as ToneProfile.
    """
    if not text.strip():
        return {"empty": True}

    sentences = _SENTENCE_PATTERN.findall(text)
    words = text.split()
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    # Sentence length
    sentence_lengths = [len(s.split()) for s in sentences] if sentences else [0]
    avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0
    if len(sentence_lengths) > 1:
        mean = avg_sentence_length
        variance = sum((l - mean) ** 2 for l in sentence_lengths) / len(sentence_lengths)
        sentence_length_variance = variance ** 0.5
    else:
        sentence_length_variance = 0.0

    # Paragraph length (in sentences)
    para_sentence_counts = []
    for para in paragraphs:
        para_sents = _SENTENCE_PATTERN.findall(para)
        para_sentence_counts.append(len(para_sents) if para_sents else 1)
    avg_paragraph_length = (
        sum(para_sentence_counts) / len(para_sentence_counts)
        if para_sentence_counts else 0
    )
    uses_single_sentence_paragraphs = any(c == 1 for c in para_sentence_counts)

    # Fragments
    fragment_count = sum(1 for s in sentences if _is_fragment(s.strip()))
    uses_fragments = fragment_count > 0

    # Contractions
    contraction_count = len(_CONTRACTION_PATTERN.findall(text))
    expanded_count = len(_EXPANDED_PATTERN.findall(text))
    total_contractable = contraction_count + expanded_count
    contractions_frequency = (
        contraction_count / total_contractable if total_contractable > 0 else 0.5
    )

    # Voice patterns
    uses_second_person = bool(_SECOND_PERSON_PATTERN.search(text))
    uses_first_person = bool(_FIRST_PERSON_PATTERN.search(text))

    # Rhetorical devices
    uses_em_dashes = bool(_EM_DASH_PATTERN.search(text))
    uses_ellipses = bool(_ELLIPSIS_PATTERN.search(text))
    uses_parentheticals = bool(_PARENTHETICAL_PATTERN.search(text))
    uses_colons_for_emphasis = bool(_COLON_EMPHASIS_PATTERN.search(text))

    # Rhetorical questions (questions not at end of document, heuristic)
    question_marks = text.count('?')
    uses_rhetorical_questions = question_marks > 0

    return {
        "avg_sentence_length": round(avg_sentence_length),
        "sentence_length_variance": round(sentence_length_variance, 1),
        "uses_fragments": uses_fragments,
        "uses_colons_for_emphasis": uses_colons_for_emphasis,
        "avg_paragraph_length": round(avg_paragraph_length),
        "uses_single_sentence_paragraphs": uses_single_sentence_paragraphs,
        "uses_second_person": uses_second_person,
        "uses_first_person": uses_first_person,
        "contractions_frequency": round(contractions_frequency, 2),
        "uses_rhetorical_questions": uses_rhetorical_questions,
        "uses_parentheticals": uses_parentheticals,
        "uses_em_dashes": uses_em_dashes,
        "uses_ellipses": uses_ellipses,
        "technical_density": round(_estimate_technical_density(words), 2),
        "sentence_count": len(sentences),
        "word_count": len(words),
        "paragraph_count": len(paragraphs),
    }


# =============================================================================
# Tone Checker (Phase T1: basic mechanical checks)
# =============================================================================


class ToneChecker:
    """
    Check text against a ToneProfile.

    Phase T1: Checks mechanically observable properties.
    Does NOT check vocabulary, opening patterns, or other properties
    that require corpus analysis (Phase T2).
    """

    def __init__(self, profile: ToneProfile, tolerance: float = 0.2):
        self.profile = profile
        self.tolerance = tolerance

    def check(self, text: str) -> ToneCheckResult:
        """Check text against the profile. Returns violations."""
        metrics = analyze_text(text)
        if metrics.get("empty"):
            return ToneCheckResult(valid=True, metrics=metrics)

        violations: list[ToneViolation] = []

        # Sentence length
        length_diff = abs(metrics["avg_sentence_length"] - self.profile.avg_sentence_length)
        if length_diff > 5:
            violations.append(ToneViolation(
                dimension="sentence_length",
                message=f"Sentence length drift: {metrics['avg_sentence_length']} vs expected {self.profile.avg_sentence_length}",
                expected=self.profile.avg_sentence_length,
                actual=metrics["avg_sentence_length"],
                suggestion="Break up long sentences" if metrics["avg_sentence_length"] > self.profile.avg_sentence_length else "Combine short sentences for flow",
            ))

        # Fragment usage
        if self.profile.uses_fragments and not metrics["uses_fragments"]:
            violations.append(ToneViolation(
                dimension="fragments",
                message="Missing characteristic sentence fragments",
                expected=True,
                actual=False,
                suggestion="Add sentence fragments for emphasis. Short. Punchy. Declarative.",
            ))

        # Second person
        if self.profile.uses_second_person and not metrics["uses_second_person"]:
            violations.append(ToneViolation(
                dimension="second_person",
                message="Missing characteristic 'you' voice",
                expected=True,
                actual=False,
                suggestion="Address the reader directly with 'you'",
            ))

        # First person
        if self.profile.uses_first_person and not metrics["uses_first_person"]:
            violations.append(ToneViolation(
                dimension="first_person",
                message="Missing first person voice",
                expected=True,
                actual=False,
                suggestion="Use first person when making arguments",
            ))

        # Contractions
        contraction_diff = abs(
            metrics["contractions_frequency"] - self.profile.contractions_frequency
        )
        if contraction_diff > self.tolerance:
            direction = (
                "Use more contractions (it's, don't, won't)"
                if metrics["contractions_frequency"] < self.profile.contractions_frequency
                else "Use fewer contractions for formality"
            )
            violations.append(ToneViolation(
                dimension="contractions",
                message=(
                    f"Contraction frequency off: {metrics['contractions_frequency']:.0%} "
                    f"vs expected {self.profile.contractions_frequency:.0%}"
                ),
                expected=self.profile.contractions_frequency,
                actual=metrics["contractions_frequency"],
                suggestion=direction,
            ))

        # Em dashes
        if self.profile.uses_em_dashes and not metrics["uses_em_dashes"]:
            violations.append(ToneViolation(
                dimension="em_dashes",
                message="Missing characteristic em dashes",
                expected=True,
                actual=False,
                suggestion="Use em dashes for parenthetical asides or emphasis",
            ))

        # Rhetorical questions
        if self.profile.uses_rhetorical_questions and not metrics["uses_rhetorical_questions"]:
            violations.append(ToneViolation(
                dimension="rhetorical_questions",
                message="Missing rhetorical questions",
                expected=True,
                actual=False,
                suggestion="Add rhetorical questions to engage the reader",
            ))

        # Parentheticals
        if self.profile.uses_parentheticals and not metrics["uses_parentheticals"]:
            violations.append(ToneViolation(
                dimension="parentheticals",
                message="Missing parenthetical asides",
                expected=True,
                actual=False,
                suggestion="Use parentheticals for asides (like this)",
            ))

        # Technical density
        density_diff = abs(
            metrics.get("technical_density", 0.3) - self.profile.technical_density
        )
        if density_diff > self.tolerance:
            direction = (
                "Use more precise technical vocabulary"
                if metrics.get("technical_density", 0.3) < self.profile.technical_density
                else "Simplify vocabulary; prefer plain language"
            )
            violations.append(ToneViolation(
                dimension="technical_density",
                message=(
                    f"Technical density off: {metrics.get('technical_density', 0.3):.0%} "
                    f"vs expected {self.profile.technical_density:.0%}"
                ),
                expected=self.profile.technical_density,
                actual=metrics.get("technical_density", 0.3),
                suggestion=direction,
            ))

        return ToneCheckResult(
            valid=len(violations) == 0,
            violations=violations,
            metrics=metrics,
        )


# =============================================================================
# Tone Guidance Generator
# =============================================================================


def generate_tone_guidance(profile: ToneProfile) -> str:
    """
    Convert a ToneProfile into natural language style guidance.

    This is injected into system prompts for autonomous writing.
    """
    guidance: list[str] = []

    # Sentence structure
    guidance.append(
        f"Write sentences averaging {profile.avg_sentence_length} words. "
        f"Vary length (standard deviation ~{profile.sentence_length_variance:.0f} words)."
    )

    if profile.uses_fragments:
        guidance.append(
            "Use sentence fragments for emphasis. Short. Punchy. Declarative."
        )

    if profile.uses_colons_for_emphasis:
        guidance.append(
            "Use colons to set up payoffs: like this. The problem: X. The solution: Y."
        )

    # Paragraph structure
    if profile.uses_single_sentence_paragraphs:
        guidance.append(
            "Single-sentence paragraphs are acceptable for emphasis."
        )

    # Voice
    if profile.uses_second_person:
        guidance.append(
            "Address the reader directly with 'you'. "
            "Make them complicit in the observation."
        )

    if profile.uses_first_person:
        guidance.append(
            "Use first person when making arguments. "
            "Don't hide behind passive voice."
        )

    # Contractions
    if profile.contractions_frequency > 0.6:
        guidance.append(
            f"Use contractions frequently ({profile.contractions_frequency:.0%}). "
            "Write like you talk: it's, don't, won't."
        )
    elif profile.contractions_frequency < 0.3:
        guidance.append(
            f"Use contractions sparingly ({profile.contractions_frequency:.0%}). "
            "Prefer formal expansion: it is, do not, will not."
        )

    # Rhetorical devices
    if profile.uses_em_dashes:
        guidance.append(
            "Use em dashes\u2014like this\u2014for parenthetical asides or emphasis."
        )

    if profile.uses_parentheticals:
        guidance.append(
            "Use parenthetical asides (like this) for secondary observations."
        )

    if profile.uses_rhetorical_questions:
        guidance.append(
            "Use rhetorical questions to engage the reader and set up arguments."
        )

    if profile.uses_ellipses:
        guidance.append(
            "Trailing off with ellipses is acceptable for effect..."
        )

    # Opening patterns
    if profile.opening_patterns:
        patterns = "', '".join(profile.opening_patterns[:3])
        guidance.append(
            f"Start sections with characteristic phrases like: '{patterns}'"
        )

    # Vocabulary
    if profile.favorite_adjectives:
        words = ", ".join(profile.favorite_adjectives[:5])
        guidance.append(f"Lean toward adjectives like: {words}")

    if profile.favorite_verbs:
        words = ", ".join(profile.favorite_verbs[:5])
        guidance.append(f"Lean toward verbs like: {words}")

    # Technical density
    guidance.append(
        f"Technical density: {profile.technical_density:.0%}. "
        "Use jargon when precise, plain language when explaining. "
        "Never choose complexity for its own sake."
    )

    # Tone markers
    if profile.uses_profanity:
        guidance.append(
            "Profanity is acceptable when it serves emphasis. Don't sanitize the voice."
        )

    if profile.sarcasm_frequency > 0.3:
        guidance.append(
            "Employ dry sarcasm and ironic observation. "
            "The tone is 'observing the absurd, not surprised by it.'"
        )

    if profile.uses_pop_culture_refs:
        guidance.append(
            "Pop culture references are welcome when they illuminate the point."
        )

    # Structure
    if profile.header_style == "provocative":
        guidance.append("Make headers provocative or surprising, not just descriptive.")
    elif profile.header_style == "question":
        guidance.append("Frame headers as questions when possible.")

    if profile.uses_lists == "sparingly":
        guidance.append("Use lists sparingly. Prefer prose to bullet points.")
    elif profile.uses_lists == "frequent":
        guidance.append("Lists are welcome. Use them to organize dense information.")

    # Custom guidance
    if profile.custom_guidance.strip():
        guidance.append(profile.custom_guidance.strip())

    return "\n".join(guidance)


def format_system_prompt(profile: ToneProfile) -> str:
    """
    Generate a complete system prompt fragment for tone guidance.

    This is the full text to inject into the system message.
    """
    guidance = generate_tone_guidance(profile)
    return (
        f"You are writing in the author's established voice ({profile.name}).\n\n"
        f"{guidance}\n\n"
        "Match this style precisely. Do not deviate into generic AI prose."
    )


# =============================================================================
# ToneManager (persistence + lifecycle)
# =============================================================================


class ToneManager:
    """
    Manages tone profiles for a project.

    Profiles are stored as JSON in .governor/tone_profile.json.
    Only one profile is active at a time.
    """

    DEFAULT_PATH = ".governor/tone_profile.json"

    def __init__(self, root: Path | None = None):
        self.root = root or Path(".")
        self.profile_path = self.root / self.DEFAULT_PATH
        self._profile: ToneProfile | None = None
        self._locked: bool = False

    @property
    def has_profile(self) -> bool:
        return self._profile is not None or self.profile_path.exists()

    @property
    def profile(self) -> ToneProfile | None:
        if self._profile is None and self.profile_path.exists():
            self._profile = ToneProfile.load(self.profile_path)
        return self._profile

    @property
    def is_locked(self) -> bool:
        lock_path = self.root / ".governor" / "tone_locked"
        return lock_path.exists()

    def set_profile(self, profile: ToneProfile) -> None:
        """Set the active tone profile and save to disk."""
        self._profile = profile
        profile.save(self.profile_path)

    def clear_profile(self) -> None:
        """Remove the tone profile."""
        self._profile = None
        if self.profile_path.exists():
            self.profile_path.unlink()

    def lock(self) -> None:
        """Lock the tone profile as an enforcement invariant."""
        lock_path = self.root / ".governor" / "tone_locked"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(datetime.now().isoformat() + "\n")

    def unlock(self) -> None:
        """Unlock the tone profile."""
        lock_path = self.root / ".governor" / "tone_locked"
        if lock_path.exists():
            lock_path.unlink()

    def check_text(self, text: str, tolerance: float = 0.2) -> ToneCheckResult:
        """Check text against the active profile."""
        if self.profile is None:
            return ToneCheckResult(valid=True)
        checker = ToneChecker(self.profile, tolerance=tolerance)
        return checker.check(text)

    def get_guidance(self) -> str:
        """Get tone guidance for the active profile."""
        if self.profile is None:
            return ""
        return generate_tone_guidance(self.profile)

    def get_system_prompt(self) -> str:
        """Get system prompt fragment for the active profile."""
        if self.profile is None:
            return ""
        return format_system_prompt(self.profile)


# =============================================================================
# Phase T2: Corpus Analysis & Automatic Extraction
# =============================================================================


@dataclass
class ProfileDeviation:
    """A deviation between two tone profiles on a single dimension."""

    dimension: str
    baseline_value: Any
    other_value: Any
    deviation: float  # Absolute diff for numeric, 1.0 for boolean/string changes
    significant: bool  # Exceeds tolerance
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "baseline_value": self.baseline_value,
            "other_value": self.other_value,
            "deviation": self.deviation,
            "significant": self.significant,
            "message": self.message,
        }


# Suffixes for heuristic word classification
_ADJ_SUFFIXES = ("al", "ial", "ful", "ive", "ous", "ible", "able", "ic", "ical", "less", "ary")
_VERB_SUFFIXES = ("ize", "ise", "ate", "ify", "en")


def _extract_ngram_patterns(texts: list[str], n: int = 3, top_k: int = 5) -> list[str]:
    """Extract the most frequent n-gram patterns from text snippets."""
    patterns: Counter[str] = Counter()
    for text in texts:
        words = text.split()[:n]
        if len(words) >= 2:
            pattern = " ".join(words)
            patterns[pattern] += 1
    # Only return patterns seen more than once
    return [p for p, c in patterns.most_common(top_k) if c > 1]


def _extract_opening_patterns(paragraphs: list[str], top_n: int = 5) -> list[str]:
    """Extract common opening patterns from first sentences of paragraphs."""
    openings = []
    for para in paragraphs:
        sentences = _SENTENCE_PATTERN.findall(para)
        if sentences:
            openings.append(sentences[0].strip())
    return _extract_ngram_patterns(openings, n=3, top_k=top_n)


def _extract_transition_patterns(paragraphs: list[str], top_n: int = 5) -> list[str]:
    """Extract transition patterns from non-first paragraphs."""
    transitions = []
    for para in paragraphs[1:]:  # Skip first paragraph
        sentences = _SENTENCE_PATTERN.findall(para)
        if sentences:
            transitions.append(sentences[0].strip())
    return _extract_ngram_patterns(transitions, n=3, top_k=top_n)


def _extract_closing_patterns(paragraphs: list[str], top_n: int = 5) -> list[str]:
    """Extract closing patterns from last sentences of paragraphs."""
    closings = []
    for para in paragraphs:
        sentences = _SENTENCE_PATTERN.findall(para)
        if sentences:
            closings.append(sentences[-1].strip())
    return _extract_ngram_patterns(closings, n=3, top_k=top_n)


def _extract_frequent_content_words(
    all_words: list[str],
    stop_words: frozenset[str],
    top_n: int = 20,
) -> list[str]:
    """Extract most frequent non-stop-word content words."""
    cleaned = [w.lower().strip(".,!?;:\"'()[]") for w in all_words]
    content = [w for w in cleaned if w and len(w) > 2 and w not in stop_words]
    counts = Counter(content)
    return [w for w, _ in counts.most_common(top_n)]


def _classify_content_words(words: list[str]) -> tuple[list[str], list[str]]:
    """Heuristically classify content words as adjectives or verbs by suffix."""
    adjectives = []
    verbs = []
    for w in words:
        lower = w.lower()
        if any(lower.endswith(s) for s in _ADJ_SUFFIXES):
            adjectives.append(lower)
        elif any(lower.endswith(s) for s in _VERB_SUFFIXES):
            verbs.append(lower)
    return adjectives[:5], verbs[:5]


def extract_tone_profile(
    corpus_files: list[Path],
    name: str = "extracted",
    bool_threshold: float = 0.3,
) -> ToneProfile:
    """
    Analyze reference writing files to automatically extract a ToneProfile.

    Reads each file, runs analyze_text(), and aggregates metrics:
    - Numeric dimensions: averaged across files
    - Boolean dimensions: True if proportion of files >= bool_threshold
    - Patterns: extracted from combined text via n-gram frequency
    - Vocabulary: frequency analysis across all text
    """
    if not corpus_files:
        return ToneProfile(name=name)

    # Analyze each file
    file_metrics: list[dict[str, Any]] = []
    all_text_parts: list[str] = []

    for path in corpus_files:
        text = path.read_text()
        if not text.strip():
            continue
        metrics = analyze_text(text)
        if not metrics.get("empty"):
            file_metrics.append(metrics)
            all_text_parts.append(text)

    if not file_metrics:
        return ToneProfile(name=name)

    n = len(file_metrics)

    # Aggregate numeric dimensions (averages)
    avg_sentence_length = round(
        sum(m["avg_sentence_length"] for m in file_metrics) / n
    )
    sentence_length_variance = round(
        sum(m["sentence_length_variance"] for m in file_metrics) / n, 1
    )
    avg_paragraph_length = round(
        sum(m.get("avg_paragraph_length", 4) for m in file_metrics) / n
    )
    contractions_frequency = round(
        sum(m["contractions_frequency"] for m in file_metrics) / n, 2
    )

    # Aggregate boolean dimensions (threshold-based)
    def bool_agg(key: str) -> bool:
        count = sum(1 for m in file_metrics if m.get(key, False))
        return count / n >= bool_threshold

    uses_fragments = bool_agg("uses_fragments")
    uses_colons_for_emphasis = bool_agg("uses_colons_for_emphasis")
    uses_single_sentence_paragraphs = bool_agg("uses_single_sentence_paragraphs")
    uses_second_person = bool_agg("uses_second_person")
    uses_first_person = bool_agg("uses_first_person")
    uses_rhetorical_questions = bool_agg("uses_rhetorical_questions")
    uses_parentheticals = bool_agg("uses_parentheticals")
    uses_em_dashes = bool_agg("uses_em_dashes")
    uses_ellipses = bool_agg("uses_ellipses")

    # Combined text analysis for patterns and vocabulary
    combined_text = "\n\n".join(all_text_parts)
    all_paragraphs = [p.strip() for p in combined_text.split("\n\n") if p.strip()]
    all_words = combined_text.split()

    # Pattern extraction
    opening_patterns = _extract_opening_patterns(all_paragraphs)
    transition_patterns = _extract_transition_patterns(all_paragraphs)
    closing_patterns = _extract_closing_patterns(all_paragraphs)

    # Vocabulary analysis
    technical_density = round(_estimate_technical_density(all_words), 2)
    frequent_words = _extract_frequent_content_words(all_words, _STOP_WORDS, top_n=20)
    adjectives, verbs = _classify_content_words(frequent_words)

    return ToneProfile(
        name=name,
        description=f"Extracted from {n} reference file(s)",
        avg_sentence_length=avg_sentence_length,
        sentence_length_variance=sentence_length_variance,
        uses_fragments=uses_fragments,
        uses_colons_for_emphasis=uses_colons_for_emphasis,
        avg_paragraph_length=avg_paragraph_length,
        uses_single_sentence_paragraphs=uses_single_sentence_paragraphs,
        uses_second_person=uses_second_person,
        uses_first_person=uses_first_person,
        contractions_frequency=contractions_frequency,
        uses_rhetorical_questions=uses_rhetorical_questions,
        uses_parentheticals=uses_parentheticals,
        uses_em_dashes=uses_em_dashes,
        uses_ellipses=uses_ellipses,
        opening_patterns=opening_patterns,
        transition_patterns=transition_patterns,
        closing_patterns=closing_patterns,
        favorite_adjectives=adjectives,
        favorite_verbs=verbs,
        technical_density=technical_density,
    )


def compare_profiles(
    baseline: ToneProfile,
    other: ToneProfile,
    tolerance: float = 0.2,
) -> list[ProfileDeviation]:
    """
    Compare two profiles dimension-by-dimension.

    Returns a list of deviations. Each deviation indicates whether
    it is significant (exceeds tolerance).
    """
    deviations: list[ProfileDeviation] = []

    # Numeric comparisons with per-dimension tolerances
    numeric_dims: list[tuple[str, float]] = [
        ("avg_sentence_length", 5.0),           # 5-word tolerance
        ("sentence_length_variance", 3.0),       # 3-word std deviation
        ("avg_paragraph_length", 2.0),           # 2-sentence tolerance
        ("contractions_frequency", tolerance),    # direct tolerance
        ("technical_density", tolerance),         # direct tolerance
        ("sarcasm_frequency", tolerance),         # direct tolerance
    ]

    for dim, tol in numeric_dims:
        bv = getattr(baseline, dim)
        ov = getattr(other, dim)
        diff = abs(bv - ov)
        sig = diff > tol
        if diff > 0:
            deviations.append(ProfileDeviation(
                dimension=dim,
                baseline_value=bv,
                other_value=ov,
                deviation=round(diff, 3),
                significant=sig,
                message=(
                    f"{dim}: {bv} → {ov} (Δ={diff:.2f})"
                    + (" [SIGNIFICANT]" if sig else "")
                ),
            ))

    # Boolean comparisons
    bool_dims = [
        "uses_fragments", "uses_colons_for_emphasis",
        "uses_single_sentence_paragraphs",
        "uses_second_person", "uses_first_person",
        "uses_rhetorical_questions", "uses_parentheticals",
        "uses_em_dashes", "uses_ellipses",
        "uses_profanity", "uses_pop_culture_refs",
    ]

    for dim in bool_dims:
        bv = getattr(baseline, dim)
        ov = getattr(other, dim)
        if bv != ov:
            deviations.append(ProfileDeviation(
                dimension=dim,
                baseline_value=bv,
                other_value=ov,
                deviation=1.0,
                significant=True,
                message=f"{dim}: {bv} → {ov} [SIGNIFICANT]",
            ))

    # String comparisons
    string_dims = ["header_style", "uses_lists", "example_placement"]
    for dim in string_dims:
        bv = getattr(baseline, dim)
        ov = getattr(other, dim)
        if bv != ov:
            deviations.append(ProfileDeviation(
                dimension=dim,
                baseline_value=bv,
                other_value=ov,
                deviation=1.0,
                significant=True,
                message=f"{dim}: '{bv}' → '{ov}' [SIGNIFICANT]",
            ))

    return deviations
