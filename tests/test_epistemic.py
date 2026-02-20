# SPDX-License-Identifier: Apache-2.0
"""
Tests for epistemic governance: provenance, confidence, and evidence tracking.
"""

import pytest
from datetime import datetime

from governor.epistemic import (
    # Provenance
    Provenance,
    FORBIDDEN_PROMOTIONS,
    PROMOTIONS_REQUIRING_EVIDENCE,
    # Evidence
    EvidenceType,
    EvidenceRef,
    INDEPENDENCE_CLASSES,
    # Claims
    GroundedClaim,
    GroundedClaimStatus,
    PromotionResult,
    DEFAULT_CONFIDENCE,
    MAX_PEER_CONFIDENCE,
    HIGH_CONFIDENCE_THRESHOLD,
    # Ledger
    EpistemicLedger,
    PromotionAttempt,
)


# =============================================================================
# Provenance Tests
# =============================================================================


class TestProvenance:
    """Tests for provenance types and hierarchy."""

    def test_provenance_values(self):
        """All provenance types should have string values."""
        assert Provenance.OBSERVED.value == "observed"
        assert Provenance.RETRIEVED.value == "retrieved"
        assert Provenance.USER_PROVIDED.value == "user_provided"
        assert Provenance.DERIVED.value == "derived"
        assert Provenance.PEER_ASSERTED.value == "peer_asserted"
        assert Provenance.ASSUMED.value == "assumed"

    def test_grounded_provenances(self):
        """OBSERVED, RETRIEVED, USER_PROVIDED are grounded."""
        assert Provenance.OBSERVED.is_grounded is True
        assert Provenance.RETRIEVED.is_grounded is True
        assert Provenance.USER_PROVIDED.is_grounded is True
        assert Provenance.DERIVED.is_grounded is False
        assert Provenance.PEER_ASSERTED.is_grounded is False
        assert Provenance.ASSUMED.is_grounded is False

    def test_requires_evidence_for_confidence(self):
        """ASSUMED and PEER_ASSERTED require evidence for confidence increase."""
        assert Provenance.ASSUMED.requires_evidence_for_confidence is True
        assert Provenance.PEER_ASSERTED.requires_evidence_for_confidence is True
        assert Provenance.DERIVED.requires_evidence_for_confidence is False
        assert Provenance.RETRIEVED.requires_evidence_for_confidence is False

    def test_trust_levels(self):
        """Trust levels should be ordered correctly."""
        assert Provenance.OBSERVED.trust_level > Provenance.RETRIEVED.trust_level
        assert Provenance.RETRIEVED.trust_level > Provenance.USER_PROVIDED.trust_level
        assert Provenance.USER_PROVIDED.trust_level > Provenance.DERIVED.trust_level
        assert Provenance.DERIVED.trust_level > Provenance.PEER_ASSERTED.trust_level
        assert Provenance.PEER_ASSERTED.trust_level > Provenance.ASSUMED.trust_level

    def test_forbidden_promotions_to_observed(self):
        """Nothing can be promoted to OBSERVED."""
        for prov in Provenance:
            if prov != Provenance.OBSERVED:
                assert (prov, Provenance.OBSERVED) in FORBIDDEN_PROMOTIONS

    def test_promotions_requiring_evidence(self):
        """ASSUMED and PEER_ASSERTED require evidence for promotion."""
        assert (Provenance.ASSUMED, Provenance.RETRIEVED) in PROMOTIONS_REQUIRING_EVIDENCE
        assert (Provenance.PEER_ASSERTED, Provenance.RETRIEVED) in PROMOTIONS_REQUIRING_EVIDENCE


# =============================================================================
# Evidence Reference Tests
# =============================================================================


