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
    _command_label,
    _slugify,
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


# --------------------------------------------------------------------------- #
# Receipt filename label (#1) — operator-preferred / command-basename fallback,
# cosmetic-only: it must never change the receipt identity/hash.
# --------------------------------------------------------------------------- #


class TestReceiptLabel:
    def test_command_label_uses_argv0_basename_only(self) -> None:
        # NOT a shell parser — only basename(argv[0]).
        assert _command_label(["lake", "build"]) == "lake"
        assert _command_label(["cargo", "test", "-p", "x"]) == "cargo"
        assert _command_label(["/usr/bin/pytest", "-q"]) == "pytest"
        assert _command_label([]) == ""

    def test_slugify_is_filename_safe(self) -> None:
        assert _slugify("My Lean Build") == "my_lean_build"
        # no path traversal can survive the slug
        assert "/" not in _slugify("../../etc/passwd")
        assert ".." not in _slugify("../../etc/passwd")
        # bounded length
        assert len(_slugify("x" * 200)) <= 40

    def test_operator_label_preferred_in_filename(self, tmp_path) -> None:
        d = tmp_path / "receipts"  # directory mode → filename is generated
        r = verify_run(_PASS, "unit_tests", d, label="My Lean Build")
        assert r.refused is False
        assert r.receipt_path.parent == d
        assert r.receipt_path.name.startswith("my_lean_build_")
        assert r.receipt_path.name.endswith(".json")
        # the misleading ci_kind no longer drives the name when a label is given
        assert "unit_tests" not in r.receipt_path.name

    def test_command_basename_fallback_when_no_label(self, tmp_path) -> None:
        d = tmp_path / "receipts"
        r = verify_run(_PASS, "unit_tests", d)  # no label
        expected = _command_label(_PASS)  # slug of basename(sys.executable)
        assert expected
        assert r.receipt_path.name.startswith(expected + "_")
        # the headline defect — `ci_wrap_unit_tests_*` for a non-unit-test cmd —
        # is gone: the default ci_kind no longer mislabels the file.
        assert not r.receipt_path.name.startswith("ci_wrap_unit_tests_")

    def test_label_does_not_change_receipt_identity(self, tmp_path) -> None:
        # The load-bearing invariant: the label is cosmetic (filename only). With
        # the same command + timestamp, a labeled and an unlabeled run produce
        # DIFFERENT filenames but the SAME receipt identity/hash — the label
        # enters neither the subject bytes nor the hashed evidence.
        ts = "2026-06-17T00:00:00Z"
        r_lab = verify_run(_PASS, "unit_tests", tmp_path / "a", label="custom", timestamp=ts)
        r_plain = verify_run(_PASS, "unit_tests", tmp_path / "b", label=None, timestamp=ts)
        assert r_lab.receipt_path.name.startswith("custom_")
        assert not r_plain.receipt_path.name.startswith("custom_")
        assert r_lab.receipt.receipt_id == r_plain.receipt.receipt_id

    def test_masked_refusal_receipt_also_uses_label(self, tmp_path) -> None:
        # Both paths use the label — the refusal (block) receipt is named too.
        d = tmp_path / "receipts"
        r = verify_run(["bash", "-c", "false | tail"], "unit_tests", d, label="refused-probe")
        assert r.refused is True
        assert r.receipt_path.name.startswith("refused_probe_")


def _evidence(result) -> dict:
    """Read back the evidence bundle the receipt was written with."""
    import json

    with open(result.receipt_path) as f:
        text = f.read().strip()
    # .json single object; .jsonl one-per-line (take the last)
    obj = json.loads(text.splitlines()[-1])
    return obj["evidence"]
