# SPDX-License-Identifier: Apache-2.0
"""
Tests for claim status dashboard and weather report.
"""

from datetime import datetime, timedelta

import pytest

from governor.claim_status import (
    ClaimStatusSummary,
    ClaimDetail,
    ClaimStatusDashboard,
    create_claim_status_dashboard,
)
from governor.epistemic import (
    EpistemicLedger,
    Provenance,
    ClaimStatus,
    EvidenceRef,
    EvidenceType,
)
from governor.docket import DocketManager, CaseType


# =============================================================================
# ClaimStatusSummary Tests
# =============================================================================


class TestClaimStatusSummary:
    def test_to_dict(self):
        summary = ClaimStatusSummary(
            live_count=10,
            live_confidence_avg=0.9,
            degrading_count=3,
            stale_count=2,
            contested_count=1,
            total_claims=16,
            high_confidence_count=8,
            with_evidence_count=5,
            with_assumptions_count=2,
        )
        data = summary.to_dict()

        assert data["live_count"] == 10
        assert data["live_confidence_avg"] == 0.9
        assert data["degrading_count"] == 3
        assert data["stale_count"] == 2
        assert data["contested_count"] == 1
        assert data["total_claims"] == 16

    def test_health_score_perfect(self):
        summary = ClaimStatusSummary(
            live_count=10,
            live_confidence_avg=0.95,
            degrading_count=0,
            stale_count=0,
            contested_count=0,
            total_claims=10,
        )
        assert summary.health_score == 100.0

    def test_health_score_with_stale(self):
        summary = ClaimStatusSummary(
            live_count=8,
            live_confidence_avg=0.9,
            degrading_count=0,
            stale_count=2,
            contested_count=0,
            total_claims=10,
        )
        # 80% live, but stale penalty
        assert summary.health_score < 80.0

    def test_health_score_with_contested(self):
        summary = ClaimStatusSummary(
            live_count=9,
            live_confidence_avg=0.9,
            degrading_count=0,
            stale_count=0,
            contested_count=1,
            total_claims=10,
        )
        # 90% live, but contested penalty
        assert summary.health_score < 90.0

    def test_health_score_empty(self):
        summary = ClaimStatusSummary(
            live_count=0,
            live_confidence_avg=0.0,
            degrading_count=0,
            stale_count=0,
            contested_count=0,
            total_claims=0,
        )
        assert summary.health_score == 100.0  # No claims = healthy


# =============================================================================
# ClaimDetail Tests
# =============================================================================


class TestClaimDetail:
    def test_to_dict(self):
        now = datetime.now()
        detail = ClaimDetail(
            claim_id="gc_test123",
            content="Test claim content",
            status="active",
            epistemic_status="supported",
            confidence=0.85,
            provenance="retrieved",
            verified_at=now,
            freshness_remaining=timedelta(days=3),
            evidence_summary="2 evidence item(s): tool_trace, url",
            assumptions=[("assumption1", True), ("assumption2", False)],
            commit_level="hard",
            source_agent="agent_1",
            depends_on=["gc_dep1", "gc_dep2"],
        )
        data = detail.to_dict()

        assert data["claim_id"] == "gc_test123"
        assert data["content"] == "Test claim content"
        assert data["status"] == "active"
        assert data["epistemic_status"] == "supported"
        assert data["confidence"] == 0.85
        assert data["provenance"] == "retrieved"
        assert data["freshness_remaining_seconds"] == 3 * 24 * 3600
        assert len(data["assumptions"]) == 2
        assert data["assumptions"][0]["text"] == "assumption1"
        assert data["assumptions"][0]["valid"] is True
        assert data["depends_on"] == ["gc_dep1", "gc_dep2"]

    def test_to_dict_no_freshness(self):
        detail = ClaimDetail(
            claim_id="gc_stale",
            content="Stale claim",
            status="active",
            epistemic_status=None,
            confidence=0.3,
            provenance="assumed",
            verified_at=None,
            freshness_remaining=None,
            evidence_summary="No evidence attached",
            assumptions=[],
        )
        data = detail.to_dict()

        assert data["verified_at"] is None
        assert data["freshness_remaining_seconds"] is None


