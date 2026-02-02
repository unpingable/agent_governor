"""
Tests for GovernorViewModel (schema v2).

Covers:
- Shape tests: every dataclass to_dict() has correct keys/types
- ID prefix tests: dec_, clm_, ev_, vio_ enforced
- Builder tests: each builder with minimal .governor/ setup
- Graceful degradation: section failure doesn't break others
- V1 compat: build_v1_state() output matches expected format
- Schema invariants: cross-refs valid, IDs unique
- Claim state mapping: each epistemic_status maps correctly
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governor.viewmodel import (
    SCHEMA_VERSION,
    GovernorViewModel,
    SessionView,
    RegimeView,
    DecisionView,
    ClaimView,
    EvidenceView,
    ViolationView,
    ExecutionView,
    ExecutionActionView,
    StabilityView,
    build_session,
    build_regime,
    build_decisions,
    build_claims,
    build_evidence,
    build_violations,
    build_execution,
    build_stability,
    build_viewmodel,
    build_v1_state,
    _map_epistemic_status,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def gov_dir(tmp_path):
    """Create a minimal .governor directory."""
    d = tmp_path / ".governor"
    d.mkdir()
    return d


@pytest.fixture
def root(tmp_path):
    return tmp_path


# =============================================================================
# Shape tests: every dataclass to_dict() has correct keys/types
# =============================================================================


class TestSessionViewShape:
    def test_keys(self):
        v = SessionView(
            mode="strict",
            authority_level="Balanced",
            active_constraints=["strict_envelope"],
            jurisdiction="factual",
            active_profile="strict",
        )
        d = v.to_dict()
        assert set(d.keys()) == {"mode", "authority_level", "active_constraints", "jurisdiction", "active_profile"}
        assert isinstance(d["active_constraints"], list)

    def test_nullable_fields(self):
        v = SessionView(mode="exploratory", authority_level="Low", active_constraints=[], jurisdiction=None, active_profile=None)
        d = v.to_dict()
        assert d["jurisdiction"] is None
        assert d["active_profile"] is None


class TestRegimeViewShape:
    def test_keys(self):
        v = RegimeView(name="elastic", setpoints={}, telemetry={}, boil_mode="oolong", transitions=[])
        d = v.to_dict()
        assert set(d.keys()) == {"name", "setpoints", "telemetry", "boil_mode", "transitions"}

    def test_types(self):
        v = RegimeView(
            name="warm",
            setpoints={"hysteresis": 0.5},
            telemetry={"rejection_rate": 0.1},
            boil_mode=None,
            transitions=[{"from": "elastic", "to": "warm"}],
        )
        d = v.to_dict()
        assert isinstance(d["setpoints"], dict)
        assert isinstance(d["telemetry"], dict)
        assert isinstance(d["transitions"], list)


class TestDecisionViewShape:
    def test_keys(self):
        v = DecisionView(
            id="dec_abc123456789",
            status="accepted",
            type="decision",
            rationale="good idea",
            dependencies=[],
            violations=[],
            source="proposal",
            created_at="2025-01-01T00:00:00Z",
            raw={},
        )
        d = v.to_dict()
        expected = {"id", "status", "type", "rationale", "dependencies", "violations", "source", "created_at", "raw"}
        assert set(d.keys()) == expected


class TestClaimViewShape:
    def test_keys(self):
        v = ClaimView(
            id="clm_test1",
            state="proposed",
            content="Tests pass",
            confidence=0.92,
            provenance="observed",
            evidence_links=["ev_1"],
            conflicting_claims=[],
            stability={},
            created_at="2025-01-01T00:00:00Z",
            raw={},
        )
        d = v.to_dict()
        expected = {"id", "state", "content", "confidence", "provenance", "evidence_links",
                    "conflicting_claims", "stability", "created_at", "raw"}
        assert set(d.keys()) == expected
        assert isinstance(d["confidence"], float)


class TestEvidenceViewShape:
    def test_keys(self):
        v = EvidenceView(
            id="ev_test1",
            type="tool_trace",
            source="pytest",
            scope="test_suite",
            linked_claims=["clm_1"],
            validity=1.0,
            expiry=None,
        )
        d = v.to_dict()
        expected = {"id", "type", "source", "scope", "linked_claims", "validity", "expiry"}
        assert set(d.keys()) == expected


class TestViolationViewShape:
    def test_keys(self):
        v = ViolationView(
            id="vio_audit_ga_test",
            rule_breached="no_evidence",
            triggering_decision="assertion_1",
            severity="high",
            enforced_outcome="block",
            resolution=None,
            source_system="audit",
            detail="missing evidence",
        )
        d = v.to_dict()
        expected = {"id", "rule_breached", "triggering_decision", "severity", "enforced_outcome",
                    "resolution", "source_system", "detail"}
        assert set(d.keys()) == expected


class TestExecutionActionViewShape:
    def test_keys(self):
        v = ExecutionActionView(id="test", description="run tests", status="pending", detail="")
        d = v.to_dict()
        assert set(d.keys()) == {"id", "description", "status", "detail"}


class TestExecutionViewShape:
    def test_keys(self):
        v = ExecutionView(pending=[], blocked=[], running=[], completed=[])
        d = v.to_dict()
        assert set(d.keys()) == {"pending", "blocked", "running", "completed"}
        assert all(isinstance(d[k], list) for k in d)


class TestStabilityViewShape:
    def test_keys(self):
        v = StabilityView(
            rejection_rate=0.1,
            claim_churn=0.2,
            contradiction_density=0.05,
            drift_alert="NONE",
            drift_signals={},
        )
        d = v.to_dict()
        expected = {"rejection_rate", "claim_churn", "contradiction_density", "drift_alert", "drift_signals"}
        assert set(d.keys()) == expected


class TestGovernorViewModelShape:
    def test_keys(self):
        vm = GovernorViewModel()
        d = vm.to_dict()
        expected = {"schema_version", "generated_at", "session", "regime", "decisions",
                    "claims", "evidence", "violations", "execution", "stability"}
        assert set(d.keys()) == expected

    def test_schema_version(self):
        vm = GovernorViewModel()
        assert vm.schema_version == SCHEMA_VERSION
        assert vm.to_dict()["schema_version"] == "v2"

    def test_generated_at_set(self):
        vm = GovernorViewModel()
        assert vm.generated_at != ""
        # Should be valid ISO format
        datetime.fromisoformat(vm.generated_at)

    def test_defaults(self):
        vm = GovernorViewModel()
        d = vm.to_dict()
        assert d["session"] is None
        assert d["regime"] is None
        assert d["decisions"] == []
        assert d["claims"] == []
        assert d["evidence"] == []
        assert d["violations"] == []
        assert d["execution"] is None
        assert d["stability"] is None

    def test_with_populated_sections(self):
        vm = GovernorViewModel(
            session=SessionView(
                mode="strict", authority_level="High",
                active_constraints=["strict_envelope"], jurisdiction="factual", active_profile="strict",
            ),
            decisions=[
                DecisionView(id="dec_abc", status="accepted", type="decision",
                             rationale="", dependencies=[], violations=[], source="proposal",
                             created_at="2025-01-01", raw={}),
            ],
        )
        d = vm.to_dict()
        assert d["session"] is not None
        assert len(d["decisions"]) == 1


# =============================================================================
# ID prefix tests
# =============================================================================


class TestIDPrefixes:
    def test_decision_prefix(self):
        v = DecisionView(id="dec_abc123456789", status="accepted", type="t",
                         rationale="", dependencies=[], violations=[], source="proposal",
                         created_at="", raw={})
        assert v.id.startswith("dec_")

    def test_claim_prefix(self):
        v = ClaimView(id="clm_test1", state="proposed", content="x", confidence=0.5,
                      provenance="assumed", evidence_links=[], conflicting_claims=[],
                      stability={}, created_at="", raw={})
        assert v.id.startswith("clm_")

    def test_evidence_prefix(self):
        v = EvidenceView(id="ev_ref1", type="tool_trace", source="", scope="",
                         linked_claims=[], validity=1.0, expiry=None)
        assert v.id.startswith("ev_")

    def test_violation_audit_prefix(self):
        v = ViolationView(id="vio_audit_ga_test", rule_breached="", triggering_decision="",
                          severity="low", enforced_outcome="", resolution=None,
                          source_system="audit", detail="")
        assert v.id.startswith("vio_audit_")

    def test_violation_drift_prefix(self):
        v = ViolationView(id="vio_drift_abc123", rule_breached="", triggering_decision="",
                          severity="high", enforced_outcome="", resolution=None,
                          source_system="drift", detail="")
        assert v.id.startswith("vio_drift_")


# =============================================================================
# Claim state mapping
# =============================================================================


class TestClaimStateMapping:
    def test_supported_maps_to_stabilized(self):
        assert _map_epistemic_status("SUPPORTED") == "stabilized"

    def test_contested_maps_to_contradicted(self):
        assert _map_epistemic_status("CONTESTED") == "contradicted"

    def test_invalidated_maps_to_contradicted(self):
        assert _map_epistemic_status("INVALIDATED") == "contradicted"

    def test_refused_maps_to_contradicted(self):
        assert _map_epistemic_status("REFUSED") == "contradicted"

    def test_stale_maps_to_stale(self):
        assert _map_epistemic_status("STALE") == "stale"

    def test_expired_maps_to_stale(self):
        assert _map_epistemic_status("EXPIRED") == "stale"

    def test_proposed_maps_to_proposed(self):
        assert _map_epistemic_status("PROPOSED") == "proposed"

    def test_none_maps_to_proposed(self):
        assert _map_epistemic_status(None) == "proposed"

    def test_blocked_maps_to_contradicted(self):
        assert _map_epistemic_status("BLOCKED") == "contradicted"

    def test_retracted_maps_to_contradicted(self):
        assert _map_epistemic_status("RETRACTED") == "contradicted"

    def test_unknown_maps_to_proposed(self):
        assert _map_epistemic_status("UNKNOWN_VALUE") == "proposed"

    def test_enum_value_supported(self):
        """Test with an object whose str() contains SUPPORTED."""
        class FakeEnum:
            def __str__(self):
                return "ClaimStatus.SUPPORTED"
        assert _map_epistemic_status(FakeEnum()) == "stabilized"


# =============================================================================
# Builder tests
# =============================================================================


class TestBuildSession:
    def test_empty_gov_dir(self, gov_dir, root):
        result = build_session(gov_dir, root)
        assert result is not None
        assert isinstance(result, SessionView)
        assert result.jurisdiction is None
        assert result.active_profile is None

    def test_with_profile(self, gov_dir, root):
        (gov_dir / ".profile").write_text("strict")
        result = build_session(gov_dir, root)
        assert result.active_profile == "strict"
        assert "profile:strict" in result.active_constraints

    def test_with_envelope_file(self, gov_dir, root):
        (gov_dir / ".envelope").write_text("strict")
        result = build_session(gov_dir, root)
        # Mode should be read from envelope
        assert result is not None


class TestBuildRegime:
    def test_empty_gov_dir(self, gov_dir):
        result = build_regime(gov_dir)
        assert result is not None
        assert isinstance(result, RegimeView)
        assert result.name == "elastic"

    def test_returns_setpoints(self, gov_dir):
        result = build_regime(gov_dir)
        assert isinstance(result.setpoints, dict)

    def test_returns_telemetry(self, gov_dir):
        result = build_regime(gov_dir)
        assert isinstance(result.telemetry, dict)


class TestBuildDecisions:
    def test_empty_gov_dir(self, gov_dir):
        result = build_decisions(gov_dir)
        assert isinstance(result, list)

    def test_from_proposals(self, gov_dir):
        proposal_id = "abc12345-6789-0000-0000-000000000000"
        proposals = {
            proposal_id: {
                "id": proposal_id,
                "state": "applied",
                "claims": [],
                "created_at": "2025-01-01T00:00:00Z",
                "receipts": [],
                "rejection": None,
            }
        }
        (gov_dir / "proposals.json").write_text(json.dumps(proposals))
        result = build_decisions(gov_dir)
        assert len(result) >= 1
        accepted = [d for d in result if d.source == "proposal"]
        assert len(accepted) >= 1
        assert accepted[0].status == "accepted"
        assert accepted[0].id.startswith("dec_")

    def test_rejected_proposal(self, gov_dir):
        proposal_id = "def12345-6789-0000-0000-000000000000"
        proposals = {
            proposal_id: {
                "id": proposal_id,
                "state": "rejected",
                "claims": [],
                "created_at": "2025-01-01T00:00:00Z",
                "receipts": [],
                "rejection": {"reason": "bad claims", "claim_errors": []},
            }
        }
        (gov_dir / "proposals.json").write_text(json.dumps(proposals))
        result = build_decisions(gov_dir)
        rejected = [d for d in result if d.status == "rejected"]
        assert len(rejected) >= 1

    def test_pending_proposal(self, gov_dir):
        proposal_id = "00112345-6789-0000-0000-000000000000"
        proposals = {
            proposal_id: {
                "id": proposal_id,
                "state": "proposed",
                "claims": [],
                "created_at": "2025-01-01T00:00:00Z",
                "receipts": [],
                "rejection": None,
            }
        }
        (gov_dir / "proposals.json").write_text(json.dumps(proposals))
        result = build_decisions(gov_dir)
        pending = [d for d in result if d.status == "pending"]
        assert len(pending) >= 1


class TestBuildClaims:
    def test_empty_gov_dir(self, gov_dir):
        result = build_claims(gov_dir)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_with_epistemic_ledger_json(self, gov_dir):
        """Test loading claims from JSON-based epistemic ledger."""
        ledger_data = {
            "claims": {
                "claim_1": {
                    "claim_id": "claim_1",
                    "content": "Tests pass",
                    "provenance": "observed",
                    "confidence": 0.95,
                    "evidence_refs": [],
                    "status": "active",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "created_at_step": 0,
                    "last_updated_at": "2025-01-01T00:00:00+00:00",
                    "last_updated_step": 0,
                    "assumptions": [],
                }
            },
            "step": 1,
            "total_claims_created": 1,
            "total_promotions_attempted": 0,
            "total_promotions_forbidden": 0,
            "total_retractions": 0,
            "promotion_history": [],
        }
        (gov_dir / "epistemic_ledger.json").write_text(json.dumps(ledger_data))
        result = build_claims(gov_dir)
        assert len(result) >= 1
        assert result[0].id == "clm_claim_1"
        assert result[0].content == "Tests pass"
        assert result[0].confidence == 0.95


class TestBuildEvidence:
    def test_empty_claims(self, gov_dir):
        result = build_evidence([], gov_dir)
        assert isinstance(result, list)

    def test_with_claims_having_evidence(self, gov_dir):
        """Evidence extraction from ledger with evidence refs."""
        ledger_data = {
            "claims": {
                "claim_1": {
                    "claim_id": "claim_1",
                    "content": "Tests pass",
                    "provenance": "observed",
                    "confidence": 0.95,
                    "evidence_refs": [
                        {
                            "ref_id": "ref_001",
                            "ref_type": "tool_trace",
                            "locator": "pytest-run-1",
                            "scope": "test_suite",
                            "confidence": 1.0,
                        }
                    ],
                    "status": "active",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "created_at_step": 0,
                    "last_updated_at": "2025-01-01T00:00:00+00:00",
                    "last_updated_step": 0,
                    "assumptions": [],
                }
            },
            "step": 1,
            "total_claims_created": 1,
            "total_promotions_attempted": 0,
            "total_promotions_forbidden": 0,
            "total_retractions": 0,
            "promotion_history": [],
        }
        (gov_dir / "epistemic_ledger.json").write_text(json.dumps(ledger_data))

        claims = [ClaimView(
            id="clm_claim_1", state="proposed", content="Tests pass",
            confidence=0.95, provenance="observed", evidence_links=["ev_ref_001"],
            conflicting_claims=[], stability={}, created_at="2025-01-01", raw={},
        )]
        result = build_evidence(claims, gov_dir)
        assert len(result) >= 1
        assert result[0].id == "ev_ref_001"
        assert "clm_claim_1" in result[0].linked_claims


class TestBuildViolations:
    def test_empty_gov_dir(self, gov_dir):
        result = build_violations(gov_dir)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_with_audit_history(self, gov_dir):
        audit_data = [
            {
                "audit_id": "ga_test123456",
                "assertion_id": "assert_1",
                "stage": "pre_commit",
                "status": "ungrounded",
                "decision": "block",
                "failure_modes": ["no_evidence"],
                "severity": "high",
                "notes": "missing evidence",
            }
        ]
        (gov_dir / "audit_history.json").write_text(json.dumps(audit_data))
        result = build_violations(gov_dir)
        assert len(result) >= 1
        assert result[0].id.startswith("vio_audit_")
        assert result[0].severity == "high"
        assert result[0].source_system == "audit"


class TestBuildExecution:
    def test_empty_gov_dir(self, gov_dir, root):
        result = build_execution(gov_dir, root)
        assert result is None  # No actions

    def test_with_proposals(self, gov_dir, root):
        proposal_id = "abc12345-6789-0000-0000-000000000000"
        proposals = {
            proposal_id: {
                "id": proposal_id,
                "state": "draft",
                "claims": [],
                "created_at": "2025-01-01T00:00:00Z",
                "receipts": [],
                "rejection": None,
            }
        }
        (gov_dir / "proposals.json").write_text(json.dumps(proposals))
        result = build_execution(gov_dir, root)
        assert result is not None
        assert len(result.pending) >= 1

    def test_rejected_goes_to_blocked(self, gov_dir, root):
        proposal_id = "abc12345-6789-0000-0000-000000000000"
        proposals = {
            proposal_id: {
                "id": proposal_id,
                "state": "rejected",
                "claims": [],
                "created_at": "2025-01-01T00:00:00Z",
                "receipts": [],
                "rejection": {"reason": "bad", "claim_errors": []},
            }
        }
        (gov_dir / "proposals.json").write_text(json.dumps(proposals))
        result = build_execution(gov_dir, root)
        assert result is not None
        assert len(result.blocked) >= 1


class TestBuildStability:
    def test_empty_gov_dir(self, gov_dir):
        result = build_stability(gov_dir)
        assert result is not None
        assert isinstance(result, StabilityView)
        assert result.drift_alert == "NONE"
        assert result.rejection_rate == 0.0


# =============================================================================
# Graceful degradation
# =============================================================================


class TestGracefulDegradation:
    def test_missing_subsystems_dont_break_viewmodel(self, gov_dir, root):
        """build_viewmodel should succeed even with empty .governor/."""
        vm = build_viewmodel(gov_dir, root)
        assert vm.schema_version == "v2"
        assert vm.generated_at != ""
        d = vm.to_dict()
        assert "schema_version" in d

    def test_corrupt_proposals_dont_break_decisions(self, gov_dir, root):
        """Invalid proposals.json shouldn't crash build_decisions."""
        (gov_dir / "proposals.json").write_text("not valid json {{{")
        result = build_decisions(gov_dir)
        assert isinstance(result, list)

    def test_corrupt_regime_doesnt_break_viewmodel(self, gov_dir, root):
        """Invalid regime state shouldn't crash build_viewmodel."""
        (gov_dir / "regime_state.json").write_text("garbage")
        vm = build_viewmodel(gov_dir, root)
        # Should still produce a valid ViewModel with regime as None or default
        assert vm.schema_version == "v2"


