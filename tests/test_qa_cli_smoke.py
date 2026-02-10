"""QA Harness: CLI Smoke Tests.

Verify all CLI commands execute without crashing.
"Every CLI command should at least parse and not crash."

This catches the dumbest bugs first - import errors, typos,
missing dependencies, broken decorators.
"""

import subprocess
import pytest
from pathlib import Path


# =============================================================================
# Command Extraction
# =============================================================================

# Core governor commands (extracted from cli-reference.md)
GOVERNOR_COMMANDS = [
    # Core workflow
    "governor --help",
    "governor init --help",
    "governor propose --help",
    "governor verify --help",
    "governor apply --help",
    # Query state
    "governor facts --help",
    "governor decisions --help",
    "governor status --help",
    "governor state --help",
    "governor rejections --help",
    # Configuration
    "governor envelope --help",
    "governor decay --help",
    # Integration
    "governor hook --help",
    "governor wrap --help",
    "governor changes --help",
    # MCP
    "governor mcp --help",
    # Multi-agent
    "governor agent --help",
    "governor task --help",
    # Epistemic
    "governor epistemic --help",
    "governor regime --help",
    "governor boil --help",
    "governor jurisdiction --help",
    # Security
    "governor security --help",
    "governor watch --help",
    "governor claude-hooks --help",
    # Routing
    "governor routing --help",
    # Failure provenance
    "governor scar --help",
    # Audit
    "governor audit --help",
    "governor adapt --help",
    # Exploration
    "governor explore --help",
    "governor vitals --help",
    # Strict mode
    "governor strict --help",
    # Drift
    "governor drift --help",
    # Claim diff
    "governor claim-diff --help",
    # Signals
    "governor signals --help",
    # Profiles
    "governor profile --help",
    # Quorum
    "governor quorum --help",
    "governor independence --help",
    # Semantic variety
    "governor semvar --help",
    # Tuning
    "governor tune --help",
    # Taint
    "governor taint --help",
    # Puppet
    "governor puppet --help",
    # Spine
    "governor spine --help",
    # Invariants
    "governor invariant --help",
    # Autonomous
    "governor autonomous --help",
    # Telemetry
    "governor telemetry --help",
    "governor dashboard --help",
    "governor prometheus --help",
    # Continuity
    "governor continuity --help",
    "governor gate --help",
    # Check
    "governor check --help",
    # Intent/Override
    "governor intent --help",
    "governor override --help",
    # Interferometry
    "governor interferometry --help",
    # External
    "governor external --help",
    # Session
    "governor session --help",
    # Fiction/Code (friendly commands)
    "governor fiction --help",
    "governor code --help",
    "governor resolve --help",
    "governor advanced --help",
]

# Fiction governor commands
FICTION_GOV_COMMANDS = [
    "fiction-gov --help",
    "fiction-gov drift --help",
    "fiction-gov guardrails --help",
]

# Nonfiction governor commands (if exists)
NONFICTION_GOV_COMMANDS = [
    "nonfiction-gov --help",
]

# Ops governor commands (if exists)
OPS_GOV_COMMANDS = [
    "ops-gov --help",
]


# =============================================================================
# Test Infrastructure
# =============================================================================


def run_cli_command(cmd: str) -> tuple[int, str, str]:
    """Run a CLI command and capture output.

    Returns: (returncode, stdout, stderr)
    """
    result = subprocess.run(
        cmd.split(),
        capture_output=True,
        text=True,
        timeout=30,  # Commands should respond quickly
    )
    return result.returncode, result.stdout, result.stderr


def assert_no_traceback(stderr: str, cmd: str) -> None:
    """Assert no Python traceback in stderr."""
    assert "Traceback" not in stderr, f"Command '{cmd}' crashed with traceback:\n{stderr}"


def assert_valid_exit_code(code: int, cmd: str) -> None:
    """Assert exit code is acceptable.

    0 = success
    1 = expected error (e.g., missing required arg)
    2 = usage/help display
    """
    assert code in {0, 1, 2}, f"Command '{cmd}' returned unexpected code {code}"


# =============================================================================
# Governor CLI Smoke Tests
# =============================================================================


class TestGovernorCLISmoke:
    """Smoke tests for all governor CLI commands."""

    @pytest.mark.parametrize("cmd", GOVERNOR_COMMANDS)
    def test_governor_command(self, cmd: str) -> None:
        """Each governor command should parse and not crash."""
        code, stdout, stderr = run_cli_command(cmd)
        assert_no_traceback(stderr, cmd)
        assert_valid_exit_code(code, cmd)

    def test_governor_bare(self) -> None:
        """Bare 'governor' should show help, not crash."""
        code, stdout, stderr = run_cli_command("governor")
        assert_no_traceback(stderr, "governor")
        # Should show help or status
        assert code in {0, 1, 2}


