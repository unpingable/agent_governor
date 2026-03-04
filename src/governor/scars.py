# SPDX-License-Identifier: Apache-2.0
"""
Scars: Failure Provenance & Constraint Hysteresis.

Failure is not a signal to optimize; it is a signal to constrain.

Core concepts:
- Failure classification by contract violation provenance
- Internal instability -> SCAR (tighten admissible control set U)
- External hostility -> SHIELD (tighten input permeability I)
- Hysteresis: topology is permanent, stiffness relaxes under evidence
- Annealing: tau_heal >> tau_scar, evidence-gated not time-gated

Key invariants:
1. Scars introduce irreversible constraints on admissible control topology.
2. Relaxation may reduce constraint stiffness, never erase existence.
3. Never punish the agent for an impossible environment.
4. Never trust the agent after an unforced error.
5. Scar or Shield per failure, never both (mutual exclusivity).

Toggle via config.toml:
    [epistemic]
    failure_provenance = true
    scar_hysteresis = true
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import json
import math
import uuid


def _normalize_fingerprint_field(s: str) -> str:
    """Normalize a fingerprint field: lowercase, collapse whitespace to underscores."""
    if not s:
        return s
    return "_".join(s.lower().split())


# =============================================================================
# Failure Provenance
# =============================================================================


class FailureProvenance(str, Enum):
    """Classification of failure origin."""

    INTERNAL = "internal"
    """Agent failed a valid environment. Scar the agent."""

    EXTERNAL = "external"
    """Environment violated the regularity contract. Shield the interface."""

    AMBIGUOUS = "ambiguous"
    """Cannot determine provenance. Default to shielding (DoC-safe)."""


# =============================================================================
# Scar (Action Restriction)
# =============================================================================


# Stiffness bounds
MAX_STIFFNESS = 1.0
MIN_STIFFNESS = 0.05  # Permanent margin - scars never fully heal
DEFAULT_ANNEAL_FLOOR = 0.1  # Asymptotic ceiling < pre-failure


@dataclass
class Scar:
    """
    An irreversible constraint on admissible control topology.

    The scar's region (topology) is permanent.
    The scar's stiffness relaxes under evidence, but never to zero.

    Stiffness = 1.0 means full restriction (hard veto).
    Stiffness -> MIN_STIFFNESS means soft penalty (high cost, still passable).
    """

    scar_id: str
    region: str  # Identifier for the constrained region (scope, path, action type)
    stiffness: float = MAX_STIFFNESS  # [MIN_STIFFNESS, MAX_STIFFNESS]
    description: str = ""

    # Fingerprint dimensions (region is coarse; these add specificity)
    failure_kind: str = ""  # What went wrong (timeout, validation, auth, etc.)
    action_type: str = ""   # What was attempted (write, read, execute, etc.)

    # Provenance of the failure that created this scar
    provenance: FailureProvenance = FailureProvenance.INTERNAL

    # Temporal tracking
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_evidence_at: datetime | None = None  # Last time evidence relaxed stiffness
    last_tightened_at: datetime | None = None  # Last time stiffness increased

    # Evidence tracking for annealing
    evidence_count: int = 0  # Number of stability evidence observations
    required_evidence: int = 5  # Evidence needed before any relaxation

    # Anneal floor (asymptotic minimum stiffness)
    anneal_floor: float = DEFAULT_ANNEAL_FLOOR

    # Failure context
    failure_event_id: str | None = None
    failure_surprise_ratio: float = 0.0

    def __post_init__(self):
        """Clamp stiffness to valid range and normalize fingerprint fields."""
        self.stiffness = max(MIN_STIFFNESS, min(MAX_STIFFNESS, self.stiffness))
        self.failure_kind = _normalize_fingerprint_field(self.failure_kind)
        self.action_type = _normalize_fingerprint_field(self.action_type)

    @property
    def is_hard(self) -> bool:
        """Is this scar at maximum stiffness (hard veto)?"""
        return self.stiffness >= 0.95

    @property
    def is_soft(self) -> bool:
        """Has this scar relaxed below hard threshold?"""
        return self.stiffness < 0.95

    @property
    def effective_cost(self) -> float:
        """Cost multiplier imposed by this scar. Higher = more friction."""
        # Exponential cost: stiffness 1.0 -> cost 10.0, stiffness 0.1 -> cost 1.26
        return math.exp(self.stiffness * math.log(10))

    def can_anneal(self) -> bool:
        """Can this scar be annealed (has enough evidence)?"""
        return (
            self.evidence_count >= self.required_evidence
            and self.stiffness > self.anneal_floor
        )

    def anneal(self, decay_rate: float = 0.1) -> float:
        """
        Reduce stiffness toward anneal floor.

        Returns the amount of stiffness reduced.
        Evidence-gated: only called when evidence supports relaxation.
        """
        if not self.can_anneal():
            return 0.0

        old_stiffness = self.stiffness
        # Exponential decay toward floor
        self.stiffness = self.anneal_floor + (self.stiffness - self.anneal_floor) * (
            1.0 - decay_rate
        )
        self.stiffness = max(self.anneal_floor, self.stiffness)
        self.last_evidence_at = datetime.now(timezone.utc)

        return old_stiffness - self.stiffness

    def record_evidence(self) -> None:
        """Record a stability evidence observation."""
        self.evidence_count += 1
        self.last_evidence_at = datetime.now(timezone.utc)

    def retighten(self, amount: float = 0.5) -> None:
        """Re-tighten scar after re-failure in same region."""
        self.stiffness = min(MAX_STIFFNESS, self.stiffness + amount)
        self.last_tightened_at = datetime.now(timezone.utc)
        # Reset evidence counter - must re-prove stability
        self.evidence_count = 0

    @property
    def fingerprint(self) -> str:
        """Composite fingerprint: region + failure_kind + action_type."""
        return f"{self.region}::{self.failure_kind}::{self.action_type}"

    def matches_fingerprint(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> bool:
        """Check if this scar matches a fingerprint query.

        A broader scar (empty failure_kind/action_type) matches
        narrower queries. A narrow scar only matches exact queries.
        """
        if self.region != region:
            return False
        # Broad scar (no failure_kind) matches everything in this region
        if not self.failure_kind and not self.action_type:
            return True
        # Narrow query (no failure_kind) matches any scar in this region
        if not failure_kind and not action_type:
            return True
        # Check failure_kind match (empty self matches any query)
        if self.failure_kind and failure_kind and self.failure_kind != failure_kind:
            return False
        # Check action_type match (empty self matches any query)
        if self.action_type and action_type and self.action_type != action_type:
            return False
        return True

    def matches_evidence_fingerprint(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> bool:
        """Check if evidence with the given fingerprint applies to this scar.

        Inverted asymmetry from matches_fingerprint():
        - For admissibility, broad scars block narrow queries (correct).
        - For evidence, narrow success does NOT prove broad safety.

        Per-field rules:
        - Region must match.
        - If evidence field is empty → matches (broad evidence, backward compat).
        - If scar field is empty AND evidence field is set → NO match
          (narrow evidence can't prove broad safety — the key fix).
        - If both set → must be equal.
        """
        if self.region != region:
            return False
        norm_kind = _normalize_fingerprint_field(failure_kind)
        norm_action = _normalize_fingerprint_field(action_type)
        # Per-field matching with evidence-direction asymmetry
        if not self._evidence_field_matches(self.failure_kind, norm_kind):
            return False
        if not self._evidence_field_matches(self.action_type, norm_action):
            return False
        return True

    @staticmethod
    def _evidence_field_matches(scar_field: str, evidence_field: str) -> bool:
        """Check one field for evidence-direction matching.

        - evidence empty → matches (broad evidence, don't care)
        - scar empty, evidence set → no match (narrow can't prove broad)
        - both set → must be equal
        """
        if not evidence_field:
            return True  # Broad evidence matches any scar
        if not scar_field:
            return False  # Narrow evidence can't anneal broad scar
        return scar_field == evidence_field

    def to_dict(self) -> dict[str, Any]:
        return {
            "scar_id": self.scar_id,
            "region": self.region,
            "stiffness": self.stiffness,
            "description": self.description,
            "failure_kind": self.failure_kind,
            "action_type": self.action_type,
            "provenance": self.provenance.value,
            "created_at": self.created_at.isoformat(),
            "last_evidence_at": self.last_evidence_at.isoformat() if self.last_evidence_at else None,
            "last_tightened_at": self.last_tightened_at.isoformat() if self.last_tightened_at else None,
            "evidence_count": self.evidence_count,
            "required_evidence": self.required_evidence,
            "anneal_floor": self.anneal_floor,
            "failure_event_id": self.failure_event_id,
            "failure_surprise_ratio": self.failure_surprise_ratio,
            "is_hard": self.is_hard,
            "effective_cost": self.effective_cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scar":
        return cls(
            scar_id=data["scar_id"],
            region=data["region"],
            stiffness=data.get("stiffness", MAX_STIFFNESS),
            description=data.get("description", ""),
            failure_kind=data.get("failure_kind", ""),
            action_type=data.get("action_type", ""),
            provenance=FailureProvenance(data.get("provenance", "internal")),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_evidence_at=(
                datetime.fromisoformat(data["last_evidence_at"])
                if data.get("last_evidence_at")
                else None
            ),
            last_tightened_at=(
                datetime.fromisoformat(data["last_tightened_at"])
                if data.get("last_tightened_at")
                else None
            ),
            evidence_count=data.get("evidence_count", 0),
            required_evidence=data.get("required_evidence", 5),
            anneal_floor=data.get("anneal_floor", DEFAULT_ANNEAL_FLOOR),
            failure_event_id=data.get("failure_event_id"),
            failure_surprise_ratio=data.get("failure_surprise_ratio", 0.0),
        )


# =============================================================================
# Shield (Input Gating)
# =============================================================================


@dataclass
class Shield:
    """
    Temporary input permeability restriction.

    Unlike scars, shields CAN be fully removed once the attack subsides.
    Shields protect the agent from being blamed for impossible environments.
    """

    shield_id: str
    source: str  # What input source is being gated
    permeability: float = 1.0  # [0, 1] where 0 = fully blocked, 1 = fully open
    severity: float = 0.5  # How severe the external threat was

    # Temporal
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_attack_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_relaxed_at: datetime | None = None

    # Release conditions
    stable_cycles_required: int = 10  # Cycles without attack before release
    stable_cycles_observed: int = 0

    # Failure context
    failure_event_id: str | None = None
    failure_surprise_ratio: float = 0.0

    def __post_init__(self):
        """Clamp permeability."""
        self.permeability = max(0.0, min(1.0, self.permeability))

    @property
    def is_blocking(self) -> bool:
        """Is this shield actively restricting input?"""
        return self.permeability < 1.0

    @property
    def is_fully_blocked(self) -> bool:
        """Is this shield completely blocking input?"""
        return self.permeability <= 0.01

    @property
    def can_release(self) -> bool:
        """Can this shield be released (enough stable cycles)?"""
        return self.stable_cycles_observed >= self.stable_cycles_required

    def tighten(self, amount: float = 0.3) -> None:
        """Reduce permeability (more blocking)."""
        self.permeability = max(0.0, self.permeability - amount)
        self.last_attack_at = datetime.now(timezone.utc)
        # Reset stability counter
        self.stable_cycles_observed = 0

    def relax(self, amount: float = 0.1) -> None:
        """Increase permeability (less blocking)."""
        self.permeability = min(1.0, self.permeability + amount)
        self.last_relaxed_at = datetime.now(timezone.utc)

    def record_stable_cycle(self) -> None:
        """Record a cycle without attack."""
        self.stable_cycles_observed += 1

    def record_attack(self) -> None:
        """Record a new attack on this source."""
        self.last_attack_at = datetime.now(timezone.utc)
        self.stable_cycles_observed = 0

    def release(self) -> None:
        """Fully release the shield (permeability = 1.0)."""
        self.permeability = 1.0
        self.last_relaxed_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shield_id": self.shield_id,
            "source": self.source,
            "permeability": self.permeability,
            "severity": self.severity,
            "created_at": self.created_at.isoformat(),
            "last_attack_at": self.last_attack_at.isoformat(),
            "last_relaxed_at": self.last_relaxed_at.isoformat() if self.last_relaxed_at else None,
            "stable_cycles_required": self.stable_cycles_required,
            "stable_cycles_observed": self.stable_cycles_observed,
            "failure_event_id": self.failure_event_id,
            "failure_surprise_ratio": self.failure_surprise_ratio,
            "is_blocking": self.is_blocking,
            "can_release": self.can_release,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Shield":
        return cls(
            shield_id=data["shield_id"],
            source=data["source"],
            permeability=data.get("permeability", 1.0),
            severity=data.get("severity", 0.5),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_attack_at=datetime.fromisoformat(data["last_attack_at"]),
            last_relaxed_at=(
                datetime.fromisoformat(data["last_relaxed_at"])
                if data.get("last_relaxed_at")
                else None
            ),
            stable_cycles_required=data.get("stable_cycles_required", 10),
            stable_cycles_observed=data.get("stable_cycles_observed", 0),
            failure_event_id=data.get("failure_event_id"),
            failure_surprise_ratio=data.get("failure_surprise_ratio", 0.0),
        )


# =============================================================================
# Failure Event
# =============================================================================


@dataclass
class FailureEvent:
    """
    Record of a failure occurrence with context for provenance classification.
    """

    event_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # What failed
    region: str = ""  # Scope/path/action that failed
    failure_kind: str = ""  # What went wrong (timeout, validation, auth, etc.)
    action_type: str = ""   # What was attempted (write, read, execute, etc.)
    description: str = ""
    error_magnitude: float = 0.0  # How bad was the failure [0, inf)

    # Provenance metrics
    observation_shift: float = 0.0  # delta_y: how much the world changed
    prediction_error: float = 0.0  # pred_err: how wrong we were
    surprise_ratio: float = 0.0  # rho = delta_y / pred_err

    # Classification result (filled by discriminator)
    provenance: FailureProvenance | None = None
    response_type: str | None = None  # "scar" or "shield" or "ambiguous"

    # Linked objects
    scar_id: str | None = None
    shield_id: str | None = None

    def __post_init__(self):
        """Normalize fingerprint fields."""
        self.failure_kind = _normalize_fingerprint_field(self.failure_kind)
        self.action_type = _normalize_fingerprint_field(self.action_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "region": self.region,
            "failure_kind": self.failure_kind,
            "action_type": self.action_type,
            "description": self.description,
            "error_magnitude": self.error_magnitude,
            "observation_shift": self.observation_shift,
            "prediction_error": self.prediction_error,
            "surprise_ratio": self.surprise_ratio,
            "provenance": self.provenance.value if self.provenance else None,
            "response_type": self.response_type,
            "scar_id": self.scar_id,
            "shield_id": self.shield_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureEvent":
        return cls(
            event_id=data["event_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            region=data.get("region", ""),
            failure_kind=data.get("failure_kind", ""),
            action_type=data.get("action_type", ""),
            description=data.get("description", ""),
            error_magnitude=data.get("error_magnitude", 0.0),
            observation_shift=data.get("observation_shift", 0.0),
            prediction_error=data.get("prediction_error", 0.0),
            surprise_ratio=data.get("surprise_ratio", 0.0),
            provenance=(
                FailureProvenance(data["provenance"]) if data.get("provenance") else None
            ),
            response_type=data.get("response_type"),
            scar_id=data.get("scar_id"),
            shield_id=data.get("shield_id"),
        )


# =============================================================================
# Scar Configuration
# =============================================================================


@dataclass
class ScarConfig:
    """
    Configuration for the scar ledger.

    Governor-owned parameters. The agent cannot modify these.
    """

    # Surprise ratio thresholds (with hysteresis band)
    rho_lo: float = 0.3  # Below this: INTERNAL (agent fault)
    rho_hi: float = 0.7  # Above this: EXTERNAL (environment fault)
    # Between rho_lo and rho_hi: AMBIGUOUS

    # Regularity bound (L_assumed) - max expected environment volatility
    regularity_bound: float = 1.0

    # Scar parameters
    default_stiffness: float = MAX_STIFFNESS
    anneal_decay_rate: float = 0.1  # Per-anneal stiffness reduction
    anneal_floor: float = DEFAULT_ANNEAL_FLOOR
    evidence_required: int = 5  # Evidence observations before annealing

    # Shield parameters
    default_shield_reduction: float = 0.3  # Permeability reduction on shield
    shield_release_cycles: int = 10  # Stable cycles before shield release
    shield_relax_rate: float = 0.1  # Per-cycle permeability recovery

    # Ambiguous handling
    ambiguous_shield_amount: float = 0.15  # Light shield on ambiguous
    ambiguous_stiffness_bump: float = 0.1  # Soft stiffness increase (no topology fence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rho_lo": self.rho_lo,
            "rho_hi": self.rho_hi,
            "regularity_bound": self.regularity_bound,
            "default_stiffness": self.default_stiffness,
            "anneal_decay_rate": self.anneal_decay_rate,
            "anneal_floor": self.anneal_floor,
            "evidence_required": self.evidence_required,
            "default_shield_reduction": self.default_shield_reduction,
            "shield_release_cycles": self.shield_release_cycles,
            "shield_relax_rate": self.shield_relax_rate,
            "ambiguous_shield_amount": self.ambiguous_shield_amount,
            "ambiguous_stiffness_bump": self.ambiguous_stiffness_bump,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScarConfig":
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


# =============================================================================
# Scar Ledger
# =============================================================================


class ScarLedger:
    """
    Manages scars (action restrictions) and shields (input gating).

    Implements the failure provenance discriminator and constraint hysteresis.

    Key operations:
    - classify_failure(): Determine provenance using surprise ratio
    - record_failure(): Classify and apply scar or shield
    - check_admissible(): Check if action is allowed given scars
    - check_input(): Check if input passes shield gates
    - anneal_scars(): Relax scar stiffness under evidence
    - relax_shields(): Relax shields after stable periods
    """

    def __init__(self, config: ScarConfig | None = None):
        self.config = config or ScarConfig()

        # Core state
        self.scars: dict[str, Scar] = {}
        self.shields: dict[str, Shield] = {}
        self.failure_history: list[FailureEvent] = []

        # Metrics
        self.total_failures: int = 0
        self.internal_failures: int = 0
        self.external_failures: int = 0
        self.ambiguous_failures: int = 0
        self.total_anneals: int = 0
        self.total_shield_releases: int = 0

    # =========================================================================
    # Failure Provenance Discriminator
    # =========================================================================

    def classify_failure(
        self,
        observation_shift: float,
        prediction_error: float,
    ) -> tuple[FailureProvenance, float]:
        """
        Classify failure provenance using the surprise ratio.

        rho = observation_shift / prediction_error

        - Low rho (< rho_lo): World was calm, agent crashed -> INTERNAL
        - High rho (>= rho_hi): World jumped, environment hostile -> EXTERNAL
        - Middle: AMBIGUOUS (default to shielding for DoC safety)

        Returns (provenance, surprise_ratio).
        """
        # Safe division
        if prediction_error <= 0.0:
            if observation_shift > 0.0:
                # World changed but no prediction error -> external
                rho = float("inf")
            else:
                # Nothing happened -> internal (agent failed without excuse)
                rho = 0.0
        else:
            rho = observation_shift / prediction_error

        # Classify with hysteresis band
        if rho < self.config.rho_lo:
            return FailureProvenance.INTERNAL, rho
        elif rho >= self.config.rho_hi:
            return FailureProvenance.EXTERNAL, rho
        else:
            return FailureProvenance.AMBIGUOUS, rho

    # =========================================================================
    # Failure Recording (The Governor Loop Step 4b-5)
    # =========================================================================

    def record_failure_strict(
        self,
        region: str,
        failure_kind: str,
        action_type: str,
        observation_shift: float = 0.0,
        prediction_error: float = 0.0,
        error_magnitude: float = 1.0,
        description: str = "",
        source: str | None = None,
    ) -> FailureEvent:
        """Record a failure with required fingerprint fields.

        New call sites should use this instead of record_failure() to
        prevent silent fallback into the region-only bucket.
        """
        if not failure_kind:
            raise ValueError("failure_kind is required (use record_failure() for legacy)")
        return self.record_failure(
            region=region,
            observation_shift=observation_shift,
            prediction_error=prediction_error,
            error_magnitude=error_magnitude,
            description=description,
            source=source,
            failure_kind=failure_kind,
            action_type=action_type,
        )

    def check_admissible_strict(
        self,
        region: str,
        failure_kind: str,
        action_type: str = "",
    ) -> tuple[bool, float, Scar | None]:
        """Check admissibility with required fingerprint fields.

        New call sites should use this instead of check_admissible().
        """
        if not failure_kind:
            raise ValueError("failure_kind is required (use check_admissible() for legacy)")
        return self.check_admissible(region, failure_kind, action_type)

    def record_stability_evidence_strict(
        self,
        region: str,
        failure_kind: str,
        action_type: str = "",
    ) -> bool:
        """Record evidence with required fingerprint fields.

        New call sites should use this to avoid broadcast evidence.
        """
        if not failure_kind:
            raise ValueError("failure_kind is required (use record_stability_evidence() for legacy)")
        return self.record_stability_evidence(region, failure_kind, action_type)

    def record_failure(
        self,
        region: str,
        observation_shift: float = 0.0,
        prediction_error: float = 0.0,
        error_magnitude: float = 1.0,
        description: str = "",
        source: str | None = None,
        failure_kind: str = "",
        action_type: str = "",
    ) -> FailureEvent:
        """
        Record a failure event, classify provenance, and apply scar or shield.

        This is the main entry point for the failure provenance loop.

        Args:
            region: The scope/path/action that failed
            observation_shift: delta_y - how much the world changed
            prediction_error: pred_err - how wrong we were
            error_magnitude: severity of the failure
            description: human-readable description
            source: input source (for shielding)
            failure_kind: what went wrong (timeout, validation, auth, etc.)
            action_type: what was attempted (write, read, execute, etc.)

        Returns the classified FailureEvent.
        """
        # 0. Normalize fingerprint fields at API boundary
        failure_kind = _normalize_fingerprint_field(failure_kind)
        action_type = _normalize_fingerprint_field(action_type)

        # 1. Create failure event
        event = FailureEvent(
            event_id=f"fe_{uuid.uuid4().hex[:12]}",
            region=region,
            failure_kind=failure_kind,
            action_type=action_type,
            description=description,
            error_magnitude=error_magnitude,
            observation_shift=observation_shift,
            prediction_error=prediction_error,
        )

        # 2. Classify provenance
        provenance, rho = self.classify_failure(observation_shift, prediction_error)
        event.surprise_ratio = rho
        event.provenance = provenance

        # 3. Apply mutually exclusive response
        if provenance == FailureProvenance.INTERNAL:
            scar = self._apply_scar(event)
            event.response_type = "scar"
            event.scar_id = scar.scar_id
            self.internal_failures += 1

        elif provenance == FailureProvenance.EXTERNAL:
            shield_source = source or region
            shield = self._apply_shield(event, shield_source)
            event.response_type = "shield"
            event.shield_id = shield.shield_id
            self.external_failures += 1

        else:  # AMBIGUOUS
            # Conservative default: prefer shielding (prevents DoC)
            shield_source = source or region
            shield = self._apply_ambiguous(event, shield_source)
            event.response_type = "ambiguous"
            event.shield_id = shield.shield_id
            self.ambiguous_failures += 1

        # 4. Record
        self.failure_history.append(event)
        self.total_failures += 1

        return event

    def _apply_scar(self, event: FailureEvent) -> Scar:
        """Apply a scar (tighten admissible control set U).

        Three-tier novelty gate:
        1. Exact fingerprint match → retighten existing scar
        2. Similar class (same region+kind or region+action, but not exact)
           → retighten the similar scar instead of creating a new one.
           Prevents novel-but-similar retries from self-bricking with
           many narrow scars, while still accumulating evidence correctly.
        3. Different class (no match) → create new scar
        """
        # Tier 1: Exact fingerprint match → retighten
        existing = self._find_exact_scar(
            event.region, event.failure_kind, event.action_type,
        )

        if existing:
            existing.retighten()
            existing.failure_event_id = event.event_id
            existing.failure_surprise_ratio = event.surprise_ratio
            return existing

        # Tier 2: Similar class → retighten the similar scar
        # "Similar" = same region AND shares either failure_kind or action_type
        # (but only when event has fingerprint specificity to compare)
        if event.failure_kind or event.action_type:
            similar = self._find_similar_scar(
                event.region, event.failure_kind, event.action_type,
            )
            if similar:
                similar.retighten()
                similar.failure_event_id = event.event_id
                similar.failure_surprise_ratio = event.surprise_ratio
                return similar

        # Tier 3: Different class → create new scar
        scar = Scar(
            scar_id=f"sc_{uuid.uuid4().hex[:12]}",
            region=event.region,
            stiffness=self.config.default_stiffness,
            description=event.description,
            failure_kind=event.failure_kind,
            action_type=event.action_type,
            provenance=FailureProvenance.INTERNAL,
            anneal_floor=self.config.anneal_floor,
            required_evidence=self.config.evidence_required,
            failure_event_id=event.event_id,
            failure_surprise_ratio=event.surprise_ratio,
        )

        self.scars[scar.scar_id] = scar
        return scar

    def _apply_shield(self, event: FailureEvent, source: str) -> Shield:
        """Apply a shield (tighten input permeability I)."""
        # Check if shield already exists for this source
        existing = self._find_shield_by_source(source)

        if existing:
            # Tighten existing shield
            existing.tighten(self.config.default_shield_reduction)
            existing.failure_event_id = event.event_id
            existing.failure_surprise_ratio = event.surprise_ratio
            return existing

        # Create new shield
        shield = Shield(
            shield_id=f"sh_{uuid.uuid4().hex[:12]}",
            source=source,
            permeability=1.0 - self.config.default_shield_reduction,
            severity=event.error_magnitude,
            stable_cycles_required=self.config.shield_release_cycles,
            failure_event_id=event.event_id,
            failure_surprise_ratio=event.surprise_ratio,
        )

        self.shields[shield.shield_id] = shield
        return shield

    def _apply_ambiguous(self, event: FailureEvent, source: str) -> Shield:
        """Apply ambiguous response: light shield + optional soft stiffness bump."""
        # Light shield (DoC-safe default)
        existing = self._find_shield_by_source(source)

        if existing:
            existing.tighten(self.config.ambiguous_shield_amount)
            existing.failure_event_id = event.event_id
            existing.failure_surprise_ratio = event.surprise_ratio
            shield = existing
        else:
            shield = Shield(
                shield_id=f"sh_{uuid.uuid4().hex[:12]}",
                source=source,
                permeability=1.0 - self.config.ambiguous_shield_amount,
                severity=event.error_magnitude * 0.5,  # Half severity for ambiguous
                stable_cycles_required=self.config.shield_release_cycles,
                failure_event_id=event.event_id,
                failure_surprise_ratio=event.surprise_ratio,
            )
            self.shields[shield.shield_id] = shield

        # Optional: soft stiffness bump on matching scar (no new topology)
        existing_scar = self._find_exact_scar(
            event.region, event.failure_kind, event.action_type,
        )
        if existing_scar:
            existing_scar.stiffness = min(
                MAX_STIFFNESS,
                existing_scar.stiffness + self.config.ambiguous_stiffness_bump,
            )

        return shield

    # =========================================================================
    # Admissibility Checks
    # =========================================================================

    def check_admissible(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> tuple[bool, float, Scar | None]:
        """
        Check if an action in the given region is admissible.

        Returns (admissible, cost_multiplier, scar_or_none).

        An action is admissible if no hard scar (stiffness >= 0.95) covers it.
        Soft scars impose a cost multiplier but don't block.

        When multiple scars match (e.g. a region-level scar AND a
        failure_kind-specific scar), the MOST RESTRICTIVE scar wins.
        """
        failure_kind = _normalize_fingerprint_field(failure_kind)
        action_type = _normalize_fingerprint_field(action_type)
        scar = self._find_most_restrictive_scar(region, failure_kind, action_type)

        if scar is None:
            return True, 1.0, None

        if scar.is_hard:
            return False, scar.effective_cost, scar

        # Soft scar: admissible but costly
        return True, scar.effective_cost, scar

    def check_input(self, source: str) -> tuple[bool, float, Shield | None]:
        """
        Check if input from a source passes shield gates.

        Returns (passable, permeability, shield_or_none).

        Input is passable if permeability > 0.01.
        """
        shield = self._find_shield_by_source(source)

        if shield is None:
            return True, 1.0, None

        if shield.is_fully_blocked:
            return False, shield.permeability, shield

        return True, shield.permeability, shield

    def explain_admissibility(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> dict[str, Any]:
        """Explain why an action is admissible or blocked.

        Returns a structured explanation including which scars matched,
        which one won, and what fields were used for matching.
        """
        matched = self._find_matching_scars(region, failure_kind, action_type)
        winner = self._find_most_restrictive_scar(region, failure_kind, action_type)

        admissible = True
        if winner and winner.is_hard:
            admissible = False

        return {
            "query": {
                "region": region,
                "failure_kind": failure_kind or "(unspecified)",
                "action_type": action_type or "(unspecified)",
            },
            "admissible": admissible,
            "cost": winner.effective_cost if winner else 1.0,
            "winner": winner.to_dict() if winner else None,
            "winner_fingerprint": winner.fingerprint if winner else None,
            "candidates": len(matched),
            "all_matches": [
                {
                    "scar_id": s.scar_id,
                    "fingerprint": s.fingerprint,
                    "stiffness": s.stiffness,
                    "is_hard": s.is_hard,
                }
                for s in sorted(matched, key=lambda s: -s.stiffness)
            ],
        }

    # =========================================================================
    # Annealing (Stiffness Relaxation)
    # =========================================================================

    def anneal_scars(self) -> dict[str, float]:
        """
        Attempt to anneal all scars that have enough evidence.

        Evidence-gated, not time-gated.

        Returns dict of {scar_id: amount_relaxed} for scars that annealed.
        """
        results = {}

        for scar in self.scars.values():
            if scar.can_anneal():
                amount = scar.anneal(self.config.anneal_decay_rate)
                if amount > 0:
                    results[scar.scar_id] = amount
                    self.total_anneals += 1

        return results

    def record_stability_evidence(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> bool:
        """
        Record evidence of stable operation in a scarred region.

        This is how scars eventually relax - not by time passing,
        but by proving stability under similar conditions.

        When failure_kind/action_type are provided, evidence targets
        only scars matching that fingerprint. When omitted, evidence
        applies to ALL scars in the region (backward compat).

        Uses evidence-direction matching: narrow evidence does NOT
        anneal broad scars (proving "timeout works" doesn't prove
        "everything works").

        Returns True if evidence was recorded for at least one scar.
        """
        failure_kind = _normalize_fingerprint_field(failure_kind)
        action_type = _normalize_fingerprint_field(action_type)
        matched = [
            scar for scar in self.scars.values()
            if scar.matches_evidence_fingerprint(region, failure_kind, action_type)
        ]
        if not matched:
            return False

        for scar in matched:
            scar.record_evidence()
        return True

    # =========================================================================
    # Shield Relaxation
    # =========================================================================

    def relax_shields(self) -> dict[str, float]:
        """
        Relax shields that have accumulated enough stable cycles.

        Returns dict of {shield_id: new_permeability} for shields that relaxed.
        """
        results = {}
        to_remove = []

        for shield in self.shields.values():
            if shield.can_release:
                shield.release()
                to_remove.append(shield.shield_id)
                results[shield.shield_id] = 1.0
                self.total_shield_releases += 1
            elif shield.stable_cycles_observed > 0 and shield.is_blocking:
                shield.relax(self.config.shield_relax_rate)
                results[shield.shield_id] = shield.permeability

        # Remove fully released shields
        for sid in to_remove:
            del self.shields[sid]

        return results

    def record_stable_input_cycle(self, source: str) -> bool:
        """
        Record a stable cycle for a shielded source.

        Returns True if the source had a shield to update.
        """
        shield = self._find_shield_by_source(source)
        if shield is None:
            return False

        shield.record_stable_cycle()
        return True

    def record_attack(self, source: str) -> bool:
        """
        Record a new attack on a shielded source.

        Returns True if the source had a shield to update.
        """
        shield = self._find_shield_by_source(source)
        if shield is None:
            return False

        shield.record_attack()
        return True

    # =========================================================================
    # Lookup Helpers
    # =========================================================================

    def _find_scar_by_region(self, region: str) -> Scar | None:
        """Find a scar by region (backward-compat: returns first match)."""
        for scar in self.scars.values():
            if scar.region == region:
                return scar
        return None

    def _find_exact_scar(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> Scar | None:
        """Find a scar with an exact fingerprint match."""
        for scar in self.scars.values():
            if (
                scar.region == region
                and scar.failure_kind == failure_kind
                and scar.action_type == action_type
            ):
                return scar
        return None

    def _find_matching_scars(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> list[Scar]:
        """Find all scars matching a fingerprint query."""
        return [
            scar for scar in self.scars.values()
            if scar.matches_fingerprint(region, failure_kind, action_type)
        ]

    def _find_similar_scar(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> Scar | None:
        """Find a scar in the same class (similar but not exact).

        "Similar" means: same region AND shares at least one non-empty
        fingerprint dimension (failure_kind or action_type) with the query.
        Region-only scars (both fields empty) are NOT similar — they're broad.

        Returns the most restrictive similar scar, or None.
        """
        candidates = []
        for scar in self.scars.values():
            if scar.region != region:
                continue
            # Skip broad scars (no fingerprint) — they're a different class
            if not scar.failure_kind and not scar.action_type:
                continue
            # Skip exact matches (handled by _find_exact_scar)
            if scar.failure_kind == failure_kind and scar.action_type == action_type:
                continue
            # Similar = shares at least one non-empty dimension
            kind_match = (
                failure_kind and scar.failure_kind
                and scar.failure_kind == failure_kind
            )
            action_match = (
                action_type and scar.action_type
                and scar.action_type == action_type
            )
            if kind_match or action_match:
                candidates.append(scar)

        if not candidates:
            return None
        return max(candidates, key=lambda s: (
            s.stiffness,
            len(s.failure_kind) + len(s.action_type),
            s.scar_id,
        ))

    def _find_most_restrictive_scar(
        self,
        region: str,
        failure_kind: str = "",
        action_type: str = "",
    ) -> Scar | None:
        """Find the most restrictive scar matching a fingerprint query.

        Tie-breaking is deterministic: highest stiffness wins, then
        narrowest fingerprint (more fields populated), then scar_id.
        """
        matched = self._find_matching_scars(region, failure_kind, action_type)
        if not matched:
            return None
        # Deterministic: stiffness desc, then specificity desc, then scar_id asc
        return max(matched, key=lambda s: (
            s.stiffness,
            len(s.failure_kind) + len(s.action_type),  # prefer specific scars
            s.scar_id,
        ))

    def _find_shield_by_source(self, source: str) -> Shield | None:
        """Find a shield by source."""
        for shield in self.shields.values():
            if shield.source == source:
                return shield
        return None

    # =========================================================================
    # Queries
    # =========================================================================

    def get_active_scars(self) -> list[Scar]:
        """Get all scars (scars are never removed, only relaxed)."""
        return list(self.scars.values())

    def get_hard_scars(self) -> list[Scar]:
        """Get scars at maximum stiffness (hard vetoes)."""
        return [s for s in self.scars.values() if s.is_hard]

    def get_soft_scars(self) -> list[Scar]:
        """Get scars that have been partially annealed."""
        return [s for s in self.scars.values() if s.is_soft]

    def get_active_shields(self) -> list[Shield]:
        """Get all active shields (blocking input)."""
        return [s for s in self.shields.values() if s.is_blocking]

    def get_scar(self, scar_id: str) -> Scar | None:
        """Get a scar by ID."""
        return self.scars.get(scar_id)

    def get_shield(self, shield_id: str) -> Shield | None:
        """Get a shield by ID."""
        return self.shields.get(shield_id)

    def get_failure_history(self, limit: int = 50) -> list[FailureEvent]:
        """Get recent failure history."""
        return self.failure_history[-limit:]

    def get_failures_by_region(self, region: str) -> list[FailureEvent]:
        """Get all failures for a specific region."""
        return [f for f in self.failure_history if f.region == region]

    def get_scarred_regions(self) -> list[str]:
        """Get list of all scarred regions."""
        return [s.region for s in self.scars.values()]

    def get_shielded_sources(self) -> list[str]:
        """Get list of all shielded sources."""
        return [s.source for s in self.shields.values()]

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> dict[str, Any]:
        """Get scar ledger metrics."""
        scars = list(self.scars.values())
        shields = list(self.shields.values())

        avg_stiffness = (
            sum(s.stiffness for s in scars) / len(scars) if scars else 0.0
        )
        avg_permeability = (
            sum(s.permeability for s in shields) / len(shields) if shields else 1.0
        )

        return {
            "total_failures": self.total_failures,
            "internal_failures": self.internal_failures,
            "external_failures": self.external_failures,
            "ambiguous_failures": self.ambiguous_failures,
            "total_scars": len(scars),
            "hard_scars": len([s for s in scars if s.is_hard]),
            "soft_scars": len([s for s in scars if s.is_soft]),
            "total_shields": len(shields),
            "active_shields": len([s for s in shields if s.is_blocking]),
            "avg_stiffness": avg_stiffness,
            "avg_permeability": avg_permeability,
            "total_anneals": self.total_anneals,
            "total_shield_releases": self.total_shield_releases,
            "provenance_distribution": {
                "internal": self.internal_failures,
                "external": self.external_failures,
                "ambiguous": self.ambiguous_failures,
            },
        }

    def get_summary(self) -> dict[str, Any]:
        """Get a concise summary of system state."""
        metrics = self.get_metrics()
        return {
            "scars": f"{metrics['hard_scars']} hard, {metrics['soft_scars']} soft",
            "shields": f"{metrics['active_shields']} active of {metrics['total_shields']}",
            "failures": f"{metrics['total_failures']} total ({metrics['internal_failures']}I/{metrics['external_failures']}E/{metrics['ambiguous_failures']}A)",
            "health": (
                "CONSTRAINED" if metrics["hard_scars"] > 0
                else "CAUTIOUS" if metrics["total_scars"] > 0
                else "NOMINAL"
            ),
        }

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize ledger state."""
        return {
            "config": self.config.to_dict(),
            "scars": {sid: s.to_dict() for sid, s in self.scars.items()},
            "shields": {sid: s.to_dict() for sid, s in self.shields.items()},
            "failure_history": [f.to_dict() for f in self.failure_history],
            "metrics": {
                "total_failures": self.total_failures,
                "internal_failures": self.internal_failures,
                "external_failures": self.external_failures,
                "ambiguous_failures": self.ambiguous_failures,
                "total_anneals": self.total_anneals,
                "total_shield_releases": self.total_shield_releases,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScarLedger":
        """Deserialize ledger from dictionary."""
        config = ScarConfig.from_dict(data.get("config", {}))
        ledger = cls(config)

        # Restore scars
        for sid, sdata in data.get("scars", {}).items():
            ledger.scars[sid] = Scar.from_dict(sdata)

        # Restore shields
        for sid, sdata in data.get("shields", {}).items():
            ledger.shields[sid] = Shield.from_dict(sdata)

        # Restore failure history
        ledger.failure_history = [
            FailureEvent.from_dict(f) for f in data.get("failure_history", [])
        ]

        # Restore metrics
        metrics = data.get("metrics", {})
        ledger.total_failures = metrics.get("total_failures", 0)
        ledger.internal_failures = metrics.get("internal_failures", 0)
        ledger.external_failures = metrics.get("external_failures", 0)
        ledger.ambiguous_failures = metrics.get("ambiguous_failures", 0)
        ledger.total_anneals = metrics.get("total_anneals", 0)
        ledger.total_shield_releases = metrics.get("total_shield_releases", 0)

        return ledger

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2, default=str)


# =============================================================================
# Convenience Functions
# =============================================================================


def create_scar_ledger(
    rho_lo: float = 0.3,
    rho_hi: float = 0.7,
    regularity_bound: float = 1.0,
) -> ScarLedger:
    """Create a scar ledger with custom thresholds."""
    config = ScarConfig(
        rho_lo=rho_lo,
        rho_hi=rho_hi,
        regularity_bound=regularity_bound,
    )
    return ScarLedger(config)


def classify_failure(
    observation_shift: float,
    prediction_error: float,
    rho_lo: float = 0.3,
    rho_hi: float = 0.7,
) -> tuple[FailureProvenance, float]:
    """Standalone failure classification (for testing/inspection)."""
    config = ScarConfig(rho_lo=rho_lo, rho_hi=rho_hi)
    ledger = ScarLedger(config)
    return ledger.classify_failure(observation_shift, prediction_error)
