# SPDX-License-Identifier: Apache-2.0
"""OPA contrast shim (W1 item 5) — Act 2.5, the objection pre-answered.

Pure parts always tested (receipt content-addressing, render beats, custody
refusal, honest no-binary degradation); live `opa eval` tested only when the
binary is installed (smoke-stub pattern).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from governor.demo_opa_contrast import (
    LAYERING_SENTENCE,
    OPA_INPUT,
    REGO_POLICY,
    build_opa_verdict_receipt,
    evaluate_with_opa,
    render_surface,
    run_contrast,
)

HAS_OPA = shutil.which("opa") is not None


def test_custody_refuses_the_same_incident_upstream(tmp_path: Path):
    c = run_contrast(root=tmp_path, now=0)
    ag = c["ag"]
    assert ag.outcome == "refused"
    assert ag.refusal_kind == "standing_before_spendability_not_bounded"
    assert ag.refusing_seam == "standing_spendability_seam"
    assert ag.effect_count == 0  # premises failed preflight; nothing spent


def test_integrity_assertions_hold(tmp_path: Path):
    c = run_contrast(root=tmp_path, now=0)
    assert c["assertions"]
    for label, ok, detail in c["assertions"]:
        assert ok, f"integrity assertion failed: {label} ({detail})"
    assert c["aggregate_ok"] is True


def test_opa_verdict_receipt_is_content_addressed_and_provenance_labeled():
    r1 = build_opa_verdict_receipt(None)
    r2 = build_opa_verdict_receipt(None)
    assert r1 == r2  # deterministic
    assert r1["receipt_id"].startswith("opa_rcpt_")
    assert r1["policy_hash"].startswith("sha256:")
    assert r1["input_hash"].startswith("sha256:")
    # The load-bearing field: the verdict's input is unwitnessed self-report.
    assert r1["input_provenance"] == "unwitnessed_self_report"
    # No fabricated verdict without an engine.
    assert r1["decision"] is None
    assert r1["engine"] == "opa_not_installed"


def test_receipt_hash_binds_policy_and_input_bytes():
    # Changing policy or input must change the receipt id — the receipt is
    # bound to WHAT was decided over, not just the decision.
    base = build_opa_verdict_receipt(None)
    fake_eval = {"allow": True, "engine": "test"}
    assert build_opa_verdict_receipt(fake_eval)["receipt_id"] != base["receipt_id"]


def test_surface_carries_the_beats(tmp_path: Path):
    c = run_contrast(root=tmp_path, now=0)
    surface = render_surface(c)
    # The layering sentence, verbatim (ratified copy).
    assert LAYERING_SENTENCE in surface
    # Both verdicts on one surface — the contrast.
    assert "OPA SAYS:" in surface
    assert "CUSTODY SAYS:  refused — standing_before_spendability_not_bounded" in surface
    # The policy and the input are shown (the audience can check OPA was fair).
    assert "package demo.authz" in surface
    assert '"status": "valid"' in surface
    # The verdict receipt enters the evidence plane.
    assert "opa_rcpt_" in surface
    assert "unwitnessed_self_report" in surface
    # The custody side shows the clocks (the premise OPA never saw).
    assert "named monotonic basis" in surface


def test_surface_is_deterministic_without_opa(tmp_path: Path):
    if HAS_OPA:
        pytest.skip("engine present; determinism-without-engine not exercised")
    a = render_surface(run_contrast(root=tmp_path / "a", now=0))
    b = render_surface(run_contrast(root=tmp_path / "b", now=0))
    assert a == b


def test_no_verdict_fabricated_without_binary(tmp_path: Path):
    if HAS_OPA:
        pytest.skip("opa installed; degradation path not reachable")
    c = run_contrast(root=tmp_path, now=0)
    assert c["evaluation"] is None
    surface = render_surface(c)
    assert "no verdict fabricated" in surface
    assert "allow = true" not in surface  # the honest line, not a fake verdict


@pytest.mark.skipif(not HAS_OPA, reason="opa binary not installed")
def test_live_opa_returns_allow_over_the_unwitnessed_input():
    evaluation = evaluate_with_opa()
    assert evaluation is not None
    assert evaluation.get("allow") is True  # correct, for the world it was handed


def test_policy_and_input_stay_demo_sized():
    # The ratified scope fence: ~100 lines demo-grade, no policy-adapter zoo.
    # The policy must stay readable-by-eye (the no-binary degradation depends
    # on it) and the input must stay the one frozen incident.
    assert len(REGO_POLICY.splitlines()) <= 12
    assert OPA_INPUT["incident"].startswith("temporal-lapse")
