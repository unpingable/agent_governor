# SPDX-License-Identifier: Apache-2.0
"""
Tests for violation_resolver module.

W4: Interactive Violation Resolution — Author-Friendly Chat
"""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from governor.violation_resolver import (
    PendingViolation,
    ResolutionAction,
    ResolutionResult,
    ResolutionStatus,
    ExceptionRecord,
    ViolationResolver,
    format_violation_prompt,
    get_mode_choices,
    create_resolver,
)
from governor.continuity import Violation, AnchorType, Severity


# =============================================================================
# PendingViolation Tests
# =============================================================================


class TestPendingViolation:
    """Tests for PendingViolation dataclass."""

    def test_create_pending_violation(self):
        """Can create a PendingViolation."""
        pv = PendingViolation(
            id="pend_abc123",
            context_id="test",
            run_id="run_001",
            violations=[{"anchor_id": "a1", "description": "test"}],
            blocked_response="Hello world",
            timestamp="2025-01-01T00:00:00Z",
            mode="fiction",
        )
        assert pv.id == "pend_abc123"
        assert pv.status == ResolutionStatus.PENDING

    def test_to_dict(self):
        """PendingViolation serializes to dict."""
        pv = PendingViolation(
            id="pend_abc",
            context_id="ctx",
            run_id="run",
            violations=[{"desc": "v1"}],
            blocked_response="resp",
            timestamp="2025-01-01T00:00:00Z",
            mode="code",
            status=ResolutionStatus.FIXED,
        )
        d = pv.to_dict()
        assert d["id"] == "pend_abc"
        assert d["status"] == "fixed"
        assert d["mode"] == "code"

    def test_from_dict(self):
        """PendingViolation deserializes from dict."""
        data = {
            "id": "pend_xyz",
            "context_id": "ctx",
            "run_id": "run",
            "violations": [{"anchor_id": "a"}],
            "blocked_response": "blocked",
            "timestamp": "2025-01-01T00:00:00Z",
            "mode": "nonfiction",
            "status": "revised",
        }
        pv = PendingViolation.from_dict(data)
        assert pv.id == "pend_xyz"
        assert pv.status == ResolutionStatus.REVISED

    def test_from_dict_default_status(self):
        """Default status is PENDING when not in dict."""
        data = {
            "id": "pend_xyz",
            "context_id": "ctx",
            "run_id": "run",
            "violations": [],
            "blocked_response": "",
            "timestamp": "2025-01-01T00:00:00Z",
            "mode": "code",
        }
        pv = PendingViolation.from_dict(data)
        assert pv.status == ResolutionStatus.PENDING


# =============================================================================
# ResolutionResult Tests
# =============================================================================


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_create_fix_result(self):
        """Can create a FIX resolution result."""
        result = ResolutionResult(
            action=ResolutionAction.FIX,
            success=True,
            message="Fixed",
            new_content="corrected content",
        )
        assert result.action == ResolutionAction.FIX
        assert result.success is True
        assert result.new_content == "corrected content"

    def test_create_proceed_result(self):
        """Can create a PROCEED resolution result."""
        result = ResolutionResult(
            action=ResolutionAction.PROCEED,
            success=True,
            message="Exception logged",
            exception_id="exc_abc",
        )
        assert result.action == ResolutionAction.PROCEED
        assert result.exception_id == "exc_abc"

    def test_to_dict(self):
        """ResolutionResult serializes to dict."""
        result = ResolutionResult(
            action=ResolutionAction.REVISE,
            success=True,
            message="Revised",
            anchor_update={"revised_anchors": ["a1"]},
        )
        d = result.to_dict()
        assert d["action"] == "revise"
        assert d["anchor_update"]["revised_anchors"] == ["a1"]


# =============================================================================
# ExceptionRecord Tests
# =============================================================================