class TestEvidenceRef:
    """Tests for evidence references."""

    def test_create_from_tool_trace(self):
        """Create evidence from tool trace."""
        ref = EvidenceRef.from_tool_trace("trace_123", "Verification of file existence")

        assert ref.ref_type == EvidenceType.TOOL_TRACE
        assert ref.locator == "trace_123"
        assert ref.scope == "Verification of file existence"
        assert ref.retrieved_at is not None
        assert ref.ref_id.startswith("ev_")

    def test_create_from_url(self):
        """Create evidence from URL."""
        ref = EvidenceRef.from_url("https://example.com/doc", "Source document")

        assert ref.ref_type == EvidenceType.URL
        assert ref.locator == "https://example.com/doc"

    def test_create_from_receipt(self):
        """Create evidence from governor receipt."""
        ref = EvidenceRef.from_receipt("sha256:abc123", "File snapshot")

        assert ref.ref_type == EvidenceType.RECEIPT
        assert ref.locator == "sha256:abc123"

    def test_create_from_human(self):
        """Create evidence from human input."""
        ref = EvidenceRef.from_human("User confirmed via chat", "Decision approval")

        assert ref.ref_type == EvidenceType.HUMAN_INPUT

    def test_serialization(self):
        """Evidence ref should serialize/deserialize."""
        ref = EvidenceRef.from_tool_trace("trace_456", "Test")
        data = ref.to_dict()

        assert data["ref_type"] == "tool_trace"
        assert data["locator"] == "trace_456"

        restored = EvidenceRef.from_dict(data)
        assert restored.ref_type == ref.ref_type
        assert restored.locator == ref.locator

    def test_confidence_default(self):
        """Evidence confidence defaults to 1.0."""
        ref = EvidenceRef.from_tool_trace("trace", "scope")
        assert ref.confidence == 1.0


# =============================================================================
# Grounded Claim Tests
# =============================================================================


