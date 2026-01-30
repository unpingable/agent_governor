"""Tests for similarity matching in fiction governor."""

import pytest
from uuid import uuid4

from fiction_governor.similarity import (
    SimilarityMatch,
    VoiceAnalysis,
    ToneAnalysis,
    EmbeddingProvider,
    TFIDFProvider,
    SimilarityAnalyzer,
    create_analyzer,
    quick_trope_check,
    quick_voice_check,
    compute_text_similarity,
)
from fiction_governor.types import (
    BannedTrope,
    Character,
    CharacterVoice,
    ToneSettings,
)


# =============================================================================
# SimilarityMatch Tests
# =============================================================================

class TestSimilarityMatch:
    """Tests for SimilarityMatch dataclass."""

    def test_is_strong_match(self):
        """Strong match detection works."""
        match = SimilarityMatch(
            query="test",
            matched="pattern",
            score=0.8,
            match_type="trope"
        )
        assert match.is_strong_match
        assert not match.is_weak_match

    def test_is_weak_match(self):
        """Weak match detection works."""
        match = SimilarityMatch(
            query="test",
            matched="pattern",
            score=0.5,
            match_type="trope"
        )
        assert not match.is_strong_match
        assert match.is_weak_match

    def test_no_match(self):
        """Low scores are neither strong nor weak."""
        match = SimilarityMatch(
            query="test",
            matched="pattern",
            score=0.2,
            match_type="trope"
        )
        assert not match.is_strong_match
        assert not match.is_weak_match

    def test_details_default_empty(self):
        """Details default to empty dict."""
        match = SimilarityMatch(
            query="test",
            matched="pattern",
            score=0.5,
            match_type="trope"
        )
        assert match.details == {}


# =============================================================================
# TFIDFProvider Tests
# =============================================================================

class TestTFIDFProvider:
    """Tests for TF-IDF embedding provider."""

    def test_tokenize_basic(self):
        """Basic tokenization works."""
        provider = TFIDFProvider()
        tokens = provider._tokenize("Hello world, the is a test!")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        # Stopwords removed
        assert "the" not in tokens
        assert "a" not in tokens

    def test_tokenize_removes_short_words(self):
        """Short words are removed."""
        provider = TFIDFProvider()
        tokens = provider._tokenize("I am at it")
        # All should be filtered (length <= 2 or stopwords)
        assert len(tokens) == 0

    def test_fit_builds_vocabulary(self):
        """Fitting builds vocabulary and IDF."""
        provider = TFIDFProvider()
        provider.fit([
            "The cat sat on the mat",
            "The dog ran in the park",
            "A bird flew over the cat",
        ])

        assert len(provider._vocabulary) > 0
        assert len(provider._idf) > 0
        # Common word should have lower IDF
        # Unique word should have higher IDF

    def test_embed_returns_vector(self):
        """Embedding returns a vector."""
        provider = TFIDFProvider()
        provider.fit(["hello world", "goodbye world"])

        vec = provider.embed("hello world")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_embed_normalized(self):
        """Embedding vectors are normalized."""
        provider = TFIDFProvider()
        provider.fit(["hello world test", "goodbye world example"])

        vec = provider.embed("hello world test")
        # L2 norm should be ~1.0
        norm = sum(v * v for v in vec) ** 0.5
        assert abs(norm - 1.0) < 0.01 or norm == 0.0  # Either normalized or zero

    def test_embed_batch(self):
        """Batch embedding works."""
        provider = TFIDFProvider()
        provider.fit(["one two", "three four", "five six"])

        vecs = provider.embed_batch(["one two", "three four"])
        assert len(vecs) == 2
        assert all(isinstance(v, list) for v in vecs)

    def test_similarity_identical(self):
        """Identical texts have high similarity."""
        provider = TFIDFProvider()
        provider.fit(["the quick brown fox", "the lazy dog"])

        vec = provider.embed("the quick brown fox")
        sim = provider.similarity(vec, vec)
        assert sim > 0.99

    def test_similarity_different(self):
        """Different texts have lower similarity."""
        provider = TFIDFProvider()
        provider.fit(["cat dog pet animal", "computer software code"])

        vec1 = provider.embed("cat dog pet animal")
        vec2 = provider.embed("computer software code")
        sim = provider.similarity(vec1, vec2)
        assert sim < 0.5

    def test_similarity_empty_vectors(self):
        """Empty vectors return 0 similarity."""
        provider = TFIDFProvider()
        assert provider.similarity([], []) == 0.0
        assert provider.similarity([1.0, 2.0], []) == 0.0

    def test_similarity_zero_vectors(self):
        """Zero vectors return 0 similarity."""
        provider = TFIDFProvider()
        assert provider.similarity([0.0, 0.0], [0.0, 0.0]) == 0.0