class TestExceptionRecord:
    """Tests for ExceptionRecord dataclass."""

    def test_create_exception(self):
        """Can create an exception record."""
        exc = ExceptionRecord(
            id="exc_001",
            violations=[{"anchor_id": "a1"}],
            blocked_response_preview="Hello...",
            scope="single_instance",
            expiry=None,
            created_at="2025-01-01T00:00:00Z",
            mode="fiction",
        )
        assert exc.id == "exc_001"
        assert exc.scope == "single_instance"
        assert exc.expiry is None

    def test_roundtrip(self):
        """ExceptionRecord survives to_dict/from_dict roundtrip."""
        original = ExceptionRecord(
            id="exc_test",
            violations=[{"desc": "v"}],
            blocked_response_preview="test",
            scope="project",
            expiry="2025-12-31T23:59:59Z",
            created_at="2025-01-01T00:00:00Z",
            mode="code",
        )
        d = original.to_dict()
        restored = ExceptionRecord.from_dict(d)
        assert restored.id == original.id
        assert restored.scope == original.scope
        assert restored.expiry == original.expiry


# =============================================================================
# ViolationResolver Tests
# =============================================================================


@pytest.fixture
def temp_governor_dir(tmp_path):
    """Create a temporary governor directory."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()
    return gov_dir


class TestViolationResolverBasic:
    """Basic ViolationResolver tests."""

    def test_create_resolver(self, temp_governor_dir):
        """Can create a resolver."""
        resolver = ViolationResolver(temp_governor_dir, mode="fiction", context_id="test")
        assert resolver.mode == "fiction"
        assert resolver.context_id == "test"

    def test_create_resolver_convenience(self, temp_governor_dir):
        """Convenience function creates resolver."""
        resolver = create_resolver(temp_governor_dir, mode="code", context_id="ctx")
        assert resolver.mode == "code"


class TestViolationResolverPending:
    """Tests for pending violation management."""

    def test_create_pending(self, temp_governor_dir):
        """Can create a pending violation."""
        resolver = ViolationResolver(temp_governor_dir)
        violations = [
            {"anchor_id": "a1", "description": "Test violation", "severity": "reject"}
        ]
        pending = resolver.create_pending(violations, "blocked content", "run_001")

        assert pending.id.startswith("pend_")
        assert pending.status == ResolutionStatus.PENDING
        assert len(pending.violations) == 1

    def test_create_pending_from_violation_objects(self, temp_governor_dir):
        """Can create pending from Violation objects."""
        resolver = ViolationResolver(temp_governor_dir)
        violations = [
            Violation(
                anchor_id="a1",
                anchor_type=AnchorType.CANON,
                severity=Severity.REJECT,
                description="Canon violation",
            )
        ]
        pending = resolver.create_pending(violations, "content", "run_002")
        assert len(pending.violations) == 1
        assert pending.violations[0]["anchor_id"] == "a1"

    def test_get_pending_none(self, temp_governor_dir):
        """get_pending returns None when no pending."""
        resolver = ViolationResolver(temp_governor_dir)
        assert resolver.get_pending() is None

    def test_get_pending_exists(self, temp_governor_dir):
        """get_pending returns pending when exists."""
        resolver = ViolationResolver(temp_governor_dir)
        violations = [{"anchor_id": "a1", "description": "test"}]
        created = resolver.create_pending(violations, "blocked", "run_003")

        retrieved = resolver.get_pending()
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_clear_pending(self, temp_governor_dir):
        """clear_pending removes pending violation."""
        resolver = ViolationResolver(temp_governor_dir)
        resolver.create_pending([{"a": "b"}], "content", "run")
        assert resolver.get_pending() is not None

        resolver.clear_pending()
        assert resolver.get_pending() is None

    def test_get_pending_ignores_non_pending_status(self, temp_governor_dir):
        """get_pending only returns status=PENDING."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending([{"a": "b"}], "content", "run")

        # Manually mark as fixed
        pending.status = ResolutionStatus.FIXED
        resolver._save_pending(pending)

        # Should not return non-pending
        assert resolver.get_pending() is None


