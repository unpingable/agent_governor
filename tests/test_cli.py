# SPDX-License-Identifier: Apache-2.0
"""Tests for the governor CLI."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.cli import cli, parse_claim
from governor.claims import ClaimType


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def initialized_project(tmp_path):
    """Create an initialized governor project."""
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        yield Path(td)


class TestInit:
    """Test governor init command."""

    def test_init_creates_structure(self, runner, tmp_path):
        """init creates the .governor directory structure."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init"])

            assert result.exit_code == 0
            assert "Initialized" in result.output

            gov_dir = Path(".governor")
            assert gov_dir.exists()
            assert (gov_dir / "facts").exists()
            assert (gov_dir / "facts" / "receipts").exists()
            assert (gov_dir / "decisions").exists()
            assert (gov_dir / "config.toml").exists()

    def test_init_idempotent(self, runner, tmp_path):
        """init is idempotent - running twice is safe."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result1 = runner.invoke(cli, ["init"])
            result2 = runner.invoke(cli, ["init"])

            assert result1.exit_code == 0
            assert result2.exit_code == 0
            assert "already initialized" in result2.output


class TestPropose:
    """Test governor propose command."""

    def test_propose_requires_claim_or_patch(self, runner, tmp_path):
        """propose fails without claims or patch."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["propose"])

            assert result.exit_code == 1
            assert "Must provide" in result.output

    def test_propose_file_exists_claim(self, runner, tmp_path):
        """propose with file_exists claim."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("main.py").write_text("# main")

            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])

            assert result.exit_code == 0
            assert "Proposal created" in result.output
            assert "file_exists" in result.output.lower() or "File exists" in result.output

    def test_propose_decision_claim(self, runner, tmp_path):
        """propose with decision claim."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])

            assert result.exit_code == 0
            assert "Proposal created" in result.output

    def test_propose_multiple_claims(self, runner, tmp_path):
        """propose with multiple claims."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("app.py").write_text("# app")

            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=app.py",
                "--claim", "type=decision,topic=db,choice=sqlite"
            ])

            assert result.exit_code == 0
            assert "Claims: 2" in result.output

    def test_propose_requires_init(self, runner, tmp_path):
        """propose fails if not initialized."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=x.py"
            ])

            assert result.exit_code == 1
            assert "not initialized" in result.output


class TestVerify:
    """Test governor verify command."""

    def test_verify_passing_claim(self, runner, tmp_path):
        """verify succeeds when claim is valid."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("main.py").write_text("# main")

            # Create proposal
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Verify
            result = runner.invoke(cli, ["verify", proposal_id])

            assert result.exit_code == 0
            assert "VERIFIED" in result.output

    def test_verify_failing_claim(self, runner, tmp_path):
        """verify fails when claim is invalid."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create proposal for non-existent file
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Verify
            result = runner.invoke(cli, ["verify", proposal_id])

            assert result.exit_code == 1
            assert "REJECTED" in result.output

    def test_verify_not_found(self, runner, tmp_path):
        """verify fails for unknown proposal."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["verify", "nonexistent-id"])

            assert result.exit_code == 1
            assert "not found" in result.output


class TestApply:
    """Test governor apply command."""

    def test_apply_verified_proposal(self, runner, tmp_path):
        """apply succeeds for verified proposal."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("main.py").write_text("# main")

            # Create and verify proposal
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])

            # Apply
            result = runner.invoke(cli, ["apply", proposal_id])

            assert result.exit_code == 0
            assert "APPLIED" in result.output

    def test_apply_unverified_fails(self, runner, tmp_path):
        """apply fails for unverified proposal."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("main.py").write_text("# main")

            # Create proposal but don't verify
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Try to apply without verify
            result = runner.invoke(cli, ["apply", proposal_id])

            assert result.exit_code == 1
            assert "cannot apply" in result.output.lower()


class TestFacts:
    """Test governor facts command."""

    def test_facts_empty(self, runner, tmp_path):
        """facts shows empty message when no facts."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["facts"])

            assert result.exit_code == 0
            assert "No facts" in result.output

    def test_facts_after_apply(self, runner, tmp_path):
        """facts shows facts after apply."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("main.py").write_text("# main")

            # Create, verify, apply
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Check facts
            result = runner.invoke(cli, ["facts"])

            assert result.exit_code == 0
            assert "main.py" in result.output


class TestDecisions:
    """Test governor decisions command."""

    def test_decisions_empty(self, runner, tmp_path):
        """decisions shows empty message when no decisions."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["decisions"])

            assert result.exit_code == 0
            assert "No decisions" in result.output

    def test_decisions_after_apply(self, runner, tmp_path):
        """decisions shows decisions after apply."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create, verify, apply decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Check decisions
            result = runner.invoke(cli, ["decisions"])

            assert result.exit_code == 0
            assert "framework" in result.output
            assert "react" in result.output


class TestStatus:
    """Test governor status command."""

    def test_status_empty(self, runner, tmp_path):
        """status --proposals shows empty message when no proposals."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["status", "--proposals"])

            assert result.exit_code == 0
            assert "No proposals" in result.output

    def test_status_bare_is_dashboard(self, runner, tmp_path):
        """Bare status shows operator dashboard."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["status"])

            assert result.exit_code == 0
            assert "Governor:" in result.output

    def test_status_shows_proposals(self, runner, tmp_path):
        """status --proposals shows proposal list."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            Path("main.py").write_text("# main")

            runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=main.py"
            ])

            result = runner.invoke(cli, ["status", "--proposals"])

            assert result.exit_code == 0
            assert "proposed" in result.output


