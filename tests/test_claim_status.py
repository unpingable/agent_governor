"""
Tests for ClaimStatus enum, QuorumStatus mapping, EpistemicLedger from_dict/from_json,
and epistemic_status methods on GroundedClaim and EpistemicLedger.
"""

import json
import pytest
from datetime import datetime

from governor.epistemic import (
    ClaimStatus,
    QUORUM_TO_CLAIM_STATUS,
    project_quorum_status,
    Provenance,
    EvidenceType,
    EvidenceRef,
    GroundedClaim,
    GroundedClaimStatus,
    EpistemicLedger,
)


# =============================================================================
# ClaimStatus Enum Tests
# =============================================================================


class TestClaimStatusEnum:
    """Tests for the ClaimStatus enum."""

    def test_all_seven_members(self):
        """ClaimStatus should have exactly 7 members."""
        assert len(ClaimStatus) == 7

    def test_values(self):
        """Each member should have the expected string value."""
        assert ClaimStatus.PROPOSED.value == "proposed"
        assert ClaimStatus.SUPPORTED.value == "supported"
        assert ClaimStatus.CONTESTED.value == "contested"
        assert ClaimStatus.INVALIDATED.value == "invalidated"
        assert ClaimStatus.EXPIRED.value == "expired"
        assert ClaimStatus.REFUSED.value == "refused"
        assert ClaimStatus.STALE.value == "stale"

    def test_string_conversion(self):
        """ClaimStatus inherits from str — direct string comparison should work."""
        assert ClaimStatus.PROPOSED == "proposed"
        assert ClaimStatus("supported") == ClaimStatus.SUPPORTED

    def test_construct_from_string(self):
        """Should be constructable from string values."""
        for status in ClaimStatus:
            assert ClaimStatus(status.value) == status


# =============================================================================
# QuorumStatus → ClaimStatus Mapping Tests
# =============================================================================


class TestQuorumMapping:
    """Tests for QuorumStatus → ClaimStatus projection."""

    def test_collecting_maps_to_proposed(self):
        assert project_quorum_status("collecting") == ClaimStatus.PROPOSED

    def test_stabilizing_maps_to_proposed(self):
        assert project_quorum_status("stabilizing") == ClaimStatus.PROPOSED

    def test_reached_maps_to_supported(self):
        assert project_quorum_status("reached") == ClaimStatus.SUPPORTED

    def test_failed_maps_to_refused(self):
        assert project_quorum_status("failed") == ClaimStatus.REFUSED

    def test_expired_maps_to_expired(self):
        assert project_quorum_status("expired") == ClaimStatus.EXPIRED

    def test_contested_maps_to_contested(self):
        assert project_quorum_status("contested") == ClaimStatus.CONTESTED

    def test_escalated_maps_to_contested(self):
        assert project_quorum_status("escalated") == ClaimStatus.CONTESTED

    def test_resolved_commit_maps_to_supported(self):
        assert project_quorum_status("resolved_commit") == ClaimStatus.SUPPORTED

    def test_resolved_reject_maps_to_invalidated(self):
        assert project_quorum_status("resolved_reject") == ClaimStatus.INVALIDATED

    def test_unknown_returns_none(self):
        """Unknown quorum status should return None."""
        assert project_quorum_status("nonexistent") is None
        assert project_quorum_status("") is None

    def test_all_nine_quorum_states_mapped(self):
        """All 9 QuorumStatus values should be in the mapping."""
        assert len(QUORUM_TO_CLAIM_STATUS) == 9


# =============================================================================
# GroundedClaim epistemic_status Tests
# =============================================================================


