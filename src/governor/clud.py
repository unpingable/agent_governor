# SPDX-License-Identifier: Apache-2.0
"""
CLUD Clarity Sensor: compression-based precision detection.

If a claim can't survive compression to simple language without changing
meaning, it was never precise — it was *performing* precision.

This module ships the contract + regression harness (2.x).  Real LLM
backends are deferred to 3.x; all five pipeline stages are Protocol
interfaces backed by fake implementations in tests.

See docs/CLUD_CLARITY_SENSOR.md for the full spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


# =============================================================================
# Enums
# =============================================================================


class ClaimKind(str, Enum):
    """What kind of claim is being made."""

    DESCRIPTIVE = "descriptive"  # "X happens"
    NORMATIVE = "normative"  # "should/must"
    PROCEDURAL = "procedural"  # "do A then B"


class DeltaClass(str, Enum):
    """Semantic distance between original and compressed claim."""

    PRESERVED = "preserved"  # same meaning, simpler words
    INCOMPLETE = "incomplete"  # compressed lost some detail
    AMBIGUOUS = "ambiguous"  # compressed is ambiguous where original wasn't
    INFLATED = "inflated"  # original complexity wasn't load-bearing


class CludStatus(str, Enum):
    """Verdict for a clud analysis."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ArtifactGoal(str, Enum):
    """What the text is trying to be.  Controls threshold selection."""

    PROSE = "prose"
    POLICY = "policy"
    RATIONALE = "rationale"
    SPEC = "spec"
    COMMIT_MSG = "commit_msg"


# =============================================================================
# Constants (all policy-hashable)
# =============================================================================

DELTA_WEIGHTS: dict[DeltaClass, float] = {
    DeltaClass.PRESERVED: 0.0,
    DeltaClass.INCOMPLETE: 0.4,
    DeltaClass.AMBIGUOUS: 0.7,
    DeltaClass.INFLATED: 1.0,
}

PADDING_SMELL_RATIO = 0.5
CLUD_SCHEMA_VERSION = 1

# Minimum claims before drift_score alone can trigger FAIL.
# Below this, only hard signals (inflated count) trigger FAIL —
# drift_score is too noisy on small artifacts.
MIN_CLAIMS_FOR_DRIFT_FAIL = 3


# =============================================================================
# Threshold sets (per artifact_goal)
# =============================================================================


@dataclass(frozen=True)
class ThresholdSet:
    """Verdict thresholds for a given artifact goal."""

    warn_drift: float  # drift_score >= this → WARN
    fail_drift: float  # drift_score >= this → FAIL (if enough claims)
    min_claims_for_drift_fail: int  # below this, drift alone can't FAIL


# All goals currently use the same values.  The structure exists so
# tightening policy/safety or loosening commit_msg is additive, not
# a breaking change.
DEFAULT_THRESHOLDS = ThresholdSet(
    warn_drift=0.15,
    fail_drift=0.40,
    min_claims_for_drift_fail=MIN_CLAIMS_FOR_DRIFT_FAIL,
)

THRESHOLD_BY_GOAL: dict[ArtifactGoal, ThresholdSet] = {
    ArtifactGoal.PROSE: DEFAULT_THRESHOLDS,
    ArtifactGoal.POLICY: DEFAULT_THRESHOLDS,
    ArtifactGoal.RATIONALE: DEFAULT_THRESHOLDS,
    ArtifactGoal.SPEC: DEFAULT_THRESHOLDS,
    ArtifactGoal.COMMIT_MSG: DEFAULT_THRESHOLDS,
}


