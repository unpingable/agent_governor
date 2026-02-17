# SPDX-License-Identifier: Apache-2.0
"""
Detector Integration — Temporal Coherence Signals as Governor Evidence.

Sensor/controller boundary for Δt temporal coherence signals from an external
hallucination detector. The detector is a separate project that measures
per-token behavioral coherence. This module defines the integration contract:
detector as sensor, governor as controller, connected via file artifacts.

Spec: DETECTOR_INTEGRATION_SPEC.md (Layer 1, Item #4 of AG2 build order)

Invariant: No torch, no token loop, no generation-time code. The boundary is
a JSON file and a checksum.

Key properties:
  - Signal collapse: 19 raw dimensions → 5 control signals
  - Monotonic influence: signals can only tighten, never loosen
  - Failure-safe: silence from sensor = higher evidence bar
  - Optional dependency: governor works without detector signals
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PhaseFlag(str, Enum):
    """Dominant generation phase detected by the temporal coherence detector."""

    SEARCHY = "searchy"
    """Model appears to be searching/retrieving — high entropy, unstable confidence."""

    CONFAB = "confab"
    """Confabulation pattern — high confidence + low grounding, unstable trajectory."""

    DELIBERATE = "deliberate"
    """Deliberate reasoning — stable confidence, low entropy, evidence of planning."""

    REFUSAL = "refusal"
    """Model is refusing/declining — characteristic entropy + confidence patterns."""

    UNKNOWN = "unknown"
    """Phase could not be determined."""


class SignalQuality(str, Enum):
    """Overall quality classification of detector signals."""

    CLEAN = "clean"
    """High coherence, low fragility. Default thresholds apply."""

    UNCERTAIN = "uncertain"
    """Middle range. Modest tightening — raise evidence requirements."""

    DIRTY = "dirty"
    """Low coherence, high overconfidence. Aggressive tightening required."""


class GovernorAction(str, Enum):
    """Actions the governor can take in response to detector signals."""

    NO_CHANGE = "no_change"
    """Default thresholds apply."""

    RAISE_EVIDENCE = "raise_evidence"
    """Require higher evidence tier (TOOL_TRACE)."""

    FORCE_QUORUM = "force_quorum"
    """Force multi-model quorum before claim acceptance."""

    CAP_CONFIDENCE = "cap_confidence"
    """Cap claim confidence and require citations."""

    MARK_SOFT = "mark_soft"
    """Mark claims as SOFT regardless of language assertiveness."""

    BLOCK_WRITES = "block_writes"
    """Block ledger writes; mark response as unsafe to act on."""


# ---------------------------------------------------------------------------
# Signal Key (Detector ↔ Governor Join)
# ---------------------------------------------------------------------------


@dataclass
class SignalKey:
    """Join key between detector signal and governor claims."""

    run_id: str
    turn_id: str
    response_hash: str
    model_id: str
    timestamp: datetime
    byte_range: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "run_id": self.run_id,
            "turn_id": self.turn_id,
            "response_hash": self.response_hash,
            "model_id": self.model_id,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.byte_range is not None:
            d["byte_range"] = list(self.byte_range)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SignalKey:
        br = d.get("byte_range")
        return cls(
            run_id=d["run_id"],
            turn_id=d["turn_id"],
            response_hash=d["response_hash"],
            model_id=d["model_id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            byte_range=tuple(br) if br else None,
        )

    @classmethod
    def from_response(cls, response_text: str, model_id: str, run_id: str = "", turn_id: str = "") -> SignalKey:
        """Create a signal key from a response text."""
        response_hash = hashlib.sha256(response_text.encode()).hexdigest()
        return cls(
            run_id=run_id,
            turn_id=turn_id,
            response_hash=response_hash,
            model_id=model_id,
            timestamp=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Raw Signal (19 dimensions from detector)
# ---------------------------------------------------------------------------


@dataclass
class RawDetectorSignal:
    """Raw 19-dimension signal from the Δt Hallucination Detector.

    These dimensions are produced by the external detector project.
    The governor collapses them to 5 control signals.
    """

    # Temporal debt dimensions
    temporal_debt: float = 0.0
    confidence_slope: float = 0.0
    acceleration: float = 0.0

    # Entropy dimensions
    max_entropy_jump: float = 0.0
    entropy_recovery_detected: bool = False
    entropy_variance: float = 0.0

    # Perturbation dimensions
    token_jaccard: float = 1.0
    perturbation_sensitivity: float = 0.0

    # Confidence dimensions
    tokens_to_high_conf: int = 0
    confidence_monotonicity: float = 0.0

    # Phase dimensions
    early_phase_entropy: float = 0.0
    mid_phase_entropy: float = 0.0
    late_phase_entropy: float = 0.0
    early_phase_confidence: float = 0.0
    mid_phase_confidence: float = 0.0
    late_phase_confidence: float = 0.0

    # Aggregate dimensions
    mean_logprob: float = 0.0
    response_length: int = 0
    unique_token_ratio: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "temporal_debt": self.temporal_debt,
            "confidence_slope": self.confidence_slope,
            "acceleration": self.acceleration,
            "max_entropy_jump": self.max_entropy_jump,
            "entropy_recovery_detected": self.entropy_recovery_detected,
            "entropy_variance": self.entropy_variance,
            "token_jaccard": self.token_jaccard,
            "perturbation_sensitivity": self.perturbation_sensitivity,
            "tokens_to_high_conf": self.tokens_to_high_conf,
            "confidence_monotonicity": self.confidence_monotonicity,
            "early_phase_entropy": self.early_phase_entropy,
            "mid_phase_entropy": self.mid_phase_entropy,
            "late_phase_entropy": self.late_phase_entropy,
            "early_phase_confidence": self.early_phase_confidence,
            "mid_phase_confidence": self.mid_phase_confidence,
            "late_phase_confidence": self.late_phase_confidence,
            "mean_logprob": self.mean_logprob,
            "response_length": self.response_length,
            "unique_token_ratio": self.unique_token_ratio,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RawDetectorSignal:
        return cls(
            temporal_debt=d.get("temporal_debt", 0.0),
            confidence_slope=d.get("confidence_slope", 0.0),
            acceleration=d.get("acceleration", 0.0),
            max_entropy_jump=d.get("max_entropy_jump", 0.0),
            entropy_recovery_detected=d.get("entropy_recovery_detected", False),
            entropy_variance=d.get("entropy_variance", 0.0),
            token_jaccard=d.get("token_jaccard", 1.0),
            perturbation_sensitivity=d.get("perturbation_sensitivity", 0.0),
            tokens_to_high_conf=d.get("tokens_to_high_conf", 0),
            confidence_monotonicity=d.get("confidence_monotonicity", 0.0),
            early_phase_entropy=d.get("early_phase_entropy", 0.0),
            mid_phase_entropy=d.get("mid_phase_entropy", 0.0),
            late_phase_entropy=d.get("late_phase_entropy", 0.0),
            early_phase_confidence=d.get("early_phase_confidence", 0.0),
            mid_phase_confidence=d.get("mid_phase_confidence", 0.0),
            late_phase_confidence=d.get("late_phase_confidence", 0.0),
            mean_logprob=d.get("mean_logprob", 0.0),
            response_length=d.get("response_length", 0),
            unique_token_ratio=d.get("unique_token_ratio", 0.0),
        )


# ---------------------------------------------------------------------------
# Collapsed Signal (5 control signals)
# ---------------------------------------------------------------------------


@dataclass
class CollapsedSignal:
    """5 control signals collapsed from 19 raw detector dimensions.

    These are what the governor reasons about. The collapse function
    lives in the governor (not the detector) so the governor controls
    its own intake.
    """

    coherence_score: float = 1.0
    """Stability of confidence trajectory. 0.0=unstable, 1.0=stable."""

    instability_spikes: int = 0
    """Number of entropy spikes above profile threshold."""

    perturbation_fragility: float = 0.0
    """How much output changes under perturbation. 0.0=robust, 1.0=fragile."""

    overconfidence_signature: float = 0.0
    """High confidence + low grounding proxy. 0.0=grounded, 1.0=overconfident."""

    phase_flag: PhaseFlag = PhaseFlag.UNKNOWN
    """Dominant generation phase."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "coherence_score": self.coherence_score,
            "instability_spikes": self.instability_spikes,
            "perturbation_fragility": self.perturbation_fragility,
            "overconfidence_signature": self.overconfidence_signature,
            "phase_flag": self.phase_flag.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CollapsedSignal:
        return cls(
            coherence_score=d.get("coherence_score", 1.0),
            instability_spikes=d.get("instability_spikes", 0),
            perturbation_fragility=d.get("perturbation_fragility", 0.0),
            overconfidence_signature=d.get("overconfidence_signature", 0.0),
            phase_flag=PhaseFlag(d.get("phase_flag", "unknown")),
        )

    @property
    def quality(self) -> SignalQuality:
        """Classify the overall signal quality."""
        if (
            self.coherence_score > 0.8
            and self.perturbation_fragility < 0.2
            and self.overconfidence_signature < 0.3
            and self.phase_flag != PhaseFlag.CONFAB
        ):
            return SignalQuality.CLEAN
        if (
            self.coherence_score < 0.4
            or self.overconfidence_signature > 0.6
            or self.phase_flag == PhaseFlag.CONFAB
        ):
            return SignalQuality.DIRTY
        return SignalQuality.UNCERTAIN

    def to_evidence_span(self) -> str:
        """Format as evidence span string for EvidenceRef."""
        return (
            f"coherence_score={self.coherence_score:.2f}; "
            f"fragility={self.perturbation_fragility:.2f}; "
            f"phase={self.phase_flag.value}"
        )


