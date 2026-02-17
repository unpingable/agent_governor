# SPDX-License-Identifier: Apache-2.0
"""
Tainted Claim Similarity — Recurrence detection for contradicted/retracted claims.

Maintains a fingerprint index of tainted claims. On ingest, compares new claims
against the index and flags near-duplicates. Prevents "laundering" bad claims
through rephrasing.

Implementation: Option A (token-set Jaccard). Swappable to MinHash (Option B)
without API break.

Key invariants:
1. This is a recurrence detector, not semantic truth
2. Normalization is deterministic and boring
3. Fingerprint method/version is explicit in every event payload
4. Scores are always recorded; threshold gates the flag, not the measurement
5. No embeddings. No semantic cosplay.

Pipeline:
    claim marked tainted → normalize → fingerprint → add to index
    new claim ingested   → normalize → fingerprint → check index → emit audit event
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Enums
# =============================================================================


class TaintType(str, Enum):
    """Why a claim was tainted."""

    CONTRADICTED = "contradicted"
    RETRACTED = "retracted"


class FingerprintMethod(str, Enum):
    """Algorithm used to produce the fingerprint."""

    TOKEN_JACCARD = "token_jaccard_v1"


class TaintVerdict(str, Enum):
    """Outcome of a taint similarity check."""

    CLEAR = "clear"           # No match above threshold
    FLAGGED = "flagged"       # Near-duplicate detected
    EXACT = "exact"           # Exact normalized match
    TOO_SHORT = "too_short"   # Below min_tokens, skipped


# =============================================================================
# Normalization
# =============================================================================

_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

# Minimal stopwords — only the most common function words
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "it", "its", "this", "that", "these", "those",
})

MAX_NORMALIZE_LENGTH = 2000


def normalize(text: str) -> str:
    """Deterministic text normalization for fingerprinting."""
    # Unicode normalize
    text = unicodedata.normalize("NFKC", text)
    # Lowercase
    text = text.lower()
    # Strip punctuation
    text = _PUNCTUATION_RE.sub(" ", text)
    # Collapse whitespace
    text = _WHITESPACE_RE.sub(" ", text).strip()
    # Cap length
    if len(text) > MAX_NORMALIZE_LENGTH:
        text = text[:MAX_NORMALIZE_LENGTH]
    return text


def tokenize(text: str, strip_stopwords: bool = False) -> list[str]:
    """Tokenize normalized text."""
    tokens = text.split()
    if strip_stopwords:
        tokens = [t for t in tokens if t not in _STOPWORDS]
    return tokens


# =============================================================================
# Fingerprint
# =============================================================================


@dataclass(frozen=True)
class Fingerprint:
    """Token-set fingerprint of a claim."""

    tokens: frozenset[str]
    text_hash: str  # sha256 of normalized text, for exact-match dedupe
    method: FingerprintMethod = FingerprintMethod.TOKEN_JACCARD

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens": sorted(self.tokens),
            "text_hash": self.text_hash,
            "method": self.method.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Fingerprint:
        return cls(
            tokens=frozenset(d["tokens"]),
            text_hash=d["text_hash"],
            method=FingerprintMethod(d.get("method", "token_jaccard_v1")),
        )


def fingerprint(text: str, strip_stopwords: bool = False) -> Fingerprint:
    """Produce a fingerprint from raw text."""
    norm = normalize(text)
    tokens = tokenize(norm, strip_stopwords=strip_stopwords)
    text_hash = hashlib.sha256(norm.encode()).hexdigest()
    return Fingerprint(
        tokens=frozenset(tokens),
        text_hash=text_hash,
    )


# =============================================================================
# Scoring
# =============================================================================


def score(fp1: Fingerprint, fp2: Fingerprint) -> float:
    """Token-set Jaccard similarity between two fingerprints."""
    union = fp1.tokens | fp2.tokens
    if not union:
        return 0.0
    return len(fp1.tokens & fp2.tokens) / len(union)


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class TaintedClaim:
    """A tainted claim in the index."""

    claim_id: str
    taint_type: TaintType
    fingerprint: Fingerprint
    normalized_text: str
    timestamp: str  # ISO format
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "taint_type": self.taint_type.value,
            "fingerprint": self.fingerprint.to_dict(),
            "normalized_text": self.normalized_text,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaintedClaim:
        return cls(
            claim_id=d["claim_id"],
            taint_type=TaintType(d["taint_type"]),
            fingerprint=Fingerprint.from_dict(d["fingerprint"]),
            normalized_text=d["normalized_text"],
            timestamp=d["timestamp"],
            metadata=d.get("metadata", {}),
        )


@dataclass
class TaintMatch:
    """A match against a tainted claim."""

    tainted_claim_id: str
    taint_type: TaintType
    similarity: float
    method: FingerprintMethod
    threshold: float
    exact: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tainted_claim_id": self.tainted_claim_id,
            "taint_type": self.taint_type.value,
            "similarity": self.similarity,
            "method": self.method.value,
            "threshold": self.threshold,
            "exact": self.exact,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaintMatch:
        return cls(
            tainted_claim_id=d["tainted_claim_id"],
            taint_type=TaintType(d["taint_type"]),
            similarity=d["similarity"],
            method=FingerprintMethod(d.get("method", "token_jaccard_v1")),
            threshold=d["threshold"],
            exact=d.get("exact", False),
        )


@dataclass
class TaintCheckResult:
    """Result of checking a claim against the taint index."""

    verdict: TaintVerdict
    matches: list[TaintMatch] = field(default_factory=list)
    best_score: float = 0.0
    checked_against: int = 0
    input_token_count: int = 0

    @property
    def is_flagged(self) -> bool:
        return self.verdict in (TaintVerdict.FLAGGED, TaintVerdict.EXACT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "matches": [m.to_dict() for m in self.matches],
            "best_score": self.best_score,
            "checked_against": self.checked_against,
            "input_token_count": self.input_token_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaintCheckResult:
        return cls(
            verdict=TaintVerdict(d["verdict"]),
            matches=[TaintMatch.from_dict(m) for m in d.get("matches", [])],
            best_score=d.get("best_score", 0.0),
            checked_against=d.get("checked_against", 0),
            input_token_count=d.get("input_token_count", 0),
        )


@dataclass
class TaintEvent:
    """Audit event emitted on taint similarity hit."""

    event_type: str = "tainted_similarity_hit"
    new_claim_id: str = ""
    matched_claim_id: str = ""
    similarity: float = 0.0
    method: FingerprintMethod = FingerprintMethod.TOKEN_JACCARD
    threshold: float = 0.0
    taint_type: TaintType = TaintType.CONTRADICTED
    timestamp: str = ""
    exact: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "new_claim_id": self.new_claim_id,
            "matched_claim_id": self.matched_claim_id,
            "similarity": self.similarity,
            "method": self.method.value,
            "threshold": self.threshold,
            "taint_type": self.taint_type.value,
            "timestamp": self.timestamp,
            "exact": self.exact,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaintEvent:
        return cls(
            event_type=d.get("event_type", "tainted_similarity_hit"),
            new_claim_id=d.get("new_claim_id", ""),
            matched_claim_id=d.get("matched_claim_id", ""),
            similarity=d.get("similarity", 0.0),
            method=FingerprintMethod(d.get("method", "token_jaccard_v1")),
            threshold=d.get("threshold", 0.0),
            taint_type=TaintType(d.get("taint_type", "contradicted")),
            timestamp=d.get("timestamp", ""),
            exact=d.get("exact", False),
        )


@dataclass
class TaintConfig:
    """Configuration for the taint index."""

    jaccard_threshold: float = 0.8
    min_tokens: int = 6
    strip_stopwords: bool = False
    record_below_threshold: bool = True
    below_threshold_min: float = 0.5  # Only record if above this floor

    def to_dict(self) -> dict[str, Any]:
        return {
            "jaccard_threshold": self.jaccard_threshold,
            "min_tokens": self.min_tokens,
            "strip_stopwords": self.strip_stopwords,
            "record_below_threshold": self.record_below_threshold,
            "below_threshold_min": self.below_threshold_min,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaintConfig:
        return cls(
            jaccard_threshold=d.get("jaccard_threshold", 0.8),
            min_tokens=d.get("min_tokens", 6),
            strip_stopwords=d.get("strip_stopwords", False),
            record_below_threshold=d.get("record_below_threshold", True),
            below_threshold_min=d.get("below_threshold_min", 0.5),
        )


# =============================================================================
# TaintIndex
# =============================================================================

_TAINT_INDEX_FILE = "taint_index.json"
_TAINT_EVENTS_FILE = "taint_events.json"


class TaintIndex:
    """
    Fingerprint index of tainted claims with candidate retrieval.

    Uses an inverted index on tokens for fast candidate lookup (Option A).
    Swappable to LSH buckets (Option B) without API change.
    """

    def __init__(
        self,
        config: TaintConfig | None = None,
        governor_dir: Path | None = None,
    ) -> None:
        self.config = config or TaintConfig()
        self._governor_dir = governor_dir
        self._claims: dict[str, TaintedClaim] = {}
        self._inverted: dict[str, set[str]] = {}  # token → set of claim_ids
        self._hash_index: dict[str, str] = {}  # text_hash → claim_id (exact match)
        self._events: list[TaintEvent] = []

        if governor_dir is not None:
            self._load()

    # ---- Core API ----

    def add_tainted(
        self,
        claim_id: str,
        text: str,
        taint_type: TaintType,
        ts: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaintedClaim:
        """Add a claim to the taint index."""
        fp = fingerprint(text, strip_stopwords=self.config.strip_stopwords)
        norm = normalize(text)
        if ts is None:
            ts = datetime.now(timezone.utc).isoformat()

        claim = TaintedClaim(
            claim_id=claim_id,
            taint_type=taint_type,
            fingerprint=fp,
            normalized_text=norm,
            timestamp=ts,
            metadata=metadata or {},
        )

        self._claims[claim_id] = claim
        self._hash_index[fp.text_hash] = claim_id

        # Update inverted index
        for token in fp.tokens:
            if token not in self._inverted:
                self._inverted[token] = set()
            self._inverted[token].add(claim_id)

        if self._governor_dir:
            self._save()

        return claim

    def remove_tainted(self, claim_id: str) -> bool:
        """Remove a claim from the taint index."""
        if claim_id not in self._claims:
            return False

        claim = self._claims.pop(claim_id)
        self._hash_index.pop(claim.fingerprint.text_hash, None)

        for token in claim.fingerprint.tokens:
            if token in self._inverted:
                self._inverted[token].discard(claim_id)
                if not self._inverted[token]:
                    del self._inverted[token]

        if self._governor_dir:
            self._save()

        return True

    def check(self, text: str, new_claim_id: str = "") -> TaintCheckResult:
        """Check text against the taint index."""
        fp = fingerprint(text, strip_stopwords=self.config.strip_stopwords)
        token_count = len(fp.tokens)

        # Too short — bail
        if token_count < self.config.min_tokens:
            return TaintCheckResult(
                verdict=TaintVerdict.TOO_SHORT,
                input_token_count=token_count,
            )

        # Exact match check first
        if fp.text_hash in self._hash_index:
            matched_id = self._hash_index[fp.text_hash]
            matched = self._claims[matched_id]
            match = TaintMatch(
                tainted_claim_id=matched_id,
                taint_type=matched.taint_type,
                similarity=1.0,
                method=FingerprintMethod.TOKEN_JACCARD,
                threshold=self.config.jaccard_threshold,
                exact=True,
            )
            self._emit_event(new_claim_id, match)
            return TaintCheckResult(
                verdict=TaintVerdict.EXACT,
                matches=[match],
                best_score=1.0,
                checked_against=len(self._claims),
                input_token_count=token_count,
            )

        # Candidate retrieval via inverted index
        candidates = self._get_candidates(fp)

        matches: list[TaintMatch] = []
        best = 0.0

        for cid in candidates:
            candidate = self._claims[cid]
            sim = score(fp, candidate.fingerprint)
            if sim > best:
                best = sim

            if sim >= self.config.jaccard_threshold:
                match = TaintMatch(
                    tainted_claim_id=cid,
                    taint_type=candidate.taint_type,
                    similarity=sim,
                    method=FingerprintMethod.TOKEN_JACCARD,
                    threshold=self.config.jaccard_threshold,
                )
                matches.append(match)
            elif (
                self.config.record_below_threshold
                and sim >= self.config.below_threshold_min
            ):
                # Record near-misses for debugging
                match = TaintMatch(
                    tainted_claim_id=cid,
                    taint_type=candidate.taint_type,
                    similarity=sim,
                    method=FingerprintMethod.TOKEN_JACCARD,
                    threshold=self.config.jaccard_threshold,
                )
                matches.append(match)

        # Sort by similarity descending
        matches.sort(key=lambda m: m.similarity, reverse=True)

        # Determine verdict
        flagged_matches = [m for m in matches if m.similarity >= self.config.jaccard_threshold]
        if flagged_matches:
            verdict = TaintVerdict.FLAGGED
            for m in flagged_matches:
                self._emit_event(new_claim_id, m)
        else:
            verdict = TaintVerdict.CLEAR

        return TaintCheckResult(
            verdict=verdict,
            matches=matches,
            best_score=best,
            checked_against=len(candidates),
            input_token_count=token_count,
        )

    # ---- Query API ----

    def get_tainted(self, claim_id: str) -> TaintedClaim | None:
        """Get a tainted claim by ID."""
        return self._claims.get(claim_id)

    def list_tainted(self) -> list[TaintedClaim]:
        """List all tainted claims."""
        return list(self._claims.values())

    def count(self) -> int:
        """Number of tainted claims in the index."""
        return len(self._claims)

    def events(self) -> list[TaintEvent]:
        """Get all recorded taint events."""
        return list(self._events)

    def clear_events(self) -> int:
        """Clear event history, return count cleared."""
        count = len(self._events)
        self._events.clear()
        if self._governor_dir:
            self._save_events()
        return count

    def stats(self) -> dict[str, Any]:
        """Index statistics."""
        by_type = {}
        for c in self._claims.values():
            by_type[c.taint_type.value] = by_type.get(c.taint_type.value, 0) + 1
        return {
            "total_tainted": len(self._claims),
            "by_type": by_type,
            "index_tokens": len(self._inverted),
            "total_events": len(self._events),
            "flagged_events": sum(1 for e in self._events if e.similarity >= e.threshold),
        }

    # ---- Internal ----

    def _get_candidates(self, fp: Fingerprint) -> set[str]:
        """Retrieve candidate claim IDs via inverted index."""
        candidates: set[str] = set()
        for token in fp.tokens:
            if token in self._inverted:
                candidates.update(self._inverted[token])
        return candidates

    def _emit_event(self, new_claim_id: str, match: TaintMatch) -> None:
        """Record an audit event for a taint match."""
        event = TaintEvent(
            new_claim_id=new_claim_id,
            matched_claim_id=match.tainted_claim_id,
            similarity=match.similarity,
            method=match.method,
            threshold=match.threshold,
            taint_type=match.taint_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            exact=match.exact,
        )
        self._events.append(event)
        if self._governor_dir:
            self._save_events()

    # ---- Persistence ----

    def _load(self) -> None:
        if self._governor_dir is None:
            return
        # Load index
        path = self._governor_dir / _TAINT_INDEX_FILE
        if path.exists():
            data = json.loads(path.read_text())
            for cid, cd in data.get("claims", {}).items():
                claim = TaintedClaim.from_dict(cd)
                self._claims[cid] = claim
                self._hash_index[claim.fingerprint.text_hash] = cid
                for token in claim.fingerprint.tokens:
                    if token not in self._inverted:
                        self._inverted[token] = set()
                    self._inverted[token].add(cid)
        # Load events
        events_path = self._governor_dir / _TAINT_EVENTS_FILE
        if events_path.exists():
            data = json.loads(events_path.read_text())
            self._events = [TaintEvent.from_dict(e) for e in data]

    def _save(self) -> None:
        if self._governor_dir is None:
            return
        path = self._governor_dir / _TAINT_INDEX_FILE
        data = {
            "config": self.config.to_dict(),
            "claims": {cid: c.to_dict() for cid, c in self._claims.items()},
        }
        path.write_text(json.dumps(data, indent=2))

    def _save_events(self) -> None:
        if self._governor_dir is None:
            return
        path = self._governor_dir / _TAINT_EVENTS_FILE
        path.write_text(json.dumps([e.to_dict() for e in self._events], indent=2))

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "claims": {cid: c.to_dict() for cid, c in self._claims.items()},
            "events": [e.to_dict() for e in self._events],
        }

    @classmethod
    def from_dict(
        cls,
        d: dict[str, Any],
        governor_dir: Path | None = None,
    ) -> TaintIndex:
        config = TaintConfig.from_dict(d.get("config", {}))
        index = cls(config=config, governor_dir=None)
        index._governor_dir = governor_dir
        for cid, cd in d.get("claims", {}).items():
            claim = TaintedClaim.from_dict(cd)
            index._claims[cid] = claim
            index._hash_index[claim.fingerprint.text_hash] = cid
            for token in claim.fingerprint.tokens:
                if token not in index._inverted:
                    index._inverted[token] = set()
                index._inverted[token].add(cid)
        index._events = [TaintEvent.from_dict(e) for e in d.get("events", [])]
        return index


# =============================================================================
# Convenience functions
# =============================================================================


def create_taint_index(
    governor_dir: Path | None = None,
    config: TaintConfig | None = None,
) -> TaintIndex:
    """Create a taint index, optionally backed by a governor directory."""
    return TaintIndex(config=config, governor_dir=governor_dir)


def check_claim(
    index: TaintIndex,
    text: str,
    claim_id: str = "",
) -> TaintCheckResult:
    """Check a claim against a taint index."""
    return index.check(text, new_claim_id=claim_id)


def taint_claim(
    index: TaintIndex,
    claim_id: str,
    text: str,
    taint_type: TaintType,
) -> TaintedClaim:
    """Add a claim to a taint index."""
    return index.add_tainted(claim_id, text, taint_type)