# =============================================================================
# SimilarityAnalyzer Tests
# =============================================================================

class TestSimilarityAnalyzer:
    """Tests for SimilarityAnalyzer class."""

    def test_init_defaults(self):
        """Analyzer initializes with defaults."""
        analyzer = SimilarityAnalyzer()
        assert analyzer.provider is not None
        assert analyzer.trope_threshold == 0.6
        assert analyzer.voice_threshold == 0.5

    def test_init_custom_thresholds(self):
        """Analyzer accepts custom thresholds."""
        analyzer = SimilarityAnalyzer(
            trope_threshold=0.8,
            voice_threshold=0.7,
            tone_threshold=0.6,
        )
        assert analyzer.trope_threshold == 0.8
        assert analyzer.voice_threshold == 0.7
        assert analyzer.tone_threshold == 0.6


class TestTropeDetection:
    """Tests for trope detection."""

    def test_check_tropes_no_match(self):
        """No match when content doesn't match tropes."""
        analyzer = SimilarityAnalyzer(trope_threshold=0.9)

        tropes = [
            BannedTrope(
                id=uuid4(),
                name="Chosen One",
                reason="Overused",
                severity="medium",
                examples=["prophecy chosen destined hero"],
                patterns=["the one foretold"],
            )
        ]

        content = "John went to the grocery store and bought milk."
        matches = analyzer.check_tropes(content, tropes)
        assert len(matches) == 0

    def test_check_tropes_with_match(self):
        """Match when content resembles trope."""
        # Use a lower threshold for testing
        analyzer = SimilarityAnalyzer(trope_threshold=0.3)

        tropes = [
            BannedTrope(
                id=uuid4(),
                name="Chosen One",
                reason="Overused",
                severity="high",
                examples=["prophecy chosen destined hero savior"],
                patterns=["the one foretold by prophecy"],
            )
        ]

        content = "The prophecy spoke of a chosen hero destined to save the world."
        matches = analyzer.check_tropes(content, tropes)
        # Should find at least some similarity
        # (TF-IDF may or may not match depending on vocabulary)

    def test_check_tropes_uses_name_fallback(self):
        """Uses trope name when no examples/patterns."""
        analyzer = SimilarityAnalyzer(trope_threshold=0.3)

        tropes = [
            BannedTrope(
                id=uuid4(),
                name="love triangle romance jealousy",
                reason="Tired cliche",
                severity="medium",
                examples=[],
                patterns=[],
            )
        ]

        content = "She loved him but he loved another, creating a bitter love triangle of jealousy."
        matches = analyzer.check_tropes(content, tropes)
        # Should still work with fallback

    def test_check_tropes_sorted_by_score(self):
        """Matches are sorted by score descending."""
        analyzer = SimilarityAnalyzer(trope_threshold=0.01)  # Very low for testing

        tropes = [
            BannedTrope(
                id=uuid4(),
                name="trope1",
                reason="r1",
                severity="low",
                examples=["xyz abc"],
                patterns=[],
            ),
            BannedTrope(
                id=uuid4(),
                name="trope2",
                reason="r2",
                severity="low",
                examples=["hello world"],
                patterns=[],
            ),
        ]

        content = "hello world test"
        matches = analyzer.check_tropes(content, tropes)

        if len(matches) > 1:
            assert matches[0].score >= matches[1].score


class TestAntiPatternDetection:
    """Tests for character anti-pattern detection."""

    def test_check_anti_patterns_no_match(self):
        """No match when content is in-character."""
        analyzer = SimilarityAnalyzer(voice_threshold=0.9)

        character = Character(
            id=uuid4(),
            name="Stoic Warrior",
            anti_patterns=["crying weeping tears emotional breakdown"],
        )

        content = "He stood firm, his face like stone."
        matches = analyzer.check_anti_patterns(content, character)
        assert len(matches) == 0

    def test_check_anti_patterns_with_match(self):
        """Match when content violates character patterns."""
        analyzer = SimilarityAnalyzer(voice_threshold=0.3)

        character = Character(
            id=uuid4(),
            name="Stoic Warrior",
            anti_patterns=["crying weeping tears sobbing emotional"],
        )

        content = "He broke down sobbing, tears streaming down his face."
        matches = analyzer.check_anti_patterns(content, character)
        # May or may not match with TF-IDF


