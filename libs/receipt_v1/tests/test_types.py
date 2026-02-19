# SPDX-License-Identifier: Apache-2.0
"""Tests for Receipt v1 types: serialization roundtrips."""

from __future__ import annotations

import pytest

from receipt_v1.types import (
    Action,
    Actor,
    AuthContext,
    Budget,
    Chain,
    Decision,
    EffectsConfidence,
    Execution,
    ExecutionStatus,
    Origin,
    PolicyOutcome,
    PolicyStep,
    Provenance,
    Receipt,
    Tool,
    Transport,
)


class TestActorSerialization:
    def test_minimal(self):
        a = Actor(agent_id="a1", session_id="s1")
        d = a.to_dict()
        assert d == {"agent_id": "a1", "session_id": "s1"}

    def test_full(self):
        a = Actor(agent_id="a1", session_id="s1", runtime="claude-code",
                  issuer="acme", auth_context=AuthContext.OAUTH)
        d = a.to_dict()
        assert d["runtime"] == "claude-code"
        assert d["auth_context"] == "oauth"

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError, match="must not be empty"):
            Actor(agent_id="a1", session_id="s1", runtime="")


class TestToolSerialization:
    def test_minimal(self):
        t = Tool(tool_id="fs.read", args_hash="a" * 64)
        d = t.to_dict()
        assert d == {"tool_id": "fs.read", "args_hash": "a" * 64}

    def test_args_summary_sanitized(self):
        t = Tool(tool_id="fs.read", args_hash="a" * 64,
                 args_summary="line1\nline2")
        assert "\n" not in t.args_summary

    def test_args_summary_truncated(self):
        t = Tool(tool_id="fs.read", args_hash="a" * 64,
                 args_summary="x" * 300)
        assert len(t.args_summary) == 256

    def test_with_origin(self):
        o = Origin(server_id="srv1", transport=Transport.STDIO)
        t = Tool(tool_id="fs.read", args_hash="a" * 64, origin=o)
        d = t.to_dict()
        assert d["origin"] == {"server_id": "srv1", "transport": "stdio"}


class TestDecisionSerialization:
    def test_minimal(self):
        d = Decision(action=Action.ALLOW, reason_code="gov.passthrough")
        out = d.to_dict()
        assert out == {"action": "allow", "reason_code": "gov.passthrough"}

    def test_with_policy_path(self):
        steps = [PolicyStep(id="p1", version="1.0", outcome=PolicyOutcome.PASS)]
        d = Decision(action=Action.DENY, reason_code="gov.policy_deny",
                     policy_path=steps)
        out = d.to_dict()
        assert out["policy_path"] == [{"id": "p1", "version": "1.0", "outcome": "pass"}]

    def test_with_budget(self):
        b = Budget(rate_remaining=9, retries_remaining=2)
        d = Decision(action=Action.DENY, reason_code="gov.budget_exhausted",
                     budget=b)
        out = d.to_dict()
        assert out["budget"] == {"rate_remaining": 9, "retries_remaining": 2}


class TestExecutionSerialization:
    def test_minimal(self):
        e = Execution(status=ExecutionStatus.SUCCESS)
        d = e.to_dict()
        assert d == {"status": "success", "attempt": 1}

    def test_side_effects_sorted_deduped(self):
        e = Execution(status=ExecutionStatus.SUCCESS,
                      side_effects=["fs:write", "fs:read", "fs:write"])
        assert e.side_effects == ["fs:read", "fs:write"]

    def test_error_sanitized(self):
        e = Execution(status=ExecutionStatus.FAILURE,
                      error="line1\nline2\rline3")
        assert "\n" not in e.error
        assert "\r" not in e.error

    def test_invalid_attempt(self):
        with pytest.raises(ValueError, match="attempt must be >= 1"):
            Execution(status=ExecutionStatus.SUCCESS, attempt=0)

    def test_invalid_duration(self):
        with pytest.raises(ValueError, match="duration_ms must be >= 0"):
            Execution(status=ExecutionStatus.SUCCESS, duration_ms=-1)


