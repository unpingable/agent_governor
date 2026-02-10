"""
Commitment Transport — Representational Invariance Under Compression.

Extracts structured obligations (MUST/SHOULD/MAY/MUST_NOT) from text,
classifies how each obligation survives lossy transforms (compaction,
summarization, bridge compilation), and gates on the result.

Spec: COMMITMENT_TRANSPORT_SPEC.md (Layer 2, Item #5 of AG2 build order)

Core insight: Temporal coherence (Δt) is orthogonal to representational
coherence (ΔR). A system can be internally consistent while losing critical
constraints under transformation. The governor must enforce both.

Key properties:
  - Pure extraction: regex + heuristic, not LLM-based
  - Monotonic gating: transport failures only tighten, never loosen
  - Receipt-producing: every validation produces a content-addressed ShearReport
  - No false completeness: misses implicit commitments, catches explicit ones
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Modality(str, Enum):
    """RFC 2119-style obligation modality."""

    MUST = "must"
    """Hard obligation — violation blocks."""

    SHOULD = "should"
    """Soft preference — violation warns."""

    MAY = "may"
    """Permission — loss is informational."""

    MUST_NOT = "must_not"
    """Hard prohibition — violation blocks."""


class CommitmentKind(str, Enum):
    """Category of semantic obligation."""

    INVARIANT = "invariant"
    """'X must always be true' — persistent property."""

    PROHIBITION = "prohibition"
    """'Never do X' — negative constraint."""

    BOUNDARY = "boundary"
    """'Only applies to X' — scope restriction."""

    DEPENDENCY = "dependency"
    """'If X then Y' — conditional coupling."""

    EXCLUSION = "exclusion"
    """'X and Y are mutually exclusive' — disjunction."""

    REQUIREMENT = "requirement"
    """'X is required' — positive obligation."""


class TransportOutcome(str, Enum):
    """How a commitment survived a lossy transform."""

    PRESERVED = "preserved"
    """Same modality, same content, same scope."""

    WEAKENED = "weakened"
    """Modality softened (MUST→SHOULD), scope widened, or exceptions added."""

    DROPPED = "dropped"
    """No corresponding commitment in output."""

    CONTRADICTED = "contradicted"
    """Output contains negation or exception that nullifies."""


# ---------------------------------------------------------------------------
# Modality weights (for shear calculation)
# ---------------------------------------------------------------------------

MODALITY_WEIGHT: dict[Modality, float] = {
    Modality.MUST: 1.0,
    Modality.MUST_NOT: 1.0,
    Modality.SHOULD: 0.7,
    Modality.MAY: 0.3,
}

# Shear contribution per outcome
OUTCOME_SHEAR: dict[TransportOutcome, float] = {
    TransportOutcome.PRESERVED: 0.0,
    TransportOutcome.WEAKENED: 0.5,
    TransportOutcome.DROPPED: 1.0,
    TransportOutcome.CONTRADICTED: 1.0,
}


# ---------------------------------------------------------------------------
# Extraction patterns
# ---------------------------------------------------------------------------

# Modality markers: word/phrase → Modality
_MUST_PATTERNS = [
    r"\bmust\b(?!\s+not\b)",
    r"\bshall\b(?!\s+not\b)",
    r"\brequired\s+to\b",
    r"\bis\s+required\b",
    r"\bare\s+required\b",
    r"\balways\b",
    r"\bmandatory\b",
    r"\bnon-negotiable\b",
]

_MUST_NOT_PATTERNS = [
    r"\bmust\s+not\b",
    r"\bshall\s+not\b",
    r"\bnever\b",
    r"\bforbidden\b",
    r"\bprohibited\b",
    r"\bunder\s+no\s+circumstances\b",
    r"\bdo\s+not\b",
    r"\bdon'?t\b",
    r"\bcannot\b",
    r"\bmust\s+never\b",
]

_SHOULD_PATTERNS = [
    r"\bshould\b(?!\s+not\b)",
    r"\brecommended\b",
    r"\bprefer(?:ably|red)?\b",
    r"\bideal(?:ly)?\b",
    r"\bexpected\s+to\b",
    r"\bought\s+to\b",
]

_MAY_PATTERNS = [
    r"\bmay\b",
    r"\boptional(?:ly)?\b",
    r"\bcan\b",
    r"\ballowed\s+to\b",
    r"\bpermitted\b",
]

# Kind markers: patterns that indicate commitment kind
_KIND_PATTERNS: dict[CommitmentKind, list[str]] = {
    CommitmentKind.INVARIANT: [
        r"\balways\b",
        r"\bat\s+all\s+times\b",
        r"\binvariant\b",
        r"\bconsistently\b",
        r"\bpersist(?:s|ent)?\b",
    ],
    CommitmentKind.PROHIBITION: [
        r"\bnever\b",
        r"\bforbidden\b",
        r"\bprohibited\b",
        r"\bnot\s+allowed\b",
        r"\bmust\s+not\b",
        r"\bshall\s+not\b",
        r"\bdo\s+not\b",
    ],
    CommitmentKind.BOUNDARY: [
        r"\bonly\s+(?:applies?\s+to|within|for|in)\b",
        r"\blimited\s+to\b",
        r"\brestricted\s+to\b",
        r"\bexclusively\b",
        r"\bscoped?\s+to\b",
    ],
    CommitmentKind.DEPENDENCY: [
        r"\bif\s+.+\s+then\b",
        r"\bwhen(?:ever)?\b.+\bmust\b",
        r"\bunless\b",
        r"\bprovided\s+that\b",
        r"\bdepends?\s+on\b",
        r"\brequires?\b.+\bbefore\b",
    ],
    CommitmentKind.EXCLUSION: [
        r"\bmutually\s+exclusive\b",
        r"\beither\b.+\bor\b",
        r"\bcannot\s+both\b",
        r"\bincompatible\b",
        r"\bconflicts?\s+with\b",
    ],
    CommitmentKind.REQUIREMENT: [
        r"\brequired\b",
        r"\bmust\s+have\b",
        r"\bmandatory\b",
        r"\bessential\b",
        r"\bneed(?:s|ed)?\b",
    ],
}

# Scope markers: phrases that indicate scope restrictions
_SCOPE_PATTERNS = [
    (re.compile(r"\bonly\s+(?:applies?\s+to|for|in|within)\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE), 1),
    (re.compile(r"\blimited\s+to\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE), 1),
    (re.compile(r"\brestricted\s+to\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE), 1),
    (re.compile(r"\bscoped?\s+to\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE), 1),
    (re.compile(r"\bwithin\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE), 1),
    (re.compile(r"\bexcept\s+(?:for|in|when)\s+(.+?)(?:\.|,|;|$)", re.IGNORECASE), 1),
]

# Compile modality patterns
_MODALITY_COMPILED: list[tuple[re.Pattern, Modality]] = []
for _pat in _MUST_NOT_PATTERNS:  # Must-not before must (longer match first)
    _MODALITY_COMPILED.append((re.compile(_pat, re.IGNORECASE), Modality.MUST_NOT))
for _pat in _MUST_PATTERNS:
    _MODALITY_COMPILED.append((re.compile(_pat, re.IGNORECASE), Modality.MUST))
for _pat in _SHOULD_PATTERNS:
    _MODALITY_COMPILED.append((re.compile(_pat, re.IGNORECASE), Modality.SHOULD))
for _pat in _MAY_PATTERNS:
    _MODALITY_COMPILED.append((re.compile(_pat, re.IGNORECASE), Modality.MAY))

# Compile kind patterns
_KIND_COMPILED: dict[CommitmentKind, list[re.Pattern]] = {}
for _kind, _pats in _KIND_PATTERNS.items():
    _KIND_COMPILED[_kind] = [re.compile(p, re.IGNORECASE) for p in _pats]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Commitment:
    """A semantic obligation extracted from text."""

    commitment_id: str
    """Content hash of the obligation text."""

    text: str
    """Original text span containing the obligation."""

    modality: Modality
    """Obligation strength: MUST, SHOULD, MAY, MUST_NOT."""

    kind: CommitmentKind
    """Category: invariant, prohibition, boundary, etc."""

    scope: str | None = None
    """Scope restriction if detected (e.g., 'src/auth/')."""

    source_span: tuple[int, int] = (0, 0)
    """Byte offsets in source text (start, end)."""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "commitment_id": self.commitment_id,
            "text": self.text,
            "modality": self.modality.value,
            "kind": self.kind.value,
            "source_span": list(self.source_span),
        }
        if self.scope is not None:
            d["scope"] = self.scope
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Commitment:
        return cls(
            commitment_id=d["commitment_id"],
            text=d["text"],
            modality=Modality(d["modality"]),
            kind=CommitmentKind(d["kind"]),
            scope=d.get("scope"),
            source_span=tuple(d.get("source_span", [0, 0])),
        )

    @property
    def is_hard(self) -> bool:
        """MUST and MUST_NOT are hard obligations."""
        return self.modality in (Modality.MUST, Modality.MUST_NOT)

    @property
    def weight(self) -> float:
        """Shear weight for this commitment's modality."""
        return MODALITY_WEIGHT[self.modality]