class TestRejections:
    """Test governor rejections command."""

    def test_rejections_empty(self, runner, tmp_path):
        """rejections shows empty message when no rejections."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["rejections"])

            assert result.exit_code == 0
            assert "No rejected" in result.output

    def test_rejections_shows_rejected(self, runner, tmp_path):
        """rejections shows rejected proposals."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create a proposal that will be rejected
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=nonexistent.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Verify will reject it
            runner.invoke(cli, ["verify", proposal_id])

            # Check rejections
            result = runner.invoke(cli, ["rejections"])

            assert result.exit_code == 0
            assert proposal_id[:8] in result.output
            assert "Reason:" in result.output

    def test_rejections_json_output(self, runner, tmp_path):
        """rejections --json outputs JSON."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create a rejected proposal
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])

            # Get JSON output
            result = runner.invoke(cli, ["rejections", "--json"])

            assert result.exit_code == 0
            import json
            data = json.loads(result.output)
            assert len(data) == 1
            assert "rejection" in data[0]

    def test_rejections_limit(self, runner, tmp_path):
        """rejections respects --limit."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create multiple rejected proposals
            for i in range(5):
                result = runner.invoke(cli, [
                    "propose",
                    "--claim", f"type=file_exists,path=missing{i}.py"
                ])
                proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
                runner.invoke(cli, ["verify", proposal_id])

            # Get with limit
            result = runner.invoke(cli, ["rejections", "--limit", "2", "--json"])

            import json
            data = json.loads(result.output)
            assert len(data) == 2


class TestFullFlow:
    """Test complete propose → verify → apply flow."""

    def test_full_flow_file_claim(self, runner, tmp_path):
        """Complete flow with file exists claim."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Initialize
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0

            # Create file
            Path("src").mkdir()
            Path("src/app.py").write_text("def main(): pass")

            # Propose
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=src/app.py"
            ])
            assert result.exit_code == 0
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Verify
            result = runner.invoke(cli, ["verify", proposal_id])
            assert result.exit_code == 0
            assert "VERIFIED" in result.output

            # Apply
            result = runner.invoke(cli, ["apply", proposal_id])
            assert result.exit_code == 0
            assert "APPLIED" in result.output

            # Check facts
            result = runner.invoke(cli, ["facts"])
            assert "src/app.py" in result.output

    def test_full_flow_decision(self, runner, tmp_path):
        """Complete flow with decision claim."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Propose decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=api_style,choice=rest"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Verify and apply
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Check decisions
            result = runner.invoke(cli, ["decisions"])
            assert "api_style" in result.output
            assert "rest" in result.output


class TestParseClaim:
    """Test the parse_claim helper function."""

    def test_parse_file_exists(self):
        """Parse file_exists claim."""
        claim = parse_claim("type=file_exists,path=src/main.py")

        assert claim.type == ClaimType.FILE_EXISTS
        assert claim.path == "src/main.py"

    def test_parse_decision(self):
        """Parse decision claim."""
        claim = parse_claim("type=decision,topic=framework,choice=react")

        assert claim.type == ClaimType.DECISION
        assert claim.topic == "framework"
        assert claim.choice == "react"

    def test_parse_tests_pass(self):
        """Parse tests_pass claim."""
        claim = parse_claim("type=tests_pass,command=pytest -v")

        assert claim.type == ClaimType.TESTS_PASS
        assert claim.command == ("pytest", "-v")

    def test_parse_missing_type(self):
        """Raises for missing type."""
        with pytest.raises(ValueError, match="type"):
            parse_claim("path=src/main.py")

    def test_parse_unknown_type(self):
        """Raises for unknown type."""
        with pytest.raises(ValueError, match="Unknown"):
            parse_claim("type=unknown,foo=bar")
