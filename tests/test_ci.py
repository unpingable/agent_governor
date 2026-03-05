# SPDX-License-Identifier: Apache-2.0
"""Tests for CI lane: ci_wrap, ci_verify, load_ci_receipts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from governor.ci import (
    CI_VERIFY_GATE,
    CI_WRAP_GATE,
    VALID_CI_KINDS,
    CiPolicy,
    CiReceiptBundle,
    CiVerifyResult,
    CiWrapResult,
    GitState,
    capture_git_state,
    ci_verify,
    ci_wrap,
    load_ci_receipts,
    _utc_now,
)
from governor.gate_receipt import GateReceipt, canonical_json, content_hash


# =============================================================================
# GitState
# =============================================================================

class TestGitState:
    def test_git_repo_returns_sha(self, tmp_path: Path) -> None:
        """In a real git repo, capture_git_state returns a SHA."""
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
                       capture_output=True, env={**os.environ, "GIT_AUTHOR_NAME": "test",
                       "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test",
                       "GIT_COMMITTER_EMAIL": "t@t"})
        state = capture_git_state(tmp_path)
        assert len(state.sha) == 40
        assert all(c in "0123456789abcdef" for c in state.sha)
        assert not state.dirty

    def test_non_repo_returns_empty(self, tmp_path: Path) -> None:
        """Outside a git repo, sha is empty and dirty is False."""
        state = capture_git_state(tmp_path)
        assert state.sha == ""
        assert not state.dirty

    def test_dirty_catches_untracked(self, tmp_path: Path) -> None:
        """Untracked files make dirty=True."""
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
                       capture_output=True, env={**os.environ, "GIT_AUTHOR_NAME": "test",
                       "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "test",
                       "GIT_COMMITTER_EMAIL": "t@t"})
        (tmp_path / "untracked.txt").write_text("hello")
        state = capture_git_state(tmp_path)
        assert state.dirty


# =============================================================================
# ci_wrap
# =============================================================================

class TestCiWrap:
    def test_pass_verdict(self, tmp_path: Path) -> None:
        """Command with exit 0 gets verdict=pass."""
        out = tmp_path / "receipts.jsonl"
        result = ci_wrap([sys.executable, "-c", "print('ok')"], "unit_tests", out)
        assert result.exit_code == 0
        assert result.receipt is not None
        assert result.receipt.verdict == "pass"
        assert result.receipt.gate == CI_WRAP_GATE

    def test_fail_verdict(self, tmp_path: Path) -> None:
        """Command with nonzero exit gets verdict=block."""
        out = tmp_path / "receipts.jsonl"
        result = ci_wrap([sys.executable, "-c", "import sys; sys.exit(1)"], "lint", out)
        assert result.exit_code == 1
        assert result.receipt is not None
        assert result.receipt.verdict == "block"

    def test_json_file_output(self, tmp_path: Path) -> None:
        """Single JSON file output."""
        out = tmp_path / "receipt.json"
        result = ci_wrap([sys.executable, "-c", "print('ok')"], "build", out)
        assert result.receipt_path == out
        data = json.loads(out.read_text())
        assert data["receipt"]["gate"] == CI_WRAP_GATE
        assert data["evidence"]["ci_kind"] == "build"

    def test_dir_output_auto_created(self, tmp_path: Path) -> None:
        """Directory mode creates dir and writes individual JSON."""
        out = tmp_path / "ci_receipts"
        result = ci_wrap([sys.executable, "-c", "print('ok')"], "lint", out)
        assert out.is_dir()
        files = list(out.glob("ci_wrap_lint_*.json"))
        assert len(files) == 1
        assert result.receipt_path == files[0]

    def test_evidence_keys(self, tmp_path: Path) -> None:
        """Evidence bundle has all expected keys."""
        out = tmp_path / "r.jsonl"
        ci_wrap([sys.executable, "-c", "print('ok')"], "unit_tests", out)
        data = json.loads(out.read_text().strip())
        ev = data["evidence"]
        expected_keys = {
            "exit_code", "stdout_hash", "stderr_hash",
            "stdout_truncated", "stderr_truncated",
            "git_sha", "dirty", "ci_kind", "command",
            "command_display", "python_version",
        }
        assert expected_keys <= set(ev.keys())

    def test_subject_deterministic(self, tmp_path: Path) -> None:
        """Same command + kind + git state = same subject_hash."""
        out1 = tmp_path / "r1.json"
        out2 = tmp_path / "r2.json"
        # Mock git state for determinism
        with patch("governor.ci.capture_git_state", return_value=GitState(sha="abc123", dirty=False)):
            r1 = ci_wrap([sys.executable, "-c", "print('ok')"], "lint", out1)
            r2 = ci_wrap([sys.executable, "-c", "print('ok')"], "lint", out2)
        assert r1.receipt.subject_hash == r2.receipt.subject_hash

    def test_evidence_hash_excludes_duration(self, tmp_path: Path) -> None:
        """evidence_hash is deterministic (no timing in evidence bundle)."""
        out1 = tmp_path / "r1.json"
        out2 = tmp_path / "r2.json"
        with patch("governor.ci.capture_git_state", return_value=GitState(sha="abc", dirty=False)):
            r1 = ci_wrap([sys.executable, "-c", ""], "lint", out1)
            r2 = ci_wrap([sys.executable, "-c", ""], "lint", out2)
        assert r1.receipt.evidence_hash == r2.receipt.evidence_hash

    def test_command_stored_as_list(self, tmp_path: Path) -> None:
        """Command is stored as argv list in evidence."""
        out = tmp_path / "r.json"
        cmd = [sys.executable, "-c", "print('hello world')"]
        ci_wrap(cmd, "build", out)
        data = json.loads(out.read_text())
        assert data["evidence"]["command"] == cmd

    def test_command_display_truncated(self, tmp_path: Path) -> None:
        """command_display is truncated at 500 chars."""
        out = tmp_path / "r.json"
        long_arg = "x" * 1000
        ci_wrap([sys.executable, "-c", long_arg], "build", out)
        data = json.loads(out.read_text())
        assert len(data["evidence"]["command_display"]) <= 500

    def test_stdout_cap_truncation_flag(self, tmp_path: Path) -> None:
        """stdout_truncated is set when output exceeds cap."""
        out = tmp_path / "r.json"
        # Patch cap to 10 bytes for test
        with patch("governor.ci._MAX_CAPTURE_BYTES", 10):
            ci_wrap([sys.executable, "-c", "print('x' * 100)"], "unit_tests", out)
        data = json.loads(out.read_text())
        assert data["evidence"]["stdout_truncated"] is True

    def test_fail_open_on_bad_path(self, tmp_path: Path, capsys) -> None:
        """Receipt emission failure is fail-open but warns to stderr."""
        # Use a path that can't be written (file where dir expected)
        blocker = tmp_path / "blocker"
        blocker.write_text("I'm a file, not a dir")
        bad_path = blocker / "sub" / "receipt.json"  # Can't create parent
        result = ci_wrap([sys.executable, "-c", "print('ok')"], "lint", bad_path)
        assert result.exit_code == 0  # Command succeeded
        assert result.receipt is None  # Emission failed
        captured = capsys.readouterr()
        assert "WARNING: receipt emission failed" in captured.err

    def test_exit_code_passthrough(self, tmp_path: Path) -> None:
        """Exit code is always the child process exit code."""
        out = tmp_path / "r.jsonl"
        result = ci_wrap([sys.executable, "-c", "import sys; sys.exit(42)"], "build", out)
        assert result.exit_code == 42

    def test_invalid_ci_kind_raises(self, tmp_path: Path) -> None:
        """Invalid ci_kind raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ci_kind"):
            ci_wrap([sys.executable, "-c", ""], "invalid_kind", tmp_path / "r.json")

    def test_timestamps_utc_z(self, tmp_path: Path) -> None:
        """Timestamps use UTC Z-suffix."""
        out = tmp_path / "r.json"
        result = ci_wrap([sys.executable, "-c", ""], "lint", out)
        assert result.receipt.timestamp.endswith("Z")


