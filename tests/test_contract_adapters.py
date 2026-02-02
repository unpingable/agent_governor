"""
Contract tests for governor adapters (Phase A4).

Enforces the narrow interface that adapters must satisfy:
- Every factory function returns an Invariant with correct fields
- Every verify() returns InvariantResult with correct shape
- No adapter crashes on empty inputs or missing files
- AdapterFinding.to_dict() always produces the locked schema
- build_adapter_set only includes configured adapters
- Adapters never mutate their inputs

From govtests.md §3: "GovernorAdapter must implement X, emit events
in Y schema, never mutate state directly."
"""

import copy
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from governor.adapters import (
    AdapterConfig,
    AdapterFinding,
    PROSE_EXTENSIONS,
    TEXT_EXTENSIONS,
    build_adapter_set,
    cfi_invariant,
    content_invariant,
    fiction_invariant,
    nonfiction_citation_invariant,
    security_invariant,
    tone_invariant,
)
from governor.invariants import Invariant, InvariantResult, InvariantType


# =============================================================================
# Mock verifiers — minimal stubs satisfying the adapter duck-typing contracts
# =============================================================================


@dataclass
class _MockVuln:
    """Minimal vulnerability finding for SecurityVerifier mock."""
    severity: str
    message: str
    vuln_type: str
    line_number: int


class MockSecurityVerifier:
    """Stub SecurityVerifier — returns configurable findings."""

    def __init__(self, findings: list[_MockVuln] | None = None):
        self.findings = findings or []
        self.scan_count = 0

    def scan_file(self, path: Path) -> list[_MockVuln]:
        self.scan_count += 1
        return self.findings


@dataclass
class _MockFault:
    detail: str
    fault_type: str
    frame: str | None = None
    severity: str = "warning"


@dataclass
class _MockCFIResult:
    faults: list[_MockFault]


class MockCFIDetector:
    """Stub CFIDetector — returns configurable faults."""

    def __init__(self, faults: list[_MockFault] | None = None):
        self.faults = faults or []

    def check(self, content: str) -> _MockCFIResult:
        return _MockCFIResult(faults=self.faults)


class MockFictionVerifier:
    """Stub CombinedVerifier — returns configurable issues."""

    def __init__(self, passed: bool = True, issues: list[str] | None = None):
        self._passed = passed
        self._issues = issues or []

    def quick_check(self, content: str, characters: list[str]) -> tuple[bool, list[str]]:
        return (self._passed, self._issues)


@dataclass
class _MockCitationResult:
    valid: bool
    message: str


class MockCitationVerifier:
    """Stub CitationVerifier — returns configurable results."""

    def __init__(self, citations: dict[str, bool] | None = None):
        self._citations = citations or {}

    def extract_citations(self, content: str) -> list[str]:
        return list(self._citations.keys())

    def verify_citation(self, key: str) -> _MockCitationResult:
        valid = self._citations.get(key, True)
        msg = "OK" if valid else f"Citation '{key}' not found"
        return _MockCitationResult(valid=valid, message=msg)


@dataclass
class _MockToneViolation:
    message: str
    dimension: str
    suggestion: str


@dataclass
class _MockToneResult:
    valid: bool
    violations: list[_MockToneViolation]


class MockToneChecker:
    """Stub ToneChecker — returns configurable violations."""

    def __init__(self, valid: bool = True, violations: list[_MockToneViolation] | None = None):
        self._valid = valid
        self._violations = violations or []

    def check(self, content: str) -> _MockToneResult:
        return _MockToneResult(valid=self._valid, violations=self._violations)


# =============================================================================
# Contract: Invariant interface shape
# =============================================================================


