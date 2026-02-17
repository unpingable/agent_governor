# SPDX-License-Identifier: Apache-2.0
"""Tests for operating envelopes."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.envelopes import (
    EnvelopeMode,
    EnvelopeConfig,
    load_envelope_config,
    get_current_envelope,
    set_envelope,
    clear_envelope,
)
from governor.cli import cli


class TestEnvelopeConfig:
    """Test EnvelopeConfig dataclass."""

    def test_exploratory_defaults(self):
        """Exploratory envelope has correct defaults."""
        config = EnvelopeConfig.exploratory()

        assert config.mode == EnvelopeMode.EXPLORATORY
        assert config.require_receipts is False
        assert config.commit_decisions is False
        assert config.allow_conflicts is True

    def test_strict_defaults(self):
        """Strict envelope has correct defaults."""
        config = EnvelopeConfig.strict()

        assert config.mode == EnvelopeMode.STRICT
        assert config.require_receipts is True
        assert config.commit_decisions is True
        assert config.allow_conflicts is False


class TestLoadEnvelopeConfig:
    """Test loading envelope config from files."""

    def test_default_when_no_config(self, tmp_path):
        """Returns default config when no config.toml exists."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        mode, configs = load_envelope_config(gov_dir)

        assert mode == EnvelopeMode.STRICT
        assert "exploratory" in configs
        assert "strict" in configs

    def test_reads_config_file(self, tmp_path):
        """Reads configuration from config.toml."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        config_content = """
[envelopes]
default = "exploratory"

[envelopes.exploratory]
require_receipts = false
decisions_commit = false

[envelopes.strict]
require_receipts = true
decisions_commit = true
"""
        (gov_dir / "config.toml").write_text(config_content)

        mode, configs = load_envelope_config(gov_dir)

        assert mode == EnvelopeMode.EXPLORATORY


class TestSetAndGetEnvelope:
    """Test setting and getting the current envelope."""

    def test_set_and_get(self, tmp_path):
        """Can set and retrieve envelope mode."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Default should be strict
        config = get_current_envelope(gov_dir)
        assert config.mode == EnvelopeMode.STRICT

        # Set to exploratory
        set_envelope(gov_dir, EnvelopeMode.EXPLORATORY)

        config = get_current_envelope(gov_dir)
        assert config.mode == EnvelopeMode.EXPLORATORY

    def test_clear_envelope(self, tmp_path):
        """Clearing envelope reverts to default."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        set_envelope(gov_dir, EnvelopeMode.EXPLORATORY)
        clear_envelope(gov_dir)

        config = get_current_envelope(gov_dir)
        assert config.mode == EnvelopeMode.STRICT  # Default


class TestEnvelopeCLI:
    """Test envelope CLI command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_show_current_envelope(self, runner, tmp_path):
        """Shows current envelope when no argument."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["envelope"])

            assert result.exit_code == 0
            assert "strict" in result.output
            assert "require_receipts" in result.output

    def test_set_exploratory(self, runner, tmp_path):
        """Can switch to exploratory mode."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            result = runner.invoke(cli, ["envelope", "exploratory"])

            assert result.exit_code == 0
            assert "exploratory" in result.output

            # Verify it changed
            result = runner.invoke(cli, ["envelope"])
            assert "exploratory" in result.output

    def test_set_strict(self, runner, tmp_path):
        """Can switch to strict mode."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["envelope", "exploratory"])

            result = runner.invoke(cli, ["envelope", "strict"])

            assert result.exit_code == 0
            assert "strict" in result.output

    def test_clear_envelope(self, runner, tmp_path):
        """Can clear envelope override."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["envelope", "exploratory"])

            result = runner.invoke(cli, ["envelope", "--clear"])

            assert result.exit_code == 0
            assert "cleared" in result.output


class TestEnvelopeBehavior:
    """Test that envelopes affect behavior."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    def test_strict_rejects_failed_verification(self, runner, tmp_path):
        """Strict mode rejects proposals with failed verification."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["envelope", "strict"])

            # Propose non-existent file
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            result = runner.invoke(cli, ["verify", proposal_id])

            assert result.exit_code == 1
            assert "REJECTED" in result.output

    def test_exploratory_allows_failed_verification(self, runner, tmp_path):
        """Exploratory mode allows proposals with failed verification."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["envelope", "exploratory"])

            # Propose non-existent file
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=file_exists,path=missing.py"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]

            result = runner.invoke(cli, ["verify", proposal_id])

            assert result.exit_code == 0
            assert "VERIFIED" in result.output
            assert "exploratory" in result.output.lower()

    def test_exploratory_skips_decision_commit(self, runner, tmp_path):
        """Exploratory mode doesn't commit decisions."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["envelope", "exploratory"])

            # Create decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            result = runner.invoke(cli, ["apply", proposal_id])

            assert "Skipped decision" in result.output

            # Decision should not be recorded
            result = runner.invoke(cli, ["decisions"])
            assert "No decisions" in result.output

    def test_strict_commits_decision(self, runner, tmp_path):
        """Strict mode commits decisions."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])
            runner.invoke(cli, ["envelope", "strict"])

            # Create decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            result = runner.invoke(cli, ["apply", proposal_id])

            assert "Added decision" in result.output

            # Decision should be recorded
            result = runner.invoke(cli, ["decisions"])
            assert "framework" in result.output

    def test_exploratory_allows_conflicts(self, runner, tmp_path):
        """Exploratory mode allows conflicting decisions."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init"])

            # First, create decision in strict mode
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=react"
            ])
            proposal_id = result.output.split("Proposal created: ")[1].split("\n")[0]
            runner.invoke(cli, ["verify", proposal_id])
            runner.invoke(cli, ["apply", proposal_id])

            # Switch to exploratory
            runner.invoke(cli, ["envelope", "exploratory"])

            # Propose conflicting decision
            result = runner.invoke(cli, [
                "propose",
                "--claim", "type=decision,topic=framework,choice=vue"
            ])
            proposal_id2 = result.output.split("Proposal created: ")[1].split("\n")[0]

            # Should verify OK in exploratory
            result = runner.invoke(cli, ["verify", proposal_id2])

            assert result.exit_code == 0
            assert "VERIFIED" in result.output
