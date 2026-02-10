"""
Domain/Mode Detection — Bayesian Mode Posterior.

Detect when solving the wrong kind of problem. Mode mismatch is a real failure class.
p_{t+1}(m) ∝ p_t(m) · exp(β · φ(o_t, m)).
Drift detection blocks COMMIT in late phases.

Spec: MODE_DETECTION_SPEC (Layer 2.1-C)
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DomainMode(str, Enum):
    """Domain modes the governor can detect."""
    CODE = "code"
    RESEARCH = "research"
    FICTION = "fiction"
    TASK = "task"


class DriftAction(str, Enum):
    """Action taken when mode drift is detected."""
    NONE = "none"
    WARN = "warn"
    BLOCK = "block"


class DriftPhase(str, Enum):
    """Phase context for drift decisions."""
    EARLY = "early"    # SPECIFY, EXPLORE
    MID = "mid"        # DRAFT
    LATE = "late"      # VERIFY, COMMIT


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default uniform prior
DEFAULT_PRIOR = {
    DomainMode.CODE: 0.25,
    DomainMode.RESEARCH: 0.25,
    DomainMode.FICTION: 0.25,
    DomainMode.TASK: 0.25,
}

# Bayesian update sensitivity
DEFAULT_BETA = 1.0

# Drift threshold
DRIFT_THRESHOLD = 0.3

# Mode-specific verification profiles
MODE_PROFILES: dict[str, dict[str, Any]] = {
    "code": {
        "verification_focus": ["syntax", "tests", "types", "security"],
        "severity_gates": {"S3": "block", "S2": "warn"},
        "late_novelty_penalty": 2.0,
        "critic_role": "veto_on_errors",
    },
    "research": {
        "verification_focus": ["citations", "factual_claims", "contradictions"],
        "severity_gates": {"S3": "block", "S2": "evidence_required"},
        "late_novelty_penalty": 1.0,
        "critic_role": "contradiction_first",
    },
    "fiction": {
        "verification_focus": ["continuity", "voice", "constraints"],
        "severity_gates": {"S3": "warn"},
        "late_novelty_penalty": 0.5,
        "critic_role": "continuity_check",
    },
    "task": {
        "verification_focus": ["completeness", "correctness"],
        "severity_gates": {"S3": "block", "S2": "warn"},
        "late_novelty_penalty": 1.0,
        "critic_role": "completeness_check",
    },
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Observation:
    """Feature vector for mode detection."""
    has_code_blocks: bool = False
    mentions_programming_language: bool = False
    requests_implementation: bool = False
    has_error_traces: bool = False
    requests_citations: bool = False
    asks_factual_questions: bool = False
    mentions_sources: bool = False
    analytical_language: bool = False
    creative_prompt: bool = False
    character_names: bool = False
    narrative_language: bool = False
    requests_story: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "has_code_blocks": self.has_code_blocks,
            "mentions_programming_language": self.mentions_programming_language,
            "requests_implementation": self.requests_implementation,
            "has_error_traces": self.has_error_traces,
            "requests_citations": self.requests_citations,
            "asks_factual_questions": self.asks_factual_questions,
            "mentions_sources": self.mentions_sources,
            "analytical_language": self.analytical_language,
            "creative_prompt": self.creative_prompt,
            "character_names": self.character_names,
            "narrative_language": self.narrative_language,
            "requests_story": self.requests_story,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Observation:
        return cls(**{k: d.get(k, False) for k in cls.__dataclass_fields__})


@dataclass
class ModePosterior:
    """Probability distribution over domain modes."""
    code: float = 0.25
    research: float = 0.25
    fiction: float = 0.25
    task: float = 0.25

    @property
    def dominant_mode(self) -> DomainMode:
        scores = self.as_dict()
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    @property
    def confidence(self) -> float:
        """Confidence in dominant mode (max probability)."""
        return max(self.code, self.research, self.fiction, self.task)

    def as_dict(self) -> dict[DomainMode, float]:
        return {
            DomainMode.CODE: self.code,
            DomainMode.RESEARCH: self.research,
            DomainMode.FICTION: self.fiction,
            DomainMode.TASK: self.task,
        }

    def to_dict(self) -> dict[str, float]:
        return {
            "code": round(self.code, 6),
            "research": round(self.research, 6),
            "fiction": round(self.fiction, 6),
            "task": round(self.task, 6),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModePosterior:
        return cls(
            code=d.get("code", 0.25),
            research=d.get("research", 0.25),
            fiction=d.get("fiction", 0.25),
            task=d.get("task", 0.25),
        )

    @classmethod
    def uniform(cls) -> ModePosterior:
        return cls(0.25, 0.25, 0.25, 0.25)

    @classmethod
    def peaked(cls, mode: DomainMode, strength: float = 0.7) -> ModePosterior:
        """Create posterior peaked at a mode."""
        rest = (1.0 - strength) / 3.0
        d = {DomainMode.CODE: rest, DomainMode.RESEARCH: rest,
             DomainMode.FICTION: rest, DomainMode.TASK: rest}
        d[mode] = strength
        return cls(code=d[DomainMode.CODE], research=d[DomainMode.RESEARCH],
                   fiction=d[DomainMode.FICTION], task=d[DomainMode.TASK])


@dataclass
class DriftAlert:
    """Alert when mode drift is detected."""
    drift_score: float
    initial_mode: DomainMode
    current_mode: DomainMode
    action: DriftAction
    phase: DriftPhase
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_score": round(self.drift_score, 6),
            "initial_mode": self.initial_mode.value,
            "current_mode": self.current_mode.value,
            "action": self.action.value,
            "phase": self.phase.value,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DriftAlert:
        return cls(
            drift_score=d.get("drift_score", 0.0),
            initial_mode=DomainMode(d["initial_mode"]),
            current_mode=DomainMode(d["current_mode"]),
            action=DriftAction(d.get("action", "none")),
            phase=DriftPhase(d.get("phase", "early")),
            ts=d.get("ts", ""),
        )


@dataclass
class ModeState:
    """Tracking state for mode detection across a run."""
    run_id: str
    initial_posterior: ModePosterior = field(default_factory=ModePosterior.uniform)
    current_posterior: ModePosterior = field(default_factory=ModePosterior.uniform)
    observation_count: int = 0
    alerts: list[DriftAlert] = field(default_factory=list)
    active_profile: str = "task"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "initial_posterior": self.initial_posterior.to_dict(),
            "current_posterior": self.current_posterior.to_dict(),
            "observation_count": self.observation_count,
            "alerts": [a.to_dict() for a in self.alerts],
            "active_profile": self.active_profile,
            "dominant_mode": self.current_posterior.dominant_mode.value,
            "drift": round(compute_drift(
                self.current_posterior.as_dict(),
                self.initial_posterior.as_dict()
            ), 6),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModeState:
        return cls(
            run_id=d["run_id"],
            initial_posterior=ModePosterior.from_dict(d.get("initial_posterior", {})),
            current_posterior=ModePosterior.from_dict(d.get("current_posterior", {})),
            observation_count=d.get("observation_count", 0),
            alerts=[DriftAlert.from_dict(a) for a in d.get("alerts", [])],
            active_profile=d.get("active_profile", "task"),
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def compute_mode_features(observation: Observation, mode: DomainMode) -> float:
    """Score features of an observation under a mode."""
    features: dict[DomainMode, list[bool]] = {
        DomainMode.CODE: [
            observation.has_code_blocks,
            observation.mentions_programming_language,
            observation.requests_implementation,
            observation.has_error_traces,
        ],
        DomainMode.RESEARCH: [
            observation.requests_citations,
            observation.asks_factual_questions,
            observation.mentions_sources,
            observation.analytical_language,
        ],
        DomainMode.FICTION: [
            observation.creative_prompt,
            observation.character_names,
            observation.narrative_language,
            observation.requests_story,
        ],
        DomainMode.TASK: [],  # TASK is the fallback
    }
    return float(sum(features.get(mode, [])))


def update_mode_posterior(
    prior: dict[DomainMode, float],
    observation: Observation,
    beta: float = DEFAULT_BETA,
) -> dict[DomainMode, float]:
    """Bayesian update: p_{t+1}(m) ∝ p_t(m) · exp(β · φ(o_t, m))."""
    scores = {}
    for m in DomainMode:
        phi = compute_mode_features(observation, m)
        scores[m] = prior.get(m, 0.25) * math.exp(beta * phi)
    total = sum(scores.values())
    if total == 0:
        return {m: 0.25 for m in DomainMode}
    return {m: s / total for m, s in scores.items()}


def compute_drift(
    current: dict[DomainMode, float],
    initial: dict[DomainMode, float],
) -> float:
    """1 - dot product of distributions (drift metric)."""
    dot = sum(current.get(m, 0.0) * initial.get(m, 0.0) for m in DomainMode)
    return max(0.0, 1.0 - dot)


def check_mode_drift(
    current: dict[DomainMode, float],
    initial: dict[DomainMode, float],
    phase: DriftPhase,
    threshold: float = DRIFT_THRESHOLD,
) -> DriftAlert | None:
    """Check for mode drift. Returns alert if threshold exceeded in late phases."""
    drift = compute_drift(current, initial)
    if drift <= threshold:
        return None

    initial_mode = max(initial, key=initial.get)  # type: ignore[arg-type]
    current_mode = max(current, key=current.get)  # type: ignore[arg-type]

    if phase == DriftPhase.LATE:
        action = DriftAction.BLOCK
    elif phase == DriftPhase.MID:
        action = DriftAction.WARN
    else:
        return None  # No alert in early phases

    return DriftAlert(
        drift_score=drift,
        initial_mode=initial_mode,
        current_mode=current_mode,
        action=action,
        phase=phase,
    )


def get_mode_profile(mode: DomainMode) -> dict[str, Any]:
    """Get verification profile for a mode."""
    return MODE_PROFILES.get(mode.value, MODE_PROFILES["task"])


def observe_and_update(
    state: ModeState,
    observation: Observation,
    phase: DriftPhase = DriftPhase.EARLY,
    beta: float = DEFAULT_BETA,
) -> DriftAlert | None:
    """Process an observation, update state, check drift."""
    new_posterior = update_mode_posterior(
        state.current_posterior.as_dict(), observation, beta
    )
    state.current_posterior = ModePosterior(
        code=new_posterior[DomainMode.CODE],
        research=new_posterior[DomainMode.RESEARCH],
        fiction=new_posterior[DomainMode.FICTION],
        task=new_posterior[DomainMode.TASK],
    )
    state.observation_count += 1
    state.active_profile = state.current_posterior.dominant_mode.value

    alert = check_mode_drift(
        state.current_posterior.as_dict(),
        state.initial_posterior.as_dict(),
        phase,
    )
    if alert is not None:
        state.alerts.append(alert)
    return alert


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class ModeDetectionStore:
    """Persistent store for mode detection state."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.mode_dir = self.governor_dir / "mode_detection"

    def _ensure_dirs(self) -> None:
        self.mode_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: ModeState) -> Path:
        self._ensure_dirs()
        path = self.mode_dir / f"{state.run_id}.json"
        path.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
        return path

    def load(self, run_id: str) -> ModeState | None:
        path = self.mode_dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return ModeState.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def list_runs(self) -> list[str]:
        if not self.mode_dir.exists():
            return []
        return sorted(f.stem for f in self.mode_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_mode_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "mode_detection",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