@dataclass
class CommitmentTransport:
    """Transport result for a single commitment across a lossy transform."""

    commitment: Commitment
    """The original commitment being tracked."""

    outcome: TransportOutcome
    """How it survived: PRESERVED, WEAKENED, DROPPED, CONTRADICTED."""

    detail: str
    """Human-readable explanation of the transport result."""

    after_commitment: Commitment | None = None
    """Matched commitment in output, if found."""

    similarity: float = 0.0
    """Alignment score (0.0–1.0) between original and matched."""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "commitment": self.commitment.to_dict(),
            "outcome": self.outcome.value,
            "detail": self.detail,
            "similarity": self.similarity,
        }
        if self.after_commitment is not None:
            d["after_commitment"] = self.after_commitment.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CommitmentTransport:
        return cls(
            commitment=Commitment.from_dict(d["commitment"]),
            outcome=TransportOutcome(d["outcome"]),
            detail=d["detail"],
            after_commitment=Commitment.from_dict(d["after_commitment"]) if d.get("after_commitment") else None,
            similarity=d.get("similarity", 0.0),
        )

    @property
    def is_blocking(self) -> bool:
        """Would this transport result block under gating rules?"""
        if self.outcome == TransportOutcome.CONTRADICTED:
            return self.commitment.modality != Modality.MAY
        if self.outcome == TransportOutcome.DROPPED:
            return self.commitment.is_hard
        return False