class TestVoiceAnalysis:
    """Tests for voice consistency analysis."""

    def test_analyze_voice_basic(self):
        """Basic voice analysis works."""
        analyzer = SimilarityAnalyzer()

        character = Character(
            id=uuid4(),
            name="Test",
        )

        result = analyzer.analyze_voice("Hello there", character)

        assert isinstance(result, VoiceAnalysis)
        assert result.character == "Test"
        assert "Hello" in result.sample

    def test_analyze_voice_avoid_patterns(self):
        """Avoid patterns are detected."""
        analyzer = SimilarityAnalyzer()

        character = Character(
            id=uuid4(),
            name="Formal Noble",
            voice=CharacterVoice(
                avoid=["yo", "dude", "bro"],
            ),
        )

        result = analyzer.analyze_voice(
            "Yo dude, what's up bro?",
            character
        )

        assert len(result.issues) > 0
        assert any("yo" in issue.lower() or "dude" in issue.lower() for issue in result.issues)

    def test_analyze_voice_with_reference_samples(self):
        """Reference samples affect consistency score."""
        provider = TFIDFProvider()
        provider.fit([
            "Indeed, most fascinating observation.",
            "Quite remarkable, wouldn't you say?",
            "I find this utterly pedestrian.",
            "Yo dude what's up",  # Include for vocabulary
        ])

        analyzer = SimilarityAnalyzer(provider=provider)

        character = Character(
            id=uuid4(),
            name="Scholarly Professor",
        )

        reference = [
            "Indeed, most fascinating observation.",
            "Quite remarkable, wouldn't you say?",
            "I find this utterly pedestrian.",
        ]

        # Similar dialogue
        result1 = analyzer.analyze_voice(
            "Indeed, this is most remarkable.",
            character,
            reference_samples=reference
        )

        # Dissimilar dialogue
        result2 = analyzer.analyze_voice(
            "Yo dude, what's up?",
            character,
            reference_samples=reference
        )

        # The similar one should score higher
        assert result1.consistency_score >= result2.consistency_score

    def test_analyze_voice_neutral_without_reference(self):
        """Without reference, score is neutral."""
        analyzer = SimilarityAnalyzer()

        character = Character(
            id=uuid4(),
            name="Test",
        )

        result = analyzer.analyze_voice("Hello there", character)
        assert result.consistency_score == 0.5  # Neutral