# =============================================================================
# load_ci_receipts
# =============================================================================

class TestLoadCiReceipts:
    def _make_bundle(self, ci_kind: str = "lint", verdict: str = "pass",
                     git_sha: str = "abc123", dirty: bool = False,
                     gate: str = CI_WRAP_GATE, timestamp: str = "2026-01-01T00:00:00Z") -> CiReceiptBundle:
        from governor.gate_receipt import create_receipt
        evidence = {
            "exit_code": 0 if verdict == "pass" else 1,
            "stdout_hash": "aaa", "stderr_hash": "bbb",
            "stdout_truncated": False, "stderr_truncated": False,
            "git_sha": git_sha, "dirty": dirty,
            "ci_kind": ci_kind, "command": ["echo"],
            "command_display": "echo", "python_version": "3.11.0",
        }
        receipt = create_receipt(
            gate=gate, verdict=verdict, subject_kind="ci_wrap",
            subject_bytes=b"test", evidence_bundle=evidence,
            gate_config={"ci_kind": ci_kind}, timestamp=timestamp,
        )
        return CiReceiptBundle(receipt=receipt, evidence=evidence)

    def test_jsonl_file(self, tmp_path: Path) -> None:
        """Load from JSONL file."""
        f = tmp_path / "receipts.jsonl"
        b1 = self._make_bundle("lint", timestamp="2026-01-01T00:00:00Z")
        b2 = self._make_bundle("build", timestamp="2026-01-01T00:00:01Z")
        f.write_text(b1.to_json() + "\n" + b2.to_json() + "\n")
        loaded = load_ci_receipts(f)
        assert len(loaded) == 2
        assert loaded[0].evidence["ci_kind"] == "lint"
        assert loaded[1].evidence["ci_kind"] == "build"

    def test_directory_individual_json(self, tmp_path: Path) -> None:
        """Load from directory with individual JSON files."""
        d = tmp_path / "receipts"
        d.mkdir()
        b = self._make_bundle("typecheck")
        (d / "r1.json").write_text(b.to_json())
        loaded = load_ci_receipts(d)
        assert len(loaded) == 1

    def test_mixed_dir(self, tmp_path: Path) -> None:
        """Directory with both .json and .jsonl files."""
        d = tmp_path / "receipts"
        d.mkdir()
        b1 = self._make_bundle("lint", timestamp="2026-01-01T00:00:00Z")
        b2 = self._make_bundle("build", timestamp="2026-01-01T00:00:01Z")
        (d / "a.json").write_text(b1.to_json())
        (d / "b.jsonl").write_text(b2.to_json() + "\n")
        loaded = load_ci_receipts(d)
        assert len(loaded) == 2

    def test_gate_filter(self, tmp_path: Path) -> None:
        """Only CI_WRAP_GATE receipts are loaded."""
        f = tmp_path / "receipts.jsonl"
        b1 = self._make_bundle("lint", gate=CI_WRAP_GATE)
        b2 = self._make_bundle("build", gate=CI_VERIFY_GATE)
        f.write_text(b1.to_json() + "\n" + b2.to_json() + "\n")
        loaded = load_ci_receipts(f)
        assert len(loaded) == 1
        assert loaded[0].evidence["ci_kind"] == "lint"

    def test_empty(self, tmp_path: Path) -> None:
        """Empty file returns empty list."""
        f = tmp_path / "receipts.jsonl"
        f.write_text("")
        loaded = load_ci_receipts(f)
        assert loaded == []