class TestInvariantContract:
    """Every adapter factory MUST return an Invariant with the correct fields."""

    @pytest.fixture
    def tmp_root(self, tmp_path):
        """Create a temp dir with a sample .py and .md file."""
        (tmp_path / "sample.py").write_text("x = 1\n")
        (tmp_path / "sample.md").write_text("# Hello\n")
        return tmp_path

    ADAPTER_FACTORIES = [
        ("security", lambda: security_invariant(MockSecurityVerifier())),
        ("cfi", lambda: cfi_invariant(MockCFIDetector())),
        ("fiction", lambda: fiction_invariant(MockFictionVerifier())),
        ("citation", lambda: nonfiction_citation_invariant(MockCitationVerifier())),
        ("tone", lambda: tone_invariant(MockToneChecker())),
        ("content", lambda: content_invariant(lambda c, p: (True, "ok"), "test", "test rule")),
    ]

    @pytest.mark.parametrize("name,factory", ADAPTER_FACTORIES, ids=[a[0] for a in ADAPTER_FACTORIES])
    def test_returns_invariant_type(self, name, factory):
        inv = factory()
        assert isinstance(inv, Invariant)

    @pytest.mark.parametrize("name,factory", ADAPTER_FACTORIES, ids=[a[0] for a in ADAPTER_FACTORIES])
    def test_has_required_fields(self, name, factory):
        inv = factory()
        assert isinstance(inv.id, str) and len(inv.id) > 0
        assert isinstance(inv.type, InvariantType)
        assert isinstance(inv.rule, str) and len(inv.rule) > 0
        assert callable(inv.verify)
        assert inv.on_violation in ("block", "warn")
        assert isinstance(inv.enabled, bool)

    @pytest.mark.parametrize("name,factory", ADAPTER_FACTORIES, ids=[a[0] for a in ADAPTER_FACTORIES])
    def test_to_dict_shape(self, name, factory):
        inv = factory()
        d = inv.to_dict()
        assert set(d.keys()) == {"id", "type", "rule", "on_violation", "enabled"}
        assert isinstance(d["id"], str)
        assert isinstance(d["type"], str)
        assert isinstance(d["rule"], str)
        assert d["on_violation"] in ("block", "warn")
        assert isinstance(d["enabled"], bool)


# =============================================================================
# Contract: InvariantResult shape
# =============================================================================


class TestResultContract:
    """Every verify() call MUST return an InvariantResult with the locked shape."""

    @pytest.fixture
    def tmp_root(self, tmp_path):
        (tmp_path / "test.py").write_text("import os\n")
        (tmp_path / "test.md").write_text("Some prose.\n")
        return tmp_path

    VERIFY_CASES = [
        ("security_empty", lambda: security_invariant(MockSecurityVerifier()), {}),
        ("security_with_files", lambda: security_invariant(MockSecurityVerifier()), {"files_touched": ["test.py"]}),
        ("cfi_empty", lambda: cfi_invariant(MockCFIDetector()), {}),
        ("cfi_with_files", lambda: cfi_invariant(MockCFIDetector()), {"files_touched": ["test.md"]}),
        ("fiction_empty", lambda: fiction_invariant(MockFictionVerifier()), {}),
        ("citation_empty", lambda: nonfiction_citation_invariant(MockCitationVerifier()), {}),
        ("tone_empty", lambda: tone_invariant(MockToneChecker()), {}),
        ("content_empty", lambda: content_invariant(lambda c, p: (True, "ok"), "test", "r"), {}),
    ]

    @pytest.mark.parametrize("name,factory,kwargs", VERIFY_CASES, ids=[c[0] for c in VERIFY_CASES])
    def test_result_is_invariant_result(self, name, factory, kwargs, tmp_root):
        inv = factory()
        kwargs_with_root = {**kwargs, "root": tmp_root}
        result = inv.check(**kwargs_with_root)
        assert isinstance(result, InvariantResult)

    @pytest.mark.parametrize("name,factory,kwargs", VERIFY_CASES, ids=[c[0] for c in VERIFY_CASES])
    def test_result_has_required_fields(self, name, factory, kwargs, tmp_root):
        inv = factory()
        result = inv.check(**{**kwargs, "root": tmp_root})
        assert isinstance(result.passed, bool)
        assert isinstance(result.message, str)
        assert isinstance(result.invariant_id, str)
        assert isinstance(result.details, dict)

    @pytest.mark.parametrize("name,factory,kwargs", VERIFY_CASES, ids=[c[0] for c in VERIFY_CASES])
    def test_result_to_dict_shape(self, name, factory, kwargs, tmp_root):
        inv = factory()
        result = inv.check(**{**kwargs, "root": tmp_root})
        d = result.to_dict()
        assert set(d.keys()) == {"passed", "message", "invariant_id", "details"}
        assert isinstance(d["passed"], bool)
        assert isinstance(d["message"], str)
        assert isinstance(d["invariant_id"], str)
        assert isinstance(d["details"], dict)


