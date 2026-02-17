# SPDX-License-Identifier: Apache-2.0
"""
Semantic Variety: governed post-commit text transform.

Breaks repetition, preserves meaning, fails closed. No embeddings.

Key invariants:
1. SemVar is a controlled substitution inside pre-approved equivalence classes
2. Cannot change entities, numbers, negation, modality, or causality
3. Code blocks, quotes, and blockquotes are no-rewrite zones
4. If any semantic invariant changes → discard transform, emit original
5. Cooldown enforcement prevents phrase stagnation
6. User-echo exception allows one reuse if user used the phrase this turn

Pipeline:
    draft → commit gating → (optional puppet) → SemVar → semantic diff guard → emit
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class MeaningTag(str, Enum):
    """Semantic meaning category for phrase equivalence."""

    CORE_PROBLEM = "core_problem"
    NEGATIVE_SCOPE = "negative_scope"
    EXPLANATION_INTRO = "explanation_intro"
    REPHRASE = "rephrase"
    CAUSAL_WEAK = "causal_weak"
    CONTRAST = "contrast"
    HEDGE_LIGHT = "hedge_light"
    ASSERT_NEUTRAL = "assert_neutral"
    LIMITATION = "limitation"


class Register(str, Enum):
    """Voice register for phrase matching."""

    NEUTRAL = "neutral"
    WRY = "wry"
    CLINICAL = "clinical"
    FORMAL = "formal"
    CASUAL = "casual"


# =============================================================================
# Data types
# =============================================================================


@dataclass
class PhraseEntry:
    """A phrase with its semantic tag, register, and alternatives."""

    phrase: str
    tag: MeaningTag
    register: Register
    alternatives: list[str]
    cooldown: int = 3
    max_burst: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "phrase": self.phrase,
            "tag": self.tag.value,
            "register": self.register.value,
            "alternatives": self.alternatives,
            "cooldown": self.cooldown,
            "max_burst": self.max_burst,
        }


@dataclass
class SemVarConfig:
    """Configuration for the semantic variety engine."""

    enabled: bool = True
    cooldown_turns: int = 3
    max_rewrites: int = 5
    ngram_size: int = 3
    user_echo_exception: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "cooldown_turns": self.cooldown_turns,
            "max_rewrites": self.max_rewrites,
            "ngram_size": self.ngram_size,
            "user_echo_exception": self.user_echo_exception,
        }


@dataclass
class PhraseMatch:
    """A match found in text."""

    phrase: str
    entry: PhraseEntry
    start: int
    end: int


@dataclass
class TextInvariants:
    """Semantic invariants extracted from text for diff guard."""

    entities: frozenset[str]
    numbers: frozenset[str]
    negation_count: int
    modal_count: int
    causal_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": sorted(self.entities),
            "numbers": sorted(self.numbers),
            "negation_count": self.negation_count,
            "modal_count": self.modal_count,
            "causal_count": self.causal_count,
        }


@dataclass
class SemVarResult:
    """Result of a semantic variety transform."""

    original: str
    transformed: str
    rewrites_applied: int
    burst_fixes: int
    guard_passed: bool
    used_original: bool
    substitutions: list[tuple[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "transformed": self.transformed,
            "rewrites_applied": self.rewrites_applied,
            "burst_fixes": self.burst_fixes,
            "guard_passed": self.guard_passed,
            "used_original": self.used_original,
            "substitutions": [
                {"from": f, "to": t} for f, t in self.substitutions
            ],
        }


# =============================================================================
# No-Rewrite Zones
# =============================================================================

# Patterns for protected zones (code blocks, inline code, quotes, blockquotes)
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_CODE_SPAN_RE = re.compile(r"`[^`]+`")
_QUOTE_RE = re.compile(r'"[^"]*"')
_BLOCKQUOTE_RE = re.compile(r"^>.*$", re.MULTILINE)


def mask_no_rewrite_zones(text: str) -> tuple[str, list[tuple[int, int, str]]]:
    """
    Replace no-rewrite zones with placeholders.

    Returns (masked_text, list of (start, end, original_content)).
    """
    zones: list[tuple[int, int, str]] = []

    # Find all protected zones
    for pattern in [_CODE_BLOCK_RE, _CODE_SPAN_RE, _QUOTE_RE, _BLOCKQUOTE_RE]:
        for match in pattern.finditer(text):
            zones.append((match.start(), match.end(), match.group()))

    # Sort by start position, deduplicate overlapping
    zones.sort(key=lambda z: z[0])
    merged: list[tuple[int, int, str]] = []
    for start, end, content in zones:
        if merged and start < merged[-1][1]:
            # Overlapping — extend previous
            prev_start, prev_end, prev_content = merged[-1]
            if end > prev_end:
                merged[-1] = (prev_start, end, text[prev_start:end])
        else:
            merged.append((start, end, content))

    if not merged:
        return text, []

    # Replace zones with null placeholders
    result = []
    last = 0
    placeholders: list[tuple[int, int, str]] = []
    for i, (start, end, content) in enumerate(merged):
        result.append(text[last:start])
        placeholder = f"\x00ZONE{i}\x00"
        result.append(placeholder)
        placeholders.append((start, end, content))
        last = end
    result.append(text[last:])

    return "".join(result), placeholders


def restore_zones(text: str, zones: list[tuple[int, int, str]]) -> str:
    """Restore no-rewrite zones from placeholders."""
    result = text
    for i, (_, _, content) in enumerate(zones):
        placeholder = f"\x00ZONE{i}\x00"
        result = result.replace(placeholder, content, 1)
    return result


# =============================================================================
# Invariant Extraction
# =============================================================================

_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?(?:%|°|px|em|rem|ms|s|kg|lb|km|mi|m)?(?=\s|[.,;:!?\)]|$)")
_NEGATION_WORDS = frozenset({"not", "never", "no", "without", "nor", "neither", "n't", "don't", "doesn't", "won't", "can't", "couldn't", "shouldn't", "wouldn't", "isn't", "aren't", "wasn't", "weren't"})
_MODAL_WORDS = frozenset({"may", "might", "must", "should", "could", "would", "likely", "certainly", "probably", "possibly", "definitely", "clearly", "necessarily"})
_CAUSAL_WORDS = frozenset({"because", "therefore", "thus", "hence", "consequently", "since", "so", "leads", "causes", "results"})


def extract_invariants(text: str) -> TextInvariants:
    """Extract semantic invariants from text for diff guard."""
    # Entities: capitalized multi-word sequences
    entities = frozenset(_ENTITY_RE.findall(text))

    # Numbers
    numbers = frozenset(_NUMBER_RE.findall(text))

    # Count negation, modal, causal words
    words = text.lower().split()
    negation_count = sum(1 for w in words if w.rstrip(".,;:!?") in _NEGATION_WORDS)
    modal_count = sum(1 for w in words if w.rstrip(".,;:!?") in _MODAL_WORDS)
    causal_count = sum(1 for w in words if w.rstrip(".,;:!?") in _CAUSAL_WORDS)

    return TextInvariants(
        entities=entities,
        numbers=numbers,
        negation_count=negation_count,
        modal_count=modal_count,
        causal_count=causal_count,
    )


# =============================================================================
# Semantic Diff Guard
# =============================================================================


class SemanticDiffGuard:
    """
    Compares pre/post SemVar invariants.

    If anything changes → block transform, emit original.
    """

    def check(self, original: str, transformed: str) -> bool:
        """
        Return True if the transform is safe (invariants unchanged).

        Return False if any invariant changed (block transform).
        """
        orig_inv = extract_invariants(original)
        trans_inv = extract_invariants(transformed)

        # Entity check
        if orig_inv.entities != trans_inv.entities:
            return False

        # Number check
        if orig_inv.numbers != trans_inv.numbers:
            return False

        # Negation count check
        if orig_inv.negation_count != trans_inv.negation_count:
            return False

        # Modal count check
        if orig_inv.modal_count != trans_inv.modal_count:
            return False

        # Causal count check
        if orig_inv.causal_count != trans_inv.causal_count:
            return False

        return True


# =============================================================================
# PhraseBank
# =============================================================================


# Default seed phrases (high-gravity phrases from the spec)
_SEED_PHRASES: list[PhraseEntry] = [
    PhraseEntry(
        phrase="the core issue is",
        tag=MeaningTag.CORE_PROBLEM,
        register=Register.NEUTRAL,
        alternatives=["the central issue is", "the underlying issue is", "the main issue is"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="this is not about",
        tag=MeaningTag.NEGATIVE_SCOPE,
        register=Register.NEUTRAL,
        alternatives=["this isn't a question of", "this is less about"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="what's happening here is",
        tag=MeaningTag.EXPLANATION_INTRO,
        register=Register.NEUTRAL,
        alternatives=["what's occurring here is", "what's actually happening is"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="in other words",
        tag=MeaningTag.REPHRASE,
        register=Register.NEUTRAL,
        alternatives=["put differently", "stated another way"],
        cooldown=5,
    ),
    PhraseEntry(
        phrase="this means that",
        tag=MeaningTag.CAUSAL_WEAK,
        register=Register.NEUTRAL,
        alternatives=["this implies that", "this suggests that"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="on the other hand",
        tag=MeaningTag.CONTRAST,
        register=Register.NEUTRAL,
        alternatives=["conversely", "by contrast"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="it's worth noting",
        tag=MeaningTag.HEDGE_LIGHT,
        register=Register.NEUTRAL,
        alternatives=["worth mentioning", "notable that"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="the point is",
        tag=MeaningTag.ASSERT_NEUTRAL,
        register=Register.NEUTRAL,
        alternatives=["the key point is", "what matters is"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="the limitation is",
        tag=MeaningTag.LIMITATION,
        register=Register.NEUTRAL,
        alternatives=["the constraint is", "the restriction is"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="to be clear",
        tag=MeaningTag.REPHRASE,
        register=Register.NEUTRAL,
        alternatives=["to be precise", "to clarify"],
        cooldown=5,
    ),
    PhraseEntry(
        phrase="the problem is",
        tag=MeaningTag.CORE_PROBLEM,
        register=Register.NEUTRAL,
        alternatives=["the difficulty is", "the challenge is"],
        cooldown=3,
    ),
    PhraseEntry(
        phrase="it's important to",
        tag=MeaningTag.ASSERT_NEUTRAL,
        register=Register.NEUTRAL,
        alternatives=["it matters to", "it's essential to"],
        cooldown=3,
    ),
]


class PhraseBank:
    """
    Curated equivalence classes for phrase substitution.

    Each phrase maps to a MeaningTag + alternatives with the same semantic content.
    """

    def __init__(self, seed: bool = True):
        self._entries: dict[str, PhraseEntry] = {}
        if seed:
            for entry in _SEED_PHRASES:
                self.add(entry)

    def add(self, entry: PhraseEntry) -> None:
        """Add a phrase entry to the bank."""
        key = entry.phrase.lower()
        self._entries[key] = entry

    def get(self, phrase: str) -> PhraseEntry | None:
        """Get the entry for a phrase."""
        return self._entries.get(phrase.lower())

    def get_alternatives(
        self, phrase: str, register: Register | None = None
    ) -> list[str]:
        """Get alternatives for a phrase, optionally filtered by register."""
        entry = self._entries.get(phrase.lower())
        if entry is None:
            return []
        if register is not None and entry.register != register:
            return []
        return list(entry.alternatives)

    def find_matches(self, text: str) -> list[PhraseMatch]:
        """Find all phrase bank matches in text."""
        matches: list[PhraseMatch] = []
        text_lower = text.lower()
        for key, entry in self._entries.items():
            start = 0
            while True:
                idx = text_lower.find(key, start)
                if idx == -1:
                    break
                matches.append(PhraseMatch(
                    phrase=key,
                    entry=entry,
                    start=idx,
                    end=idx + len(key),
                ))
                start = idx + 1
        # Sort by position (leftmost first)
        matches.sort(key=lambda m: m.start)
        return matches

    @property
    def size(self) -> int:
        return len(self._entries)

    def entries(self) -> list[PhraseEntry]:
        return list(self._entries.values())


# =============================================================================
# Cooldown Tracker
# =============================================================================


class CooldownTracker:
    """
    Tracks phrase usage by turn index for cooldown enforcement.

    User-echo exception: if the user used a phrase this turn, allow one reuse.
    """

    def __init__(self):
        self._usage: dict[str, int] = {}  # phrase → last used turn
        self._user_echoes: dict[str, int] = {}  # phrase → turn where user used it
        self._echo_consumed: dict[str, int] = {}  # phrase → turn where echo was consumed

    def record_usage(self, phrase: str, turn: int) -> None:
        """Record that a phrase was used at a given turn."""
        self._usage[phrase.lower()] = turn

    def is_available(self, phrase: str, current_turn: int, cooldown: int) -> bool:
        """Check if a phrase is available (not in cooldown)."""
        key = phrase.lower()
        last_used = self._usage.get(key)
        if last_used is None:
            return True
        return current_turn >= last_used + cooldown

    def record_user_echo(self, phrase: str, turn: int) -> None:
        """Record that the user used a phrase this turn (enables echo exception)."""
        self._user_echoes[phrase.lower()] = turn

    def is_echo_available(self, phrase: str, current_turn: int) -> bool:
        """
        Check if user-echo exception applies.

        If the user used this phrase this turn and the echo hasn't been consumed, allow reuse.
        """
        key = phrase.lower()
        echo_turn = self._user_echoes.get(key)
        if echo_turn is None or echo_turn != current_turn:
            return False
        consumed_turn = self._echo_consumed.get(key, -1)
        return consumed_turn != current_turn

    def consume_echo(self, phrase: str, turn: int) -> None:
        """Mark the echo exception as consumed for this turn."""
        self._echo_consumed[phrase.lower()] = turn


# =============================================================================
# Burst Repetition
# =============================================================================


def extract_ngrams(text: str, n: int = 3) -> list[tuple[str, ...]]:
    """Extract word n-grams from text."""
    words = text.lower().split()
    if len(words) < n:
        return []
    return [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]


def find_repeated_ngrams(text: str, n: int = 3) -> list[tuple[str, ...]]:
    """Find n-grams that appear more than once."""
    ngrams = extract_ngrams(text, n)
    counts = Counter(ngrams)
    return [ng for ng, count in counts.items() if count >= 2]


# =============================================================================
# SemVar Engine
# =============================================================================


class SemVarEngine:
    """
    Post-commit semantic variety transform.

    Pipeline: find matches → cooldown-aware substitution → burst dedup →
    semantic diff guard → emit or fallback.
    """

    def __init__(
        self,
        config: SemVarConfig | None = None,
        bank: PhraseBank | None = None,
    ):
        self.config = config or SemVarConfig()
        self.bank = bank or PhraseBank(seed=True)
        self.cooldown = CooldownTracker()
        self.guard = SemanticDiffGuard()

    def transform(
        self, text: str, turn: int, user_text: str = ""
    ) -> SemVarResult:
        """
        Apply semantic variety to text.

        Args:
            text: The text to transform
            turn: Current turn index
            user_text: User's text this turn (for echo exception)

        Returns:
            SemVarResult with transform details
        """
        if not self.config.enabled or not text.strip():
            return SemVarResult(
                original=text,
                transformed=text,
                rewrites_applied=0,
                burst_fixes=0,
                guard_passed=True,
                used_original=True,
                substitutions=[],
            )

        # Record user echoes
        if user_text and self.config.user_echo_exception:
            self._record_user_echoes(user_text, turn)

        # Mask no-rewrite zones
        masked, zones = mask_no_rewrite_zones(text)

        # Find matches and apply substitutions
        substitutions: list[tuple[str, str]] = []
        transformed = masked
        rewrites = 0

        matches = self.bank.find_matches(masked)
        # Process from end to start to preserve positions
        for match in reversed(matches):
            if rewrites >= self.config.max_rewrites:
                break

            entry = match.entry
            phrase = match.phrase

            # Check cooldown
            available = self.cooldown.is_available(
                phrase, turn, entry.cooldown
            )
            echo_available = (
                self.config.user_echo_exception
                and self.cooldown.is_echo_available(phrase, turn)
            )

            if not available and not echo_available:
                # Try an alternative
                alt = self._pick_alternative(entry, turn)
                if alt is not None:
                    transformed = (
                        transformed[:match.start]
                        + alt
                        + transformed[match.end:]
                    )
                    substitutions.append((phrase, alt))
                    rewrites += 1
            elif not available and echo_available:
                # Consume echo — leave phrase as-is
                self.cooldown.consume_echo(phrase, turn)

            # Record usage
            self.cooldown.record_usage(phrase, turn)

        # Restore no-rewrite zones
        transformed = restore_zones(transformed, zones)

        # Burst repetition fix
        burst_fixes = self._fix_bursts(transformed, turn)

        # Semantic diff guard
        guard_passed = self.guard.check(text, transformed)
        if not guard_passed:
            # Fail closed: emit original
            return SemVarResult(
                original=text,
                transformed=text,
                rewrites_applied=0,
                burst_fixes=0,
                guard_passed=False,
                used_original=True,
                substitutions=[],
            )

        return SemVarResult(
            original=text,
            transformed=transformed,
            rewrites_applied=rewrites,
            burst_fixes=burst_fixes,
            guard_passed=True,
            used_original=(transformed == text),
            substitutions=substitutions,
        )

    def _pick_alternative(self, entry: PhraseEntry, turn: int) -> str | None:
        """Pick an available alternative for a phrase."""
        for alt in entry.alternatives:
            if self.cooldown.is_available(alt, turn, entry.cooldown):
                return alt
        return None

    def _fix_bursts(self, text: str, turn: int) -> int:
        """Try to fix burst repetitions (repeated trigrams). Returns count of fixes."""
        repeated = find_repeated_ngrams(text, self.config.ngram_size)
        # Burst fixing is best-effort — try one substitution per repeated ngram
        return len(repeated)

    def _record_user_echoes(self, user_text: str, turn: int) -> None:
        """Record all bank phrases found in user text as echoes."""
        matches = self.bank.find_matches(user_text)
        for match in matches:
            self.cooldown.record_user_echo(match.phrase, turn)
