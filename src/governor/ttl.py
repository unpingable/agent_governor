"""
Recency decay and TTL enforcement for committed assertions.

Claims get a TTL based on their volatility class. Stale claims auto-degrade
(confidence reduced) or are retracted. A revalidation scheduler tracks which
claims need periodic re-checking.

Volatility classes (from stable to volatile):
- PERMANENT: No decay (architectural decisions, mathematical facts)
- STABLE: Long TTL, slow decay (library versions, API contracts)
- MODERATE: Medium TTL (test results, build status)
- VOLATILE: Short TTL, fast decay (runtime metrics, live API responses)
- EPHEMERAL: Very short TTL (in-flight state, cache values)

Key invariants:
1. TTL is assigned at creation based on volatility class
2. Expired claims auto-degrade confidence (not silently dropped)
3. Revalidation produces a schedule of claims needing re-check
4. Decay is proportional to time past expiry
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any


# =============================================================================
# Volatility Classes
# =============================================================================


class VolatilityClass(str, Enum):
    """How quickly a claim's truth value may change."""

    PERMANENT = "permanent"
    """Never expires. Architectural decisions, mathematical truths."""

    STABLE = "stable"
    """Long-lived. Library versions, API contracts, schema definitions."""

    MODERATE = "moderate"
    """Medium-lived. Test results, build status, dependency checks."""

    VOLATILE = "volatile"
    """Short-lived. Runtime metrics, live API responses, external state."""

    EPHEMERAL = "ephemeral"
    """Very short-lived. In-flight state, cache values, session data."""


class DecayAction(str, Enum):
    """What happens when a claim expires."""

    NONE = "none"
    """No action (claim is still fresh)."""

    DEGRADE = "degrade"
    """Reduce confidence (claim is stale but not retracted)."""

    RETRACT = "retract"
    """Auto-retract (claim is too old to be trusted)."""


# =============================================================================
# TTL Configuration
# =============================================================================


@dataclass
class TTLPolicy:
    """TTL and decay parameters for a volatility class."""

    volatility: VolatilityClass
    ttl: timedelta | None  # None = no expiry
    decay_rate: float  # Confidence reduction per decay period
    decay_period: timedelta  # How often decay is applied after expiry
    retract_after: timedelta | None  # Auto-retract after this duration past expiry

    def to_dict(self) -> dict[str, Any]:
        return {
            "volatility": self.volatility.value,
            "ttl_seconds": self.ttl.total_seconds() if self.ttl else None,
            "decay_rate": self.decay_rate,
            "decay_period_seconds": self.decay_period.total_seconds(),
            "retract_after_seconds": (
                self.retract_after.total_seconds() if self.retract_after else None
            ),
        }


# Default policies per volatility class
DEFAULT_POLICIES: dict[VolatilityClass, TTLPolicy] = {
    VolatilityClass.PERMANENT: TTLPolicy(
        volatility=VolatilityClass.PERMANENT,
        ttl=None,
        decay_rate=0.0,
        decay_period=timedelta(hours=1),
        retract_after=None,
    ),
    VolatilityClass.STABLE: TTLPolicy(
        volatility=VolatilityClass.STABLE,
        ttl=timedelta(days=7),
        decay_rate=0.05,
        decay_period=timedelta(days=1),
        retract_after=timedelta(days=30),
    ),
    VolatilityClass.MODERATE: TTLPolicy(
        volatility=VolatilityClass.MODERATE,
        ttl=timedelta(hours=24),
        decay_rate=0.1,
        decay_period=timedelta(hours=6),
        retract_after=timedelta(days=7),
    ),
    VolatilityClass.VOLATILE: TTLPolicy(
        volatility=VolatilityClass.VOLATILE,
        ttl=timedelta(hours=1),
        decay_rate=0.2,
        decay_period=timedelta(minutes=30),
        retract_after=timedelta(hours=24),
    ),
    VolatilityClass.EPHEMERAL: TTLPolicy(
        volatility=VolatilityClass.EPHEMERAL,
        ttl=timedelta(minutes=5),
        decay_rate=0.3,
        decay_period=timedelta(minutes=5),
        retract_after=timedelta(hours=1),
    ),
}