# =============================================================================
# ClaimStatusDashboard Tests
# =============================================================================


class TestClaimStatusDashboard:
    @pytest.fixture
    def ledger(self):
        return EpistemicLedger()

    @pytest.fixture
    def dashboard(self, ledger):
        return ClaimStatusDashboard(ledger)

    def test_get_summary_empty(self, dashboard):
        summary = dashboard.get_summary()

        assert summary.live_count == 0
        assert summary.degrading_count == 0
        assert summary.stale_count == 0
        assert summary.contested_count == 0
        assert summary.total_claims == 0

    def test_get_summary_with_claims(self, ledger, dashboard):
        # Create claims with different confidence levels
        high_conf = ledger.new_claim("High confidence", Provenance.RETRIEVED, 0.9)
        medium_conf = ledger.new_claim("Medium confidence", Provenance.DERIVED, 0.6)
        low_conf = ledger.new_claim("Low confidence", Provenance.ASSUMED, 0.3)

        summary = dashboard.get_summary()

        assert summary.total_claims == 3
        assert summary.live_count == 1  # >= 0.8
        assert summary.degrading_count == 1  # 0.5-0.8
        assert summary.stale_count == 1  # < 0.5

    def test_get_summary_with_evidence(self, ledger, dashboard):
        claim = ledger.new_claim("Claim with evidence", Provenance.RETRIEVED, 0.9)
        evidence = EvidenceRef(
            ref_id="ev_1",
            ref_type=EvidenceType.TOOL_TRACE,
            locator="trace_123",
            scope="full",
        )
        ledger.attach_evidence(claim.claim_id, evidence)

        summary = dashboard.get_summary()

        assert summary.with_evidence_count == 1

    def test_get_summary_with_assumptions(self, ledger, dashboard):
        claim = ledger.new_claim("Claim with assumption", Provenance.DERIVED, 0.7)
        ledger.add_assumption(claim.claim_id, "Assumes X is true")

        summary = dashboard.get_summary()

        assert summary.with_assumptions_count == 1

    def test_get_detail_not_found(self, dashboard):
        detail = dashboard.get_detail("nonexistent")
        assert detail is None

    def test_get_detail_basic(self, ledger, dashboard):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, 0.85)

        detail = dashboard.get_detail(claim.claim_id)

        assert detail is not None
        assert detail.claim_id == claim.claim_id
        assert detail.content == "Test claim"
        assert detail.confidence == 0.85
        assert detail.provenance == "retrieved"
        assert detail.status == "active"

    def test_get_detail_with_epistemic_status(self, ledger, dashboard):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, 0.85)
        claim.epistemic_status = ClaimStatus.SUPPORTED

        detail = dashboard.get_detail(claim.claim_id)

        assert detail.epistemic_status == "supported"

    def test_get_detail_with_evidence(self, ledger, dashboard):
        claim = ledger.new_claim("Test claim", Provenance.RETRIEVED, 0.85)
        evidence = EvidenceRef(
            ref_id="ev_1",
            ref_type=EvidenceType.TOOL_TRACE,
            locator="trace_123",
            scope="full",
        )
        ledger.attach_evidence(claim.claim_id, evidence)

        detail = dashboard.get_detail(claim.claim_id)

        assert "1 evidence item(s)" in detail.evidence_summary
        assert "tool_trace" in detail.evidence_summary

    def test_get_detail_with_assumptions(self, ledger, dashboard):
        claim = ledger.new_claim("Test claim", Provenance.DERIVED, 0.7)
        ledger.add_assumption(claim.claim_id, "Assumes database is available")

        detail = dashboard.get_detail(claim.claim_id)

        assert len(detail.assumptions) == 1
        assert detail.assumptions[0][0] == "Assumes database is available"

    def test_get_detail_with_dependencies(self, ledger, dashboard):
        claim1 = ledger.new_claim("Base claim", Provenance.RETRIEVED, 0.9)
        claim2 = ledger.new_claim("Dependent claim", Provenance.DERIVED, 0.8)
        ledger.add_dependency(claim2.claim_id, claim1.claim_id)

        detail = dashboard.get_detail(claim2.claim_id)

        assert claim1.claim_id in detail.depends_on

    def test_freshness_remaining_fresh(self, ledger, dashboard):
        claim = ledger.new_claim("Fresh claim", Provenance.RETRIEVED, 0.85)
        # Claim just created, should have freshness remaining

        detail = dashboard.get_detail(claim.claim_id)

        assert detail.freshness_remaining is not None
        assert detail.freshness_remaining.total_seconds() > 0

    def test_freshness_remaining_expired(self, ledger, dashboard):
        claim = ledger.new_claim("Old claim", Provenance.RETRIEVED, 0.85)
        # Make claim old
        claim.last_updated_at = datetime.now() - timedelta(days=30)

        detail = dashboard.get_detail(claim.claim_id)

        assert detail.freshness_remaining is None


