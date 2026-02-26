# SPDX-License-Identifier: Apache-2.0
"""
Tests for the Verifier Gate — composition boundary for mechanical verification.

~102 tests across 14 categories:
- Candidate, VerifierEntry, VerifierSuite, FlakePolicy, EnvFingerprint
- VerifierResult, Verdict + RunStatus, aggregate_verdict, run_verifier
- run_suite, Monotonicity, Receipt integration, Golden tests, Policy drift
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from governor.gate_receipt import GateReceiptSystem, canonical_json, content_hash
from governor.verifier_gate import (
    VALID_ARTIFACT_KINDS,
    VERIFIER_GATE,
    CheckOutcome,
    Candidate,
    EnvFingerprint,
    FlakePolicy,
    RunStatus,
    SuiteResult,
    Verdict,
    VerifierEntry,
    VerifierResult,
    VerifierSuite,
    _VERDICT_TO_GATE_VERDICT,
    _normalize_metrics,
    _safe_metric_value,
    aggregate_verdict,
    compute_env_fingerprint,
    is_monotonic,
    run_suite,
    run_verifier,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_candidate(**kwargs: Any) -> Candidate:
    defaults = {
        "candidate_id": "c1",
        "artifact_kind": "code_patch",
        "payload_hash": "abc123",
    }
    defaults.update(kwargs)
    return Candidate(**defaults)


def _make_entry(**kwargs: Any) -> VerifierEntry:
    defaults = {
        "verifier_id": "v1",
        "version": "1.0",
    }
    defaults.update(kwargs)
    return VerifierEntry(**defaults)


def _make_suite(entries=None, **kwargs: Any) -> VerifierSuite:
    if entries is None:
        entries = (_make_entry(),)
    defaults = {
        "suite_id": "s1",
        "version": "1.0",
        "entries": entries,
    }
    defaults.update(kwargs)
    return VerifierSuite(**defaults)


def _pass_fn() -> bool:
    return True


def _fail_fn() -> bool:
    return False


def _error_fn() -> bool:
    raise RuntimeError("boom")


# =============================================================================
# Category 1: Candidate (9 tests)
# =============================================================================


class TestCandidate:
    def test_construction(self) -> None:
        c = _make_candidate()
        assert c.candidate_id == "c1"
        assert c.artifact_kind == "code_patch"
        assert c.payload_hash == "abc123"

    def test_frozen(self) -> None:
        c = _make_candidate()
        with pytest.raises(AttributeError):
            c.candidate_id = "new"  # type: ignore[misc]

    def test_content_hash_excludes_candidate_id(self) -> None:
        c1 = _make_candidate(candidate_id="id_a")
        c2 = _make_candidate(candidate_id="id_b")
        assert c1.content_hash() == c2.content_hash()

    def test_content_hash_excludes_provenance(self) -> None:
        c1 = _make_candidate(provenance={"source": "agent_a"})
        c2 = _make_candidate(provenance={"source": "agent_b"})
        assert c1.content_hash() == c2.content_hash()

    def test_invalid_artifact_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid artifact_kind"):
            _make_candidate(artifact_kind="banana")

    def test_artifact_kind_normalization(self) -> None:
        c = _make_candidate(artifact_kind="  Code_Patch  ")
        assert c.artifact_kind == "code_patch"

    def test_scope_normalization(self) -> None:
        c = _make_candidate(proposed_scope=["  src/foo.py  ", "bar.py"])
        assert c.proposed_scope == ("src/foo.py", "bar.py")

    def test_provenance_normalization(self) -> None:
        c = _make_candidate(provenance={"z_key": "z_val", "a_key": "a_val"})
        assert c.provenance == (("a_key", "a_val"), ("z_key", "z_val"))

    def test_to_dict(self) -> None:
        c = _make_candidate(
            base_ref="main",
            declared_intent="fix bug",
            proposed_scope=["src/a.py"],
            provenance={"source": "test"},
        )
        d = c.to_dict()
        assert d["candidate_id"] == "c1"
        assert d["artifact_kind"] == "code_patch"
        assert d["base_ref"] == "main"
        assert d["declared_intent"] == "fix bug"
        assert d["proposed_scope"] == ["src/a.py"]
        assert d["provenance"] == {"source": "test"}


# =============================================================================
# Category 2: VerifierEntry (6 tests)
# =============================================================================


class TestVerifierEntry:
    def test_construction(self) -> None:
        e = _make_entry()
        assert e.verifier_id == "v1"
        assert e.version == "1.0"

    def test_defaults(self) -> None:
        e = _make_entry()
        assert e.required is True
        assert e.timeout_s == 300
        assert e.run_contract == ()

    def test_frozen(self) -> None:
        e = _make_entry()
        with pytest.raises(AttributeError):
            e.verifier_id = "new"  # type: ignore[misc]

    def test_invalid_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout_s must be > 0"):
            _make_entry(timeout_s=0)
        with pytest.raises(ValueError, match="timeout_s must be > 0"):
            _make_entry(timeout_s=-1)

    def test_run_contract_normalization(self) -> None:
        e = _make_entry(run_contract={"z": "1", "a": "2"})
        assert e.run_contract == (("a", "2"), ("z", "1"))

    def test_to_dict(self) -> None:
        e = _make_entry(run_contract={"key": "val"})
        d = e.to_dict()
        assert d["verifier_id"] == "v1"
        assert d["run_contract"] == {"key": "val"}


# =============================================================================
# Category 3: VerifierSuite (9 tests)
# =============================================================================


class TestVerifierSuite:
    def test_construction(self) -> None:
        s = _make_suite()
        assert s.suite_id == "s1"
        assert s.version == "1.0"
        assert len(s.entries) == 1

    def test_get_entry(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s = _make_suite(entries=(e1, e2))
        assert s.get_entry("v1") is e1
        assert s.get_entry("v2") is e2
        assert s.get_entry("v3") is None

    def test_required_ids(self) -> None:
        e1 = _make_entry(verifier_id="v1", required=True)
        e2 = _make_entry(verifier_id="v2", required=False)
        s = _make_suite(entries=(e1, e2))
        assert s.required_ids() == frozenset({"v1"})

    def test_all_ids(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s = _make_suite(entries=(e1, e2))
        assert s.all_ids() == frozenset({"v1", "v2"})

    def test_policy_hash_determinism(self) -> None:
        s1 = _make_suite()
        s2 = _make_suite()
        assert s1.policy_hash() == s2.policy_hash()

    def test_duplicate_verifier_id_raises(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v1", version="2.0")
        with pytest.raises(ValueError, match="Duplicate verifier_id"):
            _make_suite(entries=(e1, e2))

    def test_empty_entries_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one entry"):
            _make_suite(entries=())

    def test_env_fingerprint_required(self) -> None:
        s = _make_suite(env_fingerprint_required=True)
        assert s.env_fingerprint_required is True
        assert s.policy_dict()["env_fingerprint_required"] is True

    def test_policy_hash_changes_on_field_change(self) -> None:
        base = _make_suite()
        # Changing timeout_s
        s2 = _make_suite(entries=(_make_entry(timeout_s=600),))
        assert base.policy_hash() != s2.policy_hash()
        # Changing run_contract
        s3 = _make_suite(entries=(_make_entry(run_contract={"k": "v"}),))
        assert base.policy_hash() != s3.policy_hash()
        # Changing flake_policy
        s4 = _make_suite(flake_policy=FlakePolicy(max_reruns=3))
        assert base.policy_hash() != s4.policy_hash()
        # Changing env_required
        s5 = _make_suite(env_fingerprint_required=True)
        assert base.policy_hash() != s5.policy_hash()


# =============================================================================
# Category 4: FlakePolicy (6 tests)
# =============================================================================


class TestFlakePolicy:
    def test_defaults(self) -> None:
        fp = FlakePolicy()
        assert fp.max_reruns == 0
        assert fp.max_flake_score == 0.0
        assert fp.quarantine_on_flake is True

    def test_negative_reruns_raises(self) -> None:
        with pytest.raises(ValueError, match="max_reruns must be >= 0"):
            FlakePolicy(max_reruns=-1)

    def test_score_too_low_raises(self) -> None:
        with pytest.raises(ValueError, match="max_flake_score must be in"):
            FlakePolicy(max_flake_score=-0.1)

    def test_score_too_high_raises(self) -> None:
        with pytest.raises(ValueError, match="max_flake_score must be in"):
            FlakePolicy(max_flake_score=1.1)

    def test_zero_tolerance(self) -> None:
        fp = FlakePolicy(max_reruns=0, max_flake_score=0.0)
        assert fp.max_flake_score == 0.0

    def test_to_dict(self) -> None:
        fp = FlakePolicy(max_reruns=2, max_flake_score=0.5, quarantine_on_flake=False)
        d = fp.to_dict()
        assert d == {
            "max_reruns": 2,
            "max_flake_score": 0.5,
            "quarantine_on_flake": False,
        }


# =============================================================================
# Category 5: EnvFingerprint (10 tests)
# =============================================================================


class TestEnvFingerprint:
    def test_construction(self) -> None:
        ef = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        assert ef.python_version == "3.11.0"
        assert ef.platform_str == "Linux-6.8"
        assert ef.git_sha is None
        assert ef.dependency_lock_hash is None
        assert ef.extra == ()

    def test_fingerprint_determinism(self) -> None:
        ef1 = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        ef2 = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        assert ef1.fingerprint() == ef2.fingerprint()

    def test_field_change_changes_hash(self) -> None:
        ef1 = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        ef2 = EnvFingerprint(python_version="3.12.0", platform_str="Linux-6.8")
        assert ef1.fingerprint() != ef2.fingerprint()

    def test_platform_change_changes_hash(self) -> None:
        ef1 = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        ef2 = EnvFingerprint(python_version="3.11.0", platform_str="Darwin-23.0")
        assert ef1.fingerprint() != ef2.fingerprint()

    def test_git_sha_change_changes_hash(self) -> None:
        ef1 = EnvFingerprint(
            python_version="3.11.0", platform_str="Linux-6.8", git_sha="aaa",
        )
        ef2 = EnvFingerprint(
            python_version="3.11.0", platform_str="Linux-6.8", git_sha="bbb",
        )
        assert ef1.fingerprint() != ef2.fingerprint()

    def test_none_normalization(self) -> None:
        ef1 = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        ef2 = EnvFingerprint(
            python_version="3.11.0", platform_str="Linux-6.8",
            git_sha=None, dependency_lock_hash=None,
        )
        assert ef1.fingerprint() == ef2.fingerprint()

    def test_extra_normalization_sorting(self) -> None:
        ef = EnvFingerprint(
            python_version="3.11.0", platform_str="Linux-6.8",
            extra={"z_key": "z_val", "a_key": "a_val"},
        )
        assert ef.extra == (("a_key", "a_val"), ("z_key", "z_val"))

    def test_to_dict_minimal(self) -> None:
        ef = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        d = ef.to_dict()
        assert d == {"python_version": "3.11.0", "platform_str": "Linux-6.8"}
        assert "git_sha" not in d
        assert "extra" not in d

    def test_to_dict_full(self) -> None:
        ef = EnvFingerprint(
            python_version="3.11.0",
            platform_str="Linux-6.8",
            git_sha="abc123",
            dependency_lock_hash="lock456",
            extra={"container": "sha256:xyz"},
        )
        d = ef.to_dict()
        assert d["git_sha"] == "abc123"
        assert d["dependency_lock_hash"] == "lock456"
        assert d["extra"] == {"container": "sha256:xyz"}

    def test_fingerprint_hex_format(self) -> None:
        ef = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        fp = ef.fingerprint()
        assert len(fp) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in fp)


# =============================================================================
# Category 6: VerifierResult (9 tests)
# =============================================================================


class TestVerifierResult:
    def test_construction(self) -> None:
        vr = VerifierResult(
            verifier_id="v1", version="1.0", passed=True,
            status=RunStatus.PASS, runs=1, failures=0,
            flake_score=0.0, duration_ms=100,
        )
        assert vr.passed is True
        assert vr.runs == 1

    def test_flake_score(self) -> None:
        vr = VerifierResult(
            verifier_id="v1", version="1.0", passed=True,
            status=RunStatus.PASS, runs=3, failures=1,
            flake_score=1 / 3, duration_ms=100,
        )
        assert abs(vr.flake_score - 1 / 3) < 1e-9

    def test_metrics_normalization(self) -> None:
        metrics = _normalize_metrics({"z_key": 1, "a_key": 2})
        assert metrics == (("a_key", 2), ("z_key", 1))

    def test_metrics_non_json_safe_raises(self) -> None:
        with pytest.raises(TypeError, match="not JSON-safe"):
            _safe_metric_value(set())
        with pytest.raises(TypeError, match="not JSON-safe"):
            _safe_metric_value(b"bytes")
        with pytest.raises(TypeError, match="NaN"):
            _safe_metric_value(float("nan"))
        with pytest.raises(TypeError, match="NaN|Infinity"):
            _safe_metric_value(float("inf"))

    def test_stable_dict_excludes_runtime_noise(self) -> None:
        vr = VerifierResult(
            verifier_id="v1", version="1.0", passed=True,
            status=RunStatus.PASS, runs=1, failures=0,
            flake_score=0.0, duration_ms=999,
            error_message="some error",
            metrics=(("key", "val"),),
        )
        sd = vr.stable_dict()
        assert "duration_ms" not in sd
        assert "error_message" not in sd
        assert "metrics" not in sd
        assert "status" not in sd
        assert "flake_score" not in sd  # float — derivable from failures/runs
        assert sd["verifier_id"] == "v1"
        assert sd["passed"] is True
        assert sd["runs"] == 1
        assert sd["failures"] == 0

    def test_to_dict(self) -> None:
        vr = VerifierResult(
            verifier_id="v1", version="1.0", passed=False,
            status=RunStatus.ERROR, runs=1, failures=1,
            flake_score=1.0, duration_ms=50,
            error_message="RuntimeError: boom",
            metrics=(("latency", 42),),
        )
        d = vr.to_dict()
        assert d["status"] == "error"
        assert d["error_message"] == "RuntimeError: boom"
        assert d["metrics"] == {"latency": 42}

    def test_frozen(self) -> None:
        vr = VerifierResult(
            verifier_id="v1", version="1.0", passed=True,
            status=RunStatus.PASS, runs=1, failures=0,
            flake_score=0.0, duration_ms=100,
        )
        with pytest.raises(AttributeError):
            vr.passed = False  # type: ignore[misc]

    def test_zero_runs(self) -> None:
        vr = VerifierResult(
            verifier_id="v1", version="1.0", passed=False,
            status=RunStatus.MISSING, runs=0, failures=0,
            flake_score=0.0, duration_ms=0,
        )
        assert vr.runs == 0
        assert vr.status == RunStatus.MISSING

    def test_status_field(self) -> None:
        for status in RunStatus:
            vr = VerifierResult(
                verifier_id="v1", version="1.0", passed=True,
                status=status, runs=1, failures=0,
                flake_score=0.0, duration_ms=10,
            )
            assert vr.status == status


# =============================================================================
# Category 7: Verdict + RunStatus (6 tests)
# =============================================================================


class TestVerdictAndRunStatus:
    def test_verdict_values(self) -> None:
        assert Verdict.PASS.value == "pass"
        assert Verdict.FAIL.value == "fail"
        assert Verdict.QUARANTINE.value == "quarantine"
        assert Verdict.NEEDS_HUMAN.value == "needs_human"
        assert Verdict.INCONCLUSIVE.value == "inconclusive"

    def test_verdict_mapping_completeness(self) -> None:
        for v in Verdict:
            assert v in _VERDICT_TO_GATE_VERDICT

    def test_verdict_string_coercion(self) -> None:
        assert str(Verdict.PASS) == "Verdict.PASS"
        assert Verdict("pass") == Verdict.PASS

    def test_run_status_values(self) -> None:
        assert RunStatus.PASS.value == "pass"
        assert RunStatus.FAIL.value == "fail"
        assert RunStatus.ERROR.value == "error"
        assert RunStatus.MISSING.value == "missing"

    def test_run_status_count(self) -> None:
        assert len(RunStatus) == 4

    def test_verdict_count(self) -> None:
        assert len(Verdict) == 5


# =============================================================================
# Category 8: aggregate_verdict (16 tests)
# =============================================================================


class TestAggregateVerdict:
    def _vr(
        self, vid: str = "v1", passed: bool = True,
        runs: int = 1, failures: int = 0, flake_score: float = 0.0,
    ) -> VerifierResult:
        status = RunStatus.PASS if passed else (RunStatus.FAIL if runs > 0 else RunStatus.MISSING)
        return VerifierResult(
            verifier_id=vid, version="1.0", passed=passed,
            status=status, runs=runs, failures=failures,
            flake_score=flake_score, duration_ms=10,
        )

    def test_all_pass(self) -> None:
        s = _make_suite(entries=(_make_entry(verifier_id="v1"),))
        results = (self._vr("v1"),)
        assert aggregate_verdict(results, s) == Verdict.PASS

    def test_required_fail(self) -> None:
        s = _make_suite(entries=(_make_entry(verifier_id="v1"),))
        results = (self._vr("v1", passed=False, runs=1, failures=1),)
        assert aggregate_verdict(results, s) == Verdict.FAIL

    def test_advisory_fail_ignored(self) -> None:
        e1 = _make_entry(verifier_id="v1", required=True)
        e2 = _make_entry(verifier_id="v2", required=False)
        s = _make_suite(entries=(e1, e2))
        results = (
            self._vr("v1", passed=True),
            self._vr("v2", passed=False, runs=1, failures=1),
        )
        assert aggregate_verdict(results, s) == Verdict.PASS

    def test_fail_before_inconclusive(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s = _make_suite(entries=(e1, e2))
        results = (
            self._vr("v1", passed=False, runs=1, failures=1),
            self._vr("v2", passed=False, runs=0),
        )
        assert aggregate_verdict(results, s) == Verdict.FAIL

    def test_inconclusive_zero_runs(self) -> None:
        s = _make_suite(entries=(_make_entry(verifier_id="v1"),))
        results = (self._vr("v1", passed=False, runs=0),)
        assert aggregate_verdict(results, s) == Verdict.INCONCLUSIVE

    def test_missing_callable_is_inconclusive_not_fail(self) -> None:
        """passed=False, runs=0 should be INCONCLUSIVE, not FAIL."""
        s = _make_suite(entries=(_make_entry(verifier_id="v1"),))
        results = (self._vr("v1", passed=False, runs=0),)
        verdict = aggregate_verdict(results, s)
        assert verdict == Verdict.INCONCLUSIVE
        assert verdict != Verdict.FAIL

    def test_quarantine_flaky(self) -> None:
        s = _make_suite(
            entries=(_make_entry(verifier_id="v1"),),
            flake_policy=FlakePolicy(max_reruns=2, max_flake_score=0.3, quarantine_on_flake=True),
        )
        # 3 runs, 1 failure → flake_score = 0.333 > 0.3
        results = (self._vr("v1", passed=True, runs=3, failures=1, flake_score=1 / 3),)
        assert aggregate_verdict(results, s) == Verdict.QUARANTINE

    def test_quarantine_off_becomes_fail(self) -> None:
        s = _make_suite(
            entries=(_make_entry(verifier_id="v1"),),
            flake_policy=FlakePolicy(max_reruns=2, max_flake_score=0.3, quarantine_on_flake=False),
        )
        results = (self._vr("v1", passed=True, runs=3, failures=1, flake_score=1 / 3),)
        assert aggregate_verdict(results, s) == Verdict.FAIL

    def test_flake_below_threshold(self) -> None:
        s = _make_suite(
            entries=(_make_entry(verifier_id="v1"),),
            flake_policy=FlakePolicy(max_reruns=2, max_flake_score=0.5),
        )
        # 3 runs, 1 failure → flake_score = 0.333 < 0.5
        results = (self._vr("v1", passed=True, runs=3, failures=1, flake_score=1 / 3),)
        assert aggregate_verdict(results, s) == Verdict.PASS

    def test_mixed_verifiers(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s = _make_suite(entries=(e1, e2))
        results = (
            self._vr("v1", passed=True),
            self._vr("v2", passed=False, runs=1, failures=1),
        )
        assert aggregate_verdict(results, s) == Verdict.FAIL

    def test_empty_results_missing_required(self) -> None:
        """No results but required verifiers → INCONCLUSIVE."""
        s = _make_suite(entries=(_make_entry(verifier_id="v1"),))
        assert aggregate_verdict((), s) == Verdict.INCONCLUSIVE

    def test_threshold_boundary(self) -> None:
        """Flake score exactly at threshold → PASS (not >)."""
        s = _make_suite(
            entries=(_make_entry(verifier_id="v1"),),
            flake_policy=FlakePolicy(max_reruns=2, max_flake_score=0.5),
        )
        results = (self._vr("v1", passed=True, runs=2, failures=1, flake_score=0.5),)
        assert aggregate_verdict(results, s) == Verdict.PASS

    def test_multiple_quarantine(self) -> None:
        """Two flaky verifiers — first one triggers quarantine."""
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s = _make_suite(
            entries=(e1, e2),
            flake_policy=FlakePolicy(max_reruns=2, max_flake_score=0.2),
        )
        results = (
            self._vr("v1", passed=True, runs=3, failures=1, flake_score=1 / 3),
            self._vr("v2", passed=True, runs=3, failures=1, flake_score=1 / 3),
        )
        assert aggregate_verdict(results, s) == Verdict.QUARANTINE

    def test_required_fail_overrides_flaky(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s = _make_suite(
            entries=(e1, e2),
            flake_policy=FlakePolicy(max_reruns=2, max_flake_score=0.2),
        )
        results = (
            self._vr("v1", passed=False, runs=1, failures=1),
            self._vr("v2", passed=True, runs=3, failures=1, flake_score=1 / 3),
        )
        assert aggregate_verdict(results, s) == Verdict.FAIL

    def test_passed_false_runs_zero_is_inconclusive(self) -> None:
        """Explicit test: passed=False, runs=0 → INCONCLUSIVE."""
        s = _make_suite(entries=(_make_entry(verifier_id="v1"),))
        results = (self._vr("v1", passed=False, runs=0),)
        assert aggregate_verdict(results, s) == Verdict.INCONCLUSIVE

    def test_all_advisory_passes(self) -> None:
        """Suite with only advisory verifiers → PASS (no required)."""
        e1 = _make_entry(verifier_id="v1", required=False)
        s = _make_suite(entries=(e1,))
        results = (self._vr("v1", passed=False, runs=1, failures=1),)
        assert aggregate_verdict(results, s) == Verdict.PASS


# =============================================================================
# Category 9: run_verifier (12 tests)
# =============================================================================


class TestRunVerifier:
    def test_pass(self) -> None:
        entry = _make_entry()
        vr = run_verifier(entry, _pass_fn)
        assert vr.passed is True
        assert vr.runs == 1
        assert vr.failures == 0
        assert vr.status == RunStatus.PASS

    def test_fail(self) -> None:
        entry = _make_entry()
        vr = run_verifier(entry, _fail_fn)
        assert vr.passed is False
        assert vr.runs == 1
        assert vr.failures == 1
        assert vr.status == RunStatus.FAIL

    def test_reruns_on_failure(self) -> None:
        call_count = 0

        def flaky() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 3  # Fails first 2, passes on 3rd

        entry = _make_entry()
        vr = run_verifier(entry, flaky, max_reruns=4)
        assert vr.passed is True
        assert vr.runs == 3
        assert vr.failures == 2
        assert abs(vr.flake_score - 2 / 3) < 1e-9

    def test_flake_detection(self) -> None:
        call_count = 0

        def flaky() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        entry = _make_entry()
        vr = run_verifier(entry, flaky, max_reruns=2)
        assert vr.passed is True
        assert vr.failures > 0
        assert vr.flake_score > 0

    def test_exception_is_failure(self) -> None:
        entry = _make_entry()
        vr = run_verifier(entry, _error_fn)
        assert vr.passed is False
        assert vr.status == RunStatus.ERROR
        assert vr.error_message is not None
        assert "RuntimeError" in vr.error_message

    def test_metrics_via_tuple(self) -> None:
        def check() -> tuple[bool, dict[str, Any]]:
            return True, {"latency": 42, "count": 5}

        entry = _make_entry()
        vr = run_verifier(entry, check)
        assert vr.passed is True
        metrics_dict = dict(vr.metrics)
        assert metrics_dict["latency"] == 42
        assert metrics_dict["count"] == 5

    def test_metrics_via_check_outcome(self) -> None:
        def check() -> CheckOutcome:
            return CheckOutcome(passed=True, metrics=(("key", "val"),))

        entry = _make_entry()
        vr = run_verifier(entry, check)
        assert vr.passed is True
        assert dict(vr.metrics)["key"] == "val"

    def test_bool_coercion(self) -> None:
        def check() -> bool:
            return True

        entry = _make_entry()
        vr = run_verifier(entry, check)
        assert vr.passed is True
        assert vr.metrics == ()

    def test_timing(self) -> None:
        def slow_check() -> bool:
            time.sleep(0.05)
            return True

        entry = _make_entry()
        vr = run_verifier(entry, slow_check)
        assert vr.duration_ms >= 40  # At least 40ms

    def test_multiple_reruns_count(self) -> None:
        entry = _make_entry()
        vr = run_verifier(entry, _fail_fn, max_reruns=3)
        assert vr.runs == 4  # 1 + 3 reruns
        assert vr.failures == 4
        assert vr.passed is False

    def test_first_pass_stops(self) -> None:
        call_count = 0

        def check() -> bool:
            nonlocal call_count
            call_count += 1
            return True

        entry = _make_entry()
        vr = run_verifier(entry, check, max_reruns=5)
        assert call_count == 1
        assert vr.runs == 1

    def test_error_message_captured(self) -> None:
        def check() -> bool:
            raise ValueError("specific error message")

        entry = _make_entry()
        vr = run_verifier(entry, check)
        assert vr.error_message == "ValueError: specific error message"


# =============================================================================
# Category 10: run_suite (13 tests)
# =============================================================================


class TestRunSuite:
    def test_full_pipeline(self) -> None:
        c = _make_candidate()
        e = _make_entry(verifier_id="v1")
        s = _make_suite(entries=(e,))
        sr = run_suite(c, s, {"v1": _pass_fn})
        assert sr.verdict == Verdict.PASS
        assert len(sr.results) == 1
        assert sr.results[0].passed is True
        assert sr.suite_id == "s1"

    def test_missing_required_inconclusive(self) -> None:
        c = _make_candidate()
        e = _make_entry(verifier_id="v1")
        s = _make_suite(entries=(e,))
        sr = run_suite(c, s, {})  # No check provided
        assert sr.verdict == Verdict.INCONCLUSIVE
        assert len(sr.results) == 1
        assert sr.results[0].status == RunStatus.MISSING
        assert sr.results[0].runs == 0

    def test_missing_advisory_skipped(self) -> None:
        c = _make_candidate()
        e1 = _make_entry(verifier_id="v1", required=True)
        e2 = _make_entry(verifier_id="v2", required=False)
        s = _make_suite(entries=(e1, e2))
        sr = run_suite(c, s, {"v1": _pass_fn})  # v2 missing, advisory
        assert sr.verdict == Verdict.PASS
        assert len(sr.results) == 1  # v2 skipped entirely
        assert sr.results[0].verifier_id == "v1"

    def test_env_required_missing_early_return(self) -> None:
        c = _make_candidate()
        s = _make_suite(env_fingerprint_required=True)
        sr = run_suite(c, s, {"v1": _pass_fn}, env=None)
        assert sr.verdict == Verdict.INCONCLUSIVE
        assert len(sr.results) == 0  # No verifiers run

    def test_receipt_emission(self, tmp_path: Path) -> None:
        c = _make_candidate()
        s = _make_suite()
        rs = GateReceiptSystem(tmp_path)
        sr = run_suite(c, s, {"v1": _pass_fn}, receipt_system=rs)
        assert sr.receipt_emission_ok is True
        assert sr.receipt_hash is not None
        # Verify receipt was stored
        receipts = rs.query(gate=VERIFIER_GATE)
        assert len(receipts) == 1
        assert receipts[0].verdict == "pass"

    def test_no_receipt_system(self) -> None:
        c = _make_candidate()
        s = _make_suite()
        sr = run_suite(c, s, {"v1": _pass_fn})
        assert sr.receipt_emission_ok is None
        assert sr.receipt_hash is None

    def test_env_fingerprint_passthrough(self) -> None:
        c = _make_candidate()
        s = _make_suite()
        env = EnvFingerprint(python_version="3.11.0", platform_str="Linux-6.8")
        sr = run_suite(c, s, {"v1": _pass_fn}, env=env)
        assert sr.env_fingerprint == env.fingerprint()

    def test_policy_version_derived(self) -> None:
        c = _make_candidate()
        s = _make_suite()
        sr = run_suite(c, s, {"v1": _pass_fn})
        assert sr.policy_version == s.policy_hash()

    def test_multiple_verifiers(self) -> None:
        c = _make_candidate()
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s = _make_suite(entries=(e1, e2))
        sr = run_suite(c, s, {"v1": _pass_fn, "v2": _pass_fn})
        assert sr.verdict == Verdict.PASS
        assert len(sr.results) == 2

    def test_flake_policy_applied(self) -> None:
        call_count = 0

        def flaky() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        c = _make_candidate()
        e = _make_entry(verifier_id="v1")
        fp = FlakePolicy(max_reruns=3, max_flake_score=0.2)
        s = _make_suite(entries=(e,), flake_policy=fp)
        sr = run_suite(c, s, {"v1": flaky})
        # Passed on 2nd run, flake_score = 0.5 > 0.2 → QUARANTINE
        assert sr.verdict == Verdict.QUARANTINE

    def test_candidate_hash_and_base_ref_hash(self) -> None:
        c = _make_candidate(base_ref="main")
        s = _make_suite()
        sr = run_suite(c, s, {"v1": _pass_fn})
        assert sr.candidate_hash == c.content_hash()
        assert sr.base_ref_hash == content_hash("main".encode("utf-8"))

    def test_result_ordering_matches_entries(self) -> None:
        c = _make_candidate()
        e1 = _make_entry(verifier_id="alpha")
        e2 = _make_entry(verifier_id="beta")
        e3 = _make_entry(verifier_id="gamma")
        s = _make_suite(entries=(e1, e2, e3))
        sr = run_suite(c, s, {
            "alpha": _pass_fn,
            "beta": _fail_fn,
            "gamma": _pass_fn,
        })
        assert [r.verifier_id for r in sr.results] == ["alpha", "beta", "gamma"]

    def test_stable_receipt_hash_always_computed(self) -> None:
        c = _make_candidate()
        s = _make_suite()
        sr = run_suite(c, s, {"v1": _pass_fn})
        assert sr.stable_receipt_hash is not None
        assert len(sr.stable_receipt_hash) == 64


# =============================================================================
# Category 11: Monotonicity (4 tests)
# =============================================================================


class TestMonotonicity:
    def test_superset(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        e3 = _make_entry(verifier_id="v3")
        strict = _make_suite(suite_id="strict", entries=(e1, e2, e3))
        weak = _make_suite(suite_id="weak", entries=(e1, e2))
        assert is_monotonic(strict, weak) is True

    def test_subset(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        e3 = _make_entry(verifier_id="v3")
        strict = _make_suite(suite_id="strict", entries=(e1,))
        weak = _make_suite(suite_id="weak", entries=(e1, e2, e3))
        assert is_monotonic(strict, weak) is False

    def test_disjoint(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s1 = _make_suite(suite_id="s1", entries=(e1,))
        s2 = _make_suite(suite_id="s2", entries=(e2,))
        assert is_monotonic(s1, s2) is False

    def test_equal(self) -> None:
        e1 = _make_entry(verifier_id="v1")
        e2 = _make_entry(verifier_id="v2")
        s1 = _make_suite(suite_id="s1", entries=(e1, e2))
        s2 = _make_suite(suite_id="s2", entries=(e1, e2))
        assert is_monotonic(s1, s2) is True


# =============================================================================
# Category 12: Receipt Integration (6 tests)
# =============================================================================


class TestReceiptIntegration:
    def test_gate_name(self) -> None:
        assert VERIFIER_GATE == "verifier_gate"

    def test_verdict_mapping(self) -> None:
        assert _VERDICT_TO_GATE_VERDICT[Verdict.PASS] == "pass"
        assert _VERDICT_TO_GATE_VERDICT[Verdict.FAIL] == "block"
        assert _VERDICT_TO_GATE_VERDICT[Verdict.QUARANTINE] == "warn"
        assert _VERDICT_TO_GATE_VERDICT[Verdict.NEEDS_HUMAN] == "observe"
        assert _VERDICT_TO_GATE_VERDICT[Verdict.INCONCLUSIVE] == "observe"

    def test_evidence_keys_stable_only(self) -> None:
        c = _make_candidate()
        s = _make_suite()
        sr = run_suite(c, s, {"v1": _pass_fn})
        evidence = sr.stable_evidence_dict()
        # Should have these keys
        assert "candidate_hash" in evidence
        assert "suite_id" in evidence
        assert "verdict" in evidence
        assert "results" in evidence
        # Each result should be stable_dict (no duration, error, metrics, status, flake_score)
        for r in evidence["results"]:
            assert "duration_ms" not in r
            assert "error_message" not in r
            assert "metrics" not in r
            assert "status" not in r
            assert "flake_score" not in r  # float excluded — derivable from failures/runs

    def test_receipt_determinism(self, tmp_path: Path) -> None:
        c = _make_candidate()
        s = _make_suite()
        rs1 = GateReceiptSystem(tmp_path / "r1")
        rs2 = GateReceiptSystem(tmp_path / "r2")
        sr1 = run_suite(c, s, {"v1": _pass_fn}, receipt_system=rs1)
        sr2 = run_suite(c, s, {"v1": _pass_fn}, receipt_system=rs2)
        assert sr1.stable_receipt_hash == sr2.stable_receipt_hash

    def test_emission_failure_fail_open(self, tmp_path: Path) -> None:
        c = _make_candidate()
        s = _make_suite()
        # Create a receipt system that will fail
        rs = GateReceiptSystem(tmp_path)
        # Monkey-patch emit to raise
        original_emit = rs.emit
        def broken_emit(*args: Any, **kwargs: Any) -> None:
            raise OSError("disk full")
        rs.emit = broken_emit  # type: ignore[assignment]
        sr = run_suite(c, s, {"v1": _pass_fn}, receipt_system=rs)
        assert sr.receipt_emission_ok is False
        assert sr.receipt_emission_error is not None
        assert "disk full" in sr.receipt_emission_error
        # Verdict still computed correctly
        assert sr.verdict == Verdict.PASS

    def test_subject_includes_suite_identity(self, tmp_path: Path) -> None:
        c = _make_candidate()
        s1 = _make_suite(suite_id="suite_a", version="1.0")
        s2 = _make_suite(suite_id="suite_b", version="1.0")
        rs = GateReceiptSystem(tmp_path)
        sr1 = run_suite(c, s1, {"v1": _pass_fn}, receipt_system=rs)
        sr2 = run_suite(c, s2, {"v1": _pass_fn}, receipt_system=rs)
        # Different suites → different receipt hashes
        assert sr1.receipt_hash != sr2.receipt_hash


# =============================================================================
# Category 13: Golden Tests (2 tests)
# =============================================================================


class TestGolden:
    def test_stable_hash_ignores_runtime_noise(self) -> None:
        """Same inputs → same stable_receipt_hash regardless of duration."""
        c = _make_candidate()
        e = _make_entry(verifier_id="v1")
        s = _make_suite(entries=(e,))

        # Run twice — duration will differ
        sr1 = run_suite(c, s, {"v1": _pass_fn})
        sr2 = run_suite(c, s, {"v1": _pass_fn})
        assert sr1.stable_receipt_hash == sr2.stable_receipt_hash

        # Verify durations may differ but stable hash is identical
        # (This is the golden test contract)

    def test_flake_simulation_quarantine(self) -> None:
        """Flake simulation → QUARANTINE verdict with stable hash."""
        call_count = 0

        def flaky_a() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        c = _make_candidate()
        e = _make_entry(verifier_id="v1")
        fp = FlakePolicy(max_reruns=3, max_flake_score=0.2, quarantine_on_flake=True)
        s = _make_suite(entries=(e,), flake_policy=fp)
        sr = run_suite(c, s, {"v1": flaky_a})
        assert sr.verdict == Verdict.QUARANTINE

        # Reproduce with same flake behavior
        call_count_b = 0

        def flaky_b() -> bool:
            nonlocal call_count_b
            call_count_b += 1
            return call_count_b >= 2

        sr2 = run_suite(c, s, {"v1": flaky_b})
        assert sr2.verdict == Verdict.QUARANTINE
        assert sr.stable_receipt_hash == sr2.stable_receipt_hash


# =============================================================================
# Category 14: Policy Drift (4 tests)
# =============================================================================


class TestPolicyDrift:
    def test_timeout_change_changes_policy_hash(self) -> None:
        s1 = _make_suite(entries=(_make_entry(timeout_s=300),))
        s2 = _make_suite(entries=(_make_entry(timeout_s=600),))
        assert s1.policy_hash() != s2.policy_hash()

    def test_run_contract_change_changes_policy_hash(self) -> None:
        s1 = _make_suite(entries=(_make_entry(run_contract={}),))
        s2 = _make_suite(entries=(_make_entry(run_contract={"env": "prod"}),))
        assert s1.policy_hash() != s2.policy_hash()

    def test_flake_policy_change_changes_policy_hash(self) -> None:
        s1 = _make_suite(flake_policy=FlakePolicy())
        s2 = _make_suite(flake_policy=FlakePolicy(max_reruns=5))
        assert s1.policy_hash() != s2.policy_hash()

    def test_env_required_change_changes_policy_hash(self) -> None:
        s1 = _make_suite(env_fingerprint_required=False)
        s2 = _make_suite(env_fingerprint_required=True)
        assert s1.policy_hash() != s2.policy_hash()