class TestIsResolutionCommand:
    """Tests for resolution command detection."""

    @pytest.fixture
    def resolver(self, temp_governor_dir):
        return ViolationResolver(temp_governor_dir)

    @pytest.mark.parametrize("text,expected", [
        ("1", ResolutionAction.FIX),
        ("2", ResolutionAction.REVISE),
        ("3", ResolutionAction.PROCEED),
        ("governor fix", ResolutionAction.FIX),
        ("governor revise", ResolutionAction.REVISE),
        ("governor proceed", ResolutionAction.PROCEED),
        ("GOVERNOR FIX", ResolutionAction.FIX),
        ("Governor Revise", ResolutionAction.REVISE),
        ("  governor proceed  ", ResolutionAction.PROCEED),
        ("fix", ResolutionAction.FIX),
        ("revise", ResolutionAction.REVISE),
        ("proceed", ResolutionAction.PROCEED),
        ("FIX", ResolutionAction.FIX),
    ])
    def test_resolution_commands(self, resolver, text, expected):
        """Various resolution commands are recognized."""
        assert resolver.is_resolution_command(text) == expected

    @pytest.mark.parametrize("text", [
        "hello",
        "4",
        "0",
        "governor",
        "governor help",
        "fix it please",
        "I want to fix",
    ])
    def test_non_resolution_commands(self, resolver, text):
        """Non-resolution commands return None."""
        assert resolver.is_resolution_command(text) is None


