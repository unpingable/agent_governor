# SPDX-License-Identifier: Apache-2.0
"""Tests for ReceiptBuilder and ReceiptChain."""

from __future__ import annotations

import pytest

from receipt_v1.canonical import receipt_hash as compute_receipt_hash
from receipt_v1.receipt import ReceiptBuilder, ReceiptChain
from receipt_v1.types import (
    Action,
    Actor,
    Budget,
    Chain,
    EffectsConfidence,
    ExecutionStatus,
    PolicyOutcome,
    PolicyStep,
    Provenance,
)

ACTOR = Actor(agent_id="test-agent", session_id="test-session")
PROVENANCE = Provenance(
    deployment_id="test-dep", instance_id="test-inst",
    governor_version="2.3.0",
)


def _base_builder() -> ReceiptBuilder:
    return (
        ReceiptBuilder()
        .actor(ACTOR)
        .tool("fs.read", {"path": "/etc/config"})
        .decision(Action.ALLOW, "gov.passthrough")
        .provenance(PROVENANCE)
    )


class TestReceiptBuilder:

    def test_build_minimal(self):
        r = _base_builder().build(Chain(seq=1))
        assert r.receipt_version == "1.0"
        assert r.chain.seq == 1
        assert r.decision.action == Action.ALLOW
        assert len(r.receipt_hash) == 64

    def test_hash_is_correct(self):
        r = _base_builder().build(Chain(seq=1))
        d = r.to_dict()
        recomputed = compute_receipt_hash(d)
        assert r.receipt_hash == recomputed

    def test_uuid7_generated(self):
        r = _base_builder().build(Chain(seq=1))
        parts = r.receipt_id.split("-")
        assert len(parts) == 5
        hex_str = r.receipt_id.replace("-", "")
        assert int(hex_str[12], 16) == 7  # version nibble

    def test_timestamp_generated(self):
        r = _base_builder().build(Chain(seq=1))
        assert r.timestamp_wall.endswith("Z")
        assert "T" in r.timestamp_wall

    def test_explicit_id_and_timestamp(self):
        r = (
            _base_builder()
            .receipt_id("custom-id")
            .timestamp_wall("2026-02-18T00:00:00.000Z")
            .build(Chain(seq=1))
        )
        assert r.receipt_id == "custom-id"
        assert r.timestamp_wall == "2026-02-18T00:00:00.000Z"

    def test_with_execution(self):
        r = (
            _base_builder()
            .execution(
                ExecutionStatus.SUCCESS,
                side_effects=["fs:read"],
                effects_confidence=EffectsConfidence.COARSE,
                duration_ms=42,
                sanitized_result={"ok": True},
            )
            .build(Chain(seq=1))
        )
        assert r.execution is not None
        assert r.execution.status == ExecutionStatus.SUCCESS
        assert r.execution.result_hash is not None
        assert len(r.execution.result_hash) == 64

    def test_with_transform(self):
        r = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.write", {"path": "/etc/config", "content": "secret"})
            .decision(
                Action.TRANSFORM, "gov.transform_applied",
                transformed_args={"path": "/etc/config", "content": "[REDACTED]"},
            )
            .provenance(PROVENANCE)
            .build(Chain(seq=1))
        )
        assert r.decision.action == Action.TRANSFORM
        assert r.decision.transformed_args_hash is not None
        assert r.decision.transformed_args_hash != r.tool.args_hash

    def test_with_ext(self):
        r = _base_builder().ext({"acme.trace": "abc"}).build(Chain(seq=1))
        assert r.ext == {"acme.trace": "abc"}
        # ext should be included in hash
        d = r.to_dict()
        assert "ext" in d

    def test_missing_actor_raises(self):
        with pytest.raises(ValueError, match="actor is required"):
            (
                ReceiptBuilder()
                .tool("fs.read", {"path": "/"})
                .decision(Action.ALLOW, "gov.passthrough")
                .provenance(PROVENANCE)
                .build(Chain(seq=1))
            )

    def test_missing_tool_raises(self):
        with pytest.raises(ValueError, match="tool.*is required"):
            (
                ReceiptBuilder()
                .actor(ACTOR)
                .decision(Action.ALLOW, "gov.passthrough")
                .provenance(PROVENANCE)
                .build(Chain(seq=1))
            )

    def test_with_policy_path(self):
        steps = [
            PolicyStep(id="scope-check", version="1.0", outcome=PolicyOutcome.PASS),
            PolicyStep(id="budget-check", version="1.0", outcome=PolicyOutcome.PASS),
        ]
        r = (
            _base_builder()
            .decision(Action.ALLOW, "gov.passthrough", policy_path=steps)
            .provenance(PROVENANCE)
            .build(Chain(seq=1))
        )
        d = r.to_dict()
        assert len(d["decision"]["policy_path"]) == 2

    def test_with_budget(self):
        r = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.read", {"path": "/"})
            .decision(
                Action.DENY, "gov.budget_exhausted",
                budget=Budget(rate_remaining=0, retries_remaining=0),
            )
            .provenance(PROVENANCE)
            .build(Chain(seq=1))
        )
        d = r.to_dict()
        assert d["decision"]["budget"]["rate_remaining"] == 0


class TestReceiptChain:

    def test_first_receipt(self):
        chain = ReceiptChain()
        c = chain.next()
        assert c.seq == 1
        assert c.parent_receipt_id is None

    def test_chain_two(self):
        chain = ReceiptChain()
        r1 = _base_builder().build(chain.next())
        chain.append(r1)
        c2 = chain.next()
        assert c2.seq == 2
        assert c2.parent_receipt_id == r1.receipt_id
        assert c2.parent_receipt_hash == r1.receipt_hash

    def test_chain_three(self):
        chain = ReceiptChain()
        r1 = _base_builder().build(chain.next())
        chain.append(r1)
        r2 = _base_builder().build(chain.next())
        chain.append(r2)
        c3 = chain.next()
        assert c3.seq == 3
        assert c3.parent_receipt_id == r2.receipt_id

    def test_seq_mismatch_raises(self):
        chain = ReceiptChain()
        r = _base_builder().build(Chain(seq=5, parent_receipt_id="x", parent_receipt_hash="y" * 64))
        with pytest.raises(ValueError, match="Expected seq 1"):
            chain.append(r)

    def test_chain_hash_integrity(self):
        """Verify that chained receipts have correct hash pointers."""
        chain = ReceiptChain()
        r1 = _base_builder().build(chain.next())
        chain.append(r1)
        r2 = _base_builder().build(chain.next())
        chain.append(r2)

        # r2's parent hash should match r1's actual hash
        assert r2.chain.parent_receipt_hash == r1.receipt_hash
        # Both hashes should verify
        assert r1.receipt_hash == compute_receipt_hash(r1.to_dict())
        assert r2.receipt_hash == compute_receipt_hash(r2.to_dict())
