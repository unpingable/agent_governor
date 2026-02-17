# SPDX-License-Identifier: Apache-2.0
"""
Staleness detection: Time-bounded verification and artifact mutation tracking.

Verification is not a property of artifacts. It is a time-bounded relation
between artifact, context, and evidence.

This module extends TTL with:
- Artifact mutation detection (file hash changed)
- Assumption violation tracking
- Re-verification triggering

Flow: TTL decay -> confidence reduction -> staleness check -> ClaimStatus = STALE
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .epistemic import EpistemicLedger, GroundedClaim


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class StalenessConfig:
    """Configuration for staleness detection."""

    # Default freshness window (how long before decay begins)
    default_freshness_window: timedelta = field(
        default_factory=lambda: timedelta(days=7)
    )

    # Decay rate per day after freshness window expires
    default_decay_rate: float = 0.1

    # Confidence threshold below which a claim is considered stale
    confidence_threshold: float = 0.5

    # Confidence penalty when an assumption is violated
    assumption_violation_penalty: float = 0.3

    # Per-claim-type overrides: {claim_type: {freshness_window_days: int, ...}}
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_freshness_window(self, claim_type: str | None = None) -> timedelta:
        """Get freshness window, with optional per-type override."""
        if claim_type and claim_type in self.overrides:
            days = self.overrides[claim_type].get("freshness_window_days")
            if days is not None:
                return timedelta(days=days)
        return self.default_freshness_window

    def get_decay_rate(self, claim_type: str | None = None) -> float:
        """Get decay rate, with optional per-type override."""
        if claim_type and claim_type in self.overrides:
            rate = self.overrides[claim_type].get("decay_rate")
            if rate is not None:
                return rate
        return self.default_decay_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_freshness_window_days": self.default_freshness_window.days,
            "default_decay_rate": self.default_decay_rate,
            "confidence_threshold": self.confidence_threshold,
            "assumption_violation_penalty": self.assumption_violation_penalty,
            "overrides": self.overrides,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StalenessConfig:
        return cls(
            default_freshness_window=timedelta(
                days=data.get("default_freshness_window_days", 7)
            ),
            default_decay_rate=data.get("default_decay_rate", 0.1),
            confidence_threshold=data.get("confidence_threshold", 0.5),
            assumption_violation_penalty=data.get("assumption_violation_penalty", 0.3),
            overrides=data.get("overrides", {}),
        )


# =============================================================================
# Freshness Result
# =============================================================================


@dataclass
class ClaimFreshness:
    """Result of computing a claim's freshness status."""

    claim_id: str
    confidence: float
    verified_at: datetime | None
    freshness_window: timedelta
    time_since_verification: timedelta
    decay_amount: float
    violated_assumptions: list[str]
    is_live: bool  # confidence >= threshold
    staleness_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "confidence": self.confidence,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "freshness_window_seconds": self.freshness_window.total_seconds(),
            "time_since_verification_seconds": self.time_since_verification.total_seconds(),
            "decay_amount": self.decay_amount,
            "violated_assumptions": self.violated_assumptions,
            "is_live": self.is_live,
            "staleness_reason": self.staleness_reason,
        }


# =============================================================================
# Staleness Event
# =============================================================================


@dataclass
class StalenessEvent:
    """Record of a staleness detection event."""

    event_id: str
    claim_id: str
    event_type: str  # "decay", "artifact_mutation", "assumption_violation"
    reason: str
    old_confidence: float
    new_confidence: float
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "claim_id": self.claim_id,
            "event_type": self.event_type,
            "reason": self.reason,
            "old_confidence": self.old_confidence,
            "new_confidence": self.new_confidence,
            "created_at": self.created_at.isoformat(),
        }


# =============================================================================
# Staleness Detector
# =============================================================================


