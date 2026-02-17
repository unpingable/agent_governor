# SPDX-License-Identifier: Apache-2.0
"""Tests for manuscript scanner."""

import pytest
from pathlib import Path
import tempfile
import os

from fiction_governor.manuscript import (
    ManuscriptScanner,
    ScanResult,
    ExtractedCharacter,
    ExtractedLocation,
    ExtractedEvent,
    ExtractedThread,
    scan_single_chapter,
)
from fiction_governor.types import ThreadType


# =============================================================================
# Test Data
# =============================================================================

SAMPLE_CHAPTER = """
# Chapter 1: The Beginning

John walked into the tavern, his eyes scanning the dark interior.

"Looking for someone?" asked Sarah, sliding a drink across the bar.

"Just an old friend," John replied.

The tavern was dark and crowded. Outside, the city of Westport bustled with merchants.

John discovered that Sarah had been hiding the truth. She knew about the mysterious letter
that Marcus had sent before his disappearance.

Little did John know, the letter would prove important later.

"I promise to find Marcus," John said. "No matter what it takes."

Sarah nodded. "Be careful. The Dark Forest is dangerous at night."
"""

CHAPTER_WITH_EVENTS = """
Marcus discovered that the artifact was fake.

Elena killed the assassin before he could strike.

John revealed his true identity to Sarah.

Elena and Marcus met in the abandoned chapel.

The Queen arrived at the castle gates.
"""

CHAPTER_WITH_THREADS = """
The mysterious stranger watched from the shadows.

Little did Elena know, the decision would haunt her forever.

The old sword would prove crucial in the final battle.

She kept the secret hidden deep within her heart.

He promised to return before winter.

One day, they would understand why he left.
"""


# =============================================================================
# ScanResult Tests
# =============================================================================

class TestScanResult:
    """Tests for ScanResult dataclass."""

    def test_empty_result(self):
        """Empty result has sensible defaults."""
        result = ScanResult()
        assert result.characters == {}
        assert result.locations == {}
        assert result.events == []
        assert result.threads == []
        assert result.chapters == []
        assert result.word_count == 0

    def test_merge_characters(self):
        """Merging results combines character mentions."""
        result1 = ScanResult()
        result1.characters["john"] = ExtractedCharacter(
            name="John", mentions=3, speaking=True
        )

        result2 = ScanResult()
        result2.characters["john"] = ExtractedCharacter(
            name="John", mentions=2, speaking=False
        )
        result2.characters["sarah"] = ExtractedCharacter(
            name="Sarah", mentions=1
        )

        result1.merge(result2)

        assert result1.characters["john"].mentions == 5
        assert result1.characters["john"].speaking is True  # Preserved
        assert "sarah" in result1.characters

    def test_merge_locations(self):
        """Merging results combines location mentions."""
        result1 = ScanResult()
        result1.locations["tavern"] = ExtractedLocation(
            name="Tavern", mentions=2
        )

        result2 = ScanResult()
        result2.locations["tavern"] = ExtractedLocation(
            name="Tavern", mentions=1
        )
        result2.locations["castle"] = ExtractedLocation(
            name="Castle", mentions=1
        )

        result1.merge(result2)

        assert result1.locations["tavern"].mentions == 3
        assert "castle" in result1.locations

    def test_merge_events_and_threads(self):
        """Merging appends events and threads."""
        result1 = ScanResult()
        result1.events = [ExtractedEvent(summary="Event 1")]
        result1.threads = [ExtractedThread(
            description="Thread 1",
            thread_type=ThreadType.MYSTERY
        )]

        result2 = ScanResult()
        result2.events = [ExtractedEvent(summary="Event 2")]
        result2.threads = [ExtractedThread(
            description="Thread 2",
            thread_type=ThreadType.FORESHADOWING
        )]

        result1.merge(result2)

        assert len(result1.events) == 2
        assert len(result1.threads) == 2

    def test_merge_chapters_and_word_count(self):
        """Merging combines chapters and word counts."""
        result1 = ScanResult()
        result1.chapters = [1]
        result1.word_count = 100

        result2 = ScanResult()
        result2.chapters = [2]
        result2.word_count = 150

        result1.merge(result2)

        assert result1.chapters == [1, 2]
        assert result1.word_count == 250

    def test_to_dict(self):
        """Conversion to dict produces serializable output."""
        result = ScanResult()
        result.characters["john"] = ExtractedCharacter(
            name="John", mentions=3, first_chapter=1, speaking=True
        )
        result.locations["tavern"] = ExtractedLocation(
            name="Tavern", mentions=2, first_chapter=1
        )
        result.events = [ExtractedEvent(
            summary="John arrived",
            characters=["John"],
            chapter=1
        )]
        result.threads = [ExtractedThread(
            description="mysterious letter",
            thread_type=ThreadType.MYSTERY,
            chapter=1,
            confidence=0.6
        )]
        result.chapters = [1]
        result.word_count = 500

        d = result.to_dict()

        assert d["characters"]["john"]["name"] == "John"
        assert d["characters"]["john"]["mentions"] == 3
        assert d["locations"]["tavern"]["name"] == "Tavern"
        assert len(d["events"]) == 1
        assert d["events"][0]["summary"] == "John arrived"
        assert len(d["threads"]) == 1
        assert d["threads"][0]["type"] == "mystery"
        assert d["word_count"] == 500


