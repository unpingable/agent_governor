"""
Tests for Phase A4: Governor adapter invariants.

Thin adapters wrapping domain governors as Invariant objects
for the autonomous executor.
"""

import os
import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from governor.adapters import (
    AdapterFinding,
    AdapterConfig,
    security_invariant,
    cfi_invariant,
    fiction_invariant,
    nonfiction_citation_invariant,
    tone_invariant,
    content_invariant,
    build_adapter_set,
    _read_text_files,
    TEXT_EXTENSIONS,
    PROSE_EXTENSIONS,
    ContentCheckFn,
)
from governor.invariants import (
    Invariant,
    InvariantType,
    InvariantResult,
    InvariantSet,
)


# =============================================================================
# Test helpers: mock governor objects
# =============================================================================


@dataclass
class MockSecurityFinding:
    """Mimics SecurityFinding from governor.security."""

    vuln_type: Any
    severity: Any
    file_path: str
    line_number: int
    line_content: str
    message: str

    def to_dict(self):
        return {
            "vuln_type": self.vuln_type.value if hasattr(self.vuln_type, "value") else str(self.vuln_type),
            "severity": self.severity.value if hasattr(self.severity, "value") else str(self.severity),
            "file_path": self.file_path,
            "line_number": self.line_number,
            "message": self.message,
        }


class MockEnum:
    """Mimics an enum with a .value attribute."""

    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return self.value


class MockSecurityVerifier:
    """Mimics SecurityVerifier from governor.security."""

    def __init__(self, findings_by_file: dict[str, list[MockSecurityFinding]] | None = None):
        self._findings = findings_by_file or {}

    def scan_file(self, path: Path) -> list[MockSecurityFinding]:
        return self._findings.get(str(path), [])


@dataclass
class MockCFIFault:
    """Mimics CFIFault from nonfiction_governor.cfi."""

    fault_type: Any
    detail: str
    frame: Any = None
    severity: str = "warning"

    def to_dict(self):
        return {
            "fault_type": self.fault_type.value if hasattr(self.fault_type, "value") else str(self.fault_type),
            "detail": self.detail,
            "frame": self.frame.value if self.frame and hasattr(self.frame, "value") else None,
        }


@dataclass
class MockCFIResult:
    """Mimics CFICheckResult from nonfiction_governor.cfi."""

    faults: list[MockCFIFault] = field(default_factory=list)
    has_faults: bool = False


class MockCFIDetector:
    """Mimics CFIDetector from nonfiction_governor.cfi."""

    def __init__(self, results_by_content: dict[str, MockCFIResult] | None = None):
        self._results = results_by_content or {}
        self._default = MockCFIResult()

    def check(self, text: str) -> MockCFIResult:
        return self._results.get(text, self._default)


@dataclass
class MockVerificationResult:
    """Mimics nonfiction VerificationResult."""

    valid: bool
    message: str


class MockCitationVerifier:
    """Mimics CitationVerifier from nonfiction_governor.verifiers."""

    def __init__(
        self,
        valid_keys: set[str] | None = None,
        extracted: dict[str, list[str]] | None = None,
    ):
        self._valid = valid_keys or set()
        self._extracted = extracted or {}

    def extract_citations(self, text: str) -> list[str]:
        return self._extracted.get(text, [])

    def verify_citation(self, key: str) -> MockVerificationResult:
        if key in self._valid:
            return MockVerificationResult(valid=True, message="OK")
        return MockVerificationResult(valid=False, message=f"Unknown citation: {key}")


class MockFictionVerifier:
    """Mimics CombinedVerifier from fiction_governor.verifiers."""

    def __init__(self, results_by_content: dict[str, tuple[bool, list[str]]] | None = None):
        self._results = results_by_content or {}

    def quick_check(self, content: str, characters: list[str]) -> tuple[bool, list[str]]:
        return self._results.get(content, (True, []))


@dataclass
class MockToneViolation:
    """Mimics ToneViolation from nonfiction_governor.tone."""

    dimension: str
    message: str
    suggestion: str = ""


@dataclass
class MockToneCheckResult:
    """Mimics ToneCheckResult from nonfiction_governor.tone."""

    valid: bool
    violations: list[MockToneViolation] = field(default_factory=list)


