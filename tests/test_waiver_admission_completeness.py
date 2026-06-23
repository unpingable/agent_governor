# SPDX-License-Identifier: Apache-2.0
"""Waiver-admission completeness pins (packet: working/packet-waiver-completeness.md).

Model A (operator-ratified 2026-06-23): "clean antecedents not certified" is a
NonDischargeClaim of the SPECIFIC existing non-discharge kind the waiver bypasses — no
new `clean_antecedents` kind, no change to VALID_NON_DISCHARGE_KINDS.

Criteria 1, 2, 4 are pinned here (in-grant). Criterion 3 (consumer refusal) is the
Slice-3b micro-grant: the real consumer edge is ci.py / ci_verify, made refuse-by-default
for waiver-admission receipts with an explicit accepts_waiver_admitted opt-in.
"""

from __future__ import annotations

import inspect

import pytest

from governor.admissibility import (
    WAIVER_ADMISSION_GATE,
    build_clean_antecedents_unsettled,
    emit_waiver_admission,
)
from governor.ci import CI_WRAP_GATE, CiPolicy, CiReceiptBundle, ci_verify
from governor.gate_receipt import (
    VALID_NON_DISCHARGE_KINDS,
    VERDICT_PASS,
    VERDICT_PROCEED,
    GateReceiptSystem,
    NonDischargeClaim,
    create_receipt,
)
from governor.overrides import (
    OVERRIDE_ADMISSION_GATE,
    OverrideReceipt,
    emit_override_admission,
)


def _system(tmp_path) -> GateReceiptSystem:
    return GateReceiptSystem(tmp_path)


def _override() -> OverrideReceipt:
    return OverrideReceipt(
        id="ovr1",
        anchor_id="anchor-x",
        reason="operator accepted risk",
        operator="alice",
        scope=["src/**"],
        created_at="",
        expires_at="2099-01-01T00:00:00+00:00",
        violation_snapshot={"kind": "anchor_violation"},
    )


# ---------------------------------------------------------------------------
# Criterion 1 — verdict-distinct from a clean pass
# ---------------------------------------------------------------------------


def test_criterion1_waiver_admission_is_proceed_never_pass(tmp_path):
    r = emit_waiver_admission(
        _system(tmp_path),
        bypassed_kind="evidence_sufficiency",
        detail="waiver of unknown U1",
        subject_bytes=b"subject",
        granted_by="alice",
    )
    assert r.verdict == VERDICT_PROCEED
    assert r.verdict != VERDICT_PASS


def test_criterion1_override_admission_is_proceed_never_pass(tmp_path):
    r = emit_override_admission(
        _system(tmp_path),
        _override(),
        bypassed_kind="scope",
        path="src/foo.py",
    )
    assert r.verdict == VERDICT_PROCEED
    assert r.verdict != VERDICT_PASS
    assert r.gate == OVERRIDE_ADMISSION_GATE


# ---------------------------------------------------------------------------
# Criterion 2 — non-empty unsettled, Model A (existing kind, not a new one)
# ---------------------------------------------------------------------------


def test_criterion2_unsettled_present_and_nonempty(tmp_path):
    r = emit_waiver_admission(
        _system(tmp_path),
        bypassed_kind="authority",
        detail="waiver bypassed an authority check",
        subject_bytes=b"s",
        granted_by="bob",
    )
    assert len(r.unsettled) >= 1
    claim = r.unsettled[0]
    # Model A: the kind is the SPECIFIC existing kind bypassed, not a new one.
    assert claim.kind == "authority"
    assert claim.kind in VALID_NON_DISCHARGE_KINDS
    assert "clean antecedents not certified" in claim.reason


def test_criterion2_model_A_no_new_kind_invented():
    # The non-claim builder cannot mint a kind outside the closed vocabulary.
    with pytest.raises(ValueError):
        build_clean_antecedents_unsettled("clean_antecedents", detail="nope")
    assert "clean_antecedents" not in VALID_NON_DISCHARGE_KINDS


# ---------------------------------------------------------------------------
# Criterion 4 — no silent path: never (verdict==pass AND unsettled empty)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(VALID_NON_DISCHARGE_KINDS))
def test_criterion4_every_kind_proceeds_with_nonempty_unsettled(tmp_path, kind):
    r = emit_waiver_admission(
        _system(tmp_path / kind),
        bypassed_kind=kind,
        detail=f"bypassed {kind}",
        subject_bytes=kind.encode(),
        granted_by="alice",
    )
    # The anti-laundering invariant, exhaustively over the closed kind set:
    assert not (r.verdict == VERDICT_PASS and not r.unsettled)
    assert r.verdict == VERDICT_PROCEED
    assert len(r.unsettled) >= 1


