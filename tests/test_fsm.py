# SPDX-License-Identifier: Apache-2.0
"""Tests for the proposal state machine."""

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from governor.claims import file_exists, decision, claim_tests_pass
from governor.receipts import FileSnapshot, CmdRun
from governor.fsm import (
    ProposalState,
    TransitionError,
    RejectionInfo,
    Proposal,
    ProposalFSM,
    create_proposal,
)


class TestProposalState:
    """Test ProposalState enum."""

    def test_all_states_exist(self):
        """All expected states are defined."""
        assert ProposalState.DRAFT.value == "draft"
        assert ProposalState.PROPOSED.value == "proposed"
        assert ProposalState.VERIFIED.value == "verified"
        assert ProposalState.APPLIED.value == "applied"
        assert ProposalState.REJECTED.value == "rejected"


class TestRejectionInfo:
    """Test RejectionInfo dataclass."""

    def test_create_basic(self):
        """Can create with just a reason."""
        info = RejectionInfo(reason="Tests failed")
        assert info.reason == "Tests failed"
        assert info.missing_receipts == []

    def test_create_with_details(self):
        """Can create with all fields."""
        conflict_id = uuid4()
        info = RejectionInfo(
            reason="Multiple issues",
            missing_receipts=["file_snapshot", "cmd_run"],
            conflicting_decisions=[conflict_id],
            failed_claims=[0, 2],
            details={"exit_code": 1},
        )

        assert len(info.missing_receipts) == 2
        assert conflict_id in info.conflicting_decisions
        assert info.failed_claims == [0, 2]
        assert info.details["exit_code"] == 1

    def test_serialization(self):
        """RejectionInfo survives round-trip."""
        original = RejectionInfo(
            reason="Test failure",
            missing_receipts=["file_snapshot"],
            conflicting_decisions=[uuid4()],
            failed_claims=[1],
        )

        data = original.to_dict()
        restored = RejectionInfo.from_dict(data)

        assert restored.reason == original.reason
        assert restored.missing_receipts == original.missing_receipts
        assert restored.failed_claims == original.failed_claims


class TestProposal:
    """Test Proposal dataclass."""

    def test_create_proposal(self):
        """Can create a proposal."""
        claims = [file_exists("test.py")]
        proposal = Proposal(
            id=uuid4(),
            claims=claims,
            state=ProposalState.DRAFT,
            created_at=datetime.now(timezone.utc),
        )

        assert proposal.state == ProposalState.DRAFT
        assert len(proposal.claims) == 1

    def test_serialization(self):
        """Proposal survives JSON round-trip."""
        receipt = FileSnapshot(
            path="test.py",
            blob_hash="abc",
            size_bytes=100,
            timestamp=datetime.now(timezone.utc),
        )

        original = Proposal(
            id=uuid4(),
            claims=[file_exists("test.py")],
            state=ProposalState.VERIFIED,
            created_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            receipts=[receipt],
            patch_path="changes.patch",
        )

        json_str = json.dumps(original.to_dict())
        restored = Proposal.from_dict(json.loads(json_str))

        assert restored.id == original.id
        assert restored.state == ProposalState.VERIFIED
        assert len(restored.receipts) == 1
        assert restored.patch_path == "changes.patch"

    def test_serialization_with_rejection(self):
        """Rejected proposal serializes correctly."""
        original = Proposal(
            id=uuid4(),
            claims=[file_exists("test.py")],
            state=ProposalState.REJECTED,
            created_at=datetime.now(timezone.utc),
            rejection=RejectionInfo(reason="File not found"),
        )

        data = original.to_dict()
        restored = Proposal.from_dict(data)

        assert restored.rejection is not None
        assert restored.rejection.reason == "File not found"