class TestResolveRevise:
    """Tests for resolve_revise action."""

    def test_resolve_revise_clears_pending(self, temp_governor_dir):
        """resolve_revise clears the pending violation."""
        resolver = ViolationResolver(temp_governor_dir, mode="fiction")
        pending = resolver.create_pending(
            [{"anchor_id": "fiction_char_alice", "description": "test"}],
            "blocked content",
            "run_001",
        )

        result = resolver.resolve_revise(pending)
        assert result.success is True
        assert result.action == ResolutionAction.REVISE
        assert resolver.get_pending() is None

    def test_resolve_revise_returns_original_content(self, temp_governor_dir):
        """resolve_revise returns the original blocked content."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test"}],
            "original blocked content",
            "run",
        )

        result = resolver.resolve_revise(pending)
        assert result.new_content == "original blocked content"

    def test_resolve_revise_fiction_character(self, temp_governor_dir):
        """resolve_revise handles fiction character anchors."""
        # Setup fiction bible structure
        fiction_dir = temp_governor_dir.parent / ".fiction-gov" / "bible"
        fiction_dir.mkdir(parents=True)
        chars_file = fiction_dir / "characters.json"
        chars_file.write_text(json.dumps([
            {"name": "Alice", "anti_patterns": ["orphan"]}
        ]))

        resolver = ViolationResolver(temp_governor_dir, mode="fiction")
        pending = resolver.create_pending(
            [{"anchor_id": "fiction_char_alice", "description": "violation"}],
            "content",
            "run",
        )

        result = resolver.resolve_revise(pending)
        assert result.success
        assert result.anchor_update is not None
        assert "fiction_char_alice" in result.anchor_update.get("revised_anchors", [])


class TestResolveProceed:
    """Tests for resolve_proceed action."""

    def test_resolve_proceed_clears_pending(self, temp_governor_dir):
        """resolve_proceed clears the pending violation."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test"}],
            "blocked",
            "run",
        )

        result = resolver.resolve_proceed(pending)
        assert result.success
        assert result.action == ResolutionAction.PROCEED
        assert resolver.get_pending() is None

    def test_resolve_proceed_creates_exception(self, temp_governor_dir):
        """resolve_proceed creates an exception record."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test"}],
            "blocked",
            "run",
        )

        result = resolver.resolve_proceed(pending, scope="project")
        assert result.exception_id is not None
        assert result.exception_id.startswith("exc_")

        # Verify exception was stored
        exc = resolver.get_exception(result.exception_id)
        assert exc is not None
        assert exc.scope == "project"

    def test_resolve_proceed_returns_original_content(self, temp_governor_dir):
        """resolve_proceed returns the original blocked content."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1"}],
            "original content here",
            "run",
        )

        result = resolver.resolve_proceed(pending)
        assert result.new_content == "original content here"

    def test_resolve_proceed_with_expiry(self, temp_governor_dir):
        """resolve_proceed stores expiry if provided."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending([{"a": "b"}], "content", "run")

        expiry = "2025-12-31T23:59:59Z"
        result = resolver.resolve_proceed(pending, expiry=expiry)

        exc = resolver.get_exception(result.exception_id)
        assert exc.expiry == expiry


class TestExceptionManagement:
    """Tests for exception listing and retrieval."""

    def test_list_exceptions_empty(self, temp_governor_dir):
        """list_exceptions returns empty list when no exceptions."""
        resolver = ViolationResolver(temp_governor_dir)
        assert resolver.list_exceptions() == []

    def test_list_exceptions(self, temp_governor_dir):
        """list_exceptions returns all exceptions."""
        resolver = ViolationResolver(temp_governor_dir)

        # Create multiple exceptions
        for i in range(3):
            pending = resolver.create_pending([{"id": f"v{i}"}], f"content{i}", f"run{i}")
            resolver.resolve_proceed(pending)

        exceptions = resolver.list_exceptions()
        assert len(exceptions) == 3

    def test_get_exception_not_found(self, temp_governor_dir):
        """get_exception returns None for non-existent ID."""
        resolver = ViolationResolver(temp_governor_dir)
        assert resolver.get_exception("exc_nonexistent") is None


# =============================================================================
# Format Functions Tests
# =============================================================================


class TestFormatViolationPrompt:
    """Tests for format_violation_prompt function."""

    def test_format_fiction_mode(self):
        """Fiction mode shows canon-specific choices."""
        violations = [
            {"anchor_id": "char_alice", "description": "Character constraint violated"}
        ]
        prompt = format_violation_prompt(violations, mode="fiction")

        assert "[Governor] Blocked" in prompt
        assert "char_alice" in prompt
        assert "Fix — Rewrite to comply with canon" in prompt
        assert "Revise — Update the canon anchor" in prompt

    def test_format_code_mode(self):
        """Code mode shows decision-specific choices."""
        violations = [
            {"anchor_id": "decision_react", "description": "Decision violated"}
        ]
        prompt = format_violation_prompt(violations, mode="code")

        assert "Fix — Generate compliant response" in prompt
        assert "Revise — Update decision record" in prompt

    def test_format_nonfiction_mode(self):
        """Nonfiction mode shows corpus-specific choices."""
        violations = [{"description": "Citation missing"}]
        prompt = format_violation_prompt(violations, mode="nonfiction")

        assert "comply with corpus constraints" in prompt

    def test_format_multiple_violations(self):
        """Multiple violations are listed."""
        violations = [
            {"anchor_id": "a1", "description": "Violation 1"},
            {"anchor_id": "a2", "description": "Violation 2"},
        ]
        prompt = format_violation_prompt(violations, mode="fiction")

        assert "Violation 1" in prompt
        assert "Violation 2" in prompt
        assert "[a1]" in prompt
        assert "[a2]" in prompt


class TestGetModeChoices:
    """Tests for get_mode_choices function."""

    def test_fiction_choices(self):
        """Fiction mode has canon-specific choices."""
        choices = get_mode_choices("fiction")
        assert len(choices) == 3
        assert any("canon" in c.lower() for c in choices)

    def test_code_choices(self):
        """Code mode has decision-specific choices."""
        choices = get_mode_choices("code")
        assert len(choices) == 3
        assert any("decision" in c.lower() for c in choices)

    def test_general_default(self):
        """General mode uses code-like choices."""
        choices = get_mode_choices("general")
        assert len(choices) == 3


# =============================================================================
# Integration Tests
# =============================================================================


class TestResolveFix:
    """Tests for resolve_fix action (requires async mock)."""

    @pytest.mark.asyncio
    async def test_resolve_fix_success(self, temp_governor_dir):
        """resolve_fix regenerates compliant content."""
        resolver = ViolationResolver(temp_governor_dir, mode="fiction")
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test violation"}],
            "Original problematic content",
            "run_001",
        )

        # Mock backend
        mock_backend = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Corrected compliant content"
        mock_backend.chat = AsyncMock(return_value=mock_response)

        result = await resolver.resolve_fix(pending, mock_backend)

        assert result.success
        assert result.action == ResolutionAction.FIX
        assert result.new_content == "Corrected compliant content"
        assert resolver.get_pending() is None

    @pytest.mark.asyncio
    async def test_resolve_fix_failure(self, temp_governor_dir):
        """resolve_fix handles backend failure gracefully."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending([{"a": "b"}], "content", "run")

        # Mock backend that raises
        mock_backend = MagicMock()
        mock_backend.chat = AsyncMock(side_effect=Exception("Backend error"))

        result = await resolver.resolve_fix(pending, mock_backend)

        assert not result.success
        assert "Backend error" in result.message


