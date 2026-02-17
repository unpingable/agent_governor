# SPDX-License-Identifier: Apache-2.0
"""
Claim Status Dashboard: Weather report for claim health.

Provides a high-level summary of claim freshness and health,
plus detailed views of individual claims.

The "weather report" format gives users at-a-glance understanding
of their epistemic state without diving into individual claims.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .epistemic import EpistemicLedger, GroundedClaim, ClaimStatus as EpistemicClaimStatus
    from .docket import DocketManager


# =============================================================================
# Summary
# =============================================================================


@dataclass
class ClaimStatusSummary:
    """High-level summary of claim health."""

    live_count: int
    live_confidence_avg: float
    degrading_count: int  # confidence 0.5-0.8
    stale_count: int      # confidence < 0.5
    contested_count: int  # awaiting ruling

    # Additional metrics
    total_claims: int = 0
    high_confidence_count: int = 0  # confidence >= 0.8
    with_evidence_count: int = 0
    with_assumptions_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "live_count": self.live_count,
            "live_confidence_avg": self.live_confidence_avg,
            "degrading_count": self.degrading_count,
            "stale_count": self.stale_count,
            "contested_count": self.contested_count,
            "total_claims": self.total_claims,
            "high_confidence_count": self.high_confidence_count,
            "with_evidence_count": self.with_evidence_count,
            "with_assumptions_count": self.with_assumptions_count,
        }

    @property
    def health_score(self) -> float:
        """Overall health score 0-100."""
        if self.total_claims == 0:
            return 100.0

        # Penalize stale and contested claims heavily
        base = (self.live_count / self.total_claims) * 100
        penalty = (self.stale_count + self.contested_count) / self.total_claims * 30
        return max(0.0, min(100.0, base - penalty))


# =============================================================================
# Detail
# =============================================================================


@dataclass
class ClaimDetail:
    """Detailed view of a single claim's status."""

    claim_id: str
    content: str
    status: str  # governance status
    epistemic_status: str | None
    confidence: float
    provenance: str
    verified_at: datetime | None
    freshness_remaining: timedelta | None
    evidence_summary: str
    assumptions: list[tuple[str, bool]]  # (assumption, still_valid)

    # Additional context
    commit_level: str | None = None
    source_agent: str | None = None
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "content": self.content,
            "status": self.status,
            "epistemic_status": self.epistemic_status,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "freshness_remaining_seconds": (
                self.freshness_remaining.total_seconds()
                if self.freshness_remaining
                else None
            ),
            "evidence_summary": self.evidence_summary,
            "assumptions": [
                {"text": a, "valid": v} for a, v in self.assumptions
            ],
            "commit_level": self.commit_level,
            "source_agent": self.source_agent,
            "depends_on": self.depends_on,
        }


# =============================================================================
# Dashboard
# =============================================================================