# ---------------------------------------------------------------------------
# Signal-to-Action Policy
# ---------------------------------------------------------------------------


@dataclass
class SignalPolicy:
    """Configurable thresholds for signal-to-action mapping."""

    coherence_threshold: float = 0.4
    """Below this coherence, raise evidence requirements."""

    spike_threshold: int = 3
    """Above this many spikes, force quorum."""

    fragility_threshold: float = 0.7
    """Above this fragility, mark claims as SOFT."""

    overconfidence_threshold: float = 0.6
    """Above this overconfidence, cap confidence and require citations."""

    confab_blocks_writes: bool = True
    """If True, confab phase flag blocks ledger writes entirely."""

    # Failure-safe defaults
    unavailable_penalty: float = 0.5
    """Overconfidence penalty applied when detector is unavailable."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "coherence_threshold": self.coherence_threshold,
            "spike_threshold": self.spike_threshold,
            "fragility_threshold": self.fragility_threshold,
            "overconfidence_threshold": self.overconfidence_threshold,
            "confab_blocks_writes": self.confab_blocks_writes,
            "unavailable_penalty": self.unavailable_penalty,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SignalPolicy:
        return cls(
            coherence_threshold=d.get("coherence_threshold", 0.4),
            spike_threshold=d.get("spike_threshold", 3),
            fragility_threshold=d.get("fragility_threshold", 0.7),
            overconfidence_threshold=d.get("overconfidence_threshold", 0.6),
            confab_blocks_writes=d.get("confab_blocks_writes", True),
            unavailable_penalty=d.get("unavailable_penalty", 0.5),
        )


@dataclass
class SignalActionResult:
    """Result of applying signal-to-action mapping."""

    actions: list[GovernorAction]
    confidence_cap: float | None = None
    evidence_tier: str | None = None
    reason: str = ""
    signal_quality: SignalQuality = SignalQuality.CLEAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [a.value for a in self.actions],
            "confidence_cap": self.confidence_cap,
            "evidence_tier": self.evidence_tier,
            "reason": self.reason,
            "signal_quality": self.signal_quality.value,
        }


# ---------------------------------------------------------------------------
# Signal Collapse Function
# ---------------------------------------------------------------------------


def collapse_signal(raw: RawDetectorSignal) -> CollapsedSignal:
    """Collapse 19 raw detector dimensions to 5 control signals.

    The collapse function lives in the governor so it controls its own intake.
    """
    # Coherence score: inversely related to temporal debt + instability
    # Higher temporal debt and acceleration → lower coherence
    coherence = 1.0 - min(1.0, abs(raw.temporal_debt) + abs(raw.acceleration) * 0.5)
    # Factor in confidence slope instability
    if abs(raw.confidence_slope) > 0.5:
        coherence *= 0.8

    coherence = max(0.0, min(1.0, coherence))

    # Instability spikes: count of entropy jumps
    spikes = 0
    if raw.max_entropy_jump > 0.5:
        spikes += 1
    if raw.max_entropy_jump > 1.0:
        spikes += 1
    if raw.entropy_recovery_detected:
        spikes += 1
    if raw.entropy_variance > 0.3:
        spikes += 1

    # Perturbation fragility
    fragility = 1.0 - raw.token_jaccard  # Low jaccard = high fragility
    fragility = max(fragility, raw.perturbation_sensitivity)
    fragility = max(0.0, min(1.0, fragility))

    # Overconfidence signature
    # Quick high confidence + monotonic confidence + low entropy variance
    overconfidence = 0.0
    if raw.tokens_to_high_conf > 0 and raw.tokens_to_high_conf < 20:
        overconfidence += 0.3  # Suspiciously fast to high confidence
    if raw.confidence_monotonicity > 0.8:
        overconfidence += 0.3  # Too smooth — real reasoning has bumps
    if raw.entropy_variance < 0.1 and raw.response_length > 0:
        overconfidence += 0.2  # Low entropy variance suggests rote recall
    overconfidence = max(0.0, min(1.0, overconfidence))

    # Phase flag: classify dominant generation phase
    phase = _classify_phase(raw)

    return CollapsedSignal(
        coherence_score=round(coherence, 3),
        instability_spikes=spikes,
        perturbation_fragility=round(fragility, 3),
        overconfidence_signature=round(overconfidence, 3),
        phase_flag=phase,
    )


def _classify_phase(raw: RawDetectorSignal) -> PhaseFlag:
    """Classify the dominant generation phase from raw signal features."""
    # High early entropy + declining = searchy
    if raw.early_phase_entropy > 0.7 and raw.late_phase_entropy < 0.3:
        return PhaseFlag.SEARCHY

    # High confidence throughout + low entropy = potential confab
    avg_conf = (raw.early_phase_confidence + raw.mid_phase_confidence + raw.late_phase_confidence) / 3
    avg_entropy = (raw.early_phase_entropy + raw.mid_phase_entropy + raw.late_phase_entropy) / 3
    if avg_conf > 0.8 and avg_entropy < 0.2:
        return PhaseFlag.CONFAB

    # Very low confidence + high entropy = refusal
    if avg_conf < 0.2 and avg_entropy > 0.7:
        return PhaseFlag.REFUSAL

    # Moderate, stable values = deliberate
    if 0.3 <= avg_conf <= 0.8 and raw.entropy_variance < 0.3:
        return PhaseFlag.DELIBERATE

    return PhaseFlag.UNKNOWN


# ---------------------------------------------------------------------------
# Signal-to-Action Mapping
# ---------------------------------------------------------------------------


def map_signal_to_actions(
    signal: CollapsedSignal,
    policy: SignalPolicy | None = None,
) -> SignalActionResult:
    """Map collapsed detector signals to governor enforcement actions.

    Monotonic: signals can only tighten constraints, never loosen them.
    A clean signal results in no change (default thresholds apply).
    """
    policy = policy or SignalPolicy()
    actions: list[GovernorAction] = []
    confidence_cap: float | None = None
    evidence_tier: str | None = None
    reasons: list[str] = []

    # Check each threshold
    if signal.coherence_score < policy.coherence_threshold:
        actions.append(GovernorAction.RAISE_EVIDENCE)
        evidence_tier = "TOOL_TRACE"
        reasons.append(f"coherence {signal.coherence_score:.2f} < {policy.coherence_threshold}")

    if signal.instability_spikes > policy.spike_threshold:
        actions.append(GovernorAction.FORCE_QUORUM)
        reasons.append(f"spikes {signal.instability_spikes} > {policy.spike_threshold}")

    if signal.perturbation_fragility > policy.fragility_threshold:
        actions.append(GovernorAction.MARK_SOFT)
        reasons.append(f"fragility {signal.perturbation_fragility:.2f} > {policy.fragility_threshold}")

    if signal.overconfidence_signature > policy.overconfidence_threshold:
        actions.append(GovernorAction.CAP_CONFIDENCE)
        confidence_cap = 0.5
        evidence_tier = evidence_tier or "TOOL_TRACE"
        reasons.append(f"overconfidence {signal.overconfidence_signature:.2f} > {policy.overconfidence_threshold}")

    if signal.phase_flag == PhaseFlag.CONFAB and policy.confab_blocks_writes:
        actions.append(GovernorAction.BLOCK_WRITES)
        reasons.append("phase=confab — blocking ledger writes")

    if not actions:
        actions.append(GovernorAction.NO_CHANGE)
        reasons.append("all signals within tolerance")

    return SignalActionResult(
        actions=actions,
        confidence_cap=confidence_cap,
        evidence_tier=evidence_tier,
        reason="; ".join(reasons),
        signal_quality=signal.quality,
    )


# ---------------------------------------------------------------------------
# Failure-Safe Default
# ---------------------------------------------------------------------------


def failure_safe_signal(policy: SignalPolicy | None = None) -> CollapsedSignal:
    """Generate the failure-safe signal used when detector is unavailable.

    Silence from the sensor = uncertainty = higher evidence bar.
    Equivalent to overconfidence_signature = unavailable_penalty.
    """
    policy = policy or SignalPolicy()
    return CollapsedSignal(
        coherence_score=0.5,
        instability_spikes=0,
        perturbation_fragility=0.0,
        overconfidence_signature=policy.unavailable_penalty,
        phase_flag=PhaseFlag.UNKNOWN,
    )


# ---------------------------------------------------------------------------
# Detector Signal File I/O
# ---------------------------------------------------------------------------


@dataclass
class DetectorSignalFile:
    """A signal.json file produced by the external detector."""

    key: SignalKey
    raw: RawDetectorSignal
    collapsed: CollapsedSignal | None = None
    detector_version: str = ""
    profile: str = "general"
    file_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "key": self.key.to_dict(),
            "raw": self.raw.to_dict(),
            "detector_version": self.detector_version,
            "profile": self.profile,
        }
        if self.collapsed:
            d["collapsed"] = self.collapsed.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DetectorSignalFile:
        collapsed = None
        if "collapsed" in d:
            collapsed = CollapsedSignal.from_dict(d["collapsed"])
        return cls(
            key=SignalKey.from_dict(d["key"]),
            raw=RawDetectorSignal.from_dict(d.get("raw", {})),
            collapsed=collapsed,
            detector_version=d.get("detector_version", ""),
            profile=d.get("profile", "general"),
        )


def load_signal_file(path: Path) -> DetectorSignalFile:
    """Load a signal.json file from disk.

    Raises ValueError if the file is malformed.
    """
    if not path.exists():
        raise FileNotFoundError(f"Signal file not found: {path}")

    content = path.read_text()
    file_hash = hashlib.sha256(content.encode()).hexdigest()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed signal file: {e}") from e

    if "key" not in data:
        raise ValueError("Signal file missing required 'key' field")

    signal_file = DetectorSignalFile.from_dict(data)
    signal_file.file_hash = file_hash
    return signal_file


def save_signal_file(signal_file: DetectorSignalFile, path: Path) -> None:
    """Save a signal file to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(signal_file.to_dict(), indent=2, default=str)
    path.write_text(content + "\n")
    signal_file.file_hash = hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Integration with Constraint Compiler (Layer 12)
