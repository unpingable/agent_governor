# SPDX-License-Identifier: Apache-2.0
"""Bootstrap-lab LA-backed effect gate — slice 1 acceptance.

Drives the REAL supervisor hot path (`create_session` → `launch_session` →
`_handle_tool_proposed`) with a fake worker adapter (the inner Claude) and a
thread-safe, contract-faithful injected Linear Accountant seam (the same shape
LA's own tests use). No real cross-repo transport; no ActiveTunableStore.

Acceptance (working/campaign-ag-walking-skeleton.md, amended):
 1. outer (this test) launches + drives an AG-supervised inner session;
 2. one inner WRITE effect crosses ONLY after LA authorizes consumption;
 3. exhaustion / replay refuses before the effect;
 4. every effect consumes one unit against its proposal identity;
 5. concurrent double-consume → at most one effect;
 6. exactly one effect crosses for one consumable unit;
 7. AG's event chain references session · proposal · LA grant/consume · effect;
 8. no BA3 budget decision competes with LA on this path;
 9. no promotion / production-baseline evidence (the bootstrap_lab fence).
"""

import threading
import time

import pytest

from governor.linear_accountant_client import LinearAccountantClient
from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    NativeEvent,
)
from governor.runtime.events import EventKind
from governor.runtime.lab_gate import (
    BOOTSTRAP_LAB_PROFILE,
    LabGate,
    LabScopeViolation,
    forbid_promotion,
)
from governor.runtime.supervisor import SessionSupervisor


# --------------------------------------------------------------------------- #
# Injected LA seam — thread-safe, faithful to InMemoryAccountant semantics.
# --------------------------------------------------------------------------- #


class _FakeReceipt:
    def __init__(self, rid: str) -> None:
        self.receipt_id = rid


class _FakeSink:
    """Minimal ReceiptSink: returns an object with .receipt_id per emit."""

    def __init__(self) -> None:
        self.n = 0
        self.emitted: list[tuple[str, str]] = []

    def emit(self, gate, verdict, subject_kind, subject_bytes,
             evidence_bundle, gate_config, **kwargs):
        self.n += 1
        rid = f"rcpt_{self.n}"
        self.emitted.append((gate, verdict))
        return _FakeReceipt(rid)


class _FakeLA:
    """Faithful fake: deposit N, grant a token, consume decrements, replay of a
    consumption_event_id → AlreadyConsumed, exhaustion → InsufficientCapacity.
    Lock-guarded so concurrent consumes cannot double-spend (matches LA's
    single-writer mutex)."""

    def __init__(self, capacity: int) -> None:
        self._lock = threading.Lock()
        self._remaining = capacity
        self._granted = capacity
        self._consumed: dict[str, int] = {}
        self.token = "tok_lab_1"
        self.consume_calls: list[str] = []

    def request_capacity(self, req: dict, now: int) -> dict:
        with self._lock:
            return {
                "decision": "Granted",
                "token_id": self.token,
                "granted_capacity": self._granted,
                "scope": req["scope"],
                "expires_at": now + 10_000,
                "receipt": "la_grant",
            }

    def consume(self, req: dict, now: int) -> dict:
        with self._lock:
            eid = req["consumption_event_id"]
            self.consume_calls.append(eid)
            if eid in self._consumed:
                return {"decision": "AlreadyConsumed"}
            if self._remaining < req["amount"]:
                return {"decision": "InsufficientCapacity"}
            self._remaining -= req["amount"]
            self._consumed[eid] = self._remaining
            return {
                "decision": "Consumed",
                "token_id": self.token,
                "consumed_amount": req["amount"],
                "remaining_capacity": self._remaining,
                "receipt": "la_consume",
            }


def _lab_context(capacity: int):
    """Build the injected LA client + bootstrap_lab policy_context."""
    fake = _FakeLA(capacity)
    sink = _FakeSink()
    client = LinearAccountantClient(
        request_capacity_callable=fake.request_capacity,
        consume_callable=fake.consume,
        admission_verifier=lambda rid: rid == "adm_lab",
        receipt_sink=sink,
    )
    ctx = {
        "bootstrap_lab": {
            "la_client": client,
            "actor": "inner_worker",
            "scope": "lab/sandbox",
            "requested_capacity": capacity,
            "admission_receipt_id": "adm_lab",
            "eligibility_valid_until": 10_000,
            "expires_after": 10_000,
            "now": 0,
        }
    }
    return ctx, fake, sink


# --------------------------------------------------------------------------- #
# Fake inner worker: proposes a sequence of governed WRITE effects.
# --------------------------------------------------------------------------- #


class _WriteWorkerAdapter:
    def __init__(self, proposals: list[tuple[str, str]]) -> None:
        # proposals: list of (tool_call_id, tool_name)
        self._proposals = proposals
        self.controls: list = []

    def capabilities(self):
        return AdapterCapabilities()

    def launch(self, config):
        return BackendHandle(pid=1)

    def iter_events(self, h):
        for tcid, name in self._proposals:
            yield NativeEvent(kind="pre_tool_use", payload={
                "tool_name": name, "tool_call_id": tcid,
                "tool_input": {"file_path": "/tmp/sandbox.txt", "content": "x"},
            })
            yield NativeEvent(kind="post_tool_use", payload={
                "tool_name": name, "tool_call_id": tcid,
            })
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, h, a):
        self.controls.append(a)

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


def _run(supervisor, adapter, ctx):
    record = supervisor.create_session(
        adapter, "test", "/tmp", operator_mode="autonomous", policy_context=ctx,
    )
    supervisor.launch_session(record.session_id)
    time.sleep(0.5)
    return record


def _by_kind(events, kind):
    return [e for e in events if e.kind == kind]