class TestGroundedClaim:
    """Tests for grounded claims."""

    def test_create_basic_claim(self):
        """Create a basic grounded claim."""
        claim = GroundedClaim(
            claim_id="gc_001",
            content="Tests pass for module X",
            provenance=Provenance.RETRIEVED,
            confidence=0.85,
        )

        assert claim.claim_id == "gc_001"
        assert claim.provenance == Provenance.RETRIEVED
        assert claim.confidence == 0.85
        assert claim.status == GroundedClaimStatus.ACTIVE

    def test_confidence_clamping(self):
        """Confidence should be clamped to [0, 1]."""
        claim1 = GroundedClaim(
            claim_id="gc_001",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=1.5,
        )
        assert claim1.confidence == 1.0

        claim2 = GroundedClaim(
            claim_id="gc_002",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=-0.5,
        )
        assert claim2.confidence == 0.0

    def test_peer_confidence_cap(self):
        """PEER_ASSERTED claims have capped confidence."""
        claim = GroundedClaim(
            claim_id="gc_001",
            content="Peer says tests pass",
            provenance=Provenance.PEER_ASSERTED,
            confidence=0.9,  # Should be capped
        )
        assert claim.confidence == MAX_PEER_CONFIDENCE

    def test_is_grounded_by_provenance(self):
        """Grounded provenance = grounded claim."""
        claim = GroundedClaim(
            claim_id="gc_001",
            content="test",
            provenance=Provenance.RETRIEVED,
            confidence=0.85,
        )
        assert claim.is_grounded is True

    def test_is_grounded_by_evidence(self):
        """Evidence makes ungrounded provenance grounded."""
        claim = GroundedClaim(
            claim_id="gc_001",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.3,
            evidence_refs=[EvidenceRef.from_tool_trace("trace", "scope")],
        )
        assert claim.is_grounded is True

    def test_is_not_grounded(self):
        """ASSUMED without evidence is not grounded."""
        claim = GroundedClaim(
            claim_id="gc_001",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        assert claim.is_grounded is False

    def test_is_dangerous(self):
        """High confidence + ungrounded = dangerous."""
        # Dangerous: high confidence, no evidence, ungrounded provenance
        dangerous = GroundedClaim(
            claim_id="gc_001",
            content="test",
            provenance=Provenance.DERIVED,
            confidence=0.8,
        )
        assert dangerous.is_dangerous is True

        # Not dangerous: low confidence
        safe1 = GroundedClaim(
            claim_id="gc_002",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        assert safe1.is_dangerous is False

        # Not dangerous: grounded provenance
        safe2 = GroundedClaim(
            claim_id="gc_003",
            content="test",
            provenance=Provenance.RETRIEVED,
            confidence=0.9,
        )
        assert safe2.is_dangerous is False

        # Not dangerous: has evidence
        safe3 = GroundedClaim(
            claim_id="gc_004",
            content="test",
            provenance=Provenance.DERIVED,
            confidence=0.8,
            evidence_refs=[EvidenceRef.from_tool_trace("t", "s")],
        )
        assert safe3.is_dangerous is False

    def test_content_hash(self):
        """Content hash should be consistent."""
        claim1 = GroundedClaim(
            claim_id="gc_001",
            content="Tests pass",
            provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        claim2 = GroundedClaim(
            claim_id="gc_002",
            content="  tests pass  ",  # Same content, different whitespace
            provenance=Provenance.ASSUMED,
            confidence=0.3,
        )
        assert claim1.content_hash == claim2.content_hash

    def test_serialization(self):
        """Claim should serialize/deserialize."""
        claim = GroundedClaim(
            claim_id="gc_001",
            content="Test claim",
            provenance=Provenance.RETRIEVED,
            confidence=0.85,
            evidence_refs=[EvidenceRef.from_tool_trace("trace", "scope")],
        )

        data = claim.to_dict()
        restored = GroundedClaim.from_dict(data)

        assert restored.claim_id == claim.claim_id
        assert restored.provenance == claim.provenance
        assert restored.confidence == claim.confidence
        assert len(restored.evidence_refs) == 1


# =============================================================================
# Epistemic Ledger Tests
# =============================================================================


class TestEpistemicLedger:
    """Tests for the epistemic ledger."""

    def test_create_assumed_claim(self):
        """Create an ASSUMED claim via ledger."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("The sky is blue")

        assert claim.provenance == Provenance.ASSUMED
        assert claim.confidence == 0.3
        assert claim.claim_id in ledger.claims

    def test_create_retrieved_claim(self):
        """Create a RETRIEVED claim with evidence."""
        ledger = EpistemicLedger()
        evidence = EvidenceRef.from_tool_trace("trace_001", "File check")
        claim = ledger.new_retrieved_claim("File exists", evidence)

        assert claim.provenance == Provenance.RETRIEVED
        assert claim.is_grounded is True
        assert len(claim.evidence_refs) == 1

    def test_create_peer_claim(self):
        """Create a peer claim with capped confidence."""
        ledger = EpistemicLedger()
        claim = ledger.new_peer_claim(
            "Agent B says tests pass",
            peer_agent_id="agent_b",
            confidence=0.9,  # Should be capped
        )

        assert claim.provenance == Provenance.PEER_ASSERTED
        assert claim.confidence == MAX_PEER_CONFIDENCE
        assert claim.source_agent_id == "agent_b"

    def test_attach_evidence(self):
        """Attach evidence to an existing claim."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Tests might pass")

        assert claim.is_grounded is False

        evidence = EvidenceRef.from_tool_trace("pytest_output", "Test execution")
        ledger.attach_evidence(claim.claim_id, evidence)

        assert claim.is_grounded is True

    def test_tick_advances_step(self):
        """Tick should advance the step counter."""
        ledger = EpistemicLedger()
        assert ledger.step == 0

        ledger.tick()
        assert ledger.step == 1

    # -------------------------------------------------------------------------
    # Provenance Promotion Tests
    # -------------------------------------------------------------------------

    def test_promotion_forbidden(self):
        """Cannot promote to OBSERVED."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")

        result = ledger.promote(claim.claim_id, Provenance.OBSERVED)

        assert result == PromotionResult.FORBIDDEN
        assert claim.provenance == Provenance.ASSUMED  # Unchanged

    def test_promotion_needs_evidence(self):
        """ASSUMED -> RETRIEVED needs evidence."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")

        result = ledger.promote(claim.claim_id, Provenance.RETRIEVED)

        assert result == PromotionResult.NEEDS_EVIDENCE
        assert claim.provenance == Provenance.ASSUMED  # Unchanged

    def test_promotion_succeeds_with_evidence(self):
        """ASSUMED -> RETRIEVED succeeds with evidence."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("File exists")

        # Attach evidence first
        evidence = EvidenceRef.from_tool_trace("ls_output", "Directory listing")
        ledger.attach_evidence(claim.claim_id, evidence)

        # Now promotion should succeed
        result = ledger.promote(claim.claim_id, Provenance.RETRIEVED)

        assert result == PromotionResult.SUCCESS
        assert claim.provenance == Provenance.RETRIEVED

    def test_can_promote_check(self):
        """can_promote returns reason for failure."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")

        allowed, reason = ledger.can_promote(claim.claim_id, Provenance.OBSERVED)
        assert allowed is False
        assert "Forbidden" in reason

        allowed, reason = ledger.can_promote(claim.claim_id, Provenance.RETRIEVED)
        assert allowed is False
        assert "evidence" in reason.lower()

    # -------------------------------------------------------------------------
    # Confidence Update Tests (The Money Rule)
    # -------------------------------------------------------------------------

    def test_confidence_increase_blocked_without_evidence(self):
        """ASSUMED claims cannot increase confidence without evidence."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")
        original_confidence = claim.confidence

        # Try to increase confidence
        result = ledger.update_confidence(claim.claim_id, +0.3)

        assert result is False
        assert claim.confidence == original_confidence  # Unchanged

    def test_confidence_increase_allowed_with_evidence(self):
        """Claims with evidence can increase confidence."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")

        # Add evidence
        ledger.attach_evidence(claim.claim_id, EvidenceRef.from_tool_trace("t", "s"))
        original = claim.confidence

        # Now increase should work
        result = ledger.update_confidence(claim.claim_id, +0.3)

        assert result is True
        assert claim.confidence == original + 0.3

    def test_confidence_decrease_always_allowed(self):
        """Confidence can always decrease."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")
        original = claim.confidence

        result = ledger.update_confidence(claim.claim_id, -0.1)

        assert result is True
        assert claim.confidence == original - 0.1

    def test_peer_confidence_capped_on_update(self):
        """Peer claims stay capped even with evidence."""
        ledger = EpistemicLedger()
        claim = ledger.new_peer_claim("Agent B says X", "agent_b")

        # Add evidence and try to increase
        ledger.attach_evidence(claim.claim_id, EvidenceRef.from_tool_trace("t", "s"))
        ledger.update_confidence(claim.claim_id, +0.5, requires_evidence=False)

        # Still capped
        assert claim.confidence <= MAX_PEER_CONFIDENCE

    def test_decay_ungrounded_confidence(self):
        """Decay reduces confidence on ungrounded claims."""
        ledger = EpistemicLedger()

        # Create some claims
        grounded = ledger.new_retrieved_claim(
            "Grounded",
            EvidenceRef.from_tool_trace("t", "s"),
            confidence=0.8,
        )
        ungrounded = ledger.new_assumed_claim("Ungrounded")
        ungrounded.confidence = 0.5  # Set directly for test

        grounded_before = grounded.confidence
        ungrounded_before = ungrounded.confidence

        # Decay
        count = ledger.decay_ungrounded_confidence(decay=0.1)

        assert count == 1
        assert grounded.confidence == grounded_before  # Unchanged
        assert ungrounded.confidence == ungrounded_before - 0.1

    # -------------------------------------------------------------------------
    # Status Change Tests
    # -------------------------------------------------------------------------

    def test_block_claim(self):
        """Block a claim."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")

        ledger.block(claim.claim_id, "No evidence provided")

        assert claim.status == GroundedClaimStatus.BLOCKED
        assert claim not in ledger.active_claims()
        assert claim in ledger.blocked_claims()

    def test_retract_claim(self):
        """Retract a claim."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")

        ledger.retract(claim.claim_id, "User correction")

        assert claim.status == GroundedClaimStatus.RETRACTED
        assert claim.retraction_reason == "User correction"
        assert ledger.total_retractions == 1

    def test_unblock_requires_grounding(self):
        """Cannot unblock without grounding."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("Test")
        ledger.block(claim.claim_id)

        # Try to unblock without evidence
        result = ledger.unblock(claim.claim_id)
        assert result is False
        assert claim.status == GroundedClaimStatus.BLOCKED

        # Add evidence
        ledger.attach_evidence(claim.claim_id, EvidenceRef.from_tool_trace("t", "s"))

        # Now unblock should work
        result = ledger.unblock(claim.claim_id)
        assert result is True
        assert claim.status == GroundedClaimStatus.ACTIVE

    # -------------------------------------------------------------------------
    # Query Tests
    # -------------------------------------------------------------------------

    def test_dangerous_claims_query(self):
        """Query for dangerous claims."""
        ledger = EpistemicLedger()

        # Safe: low confidence
        ledger.new_assumed_claim("Safe 1")

        # Safe: grounded
        ledger.new_retrieved_claim(
            "Safe 2",
            EvidenceRef.from_tool_trace("t", "s"),
        )

        # Dangerous: high confidence, ungrounded
        dangerous = ledger.new_claim(
            "Dangerous claim",
            Provenance.DERIVED,
            confidence=0.9,
        )

        dangerous_list = ledger.dangerous_claims()

        assert len(dangerous_list) == 1
        assert dangerous_list[0].claim_id == dangerous.claim_id

    def test_claims_by_provenance(self):
        """Query claims by provenance."""
        ledger = EpistemicLedger()

        ledger.new_assumed_claim("Assumed 1")
        ledger.new_assumed_claim("Assumed 2")
        ledger.new_retrieved_claim(
            "Retrieved",
            EvidenceRef.from_tool_trace("t", "s"),
        )

        assumed = ledger.claims_by_provenance(Provenance.ASSUMED)
        assert len(assumed) == 2

        retrieved = ledger.claims_by_provenance(Provenance.RETRIEVED)
        assert len(retrieved) == 1

    def test_claims_by_agent(self):
        """Query claims by source agent."""
        ledger = EpistemicLedger()

        ledger.new_peer_claim("From A", "agent_a")
        ledger.new_peer_claim("From A again", "agent_a")
        ledger.new_peer_claim("From B", "agent_b")

        from_a = ledger.claims_by_agent("agent_a")
        assert len(from_a) == 2

    def test_find_by_content(self):
        """Find claim by content."""
        ledger = EpistemicLedger()
        claim = ledger.new_assumed_claim("The answer is 42")

        found = ledger.find_by_content("the answer is 42")  # Case insensitive
        assert found is not None
        assert found.claim_id == claim.claim_id

    # -------------------------------------------------------------------------
    # Metrics Tests
    # -------------------------------------------------------------------------

    def test_metrics(self):
        """Get ledger metrics."""
        ledger = EpistemicLedger()

        ledger.new_assumed_claim("Test 1")
        ledger.new_retrieved_claim("Test 2", EvidenceRef.from_tool_trace("t", "s"))

        metrics = ledger.get_metrics()

        assert metrics["total_claims"] == 2
        assert metrics["active_claims"] == 2
        assert metrics["provenance_distribution"]["assumed"] == 1
        assert metrics["provenance_distribution"]["retrieved"] == 1

    def test_provenance_entropy(self):
        """Provenance entropy calculation."""
        ledger = EpistemicLedger()

        # All same provenance = low entropy
        ledger.new_assumed_claim("Test 1")
        ledger.new_assumed_claim("Test 2")
        ledger.new_assumed_claim("Test 3")

        entropy1 = ledger.get_provenance_entropy()

        # Add variety
        ledger.new_retrieved_claim("Test 4", EvidenceRef.from_tool_trace("t", "s"))

        entropy2 = ledger.get_provenance_entropy()

        # More variety = higher entropy
        assert entropy2 > entropy1

    def test_serialization(self):
        """Ledger serializes to dict and JSON."""
        ledger = EpistemicLedger()
        ledger.new_assumed_claim("Test")
        ledger.tick()

        data = ledger.to_dict()
        assert data["step"] == 1
        assert len(data["claims"]) == 1

        json_str = ledger.to_json()
        assert "Test" in json_str