# =============================================================================
# CiPolicy
# =============================================================================

class TestCiPolicy:
    def test_roundtrip(self) -> None:
        """to_dict → from_dict roundtrip."""
        p = CiPolicy(required_kinds=frozenset({"lint", "unit_tests"}), require_clean=False)
        p2 = CiPolicy.from_dict(p.to_dict())
        assert p2.required_kinds == p.required_kinds
        assert p2.require_clean == p.require_clean
        assert p2.require_same_sha == p.require_same_sha

    def test_defaults(self) -> None:
        """Default policy: require_clean=True, require_same_sha=True."""
        p = CiPolicy(required_kinds=frozenset())
        assert p.require_clean is True
        assert p.require_same_sha is True

    def test_file_load(self, tmp_path: Path) -> None:
        """Load from JSON file."""
        f = tmp_path / "policy.json"
        f.write_text(json.dumps({"required_kinds": ["lint"], "require_clean": False}))
        p = CiPolicy.from_dict(json.loads(f.read_text()))
        assert p.required_kinds == frozenset({"lint"})
        assert p.require_clean is False


# =============================================================================
# ci_verify
# =============================================================================

class TestCiVerify:
    def _make_bundle(self, ci_kind: str = "lint", verdict: str = "pass",
                     git_sha: str = "abc123def456", dirty: bool = False,
                     timestamp: str = "2026-01-01T00:00:00Z") -> CiReceiptBundle:
        from governor.gate_receipt import create_receipt
        evidence = {
            "exit_code": 0 if verdict == "pass" else 1,
            "stdout_hash": "aaa", "stderr_hash": "bbb",
            "stdout_truncated": False, "stderr_truncated": False,
            "git_sha": git_sha, "dirty": dirty,
            "ci_kind": ci_kind, "command": ["echo"],
            "command_display": "echo", "python_version": "3.11.0",
        }
        receipt = create_receipt(
            gate=CI_WRAP_GATE, verdict=verdict, subject_kind="ci_wrap",
            subject_bytes=b"test", evidence_bundle=evidence,
            gate_config={"ci_kind": ci_kind}, timestamp=timestamp,
        )
        return CiReceiptBundle(receipt=receipt, evidence=evidence)

    def _write_bundles(self, tmp_path: Path, bundles: list[CiReceiptBundle]) -> Path:
        f = tmp_path / "receipts.jsonl"
        f.write_text("\n".join(b.to_json() for b in bundles) + "\n")
        return f

    def test_all_pass(self, tmp_path: Path) -> None:
        """All receipts pass → PASS."""
        bundles = [
            self._make_bundle("lint"),
            self._make_bundle("unit_tests"),
        ]
        f = self._write_bundles(tmp_path, bundles)
        policy = CiPolicy(required_kinds=frozenset({"lint", "unit_tests"}))
        result = ci_verify(f, policy)
        assert result.ok
        assert result.verdict == "pass"
        assert result.receipts_loaded == 2

    def test_missing_kind(self, tmp_path: Path) -> None:
        """Missing required kind → BLOCK."""
        f = self._write_bundles(tmp_path, [self._make_bundle("lint")])
        policy = CiPolicy(required_kinds=frozenset({"lint", "typecheck"}))
        result = ci_verify(f, policy)
        assert not result.ok
        assert result.verdict == "block"
        assert any("typecheck" in e for e in result.errors)

    def test_failed_verdict(self, tmp_path: Path) -> None:
        """Receipt with verdict=block → BLOCK."""
        bundles = [
            self._make_bundle("lint", verdict="pass"),
            self._make_bundle("unit_tests", verdict="block"),
        ]
        f = self._write_bundles(tmp_path, bundles)
        result = ci_verify(f, CiPolicy(required_kinds=frozenset()))
        assert not result.ok
        assert not result.checks["all_pass"]

    def test_mixed_sha(self, tmp_path: Path) -> None:
        """Different git_sha values → BLOCK when require_same_sha."""
        bundles = [
            self._make_bundle("lint", git_sha="aaa111"),
            self._make_bundle("build", git_sha="bbb222"),
        ]
        f = self._write_bundles(tmp_path, bundles)
        policy = CiPolicy(required_kinds=frozenset(), require_same_sha=True)
        result = ci_verify(f, policy)
        assert not result.ok
        assert not result.checks["same_sha"]

    def test_missing_sha_fail_closed(self, tmp_path: Path) -> None:
        """Empty git_sha with require_same_sha → BLOCK (fail closed)."""
        bundles = [self._make_bundle("lint", git_sha="")]
        f = self._write_bundles(tmp_path, bundles)
        policy = CiPolicy(required_kinds=frozenset(), require_same_sha=True)
        result = ci_verify(f, policy)
        assert not result.ok
        assert not result.checks["sha_known"]

    def test_dirty_flag(self, tmp_path: Path) -> None:
        """dirty=True with require_clean → BLOCK."""
        bundles = [self._make_bundle("lint", dirty=True)]
        f = self._write_bundles(tmp_path, bundles)
        policy = CiPolicy(required_kinds=frozenset(), require_clean=True)
        result = ci_verify(f, policy)
        assert not result.ok
        assert not result.checks["clean"]

    def test_identical_bundle_dedupe_ok(self, tmp_path: Path) -> None:
        """Duplicate receipt IDs with identical payload → OK."""
        b = self._make_bundle("lint")
        f = self._write_bundles(tmp_path, [b, b])  # Exact duplicate
        result = ci_verify(f, CiPolicy(required_kinds=frozenset()))
        assert result.checks["no_conflicting_ids"]

    def test_conflicting_id_block(self, tmp_path: Path) -> None:
        """Same receipt ID with different payload → BLOCK."""
        b1 = self._make_bundle("lint", git_sha="aaa")
        # Create b2 with same receipt_id but different evidence
        evidence2 = dict(b1.evidence)
        evidence2["exit_code"] = 99  # Different payload
        b2 = CiReceiptBundle(receipt=b1.receipt, evidence=evidence2)
        f = self._write_bundles(tmp_path, [b1, b2])
        result = ci_verify(f, CiPolicy(required_kinds=frozenset(), require_same_sha=False))
        assert not result.checks["no_conflicting_ids"]

    def test_meta_receipt_structure(self, tmp_path: Path) -> None:
        """Meta-receipt has correct gate."""
        bundles = [self._make_bundle("lint")]
        f = self._write_bundles(tmp_path, bundles)
        result = ci_verify(f, CiPolicy(required_kinds=frozenset()))
        assert result.receipt is not None
        assert result.receipt.gate == CI_VERIFY_GATE

    def test_no_receipts(self, tmp_path: Path) -> None:
        """No receipts found → BLOCK."""
        f = tmp_path / "empty.jsonl"
        f.write_text("")
        result = ci_verify(f, CiPolicy(required_kinds=frozenset()))
        assert not result.ok
        assert not result.checks["receipts_loaded"]

    def test_custom_policy(self, tmp_path: Path) -> None:
        """Custom policy with require_clean=False allows dirty."""
        bundles = [self._make_bundle("lint", dirty=True)]
        f = self._write_bundles(tmp_path, bundles)
        policy = CiPolicy(required_kinds=frozenset(), require_clean=False, require_same_sha=False)
        result = ci_verify(f, policy)
        assert result.ok

    def test_receipt_out_writes_meta_receipt(self, tmp_path: Path) -> None:
        """Meta-receipt written when receipt_out is specified."""
        bundles = [self._make_bundle("lint")]
        f = self._write_bundles(tmp_path, bundles)
        meta_out = tmp_path / "meta.json"
        ci_verify(f, CiPolicy(required_kinds=frozenset()), receipt_out=meta_out)
        assert meta_out.exists()
        data = json.loads(meta_out.read_text())
        assert data["receipt"]["gate"] == CI_VERIFY_GATE

    def test_sha_known_in_checks(self, tmp_path: Path) -> None:
        """sha_known appears as separate boolean in checks dict."""
        bundles = [self._make_bundle("lint", git_sha="abc123")]
        f = self._write_bundles(tmp_path, bundles)
        result = ci_verify(f, CiPolicy(required_kinds=frozenset()))
        assert "sha_known" in result.checks
        assert result.checks["sha_known"] is True


