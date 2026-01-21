"""Tests for decision conflict detection."""

from uuid import uuid4

import pytest
from click.testing import CliRunner

from governor.claims import decision
from governor.ledgers import DecisionLedger
from governor.cli import cli


class TestDecisionLedgerConflicts:
    """Test DecisionLedger conflict detection."""

    @pytest.fixture
    def ledger(self, tmp_path):
        """Create a DecisionLedger in a temp directory."""
        governor_dir = tmp_path / ".governor"
        return DecisionLedger(governor_dir)

    def test_no_conflict_new_topic(self, ledger):
        """No conflict for a new topic."""
        ledger.add(decision("framework", "react"))

        conflict = ledger.check_conflict(decision("database", "postgresql"))

        assert conflict is None

    def test_no_conflict_same_choice(self, ledger):
        """No conflict when choice matches."""
        ledger.add(decision("framework", "react"))

        conflict = ledger.check_conflict(decision("framework", "react"))

        assert conflict is None

    def test_conflict_different_choice(self, ledger):
        """Conflict when topic exists with different choice."""
        original = ledger.add(decision("framework", "react"))

        conflict = ledger.check_conflict(decision("framework", "vue"))

        assert conflict is not None
        assert conflict.id == original.id
        assert conflict.choice == "react"

    def test_superseded_decision_no_conflict(self, ledger):
        """Superseded decisions don't cause conflicts."""
        original = ledger.add(decision("framework", "react"))
        ledger.revise(original.id, decision("framework", "vue"))

        # No conflict with vue (the current choice)
        conflict = ledger.check_conflict(decision("framework", "vue"))
        assert conflict is None

        # Conflict with react would be against current vue decision
        conflict2 = ledger.check_conflict(decision("framework", "react"))
        assert conflict2 is not None
        assert conflict2.choice == "vue"

    def test_revise_creates_supersession(self, ledger):
        """Revise properly supersedes old decision."""
        original = ledger.add(decision("db", "mysql"))

        revised = ledger.revise(original.id, decision("db", "postgresql"))

        assert revised is not None
        assert revised.supersedes == original.id
        assert revised.choice == "postgresql"

        # Only one active decision
        active = ledger.query(topic="db")
        assert len(active) == 1
        assert active[0].choice == "postgresql"


class TestConflictDetectionCLI:
    """Test conflict detection in CLI flow."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_conflict_blocks_verification(self, runner, tmp_path):
        """Conflicting decision blocks verification."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # First, create and apply a decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Now try to propose conflicting decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=vue"
            ])
            proposal_id2 = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Verify should fail with conflict
            result = runner.invoke(cli, ["verify", proposal_id2])

            assert result.exit_code == 1
            assert "conflict" in result.output.lower()
            assert "react" in result.output

    def test_same_choice_no_conflict(self, runner, tmp_path):
        """Same choice doesn't cause conflict."""
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

            # Propose same choice again
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id2 = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Should verify OK
            result = runner.invoke(cli, ["verify", proposal_id2])

            assert result.exit_code == 0
            assert "VERIFIED" in result.output

    def test_different_topic_no_conflict(self, runner, tmp_path):
        """Different topic doesn't cause conflict."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create framework decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Propose different topic
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=database,choice=postgresql"
            ])
            proposal_id2 = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Should verify OK
            result = runner.invoke(cli, ["verify", proposal_id2])

            assert result.exit_code == 0


class TestReviseCLI:
    """Test the governor revise command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_revise_decision(self, runner, tmp_path):
        """Can revise an existing decision."""
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

            # Get decision ID from decisions output
            result = runner.invoke(cli, ["decisions"])
            # Extract ID from output
            lines = result.output.split("\n")
            decision_id = None
            for line in lines:
                if "ID:" in line:
                    decision_id = line.split("ID:")[1].strip()
                    break

            assert decision_id is not None

            # Revise
            result = runner.invoke(cli, [
                "revise", decision_id,
                "--choice", "vue",
                "--rationale", "Migrating to Vue"
            ])

            assert result.exit_code == 0
            assert "revised" in result.output.lower()
            assert "vue" in result.output
            assert "Migrating" in result.output

            # Verify new choice is active
            result = runner.invoke(cli, ["decisions"])
            assert "vue" in result.output

    def test_revise_nonexistent_fails(self, runner, tmp_path):
        """Revising nonexistent decision fails."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            fake_id = str(uuid4())
            result = runner.invoke(cli, [
                "revise", fake_id,
                "--choice", "whatever"
            ])

            assert result.exit_code == 1
            assert "not found" in result.output

    def test_revise_invalid_id_fails(self, runner, tmp_path):
        """Revising with invalid ID fails."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, [
                "revise", "not-a-uuid",
                "--choice", "whatever"
            ])

            assert result.exit_code == 1
            assert "Invalid" in result.output

    def test_revise_removes_conflict(self, runner, tmp_path):
        """After revision, the conflict is resolved."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # Create react decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Get decision ID
            result = runner.invoke(cli, ["decisions"])
            lines = result.output.split("\n")
            decision_id = None
            for line in lines:
                if "ID:" in line:
                    decision_id = line.split("ID:")[1].strip()
                    break

            # Revise to vue
            runner.invoke(cli, ["revise", decision_id, "--choice", "vue"])

            # Now proposing vue should work (no conflict)
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=vue"
            ])
            proposal_id2 = result.output.split("Proposal created: ")[1].split("\n")[0]

            result = runner.invoke(cli, ["verify", proposal_id2])
            assert result.exit_code == 0