# =============================================================================
# Integration Tests
# =============================================================================


class TestEpistemicIntegration:
    """Integration tests for epistemic governance workflows."""

    def test_claim_lifecycle(self):
        """Test full claim lifecycle: create -> evidence -> promote -> update."""
        ledger = EpistemicLedger()

        # 1. Create assumed claim
        claim = ledger.new_assumed_claim("File src/main.py exists")
        assert claim.provenance == Provenance.ASSUMED
        assert claim.is_grounded is False

        # 2. Try to promote (fails without evidence)
        result = ledger.promote(claim.claim_id, Provenance.RETRIEVED)
        assert result == PromotionResult.NEEDS_EVIDENCE

        # 3. Attach evidence
        evidence = EvidenceRef.from_receipt("sha256:abc123", "File snapshot")
        ledger.attach_evidence(claim.claim_id, evidence)
        assert claim.is_grounded is True

        # 4. Promote (succeeds)
        result = ledger.promote(claim.claim_id, Provenance.RETRIEVED)
        assert result == PromotionResult.SUCCESS

        # 5. Increase confidence (now allowed)
        result = ledger.update_confidence(claim.claim_id, +0.1)
        assert result is True

    def test_multi_agent_resonance_prevention(self):
        """Test that peer assertions cannot escalate without evidence."""
        ledger = EpistemicLedger()

        # Agent A makes a claim
        claim_a = ledger.new_peer_claim(
            "The API is RESTful",
            peer_agent_id="agent_a",
            confidence=0.9,  # Capped
        )

        # Agent B echoes the claim
        claim_b = ledger.new_peer_claim(
            "The API is RESTful",
            peer_agent_id="agent_b",
            confidence=0.9,  # Also capped
        )

        # Both are low confidence despite both "agreeing"
        assert claim_a.confidence <= MAX_PEER_CONFIDENCE
        assert claim_b.confidence <= MAX_PEER_CONFIDENCE

        # Cannot increase without evidence
        result = ledger.update_confidence(claim_a.claim_id, +0.5)
        assert result is False

    def test_dangerous_claim_detection_workflow(self):
        """Test detecting and handling dangerous claims."""
        ledger = EpistemicLedger()

        # Create a claim that will be dangerous
        claim = ledger.new_claim(
            "This is definitely correct",
            Provenance.DERIVED,
            confidence=0.85,
        )

        # Should be flagged as dangerous
        dangerous = ledger.dangerous_claims()
        assert len(dangerous) == 1
        assert dangerous[0].claim_id == claim.claim_id

        # Block it
        ledger.block(claim.claim_id, "High confidence without evidence")

        # No longer in active dangerous list
        assert len(ledger.dangerous_claims()) == 0

        # Add evidence and unblock
        ledger.attach_evidence(claim.claim_id, EvidenceRef.from_tool_trace("t", "s"))
        ledger.unblock(claim.claim_id)

        # Now active but not dangerous (has evidence)
        assert claim.is_active
        assert not claim.is_dangerous


