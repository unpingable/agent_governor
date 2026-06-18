# SPDX-License-Identifier: Apache-2.0
"""GAP-2 C2: the continuation office spliced into the live supervisor (observe/hold; no burn).

Stage 3 governed consequence (may this effect happen?). C2 puts the continuation office in the live AG
artery to identify where the legacy loop self-authorizes the *next step*. observe records the decision and
lets the loop continue (a non-grant is a LOUD divergence); hold records and stops before the next step.

The clerk does not spend the renewal stamp: C2 calls the continuation OFFICE only — never the consumer —
so no grant is burned, no capacity consumed, no effect performed merely because C2 observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from governor.runtime.adapter import AdapterCapabilities, BackendHandle, NativeEvent
from governor.runtime.events import EventKind
from governor.runtime.supervisor import SessionSupervisor
from governor.runtime.transition_subprocess import DEFAULT_TRANSITION_CLI, TransitionSubprocess

TK_CLI = os.environ.get("GOVERNOR_TRANSITION_CLI", DEFAULT_TRANSITION_CLI)
pytestmark = pytest.mark.skipif(not Path(TK_CLI).exists(), reason="transition-cli not built")

SCOPE = "lab"
KERNEL_VERSION = "0.0.0"  # transition_kernel CARGO_PKG_VERSION
POLICY_VERSION = "policy.v1"


def _snapshot():
    return {
        "schema": "transition_kernel.composed_snapshot.v1", "kernel_version": KERNEL_VERSION,
        "operation_hash": "op-1", "admission_candidate_hash": "sha256:basis",
        "eligibility_reference": "sha256:standing-xyz", "revalidation_live": True,
        "revalidation_valid_until": 1000, "revalidated_at": 10, "capability_nonce": "nonce-7",
        "consumption_event_id": "op-1:nonce-7", "consumer": "ag:main", "scope": SCOPE,
        "target": "write", "effect_class": "create_marker_v1",
    }


def _tip(snapshot):
    return "sha256:" + hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _prior(*, outcome="consumed_effect_succeeded", snapshot="default", tip=None):
    snap = _snapshot() if snapshot == "default" else snapshot
    return {
        "prior_snapshot": snap,
        "terminal_outcome": outcome,
        "prior_chain_tip": tip if tip is not None else (_tip(snap) if snap else ""),
        "session_id": "sess-1", "actor_id": "ag:main",
        "policy_version": POLICY_VERSION, "kernel_version": KERNEL_VERSION, "scope": SCOPE,
        "remaining_capacity_ref": "token:t0",
    }


def _policy():
    return {
        "current_policy_version": POLICY_VERSION,
        "admissible_next_step_classes": ["write", "create_marker_v1"],
        "grant_ttl": 100,
    }


class _Receipts:
    """Captures every gate-receipt emit so tests can assert what C2 recorded."""

    def __init__(self):
        self.receipts = []

    def emit(self, **kw):
        self.receipts.append(kw)
        return kw

    def by_gate(self, gate):
        return [r for r in self.receipts if r.get("gate") == gate]


class _Worker:
    def __init__(self, proposals):
        self.proposals = proposals  # list of (tool_call_id, tool_name, tool_input)
        self.controls = []

    def capabilities(self):
        return AdapterCapabilities()

    def launch(self, config):
        return BackendHandle(pid=1)

    def iter_events(self, h):
        for tcid, name, tinput in self.proposals:
            yield NativeEvent(kind="pre_tool_use", payload={
                "tool_name": name, "tool_call_id": tcid, "tool_input": tinput})
            yield NativeEvent(kind="post_tool_use", payload={"tool_name": name, "tool_call_id": tcid})
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, h, a):
        self.controls.append((getattr(a, "kind", None), a.target_id))

    def shutdown(self, h, g=True):
        pass

    def is_alive(self, h):
        return False

    def map_event(self, e):
        if e.kind == "pre_tool_use":
            return [{"kind": EventKind.TOOL_CALL_PROPOSED, "source_layer": "adapter",
                     "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
        if e.kind == "post_tool_use":
            return [{"kind": EventKind.TOOL_CALL_COMPLETED, "source_layer": "adapter",
                     "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
        if e.kind == "process_exit":
            return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter", "payload": e.payload}]
        return []


def _run(tmp_path, *, mode, prior, tool_input, receipts=None, proposal=("a", "write")):
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    cont_cfg = {
        "transport": transition, "mode": mode, "receipt_system": receipts,
        "prior_terminal": prior, "policy": _policy(),
    }
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    worker = _Worker([(proposal[0], proposal[1], tool_input)])
    record = sup.create_session(worker, "t", str(tmp_path), operator_mode="autonomous",
                                policy_context={"continuation_probe": cont_cfg})
    sup.launch_session(record.session_id)
    time.sleep(0.7)
    return sup, record, worker


def _events(sup, record, kind):
    return [e for e in sup.get_events(record.session_id) if e.kind == kind]


def _no_markers(tmp_path):
    return not list(Path(tmp_path).rglob("*.marker"))


# 1. disabled is byte-identical baseline -------------------------------------- #


def test_disabled_makes_no_continuation_call(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="disabled", prior=_prior(),
                               tool_input={"x": 1}, receipts=receipts)
    assert receipts.receipts == [], "disabled probe records nothing"
    assert _events(sup, record, "continuation_divergence_observed") == []
    assert _events(sup, record, "continuation_held") == []
    # Baseline path proceeds: the write is auto-approved in autonomous mode.
    assert ("approve", "a") in worker.controls
    assert _no_markers(tmp_path)


# 2. observe records the decision and lets legacy continue -------------------- #


def test_observe_clean_continuation_grants_and_continues(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe", prior=_prior(),
                               tool_input={"x": 1}, receipts=receipts)
    seam = receipts.by_gate("continuation_seam")
    assert len(seam) == 1 and seam[0]["evidence_bundle"]["decision"] == "grant"
    # A clean grant is not a divergence; the legacy loop continues and the write is approved.
    assert _events(sup, record, "continuation_divergence_observed") == []
    assert ("approve", "a") in worker.controls
    assert _no_markers(tmp_path)


# 3. hold stops before the next step ------------------------------------------ #


def test_hold_stops_before_next_step_even_on_grant(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="hold", prior=_prior(),
                               tool_input={"x": 1}, receipts=receipts)
    held = _events(sup, record, "continuation_held")
    assert len(held) == 1
    assert ("deny", "a") in worker.controls
    assert _no_markers(tmp_path)


# 4. missing composed snapshot -> refusal recorded --------------------------- #


def test_observe_missing_snapshot_refusal_recorded(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe",
                               prior=_prior(snapshot=None), tool_input={"x": 1}, receipts=receipts)
    seam = receipts.by_gate("continuation_seam")[0]["evidence_bundle"]
    assert seam["decision"] == "refuse" and seam["kind"] == "terminal_receipt_missing_snapshot"
    assert len(_events(sup, record, "continuation_divergence_observed")) == 1


# 5. wrong chain tip -> refusal recorded ------------------------------------- #


def test_observe_wrong_chain_tip_refusal_recorded(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe",
                               prior=_prior(tip="sha256:not-the-tip"), tool_input={"x": 1},
                               receipts=receipts)
    seam = receipts.by_gate("continuation_seam")[0]["evidence_bundle"]
    assert seam["decision"] == "refuse" and seam["kind"] == "chain_tip_mismatch"
    assert len(_events(sup, record, "continuation_divergence_observed")) == 1


# 6. scope expansion request -> refusal recorded ----------------------------- #


def test_observe_scope_expansion_refusal_recorded(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe", prior=_prior(),
                               tool_input={"scope": "lab+prod"}, receipts=receipts)
    seam = receipts.by_gate("continuation_seam")[0]["evidence_bundle"]
    assert seam["decision"] == "refuse" and seam["kind"] == "scope_expansion"
    assert len(_events(sup, record, "continuation_divergence_observed")) == 1


# 7. unknown next-step class -> escalation recorded, not continuation --------- #


def test_observe_unknown_class_escalates_not_grants(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe", prior=_prior(),
                               tool_input={"next_step_class": "delete_everything"}, receipts=receipts)
    seam = receipts.by_gate("continuation_seam")[0]["evidence_bundle"]
    assert seam["decision"] == "escalate"
    assert "delete_everything" in (seam["required_authority"] or "")
    assert len(_events(sup, record, "continuation_divergence_observed")) == 1


# 8. legacy would continue after a non-success prior; kernel refuses, loudly --- #


def test_observe_refuses_continuation_after_unknown_outcome_divergence_loud(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe",
                               prior=_prior(outcome="consumed_outcome_unknown"),
                               tool_input={"x": 1}, receipts=receipts)
    seam = receipts.by_gate("continuation_seam")[0]["evidence_bundle"]
    assert seam["decision"] == "refuse" and seam["kind"] == "prior_step_not_succeeded"
    div = _events(sup, record, "continuation_divergence_observed")
    assert len(div) == 1
    assert div[0].payload["classification"] == "kernel_refuse_continuation_vs_legacy_continue"
    # The legacy loop nonetheless continued — that is the divergence we surfaced, not acted on.
    assert ("approve", "a") in worker.controls


# 9. C2 observing burns nothing / consumes nothing / performs no effect ------- #


def test_observe_burns_no_grant_consumes_nothing_no_effect(tmp_path):
    receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe", prior=_prior(),
                               tool_input={"x": 1}, receipts=receipts)
    # No marker effect anywhere; no enforce allow; the only receipt is the measurement decision.
    assert _no_markers(tmp_path)
    allowed = _events(sup, record, EventKind.TOOL_CALL_ALLOWED)
    assert all(not e.payload.get("enforce") for e in allowed)
    seam = receipts.by_gate("continuation_seam")[0]["evidence_bundle"]
    # The grant is DESCRIBED, never burned: a bound grant is present, but nothing marks it consumed.
    assert seam["decision"] == "grant"
    assert seam["grant"] is not None and "grant_id" in seam["grant"]
    assert "burned" not in seam and "consumed" not in seam


# Centerpiece: prior succeeded, agent proposes outside the slice -------------- #


def test_centerpiece_scope_expansion_observe_diverges_hold_stops(tmp_path):
    # Prior governed effect succeeded; the agent proposes a next step outside the bounded scope. A legacy
    # loop would continue. The continuation office refuses scope expansion.
    obs_receipts = _Receipts()
    sup, record, worker = _run(tmp_path, mode="observe", prior=_prior(),
                               tool_input={"scope": "lab+prod"}, receipts=obs_receipts)
    # observe: divergence recorded, legacy continued.
    assert len(_events(sup, record, "continuation_divergence_observed")) == 1
    assert ("approve", "a") in worker.controls

    # hold: same proposal STOPS before the next step.
    hold_receipts = _Receipts()
    sup2, record2, worker2 = _run(tmp_path, mode="hold", prior=_prior(),
                                  tool_input={"scope": "lab+prod"}, receipts=hold_receipts)
    assert len(_events(sup2, record2, "continuation_held")) == 1
    assert ("deny", "a") in worker2.controls
    # In both modes the renewal stamp was never spent.
    assert _no_markers(tmp_path)
