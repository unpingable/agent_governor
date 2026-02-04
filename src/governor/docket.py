"""
Docket UX: Adjudicator framing for violation resolution.

Reframes violations as "contested claims" and stale claims as "docket cases"
that require rulings. This provides a more structured UX than simple linting.

Key concepts:
- CONTESTED: Anchor violation (output conflicts with constraint)
- STALE: Confidence decayed below threshold

Rulings:
- SUSTAIN (fix): Regenerate compliant output
- AMEND (revise): Update the anchor
- GRANT_EXCEPTION (proceed): Log as intentional deviation (precedent)
- REVERIFY: Re-run verification on stale claim
- DISMISS: Accept current state for stale claim
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .staleness import StalenessDetector, ClaimFreshness
    from .violation_resolver import ViolationResolver, PendingViolation, ExceptionRecord


# =============================================================================
# Enums
# =============================================================================


class CaseType(str, Enum):
    """Types of cases on the docket."""

    CONTESTED = "contested"  # Anchor violation
    STALE = "stale"          # Confidence decayed


class CaseStatus(str, Enum):
    """Status of a docket case."""

    PENDING = "pending"      # Awaiting ruling
    RULED = "ruled"          # Ruling issued


class RulingType(str, Enum):
    """Types of rulings."""

    # For CONTESTED cases
    SUSTAIN = "sustain"           # Fix - regenerate compliant
    AMEND = "amend"               # Revise - update anchor
    GRANT_EXCEPTION = "grant_exception"  # Proceed - log as precedent

    # For STALE cases
    REVERIFY = "reverify"         # Re-run verification
    DISMISS = "dismiss"           # Accept current state


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class DocketCase:
    """A case on the docket awaiting ruling."""

    case_number: int
    case_type: CaseType
    claim_id: str
    anchor_id: str | None  # For CONTESTED cases
    status: CaseStatus
    description: str
    evidence: list[dict[str, Any]]
    created_at: datetime

    # Optional details
    blocked_content: str | None = None  # For CONTESTED: the blocked response
    freshness_info: dict[str, Any] | None = None  # For STALE: freshness details

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_number": self.case_number,
            "case_type": self.case_type.value,
            "claim_id": self.claim_id,
            "anchor_id": self.anchor_id,
            "status": self.status.value,
            "description": self.description,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat(),
            "blocked_content": self.blocked_content,
            "freshness_info": self.freshness_info,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocketCase:
        return cls(
            case_number=data["case_number"],
            case_type=CaseType(data["case_type"]),
            claim_id=data["claim_id"],
            anchor_id=data.get("anchor_id"),
            status=CaseStatus(data["status"]),
            description=data["description"],
            evidence=data.get("evidence", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            blocked_content=data.get("blocked_content"),
            freshness_info=data.get("freshness_info"),
        )


@dataclass
class PrecedentRecord:
    """
    Record of a ruling (formerly ExceptionRecord).

    A precedent is a logged ruling that may inform future decisions.
    """

    id: str
    case_number: int
    ruling: RulingType
    claim_id: str
    anchor_id: str | None
    scope: str  # "single_instance", "session", "project"
    rationale: str
    created_at: datetime
    expiry: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "case_number": self.case_number,
            "ruling": self.ruling.value,
            "claim_id": self.claim_id,
            "anchor_id": self.anchor_id,
            "scope": self.scope,
            "rationale": self.rationale,
            "created_at": self.created_at.isoformat(),
            "expiry": self.expiry.isoformat() if self.expiry else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PrecedentRecord:
        return cls(
            id=data["id"],
            case_number=data["case_number"],
            ruling=RulingType(data["ruling"]),
            claim_id=data["claim_id"],
            anchor_id=data.get("anchor_id"),
            scope=data["scope"],
            rationale=data.get("rationale", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            expiry=(
                datetime.fromisoformat(data["expiry"])
                if data.get("expiry")
                else None
            ),
        )


# =============================================================================
# DocketManager
# =============================================================================


class DocketManager:
    """
    Manages the docket of cases requiring adjudication.

    Aggregates:
    - Contested claims from ViolationResolver
    - Stale claims from StalenessDetector

    Provides ruling actions and precedent storage.
    """

    def __init__(
        self,
        resolver: ViolationResolver | None = None,
        staleness: StalenessDetector | None = None,
        governor_dir: Path | None = None,
    ):
        self.resolver = resolver
        self.staleness = staleness
        self.governor_dir = governor_dir

        # In-memory state
        self._cases: dict[int, DocketCase] = {}
        self._precedents: list[PrecedentRecord] = []
        self._next_case_number = 1

        # Load from disk if available
        if governor_dir:
            self._load_state()

    # =========================================================================
    # Case Management
    # =========================================================================

    def get_docket(self) -> list[DocketCase]:
        """
        Get all pending cases on the docket.

        Combines:
        - Pending violations from resolver (CONTESTED)
        - Stale claims from staleness detector (STALE)
        """
        cases: list[DocketCase] = []

        # Get contested cases from resolver
        if self.resolver:
            pending = self.resolver.get_pending()
            if pending:
                case = self._pending_to_case(pending)
                if case:
                    cases.append(case)

        # Get stale cases from staleness detector
        if self.staleness:
            stale_claims = self.staleness.detect_stale_claims()
            for freshness in stale_claims:
                case = self._freshness_to_case(freshness)
                if case:
                    cases.append(case)

        # Include in-memory pending cases
        for case in self._cases.values():
            if case.status == CaseStatus.PENDING:
                # Avoid duplicates
                if not any(c.case_number == case.case_number for c in cases):
                    cases.append(case)

        # Sort by case number
        cases.sort(key=lambda c: c.case_number)
        return cases

    def get_case(self, case_number: int) -> DocketCase | None:
        """Get a specific case by number."""
        # Check in-memory first
        if case_number in self._cases:
            return self._cases[case_number]

        # Check current docket
        for case in self.get_docket():
            if case.case_number == case_number:
                return case

        return None

    def create_case(
        self,
        case_type: CaseType,
        claim_id: str,
        description: str,
        anchor_id: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        blocked_content: str | None = None,
        freshness_info: dict[str, Any] | None = None,
    ) -> DocketCase:
        """Create a new case on the docket."""
        case = DocketCase(
            case_number=self._next_case_number,
            case_type=case_type,
            claim_id=claim_id,
            anchor_id=anchor_id,
            status=CaseStatus.PENDING,
            description=description,
            evidence=evidence or [],
            created_at=datetime.now(timezone.utc),
            blocked_content=blocked_content,
            freshness_info=freshness_info,
        )
        self._cases[case.case_number] = case
        self._next_case_number += 1
        self._save_state()
        return case

    # =========================================================================
    # Ruling Actions - CONTESTED Cases
    # =========================================================================

    def rule_sustain(self, case_number: int, rationale: str = "") -> PrecedentRecord:
        """
        Sustain the constraint - regenerate compliant output.

        Maps to ViolationResolver.resolve_fix()
        """
        case = self._get_pending_case(case_number)
        if case.case_type != CaseType.CONTESTED:
            raise ValueError(f"Case #{case_number} is not a contested case")

        # Mark case as ruled
        case.status = CaseStatus.RULED
        self._cases[case_number] = case

        # Create precedent
        precedent = self._create_precedent(
            case, RulingType.SUSTAIN, rationale or "Constraint sustained"
        )

        self._save_state()
        return precedent

    def rule_amend(self, case_number: int, rationale: str = "") -> PrecedentRecord:
        """
        Amend the anchor to permit the output.

        Maps to ViolationResolver.resolve_revise()
        """
        case = self._get_pending_case(case_number)
        if case.case_type != CaseType.CONTESTED:
            raise ValueError(f"Case #{case_number} is not a contested case")

        # Mark case as ruled
        case.status = CaseStatus.RULED
        self._cases[case_number] = case

        # Create precedent
        precedent = self._create_precedent(
            case, RulingType.AMEND, rationale or "Anchor amended"
        )

        self._save_state()
        return precedent

    def rule_grant_exception(
        self,
        case_number: int,
        scope: str = "single_instance",
        rationale: str = "",
    ) -> PrecedentRecord:
        """
        Grant exception - log as precedent.

        Maps to ViolationResolver.resolve_proceed()
        """
        case = self._get_pending_case(case_number)
        if case.case_type != CaseType.CONTESTED:
            raise ValueError(f"Case #{case_number} is not a contested case")

        # Mark case as ruled
        case.status = CaseStatus.RULED
        self._cases[case_number] = case

        # Create precedent with scope
        precedent = self._create_precedent(
            case,
            RulingType.GRANT_EXCEPTION,
            rationale or "Exception granted",
            scope=scope,
        )

        self._save_state()
        return precedent

    # =========================================================================
    # Ruling Actions - STALE Cases
    # =========================================================================

    def rule_reverify(self, case_number: int, rationale: str = "") -> PrecedentRecord:
        """
        Re-run verification on a stale claim.
        """
        case = self._get_pending_case(case_number)
        if case.case_type != CaseType.STALE:
            raise ValueError(f"Case #{case_number} is not a stale case")

        # Mark case as ruled
        case.status = CaseStatus.RULED
        self._cases[case_number] = case

        # Create precedent
        precedent = self._create_precedent(
            case, RulingType.REVERIFY, rationale or "Claim scheduled for reverification"
        )

        self._save_state()
        return precedent

    def rule_dismiss(self, case_number: int, rationale: str = "") -> PrecedentRecord:
        """
        Dismiss stale claim - accept current state.
        """
        case = self._get_pending_case(case_number)
        if case.case_type != CaseType.STALE:
            raise ValueError(f"Case #{case_number} is not a stale case")

        # Mark case as ruled
        case.status = CaseStatus.RULED
        self._cases[case_number] = case

        # Create precedent
        precedent = self._create_precedent(
            case, RulingType.DISMISS, rationale or "Stale claim dismissed"
        )

        self._save_state()
        return precedent

    # =========================================================================
    # Precedent Management
    # =========================================================================

    def get_precedents(self) -> list[PrecedentRecord]:
        """Get all logged precedents."""
        return list(self._precedents)

    def search_precedents(self, query: str) -> list[PrecedentRecord]:
        """Search precedents by query string."""
        query_lower = query.lower()
        return [
            p
            for p in self._precedents
            if query_lower in p.claim_id.lower()
            or query_lower in (p.anchor_id or "").lower()
            or query_lower in p.rationale.lower()
        ]

    # =========================================================================
    # Display Formatting
    # =========================================================================

    def format_case(self, case: DocketCase, style: str = "full") -> str:
        """
        Format a case for display.

        Styles:
        - "full": Detailed box format
        - "compact": Single line
        - "legacy": Simple text (backward compat)
        """
        if style == "compact":
            return self._format_compact(case)
        elif style == "legacy":
            return self._format_legacy(case)
        else:
            return self._format_full(case)

    def _format_full(self, case: DocketCase) -> str:
        """Full box format for docket display."""
        width = 50
        lines = [
            "+" + "-" * (width - 2) + "+",
            f"|{'DOCKET #' + str(case.case_number):^{width - 2}}|",
            "+" + "-" * (width - 2) + "+",
        ]

        # Claim info
        claim_line = f"| CLAIM: {case.claim_id[:width - 12]}"
        lines.append(claim_line.ljust(width - 1) + "|")

        if case.anchor_id:
            anchor_line = f"| ANCHOR: {case.anchor_id[:width - 13]}"
            lines.append(anchor_line.ljust(width - 1) + "|")

        status_label = "Contested" if case.case_type == CaseType.CONTESTED else "Stale"
        status_line = f"| STATUS: {status_label}"
        lines.append(status_line.ljust(width - 1) + "|")

        lines.append("+" + "-" * (width - 2) + "+")

        # Evidence
        if case.evidence:
            lines.append("| EVIDENCE AGAINST:".ljust(width - 1) + "|")
            for ev in case.evidence[:3]:  # Max 3
                desc = ev.get("description", str(ev))[:width - 6]
                lines.append(f"|   {desc}".ljust(width - 1) + "|")
            lines.append("+" + "-" * (width - 2) + "+")

        # Ruling options
        lines.append("| RULING OPTIONS:".ljust(width - 1) + "|")
        if case.case_type == CaseType.CONTESTED:
            lines.append("|   [S] Sustain  - Regenerate compliant".ljust(width - 1) + "|")
            lines.append("|   [A] Amend    - Update the anchor".ljust(width - 1) + "|")
            lines.append("|   [G] Grant    - Log exception".ljust(width - 1) + "|")
        else:
            lines.append("|   [R] Reverify - Re-run verification".ljust(width - 1) + "|")
            lines.append("|   [D] Dismiss  - Accept current state".ljust(width - 1) + "|")
        lines.append("|   [I] Inspect  - View full context".ljust(width - 1) + "|")
        lines.append("+" + "-" * (width - 2) + "+")

        return "\n".join(lines)

    def _format_compact(self, case: DocketCase) -> str:
        """Compact single-line format."""
        status = "CONTESTED" if case.case_type == CaseType.CONTESTED else "STALE"
        anchor = f" [{case.anchor_id}]" if case.anchor_id else ""
        return f"#{case.case_number} [{status}]{anchor} {case.claim_id}"

    def _format_legacy(self, case: DocketCase) -> str:
        """Legacy simple text format."""
        lines = [f"Case #{case.case_number}: {case.description}"]
        if case.anchor_id:
            lines.append(f"  Anchor: {case.anchor_id}")
        lines.append(f"  Type: {case.case_type.value}")
        lines.append(f"  Status: {case.status.value}")
        return "\n".join(lines)

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _get_pending_case(self, case_number: int) -> DocketCase:
        """Get a pending case or raise an error."""
        case = self.get_case(case_number)
        if case is None:
            raise ValueError(f"Case #{case_number} not found")
        if case.status != CaseStatus.PENDING:
            raise ValueError(f"Case #{case_number} has already been ruled")
        return case

    def _pending_to_case(self, pending: PendingViolation) -> DocketCase | None:
        """Convert a PendingViolation to a DocketCase."""
        # Check if we already have this case
        for case in self._cases.values():
            if case.claim_id == pending.id:
                return None  # Already tracked

        # Extract anchor IDs from violations
        anchor_ids = list({v.get("anchor_id") for v in pending.violations if v.get("anchor_id")})
        anchor_id = anchor_ids[0] if anchor_ids else None

        # Build evidence from violations
        evidence = []
        for v in pending.violations:
            evidence.append({
                "anchor_id": v.get("anchor_id"),
                "description": v.get("description", str(v)),
                "line": v.get("line"),
            })

        return self.create_case(
            case_type=CaseType.CONTESTED,
            claim_id=pending.id,
            description=f"Contested: {len(pending.violations)} violation(s)",
            anchor_id=anchor_id,
            evidence=evidence,
            blocked_content=pending.blocked_response,
        )

    def _freshness_to_case(self, freshness: ClaimFreshness) -> DocketCase | None:
        """Convert a ClaimFreshness to a DocketCase."""
        # Check if we already have this case
        for case in self._cases.values():
            if case.claim_id == freshness.claim_id and case.case_type == CaseType.STALE:
                return None  # Already tracked

        return self.create_case(
            case_type=CaseType.STALE,
            claim_id=freshness.claim_id,
            description=freshness.staleness_reason or "Claim confidence decayed",
            evidence=[{"reason": freshness.staleness_reason}] if freshness.staleness_reason else [],
            freshness_info=freshness.to_dict(),
        )

    def _create_precedent(
        self,
        case: DocketCase,
        ruling: RulingType,
        rationale: str,
        scope: str = "single_instance",
    ) -> PrecedentRecord:
        """Create and store a precedent record."""
        precedent = PrecedentRecord(
            id=f"prec_{uuid.uuid4().hex[:8]}",
            case_number=case.case_number,
            ruling=ruling,
            claim_id=case.claim_id,
            anchor_id=case.anchor_id,
            scope=scope,
            rationale=rationale,
            created_at=datetime.now(timezone.utc),
        )
        self._precedents.append(precedent)
        return precedent

    def _load_state(self) -> None:
        """Load docket state from disk."""
        if not self.governor_dir:
            return

        # Load cases
        cases_path = self.governor_dir / "docket_cases.json"
        if cases_path.exists():
            try:
                data = json.loads(cases_path.read_text())
                self._cases = {
                    int(k): DocketCase.from_dict(v) for k, v in data.get("cases", {}).items()
                }
                self._next_case_number = data.get("next_case_number", 1)
            except (json.JSONDecodeError, KeyError):
                pass

        # Load precedents
        prec_path = self.governor_dir / "precedents.json"
        if prec_path.exists():
            try:
                data = json.loads(prec_path.read_text())
                self._precedents = [
                    PrecedentRecord.from_dict(p) for p in data.get("precedents", [])
                ]
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_state(self) -> None:
        """Save docket state to disk."""
        if not self.governor_dir:
            return

        self.governor_dir.mkdir(parents=True, exist_ok=True)

        # Save cases
        cases_data = {
            "cases": {str(k): v.to_dict() for k, v in self._cases.items()},
            "next_case_number": self._next_case_number,
        }
        (self.governor_dir / "docket_cases.json").write_text(
            json.dumps(cases_data, indent=2)
        )

        # Save precedents
        prec_data = {
            "precedents": [p.to_dict() for p in self._precedents],
        }
        (self.governor_dir / "precedents.json").write_text(
            json.dumps(prec_data, indent=2)
        )


# =============================================================================
# Convenience
# =============================================================================


def create_docket_manager(
    resolver: ViolationResolver | None = None,
    staleness: StalenessDetector | None = None,
    governor_dir: Path | None = None,
) -> DocketManager:
    """Create a DocketManager with the given dependencies."""
    return DocketManager(resolver, staleness, governor_dir)


# Alias for backward compatibility
ExceptionRecordAlias = PrecedentRecord
