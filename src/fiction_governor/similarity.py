# SPDX-License-Identifier: Apache-2.0
"""
Similarity matching for fiction verification.

Provides embedding-based and TF-IDF-based similarity for:
- Trope detection (compare new content against banned tropes)
- Character voice consistency (compare dialogue against established voice)
- Tone matching (compare prose against tone settings)
"""

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from .types import BannedTrope, Character, ToneSettings


# =============================================================================
# Base Types
# =============================================================================

@dataclass
class SimilarityMatch:
    """A similarity match result."""
    query: str
    matched: str
    score: float  # 0.0 to 1.0
    match_type: str  # 'trope', 'voice', 'tone', 'anti_pattern'
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_strong_match(self) -> bool:
        """Whether this is a strong match (> 0.7)."""
        return self.score > 0.7

    @property
    def is_weak_match(self) -> bool:
        """Whether this is a weak match (0.3 - 0.7)."""
        return 0.3 <= self.score <= 0.7


@dataclass
class VoiceAnalysis:
    """Analysis of character voice consistency."""
    character: str
    sample: str
    consistency_score: float  # How well it matches established voice
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ToneAnalysis:
    """Analysis of tone consistency."""
    sample: str
    tone_score: float  # How well it matches target tone
    genre_match: float  # How well it matches genre expectations
    issues: list[str] = field(default_factory=list)


# =============================================================================
# Embedding Provider Interface
# =============================================================================

class EmbeddingProvider(ABC):
    """Abstract interface for embedding providers."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Get embedding vector for text."""
        pass

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embedding vectors for multiple texts."""
        pass

    def similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


class TFIDFProvider(EmbeddingProvider):
    """
    TF-IDF based similarity (no external dependencies).

    This is a fallback when no embedding model is available.
    It's less semantic but still useful for pattern matching.
    """

    def __init__(self, vocabulary: list[str] | None = None):
        self._vocabulary: dict[str, int] = {}
        self._idf: dict[str, float] = {}
        self._documents: list[str] = []

        if vocabulary:
            self._vocabulary = {word: i for i, word in enumerate(vocabulary)}

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words."""
        # Simple tokenization: lowercase, split on non-alphanumeric
        text = text.lower()
        words = re.findall(r'\b[a-z]+\b', text)
        # Remove very common words
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'is', 'are', 'was', 'were'}
        return [w for w in words if w not in stopwords and len(w) > 2]

    def _compute_tf(self, tokens: list[str]) -> dict[str, float]:
        """Compute term frequency."""
        counts = Counter(tokens)
        total = len(tokens) if tokens else 1
        return {word: count / total for word, count in counts.items()}

    def fit(self, documents: list[str]) -> None:
        """Fit IDF on a corpus of documents."""
        self._documents = documents
        n_docs = len(documents)

        # Count document frequency
        df: dict[str, int] = Counter()
        for doc in documents:
            tokens = set(self._tokenize(doc))
            for token in tokens:
                df[token] += 1

        # Compute IDF
        self._idf = {}
        for word, count in df.items():
            self._idf[word] = math.log((n_docs + 1) / (count + 1)) + 1

        # Build vocabulary
        self._vocabulary = {word: i for i, word in enumerate(self._idf.keys())}

    def embed(self, text: str) -> list[float]:
        """Get TF-IDF vector for text."""
        tokens = self._tokenize(text)
        tf = self._compute_tf(tokens)

        # Build vector
        vector = [0.0] * len(self._vocabulary)
        for word, freq in tf.items():
            if word in self._vocabulary:
                idx = self._vocabulary[word]
                idf = self._idf.get(word, 1.0)
                vector[idx] = freq * idf

        # Normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Get TF-IDF vectors for multiple texts."""
        return [self.embed(text) for text in texts]


# =============================================================================
# Similarity Analyzer
# =============================================================================