# ---------------------------------------------------------------------------


def signal_to_constraints(
    signal: CollapsedSignal,
    policy: SignalPolicy | None = None,
) -> list[dict[str, Any]]:
    """Convert detector signals to constraint-compiler-compatible constraints.

    Returns a list of dicts that can be added to the constraint compiler's
    resolution pipeline as Layer 12 constraints.
    """
    from .constraint_compiler import (
        ConstraintKind,
        ConstraintSeverity,
        ResolvedConstraint,
        make_constraint_id,
    )

    action_result = map_signal_to_actions(signal, policy)
    constraints: list[ResolvedConstraint] = []

    for action in action_result.actions:
        if action == GovernorAction.NO_CHANGE:
            continue

        if action == GovernorAction.RAISE_EVIDENCE:
            constraints.append(ResolvedConstraint(
                constraint_id=make_constraint_id(
                    "detector", "detector", "", "", "raise_evidence"
                ),
                kind=ConstraintKind.ENVELOPE,
                severity=ConstraintSeverity.REJECT,
                description=f"Detector: require {action_result.evidence_tier} evidence (coherence low)",
                source="detector",
                projection_priority=0.95,
            ))

        elif action == GovernorAction.FORCE_QUORUM:
            constraints.append(ResolvedConstraint(
                constraint_id=make_constraint_id(
                    "detector", "detector", "", "", "force_quorum"
                ),
                kind=ConstraintKind.ENVELOPE,
                severity=ConstraintSeverity.REJECT,
                description="Detector: force multi-model quorum (instability detected)",
                source="detector",
                projection_priority=0.9,
            ))

        elif action == GovernorAction.CAP_CONFIDENCE:
            cap = action_result.confidence_cap or 0.5
            constraints.append(ResolvedConstraint(
                constraint_id=make_constraint_id(
                    "detector", "detector", "", "", "cap_confidence"
                ),
                kind=ConstraintKind.ENVELOPE,
                severity=ConstraintSeverity.WARN,
                description=f"Detector: cap confidence at {cap} (overconfidence detected)",
                source="detector",
                projection_priority=0.85,
            ))

        elif action == GovernorAction.MARK_SOFT:
            constraints.append(ResolvedConstraint(
                constraint_id=make_constraint_id(
                    "detector", "detector", "", "", "mark_soft"
                ),
                kind=ConstraintKind.ENVELOPE,
                severity=ConstraintSeverity.WARN,
                description="Detector: mark claims as SOFT (perturbation fragility high)",
                source="detector",
                projection_priority=0.85,
            ))

        elif action == GovernorAction.BLOCK_WRITES:
            constraints.append(ResolvedConstraint(
                constraint_id=make_constraint_id(
                    "detector", "detector", "", "", "block_writes"
                ),
                kind=ConstraintKind.ENVELOPE,
                severity=ConstraintSeverity.REJECT,
                description="Detector: block ledger writes (confabulation phase detected)",
                source="detector",
                projection_priority=1.0,
            ))

    return [c.to_dict() for c in constraints]