# =============================================================================
# Contract: Empty inputs never crash
# =============================================================================


class TestEmptyInputSafety:
    """Adapters must handle empty/missing inputs gracefully."""

    def test_security_no_files(self):
        inv = security_invariant(MockSecurityVerifier())
        result = inv.check(root=Path("/nonexistent"), files_touched=[])
        assert result.passed is True

    def test_cfi_no_files(self):
        inv = cfi_invariant(MockCFIDetector())
        result = inv.check(root=Path("/nonexistent"), files_touched=[])
        assert result.passed is True

    def test_fiction_no_files(self):
        inv = fiction_invariant(MockFictionVerifier())
        result = inv.check(root=Path("/nonexistent"), files_touched=[])
        assert result.passed is True

    def test_citation_no_files(self):
        inv = nonfiction_citation_invariant(MockCitationVerifier())
        result = inv.check(root=Path("/nonexistent"), files_touched=[])
        assert result.passed is True

    def test_tone_no_files(self):
        inv = tone_invariant(MockToneChecker())
        result = inv.check(root=Path("/nonexistent"), files_touched=[])
        assert result.passed is True

    def test_content_no_files(self):
        inv = content_invariant(lambda c, p: (True, "ok"), "test", "rule")
        result = inv.check(root=Path("/nonexistent"), files_touched=[])
        assert result.passed is True

    def test_security_no_kwargs(self):
        """verify() with zero kwargs must not crash."""
        inv = security_invariant(MockSecurityVerifier())
        result = inv.check()
        assert result.passed is True

    def test_cfi_no_kwargs(self):
        inv = cfi_invariant(MockCFIDetector())
        result = inv.check()
        assert result.passed is True

    def test_fiction_no_kwargs(self):
        inv = fiction_invariant(MockFictionVerifier())
        result = inv.check()
        assert result.passed is True

    def test_content_no_kwargs(self):
        inv = content_invariant(lambda c, p: (True, "ok"), "test", "rule")
        result = inv.check()
        assert result.passed is True

    def test_nonexistent_files_skipped(self, tmp_path):
        """Files that don't exist on disk are silently skipped."""
        inv = security_invariant(MockSecurityVerifier())
        result = inv.check(root=tmp_path, files_touched=["does_not_exist.py"])
        assert result.passed is True


# =============================================================================
# Contract: Findings produce violations
# =============================================================================


class TestFindingDetection:
    """When a verifier reports issues, the adapter MUST surface them."""

    def test_security_finding_causes_failure(self, tmp_path):
        vuln = _MockVuln(severity="high", message="SQL injection", vuln_type="sql_injection", line_number=1)
        verifier = MockSecurityVerifier(findings=[vuln])
        inv = security_invariant(verifier)
        (tmp_path / "bad.py").write_text("query = f'SELECT * FROM {user_input}'")
        result = inv.check(root=tmp_path, files_touched=["bad.py"])
        assert result.passed is False
        assert "finding" in result.message.lower()
        assert "findings" in result.details

    def test_cfi_faults_cause_failure(self, tmp_path):
        fault = _MockFault(detail="Register shift detected", fault_type="register_shift")
        detector = MockCFIDetector(faults=[fault])
        inv = cfi_invariant(detector, max_faults=0)
        (tmp_path / "doc.md").write_text("Some text with register shift.")
        result = inv.check(root=tmp_path, files_touched=["doc.md"])
        assert result.passed is False
        assert "faults" in result.details

    def test_fiction_issues_cause_failure(self, tmp_path):
        verifier = MockFictionVerifier(passed=False, issues=["Character OOC"])
        inv = fiction_invariant(verifier)
        (tmp_path / "ch1.md").write_text("He said something out of character.")
        result = inv.check(root=tmp_path, files_touched=["ch1.md"])
        assert result.passed is False
        assert "issues" in result.details

    def test_citation_invalid_causes_failure(self, tmp_path):
        verifier = MockCitationVerifier(citations={"smith2020": False})
        inv = nonfiction_citation_invariant(verifier)
        (tmp_path / "paper.md").write_text("As shown by @smith2020...")
        result = inv.check(root=tmp_path, files_touched=["paper.md"])
        assert result.passed is False
        assert "findings" in result.details

    def test_tone_violations_cause_failure(self, tmp_path):
        violation = _MockToneViolation(
            message="Too formal", dimension="formality", suggestion="Relax tone"
        )
        checker = MockToneChecker(valid=False, violations=[violation])
        inv = tone_invariant(checker)
        (tmp_path / "essay.md").write_text("Herein we present our findings.")
        result = inv.check(root=tmp_path, files_touched=["essay.md"])
        assert result.passed is False
        assert "violations" in result.details

    def test_content_check_failure(self, tmp_path):
        def bad_check(content: str, path: str) -> tuple[bool, str]:
            return (False, "Content too short")

        inv = content_invariant(bad_check, "length", "Min length rule")
        (tmp_path / "short.py").write_text("x")
        result = inv.check(root=tmp_path, files_touched=["short.py"])
        assert result.passed is False


