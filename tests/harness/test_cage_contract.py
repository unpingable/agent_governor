# SPDX-License-Identifier: Apache-2.0
"""Tests for the H-series cage-design slice (`harness/cage.py`).

Cover the three ratified terms (harness-cage review, operator pass 2026-06-30):
refuse-live admission (typed), the XDG audit-store layout outside AG, and the
one-artifact AG-ingest boundary. Plus: AG does not crawl/import the audit store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.cage import (
    AG_INGESTIBLE_ARTIFACT_TYPE,
    LIVE_ADMISSION_REFUSAL_CODES,
    REFUSED_NO_ISOLATION_ATTESTED,
    REFUSED_UNKNOWN_ACTOR_KIND,
    SCOPE_LIVE,
    SCOPE_NONE,
    AuditPathError,
    CageAttestation,
    CageError,
    LiveAdmission,
    LiveAdmissionRefused,
    LiveAdmissionRequest,
    NonIngestibleArtifact,
    NoLiveCage,
    RefusingCage,
    assert_ag_ingestible,
    audit_store_root,
    evaluate_live_admission,
    require_live_admission,
    run_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _req(actor_kind: str = "claude") -> LiveAdmissionRequest:
    return LiveAdmissionRequest(actor_kind=actor_kind, handoff_id="handoff-1")


# --------------------------------------------------------------------------- #
# Refuse-live admission (typed).
# --------------------------------------------------------------------------- #


def test_refusing_cage_refuses_live_admission_typed():
    decision = RefusingCage().admit_live(_req())
    assert decision.admitted is False
    assert decision.refusal_code == REFUSED_NO_ISOLATION_ATTESTED
    assert decision.refusal_code in LIVE_ADMISSION_REFUSAL_CODES


def test_no_live_cage_is_the_same_refusing_backend():
    assert NoLiveCage is RefusingCage
    assert NoLiveCage().admit_live(_req()).admitted is False


def test_require_live_admission_raises_typed_refusal():
    with pytest.raises(LiveAdmissionRefused) as exc:
        require_live_admission(RefusingCage(), _req())
    assert exc.value.code == REFUSED_NO_ISOLATION_ATTESTED


def test_refusing_cage_attests_no_isolation():
    att = RefusingCage().attest()
    assert att.confirms_isolation is False
    assert att.scope == SCOPE_NONE


def test_unknown_actor_kind_is_refused_typed():
    decision = RefusingCage().admit_live(_req(actor_kind="rogue"))
    assert decision.admitted is False
    assert decision.refusal_code == REFUSED_UNKNOWN_ACTOR_KIND


def test_live_admission_is_structurally_unreachable():
    """No half-confirmed cage can exist (the attestation invariant), and the only
    shipped backend attests nothing — so nothing in this slice yields admitted=True."""
    # A backend cannot confirm isolation outside live scope.
    with pytest.raises(CageError):
        CageAttestation(backend_id="liar", confirms_isolation=True, scope=SCOPE_NONE)
    # The only shipped cage refuses.
    assert RefusingCage().admit_live(_req()).admitted is False


def test_admitted_decision_cannot_carry_refusal_code():
    with pytest.raises(CageError):
        LiveAdmission(
            admitted=True,
            backend_id="x",
            actor_kind="claude",
            refusal_code=REFUSED_NO_ISOLATION_ATTESTED,
        )


def test_refusal_must_carry_a_closed_code():
    with pytest.raises(CageError):
        LiveAdmission(admitted=False, backend_id="x", actor_kind="claude")


def test_evaluate_live_admission_pure_guard_matches_backend():
    att = RefusingCage().attest()
    assert evaluate_live_admission(att, _req()).refusal_code == (
        REFUSED_NO_ISOLATION_ATTESTED
    )


# --------------------------------------------------------------------------- #
# Audit-store layout (XDG), outside AG.
# --------------------------------------------------------------------------- #


def test_audit_store_root_uses_xdg_state_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert audit_store_root() == tmp_path / "agent-gov" / "harness-runs"


def test_audit_store_root_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/tester")))
    assert audit_store_root() == Path(
        "/home/tester/.local/state/agent-gov/harness-runs"
    )


def test_audit_store_is_outside_the_ag_repo(monkeypatch):
    """The audit store must never resolve inside the agent_gov repo (no AG ingest path,
    no chance AG crawls it as part of its own tree)."""
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    root = audit_store_root().resolve()
    assert REPO_ROOT not in root.parents and root != REPO_ROOT


def test_run_dir_is_under_the_store_and_pure(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    d = run_dir("run-abc123")
    assert d == tmp_path / "agent-gov" / "harness-runs" / "run-abc123"
    # Pure: computing the path created nothing.
    assert not d.exists()


@pytest.mark.parametrize("bad", ["../escape", "a/b", "..", ".", "", ".hidden"])
def test_run_dir_rejects_traversal_and_separators(bad):
    with pytest.raises(AuditPathError):
        run_dir(bad)


# --------------------------------------------------------------------------- #
# One-artifact AG-ingest boundary.
# --------------------------------------------------------------------------- #


def test_only_actor_output_v0_is_ag_ingestible():
    assert_ag_ingestible(AG_INGESTIBLE_ARTIFACT_TYPE)  # does not raise


@pytest.mark.parametrize(
    "bad",
    [
        "diff",
        "diff_reference",
        "review_test_result",
        "verifier_result",
        "bundle",
        "actor_output.v1",
        "handoff.v0",
    ],
)
def test_non_envelope_artifacts_are_refused(bad):
    with pytest.raises(NonIngestibleArtifact):
        assert_ag_ingestible(bad)


# --------------------------------------------------------------------------- #
# AG does not crawl or import the audit store (the wall, from AG's side).
# --------------------------------------------------------------------------- #


def test_ag_governor_does_not_reference_the_audit_store_or_harness():
    """Static proof AG never crawls/imports the harness audit store: no module under
    src/governor mentions the harness, the audit-store path, or its XDG marker."""
    gov_root = REPO_ROOT / "src" / "governor"
    markers = ("harness-runs", "import harness", "from harness", "harness.cage")
    offenders: list[str] = []
    for py in gov_root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for marker in markers:
            if marker in text:
                offenders.append(f"{py.relative_to(REPO_ROOT)}: {marker!r}")
    assert not offenders, "AG must not know about the harness/audit store: " + "; ".join(
        offenders
    )


def test_cage_module_does_not_import_governor():
    """The cage stays in the harness lane — no dependency arrow into AG."""
    import ast

    src = (REPO_ROOT / "harness" / "cage.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("governor")
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("governor")