class TestProposalFSM:
    """Test the ProposalFSM state machine."""

    @pytest.fixture
    def sample_claims(self):
        """Sample claims for testing."""
        return [file_exists("src/main.py")]

    @pytest.fixture
    def sample_receipt(self):
        """Sample receipt for testing."""
        return FileSnapshot(
            path="src/main.py",
            blob_hash="abc123",
            size_bytes=100,
            timestamp=datetime.now(timezone.utc),
        )

    def test_create_starts_in_draft(self, sample_claims):
        """New proposal starts in DRAFT state."""
        fsm = ProposalFSM.create(sample_claims)

        assert fsm.state == ProposalState.DRAFT
        assert fsm.proposal.id is not None

    def test_create_with_patch_path(self, sample_claims):
        """Can create with patch path."""
        fsm = ProposalFSM.create(sample_claims, patch_path="fix.patch")

        assert fsm.proposal.patch_path == "fix.patch"

    # Happy path: DRAFT → PROPOSED → VERIFIED → APPLIED

    def test_draft_to_proposed(self, sample_claims):
        """Can transition from DRAFT to PROPOSED."""
        fsm = ProposalFSM.create(sample_claims)

        fsm.propose()

        assert fsm.state == ProposalState.PROPOSED

    def test_proposed_to_verified(self, sample_claims, sample_receipt):
        """Can transition from PROPOSED to VERIFIED."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()

        fsm.verify([sample_receipt])

        assert fsm.state == ProposalState.VERIFIED
        assert len(fsm.proposal.receipts) == 1

    def test_verified_to_applied(self, sample_claims, sample_receipt):
        """Can transition from VERIFIED to APPLIED."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()
        fsm.verify([sample_receipt])

        fsm.apply()

        assert fsm.state == ProposalState.APPLIED
        assert fsm.proposal.applied_at is not None

    def test_full_happy_path(self, sample_claims, sample_receipt):
        """Complete flow from DRAFT to APPLIED."""
        fsm = ProposalFSM.create(sample_claims)

        assert fsm.state == ProposalState.DRAFT
        fsm.propose()

        assert fsm.state == ProposalState.PROPOSED
        fsm.verify([sample_receipt])

        assert fsm.state == ProposalState.VERIFIED
        fsm.apply()

        assert fsm.state == ProposalState.APPLIED
        assert fsm.is_terminal

    # Invalid transitions

    def test_cannot_verify_from_draft(self, sample_claims, sample_receipt):
        """Cannot transition directly from DRAFT to VERIFIED."""
        fsm = ProposalFSM.create(sample_claims)

        with pytest.raises(TransitionError) as exc_info:
            fsm.verify([sample_receipt])

        assert exc_info.value.from_state == ProposalState.DRAFT
        assert exc_info.value.to_state == ProposalState.VERIFIED

    def test_cannot_apply_from_proposed(self, sample_claims):
        """Cannot transition directly from PROPOSED to APPLIED."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()

        with pytest.raises(TransitionError):
            fsm.apply()

    def test_cannot_apply_from_draft(self, sample_claims):
        """Cannot transition directly from DRAFT to APPLIED."""
        fsm = ProposalFSM.create(sample_claims)

        with pytest.raises(TransitionError):
            fsm.apply()

    def test_cannot_propose_empty_claims(self):
        """Cannot propose with no claims."""
        fsm = ProposalFSM.create([])

        with pytest.raises(TransitionError, match="no claims"):
            fsm.propose()

    def test_cannot_verify_without_receipts(self, sample_claims):
        """Cannot verify without receipts."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()

        with pytest.raises(TransitionError, match="without receipts"):
            fsm.verify([])

    # Rejection paths

    def test_reject_from_draft(self, sample_claims):
        """Can reject from DRAFT."""
        fsm = ProposalFSM.create(sample_claims)

        fsm.reject(RejectionInfo(reason="Invalid claims"))

        assert fsm.state == ProposalState.REJECTED
        assert fsm.proposal.rejection is not None

    def test_reject_from_proposed(self, sample_claims):
        """Can reject from PROPOSED."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()

        fsm.reject(RejectionInfo(
            reason="Verification failed",
            failed_claims=[0],
        ))

        assert fsm.state == ProposalState.REJECTED
        assert fsm.proposal.rejection.failed_claims == [0]

    def test_reject_from_verified(self, sample_claims, sample_receipt):
        """Can reject from VERIFIED (e.g., conflict on apply)."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()
        fsm.verify([sample_receipt])

        conflict_id = uuid4()
        fsm.reject(RejectionInfo(
            reason="Conflict detected",
            conflicting_decisions=[conflict_id],
        ))

        assert fsm.state == ProposalState.REJECTED

    def test_cannot_reject_applied(self, sample_claims, sample_receipt):
        """Cannot reject an already applied proposal."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()
        fsm.verify([sample_receipt])
        fsm.apply()

        with pytest.raises(TransitionError, match="already-applied"):
            fsm.reject(RejectionInfo(reason="Too late"))

    # Reset/retry

    def test_reset_to_draft(self, sample_claims):
        """Can reset rejected proposal to DRAFT."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()
        fsm.reject(RejectionInfo(reason="Try again"))

        fsm.reset_to_draft()

        assert fsm.state == ProposalState.DRAFT
        assert fsm.proposal.rejection is None
        assert fsm.proposal.receipts == []

    def test_cannot_reset_non_rejected(self, sample_claims):
        """Cannot reset to draft from non-rejected state."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()

        with pytest.raises(TransitionError, match="from rejected state"):
            fsm.reset_to_draft()

    # State query helpers

    def test_can_propose_in_draft(self, sample_claims):
        """can_propose is True in DRAFT."""
        fsm = ProposalFSM.create(sample_claims)
        assert fsm.can_propose is True

    def test_cannot_propose_in_proposed(self, sample_claims):
        """can_propose is False after proposing."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()
        assert fsm.can_propose is False

    def test_can_verify_in_proposed(self, sample_claims):
        """can_verify is True in PROPOSED."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()
        assert fsm.can_verify is True

    def test_can_apply_in_verified(self, sample_claims, sample_receipt):
        """can_apply is True in VERIFIED."""
        fsm = ProposalFSM.create(sample_claims)
        fsm.propose()
        fsm.verify([sample_receipt])
        assert fsm.can_apply is True

    def test_is_terminal_only_when_applied(self, sample_claims, sample_receipt):
        """is_terminal is True only in APPLIED state."""
        fsm = ProposalFSM.create(sample_claims)
        assert fsm.is_terminal is False

        fsm.propose()
        assert fsm.is_terminal is False

        fsm.verify([sample_receipt])
        assert fsm.is_terminal is False

        fsm.apply()
        assert fsm.is_terminal is True


class TestCreateProposal:
    """Test the create_proposal convenience function."""

    def test_creates_fsm(self):
        """create_proposal returns a ProposalFSM."""
        claims = [file_exists("test.py")]
        fsm = create_proposal(claims)

        assert isinstance(fsm, ProposalFSM)
        assert fsm.state == ProposalState.DRAFT

    def test_with_patch_path(self):
        """create_proposal accepts patch_path."""
        claims = [file_exists("test.py")]
        fsm = create_proposal(claims, patch_path="my.patch")

        assert fsm.proposal.patch_path == "my.patch"


class TestMultipleClaims:
    """Test proposals with multiple claims."""

    def test_multiple_claims(self):
        """Can create proposal with multiple claims."""
        claims = [
            file_exists("src/main.py"),
            claim_tests_pass(["pytest"]),
            decision("framework", "fastapi"),
        ]

        fsm = create_proposal(claims)

        assert len(fsm.proposal.claims) == 3

    def test_multiple_receipts(self):
        """Can verify with multiple receipts."""
        claims = [
            file_exists("main.py"),
            claim_tests_pass(["pytest"]),
        ]

        receipts = [
            FileSnapshot(
                path="main.py",
                blob_hash="abc",
                size_bytes=100,
                timestamp=datetime.now(timezone.utc),
            ),
            CmdRun(
                command=("pytest",),
                exit_code=0,
                stdout_hash="x",
                stderr_hash="y",
                cwd="/project",
                duration_ms=1000,
                timestamp=datetime.now(timezone.utc),
            ),
        ]

        fsm = create_proposal(claims)
        fsm.propose()
        fsm.verify(receipts)

        assert fsm.state == ProposalState.VERIFIED
        assert len(fsm.proposal.receipts) == 2
