# SPDX-License-Identifier: Apache-2.0
"""Tests for budgeted execution: spend tracking, limits, violations."""

import time
import subprocess
from pathlib import Path
from typing import Any, Iterable

import pytest

from governor.runtime.budget import (
    BudgetLimit,
    BudgetPolicy,
    BudgetViolation,
    RunBudgetLedger,
    Spend,
    StepSpend,
    default_budget_policy,
)


class TestSpend:
    def test_add(self):
        a = Spend(latency_ms=100, total_tokens=500, tool_calls=1)
        b = Spend(latency_ms=200, total_tokens=300, tool_calls=2)
        c = a + b
        assert c.latency_ms == 300
        assert c.total_tokens == 800
        assert c.tool_calls == 3

    def test_to_dict_roundtrip(self):
        s = Spend(latency_ms=42, usd_micros=100)
        d = s.to_dict()
        s2 = Spend.from_dict(d)
        assert s2.latency_ms == 42
        assert s2.usd_micros == 100

    def test_zero_default(self):
        s = Spend()
        assert s.total_tokens == 0
        assert s.usd_micros == 0


class TestBudgetPolicy:
    def test_no_violation_under_limit(self):
        policy = BudgetPolicy(limits=[
            BudgetLimit(dimension="tool_calls", limit=10),
        ])
        violations = policy.check(Spend(tool_calls=5), step_count=5)
        assert violations == []

    def test_violation_over_limit(self):
        policy = BudgetPolicy(limits=[
            BudgetLimit(dimension="tool_calls", limit=3, hard=True),
        ])
        violations = policy.check(Spend(tool_calls=5), step_count=5)
        assert len(violations) == 1
        assert violations[0].dimension == "tool_calls"
        assert violations[0].actual == 5
        assert violations[0].limit == 3

    def test_max_steps(self):
        policy = BudgetPolicy(max_steps=10)
        violations = policy.check(Spend(), step_count=15)
        assert len(violations) == 1
        assert violations[0].dimension == "steps"

    def test_would_breach_hard(self):
        policy = BudgetPolicy(limits=[
            BudgetLimit(dimension="total_tokens", limit=1000, hard=True),
            BudgetLimit(dimension="tool_calls", limit=100, hard=False),  # soft
        ])
        # Over soft limit only
        v = policy.would_breach_hard(Spend(total_tokens=500, tool_calls=200), step_count=1)
        assert v is None  # soft violations don't count

        # Over hard limit
        v = policy.would_breach_hard(Spend(total_tokens=1500), step_count=1)
        assert v is not None
        assert v.dimension == "total_tokens"

    def test_multiple_limits(self):
        policy = BudgetPolicy(limits=[
            BudgetLimit(dimension="tool_calls", limit=5),
            BudgetLimit(dimension="remote_calls", limit=2),
        ])
        violations = policy.check(Spend(tool_calls=10, remote_calls=5), step_count=10)
        assert len(violations) == 2

    def test_to_dict_roundtrip(self):
        policy = BudgetPolicy(
            policy_id="test",
            limits=[BudgetLimit(dimension="tool_calls", limit=10)],
            max_steps=50,
        )
        d = policy.to_dict()
        p2 = BudgetPolicy.from_dict(d)
        assert p2.policy_id == "test"
        assert len(p2.limits) == 1
        assert p2.max_steps == 50

    def test_default_policy(self):
        p = default_budget_policy()
        assert len(p.limits) > 0
        assert p.max_steps is not None


class TestRunBudgetLedger:
    def test_record_steps(self):
        ledger = RunBudgetLedger(session_id="sess_1")
        ledger.record_step(StepSpend(
            step_index=0, step_kind="tool", tool_name="Read",
            spend=Spend(tool_calls=1, latency_ms=50),
        ))
        ledger.record_step(StepSpend(
            step_index=1, step_kind="tool", tool_name="Bash",
            spend=Spend(tool_calls=1, latency_ms=200),
        ))
        assert ledger.total_steps == 2
        assert ledger.total_spend.tool_calls == 2
        assert ledger.total_spend.latency_ms == 250

    def test_remote_hop_counting(self):
        ledger = RunBudgetLedger(session_id="sess_1")
        ledger.record_step(StepSpend(
            step_index=0, step_kind="model", provider_kind="remote",
            spend=Spend(remote_calls=1),
        ))
        ledger.record_step(StepSpend(
            step_index=1, step_kind="tool", provider_kind="local",
            spend=Spend(tool_calls=1),
        ))
        assert ledger.total_remote_hops == 1

    def test_to_dict(self):
        ledger = RunBudgetLedger(session_id="sess_1", policy_id="default")
        ledger.record_step(StepSpend(
            step_index=0, step_kind="tool",
            spend=Spend(tool_calls=1),
        ))
        d = ledger.to_dict()
        assert d["session_id"] == "sess_1"
        assert d["total_steps"] == 1
        assert d["total_spend"]["tool_calls"] == 1


