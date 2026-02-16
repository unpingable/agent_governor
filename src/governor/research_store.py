"""
Research Store: epistemic debt tracking for research writing.

Claims, assumptions, uncertainties, typed links, and an ED (Epistemic Debt)
score that makes epistemic debt feel like technical debt — visible, survivable,
impossible to gaslight away.

Data model supports:
- Claims with status tracking (FLOATING → SUPPORTED / CONTESTED / RETRACTED / SUPERSEDED)
- Assumptions with lifecycle (PROPOSED → ACCEPTED / DEPRECATED)
- Uncertainties with resolution (OPEN → RESOLVED / COLLAPSED)
- Typed links between items (SUPPORTS, CONTESTS, ASSUMES, SUPERSEDES, NARROWS)
- Collapse events (logged when uncertainty resolves without new support)
- ED formula: weighted sum of epistemic liabilities

Storage: JSON file at {governor_dir}/research/store.json
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ============================================================================
# Enums
# ============================================================================


class ClaimStatus(Enum):
    """Status of a research claim."""
    FLOATING = "floating"       # No support links
    SUPPORTED = "supported"     # Has at least one SUPPORTS link
    CONTESTED = "contested"     # Has at least one CONTESTS link
    RETRACTED = "retracted"     # Manually retracted
    SUPERSEDED = "superseded"   # Replaced by another claim


class AssumptionStatus(Enum):
    """Status of an assumption."""
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"


class UncertaintyStatus(Enum):
    """Status of an uncertainty."""
    OPEN = "open"
    RESOLVED = "resolved"
    COLLAPSED = "collapsed"     # Resolved without new support — danger


class LinkType(Enum):
    """Type of typed link between items."""
    SUPPORTS = "supports"
    CONTESTS = "contests"
    ASSUMES = "assumes"
    SUPERSEDES = "supersedes"
    NARROWS = "narrows"


class EvidenceSourceType(Enum):
    """Source type for evidence backing."""
    CITATION = "citation"
    EMPIRICAL = "empirical"
    OBSERVATION = "observation"
    AUTHORITY = "authority"
    ANALOGY = "analogy"
    INTUITION = "intuition"


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class ResearchClaim:
    """A claim in the research store."""
    id: str
    content: str
    status: ClaimStatus = ClaimStatus.FLOATING
    scope: str = ""
    source_ref: str = ""
    """Structured source reference (e.g., 'doi:10.1038/x', 'pypi:numpy', 'cve:CVE-2021-1234')."""
    captured_from: str = ""
    """Capture ID or turn ID that produced this claim."""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "scope": self.scope,
            "created_at": self.created_at,
        }
        if self.source_ref:
            d["source_ref"] = self.source_ref
        if self.captured_from:
            d["captured_from"] = self.captured_from
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchClaim:
        return cls(
            id=data["id"],
            content=data["content"],
            status=ClaimStatus(data.get("status", "floating")),
            scope=data.get("scope", ""),
            source_ref=data.get("source_ref", ""),
            captured_from=data.get("captured_from", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class Assumption:
    """An assumption underlying one or more claims."""
    id: str
    content: str
    status: AssumptionStatus = AssumptionStatus.PROPOSED
    dependent_claims: list[str] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "dependent_claims": self.dependent_claims,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Assumption:
        return cls(
            id=data["id"],
            content=data["content"],
            status=AssumptionStatus(data.get("status", "proposed")),
            dependent_claims=data.get("dependent_claims", []),
            created_at=data.get("created_at", ""),
        )


@dataclass
class Uncertainty:
    """An open uncertainty attached to a claim or assumption."""
    id: str
    content: str
    status: UncertaintyStatus = UncertaintyStatus.OPEN
    attached_to: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status.value,
            "attached_to": self.attached_to,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Uncertainty:
        return cls(
            id=data["id"],
            content=data["content"],
            status=UncertaintyStatus(data.get("status", "open")),
            attached_to=data.get("attached_to", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class TypedLink:
    """A typed link between two items in the store."""
    id: str
    link_type: LinkType
    from_id: str
    to_id: str
    subtype: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "link_type": self.link_type.value,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "subtype": self.subtype,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TypedLink:
        return cls(
            id=data["id"],
            link_type=LinkType(data["link_type"]),
            from_id=data["from_id"],
            to_id=data["to_id"],
            subtype=data.get("subtype", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class CollapseEvent:
    """Logged when an uncertainty resolves without new supporting evidence."""
    id: str
    claim_id: str
    timestamp: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "timestamp": self.timestamp,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CollapseEvent:
        return cls(
            id=data["id"],
            claim_id=data["claim_id"],
            timestamp=data.get("timestamp", ""),
            description=data.get("description", ""),
        )


# ============================================================================
# ResearchStore
# ============================================================================


class ResearchStore:
    """Persistent store for research claims, assumptions, uncertainties, and links.

    Storage format: JSON file at {governor_dir}/research/store.json
    """

    def __init__(self, governor_dir: Path) -> None:
        self._dir = governor_dir / "research"
        self._path = self._dir / "store.json"
        self.claims: dict[str, ResearchClaim] = {}
        self.assumptions: dict[str, Assumption] = {}
        self.uncertainties: dict[str, Uncertainty] = {}
        self.links: dict[str, TypedLink] = {}
        self.collapse_events: list[CollapseEvent] = []
        self._load()

    # ── CRUD: Claims ────────────────────────────────────────────────────

    def add_claim(
        self,
        content: str,
        scope: str = "",
        source_ref: str = "",
        captured_from: str = "",
    ) -> ResearchClaim:
        """Add a new research claim."""
        claim_id = f"C-{uuid.uuid4().hex[:6].upper()}"
        claim = ResearchClaim(
            id=claim_id,
            content=content,
            scope=scope,
            source_ref=source_ref,
            captured_from=captured_from,
        )
        self.claims[claim_id] = claim
        self._save()
        return claim

    def update_claim_status(self, claim_id: str, status: ClaimStatus) -> ResearchClaim:
        """Manually override a claim's status."""
        if claim_id not in self.claims:
            raise KeyError(f"Claim not found: {claim_id}")
        self.claims[claim_id].status = status
        self._save()
        return self.claims[claim_id]

    def delete_claim(self, claim_id: str) -> bool:
        """Delete a claim and its associated links."""
        if claim_id not in self.claims:
            return False
        del self.claims[claim_id]
        # Remove links referencing this claim
        to_remove = [
            lid for lid, link in self.links.items()
            if link.from_id == claim_id or link.to_id == claim_id
        ]
        for lid in to_remove:
            del self.links[lid]
        self._save()
        return True

    # ── CRUD: Assumptions ───────────────────────────────────────────────

    def add_assumption(self, content: str) -> Assumption:
        """Add a new assumption."""
        assumption_id = f"A-{uuid.uuid4().hex[:6].upper()}"
        assumption = Assumption(id=assumption_id, content=content)
        self.assumptions[assumption_id] = assumption
        self._save()
        return assumption

    def update_assumption_status(
        self, assumption_id: str, status: AssumptionStatus
    ) -> Assumption:
        """Update an assumption's status."""
        if assumption_id not in self.assumptions:
            raise KeyError(f"Assumption not found: {assumption_id}")
        self.assumptions[assumption_id].status = status
        self._save()
        return self.assumptions[assumption_id]

    def delete_assumption(self, assumption_id: str) -> bool:
        """Delete an assumption."""
        if assumption_id not in self.assumptions:
            return False
        del self.assumptions[assumption_id]
        # Remove links referencing this assumption
        to_remove = [
            lid for lid, link in self.links.items()
            if link.from_id == assumption_id or link.to_id == assumption_id
        ]
        for lid in to_remove:
            del self.links[lid]
        self._save()
        return True

    # ── CRUD: Uncertainties ─────────────────────────────────────────────

    def add_uncertainty(
        self, content: str, attached_to: str = ""
    ) -> Uncertainty:
        """Add a new uncertainty, optionally attached to a claim or assumption."""
        uncertainty_id = f"U-{uuid.uuid4().hex[:6].upper()}"
        uncertainty = Uncertainty(
            id=uncertainty_id, content=content, attached_to=attached_to
        )
        self.uncertainties[uncertainty_id] = uncertainty
        self._save()
        return uncertainty

    def update_uncertainty_status(
        self, uncertainty_id: str, status: UncertaintyStatus
    ) -> Uncertainty:
        """Update an uncertainty's status.

        If transitioning OPEN → RESOLVED, checks whether the attached claim
        gained new support. If not, logs a CollapseEvent.
        """
        if uncertainty_id not in self.uncertainties:
            raise KeyError(f"Uncertainty not found: {uncertainty_id}")

        unc = self.uncertainties[uncertainty_id]
        old_status = unc.status

        # Collapse detection: OPEN → RESOLVED without new support
        if (
            old_status == UncertaintyStatus.OPEN
            and status == UncertaintyStatus.RESOLVED
            and unc.attached_to
        ):
            # Check if the attached claim has any SUPPORTS links
            has_support = any(
                link.link_type == LinkType.SUPPORTS and link.to_id == unc.attached_to
                for link in self.links.values()
            )
            if not has_support:
                event = CollapseEvent(
                    id=f"CE-{uuid.uuid4().hex[:6].upper()}",
                    claim_id=unc.attached_to,
                    description=(
                        f"Uncertainty {uncertainty_id} resolved without new support "
                        f"for {unc.attached_to}"
                    ),
                )
                self.collapse_events.append(event)
                status = UncertaintyStatus.COLLAPSED

        unc.status = status
        self._save()
        return unc

    def delete_uncertainty(self, uncertainty_id: str) -> bool:
        """Delete an uncertainty."""
        if uncertainty_id not in self.uncertainties:
            return False
        del self.uncertainties[uncertainty_id]
        self._save()
        return True

    # ── CRUD: Links ─────────────────────────────────────────────────────

    def add_link(
        self,
        link_type: LinkType,
        from_id: str,
        to_id: str,
        subtype: str = "",
    ) -> TypedLink:
        """Add a typed link between two items."""
        link_id = f"L-{uuid.uuid4().hex[:6].upper()}"
        link = TypedLink(
            id=link_id,
            link_type=link_type,
            from_id=from_id,
            to_id=to_id,
            subtype=subtype,
        )
        self.links[link_id] = link
        # Recompute status of the target claim if applicable
        if to_id in self.claims:
            self.recompute_claim_status(to_id)
        self._save()
        return link

    def remove_link(self, link_id: str) -> bool:
        """Remove a link and recompute affected claim status."""
        if link_id not in self.links:
            return False
        link = self.links.pop(link_id)
        # Recompute status of the target claim if applicable
        if link.to_id in self.claims:
            self.recompute_claim_status(link.to_id)
        self._save()
        return True

    # ── Status Recomputation ────────────────────────────────────────────

    def recompute_claim_status(self, claim_id: str) -> None:
        """Recompute a claim's status from its incoming links.

        Rules:
        - Has any CONTESTS link targeting it → CONTESTED
        - Has any SUPPORTS link targeting it → SUPPORTED
        - Otherwise → FLOATING
        - RETRACTED and SUPERSEDED are manual — not overwritten
        """
        if claim_id not in self.claims:
            return

        claim = self.claims[claim_id]

        # Don't overwrite manual terminal states
        if claim.status in (ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED):
            return

        incoming = [
            link for link in self.links.values() if link.to_id == claim_id
        ]

        has_contest = any(link.link_type == LinkType.CONTESTS for link in incoming)
        has_support = any(link.link_type == LinkType.SUPPORTS for link in incoming)

        if has_contest:
            claim.status = ClaimStatus.CONTESTED
        elif has_support:
            claim.status = ClaimStatus.SUPPORTED
        else:
            claim.status = ClaimStatus.FLOATING

    # ── ED Computation ──────────────────────────────────────────────────

    def compute_ed(self) -> dict[str, int]:
        """Compute the Epistemic Debt score.

        ED = 3 * floating_claims
           + 2 * missing_scope_claims
           + 2 * open_uncertainties
           + 4 * collapse_events
           + 1 * open_contests
        """
        floating = sum(
            1 for c in self.claims.values() if c.status == ClaimStatus.FLOATING
        )
        missing_scope = sum(
            1 for c in self.claims.values() if not c.scope
        )
        open_uncertain = sum(
            1 for u in self.uncertainties.values()
            if u.status == UncertaintyStatus.OPEN
        )
        collapses = len(self.collapse_events)
        contests = sum(
            1 for c in self.claims.values() if c.status == ClaimStatus.CONTESTED
        )

        total = (
            3 * floating
            + 2 * missing_scope
            + 2 * open_uncertain
            + 4 * collapses
            + 1 * contests
        )

        return {
            "floating": floating,
            "missing_scope": missing_scope,
            "open_uncertain": open_uncertain,
            "collapses": collapses,
            "contests": contests,
            "total": total,
        }

    # ── State Snapshot ──────────────────────────────────────────────────

    def get_state(self) -> dict[str, Any]:
        """Full state snapshot for sidebar polling."""
        return {
            "claims": [c.to_dict() for c in self.claims.values()],
            "assumptions": [a.to_dict() for a in self.assumptions.values()],
            "uncertainties": [u.to_dict() for u in self.uncertainties.values()],
            "links": [l.to_dict() for l in self.links.values()],
            "collapse_events": [e.to_dict() for e in self.collapse_events],
            "ed": self.compute_ed(),
        }

    # ── Export / Import ─────────────────────────────────────────────────

    def export_data(self) -> dict[str, Any]:
        """Export all data for backup/transfer."""
        return self.to_dict()

    def import_data(self, data: dict[str, Any]) -> int:
        """Import data from an export, merging with existing. Returns count imported."""
        imported = 0

        for claim_data in data.get("claims", []):
            cid = claim_data.get("id", "")
            if cid and cid not in self.claims:
                self.claims[cid] = ResearchClaim.from_dict(claim_data)
                imported += 1

        for assum_data in data.get("assumptions", []):
            aid = assum_data.get("id", "")
            if aid and aid not in self.assumptions:
                self.assumptions[aid] = Assumption.from_dict(assum_data)
                imported += 1

        for unc_data in data.get("uncertainties", []):
            uid = unc_data.get("id", "")
            if uid and uid not in self.uncertainties:
                self.uncertainties[uid] = Uncertainty.from_dict(unc_data)
                imported += 1

        for link_data in data.get("links", []):
            lid = link_data.get("id", "")
            if lid and lid not in self.links:
                self.links[lid] = TypedLink.from_dict(link_data)
                imported += 1

        for event_data in data.get("collapse_events", []):
            eid = event_data.get("id", "")
            existing_ids = {e.id for e in self.collapse_events}
            if eid and eid not in existing_ids:
                self.collapse_events.append(CollapseEvent.from_dict(event_data))
                imported += 1

        self._save()
        return imported

    # ── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize entire store to dict."""
        return {
            "claims": [c.to_dict() for c in self.claims.values()],
            "assumptions": [a.to_dict() for a in self.assumptions.values()],
            "uncertainties": [u.to_dict() for u in self.uncertainties.values()],
            "links": [l.to_dict() for l in self.links.values()],
            "collapse_events": [e.to_dict() for e in self.collapse_events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], governor_dir: Path) -> ResearchStore:
        """Deserialize from dict. Creates a store and populates it."""
        store = cls.__new__(cls)
        store._dir = governor_dir / "research"
        store._path = store._dir / "store.json"
        store.claims = {
            c["id"]: ResearchClaim.from_dict(c)
            for c in data.get("claims", [])
        }
        store.assumptions = {
            a["id"]: Assumption.from_dict(a)
            for a in data.get("assumptions", [])
        }
        store.uncertainties = {
            u["id"]: Uncertainty.from_dict(u)
            for u in data.get("uncertainties", [])
        }
        store.links = {
            l["id"]: TypedLink.from_dict(l)
            for l in data.get("links", [])
        }
        store.collapse_events = [
            CollapseEvent.from_dict(e)
            for e in data.get("collapse_events", [])
        ]
        return store

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load store from disk. Starts empty if file doesn't exist or is corrupt."""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text())
            self.claims = {
                c["id"]: ResearchClaim.from_dict(c)
                for c in data.get("claims", [])
            }
            self.assumptions = {
                a["id"]: Assumption.from_dict(a)
                for a in data.get("assumptions", [])
            }
            self.uncertainties = {
                u["id"]: Uncertainty.from_dict(u)
                for u in data.get("uncertainties", [])
            }
            self.links = {
                l["id"]: TypedLink.from_dict(l)
                for l in data.get("links", [])
            }
            self.collapse_events = [
                CollapseEvent.from_dict(e)
                for e in data.get("collapse_events", [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            # Corrupted JSON — start fresh
            self.claims = {}
            self.assumptions = {}
            self.uncertainties = {}
            self.links = {}
            self.collapse_events = []

    def _save(self) -> None:
        """Persist store to disk."""
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self.to_dict(), indent=2))