# =============================================================================
# Contract: AdapterFinding shape
# =============================================================================


class TestAdapterFindingContract:
    """AdapterFinding.to_dict() shape is locked."""

    REQUIRED_KEYS = {"source", "file_path", "message", "severity", "details"}

    def test_to_dict_keys(self):
        f = AdapterFinding(source="test", file_path="a.py", message="msg")
        assert set(f.to_dict().keys()) == self.REQUIRED_KEYS

    def test_to_dict_types(self):
        f = AdapterFinding(
            source="sec", file_path="b.py", message="m",
            severity="high", details={"a": 1},
        )
        d = f.to_dict()
        assert isinstance(d["source"], str)
        assert isinstance(d["file_path"], str)
        assert isinstance(d["message"], str)
        assert isinstance(d["severity"], str)
        assert isinstance(d["details"], dict)

    def test_default_severity(self):
        f = AdapterFinding(source="x", file_path="y", message="z")
        assert f.severity == "error"

    def test_default_details(self):
        f = AdapterFinding(source="x", file_path="y", message="z")
        assert f.details == {}

    def test_finding_in_security_details(self, tmp_path):
        """Security adapter surfaces findings as list of AdapterFinding dicts."""
        vuln = _MockVuln(severity="critical", message="XSS", vuln_type="xss", line_number=5)
        verifier = MockSecurityVerifier(findings=[vuln])
        inv = security_invariant(verifier, min_severity="critical")
        (tmp_path / "x.py").write_text("innerHTML = user_input")
        result = inv.check(root=tmp_path, files_touched=["x.py"])
        assert result.passed is False
        for finding_dict in result.details["findings"]:
            assert set(finding_dict.keys()) == self.REQUIRED_KEYS


# =============================================================================
# Contract: on_violation parameter respected
# =============================================================================


class TestOnViolationParameter:
    """Adapters must forward on_violation to the Invariant."""

    @pytest.mark.parametrize("mode", ["block", "warn"])
    def test_security_on_violation(self, mode):
        inv = security_invariant(MockSecurityVerifier(), on_violation=mode)
        assert inv.on_violation == mode

    @pytest.mark.parametrize("mode", ["block", "warn"])
    def test_cfi_on_violation(self, mode):
        inv = cfi_invariant(MockCFIDetector(), on_violation=mode)
        assert inv.on_violation == mode

    @pytest.mark.parametrize("mode", ["block", "warn"])
    def test_fiction_on_violation(self, mode):
        inv = fiction_invariant(MockFictionVerifier(), on_violation=mode)
        assert inv.on_violation == mode

    @pytest.mark.parametrize("mode", ["block", "warn"])
    def test_citation_on_violation(self, mode):
        inv = nonfiction_citation_invariant(MockCitationVerifier(), on_violation=mode)
        assert inv.on_violation == mode

    @pytest.mark.parametrize("mode", ["block", "warn"])
    def test_tone_on_violation(self, mode):
        inv = tone_invariant(MockToneChecker(), on_violation=mode)
        assert inv.on_violation == mode

    @pytest.mark.parametrize("mode", ["block", "warn"])
    def test_content_on_violation(self, mode):
        inv = content_invariant(lambda c, p: (True, "ok"), "t", "r", on_violation=mode)
        assert inv.on_violation == mode