class TestSupervisorBudget:
    """Test budget integration with the supervisor."""

    def test_budget_exhaustion_denies_tool(self, tmp_path):
        """When budget is exhausted, new tool calls are denied."""
        from governor.runtime.supervisor import SessionSupervisor
        from governor.runtime.adapter import BackendHandle, AdapterCapabilities, NativeEvent, ControlAction
        from governor.runtime.events import EventKind
        from governor.runtime.budget import BudgetPolicy, BudgetLimit

        class BudgetTestAdapter:
            def __init__(self):
                self._controls = []
            def capabilities(self): return AdapterCapabilities()
            def launch(self, config): return BackendHandle(pid=1)
            def iter_events(self, h):
                # Propose 5 tool calls — budget allows only 3
                for i in range(5):
                    yield NativeEvent(kind="pre_tool_use", payload={
                        "tool_name": "Read", "tool_call_id": f"tc_{i}",
                    })
                    yield NativeEvent(kind="post_tool_use", payload={
                        "tool_name": "Read", "tool_call_id": f"tc_{i}",
                    })
                yield NativeEvent(kind="process_exit", payload={"returncode": 0})
            def send_control(self, h, a): self._controls.append(a)
            def shutdown(self, h, g=True): pass
            def map_event(self, e):
                if e.kind == "pre_tool_use":
                    return [{"kind": EventKind.TOOL_CALL_PROPOSED, "source_layer": "adapter",
                             "tool_call_id": e.payload.get("tool_call_id"),
                             "payload": e.payload}]
                elif e.kind == "post_tool_use":
                    return [{"kind": EventKind.TOOL_CALL_COMPLETED, "source_layer": "adapter",
                             "tool_call_id": e.payload.get("tool_call_id"),
                             "payload": e.payload}]
                elif e.kind == "process_exit":
                    return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter",
                             "payload": e.payload}]
                return []
            def is_alive(self, h): return False

        # Budget: max 3 tool calls
        tight_policy = BudgetPolicy(
            policy_id="tight",
            limits=[BudgetLimit(dimension="tool_calls", limit=3, hard=True)],
        )

        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        adapter = BudgetTestAdapter()
        record = supervisor.create_session(
            adapter, "test", "/tmp",
            operator_mode="autonomous",
            policy_context={"budget_policy": tight_policy},
        )
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        events = supervisor.get_events(record.session_id)
        denied = [e for e in events if e.kind == EventKind.TOOL_CALL_DENIED]
        allowed = [e for e in events if e.kind == EventKind.TOOL_CALL_ALLOWED]

        # Should have some allowed and some denied
        assert len(allowed) > 0, "Should allow some tools"
        assert len(denied) > 0, "Should deny when budget exhausted"

        # Budget status should show the spend
        budget = supervisor.get_budget(record.session_id)
        assert budget is not None
        assert budget["total_steps"] > 0

    def test_budget_ledger_emitted_at_exit(self, tmp_path):
        """Budget ledger event emitted when session exits."""
        from governor.runtime.supervisor import SessionSupervisor
        from governor.runtime.adapter import BackendHandle, AdapterCapabilities, NativeEvent
        from governor.runtime.events import EventKind

        class SimpleAdapter:
            def capabilities(self): return AdapterCapabilities()
            def launch(self, config): return BackendHandle(pid=1)
            def iter_events(self, h):
                yield NativeEvent(kind="pre_tool_use", payload={
                    "tool_name": "Read", "tool_call_id": "tc_1",
                })
                yield NativeEvent(kind="post_tool_use", payload={
                    "tool_name": "Read", "tool_call_id": "tc_1",
                })
                yield NativeEvent(kind="process_exit", payload={"returncode": 0})
            def send_control(self, h, a): pass
            def shutdown(self, h, g=True): pass
            def map_event(self, e):
                if e.kind == "pre_tool_use":
                    return [{"kind": EventKind.TOOL_CALL_PROPOSED, "source_layer": "adapter",
                             "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
                elif e.kind == "post_tool_use":
                    return [{"kind": EventKind.TOOL_CALL_COMPLETED, "source_layer": "adapter",
                             "tool_call_id": e.payload.get("tool_call_id"), "payload": e.payload}]
                elif e.kind == "process_exit":
                    return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter",
                             "payload": e.payload}]
                return []
            def is_alive(self, h): return False

        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        record = supervisor.create_session(SimpleAdapter(), "test", "/tmp", operator_mode="autonomous")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        events = supervisor.get_events(record.session_id)
        ledger_events = [e for e in events if e.kind == "budget_ledger"]
        assert len(ledger_events) == 1
        assert ledger_events[0].payload["total_steps"] > 0
