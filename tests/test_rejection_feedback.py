# SPDX-License-Identifier: Apache-2.0
"""Tests for structured rejection feedback."""

import json
from uuid import uuid4

import pytest
from click.testing import CliRunner

from governor.fsm import (
    ClaimError,
    RejectionInfo,
    ProposalState,
    create_proposal,
)
from governor.claims import file_exists, decision, claim_tests_pass
from governor.cli import cli


class TestClaimError:
    """Test ClaimError dataclass."""

    def test_basic_error(self):
        """ClaimError stores error details."""
        error = ClaimError(
            claim_index=0,
            error_type="file_not_found",
            message="File does not exist: missing.py",
        )

        assert error.claim_index == 0
        assert error.error_type == "file_not_found"
        assert error.message == "File does not exist: missing.py"
        assert error.suggestion is None

    def test_error_with_suggestion(self):
        """ClaimError can include a suggestion."""
        error = ClaimError(
            claim_index=1,
            error_type="tests_failed",
            message="Tests failed with exit code 1",
            suggestion="Fix failing tests before proposing",
        )

        assert error.suggestion == "Fix failing tests before proposing"

    def test_to_dict(self):
        """ClaimError serializes to dict."""
        error = ClaimError(
            claim_index=2,
            error_type="verification_failed",
            message="Could not verify claim",
            suggestion="Check the claim parameters",
        )

        data = error.to_dict()

        assert data["claim_index"] == 2
        assert data["error_type"] == "verification_failed"
        assert data["message"] == "Could not verify claim"
        assert data["suggestion"] == "Check the claim parameters"

    def test_to_dict_no_suggestion(self):
        """ClaimError without suggestion omits it from dict."""
        error = ClaimError(
            claim_index=0,
            error_type="file_not_found",
            message="File missing",
        )

        data = error.to_dict()

        assert "suggestion" not in data


class TestRejectionInfoEnhanced:
    """Test enhanced RejectionInfo with claim_errors."""

    def test_with_claim_errors(self):
        """RejectionInfo can include detailed claim errors."""
        errors = [
            ClaimError(
                claim_index=0,
                error_type="file_not_found",
                message="File not found: src/missing.py",
                suggestion="Create the file first",
            ),
            ClaimError(
                claim_index=2,
                error_type="tests_failed",
                message="Tests failed",
            ),
        ]

        rejection = RejectionInfo(
            reason="Verification failed",
            failed_claims=[0, 2],
            claim_errors=errors,
        )

        assert len(rejection.claim_errors) == 2
        assert rejection.claim_errors[0].error_type == "file_not_found"
        assert rejection.claim_errors[1].error_type == "tests_failed"

    def test_to_dict_includes_claim_errors(self):
        """RejectionInfo.to_dict includes claim_errors."""
        errors = [
            ClaimError(
                claim_index=0,
                error_type="file_not_found",
                message="Missing file",
                suggestion="Create the file",
            ),
        ]

        rejection = RejectionInfo(
            reason="Failed",
            claim_errors=errors,
        )

        data = rejection.to_dict()

        assert "claim_errors" in data
        assert len(data["claim_errors"]) == 1
        assert data["claim_errors"][0]["claim_index"] == 0
        assert data["claim_errors"][0]["suggestion"] == "Create the file"

    def test_from_dict_restores_claim_errors(self):
        """RejectionInfo.from_dict restores claim_errors."""
        data = {
            "reason": "Failed",
            "missing_receipts": [],
            "conflicting_decisions": [],
            "failed_claims": [0],
            "claim_errors": [
                {
                    "claim_index": 0,
                    "error_type": "file_not_found",
                    "message": "Missing",
                    "suggestion": "Create it",
                }
            ],
            "details": {},
        }

        rejection = RejectionInfo.from_dict(data)

        assert len(rejection.claim_errors) == 1
        assert rejection.claim_errors[0].claim_index == 0
        assert rejection.claim_errors[0].suggestion == "Create it"


class TestGetSuggestions:
    """Test RejectionInfo.get_suggestions method."""

    def test_suggestions_from_claim_errors(self):
        """get_suggestions includes suggestions from claim_errors."""
        errors = [
            ClaimError(
                claim_index=0,
                error_type="file_not_found",
                message="Missing",
                suggestion="Create the file",
            ),
            ClaimError(
                claim_index=1,
                error_type="tests_failed",
                message="Failed",
                suggestion="Fix the tests",
            ),
        ]

        rejection = RejectionInfo(
            reason="Failed",
            claim_errors=errors,
        )

        suggestions = rejection.get_suggestions()

        assert "Create the file" in suggestions
        assert "Fix the tests" in suggestions

    def test_suggestions_for_conflicts(self):
        """get_suggestions includes revise suggestion for conflicts."""
        rejection = RejectionInfo(
            reason="Conflict",
            conflicting_decisions=[uuid4()],
        )

        suggestions = rejection.get_suggestions()

        assert any("revise" in s.lower() for s in suggestions)

    def test_suggestions_for_missing_receipts(self):
        """get_suggestions includes receipt suggestion."""
        rejection = RejectionInfo(
            reason="Missing receipts",
            missing_receipts=["file_snapshot"],
        )

        suggestions = rejection.get_suggestions()

        assert any("exist" in s.lower() or "pass" in s.lower() for s in suggestions)

    def test_default_suggestion(self):
        """get_suggestions returns default if no specific suggestions."""
        rejection = RejectionInfo(reason="Unknown error")

        suggestions = rejection.get_suggestions()

        assert len(suggestions) >= 1
        assert any("review" in s.lower() for s in suggestions)


