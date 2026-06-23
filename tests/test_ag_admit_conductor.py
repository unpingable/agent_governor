# SPDX-License-Identifier: Apache-2.0
"""Slice 1 + Slice 2: the disposable conductor and the toy refuse→repair→admit trace.

Slice 1: bad input refuses, good input admits, each with a receipt; non-ADMIT verdicts
never mutate.
Slice 2: full toy trace on a real throwaway git repo, reproducible from receipts alone,
with the final commit causally linked to the admission receipt.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

# The conductor is a disposable script under working/ — import it by path.
_WORKING = pathlib.Path(__file__).resolve().parents[1] / "working"
sys.path.insert(0, str(_WORKING))

import ag_admit_conductor  # noqa: E402
from governor.ag_admit import CandidateStep, DiffPathScopeGate, StepVerdict  # noqa: E402
from governor.gate_receipt import GateReceiptSystem  # noqa: E402

GRANT = ("toy_repo/allowed/**",)


def _diff_new_file(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{path}\n"
        "@@ -0,0 +1 @@\n+hello\n"
    )


def _diff_modify(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"
    )


def _step(step_id: str, diff: str, *, declared=()) -> CandidateStep:
    return CandidateStep(
        step_id=step_id,
        repo="toy_repo",
        base_commit="0" * 40,
        diff=diff,
        declared_intent="touch a file",
        scope="toy_repo/allowed/**",
        touched_paths=tuple(declared),
        tests_to_run=("true",),
    )


# ---------------------------------------------------------------------------
# Slice 1 — conductor behavior
# ---------------------------------------------------------------------------


def test_slice1_bad_refuses_good_admits(tmp_path):
    system = GateReceiptSystem(tmp_path)
    gate = DiffPathScopeGate(GRANT)

    bad = ag_admit_conductor.conduct(
        _step("bad", _diff_new_file("toy_repo/forbidden/secret.txt")), gate, system
    )
    good = ag_admit_conductor.conduct(
        _step("good", _diff_modify("toy_repo/allowed/example.txt")), gate, system
    )

    assert bad.verdict is StepVerdict.REJECT
    assert bad.action == "refuse"
    assert good.verdict is StepVerdict.ADMIT
    assert good.action == "execute"

    receipts = system.receipt_store.all()
    assert [r.verdict for r in receipts] == ["block", "proceed"]
    for r in receipts:
        ev = system.evidence_for(r)
        assert ev["conductor_decided"] is False


def test_slice1_cannot_testify_does_not_mutate_or_escalate(tmp_path):
    system = GateReceiptSystem(tmp_path)
    gate = DiffPathScopeGate(GRANT)
    out = ag_admit_conductor.conduct(_step("x", "not a diff\n"), gate, system)
    assert out.verdict is StepVerdict.CANNOT_TESTIFY
    assert out.action == "request_evidence"  # NOT execute, NOT halt_for_human
    # Only the single admission receipt exists; no execution/commit (no mutation).
    receipts = system.receipt_store.all()
    assert len(receipts) == 1
    assert receipts[0].gate == "step_admission"
    assert receipts[0].verdict == "warn"


def test_slice1_conductor_has_no_diff_parsing():
    """The conductor stays stupid: it must not parse diffs or branch on raw strings."""
    src = (_WORKING / "ag_admit_conductor.py").read_text()
    assert "splitlines" not in src
    assert "+++" not in src
    assert "_observe_paths" not in src
    # It branches on the StepVerdict enum via a static table, not on substrings.
    assert "_VERDICT_TABLE" in src


# ---------------------------------------------------------------------------
# Slice 2 — full toy trace on real git, reconstructed from receipts
# ---------------------------------------------------------------------------


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init_toy_repo(root: pathlib.Path) -> pathlib.Path:
    repo = root / "work"
    (repo / "toy_repo" / "allowed").mkdir(parents=True)
    (repo / "toy_repo" / "forbidden").mkdir(parents=True)
    (repo / "toy_repo" / "allowed" / "example.txt").write_text("seed\n")
    (repo / "toy_repo" / "forbidden" / "secret.txt").write_text("seed\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "toy@example.com")
    _git(repo, "config", "user.name", "toy")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


def test_slice2_toy_trace_refuse_repair_admit_commit(tmp_path):
    repo = _init_toy_repo(tmp_path)
    gov = tmp_path / "gov"
    system = GateReceiptSystem(gov)
    gate = DiffPathScopeGate(GRANT)
    base = _git(repo, "rev-parse", "HEAD")
    trace_id = "trace-1"

    # 1. Bad step → REFUSE (authority refusal on an observed forbidden path).
    bad = _step(trace_id, _diff_new_file("toy_repo/forbidden/secret.txt"))
    bad_out = ag_admit_conductor.conduct(bad, gate, system)
    assert bad_out.verdict is StepVerdict.REJECT
    assert bad_out.action == "refuse"  # no mutation

    # 2. Repair event (the generator/operator narrows the diff — NOT the conductor).
    system.emit(
        gate="step_repair",
        verdict="observe",
        subject_kind="repair",
        subject_bytes=b"narrow diff to allowed path",
        evidence_bundle={
            "step_id": trace_id,
            "prior_refusal_reason": "path_out_of_scope",
            "next_constraint": "touch only toy_repo/allowed/**",
        },
        gate_config={"actor": "generator"},
    )

    # 3. Repaired step → ADMIT.
    repaired = _step(trace_id, _diff_modify("toy_repo/allowed/example.txt"))
    admit_out = ag_admit_conductor.conduct(repaired, gate, system)
    assert admit_out.verdict is StepVerdict.ADMIT
    assert admit_out.action == "execute"

    # 4. Executor applies the admitted change + runs tests with OBSERVED exit code.
    (repo / "toy_repo" / "allowed" / "example.txt").write_text("new\n")
    proc = subprocess.run(["true"], cwd=repo)  # tests_to_run; real exit code observed
    exec_verdict = "pass" if proc.returncode == 0 else "block"
    system.emit(
        gate="step_execution",
        verdict=exec_verdict,
        subject_kind="command",
        subject_bytes=b"true",
        evidence_bundle={
            "step_id": trace_id,
            "command": ["true"],
            "exit_code": proc.returncode,
            "exit_observed": True,
            "admission_receipt_id": admit_out.receipt_id,
        },
        gate_config={"observation": "subprocess_returncode"},
    )

    # 5. Commit, causally linked to the admission receipt.
    _git(repo, "add", "-A")
    _git(
        repo,
        "commit",
        "-q",
        "-m",
        f"toy: admitted change\n\nAdmitted-By-Receipt: {admit_out.receipt_id}",
    )
    commit_sha = _git(repo, "rev-parse", "HEAD")
    system.emit(
        gate="step_commit",
        verdict="pass",
        subject_kind="commit",
        subject_bytes=commit_sha.encode(),
        evidence_bundle={
            "step_id": trace_id,
            "base_commit": base,
            "commit_sha": commit_sha,
            "admission_receipt_id": admit_out.receipt_id,  # causal link
        },
        gate_config={},
    )

    # --- Reconstruct the trace from receipts ALONE ---
    all_receipts = system.receipt_store.all()
    trace = [
        r
        for r in all_receipts
        if (system.evidence_for(r) or {}).get("step_id") == trace_id
    ]
    sequence = [(r.gate, r.verdict) for r in trace]
    assert sequence == [
        ("step_admission", "block"),
        ("step_repair", "observe"),
        ("step_admission", "proceed"),
        ("step_execution", "pass"),
        ("step_commit", "pass"),
    ]

    # Causal link: commit receipt references the admission receipt that authorized it.
    commit_ev = system.evidence_for(trace[-1])
    assert commit_ev["admission_receipt_id"] == admit_out.receipt_id
    assert admit_out.receipt_id != bad_out.receipt_id  # NOT the refusal

    # The commit message itself carries the causal trailer.
    msg = _git(repo, "log", "-1", "--format=%B")
    assert admit_out.receipt_id in msg

    # Negative pin: exactly one execution and one commit; none tied to the refusal.
    execs = [r for r in trace if r.gate == "step_execution"]
    commits = [r for r in trace if r.gate == "step_commit"]
    assert len(execs) == 1 and len(commits) == 1
    for r in execs + commits:
        assert system.evidence_for(r)["admission_receipt_id"] == admit_out.receipt_id


def test_slice2_no_mutation_receipts_when_refused(tmp_path):
    """A refused-only run (no repair) produces zero execution/commit receipts."""
    gov = tmp_path / "gov"
    system = GateReceiptSystem(gov)
    gate = DiffPathScopeGate(GRANT)
    out = ag_admit_conductor.conduct(
        _step("r", _diff_new_file("toy_repo/forbidden/secret.txt")), gate, system
    )
    assert out.verdict is StepVerdict.REJECT
    gates = [r.gate for r in system.receipt_store.all()]
    assert gates == ["step_admission"]
    assert "step_execution" not in gates
    assert "step_commit" not in gates
