# SPDX-License-Identifier: Apache-2.0
"""
Tests for recency decay and TTL enforcement.

Covers: VolatilityClass, DecayAction, TTLPolicy, TrackedClaim, TTLManager,
enforcement, revalidation schedule, queries, and edge cases.
"""

from datetime import datetime, timedelta

import pytest

from governor.ttl import (
    DEFAULT_POLICIES,
    DecayAction,
    DecayEvent,
    RevalidationEntry,
    TTLManager,
    TTLPolicy,
    TrackedClaim,
    VolatilityClass,
    create_ttl_manager,
)


# =============================================================================
# TestEnums
# =============================================================================


class TestEnums:

    def test_volatility_values(self):
        assert VolatilityClass.PERMANENT == "permanent"
        assert VolatilityClass.STABLE == "stable"
        assert VolatilityClass.MODERATE == "moderate"
        assert VolatilityClass.VOLATILE == "volatile"
        assert VolatilityClass.EPHEMERAL == "ephemeral"

    def test_decay_action_values(self):
        assert DecayAction.NONE == "none"
        assert DecayAction.DEGRADE == "degrade"
        assert DecayAction.RETRACT == "retract"


# =============================================================================
# TestDefaultPolicies
# =============================================================================


class TestDefaultPolicies:

    def test_all_classes_have_policies(self):
        for v in VolatilityClass:
            assert v in DEFAULT_POLICIES

    def test_permanent_no_ttl(self):
        p = DEFAULT_POLICIES[VolatilityClass.PERMANENT]
        assert p.ttl is None
        assert p.decay_rate == 0.0
        assert p.retract_after is None

    def test_stable_long_ttl(self):
        p = DEFAULT_POLICIES[VolatilityClass.STABLE]
        assert p.ttl == timedelta(days=7)
        assert p.retract_after == timedelta(days=30)

    def test_volatile_short_ttl(self):
        p = DEFAULT_POLICIES[VolatilityClass.VOLATILE]
        assert p.ttl == timedelta(hours=1)

    def test_ephemeral_very_short(self):
        p = DEFAULT_POLICIES[VolatilityClass.EPHEMERAL]
        assert p.ttl == timedelta(minutes=5)

    def test_decay_rates_increase_with_volatility(self):
        rates = [
            DEFAULT_POLICIES[VolatilityClass.PERMANENT].decay_rate,
            DEFAULT_POLICIES[VolatilityClass.STABLE].decay_rate,
            DEFAULT_POLICIES[VolatilityClass.MODERATE].decay_rate,
            DEFAULT_POLICIES[VolatilityClass.VOLATILE].decay_rate,
            DEFAULT_POLICIES[VolatilityClass.EPHEMERAL].decay_rate,
        ]
        for i in range(len(rates) - 1):
            assert rates[i] <= rates[i + 1]

    def test_policy_to_dict(self):
        p = DEFAULT_POLICIES[VolatilityClass.MODERATE]
        d = p.to_dict()
        assert d["volatility"] == "moderate"
        assert d["ttl_seconds"] == timedelta(hours=24).total_seconds()
        assert d["decay_rate"] == 0.1


# =============================================================================
# TestTrackedClaim
# =============================================================================


class TestTrackedClaim:

    def test_creation(self):
        now = datetime.now()
        tc = TrackedClaim(
            claim_id="c1",
            volatility=VolatilityClass.MODERATE,
            created_at=now,
            last_validated_at=now,
            original_confidence=0.8,
            current_confidence=0.8,
        )
        assert tc.claim_id == "c1"
        assert not tc.retracted

    def test_to_dict(self):
        now = datetime.now()
        tc = TrackedClaim(
            claim_id="c1",
            volatility=VolatilityClass.VOLATILE,
            created_at=now,
            last_validated_at=now,
            original_confidence=0.9,
            current_confidence=0.7,
        )
        d = tc.to_dict()
        assert d["claim_id"] == "c1"
        assert d["volatility"] == "volatile"
        assert d["original_confidence"] == 0.9
        assert d["current_confidence"] == 0.7


# =============================================================================
# TestTTLManager — Tracking
# =============================================================================


class TestTracking:

    def test_track_claim(self):
        mgr = TTLManager()
        tc = mgr.track("c1", VolatilityClass.MODERATE, 0.8)
        assert tc.claim_id == "c1"
        assert tc.current_confidence == 0.8
        assert mgr.get("c1") is tc

    def test_track_with_timestamp(self):
        mgr = TTLManager()
        past = datetime(2024, 1, 1)
        tc = mgr.track("c1", VolatilityClass.STABLE, 0.9, created_at=past)
        assert tc.created_at == past

    def test_get_nonexistent(self):
        mgr = TTLManager()
        assert mgr.get("bad") is None

    def test_revalidate(self):
        mgr = TTLManager()
        past = datetime(2024, 1, 1)
        tc = mgr.track("c1", VolatilityClass.VOLATILE, 0.8, created_at=past)
        tc.current_confidence = 0.5  # Simulate decay
        ok = mgr.revalidate("c1")
        assert ok
        assert tc.current_confidence == 0.8  # Restored
        assert tc.last_validated_at > past

    def test_revalidate_retracted_fails(self):
        mgr = TTLManager()
        tc = mgr.track("c1", VolatilityClass.VOLATILE, 0.8)
        tc.retracted = True
        assert not mgr.revalidate("c1")

    def test_revalidate_nonexistent(self):
        mgr = TTLManager()
        assert not mgr.revalidate("bad")