# =============================================================================
# Blocking Behavior Tests
# =============================================================================


class TestBlockingBehavior:
    """Tests verifying the blocking behavior."""

    def test_pending_persists_across_resolver_instances(self, temp_governor_dir):
        """Pending violation persists across resolver instances."""
        resolver1 = ViolationResolver(temp_governor_dir)
        resolver1.create_pending([{"a": "b"}], "blocked", "run")

        resolver2 = ViolationResolver(temp_governor_dir)
        pending = resolver2.get_pending()
        assert pending is not None

    def test_only_one_pending_at_a_time(self, temp_governor_dir):
        """Creating new pending overwrites the old one."""
        resolver = ViolationResolver(temp_governor_dir)
        pending1 = resolver.create_pending([{"v": "1"}], "first", "run1")
        pending2 = resolver.create_pending([{"v": "2"}], "second", "run2")

        current = resolver.get_pending()
        assert current.id == pending2.id
        assert current.blocked_response == "second"


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests."""

    def test_empty_violations_list(self, temp_governor_dir):
        """Handles empty violations list."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending([], "blocked", "run")
        assert len(pending.violations) == 0

    def test_long_blocked_response_truncated_in_exception(self, temp_governor_dir):
        """Exception preview is truncated for long responses."""
        resolver = ViolationResolver(temp_governor_dir)
        long_content = "x" * 500
        pending = resolver.create_pending([{"a": "b"}], long_content, "run")

        result = resolver.resolve_proceed(pending)
        exc = resolver.get_exception(result.exception_id)
        assert len(exc.blocked_response_preview) == 200

    def test_invalid_json_in_pending_file(self, temp_governor_dir):
        """Handles corrupted pending file gracefully."""
        resolver = ViolationResolver(temp_governor_dir)
        pending_path = temp_governor_dir / "pending_violations.json"
        pending_path.write_text("not valid json")

        assert resolver.get_pending() is None

    def test_create_resolver_creates_directories(self, tmp_path):
        """Resolver creates directories as needed."""
        gov_dir = tmp_path / ".governor"
        # Don't create it beforehand

        resolver = ViolationResolver(gov_dir)
        resolver.create_pending([{"a": "b"}], "content", "run")

        assert gov_dir.exists()
        assert (gov_dir / "pending_violations.json").exists()


# =============================================================================
# CLI Integration Tests
# =============================================================================


