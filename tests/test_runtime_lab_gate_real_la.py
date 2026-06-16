# SPDX-License-Identifier: Apache-2.0
"""Slice 2: the bootstrap-lab effect gate against the REAL Linear Accountant.

Replaces the injected seam with the real `la_cli` subprocess (the Rust v0
boundary). Drives the REAL supervisor hot path; the worker performs a real file
write into a disposable git worktree ONLY when AG approves — so "exactly one
effect crosses for one unit" is checked on the filesystem, end-to-end, through
the real spendability authority.

Skips if `la_cli` is not built (`cargo build --bin la_cli` in
`~/git/linearaccountant`). Proves slice-2 acceptance §2-§6, §8, §9 with the real
transport + the constellation-edge boundary record (§4). The fully-live
inner-Claude-CLI session (§1/§7 with an actual LLM worker) is the remaining
manual dogfood; the worker here is scripted, which is the established pattern for
the supervisor's automated tests.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

from governor.linear_accountant_client import LinearAccountantClient
from governor.runtime.adapter import AdapterCapabilities, BackendHandle, NativeEvent
from governor.runtime.events import EventKind
from governor.runtime.la_subprocess import DEFAULT_LA_CLI, LASubprocess
from governor.runtime.lab_gate import (
    BOOTSTRAP_LAB_PROFILE,
    LabScopeViolation,
    forbid_promotion,
)
from governor.runtime.supervisor import SessionSupervisor

LA_CLI = os.environ.get("GOVERNOR_LA_CLI", DEFAULT_LA_CLI)

pytestmark = pytest.mark.skipif(
    not Path(LA_CLI).exists(),
    reason="la_cli not built; run `cargo build --bin la_cli` in ~/git/linearaccountant",
)


class _R:
    def __init__(self, rid):
        self.receipt_id = rid


class _Sink:
    def __init__(self):
        self.n = 0

    def emit(self, *a, **k):
        self.n += 1
        return _R(f"rcpt_{self.n}")


class _RealWriteWorker:
    """Inner worker: proposes WRITEs and performs the real file effect — but only
    when AG actually approves the proposal (the effect crosses iff LA authorized)."""

    def __init__(self, worktree, proposals):
        self.worktree = Path(worktree)
        self.proposals = proposals  # list[(tool_call_id, tool_name)]
        self.controls = []

    def capabilities(self):
        return AdapterCapabilities()

    def launch(self, config):
        return BackendHandle(pid=1)

    def iter_events(self, h):
        for tcid, name in self.proposals:
            yield NativeEvent(kind="pre_tool_use", payload={
                "tool_name": name, "tool_call_id": tcid,
                "tool_input": {"file_path": str(self.worktree / f"{tcid}.txt"),
                               "content": "effect"},
            })
            yield NativeEvent(kind="post_tool_use", payload={
                "tool_name": name, "tool_call_id": tcid,
            })
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, h, a):
        self.controls.append(a)
        if getattr(a, "kind", None) == "approve":
            # The inner worker's WRITE effect actually crosses.
            (self.worktree / f"{a.target_id}.txt").write_text("effect")

    def shutdown(self, h, g=True):
        pass

    def map_event(self, e):
        if e.kind == "pre_tool_use":
            return [{"kind": EventKind.TOOL_CALL_PROPOSED, "source_layer": "adapter",
                     "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
        if e.kind == "post_tool_use":
            return [{"kind": EventKind.TOOL_CALL_COMPLETED, "source_layer": "adapter",
                     "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
        if e.kind == "process_exit":
            return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter",
                     "payload": e.payload}]
        return []

    def is_alive(self, h):
        return False


def _disposable_worktree(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "init", "-q", str(wt)], check=True)
    subprocess.run(["git", "-C", str(wt), "config", "user.email", "lab@example.com"], check=True)
    subprocess.run(["git", "-C", str(wt), "config", "user.name", "lab"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "--allow-empty", "-m", "init"], check=True)
    return wt


def _run_real(tmp_path, capacity, proposals):
    wt = _disposable_worktree(tmp_path)
    bridge = LASubprocess(LA_CLI)
    identity = bridge.start()
    scope = "lab/sandbox"
    bridge.deposit(scope, capacity)
    client = LinearAccountantClient(
        request_capacity_callable=bridge.request_capacity,
        consume_callable=bridge.consume,
        admission_verifier=lambda rid: rid == "adm_lab",
        receipt_sink=_Sink(),
    )
    ctx = {"bootstrap_lab": {
        "la_client": client, "actor": "inner_worker", "scope": scope,
        "requested_capacity": capacity, "admission_receipt_id": "adm_lab",
        "eligibility_valid_until": 10_000, "expires_after": 10_000, "now": 0,
        "la_boundary": identity.to_dict(),
    }}
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    worker = _RealWriteWorker(wt, proposals)
    record = sup.create_session(worker, "test", str(wt),
                                operator_mode="autonomous", policy_context=ctx)
    sup.launch_session(record.session_id)
    time.sleep(0.7)
    return sup, record, wt, identity, bridge


def _kinds(events, kind):
    return [e for e in events if e.kind == kind]


def test_real_la_one_grant_one_effect(tmp_path):
    """§2,§3,§5,§6: capacity=1, three WRITEs → exactly one real file on disk;
    the other two refused (capacity_refused) BEFORE the effect — through the
    real Rust accountant."""
    sup, record, wt, _id, bridge = _run_real(tmp_path, 1, [("a", "write"), ("b", "write"), ("c", "write")])
    try:
        files = sorted(p.name for p in wt.glob("*.txt"))
        assert len(files) == 1, f"exactly one effect should cross; saw {files}"
        events = sup.get_events(record.session_id)
        allowed = _kinds(events, EventKind.TOOL_CALL_ALLOWED)
        denied = _kinds(events, EventKind.TOOL_CALL_DENIED)
        assert len(allowed) == 1
        assert allowed[0].payload["la_kind"] == "consumed"
        assert allowed[0].payload["consume_receipt_id"] is not None
        assert allowed[0].payload["grant_receipt_id"] is not None
        assert len(denied) == 2
        assert all(d.payload["la_kind"] == "capacity_refused" for d in denied)
    finally:
        bridge.close()


def test_real_la_replay_refused(tmp_path):
    """§3: a replayed proposal id → already_consumed (the real replay-kill)."""
    sup, record, wt, _id, bridge = _run_real(tmp_path, 5, [("dup", "write"), ("dup", "write")])
    try:
        events = sup.get_events(record.session_id)
        allowed = _kinds(events, EventKind.TOOL_CALL_ALLOWED)
        denied = _kinds(events, EventKind.TOOL_CALL_DENIED)
        assert len(allowed) == 1
        assert len(denied) == 1
        assert denied[0].payload["la_kind"] == "already_consumed"
        assert len(list(wt.glob("*.txt"))) == 1
    finally:
        bridge.close()


def test_real_la_boundary_recorded(tmp_path):
    """§4: the exact LA version/commit is pinned in AG's durable event chain."""
    sup, record, wt, identity, bridge = _run_real(tmp_path, 1, [("a", "write")])
    try:
        assert identity.la == "linear-accountant"
        assert identity.version == "0.0.0"
        assert identity.protocol == "v0"
        # repo_commit is the LA repo HEAD (40-hex) when resolvable.
        assert identity.repo_commit is None or len(identity.repo_commit) == 40
        events = sup.get_events(record.session_id)
        boundary = _kinds(events, "la_boundary")
        assert len(boundary) == 1
        assert boundary[0].payload["version"] == "0.0.0"
        assert boundary[0].payload["protocol"] == "v0"
        assert boundary[0].payload["grant_receipt_id"] is not None
    finally:
        bridge.close()


def test_real_la_no_ba3_and_fence(tmp_path):
    """§8,§9: no BA3 budget competes on this path; the bootstrap_lab fence bars
    promotion/baseline evidence."""
    sup, record, wt, _id, bridge = _run_real(tmp_path, 1, [("a", "write")])
    try:
        assert sup.get_budget(record.session_id) is None
        events = sup.get_events(record.session_id)
        assert _kinds(events, "budget_ledger") == []
        with pytest.raises(LabScopeViolation):
            forbid_promotion(BOOTSTRAP_LAB_PROFILE)
    finally:
        bridge.close()