# =============================================================================
# ManuscriptScanner Tests
# =============================================================================

class TestManuscriptScanner:
    """Tests for ManuscriptScanner class."""

    def test_init_defaults(self):
        """Scanner initializes with empty defaults."""
        scanner = ManuscriptScanner()
        assert scanner.known_characters == set()
        assert scanner.known_locations == set()

    def test_init_with_known_characters(self):
        """Scanner accepts known character list."""
        scanner = ManuscriptScanner(known_characters=["John", "Sarah"])
        assert "john" in scanner.known_characters
        assert "sarah" in scanner.known_characters

    def test_init_with_known_locations(self):
        """Scanner accepts known location list."""
        scanner = ManuscriptScanner(known_locations=["Westport", "Castle"])
        assert "westport" in scanner.known_locations
        assert "castle" in scanner.known_locations

    def test_scan_content_basic(self):
        """Basic content scanning works."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(SAMPLE_CHAPTER, chapter=1)

        # Should find characters with dialogue
        assert "john" in result.characters
        assert "sarah" in result.characters
        assert result.characters["john"].speaking
        assert result.characters["sarah"].speaking

    def test_scan_content_word_count(self):
        """Word count is calculated."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(SAMPLE_CHAPTER, chapter=1)
        assert result.word_count > 0

    def test_scan_content_chapter_tracked(self):
        """Chapter number is tracked."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(SAMPLE_CHAPTER, chapter=5)
        assert 5 in result.chapters

    def test_extract_characters_dialogue(self):
        """Characters with dialogue are extracted."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            '"Hello," said Marcus.\n"Goodbye," John replied.',
            chapter=1
        )
        assert "marcus" in result.characters
        assert "john" in result.characters

    def test_extract_characters_possessive(self):
        """Characters referenced possessively are extracted."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            "Elena's eyes widened. Elena's voice trembled. Elena walked away.",
            chapter=1
        )
        assert "elena" in result.characters

    def test_extract_characters_known(self):
        """Known characters are found even without dialogue."""
        scanner = ManuscriptScanner(known_characters=["Marcus"])
        result = scanner.scan_content(
            "Marcus stood in the corner. Marcus was silent.",
            chapter=1
        )
        assert "marcus" in result.characters

    def test_filter_non_characters(self):
        """Common words are filtered out as characters."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            'The said hello. Chapter walked by.',
            chapter=1
        )
        assert "the" not in result.characters
        assert "chapter" not in result.characters

    def test_extract_events(self):
        """Significant events are extracted."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(CHAPTER_WITH_EVENTS, chapter=1)

        assert len(result.events) > 0
        summaries = [e.summary for e in result.events]
        # Should capture discovery, killing, revealing events
        assert any("Marcus" in s and "discovered" in s.lower() for s in summaries)

    def test_extract_events_characters(self):
        """Events track involved characters."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            "Elena killed the assassin before he could strike.",
            chapter=1
        )

        assert len(result.events) > 0
        assert "Elena" in result.events[0].characters

    def test_extract_threads_mystery(self):
        """Mystery threads are detected."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            "The mysterious stranger watched from the shadows.",
            chapter=1
        )

        threads_by_type = {t.thread_type for t in result.threads}
        assert ThreadType.MYSTERY in threads_by_type

    def test_extract_threads_foreshadowing(self):
        """Foreshadowing threads are detected."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            "Little did Elena know, the decision would haunt her forever.",
            chapter=1
        )

        threads_by_type = {t.thread_type for t in result.threads}
        assert ThreadType.FORESHADOWING in threads_by_type

    def test_extract_threads_chekhov_gun(self):
        """Chekhov's gun threads are detected."""
        scanner = ManuscriptScanner()
        # Pattern matches: The/A [word] would prove/become important/significant/crucial
        result = scanner.scan_content(
            "The sword would prove important in the final battle.",
            chapter=1
        )

        threads_by_type = {t.thread_type for t in result.threads}
        assert ThreadType.CHEKHOV_GUN in threads_by_type

    def test_extract_threads_promise(self):
        """Promise threads are detected."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            "He promised to return before winter.",
            chapter=1
        )

        threads_by_type = {t.thread_type for t in result.threads}
        assert ThreadType.PROMISE in threads_by_type

    def test_thread_confidence_levels(self):
        """Different thread types have different confidence levels."""
        scanner = ManuscriptScanner()

        # Chekhov's gun - high confidence
        result1 = scanner.scan_content(
            "The sword would prove important later.",
            chapter=1
        )
        chekhov_threads = [t for t in result1.threads if t.thread_type == ThreadType.CHEKHOV_GUN]
        if chekhov_threads:
            assert chekhov_threads[0].confidence >= 0.7

        # Mystery - lower confidence
        result2 = scanner.scan_content(
            "A mysterious noise echoed.",
            chapter=1
        )
        mystery_threads = [t for t in result2.threads if t.thread_type == ThreadType.MYSTERY]
        if mystery_threads:
            assert mystery_threads[0].confidence <= 0.6

    def test_detect_chapter_from_filename(self):
        """Chapter detection from filename works."""
        scanner = ManuscriptScanner()

        assert scanner._detect_chapter("chapter_01.md") == 1
        assert scanner._detect_chapter("chapter-5.md") == 5
        assert scanner._detect_chapter("ch_12.txt") == 12
        assert scanner._detect_chapter("03_the_beginning.md") == 3
        assert scanner._detect_chapter("random.md") is None


# =============================================================================
# File Scanning Tests
# =============================================================================

class TestFileScanningIntegration:
    """Tests for file-based scanning."""

    def test_scan_file(self, tmp_path):
        """Scanning a file works."""
        chapter_file = tmp_path / "chapter_01.md"
        chapter_file.write_text(SAMPLE_CHAPTER)

        scanner = ManuscriptScanner()
        result = scanner.scan_file(chapter_file)

        assert result.word_count > 0
        assert 1 in result.chapters  # Auto-detected from filename
        assert len(result.characters) > 0

    def test_scan_file_explicit_chapter(self, tmp_path):
        """Explicit chapter number overrides detection."""
        chapter_file = tmp_path / "draft.md"
        chapter_file.write_text(SAMPLE_CHAPTER)

        scanner = ManuscriptScanner()
        result = scanner.scan_file(chapter_file, chapter=42)

        assert 42 in result.chapters

    def test_scan_directory(self, tmp_path):
        """Scanning a directory merges all files."""
        (tmp_path / "chapter_01.md").write_text('"Hello," said John.')
        (tmp_path / "chapter_02.md").write_text('"Goodbye," said Sarah.')

        scanner = ManuscriptScanner()
        result = scanner.scan_directory(tmp_path)

        assert len(result.chapters) == 2
        assert "john" in result.characters
        assert "sarah" in result.characters

    def test_scan_directory_with_pattern(self, tmp_path):
        """Directory scan respects glob pattern."""
        (tmp_path / "chapter_01.md").write_text('"Hello," said John.')
        (tmp_path / "notes.txt").write_text('"Ignore," said Nobody.')

        scanner = ManuscriptScanner()
        result = scanner.scan_directory(tmp_path, pattern="*.md")

        assert "john" in result.characters
        # Nobody should not be found if .txt was ignored
        assert "nobody" not in result.characters

    def test_scan_directory_custom_chapter_extractor(self, tmp_path):
        """Custom chapter extractor works."""
        (tmp_path / "part_one.md").write_text('"Hello," said John.')
        (tmp_path / "part_two.md").write_text('"Goodbye," said Sarah.')

        def extract_part(filename: str) -> int | None:
            if "one" in filename:
                return 1
            elif "two" in filename:
                return 2
            return None

        scanner = ManuscriptScanner()
        result = scanner.scan_directory(
            tmp_path,
            pattern="*.md",
            chapter_extractor=extract_part
        )

        assert 1 in result.chapters
        assert 2 in result.chapters


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_scan_single_chapter(self):
        """scan_single_chapter works."""
        result = scan_single_chapter(SAMPLE_CHAPTER, chapter=1)

        assert result.word_count > 0
        assert 1 in result.chapters
        assert len(result.characters) > 0

    def test_scan_single_chapter_with_known_characters(self):
        """scan_single_chapter accepts known characters."""
        result = scan_single_chapter(
            "The mysterious Marcus lurked nearby. Marcus watched.",
            chapter=1,
            known_characters=["Marcus"]
        )

        assert "marcus" in result.characters


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_content(self):
        """Empty content produces empty result."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content("", chapter=1)

        assert result.word_count == 0
        assert len(result.characters) == 0
        assert len(result.events) == 0

    def test_no_dialogue_content(self):
        """Content without dialogue still works."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            "The sun rose over the mountains. Birds sang in the trees.",
            chapter=1
        )

        # Should work, just not find speaking characters
        assert result.word_count > 0

    def test_unicode_content(self):
        """Unicode content is handled."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            '"Bonjour," said André. "Comment ça va?"',
            chapter=1
        )

        # Should at least not crash
        assert result.word_count > 0

    def test_very_long_lines(self):
        """Very long lines are handled."""
        scanner = ManuscriptScanner()
        long_line = '"Hello," said John. ' * 1000
        result = scanner.scan_content(long_line, chapter=1)

        assert "john" in result.characters

    def test_special_characters_in_names(self):
        """Names with special formatting are handled."""
        scanner = ManuscriptScanner()
        result = scanner.scan_content(
            '"Yes," said Mary-Jane. O\'Brien nodded.',
            chapter=1
        )

        # Should handle hyphenated and apostrophe names
        assert result.word_count > 0