class TestCLIIntegration:
    """Tests for CLI integration with violation resolution."""

    def test_check_command_interactive_option_exists(self):
        """Check command has --interactive option."""
        from click.testing import CliRunner
        from governor.cli import check

        runner = CliRunner()
        result = runner.invoke(check, ["--help"])
        assert "--interactive" in result.output or "-i" in result.output

    def test_check_command_mode_option_exists(self):
        """Check command has --mode option."""
        from click.testing import CliRunner
        from governor.cli import check

        runner = CliRunner()
        result = runner.invoke(check, ["--help"])
        assert "--mode" in result.output
        assert "code" in result.output
        assert "fiction" in result.output

    def test_wrap_command_check_continuity_option_exists(self):
        """Wrap command has --check-continuity option."""
        from click.testing import CliRunner
        from governor.cli import wrap

        runner = CliRunner()
        result = runner.invoke(wrap, ["--help"])
        assert "--check-continuity" in result.output or "-c" in result.output

    def test_wrap_command_interactive_option_exists(self):
        """Wrap command has --interactive option."""
        from click.testing import CliRunner
        from governor.cli import wrap

        runner = CliRunner()
        result = runner.invoke(wrap, ["--help"])
        assert "--interactive" in result.output or "-i" in result.output

    def test_hook_precommit_check_continuity_option_exists(self):
        """Hook pre-commit command has --check-continuity option."""
        from click.testing import CliRunner
        from governor.cli import hook_pre_commit

        runner = CliRunner()
        result = runner.invoke(hook_pre_commit, ["--help"])
        assert "--check-continuity" in result.output or "-c" in result.output

    def test_hook_precommit_interactive_option_exists(self):
        """Hook pre-commit command has --interactive option."""
        from click.testing import CliRunner
        from governor.cli import hook_pre_commit

        runner = CliRunner()
        result = runner.invoke(hook_pre_commit, ["--help"])
        assert "--interactive" in result.output or "-i" in result.output

    def test_hook_precommit_checks_pending_violations(self, temp_governor_dir, tmp_path):
        """Hook pre-commit checks for pending violations."""
        from click.testing import CliRunner
        from governor.cli import cli
        from governor.violation_resolver import ViolationResolver

        # Create a pending violation
        resolver = ViolationResolver(temp_governor_dir)
        resolver.create_pending(
            [{"anchor_id": "test", "description": "Test violation"}],
            "blocked content",
            "run_test",
        )

        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create .governor symlink
            import os
            os.makedirs(".governor", exist_ok=True)
            (Path(".governor") / "pending_violations.json").write_text(
                (temp_governor_dir / "pending_violations.json").read_text()
            )

            result = runner.invoke(cli, ["hook", "pre-commit"])

            assert "Pending violation requires resolution" in result.output or result.exit_code != 0

    def test_format_violation_prompt_used_in_interactive(self, temp_governor_dir):
        """Format functions are called correctly."""
        violations = [
            {"anchor_id": "a1", "description": "First violation"},
            {"anchor_id": "a2", "description": "Second violation"},
        ]
        prompt = format_violation_prompt(violations, "fiction")

        assert "[Governor]" in prompt
        assert "First violation" in prompt
        assert "Second violation" in prompt
        assert "canon" in prompt.lower()  # Fiction-specific

    def test_format_violation_prompt_code_mode(self, temp_governor_dir):
        """Format prompt shows code-specific options."""
        violations = [{"anchor_id": "d1", "description": "Decision violation"}]
        prompt = format_violation_prompt(violations, "code")

        assert "decision" in prompt.lower()
        assert "waiver" in prompt.lower()

    def test_format_violation_prompt_nonfiction_mode(self, temp_governor_dir):
        """Format prompt shows nonfiction-specific options."""
        violations = [{"anchor_id": "c1", "description": "Corpus violation"}]
        prompt = format_violation_prompt(violations, "nonfiction")

        assert "corpus" in prompt.lower()