# ---------------------------------------------------------------------------
# Evidence Ref Helper
# ---------------------------------------------------------------------------


def make_evidence_ref(
    signal: CollapsedSignal,
    key: SignalKey,
    file_hash: str = "",
) -> dict[str, Any]:
    """Create an EvidenceRef dict for a detector signal.

    Compatible with governor.epistemic.EvidenceRef.
    """
    return {
        "type": "detector_signal",
        "location": key.run_id,
        "span": signal.to_evidence_span(),
        "content_hash": file_hash,
    }


# ---------------------------------------------------------------------------
# DetectorIntegration Facade
# ---------------------------------------------------------------------------


class DetectorIntegration:
    """Top-level facade for detector integration.

    Wraps signal loading, collapse, action mapping, and constraint generation.
    """

    def __init__(self, policy: SignalPolicy | None = None) -> None:
        self.policy = policy or SignalPolicy()

    def load_and_collapse(self, signal_path: Path) -> tuple[CollapsedSignal, SignalKey, str]:
        """Load a signal file, collapse if needed, return (signal, key, hash).

        Raises ValueError for malformed files, FileNotFoundError for missing files.
        """
        signal_file = load_signal_file(signal_path)

        if signal_file.collapsed:
            collapsed = signal_file.collapsed
        else:
            collapsed = collapse_signal(signal_file.raw)

        return collapsed, signal_file.key, signal_file.file_hash

    def evaluate(self, signal: CollapsedSignal) -> SignalActionResult:
        """Evaluate a collapsed signal and return recommended actions."""
        return map_signal_to_actions(signal, self.policy)

    def get_constraints(self, signal: CollapsedSignal) -> list[dict[str, Any]]:
        """Get constraint-compiler-compatible constraints from a signal."""
        return signal_to_constraints(signal, self.policy)

    def failure_safe(self) -> CollapsedSignal:
        """Get the failure-safe signal for when detector is unavailable."""
        return failure_safe_signal(self.policy)

    def process_file(self, signal_path: Path) -> SignalActionResult:
        """Full pipeline: load file → collapse → evaluate."""
        try:
            collapsed, key, file_hash = self.load_and_collapse(signal_path)
        except (FileNotFoundError, ValueError):
            collapsed = self.failure_safe()
        return self.evaluate(collapsed)

    def status(self) -> dict[str, Any]:
        """Return status info."""
        return {
            "policy": self.policy.to_dict(),
            "failure_safe_signal": self.failure_safe().to_dict(),
        }