class TestFictionGovCLISmoke:
    """Smoke tests for fiction-gov CLI commands."""

    @pytest.mark.parametrize("cmd", FICTION_GOV_COMMANDS)
    def test_fiction_gov_command(self, cmd: str) -> None:
        """Each fiction-gov command should parse and not crash."""
        try:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)
            assert_valid_exit_code(code, cmd)
        except FileNotFoundError:
            pytest.skip(f"fiction-gov not installed: {cmd}")


class TestNonfictionGovCLISmoke:
    """Smoke tests for nonfiction-gov CLI commands."""

    @pytest.mark.parametrize("cmd", NONFICTION_GOV_COMMANDS)
    def test_nonfiction_gov_command(self, cmd: str) -> None:
        """Each nonfiction-gov command should parse and not crash."""
        try:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)
            assert_valid_exit_code(code, cmd)
        except FileNotFoundError:
            pytest.skip(f"nonfiction-gov not installed: {cmd}")


class TestOpsGovCLISmoke:
    """Smoke tests for ops-gov CLI commands."""

    @pytest.mark.parametrize("cmd", OPS_GOV_COMMANDS)
    def test_ops_gov_command(self, cmd: str) -> None:
        """Each ops-gov command should parse and not crash."""
        try:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)
            assert_valid_exit_code(code, cmd)
        except FileNotFoundError:
            pytest.skip(f"ops-gov not installed: {cmd}")


# =============================================================================
# Subcommand Depth Tests
# =============================================================================


class TestGovernorSubcommandDepth:
    """Test subcommand hierarchies work correctly."""

    def test_session_subcommands(self) -> None:
        """Session subcommands should all work."""
        subcommands = [
            "governor session create --help",
            "governor session list --help",
            "governor session resume --help",
            "governor session show --help",
            "governor session fork --help",
            "governor session checkpoint --help",
            "governor session checkpoints --help",
            "governor session promote --help",
            "governor session delete --help",
        ]
        for cmd in subcommands:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)

    def test_continuity_subcommands(self) -> None:
        """Continuity subcommands should all work."""
        subcommands = [
            "governor continuity status --help",
            "governor continuity anchor --help",
            "governor continuity check --help",
            "governor continuity import --help",
        ]
        for cmd in subcommands:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)

    def test_epistemic_subcommands(self) -> None:
        """Epistemic subcommands should all work."""
        subcommands = [
            "governor epistemic status --help",
            "governor epistemic claims --help",
            "governor epistemic create --help",
            "governor epistemic evidence --help",
        ]
        for cmd in subcommands:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)

    def test_external_subcommands(self) -> None:
        """External subcommands should all work."""
        subcommands = [
            "governor external query --help",
            "governor external attach --help",
            "governor external bindings --help",
            "governor external discrepancies --help",
            "governor external resolve --help",
            "governor external substrates --help",
        ]
        for cmd in subcommands:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)

    def test_interferometry_subcommands(self) -> None:
        """Interferometry subcommands should all work."""
        subcommands = [
            "governor interferometry run --help",
            "governor interferometry results --help",
            "governor interferometry divergence --help",
            "governor interferometry accept --help",
        ]
        for cmd in subcommands:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)


# =============================================================================
# Edge Cases
# =============================================================================


class TestCLIEdgeCases:
    """Test CLI edge cases and error handling."""

    def test_unknown_command(self) -> None:
        """Unknown commands should fail gracefully."""
        code, stdout, stderr = run_cli_command("governor nonexistent-command")
        # Should not crash with traceback
        assert "Traceback" not in stderr
        # Should return error code
        assert code != 0

    def test_missing_required_args(self) -> None:
        """Missing required args should show usage, not crash."""
        # Commands that require arguments
        commands = [
            "governor verify",  # Needs proposal ID
            "governor apply",   # Needs proposal ID
        ]
        for cmd in commands:
            code, stdout, stderr = run_cli_command(cmd)
            assert_no_traceback(stderr, cmd)
            # Should show usage or error, not crash
            assert code in {1, 2}

    def test_invalid_options(self) -> None:
        """Invalid options should show error, not crash."""
        code, stdout, stderr = run_cli_command("governor --invalid-option-xyz")
        assert "Traceback" not in stderr
        assert code != 0