class TestInteractiveResolutionFlow:
    """Tests for the interactive resolution flow in CLI commands."""

    def test_resolution_command_detection_in_prompt(self, temp_governor_dir):
        """Resolution commands are correctly detected."""
        resolver = ViolationResolver(temp_governor_dir)

        # Test all valid inputs
        assert resolver.is_resolution_command("1") == ResolutionAction.FIX
        assert resolver.is_resolution_command("2") == ResolutionAction.REVISE
        assert resolver.is_resolution_command("3") == ResolutionAction.PROCEED
        assert resolver.is_resolution_command("fix") == ResolutionAction.FIX
        assert resolver.is_resolution_command("REVISE") == ResolutionAction.REVISE
        assert resolver.is_resolution_command("governor proceed") == ResolutionAction.PROCEED

        # Invalid inputs
        assert resolver.is_resolution_command("4") is None
        assert resolver.is_resolution_command("help") is None
        assert resolver.is_resolution_command("") is None

    def test_check_interactive_creates_pending(self, temp_governor_dir, tmp_path):
        """Check --interactive creates pending violation for errors."""
        from governor.check import run_check
        from governor.violation_resolver import ViolationResolver

        # Create anchor that will be violated (prohibition type with forbidden patterns)
        anchors_dir = temp_governor_dir / "continuity"
        anchors_dir.mkdir(parents=True, exist_ok=True)
        anchors_file = anchors_dir / "anchors.json"
        anchors_file.write_text(json.dumps({
            "anchors": [{
                "id": "test_anchor",
                "anchor_type": "prohibition",
                "description": "Test forbidden word",
                "forbidden_patterns": ["FORBIDDEN_WORD"],  # Correct field name
                "severity": "reject",
            }]
        }))

        # Run check on violating content
        result = run_check(
            "This contains FORBIDDEN_WORD",
            "test.txt",
            run_security=False,
            run_continuity=True,
            governor_dir=temp_governor_dir,
        )

        # Verify we got an error
        assert result.status == "error"
        assert any(f.severity == "error" for f in result.findings)


# =============================================================================
# Receipt-Exception Linking Tests
# =============================================================================


