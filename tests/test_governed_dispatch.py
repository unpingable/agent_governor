# SPDX-License-Identifier: Apache-2.0
"""Tests for governed_dispatch — the enforcement membrane."""

from __future__ import annotations

import asyncio
import pytest
from dataclasses import dataclass, field
from typing import Any

from governor.governed_dispatch import (
    DaemonPreflightClient,
    DispatchContext,
    DispatchResult,
    GovernanceError,
    PreflightClient,
    PreflightDecision,
    PreflightRequest,
    governed_dispatch,
)


# =============================================================================
# Test fakes
# =============================================================================


class FakePreflightClient:
    """Returns a fixed decision for all preflight calls."""

    def __init__(
        self,
        decision: str = "allow",
        preflight_token: str | None = "fake-token",
        mode: str = "detect_only",
        block_reasons: list[dict] | None = None,
    ):
        self._decision = decision
        self._token = preflight_token
        self._mode = mode
        self._block_reasons = block_reasons or []
        self.preflight_calls: list[PreflightRequest] = []
        self.record_calls: list[dict[str, Any]] = []

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        self.preflight_calls.append(request)
        return PreflightDecision(
            decision=self._decision,
            preflight_token=self._token,
            mode=self._mode,
            block_reasons=self._block_reasons,
        )

    async def record(
        self,
        request: PreflightRequest,
        result_status: str,
        preflight_token: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        call = {
            "request": request,
            "result_status": result_status,
            "preflight_token": preflight_token,
            "record_id": record_id,
        }
        self.record_calls.append(call)
        return {"recorded": True}


class SequencePreflightClient:
    """Returns decisions from a sequence. Wraps around if exhausted."""

    def __init__(self, decisions: list[str]):
        self._decisions = decisions
        self._index = 0
        self.preflight_calls: list[PreflightRequest] = []
        self.record_calls: list[dict] = []

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        self.preflight_calls.append(request)
        decision = self._decisions[self._index % len(self._decisions)]
        self._index += 1
        return PreflightDecision(
            decision=decision,
            preflight_token=f"token-{self._index}",
            mode="enforce",
        )

    async def record(
        self,
        request: PreflightRequest,
        result_status: str,
        preflight_token: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        self.record_calls.append({
            "request": request,
            "result_status": result_status,
            "preflight_token": preflight_token,
            "record_id": record_id,
        })
        return {"recorded": True}


class FailingPreflightClient:
    """Preflight always raises."""

    def __init__(self, error: Exception | None = None):
        self._error = error or ConnectionError("daemon unreachable")

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        raise self._error

    async def record(self, *args, **kwargs) -> dict[str, Any]:
        raise self._error


class FailingRecordClient:
    """Preflight succeeds, record always raises."""

    def __init__(self):
        self.preflight_calls: list[PreflightRequest] = []
        self.record_calls: int = 0

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        self.preflight_calls.append(request)
        return PreflightDecision(decision="allow", preflight_token="tok")

    async def record(self, *args, **kwargs) -> dict[str, Any]:
        self.record_calls += 1
        raise ConnectionError("daemon died during record")


@dataclass
class SpyReceipts:
    """Spy that records transport_call invocations."""
    calls: list[DispatchContext] = field(default_factory=list)
    return_value: Any = "tool-output"
    should_fail: bool = False

    async def __call__(self, ctx: DispatchContext) -> Any:
        self.calls.append(ctx)
        if self.should_fail:
            raise RuntimeError("tool execution failed")
        return self.return_value


# =============================================================================
# Helpers
# =============================================================================


def make_request(
    tool_id: str = "read_file",
    correlation_id: str = "corr-1",
    args: dict | None = None,
    exceptions: list[str] | None = None,
) -> PreflightRequest:
    return PreflightRequest(
        tool_id=tool_id,
        correlation_id=correlation_id,
        args=args or {},
        exceptions=exceptions or [],
    )


# =============================================================================
# Test: Data types
# =============================================================================


class TestDataTypes:
    """Verify dataclass shapes and defaults."""

    def test_preflight_request_defaults(self):
        r = PreflightRequest(tool_id="t", correlation_id="c")
        assert r.args == {}
        assert r.exceptions == []

    def test_preflight_decision_defaults(self):
        d = PreflightDecision(decision="allow")
        assert d.preflight_token is None
        assert d.mode == "detect_only"
        assert d.block_reasons == []
        assert d.raw == {}

    def test_dispatch_result_defaults(self):
        d = DispatchResult(
            blocked=False,
            decision="allow",
            preflight_decision=PreflightDecision(decision="allow"),
        )
        assert d.transport_result is None
        assert d.result_status == "ok"
        assert d.record_id is None
        assert d.error is None

    def test_dispatch_context_fields(self):
        dec = PreflightDecision(decision="allow")
        ctx = DispatchContext(
            tool_id="t",
            args={"path": "/etc"},
            correlation_id="c",
            preflight_decision=dec,
        )
        assert ctx.tool_id == "t"
        assert ctx.preflight_decision is dec


# =============================================================================
# Test: Protocol
# =============================================================================


class TestProtocol:
    """Verify PreflightClient is a runtime-checkable protocol."""

    def test_fake_satisfies_protocol(self):
        client = FakePreflightClient()
        assert isinstance(client, PreflightClient)

    def test_daemon_client_satisfies_protocol(self):
        async def noop_rpc(method, params):
            return {}
        client = DaemonPreflightClient(noop_rpc)
        assert isinstance(client, PreflightClient)


# =============================================================================
# Test: GovernanceError
# =============================================================================


class TestGovernanceError:

    def test_error_fields(self):
        cause = RuntimeError("boom")
        err = GovernanceError("preflight broke", phase="preflight", cause=cause)
        assert str(err) == "preflight broke"
        assert err.phase == "preflight"
        assert err.cause is cause

    def test_error_defaults(self):
        err = GovernanceError("oops")
        assert err.phase == "unknown"
        assert err.cause is None


# =============================================================================
# Test: Blocked dispatch — THE core invariant
# =============================================================================


class TestBlockedDispatch:
    """If preflight returns blocked, transport_call is NEVER invoked."""

    @pytest.mark.asyncio
    async def test_blocked_never_calls_transport(self):
        """The test invariant: blocked → transport never called."""
        client = FakePreflightClient(decision="blocked")
        spy = SpyReceipts()
        request = make_request()

        result = await governed_dispatch(client, request, spy)

        assert result.blocked is True
        assert result.decision == "blocked"
        assert len(spy.calls) == 0, "Transport must NOT be called when blocked"

    @pytest.mark.asyncio
    async def test_blocked_result_has_no_transport_result(self):
        client = FakePreflightClient(decision="blocked")
        spy = SpyReceipts()

        result = await governed_dispatch(client, make_request(), spy)

        assert result.transport_result is None
        assert result.result_status == "blocked"

    @pytest.mark.asyncio
    async def test_blocked_does_not_call_record(self):
        """Blocked preflights must NOT record — nothing happened."""
        client = FakePreflightClient(decision="blocked")
        spy = SpyReceipts()

        await governed_dispatch(client, make_request(), spy)

        assert len(client.record_calls) == 0

    @pytest.mark.asyncio
    async def test_blocked_preserves_block_reasons(self):
        reasons = [{"rule_id": "R1", "message": "Egress after secrets read"}]
        client = FakePreflightClient(
            decision="blocked",
            block_reasons=reasons,
        )
        spy = SpyReceipts()

        result = await governed_dispatch(client, make_request(), spy)

        assert result.preflight_decision.block_reasons == reasons


# =============================================================================
# Test: Allowed dispatch (happy path)
# =============================================================================


class TestAllowedDispatch:
    """Normal flow: preflight allows, transport runs, record happens."""

    @pytest.mark.asyncio
    async def test_allow_calls_transport(self):
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts(return_value="file contents")
        request = make_request(tool_id="read_file", args={"path": "/foo"})

        result = await governed_dispatch(client, request, spy)

        assert result.blocked is False
        assert result.decision == "allow"
        assert result.transport_result == "file contents"
        assert len(spy.calls) == 1
        assert spy.calls[0].tool_id == "read_file"

    @pytest.mark.asyncio
    async def test_allow_calls_record(self):
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts()

        result = await governed_dispatch(client, make_request(), spy)

        assert len(client.record_calls) == 1
        call = client.record_calls[0]
        assert call["result_status"] == "ok"
        assert call["preflight_token"] == "fake-token"

    @pytest.mark.asyncio
    async def test_would_block_still_dispatches(self):
        """would_block (shadow mode) dispatches — it's informational."""
        client = FakePreflightClient(decision="would_block")
        spy = SpyReceipts()

        result = await governed_dispatch(client, make_request(), spy)

        assert result.blocked is False
        assert result.decision == "would_block"
        assert len(spy.calls) == 1

    @pytest.mark.asyncio
    async def test_dispatch_passes_context(self):
        """Transport receives DispatchContext with correct fields."""
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts()
        request = make_request(tool_id="http_post", args={"url": "http://x"})

        await governed_dispatch(client, request, spy)

        ctx = spy.calls[0]
        assert ctx.tool_id == "http_post"
        assert ctx.args == {"url": "http://x"}
        assert ctx.correlation_id == "corr-1"
        assert ctx.preflight_decision.decision == "allow"

    @pytest.mark.asyncio
    async def test_record_id_generated_when_not_provided(self):
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts()

        result = await governed_dispatch(client, make_request(), spy)

        assert result.record_id is not None
        assert len(result.record_id) == 32  # uuid4().hex

    @pytest.mark.asyncio
    async def test_record_id_passed_through(self):
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts()

        result = await governed_dispatch(
            client, make_request(), spy, record_id="my-id-123"
        )

        assert result.record_id == "my-id-123"
        assert client.record_calls[0]["record_id"] == "my-id-123"


# =============================================================================
# Test: Transport failure
# =============================================================================


class TestTransportFailure:
    """Transport_call raises — record still happens with failed status."""

    @pytest.mark.asyncio
    async def test_transport_failure_records_failed(self):
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts(should_fail=True)

        result = await governed_dispatch(client, make_request(), spy)

        assert result.blocked is False
        assert result.result_status == "failed"
        assert result.error is not None
        assert "tool execution failed" in result.error

    @pytest.mark.asyncio
    async def test_transport_failure_still_records(self):
        """Even when transport fails, we still call record (with 'failed')."""
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts(should_fail=True)

        await governed_dispatch(client, make_request(), spy)

        assert len(client.record_calls) == 1
        assert client.record_calls[0]["result_status"] == "failed"

    @pytest.mark.asyncio
    async def test_transport_failure_result_is_none(self):
        client = FakePreflightClient(decision="allow")
        spy = SpyReceipts(should_fail=True)

        result = await governed_dispatch(client, make_request(), spy)

        assert result.transport_result is None


# =============================================================================
# Test: Preflight failure
# =============================================================================


class TestPreflightFailure:
    """Preflight itself fails — default is fail-closed."""

    @pytest.mark.asyncio
    async def test_preflight_error_raises_governance_error(self):
        client = FailingPreflightClient()
        spy = SpyReceipts()

        with pytest.raises(GovernanceError) as exc_info:
            await governed_dispatch(client, make_request(), spy)

        assert exc_info.value.phase == "preflight"
        assert exc_info.value.cause is not None
        assert len(spy.calls) == 0, "Transport must NOT be called"

    @pytest.mark.asyncio
    async def test_fail_open_dispatches_on_preflight_error(self):
        """With fail_open=True, preflight error → dispatch proceeds."""
        client = FailingPreflightClient()
        spy = SpyReceipts(return_value="fallback-result")

        result = await governed_dispatch(
            client, make_request(), spy, fail_open=True
        )

        assert result.blocked is False
        assert result.decision == "allow"
        assert result.transport_result == "fallback-result"
        assert result.preflight_decision.mode == "fail_open"

    @pytest.mark.asyncio
    async def test_fail_open_still_attempts_record(self):
        """fail_open: preflight fails, dispatch runs, record is attempted
        (record may also fail since daemon is down — that's logged, not fatal)."""
        # Use a client where preflight fails but record also fails
        failing_client = FailingPreflightClient()
        spy = SpyReceipts()

        # Should not raise even though record will also fail
        result = await governed_dispatch(
            failing_client, make_request(), spy, fail_open=True
        )

        assert result.blocked is False
        assert len(spy.calls) == 1


# =============================================================================
# Test: Record failure (tool already ran)
# =============================================================================


class TestRecordFailure:
    """Record fails after transport succeeds — result is still returned."""

    @pytest.mark.asyncio
    async def test_record_failure_returns_result(self):
        """Tool ran successfully but record failed — return the result anyway."""
        client = FailingRecordClient()
        spy = SpyReceipts(return_value="precious-data")

        result = await governed_dispatch(client, make_request(), spy)

        assert result.blocked is False
        assert result.transport_result == "precious-data"
        assert result.result_status == "ok"

    @pytest.mark.asyncio
    async def test_record_failure_attempted(self):
        client = FailingRecordClient()
        spy = SpyReceipts()

        await governed_dispatch(client, make_request(), spy)

        assert client.record_calls == 1


# =============================================================================
# Test: Sequence (multi-step composition)
# =============================================================================


class TestSequenceDispatch:
    """Multiple governed dispatches in sequence."""

    @pytest.mark.asyncio
    async def test_allow_then_blocked(self):
        """First call allowed, second blocked — models a composition deny."""
        client = SequencePreflightClient(["allow", "blocked"])
        spy = SpyReceipts()

        r1 = await governed_dispatch(client, make_request(tool_id="read_file"), spy)
        r2 = await governed_dispatch(client, make_request(tool_id="http_post"), spy)

        assert r1.blocked is False
        assert r2.blocked is True
        assert len(spy.calls) == 1  # only read_file ran

    @pytest.mark.asyncio
    async def test_three_step_sequence(self):
        client = SequencePreflightClient(["allow", "allow", "blocked"])
        spy = SpyReceipts()

        results = []
        for tool in ["read_file", "analyze", "http_post"]:
            r = await governed_dispatch(client, make_request(tool_id=tool), spy)
            results.append(r)

        assert not results[0].blocked
        assert not results[1].blocked
        assert results[2].blocked
        assert len(spy.calls) == 2


# =============================================================================
# Test: DaemonPreflightClient adapter
# =============================================================================


class TestDaemonPreflightClient:
    """Tests for the daemon RPC adapter."""

    @pytest.mark.asyncio
    async def test_preflight_calls_rpc(self):
        calls = []

        async def fake_rpc(method: str, params: dict) -> dict:
            calls.append((method, params))
            return {
                "decision": "allow",
                "preflight_token": "tok-abc",
                "mode": "enforce",
                "block_reasons": [],
            }

        client = DaemonPreflightClient(fake_rpc)
        request = make_request(tool_id="shell_exec", args={"cmd": "ls"})

        decision = await client.preflight(request)

        assert len(calls) == 1
        assert calls[0][0] == "chain.preflight"
        assert calls[0][1]["tool_id"] == "shell_exec"
        assert calls[0][1]["correlation_id"] == "corr-1"
        assert calls[0][1]["args"] == {"cmd": "ls"}
        assert decision.decision == "allow"
        assert decision.preflight_token == "tok-abc"
        assert decision.mode == "enforce"

    @pytest.mark.asyncio
    async def test_record_calls_rpc(self):
        calls = []

        async def fake_rpc(method: str, params: dict) -> dict:
            calls.append((method, params))
            return {"recorded": True}

        client = DaemonPreflightClient(fake_rpc)
        request = make_request()

        resp = await client.record(
            request,
            result_status="ok",
            preflight_token="tok-abc",
            record_id="rid-1",
        )

        assert len(calls) == 1
        assert calls[0][0] == "chain.record"
        assert calls[0][1]["result_status"] == "ok"
        assert calls[0][1]["preflight_token"] == "tok-abc"
        assert calls[0][1]["record_id"] == "rid-1"
        assert resp["recorded"] is True

    @pytest.mark.asyncio
    async def test_preflight_error_response_raises(self):
        async def error_rpc(method: str, params: dict) -> dict:
            return {"error": "not_allowed_in_mode", "message": "use preflight"}

        client = DaemonPreflightClient(error_rpc)

        with pytest.raises(GovernanceError) as exc_info:
            await client.preflight(make_request())

        assert "not_allowed_in_mode" in str(exc_info.value) or "use preflight" in str(exc_info.value)
        assert exc_info.value.phase == "preflight"

    @pytest.mark.asyncio
    async def test_record_error_response_raises(self):
        async def error_rpc(method: str, params: dict) -> dict:
            return {"error": "stale_preflight", "message": "log drifted"}

        client = DaemonPreflightClient(error_rpc)

        with pytest.raises(GovernanceError) as exc_info:
            await client.record(make_request(), result_status="ok")

        assert exc_info.value.phase == "record"

    @pytest.mark.asyncio
    async def test_preflight_omits_empty_args(self):
        """Empty args/exceptions should not be sent as params."""
        calls = []

        async def spy_rpc(method: str, params: dict) -> dict:
            calls.append(params)
            return {"decision": "allow"}

        client = DaemonPreflightClient(spy_rpc)
        request = PreflightRequest(tool_id="t", correlation_id="c")

        await client.preflight(request)

        assert "args" not in calls[0]
        assert "exceptions" not in calls[0]

    @pytest.mark.asyncio
    async def test_preflight_includes_exceptions(self):
        calls = []

        async def spy_rpc(method: str, params: dict) -> dict:
            calls.append(params)
            return {"decision": "allow"}

        client = DaemonPreflightClient(spy_rpc)
        request = PreflightRequest(
            tool_id="t", correlation_id="c", exceptions=["EX-1"]
        )

        await client.preflight(request)

        assert calls[0]["exceptions"] == ["EX-1"]

    @pytest.mark.asyncio
    async def test_preflight_raw_preserved(self):
        """The raw daemon response is preserved for debugging."""
        raw_resp = {
            "decision": "would_block",
            "mode": "enforce_shadow",
            "kernel_verdict": "deny",
            "effective_verdict": "deny",
            "block_reasons": [{"rule_id": "R1"}],
            "preflight_token": "tok",
            "extra_field": "preserved",
        }

        async def rpc(method: str, params: dict) -> dict:
            return raw_resp

        client = DaemonPreflightClient(rpc)
        decision = await client.preflight(make_request())

        assert decision.raw == raw_resp
        assert decision.raw["extra_field"] == "preserved"


# =============================================================================
# Test: Integration with daemon dispatcher (in-process)
# =============================================================================


class TestDaemonIntegration:
    """Test DaemonPreflightClient wired to the real daemon dispatcher."""

    @staticmethod
    def _make_rpc_caller(dispatcher):
        """Build an async rpc_call function for a given dispatcher."""
        async def rpc_call(method: str, params: dict) -> dict:
            msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            }
            resp = await dispatcher.dispatch(msg)
            if resp and "error" in resp:
                return {
                    "error": resp["error"]["code"],
                    "message": resp["error"]["message"],
                }
            return resp.get("result", {})
        return rpc_call

    @staticmethod
    def _setup_daemon(gov_dir):
        """Create DaemonState + Dispatcher with handlers registered."""
        from governor.daemon import Dispatcher, register_handlers, DaemonState
        state = DaemonState(gov_dir, mode="general")
        d = Dispatcher()
        register_handlers(d, state)
        return d, state

    @staticmethod
    def _write_chain_rules(gov_dir, rules=None):
        """Write chain_rules.json for the daemon to load."""
        import json
        if rules is None:
            rules = [{
                "rule_id": "exfil-001",
                "prior_sensitivity_gte": "secret_candidate",
                "proposed_capability": "network_egress",
                "proposed_trust_domain": "external",
                "effect": "deny",
            }]
        data = {"rules": rules, "rule_set_version": "1.0.0"}
        (gov_dir / "chain_rules.json").write_text(json.dumps(data))

    @pytest.mark.asyncio
    async def test_full_governed_dispatch_with_daemon(self, tmp_path):
        """End-to-end: governed_dispatch → DaemonPreflightClient → real daemon."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        d, state = self._setup_daemon(gov_dir)
        rpc_call = self._make_rpc_caller(d)

        client = DaemonPreflightClient(rpc_call)
        spy = SpyReceipts(return_value="real-output")
        request = make_request(tool_id="read_file", args={"path": "/etc/passwd"})

        result = await governed_dispatch(client, request, spy)

        # Default mode is detect_only, no rules → should allow
        assert result.blocked is False
        assert result.decision == "allow"
        assert result.transport_result == "real-output"
        assert len(spy.calls) == 1

    @pytest.mark.asyncio
    async def test_governed_dispatch_blocked_in_enforce_mode(self, tmp_path):
        """With enforce mode + deny rule, dispatch is blocked.

        Scenario: read_file(.env) already in action log, then
        http_post(external URL) triggers the exfil composition rule.

        We record the first step via chain.record directly (simulating
        a prior governed_dispatch cycle), then use governed_dispatch
        for the second step to prove the enforcement gate works.
        """
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Write chain rules and set up daemon
        self._write_chain_rules(gov_dir)
        d, state = self._setup_daemon(gov_dir)

        # Force enforce mode
        state._chain_mode = "enforce"
        # Force lazy reload of rules from file
        state._chain_rule_set = None

        rpc_call = self._make_rpc_caller(d)
        client = DaemonPreflightClient(rpc_call)

        # Plant history: record read_file(.env) directly via chain.record RPC
        # (this simulates a prior governed_dispatch cycle that already completed)
        record_resp = await rpc_call("chain.record", {
            "tool_id": "read_file",
            "args": {"path": "/app/.env"},
            "result_status": "ok",
            "correlation_id": "corr-1",
        })
        assert record_resp.get("recorded") is True

        # Now: http_post to external URL should be BLOCKED by exfil rule
        spy = SpyReceipts(return_value="should-never-get-this")
        result = await governed_dispatch(
            client,
            make_request(
                tool_id="http_post",
                args={"url": "https://attacker.com/api"},
            ),
            spy,
        )

        assert result.blocked is True
        assert result.decision == "blocked"
        assert len(spy.calls) == 0, "Transport MUST NOT be called when blocked"
