"""
Manuscript scanner for auto-populating canon from existing text.

Parses markdown/text files to extract:
- Characters mentioned
- Events/scenes
- Locations
- Timeline markers
- Potential plot threads (foreshadowing, mysteries, setups)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .types import (
    CanonEvent,
    PlotThread,
    ThreadType,
    ThreadStatus,
)


# =============================================================================
# Extraction Patterns
# =============================================================================

# Character name patterns (capitalized words, possibly with titles)
CHARACTER_PATTERNS = [
    r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b(?:\s+said|\s+asked|\s+replied|\s+whispered|\s+shouted)',
    r'(?:said|asked|replied)\s+([A-Z][a-z]+)',
    r'"[^"]+"\s+([A-Z][a-z]+)\s+(?:said|asked|replied)',
    r'\b([A-Z][a-z]+)\'s\s+(?:eyes|voice|hand|face|expression)',
]

# Location patterns
LOCATION_PATTERNS = [
    r'(?:in|at|to|from|inside|outside|near|towards?)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    r'(?:entered|left|arrived at|reached)\s+(?:the\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
    r'(?:The\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+was\s+(?:dark|bright|empty|crowded|quiet|loud)',
]

# Event/action patterns
EVENT_PATTERNS = [
    r'([A-Z][a-z]+)\s+(discovered|found|learned|realized|understood)\s+(?:that\s+)?(.+?)(?:\.|$)',
    r'([A-Z][a-z]+)\s+(killed|attacked|fought|defeated|saved|rescued)\s+(.+?)(?:\.|$)',
    r'([A-Z][a-z]+)\s+(revealed|confessed|admitted|told)\s+(.+?)(?:\.|$)',
    r'([A-Z][a-z]+)\s+(left|arrived|escaped|returned|fled)\s*(?:to|from)?\s*(.+?)(?:\.|$)',
    r'([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)\s+(met|fought|kissed|argued|agreed)\b',
]

# Foreshadowing/mystery patterns (potential plot threads)
THREAD_PATTERNS = [
    (r'(?:mysterious|strange|odd|peculiar)\s+([a-z]+(?:\s+[a-z]+)?)', ThreadType.MYSTERY),
    (r'(?:He|She|They)\s+would\s+(?:later\s+)?(?:learn|discover|find out)', ThreadType.FORESHADOWING),
    (r'(?:Little did|Unknown to)\s+(?:he|she|they|[A-Z][a-z]+)\s+know', ThreadType.FORESHADOWING),
    (r'(?:The|A)\s+([a-z]+)\s+(?:would\s+)?(?:prove|become)\s+(?:important|significant|crucial)', ThreadType.CHEKHOV_GUN),
    (r'(?:kept|hidden|concealed|secret)\s+([a-z]+(?:\s+[a-z]+)?)', ThreadType.MYSTERY),
    (r'(?:promised|swore|vowed)\s+(?:to\s+)?(.+?)(?:\.|,|$)', ThreadType.PROMISE),
    (r'One day,?\s+(.+?)(?:\.|$)', ThreadType.FORESHADOWING),
]

# Timeline markers
TIMELINE_PATTERNS = [
    r'(?:(\d+)\s+)?(?:days?|weeks?|months?|years?)\s+(?:later|earlier|before|after)',
    r'(?:The\s+)?(?:next|following|previous)\s+(?:day|morning|evening|night|week)',
    r'(?:dawn|dusk|midnight|noon|morning|afternoon|evening|night)',
    r'(?:spring|summer|autumn|fall|winter)',
]

# Scene break patterns
SCENE_BREAK_PATTERNS = [
    r'^#{1,3}\s+',  # Markdown headers
    r'^\*{3,}$',    # *** scene break
    r'^-{3,}$',     # --- scene break
    r'^\s*$\n\s*$', # Double blank line
]

# Common non-character words to filter out
NON_CHARACTERS = {
    'the', 'a', 'an', 'and', 'but', 'or', 'for', 'nor', 'yet', 'so',
    'it', 'this', 'that', 'these', 'those', 'he', 'she', 'they', 'we', 'you', 'i',
    'his', 'her', 'their', 'its', 'my', 'your', 'our',
    'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did',
    'will', 'would', 'could', 'should', 'may', 'might', 'must',
    'said', 'asked', 'replied', 'told', 'thought',
    'then', 'now', 'here', 'there', 'when', 'where', 'why', 'how',
    'yes', 'no', 'not', 'just', 'only', 'even', 'also', 'still',
    'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
    'one', 'two', 'three', 'first', 'second', 'last', 'next',
    'new', 'old', 'long', 'little', 'own', 'same', 'right', 'big',
    'chapter', 'part', 'book', 'section', 'page',
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ExtractedCharacter:
    """A character mention extracted from text."""
    name: str
    mentions: int = 1
    contexts: list[str] = field(default_factory=list)
    first_chapter: int = 0
    speaking: bool = False  # Has dialogue


@dataclass
class ExtractedLocation:
    """A location extracted from text."""
    name: str
    mentions: int = 1
    contexts: list[str] = field(default_factory=list)
    first_chapter: int = 0


@dataclass
class ExtractedEvent:
    """An event extracted from text."""
    summary: str
    characters: list[str] = field(default_factory=list)
    location: str | None = None
    chapter: int = 0
    line_number: int = 0
    quote: str | None = None


@dataclass
class ExtractedThread:
    """A potential plot thread extracted from text."""
    description: str
    thread_type: ThreadType
    chapter: int = 0
    line_number: int = 0
    quote: str | None = None
    confidence: float = 0.5  # How confident we are this is a real thread


@dataclass
class ScanResult:
    """Result of scanning a manuscript."""
    characters: dict[str, ExtractedCharacter] = field(default_factory=dict)
    locations: dict[str, ExtractedLocation] = field(default_factory=dict)
    events: list[ExtractedEvent] = field(default_factory=list)
    threads: list[ExtractedThread] = field(default_factory=list)
    chapters: list[int] = field(default_factory=list)
    word_count: int = 0

    def merge(self, other: "ScanResult") -> None:
        """Merge another scan result into this one."""
        # Merge characters
        for name, char in other.characters.items():
            if name in self.characters:
                self.characters[name].mentions += char.mentions
                self.characters[name].contexts.extend(char.contexts)
                self.characters[name].speaking = self.characters[name].speaking or char.speaking
            else:
                self.characters[name] = char

        # Merge locations
        for name, loc in other.locations.items():
            if name in self.locations:
                self.locations[name].mentions += loc.mentions
                self.locations[name].contexts.extend(loc.contexts)
            else:
                self.locations[name] = loc

        # Append events and threads
        self.events.extend(other.events)
        self.threads.extend(other.threads)
        self.chapters.extend(other.chapters)
        self.word_count += other.word_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": {
                name: {
                    "name": char.name,
                    "mentions": char.mentions,
                    "first_chapter": char.first_chapter,
                    "speaking": char.speaking,
                }
                for name, char in self.characters.items()
            },
            "locations": {
                name: {
                    "name": loc.name,
                    "mentions": loc.mentions,
                    "first_chapter": loc.first_chapter,
                }
                for name, loc in self.locations.items()
            },
            "events": [
                {
                    "summary": e.summary,
                    "characters": e.characters,
                    "location": e.location,
                    "chapter": e.chapter,
                }
                for e in self.events
            ],
            "threads": [
                {
                    "description": t.description,
                    "type": t.thread_type.value,
                    "chapter": t.chapter,
                    "confidence": t.confidence,
                }
                for t in self.threads
            ],
            "chapters": self.chapters,
            "word_count": self.word_count,
        }


# =============================================================================
# Scanner Class
# =============================================================================

class ManuscriptScanner:
    """
    Scans manuscript files to extract story elements.

    Usage:
        scanner = ManuscriptScanner()
        result = scanner.scan_file(Path("chapter_01.md"), chapter=1)
        # or
        result = scanner.scan_directory(Path("manuscript/"))
    """

    def __init__(
        self,
        known_characters: list[str] | None = None,
        known_locations: list[str] | None = None,
        custom_patterns: dict[str, list[str]] | None = None,
    ):
        """
        Initialize the scanner.

        Args:
            known_characters: List of known character names (improves detection)
            known_locations: List of known location names (improves detection)
            custom_patterns: Custom regex patterns for domain-specific extraction
        """
        self.known_characters = set(c.lower() for c in (known_characters or []))
        self.known_locations = set(l.lower() for l in (known_locations or []))
        self.custom_patterns = custom_patterns or {}

        # Compile patterns
        self._character_patterns = [re.compile(p, re.MULTILINE) for p in CHARACTER_PATTERNS]
        self._location_patterns = [re.compile(p, re.MULTILINE) for p in LOCATION_PATTERNS]
        self._event_patterns = [re.compile(p, re.MULTILINE | re.IGNORECASE) for p in EVENT_PATTERNS]
        self._thread_patterns = [(re.compile(p, re.MULTILINE | re.IGNORECASE), t) for p, t in THREAD_PATTERNS]
        self._timeline_patterns = [re.compile(p, re.IGNORECASE) for p in TIMELINE_PATTERNS]

    def scan_file(
        self,
        file_path: Path,
        chapter: int | None = None,
    ) -> ScanResult:
        """
        Scan a single manuscript file.

        Args:
            file_path: Path to the file
            chapter: Chapter number (auto-detected from filename if not provided)

        Returns:
            ScanResult with extracted elements
        """
        content = file_path.read_text(errors="ignore")

        # Try to auto-detect chapter number from filename
        if chapter is None:
            chapter = self._detect_chapter(file_path.name)

        return self.scan_content(content, chapter or 0, str(file_path))

    def scan_content(
        self,
        content: str,
        chapter: int = 0,
        source: str = "<unknown>",
    ) -> ScanResult:
        """
        Scan text content for story elements.

        Args:
            content: The text to scan
            chapter: Chapter number
            source: Source identifier for references

        Returns:
            ScanResult with extracted elements
        """
        result = ScanResult()
        result.word_count = len(content.split())

        if chapter > 0:
            result.chapters = [chapter]

        lines = content.split('\n')

        # Extract characters
        self._extract_characters(content, lines, chapter, result)

        # Extract locations
        self._extract_locations(content, lines, chapter, result)

        # Extract events
        self._extract_events(content, lines, chapter, result)

        # Extract potential plot threads
        self._extract_threads(content, lines, chapter, result)

        return result

    def scan_directory(
        self,
        directory: Path,
        pattern: str = "*.md",
        chapter_extractor: Callable[[str], int | None] | None = None,
    ) -> ScanResult:
        """
        Scan all manuscript files in a directory.

        Args:
            directory: Directory to scan
            pattern: Glob pattern for files
            chapter_extractor: Function to extract chapter number from filename

        Returns:
            Merged ScanResult from all files
        """
        result = ScanResult()

        files = sorted(directory.glob(pattern))
        for file_path in files:
            if file_path.is_file():
                chapter = None
                if chapter_extractor:
                    chapter = chapter_extractor(file_path.name)
                else:
                    chapter = self._detect_chapter(file_path.name)

                file_result = self.scan_file(file_path, chapter)
                result.merge(file_result)

        return result

    def _detect_chapter(self, filename: str) -> int | None:
        """Try to detect chapter number from filename."""
        patterns = [
            r'chapter[_\s-]*(\d+)',
            r'ch[_\s-]*(\d+)',
            r'^(\d+)[_\s-]',
            r'(\d+)\.(?:md|txt)$',
        ]

        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return int(match.group(1))

        return None

    def _extract_characters(
        self,
        content: str,
        lines: list[str],
        chapter: int,
        result: ScanResult,
    ) -> None:
        """Extract character mentions."""
        candidates: dict[str, ExtractedCharacter] = {}

        # Look for dialogue attributions
        for pattern in self._character_patterns:
            for match in pattern.finditer(content):
                name = match.group(1).strip()
                name_lower = name.lower()

                if name_lower in NON_CHARACTERS:
                    continue

                if len(name) < 2:
                    continue

                if name_lower not in candidates:
                    candidates[name_lower] = ExtractedCharacter(
                        name=name,
                        first_chapter=chapter,
                    )
                candidates[name_lower].mentions += 1
                candidates[name_lower].speaking = True

        # Also look for known characters
        for known in self.known_characters:
            pattern = re.compile(rf'\b{re.escape(known)}\b', re.IGNORECASE)
            matches = pattern.findall(content)
            if matches:
                if known not in candidates:
                    candidates[known] = ExtractedCharacter(
                        name=matches[0],  # Use first match for capitalization
                        first_chapter=chapter,
                    )
                candidates[known].mentions += len(matches)

        # Filter: require at least 2 mentions or dialogue
        for name, char in candidates.items():
            if char.mentions >= 2 or char.speaking or name in self.known_characters:
                result.characters[name] = char

    def _extract_locations(
        self,
        content: str,
        lines: list[str],
        chapter: int,
        result: ScanResult,
    ) -> None:
        """Extract location mentions."""
        candidates: dict[str, ExtractedLocation] = {}

        for pattern in self._location_patterns:
            for match in pattern.finditer(content):
                name = match.group(1).strip()
                name_lower = name.lower()

                if name_lower in NON_CHARACTERS:
                    continue

                # Skip if it's likely a character
                if name_lower in result.characters:
                    continue

                if len(name) < 2:
                    continue

                if name_lower not in candidates:
                    candidates[name_lower] = ExtractedLocation(
                        name=name,
                        first_chapter=chapter,
                    )
                candidates[name_lower].mentions += 1

                # Add context
                context = match.group(0)[:100]
                candidates[name_lower].contexts.append(context)

        # Also look for known locations
        for known in self.known_locations:
            pattern = re.compile(rf'\b{re.escape(known)}\b', re.IGNORECASE)
            matches = pattern.findall(content)
            if matches:
                if known not in candidates:
                    candidates[known] = ExtractedLocation(
                        name=matches[0],
                        first_chapter=chapter,
                    )
                candidates[known].mentions += len(matches)

        # Filter: require at least 2 mentions or known
        for name, loc in candidates.items():
            if loc.mentions >= 2 or name in self.known_locations:
                result.locations[name] = loc

    def _extract_events(
        self,
        content: str,
        lines: list[str],
        chapter: int,
        result: ScanResult,
    ) -> None:
        """Extract significant events."""
        for i, line in enumerate(lines):
            for pattern in self._event_patterns:
                for match in pattern.finditer(line):
                    groups = match.groups()
                    if len(groups) >= 2:
                        # Build event summary
                        characters = []
                        action = ""
                        detail = ""

                        if len(groups) >= 1 and groups[0]:
                            characters.append(groups[0])
                        if len(groups) >= 2 and groups[1]:
                            action = groups[1]
                        if len(groups) >= 3 and groups[2]:
                            detail = groups[2].strip()
                            # Check if detail is another character
                            if re.match(r'^[A-Z][a-z]+$', detail):
                                characters.append(detail)

                        summary = f"{', '.join(characters)} {action}"
                        if detail and detail not in characters:
                            summary += f" {detail}"

                        event = ExtractedEvent(
                            summary=summary.strip(),
                            characters=characters,
                            chapter=chapter,
                            line_number=i + 1,
                            quote=line.strip()[:200],
                        )
                        result.events.append(event)

    def _extract_threads(
        self,
        content: str,
        lines: list[str],
        chapter: int,
        result: ScanResult,
    ) -> None:
        """Extract potential plot threads."""
        for i, line in enumerate(lines):
            for pattern, thread_type in self._thread_patterns:
                for match in pattern.finditer(line):
                    description = match.group(0).strip()

                    # Get more context
                    context_start = max(0, i - 1)
                    context_end = min(len(lines), i + 2)
                    quote = " ".join(lines[context_start:context_end]).strip()[:300]

                    # Confidence based on pattern type
                    confidence = 0.6
                    if thread_type == ThreadType.CHEKHOV_GUN:
                        confidence = 0.8
                    elif thread_type == ThreadType.FORESHADOWING:
                        confidence = 0.7
                    elif thread_type == ThreadType.MYSTERY:
                        confidence = 0.5

                    thread = ExtractedThread(
                        description=description,
                        thread_type=thread_type,
                        chapter=chapter,
                        line_number=i + 1,
                        quote=quote,
                        confidence=confidence,
                    )
                    result.threads.append(thread)


# =============================================================================
# Integration Functions
# =============================================================================

def scan_manuscript_to_canon(
    manuscript_dir: Path,
    canon,  # Canon instance from .canon
    min_character_mentions: int = 3,
    min_event_confidence: float = 0.5,
    known_characters: list[str] | None = None,
) -> dict[str, Any]:
    """
    Scan a manuscript directory and populate canon.

    Args:
        manuscript_dir: Directory containing manuscript files
        canon: Canon instance to populate
        min_character_mentions: Minimum mentions to add a character
        min_event_confidence: Minimum confidence to add a thread
        known_characters: List of already-known character names

    Returns:
        Summary of what was added
    """
    # Get known characters from canon's bible if available
    if known_characters is None:
        known_characters = []

    scanner = ManuscriptScanner(known_characters=known_characters)
    result = scanner.scan_directory(manuscript_dir)

    summary = {
        "characters_found": len(result.characters),
        "locations_found": len(result.locations),
        "events_found": len(result.events),
        "threads_found": len(result.threads),
        "events_added": 0,
        "threads_added": 0,
    }

    # Add events to canon
    for event in result.events:
        canon.add_event(
            chapter=event.chapter,
            summary=event.summary,
            characters=event.characters,
            location=event.location,
            quote=event.quote,
        )
        summary["events_added"] += 1

    # Add threads to canon (only high-confidence ones)
    for thread in result.threads:
        if thread.confidence >= min_event_confidence:
            canon.add_thread(
                name=thread.description[:50],
                thread_type=thread.thread_type,
                description=thread.description,
                planted_chapter=thread.chapter,
                planted_text=thread.quote,
            )
            summary["threads_added"] += 1

    return summary


def scan_single_chapter(
    content: str,
    chapter: int,
    known_characters: list[str] | None = None,
) -> ScanResult:
    """
    Scan a single chapter's content.

    Convenience function for scanning new content.
    """
    scanner = ManuscriptScanner(known_characters=known_characters)
    return scanner.scan_content(content, chapter)