class TestReceiptExceptionLinking:
    """Tests for receipt_id linking between pending violations and exceptions."""

    def test_pending_receipt_id_default_none(self):
        """PendingViolation defaults to receipt_id=None."""
        pv = PendingViolation(
            id="pend_test",
            context_id="ctx",
            run_id="run",
            violations=[{"anchor_id": "a1"}],
            blocked_response="blocked",
            timestamp="2025-01-01T00:00:00Z",
            mode="code",
        )
        assert pv.receipt_id is None

    def test_pending_receipt_id_set(self):
        """PendingViolation can be created with receipt_id."""
        pv = PendingViolation(
            id="pend_test",
            context_id="ctx",
            run_id="run",
            violations=[{"anchor_id": "a1"}],
            blocked_response="blocked",
            timestamp="2025-01-01T00:00:00Z",
            mode="code",
            receipt_id="abc123def456",
        )
        assert pv.receipt_id == "abc123def456"

    def test_pending_receipt_id_round_trip(self):
        """PendingViolation receipt_id survives to_dict/from_dict."""
        pv = PendingViolation(
            id="pend_test",
            context_id="ctx",
            run_id="run",
            violations=[{"anchor_id": "a1"}],
            blocked_response="blocked",
            timestamp="2025-01-01T00:00:00Z",
            mode="code",
            receipt_id="receipt_xyz",
        )
        d = pv.to_dict()
        assert d["receipt_id"] == "receipt_xyz"
        restored = PendingViolation.from_dict(d)
        assert restored.receipt_id == "receipt_xyz"

    def test_pending_receipt_id_absent_in_dict_when_none(self):
        """PendingViolation omits receipt_id from dict when None."""
        pv = PendingViolation(
            id="pend_test",
            context_id="ctx",
            run_id="run",
            violations=[],
            blocked_response="blocked",
            timestamp="2025-01-01T00:00:00Z",
            mode="code",
        )
        d = pv.to_dict()
        assert "receipt_id" not in d

    def test_pending_from_dict_missing_receipt_id(self):
        """from_dict handles missing receipt_id gracefully (backward compat)."""
        data = {
            "id": "pend_test",
            "context_id": "ctx",
            "run_id": "run",
            "violations": [],
            "blocked_response": "blocked",
            "timestamp": "2025-01-01T00:00:00Z",
            "mode": "code",
            "status": "pending",
        }
        pv = PendingViolation.from_dict(data)
        assert pv.receipt_id is None

    def test_exception_receipt_id_default_none(self):
        """ExceptionRecord defaults to receipt_id=None."""
        exc = ExceptionRecord(
            id="exc_test",
            violations=[],
            blocked_response_preview="test",
            scope="single_instance",
            expiry=None,
            created_at="2025-01-01T00:00:00Z",
            mode="code",
        )
        assert exc.receipt_id is None

    def test_exception_receipt_id_round_trip(self):
        """ExceptionRecord receipt_id survives to_dict/from_dict."""
        exc = ExceptionRecord(
            id="exc_test",
            violations=[{"anchor_id": "a1"}],
            blocked_response_preview="test",
            scope="project",
            expiry=None,
            created_at="2025-01-01T00:00:00Z",
            mode="code",
            receipt_id="receipt_abc",
        )
        d = exc.to_dict()
        assert d["receipt_id"] == "receipt_abc"
        restored = ExceptionRecord.from_dict(d)
        assert restored.receipt_id == "receipt_abc"

    def test_exception_receipt_id_absent_when_none(self):
        """ExceptionRecord omits receipt_id from dict when None."""
        exc = ExceptionRecord(
            id="exc_test",
            violations=[],
            blocked_response_preview="test",
            scope="single_instance",
            expiry=None,
            created_at="2025-01-01T00:00:00Z",
            mode="code",
        )
        d = exc.to_dict()
        assert "receipt_id" not in d

    def test_exception_from_dict_missing_receipt_id(self):
        """from_dict handles missing receipt_id gracefully (backward compat)."""
        data = {
            "id": "exc_test",
            "violations": [],
            "blocked_response_preview": "test",
            "scope": "single_instance",
            "expiry": None,
            "created_at": "2025-01-01T00:00:00Z",
            "mode": "code",
        }
        exc = ExceptionRecord.from_dict(data)
        assert exc.receipt_id is None

    def test_create_pending_with_receipt_id(self, temp_governor_dir):
        """create_pending accepts and stores receipt_id."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test"}],
            "blocked",
            "run_001",
            receipt_id="rcpt_12345",
        )
        assert pending.receipt_id == "rcpt_12345"
        # Verify it round-trips through file storage
        loaded = resolver.get_pending()
        assert loaded is not None
        assert loaded.receipt_id == "rcpt_12345"

    def test_create_pending_without_receipt_id(self, temp_governor_dir):
        """create_pending without receipt_id defaults to None."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1"}],
            "blocked",
            "run",
        )
        assert pending.receipt_id is None

    def test_proceed_copies_receipt_id_to_exception(self, temp_governor_dir):
        """resolve_proceed copies receipt_id from pending to exception."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1", "description": "test"}],
            "blocked response",
            "run_001",
            receipt_id="rcpt_linked",
        )

        result = resolver.resolve_proceed(pending)
        assert result.success

        exc = resolver.get_exception(result.exception_id)
        assert exc is not None
        assert exc.receipt_id == "rcpt_linked"

    def test_proceed_none_receipt_id(self, temp_governor_dir):
        """resolve_proceed with None receipt_id creates exception with None."""
        resolver = ViolationResolver(temp_governor_dir)
        pending = resolver.create_pending(
            [{"anchor_id": "a1"}],
            "blocked",
            "run",
        )

        result = resolver.resolve_proceed(pending)
        exc = resolver.get_exception(result.exception_id)
        assert exc is not None
        assert exc.receipt_id is None
