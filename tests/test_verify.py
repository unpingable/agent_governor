"""Specimens for the governor verifier wrapper (src/governor/verify.py).

The discipline under test: a verifier result is admissible only when the
verifier's own exit status is observed. A pipeline that masks the exit
(`cargo test | tail`) must never be accepted as green.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from governor.verify import (
    EXIT_CHILD,
    EXIT_PIPEFAIL,
    EXIT_UNKNOWN,
    REFUSAL_EXIT,
    analyze_command,
    verify_run,
)

PY = sys.executable
_PASS = [PY, "-c", "import sys; sys.exit(0)"]
_FAIL = [PY, "-c", "import sys; sys.exit(1)"]


# --------------------------------------------------------------------------- #
# analyze_command — the masking classifier
# --------------------------------------------------------------------------- #


class TestAnalyzeCommand:
    def test_direct_exec_is_child_exit(self) -> None:
        s = analyze_command(["cargo", "test", "-p", "nq-db"])
        assert s.shell_used is False
        assert s.masked_exit_risk is False
        assert s.exit_source == EXIT_CHILD

    def test_shell_pipe_without_pipefail_is_masked(self) -> None:
        s = analyze_command(["bash", "-c", "cargo test | tail"])
        assert s.shell_used is True
        assert s.has_pipe is True
        assert s.masked_exit_risk is True
        assert s.exit_source == EXIT_UNKNOWN

    def test_shell_pipe_with_pipefail_preserves_source(self) -> None:
        s = analyze_command(["bash", "-c", "set -o pipefail; cargo test | tail"])
        assert s.has_pipe is True
        assert s.has_pipefail is True
        assert s.masked_exit_risk is False
        assert s.exit_source == EXIT_PIPEFAIL

    def test_shell_pipe_with_pipestatus_preserves_source(self) -> None:
        s = analyze_command(["bash", "-c", "cargo test | tee log; exit ${PIPESTATUS[0]}"])
        assert s.masked_exit_risk is False
        assert s.exit_source == EXIT_PIPEFAIL

    def test_shell_without_pipe_is_child_exit(self) -> None:
        s = analyze_command(["bash", "-c", "cargo test && echo done"])
        assert s.has_pipe is False
        assert s.masked_exit_risk is False
        assert s.exit_source == EXIT_CHILD

    def test_logical_or_is_not_a_pipe(self) -> None:
        s = analyze_command(["bash", "-c", "cargo test || echo failed"])
        assert s.has_pipe is False
        assert s.masked_exit_risk is False


# --------------------------------------------------------------------------- #
# verify_run — the four required specimens
# --------------------------------------------------------------------------- #


class TestVerifyRun:
    def test_passing_direct_is_pass(self, tmp_path) -> None:
        r = verify_run(_PASS, "unit_tests", tmp_path / "r.json")
        assert r.refused is False
        assert r.exit_code == 0
        assert r.receipt is not None
        assert r.receipt.verdict == "pass"
        assert r.safety.exit_source == EXIT_CHILD
        ev = _evidence(r)
        assert ev["verifier_exit_observed"] is True
        assert ev["masked_exit_risk"] is False
        assert ev["verifier_exit_source"] == EXIT_CHILD

    def test_failing_direct_is_fail(self, tmp_path) -> None:
        r = verify_run(_FAIL, "unit_tests", tmp_path / "r.json")
        assert r.refused is False
        assert r.exit_code == 1
        assert r.receipt is not None
        assert r.receipt.verdict == "block"
        ev = _evidence(r)
        assert ev["verifier_exit_observed"] is True
        assert ev["verifier_exit_source"] == EXIT_CHILD

    def test_failing_piped_to_tail_is_not_green(self, tmp_path) -> None:
        # The masking: `false | tail` exits 0 because tail succeeds. If we
        # trusted the shell's exit, this would read as green.
        masking = subprocess.run(["bash", "-c", "false | tail"]).returncode
        assert masking == 0, "precondition: the pipe really does mask the failure"

        # The wrapper refuses it before running — no green is possible.
        r = verify_run(["bash", "-c", "false | tail"], "unit_tests", tmp_path / "r.json")
        assert r.refused is True
        assert r.exit_code == REFUSAL_EXIT
        assert r.exit_code != 0
        assert r.receipt is not None
        assert r.receipt.verdict == "block"
        ev = _evidence(r)
        assert ev["verifier_exit_observed"] is False
        assert ev["masked_exit_risk"] is True
        assert ev["refused"] is True

    def test_pipefail_preserved_failing_is_recorded_as_fail(self, tmp_path) -> None:
        # Accepted (pipefail present) — but the FAILING upstream must propagate,
        # i.e. accepted only because the tested command's exit is the source.
        r = verify_run(
            ["bash", "-c", "set -o pipefail; false | cat"],
            "unit_tests",
            tmp_path / "r.json",
        )
        assert r.refused is False
        assert r.exit_code != 0, "pipefail must propagate the upstream failure"
        assert r.receipt.verdict == "block"
        ev = _evidence(r)
        assert ev["verifier_exit_observed"] is True
        assert ev["verifier_exit_source"] == EXIT_PIPEFAIL
        assert ev["masked_exit_risk"] is False

    def test_pipefail_preserved_passing_is_pass(self, tmp_path) -> None:
        r = verify_run(
            ["bash", "-c", "set -o pipefail; true | cat"],
            "unit_tests",
            tmp_path / "r.json",
        )
        assert r.refused is False
        assert r.exit_code == 0
        assert r.receipt.verdict == "pass"

    def test_allow_masked_runs_but_flags_risk(self, tmp_path) -> None:
        # Escape hatch: it runs, but the receipt still carries masked_exit_risk
        # so a downstream audit can refuse the evidence.
        r = verify_run(
            ["bash", "-c", "false | tail"],
            "unit_tests",
            tmp_path / "r.json",
            allow_masked=True,
        )
        assert r.refused is False
        ev = _evidence(r)
        assert ev["masked_exit_risk"] is True
        assert ev["verifier_exit_source"] == EXIT_UNKNOWN

    def test_receipt_carries_required_provenance_fields(self, tmp_path) -> None:
        r = verify_run(_PASS, "unit_tests", tmp_path / "r.json")
        ev = _evidence(r)
        for field in ("verifier_exit_observed", "verifier_exit_source", "masked_exit_risk"):
            assert field in ev, f"receipt evidence must carry {field}"
        # And the boring-but-required provenance the wrapper records.
        assert ev["command"] == _PASS
        assert "cwd" in ev
        assert "exit_code" in ev

    def test_invalid_ci_kind_rejected(self, tmp_path) -> None:
        with pytest.raises(ValueError):
            verify_run(_PASS, "not_a_real_kind", tmp_path / "r.json")


def _evidence(result) -> dict:
    """Read back the evidence bundle the receipt was written with."""
    import json

    with open(result.receipt_path) as f:
        text = f.read().strip()
    # .json single object; .jsonl one-per-line (take the last)
    obj = json.loads(text.splitlines()[-1])
    return obj["evidence"]