class ClaimStatusDashboard:
    """
    Dashboard for claim health monitoring.

    Provides:
    - Summary view ("weather report")
    - Detailed individual claim views
    - Health scoring
    """

    def __init__(
        self,
        ledger: EpistemicLedger,
        docket: DocketManager | None = None,
        freshness_window: timedelta | None = None,
    ):
        self.ledger = ledger
        self.docket = docket
        self.freshness_window = freshness_window or timedelta(days=7)

    def get_summary(self) -> ClaimStatusSummary:
        """Get high-level summary of all claims."""
        claims = list(self.ledger.claims.values())

        # Count contested (from docket) - always check even if no claims
        contested_count = 0
        if self.docket:
            from .docket import CaseType, CaseStatus
            contested_cases = [
                c for c in self.docket.get_docket()
                if c.case_type == CaseType.CONTESTED and c.status == CaseStatus.PENDING
            ]
            contested_count = len(contested_cases)

        if not claims:
            return ClaimStatusSummary(
                live_count=0,
                live_confidence_avg=0.0,
                degrading_count=0,
                stale_count=0,
                contested_count=contested_count,
                total_claims=0,
            )

        # Count by confidence level
        live = []
        degrading = []
        stale = []

        for claim in claims:
            if claim.confidence >= 0.8:
                live.append(claim)
            elif claim.confidence >= 0.5:
                degrading.append(claim)
            else:
                stale.append(claim)

        # Calculate averages
        live_confidence_avg = (
            sum(c.confidence for c in live) / len(live)
            if live else 0.0
        )

        # Additional metrics
        with_evidence = len([c for c in claims if c.evidence_refs])
        with_assumptions = len([c for c in claims if c.assumptions])
        high_confidence = len([c for c in claims if c.confidence >= 0.8])

        return ClaimStatusSummary(
            live_count=len(live),
            live_confidence_avg=live_confidence_avg,
            degrading_count=len(degrading),
            stale_count=len(stale),
            contested_count=contested_count,
            total_claims=len(claims),
            high_confidence_count=high_confidence,
            with_evidence_count=with_evidence,
            with_assumptions_count=with_assumptions,
        )

    def get_detail(self, claim_id: str) -> ClaimDetail | None:
        """Get detailed view of a specific claim."""
        claim = self.ledger.get(claim_id)
        if claim is None:
            return None

        # Calculate freshness remaining
        now = datetime.now()
        age = now - claim.last_updated_at
        freshness_remaining = self.freshness_window - age
        if freshness_remaining.total_seconds() < 0:
            freshness_remaining = None

        # Build evidence summary
        if claim.evidence_refs:
            evidence_types = [e.ref_type.value for e in claim.evidence_refs]
            evidence_summary = f"{len(claim.evidence_refs)} evidence item(s): {', '.join(set(evidence_types))}"
        else:
            evidence_summary = "No evidence attached"

        # Check assumption validity (simplified - just mark as valid)
        assumptions = [(a, True) for a in claim.assumptions]

        return ClaimDetail(
            claim_id=claim.claim_id,
            content=claim.content,
            status=claim.status.value,
            epistemic_status=claim.epistemic_status.value if claim.epistemic_status else None,
            confidence=claim.confidence,
            provenance=claim.provenance.value,
            verified_at=claim.last_updated_at,
            freshness_remaining=freshness_remaining,
            evidence_summary=evidence_summary,
            assumptions=assumptions,
            commit_level=claim.commit_level,
            source_agent=claim.source_agent_id,
            depends_on=list(claim.depends_on),
        )

    def format_summary(self) -> str:
        """Format summary as a "weather report"."""
        summary = self.get_summary()

        # Build progress bar
        total = max(1, summary.total_claims)
        live_bar = int((summary.live_count / total) * 20)
        degrading_bar = int((summary.degrading_count / total) * 20)
        stale_bar = int((summary.stale_count / total) * 20)

        lines = [
            "CLAIM STATUS SUMMARY",
            "=" * 50,
            f"Live Claims:          {summary.live_count:3}  {'█' * live_bar}{'░' * (20 - live_bar)}",
            f"Degrading:            {summary.degrading_count:3}  {'█' * degrading_bar}{'░' * (20 - degrading_bar)}  (confidence 0.5-0.8)",
            f"Stale:                {summary.stale_count:3}  {'█' * stale_bar}{'░' * (20 - stale_bar)}  (confidence <0.5)",
            f"Contested:            {summary.contested_count:3}  {'░' * 20}  (awaiting ruling)",
            "",
            f"Health Score: {summary.health_score:.0f}/100",
        ]

        # Attention required section
        attention = []
        if summary.contested_count > 0:
            attention.append(f"  * {summary.contested_count} contested claim(s) awaiting ruling")
        if summary.stale_count > 0:
            attention.append(f"  * {summary.stale_count} stale claim(s) need reverification or dismissal")

        if attention:
            lines.append("")
            lines.append("ATTENTION REQUIRED:")
            lines.extend(attention)
            lines.append("")
            lines.append("Run `governor docket` to adjudicate.")

        return "\n".join(lines)

    def format_detail(self, detail: ClaimDetail) -> str:
        """Format a detailed claim view."""
        lines = [
            f"CLAIM: {detail.claim_id}",
            "=" * 50,
            f"Content: {detail.content[:100]}{'...' if len(detail.content) > 100 else ''}",
            "",
            f"Status:           {detail.status}",
            f"Epistemic Status: {detail.epistemic_status or 'N/A'}",
            f"Confidence:       {detail.confidence:.2f}",
            f"Provenance:       {detail.provenance}",
            f"Commit Level:     {detail.commit_level or 'N/A'}",
            "",
            f"Verified At:      {detail.verified_at.isoformat() if detail.verified_at else 'N/A'}",
        ]

        if detail.freshness_remaining:
            hours = detail.freshness_remaining.total_seconds() / 3600
            lines.append(f"Freshness:        {hours:.1f} hours remaining")
        else:
            lines.append("Freshness:        EXPIRED")

        lines.append("")
        lines.append(f"Evidence:         {detail.evidence_summary}")

        if detail.assumptions:
            lines.append("")
            lines.append("Assumptions:")
            for assumption, valid in detail.assumptions:
                status = "OK" if valid else "VIOLATED"
                lines.append(f"  [{status}] {assumption}")

        if detail.depends_on:
            lines.append("")
            lines.append("Dependencies:")
            for dep_id in detail.depends_on:
                lines.append(f"  -> {dep_id}")

        return "\n".join(lines)


# =============================================================================
# Convenience
# =============================================================================


def create_claim_status_dashboard(
    ledger: EpistemicLedger,
    docket: DocketManager | None = None,
    freshness_window: timedelta | None = None,
) -> ClaimStatusDashboard:
    """Create a ClaimStatusDashboard for an epistemic ledger."""
    return ClaimStatusDashboard(ledger, docket, freshness_window)