class SimilarityAnalyzer:
    """
    Analyzes text similarity for fiction verification.

    Supports both embedding-based (if provider given) and TF-IDF fallback.
    """

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        trope_threshold: float = 0.6,
        voice_threshold: float = 0.5,
        tone_threshold: float = 0.5,
    ):
        """
        Initialize the analyzer.

        Args:
            provider: Embedding provider (uses TF-IDF if None)
            trope_threshold: Similarity threshold for trope detection
            voice_threshold: Similarity threshold for voice consistency
            tone_threshold: Similarity threshold for tone consistency
        """
        self.provider = provider or TFIDFProvider()
        self.trope_threshold = trope_threshold
        self.voice_threshold = voice_threshold
        self.tone_threshold = tone_threshold

        # Cache embeddings
        self._trope_embeddings: dict[str, list[float]] = {}
        self._voice_embeddings: dict[str, list[float]] = {}

    def _get_or_compute_embedding(
        self,
        text: str,
        cache: dict[str, list[float]],
    ) -> list[float]:
        """Get embedding from cache or compute it."""
        if text not in cache:
            cache[text] = self.provider.embed(text)
        return cache[text]

    # -------------------------------------------------------------------------
    # Trope Detection
    # -------------------------------------------------------------------------

    def check_tropes(
        self,
        content: str,
        banned_tropes: list[BannedTrope],
    ) -> list[SimilarityMatch]:
        """
        Check content against banned tropes.

        Returns list of matches above threshold.
        """
        matches = []

        content_embedding = self.provider.embed(content)

        for trope in banned_tropes:
            # Check against trope examples and patterns
            trope_texts = trope.examples + trope.patterns

            if not trope_texts:
                # Use name and reason as fallback
                trope_texts = [trope.name, trope.reason]

            for trope_text in trope_texts:
                trope_embedding = self._get_or_compute_embedding(
                    trope_text,
                    self._trope_embeddings,
                )

                score = self.provider.similarity(content_embedding, trope_embedding)

                if score >= self.trope_threshold:
                    matches.append(SimilarityMatch(
                        query=content[:100] + "...",
                        matched=trope.name,
                        score=score,
                        match_type="trope",
                        details={
                            "trope_id": str(trope.id),
                            "reason": trope.reason,
                            "severity": trope.severity,
                            "matched_pattern": trope_text,
                        },
                    ))
                    break  # One match per trope is enough

        return sorted(matches, key=lambda m: m.score, reverse=True)

    def check_anti_patterns(
        self,
        content: str,
        character: Character,
    ) -> list[SimilarityMatch]:
        """
        Check content against character anti-patterns.

        Returns matches that suggest out-of-character behavior.
        """
        matches = []

        content_embedding = self.provider.embed(content)

        for anti_pattern in character.anti_patterns:
            pattern_embedding = self.provider.embed(anti_pattern)
            score = self.provider.similarity(content_embedding, pattern_embedding)

            if score >= self.voice_threshold:
                matches.append(SimilarityMatch(
                    query=content[:100] + "...",
                    matched=anti_pattern,
                    score=score,
                    match_type="anti_pattern",
                    details={
                        "character": character.name,
                        "anti_pattern": anti_pattern,
                    },
                ))

        return sorted(matches, key=lambda m: m.score, reverse=True)

    # -------------------------------------------------------------------------
    # Voice Consistency
    # -------------------------------------------------------------------------

    def analyze_voice(
        self,
        dialogue: str,
        character: Character,
        reference_samples: list[str] | None = None,
    ) -> VoiceAnalysis:
        """
        Analyze how well dialogue matches a character's voice.

        Args:
            dialogue: The dialogue to check
            character: Character to check against
            reference_samples: Known good dialogue samples for this character

        Returns:
            VoiceAnalysis with consistency score and issues
        """
        issues = []
        suggestions = []
        scores = []

        # Check against voice avoid patterns
        if character.voice and character.voice.avoid:
            for avoid in character.voice.avoid:
                if avoid.lower() in dialogue.lower():
                    issues.append(f"Contains '{avoid}' which should be avoided")
                    scores.append(0.3)  # Penalty

        # Check against reference samples if provided
        if reference_samples:
            dialogue_embedding = self.provider.embed(dialogue)
            sample_scores = []

            for sample in reference_samples:
                sample_embedding = self._get_or_compute_embedding(
                    sample,
                    self._voice_embeddings,
                )
                score = self.provider.similarity(dialogue_embedding, sample_embedding)
                sample_scores.append(score)

            if sample_scores:
                avg_score = sum(sample_scores) / len(sample_scores)
                scores.append(avg_score)

                if avg_score < self.voice_threshold:
                    issues.append(f"Voice differs from established patterns (score: {avg_score:.2f})")
                    suggestions.append("Review character voice guidelines")

        # Check for voice style markers
        if character.voice:
            if character.voice.dialogue:
                # Simple keyword matching for dialogue style
                style_keywords = character.voice.dialogue.lower().split()
                matching_keywords = sum(1 for kw in style_keywords if kw in dialogue.lower())
                keyword_score = matching_keywords / len(style_keywords) if style_keywords else 1.0
                scores.append(keyword_score)

        # Calculate overall score
        if scores:
            consistency_score = sum(scores) / len(scores)
        else:
            consistency_score = 0.5  # Neutral if no reference

        return VoiceAnalysis(
            character=character.name,
            sample=dialogue[:200],
            consistency_score=consistency_score,
            issues=issues,
            suggestions=suggestions,
        )

    # -------------------------------------------------------------------------
    # Tone Analysis
    # -------------------------------------------------------------------------

    def analyze_tone(
        self,
        content: str,
        tone_settings: ToneSettings,
        reference_samples: list[str] | None = None,
    ) -> ToneAnalysis:
        """
        Analyze how well content matches tone settings.

        Args:
            content: The prose to check
            tone_settings: Target tone settings
            reference_samples: Known good prose samples

        Returns:
            ToneAnalysis with scores and issues
        """
        issues = []
        scores = []

        # Check avoid patterns
        for avoid in tone_settings.avoid:
            if avoid.lower() in content.lower():
                issues.append(f"Contains '{avoid}' which should be avoided")
                scores.append(0.3)

        # Check against not-genres markers
        genre_markers = {
            "YA": ["totally", "like,", "awesome", "epic fail", "omg"],
            "cozy": ["cozy", "quaint", "snuggled", "heartwarming"],
            "romance": ["smoldering", "chiseled", "heaving bosom"],
            "thriller": ["heart pounding", "adrenaline", "raced against time"],
        }

        for not_genre in tone_settings.not_genres:
            if not_genre in genre_markers:
                for marker in genre_markers[not_genre]:
                    if marker.lower() in content.lower():
                        issues.append(f"Contains '{marker}' which suggests {not_genre} tone")
                        scores.append(0.4)

        # Check against reference samples
        genre_match = 0.5
        if reference_samples:
            content_embedding = self.provider.embed(content)
            sample_scores = []

            for sample in reference_samples:
                sample_embedding = self.provider.embed(sample)
                score = self.provider.similarity(content_embedding, sample_embedding)
                sample_scores.append(score)

            if sample_scores:
                genre_match = sum(sample_scores) / len(sample_scores)
                scores.append(genre_match)

                if genre_match < self.tone_threshold:
                    issues.append(f"Tone differs from established style (score: {genre_match:.2f})")

        # Calculate overall score
        if scores:
            tone_score = sum(scores) / len(scores)
        else:
            tone_score = 0.5  # Neutral

        return ToneAnalysis(
            sample=content[:200],
            tone_score=tone_score,
            genre_match=genre_match,
            issues=issues,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

def create_analyzer(
    corpus: list[str] | None = None,
    provider: EmbeddingProvider | None = None,
) -> SimilarityAnalyzer:
    """
    Create a similarity analyzer.

    If corpus is provided and no provider given, fits a TF-IDF model on it.
    """
    if provider is None:
        provider = TFIDFProvider()
        if corpus:
            provider.fit(corpus)

    return SimilarityAnalyzer(provider=provider)


def quick_trope_check(
    content: str,
    banned_tropes: list[BannedTrope],
    threshold: float = 0.6,
) -> list[SimilarityMatch]:
    """
    Quick trope check using TF-IDF (no external dependencies).

    Args:
        content: Content to check
        banned_tropes: List of banned tropes
        threshold: Similarity threshold

    Returns:
        List of matching tropes
    """
    # Build corpus from trope patterns
    corpus = []
    for trope in banned_tropes:
        corpus.extend(trope.examples)
        corpus.extend(trope.patterns)

    if not corpus:
        return []

    provider = TFIDFProvider()
    provider.fit(corpus + [content])

    analyzer = SimilarityAnalyzer(
        provider=provider,
        trope_threshold=threshold,
    )

    return analyzer.check_tropes(content, banned_tropes)


def quick_voice_check(
    dialogue: str,
    character: Character,
    reference_samples: list[str],
) -> VoiceAnalysis:
    """
    Quick voice consistency check using TF-IDF.

    Args:
        dialogue: Dialogue to check
        character: Character to check against
        reference_samples: Known good samples

    Returns:
        VoiceAnalysis
    """
    provider = TFIDFProvider()
    provider.fit(reference_samples + [dialogue])

    analyzer = SimilarityAnalyzer(provider=provider)
    return analyzer.analyze_voice(dialogue, character, reference_samples)


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Compute similarity between two texts using TF-IDF.

    Convenience function for simple comparisons.
    """
    provider = TFIDFProvider()
    provider.fit([text1, text2])

    vec1 = provider.embed(text1)
    vec2 = provider.embed(text2)

    return provider.similarity(vec1, vec2)