# =============================================================================
# Contract: invariant_id parameter respected
# =============================================================================


class TestInvariantIdParameter:
    """Custom invariant_id is forwarded to Invariant and results."""

    def test_security_custom_id(self, tmp_path):
        inv = security_invariant(MockSecurityVerifier(), invariant_id="my_sec")
        assert inv.id == "my_sec"
        result = inv.check(root=tmp_path, files_touched=[])
        assert result.invariant_id == "my_sec"

    def test_cfi_custom_id(self, tmp_path):
        inv = cfi_invariant(MockCFIDetector(), invariant_id="my_cfi")
        assert inv.id == "my_cfi"
        result = inv.check(root=tmp_path, files_touched=[])
        assert result.invariant_id == "my_cfi"

    def test_fiction_custom_id(self, tmp_path):
        inv = fiction_invariant(MockFictionVerifier(), invariant_id="my_fiction")
        assert inv.id == "my_fiction"
        result = inv.check(root=tmp_path, files_touched=[])
        assert result.invariant_id == "my_fiction"

    def test_citation_custom_id(self, tmp_path):
        inv = nonfiction_citation_invariant(MockCitationVerifier(), invariant_id="my_cite")
        assert inv.id == "my_cite"
        result = inv.check(root=tmp_path, files_touched=[])
        assert result.invariant_id == "my_cite"

    def test_tone_custom_id(self, tmp_path):
        inv = tone_invariant(MockToneChecker(), invariant_id="my_tone")
        assert inv.id == "my_tone"
        result = inv.check(root=tmp_path, files_touched=[])
        assert result.invariant_id == "my_tone"

    def test_content_custom_id(self, tmp_path):
        inv = content_invariant(
            lambda c, p: (True, "ok"), "t", "r", invariant_id="my_content"
        )
        assert inv.id == "my_content"
        result = inv.check(root=tmp_path, files_touched=[])
        assert result.invariant_id == "my_content"


# =============================================================================
# Contract: No input mutation
# =============================================================================


