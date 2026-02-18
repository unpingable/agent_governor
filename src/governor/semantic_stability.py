# SPDX-License-Identifier: Apache-2.0
"""
Semantic Stability — Perturbation-based conditioning audit.

Measures how stable the prompt→output mapping is by applying mechanical
perturbations to the prompt and measuring divergence of outputs.  A model
can produce a correct answer that's on a knife-edge — one synonym swap away
from a completely different output.  That's a conditioning problem.

Four signals:
  stiffness        median(excess_divergence / magnitude) — dimensionless,
                   how much output changes per unit of input change.
  anisotropy       p90/p10 excess divergence ratio — is sensitivity directional?
  basin_entropy    count of distinct output clusters — multimodal detection.
  commutator_drift divergence(out_AB, out_BA) − noise_floor — order-dependence.

Key design decisions:
1. Mechanical perturbations only (no LLM calls for perturbation generation).
2. Noise floor baseline: run same prompt k times, subtract temperature noise.
3. Negation probe is a positive CONTROL — excluded from stiffness, reported
   separately as control_divergence.  Low control = model not reading prompt.
4. Observational receipts only (verdict always "observe").
5. Code blocks / JSON / XML treated as atomic segments — never scrambled.
6. Call budget guardrail: returns partial result, never raises.
7. Dual divergence: raw + stripped (boilerplate stripped for stiffness).
8. Deterministic sampling via sha256(prompt), never Python hash().
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]  # Windows — no file locking

logger = logging.getLogger(__name__)


# =============================================================================
# Schema
# =============================================================================

STABILITY_SCHEMA_VERSION = 2


# =============================================================================
# Enums
# =============================================================================


class PerturbationKind(str, Enum):
    """Mechanical perturbation types applied to prompts."""

    FORMAT_JITTER = "format_jitter"
    """Whitespace, bullet/numbered swaps, indentation changes."""

    CLAUSE_REORDER = "clause_reorder"
    """Sentence-boundary shuffle of prose segments."""

    ROLE_REWRAP = "role_rewrap"
    """'You are X. Do Y.' ↔ 'Task: Y. Context: X.' framing rotation."""

    HEDGE_INSERT = "hedge_insert"
    """Semantically inert hedge words ('please', 'if possible')."""

    NEGATION_PROBE = "negation_probe"
    """Positive CONTROL — should produce high divergence."""

    INSTRUCTION_RELOCATE = "instruction_relocate"
    """Move instruction block from top→bottom or bottom→top.  Catches position bias."""

    REPEAT_TRUSTED = "repeat_trusted"
    """Duplicate the instruction/task block (trusted-only).  Probe for salience."""

    STRUCTURED_REWRAP = "structured_rewrap"
    """Prose constraints ↔ structured format (bullets, key:value, numbered)."""

    DISTRACTOR_INSERT = "distractor_insert"
    """Insert a realistic but irrelevant paragraph before the task."""


class DivergenceMethod(str, Enum):
    """Divergence proxy between two text outputs."""

    JACCARD = "jaccard"
    """Token-set Jaccard divergence: 1 − |A∩B|/|A∪B|.  Order-blind, cheap."""

    SHINGLED_JACCARD = "shingled_jaccard"
    """3-gram shingle Jaccard.  Order-aware, catches rearrangement."""

    EDIT_DISTANCE = "edit_distance"
    """Normalized character-level Levenshtein.  Short texts only (< 2000 chars)."""


# =============================================================================
# Canonical JSON (local copy of gate_receipt pattern)
# =============================================================================


def _round_floats(obj: Any) -> Any:
    """Round floats to 6 decimal places for canonical hashing stability."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v) for v in obj]
    return obj


