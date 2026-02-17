# SPDX-License-Identifier: Apache-2.0
"""
Tests for docket management and adjudicator UX.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governor.docket import (
    CaseType,
    CaseStatus,
    RulingType,
    DocketCase,
    PrecedentRecord,
    DocketManager,
    create_docket_manager,
    ExceptionRecordAlias,
)
from governor.staleness import StalenessDetector, ClaimFreshness, StalenessConfig
from governor.epistemic import EpistemicLedger, Provenance


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    def test_case_type_values(self):
        assert CaseType.CONTESTED.value == "contested"
        assert CaseType.STALE.value == "stale"

    def test_case_status_values(self):
        assert CaseStatus.PENDING.value == "pending"
        assert CaseStatus.RULED.value == "ruled"

    def test_ruling_type_values(self):
        assert RulingType.SUSTAIN.value == "sustain"
        assert RulingType.AMEND.value == "amend"
        assert RulingType.GRANT_EXCEPTION.value == "grant_exception"
        assert RulingType.REVERIFY.value == "reverify"
        assert RulingType.DISMISS.value == "dismiss"


# =============================================================================
# DocketCase Tests
# =============================================================================


class TestDocketCase:
    def test_to_dict(self):
        now = datetime.now(timezone.utc)
        case = DocketCase(
            case_number=1,
            case_type=CaseType.CONTESTED,
            claim_id="gc_test123",
            anchor_id="anchor_1",
            status=CaseStatus.PENDING,
            description="Test case",
            evidence=[{"description": "Evidence 1"}],
            created_at=now,
            blocked_content="blocked response",
        )
        data = case.to_dict()

        assert data["case_number"] == 1
        assert data["case_type"] == "contested"
        assert data["claim_id"] == "gc_test123"
        assert data["anchor_id"] == "anchor_1"
        assert data["status"] == "pending"
        assert data["description"] == "Test case"
        assert data["blocked_content"] == "blocked response"

    def test_from_dict(self):
        data = {
            "case_number": 2,
            "case_type": "stale",
            "claim_id": "gc_stale",
            "anchor_id": None,
            "status": "pending",
            "description": "Stale claim",
            "evidence": [],
            "created_at": "2024-01-01T12:00:00+00:00",
        }
        case = DocketCase.from_dict(data)

        assert case.case_number == 2
        assert case.case_type == CaseType.STALE
        assert case.claim_id == "gc_stale"
        assert case.status == CaseStatus.PENDING

    def test_roundtrip(self):
        original = DocketCase(
            case_number=3,
            case_type=CaseType.CONTESTED,
            claim_id="gc_rt",
            anchor_id="anchor_2",
            status=CaseStatus.PENDING,
            description="Roundtrip test",
            evidence=[{"desc": "e1"}],
            created_at=datetime.now(timezone.utc),
            freshness_info={"confidence": 0.3},
        )
        data = original.to_dict()
        restored = DocketCase.from_dict(data)

        assert restored.case_number == original.case_number
        assert restored.case_type == original.case_type
        assert restored.claim_id == original.claim_id
        assert restored.description == original.description


# =============================================================================
# PrecedentRecord Tests
# =============================================================================


class TestPrecedentRecord:
    def test_to_dict(self):
        now = datetime.now(timezone.utc)
        precedent = PrecedentRecord(
            id="prec_test",
            case_number=1,
            ruling=RulingType.SUSTAIN,
            claim_id="gc_claim",
            anchor_id="anchor_1",
            scope="single_instance",
            rationale="Test rationale",
            created_at=now,
            expiry=None,
        )
        data = precedent.to_dict()

        assert data["id"] == "prec_test"
        assert data["case_number"] == 1
        assert data["ruling"] == "sustain"
        assert data["claim_id"] == "gc_claim"
        assert data["scope"] == "single_instance"
        assert data["rationale"] == "Test rationale"
        assert data["expiry"] is None

    def test_from_dict(self):
        data = {
            "id": "prec_test2",
            "case_number": 2,
            "ruling": "amend",
            "claim_id": "gc_claim2",
            "anchor_id": "anchor_2",
            "scope": "project",
            "rationale": "Amended",
            "created_at": "2024-01-01T12:00:00+00:00",
            "expiry": "2024-02-01T12:00:00+00:00",
        }
        precedent = PrecedentRecord.from_dict(data)

        assert precedent.id == "prec_test2"
        assert precedent.ruling == RulingType.AMEND
        assert precedent.scope == "project"
        assert precedent.expiry is not None

    def test_exception_alias(self):
        # ExceptionRecordAlias should be same as PrecedentRecord
        assert ExceptionRecordAlias is PrecedentRecord


# =============================================================================
# DocketManager Tests
# =============================================================================


class TestDocketManager:
    @pytest.fixture
    def tmp_gov_dir(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        return gov_dir

    @pytest.fixture
    def ledger(self):
        return EpistemicLedger()

    @pytest.fixture
    def staleness(self, ledger):
        return StalenessDetector(ledger)

    @pytest.fixture
    def docket(self, staleness, tmp_gov_dir):
        return DocketManager(staleness=staleness, governor_dir=tmp_gov_dir)

    def test_get_docket_empty(self, docket):
        cases = docket.get_docket()
        assert cases == []

    def test_create_case(self, docket):
        case = docket.create_case(
            case_type=CaseType.CONTESTED,
            claim_id="gc_test",
            description="Test contested case",
            anchor_id="anchor_1",
        )

        assert case.case_number == 1
        assert case.case_type == CaseType.CONTESTED
        assert case.claim_id == "gc_test"
        assert case.status == CaseStatus.PENDING

    def test_get_case(self, docket):
        case = docket.create_case(
            case_type=CaseType.STALE,
            claim_id="gc_stale",
            description="Stale case",
        )

        retrieved = docket.get_case(case.case_number)

        assert retrieved is not None
        assert retrieved.case_number == case.case_number
        assert retrieved.claim_id == "gc_stale"

    def test_get_case_not_found(self, docket):
        case = docket.get_case(999)
        assert case is None

    def test_case_numbers_auto_increment(self, docket):
        case1 = docket.create_case(CaseType.CONTESTED, "gc_1", "Case 1")
        case2 = docket.create_case(CaseType.STALE, "gc_2", "Case 2")
        case3 = docket.create_case(CaseType.CONTESTED, "gc_3", "Case 3")

        assert case1.case_number == 1
        assert case2.case_number == 2
        assert case3.case_number == 3


# =============================================================================
# Ruling Tests - CONTESTED
# =============================================================================


class TestContestedRulings:
    @pytest.fixture
    def docket_with_contested(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        ledger = EpistemicLedger()
        staleness = StalenessDetector(ledger)
        docket = DocketManager(staleness=staleness, governor_dir=gov_dir)

        case = docket.create_case(
            case_type=CaseType.CONTESTED,
            claim_id="gc_contested",
            description="Contested claim",
            anchor_id="anchor_1",
        )
        return docket, case.case_number

    def test_rule_sustain(self, docket_with_contested):
        docket, case_num = docket_with_contested

        precedent = docket.rule_sustain(case_num, "Upheld constraint")

        assert precedent.ruling == RulingType.SUSTAIN
        assert precedent.rationale == "Upheld constraint"
        assert precedent.case_number == case_num

        # Case should be marked as ruled
        case = docket.get_case(case_num)
        assert case.status == CaseStatus.RULED

    def test_rule_amend(self, docket_with_contested):
        docket, case_num = docket_with_contested

        precedent = docket.rule_amend(case_num, "Anchor updated")

        assert precedent.ruling == RulingType.AMEND
        assert precedent.rationale == "Anchor updated"

    def test_rule_grant_exception(self, docket_with_contested):
        docket, case_num = docket_with_contested

        precedent = docket.rule_grant_exception(
            case_num, scope="session", rationale="Intentional deviation"
        )

        assert precedent.ruling == RulingType.GRANT_EXCEPTION
        assert precedent.scope == "session"
        assert precedent.rationale == "Intentional deviation"

    def test_rule_contested_wrong_type(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        # Create STALE case
        case = docket.create_case(
            case_type=CaseType.STALE,
            claim_id="gc_stale",
            description="Stale case",
        )

        # Try to use contested ruling
        with pytest.raises(ValueError, match="not a contested case"):
            docket.rule_sustain(case.case_number)

    def test_rule_already_ruled(self, docket_with_contested):
        docket, case_num = docket_with_contested

        # First ruling
        docket.rule_sustain(case_num)

        # Second ruling should fail
        with pytest.raises(ValueError, match="already been ruled"):
            docket.rule_amend(case_num)


# =============================================================================
# Ruling Tests - STALE
# =============================================================================


class TestStaleRulings:
    @pytest.fixture
    def docket_with_stale(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        case = docket.create_case(
            case_type=CaseType.STALE,
            claim_id="gc_stale",
            description="Stale claim",
        )
        return docket, case.case_number

    def test_rule_reverify(self, docket_with_stale):
        docket, case_num = docket_with_stale

        precedent = docket.rule_reverify(case_num, "Needs re-check")

        assert precedent.ruling == RulingType.REVERIFY
        assert precedent.rationale == "Needs re-check"

    def test_rule_dismiss(self, docket_with_stale):
        docket, case_num = docket_with_stale

        precedent = docket.rule_dismiss(case_num, "Accept current state")

        assert precedent.ruling == RulingType.DISMISS
        assert precedent.rationale == "Accept current state"

    def test_rule_stale_wrong_type(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        # Create CONTESTED case
        case = docket.create_case(
            case_type=CaseType.CONTESTED,
            claim_id="gc_contested",
            description="Contested case",
            anchor_id="anchor_1",
        )

        # Try to use stale ruling
        with pytest.raises(ValueError, match="not a stale case"):
            docket.rule_reverify(case.case_number)


# =============================================================================
# Precedent Management Tests
# =============================================================================


class TestPrecedentManagement:
    @pytest.fixture
    def docket_with_precedents(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        # Create and rule on multiple cases
        case1 = docket.create_case(CaseType.CONTESTED, "gc_1", "Case 1", "anchor_1")
        docket.rule_sustain(case1.case_number, "Sustained case 1")

        case2 = docket.create_case(CaseType.STALE, "gc_2", "Case 2")
        docket.rule_dismiss(case2.case_number, "Dismissed case 2")

        case3 = docket.create_case(CaseType.CONTESTED, "gc_3", "Case 3", "anchor_2")
        docket.rule_amend(case3.case_number, "Amended anchor_2")

        return docket

    def test_get_precedents(self, docket_with_precedents):
        precedents = docket_with_precedents.get_precedents()

        assert len(precedents) == 3

    def test_search_precedents_by_claim(self, docket_with_precedents):
        results = docket_with_precedents.search_precedents("gc_1")

        assert len(results) == 1
        assert results[0].claim_id == "gc_1"

    def test_search_precedents_by_anchor(self, docket_with_precedents):
        results = docket_with_precedents.search_precedents("anchor_2")

        assert len(results) == 1
        assert results[0].anchor_id == "anchor_2"

    def test_search_precedents_by_rationale(self, docket_with_precedents):
        results = docket_with_precedents.search_precedents("Dismissed")

        assert len(results) == 1
        assert "Dismissed" in results[0].rationale

    def test_search_precedents_no_match(self, docket_with_precedents):
        results = docket_with_precedents.search_precedents("nonexistent")

        assert len(results) == 0


# =============================================================================
# Format Tests
# =============================================================================


class TestFormatting:
    @pytest.fixture
    def contested_case(self):
        return DocketCase(
            case_number=4721,
            case_type=CaseType.CONTESTED,
            claim_id="gc_contested_test",
            anchor_id="elena-eyes",
            status=CaseStatus.PENDING,
            description="Contested claim",
            evidence=[
                {"description": "Line 42: Elena's blue eyes glistened"},
                {"description": "Violates: forbidden_pattern match"},
            ],
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def stale_case(self):
        return DocketCase(
            case_number=1234,
            case_type=CaseType.STALE,
            claim_id="gc_stale_test",
            anchor_id=None,
            status=CaseStatus.PENDING,
            description="Confidence decayed",
            evidence=[],
            created_at=datetime.now(timezone.utc),
        )

    def test_format_full_contested(self, contested_case, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        output = docket.format_case(contested_case, style="full")

        assert "DOCKET #4721" in output
        assert "elena-eyes" in output.lower() or "ANCHOR" in output
        assert "Contested" in output
        assert "[S] Sustain" in output
        assert "[A] Amend" in output
        assert "[G] Grant" in output

    def test_format_full_stale(self, stale_case, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        output = docket.format_case(stale_case, style="full")

        assert "DOCKET #1234" in output
        assert "Stale" in output
        assert "[R] Reverify" in output
        assert "[D] Dismiss" in output

    def test_format_compact(self, contested_case, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        output = docket.format_case(contested_case, style="compact")

        assert "#4721" in output
        assert "CONTESTED" in output
        assert "gc_contested_test" in output

    def test_format_legacy(self, contested_case, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        docket = DocketManager(governor_dir=gov_dir)

        output = docket.format_case(contested_case, style="legacy")

        assert "Case #4721" in output
        assert "contested" in output


# =============================================================================
# Persistence Tests
# =============================================================================


class TestPersistence:
    def test_save_and_load_cases(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create docket and add cases
        docket1 = DocketManager(governor_dir=gov_dir)
        case = docket1.create_case(CaseType.CONTESTED, "gc_persist", "Persist test")

        # Create new docket instance and verify cases loaded
        docket2 = DocketManager(governor_dir=gov_dir)
        loaded_case = docket2.get_case(case.case_number)

        assert loaded_case is not None
        assert loaded_case.claim_id == "gc_persist"

    def test_save_and_load_precedents(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create docket, add case, and rule
        docket1 = DocketManager(governor_dir=gov_dir)
        case = docket1.create_case(CaseType.CONTESTED, "gc_prec", "Precedent test", "anchor")
        docket1.rule_sustain(case.case_number, "Test rationale")

        # Create new docket instance and verify precedent loaded
        docket2 = DocketManager(governor_dir=gov_dir)
        precedents = docket2.get_precedents()

        assert len(precedents) == 1
        assert precedents[0].rationale == "Test rationale"

    def test_case_number_persists(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create docket and add cases
        docket1 = DocketManager(governor_dir=gov_dir)
        docket1.create_case(CaseType.CONTESTED, "gc_1", "Case 1")
        docket1.create_case(CaseType.CONTESTED, "gc_2", "Case 2")

        # Create new docket instance and add another case
        docket2 = DocketManager(governor_dir=gov_dir)
        case3 = docket2.create_case(CaseType.CONTESTED, "gc_3", "Case 3")

        # Should continue from 3, not restart from 1
        assert case3.case_number == 3


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions:
    def test_create_docket_manager(self):
        docket = create_docket_manager()
        assert isinstance(docket, DocketManager)

    def test_create_docket_manager_with_staleness(self):
        ledger = EpistemicLedger()
        staleness = StalenessDetector(ledger)
        docket = create_docket_manager(staleness=staleness)

        assert docket.staleness is staleness

    def test_create_docket_manager_with_governor_dir(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        docket = create_docket_manager(governor_dir=gov_dir)

        assert docket.governor_dir == gov_dir
