# SPDX-License-Identifier: Apache-2.0
"""Tests for CuratedGroup — categorized CLI help."""

import re

import click
import pytest
from click.testing import CliRunner

from governor.cli_group import CATEGORIES, CuratedGroup, _CURATED_NAMES


# ---------------------------------------------------------------------------
# Fixture: minimal CLI using CuratedGroup
# ---------------------------------------------------------------------------

def _set_help_all(ctx, param, value):
    ctx.ensure_object(dict)
    ctx.obj["help_all"] = value
    if value:
        click.echo(ctx.get_help())
        ctx.exit(0)


def _make_cli(**kwargs):
    """Build a small CLI using CuratedGroup for testing."""

    @click.group(cls=CuratedGroup, invoke_without_command=True, **kwargs)
    @click.option("--help-all", is_flag=True, is_eager=True, expose_value=False,
                  callback=_set_help_all, help="Show all commands")
    @click.pass_context
    def cli(ctx):
        """Test CLI."""
        ctx.ensure_object(dict)

    @cli.command()
    def status():
        """Show status."""
        click.echo("status-output")

    @cli.command()
    def doctor():
        """Run diagnostics."""
        click.echo("doctor-output")

    @cli.command()
    def init():
        """Initialize project."""
        click.echo("init-output")

    @cli.command()
    def serve():
        """Start server."""
        click.echo("serve-output")

    @cli.command()
    def hidden_deep():
        """A deep command not in any category."""
        click.echo("hidden-output")

    return cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def test_cli():
    return _make_cli()


# ---------------------------------------------------------------------------
# CuratedGroup structure tests
# ---------------------------------------------------------------------------

class TestCategoriesStructure:
    def test_categories_is_ordered_dict(self):
        assert isinstance(CATEGORIES, dict)
        assert list(CATEGORIES.keys()) == ["Operator", "Workflow", "Config"]

    def test_operator_category_has_status(self):
        assert "status" in CATEGORIES["Operator"]

    def test_curated_names_set_populated(self):
        assert "status" in _CURATED_NAMES
        assert "init" in _CURATED_NAMES
        assert "serve" in _CURATED_NAMES

    def test_no_duplicate_names_across_categories(self):
        seen = set()
        for names in CATEGORIES.values():
            for n in names:
                assert n not in seen, f"Duplicate: {n}"
                seen.add(n)


# ---------------------------------------------------------------------------
# Help output tests
# ---------------------------------------------------------------------------

class TestCuratedHelp:
    def test_default_help_shows_categories(self, runner, test_cli):
        result = runner.invoke(test_cli, ["--help"])
        assert result.exit_code == 0
        assert "Operator:" in result.output
        assert "Workflow:" in result.output

    def test_default_help_shows_curated_commands(self, runner, test_cli):
        result = runner.invoke(test_cli, ["--help"])
        assert "status" in result.output
        assert "doctor" in result.output
        assert "init" in result.output
        assert "serve" in result.output

    def test_default_help_hides_non_curated(self, runner, test_cli):
        result = runner.invoke(test_cli, ["--help"])
        assert "hidden-deep" not in result.output
        assert "hidden_deep" not in result.output

    def test_default_help_shows_footer(self, runner, test_cli):
        result = runner.invoke(test_cli, ["--help"])
        assert "--help-all" in result.output

    def test_help_all_shows_everything(self, runner, test_cli):
        result = runner.invoke(test_cli, ["--help-all"])
        assert result.exit_code == 0
        assert "hidden-deep" in result.output

    def test_help_all_shows_curated_commands_too(self, runner, test_cli):
        result = runner.invoke(test_cli, ["--help-all"])
        assert "status" in result.output
        assert "init" in result.output

    def test_commands_still_work(self, runner, test_cli):
        result = runner.invoke(test_cli, ["status"])
        assert result.exit_code == 0
        assert "status-output" in result.output

    def test_hidden_commands_still_work(self, runner, test_cli):
        result = runner.invoke(test_cli, ["hidden-deep"])
        assert result.exit_code == 0
        assert "hidden-output" in result.output


# ---------------------------------------------------------------------------
# Real CLI tests (governor CLI itself)
# ---------------------------------------------------------------------------

class TestRealCLI:
    def test_governor_help_shows_categories(self, runner):
        from governor.cli import cli
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Operator:" in result.output
        assert "Workflow:" in result.output
        assert "Config:" in result.output

    def test_governor_help_shows_footer(self, runner):
        from governor.cli import cli
        result = runner.invoke(cli, ["--help"])
        assert "--help-all" in result.output

    def test_governor_help_all_shows_many_commands(self, runner):
        from governor.cli import cli
        result = runner.invoke(cli, ["--help-all"])
        assert result.exit_code == 0
        # --help-all output should include many commands (the flat listing)
        # Look for the "Commands:" section which lists all commands
        assert "Commands:" in result.output
        assert len(result.output) > 2000  # Full listing is large

    def test_governor_operator_group_exists(self, runner):
        from governor.cli import cli
        result = runner.invoke(cli, ["operator", "--help"])
        assert result.exit_code == 0
        assert "doctor" in result.output
        assert "status" in result.output
        assert "trace" in result.output
        assert "explain" in result.output
        assert "receipts" in result.output