def _canonical_json(obj: dict[str, Any]) -> bytes:
    """Deterministic JSON: sorted keys, compact separators, ASCII-safe.

    Floats rounded to 6 decimal places to prevent hash drift from
    trivial representation differences (0.7 vs 0.6999999999999999).
    """
    return json.dumps(
        _round_floats(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class Perturbation:
    """Record of a single prompt perturbation (for replay)."""

    kind: str
    original_hash: str
    perturbed_hash: str
    magnitude: float  # token-set Jaccard between original and perturbed prompt
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "original_hash": self.original_hash,
            "perturbed_hash": self.perturbed_hash,
            "magnitude": self.magnitude,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Perturbation:
        return cls(
            kind=d["kind"],
            original_hash=d["original_hash"],
            perturbed_hash=d["perturbed_hash"],
            magnitude=d["magnitude"],
            seed=d["seed"],
        )


@dataclass(frozen=True)
class StabilityFingerprint:
    """Four-signal conditioning fingerprint.

    stiffness:        median(excess_d / magnitude), dimensionless.
                      High = output changes faster than input.
    anisotropy:       p90 / p10 of excess divergence.
                      High = sensitivity is directional (some perturbation kinds
                      cause disproportionate change).
    basin_entropy:    count of distinct output clusters.
                      >1 = multimodal (prompt sits near a decision boundary).
    commutator_drift: divergence(out_AB, out_BA) − noise_floor.
                      High = perturbation order matters (non-commutative).
    noise_floor:      intrinsic temperature variance baseline.
    control_divergence: negation probe excess divergence (sanity check).
                        Low = model may not be reading the prompt.
    """

    stiffness: float
    anisotropy: float
    basin_entropy: float
    commutator_drift: float
    noise_floor: float
    control_divergence: float
    stiffness_by_kind: dict[str, float]
    commutator_kinds: tuple[str, str]
    escape_rate: float = 0.0
    escape_rate_by_kind: dict[str, float] = field(default_factory=dict)
    escape_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "stiffness": self.stiffness,
            "anisotropy": self.anisotropy,
            "basin_entropy": self.basin_entropy,
            "commutator_drift": self.commutator_drift,
            "noise_floor": self.noise_floor,
            "control_divergence": self.control_divergence,
            "stiffness_by_kind": dict(self.stiffness_by_kind),
            "commutator_kinds": list(self.commutator_kinds),
            "escape_rate": self.escape_rate,
            "escape_rate_by_kind": dict(self.escape_rate_by_kind),
            "escape_count": self.escape_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StabilityFingerprint:
        return cls(
            stiffness=d["stiffness"],
            anisotropy=d["anisotropy"],
            basin_entropy=d["basin_entropy"],
            commutator_drift=d["commutator_drift"],
            noise_floor=d["noise_floor"],
            control_divergence=d["control_divergence"],
            stiffness_by_kind=d.get("stiffness_by_kind", {}),
            commutator_kinds=tuple(
                d.get("commutator_kinds", ("role_rewrap", "clause_reorder"))
            ),
            escape_rate=d.get("escape_rate", 0.0),
            escape_rate_by_kind=d.get("escape_rate_by_kind", {}),
            escape_count=d.get("escape_count", 0),
        )


@dataclass
class StabilityConfig:
    """Configuration for the stability auditor."""

    n_perturbations: int = 8
    kinds: list[str] = field(
        default_factory=lambda: [k.value for k in PerturbationKind]
    )
    divergence_method: str = "jaccard"
    noise_floor_samples: int = 3
    basin_threshold: float = 0.3
    seed: int = 42
    store_raw_outputs: bool = False
    sample_rate: float = 0.1  # <=0 never, >=1 always
    max_generate_calls: int = 20
    commutator_pair: tuple[str, str] = ("role_rewrap", "clause_reorder")
    decoding_params: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_perturbations": self.n_perturbations,
            "kinds": list(self.kinds),
            "divergence_method": self.divergence_method,
            "noise_floor_samples": self.noise_floor_samples,
            "basin_threshold": self.basin_threshold,
            "seed": self.seed,
            "store_raw_outputs": self.store_raw_outputs,
            "sample_rate": self.sample_rate,
            "max_generate_calls": self.max_generate_calls,
            "commutator_pair": list(self.commutator_pair),
            "decoding_params": self.decoding_params,
            "schema_version": STABILITY_SCHEMA_VERSION,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StabilityConfig:
        return cls(
            n_perturbations=d.get("n_perturbations", 8),
            kinds=d.get("kinds", [k.value for k in PerturbationKind]),
            divergence_method=d.get("divergence_method", "jaccard"),
            noise_floor_samples=d.get("noise_floor_samples", 3),
            basin_threshold=d.get("basin_threshold", 0.3),
            seed=d.get("seed", 42),
            store_raw_outputs=d.get("store_raw_outputs", False),
            sample_rate=d.get("sample_rate", 0.1),
            max_generate_calls=d.get("max_generate_calls", 20),
            commutator_pair=tuple(
                d.get("commutator_pair", ("role_rewrap", "clause_reorder"))
            ),
            decoding_params=d.get("decoding_params"),
        )


@dataclass
class StabilityAuditResult:
    """Result of a single stability audit run."""

    fingerprint: StabilityFingerprint
    excess_divergences: list[float]
    raw_divergences: list[float]
    stripped_divergences: list[float]
    perturbation_kinds: list[str]
    magnitudes: list[float]
    perturbations: list[dict[str, Any]]  # for replay: kind, seed, perturbed_hash
    prompt_hash: str
    output_hash: str
    envelope_hash: str
    timestamp: str
    config_hash: str
    mode: str = "observational"
    recommendation: str = "calibrating"
    recommendation_reason: str = ""
    budget_exceeded: bool = False
    calls_used: int = 0
    n_attempted: int = 0
    n_completed: int = 0
    receipt_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STABILITY_SCHEMA_VERSION,
            "fingerprint": self.fingerprint.to_dict(),
            "excess_divergences": self.excess_divergences,
            "raw_divergences": self.raw_divergences,
            "stripped_divergences": self.stripped_divergences,
            "perturbation_kinds": self.perturbation_kinds,
            "magnitudes": self.magnitudes,
            "perturbations": self.perturbations,
            "prompt_hash": self.prompt_hash,
            "output_hash": self.output_hash,
            "envelope_hash": self.envelope_hash,
            "timestamp": self.timestamp,
            "config_hash": self.config_hash,
            "mode": self.mode,
            "recommendation": self.recommendation,
            "recommendation_reason": self.recommendation_reason,
            "budget_exceeded": self.budget_exceeded,
            "calls_used": self.calls_used,
            "n_attempted": self.n_attempted,
            "n_completed": self.n_completed,
            "receipt_id": self.receipt_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StabilityAuditResult:
        version = d.get("schema_version", 1)
        if version > STABILITY_SCHEMA_VERSION:
            raise ValueError(
                f"Stability schema version {version} is newer than supported "
                f"({STABILITY_SCHEMA_VERSION}). Upgrade governor."
            )
        return cls(
            fingerprint=StabilityFingerprint.from_dict(d["fingerprint"]),
            excess_divergences=d["excess_divergences"],
            raw_divergences=d["raw_divergences"],
            stripped_divergences=d.get("stripped_divergences", []),
            perturbation_kinds=d["perturbation_kinds"],
            magnitudes=d["magnitudes"],
            perturbations=d.get("perturbations", []),
            prompt_hash=d["prompt_hash"],
            output_hash=d["output_hash"],
            envelope_hash=d.get("envelope_hash", ""),
            timestamp=d["timestamp"],
            config_hash=d["config_hash"],
            mode=d.get("mode", "observational"),
            recommendation=d.get("recommendation", "calibrating"),
            recommendation_reason=d.get("recommendation_reason", ""),
            budget_exceeded=d.get("budget_exceeded", False),
            calls_used=d.get("calls_used", 0),
            n_attempted=d.get("n_attempted", 0),
            n_completed=d.get("n_completed", 0),
            receipt_id=d.get("receipt_id"),
        )


# =============================================================================
# Probe vs Mitigation Policy Types
# =============================================================================


class ProbeDecisionKind(str, Enum):
    """Decision produced by a stability probe.

    Probe is for measurement. Mitigation is for control. Never mix them.
    """

    PROCEED = "proceed"
    """Stable — no action needed."""

    INCONCLUSIVE = "inconclusive"
    """Measurement failed — budget exceeded or no backend."""

    MITIGATE = "mitigate"
    """Unstable — apply targeted transforms."""

    BLOCK = "block"
    """Dangerous + tools active — refuse until resolved."""

    HUMAN_GATE = "human_gate"
    """High risk + tools active — escalate to human."""


@dataclass(frozen=True)
class PromptSegment:
    """Typed prompt segment — not naked strings.

    Trust metadata prevents heuristic re-derivation later.
    """

    text: str
    trust: str       # "trusted" | "untrusted"
    seg_class: str   # "policy" | "contract" | "task" | "context" | "evidence" | "user_query"
    seg_hash: str    # sha256 of text

    @staticmethod
    def make(text: str, trust: str, seg_class: str) -> PromptSegment:
        """Construct with auto-computed hash."""
        return PromptSegment(
            text=text,
            trust=trust,
            seg_class=seg_class,
            seg_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


@dataclass(frozen=True)
class ProbeContext:
    """Prompt features that drive transform selection and escalation."""

    has_side_effects: bool = False
    """Tools enabled, can mutate state."""

    approx_words: int = 0
    """len(text.split()) — not tokens, a heuristic."""

    is_long_prompt: bool = False
    """Derived: approx_words > 1500 or char_count > 8000."""

    is_strict_format: bool = False
    """JSON/code-heavy output expected."""

    is_retrieval_heavy: bool = False
    """Lots of context/evidence blocks."""

    risk_class: str = "standard"
    """standard | elevated | critical"""

    trusted_segments: list[PromptSegment] | None = None
    """Typed segments (if available)."""

    envelope_mode: str = "strict"
    """strict | exploratory"""

    dry_run: bool = False
    """True = echo fallback, no real generation."""


@dataclass(frozen=True)
class MitigationSuggestion:
    """Axis-targeted fix suggestion from probe analysis."""

    axis: str
    """Which sensitivity axis triggered this."""

    transform: str
    """PerturbationKind value to apply as mitigation."""

    reason: str
    """Diagnostic explanation."""

    def to_dict(self) -> dict[str, str]:
        return {"axis": self.axis, "transform": self.transform, "reason": self.reason}


@dataclass
class ProbeDecision:
    """Decision artifact from a stability probe."""

    decision: str
    """ProbeDecisionKind value."""

    trigger_reasons: list[str]
    """Why this decision was reached."""

    transforms_run: list[str]
    """Which probe transforms executed."""

    mitigations: list[dict[str, str]]
    """MitigationSuggestion dicts."""

    recommendation: str
    """Underlying classification (stable/brittle/etc)."""

    measurement_failed: bool = False
    """True when budget exceeded or dry_run."""

    fingerprint_summary: dict[str, float] | None = None
    """Compact: stiffness + anisotropy + basin_entropy + escape_rate."""

    receipt_id: str | None = None
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "trigger_reasons": list(self.trigger_reasons),
            "transforms_run": list(self.transforms_run),
            "mitigations": list(self.mitigations),
            "recommendation": self.recommendation,
            "measurement_failed": self.measurement_failed,
            "fingerprint_summary": dict(self.fingerprint_summary) if self.fingerprint_summary else None,
            "receipt_id": self.receipt_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProbeDecision:
        return cls(
            decision=d["decision"],
            trigger_reasons=d.get("trigger_reasons", []),
            transforms_run=d.get("transforms_run", []),
            mitigations=d.get("mitigations", []),
            recommendation=d.get("recommendation", ""),
            measurement_failed=d.get("measurement_failed", False),
            fingerprint_summary=d.get("fingerprint_summary"),
            receipt_id=d.get("receipt_id"),
            timestamp=d.get("timestamp", ""),
        )


# =============================================================================
# Helpers: Atomic segment detection
# =============================================================================

# Fenced code blocks: ```...``` with optional language tag
_CODE_FENCE_RE = re.compile(r"^```[^\n]*\n.*?^```", re.MULTILINE | re.DOTALL)

# Multi-line JSON blocks: { ... } with newlines (conservative — single-line is prose)
_JSON_BLOCK_RE = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)

# Multi-line XML/HTML: <tag>...</tag>
_XML_BLOCK_RE = re.compile(r"<(\w+)[^>]*>.*?</\1>", re.DOTALL)


def find_atomic_segments(text: str) -> list[tuple[int, int]]:
    """Find spans of structured content that should not be perturbed.

    Conservative: fenced code blocks always; JSON/XML only when multi-line.
    False positives are worse than false negatives — when in doubt, treat as prose.
    """
    segments: list[tuple[int, int]] = []

    for m in _CODE_FENCE_RE.finditer(text):
        segments.append((m.start(), m.end()))

    for m in _JSON_BLOCK_RE.finditer(text):
        if "\n" in m.group():
            segments.append((m.start(), m.end()))

    for m in _XML_BLOCK_RE.finditer(text):
        if "\n" in m.group():
            segments.append((m.start(), m.end()))

    if not segments:
        return []
    segments.sort()
    merged: list[tuple[int, int]] = [segments[0]]
    for start, end in segments[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _extract_prose_regions(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, content) for each prose (non-atomic) region."""
    segments = find_atomic_segments(text)
    if not segments:
        return [(0, len(text), text)]

    regions: list[tuple[int, int, str]] = []
    pos = 0
    for seg_start, seg_end in segments:
        if pos < seg_start:
            regions.append((pos, seg_start, text[pos:seg_start]))
        pos = seg_end
    if pos < len(text):
        regions.append((pos, len(text), text[pos:]))
    return regions


def _reconstruct_with_prose(
    text: str, new_prose: list[str]
) -> str:
    """Rebuild text: perturbed prose interleaved with original atomic segments."""
    segments = find_atomic_segments(text)
    if not segments:
        return "".join(new_prose)

    parts: list[str] = []
    pos = 0
    prose_idx = 0
    for seg_start, seg_end in segments:
        if pos < seg_start and prose_idx < len(new_prose):
            parts.append(new_prose[prose_idx])
            prose_idx += 1
        parts.append(text[seg_start:seg_end])
        pos = seg_end
    if prose_idx < len(new_prose):
        parts.append(new_prose[prose_idx])
    return "".join(parts)


# =============================================================================
# Helpers: Boilerplate stripping
# =============================================================================

# Allowlist-driven — only strip patterns known to be common LLM pleasantries.
# Never guess.  False negatives preferred over removing meaningful content.
_BOILERPLATE_PREFIXES = [
    "sure, i can help with that.",
    "sure! here's",
    "here's the answer:",
    "here is the answer:",
    "of course! ",
    "of course, ",
    "certainly! ",
    "certainly, ",
    "absolutely! ",
    "great question! ",
    "i'd be happy to help.",
    "i'd be happy to help!",
    "let me help you with that.",
]

_BOILERPLATE_SUFFIXES = [
    "let me know if you have any questions!",
    "let me know if you need anything else!",
    "hope this helps!",
    "feel free to ask if you have any questions.",
    "i hope this helps!",
    "is there anything else i can help with?",
    "is there anything else you'd like to know?",
]


def strip_boilerplate(text: str) -> str:
    """Strip known boilerplate prefixes and suffixes (allowlist-driven)."""
    stripped = text.strip()
    lower = stripped.lower()

    for prefix in _BOILERPLATE_PREFIXES:
        if lower.startswith(prefix):
            stripped = stripped[len(prefix):].lstrip()
            break

    lower = stripped.lower()
    for suffix in _BOILERPLATE_SUFFIXES:
        if lower.endswith(suffix):
            stripped = stripped[: -len(suffix)].rstrip()
            break

    return stripped


# =============================================================================
# Tokenization + Divergence
# =============================================================================

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def tokenize_normalize(text: str) -> list[str]:
    """Normalize and tokenize for divergence.  Same pattern as taint.py."""
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text.split()


def _jaccard_divergence(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Token-set Jaccard divergence: 1 − |A∩B| / |A∪B|.  Order-blind."""
    set_a = frozenset(tokens_a)
    set_b = frozenset(tokens_b)
    union = set_a | set_b
    if not union:
        return 0.0
    return 1.0 - len(set_a & set_b) / len(union)


def _shingled_jaccard(
    tokens_a: list[str], tokens_b: list[str], n: int = 3
) -> float:
    """Shingled Jaccard divergence: 3-gram shingles, order-aware."""

    def shingles(tokens: list[str]) -> frozenset[tuple[str, ...]]:
        if len(tokens) < n:
            return frozenset([tuple(tokens)]) if tokens else frozenset()
        return frozenset(
            tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)
        )

    sa = shingles(tokens_a)
    sb = shingles(tokens_b)
    union = sa | sb
    if not union:
        return 0.0
    return 1.0 - len(sa & sb) / len(union)


def _edit_distance_normalized(text_a: str, text_b: str) -> float:
    """Normalized character-level Levenshtein.  Raises on texts > 2000 chars."""
    max_len = max(len(text_a), len(text_b))
    if max_len > 2000:
        raise ValueError(
            f"Edit distance not supported for texts > 2000 chars "
            f"(got {len(text_a)}, {len(text_b)})"
        )
    if max_len == 0:
        return 0.0

    # Standard DP with O(min(m,n)) space
    if len(text_a) < len(text_b):
        text_a, text_b = text_b, text_a

    prev = list(range(len(text_b) + 1))
    for i in range(1, len(text_a) + 1):
        curr = [i] + [0] * len(text_b)
        for j in range(1, len(text_b) + 1):
            cost = 0 if text_a[i - 1] == text_b[j - 1] else 1
            curr[j] = min(
                curr[j - 1] + 1,
                prev[j] + 1,
                prev[j - 1] + cost,
            )
        prev = curr

    return prev[len(text_b)] / max_len


def compute_divergence(
    output_a: str, output_b: str, method: str = "jaccard"
) -> float:
    """Compute divergence (0=identical, 1=disjoint) between two outputs.

    For edit_distance on texts > 2000 chars, falls back to jaccard (never crashes).
    """
    if method == DivergenceMethod.EDIT_DISTANCE.value:
        try:
            return _edit_distance_normalized(output_a, output_b)
        except ValueError:
            logger.warning(
                "Edit distance text too long (%d/%d chars), falling back to jaccard",
                len(output_a),
                len(output_b),
            )
            method = DivergenceMethod.JACCARD.value

    tokens_a = tokenize_normalize(output_a)
    tokens_b = tokenize_normalize(output_b)

    if method == DivergenceMethod.SHINGLED_JACCARD.value:
        return _shingled_jaccard(tokens_a, tokens_b)

    return _jaccard_divergence(tokens_a, tokens_b)


# =============================================================================
# Perturbation Generators
# =============================================================================

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

_HEDGES = [
    "please",
    "if possible",
    "I think",
    "perhaps",
    "kindly",
    "I believe",
    "it seems like",
    "maybe",
    "ideally",
]

_NEGATION_PAIRS = [
    ("should", "should not"),
    ("must", "must not"),
    ("always", "never"),
    ("do", "do not"),
    ("can", "cannot"),
    ("will", "will not"),
    ("is", "is not"),
    ("are", "are not"),
]


def perturb_format_jitter(text: str, seed: int) -> tuple[str, float]:
    """Swap bullets ↔ numbered, add/remove trailing newlines, change indentation."""
    rng = random.Random(seed)

    prose_regions = _extract_prose_regions(text)
    if not prose_regions:
        return text, 0.0

    new_prose: list[str] = []
    for _, _, content in prose_regions:
        lines = content.split("\n")
        result_lines: list[str] = []
        counter = 1
        for line in lines:
            if line.lstrip().startswith("- ") and rng.random() > 0.5:
                indent = len(line) - len(line.lstrip())
                line = " " * indent + f"{counter}. " + line.lstrip()[2:]
                counter += 1
            elif re.match(r"\s*\d+\.\s", line) and rng.random() > 0.5:
                indent = len(line) - len(line.lstrip())
                content_part = re.sub(r"^\s*\d+\.\s", "", line)
                line = " " * indent + "- " + content_part

            if rng.random() > 0.7:
                if line.startswith("  "):
                    line = line[2:]
                elif line and not line.startswith(" "):
                    line = "  " + line

            result_lines.append(line)

        result = "\n".join(result_lines)
        if rng.random() > 0.5:
            result = result.rstrip("\n") + "\n\n"
        else:
            result = result.rstrip("\n")
        new_prose.append(result)

    perturbed = _reconstruct_with_prose(text, new_prose)
    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


def perturb_clause_reorder(text: str, seed: int) -> tuple[str, float]:
    """Split on sentence boundaries and shuffle segments."""
    rng = random.Random(seed)

    prose_regions = _extract_prose_regions(text)
    if not prose_regions:
        return text, 0.0

    new_prose: list[str] = []
    for _, _, content in prose_regions:
        sentences = _SENTENCE_RE.split(content)
        if len(sentences) <= 1:
            new_prose.append(content)
            continue

        shuffleable = [s for s in sentences if len(s.split()) >= 3]
        fixed = [s for s in sentences if len(s.split()) < 3]

        if len(shuffleable) > 1:
            rng.shuffle(shuffleable)

        new_prose.append(" ".join(shuffleable + fixed))

    perturbed = _reconstruct_with_prose(text, new_prose)
    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


def perturb_role_rewrap(text: str, seed: int) -> tuple[str, float]:
    """Rotate between different role/instruction framing patterns."""
    rng = random.Random(seed)

    prose_regions = _extract_prose_regions(text)
    if not prose_regions:
        return text, 0.0

    new_prose: list[str] = []
    for _, _, content in prose_regions:
        transformed = False

        m = re.match(r"^You are (.+?)\.\s*(.+)$", content, re.DOTALL)
        if m:
            role, task = m.group(1), m.group(2)
            templates = [
                f"Task: {task} Context: {role}",
                f"As {role}, {task}",
                f"Acting as {role}, please: {task}",
            ]
            new_prose.append(rng.choice(templates))
            transformed = True

        if not transformed:
            m = re.match(r"^As (.+?),\s*(.+)$", content, re.DOTALL)
            if m:
                role, task = m.group(1), m.group(2)
                templates = [
                    f"You are {role}. {task}",
                    f"Task: {task} Context: {role}",
                ]
                new_prose.append(rng.choice(templates))
                transformed = True

        if not transformed:
            m = re.match(r"^Task:\s*(.+?)\s*Context:\s*(.+)$", content, re.DOTALL)
            if m:
                task, role = m.group(1), m.group(2)
                templates = [
                    f"You are {role}. {task}",
                    f"As {role}, {task}",
                ]
                new_prose.append(rng.choice(templates))
                transformed = True

        if not transformed:
            templates = [
                f"Please respond to: {content}",
                f"Consider the following: {content}",
                f"Given the prompt: {content}",
            ]
            new_prose.append(rng.choice(templates))

    perturbed = _reconstruct_with_prose(text, new_prose)
    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


def perturb_hedge_insert(text: str, seed: int) -> tuple[str, float]:
    """Insert semantically inert hedge words at random positions."""
    rng = random.Random(seed)

    prose_regions = _extract_prose_regions(text)
    if not prose_regions:
        return text, 0.0

    new_prose: list[str] = []
    for _, _, content in prose_regions:
        words = content.split()
        if not words:
            new_prose.append(content)
            continue

        n_hedges = rng.randint(1, min(3, max(1, len(words) // 5)))
        result_words = list(words)
        for _ in range(n_hedges):
            pos = rng.randint(0, len(result_words))
            hedge = rng.choice(_HEDGES)
            if 0 < pos < len(result_words):
                hedge = hedge + ","
            result_words.insert(pos, hedge)

        new_prose.append(" ".join(result_words))

    perturbed = _reconstruct_with_prose(text, new_prose)
    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


def perturb_negation_probe(text: str, seed: int) -> tuple[str, float]:
    """Negate a clause — positive control, SHOULD produce high divergence."""
    rng = random.Random(seed)

    prose_regions = _extract_prose_regions(text)
    if not prose_regions:
        return text, 0.0

    new_prose: list[str] = []
    negated = False

    for _, _, content in prose_regions:
        if negated:
            new_prose.append(content)
            continue

        words = content.split()

        # Find all negation targets
        targets: list[tuple[int, str, str]] = []
        for i, w in enumerate(words):
            w_lower = w.lower().rstrip(".,;:!?")
            for word_orig, word_neg in _NEGATION_PAIRS:
                if w_lower == word_orig:
                    targets.append((i, word_orig, word_neg))

        if targets:
            idx, _, word_neg = rng.choice(targets)
            w = words[idx]
            trailing = ""
            stripped_w = w.rstrip(".,;:!?")
            if len(w) > len(stripped_w):
                trailing = w[len(stripped_w):]
            words[idx] = word_neg + trailing
            negated = True
        elif words:
            words.insert(0, "Do not")
            negated = True

        new_prose.append(" ".join(words))

    perturbed = _reconstruct_with_prose(text, new_prose)
    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


# ---------------------------------------------------------------------------
# New perturbation family (v2.3): instruction salience, repetition,
# structured representation, distractor insertion.
# ---------------------------------------------------------------------------

_PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n")

_DISTRACTORS = [
    "Note: the project uses a standard CI/CD pipeline with automated "
    "testing on every commit. Build artifacts are cached for 30 days.",
    "For context, the team adopted this codebase in Q3 2024 after "
    "evaluating three alternatives. Migration was completed in two sprints.",
    "The deployment environment uses Kubernetes with auto-scaling "
    "configured between 2 and 8 replicas based on CPU utilisation.",
    "Background: the authentication module was last audited in January. "
    "No critical findings were reported, though two minor items remain open.",
    "The database schema was normalised to 3NF during the initial design "
    "phase. Denormalisation was applied selectively for read-heavy queries.",
    "Historical note: this repository was migrated from SVN in 2021. "
    "Some legacy commit messages may reference old ticket IDs.",
]


def perturb_instruction_relocate(text: str, seed: int) -> tuple[str, float]:
    """Move the first paragraph to the end (or vice versa).

    Splits on the first blank-line boundary.  If there's only one block,
    returns unchanged (magnitude 0).  Deterministic given seed: even seeds
    move top→bottom, odd seeds move bottom→top.
    """
    parts = _PARAGRAPH_BREAK_RE.split(text, maxsplit=1)
    if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
        return text, 0.0

    rng = random.Random(seed)
    if rng.random() > 0.5:
        # top → bottom
        perturbed = parts[1].strip() + "\n\n" + parts[0].strip()
    else:
        # bottom → top  (split from end)
        last_break = text.rfind("\n\n")
        if last_break <= 0:
            perturbed = parts[1].strip() + "\n\n" + parts[0].strip()
        else:
            tail = text[last_break:].strip()
            head = text[:last_break].strip()
            perturbed = tail + "\n\n" + head

    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


def perturb_repeat_trusted(text: str, seed: int) -> tuple[str, float]:
    """Duplicate the first paragraph (instruction block) at the end.

    Models the "repeat trusted instruction" technique from prompt repetition
    research (arXiv:2512.14982).  The transform appends the instruction
    block as-is, prefixed by a separator.  Only the *first* block is
    repeated — context/evidence blocks are left alone.

    Security invariant: in production (mitigation mode), callers must
    ensure only trusted segments are repeated.  This function operates on
    raw text for probe purposes.
    """
    parts = _PARAGRAPH_BREAK_RE.split(text, maxsplit=1)
    instruction_block = parts[0].strip()

    if not instruction_block:
        return text, 0.0

    rng = random.Random(seed)
    separators = [
        "\n\n",
        "\n\nTo reiterate:\n",
        "\n\nReminder:\n",
    ]
    sep = rng.choice(separators)
    perturbed = text.rstrip() + sep + instruction_block

    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


_STRUCTURED_TEMPLATES = [
    # bullet list
    lambda items: "\n".join(f"- {item}" for item in items),
    # numbered list
    lambda items: "\n".join(f"{i+1}. {item}" for i, item in enumerate(items)),
    # key:value
    lambda items: "\n".join(
        f"Constraint {i+1}: {item}" for i, item in enumerate(items)
    ),
]


def perturb_structured_rewrap(text: str, seed: int) -> tuple[str, float]:
    """Convert prose constraints into a different structured format.

    Splits prose on sentence boundaries, then rewraps as bullet list,
    numbered list, or key:value pairs.  Catches models that behave
    differently with explicit structure vs. flowing prose.
    """
    rng = random.Random(seed)

    prose_regions = _extract_prose_regions(text)
    if not prose_regions:
        return text, 0.0

    new_prose: list[str] = []
    for _, _, content in prose_regions:
        sentences = _SENTENCE_RE.split(content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) < 2:
            new_prose.append(content)
            continue

        template = rng.choice(_STRUCTURED_TEMPLATES)
        new_prose.append(template(sentences))

    perturbed = _reconstruct_with_prose(text, new_prose)
    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


def perturb_distractor_insert(text: str, seed: int) -> tuple[str, float]:
    """Insert a realistic but irrelevant paragraph before the task.

    Uses seeded selection from a fixed template bank (_DISTRACTORS).
    Catches instruction drift / distraction susceptibility.
    """
    rng = random.Random(seed)

    if not text.strip():
        return text, 0.0

    distractor = rng.choice(_DISTRACTORS)
    perturbed = distractor + "\n\n" + text

    magnitude = compute_divergence(text, perturbed, "jaccard")
    return perturbed, magnitude


_PERTURBATION_FNS: dict[str, Callable[[str, int], tuple[str, float]]] = {
    PerturbationKind.FORMAT_JITTER.value: perturb_format_jitter,
    PerturbationKind.CLAUSE_REORDER.value: perturb_clause_reorder,
    PerturbationKind.ROLE_REWRAP.value: perturb_role_rewrap,
    PerturbationKind.HEDGE_INSERT.value: perturb_hedge_insert,
    PerturbationKind.NEGATION_PROBE.value: perturb_negation_probe,
    PerturbationKind.INSTRUCTION_RELOCATE.value: perturb_instruction_relocate,
    PerturbationKind.REPEAT_TRUSTED.value: perturb_repeat_trusted,
    PerturbationKind.STRUCTURED_REWRAP.value: perturb_structured_rewrap,
    PerturbationKind.DISTRACTOR_INSERT.value: perturb_distractor_insert,
}


def generate_perturbation(text: str, kind: str, seed: int) -> tuple[str, float]:
    """Generate a single perturbation of the given kind."""
    fn = _PERTURBATION_FNS.get(kind)
    if fn is None:
        raise ValueError(f"Unknown perturbation kind: {kind}")
    return fn(text, seed)


# =============================================================================
# Basin Clustering (distance-to-baseline)
# =============================================================================


def compute_basin_entropy(
    baseline_output: str,
    perturbed_outputs: list[str],
    threshold: float = 0.3,
    method: str = "jaccard",
) -> float:
    """Count distinct output basins via distance-to-baseline clustering.

    1. Outputs within threshold of baseline = near-baseline basin (count 1).
    2. Far-from-baseline outputs clustered greedily among themselves.
    3. Returns total basin count.
    """
    if not perturbed_outputs:
        return 1.0

    far_from_baseline: list[str] = []

    for output in perturbed_outputs:
        d = compute_divergence(baseline_output, output, method)
        if d > threshold:
            far_from_baseline.append(output)

    # Near-baseline basin always exists (the baseline itself)
    basin_count = 1

    # Greedy clustering of far-from-baseline outputs
    clusters: list[str] = []
    for output in far_from_baseline:
        assigned = False
        for rep in clusters:
            if compute_divergence(rep, output, method) <= threshold:
                assigned = True
                break
        if not assigned:
            clusters.append(output)

    basin_count += len(clusters)
    return float(basin_count)


# =============================================================================
# Escape Rate (basin leakiness)
# =============================================================================


def compute_escape_stats(
    baseline_output: str,
    perturbed_outputs: list[str],
    kinds: list[str],
    threshold: float,
    method: str = "jaccard",
    strip: bool = True,
) -> tuple[float, dict[str, float], int, list[float]]:
    """Compute escape rate: fraction of perturbations that leave the baseline basin.

    Uses absolute divergence to baseline (not excess), because basin membership
    is a semantics boundary, not a temperature-corrected boundary.

    Excludes negation probe and zero-magnitude perturbations from the rate.

    Returns:
        escape_rate: fraction of valid perturbations that escaped.
        escape_rate_by_kind: per-kind escape fractions (negation excluded).
        escape_count: absolute number of escapes.
        baseline_divergences: divergence from baseline for each perturbed output.
    """
    if not perturbed_outputs:
        return 0.0, {}, 0, []

    neg_kind = PerturbationKind.NEGATION_PROBE.value
    strip_fn = strip_boilerplate if strip else (lambda x: x)
    baseline_stripped = strip_fn(baseline_output)

    baseline_divergences: list[float] = []
    kind_escapes: dict[str, int] = {}
    kind_totals: dict[str, int] = {}
    escape_count = 0
    valid_count = 0

    for i, perturbed in enumerate(perturbed_outputs):
        d = compute_divergence(baseline_stripped, strip_fn(perturbed), method)
        baseline_divergences.append(d)

        kind = kinds[i] if i < len(kinds) else ""
        if kind == neg_kind:
            continue

        valid_count += 1
        escaped = d > threshold

        if escaped:
            escape_count += 1

        kind_escapes.setdefault(kind, 0)
        kind_totals.setdefault(kind, 0)
        kind_totals[kind] += 1
        if escaped:
            kind_escapes[kind] += 1

    escape_rate = escape_count / valid_count if valid_count > 0 else 0.0
    escape_rate_by_kind = {
        k: kind_escapes.get(k, 0) / kind_totals[k]
        for k in kind_totals
        if kind_totals[k] > 0
    }

    return escape_rate, escape_rate_by_kind, escape_count, baseline_divergences


# =============================================================================
# Noise Floor
# =============================================================================


def compute_noise_floor(
    prompt: str,
    generate_fn: Callable[[str], str],
    n: int = 3,
    method: str = "jaccard",
) -> float:
    """Intrinsic variance: median pairwise divergence of n identical runs."""
    if n < 2:
        return 0.0

    outputs = [generate_fn(prompt) for _ in range(n)]

    pairwise: list[float] = []
    for i in range(len(outputs)):
        for j in range(i + 1, len(outputs)):
            pairwise.append(compute_divergence(outputs[i], outputs[j], method))

    return statistics.median(pairwise) if pairwise else 0.0


# =============================================================================
# Commutator Drift
# =============================================================================


def compute_commutator_drift(
    prompt: str,
    kind_a: str,
    kind_b: str,
    generate_fn: Callable[[str], str],
    seed: int,
    noise_floor: float,
    method: str = "jaccard",
) -> float:
    """Non-commutativity: divergence(out_AB, out_BA) − noise_floor.

    Apply A then B → generate.  Apply B then A → generate.
    Positive result = perturbation order matters.
    """
    text_a, _ = generate_perturbation(prompt, kind_a, seed)
    text_ab, _ = generate_perturbation(text_a, kind_b, seed + 1)
    out_ab = generate_fn(text_ab)

    text_b, _ = generate_perturbation(prompt, kind_b, seed)
    text_ba, _ = generate_perturbation(text_b, kind_a, seed + 1)
    out_ba = generate_fn(text_ba)

    d = compute_divergence(out_ab, out_ba, method)
    return max(0.0, d - noise_floor)


# =============================================================================
# Fingerprint Computation
# =============================================================================


def compute_fingerprint(
    stripped_divergences: list[float],
    magnitudes: list[float],
    kinds: list[str],
    noise_floor: float,
    commutator_drift: float,
    commutator_kinds: tuple[str, str],
    baseline_output: str,
    perturbed_outputs: list[str],
    control_divergence: float,
    basin_threshold: float = 0.3,
    method: str = "jaccard",
) -> StabilityFingerprint:
    """Compute stability fingerprint from audit data.

    Uses stripped_divergences (boilerplate removed) for stiffness/anisotropy
    so that irrelevant preamble changes don't mask real shifts.
    """
    neg_kind = PerturbationKind.NEGATION_PROBE.value

    excess_d = [max(0.0, d - noise_floor) for d in stripped_divergences]

    # Filter to non-negation entries
    non_neg_excess: list[float] = []
    non_neg_magnitudes: list[float] = []
    non_neg_kinds: list[str] = []
    for i, kind in enumerate(kinds):
        if kind != neg_kind:
            non_neg_excess.append(excess_d[i])
            non_neg_magnitudes.append(magnitudes[i])
            non_neg_kinds.append(kind)

    # stiffness = median(excess_d / magnitude), dimensionless
    stiffness_values: list[float] = []
    for ed, mag in zip(non_neg_excess, non_neg_magnitudes):
        if mag > 0:
            stiffness_values.append(ed / mag)
    stiffness = statistics.median(stiffness_values) if stiffness_values else 0.0

    # anisotropy = p90 / p10 — directional sensitivity
    if len(non_neg_excess) >= 2:
        sorted_ed = sorted(non_neg_excess)
        p10_idx = max(0, int(len(sorted_ed) * 0.1))
        p90_idx = min(len(sorted_ed) - 1, int(len(sorted_ed) * 0.9))
        p10 = sorted_ed[p10_idx]
        p90 = sorted_ed[p90_idx]
        anisotropy = p90 / max(p10, 1e-6)
    else:
        anisotropy = 1.0

    basin_entropy = compute_basin_entropy(
        baseline_output, perturbed_outputs, basin_threshold, method
    )

    # Escape rate (absolute divergence to baseline, not excess)
    escape_rate, escape_rate_by_kind, escape_count, _ = compute_escape_stats(
        baseline_output, perturbed_outputs, kinds, basin_threshold, method,
    )

    # Per-kind stiffness vector
    kind_stiffness: dict[str, list[float]] = {}
    for i, kind in enumerate(non_neg_kinds):
        if non_neg_magnitudes[i] > 0:
            kind_stiffness.setdefault(kind, []).append(
                non_neg_excess[i] / non_neg_magnitudes[i]
            )
    stiffness_by_kind = {
        k: statistics.median(v) for k, v in kind_stiffness.items()
    }

    return StabilityFingerprint(
        stiffness=stiffness,
        anisotropy=anisotropy,
        basin_entropy=basin_entropy,
        commutator_drift=commutator_drift,
        noise_floor=noise_floor,
        control_divergence=control_divergence,
        stiffness_by_kind=stiffness_by_kind,
        commutator_kinds=commutator_kinds,
        escape_rate=escape_rate,
        escape_rate_by_kind=escape_rate_by_kind,
        escape_count=escape_count,
    )


# =============================================================================
# Probe Transform Selection
# =============================================================================

# Short aliases for budget tier definitions
_FJ = PerturbationKind.FORMAT_JITTER.value
_CR = PerturbationKind.CLAUSE_REORDER.value
_RR = PerturbationKind.ROLE_REWRAP.value
_IR = PerturbationKind.INSTRUCTION_RELOCATE.value
_SR = PerturbationKind.STRUCTURED_REWRAP.value
_DI = PerturbationKind.DISTRACTOR_INSERT.value
_RT = PerturbationKind.REPEAT_TRUSTED.value
_NP = PerturbationKind.NEGATION_PROBE.value


# Ordered transform sets by information value.
# Each tier: (name, predicate on ProbeContext, list of PerturbationKind values)
_PROBE_BUDGET_TIERS: list[tuple[str, Callable[[ProbeContext], bool], list[str]]] = [
    # Tier 0: single canary (always, minimal cost)
    ("canary", lambda _: True, [_FJ]),
    # Tier 1: add for deep probe or elevated risk
    ("canary_deep", lambda c: c.risk_class != "standard", [_CR, _RR]),
    # Tier 2: add for long-context or retrieval-heavy
    ("long_context", lambda c: c.is_long_prompt or c.is_retrieval_heavy, [_IR]),
    # Tier 3: structure sensitivity
    ("structure", lambda c: c.is_strict_format, [_SR]),
    # Tier 4: drift detection
    ("drift", lambda c: c.is_retrieval_heavy or c.is_long_prompt, [_DI]),
    # Tier 5: salience probe (needs typed segments)
    ("salience", lambda c: c.trusted_segments is not None, [_RT]),
]


def select_probe_transforms(
    context: ProbeContext,
    deep: bool = False,
    max_kinds: int = 5,
) -> list[str]:
    """Select transforms based on context and budget.

    Default: tier 0 only (1 transform: format_jitter). Cheap canary.
    deep=True: also includes tier 1 (clause_reorder + role_rewrap).
    Remaining tiers selected by context predicates.
    Negation probe always appended as positive control (not counted against cap).
    """
    selected: list[str] = []

    for name, predicate, kinds in _PROBE_BUDGET_TIERS:
        if name == "canary":
            selected.extend(kinds)
        elif name == "canary_deep":
            if deep or predicate(context):
                selected.extend(kinds)
        else:
            if predicate(context):
                selected.extend(kinds)

        if len(selected) >= max_kinds:
            break

    selected = selected[:max_kinds]

    # Negation probe is ALWAYS appended as positive control.
    # Does NOT count against max_kinds cap.
    # Must NOT be in the main selected list (excluded from all scoring).
    if _NP in selected:
        selected.remove(_NP)
    return selected


# =============================================================================
# Mitigation Selection
# =============================================================================


def select_mitigations(
    fingerprint: StabilityFingerprint,
    context: ProbeContext,
) -> list[MitigationSuggestion]:
    """Axis-targeted diagnostic interpretation from per-kind stiffness.

    Uses fingerprint.stiffness_by_kind dict. Threshold: per-kind stiffness > 2.0.
    HARD INVARIANT: repeat_trusted mitigation only emitted when
    context.trusted_segments is not None.
    """
    suggestions: list[MitigationSuggestion] = []
    by_kind = fingerprint.stiffness_by_kind

    # High instruction_relocate stiffness → position/recency bias
    if by_kind.get(_IR, 0.0) > _STIFFNESS_BRITTLE:
        suggestions.append(MitigationSuggestion(
            axis="position_bias",
            transform=_IR,
            reason="High instruction-relocate stiffness indicates position/recency bias. "
                   "Place critical instructions at both start and end (sandwich).",
        ))

    # High structured_rewrap stiffness → representation sensitivity
    if by_kind.get(_SR, 0.0) > _STIFFNESS_BRITTLE:
        suggestions.append(MitigationSuggestion(
            axis="representation_sensitivity",
            transform=_SR,
            reason="High structured-rewrap stiffness indicates representation sensitivity. "
                   "Use explicit schema form (bullet/numbered) for constraints.",
        ))

    # High distractor_insert stiffness → instruction drift
    if by_kind.get(_DI, 0.0) > _STIFFNESS_BRITTLE:
        suggestions.append(MitigationSuggestion(
            axis="instruction_drift",
            transform=_DI,
            reason="High distractor stiffness indicates instruction drift susceptibility. "
                   "Add stronger task boundaries and reassert instructions after context.",
        ))

    # Low stiffness with repeat_trusted → attention dilution (repeat helps)
    # HARD INVARIANT: only suggest repeat_trusted when typed segments available
    rt_stiffness = by_kind.get(_RT, None)
    if rt_stiffness is not None and rt_stiffness < _STIFFNESS_BRITTLE:
        if context.trusted_segments is not None:
            suggestions.append(MitigationSuggestion(
                axis="attention_dilution",
                transform=_RT,
                reason="Low repeat-trusted stiffness suggests attention dilution. "
                       "Repeating trusted instruction block improves salience.",
            ))
        else:
            logger.debug(
                "repeat_trusted mitigation suppressed: no typed segments available"
            )

    # High clause_reorder stiffness → order sensitivity
    if by_kind.get(_CR, 0.0) > _STIFFNESS_BRITTLE:
        suggestions.append(MitigationSuggestion(
            axis="order_sensitivity",
            transform=_CR,
            reason="High clause-reorder stiffness indicates order sensitivity. "
                   "Ensure critical constraints appear first or use structured format.",
        ))

    return suggestions


# =============================================================================
# Escalation Ladder
# =============================================================================


def _escalate(
    recommendation: str,
    context: ProbeContext,
    measurement_failed: bool,
) -> tuple[ProbeDecisionKind, list[str]]:
    """Map recommendation + context → ProbeDecisionKind + trigger reasons.

    Exploratory mode downgrade: only applies when has_side_effects=False.
    If has_side_effects=True, exploratory mode does NOT soften BLOCK/HUMAN_GATE.
    """
    reasons: list[str] = []

    # --- Budget exceeded / measurement failed ---
    if measurement_failed:
        reasons.append("measurement_failed")
        if not context.has_side_effects:
            return ProbeDecisionKind.INCONCLUSIVE, reasons
        if context.risk_class == "standard":
            return ProbeDecisionKind.INCONCLUSIVE, reasons
        reasons.append(f"risk_class={context.risk_class} + side_effects + measurement_failed")
        return ProbeDecisionKind.BLOCK, reasons

    # --- Normal (measurement succeeded) ---
    reasons.append(f"recommendation={recommendation}")

    if recommendation in ("stable", "calibrating"):
        return ProbeDecisionKind.PROCEED, reasons

    if recommendation == "brittle":
        if not context.has_side_effects:
            return ProbeDecisionKind.MITIGATE, reasons
        if context.risk_class == "standard":
            return ProbeDecisionKind.MITIGATE, reasons
        # elevated or critical + tools
        reasons.append(f"risk_class={context.risk_class} + side_effects")
        return ProbeDecisionKind.BLOCK, reasons

    if recommendation == "multimodal":
        if not context.has_side_effects:
            return ProbeDecisionKind.MITIGATE, reasons
        if context.risk_class == "standard":
            reasons.append("multimodal + side_effects")
            return ProbeDecisionKind.BLOCK, reasons
        # elevated or critical
        reasons.append(f"risk_class={context.risk_class} + multimodal + side_effects")
        return ProbeDecisionKind.HUMAN_GATE, reasons

    # Unknown recommendation → PROCEED with warning
    reasons.append(f"unknown_recommendation={recommendation}")
    return ProbeDecisionKind.PROCEED, reasons


# Verdict mapping for probe receipts
_PROBE_DECISION_TO_VERDICT: dict[str, str] = {
    ProbeDecisionKind.PROCEED.value: "pass",
    ProbeDecisionKind.INCONCLUSIVE.value: "observe",
    ProbeDecisionKind.MITIGATE.value: "warn",
    ProbeDecisionKind.BLOCK.value: "block",
    ProbeDecisionKind.HUMAN_GATE.value: "block",
}


# =============================================================================
# Integration Gate
# =============================================================================


def check_probe_gate(
    decision: ProbeDecision,
    mitigations_applied: list[str] | None = None,
) -> tuple[bool, str]:
    """Check whether an action should proceed based on a probe decision.

    Returns (allowed, reason).

    Rules:
      PROCEED              → allowed
      INCONCLUSIVE         → allowed (with warning)
      MITIGATE + ack'd     → allowed (mitigations_applied covers suggestions)
      MITIGATE + not ack'd → blocked
      BLOCK                → blocked
      HUMAN_GATE           → blocked
    """
    kind = decision.decision

    if kind == ProbeDecisionKind.PROCEED.value:
        return True, "stable"

    if kind == ProbeDecisionKind.INCONCLUSIVE.value:
        return True, "inconclusive: measurement failed, proceeding with caution"

    if kind == ProbeDecisionKind.MITIGATE.value:
        suggested = {m["transform"] for m in decision.mitigations}
        applied = set(mitigations_applied or [])
        if not suggested or suggested <= applied:
            return True, "mitigations acknowledged"
        missing = suggested - applied
        return False, f"mitigations not applied: {', '.join(sorted(missing))}"

    if kind == ProbeDecisionKind.BLOCK.value:
        return False, f"blocked: {'; '.join(decision.trigger_reasons)}"

    if kind == ProbeDecisionKind.HUMAN_GATE.value:
        return False, f"human gate required: {'; '.join(decision.trigger_reasons)}"

    return True, f"unknown decision kind: {kind}"


# =============================================================================
# Auditor
# =============================================================================

# Recommendation thresholds (placeholders — calibrate from data)
_STIFFNESS_BRITTLE = 2.0
_ANISOTROPY_HIGH = 3.0
_BASIN_MULTIMODAL = 3
_STIFFNESS_STABLE = 0.5
_ANISOTROPY_STABLE = 3.0
_BASIN_STABLE = 1.5


class StabilityAuditor:
    """Runs perturbation-based conditioning audits on prompt→output mappings.

    Audit-mode, not inline gate.  Runs on sampled generations (configurable rate).
    Returns StabilityAuditResult with four-signal fingerprint.
    """

    def __init__(self, config: StabilityConfig | None = None) -> None:
        self.config = config or StabilityConfig()

    def should_audit(self, prompt: str) -> bool:
        """Deterministic sampling: sha256(prompt) mod divisor == 0.

        Clamped: sample_rate<=0 → never, >=1 → always.
        Uses sha256, never Python hash() (non-deterministic across runs).
        """
        rate = self.config.sample_rate
        if rate <= 0:
            return False
        if rate >= 1:
            return True
        divisor = max(1, round(1 / rate))
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big")
        return value % divisor == 0

    def audit(
        self,
        prompt: str,
        output: str,
        generate_fn: Callable[[str], str],
        receipt_system: Any | None = None,
        envelope: dict | None = None,
    ) -> StabilityAuditResult:
        """Run stability audit.  Returns result, never raises."""
        config = self.config
        method = config.divergence_method
        timestamp = datetime.now(timezone.utc).isoformat()

        # Call budget
        call_count = 0
        budget = config.max_generate_calls
        budget_exceeded = False

        def counted_generate(p: str) -> str:
            nonlocal call_count, budget_exceeded
            call_count += 1
            if call_count > budget:
                budget_exceeded = True
                return ""
            return generate_fn(p)

        # Hashes
        prompt_hash = _content_hash(prompt.encode("utf-8"))
        output_hash = _content_hash(output.encode("utf-8"))

        envelope_data = dict(envelope) if envelope else {}
        envelope_data["user_prompt_hash"] = prompt_hash
        envelope_hash = _content_hash(_canonical_json(envelope_data))
        config_hash = _content_hash(_canonical_json(config.to_dict()))

        # Noise floor
        noise_val = compute_noise_floor(
            prompt, counted_generate, config.noise_floor_samples, method
        )

        if budget_exceeded:
            return self._partial_result(
                prompt_hash, output_hash, envelope_hash, config_hash,
                timestamp, call_count, noise_val,
            )

        # Run perturbations
        raw_divergences: list[float] = []
        stripped_divergences: list[float] = []
        perturbation_kinds: list[str] = []
        magnitudes_list: list[float] = []
        perturbed_outputs: list[str] = []
        perturbation_records: list[dict[str, Any]] = []
        control_divergence = 0.0

        rng_seed = config.seed
        for i in range(config.n_perturbations):
            if budget_exceeded:
                break

            kind = config.kinds[i % len(config.kinds)]
            this_seed = rng_seed + i
            perturbed_text, mag = generate_perturbation(prompt, kind, this_seed)
            perturbed_output = counted_generate(perturbed_text)

            if budget_exceeded:
                break

            raw_d = compute_divergence(output, perturbed_output, method)
            stripped_d = compute_divergence(
                strip_boilerplate(output),
                strip_boilerplate(perturbed_output),
                method,
            )

            raw_divergences.append(raw_d)
            stripped_divergences.append(stripped_d)
            perturbation_kinds.append(kind)
            magnitudes_list.append(mag)
            perturbed_outputs.append(perturbed_output)

            perturbation_records.append({
                "kind": kind,
                "seed": this_seed,
                "perturbed_hash": _content_hash(
                    perturbed_text.encode("utf-8")
                ),
                "magnitude": mag,
            })

            if kind == PerturbationKind.NEGATION_PROBE.value:
                control_divergence = max(0.0, raw_d - noise_val)

        if budget_exceeded or not raw_divergences:
            return self._partial_result(
                prompt_hash, output_hash, envelope_hash, config_hash,
                timestamp, call_count, noise_val, len(raw_divergences),
            )

        # Commutator drift
        comm_drift = 0.0
        if not budget_exceeded:
            comm_drift = compute_commutator_drift(
                prompt,
                config.commutator_pair[0],
                config.commutator_pair[1],
                counted_generate,
                config.seed + 1000,
                noise_val,
                method,
            )

        # Fingerprint
        fingerprint = compute_fingerprint(
            stripped_divergences,
            magnitudes_list,
            perturbation_kinds,
            noise_val,
            comm_drift,
            config.commutator_pair,
            output,
            perturbed_outputs,
            control_divergence,
            config.basin_threshold,
            method,
        )

        excess_d = [max(0.0, d - noise_val) for d in stripped_divergences]
        recommendation, reason = self._classify_recommendation(fingerprint)

        result = StabilityAuditResult(
            fingerprint=fingerprint,
            excess_divergences=excess_d,
            raw_divergences=raw_divergences,
            stripped_divergences=stripped_divergences,
            perturbation_kinds=perturbation_kinds,
            magnitudes=magnitudes_list,
            perturbations=perturbation_records,
            prompt_hash=prompt_hash,
            output_hash=output_hash,
            envelope_hash=envelope_hash,
            timestamp=timestamp,
            config_hash=config_hash,
            mode="observational",
            recommendation=recommendation,
            recommendation_reason=reason,
            budget_exceeded=budget_exceeded,
            calls_used=call_count,
            n_attempted=config.n_perturbations,
            n_completed=len(raw_divergences),
        )

        if receipt_system is not None:
            try:
                result = self._emit_receipt(result, receipt_system, config)
            except Exception:
                logger.warning("Failed to emit stability receipt", exc_info=True)

        return result

    def _partial_result(
        self,
        prompt_hash: str,
        output_hash: str,
        envelope_hash: str,
        config_hash: str,
        timestamp: str,
        calls_used: int,
        noise_floor: float,
        n_completed: int = 0,
    ) -> StabilityAuditResult:
        """Return partial result when budget exceeded."""
        fp = StabilityFingerprint(
            stiffness=0.0,
            anisotropy=1.0,
            basin_entropy=1.0,
            commutator_drift=0.0,
            noise_floor=noise_floor,
            control_divergence=0.0,
            stiffness_by_kind={},
            commutator_kinds=self.config.commutator_pair,
        )
        return StabilityAuditResult(
            fingerprint=fp,
            excess_divergences=[],
            raw_divergences=[],
            stripped_divergences=[],
            perturbation_kinds=[],
            magnitudes=[],
            perturbations=[],
            prompt_hash=prompt_hash,
            output_hash=output_hash,
            envelope_hash=envelope_hash,
            timestamp=timestamp,
            config_hash=config_hash,
            mode="observational",
            recommendation="calibrating",
            recommendation_reason="budget_exceeded: insufficient data",
            budget_exceeded=True,
            calls_used=calls_used,
            n_attempted=self.config.n_perturbations,
            n_completed=n_completed,
        )

    def _classify_recommendation(
        self, fp: StabilityFingerprint
    ) -> tuple[str, str]:
        """Classify stability and return (recommendation, reason).

        Thresholds are calibration placeholders — calibrate from data.
        """
        if fp.basin_entropy >= _BASIN_MULTIMODAL:
            return (
                "multimodal",
                f"basin_entropy={fp.basin_entropy:.1f} >= {_BASIN_MULTIMODAL}"
                f" (prompt near decision boundary)",
            )
        if fp.stiffness > _STIFFNESS_BRITTLE:
            return (
                "brittle",
                f"stiffness={fp.stiffness:.2f} > {_STIFFNESS_BRITTLE}"
                f" and anisotropy={fp.anisotropy:.2f}",
            )
        if (
            fp.stiffness < _STIFFNESS_STABLE
            and fp.anisotropy < _ANISOTROPY_STABLE
            and fp.basin_entropy <= _BASIN_STABLE
        ):
            return (
                "stable",
                f"stiffness={fp.stiffness:.2f} < {_STIFFNESS_STABLE},"
                f" anisotropy={fp.anisotropy:.2f} < {_ANISOTROPY_STABLE},"
                f" basins={fp.basin_entropy:.1f} <= {_BASIN_STABLE}",
            )
        return (
            "calibrating",
            f"stiffness={fp.stiffness:.2f},"
            f" anisotropy={fp.anisotropy:.2f},"
            f" basins={fp.basin_entropy:.1f}"
            f" (no threshold triggered)",
        )

    def _emit_receipt(
        self,
        result: StabilityAuditResult,
        receipt_system: Any,
        config: StabilityConfig,
    ) -> StabilityAuditResult:
        """Emit an observational gate receipt (verdict always 'observe').

        Uses GateReceiptSystem.emit() which handles evidence storage,
        receipt creation, and content-addressed hashing internally.
        """
        from .gate_receipt import canonical_json

        subject_bytes = canonical_json({
            "prompt_hash": result.prompt_hash,
            "output_hash": result.output_hash,
            "envelope_hash": result.envelope_hash,
        })

        evidence_dict = {
            "stiffness": result.fingerprint.stiffness,
            "anisotropy": result.fingerprint.anisotropy,
            "basin_entropy": result.fingerprint.basin_entropy,
            "commutator_drift": result.fingerprint.commutator_drift,
            "noise_floor": result.fingerprint.noise_floor,
            "control_divergence": result.fingerprint.control_divergence,
            "recommendation": result.recommendation,
            "recommendation_reason": result.recommendation_reason,
            "mode": result.mode,
        }

        receipt = receipt_system.emit(
            gate="semantic_stability",
            verdict="observe",
            subject_kind="stability_audit",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_dict,
            gate_config=config.to_dict(),
        )

        # Return result with receipt_id attached
        return StabilityAuditResult(
            fingerprint=result.fingerprint,
            excess_divergences=result.excess_divergences,
            raw_divergences=result.raw_divergences,
            stripped_divergences=result.stripped_divergences,
            perturbation_kinds=result.perturbation_kinds,
            magnitudes=result.magnitudes,
            perturbations=result.perturbations,
            prompt_hash=result.prompt_hash,
            output_hash=result.output_hash,
            envelope_hash=result.envelope_hash,
            timestamp=result.timestamp,
            config_hash=result.config_hash,
            mode=result.mode,
            recommendation=result.recommendation,
            recommendation_reason=result.recommendation_reason,
            budget_exceeded=result.budget_exceeded,
            calls_used=result.calls_used,
            receipt_id=receipt.receipt_id,
        )

    # -----------------------------------------------------------------
    # probe() — decision-producing stability probe
    # -----------------------------------------------------------------

    def probe(
        self,
        prompt: str,
        output: str,
        generate_fn: Callable[[str], str] | None = None,
        context: ProbeContext | None = None,
        receipt_system: Any | None = None,
        deep: bool = False,
        collector: Any | None = None,
    ) -> ProbeDecision:
        """Run a decision-producing stability probe.

        Unlike audit() which is purely observational, probe() produces an
        actionable decision (PROCEED/INCONCLUSIVE/MITIGATE/BLOCK/HUMAN_GATE)
        based on the stability fingerprint and the operational context.

        Args:
            prompt: The original prompt.
            output: The baseline output from the model.
            generate_fn: Model generation function. Required unless dry_run=True.
            context: Operational context (tools, risk, segments). Conservative defaults if None.
            receipt_system: Optional GateReceiptSystem for receipt emission.
            deep: If True, run full canary set (3 transforms) instead of default single.
            collector: Optional TelemetryCollector for failure telemetry.

        Returns:
            ProbeDecision with decision kind, trigger reasons, and mitigations.

        Raises:
            ValueError: If generate_fn is None and dry_run is False.
        """
        if context is None:
            context = ProbeContext()

        timestamp = datetime.now(timezone.utc).isoformat()

        # Validate generate_fn requirement
        if generate_fn is None and not context.dry_run:
            raise ValueError(
                "probe requires generate_fn or dry_run=True"
            )

        # Dry run: echo function, labeled as measurement failure
        measurement_failed = False
        if context.dry_run:
            generate_fn = lambda p: p  # noqa: E731
            measurement_failed = True

        # Select transforms
        selected_kinds = select_probe_transforms(context, deep=deep)

        # Build temporary config with only selected kinds + negation control
        # Force temperature=0 for deterministic probe runs
        probe_kinds = selected_kinds + [_NP]
        probe_config = StabilityConfig(
            n_perturbations=len(probe_kinds),
            kinds=probe_kinds,
            divergence_method=self.config.divergence_method,
            noise_floor_samples=self.config.noise_floor_samples,
            basin_threshold=self.config.basin_threshold,
            seed=self.config.seed,
            store_raw_outputs=False,
            sample_rate=1.0,  # Always run when explicitly probed
            max_generate_calls=self.config.max_generate_calls,
            commutator_pair=self.config.commutator_pair,
            decoding_params={"temperature": 0},
        )

        # Run via existing audit machinery
        probe_auditor = StabilityAuditor(probe_config)
        audit_result = probe_auditor.audit(
            prompt, output, generate_fn,
            receipt_system=None,  # We emit our own receipt below
        )

        # If audit itself exceeded budget, mark as measurement failure
        if audit_result.budget_exceeded:
            measurement_failed = True

        # Escalate
        decision_kind, trigger_reasons = _escalate(
            audit_result.recommendation, context, measurement_failed,
        )

        # Mitigations (only for MITIGATE or higher)
        mitigations: list[MitigationSuggestion] = []
        if decision_kind in (
            ProbeDecisionKind.MITIGATE,
            ProbeDecisionKind.BLOCK,
            ProbeDecisionKind.HUMAN_GATE,
        ):
            mitigations = select_mitigations(audit_result.fingerprint, context)

        # Compact fingerprint summary (4 floats)
        fp = audit_result.fingerprint
        fingerprint_summary = {
            "stiffness": fp.stiffness,
            "anisotropy": fp.anisotropy,
            "basin_entropy": fp.basin_entropy,
            "escape_rate": fp.escape_rate,
        }

        result = ProbeDecision(
            decision=decision_kind.value,
            trigger_reasons=trigger_reasons,
            transforms_run=selected_kinds,
            mitigations=[m.to_dict() for m in mitigations],
            recommendation=audit_result.recommendation,
            measurement_failed=measurement_failed,
            fingerprint_summary=fingerprint_summary,
            timestamp=timestamp,
        )

        # Emit receipt
        if receipt_system is not None:
            try:
                from .gate_receipt import canonical_json

                subject_bytes = canonical_json({
                    "prompt_hash": audit_result.prompt_hash,
                    "output_hash": audit_result.output_hash,
                })
                evidence_dict = {
                    "decision": result.decision,
                    "recommendation": result.recommendation,
                    "measurement_failed": result.measurement_failed,
                    "transforms_run": result.transforms_run,
                    "stiffness": fp.stiffness,
                    "anisotropy": fp.anisotropy,
                    "basin_entropy": fp.basin_entropy,
                    "escape_rate": fp.escape_rate,
                }
                verdict = _PROBE_DECISION_TO_VERDICT.get(result.decision, "observe")
                receipt = receipt_system.emit(
                    gate="stability_probe",
                    verdict=verdict,
                    subject_kind="stability_probe",
                    subject_bytes=subject_bytes,
                    evidence_bundle=evidence_dict,
                    gate_config=probe_config.to_dict(),
                )
                result.receipt_id = receipt.receipt_id
            except Exception:
                logger.warning("Failed to emit stability probe receipt", exc_info=True)

        # Emit telemetry
        if collector is not None:
            try:
                unstable_axes = [m.axis for m in mitigations]
                collector.record_stability_probe(
                    decision=result.decision,
                    recommendation=result.recommendation,
                    transforms_run=selected_kinds,
                    mitigations_suggested=len(mitigations),
                    measurement_failed=measurement_failed,
                    budget_exceeded=audit_result.budget_exceeded,
                    stiffness=fp.stiffness,
                    escape_rate=fp.escape_rate,
                    unstable_axes=unstable_axes,
                )
            except Exception:
                logger.debug("Failed to emit probe telemetry", exc_info=True)

        return result


# =============================================================================
# Store + Persistence
# =============================================================================


class StabilityStore:
    """JSONL persistence for stability audit results.

    Append: O_APPEND + os.write() single newline-terminated line.
    File lock: fcntl.flock() on Linux/macOS, no-op on platforms without fcntl.
    Tolerates partial last line on read (drops it, logs warning).
    """

    def __init__(self, gov_dir: Path) -> None:
        self.dir = gov_dir / "stability"
        self.log_path = self.dir / "audit_log.jsonl"

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def append(self, result: StabilityAuditResult) -> None:
        """Append a single audit result as a JSONL line."""
        self._ensure_dir()
        line = (
            json.dumps(result.to_dict(), separators=(",", ":"), sort_keys=True)
            + "\n"
        )
        data = line.encode("utf-8")

        fd = os.open(
            str(self.log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644
        )
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                os.write(fd, data)
            finally:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def query(self, limit: int = 50) -> list[StabilityAuditResult]:
        """Read audit results, newest first.  Tolerates partial/corrupted lines."""
        if not self.log_path.exists():
            return []

        results: list[StabilityAuditResult] = []
        try:
            text = self.log_path.read_text(encoding="utf-8")
        except Exception:
            logger.warning("Failed to read stability log", exc_info=True)
            return []

        lines = text.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                results.append(StabilityAuditResult.from_dict(d))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                if i == len(lines) - 1:
                    logger.debug("Dropping partial last line in stability log")
                else:
                    logger.warning(
                        "Skipping corrupted line %d in stability log: %s", i, e
                    )

        results.reverse()
        return results[:limit]

    def count(self) -> int:
        """Count audit results without deserializing.  O(lines), not O(parse)."""
        if not self.log_path.exists():
            return 0
        try:
            text = self.log_path.read_text(encoding="utf-8")
        except Exception:
            return 0
        return sum(1 for line in text.split("\n") if line.strip())

    def get_distribution(self, metric: str, limit: int = 10000) -> list[float]:
        """Extract a specific metric from audit results."""
        results = self.query(limit=limit)
        values: list[float] = []
        for r in results:
            fp = r.fingerprint
            val = getattr(fp, metric, None)
            if isinstance(val, (int, float)):
                values.append(float(val))
        return values