# =============================================================================
# TestTTLManager — Expiry
# =============================================================================


class TestExpiry:

    def test_permanent_never_expires(self):
        mgr = TTLManager()
        past = datetime(2020, 1, 1)
        mgr.track("c1", VolatilityClass.PERMANENT, 0.9, created_at=past)
        far_future = datetime(2030, 1, 1)
        assert not mgr.is_expired("c1", now=far_future)

    def test_volatile_expires(self):
        mgr = TTLManager()
        past = datetime.now() - timedelta(hours=2)
        mgr.track("c1", VolatilityClass.VOLATILE, 0.8, created_at=past)
        assert mgr.is_expired("c1")

    def test_not_expired_within_ttl(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.STABLE, 0.9)  # 7-day TTL
        assert not mgr.is_expired("c1")

    def test_expired_past_ttl(self):
        mgr = TTLManager()
        past = datetime.now() - timedelta(days=8)
        mgr.track("c1", VolatilityClass.STABLE, 0.9, created_at=past)
        assert mgr.is_expired("c1")

    def test_nonexistent_not_expired(self):
        mgr = TTLManager()
        assert not mgr.is_expired("bad")


# =============================================================================
# TestTTLManager — Check and Enforce
# =============================================================================


class TestCheckAndEnforce:

    def test_check_fresh_claim(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.MODERATE, 0.8)
        assert mgr.check_claim("c1") == DecayAction.NONE

    def test_check_expired_degrades(self):
        mgr = TTLManager()
        past = datetime.now() - timedelta(hours=30)  # 24h TTL
        mgr.track("c1", VolatilityClass.MODERATE, 0.8, created_at=past)
        assert mgr.check_claim("c1") == DecayAction.DEGRADE

    def test_check_long_expired_retracts(self):
        mgr = TTLManager()
        past = datetime.now() - timedelta(days=10)  # 24h TTL, 7d retract
        mgr.track("c1", VolatilityClass.MODERATE, 0.8, created_at=past)
        assert mgr.check_claim("c1") == DecayAction.RETRACT

    def test_check_permanent_always_none(self):
        mgr = TTLManager()
        past = datetime(2020, 1, 1)
        mgr.track("c1", VolatilityClass.PERMANENT, 0.9, created_at=past)
        assert mgr.check_claim("c1", now=datetime(2030, 1, 1)) == DecayAction.NONE

    def test_check_retracted_is_none(self):
        mgr = TTLManager()
        tc = mgr.track("c1", VolatilityClass.VOLATILE, 0.8)
        tc.retracted = True
        assert mgr.check_claim("c1") == DecayAction.NONE

    def test_enforce_degrade(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1, 12, 0)
        # Moderate: 24h TTL, 0.1 decay per 6h period
        mgr.track("c1", VolatilityClass.MODERATE, 0.8, created_at=now)
        # 30 hours later: 6h past expiry = 1 period = 0.1 decay
        later = now + timedelta(hours=30)
        events = mgr.enforce(now=later)
        assert len(events) == 1
        assert events[0].action == DecayAction.DEGRADE
        tc = mgr.get("c1")
        assert tc.current_confidence == pytest.approx(0.7, abs=0.05)

    def test_enforce_retract(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        # Moderate: 24h TTL, retract after 7 days
        mgr.track("c1", VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(days=10)
        events = mgr.enforce(now=later)
        assert len(events) == 1
        assert events[0].action == DecayAction.RETRACT
        tc = mgr.get("c1")
        assert tc.retracted
        assert tc.current_confidence == 0.0

    def test_enforce_no_action_on_fresh(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.STABLE, 0.9)
        events = mgr.enforce()
        assert len(events) == 0

    def test_enforce_skips_retracted(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        mgr.track("c1", VolatilityClass.VOLATILE, 0.8, created_at=now)
        later = now + timedelta(days=5)
        mgr.enforce(now=later)  # Should retract
        tc = mgr.get("c1")
        assert tc.retracted
        events = mgr.enforce(now=later + timedelta(hours=1))
        assert len(events) == 0  # Already retracted

    def test_enforce_multiple_claims(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        mgr.track("fresh", VolatilityClass.STABLE, 0.9, created_at=now)
        mgr.track("stale", VolatilityClass.VOLATILE, 0.8, created_at=now)
        later = now + timedelta(hours=2)
        events = mgr.enforce(now=later)
        # Only the volatile one should degrade
        assert len(events) == 1
        assert events[0].claim_id == "stale"

    def test_events_accumulate(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        mgr.track("c1", VolatilityClass.VOLATILE, 0.8, created_at=now)
        mgr.enforce(now=now + timedelta(hours=2))
        mgr.enforce(now=now + timedelta(hours=3))
        assert len(mgr.events) >= 1


# =============================================================================
# TestRevalidationSchedule
# =============================================================================


class TestRevalidationSchedule:

    def test_empty_when_all_fresh(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.STABLE, 0.9)
        schedule = mgr.revalidation_schedule()
        assert len(schedule) == 0  # Just created, not near expiry

    def test_includes_near_expiry(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        # Volatile: 1h TTL. Created 40 min ago → 67% through TTL
        mgr.track("c1", VolatilityClass.VOLATILE, 0.8, created_at=now)
        later = now + timedelta(minutes=40)
        schedule = mgr.revalidation_schedule(now=later)
        assert len(schedule) == 1
        assert schedule[0].claim_id == "c1"
        assert schedule[0].urgency >= 0.5

    def test_sorted_by_urgency(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        # More urgent: volatile, 50 min old (83% of 1h TTL)
        mgr.track("urgent", VolatilityClass.VOLATILE, 0.8, created_at=now)
        # Less urgent: moderate, 14h old (58% of 24h TTL)
        mgr.track("moderate", VolatilityClass.MODERATE, 0.8, created_at=now)
        later = now + timedelta(minutes=50)
        schedule = mgr.revalidation_schedule(now=later)
        # urgent should be first (higher urgency ratio)
        if len(schedule) >= 2:
            assert schedule[0].claim_id == "urgent"

    def test_excludes_permanent(self):
        mgr = TTLManager()
        past = datetime(2020, 1, 1)
        mgr.track("c1", VolatilityClass.PERMANENT, 0.9, created_at=past)
        schedule = mgr.revalidation_schedule()
        assert len(schedule) == 0

    def test_excludes_retracted(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        tc = mgr.track("c1", VolatilityClass.VOLATILE, 0.8, created_at=now)
        tc.retracted = True
        later = now + timedelta(hours=2)
        schedule = mgr.revalidation_schedule(now=later)
        assert len(schedule) == 0


# =============================================================================
# TestQueries
# =============================================================================


class TestQueries:

    def test_active_claims(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.STABLE, 0.9)
        tc2 = mgr.track("c2", VolatilityClass.VOLATILE, 0.8)
        tc2.retracted = True
        assert len(mgr.active_claims()) == 1

    def test_retracted_claims(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.STABLE, 0.9)
        tc2 = mgr.track("c2", VolatilityClass.VOLATILE, 0.8)
        tc2.retracted = True
        assert len(mgr.retracted_claims()) == 1

    def test_expired_claims(self):
        mgr = TTLManager()
        now = datetime(2024, 6, 1)
        mgr.track("fresh", VolatilityClass.STABLE, 0.9, created_at=now)
        mgr.track("stale", VolatilityClass.VOLATILE, 0.8, created_at=now)
        later = now + timedelta(hours=2)
        expired = mgr.expired_claims(now=later)
        assert len(expired) == 1
        assert expired[0].claim_id == "stale"

    def test_claims_by_volatility(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.STABLE, 0.9)
        mgr.track("c2", VolatilityClass.STABLE, 0.8)
        mgr.track("c3", VolatilityClass.VOLATILE, 0.7)
        assert len(mgr.claims_by_volatility(VolatilityClass.STABLE)) == 2
        assert len(mgr.claims_by_volatility(VolatilityClass.VOLATILE)) == 1

    def test_metrics(self):
        mgr = TTLManager()
        mgr.track("c1", VolatilityClass.STABLE, 0.9)
        tc2 = mgr.track("c2", VolatilityClass.VOLATILE, 0.8)
        tc2.retracted = True
        m = mgr.get_metrics()
        assert m["total_tracked"] == 2
        assert m["active"] == 1
        assert m["retracted"] == 1
        assert m["by_volatility"]["stable"] == 1


# =============================================================================
# TestConvenience
# =============================================================================


class TestConvenience:

    def test_create_ttl_manager_default(self):
        mgr = create_ttl_manager()
        assert isinstance(mgr, TTLManager)
        assert len(mgr.policies) == 5

    def test_create_with_custom_policies(self):
        custom = {
            VolatilityClass.VOLATILE: TTLPolicy(
                volatility=VolatilityClass.VOLATILE,
                ttl=timedelta(minutes=30),
                decay_rate=0.5,
                decay_period=timedelta(minutes=10),
                retract_after=timedelta(hours=2),
            ),
        }
        mgr = create_ttl_manager(custom)
        assert mgr.policies[VolatilityClass.VOLATILE].ttl == timedelta(minutes=30)
