"""Tests for the unified check aggregation module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from governor.check import (
    Position,
    Range,
    CheckFinding,
    CheckResult,
    security_finding_to_check,
    continuity_violation_to_check,
    run_check,
    _locate_pattern_in_text,
)


# =============================================================================
# CheckFinding / CheckResult serialization
# =============================================================================


class TestSerialization:
    """Test to_dict output shapes."""

    def test_check_finding_to_dict_all_fields(self):
        f = CheckFinding(
            code="SECURITY.SECRET_LEAK",
            message="API key detected",
            severity="error",
            source="security",
            range=Range(
                start=Position(line=5, character=0),
                end=Position(line=5, character=30),
            ),
            suggestion="Use environment variables",
        )
        d = f.to_dict()
        assert d["code"] == "SECURITY.SECRET_LEAK"
        assert d["message"] == "API key detected"
        assert d["severity"] == "error"
        assert d["source"] == "security"
        assert d["range"]["start"]["line"] == 5
        assert d["range"]["start"]["character"] == 0
        assert d["range"]["end"]["line"] == 5
        assert d["range"]["end"]["character"] == 30
        assert d["suggestion"] == "Use environment variables"

    def test_check_finding_to_dict_no_suggestion(self):
        f = CheckFinding(
            code="CONTINUITY.PROHIBITION.no-foo",
            message="Forbidden pattern",
            severity="warning",
            source="continuity",
            range=Range(
                start=Position(line=0, character=0),
                end=Position(line=0, character=0),
            ),
        )
        d = f.to_dict()
        assert "suggestion" not in d

    def test_check_result_to_dict(self):
        r = CheckResult(
            status="warn",
            findings=[
                CheckFinding(
                    code="X",
                    message="m",
                    severity="warning",
                    source="security",
                    range=Range(
                        start=Position(line=0, character=0),
                        end=Position(line=0, character=1),
                    ),
                )
            ],
            summary="Found 1 issue(s): 1 warning(s).",
        )
        d = r.to_dict()
        assert d["status"] == "warn"
        assert len(d["findings"]) == 1
        assert d["summary"] == "Found 1 issue(s): 1 warning(s)."

    def test_check_result_json_roundtrip(self):
        r = CheckResult(status="pass", findings=[], summary="No issues found.")
        serialized = json.dumps(r.to_dict())
        parsed = json.loads(serialized)
        assert parsed["status"] == "pass"
        assert parsed["findings"] == []


# =============================================================================
# Security severity mapping
# =============================================================================


class TestSecuritySeverityMapping:
    """Test security finding severity → check severity."""

    def _make_security_finding(self, severity_value: str):
        """Create a mock SecurityFinding."""
        sf = MagicMock()
        sf.line_number = 10
        sf.line_content = "password = 'hunter2'"
        sf.vuln_type.value = "secret_leak"
        sf.severity.value = severity_value
        sf.message = "test"
        sf.suggestion = None
        return sf

    def test_critical_maps_to_error(self):
        sf = self._make_security_finding("critical")
        cf = security_finding_to_check(sf)
        assert cf.severity == "error"

    def test_high_maps_to_error(self):
        sf = self._make_security_finding("high")
        cf = security_finding_to_check(sf)
        assert cf.severity == "error"

    def test_medium_maps_to_warning(self):
        sf = self._make_security_finding("medium")
        cf = security_finding_to_check(sf)
        assert cf.severity == "warning"

    def test_low_maps_to_info(self):
        sf = self._make_security_finding("low")
        cf = security_finding_to_check(sf)
        assert cf.severity == "info"


# =============================================================================
# Continuity severity mapping
# =============================================================================


class TestContinuitySeverityMapping:
    """Test continuity violation severity → check severity."""

    def _make_violation(self, severity_value: str):
        v = MagicMock()
        v.anchor_id = "test-anchor"
        v.anchor_type.value = "prohibition"
        v.severity.value = severity_value
        v.description = "test violation"
        v.evidence = []
        return v

    def test_reject_maps_to_error(self):
        v = self._make_violation("reject")
        cf = continuity_violation_to_check(v, "some text")
        assert cf.severity == "error"

    def test_correct_maps_to_warning(self):
        v = self._make_violation("correct")
        cf = continuity_violation_to_check(v, "some text")
        assert cf.severity == "warning"

    def test_warn_maps_to_info(self):
        v = self._make_violation("warn")
        cf = continuity_violation_to_check(v, "some text")
        assert cf.severity == "info"


# =============================================================================
# security_finding_to_check conversion
# =============================================================================


class TestSecurityFindingToCheck:
    """Test SecurityFinding → CheckFinding conversion."""

    def test_line_number_conversion_1_to_0_based(self):
        sf = MagicMock()
        sf.line_number = 1
        sf.line_content = "x = 1"
        sf.vuln_type.value = "debug_code"
        sf.severity.value = "low"
        sf.message = "Debug code"
        sf.suggestion = None
        cf = security_finding_to_check(sf)
        assert cf.range.start.line == 0
        assert cf.range.end.line == 0

    def test_code_format(self):
        sf = MagicMock()
        sf.line_number = 5
        sf.line_content = "eval(x)"
        sf.vuln_type.value = "command_injection"
        sf.severity.value = "high"
        sf.message = "Potential command injection"
        sf.suggestion = "Use subprocess"
        cf = security_finding_to_check(sf)
        assert cf.code == "SECURITY.COMMAND_INJECTION"

    def test_suggestion_preserved(self):
        sf = MagicMock()
        sf.line_number = 3
        sf.line_content = "os.system(cmd)"
        sf.vuln_type.value = "command_injection"
        sf.severity.value = "high"
        sf.message = "Command injection"
        sf.suggestion = "Use subprocess.run with shell=False"
        cf = security_finding_to_check(sf)
        assert cf.suggestion == "Use subprocess.run with shell=False"

    def test_end_character_matches_line_content_length(self):
        sf = MagicMock()
        sf.line_number = 2
        sf.line_content = "password = 'secret'"
        sf.vuln_type.value = "secret_leak"
        sf.severity.value = "critical"
        sf.message = "Secret"
        sf.suggestion = None
        cf = security_finding_to_check(sf)
        assert cf.range.end.character == len("password = 'secret'")
        assert cf.range.start.character == 0


# =============================================================================
# continuity_violation_to_check conversion
# =============================================================================


class TestContinuityViolationToCheck:
    """Test Violation → CheckFinding conversion."""

    def test_forbidden_pattern_located_in_text(self):
        v = MagicMock()
        v.anchor_id = "no-foo"
        v.anchor_type.value = "prohibition"
        v.severity.value = "reject"
        v.description = "Forbidden pattern found: 'badword'"
        v.evidence = ["Pattern 'badword' matched in output"]

        text = "line one\nline two has badword here\nline three"
        cf = continuity_violation_to_check(v, text)
        assert cf.range.start.line == 1
        assert cf.range.start.character == 13  # "line two has " = 13 chars
        assert cf.range.end.character == 20  # 13 + len("badword") = 20

    def test_missing_pattern_defaults_to_line_0(self):
        v = MagicMock()
        v.anchor_id = "concept-x"
        v.anchor_type.value = "requirement"
        v.severity.value = "correct"
        v.description = "Required concept missing: 'quantum'"
        v.evidence = ["Concept 'quantum' not found in output"]

        text = "no quantum here"
        # 'quantum' is actually in the text here, but let's test with text that doesn't have it
        text_no_match = "nothing relevant"
        cf = continuity_violation_to_check(v, text_no_match)
        assert cf.range.start.line == 0

    def test_code_format(self):
        v = MagicMock()
        v.anchor_id = "char-alice"
        v.anchor_type.value = "canon"
        v.severity.value = "warn"
        v.description = "Canon violation"
        v.evidence = []

        cf = continuity_violation_to_check(v, "text")
        assert cf.code == "CONTINUITY.CANON.char-alice"
        assert cf.source == "continuity"


# =============================================================================
# _locate_pattern_in_text
# =============================================================================


class TestLocatePattern:
    """Test pattern location helper."""

    def test_find_on_first_line(self):
        result = _locate_pattern_in_text("hello world", "hello")
        assert result == (0, 0, 5)

    def test_find_on_second_line(self):
        result = _locate_pattern_in_text("first\nsecond target here", "target")
        assert result == (1, 7, 13)

    def test_not_found(self):
        result = _locate_pattern_in_text("abc def", "xyz")
        assert result is None

    def test_case_insensitive(self):
        result = _locate_pattern_in_text("Hello World", "hello")
        assert result is not None
        assert result[0] == 0


# =============================================================================
# run_check orchestration
# =============================================================================


class TestRunCheck:
    """Test the run_check orchestrator."""

    def test_clean_file_returns_pass(self):
        result = run_check("x = 1 + 2\nprint(x)\n", "test.py")
        assert result.status == "pass"
        assert len(result.findings) == 0
        assert result.summary == "No issues found."

    def test_security_findings_detected(self):
        content = 'api_key = "AKIA1234567890123456"\n'
        result = run_check(content, "config.py")
        assert result.status == "error"
        assert any(f.source == "security" for f in result.findings)

    def test_continuity_findings_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            gov_dir = Path(tmp)
            cont_dir = gov_dir / "continuity"
            cont_dir.mkdir(parents=True)
            anchors_data = {
                "anchors": [
                    {
                        "id": "no-badword",
                        "anchor_type": "prohibition",
                        "description": "No badword allowed",
                        "forbidden_patterns": ["badword"],
                        "severity": "reject",
                    }
                ]
            }
            (cont_dir / "anchors.json").write_text(json.dumps(anchors_data))

            content = "this has badword in it"
            result = run_check(content, "test.txt", governor_dir=gov_dir)
            assert any(f.source == "continuity" for f in result.findings)
            assert result.status == "error"

    def test_both_sources_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            gov_dir = Path(tmp)
            cont_dir = gov_dir / "continuity"
            cont_dir.mkdir(parents=True)
            anchors_data = {
                "anchors": [
                    {
                        "id": "no-badword",
                        "anchor_type": "prohibition",
                        "description": "No badword allowed",
                        "forbidden_patterns": ["badword"],
                        "severity": "warn",
                    }
                ]
            }
            (cont_dir / "anchors.json").write_text(json.dumps(anchors_data))

            content = 'api_key = "AKIA1234567890123456"\nbadword here\n'
            result = run_check(content, "test.py", governor_dir=gov_dir)
            sources = {f.source for f in result.findings}
            assert "security" in sources
            assert "continuity" in sources

    def test_graceful_without_governor_dir(self):
        result = run_check("hello world\n", "test.txt", governor_dir=None)
        assert result.status == "pass"

    def test_no_security_flag(self):
        content = 'api_key = "AKIA1234567890123456"\n'
        result = run_check(content, "config.py", run_security=False)
        assert not any(f.source == "security" for f in result.findings)

    def test_no_continuity_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            gov_dir = Path(tmp)
            cont_dir = gov_dir / "continuity"
            cont_dir.mkdir(parents=True)
            anchors_data = {
                "anchors": [
                    {
                        "id": "no-x",
                        "anchor_type": "prohibition",
                        "description": "No x",
                        "forbidden_patterns": ["forbidden_text_xyz"],
                        "severity": "reject",
                    }
                ]
            }
            (cont_dir / "anchors.json").write_text(json.dumps(anchors_data))

            content = "forbidden_text_xyz is here"
            result = run_check(content, "test.txt", governor_dir=gov_dir, run_continuity=False)
            assert not any(f.source == "continuity" for f in result.findings)


# =============================================================================
# CLI tests
# =============================================================================


class TestCheckCLI:
    """Test the governor check CLI command."""

    def _get_cli(self):
        from governor.cli import cli
        return cli

    def test_file_json_output(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\nprint(x)\n")
            f.flush()
            try:
                runner = CliRunner()
                result = runner.invoke(self._get_cli(), ["check", f.name, "--format", "json"])
                assert result.exit_code == 0
                data = json.loads(result.output)
                assert data["status"] in ("pass", "warn", "error")
                assert "findings" in data
                assert "summary" in data
            finally:
                os.unlink(f.name)

    def test_file_text_output(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("x = 1\n")
            f.flush()
            try:
                runner = CliRunner()
                result = runner.invoke(self._get_cli(), ["check", f.name])
                assert result.exit_code == 0
                assert "No issues found" in result.output or "issue" in result.output.lower()
            finally:
                os.unlink(f.name)

    def test_stdin_json_input(self):
        runner = CliRunner()
        stdin_data = json.dumps({"content": "x = 1\n", "filepath": "test.py"})
        result = runner.invoke(
            self._get_cli(),
            ["check", "--stdin", "--format", "json"],
            input=stdin_data,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "pass"

    def test_no_input_error(self):
        runner = CliRunner()
        result = runner.invoke(self._get_cli(), ["check", "--format", "json"])
        assert result.exit_code != 0

    def test_missing_file_error(self):
        runner = CliRunner()
        result = runner.invoke(
            self._get_cli(),
            ["check", "/nonexistent/file.py", "--format", "json"],
        )
        assert result.exit_code != 0