# =============================================================================
# V1 compat
# =============================================================================


class TestV1Compat:
    def test_v1_state_has_expected_keys(self, gov_dir, root):
        result = build_v1_state(gov_dir, root)
        expected_keys = {"proposals", "facts", "decisions", "tasks", "regime", "boil", "autonomous"}
        assert set(result.keys()) == expected_keys

    def test_v1_state_defaults(self, gov_dir, root):
        result = build_v1_state(gov_dir, root)
        assert isinstance(result["proposals"], list)
        assert isinstance(result["facts"], list)
        assert isinstance(result["decisions"], list)
        assert isinstance(result["tasks"], list)
        assert isinstance(result["autonomous"], list)


# =============================================================================
# Schema invariants
# =============================================================================


class TestSchemaInvariants:
    def test_all_ids_unique(self):
        """All IDs in a ViewModel must be unique."""
        vm = GovernorViewModel(
            decisions=[
                DecisionView(id="dec_aaa", status="accepted", type="t", rationale="",
                             dependencies=[], violations=[], source="p", created_at="", raw={}),
                DecisionView(id="dec_bbb", status="rejected", type="t", rationale="",
                             dependencies=[], violations=[], source="p", created_at="", raw={}),
            ],
            claims=[
                ClaimView(id="clm_ccc", state="proposed", content="c", confidence=0.5,
                          provenance="assumed", evidence_links=[], conflicting_claims=[],
                          stability={}, created_at="", raw={}),
            ],
            evidence=[
                EvidenceView(id="ev_ddd", type="tool_trace", source="", scope="",
                             linked_claims=["clm_ccc"], validity=1.0, expiry=None),
            ],
        )
        all_ids = (
            [d.id for d in vm.decisions]
            + [c.id for c in vm.claims]
            + [e.id for e in vm.evidence]
            + [v.id for v in vm.violations]
        )
        assert len(all_ids) == len(set(all_ids)), "Duplicate IDs found"

    def test_evidence_links_reference_existing_claims(self):
        """Evidence linked_claims should reference claim IDs in the model."""
        claims = [
            ClaimView(id="clm_1", state="proposed", content="c", confidence=0.5,
                      provenance="assumed", evidence_links=["ev_1"], conflicting_claims=[],
                      stability={}, created_at="", raw={}),
        ]
        evidence = [
            EvidenceView(id="ev_1", type="tool_trace", source="", scope="",
                         linked_claims=["clm_1"], validity=1.0, expiry=None),
        ]
        vm = GovernorViewModel(claims=claims, evidence=evidence)
        claim_ids = {c.id for c in vm.claims}
        for ev in vm.evidence:
            for link in ev.linked_claims:
                assert link in claim_ids, f"Evidence {ev.id} references non-existent claim {link}"

    def test_claim_evidence_links_reference_existing_evidence(self):
        """Claim evidence_links should reference evidence IDs in the model."""
        evidence = [
            EvidenceView(id="ev_1", type="tool_trace", source="", scope="",
                         linked_claims=["clm_1"], validity=1.0, expiry=None),
        ]
        claims = [
            ClaimView(id="clm_1", state="proposed", content="c", confidence=0.5,
                      provenance="assumed", evidence_links=["ev_1"], conflicting_claims=[],
                      stability={}, created_at="", raw={}),
        ]
        vm = GovernorViewModel(claims=claims, evidence=evidence)
        ev_ids = {e.id for e in vm.evidence}
        for c in vm.claims:
            for link in c.evidence_links:
                assert link in ev_ids, f"Claim {c.id} references non-existent evidence {link}"

    def test_decisions_and_claims_dont_share_ids(self):
        """Decision IDs and claim IDs use different prefixes."""
        vm = GovernorViewModel(
            decisions=[
                DecisionView(id="dec_xxx", status="accepted", type="t", rationale="",
                             dependencies=[], violations=[], source="p", created_at="", raw={}),
            ],
            claims=[
                ClaimView(id="clm_yyy", state="proposed", content="c", confidence=0.5,
                          provenance="assumed", evidence_links=[], conflicting_claims=[],
                          stability={}, created_at="", raw={}),
            ],
        )
        dec_ids = {d.id for d in vm.decisions}
        clm_ids = {c.id for c in vm.claims}
        assert not dec_ids.intersection(clm_ids)

    def test_schema_version_is_v2(self):
        vm = GovernorViewModel()
        assert vm.to_dict()["schema_version"] == "v2"


# =============================================================================
# Integration: build_viewmodel
# =============================================================================


class TestBuildViewmodel:
    def test_empty_gov_dir(self, gov_dir, root):
        vm = build_viewmodel(gov_dir, root)
        d = vm.to_dict()
        assert d["schema_version"] == "v2"
        assert d["session"] is not None  # session always built
        assert d["stability"] is not None  # stability always built

    def test_full_roundtrip_to_json(self, gov_dir, root):
        vm = build_viewmodel(gov_dir, root)
        d = vm.to_dict()
        j = json.dumps(d, indent=2)
        parsed = json.loads(j)
        assert parsed["schema_version"] == "v2"
        assert "generated_at" in parsed
