# SPDX-License-Identifier: Apache-2.0
"""AG-side contract tests for H1 (the external actor harness in ``harness/``).

These are the drift-control + treaty tests the operator named: H1 is treated as a
black-box *foreign producer* (run as a subprocess; its source is scanned statically,
never imported here). AG ingests the JSON it emits with its OWN parser
(``ActorOutput.from_dict``), normalizes S7→S5, and confirms an actor's *claimed*
passing test still fails ``required_test_not_passing``.

The wall under test:

    actor execution ≠ AG execution
    captured output ≠ verifier receipt
    claimed pass    ≠ passed test
    offline harness ≠ live adapter
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from governor.playbooks.actor_output_normalizer import (
    ActorOutput,
    normalize_actor_output_to_review_packet,
)
from governor.playbooks.handoff_renderer import ACTOR_CLAUDE, render_handoff
from governor.playbooks.playbook_queue import (
    OUTPUT_REVIEW_PACKET,
    PlaybookQueue,
    QueuedPlaybook,
)
from governor.playbooks.review_packet_validator import (
    CODE_REQUIRED_TEST_NOT_PASSING,
    validate_review_packet_for_queue_item,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_DIR = REPO_ROOT / "harness"
SAMPLE_REQ_TEST = "pytest tests/widget -q"


def _run_harness(*args: str) -> str:
    """Run H1 as a foreign subprocess from the repo root and return its stdout.

    ``-m harness.actor_harness`` resolves because cwd (repo root) is on the child's
    path — H1 needs nothing from the installed ``governor`` package to run."""
    proc = subprocess.run(
        [sys.executable, "-m", "harness.actor_harness", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"harness failed: {proc.stderr}"
    return proc.stdout


# --------------------------------------------------------------------------- #
# 1. The treaty: a foreign harness claiming a pass cannot green S5.
# --------------------------------------------------------------------------- #


def _matching_handoff_for_sample():
    """Build the S6 handoff the canned ``--sample`` capture answers."""
    item = QueuedPlaybook(
        playbook_id="pb-sample",
        title="sample",
        objective="sample objective",
        output_kind=OUTPUT_REVIEW_PACKET,
        allowed_paths=("src/widget/*",),
        forbidden_paths=(),
        required_tests=(SAMPLE_REQ_TEST,),
        stop_conditions=("any test fails",),
        operator_approved=True,
        base_branch="main",
        base_sha="cafef00d",
    )
    handoff = render_handoff(
        item,
        handoff_id="handoff-sample-0001",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        actor_kind=ACTOR_CLAUDE,
    )
    queue = PlaybookQueue(
        queue_id="q-sample",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        mode="synthetic_conveyor",
        items=(item,),
    )
    return queue, item, handoff


def test_h1_sample_subprocess_is_refused_by_s5(tmp_path):
    out_path = tmp_path / "ao.json"
    _run_harness("--sample", "--out", str(out_path))

    # AG ingests the foreign JSON with ITS OWN parser (drift guard) — never trusts
    # H1's Python types.
    data = json.loads(out_path.read_text())
    assert data["schema_version"] == "actor_output.v0"
    actor_output = ActorOutput.from_dict(data)

    queue, item, handoff = _matching_handoff_for_sample()
    packet = normalize_actor_output_to_review_packet(actor_output, handoff)

    report = validate_review_packet_for_queue_item(queue, item, packet)
    # The actor CLAIMED its required test passed. S5 still refuses it.
    assert not report.valid
    assert CODE_REQUIRED_TEST_NOT_PASSING in report.codes()
    # The actor's authority claims were stripped, never admitted.
    assert packet.operator_review_required is True
    assert packet.authority.used.as_dict() == {
        k: False for k in packet.authority.used.as_dict()
    }
    assert any("tests_pass" in r and "REFUSED" in r for r in packet.risks)


# --------------------------------------------------------------------------- #
# 2. Binding: H1 captures against a real handoff; AG still refuses.
# --------------------------------------------------------------------------- #


def test_h1_binds_to_handoff_and_is_refused(tmp_path):
    """H1 reads a handoff manifest, binds its capture, and emits JSON. Even with NO
    actor claim, the required test is represented (not passed) → S5 refuses."""
    item = QueuedPlaybook(
        playbook_id="pb-bind",
        title="bind",
        objective="bind objective",
        output_kind=OUTPUT_REVIEW_PACKET,
        allowed_paths=("src/widget/*",),
        forbidden_paths=(),
        required_tests=(SAMPLE_REQ_TEST,),
        stop_conditions=("stop",),
        operator_approved=True,
        base_branch="main",
        base_sha="deadbeef",
    )
    handoff = render_handoff(
        item,
        handoff_id="handoff-bind-1",
        repo="agent_gov",
        base_branch="main",
        base_sha="deadbeef",
        actor_kind=ACTOR_CLAUDE,
    )
    queue = PlaybookQueue(
        queue_id="q-bind",
        repo="agent_gov",
        base_branch="main",
        base_sha="deadbeef",
        mode="synthetic_conveyor",
        items=(item,),
    )

    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(json.dumps(handoff.to_manifest_dict()))
    text_path = tmp_path / "reply.txt"
    text_path.write_text("I made the change and believe the tests pass.")
    out_path = tmp_path / "ao.json"

    _run_harness(
        "--handoff", str(handoff_path),
        "--captured-text-file", str(text_path),
        "--out", str(out_path),
    )

    data = json.loads(out_path.read_text())
    assert data["handoff_packet_id"] == "handoff-bind-1"
    assert data["actor_kind"] == ACTOR_CLAUDE
    assert isinstance(data["captured_at"], str) and data["captured_at"]

    actor_output = ActorOutput.from_dict(data)
    packet = normalize_actor_output_to_review_packet(actor_output, handoff)
    report = validate_review_packet_for_queue_item(queue, item, packet)
    assert not report.valid
    assert CODE_REQUIRED_TEST_NOT_PASSING in report.codes()


# --------------------------------------------------------------------------- #
# 3. The no-import / no-authority-surface boundary (static; H1 never imported).
# --------------------------------------------------------------------------- #


def _harness_sources() -> list[Path]:
    return sorted(HARNESS_DIR.glob("*.py"))


def test_harness_does_not_import_governor():
    """Static AST scan: no module under harness/ may import ``governor`` (or any of
    S5/S7/ration-card/admission/validator internals). The contract is the JSON
    envelope, not shared Python types — so the dependency arrow never points into AG."""
    sources = _harness_sources()
    assert sources, "expected harness/*.py to exist"
    for src in sources:
        tree = ast.parse(src.read_text(), filename=str(src))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("governor"), (
                        f"{src.name} imports {alias.name!r} — H1 must not import AG"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not mod.startswith("governor"), (
                    f"{src.name} imports from {mod!r} — H1 must not import AG"
                )


def test_harness_has_no_verifier_or_admission_surface():
    """H1 produces ONLY actor_output.v0 testimony. It must not name a verifier-result
    / admission / receipt-greening surface in CODE — there is no code path by which it
    could mint an object that satisfies S5. (AST identifier scan, so the boundary
    *prose* in the docstrings — which names these on purpose — does not trip it.)"""
    forbidden = frozenset(
        {
            "ReviewTestResult",
            "verifier_results",
            "verifier_receipt",
            "VerifierReceipt",
            "admission_receipt",
            "AdmissionReceipt",
            "ReviewPacket",
        }
    )
    for src in _harness_sources():
        tree = ast.parse(src.read_text(), filename=str(src))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.arg)):
                name = node.arg if isinstance(node, ast.arg) else node.name
            if name in forbidden:
                raise AssertionError(
                    f"{src.name} uses identifier {name!r} in code — H1 may emit "
                    "only actor_output.v0 testimony"
                )


def test_harness_sample_is_well_formed_wire_json():
    """The standalone sample emission (acceptance criterion) is parseable as the
    documented wire shape, with the actor's claim present as a CLAIM."""
    text = _run_harness("--sample")
    data = json.loads(text)
    assert data["schema_version"] == "actor_output.v0"
    assert data["actor_kind"] in {"claude", "codex"}
    claims = data["claimed_test_results"]
    assert claims and claims[0]["claimed_status"] == "passed"
    # The claim is carried as testimony only; nothing here is a verified status.
    assert "status" not in claims[0]  # no "passed/failed" VERIFIED status field