def thresholds_for(artifact_goal: str | ArtifactGoal) -> ThresholdSet:
    """Look up thresholds for an artifact goal, falling back to defaults.

    Accepts both ArtifactGoal enum and raw strings (normalized to lowercase).
    """
    if isinstance(artifact_goal, ArtifactGoal):
        return THRESHOLD_BY_GOAL.get(artifact_goal, DEFAULT_THRESHOLDS)
    try:
        goal = ArtifactGoal(artifact_goal.lower())
    except ValueError:
        return DEFAULT_THRESHOLDS
    return THRESHOLD_BY_GOAL.get(goal, DEFAULT_THRESHOLDS)


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class CludContext:
    """Structured context for the compression pipeline."""

    glossary: dict[str, str] = field(default_factory=dict)
    audience: str = "developer"
    artifact_goal: ArtifactGoal = ArtifactGoal.PROSE
    must_preserve: tuple[str, ...] = ()

    def __init__(
        self,
        glossary: dict[str, str] | None = None,
        audience: str = "developer",
        artifact_goal: str | ArtifactGoal = ArtifactGoal.PROSE,
        must_preserve: tuple[str, ...] = (),
    ) -> None:
        object.__setattr__(self, "glossary", glossary if glossary is not None else {})
        object.__setattr__(self, "audience", audience)
        # Normalize string → ArtifactGoal (case-insensitive)
        if isinstance(artifact_goal, ArtifactGoal):
            object.__setattr__(self, "artifact_goal", artifact_goal)
        else:
            try:
                object.__setattr__(
                    self, "artifact_goal", ArtifactGoal(artifact_goal.lower())
                )
            except ValueError:
                raise ValueError(
                    f"Unknown artifact_goal: {artifact_goal!r}. "
                    f"Valid: {[g.value for g in ArtifactGoal]}"
                )
        object.__setattr__(self, "must_preserve", must_preserve)

    def to_dict(self) -> dict[str, Any]:
        return {
            "glossary": dict(self.glossary),
            "audience": self.audience,
            "artifact_goal": self.artifact_goal.value,
            "must_preserve": list(self.must_preserve),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CludContext:
        return cls(
            glossary=dict(data.get("glossary", {})),
            audience=data.get("audience", "developer"),
            artifact_goal=data.get("artifact_goal", "prose"),
            must_preserve=tuple(data.get("must_preserve", ())),
        )


@dataclass(frozen=True)
class CludClaim:
    """A single claim after pipeline processing."""

    original: str
    kind: ClaimKind
    compressed: str | None  # None when cannot_compress
    cannot_compress_reason: str | None
    uncertainty: str | None
    delta: DeltaClass
    falsifiable: bool
    falsification: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "kind": self.kind.value,
            "compressed": self.compressed,
            "cannot_compress_reason": self.cannot_compress_reason,
            "uncertainty": self.uncertainty,
            "delta": self.delta.value,
            "falsifiable": self.falsifiable,
            "falsification": self.falsification,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CludClaim:
        try:
            kind = ClaimKind(data["kind"])
        except ValueError:
            raise ValueError(f"Unknown ClaimKind: {data['kind']!r}")
        try:
            delta = DeltaClass(data["delta"])
        except ValueError:
            raise ValueError(f"Unknown DeltaClass: {data['delta']!r}")
        return cls(
            original=data["original"],
            kind=kind,
            compressed=data.get("compressed"),
            cannot_compress_reason=data.get("cannot_compress_reason"),
            uncertainty=data.get("uncertainty"),
            delta=delta,
            falsifiable=data["falsifiable"],
            falsification=data.get("falsification"),
        )


@dataclass
class CludResult:
    """Full result of a clud analysis."""

    schema_version: int
    status: CludStatus
    claims: list[CludClaim]
    drift_score: float
    hidden_assumptions: list[str]
    missing_definitions: list[str]
    unfalsifiable_claims: list[tuple[str, ClaimKind]]
    padded_or_implicit: bool
    sentence_count: int
    claim_count: int
    summary: str
    thresholds_used: ThresholdSet = field(default_factory=lambda: DEFAULT_THRESHOLDS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "claims": [c.to_dict() for c in self.claims],
            "drift_score": self.drift_score,
            "hidden_assumptions": list(self.hidden_assumptions),
            "missing_definitions": list(self.missing_definitions),
            "unfalsifiable_claims": [
                [text, kind.value] for text, kind in self.unfalsifiable_claims
            ],
            "padded_or_implicit": self.padded_or_implicit,
            "sentence_count": self.sentence_count,
            "claim_count": self.claim_count,
            "summary": self.summary,
            "thresholds_used": {
                "warn_drift": self.thresholds_used.warn_drift,
                "fail_drift": self.thresholds_used.fail_drift,
                "min_claims_for_drift_fail": self.thresholds_used.min_claims_for_drift_fail,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CludResult:
        sv = data.get("schema_version", 1)
        if sv > CLUD_SCHEMA_VERSION:
            raise ValueError(
                f"Schema version {sv} > supported {CLUD_SCHEMA_VERSION}"
            )
        try:
            status = CludStatus(data["status"])
        except ValueError:
            raise ValueError(f"Unknown CludStatus: {data['status']!r}")
        claims = [CludClaim.from_dict(c) for c in data.get("claims", [])]
        unfalsifiable = [
            (text, ClaimKind(kind))
            for text, kind in data.get("unfalsifiable_claims", [])
        ]
        t_data = data.get("thresholds_used")
        if t_data:
            thresholds = ThresholdSet(
                warn_drift=t_data["warn_drift"],
                fail_drift=t_data["fail_drift"],
                min_claims_for_drift_fail=t_data["min_claims_for_drift_fail"],
            )
        else:
            thresholds = DEFAULT_THRESHOLDS
        return cls(
            schema_version=sv,
            status=status,
            claims=claims,
            drift_score=data["drift_score"],
            hidden_assumptions=list(data.get("hidden_assumptions", [])),
            missing_definitions=list(data.get("missing_definitions", [])),
            unfalsifiable_claims=unfalsifiable,
            padded_or_implicit=data["padded_or_implicit"],
            sentence_count=data["sentence_count"],
            claim_count=data["claim_count"],
            summary=data.get("summary", ""),
            thresholds_used=thresholds,
        )


# =============================================================================
# Sentence splitter (deterministic, no NLP deps)
# =============================================================================

_SENTENCE_RE = re.compile(r"[.!?]+(?:\s|$)")


def count_sentences(text: str) -> int:
    """Split on .?! with minimal heuristics.  Documented, testable."""
    stripped = text.strip()
    if not stripped:
        return 1
    parts = _SENTENCE_RE.split(stripped)
    return max(1, sum(1 for p in parts if p.strip()))


# =============================================================================
# Drift score
# =============================================================================


def compute_drift_score(claims: list[CludClaim]) -> float:
    """Weighted average of delta classifications.

    When cannot_compress is set, delta is forced to INFLATED by the
    orchestrator, so DELTA_WEIGHTS[INFLATED] = 1.0 flows through.
    """
    if not claims:
        return 0.0
    total = sum(DELTA_WEIGHTS[c.delta] for c in claims)
    return total / len(claims)


# =============================================================================
# Verdict (severity ceiling: FAIL > WARN > PASS)
# =============================================================================


def compute_verdict(
    claims: list[CludClaim],
    drift_score: float,
    thresholds: ThresholdSet | None = None,
) -> CludStatus:
    """Severity ceiling — FAIL beats WARN beats PASS.

    FAIL triggers:
      - Any INFLATED claim (hard signal, always FAIL)
      - drift_score >= fail_drift AND len(claims) >= min_claims_for_drift_fail
        (drift is noisy on small artifacts — require statistical mass)

    WARN triggers:
      - Any AMBIGUOUS, INCOMPLETE, or unfalsifiable claim
      - drift_score >= warn_drift
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    if not claims:
        return CludStatus.PASS

    inflated = sum(1 for c in claims if c.delta == DeltaClass.INFLATED)
    ambiguous = sum(1 for c in claims if c.delta == DeltaClass.AMBIGUOUS)
    incomplete = sum(1 for c in claims if c.delta == DeltaClass.INCOMPLETE)
    unfalsifiable = sum(1 for c in claims if not c.falsifiable)

    # FAIL-first: inflated is always hard-FAIL; drift needs enough claims
    drift_fail = (
        drift_score >= thresholds.fail_drift
        and len(claims) >= thresholds.min_claims_for_drift_fail
    )
    if inflated > 0 or drift_fail:
        return CludStatus.FAIL

    if (
        ambiguous > 0
        or incomplete > 0
        or unfalsifiable > 0
        or drift_score >= thresholds.warn_drift
    ):
        return CludStatus.WARN
    return CludStatus.PASS


# =============================================================================
# Pipeline Protocols (5 stages)
# =============================================================================


class Extractor(Protocol):
    """Stage 1: split text into individual claims with kinds."""

    def __call__(
        self, text: str, context: CludContext
    ) -> list[dict[str, str]]:
        """Return dicts with keys: 'original', 'kind'."""
        ...


class Compressor(Protocol):
    """Stage 2: compress a claim to simple language."""

    def __call__(self, claim: str, context: CludContext) -> dict[str, str]:
        """Return exactly one of: {'compressed': str} or {'cannot_compress_reason': str}."""
        ...


class UncertaintySurfacer(Protocol):
    """Stage 3: surface hidden uncertainty between original and compressed."""

    def __call__(self, original: str, compressed: str) -> str | None:
        """Return uncertainty description or None."""
        ...


class DeltaChecker(Protocol):
    """Stage 4: classify semantic distance."""

    def __call__(
        self,
        original: str,
        compressed: str | None,
        cannot_compress_reason: str | None,
    ) -> DeltaClass:
        """Return the delta classification."""
        ...


class FalsifiabilityChecker(Protocol):
    """Stage 5: check if a claim can be tested."""

    def __call__(
        self, claim: str, kind: ClaimKind
    ) -> tuple[bool, str | None]:
        """Return (falsifiable, falsification_description)."""
        ...


# =============================================================================
# Protocol error
# =============================================================================


class CludProtocolError(ValueError):
    """Raised when a pipeline stage returns malformed output."""


# =============================================================================
# CludSensor orchestrator
# =============================================================================


class CludSensor:
    """Orchestrates the five pipeline stages into a CludResult.

    All stages are injected via Protocol interfaces.  In 2.x these are
    backed by fake/deterministic implementations; 3.x wires real LLM backends.
    """

    def __init__(
        self,
        extractor: Extractor,
        compressor: Compressor,
        surfacer: UncertaintySurfacer,
        delta_checker: DeltaChecker,
        falsifier: FalsifiabilityChecker,
    ) -> None:
        self._extractor = extractor
        self._compressor = compressor
        self._surfacer = surfacer
        self._delta_checker = delta_checker
        self._falsifier = falsifier

    def analyze(
        self, text: str, context: CludContext | None = None
    ) -> CludResult:
        """Run the full pipeline and return a CludResult."""
        if context is None:
            context = CludContext()

        sentence_count = count_sentences(text)

        # Stage 1: Extraction
        raw_claims = self._extractor(text, context)
        for i, rc in enumerate(raw_claims):
            if "original" not in rc or "kind" not in rc:
                raise CludProtocolError(
                    f"Extractor claim [{i}] missing 'original' or 'kind': "
                    f"got keys {sorted(rc.keys())}"
                )
            try:
                ClaimKind(rc["kind"])
            except ValueError:
                raise CludProtocolError(
                    f"Extractor claim [{i}] unknown kind: {rc['kind']!r}"
                )

        claims: list[CludClaim] = []
        hidden_assumptions: list[str] = []
        missing_definitions: list[str] = []
        unfalsifiable_claims: list[tuple[str, ClaimKind]] = []

        for rc in raw_claims:
            original = rc["original"]
            kind = ClaimKind(rc["kind"])

            # Stage 2: Compression
            comp_result = self._compressor(original, context)
            has_compressed = "compressed" in comp_result
            has_cannot = "cannot_compress_reason" in comp_result
            if has_compressed == has_cannot:
                raise CludProtocolError(
                    f"Compressor must return exactly one of 'compressed' or "
                    f"'cannot_compress_reason', got: {sorted(comp_result.keys())}"
                )

            compressed = comp_result.get("compressed")
            cannot_compress_reason = comp_result.get("cannot_compress_reason")

            # Stage 3: Uncertainty surfacing (only when we have both forms)
            uncertainty: str | None = None
            if compressed is not None:
                uncertainty = self._surfacer(original, compressed)
                if uncertainty:
                    hidden_assumptions.append(uncertainty)

            # Stage 4: Delta classification
            if cannot_compress_reason is not None:
                # Force INFLATED regardless of checker
                delta = DeltaClass.INFLATED
            else:
                delta = self._delta_checker(
                    original, compressed, cannot_compress_reason
                )

            # Stage 5: Falsifiability
            falsifiable, falsification = self._falsifier(original, kind)
            if not falsifiable:
                unfalsifiable_claims.append((original, kind))

            claims.append(
                CludClaim(
                    original=original,
                    kind=kind,
                    compressed=compressed,
                    cannot_compress_reason=cannot_compress_reason,
                    uncertainty=uncertainty,
                    delta=delta,
                    falsifiable=falsifiable,
                    falsification=falsification,
                )
            )

        claim_count = len(claims)
        padded_or_implicit = (
            claim_count < sentence_count * PADDING_SMELL_RATIO
        )

        drift_score = compute_drift_score(claims)
        thresholds = thresholds_for(context.artifact_goal)
        status = compute_verdict(claims, drift_score, thresholds)

        return CludResult(
            schema_version=CLUD_SCHEMA_VERSION,
            status=status,
            claims=claims,
            drift_score=drift_score,
            hidden_assumptions=hidden_assumptions,
            missing_definitions=missing_definitions,
            unfalsifiable_claims=unfalsifiable_claims,
            padded_or_implicit=padded_or_implicit,
            sentence_count=sentence_count,
            claim_count=claim_count,
            summary="",
            thresholds_used=thresholds,
        )