class TestRejectionFeedbackCLI:
    """Test rejection feedback in CLI."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_verify_shows_detailed_errors(self, runner, tmp_path):
        """Verify command shows detailed error information."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Propose non-existent file
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            result = runner.invoke(cli, ["verify", proposal_id])

            assert result.exit_code == 1
            assert "REJECTED" in result.output
            assert "Errors:" in result.output
            assert "Suggestion" in result.output

    def test_verify_json_output(self, runner, tmp_path):
        """Verify command with --json outputs structured JSON."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Propose non-existent file
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=nonexistent.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            result = runner.invoke(cli, ["verify", proposal_id, "--json"])

            assert result.exit_code == 1

            # Parse JSON output (skip the "Operating in strict mode" line)
            lines = result.output.strip().split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.strip().startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(line)

            json_str = "\n".join(json_lines)
            data = json.loads(json_str)

            assert data["status"] == "rejected"
            assert data["proposal_id"] == proposal_id
            assert "rejection" in data
            assert "suggestions" in data

    def test_verify_json_includes_claim_errors(self, runner, tmp_path):
        """JSON output includes detailed claim errors."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Propose non-existent file
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing_file.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            result = runner.invoke(cli, ["verify", proposal_id, "--json"])

            # Parse JSON
            lines = result.output.strip().split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.strip().startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(line)

            json_str = "\n".join(json_lines)
            data = json.loads(json_str)

            assert "claim_errors" in data["rejection"]
            errors = data["rejection"]["claim_errors"]
            assert len(errors) >= 1
            assert errors[0]["claim_index"] == 0
            assert "error_type" in errors[0]

    def test_conflict_json_output(self, runner, tmp_path):
        """Conflict rejection includes JSON output."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create and apply a decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Propose conflicting decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=vue"
            ])
            proposal_id2 = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Verify with JSON
            result = runner.invoke(cli, ["verify", proposal_id2, "--json"])

            assert result.exit_code == 1

            # Parse JSON
            lines = result.output.strip().split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.strip().startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(line)

            json_str = "\n".join(json_lines)
            data = json.loads(json_str)

            assert data["status"] == "rejected"
            assert len(data["rejection"]["conflicting_decisions"]) > 0
            assert "suggestions" in data

    def test_multiple_claim_errors(self, runner, tmp_path):
        """Multiple failed claims produce multiple errors."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Propose multiple non-existent files
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing1.py",
                "--claim", "type=file_exists,path=missing2.py",
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            result = runner.invoke(cli, ["verify", proposal_id, "--json"])

            # Parse JSON
            lines = result.output.strip().split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.strip().startswith("{"):
                    in_json = True
                if in_json:
                    json_lines.append(line)

            json_str = "\n".join(json_lines)
            data = json.loads(json_str)

            assert len(data["rejection"]["claim_errors"]) == 2
            assert data["rejection"]["claim_errors"][0]["claim_index"] == 0
            assert data["rejection"]["claim_errors"][1]["claim_index"] == 1


class TestRejectionPersistence:
    """Test that rejection info is persisted correctly."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_rejection_persisted_in_proposal(self, runner, tmp_path):
        """Rejection info is persisted in proposal."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Propose non-existent file
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])

            # Check status shows rejected
            result = runner.invoke(cli, ["status"])

            assert "rejected" in result.output.lower()

    def test_rejection_claim_errors_roundtrip(self):
        """Claim errors survive serialization roundtrip."""
        from governor.fsm import Proposal
        from datetime import datetime, timezone
        from uuid import uuid4

        errors = [
            ClaimError(
                claim_index=0,
                error_type="file_not_found",
                message="Missing",
                suggestion="Create it",
            ),
        ]

        rejection = RejectionInfo(
            reason="Failed",
            failed_claims=[0],
            claim_errors=errors,
        )

        proposal = Proposal(
            id=uuid4(),
            claims=[file_exists("test.py")],
            state=ProposalState.REJECTED,
            created_at=datetime.now(timezone.utc),
            rejection=rejection,
        )

        # Serialize and deserialize
        data = proposal.to_dict()
        restored = Proposal.from_dict(data)

        assert restored.rejection is not None
        assert len(restored.rejection.claim_errors) == 1
        assert restored.rejection.claim_errors[0].suggestion == "Create it"