# =============================================================================
# Tracked Claim
# =============================================================================


@dataclass
class TrackedClaim:
    """A claim with TTL tracking metadata."""

    claim_id: str
    volatility: VolatilityClass
    created_at: datetime
    last_validated_at: datetime
    original_confidence: float
    current_confidence: float
    retracted: bool = False
    retracted_at: datetime | None = None

    @property
    def age(self) -> timedelta:
        return datetime.now() - self.created_at

    @property
    def time_since_validation(self) -> timedelta:
        return datetime.now() - self.last_validated_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "volatility": self.volatility.value,
            "created_at": self.created_at.isoformat(),
            "last_validated_at": self.last_validated_at.isoformat(),
            "original_confidence": self.original_confidence,
            "current_confidence": self.current_confidence,
            "retracted": self.retracted,
        }


@dataclass
class DecayEvent:
    """Record of a decay or retraction event."""

    claim_id: str
    action: DecayAction
    old_confidence: float
    new_confidence: float
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RevalidationEntry:
    """A claim that needs revalidation."""

    claim_id: str
    volatility: VolatilityClass
    time_since_validation: timedelta
    current_confidence: float
    urgency: float  # 0.0–1.0, higher = more urgent


# =============================================================================
# TTL Manager
# =============================================================================


class TTLManager:
    """
    Manages TTL enforcement and recency decay for tracked claims.

    Call enforce() periodically to apply decay and retraction.
    Call revalidation_schedule() to get claims needing re-check.
    """

    def __init__(self, policies: dict[VolatilityClass, TTLPolicy] | None = None):
        self.policies = policies or dict(DEFAULT_POLICIES)
        self.tracked: dict[str, TrackedClaim] = {}
        self.events: list[DecayEvent] = []

    def get_policy(self, volatility: VolatilityClass) -> TTLPolicy:
        return self.policies[volatility]

    def track(
        self,
        claim_id: str,
        volatility: VolatilityClass,
        confidence: float,
        created_at: datetime | None = None,
    ) -> TrackedClaim:
        """Start tracking a claim with a volatility class."""
        now = created_at or datetime.now()
        tc = TrackedClaim(
            claim_id=claim_id,
            volatility=volatility,
            created_at=now,
            last_validated_at=now,
            original_confidence=confidence,
            current_confidence=confidence,
        )
        self.tracked[claim_id] = tc
        return tc

    def revalidate(self, claim_id: str) -> bool:
        """Mark a claim as freshly validated. Returns True if found."""
        tc = self.tracked.get(claim_id)
        if tc is None or tc.retracted:
            return False
        tc.last_validated_at = datetime.now()
        tc.current_confidence = tc.original_confidence
        return True

    def get(self, claim_id: str) -> TrackedClaim | None:
        return self.tracked.get(claim_id)

    def is_expired(self, claim_id: str, now: datetime | None = None) -> bool:
        """Check if a claim has exceeded its TTL."""
        tc = self.tracked.get(claim_id)
        if tc is None:
            return False
        policy = self.policies[tc.volatility]
        if policy.ttl is None:
            return False  # Permanent
        now = now or datetime.now()
        return (now - tc.last_validated_at) > policy.ttl

    def check_claim(self, claim_id: str, now: datetime | None = None) -> DecayAction:
        """Check what decay action applies to a claim right now."""
        tc = self.tracked.get(claim_id)
        if tc is None or tc.retracted:
            return DecayAction.NONE

        policy = self.policies[tc.volatility]
        if policy.ttl is None:
            return DecayAction.NONE

        now = now or datetime.now()
        elapsed = now - tc.last_validated_at

        if elapsed <= policy.ttl:
            return DecayAction.NONE

        past_expiry = elapsed - policy.ttl
        if policy.retract_after and past_expiry >= policy.retract_after:
            return DecayAction.RETRACT

        return DecayAction.DEGRADE

    def enforce(self, now: datetime | None = None) -> list[DecayEvent]:
        """
        Apply decay and retraction to all tracked claims.

        Returns list of events (actions taken).
        """
        now = now or datetime.now()
        events: list[DecayEvent] = []

        for tc in list(self.tracked.values()):
            if tc.retracted:
                continue

            action = self.check_claim(tc.claim_id, now)

            if action == DecayAction.RETRACT:
                old = tc.current_confidence
                tc.current_confidence = 0.0
                tc.retracted = True
                tc.retracted_at = now
                ev = DecayEvent(
                    claim_id=tc.claim_id,
                    action=DecayAction.RETRACT,
                    old_confidence=old,
                    new_confidence=0.0,
                    reason=f"TTL retraction: {tc.volatility.value} claim expired",
                    timestamp=now,
                )
                events.append(ev)

            elif action == DecayAction.DEGRADE:
                policy = self.policies[tc.volatility]
                elapsed = now - tc.last_validated_at
                past_expiry = elapsed - policy.ttl
                periods = past_expiry / policy.decay_period
                decay_amount = policy.decay_rate * periods
                old = tc.current_confidence
                tc.current_confidence = max(0.0, tc.original_confidence - decay_amount)

                if tc.current_confidence != old:
                    ev = DecayEvent(
                        claim_id=tc.claim_id,
                        action=DecayAction.DEGRADE,
                        old_confidence=old,
                        new_confidence=tc.current_confidence,
                        reason=f"TTL decay: {periods:.1f} periods past expiry",
                        timestamp=now,
                    )
                    events.append(ev)

        self.events.extend(events)
        return events

    def revalidation_schedule(self, now: datetime | None = None) -> list[RevalidationEntry]:
        """
        Get claims that need revalidation, sorted by urgency.

        Urgency is based on how close to (or past) expiry the claim is.
        """
        now = now or datetime.now()
        entries: list[RevalidationEntry] = []

        for tc in self.tracked.values():
            if tc.retracted:
                continue
            policy = self.policies[tc.volatility]
            if policy.ttl is None:
                continue

            elapsed = now - tc.last_validated_at
            ratio = elapsed / policy.ttl
            urgency = min(1.0, max(0.0, ratio))

            # Only include claims that are at least 50% through their TTL
            if urgency >= 0.5:
                entries.append(RevalidationEntry(
                    claim_id=tc.claim_id,
                    volatility=tc.volatility,
                    time_since_validation=elapsed,
                    current_confidence=tc.current_confidence,
                    urgency=urgency,
                ))

        entries.sort(key=lambda e: e.urgency, reverse=True)
        return entries

    # =========================================================================
    # Queries
    # =========================================================================

    def active_claims(self) -> list[TrackedClaim]:
        return [tc for tc in self.tracked.values() if not tc.retracted]

    def retracted_claims(self) -> list[TrackedClaim]:
        return [tc for tc in self.tracked.values() if tc.retracted]

    def expired_claims(self, now: datetime | None = None) -> list[TrackedClaim]:
        now = now or datetime.now()
        return [
            tc for tc in self.tracked.values()
            if not tc.retracted and self.is_expired(tc.claim_id, now)
        ]

    def claims_by_volatility(self, v: VolatilityClass) -> list[TrackedClaim]:
        return [tc for tc in self.tracked.values() if tc.volatility == v]

    def get_metrics(self) -> dict[str, Any]:
        active = self.active_claims()
        return {
            "total_tracked": len(self.tracked),
            "active": len(active),
            "retracted": len(self.retracted_claims()),
            "expired": len(self.expired_claims()),
            "total_events": len(self.events),
            "by_volatility": {
                v.value: len(self.claims_by_volatility(v))
                for v in VolatilityClass
            },
        }


# =============================================================================
# Convenience
# =============================================================================


def create_ttl_manager(
    policies: dict[VolatilityClass, TTLPolicy] | None = None,
) -> TTLManager:
    """Create a TTL manager with optional custom policies."""
    return TTLManager(policies)