class TestNoInputMutation:
    """Adapters must NEVER mutate files_touched, root, or the verifier."""

    def test_security_does_not_mutate_files_list(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        files = ["a.py"]
        files_copy = files.copy()
        inv = security_invariant(MockSecurityVerifier())
        inv.check(root=tmp_path, files_touched=files)
        assert files == files_copy

    def test_cfi_does_not_mutate_files_list(self, tmp_path):
        (tmp_path / "a.md").write_text("text")
        files = ["a.md"]
        files_copy = files.copy()
        inv = cfi_invariant(MockCFIDetector())
        inv.check(root=tmp_path, files_touched=files)
        assert files == files_copy

    def test_fiction_does_not_mutate_files_list(self, tmp_path):
        (tmp_path / "a.md").write_text("text")
        files = ["a.md"]
        files_copy = files.copy()
        inv = fiction_invariant(MockFictionVerifier())
        inv.check(root=tmp_path, files_touched=files)
        assert files == files_copy

    def test_content_does_not_mutate_files_list(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        files = ["a.py"]
        files_copy = files.copy()
        inv = content_invariant(lambda c, p: (True, "ok"), "t", "r")
        inv.check(root=tmp_path, files_touched=files)
        assert files == files_copy


# =============================================================================
# Contract: Disabled invariants always pass
# =============================================================================


class TestDisabledInvariant:
    """When enabled=False, check() must return passed=True without calling verify."""

    def test_disabled_security_passes(self, tmp_path):
        vuln = _MockVuln(severity="critical", message="Vuln!", vuln_type="rce", line_number=1)
        verifier = MockSecurityVerifier(findings=[vuln])
        inv = security_invariant(verifier)
        inv.enabled = False
        (tmp_path / "evil.py").write_text("os.system(input())")
        result = inv.check(root=tmp_path, files_touched=["evil.py"])
        assert result.passed is True
        assert verifier.scan_count == 0  # verify was NOT called

    def test_disabled_content_passes(self):
        inv = content_invariant(lambda c, p: (False, "fail"), "t", "r")
        inv.enabled = False
        result = inv.check(root=Path("."), files_touched=["x.py"])
        assert result.passed is True


# =============================================================================
# Contract: build_adapter_set
# =============================================================================


class TestBuildAdapterSet:
    """build_adapter_set must only include adapters for provided verifiers."""

    def test_empty_config_produces_empty_set(self):
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

    def test_custom_checks(self):
        config = AdapterConfig(
            custom_checks=[
                (lambda c, p: (True, "ok"), "custom_a", "rule A"),
                (lambda c, p: (True, "ok"), "custom_b", "rule B"),
            ]
        )
        result = build_adapter_set(config)
        assert len(result) == 2

    def test_all_adapters(self):
        config = AdapterConfig(
            security_verifier=MockSecurityVerifier(),
            cfi_detector=MockCFIDetector(),
            fiction_verifier=MockFictionVerifier(),
            citation_verifier=MockCitationVerifier(),
            tone_checker=MockToneChecker(),
            custom_checks=[(lambda c, p: (True, "ok"), "x", "r")],
        )
        result = build_adapter_set(config)
        assert len(result) == 6

    def test_all_are_invariant_instances(self):
        config = AdapterConfig(
            security_verifier=MockSecurityVerifier(),
            cfi_detector=MockCFIDetector(),
        )
        for inv in build_adapter_set(config):
            assert isinstance(inv, Invariant)

    def test_min_severity_forwarded(self):
        config = AdapterConfig(
            security_verifier=MockSecurityVerifier(),
            security_min_severity="medium",
        )
        result = build_adapter_set(config)
        # Medium severity vuln should trigger
        assert "medium" in result[0].rule.lower()

    def test_cfi_max_faults_forwarded(self):
        config = AdapterConfig(
            cfi_detector=MockCFIDetector(),
            cfi_max_faults=3,
        )
        result = build_adapter_set(config)
        assert "3" in result[0].rule

    def test_fiction_characters_forwarded(self, tmp_path):
        """Characters list is threaded through to quick_check."""
        class CapturingVerifier:
            def __init__(self):
                self.last_chars = None
            def quick_check(self, content, chars):
                self.last_chars = chars
                return (True, [])

        verifier = CapturingVerifier()
        config = AdapterConfig(
            fiction_verifier=verifier,
            fiction_characters=["Alice", "Bob"],
        )
        invs = build_adapter_set(config)
        (tmp_path / "ch.md").write_text("Dialog here.")
        invs[0].check(root=tmp_path, files_touched=["ch.md"])
        assert verifier.last_chars == ["Alice", "Bob"]


# =============================================================================
# Contract: content_invariant escape hatch
# =============================================================================


class TestContentInvariantContract:
    """content_invariant is the generic escape hatch — test its contract."""

    def test_check_fn_receives_content_and_path(self, tmp_path):
        received = {}

        def capture(content: str, path: str) -> tuple[bool, str]:
            received["content"] = content
            received["path"] = path
            return (True, "ok")

        inv = content_invariant(capture, "capture", "rule")
        (tmp_path / "data.py").write_text("payload = 42")
        inv.check(root=tmp_path, files_touched=["data.py"])
        assert received["content"] == "payload = 42"
        assert received["path"] == "data.py"

    def test_check_fn_exception_is_finding(self, tmp_path):
        def broken(content: str, path: str) -> tuple[bool, str]:
            raise ValueError("boom")

        inv = content_invariant(broken, "broken", "rule")
        (tmp_path / "x.py").write_text("code")
        result = inv.check(root=tmp_path, files_touched=["x.py"])
        assert result.passed is False
        assert "failures" in result.details

    def test_custom_extensions_filter(self, tmp_path):
        calls = []

        def track(content: str, path: str) -> tuple[bool, str]:
            calls.append(path)
            return (True, "ok")

        inv = content_invariant(track, "t", "r", file_extensions={".rs"})
        (tmp_path / "a.py").write_text("python")
        (tmp_path / "b.rs").write_text("rust")
        inv.check(root=tmp_path, files_touched=["a.py", "b.rs"])
        assert calls == ["b.rs"]

    def test_invariant_type_forwarded(self):
        inv = content_invariant(
            lambda c, p: (True, "ok"), "t", "r",
            invariant_type=InvariantType.FORBIDDEN,
        )
        assert inv.type == InvariantType.FORBIDDEN

    def test_default_invariant_type_is_consistency(self):
        inv = content_invariant(lambda c, p: (True, "ok"), "t", "r")
        assert inv.type == InvariantType.CONSISTENCY

    def test_id_derived_from_name(self):
        inv = content_invariant(lambda c, p: (True, "ok"), "My Check", "rule")
        assert inv.id == "content_my_check"


# =============================================================================
# Contract: Severity threshold
# =============================================================================


class TestSecuritySeverityThreshold:
    """Security adapter must respect the min_severity threshold."""

    def test_low_finding_below_high_threshold(self, tmp_path):
        vuln = _MockVuln(severity="low", message="Minor", vuln_type="info", line_number=1)
        inv = security_invariant(MockSecurityVerifier(findings=[vuln]), min_severity="high")
        (tmp_path / "f.py").write_text("x")
        result = inv.check(root=tmp_path, files_touched=["f.py"])
        assert result.passed is True

    def test_high_finding_at_high_threshold(self, tmp_path):
        vuln = _MockVuln(severity="high", message="Bad", vuln_type="sqli", line_number=1)
        inv = security_invariant(MockSecurityVerifier(findings=[vuln]), min_severity="high")
        (tmp_path / "f.py").write_text("x")
        result = inv.check(root=tmp_path, files_touched=["f.py"])
        assert result.passed is False

    def test_critical_finding_at_high_threshold(self, tmp_path):
        vuln = _MockVuln(severity="critical", message="RCE", vuln_type="rce", line_number=1)
        inv = security_invariant(MockSecurityVerifier(findings=[vuln]), min_severity="high")
        (tmp_path / "f.py").write_text("x")
        result = inv.check(root=tmp_path, files_touched=["f.py"])
        assert result.passed is False

    def test_medium_finding_at_medium_threshold(self, tmp_path):
        vuln = _MockVuln(severity="medium", message="XSS", vuln_type="xss", line_number=1)
        inv = security_invariant(MockSecurityVerifier(findings=[vuln]), min_severity="medium")
        (tmp_path / "f.py").write_text("x")
        result = inv.check(root=tmp_path, files_touched=["f.py"])
        assert result.passed is False


# =============================================================================
# Contract: CFI fault tolerance
# =============================================================================


class TestCFIFaultTolerance:
    """CFI adapter respects max_faults tolerance."""

    def test_one_fault_within_tolerance_of_one(self, tmp_path):
        fault = _MockFault(detail="Shift", fault_type="register_shift")
        inv = cfi_invariant(MockCFIDetector(faults=[fault]), max_faults=1)
        (tmp_path / "doc.md").write_text("text")
        result = inv.check(root=tmp_path, files_touched=["doc.md"])
        assert result.passed is True

    def test_two_faults_exceed_tolerance_of_one(self, tmp_path):
        faults = [
            _MockFault(detail="Shift 1", fault_type="register_shift"),
            _MockFault(detail="Shift 2", fault_type="register_shift"),
        ]
        inv = cfi_invariant(MockCFIDetector(faults=faults), max_faults=1)
        (tmp_path / "doc.md").write_text("text")
        result = inv.check(root=tmp_path, files_touched=["doc.md"])
        assert result.passed is False


# =============================================================================
# Contract: File extension filtering
# =============================================================================


class TestFileExtensionFiltering:
    """Adapters must only scan files with matching extensions."""

    def test_cfi_skips_non_prose_files(self, tmp_path):
        """CFI only scans prose extensions by default."""
        calls = []
        original_check = MockCFIDetector.check

        class TrackingDetector(MockCFIDetector):
            def check(self, content):
                calls.append(content)
                return super().check(content)

        inv = cfi_invariant(TrackingDetector())
        (tmp_path / "code.py").write_text("import os")
        (tmp_path / "doc.md").write_text("# Heading")
        inv.check(root=tmp_path, files_touched=["code.py", "doc.md"])
        # Only .md should be checked (it's in PROSE_EXTENSIONS)
        assert len(calls) == 1
        assert calls[0] == "# Heading"

    def test_fiction_skips_non_prose_files(self, tmp_path):
        calls = []

        class TrackingVerifier(MockFictionVerifier):
            def quick_check(self, content, characters):
                calls.append(content)
                return super().quick_check(content, characters)

        inv = fiction_invariant(TrackingVerifier())
        (tmp_path / "code.py").write_text("import os")
        (tmp_path / "story.md").write_text("Once upon a time...")
        inv.check(root=tmp_path, files_touched=["code.py", "story.md"])
        assert len(calls) == 1


# =============================================================================
# Contract: InvariantSet integration
# =============================================================================


class TestInvariantSetIntegration:
    """Adapters work correctly when composed into an InvariantSet."""

    def test_adapter_set_in_invariant_set(self, tmp_path):
        from governor.invariants import InvariantSet

        config = AdapterConfig(
            security_verifier=MockSecurityVerifier(),
            cfi_detector=MockCFIDetector(),
        )
        inv_set = InvariantSet()
        for inv in build_adapter_set(config):
            inv_set.add(inv)

        results = inv_set.check_all(root=tmp_path, files_touched=[])
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_blocking_violations_from_adapter(self, tmp_path):
        from governor.invariants import InvariantSet

        vuln = _MockVuln(severity="critical", message="RCE", vuln_type="rce", line_number=1)
        inv_set = InvariantSet()
        inv_set.add(security_invariant(MockSecurityVerifier(findings=[vuln])))
        (tmp_path / "bad.py").write_text("os.system(input())")

        blocking = inv_set.blocking_violations(root=tmp_path, files_touched=["bad.py"])
        assert len(blocking) == 1

    def test_warn_adapter_not_in_blocking(self, tmp_path):
        from governor.invariants import InvariantSet

        fault = _MockFault(detail="Shift", fault_type="register_shift")
        inv_set = InvariantSet()
        inv_set.add(cfi_invariant(MockCFIDetector(faults=[fault]), on_violation="warn"))
        (tmp_path / "doc.md").write_text("text")

        blocking = inv_set.blocking_violations(root=tmp_path, files_touched=["doc.md"])
        assert len(blocking) == 0  # warn, not block


# =============================================================================
# Contract: Verifier exception handling
# =============================================================================


class TestVerifierExceptionHandling:
    """If a wrapped verifier throws, the adapter must not crash."""

    def test_security_verifier_exception_skipped(self, tmp_path):
        class CrashingVerifier:
            def scan_file(self, path):
                raise RuntimeError("Connection refused")

        inv = security_invariant(CrashingVerifier())
        (tmp_path / "f.py").write_text("code")
        result = inv.check(root=tmp_path, files_touched=["f.py"])
        assert result.passed is True  # Gracefully skipped

    def test_cfi_detector_exception_skipped(self, tmp_path):
        class CrashingDetector:
            def check(self, content):
                raise RuntimeError("Parse error")

        inv = cfi_invariant(CrashingDetector())
        (tmp_path / "f.md").write_text("text")
        result = inv.check(root=tmp_path, files_touched=["f.md"])
        assert result.passed is True

    def test_fiction_verifier_exception_skipped(self, tmp_path):
        class CrashingVerifier:
            def quick_check(self, content, chars):
                raise RuntimeError("OOM")

        inv = fiction_invariant(CrashingVerifier())
        (tmp_path / "f.md").write_text("text")
        result = inv.check(root=tmp_path, files_touched=["f.md"])
        assert result.passed is True

    def test_citation_verifier_extract_exception_skipped(self, tmp_path):
        class CrashingVerifier:
            def extract_citations(self, content):
                raise RuntimeError("Regex timeout")

        inv = nonfiction_citation_invariant(CrashingVerifier())
        (tmp_path / "f.md").write_text("text")
        result = inv.check(root=tmp_path, files_touched=["f.md"])
        assert result.passed is True

    def test_tone_checker_exception_skipped(self, tmp_path):
        class CrashingChecker:
            def check(self, content):
                raise RuntimeError("Model unavailable")

        inv = tone_invariant(CrashingChecker())
        (tmp_path / "f.md").write_text("text")
        result = inv.check(root=tmp_path, files_touched=["f.md"])
        assert result.passed is True
