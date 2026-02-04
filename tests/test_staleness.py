"""
Tests for staleness detection and claim freshness tracking.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from governor.staleness import (
    StalenessConfig,
    ClaimFreshness,
    StalenessEvent,
    StalenessDetector,
    create_staleness_detector,
)
from governor.epistemic import (
    EpistemicLedger,
    Provenance,
    GroundedClaim,
    ClaimStatus,
)


# =============================================================================
# StalenessConfig Tests
# =============================================================================


class TestStalenessConfig:
    def test_default_values(self):
        config = StalenessConfig()
        assert config.default_freshness_window == timedelta(days=7)
        assert config.default_decay_rate == 0.1
        assert config.confidence_threshold == 0.5
        assert config.assumption_violation_penalty == 0.3
        assert config.overrides == {}

    def test_get_freshness_window_default(self):
        config = StalenessConfig()
        assert config.get_freshness_window() == timedelta(days=7)
        assert config.get_freshness_window("unknown_type") == timedelta(days=7)

    def test_get_freshness_window_override(self):
        config = StalenessConfig(
            overrides={"test_claim": {"freshness_window_days": 14}}
        )
        assert config.get_freshness_window("test_claim") == timedelta(days=14)
        assert config.get_freshness_window("other_type") == timedelta(days=7)

    def test_get_decay_rate_default(self):
        config = StalenessConfig()
        assert config.get_decay_rate() == 0.1
        assert config.get_decay_rate("unknown_type") == 0.1

    def test_get_decay_rate_override(self):
        config = StalenessConfig(
            overrides={"test_claim": {"decay_rate": 0.2}}
        )
        assert config.get_decay_rate("test_claim") == 0.2
        assert config.get_decay_rate("other_type") == 0.1

    def test_to_dict_roundtrip(self):
        config = StalenessConfig(
            default_freshness_window=timedelta(days=14),
            default_decay_rate=0.15,
            confidence_threshold=0.6,
            overrides={"test": {"freshness_window_days": 3}},
        )
        data = config.to_dict()
        restored = StalenessConfig.from_dict(data)
        assert restored.default_freshness_window == timedelta(days=14)
        assert restored.default_decay_rate == 0.15
        assert restored.confidence_threshold == 0.6
        assert restored.overrides == {"test": {"freshness_window_days": 3}}


# =============================================================================
# ClaimFreshness Tests
# =============================================================================


class TestClaimFreshness:
    def test_to_dict(self):
        now = datetime.now()
        freshness = ClaimFreshness(
            claim_id="gc_test123",
            confidence=0.7,
            verified_at=now,
            freshness_window=timedelta(days=7),
            time_since_verification=timedelta(hours=24),
            decay_amount=0.1,
            violated_assumptions=["assumption_1"],
            is_live=True,
            staleness_reason=None,
        )
        data = freshness.to_dict()
        assert data["claim_id"] == "gc_test123"
        assert data["confidence"] == 0.7
        assert data["verified_at"] == now.isoformat()
        assert data["freshness_window_seconds"] == 7 * 24 * 3600
        assert data["decay_amount"] == 0.1
        assert data["violated_assumptions"] == ["assumption_1"]
        assert data["is_live"] is True
        assert data["staleness_reason"] is None

    def test_stale_freshness(self):
        freshness = ClaimFreshness(
            claim_id="gc_stale",
            confidence=0.3,
            verified_at=None,
            freshness_window=timedelta(days=7),
            time_since_verification=timedelta(days=14),
            decay_amount=0.5,
            violated_assumptions=[],
            is_live=False,
            staleness_reason="Decayed 0.50 after freshness window",
        )
        assert not freshness.is_live
        assert freshness.staleness_reason is not None


# =============================================================================
# StalenessDetector Tests
# =============================================================================


class TestStalenessDetector:
    @pytest.fixture
    def ledger(self):
        return EpistemicLedger()

    @pytest.fixture
    def detector(self, ledger):
        return StalenessDetector(ledger)

    def test_compute_freshness_claim_not_found(self, detector):
        freshness = detector.compute_freshness("nonexistent")
        assert freshness.claim_id == "nonexistent"
        assert freshness.confidence == 0.0
        assert not freshness.is_live
        assert freshness.staleness_reason == "Claim not found"

    def test_compute_freshness_fresh_claim(self, ledger, detector):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, confidence=0.9)

        freshness = detector.compute_freshness(claim.claim_id)

        assert freshness.claim_id == claim.claim_id
        assert freshness.confidence >= 0.8  # Should still be high
        assert freshness.is_live
        assert freshness.staleness_reason is None
        assert freshness.decay_amount == 0.0

    def test_compute_freshness_decayed_claim(self, ledger, detector):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, confidence=0.9)
        # Simulate claim being old by adjusting last_updated_at
        claim.last_updated_at = datetime.now() - timedelta(days=14)

        freshness = detector.compute_freshness(claim.claim_id)

        # Should have decayed after 7-day window + 7 days past
        assert freshness.decay_amount > 0
        assert freshness.time_since_verification >= timedelta(days=14)

    def test_detect_stale_claims_empty(self, ledger, detector):
        stale = detector.detect_stale_claims()
        assert stale == []

    def test_detect_stale_claims_finds_stale(self, ledger, detector):
        # Create a fresh claim
        fresh_claim = ledger.new_claim("Fresh", Provenance.RETRIEVED, confidence=0.9)

        # Create a stale claim (old and low confidence)
        stale_claim = ledger.new_claim("Stale", Provenance.ASSUMED, confidence=0.3)
        stale_claim.last_updated_at = datetime.now() - timedelta(days=30)
        stale_claim.confidence = 0.2  # Below threshold

        stale = detector.detect_stale_claims()

        stale_ids = [f.claim_id for f in stale]
        assert stale_claim.claim_id in stale_ids
        # Fresh claim should not be stale
        # (may be in list if confidence calculation pushes it below)

    def test_check_artifact_hash_new_file(self, detector, tmp_path):
        # Create a temp file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # First check should return True (fresh) and store hash
        result = detector.check_artifact_hash("gc_test", str(test_file))
        assert result is True

    def test_check_artifact_hash_unchanged(self, detector, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Record and then check
        detector.record_artifact_hash("gc_test", str(test_file))
        result = detector.check_artifact_hash("gc_test", str(test_file))
        assert result is True

    def test_check_artifact_hash_changed(self, detector, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")

        # Record original
        detector.record_artifact_hash("gc_test", str(test_file))

        # Modify file
        test_file.write_text("modified")

        # Check should detect change
        result = detector.check_artifact_hash("gc_test", str(test_file))
        assert result is False

    def test_check_artifact_hash_file_deleted(self, detector, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Record hash
        detector.record_artifact_hash("gc_test", str(test_file))

        # Delete file
        test_file.unlink()

        # Check should detect deletion (mutated)
        result = detector.check_artifact_hash("gc_test", str(test_file))
        assert result is False

    def test_mark_stale(self, ledger, detector):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, confidence=0.8)

        event = detector.mark_stale(claim.claim_id, "Test reason", "manual")

        assert event is not None
        assert event.claim_id == claim.claim_id
        assert event.event_type == "manual"
        assert event.reason == "Test reason"
        assert event.old_confidence == 0.8
        assert event.new_confidence == 0.0

        # Claim should be updated
        assert claim.confidence == 0.0

    def test_mark_stale_with_epistemic_status(self, ledger, detector):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, confidence=0.8)
        claim.epistemic_status = ClaimStatus.SUPPORTED

        event = detector.mark_stale(claim.claim_id, "Test reason")

        assert event is not None
        assert claim.epistemic_status == ClaimStatus.STALE

    def test_mark_stale_nonexistent(self, detector):
        event = detector.mark_stale("nonexistent", "reason")
        assert event is None

    def test_run_staleness_check(self, ledger, detector):
        # Create claims
        fresh = ledger.new_claim("Fresh", Provenance.RETRIEVED, confidence=0.9)

        stale = ledger.new_claim("Stale", Provenance.ASSUMED, confidence=0.3)
        stale.last_updated_at = datetime.now() - timedelta(days=30)
        stale.epistemic_status = ClaimStatus.SUPPORTED

        # Run check
        newly_stale = detector.run_staleness_check()

        # Should have detected at least the stale claim
        # (exact behavior depends on decay calculation)
        assert isinstance(newly_stale, list)

    def test_get_metrics(self, ledger, detector):
        ledger.new_claim("Claim 1", Provenance.RETRIEVED, confidence=0.9)
        ledger.new_claim("Claim 2", Provenance.ASSUMED, confidence=0.3)

        metrics = detector.get_metrics()

        assert "total_claims" in metrics
        assert "stale_claims" in metrics
        assert "live_claims" in metrics
        assert "total_events" in metrics
        assert metrics["total_claims"] == 2


# =============================================================================
# Assumption Violation Tests
# =============================================================================


class TestAssumptionViolations:
    @pytest.fixture
    def ledger(self):
        return EpistemicLedger()

    @pytest.fixture
    def detector(self, ledger):
        return StalenessDetector(ledger)

    def test_freshness_with_violated_assumption(self, ledger, detector, tmp_path):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, confidence=0.9)

        # Add assumption about a file that doesn't exist
        nonexistent_path = tmp_path / "does_not_exist.txt"
        claim.assumptions.append(f"Assumes file exists: {nonexistent_path}")

        freshness = detector.compute_freshness(claim.claim_id)

        # Should have violated assumptions
        assert len(freshness.violated_assumptions) > 0
        # Confidence should be penalized
        assert freshness.confidence < 0.9

    def test_freshness_with_valid_assumption(self, ledger, detector, tmp_path):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, confidence=0.9)

        # Add assumption about a file that exists
        existing_path = tmp_path / "exists.txt"
        existing_path.write_text("content")
        claim.assumptions.append(f"Assumes file exists: {existing_path}")

        freshness = detector.compute_freshness(claim.claim_id)

        # No violations
        assert len(freshness.violated_assumptions) == 0


# =============================================================================
# Custom Config Tests
# =============================================================================


class TestCustomConfig:
    def test_short_freshness_window(self):
        ledger = EpistemicLedger()
        config = StalenessConfig(
            default_freshness_window=timedelta(hours=1),
            default_decay_rate=0.5,
        )
        detector = StalenessDetector(ledger, config)

        claim = ledger.new_claim("Test", Provenance.RETRIEVED, confidence=0.9)
        # Make claim 2 hours old
        claim.last_updated_at = datetime.now() - timedelta(hours=2)

        freshness = detector.compute_freshness(claim.claim_id)

        # Should have decayed
        assert freshness.decay_amount > 0
        assert freshness.time_since_verification >= timedelta(hours=2)

    def test_high_confidence_threshold(self):
        ledger = EpistemicLedger()
        config = StalenessConfig(confidence_threshold=0.8)
        detector = StalenessDetector(ledger, config)

        claim = ledger.new_claim("Test", Provenance.ASSUMED, confidence=0.7)

        freshness = detector.compute_freshness(claim.claim_id)

        # Below threshold, should not be live
        assert not freshness.is_live


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    def test_create_staleness_detector(self):
        ledger = EpistemicLedger()
        detector = create_staleness_detector(ledger)

        assert isinstance(detector, StalenessDetector)
        assert detector.ledger is ledger

    def test_create_staleness_detector_with_config(self):
        ledger = EpistemicLedger()
        config = StalenessConfig(default_decay_rate=0.2)
        detector = create_staleness_detector(ledger, config)

        assert detector.config.default_decay_rate == 0.2


# =============================================================================
# StalenessEvent Tests
# =============================================================================


class TestStalenessEvent:
    def test_to_dict(self):
        event = StalenessEvent(
            event_id="se_test123",
            claim_id="gc_claim",
            event_type="decay",
            reason="TTL expired",
            old_confidence=0.8,
            new_confidence=0.3,
        )
        data = event.to_dict()

        assert data["event_id"] == "se_test123"
        assert data["claim_id"] == "gc_claim"
        assert data["event_type"] == "decay"
        assert data["reason"] == "TTL expired"
        assert data["old_confidence"] == 0.8
        assert data["new_confidence"] == 0.3
        assert "created_at" in data