# =============================================================================
# Format Tests
# =============================================================================


class TestFormatting:
    @pytest.fixture
    def ledger_with_claims(self):
        ledger = EpistemicLedger()
        # Create variety of claims
        for i in range(10):
            ledger.new_claim(f"High conf claim {i}", Provenance.RETRIEVED, 0.9)
        for i in range(5):
            ledger.new_claim(f"Med conf claim {i}", Provenance.DERIVED, 0.6)
        for i in range(2):
            ledger.new_claim(f"Low conf claim {i}", Provenance.ASSUMED, 0.3)
        return ledger

    def test_format_summary(self, ledger_with_claims):
        dashboard = ClaimStatusDashboard(ledger_with_claims)
        output = dashboard.format_summary()

        assert "CLAIM STATUS SUMMARY" in output
        assert "Live Claims:" in output
        assert "Degrading:" in output
        assert "Stale:" in output
        assert "Health Score:" in output

    def test_format_summary_with_attention(self, ledger_with_claims):
        dashboard = ClaimStatusDashboard(ledger_with_claims)
        output = dashboard.format_summary()

        # Should have attention section for stale claims
        assert "ATTENTION REQUIRED:" in output or "stale" in output.lower()

    def test_format_detail(self):
        ledger = EpistemicLedger()
        claim = ledger.new_claim("Test claim content", Provenance.RETRIEVED, 0.85)
        claim.epistemic_status = ClaimStatus.SUPPORTED
        claim.commit_level = "hard"

        dashboard = ClaimStatusDashboard(ledger)
        detail = dashboard.get_detail(claim.claim_id)
        output = dashboard.format_detail(detail)

        assert claim.claim_id in output
        assert "Test claim content" in output
        assert "0.85" in output
        assert "retrieved" in output
        assert "SUPPORTED" in output or "supported" in output


# =============================================================================
# Integration with Docket Tests
# =============================================================================


class TestDocketIntegration:
    def test_summary_with_contested_cases(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        ledger = EpistemicLedger()
        docket = DocketManager(governor_dir=gov_dir)

        # Create a contested case
        docket.create_case(
            CaseType.CONTESTED,
            "gc_contested",
            "Contested claim",
            "anchor_1"
        )

        dashboard = ClaimStatusDashboard(ledger, docket=docket)
        summary = dashboard.get_summary()

        assert summary.contested_count == 1


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    def test_create_claim_status_dashboard(self):
        ledger = EpistemicLedger()
        dashboard = create_claim_status_dashboard(ledger)

        assert isinstance(dashboard, ClaimStatusDashboard)
        assert dashboard.ledger is ledger

    def test_create_claim_status_dashboard_with_docket(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        ledger = EpistemicLedger()
        docket = DocketManager(governor_dir=gov_dir)

        dashboard = create_claim_status_dashboard(ledger, docket=docket)

        assert dashboard.docket is docket

    def test_create_claim_status_dashboard_custom_freshness(self):
        ledger = EpistemicLedger()
        dashboard = create_claim_status_dashboard(
            ledger, freshness_window=timedelta(days=14)
        )

        assert dashboard.freshness_window == timedelta(days=14)