@dataclass
class ShearReport:
    """Aggregate transport result for all commitments across a transform."""

    report_id: str
    """Content hash of this report."""

    transports: list[CommitmentTransport]
    """Per-commitment transport results."""

    transform_type: str = ""
    """Description of the lossy transform (e.g., 'compaction', 'bridge')."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    """When this report was generated."""

    @property
    def shear_score(self) -> float:
        """Weighted shear across all commitments.

        Formula: sum(outcome_shear * modality_weight) / sum(modality_weight)
        """
        if not self.transports:
            return 0.0
        total_weight = sum(t.commitment.weight for t in self.transports)
        if total_weight == 0:
            return 0.0
        weighted_shear = sum(
            OUTCOME_SHEAR[t.outcome] * t.commitment.weight
            for t in self.transports
        )
        return round(weighted_shear / total_weight, 4)

    @property
    def hard_shear(self) -> float:
        """Shear on MUST/MUST_NOT commitments only."""
        hard = [t for t in self.transports if t.commitment.is_hard]
        if not hard:
            return 0.0
        total = len(hard)
        sheared = sum(1 for t in hard if t.outcome != TransportOutcome.PRESERVED)
        return round(sheared / total, 4)

    @property
    def content_hash(self) -> str:
        """Hash of full report for receipts."""
        import json
        data = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @property
    def blocking(self) -> bool:
        """Any DROPPED or CONTRADICTED hard commitment blocks."""
        return any(t.is_blocking for t in self.transports)

    @property
    def hard_commitments(self) -> list[Commitment]:
        """All hard (MUST/MUST_NOT) commitments that were not preserved."""
        return [
            t.commitment for t in self.transports
            if t.commitment.is_hard and t.outcome != TransportOutcome.PRESERVED
        ]

    @property
    def outcome_counts(self) -> dict[str, int]:
        """Count of each transport outcome."""
        counts: dict[str, int] = {o.value: 0 for o in TransportOutcome}
        for t in self.transports:
            counts[t.outcome.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "transports": [t.to_dict() for t in self.transports],
            "transform_type": self.transform_type,
            "created_at": self.created_at.isoformat(),
            "shear_score": self.shear_score,
            "hard_shear": self.hard_shear,
            "blocking": self.blocking,
            "outcome_counts": self.outcome_counts,
            "total_commitments": len(self.transports),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ShearReport:
        return cls(
            report_id=d["report_id"],
            transports=[CommitmentTransport.from_dict(t) for t in d["transports"]],
            transform_type=d.get("transform_type", ""),
            created_at=datetime.fromisoformat(d["created_at"]) if "created_at" in d else datetime.now(timezone.utc),
        )

    def to_summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Shear Report: {self.report_id}",
            f"  Transform: {self.transform_type or '(unspecified)'}",
            f"  Total commitments: {len(self.transports)}",
            f"  Shear score: {self.shear_score:.4f}",
            f"  Hard shear: {self.hard_shear:.4f}",
            f"  Blocking: {self.blocking}",
        ]
        counts = self.outcome_counts
        lines.append(f"  Outcomes: {counts}")
        if self.blocking:
            lines.append("  BLOCKED commitments:")
            for t in self.transports:
                if t.is_blocking:
                    lines.append(f"    [{t.commitment.modality.value}] {t.commitment.text[:80]}")
                    lines.append(f"      → {t.outcome.value}: {t.detail}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Markdown report."""
        lines = [
            f"# Shear Report: {self.report_id}",
            "",
            f"**Transform**: {self.transform_type or '(unspecified)'}",
            f"**Shear score**: {self.shear_score:.4f}",
            f"**Hard shear**: {self.hard_shear:.4f}",
            f"**Blocking**: {'YES' if self.blocking else 'no'}",
            "",
            "## Outcomes",
            "",
            "| Outcome | Count |",
            "|---------|-------|",
        ]
        for outcome, count in self.outcome_counts.items():
            lines.append(f"| {outcome} | {count} |")

        if self.transports:
            lines.extend(["", "## Details", ""])
            for t in self.transports:
                marker = "**BLOCK**" if t.is_blocking else ""
                lines.append(
                    f"- [{t.commitment.modality.value}] {t.commitment.text[:80]} "
                    f"→ **{t.outcome.value}** (sim={t.similarity:.2f}) {marker}"
                )
                if t.detail:
                    lines.append(f"  - {t.detail}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commitment Extractor
# ---------------------------------------------------------------------------


def _make_commitment_id(text: str) -> str:
    """Content-addressed ID from obligation text."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()[:12]


def _detect_modality(sentence: str) -> Modality | None:
    """Detect the strongest modality in a sentence."""
    # Check patterns in priority order (must_not > must > should > may)
    for pattern, modality in _MODALITY_COMPILED:
        if pattern.search(sentence):
            return modality
    return None


def _detect_kind(sentence: str, modality: Modality) -> CommitmentKind:
    """Detect commitment kind from sentence content."""
    # Check each kind's patterns
    for kind, patterns in _KIND_COMPILED.items():
        for pat in patterns:
            if pat.search(sentence):
                return kind

    # Fall back based on modality
    if modality in (Modality.MUST_NOT,):
        return CommitmentKind.PROHIBITION
    if modality == Modality.MUST:
        return CommitmentKind.REQUIREMENT
    return CommitmentKind.REQUIREMENT


def _detect_scope(sentence: str) -> str | None:
    """Extract scope restriction from sentence."""
    for pattern, group in _SCOPE_PATTERNS:
        m = pattern.search(sentence)
        if m:
            scope = m.group(group).strip()
            if len(scope) > 2:  # Skip trivially short matches
                return scope
    return None


def _split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Split text into sentences with byte offsets.

    Returns list of (sentence_text, start_offset, end_offset).
    """
    # Split on sentence boundaries
    sentences: list[tuple[str, int, int]] = []
    # Match sentences ending with . ! ? or at end of string
    for m in re.finditer(r'[^.!?\n]+[.!?]?', text):
        sent = m.group().strip()
        if sent and len(sent) > 5:  # Skip trivially short fragments
            sentences.append((sent, m.start(), m.end()))
    return sentences


def extract_commitments(text: str) -> list[Commitment]:
    """Extract structured obligations from text.

    Uses regex + heuristic pattern matching (not LLM-based).
    Will miss implicit commitments — catches explicit ones that
    compression most commonly drops.
    """
    if not text or not text.strip():
        return []

    commitments: list[Commitment] = []
    seen_ids: set[str] = set()

    for sentence, start, end in _split_sentences(text):
        modality = _detect_modality(sentence)
        if modality is None:
            continue

        kind = _detect_kind(sentence, modality)
        scope = _detect_scope(sentence)
        cid = _make_commitment_id(sentence)

        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        commitments.append(Commitment(
            commitment_id=cid,
            text=sentence,
            modality=modality,
            kind=kind,
            scope=scope,
            source_span=(start, end),
        ))

    return commitments


# ---------------------------------------------------------------------------
# Transport Validation
# ---------------------------------------------------------------------------


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for fuzzy comparison."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text


def _token_jaccard(a: str, b: str) -> float:
    """Token-set Jaccard similarity between two strings."""
    tokens_a = set(_normalize_for_comparison(a).split())
    tokens_b = set(_normalize_for_comparison(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union) if union else 0.0


def _find_best_match(
    commitment: Commitment,
    candidates: list[Commitment],
    threshold: float = 0.3,
) -> tuple[Commitment | None, float]:
    """Find the best matching commitment in candidates.

    Returns (best_match, similarity_score).
    """
    best: Commitment | None = None
    best_score = 0.0

    for candidate in candidates:
        score = _token_jaccard(commitment.text, candidate.text)
        if score > best_score:
            best_score = score
            best = candidate

    if best_score < threshold:
        return None, 0.0

    return best, best_score


def _classify_transport(
    before: Commitment,
    after: Commitment | None,
    similarity: float,
) -> tuple[TransportOutcome, str]:
    """Classify how a commitment was transported.

    Returns (outcome, detail_string).
    """
    if after is None:
        return TransportOutcome.DROPPED, "No corresponding commitment found in output"

    # Check for contradiction: modality flipped
    if (before.modality in (Modality.MUST, Modality.MUST_NOT)
            and after.modality not in (Modality.MUST, Modality.MUST_NOT, Modality.SHOULD)):
        # Hard obligation → MAY/permission is effectively contradicted
        if before.modality == Modality.MUST_NOT and after.modality == Modality.MAY:
            return TransportOutcome.CONTRADICTED, (
                f"Prohibition ({before.modality.value}) became permission ({after.modality.value})"
            )

    # Check for direct contradiction in text
    before_norm = _normalize_for_comparison(before.text)
    after_norm = _normalize_for_comparison(after.text)

    # If before says "never X" and after says "may X" or "should X"
    if before.modality == Modality.MUST_NOT and after.modality in (Modality.MUST, Modality.SHOULD, Modality.MAY):
        return TransportOutcome.CONTRADICTED, (
            f"Prohibition contradicted: '{before.text[:40]}' → '{after.text[:40]}'"
        )

    # Check for weakening: modality softened
    _MODALITY_RANK = {
        Modality.MUST: 3,
        Modality.MUST_NOT: 3,
        Modality.SHOULD: 2,
        Modality.MAY: 1,
    }
    if _MODALITY_RANK[after.modality] < _MODALITY_RANK[before.modality]:
        return TransportOutcome.WEAKENED, (
            f"Modality softened: {before.modality.value} → {after.modality.value}"
        )

    # Check for scope widening
    if before.scope and not after.scope:
        return TransportOutcome.WEAKENED, (
            f"Scope restriction lost: was scoped to '{before.scope}'"
        )

    # Low similarity = weakened (paraphrase lost nuance)
    if similarity < 0.6:
        return TransportOutcome.WEAKENED, (
            f"Low content similarity ({similarity:.2f}): obligation may have lost nuance"
        )

    return TransportOutcome.PRESERVED, (
        f"Preserved (similarity={similarity:.2f})"
    )


def validate_transport(
    before: list[Commitment],
    after: list[Commitment],
    transform_type: str = "",
) -> ShearReport:
    """Compare commitments before and after a lossy transform.

    Matches each before-commitment to its best after-commitment,
    classifies the transport outcome, and produces a ShearReport.
    """
    transports: list[CommitmentTransport] = []
    used_after: set[str] = set()  # Track matched after-commitments

    for b_commitment in before:
        # Find best match among unused after-commitments
        available = [a for a in after if a.commitment_id not in used_after]
        match, similarity = _find_best_match(b_commitment, available)

        if match is not None:
            used_after.add(match.commitment_id)

        outcome, detail = _classify_transport(b_commitment, match, similarity)

        transports.append(CommitmentTransport(
            commitment=b_commitment,
            outcome=outcome,
            detail=detail,
            after_commitment=match,
            similarity=similarity,
        ))

    # Generate report ID from content hash
    import json
    content = json.dumps([t.to_dict() for t in transports], sort_keys=True, default=str)
    report_id = hashlib.sha256(content.encode()).hexdigest()[:12]

    return ShearReport(
        report_id=report_id,
        transports=transports,
        transform_type=transform_type,
    )


# ---------------------------------------------------------------------------
# Convenience: extract + validate in one step
# ---------------------------------------------------------------------------


def check_transport(
    before_text: str,
    after_text: str,
    transform_type: str = "",
) -> ShearReport:
    """Extract commitments from both texts and validate transport.

    Convenience function combining extraction + validation.
    """
    before_commitments = extract_commitments(before_text)
    after_commitments = extract_commitments(after_text)
    return validate_transport(before_commitments, after_commitments, transform_type)


# ---------------------------------------------------------------------------
# Transport History (file-based persistence)
# ---------------------------------------------------------------------------


@dataclass
class TransportHistory:
    """Persistent transport history for a governor directory."""

    governor_dir: Path | None = None
    """Root .governor directory."""

    @property
    def _history_dir(self) -> Path | None:
        if self.governor_dir is None:
            return None
        d = self.governor_dir / "transport"
        return d

    def save_report(self, report: ShearReport) -> Path | None:
        """Save a shear report to disk."""
        import json
        d = self._history_dir
        if d is None:
            return None
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{report.report_id}.json"
        path.write_text(json.dumps(report.to_dict(), indent=2, default=str))
        return path

    def load_report(self, report_id: str) -> ShearReport | None:
        """Load a shear report by ID."""
        import json
        d = self._history_dir
        if d is None:
            return None
        path = d / f"{report_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return ShearReport.from_dict(data)

    def list_reports(self) -> list[dict[str, Any]]:
        """List all saved reports (summary only)."""
        import json
        d = self._history_dir
        if d is None:
            return []
        if not d.exists():
            return []
        reports: list[dict[str, Any]] = []
        for path in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text())
                reports.append({
                    "report_id": data.get("report_id", path.stem),
                    "transform_type": data.get("transform_type", ""),
                    "shear_score": data.get("shear_score", 0.0),
                    "hard_shear": data.get("hard_shear", 0.0),
                    "blocking": data.get("blocking", False),
                    "total_commitments": data.get("total_commitments", 0),
                    "created_at": data.get("created_at", ""),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return reports

    def stats(self) -> dict[str, Any]:
        """Aggregate statistics across all reports."""
        reports = self.list_reports()
        if not reports:
            return {
                "total_reports": 0,
                "avg_shear": 0.0,
                "max_shear": 0.0,
                "blocking_count": 0,
            }
        shear_scores = [r["shear_score"] for r in reports]
        return {
            "total_reports": len(reports),
            "avg_shear": round(sum(shear_scores) / len(shear_scores), 4),
            "max_shear": max(shear_scores),
            "blocking_count": sum(1 for r in reports if r["blocking"]),
        }


# ---------------------------------------------------------------------------
# Integration: context compaction wrapper
# ---------------------------------------------------------------------------

from pathlib import Path


def validate_compaction_transport(
    before_text: str,
    after_summary: str,
    governor_dir: Path | None = None,
) -> ShearReport:
    """Validate that compaction preserved all hard commitments.

    Wraps context_compact.py compaction step with transport validation.
    """
    report = check_transport(before_text, after_summary, transform_type="compaction")

    if governor_dir is not None:
        history = TransportHistory(governor_dir)
        history.save_report(report)

    return report


def validate_bridge_transport(
    source_text: str,
    anchor_descriptions: list[str],
    bridge_type: str = "bridge",
    governor_dir: Path | None = None,
) -> ShearReport:
    """Validate that a continuity bridge preserved commitments.

    Checks that obligations in source text survive conversion to anchors.
    """
    # Combine anchor descriptions into a single text for extraction
    after_text = "\n".join(anchor_descriptions)
    report = check_transport(source_text, after_text, transform_type=bridge_type)

    if governor_dir is not None:
        history = TransportHistory(governor_dir)
        history.save_report(report)

    return report


def validate_constraint_transport(
    full_constraints: str,
    summarized_constraints: str,
    governor_dir: Path | None = None,
) -> ShearReport:
    """Validate that constraint projection preserved MUST obligations.

    Wraps CONSTRAINT_COMPILER_SPEC.md soft constraint summarization.
    """
    report = check_transport(
        full_constraints, summarized_constraints,
        transform_type="constraint_projection",
    )

    if governor_dir is not None:
        history = TransportHistory(governor_dir)
        history.save_report(report)

    return report


# ---------------------------------------------------------------------------
# Telemetry event helpers
# ---------------------------------------------------------------------------


def make_transport_event(report: ShearReport) -> dict[str, Any]:
    """Create a telemetry event dict for a transport validation."""
    return {
        "type": "commitment_transport",
        "report_id": report.report_id,
        "transform_type": report.transform_type,
        "shear_score": report.shear_score,
        "hard_shear": report.hard_shear,
        "blocking": report.blocking,
        "outcome_counts": report.outcome_counts,
        "total_commitments": len(report.transports),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