# =============================================================================
# CLI integration
# =============================================================================

class TestCli:
    def test_wrap_pass(self, tmp_path: Path) -> None:
        """governor wrap --receipt-out --ci-kind with passing command."""
        from click.testing import CliRunner
        from governor.cli import cli

        out = tmp_path / "receipts.jsonl"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "wrap", "--receipt-out", str(out), "--ci-kind", "lint",
            "--", sys.executable, "-c", "print('ok')",
        ])
        assert result.exit_code == 0
        assert out.exists()

    def test_wrap_fail(self, tmp_path: Path) -> None:
        """governor wrap --receipt-out --ci-kind with failing command."""
        from click.testing import CliRunner
        from governor.cli import cli

        out = tmp_path / "receipts.jsonl"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "wrap", "--receipt-out", str(out), "--ci-kind", "unit_tests",
            "--", sys.executable, "-c", "import sys; sys.exit(1)",
        ])
        assert result.exit_code == 1

    def test_wrap_missing_ci_kind(self) -> None:
        """--receipt-out without --ci-kind gives error."""
        from click.testing import CliRunner
        from governor.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, [
            "wrap", "--receipt-out", "/tmp/test", "--",
            sys.executable, "-c", "print('ok')",
        ])
        assert result.exit_code == 1
        assert "ci-kind is required" in result.output or "ci-kind is required" in (result.output + (result.stderr if hasattr(result, 'stderr') else ''))

    def test_ci_verify_pass(self, tmp_path: Path) -> None:
        """governor ci verify with passing receipts."""
        from click.testing import CliRunner
        from governor.cli import cli

        # Create receipts via ci_wrap with relaxed policy (may be dirty repo)
        out = tmp_path / "receipts"
        ci_wrap([sys.executable, "-c", "print('ok')"], "lint", out)
        ci_wrap([sys.executable, "-c", "print('ok')"], "unit_tests", out)

        # Use relaxed policy file (no clean/sha requirements)
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps({
            "required_kinds": ["lint", "unit_tests"],
            "require_clean": False,
            "require_same_sha": False,
        }))

        runner = CliRunner()
        result = runner.invoke(cli, ["ci", "verify", "--policy", str(policy_file), str(out)])
        assert result.exit_code == 0
        assert "PASS" in result.output


# =============================================================================
# _utc_now
# =============================================================================

class TestUtcNow:
    def test_z_suffix(self) -> None:
        ts = _utc_now()
        assert ts.endswith("Z")
        assert "T" in ts
