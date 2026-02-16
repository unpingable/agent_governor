"""Tests for oracle:pytest_log — the first real oracle evidence artifact.

Key regressions:
1. Artifact determinism: runner produces stable schema
2. Hash binding: tampering changes sha256, breaks verification
3. Gate behavior: HARD claims + oracle → PASS; without oracle → FAIL
4. Strength: oracle:pytest_log is STRONG, model:* is WEAK
5. No log-as-instructions: parsing reads junit, not arbitrary text
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from governor.oracle_pytest import (
    MAX_FAILURE_MSG_LEN,
    OraclePytestLog,
    PytestFailure,
    PytestRunResult,
    PytestRunner,
    parse_junit_xml,
    _sha256,
)


# =============================================================================
# JUnit XML parsing
# =============================================================================


class TestJunitXmlParser:
    """Parse junit.xml for structured results, not raw log text."""

    def test_parse_simple_pass(self):
        xml = b'<testsuite tests="3" failures="0" errors="0" skipped="0"></testsuite>'
        result = parse_junit_xml(xml)
        assert result["tests_total"] == 3
        assert result["tests_passed"] == 3
        assert result["tests_failed"] == 0
        assert result["failures"] == []

    def test_parse_with_failure(self):
        xml = textwrap.dedent("""\
        <testsuite tests="2" failures="1" errors="0">
          <testcase classname="test_foo" name="test_bar">
            <failure message="assert 1 == 2">AssertionError</failure>
          </testcase>
          <testcase classname="test_foo" name="test_ok" />
        </testsuite>
        """).encode()
        result = parse_junit_xml(xml)
        assert result["tests_total"] == 2
        assert result["tests_failed"] == 1
        assert result["tests_passed"] == 1
        assert len(result["failures"]) == 1
        assert result["failures"][0].nodeid == "test_foo::test_bar"
        assert "assert 1 == 2" in result["failures"][0].message

    def test_parse_with_error(self):
        xml = textwrap.dedent("""\
        <testsuite tests="1" failures="0" errors="1">
          <testcase classname="test_foo" name="test_crash">
            <error message="RuntimeError">boom</error>
          </testcase>
        </testsuite>
        """).encode()
        result = parse_junit_xml(xml)
        assert result["tests_errored"] == 1
        assert len(result["failures"]) == 1

    def test_parse_with_skipped(self):
        xml = b'<testsuite tests="5" failures="0" errors="0" skipped="2"></testsuite>'
        result = parse_junit_xml(xml)
        assert result["tests_skipped"] == 2
        assert result["tests_passed"] == 3

    def test_parse_testsuites_wrapper(self):
        """pytest sometimes wraps in <testsuites>."""
        xml = textwrap.dedent("""\
        <testsuites>
          <testsuite tests="4" failures="1" errors="0" skipped="0">
            <testcase classname="a" name="b">
              <failure message="nope">fail</failure>
            </testcase>
          </testsuite>
        </testsuites>
        """).encode()
        result = parse_junit_xml(xml)
        assert result["tests_total"] == 4
        assert result["tests_failed"] == 1

    def test_failure_message_truncated(self):
        """Long messages are truncated to prevent log-as-instructions."""
        long_msg = "x" * 2000
        xml = f'''<testsuite tests="1" failures="1">
          <testcase classname="t" name="t">
            <failure message="{long_msg}">detail</failure>
          </testcase>
        </testsuite>'''.encode()
        result = parse_junit_xml(xml)
        assert len(result["failures"][0].message) <= MAX_FAILURE_MSG_LEN

    def test_empty_xml(self):
        xml = b'<testsuite tests="0" failures="0" errors="0" />'
        result = parse_junit_xml(xml)
        assert result["tests_total"] == 0
        assert result["failures"] == []


# =============================================================================
# OraclePytestLog schema
# =============================================================================


class TestOraclePytestLogSchema:
    """Schema stability and serialization."""

    def _make_log(self, **overrides) -> OraclePytestLog:
        defaults = dict(
            schema_version=1,
            kind="oracle:pytest_log",
            oracle_class=0,
            run_id="test-run-id",
            cmd=["python3", "-m", "pytest", "tests/"],
            cwd="/repo",
            start_ts=1000.0,
            end_ts=1002.5,
            duration_s=2.5,
            exit_code=0,
            junit_xml_sha256="abc123",
            log_sha256="def456",
            tests_total=10,
            tests_passed=9,
            tests_failed=0,
            tests_errored=0,
            tests_skipped=1,
            failures=[],
            environment={"python_version": "3.12.3", "platform": "Linux"},
            git={"commit": "abc", "branch": "main", "dirty": "false"},
        )
        defaults.update(overrides)
        return OraclePytestLog(**defaults)

    def test_to_dict_has_all_fields(self):
        log = self._make_log()
        d = log.to_dict()
        assert d["schema_version"] == 1
        assert d["kind"] == "oracle:pytest_log"
        assert d["oracle_class"] == 0
        assert d["exit_code"] == 0
        assert d["tests_total"] == 10
        assert d["tests_passed"] == 9

    def test_roundtrip(self):
        log = self._make_log(failures=[PytestFailure("t::f", "msg")])
        d = log.to_dict()
        restored = OraclePytestLog.from_dict(d)
        assert restored == log

    def test_to_json_is_canonical(self):
        """JSON is sorted + compact for content-addressing."""
        log = self._make_log()
        j = log.to_json()
        parsed = json.loads(j)
        # Re-encode should be identical (deterministic)
        j2 = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert j == j2

    def test_to_bytes_is_utf8(self):
        log = self._make_log()
        b = log.to_bytes()
        assert isinstance(b, bytes)
        assert json.loads(b.decode("utf-8"))["kind"] == "oracle:pytest_log"

    def test_all_passed_true(self):
        log = self._make_log(exit_code=0, tests_failed=0, tests_errored=0)
        assert log.all_passed is True

    def test_all_passed_false_on_failure(self):
        log = self._make_log(exit_code=1, tests_failed=1)
        assert log.all_passed is False

    def test_all_passed_false_on_error(self):
        log = self._make_log(exit_code=0, tests_errored=1)
        assert log.all_passed is False

    def test_kind_is_oracle_pytest_log(self):
        log = self._make_log()
        assert log.kind == "oracle:pytest_log"


# =============================================================================
# Hash binding
# =============================================================================


class TestHashBinding:
    """Hashes bind artifacts to evidence refs. Tampering breaks verification."""

    def test_same_bytes_same_hash(self):
        data = b"hello world"
        assert _sha256(data) == _sha256(data)

    def test_different_bytes_different_hash(self):
        assert _sha256(b"hello") != _sha256(b"world")

    def test_log_hash_changes_with_content(self):
        """If log content changes, log_sha256 changes."""
        log1 = b"test output: 5 passed"
        log2 = b"test output: 4 passed, 1 failed"
        assert _sha256(log1) != _sha256(log2)


# =============================================================================
# Runner (subprocess pytest execution)
# =============================================================================


class TestPytestRunner:
    """Run actual pytest and produce artifacts."""

    def test_run_passing_tests(self, tmp_path):
        """Run a real pytest on a trivial test file."""
        test_file = tmp_path / "test_trivial.py"
        test_file.write_text("def test_one(): assert 1 + 1 == 2\ndef test_two(): pass\n")

        runner = PytestRunner()
        result = runner.run(
            [str(test_file)],
            cwd=str(tmp_path),
            run_id="test-run",
        )

        assert result.log.exit_code == 0
        assert result.log.tests_total == 2
        assert result.log.tests_passed == 2
        assert result.log.tests_failed == 0
        assert result.log.all_passed is True
        assert result.log.kind == "oracle:pytest_log"
        assert result.log.run_id == "test-run"

    def test_run_failing_test(self, tmp_path):
        test_file = tmp_path / "test_fail.py"
        test_file.write_text("def test_bad(): assert False\n")

        runner = PytestRunner()
        result = runner.run([str(test_file)], cwd=str(tmp_path))

        assert result.log.exit_code != 0
        assert result.log.tests_failed == 1
        assert result.log.all_passed is False
        assert len(result.log.failures) == 1

    def test_artifacts_have_stable_hashes(self, tmp_path):
        """Artifact hashes are deterministic and non-empty."""
        test_file = tmp_path / "test_hash.py"
        test_file.write_text("def test_ok(): pass\n")

        runner = PytestRunner()
        result = runner.run([str(test_file)], cwd=str(tmp_path))

        assert len(result.log.log_sha256) == 64  # sha256 hex
        assert len(result.log.junit_xml_sha256) == 64
        # Verify hashes match actual content
        assert _sha256(result.log_bytes) == result.log.log_sha256
        assert _sha256(result.junit_bytes) == result.log.junit_xml_sha256

    def test_environment_captured(self, tmp_path):
        test_file = tmp_path / "test_env.py"
        test_file.write_text("def test_ok(): pass\n")

        runner = PytestRunner()
        result = runner.run([str(test_file)], cwd=str(tmp_path))

        assert "python_version" in result.log.environment
        assert "platform" in result.log.environment

    def test_duration_recorded(self, tmp_path):
        test_file = tmp_path / "test_dur.py"
        test_file.write_text("def test_ok(): pass\n")

        runner = PytestRunner()
        result = runner.run([str(test_file)], cwd=str(tmp_path))

        assert result.log.duration_s > 0
        assert result.log.end_ts > result.log.start_ts

    def test_oracle_class_default_is_zero(self, tmp_path):
        """Class 0 = local. Same host, same session. Weak independence."""
        test_file = tmp_path / "test_cls.py"
        test_file.write_text("def test_ok(): pass\n")

        runner = PytestRunner()
        result = runner.run([str(test_file)], cwd=str(tmp_path))
        assert result.log.oracle_class == 0

    def test_skipped_tests(self, tmp_path):
        test_file = tmp_path / "test_skip.py"
        test_file.write_text(
            "import pytest\n"
            "@pytest.mark.skip(reason='not today')\n"
            "def test_skip(): pass\n"
            "def test_ok(): pass\n"
        )

        runner = PytestRunner()
        result = runner.run([str(test_file)], cwd=str(tmp_path))

        assert result.log.tests_skipped == 1
        assert result.log.tests_passed == 1


# =============================================================================
# Evidence Gate integration — the HARD→PASS path
# =============================================================================


class TestEvidenceGateOracleIntegration:
    """Oracle evidence makes HARD claims earn PASS in confidence.sanity."""

    @pytest.fixture
    def store(self, tmp_path):
        from receipt_kernel.store_sqlite import SqliteReceiptStore
        s = SqliteReceiptStore(str(tmp_path / "test.db"), redaction_enabled=False)
        s.initialize_schema()
        yield s
        s.close()

    @pytest.fixture
    def bridge(self, store):
        from governor.receipt_bridge import ReceiptKernelBridge
        return ReceiptKernelBridge(
            store=store,
            policy_id="evidence_gate_v1",
            policy_version="0.3",
            stage_graph_id="v1_default",
        )

    @pytest.fixture
    def gate(self, bridge):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig
        return EvidenceGate(
            config=EvidenceGateConfig(strict=False),
            kernel_bridge=bridge,
        )

    def _make_oracle_log(self, run_id: str = "") -> OraclePytestLog:
        """Create a passing oracle log without running pytest."""
        return OraclePytestLog(
            schema_version=1,
            kind="oracle:pytest_log",
            oracle_class=0,
            run_id=run_id,
            cmd=["python3", "-m", "pytest", "tests/"],
            cwd="/repo",
            start_ts=1000.0,
            end_ts=1002.0,
            duration_s=2.0,
            exit_code=0,
            junit_xml_sha256=_sha256(b"<junit/>"),
            log_sha256=_sha256(b"all passed"),
            tests_total=10,
            tests_passed=10,
            tests_failed=0,
            tests_errored=0,
            tests_skipped=0,
            failures=[],
            environment={"python_version": "3.12"},
            git={"commit": "abc123"},
        )

    def test_hard_claim_without_oracle_fails_confidence_sanity(self, gate, store):
        """HARD claim + no oracle → confidence.sanity FAIL (model:generated is WEAK)."""
        from receipt_kernel.invariants import ConfidenceSanityInvariant
        from receipt_kernel.types import Verdict

        result = gate.check(
            task="verify",
            context="code",
            output="This guarantees thread safety.",
        )
        inv = ConfidenceSanityInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.FAIL
        assert any(reason.code == "HIGH_CONFIDENCE_WEAK_EVIDENCE" for reason in r.reasons)

    def test_hard_claim_with_oracle_passes_confidence_sanity(self, gate, store):
        """HARD claim + oracle:pytest_log → confidence.sanity PASS.

        This is THE test: oracle evidence upgrades claim backing from
        WEAK (model:generated) to STRONG (oracle:pytest_log), satisfying
        the invariant.
        """
        from receipt_kernel.invariants import ConfidenceSanityInvariant
        from receipt_kernel.types import Verdict

        oracle = self._make_oracle_log()
        result = gate.check(
            task="verify",
            context="code",
            output="This guarantees thread safety.",
            oracle_evidence=[oracle],
        )
        inv = ConfidenceSanityInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS, f"Expected PASS but got {r.verdict}: {r.reasons}"

    def test_oracle_blob_stored_in_kernel(self, gate, store):
        """Oracle evidence is stored as a COLLECT-stage blob."""
        oracle = self._make_oracle_log()
        result = gate.check(
            task="t", context="c", output="Tests pass.",
            oracle_evidence=[oracle],
        )
        events = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        keys = [e["payload"]["key"] for e in events]
        assert "oracle_pytest_log" in keys  # colon replaced with underscore

    def test_oracle_blob_has_correct_kind_tag(self, gate, store):
        """The evidence_kind tag on the oracle blob is oracle:pytest_log."""
        oracle = self._make_oracle_log()
        result = gate.check(
            task="t", context="c", output="Test output.",
            oracle_evidence=[oracle],
        )
        events = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        oracle_events = [
            e for e in events
            if e["payload"]["key"] == "oracle_pytest_log"
        ]
        assert len(oracle_events) == 1
        assert oracle_events[0]["payload"]["meta"]["evidence_kind"] == "oracle:pytest_log"

    def test_oracle_class_recorded(self, gate, store):
        """Oracle class is recorded in evidence metadata for future policy."""
        oracle = self._make_oracle_log()
        result = gate.check(
            task="t", context="c", output="Test output.",
            oracle_evidence=[oracle],
        )
        events = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        oracle_events = [
            e for e in events
            if e["payload"]["key"] == "oracle_pytest_log"
        ]
        assert oracle_events[0]["payload"]["meta"]["oracle_class"] == 0

    def test_hard_claims_reference_oracle_blob(self, gate, store):
        """HARD claims in the claims_map include oracle blob refs."""
        from governor.evidence_gate import ClaimLevel

        oracle = self._make_oracle_log()
        result = gate.check(
            task="verify",
            context="code",
            output="This guarantees thread safety.",
            oracle_evidence=[oracle],
        )
        # Get claims_map blob
        events = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        claims_events = [e for e in events if e["payload"]["key"] == "claims_map"]
        assert len(claims_events) == 1

        blob_ref = claims_events[0]["payload"]["evidence"]["ref"]
        blob_sha = blob_ref.split(":")[-1] if ":" in blob_ref else None
        if blob_sha:
            blob_data = store.get_blob(blob_sha)
            if blob_data:
                claims_map = json.loads(blob_data)
                hard_claims = [c for c in claims_map.get("claims", []) if c["confidence"] == "high"]
                assert len(hard_claims) > 0
                # Hard claims should have more than just the output ref
                for hc in hard_claims:
                    assert len(hc["evidence_refs"]) > 1, "HARD claims should reference oracle blob"

    def test_soft_claims_dont_get_oracle_refs(self, gate, store):
        """SOFT claims stay with output-only refs (no upgrade needed)."""
        oracle = self._make_oracle_log()
        result = gate.check(
            task="t", context="c",
            output="This should improve performance slightly.",
            oracle_evidence=[oracle],
        )
        events = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        claims_events = [e for e in events if e["payload"]["key"] == "claims_map"]
        if claims_events:
            blob_ref = claims_events[0]["payload"]["evidence"]["ref"]
            blob_sha = blob_ref.split(":")[-1] if ":" in blob_ref else None
            if blob_sha:
                blob_data = store.get_blob(blob_sha)
                if blob_data:
                    claims_map = json.loads(blob_data)
                    soft_claims = [c for c in claims_map.get("claims", []) if c["confidence"] == "low"]
                    for sc in soft_claims:
                        # Soft claims should only have the output ref
                        assert len(sc["evidence_refs"]) <= 1

    def test_multiple_oracles(self, gate, store):
        """Multiple oracle artifacts can be attached."""
        oracle1 = self._make_oracle_log()
        oracle2 = OraclePytestLog(
            schema_version=1,
            kind="oracle:pytest_log",
            oracle_class=0,
            run_id="",
            cmd=["python3", "-m", "pytest", "tests/integration"],
            cwd="/repo",
            start_ts=2000.0, end_ts=2005.0, duration_s=5.0,
            exit_code=0,
            junit_xml_sha256=_sha256(b"<junit2/>"),
            log_sha256=_sha256(b"integration passed"),
            tests_total=5, tests_passed=5, tests_failed=0, tests_errored=0, tests_skipped=0,
            failures=[], environment={}, git={},
        )
        result = gate.check(
            task="t", context="c", output="All tests pass.",
            oracle_evidence=[oracle1, oracle2],
        )
        events = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        oracle_events = [
            e for e in events
            if e["payload"]["meta"].get("evidence_kind") == "oracle:pytest_log"
        ]
        assert len(oracle_events) == 2

    def test_check_without_oracle_still_works(self, gate, store):
        """Backward compatibility: check() without oracle_evidence works."""
        result = gate.check(task="t", context="c", output="Hello world.")
        assert result.kernel_run_id is not None
        assert result.kernel_ok is True


# =============================================================================
# Evidence strength mapping
# =============================================================================


class TestEvidenceStrengthMapping:
    """oracle:pytest_log is STRONG in the kernel taxonomy."""

    def test_pytest_log_is_strong(self):
        from receipt_kernel.types import EvidenceStrength, strength_for_kind
        assert strength_for_kind("oracle:pytest_log") == EvidenceStrength.STRONG

    def test_model_generated_is_weak(self):
        from receipt_kernel.types import EvidenceStrength, strength_for_kind
        assert strength_for_kind("model:generated") == EvidenceStrength.WEAK

    def test_model_self_report_is_weak(self):
        from receipt_kernel.types import EvidenceStrength, strength_for_kind
        assert strength_for_kind("model:self_report") == EvidenceStrength.WEAK

    def test_oracle_stronger_than_model(self):
        from receipt_kernel.types import EvidenceStrength, strength_for_kind
        oracle = strength_for_kind("oracle:pytest_log")
        model = strength_for_kind("model:generated")
        rank = {"strong": 3, "medium": 2, "weak": 1}
        assert rank[oracle.value] > rank[model.value]


# =============================================================================
# End-to-end: runner + gate
# =============================================================================


class TestEndToEnd:
    """Run real pytest, feed oracle to gate, verify confidence.sanity PASS."""

    @pytest.fixture
    def store(self, tmp_path):
        from receipt_kernel.store_sqlite import SqliteReceiptStore
        s = SqliteReceiptStore(str(tmp_path / "e2e.db"), redaction_enabled=False)
        s.initialize_schema()
        yield s
        s.close()

    @pytest.fixture
    def bridge(self, store):
        from governor.receipt_bridge import ReceiptKernelBridge
        return ReceiptKernelBridge(
            store=store,
            policy_id="evidence_gate_v1",
            policy_version="0.3",
            stage_graph_id="v1_default",
        )

    @pytest.fixture
    def gate(self, bridge):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig
        return EvidenceGate(
            config=EvidenceGateConfig(strict=False),
            kernel_bridge=bridge,
        )

    def test_real_pytest_run_makes_hard_claim_pass(self, gate, store, tmp_path):
        """The full loop: real pytest → oracle artifact → gate → confidence.sanity PASS."""
        from receipt_kernel.invariants import ConfidenceSanityInvariant
        from receipt_kernel.types import Verdict

        # 1. Write a real test file
        test_file = tmp_path / "test_real.py"
        test_file.write_text("def test_real(): assert True\n")

        # 2. Run pytest (real subprocess)
        runner = PytestRunner()
        pytest_result = runner.run([str(test_file)], cwd=str(tmp_path))
        assert pytest_result.log.all_passed

        # 3. Feed oracle to evidence gate with a HARD claim
        result = gate.check(
            task="verify thread safety",
            context="concurrent module",
            output="This guarantees thread safety.",
            oracle_evidence=[pytest_result.log],
        )

        # 4. Verify confidence.sanity PASS (not FAIL like without oracle)
        inv = ConfidenceSanityInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS, f"Expected PASS but got {r.verdict}: {r.reasons}"
