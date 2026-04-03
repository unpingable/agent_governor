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
        assert list(CATEGORIES.keys()) == ["Operator", "Workflow", "Config", "Debug", "Advanced"]

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
        assert "advanced --help" in result.output

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
        assert "advanced --help" in result.output

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


# ---------------------------------------------------------------------------
# Guardrail: explicit allowlist for uncategorized commands
# ---------------------------------------------------------------------------

# Attic surface: deep/kernel commands that are intentionally not in the
# curated help.  Add here only when adding a new top-level CLI group.
# If this set grows past ~120, it's time to nest under `governor advanced`.
ALLOWED_UNCATEGORIZED: set[str] = {
    "adapt", "admit", "advanced", "agent", "anchor", "audit",
    "autonomous", "backend", "boil", "cbi", "changes", "chat",
    "claim", "claim-diff", "claim-signals", "claude-hooks", "code", "codex-exec",
    "codex-hooks", "collapse", "conditioning", "constraints",
    "context", "continuity", "correlator", "dashboard",
    "dashboard-ux", "decay", "decide", "decisions", "demo",
    "deploy", "detector", "doc", "docket", "drift", "epistemic",
    "evasion", "explore", "external", "facts", "fiction", "gate",
    "git-gov", "graph", "hook", "hysteresis", "independence",
    "instrument", "interferometry", "invariant", "issue",
    "jurisdiction", "kernel", "lanes", "lock", "mcp", "measure",
    "metrics", "mode", "must-exist", "must-pass", "ops",
    "override", "p4", "phase", "precedent", "preflight",
    "prometheus", "puppet", "quorum", "quorum-ext", "regime", "replay",
    "rejections", "resolve", "revise", "risk", "routing", "rule", "runtime",
    "scar", "scope", "security", "selfcheck", "semvar", "signals",
    "slim", "spine", "stability", "state", "strict", "taint",
    "task", "telemetry", "temporal", "transport", "tune", "unlock",
    "vitals", "watch",
}


class TestCuratedGuardrail:
    def test_no_unknown_uncategorized_commands(self):
        """New commands must be curated or explicitly allowlisted."""
        from governor.cli import cli

        ctx = click.Context(cli)
        all_commands = set(cli.list_commands(ctx))
        uncategorized = all_commands - _CURATED_NAMES
        unknown = uncategorized - ALLOWED_UNCATEGORIZED
        assert not unknown, (
            f"New uncategorized command(s) not in allowlist: {sorted(unknown)}. "
            f"Add to CATEGORIES in cli_group.py or to ALLOWED_UNCATEGORIZED "
            f"in test_cli_group.py."
        )

    def test_allowlist_not_stale(self):
        """Removed commands must be cleaned from the allowlist."""
        from governor.cli import cli

        ctx = click.Context(cli)
        all_commands = set(cli.list_commands(ctx))
        stale = ALLOWED_UNCATEGORIZED - all_commands
        assert not stale, (
            f"Stale entries in ALLOWED_UNCATEGORIZED (commands no longer exist): "
            f"{sorted(stale)}. Remove them."
        )


# ---------------------------------------------------------------------------
# Operator surface contract — frozen public surface
# ---------------------------------------------------------------------------
# If any of these tests fail, you're changing the public surface.
# That's fine — but it should be deliberate, not accidental.

# The 5 help categories and 21 curated commands. Update only with intent.
FROZEN_CATEGORIES = ["Operator", "Workflow", "Config", "Debug", "Advanced"]
FROZEN_CURATED_COMMANDS: set[str] = {
    # Operator
    "status", "doctor", "trace", "explain", "operator", "receipts", "check",
    # Workflow
    "quickstart", "init", "propose", "verify", "apply", "wrap", "serve", "ci",
    # Config
    "envelope", "profile", "intent", "session", "config",
    # Debug
    "rpc",
    # Advanced
    "advanced",
}


class TestOperatorContract:
    """Freeze the public operator surface. Prevents "just one more command" entropy."""

    def test_help_has_exactly_five_categories(self, runner):
        """Root help shows exactly 5 category sections."""
        from governor.cli import cli
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        for cat in FROZEN_CATEGORIES:
            assert f"{cat}:" in result.output, f"Missing category: {cat}"

    def test_category_names_match_frozen(self):
        """CATEGORIES keys match the frozen list exactly."""
        assert list(CATEGORIES.keys()) == FROZEN_CATEGORIES

    def test_curated_commands_match_frozen(self):
        """Curated command set matches the frozen set exactly."""
        assert _CURATED_NAMES == FROZEN_CURATED_COMMANDS, (
            f"Curated commands changed.\n"
            f"  Added:   {sorted(_CURATED_NAMES - FROZEN_CURATED_COMMANDS)}\n"
            f"  Removed: {sorted(FROZEN_CURATED_COMMANDS - _CURATED_NAMES)}\n"
            f"Update FROZEN_CURATED_COMMANDS if this was intentional."
        )

    def test_all_curated_commands_exist(self):
        """Every curated command actually exists in the CLI."""
        from governor.cli import cli
        for name in FROZEN_CURATED_COMMANDS:
            assert name in cli.commands, (
                f"Curated command '{name}' does not exist in cli.commands"
            )

    def test_advanced_group_exists_and_is_populated(self):
        """Advanced group exists and contains the attic commands."""
        from governor.cli import advanced
        assert len(advanced.commands) > 50, (
            f"Advanced group has only {len(advanced.commands)} commands — "
            f"expected 50+. Did _populate_advanced() run?"
        )

    def test_bare_invocation_shows_state(self, runner):
        """Bare 'governor' prints rollup state, not a tutorial."""
        from governor.cli import cli
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        # Must contain the state label (from render_bare)
        assert "Governor:" in result.output or "Not initialized." in result.output


# ---------------------------------------------------------------------------
# Advanced group tests
# ---------------------------------------------------------------------------

class TestAdvancedGroup:
    @pytest.fixture(autouse=True)
    def _load_cli(self):
        from governor.cli import cli, advanced
        self.cli = cli
        self.advanced = advanced

    def test_advanced_commands_match_attic(self):
        """Advanced group contains exactly the non-curated, non-self commands."""
        all_cmds = set(self.cli.commands.keys())
        expected = all_cmds - _CURATED_NAMES - {"advanced"}
        actual = set(self.advanced.commands.keys())
        assert actual == expected

    def test_advanced_excludes_curated(self):
        """No curated command should appear in the advanced group."""
        overlap = set(self.advanced.commands.keys()) & _CURATED_NAMES
        assert overlap == set(), f"Curated commands leaked into advanced: {overlap}"

    def test_advanced_excludes_self(self):
        """The advanced group must not contain itself."""
        assert "advanced" not in self.advanced.commands

    def test_advanced_help_output(self, runner):
        """'governor advanced --help' lists subcommands."""
        result = runner.invoke(self.cli, ["advanced", "--help"])
        assert result.exit_code == 0
        # Should list many commands (the attic)
        assert "Commands:" in result.output
        assert len(result.output) > 500

    def test_help_all_still_works(self, runner):
        """--help-all still produces the flat listing."""
        result = runner.invoke(self.cli, ["--help-all"])
        assert result.exit_code == 0
        assert "Commands:" in result.output
        assert len(result.output) > 2000

    def test_every_noncurated_in_advanced(self):
        """Every non-curated root command is accessible via advanced."""
        for name in self.cli.commands:
            if name in _CURATED_NAMES or name == "advanced":
                continue
            assert name in self.advanced.commands, (
                f"Non-curated command '{name}' missing from advanced group"
            )