class TestGroundedClaimEpistemicStatus:
    """Tests for the epistemic_status field on GroundedClaim."""

    def test_default_none(self):
        """New GroundedClaim should have epistemic_status = None."""
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test claim",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
        )
        assert claim.epistemic_status is None

    def test_set_epistemic_status(self):
        """Should be able to set epistemic_status directly."""
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test claim",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
            epistemic_status=ClaimStatus.PROPOSED,
        )
        assert claim.epistemic_status == ClaimStatus.PROPOSED

    def test_to_dict_includes_epistemic_status(self):
        """to_dict should include epistemic_status when set."""
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test claim",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
            epistemic_status=ClaimStatus.SUPPORTED,
        )
        d = claim.to_dict()
        assert d["epistemic_status"] == "supported"

    def test_to_dict_omits_epistemic_status_when_none(self):
        """to_dict should NOT include epistemic_status when None."""
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test claim",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
        )
        d = claim.to_dict()
        assert "epistemic_status" not in d

    def test_from_dict_round_trip(self):
        """from_dict should preserve epistemic_status."""
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test claim",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
            epistemic_status=ClaimStatus.CONTESTED,
        )
        d = claim.to_dict()
        restored = GroundedClaim.from_dict(d)
        assert restored.epistemic_status == ClaimStatus.CONTESTED

    def test_from_dict_legacy_no_epistemic_status(self):
        """from_dict should handle missing epistemic_status (legacy data)."""
        d = {
            "claim_id": "gc_test",
            "content": "test claim",
            "provenance": "assumed",
            "confidence": 0.5,
            "created_at": datetime.now().isoformat(),
        }
        restored = GroundedClaim.from_dict(d)
        assert restored.epistemic_status is None


# =============================================================================
# EpistemicLedger Status Methods Tests
# =============================================================================


class TestEpistemicLedgerStatusMethods:
    """Tests for set_epistemic_status and claims_by_epistemic_status."""

    def test_set_epistemic_status(self):
        """Should set epistemic status on existing claim."""
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        result = ledger.set_epistemic_status(claim.claim_id, ClaimStatus.PROPOSED)
        assert result is True
        assert claim.epistemic_status == ClaimStatus.PROPOSED

    def test_set_epistemic_status_nonexistent(self):
        """Should return False for nonexistent claim."""
        ledger = EpistemicLedger()
        result = ledger.set_epistemic_status("gc_fake", ClaimStatus.PROPOSED)
        assert result is False

    def test_set_epistemic_status_updates_timestamp(self):
        """Setting epistemic status should update last_updated_at."""
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        old_ts = claim.last_updated_at
        ledger.tick()
        ledger.set_epistemic_status(claim.claim_id, ClaimStatus.SUPPORTED)
        assert claim.last_updated_step == 1

    def test_claims_by_epistemic_status(self):
        """Should filter claims by epistemic status."""
        ledger = EpistemicLedger()
        c1 = ledger.new_claim("claim1", Provenance.ASSUMED)
        c2 = ledger.new_claim("claim2", Provenance.RETRIEVED)
        c3 = ledger.new_claim("claim3", Provenance.ASSUMED)

        ledger.set_epistemic_status(c1.claim_id, ClaimStatus.PROPOSED)
        ledger.set_epistemic_status(c2.claim_id, ClaimStatus.SUPPORTED)
        ledger.set_epistemic_status(c3.claim_id, ClaimStatus.PROPOSED)

        proposed = ledger.claims_by_epistemic_status(ClaimStatus.PROPOSED)
        assert len(proposed) == 2
        supported = ledger.claims_by_epistemic_status(ClaimStatus.SUPPORTED)
        assert len(supported) == 1

    def test_claims_by_epistemic_status_empty(self):
        """Should return empty list when no claims match."""
        ledger = EpistemicLedger()
        ledger.new_claim("claim1", Provenance.ASSUMED)
        assert ledger.claims_by_epistemic_status(ClaimStatus.CONTESTED) == []

    def test_claims_by_epistemic_status_includes_all_statuses(self):
        """Should include retracted claims if they have the epistemic status."""
        ledger = EpistemicLedger()
        c1 = ledger.new_claim("retracted claim", Provenance.ASSUMED)
        ledger.set_epistemic_status(c1.claim_id, ClaimStatus.INVALIDATED)
        ledger.retract(c1.claim_id)
        # Still findable by epistemic status (separate from governance status)
        result = ledger.claims_by_epistemic_status(ClaimStatus.INVALIDATED)
        assert len(result) == 1


# =============================================================================
# EpistemicLedger from_dict / from_json Tests
# =============================================================================