# =============================================================================
# Provenance Independence Fields (3.x seam)
# =============================================================================


class TestProvenanceIndependence:
    """independence_class, source_channel, derived_from on EvidenceRef."""

    def test_default_none(self):
        ref = EvidenceRef(
            ref_id="ev_test", ref_type=EvidenceType.TOOL_TRACE,
            locator="trace-1", scope="full",
        )
        assert ref.independence_class is None
        assert ref.source_channel is None
        assert ref.derived_from is None

    def test_explicit_values(self):
        ref = EvidenceRef(
            ref_id="ev_test", ref_type=EvidenceType.TOOL_TRACE,
            locator="trace-1", scope="full",
            independence_class="external",
            source_channel="api",
            derived_from=("ev_parent1", "ev_parent2"),
        )
        assert ref.independence_class == "external"
        assert ref.source_channel == "api"
        assert ref.derived_from == ("ev_parent1", "ev_parent2")

    def test_round_trip(self):
        ref = EvidenceRef(
            ref_id="ev_rt", ref_type=EvidenceType.URL,
            locator="https://example.com", scope="citation",
            independence_class="peer",
            source_channel="daemon_rpc",
            derived_from=("ev_a",),
        )
        d = ref.to_dict()
        ref2 = EvidenceRef.from_dict(d)
        assert ref2.independence_class == "peer"
        assert ref2.source_channel == "daemon_rpc"
        assert ref2.derived_from == ("ev_a",)

    def test_none_fields_absent_from_dict(self):
        """When None, independence fields should not appear in serialized dict."""
        ref = EvidenceRef(
            ref_id="ev_test", ref_type=EvidenceType.TOOL_TRACE,
            locator="t", scope="s",
        )
        d = ref.to_dict()
        assert "independence_class" not in d
        assert "source_channel" not in d
        assert "derived_from" not in d

    def test_backwards_compat(self):
        """Old dicts without independence fields deserialize cleanly."""
        d = {
            "ref_id": "ev_old",
            "ref_type": "tool_trace",
            "locator": "trace-1",
            "scope": "full",
            "confidence": 0.9,
        }
        ref = EvidenceRef.from_dict(d)
        assert ref.independence_class is None
        assert ref.source_channel is None
        assert ref.derived_from is None

    def test_factory_defaults_tool_trace(self):
        ref = EvidenceRef.from_tool_trace("t1", "scope")
        assert ref.independence_class == "tool"

    def test_factory_defaults_url(self):
        ref = EvidenceRef.from_url("https://example.com", "scope")
        assert ref.independence_class == "external"

    def test_factory_defaults_receipt(self):
        ref = EvidenceRef.from_receipt("hash123", "scope")
        assert ref.independence_class == "tool"

    def test_factory_defaults_human(self):
        ref = EvidenceRef.from_human("user said X", "scope")
        assert ref.independence_class == "operator"

    def test_invalid_independence_class_raises(self):
        with pytest.raises(ValueError, match="Invalid independence_class"):
            EvidenceRef(
                ref_id="ev_bad", ref_type=EvidenceType.TOOL_TRACE,
                locator="t", scope="s",
                independence_class="bogus",
            )

    def test_derived_from_as_tuple(self):
        """derived_from must be a tuple (from_dict accepts list → tuple)."""
        d = {
            "ref_id": "ev_t",
            "ref_type": "tool_trace",
            "locator": "t",
            "scope": "s",
            "derived_from": ["ev_a", "ev_b"],
        }
        ref = EvidenceRef.from_dict(d)
        assert isinstance(ref.derived_from, tuple)
        assert ref.derived_from == ("ev_a", "ev_b")