class StalenessDetector:
    """
    Detects stale claims based on time decay and artifact mutation.

    Staleness adds to TTL:
    - Artifact mutation detection (file hash changed)
    - Assumption violation tracking
    - Re-verification triggering
    """

    def __init__(
        self,
        ledger: EpistemicLedger,
        config: StalenessConfig | None = None,
    ):
        self.ledger = ledger
        self.config = config or StalenessConfig()
        self.events: list[StalenessEvent] = []
        self._artifact_hashes: dict[str, dict[str, str]] = {}  # claim_id -> {path: hash}

    def compute_freshness(
        self,
        claim_id: str,
        now: datetime | None = None,
    ) -> ClaimFreshness:
        """
        Compute the freshness status of a claim.

        Returns ClaimFreshness with decay info and staleness status.
        """
        now = now or datetime.now()
        claim = self.ledger.get(claim_id)

        if claim is None:
            return ClaimFreshness(
                claim_id=claim_id,
                confidence=0.0,
                verified_at=None,
                freshness_window=self.config.default_freshness_window,
                time_since_verification=timedelta(0),
                decay_amount=0.0,
                violated_assumptions=[],
                is_live=False,
                staleness_reason="Claim not found",
            )

        # Get claim type for overrides
        claim_type = getattr(claim, "claim_type", None)
        freshness_window = self.config.get_freshness_window(claim_type)
        decay_rate = self.config.get_decay_rate(claim_type)

        # Determine verified_at time
        # Use last_updated_at as proxy for verification time
        verified_at = claim.last_updated_at
        time_since = now - verified_at

        # Calculate decay
        decay_amount = 0.0
        if time_since > freshness_window:
            # Days past freshness window
            past_window = time_since - freshness_window
            days_past = past_window.total_seconds() / 86400
            decay_amount = decay_rate * days_past

        # Check assumption violations
        violated = self._check_assumptions(claim)

        # Calculate effective confidence
        effective_confidence = claim.confidence - decay_amount
        effective_confidence -= len(violated) * self.config.assumption_violation_penalty
        effective_confidence = max(0.0, min(1.0, effective_confidence))

        # Determine if live
        is_live = effective_confidence >= self.config.confidence_threshold

        # Determine staleness reason
        staleness_reason: str | None = None
        if not is_live:
            if decay_amount > 0:
                staleness_reason = f"Decayed {decay_amount:.2f} after freshness window"
            if violated:
                if staleness_reason:
                    staleness_reason += f"; assumptions violated: {', '.join(violated)}"
                else:
                    staleness_reason = f"Assumptions violated: {', '.join(violated)}"

        return ClaimFreshness(
            claim_id=claim_id,
            confidence=effective_confidence,
            verified_at=verified_at,
            freshness_window=freshness_window,
            time_since_verification=time_since,
            decay_amount=decay_amount,
            violated_assumptions=violated,
            is_live=is_live,
            staleness_reason=staleness_reason,
        )

    def detect_stale_claims(
        self,
        now: datetime | None = None,
    ) -> list[ClaimFreshness]:
        """
        Detect all stale claims in the ledger.

        Returns list of ClaimFreshness for claims that are not live.
        """
        now = now or datetime.now()
        stale: list[ClaimFreshness] = []

        for claim_id in self.ledger.claims:
            freshness = self.compute_freshness(claim_id, now)
            if not freshness.is_live:
                stale.append(freshness)

        return stale

    def check_artifact_hash(self, claim_id: str, path: str) -> bool:
        """
        Check if an artifact's hash has changed since last verification.

        Returns True if hash is unchanged (artifact is fresh), False if changed.
        """
        # Get stored hash
        stored_hashes = self._artifact_hashes.get(claim_id, {})
        stored_hash = stored_hashes.get(path)

        # Compute current hash
        try:
            file_path = Path(path)
            if not file_path.exists():
                # File deleted = artifact mutated
                return stored_hash is None

            content = file_path.read_bytes()
            current_hash = hashlib.sha256(content).hexdigest()[:16]
        except (OSError, IOError):
            # Can't read file = treat as mutated
            return False

        if stored_hash is None:
            # First check - store and consider fresh
            self._artifact_hashes.setdefault(claim_id, {})[path] = current_hash
            return True

        return current_hash == stored_hash

    def record_artifact_hash(self, claim_id: str, path: str) -> str:
        """
        Record the current hash of an artifact for a claim.

        Returns the hash.
        """
        try:
            content = Path(path).read_bytes()
            hash_value = hashlib.sha256(content).hexdigest()[:16]
        except (OSError, IOError):
            hash_value = ""

        self._artifact_hashes.setdefault(claim_id, {})[path] = hash_value
        return hash_value

    def mark_stale(
        self,
        claim_id: str,
        reason: str,
        event_type: str = "manual",
    ) -> StalenessEvent | None:
        """
        Mark a claim as stale and record the event.

        Returns the StalenessEvent if claim was found.
        """
        claim = self.ledger.get(claim_id)
        if claim is None:
            return None

        old_confidence = claim.confidence
        new_confidence = 0.0

        # Update claim
        claim.confidence = new_confidence
        claim.last_updated_at = datetime.now()

        # Transition epistemic status to STALE if applicable
        from .epistemic import ClaimStatus, TransitionReason

        if claim.epistemic_status is not None:
            self.ledger.transition_epistemic_status(
                claim_id,
                ClaimStatus.STALE,
                TransitionReason.TTL_EXPIRY,
                f"Marked stale: {reason}",
            )

        # Record event
        import uuid

        event = StalenessEvent(
            event_id=f"se_{uuid.uuid4().hex[:12]}",
            claim_id=claim_id,
            event_type=event_type,
            reason=reason,
            old_confidence=old_confidence,
            new_confidence=new_confidence,
        )
        self.events.append(event)

        return event

    def run_staleness_check(
        self,
        now: datetime | None = None,
    ) -> list[str]:
        """
        Run a full staleness check and mark stale claims.

        Returns list of newly stale claim IDs.
        """
        now = now or datetime.now()
        newly_stale: list[str] = []

        for claim_id in list(self.ledger.claims.keys()):
            freshness = self.compute_freshness(claim_id, now)
            if not freshness.is_live and freshness.staleness_reason:
                # Only mark if not already stale
                claim = self.ledger.get(claim_id)
                from .epistemic import ClaimStatus

                if claim and claim.epistemic_status != ClaimStatus.STALE:
                    self.mark_stale(
                        claim_id,
                        freshness.staleness_reason,
                        event_type="decay" if freshness.decay_amount > 0 else "assumption_violation",
                    )
                    newly_stale.append(claim_id)

        return newly_stale

    def _check_assumptions(self, claim: GroundedClaim) -> list[str]:
        """
        Check which of a claim's assumptions have been violated.

        Returns list of violated assumption descriptions.
        """
        violated: list[str] = []

        # Check explicit assumptions
        for assumption in claim.assumptions:
            # Simple heuristic: if assumption mentions a file path, check it exists
            if "/" in assumption or "\\" in assumption:
                # Extract path-like strings
                words = assumption.split()
                for word in words:
                    if "/" in word or "\\" in word:
                        clean_path = word.strip("'\".,;:()")
                        if not Path(clean_path).exists():
                            violated.append(f"File missing: {clean_path}")

        return violated

    def get_metrics(self) -> dict[str, Any]:
        """Get staleness detector metrics."""
        total_claims = len(self.ledger.claims)
        stale_claims = len(self.detect_stale_claims())
        return {
            "total_claims": total_claims,
            "stale_claims": stale_claims,
            "live_claims": total_claims - stale_claims,
            "total_events": len(self.events),
            "tracked_artifacts": sum(
                len(hashes) for hashes in self._artifact_hashes.values()
            ),
        }


# =============================================================================
# Convenience
# =============================================================================


def create_staleness_detector(
    ledger: EpistemicLedger,
    config: StalenessConfig | None = None,
) -> StalenessDetector:
    """Create a StalenessDetector for an epistemic ledger."""
    return StalenessDetector(ledger, config)
