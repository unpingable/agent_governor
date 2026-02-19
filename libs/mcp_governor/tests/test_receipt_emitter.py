# SPDX-License-Identifier: Apache-2.0
"""Tests for mcp_governor.receipt_emitter."""

import json

from receipt_v1 import ExecutionStatus, verify

from mcp_governor.receipt_emitter import (
    ReceiptEmitter,
    _args_summary,
    _sanitize_string,
)
from mcp_governor.types import (
    ActorInfo,
    GatewaySession,
    PolicyDecision,
    ReasonCode,
    ToolCallEnvelope,
)


def _make_session() -> GatewaySession:
    return GatewaySession(
        session_id="test-session-001",
        actor_info=ActorInfo(
            client_name="test-agent",
            client_version="1.0",
            server_name="echo-server",
            server_version="0.1",
            protocol_version="2024-11-05",
        ),
        initialized=True,
    )


def _make_envelope(tool_name: str = "echo", call_id: str = "1") -> ToolCallEnvelope:
    return ToolCallEnvelope(
        tool_name=tool_name,
        arguments={"text": "hello"},
        call_id=call_id,
    )


class TestArgsSummary:
    def test_empty(self):
        assert _args_summary({}) == "args: (empty)"

    def test_few_keys(self):
        assert _args_summary({"a": 1, "b": 2}) == "args: a, b"

    def test_many_keys(self):
        args = {f"key{i}": i for i in range(15)}
        summary = _args_summary(args)
        assert "+5 more" in summary


class TestSanitizeString:
    def test_truncates(self):
        result = _sanitize_string("x" * 300)
        assert len(result) <= 256

    def test_single_line(self):
        result = _sanitize_string("line1\nline2\nline3")
        assert "\n" not in result

    def test_scrubs_api_key(self):
        result = _sanitize_string("error: api_key=sk-1234567890abcdefghij")
        assert "sk-1234567890" not in result
        assert "[REDACTED]" in result

    def test_scrubs_bearer_token(self):
        result = _sanitize_string("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
        assert "eyJhbG" not in result


class TestReceiptEmitter:
    def test_allow_receipt(self, tmp_path):
        emitter = ReceiptEmitter(
            receipt_path=tmp_path / "receipts.jsonl",
            upstream_command=["python", "-m", "echo_server"],
            fsync=False,
        )
        session = _make_session()
        envelope = _make_envelope()
        decision = PolicyDecision(
            allow=True,
            reason_code=ReasonCode.POLICY_ALLOW,
            reason_human="Tool not in deny list",
        )

        receipt = emitter.emit(
            session, envelope, decision,
            execution_status=ExecutionStatus.SUCCESS,
            duration_ms=42,
        )

        assert receipt.decision.action.value == "allow"
        assert receipt.decision.reason_code == "gov.policy_allow"
        assert receipt.tool.tool_id == "echo"
        assert receipt.tool.call_id == "1"
        assert receipt.chain.seq == 1
        assert receipt.ext is not None
        assert receipt.ext["gov.mcp.client.name"] == "test-agent"
        assert receipt.ext["gov.mcp.upstream.server_id"] == "upstream"

        # Verify receipt is valid
        result = verify(receipt.to_dict())
        assert result.valid, f"Invalid receipt: {result.errors}"

    def test_deny_receipt(self, tmp_path):
        emitter = ReceiptEmitter(
            receipt_path=tmp_path / "receipts.jsonl",
            fsync=False,
        )
        session = _make_session()
        envelope = _make_envelope(tool_name="shell.exec")
        decision = PolicyDecision(
            allow=False,
            reason_code=ReasonCode.POLICY_DENY,
            reason_human="Tool matches deny pattern: shell\\..*",
            matched_pattern=r"shell\..*",
        )

        receipt = emitter.emit(session, envelope, decision)

        assert receipt.decision.action.value == "deny"
        assert receipt.decision.reason_code == "gov.policy_deny"
        assert receipt.execution is None  # no execution for deny

        result = verify(receipt.to_dict())
        assert result.valid, f"Invalid receipt: {result.errors}"

    def test_chain_continuity(self, tmp_path):
        emitter = ReceiptEmitter(
            receipt_path=tmp_path / "receipts.jsonl",
            fsync=False,
        )
        session = _make_session()
        decision = PolicyDecision(allow=True, reason_code=ReasonCode.POLICY_ALLOW)

        r1 = emitter.emit(
            session, _make_envelope(call_id="1"), decision,
            execution_status=ExecutionStatus.SUCCESS,
        )
        r2 = emitter.emit(
            session, _make_envelope(call_id="2"), decision,
            execution_status=ExecutionStatus.SUCCESS,
        )

        assert r1.chain.seq == 1
        assert r2.chain.seq == 2
        assert r2.chain.parent_receipt_id == r1.receipt_id
        assert r2.chain.parent_receipt_hash == r1.receipt_hash

    def test_file_written(self, tmp_path):
        path = tmp_path / "receipts.jsonl"
        emitter = ReceiptEmitter(receipt_path=path, fsync=False)
        session = _make_session()
        decision = PolicyDecision(allow=True, reason_code=ReasonCode.POLICY_ALLOW)

        emitter.emit(
            session, _make_envelope(), decision,
            execution_status=ExecutionStatus.SUCCESS,
        )

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["decision"]["action"] == "allow"

    def test_error_sanitized_in_receipt(self, tmp_path):
        emitter = ReceiptEmitter(
            receipt_path=tmp_path / "receipts.jsonl",
            fsync=False,
        )
        session = _make_session()
        envelope = _make_envelope()
        decision = PolicyDecision(allow=True, reason_code=ReasonCode.POLICY_ALLOW)

        receipt = emitter.emit(
            session, envelope, decision,
            execution_status=ExecutionStatus.FAILURE,
            error="Error: api_key=sk-12345678901234567890 failed\nStack trace:\n  at foo.py:42",
        )

        assert receipt.execution is not None
        assert "\n" not in receipt.execution.error
        assert "sk-12345678" not in receipt.execution.error

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "receipts.jsonl"
        emitter = ReceiptEmitter(receipt_path=path, fsync=False)
        assert path.parent.exists()

    def test_int_call_id_stringified(self, tmp_path):
        emitter = ReceiptEmitter(
            receipt_path=tmp_path / "receipts.jsonl",
            fsync=False,
        )
        session = _make_session()
        envelope = ToolCallEnvelope(
            tool_name="echo",
            arguments={"text": "hello"},
            call_id="42",  # already stringified by gateway
        )
        decision = PolicyDecision(allow=True, reason_code=ReasonCode.POLICY_ALLOW)

        receipt = emitter.emit(
            session, envelope, decision,
            execution_status=ExecutionStatus.SUCCESS,
        )
        assert receipt.tool.call_id == "42"