class TestChainConstraints:
    def test_seq_1_no_parents(self):
        c = Chain(seq=1)
        assert c.to_dict() == {"seq": 1}

    def test_seq_1_rejects_parents(self):
        with pytest.raises(ValueError, match="seq=1 must not have"):
            Chain(seq=1, parent_receipt_id="abc", parent_receipt_hash="def")

    def test_seq_gt1_requires_parents(self):
        with pytest.raises(ValueError, match="seq>1 requires both"):
            Chain(seq=2)

    def test_seq_gt1_with_parents(self):
        c = Chain(seq=2, parent_receipt_id="abc", parent_receipt_hash="d" * 64)
        d = c.to_dict()
        assert d["seq"] == 2
        assert d["parent_receipt_id"] == "abc"

    def test_seq_zero_rejected(self):
        with pytest.raises(ValueError, match="seq must be >= 1"):
            Chain(seq=0)


class TestReceiptRoundtrip:
    def _make_receipt(self) -> Receipt:
        return Receipt(
            receipt_id="019505a0-1234-7000-8000-000000000001",
            receipt_version="1.0",
            receipt_hash="a" * 64,
            chain=Chain(seq=1),
            timestamp_wall="2026-02-18T00:00:00.000Z",
            actor=Actor(agent_id="a1", session_id="s1"),
            tool=Tool(tool_id="fs.read", args_hash="b" * 64),
            decision=Decision(action=Action.ALLOW, reason_code="gov.passthrough"),
            provenance=Provenance(
                deployment_id="dep1", instance_id="inst1",
                governor_version="2.3.0",
            ),
        )

    def test_to_dict_omits_none(self):
        r = self._make_receipt()
        d = r.to_dict()
        assert "timestamp_mono" not in d
        assert "execution" not in d
        assert "ext" not in d

    def test_roundtrip(self):
        r = self._make_receipt()
        d = r.to_dict()
        r2 = Receipt.from_dict(d)
        assert r2.receipt_id == r.receipt_id
        assert r2.actor.agent_id == "a1"
        assert r2.decision.action == Action.ALLOW
        assert r2.chain.seq == 1

    def test_roundtrip_with_execution(self):
        r = Receipt(
            receipt_id="019505a0-1234-7000-8000-000000000002",
            receipt_version="1.0",
            receipt_hash="a" * 64,
            chain=Chain(seq=1),
            timestamp_wall="2026-02-18T00:00:00.000Z",
            actor=Actor(agent_id="a1", session_id="s1"),
            tool=Tool(tool_id="fs.read", args_hash="b" * 64),
            decision=Decision(action=Action.ALLOW, reason_code="gov.passthrough"),
            execution=Execution(
                status=ExecutionStatus.SUCCESS,
                side_effects=["fs:read"],
                effects_confidence=EffectsConfidence.COARSE,
                duration_ms=42,
            ),
            provenance=Provenance(
                deployment_id="dep1", instance_id="inst1",
                governor_version="2.3.0",
            ),
        )
        d = r.to_dict()
        r2 = Receipt.from_dict(d)
        assert r2.execution is not None
        assert r2.execution.status == ExecutionStatus.SUCCESS
        assert r2.execution.side_effects == ["fs:read"]
        assert r2.execution.duration_ms == 42

    def test_roundtrip_with_ext(self):
        r = Receipt(
            receipt_id="019505a0-1234-7000-8000-000000000003",
            receipt_version="1.0",
            receipt_hash="a" * 64,
            chain=Chain(seq=1),
            timestamp_wall="2026-02-18T00:00:00.000Z",
            actor=Actor(agent_id="a1", session_id="s1"),
            tool=Tool(tool_id="fs.read", args_hash="b" * 64),
            decision=Decision(action=Action.ALLOW, reason_code="gov.passthrough"),
            provenance=Provenance(
                deployment_id="dep1", instance_id="inst1",
                governor_version="2.3.0",
            ),
            ext={"acme.trace_id": "abc123"},
        )
        d = r.to_dict()
        assert d["ext"] == {"acme.trace_id": "abc123"}
        r2 = Receipt.from_dict(d)
        assert r2.ext == {"acme.trace_id": "abc123"}

    def test_empty_ext_omitted(self):
        r = Receipt(
            receipt_id="019505a0-1234-7000-8000-000000000004",
            receipt_version="1.0",
            receipt_hash="a" * 64,
            chain=Chain(seq=1),
            timestamp_wall="2026-02-18T00:00:00.000Z",
            actor=Actor(agent_id="a1", session_id="s1"),
            tool=Tool(tool_id="fs.read", args_hash="b" * 64),
            decision=Decision(action=Action.ALLOW, reason_code="gov.passthrough"),
            provenance=Provenance(
                deployment_id="dep1", instance_id="inst1",
                governor_version="2.3.0",
            ),
            ext={},
        )
        d = r.to_dict()
        assert "ext" not in d
