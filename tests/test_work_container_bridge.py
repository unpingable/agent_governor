# SPDX-License-Identifier: Apache-2.0
"""Slice 4b — the WorkContainer ⇄ gate-receipt bridge (live emit/consume seam).

The through-line: admission becomes a first-class, resolvable AG GateReceipt, and
consumption RE-VERIFIES the container against it. A valid, well-sealed container that
cites an admission which does not exist — or which admitted *different* work — is
refused. And the dispatch decision never depends on the provider registry.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path

import pytest

from governor.gate_receipt import GateReceiptSystem
from governor.provider_descriptors import claude_code_descriptor
from governor.provider_registry import ProviderRegistry
from governor.work_container import WorkContainerError, _seal_over, project_cd4b_work_container, verify_container
from governor.work_container_bridge import (
    WORK_ADMISSION_GATE,
    AdmissionBindingError,
    AdmissionNotFoundError,
    AdmissionRefusedError,
    admit_cd4b,
    dispatch_preflight,
    emit_admission_receipt,
    resolve_admission,
)

_REPO = Path(__file__).resolve().parents[1]
_SPECIMEN = _REPO / "docs" / "campaigns" / "conveyor-dogfood" / "specimens" / "cd4-docs-normalize"


@pytest.fixture()
def receipts(tmp_path):
    return GateReceiptSystem(tmp_path)


@pytest.fixture()
def backed(receipts):
    receipt, wc = admit_cd4b(receipts, _SPECIMEN)
    return receipts, receipt, wc


def _reseal(d: dict) -> dict:
    body = {k: v for k, v in d.items() if k != "custody"}
    body["custody"] = {k: v for k, v in d["custody"].items() if k != "digest"}
    d["custody"]["digest"] = _seal_over(body)
    return d


# --- emit ------------------------------------------------------------------- #
def test_admit_binds_admission_ref_to_a_real_receipt(backed):
    _receipts, receipt, wc = backed
    sd = wc.to_schema_dict()
    assert sd["admission_ref"] == "sha256:" + receipt.receipt_id
    assert receipt.gate == WORK_ADMISSION_GATE
    assert receipt.verdict == "proceed"
    verify_container(sd)  # still a well-formed, sealed container


def test_s4b_admission_ref_replaces_the_s4a_bootstrap_seal(backed):
    # The S4a projection's admission_ref is the basis-seal; S4b's is a receipt id.
    _receipts, _receipt, wc = backed
    s4a = project_cd4b_work_container(_SPECIMEN).admission_ref
    assert wc.admission_ref != s4a  # replaced, not the bootstrap digest


def test_emit_fails_closed_on_unverified_citation(receipts):
    from governor.work_container import Citation

    with pytest.raises(WorkContainerError):
        emit_admission_receipt(
            receipts,
            plan_ref="sha256:" + "d" * 64,
            citations=(Citation("ration_card_digest", "sha256:" + "2" * 64, False),),
            scope_source_ref="sha256:" + "1" * 64,
            ration_source_ref="sha256:" + "1" * 64,
        )


def test_emit_is_deterministic_across_timestamp(tmp_path):
    # receipt_id is content-addressed (timestamp-free), so admitting the same basis
    # twice yields the same admission_ref — a stable, reproducible seam.
    a_receipts = GateReceiptSystem(tmp_path / "a")
    b_receipts = GateReceiptSystem(tmp_path / "b")
    _, wc_a = admit_cd4b(a_receipts, _SPECIMEN)
    _, wc_b = admit_cd4b(b_receipts, _SPECIMEN)
    assert wc_a.admission_ref == wc_b.admission_ref
    assert wc_a.to_json() == wc_b.to_json()


# --- consume: resolve ------------------------------------------------------- #
def test_resolve_round_trips(backed):
    receipts, receipt, wc = backed
    resolved = resolve_admission(wc.to_schema_dict(), receipts)
    assert resolved.receipt_id == receipt.receipt_id


def test_resolve_refuses_absent_admission(backed):
    _receipts, _receipt, wc = backed
    empty = GateReceiptSystem(Path(tempfile.mkdtemp()))
    with pytest.raises(AdmissionNotFoundError):
        resolve_admission(wc.to_schema_dict(), empty)


def test_resolve_refuses_forged_basis_reusing_valid_receipt(backed):
    # The load-bearing check: a forger swaps a citation (points at DIFFERENT work) and
    # reseals, but reuses the real receipt. The evidence-binds-basis check catches it.
    receipts, _receipt, wc = backed
    forged = json.loads(json.dumps(wc.to_schema_dict()))
    forged["admission_basis"]["citations"][0]["ref"] = "sha256:" + "0" * 64
    _reseal(forged)
    verify_container(forged)  # internally consistent + sealed…
    with pytest.raises(AdmissionBindingError):
        resolve_admission(forged, receipts)  # …but does not bind the cited admission


def test_resolve_refuses_scope_source_swap(backed):
    # Codex F1: a forger reuses the receipt (same plan/citations) but swaps the scope
    # projection to a DIFFERENT (e.g. broader) RationCard. The full-basis bind refuses.
    receipts, _receipt, wc = backed
    forged = json.loads(json.dumps(wc.to_schema_dict()))
    forged["scope_projection"]["source_ref"] = "sha256:" + "9" * 64
    _reseal(forged)
    verify_container(forged)
    with pytest.raises(AdmissionBindingError):
        resolve_admission(forged, receipts)


def test_resolve_refuses_ration_source_swap(backed):
    receipts, _receipt, wc = backed
    forged = json.loads(json.dumps(wc.to_schema_dict()))
    forged["ration_projection"]["source_ref"] = "sha256:" + "9" * 64
    _reseal(forged)
    with pytest.raises(AdmissionBindingError):
        resolve_admission(forged, receipts)


def test_resolve_refuses_wrong_role_receipt(receipts):
    # Codex F3: a work_admission/proceed receipt with a NON-measurement role must not
    # drive allow. emit only ever mints measurement; consume enforces it.
    from governor.work_container_bridge import build_admission_evidence

    _receipt, wc = admit_cd4b(receipts, _SPECIMEN)
    ev = build_admission_evidence(
        plan_ref=wc.origin.proposal_ref,
        citations=wc.admission_basis.citations,
        scope_source_ref=wc.scope_projection.source_ref,
        ration_source_ref=wc.ration_projection.source_ref,
    )
    authority_receipt = receipts.emit(
        gate=WORK_ADMISSION_GATE,
        verdict="proceed",
        subject_kind="work_admission",
        subject_bytes=b"x",
        evidence_bundle=ev,
        gate_config={"seam": "S4b"},
        receipt_role="authority",  # not measurement
    )
    pointed = dataclasses.replace(wc, admission_ref="sha256:" + authority_receipt.receipt_id)
    with pytest.raises(AdmissionBindingError):
        resolve_admission(pointed.to_schema_dict(), receipts)


def test_resolve_refuses_plan_ref_mismatch(backed):
    receipts, _receipt, wc = backed
    forged = json.loads(json.dumps(wc.to_schema_dict()))
    forged["origin"]["proposal_ref"] = "sha256:" + "0" * 64  # different plan
    _reseal(forged)
    with pytest.raises(AdmissionBindingError):
        resolve_admission(forged, receipts)


def test_resolve_refuses_non_admitting_verdict(receipts):
    # A container pointing at a real receipt whose verdict did NOT admit the work.
    receipt, wc = admit_cd4b(receipts, _SPECIMEN)
    blocked = receipts.emit(
        gate=WORK_ADMISSION_GATE,
        verdict="block",
        subject_kind="work_admission",
        subject_bytes=b"x",
        evidence_bundle={"record_kind": "work_admission"},
        gate_config={"seam": "S4b"},
    )
    pointed = dataclasses.replace(wc, admission_ref="sha256:" + blocked.receipt_id)
    with pytest.raises(AdmissionRefusedError):
        resolve_admission(pointed.to_schema_dict(), receipts)


# --- consume: dispatch preflight ------------------------------------------- #
def test_preflight_allows_admitted_container(backed):
    receipts, _receipt, wc = backed
    v = dispatch_preflight(wc.to_schema_dict(), receipts)
    assert v.allow is True
    assert v.provider == "claude_code"


def test_preflight_allow_is_registry_independent(backed):
    receipts, _receipt, wc = backed
    sd = wc.to_schema_dict()
    without = dispatch_preflight(sd, receipts)
    reg = ProviderRegistry()
    reg.register(claude_code_descriptor())
    withreg = dispatch_preflight(sd, receipts, reg)
    # allow is identical with and without the registry — the registry supplies
    # routing info only (provider_known flips), never the admission verdict.
    assert without.allow is True and withreg.allow is True
    assert without.provider_known is False and withreg.provider_known is True


def test_preflight_fails_closed_on_absent_admission(backed):
    _receipts, _receipt, wc = backed
    empty = GateReceiptSystem(Path(tempfile.mkdtemp()))
    v = dispatch_preflight(wc.to_schema_dict(), empty)
    assert v.allow is False
    assert v.reasons and "admission_unresolved" in v.reasons[0]


def test_preflight_fails_closed_on_tampered_container(backed):
    receipts, _receipt, wc = backed
    tampered = json.loads(json.dumps(wc.to_schema_dict()))
    tampered["intent"] += " (tampered)"  # stale seal, no reseal
    v = dispatch_preflight(tampered, receipts)
    assert v.allow is False
    assert "container_invalid" in v.reasons[0]


def test_preflight_survives_broken_registry(backed):
    # Codex F6: a registry whose .get() raises must not abort an already-admitted
    # decision — it degrades to a routing gap, never flips or crashes allow.
    receipts, _receipt, wc = backed

    class BrokenRegistry:
        def get(self, _pid):
            raise RuntimeError("registry down")

    v = dispatch_preflight(wc.to_schema_dict(), receipts, BrokenRegistry())
    assert v.allow is True
    assert v.provider_known is False
    assert any("registry lookup failed" in r for r in v.reasons)


# --- boundaries ------------------------------------------------------------- #
def test_bridge_has_no_launch_verb():
    # S4b decides; it does not run an agent. The live-run surface is not broadened.
    import governor.work_container_bridge as bridge

    for verb in ("launch", "run", "execute", "spawn", "start_session"):
        assert not hasattr(bridge, verb)


# --- persisted self-verifiable pair ----------------------------------------- #
def test_persisted_pair_resolves(tmp_path):
    # The specimen ships a receipt-backed container + its admission receipt/evidence.
    # Reconstruct a receipt system from them and prove the container resolves.
    container = json.loads((_SPECIMEN / "work_container.s4b.json").read_text())
    bundle = json.loads((_SPECIMEN / "admission_receipt.json").read_text())

    from governor.gate_receipt import GateReceipt

    receipts = GateReceiptSystem(tmp_path)
    receipts.receipt_store.append(GateReceipt.from_dict(bundle["receipt"]))
    stored_hash = receipts.evidence_store.put(bundle["evidence"])
    # the persisted receipt's evidence_hash must match the persisted evidence bytes
    assert stored_hash == bundle["receipt"]["evidence_hash"]
    # and the container's admission_ref must point at the persisted receipt
    assert container["admission_ref"] == "sha256:" + bundle["receipt"]["receipt_id"]

    resolved = resolve_admission(container, receipts)
    assert resolved.receipt_id == bundle["receipt"]["receipt_id"]
    v = dispatch_preflight(container, receipts)
    assert v.allow is True