# --------------------------------------------------------------------------- #
# Tests.
# --------------------------------------------------------------------------- #


def test_la_authorizes_first_write_effect_crosses(tmp_path):
    """Acceptance 1,2,4,7: one WRITE crosses only after LA Consumed; the
    effect event carries the full LA decision identity."""
    ctx, fake, _sink = _lab_context(capacity=1)
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    adapter = _WriteWorkerAdapter([("tc_1", "write")])
    record = _run(sup, adapter, ctx)

    events = sup.get_events(record.session_id)
    allowed = _by_kind(events, EventKind.TOOL_CALL_ALLOWED)
    assert len(allowed) == 1
    p = allowed[0].payload
    assert p["profile"] == BOOTSTRAP_LAB_PROFILE
    assert p["la_kind"] == "consumed"
    # Chain identity (acceptance §7): proposal + LA grant + LA consume + token.
    assert p["tool_call_id"] == "tc_1"
    assert p["grant_receipt_id"] is not None
    assert p["consume_receipt_id"] is not None
    assert p["token_id"] == "tok_lab_1"
    # Acceptance §4: consume keyed by session:proposal identity.
    assert fake.consume_calls == [f"{record.session_id}:tc_1"]
    # The effect actually crossed: an approve control was sent to the worker.
    assert any(getattr(c, "kind", None) == "approve" for c in adapter.controls)


def test_exhausted_grant_refuses_before_effect(tmp_path):
    """Acceptance 3,6: capacity=1, three distinct WRITEs → exactly one effect
    crosses; the rest are capacity_refused before crossing."""
    ctx, _fake, _sink = _lab_context(capacity=1)
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    adapter = _WriteWorkerAdapter([("tc_1", "write"), ("tc_2", "write"), ("tc_3", "write")])
    record = _run(sup, adapter, ctx)

    events = sup.get_events(record.session_id)
    allowed = _by_kind(events, EventKind.TOOL_CALL_ALLOWED)
    denied = _by_kind(events, EventKind.TOOL_CALL_DENIED)
    assert len(allowed) == 1, "exactly one effect for one consumable unit"
    assert len(denied) == 2
    assert all(d.payload["la_kind"] == "capacity_refused" for d in denied)
    # Refused before effect: only one approve control ever sent.
    approves = [c for c in adapter.controls if getattr(c, "kind", None) == "approve"]
    denies = [c for c in adapter.controls if getattr(c, "kind", None) == "deny"]
    assert len(approves) == 1
    assert len(denies) == 2


def test_replay_proposal_refused_already_consumed(tmp_path):
    """Acceptance 3: a replayed proposal id (same tool_call_id) → already_consumed."""
    ctx, _fake, _sink = _lab_context(capacity=5)  # capacity is not the limiter here
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    adapter = _WriteWorkerAdapter([("tc_dup", "write"), ("tc_dup", "write")])
    record = _run(sup, adapter, ctx)

    events = sup.get_events(record.session_id)
    allowed = _by_kind(events, EventKind.TOOL_CALL_ALLOWED)
    denied = _by_kind(events, EventKind.TOOL_CALL_DENIED)
    assert len(allowed) == 1
    assert len(denied) == 1
    assert denied[0].payload["la_kind"] == "already_consumed"


def test_concurrent_double_consume_one_effect():
    """Acceptance 5: two threads racing one unit → exactly one allowed."""
    ctx, _fake, _sink = _lab_context(capacity=1)
    client = ctx["bootstrap_lab"]["la_client"]
    gate = LabGate(la_client=client, session_id="sess_x", actor="w", scope="lab/sandbox")
    g = gate.acquire_grant(
        requested_capacity=1, admission_receipt_id="adm_lab",
        eligibility_valid_until=10_000, expires_after=10_000, now=0,
    )
    assert gate.token_id is not None

    results = []
    barrier = threading.Barrier(2)

    def attempt(tcid):
        barrier.wait()
        results.append(gate.decide_write_effect(tool_call_id=tcid, now=1))

    threads = [threading.Thread(target=attempt, args=(f"tc_{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed = [r for r in results if r.allowed]
    assert len(allowed) == 1, "exactly one effect crosses for one unit under concurrency"


def test_no_ba3_budget_competes(tmp_path):
    """Acceptance 8: lab path stands up no BA3 budget ledger — LA is sole
    spend authority. No budget_ledger event, get_budget is None."""
    ctx, _fake, _sink = _lab_context(capacity=1)
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    adapter = _WriteWorkerAdapter([("tc_1", "write")])
    record = _run(sup, adapter, ctx)

    assert sup.get_budget(record.session_id) is None
    events = sup.get_events(record.session_id)
    assert _by_kind(events, "budget_ledger") == []
    assert _by_kind(events, "budget_exhausted") == []


def test_lab_fence_forbids_promotion():
    """Acceptance 9: bootstrap_lab evidence cannot mint promotion/baseline."""
    with pytest.raises(LabScopeViolation):
        forbid_promotion(BOOTSTRAP_LAB_PROFILE)
    # A non-lab profile is unaffected (the fence is scoped, not a blanket ban).
    forbid_promotion("production")
    forbid_promotion(None)


def test_read_tools_do_not_consume(tmp_path):
    """READ effects do not spend the grant — only governed WRITE crosses the
    LA gate (the spend authority is on the effect class that mutates)."""
    ctx, fake, _sink = _lab_context(capacity=1)
    sup = SessionSupervisor(state_dir=tmp_path / "rt")
    adapter = _WriteWorkerAdapter([("tc_r", "read"), ("tc_w", "write")])
    record = _run(sup, adapter, ctx)

    # The read did not consume; only the write did.
    assert fake.consume_calls == [f"{record.session_id}:tc_w"]