class TestEpistemicLedgerFromDict:
    """Tests for EpistemicLedger.from_dict() and from_json()."""

    def test_round_trip_empty(self):
        """Empty ledger should round-trip through to_dict/from_dict."""
        ledger = EpistemicLedger()
        d = ledger.to_dict()
        restored = EpistemicLedger.from_dict(d)
        assert restored.step == 0
        assert len(restored.claims) == 0
        assert restored.total_claims_created == 0

    def test_round_trip_with_claims(self):
        """Ledger with claims should round-trip."""
        ledger = EpistemicLedger()
        c1 = ledger.new_claim("claim one", Provenance.ASSUMED)
        c2 = ledger.new_claim("claim two", Provenance.RETRIEVED)
        ledger.tick()

        d = ledger.to_dict()
        restored = EpistemicLedger.from_dict(d)

        assert restored.step == 1
        assert len(restored.claims) == 2
        assert c1.claim_id in restored.claims
        assert c2.claim_id in restored.claims
        assert restored.claims[c1.claim_id].content == "claim one"
        assert restored.claims[c2.claim_id].provenance == Provenance.RETRIEVED

    def test_round_trip_with_metrics(self):
        """Metric counters should round-trip."""
        ledger = EpistemicLedger()
        ledger.new_claim("claim", Provenance.ASSUMED)
        c = ledger.new_claim("retracted", Provenance.ASSUMED)
        ledger.retract(c.claim_id)

        d = ledger.to_dict()
        restored = EpistemicLedger.from_dict(d)

        assert restored.total_claims_created == 2
        assert restored.total_retractions == 1

    def test_round_trip_with_epistemic_status(self):
        """Claims with epistemic_status should round-trip."""
        ledger = EpistemicLedger()
        c = ledger.new_claim("test", Provenance.ASSUMED)
        ledger.set_epistemic_status(c.claim_id, ClaimStatus.CONTESTED)

        d = ledger.to_dict()
        restored = EpistemicLedger.from_dict(d)

        assert restored.claims[c.claim_id].epistemic_status == ClaimStatus.CONTESTED

    def test_from_dict_legacy_no_metrics(self):
        """from_dict should handle legacy data without metric counters."""
        d = {
            "step": 5,
            "claims": {},
        }
        restored = EpistemicLedger.from_dict(d)
        assert restored.step == 5
        assert restored.total_claims_created == 0
        assert restored.total_retractions == 0

    def test_from_dict_legacy_no_epistemic_status(self):
        """from_dict should handle legacy claim data without epistemic_status."""
        d = {
            "step": 0,
            "claims": {
                "gc_test": {
                    "claim_id": "gc_test",
                    "content": "old claim",
                    "provenance": "assumed",
                    "confidence": 0.3,
                    "created_at": datetime.now().isoformat(),
                }
            },
        }
        restored = EpistemicLedger.from_dict(d)
        assert restored.claims["gc_test"].epistemic_status is None

    def test_from_json_round_trip(self):
        """from_json should round-trip with to_json."""
        ledger = EpistemicLedger()
        ledger.new_claim("json test", Provenance.ASSUMED)
        ledger.tick()
        ledger.tick()

        json_str = ledger.to_json()
        restored = EpistemicLedger.from_json(json_str)

        assert restored.step == 2
        assert len(restored.claims) == 1

    def test_from_json_valid_json(self):
        """from_json should handle raw JSON string."""
        raw = json.dumps({
            "step": 10,
            "claims": {},
            "total_claims_created": 42,
            "total_retractions": 3,
        })
        restored = EpistemicLedger.from_json(raw)
        assert restored.step == 10
        assert restored.total_claims_created == 42
        assert restored.total_retractions == 3


# =============================================================================
# EpistemicLedger to_dict Includes Metrics Tests
# =============================================================================


class TestEpistemicLedgerToDict:
    """Tests for EpistemicLedger.to_dict() metric counter inclusion."""

    def test_to_dict_includes_total_claims_created(self):
        ledger = EpistemicLedger()
        ledger.new_claim("test", Provenance.ASSUMED)
        d = ledger.to_dict()
        assert d["total_claims_created"] == 1

    def test_to_dict_includes_total_retractions(self):
        ledger = EpistemicLedger()
        c = ledger.new_claim("test", Provenance.ASSUMED)
        ledger.retract(c.claim_id)
        d = ledger.to_dict()
        assert d["total_retractions"] == 1

    def test_to_dict_includes_promotion_counters(self):
        ledger = EpistemicLedger()
        d = ledger.to_dict()
        assert "total_promotions_attempted" in d
        assert "total_promotions_forbidden" in d

    def test_to_dict_claims_include_epistemic_status(self):
        """Claims in to_dict should include epistemic_status when set."""
        ledger = EpistemicLedger()
        c = ledger.new_claim("test", Provenance.ASSUMED)
        ledger.set_epistemic_status(c.claim_id, ClaimStatus.PROPOSED)
        d = ledger.to_dict()
        assert d["claims"][c.claim_id]["epistemic_status"] == "proposed"