def test_criterion4_emission_helpers_cannot_express_pass_or_empty():
    """Structural no-silent-path: the emission path exposes neither `verdict` nor
    `unsettled` parameters, so a caller cannot turn a waiver admission into a clean pass.
    """
    for fn in (emit_waiver_admission, emit_override_admission):
        params = inspect.signature(fn).parameters
        assert "verdict" not in params, fn.__name__
        assert "unsettled" not in params, fn.__name__


def test_criterion4_gate_names_are_distinct_from_clean_gates():
    # Waiver/override admissions are emitted under their own gate names, queryable
    # so a consumer can find exactly the admissions that rode on a waiver.
    assert WAIVER_ADMISSION_GATE == "waiver_admission"
    assert OVERRIDE_ADMISSION_GATE == "override_admission"


# ---------------------------------------------------------------------------
# Criterion 3 — consumer refusal (Slice 3b: ci.py / ci_verify)
# ---------------------------------------------------------------------------
#
# A waiver-admitted CI step is a CI_WRAP_GATE receipt carrying verdict=proceed + the
# unsettled non-discharge block (not a clean pass). ci_verify refuses such receipts by
# default and relies on them only under an explicit accepts_waiver_admitted opt-in — and
# even then only on the structurally valid waiver-admission SHAPE, never on `proceed`
# generally.


def _ci_bundle(
    verdict: str,
    *,
    unsettled: tuple[NonDischargeClaim, ...] = (),
    ci_kind: str = "unit_tests",
) -> CiReceiptBundle:
    evidence = {"ci_kind": ci_kind, "git_sha": "abc123", "dirty": False, "command": ["x"]}
    receipt = create_receipt(
        gate=CI_WRAP_GATE,
        verdict=verdict,
        subject_kind="ci_wrap",
        subject_bytes=ci_kind.encode(),
        evidence_bundle=evidence,
        gate_config={"ci_kind": ci_kind},
        timestamp="2026-01-01T00:00:00Z",
        unsettled=unsettled,
    )
    return CiReceiptBundle(receipt=receipt, evidence=evidence)


def _verify(tmp_path, bundles, *, accepts_waiver_admitted: bool = False):
    f = tmp_path / "r.jsonl"
    f.write_text("\n".join(b.to_json() for b in bundles) + "\n")
    policy = CiPolicy(
        required_kinds=frozenset(),
        require_clean=False,
        require_same_sha=False,
        accepts_waiver_admitted=accepts_waiver_admitted,
    )
    return ci_verify(f, policy)


def _waiver_shaped_proceed() -> CiReceiptBundle:
    return _ci_bundle(
        VERDICT_PROCEED,
        unsettled=(
            NonDischargeClaim(
                kind="evidence_sufficiency",
                reason="clean antecedents not certified: waiver-admitted",
            ),
        ),
    )


def test_criterion3_ci_verify_rejects_waiver_proceed_by_default(tmp_path):
    r = _verify(tmp_path, [_waiver_shaped_proceed()], accepts_waiver_admitted=False)
    assert not r.ok
    assert r.checks["all_pass"] is False


def test_criterion3_ci_verify_accepts_waiver_proceed_only_when_opted_in(tmp_path):
    r = _verify(tmp_path, [_waiver_shaped_proceed()], accepts_waiver_admitted=True)
    assert r.ok
    assert r.verdict == "pass"


def test_criterion3_malformed_proceed_rejected_even_with_flag(tmp_path):
    # verdict=proceed but NO unsettled block → not a valid waiver-admission shape.
    malformed = _ci_bundle(VERDICT_PROCEED, unsettled=())
    r = _verify(tmp_path, [malformed], accepts_waiver_admitted=True)
    assert not r.ok
    assert r.checks["all_pass"] is False


def test_criterion3_ordinary_pass_unchanged(tmp_path):
    r = _verify(tmp_path, [_ci_bundle("pass")], accepts_waiver_admitted=False)
    assert r.ok
    assert r.verdict == "pass"


@pytest.mark.parametrize("verdict", ["block", "warn", "observe"])
def test_criterion3_nonpass_nonwaiver_still_rejected(tmp_path, verdict):
    # Opting in to waiver admissions must not launder block/warn/observe into acceptance.
    r = _verify(tmp_path, [_ci_bundle(verdict)], accepts_waiver_admitted=True)
    assert not r.ok