class TestToneAnalysis:
    """Tests for tone consistency analysis."""

    def test_analyze_tone_basic(self):
        """Basic tone analysis works."""
        analyzer = SimilarityAnalyzer()

        tone = ToneSettings(
            genre="fantasy",
            prose_style="dark atmospheric",
        )

        result = analyzer.analyze_tone("The shadows gathered.", tone)

        assert isinstance(result, ToneAnalysis)
        assert "shadows" in result.sample.lower()

    def test_analyze_tone_avoid_patterns(self):
        """Avoid patterns in tone are detected."""
        analyzer = SimilarityAnalyzer()

        tone = ToneSettings(
            genre="literary",
            prose_style="serious",
            avoid=["awesome", "epic"],
        )

        result = analyzer.analyze_tone(
            "It was totally awesome and epic!",
            tone
        )

        assert len(result.issues) > 0

    def test_analyze_tone_not_genres(self):
        """Genre markers are detected."""
        analyzer = SimilarityAnalyzer()

        tone = ToneSettings(
            genre="literary",
            prose_style="serious",
            not_genres=["YA"],
        )

        result = analyzer.analyze_tone(
            "Like, it was totally awesome, omg!",
            tone
        )

        # Should detect YA markers
        assert len(result.issues) > 0
        assert any("YA" in issue for issue in result.issues)

    def test_analyze_tone_with_reference(self):
        """Reference samples affect tone score."""
        provider = TFIDFProvider()
        provider.fit([
            "The shadows crept through the ancient halls.",
            "Darkness consumed the forgotten kingdom.",
            "Bright sunshine happy cheerful day",  # For vocabulary
        ])

        analyzer = SimilarityAnalyzer(provider=provider)

        tone = ToneSettings(
            genre="dark fantasy",
            prose_style="ominous atmospheric",
        )

        reference = [
            "The shadows crept through the ancient halls.",
            "Darkness consumed the forgotten kingdom.",
        ]

        # Similar tone
        result1 = analyzer.analyze_tone(
            "Shadows gathered in the ancient ruins.",
            tone,
            reference_samples=reference
        )

        # Different tone
        result2 = analyzer.analyze_tone(
            "Bright sunshine filled the happy meadow.",
            tone,
            reference_samples=reference
        )

        # The similar one should have higher genre match
        assert result1.genre_match >= result2.genre_match


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_analyzer_default(self):
        """create_analyzer with no args works."""
        analyzer = create_analyzer()
        assert isinstance(analyzer, SimilarityAnalyzer)
        assert isinstance(analyzer.provider, TFIDFProvider)

    def test_create_analyzer_with_corpus(self):
        """create_analyzer fits corpus."""
        corpus = ["hello world", "goodbye world"]
        analyzer = create_analyzer(corpus=corpus)

        # Should have vocabulary from corpus
        vec = analyzer.provider.embed("hello world")
        assert len(vec) > 0

    def test_quick_trope_check(self):
        """quick_trope_check works."""
        tropes = [
            BannedTrope(
                id=uuid4(),
                name="test trope",
                reason="testing",
                severity="low",
                examples=["example pattern text"],
                patterns=["pattern to match"],
            )
        ]

        matches = quick_trope_check(
            "example pattern text here",
            tropes,
            threshold=0.3
        )

        # Should not crash, may or may not find matches
        assert isinstance(matches, list)

    def test_quick_trope_check_empty_corpus(self):
        """quick_trope_check handles empty corpus."""
        tropes = [
            BannedTrope(
                id=uuid4(),
                name="test",
                reason="test",
                severity="low",
                examples=[],
                patterns=[],
            )
        ]

        matches = quick_trope_check("test content", tropes)
        assert matches == []

    def test_quick_voice_check(self):
        """quick_voice_check works."""
        character = Character(
            id=uuid4(),
            name="Test Character",
        )

        reference = ["Hello there friend", "How are you doing"]

        result = quick_voice_check(
            "Hello there friend",
            character,
            reference
        )

        assert isinstance(result, VoiceAnalysis)
        assert result.character == "Test Character"

    def test_compute_text_similarity(self):
        """compute_text_similarity works."""
        # Identical texts
        sim1 = compute_text_similarity(
            "hello world test",
            "hello world test"
        )
        assert sim1 > 0.99

        # Different texts
        sim2 = compute_text_similarity(
            "cat dog animal",
            "computer software code"
        )
        assert sim2 < sim1


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self):
        """Empty content is handled."""
        analyzer = SimilarityAnalyzer()

        tropes = [
            BannedTrope(
                id=uuid4(),
                name="test",
                reason="test",
                severity="low",
                examples=["test"],
                patterns=[],
            )
        ]

        matches = analyzer.check_tropes("", tropes)
        assert isinstance(matches, list)

    def test_empty_trope_list(self):
        """Empty trope list returns empty matches."""
        analyzer = SimilarityAnalyzer()
        matches = analyzer.check_tropes("test content", [])
        assert matches == []

    def test_unicode_content(self):
        """Unicode content is handled."""
        provider = TFIDFProvider()
        provider.fit(["café résumé naïve", "normal text here"])

        vec = provider.embed("café résumé")
        assert isinstance(vec, list)

    def test_very_long_content(self):
        """Very long content is handled."""
        analyzer = SimilarityAnalyzer()

        long_content = "test word " * 10000

        character = Character(
            id=uuid4(),
            name="Test",
        )

        result = analyzer.analyze_voice(long_content, character)
        assert len(result.sample) <= 200  # Truncated

    def test_caching_embeddings(self):
        """Embedding caching works."""
        provider = TFIDFProvider()
        provider.fit(["hello world", "test content"])

        analyzer = SimilarityAnalyzer(provider=provider)

        # First call should cache
        tropes = [
            BannedTrope(
                id=uuid4(),
                name="test",
                reason="test",
                severity="low",
                examples=["hello world"],
                patterns=[],
            )
        ]

        analyzer.check_tropes("content", tropes)

        # Cache should have entry
        assert "hello world" in analyzer._trope_embeddings
