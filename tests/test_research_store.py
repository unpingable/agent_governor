"""Tests for research_store.py — epistemic debt tracking for research writing."""

import json
import pytest
from pathlib import Path

from governor.research_store import (
    AssumptionStatus,
    ClaimStatus,
    CollapseEvent,
    EvidenceSourceType,
    LinkType,
    ResearchClaim,
    ResearchStore,
    Assumption,
    TypedLink,
    Uncertainty,
    UncertaintyStatus,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def gov_dir(tmp_path: Path) -> Path:
    """Temporary governor directory."""
    d = tmp_path / ".governor"
    d.mkdir()
    return d


@pytest.fixture
def store(gov_dir: Path) -> ResearchStore:
    """Fresh research store."""
    return ResearchStore(gov_dir)


# ============================================================================
# TestEnums
# ============================================================================


class TestEnums:
    """Enum value tests."""

    def test_claim_status_values(self) -> None:
        assert ClaimStatus.FLOATING.value == "floating"
        assert ClaimStatus.SUPPORTED.value == "supported"
        assert ClaimStatus.CONTESTED.value == "contested"
        assert ClaimStatus.RETRACTED.value == "retracted"
        assert ClaimStatus.SUPERSEDED.value == "superseded"

    def test_assumption_status_values(self) -> None:
        assert AssumptionStatus.PROPOSED.value == "proposed"
        assert AssumptionStatus.ACCEPTED.value == "accepted"
        assert AssumptionStatus.DEPRECATED.value == "deprecated"

    def test_uncertainty_status_values(self) -> None:
        assert UncertaintyStatus.OPEN.value == "open"
        assert UncertaintyStatus.RESOLVED.value == "resolved"
        assert UncertaintyStatus.COLLAPSED.value == "collapsed"

    def test_link_type_values(self) -> None:
        assert LinkType.SUPPORTS.value == "supports"
        assert LinkType.CONTESTS.value == "contests"
        assert LinkType.ASSUMES.value == "assumes"
        assert LinkType.SUPERSEDES.value == "supersedes"
        assert LinkType.NARROWS.value == "narrows"

    def test_evidence_source_type_values(self) -> None:
        assert EvidenceSourceType.CITATION.value == "citation"
        assert EvidenceSourceType.INTUITION.value == "intuition"


# ============================================================================
# TestDataclasses
# ============================================================================


class TestDataclasses:
    """Dataclass creation and serialization tests."""

    def test_research_claim_creation(self) -> None:
        claim = ResearchClaim(id="C-001", content="Test claim")
        assert claim.id == "C-001"
        assert claim.status == ClaimStatus.FLOATING
        assert claim.created_at != ""

    def test_research_claim_roundtrip(self) -> None:
        claim = ResearchClaim(id="C-001", content="Test", scope="Methods")
        d = claim.to_dict()
        restored = ResearchClaim.from_dict(d)
        assert restored.id == claim.id
        assert restored.content == claim.content
        assert restored.scope == claim.scope
        assert restored.status == claim.status

    def test_assumption_creation(self) -> None:
        a = Assumption(id="A-001", content="Stable conditions")
        assert a.status == AssumptionStatus.PROPOSED
        assert a.dependent_claims == []

    def test_assumption_roundtrip(self) -> None:
        a = Assumption(id="A-001", content="Test", dependent_claims=["C-001"])
        d = a.to_dict()
        restored = Assumption.from_dict(d)
        assert restored.dependent_claims == ["C-001"]

    def test_uncertainty_creation(self) -> None:
        u = Uncertainty(id="U-001", content="Sample size")
        assert u.status == UncertaintyStatus.OPEN
        assert u.attached_to == ""

    def test_uncertainty_roundtrip(self) -> None:
        u = Uncertainty(id="U-001", content="Test", attached_to="C-001")
        d = u.to_dict()
        restored = Uncertainty.from_dict(d)
        assert restored.attached_to == "C-001"

    def test_typed_link_creation(self) -> None:
        link = TypedLink(id="L-001", link_type=LinkType.SUPPORTS, from_id="E-1", to_id="C-1")
        assert link.link_type == LinkType.SUPPORTS
        assert link.subtype == ""

    def test_typed_link_roundtrip(self) -> None:
        link = TypedLink(
            id="L-001", link_type=LinkType.CONTESTS,
            from_id="C-2", to_id="C-1", subtype="methodological"
        )
        d = link.to_dict()
        restored = TypedLink.from_dict(d)
        assert restored.link_type == LinkType.CONTESTS
        assert restored.subtype == "methodological"

    def test_collapse_event_creation(self) -> None:
        e = CollapseEvent(id="CE-001", claim_id="C-001")
        assert e.timestamp != ""
        assert e.description == ""

    def test_collapse_event_roundtrip(self) -> None:
        e = CollapseEvent(id="CE-001", claim_id="C-001", description="Test collapse")
        d = e.to_dict()
        restored = CollapseEvent.from_dict(d)
        assert restored.description == "Test collapse"


# ============================================================================
# TestResearchStore CRUD
# ============================================================================


class TestResearchStoreCRUD:
    """CRUD operations on the research store."""

    def test_add_claim(self, store: ResearchStore) -> None:
        claim = store.add_claim("Temperature affects rate")
        assert claim.id.startswith("C-")
        assert claim.content == "Temperature affects rate"
        assert claim.status == ClaimStatus.FLOATING

    def test_add_claim_with_scope(self, store: ResearchStore) -> None:
        claim = store.add_claim("Temperature affects rate", scope="Methods §3")
        assert claim.scope == "Methods §3"

    def test_update_claim_status(self, store: ResearchStore) -> None:
        claim = store.add_claim("Test claim")
        updated = store.update_claim_status(claim.id, ClaimStatus.RETRACTED)
        assert updated.status == ClaimStatus.RETRACTED

    def test_update_claim_status_not_found(self, store: ResearchStore) -> None:
        with pytest.raises(KeyError):
            store.update_claim_status("C-NONEXISTENT", ClaimStatus.SUPPORTED)

    def test_delete_claim(self, store: ResearchStore) -> None:
        claim = store.add_claim("To delete")
        assert store.delete_claim(claim.id)
        assert claim.id not in store.claims

    def test_delete_claim_removes_links(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Claim 1")
        c2 = store.add_claim("Claim 2")
        link = store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        store.delete_claim(c2.id)
        assert link.id not in store.links

    def test_delete_claim_not_found(self, store: ResearchStore) -> None:
        assert not store.delete_claim("C-NONEXISTENT")

    def test_add_assumption(self, store: ResearchStore) -> None:
        a = store.add_assumption("Stable incentives")
        assert a.id.startswith("A-")
        assert a.status == AssumptionStatus.PROPOSED

    def test_update_assumption_status(self, store: ResearchStore) -> None:
        a = store.add_assumption("Test")
        updated = store.update_assumption_status(a.id, AssumptionStatus.ACCEPTED)
        assert updated.status == AssumptionStatus.ACCEPTED

    def test_update_assumption_not_found(self, store: ResearchStore) -> None:
        with pytest.raises(KeyError):
            store.update_assumption_status("A-NONEXISTENT", AssumptionStatus.ACCEPTED)

    def test_delete_assumption(self, store: ResearchStore) -> None:
        a = store.add_assumption("To delete")
        assert store.delete_assumption(a.id)
        assert a.id not in store.assumptions

    def test_delete_assumption_removes_links(self, store: ResearchStore) -> None:
        c = store.add_claim("Claim")
        a = store.add_assumption("Assumption")
        link = store.add_link(LinkType.ASSUMES, c.id, a.id)
        store.delete_assumption(a.id)
        assert link.id not in store.links

    def test_add_uncertainty(self, store: ResearchStore) -> None:
        u = store.add_uncertainty("Sample size concern")
        assert u.id.startswith("U-")
        assert u.status == UncertaintyStatus.OPEN

    def test_add_uncertainty_with_attachment(self, store: ResearchStore) -> None:
        c = store.add_claim("Test claim")
        u = store.add_uncertainty("Unclear about this", attached_to=c.id)
        assert u.attached_to == c.id

    def test_update_uncertainty_status(self, store: ResearchStore) -> None:
        u = store.add_uncertainty("Test")
        updated = store.update_uncertainty_status(u.id, UncertaintyStatus.RESOLVED)
        assert updated.status == UncertaintyStatus.RESOLVED

    def test_update_uncertainty_not_found(self, store: ResearchStore) -> None:
        with pytest.raises(KeyError):
            store.update_uncertainty_status("U-NONEXISTENT", UncertaintyStatus.RESOLVED)

    def test_delete_uncertainty(self, store: ResearchStore) -> None:
        u = store.add_uncertainty("To delete")
        assert store.delete_uncertainty(u.id)

    def test_delete_uncertainty_not_found(self, store: ResearchStore) -> None:
        assert not store.delete_uncertainty("U-NONEXISTENT")


# ============================================================================
# TestLinks
# ============================================================================


class TestLinks:
    """Link operations and claim status recomputation."""

    def test_add_link(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Claim 1")
        c2 = store.add_claim("Claim 2")
        link = store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        assert link.id.startswith("L-")
        assert link.link_type == LinkType.SUPPORTS

    def test_supports_link_changes_status(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Evidence")
        c2 = store.add_claim("Main claim")
        assert c2.status == ClaimStatus.FLOATING
        store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        assert store.claims[c2.id].status == ClaimStatus.SUPPORTED

    def test_contests_link_changes_status(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Counter-evidence")
        c2 = store.add_claim("Main claim")
        store.add_link(LinkType.CONTESTS, c1.id, c2.id)
        assert store.claims[c2.id].status == ClaimStatus.CONTESTED

    def test_contests_overrides_supports(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Support")
        c2 = store.add_claim("Counter")
        c3 = store.add_claim("Main claim")
        store.add_link(LinkType.SUPPORTS, c1.id, c3.id)
        store.add_link(LinkType.CONTESTS, c2.id, c3.id)
        assert store.claims[c3.id].status == ClaimStatus.CONTESTED

    def test_remove_link(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Evidence")
        c2 = store.add_claim("Main")
        link = store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        assert store.claims[c2.id].status == ClaimStatus.SUPPORTED
        store.remove_link(link.id)
        assert store.claims[c2.id].status == ClaimStatus.FLOATING

    def test_remove_link_not_found(self, store: ResearchStore) -> None:
        assert not store.remove_link("L-NONEXISTENT")

    def test_retracted_claim_not_overwritten(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Evidence")
        c2 = store.add_claim("Retracted claim")
        store.update_claim_status(c2.id, ClaimStatus.RETRACTED)
        store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        assert store.claims[c2.id].status == ClaimStatus.RETRACTED

    def test_superseded_claim_not_overwritten(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Evidence")
        c2 = store.add_claim("Superseded claim")
        store.update_claim_status(c2.id, ClaimStatus.SUPERSEDED)
        store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        assert store.claims[c2.id].status == ClaimStatus.SUPERSEDED


# ============================================================================
# TestEDComputation
# ============================================================================


class TestEDComputation:
    """ED (Epistemic Debt) formula tests."""

    def test_empty_store_zero_ed(self, store: ResearchStore) -> None:
        ed = store.compute_ed()
        assert ed["total"] == 0
        assert ed["floating"] == 0

    def test_floating_claim_adds_3(self, store: ResearchStore) -> None:
        store.add_claim("Unsupported claim")
        ed = store.compute_ed()
        assert ed["floating"] == 1
        # Also has missing_scope (no scope provided)
        assert ed["missing_scope"] == 1
        # Total: 3*1 + 2*1 = 5
        assert ed["total"] == 5

    def test_supported_claim_no_floating_penalty(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Evidence")
        c2 = store.add_claim("Main claim", scope="Methods")
        store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        ed = store.compute_ed()
        # c1 is floating (no support), c2 is supported
        assert ed["floating"] == 1
        # c1 has no scope, c2 has scope
        assert ed["missing_scope"] == 1

    def test_open_uncertainty_adds_2(self, store: ResearchStore) -> None:
        store.add_uncertainty("Unknown factor")
        ed = store.compute_ed()
        assert ed["open_uncertain"] == 1
        assert ed["total"] == 2

    def test_collapse_event_adds_4(self, store: ResearchStore) -> None:
        c = store.add_claim("Test", scope="s")
        u = store.add_uncertainty("Question", attached_to=c.id)
        # Resolve without support → collapse
        store.update_uncertainty_status(u.id, UncertaintyStatus.RESOLVED)
        ed = store.compute_ed()
        assert ed["collapses"] == 1

    def test_contested_claim_adds_1(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Counter", scope="s")
        c2 = store.add_claim("Main", scope="s")
        store.add_link(LinkType.CONTESTS, c1.id, c2.id)
        ed = store.compute_ed()
        assert ed["contests"] == 1

    def test_full_ed_formula(self, store: ResearchStore) -> None:
        # 2 floating, 1 missing scope, 1 open uncertainty, 0 collapses, 1 contest
        c1 = store.add_claim("Floating 1")           # floating, no scope
        c2 = store.add_claim("Floating 2", scope="s") # floating, has scope
        c3 = store.add_claim("Contested", scope="s")  # will be contested
        c4 = store.add_claim("Counter", scope="s")     # floating (but acts as contester)
        store.add_link(LinkType.CONTESTS, c4.id, c3.id)
        store.add_uncertainty("Unknown")
        ed = store.compute_ed()
        # floating: c1, c2, c4 = 3
        # missing_scope: c1 = 1
        # open_uncertain: 1
        # contests: c3 = 1
        # collapses: 0
        # total = 3*3 + 2*1 + 2*1 + 4*0 + 1*1 = 9+2+2+0+1 = 14
        assert ed["total"] == 14


# ============================================================================
# TestCollapseEvents
# ============================================================================


class TestCollapseEvents:
    """Collapse event detection."""

    def test_resolve_without_support_creates_collapse(self, store: ResearchStore) -> None:
        c = store.add_claim("Claim")
        u = store.add_uncertainty("Doubt", attached_to=c.id)
        store.update_uncertainty_status(u.id, UncertaintyStatus.RESOLVED)
        assert len(store.collapse_events) == 1
        assert store.collapse_events[0].claim_id == c.id

    def test_resolve_with_support_no_collapse(self, store: ResearchStore) -> None:
        c1 = store.add_claim("Evidence")
        c2 = store.add_claim("Main claim")
        store.add_link(LinkType.SUPPORTS, c1.id, c2.id)
        u = store.add_uncertainty("Doubt", attached_to=c2.id)
        store.update_uncertainty_status(u.id, UncertaintyStatus.RESOLVED)
        assert len(store.collapse_events) == 0
        assert store.uncertainties[u.id].status == UncertaintyStatus.RESOLVED

    def test_resolve_unattached_no_collapse(self, store: ResearchStore) -> None:
        u = store.add_uncertainty("General doubt")
        store.update_uncertainty_status(u.id, UncertaintyStatus.RESOLVED)
        assert len(store.collapse_events) == 0

    def test_collapse_sets_collapsed_status(self, store: ResearchStore) -> None:
        c = store.add_claim("Claim")
        u = store.add_uncertainty("Doubt", attached_to=c.id)
        store.update_uncertainty_status(u.id, UncertaintyStatus.RESOLVED)
        assert store.uncertainties[u.id].status == UncertaintyStatus.COLLAPSED


# ============================================================================
# TestPersistence
# ============================================================================


class TestPersistence:
    """Save/load roundtrip tests."""

    def test_save_load_roundtrip(self, gov_dir: Path) -> None:
        store1 = ResearchStore(gov_dir)
        c = store1.add_claim("Test claim", scope="s")
        a = store1.add_assumption("Test assumption")
        u = store1.add_uncertainty("Test uncertainty", attached_to=c.id)
        store1.add_link(LinkType.SUPPORTS, a.id, c.id)

        store2 = ResearchStore(gov_dir)
        assert len(store2.claims) == 1
        assert len(store2.assumptions) == 1
        assert len(store2.uncertainties) == 1
        assert len(store2.links) == 1

    def test_empty_store_loads_clean(self, gov_dir: Path) -> None:
        store = ResearchStore(gov_dir)
        assert len(store.claims) == 0
        assert store.compute_ed()["total"] == 0

    def test_corrupted_json_recovery(self, gov_dir: Path) -> None:
        research_dir = gov_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        (research_dir / "store.json").write_text("not valid json{{{")
        store = ResearchStore(gov_dir)
        assert len(store.claims) == 0

    def test_to_dict_from_dict(self, gov_dir: Path) -> None:
        store1 = ResearchStore(gov_dir)
        store1.add_claim("Test")
        store1.add_assumption("Assumed")
        d = store1.to_dict()

        store2 = ResearchStore.from_dict(d, gov_dir)
        assert len(store2.claims) == 1
        assert len(store2.assumptions) == 1


# ============================================================================
# TestExportImport
# ============================================================================


class TestExportImport:
    """Export and import operations."""

    def test_export_data(self, store: ResearchStore) -> None:
        store.add_claim("Test")
        data = store.export_data()
        assert len(data["claims"]) == 1
        assert "links" in data

    def test_import_data_merges(self, gov_dir: Path) -> None:
        store1 = ResearchStore(gov_dir)
        store1.add_claim("Existing claim")
        exported = store1.export_data()

        store2 = ResearchStore(gov_dir)
        # Add a new claim to import data
        exported["claims"].append({
            "id": "C-IMPORT1",
            "content": "Imported claim",
            "status": "floating",
            "scope": "",
            "created_at": "2024-01-01T00:00:00",
        })
        count = store2.import_data(exported)
        assert count == 1  # Only the new one
        assert "C-IMPORT1" in store2.claims

    def test_import_skips_duplicates(self, store: ResearchStore) -> None:
        c = store.add_claim("Test")
        data = store.export_data()
        count = store.import_data(data)
        assert count == 0  # Already exists

    def test_import_empty(self, store: ResearchStore) -> None:
        count = store.import_data({})
        assert count == 0


# ============================================================================
# TestGetState
# ============================================================================


class TestGetState:
    """get_state() returns complete snapshot."""

    def test_state_includes_all_sections(self, store: ResearchStore) -> None:
        store.add_claim("Claim")
        store.add_assumption("Assumption")
        store.add_uncertainty("Uncertainty")
        state = store.get_state()
        assert "claims" in state
        assert "assumptions" in state
        assert "uncertainties" in state
        assert "links" in state
        assert "collapse_events" in state
        assert "ed" in state
        assert len(state["claims"]) == 1
        assert len(state["assumptions"]) == 1
        assert len(state["uncertainties"]) == 1

    def test_state_ed_matches_compute(self, store: ResearchStore) -> None:
        store.add_claim("Test")
        state = store.get_state()
        ed_direct = store.compute_ed()
        assert state["ed"] == ed_direct
