# SPDX-License-Identifier: Apache-2.0
"""GAP-2 C3: continuation enforce — the agent must present a single-use, receipt-bound grant to continue.

A grant authorizes one next-step ATTEMPT, not one successful effect: the burn is durable, happens before
the per-effect transition gate, and stays spent even if that gate later refuses. No grant -> no next step;
the legacy route is structurally unreachable from the enforce branch.

Ledger-level hostile/durability cases (5-8, 11) drive `continuation_enforce` directly (no kernel). The
supervisor cases (1-4, 9, 10, 12) drive the live hot path; 12 uses a fail-closed fake transport.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from governor.runtime.adapter import AdapterCapabilities, BackendHandle, NativeEvent
from governor.runtime.continuation_enforce import (
    C_ADMITTED,
    C_SPENT_UNKNOWN,
    finalize_continuation,
    present_continuation,
    reconstruct_continuation,
)
from governor.runtime.events import EventKind
from governor.runtime.supervisor import SessionSupervisor
from governor.runtime.transition_subprocess import (
    ContinuationProbe,
    DEFAULT_TRANSITION_CLI,
    TransitionProbe,
    TransitionSubprocess,
)

TK_CLI = os.environ.get("GOVERNOR_TRANSITION_CLI", DEFAULT_TRANSITION_CLI)
needs_cli = pytest.mark.skipif(not Path(TK_CLI).exists(), reason="transition-cli not built")

SCOPE = "lab"
KERNEL_VERSION = "0.0.0"
POLICY_VERSION = "policy.v1"


# =========================== ledger-level (no kernel) =========================== #


def _grant(expires_at=120, **over):
    g = {
        "grant_id": "cont:abc", "session_id": "sess-1", "actor_id": "ag:main",
        "chain_tip": "sha256:tip", "scope": SCOPE, "next_step_class": "write",
        "capacity_ref": "token:t0", "expires_at": expires_at,
    }
    g.update(over)
    return g


def _present(g):
    return {"session_id": g["session_id"], "actor_id": g["actor_id"], "chain_tip": g["chain_tip"],
            "scope": g["scope"], "next_step_class": g["next_step_class"], "now": 20}


def test_wrong_session_actor_chain_tip_refuse_without_burn(tmp_path):
    ledger = tmp_path / "c.jsonl"
    g = _grant()
    for field, reason in [("session_id", "session_mismatch"), ("actor_id", "actor_mismatch"),
                          ("chain_tip", "chain_tip_mismatch"), ("scope", "scope_mismatch"),
                          ("next_step_class", "next_step_class_mismatch")]:
        p = _present(g)
        p[field] = "WRONG"
        res = present_continuation(ledger, g, p, 20)
        assert res["result"] == "refused" and res["refusal"] == reason
    # None of the mismatched presentations burned the grant — the right step is still unused.
    assert reconstruct_continuation(ledger) == {}


def test_expired_grant_refuses_without_burn(tmp_path):
    ledger = tmp_path / "c.jsonl"
    g = _grant(expires_at=10)
    res = present_continuation(ledger, g, _present(g), now=20)
    assert res["result"] == "refused" and res["refusal"] == "expired"
    assert reconstruct_continuation(ledger) == {}


def test_clean_present_burns_once_then_finalize_admits(tmp_path):
    ledger = tmp_path / "c.jsonl"
    g = _grant()
    res = present_continuation(ledger, g, _present(g), 20)
    assert res["result"] == "admitted"
    # Burned but not yet finalized -> spent, outcome unknown (crash-after-burn shape).
    assert reconstruct_continuation(ledger) == {"cont:abc": C_SPENT_UNKNOWN}
    finalize_continuation(ledger, "cont:abc")
    assert reconstruct_continuation(ledger) == {"cont:abc": C_ADMITTED}


def test_reused_grant_refuses_and_parallel_admits_exactly_once(tmp_path):
    ledger = tmp_path / "c.jsonl"
    g = _grant()
    # Two presentations of the same grant against the shared durable ledger (parallel next steps).
    results = [present_continuation(ledger, g, _present(g), 20)["result"] for _ in range(2)]
    assert results.count("admitted") == 1, "a grant authorizes exactly one attempt"
    assert results.count("refused") == 1
    second = present_continuation(ledger, g, _present(g), 20)
    assert second["refusal"] == "already_consumed"


def test_crash_after_burn_is_spent_unknown_and_not_retryable(tmp_path):
    ledger = tmp_path / "c.jsonl"
    g = _grant()
    present_continuation(ledger, g, _present(g), 20)  # burn, then "crash" before finalize
    assert reconstruct_continuation(ledger) == {"cont:abc": C_SPENT_UNKNOWN}
    # Replay must NOT yield permission to re-present: the grant is spent.
    retry = present_continuation(ledger, g, _present(g), 20)
    assert retry["result"] == "refused" and retry["refusal"] == "already_consumed"


# =========================== supervisor enforce (live) ========================== #


def _snapshot():
    return {
        "schema": "transition_kernel.composed_snapshot.v1", "kernel_version": KERNEL_VERSION,
        "operation_hash": "op-1", "admission_candidate_hash": "sha256:basis",
        "eligibility_reference": "sha256:standing-xyz", "revalidation_live": True,
        "revalidation_valid_until": 1000, "revalidated_at": 10, "capability_nonce": "nonce-7",
        "consumption_event_id": "op-1:nonce-7", "consumer": "ag:main", "scope": SCOPE,
        "target": "write", "effect_class": "create_marker_v1",
    }


def _tip(snap):
    return "sha256:" + hashlib.sha256(
        json.dumps(snap, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _prior(*, outcome="consumed_effect_succeeded", snapshot="default", tip=None):
    snap = _snapshot() if snapshot == "default" else snapshot
    return {
        "prior_snapshot": snap, "terminal_outcome": outcome,
        "prior_chain_tip": tip if tip is not None else (_tip(snap) if snap else ""),
        "session_id": "sess-1", "actor_id": "ag:main", "policy_version": POLICY_VERSION,
        "kernel_version": KERNEL_VERSION, "scope": SCOPE, "remaining_capacity_ref": "token:t0",
    }


def _policy():
    return {"current_policy_version": POLICY_VERSION,
            "admissible_next_step_classes": ["write", "create_marker_v1"], "grant_ttl": 100}


class _Worker:
    def __init__(self, proposals):
        self.proposals = proposals
        self.controls = []

    def capabilities(self):
        return AdapterCapabilities()

    def launch(self, config):
        return BackendHandle(pid=1)

    def iter_events(self, h):
        for tcid, name, tinput in self.proposals:
            yield NativeEvent(kind="pre_tool_use",
                              payload={"tool_name": name, "tool_call_id": tcid, "tool_input": tinput})
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


def _run(tmp_path, *, prior, tool_input, ledger="c.jsonl", proposals=None, extra_probe=None,
         continuation_probe=None):
    if continuation_probe is None:
        transition = TransitionSubprocess(binary_path=TK_CLI)
        transition.start()
        continuation_probe = {
            "transport": transition, "mode": "enforce", "prior_terminal": prior, "policy": _policy(),
            "enforce_ledger_path": tmp_path / ledger,
        }
    policy_context = {"continuation_probe": continuation_probe}
    if extra_probe is not None:
        policy_context["transition_probe"] = extra_probe
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    worker = _Worker(proposals or [("a", "write", tool_input)])
    record = sup.create_session(worker, "t", str(tmp_path), operator_mode="autonomous",
                                policy_context=policy_context)
    sup.launch_session(record.session_id)
    time.sleep(0.7)
    return sup, record, worker


def _events(sup, record, kind):
    return [e for e in sup.get_events(record.session_id) if e.kind == kind]


@needs_cli
def test_clean_grant_burns_and_reaches_transition_gate(tmp_path):
    sup, record, worker = _run(tmp_path, prior=_prior(), tool_input={"x": 1})
    admitted = _events(sup, record, "continuation_admitted")
    assert len(admitted) == 1
    # The burn is durable and the next step reached the transition gate.
    assert reconstruct_continuation(tmp_path / "c.jsonl") == {admitted[0].payload["grant_id"]: C_ADMITTED}
    # No continuation denial; the step fell through (autonomous auto-approve).
    assert _events(sup, record, "continuation_denied") == []
    assert ("approve", "a") in worker.controls


@needs_cli
def test_no_grant_stops_before_transition_gate(tmp_path):
    # Missing composed snapshot -> the office refuses -> no grant -> stop. Nothing burned.
    sup, record, worker = _run(tmp_path, prior=_prior(snapshot=None), tool_input={"x": 1})
    assert len(_events(sup, record, "continuation_denied")) == 1
    assert ("deny", "a") in worker.controls
    assert reconstruct_continuation(tmp_path / "c.jsonl") == {}  # no burn


@needs_cli
def test_scope_expansion_refusal_stops(tmp_path):
    sup, record, worker = _run(tmp_path, prior=_prior(), tool_input={"scope": "lab+prod"})
    denied = _events(sup, record, "continuation_denied")
    assert len(denied) == 1 and denied[0].payload["detail"] == "scope_expansion"
    assert ("deny", "a") in worker.controls
    assert reconstruct_continuation(tmp_path / "c.jsonl") == {}


@needs_cli
def test_unknown_class_escalation_stops_no_legacy_fallthrough(tmp_path):
    sup, record, worker = _run(tmp_path, prior=_prior(),
                               tool_input={"next_step_class": "delete_everything"})
    denied = _events(sup, record, "continuation_denied")
    assert len(denied) == 1 and denied[0].payload["continuation_decision"] == "escalate"
    assert "delete_everything" in denied[0].payload["detail"]
    assert ("deny", "a") in worker.controls
    # No effect, no fallthrough.
    assert _events(sup, record, EventKind.TOOL_CALL_ALLOWED) == []


@needs_cli
def test_reused_grant_across_two_proposals_admits_once(tmp_path):
    # Two identical next-step proposals -> identical grant_id -> the durable ledger admits the first and
    # refuses the second (already_consumed).
    sup, record, worker = _run(tmp_path, prior=_prior(), tool_input={"x": 1},
                               proposals=[("a", "write", {"x": 1}), ("b", "write", {"x": 1})])
    assert len(_events(sup, record, "continuation_admitted")) == 1
    denied = _events(sup, record, "continuation_denied")
    assert len(denied) == 1 and denied[0].payload["detail"] == "already_consumed"


@needs_cli
def test_continuation_admits_but_downstream_effect_gate_refuses_grant_stays_spent(tmp_path):
    # Continuation enforce admits + burns; the per-effect transition gate (hold) then refuses the effect.
    # The grant remains spent — the agent used its attempt on something the effect gate declined.
    transition = TransitionSubprocess(binary_path=TK_CLI)
    transition.start()
    hold_probe = TransitionProbe(transport=transition, mode="hold", receipt_system=None)
    sup, record, worker = _run(tmp_path, prior=_prior(), tool_input={"x": 1}, extra_probe=hold_probe)
    assert len(_events(sup, record, "continuation_admitted")) == 1
    assert len(_events(sup, record, "transition_probe_held")) == 1  # downstream effect refused
    grant_id = _events(sup, record, "continuation_admitted")[0].payload["grant_id"]
    assert reconstruct_continuation(tmp_path / "c.jsonl") == {grant_id: C_ADMITTED}
    assert ("deny", "a") in worker.controls  # the effect was denied...
    # ...but the continuation was still spent (not refunded).


class _FailClosedTransport:
    """A transport whose continuation decision is always unavailable (fail-closed)."""

    binary_path = "/nonexistent/transition-cli"

    def decide_continuation(self, request, policy):
        return None


def test_fail_closed_kernel_durable_infra_refusal_never_observes(tmp_path):
    ledger = tmp_path / "c.jsonl"
    probe = ContinuationProbe(
        transport=_FailClosedTransport(), mode="enforce", receipt_system=None,
        prior_terminal=_prior(), policy=_policy(), enforce_ledger_path=ledger,
    )
    sup, record, worker = _run(tmp_path, prior=_prior(), tool_input={"x": 1}, continuation_probe=probe)
    denied = _events(sup, record, "continuation_denied")
    assert len(denied) == 1 and denied[0].payload["continuation_decision"] == "fail_closed"
    assert ("deny", "a") in worker.controls
    # Durable, not fail-silent: an infra refusal is on the ledger. Nothing was burned, nothing observed.
    recs = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert any(r["kind"] == "continuation_refusal" for r in recs)
    assert all(r["kind"] != "continuation_presented" for r in recs)
    assert _events(sup, record, EventKind.TOOL_CALL_ALLOWED) == []