class MockToneChecker:
    """Mimics ToneChecker from nonfiction_governor.tone."""

    def __init__(self, results_by_content: dict[str, MockToneCheckResult] | None = None):
        self._results = results_by_content or {}
        self._default = MockToneCheckResult(valid=True)

    def check(self, text: str) -> MockToneCheckResult:
        return self._results.get(text, self._default)


# =============================================================================
# AdapterFinding tests
# =============================================================================


class TestAdapterFinding:
    def test_create_finding(self):
        f = AdapterFinding(source="test", file_path="foo.py", message="bad")
        assert f.source == "test"
        assert f.file_path == "foo.py"
        assert f.message == "bad"
        assert f.severity == "error"

    def test_to_dict(self):
        f = AdapterFinding(
            source="security",
            file_path="app.py",
            message="SQL injection",
            severity="critical",
            details={"line": 42},
        )
        d = f.to_dict()
        assert d["source"] == "security"
        assert d["file_path"] == "app.py"
        assert d["severity"] == "critical"
        assert d["details"]["line"] == 42

    def test_default_severity(self):
        f = AdapterFinding(source="x", file_path="y", message="z")
        assert f.severity == "error"


# =============================================================================
# _read_text_files tests
# =============================================================================


class TestReadTextFiles:
    def test_reads_existing_text_file(self, tmp_path):
        (tmp_path / "hello.txt").write_text("hello world")
        result = _read_text_files(["hello.txt"], tmp_path)
        assert len(result) == 1
        assert result[0] == ("hello.txt", "hello world")

    def test_skips_nonexistent_file(self, tmp_path):
        result = _read_text_files(["missing.txt"], tmp_path)
        assert result == []

    def test_filters_by_extension(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1")
        (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02")
        result = _read_text_files(["code.py", "data.bin"], tmp_path, {".py"})
        assert len(result) == 1
        assert result[0][0] == "code.py"

    def test_skips_binary_files(self, tmp_path):
        # Write a file with invalid UTF-8
        (tmp_path / "binary.txt").write_bytes(b"\xff\xfe\x00\x01")
        result = _read_text_files(["binary.txt"], tmp_path)
        assert result == []

    def test_reads_multiple_files(self, tmp_path):
        (tmp_path / "a.md").write_text("alpha")
        (tmp_path / "b.md").write_text("beta")
        result = _read_text_files(["a.md", "b.md"], tmp_path)
        assert len(result) == 2

    def test_skips_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        result = _read_text_files(["subdir"], tmp_path)
        assert result == []


# =============================================================================
# Security adapter tests
# =============================================================================


class TestSecurityInvariant:
    def test_no_files_passes(self):
        verifier = MockSecurityVerifier()
        inv = security_invariant(verifier)
        result = inv.check(files_touched=[], root=Path("."))
        assert result.passed

    def test_clean_file_passes(self, tmp_path):
        (tmp_path / "clean.py").write_text("x = 1")
        verifier = MockSecurityVerifier()
        inv = security_invariant(verifier)
        result = inv.check(files_touched=["clean.py"], root=tmp_path)
        assert result.passed

    def test_finding_at_threshold_blocks(self, tmp_path):
        (tmp_path / "bad.py").write_text("password = 'admin'")
        finding = MockSecurityFinding(
            vuln_type=MockEnum("hardcoded_credential"),
            severity=MockEnum("high"),
            file_path="bad.py",
            line_number=1,
            line_content="password = 'admin'",
            message="Hardcoded password",
        )
        verifier = MockSecurityVerifier({str(tmp_path / "bad.py"): [finding]})
        inv = security_invariant(verifier, min_severity="high")
        result = inv.check(files_touched=["bad.py"], root=tmp_path)
        assert not result.passed
        assert "1 finding" in result.message

    def test_finding_below_threshold_passes(self, tmp_path):
        (tmp_path / "ok.py").write_text("import random")
        finding = MockSecurityFinding(
            vuln_type=MockEnum("insecure_random"),
            severity=MockEnum("low"),
            file_path="ok.py",
            line_number=1,
            line_content="import random",
            message="Insecure random",
        )
        verifier = MockSecurityVerifier({str(tmp_path / "ok.py"): [finding]})
        inv = security_invariant(verifier, min_severity="high")
        result = inv.check(files_touched=["ok.py"], root=tmp_path)
        assert result.passed

    def test_critical_severity(self, tmp_path):
        (tmp_path / "leak.py").write_text("key = 'sk-abc123...'")
        finding = MockSecurityFinding(
            vuln_type=MockEnum("secret_leak"),
            severity=MockEnum("critical"),
            file_path="leak.py",
            line_number=1,
            line_content="key = 'sk-abc123...'",
            message="API key exposed",
        )
        verifier = MockSecurityVerifier({str(tmp_path / "leak.py"): [finding]})
        inv = security_invariant(verifier, min_severity="critical")
        result = inv.check(files_touched=["leak.py"], root=tmp_path)
        assert not result.passed

    def test_missing_file_ignored(self, tmp_path):
        verifier = MockSecurityVerifier()
        inv = security_invariant(verifier)
        result = inv.check(files_touched=["nonexistent.py"], root=tmp_path)
        assert result.passed

    def test_invariant_metadata(self):
        verifier = MockSecurityVerifier()
        inv = security_invariant(verifier, invariant_id="sec_check", on_violation="warn")
        assert inv.id == "sec_check"
        assert inv.on_violation == "warn"
        assert inv.type == InvariantType.FORBIDDEN

    def test_multiple_findings(self, tmp_path):
        (tmp_path / "bad.py").write_text("lots of issues")
        findings = [
            MockSecurityFinding(
                vuln_type=MockEnum("sql_injection"),
                severity=MockEnum("high"),
                file_path="bad.py",
                line_number=i,
                line_content="...",
                message=f"Issue {i}",
            )
            for i in range(5)
        ]
        verifier = MockSecurityVerifier({str(tmp_path / "bad.py"): findings})
        inv = security_invariant(verifier)
        result = inv.check(files_touched=["bad.py"], root=tmp_path)
        assert not result.passed
        assert "5 finding" in result.message

    def test_scan_error_ignored(self, tmp_path):
        (tmp_path / "err.py").write_text("code")
        verifier = MockSecurityVerifier()
        verifier.scan_file = MagicMock(side_effect=RuntimeError("scan failed"))
        inv = security_invariant(verifier)
        result = inv.check(files_touched=["err.py"], root=tmp_path)
        assert result.passed  # Error is silently skipped


# =============================================================================
# CFI adapter tests
# =============================================================================


class TestCFIInvariant:
    def test_no_files_passes(self):
        detector = MockCFIDetector()
        inv = cfi_invariant(detector)
        result = inv.check(files_touched=[], root=Path("."))
        assert result.passed

    def test_clean_text_passes(self, tmp_path):
        (tmp_path / "essay.md").write_text("The cat sat on the mat.")
        detector = MockCFIDetector()
        inv = cfi_invariant(detector)
        result = inv.check(files_touched=["essay.md"], root=tmp_path)
        assert result.passed

    def test_fault_detected(self, tmp_path):
        framed_text = "Capitalism drives exploitation."
        (tmp_path / "essay.md").write_text(framed_text)
        fault = MockCFIFault(
            fault_type=MockEnum("uninvited_frame"),
            detail="Uninvited capitalism frame",
            frame=MockEnum("capitalism"),
        )
        detector = MockCFIDetector({framed_text: MockCFIResult(faults=[fault], has_faults=True)})
        inv = cfi_invariant(detector, max_faults=0)
        result = inv.check(files_touched=["essay.md"], root=tmp_path)
        assert not result.passed
        assert "1 fault" in result.message

    def test_faults_within_tolerance(self, tmp_path):
        text = "Some text."
        (tmp_path / "essay.md").write_text(text)
        fault = MockCFIFault(
            fault_type=MockEnum("frame_overuse"),
            detail="Frame overuse",
        )
        detector = MockCFIDetector({text: MockCFIResult(faults=[fault], has_faults=True)})
        inv = cfi_invariant(detector, max_faults=1)
        result = inv.check(files_touched=["essay.md"], root=tmp_path)
        assert result.passed  # 1 fault, tolerance is 1

    def test_default_warn_only(self):
        detector = MockCFIDetector()
        inv = cfi_invariant(detector)
        assert inv.on_violation == "warn"
        assert inv.type == InvariantType.CONSISTENCY

    def test_skips_non_prose_files(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1")
        detector = MockCFIDetector()
        detector.check = MagicMock(return_value=MockCFIResult())
        inv = cfi_invariant(detector)
        result = inv.check(files_touched=["code.py"], root=tmp_path)
        assert result.passed
        detector.check.assert_not_called()

    def test_custom_extensions(self, tmp_path):
        (tmp_path / "doc.py").write_text("text")
        detector = MockCFIDetector({"text": MockCFIResult()})
        inv = cfi_invariant(detector, file_extensions={".py"})
        result = inv.check(files_touched=["doc.py"], root=tmp_path)
        assert result.passed

    def test_multiple_files_faults_accumulate(self, tmp_path):
        text1 = "First essay."
        text2 = "Second essay."
        (tmp_path / "a.md").write_text(text1)
        (tmp_path / "b.md").write_text(text2)
        fault1 = MockCFIFault(fault_type=MockEnum("uninvited_frame"), detail="Frame 1")
        fault2 = MockCFIFault(fault_type=MockEnum("normative_creep"), detail="Frame 2")
        detector = MockCFIDetector({
            text1: MockCFIResult(faults=[fault1], has_faults=True),
            text2: MockCFIResult(faults=[fault2], has_faults=True),
        })
        inv = cfi_invariant(detector, max_faults=0)
        result = inv.check(files_touched=["a.md", "b.md"], root=tmp_path)
        assert not result.passed
        assert "2 fault" in result.message


# =============================================================================
# Fiction adapter tests
# =============================================================================


class TestFictionInvariant:
    def test_no_files_passes(self):
        verifier = MockFictionVerifier()
        inv = fiction_invariant(verifier)
        result = inv.check(files_touched=[], root=Path("."))
        assert result.passed

    def test_clean_content_passes(self, tmp_path):
        content = "She walked into the room."
        (tmp_path / "chapter.md").write_text(content)
        verifier = MockFictionVerifier({content: (True, [])})
        inv = fiction_invariant(verifier)
        result = inv.check(files_touched=["chapter.md"], root=tmp_path)
        assert result.passed

    def test_bad_content_fails(self, tmp_path):
        content = "The character suddenly knew everything."
        (tmp_path / "scene.md").write_text(content)
        verifier = MockFictionVerifier({
            content: (False, ["IN_CHARACTER: Out of character", "TROPE: Deus ex machina"]),
        })
        inv = fiction_invariant(verifier)
        result = inv.check(files_touched=["scene.md"], root=tmp_path)
        assert not result.passed
        assert "2 issue" in result.message

    def test_characters_forwarded(self, tmp_path):
        content = "Dialogue here."
        (tmp_path / "ch.md").write_text(content)
        mock = MagicMock(return_value=(True, []))
        verifier = MockFictionVerifier()
        verifier.quick_check = mock
        inv = fiction_invariant(verifier, characters=["Alice", "Bob"])
        inv.check(files_touched=["ch.md"], root=tmp_path)
        mock.assert_called_once_with(content, ["Alice", "Bob"])

    def test_skips_non_prose(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1")
        mock = MagicMock(return_value=(True, []))
        verifier = MockFictionVerifier()
        verifier.quick_check = mock
        inv = fiction_invariant(verifier)
        inv.check(files_touched=["code.py"], root=tmp_path)
        mock.assert_not_called()

    def test_invariant_metadata(self):
        verifier = MockFictionVerifier()
        inv = fiction_invariant(verifier, invariant_id="fic_gate", on_violation="warn")
        assert inv.id == "fic_gate"
        assert inv.on_violation == "warn"

    def test_multiple_files(self, tmp_path):
        ok = "Good prose."
        bad = "Bad prose."
        (tmp_path / "a.md").write_text(ok)
        (tmp_path / "b.md").write_text(bad)
        verifier = MockFictionVerifier({
            ok: (True, []),
            bad: (False, ["Problem"]),
        })
        inv = fiction_invariant(verifier)
        result = inv.check(files_touched=["a.md", "b.md"], root=tmp_path)
        assert not result.passed


# =============================================================================
# Nonfiction citation adapter tests
# =============================================================================


class TestNonfictionCitationInvariant:
    def test_no_files_passes(self):
        verifier = MockCitationVerifier()
        inv = nonfiction_citation_invariant(verifier)
        result = inv.check(files_touched=[], root=Path("."))
        assert result.passed

    def test_valid_citations_pass(self, tmp_path):
        text = "As shown by [@smith2020]."
        (tmp_path / "paper.md").write_text(text)
        verifier = MockCitationVerifier(
            valid_keys={"smith2020"},
            extracted={text: ["smith2020"]},
        )
        inv = nonfiction_citation_invariant(verifier)
        result = inv.check(files_touched=["paper.md"], root=tmp_path)
        assert result.passed

    def test_invalid_citation_fails(self, tmp_path):
        text = "As shown by [@nobody2024]."
        (tmp_path / "paper.md").write_text(text)
        verifier = MockCitationVerifier(
            valid_keys=set(),
            extracted={text: ["nobody2024"]},
        )
        inv = nonfiction_citation_invariant(verifier)
        result = inv.check(files_touched=["paper.md"], root=tmp_path)
        assert not result.passed
        assert "1 invalid citation" in result.message

    def test_mixed_citations(self, tmp_path):
        text = "[@valid; @invalid]"
        (tmp_path / "doc.md").write_text(text)
        verifier = MockCitationVerifier(
            valid_keys={"valid"},
            extracted={text: ["valid", "invalid"]},
        )
        inv = nonfiction_citation_invariant(verifier)
        result = inv.check(files_touched=["doc.md"], root=tmp_path)
        assert not result.passed

    def test_no_citations_passes(self, tmp_path):
        text = "No citations here."
        (tmp_path / "doc.md").write_text(text)
        verifier = MockCitationVerifier(extracted={text: []})
        inv = nonfiction_citation_invariant(verifier)
        result = inv.check(files_touched=["doc.md"], root=tmp_path)
        assert result.passed

    def test_default_warn(self):
        verifier = MockCitationVerifier()
        inv = nonfiction_citation_invariant(verifier)
        assert inv.on_violation == "warn"


# =============================================================================
# Tone adapter tests
# =============================================================================


class TestToneInvariant:
    def test_no_files_passes(self):
        checker = MockToneChecker()
        inv = tone_invariant(checker)
        result = inv.check(files_touched=[], root=Path("."))
        assert result.passed

    def test_valid_tone_passes(self, tmp_path):
        text = "Clean prose that matches the profile."
        (tmp_path / "essay.md").write_text(text)
        checker = MockToneChecker({text: MockToneCheckResult(valid=True)})
        inv = tone_invariant(checker)
        result = inv.check(files_touched=["essay.md"], root=tmp_path)
        assert result.passed

    def test_violation_detected(self, tmp_path):
        text = "This sentence is way too long and rambling with too many clauses."
        (tmp_path / "essay.md").write_text(text)
        violation = MockToneViolation(
            dimension="avg_sentence_length",
            message="Sentences too long (avg 15.2, target 10.0)",
            suggestion="Break up long sentences",
        )
        checker = MockToneChecker({
            text: MockToneCheckResult(valid=False, violations=[violation]),
        })
        inv = tone_invariant(checker)
        result = inv.check(files_touched=["essay.md"], root=tmp_path)
        assert not result.passed
        assert "1 violation" in result.message
        assert "Break up long sentences" in result.message

    def test_multiple_violations(self, tmp_path):
        text = "Bad prose."
        (tmp_path / "essay.md").write_text(text)
        violations = [
            MockToneViolation("sentence_length", "Too long", "Use shorter sentences"),
            MockToneViolation("contraction_rate", "Too formal", "Use more contractions"),
        ]
        checker = MockToneChecker({
            text: MockToneCheckResult(valid=False, violations=violations),
        })
        inv = tone_invariant(checker)
        result = inv.check(files_touched=["essay.md"], root=tmp_path)
        assert not result.passed
        assert "2 violation" in result.message

    def test_skips_non_prose_files(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1")
        checker = MockToneChecker()
        checker.check = MagicMock(return_value=MockToneCheckResult(valid=True))
        inv = tone_invariant(checker)
        result = inv.check(files_touched=["code.py"], root=tmp_path)
        assert result.passed
        checker.check.assert_not_called()

    def test_default_warn_only(self):
        checker = MockToneChecker()
        inv = tone_invariant(checker)
        assert inv.on_violation == "warn"
        assert inv.id == "tone_check"

    def test_custom_extensions(self, tmp_path):
        (tmp_path / "file.py").write_text("text")
        checker = MockToneChecker({"text": MockToneCheckResult(valid=True)})
        inv = tone_invariant(checker, file_extensions={".py"})
        result = inv.check(files_touched=["file.py"], root=tmp_path)
        assert result.passed

    def test_suggestion_in_details(self, tmp_path):
        text = "Text."
        (tmp_path / "doc.md").write_text(text)
        violation = MockToneViolation("metric", "Issue", "Add fragments for emphasis")
        checker = MockToneChecker({
            text: MockToneCheckResult(valid=False, violations=[violation]),
        })
        inv = tone_invariant(checker)
        result = inv.check(files_touched=["doc.md"], root=tmp_path)
        assert not result.passed
        assert result.details["violations"][0]["details"]["suggestion"] == "Add fragments for emphasis"


# =============================================================================
# Content invariant (generic adapter) tests
# =============================================================================


class TestContentInvariant:
    def test_passing_check(self, tmp_path):
        (tmp_path / "file.py").write_text("good code")

        def check(content: str, path: str) -> tuple[bool, str]:
            return True, "OK"

        inv = content_invariant(check, name="test", rule="Must be good")
        result = inv.check(files_touched=["file.py"], root=tmp_path)
        assert result.passed

    def test_failing_check(self, tmp_path):
        (tmp_path / "file.py").write_text("bad code")

        def check(content: str, path: str) -> tuple[bool, str]:
            if "bad" in content:
                return False, "Contains 'bad'"
            return True, "OK"

        inv = content_invariant(check, name="no_bad", rule="No bad code")
        result = inv.check(files_touched=["file.py"], root=tmp_path)
        assert not result.passed
        assert "1 failure" in result.message

    def test_check_receives_path(self, tmp_path):
        (tmp_path / "test.py").write_text("hello")
        received_paths = []

        def check(content: str, path: str) -> tuple[bool, str]:
            received_paths.append(path)
            return True, "OK"

        inv = content_invariant(check, name="test", rule="test")
        inv.check(files_touched=["test.py"], root=tmp_path)
        assert received_paths == ["test.py"]

    def test_check_error_becomes_failure(self, tmp_path):
        (tmp_path / "file.py").write_text("code")

        def check(content: str, path: str) -> tuple[bool, str]:
            raise ValueError("parse error")

        inv = content_invariant(check, name="broken", rule="test")
        result = inv.check(files_touched=["file.py"], root=tmp_path)
        assert not result.passed
        assert "1 failure" in result.message

    def test_custom_extensions(self, tmp_path):
        (tmp_path / "data.csv").write_text("a,b,c")
        called = []

        def check(content: str, path: str) -> tuple[bool, str]:
            called.append(path)
            return True, "OK"

        inv = content_invariant(check, name="csv", rule="test", file_extensions={".csv"})
        inv.check(files_touched=["data.csv"], root=tmp_path)
        assert called == ["data.csv"]

    def test_invariant_id_derived_from_name(self):
        def check(c: str, p: str) -> tuple[bool, str]:
            return True, ""

        inv = content_invariant(check, name="My Check", rule="test")
        assert inv.id == "content_my_check"

    def test_custom_invariant_id(self):
        def check(c: str, p: str) -> tuple[bool, str]:
            return True, ""

        inv = content_invariant(check, name="test", rule="test", invariant_id="custom_id")
        assert inv.id == "custom_id"

    def test_no_files_passes(self):
        def check(c: str, p: str) -> tuple[bool, str]:
            return False, "would fail"

        inv = content_invariant(check, name="test", rule="test")
        result = inv.check(files_touched=[], root=Path("."))
        assert result.passed

    def test_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("good")
        (tmp_path / "b.py").write_text("bad")

        def check(content: str, path: str) -> tuple[bool, str]:
            if "bad" in content:
                return False, "Bad content"
            return True, "OK"

        inv = content_invariant(check, name="test", rule="test")
        result = inv.check(files_touched=["a.py", "b.py"], root=tmp_path)
        assert not result.passed


# =============================================================================
# AdapterConfig and build_adapter_set tests
# =============================================================================


class TestAdapterConfig:
    def test_default_config(self):
        config = AdapterConfig()
        assert config.security_verifier is None
        assert config.cfi_detector is None
        assert config.fiction_verifier is None
        assert config.citation_verifier is None
        assert config.tone_checker is None
        assert config.custom_checks == []

    def test_empty_config_builds_empty_set(self):
        config = AdapterConfig()
        result = build_adapter_set(config)
        assert result == []

    def test_security_only(self):
        config = AdapterConfig(security_verifier=MockSecurityVerifier())
        result = build_adapter_set(config)
        assert len(result) == 1
        assert result[0].id == "security_scan"

    def test_cfi_only(self):
        config = AdapterConfig(cfi_detector=MockCFIDetector())
        result = build_adapter_set(config)
        assert len(result) == 1
        assert result[0].id == "cfi_check"

    def test_fiction_only(self):
        config = AdapterConfig(fiction_verifier=MockFictionVerifier())
        result = build_adapter_set(config)
        assert len(result) == 1
        assert result[0].id == "fiction_check"

    def test_citation_only(self):
        config = AdapterConfig(citation_verifier=MockCitationVerifier())
        result = build_adapter_set(config)
        assert len(result) == 1
        assert result[0].id == "nonfiction_citations"

    def test_tone_only(self):
        config = AdapterConfig(tone_checker=MockToneChecker())
        result = build_adapter_set(config)
        assert len(result) == 1
        assert result[0].id == "tone_check"

    def test_all_adapters(self):
        config = AdapterConfig(
            security_verifier=MockSecurityVerifier(),
            cfi_detector=MockCFIDetector(),
            fiction_verifier=MockFictionVerifier(),
            citation_verifier=MockCitationVerifier(),
            tone_checker=MockToneChecker(),
        )
        result = build_adapter_set(config)
        assert len(result) == 5
        ids = {inv.id for inv in result}
        assert ids == {"security_scan", "cfi_check", "fiction_check", "nonfiction_citations", "tone_check"}

    def test_custom_checks_included(self):
        def my_check(content: str, path: str) -> tuple[bool, str]:
            return True, "OK"

        config = AdapterConfig(
            custom_checks=[(my_check, "lint", "Must pass lint")],
        )
        result = build_adapter_set(config)
        assert len(result) == 1
        assert result[0].id == "content_lint"

    def test_multiple_custom_checks(self):
        def check1(c: str, p: str) -> tuple[bool, str]:
            return True, ""

        def check2(c: str, p: str) -> tuple[bool, str]:
            return True, ""

        config = AdapterConfig(
            custom_checks=[
                (check1, "lint", "Must pass lint"),
                (check2, "format", "Must be formatted"),
            ],
        )
        result = build_adapter_set(config)
        assert len(result) == 2

    def test_built_invariants_work_in_set(self, tmp_path):
        (tmp_path / "clean.py").write_text("x = 1")
        config = AdapterConfig(security_verifier=MockSecurityVerifier())
        invariants = build_adapter_set(config)
        inv_set = InvariantSet()
        for inv in invariants:
            inv_set.add(inv)
        results = inv_set.check_all(files_touched=["clean.py"], root=tmp_path)
        assert len(results) == 1
        assert results[0].passed

    def test_config_with_parameters(self):
        config = AdapterConfig(
            security_verifier=MockSecurityVerifier(),
            security_min_severity="critical",
            cfi_detector=MockCFIDetector(),
            cfi_max_faults=5,
            fiction_verifier=MockFictionVerifier(),
            fiction_characters=["Alice"],
        )
        result = build_adapter_set(config)
        assert len(result) == 3


# =============================================================================
# Integration with InvariantSet / executor patterns
# =============================================================================


class TestInvariantSetIntegration:
    def test_blocking_violations_empty(self, tmp_path):
        """Adapter invariants work with InvariantSet.blocking_violations()."""
        (tmp_path / "ok.py").write_text("clean")
        config = AdapterConfig(security_verifier=MockSecurityVerifier())
        invariants = build_adapter_set(config)
        inv_set = InvariantSet()
        for inv in invariants:
            inv_set.add(inv)
        blocking = inv_set.blocking_violations(files_touched=["ok.py"], root=tmp_path)
        assert blocking == []

    def test_blocking_violations_with_finding(self, tmp_path):
        """Security findings create blocking violations."""
        (tmp_path / "bad.py").write_text("password = 'admin'")
        finding = MockSecurityFinding(
            vuln_type=MockEnum("hardcoded_credential"),
            severity=MockEnum("high"),
            file_path="bad.py",
            line_number=1,
            line_content="password = 'admin'",
            message="Hardcoded password",
        )
        verifier = MockSecurityVerifier({str(tmp_path / "bad.py"): [finding]})
        inv_set = InvariantSet()
        inv_set.add(security_invariant(verifier))
        blocking = inv_set.blocking_violations(files_touched=["bad.py"], root=tmp_path)
        assert len(blocking) == 1
        assert "Security" in blocking[0].message

    def test_warn_invariant_not_blocking(self, tmp_path):
        """Warn-only invariants don't appear in blocking_violations."""
        text = "Essay text."
        (tmp_path / "essay.md").write_text(text)
        fault = MockCFIFault(fault_type=MockEnum("uninvited_frame"), detail="Frame issue")
        detector = MockCFIDetector({text: MockCFIResult(faults=[fault], has_faults=True)})
        inv_set = InvariantSet()
        inv_set.add(cfi_invariant(detector))  # Default: on_violation="warn"
        blocking = inv_set.blocking_violations(files_touched=["essay.md"], root=tmp_path)
        assert blocking == []  # Warn doesn't block

    def test_mixed_block_and_warn(self, tmp_path):
        """Mixed block/warn invariants filter correctly."""
        text = "Some text."
        (tmp_path / "file.md").write_text(text)

        # Security: block
        finding = MockSecurityFinding(
            vuln_type=MockEnum("secret_leak"),
            severity=MockEnum("high"),
            file_path="file.md",
            line_number=1,
            line_content=text,
            message="Secret found",
        )
        sec_verifier = MockSecurityVerifier({str(tmp_path / "file.md"): [finding]})

        # CFI: warn
        fault = MockCFIFault(fault_type=MockEnum("uninvited_frame"), detail="Frame")
        cfi_detector = MockCFIDetector({text: MockCFIResult(faults=[fault], has_faults=True)})

        inv_set = InvariantSet()
        inv_set.add(security_invariant(sec_verifier))
        inv_set.add(cfi_invariant(cfi_detector))

        # check_all sees both failures
        all_results = inv_set.check_all(files_touched=["file.md"], root=tmp_path)
        failures = [r for r in all_results if not r.passed]
        assert len(failures) == 2

        # blocking_violations only sees security
        blocking = inv_set.blocking_violations(files_touched=["file.md"], root=tmp_path)
        assert len(blocking) == 1
        assert "Security" in blocking[0].message

    def test_disabled_invariant_skipped(self):
        verifier = MockSecurityVerifier()
        inv = security_invariant(verifier)
        inv.enabled = False
        result = inv.check(files_touched=["any.py"], root=Path("."))
        assert result.passed
        assert "disabled" in result.message


# =============================================================================
# Extension set tests
# =============================================================================


class TestExtensionSets:
    def test_text_extensions_include_common(self):
        assert ".py" in TEXT_EXTENSIONS
        assert ".js" in TEXT_EXTENSIONS
        assert ".md" in TEXT_EXTENSIONS

    def test_prose_extensions_subset_of_text(self):
        assert PROSE_EXTENSIONS.issubset(TEXT_EXTENSIONS)

    def test_prose_includes_markdown(self):
        assert ".md" in PROSE_EXTENSIONS
        assert ".txt" in PROSE_EXTENSIONS
        assert ".rst" in PROSE_EXTENSIONS
