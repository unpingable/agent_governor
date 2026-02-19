# SPDX-License-Identifier: Apache-2.0
"""Tests for receipt_v1 bridge (dual-emit alongside gate_receipt)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from governor.receipt_v1_bridge import (
    BridgeContext,
    ReceiptV1Bridge,
    _ChainTracker,
    _VERDICT_MAP,
)

from receipt_v1.types import Receipt
from receipt_v1.verify import verify, verify_chain


@pytest.fixture
def gov_dir(tmp_path):
    """Create a temporary governor directory."""
    d = tmp_path / ".governor"
    d.mkdir()
    return d


@pytest.fixture
def bridge(gov_dir):
    """Create an enabled bridge with fsync=False for speed."""
    return ReceiptV1Bridge(
        gov_dir,
        enabled=True,
        deployment_id="test-dep",
        instance_id="test-inst",
        fsync=False,
    )


@pytest.fixture
def disabled_bridge(gov_dir):
    """Create a disabled bridge."""
    return ReceiptV1Bridge(gov_dir, enabled=False)


def _read_receipts(gov_dir: Path) -> list[dict]:
    """Read all receipt_v1 records from the JSONL file."""
    path = gov_dir / "receipts" / "receipt_v1.jsonl"
    if not path.exists():
        return []
    receipts = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            receipts.append(json.loads(line))
    return receipts


# =============================================================================
# Toggle
# =============================================================================


class TestToggle:

    def test_disabled_by_default(self, gov_dir):
        b = ReceiptV1Bridge(gov_dir)
        assert not b.enabled

    def test_enabled_by_arg(self, gov_dir):
        b = ReceiptV1Bridge(gov_dir, enabled=True)
        assert b.enabled

    def test_enabled_by_env(self, gov_dir, monkeypatch):
        monkeypatch.setenv("GOV_RECEIPT_V1", "1")
        b = ReceiptV1Bridge(gov_dir)
        assert b.enabled

    def test_env_not_1_means_disabled(self, gov_dir, monkeypatch):
        monkeypatch.setenv("GOV_RECEIPT_V1", "yes")
        b = ReceiptV1Bridge(gov_dir)
        assert not b.enabled

    def test_disabled_emits_nothing(self, disabled_bridge, gov_dir):
        result = disabled_bridge.emit(BridgeContext(verdict="pass"))
        assert result is None
        assert not _read_receipts(gov_dir)


# =============================================================================
# Basic emission
# =============================================================================


class TestBasicEmission:

    def test_emit_pass(self, bridge, gov_dir):
        rid = bridge.emit(BridgeContext(
            agent_id="claude",
            session_id="sess-1",
            gate="evidence_gate",
            verdict="pass",
        ))
        assert rid is not None
        receipts = _read_receipts(gov_dir)
        assert len(receipts) == 1
        r = receipts[0]
        assert r["decision"]["action"] == "allow"
        assert r["decision"]["reason_code"] == "gov.passthrough"
        assert r["actor"]["agent_id"] == "claude"
        assert r["actor"]["session_id"] == "sess-1"
        assert r["chain"]["seq"] == 1

    def test_emit_block(self, bridge, gov_dir):
        rid = bridge.emit(BridgeContext(
            agent_id="claude",
            session_id="sess-1",
            gate="evidence_gate",
            verdict="block",
            blocking_reasons=["HARD claim lacks evidence"],
        ))
        assert rid is not None
        receipts = _read_receipts(gov_dir)
        r = receipts[0]
        assert r["decision"]["action"] == "deny"
        assert r["decision"]["reason_code"] == "gov.blocked"
        assert "HARD claim" in r["decision"]["reason_human"]
        # deny should NOT have execution
        assert "execution" not in r

    def test_emit_warn(self, bridge, gov_dir):
        rid = bridge.emit(BridgeContext(verdict="warn"))
        receipts = _read_receipts(gov_dir)
        r = receipts[0]
        assert r["decision"]["action"] == "allow"
        assert r["decision"]["reason_code"] == "gov.warn"

    def test_all_emitted_receipts_verify(self, bridge, gov_dir):
        """Every receipt the bridge emits must pass verify()."""
        for verdict in ("pass", "warn", "block"):
            bridge.emit(BridgeContext(
                agent_id="claude",
                session_id=f"sess-{verdict}",
                gate="evidence_gate",
                verdict=verdict,
            ))

        for d in _read_receipts(gov_dir):
            result = verify(d)
            assert result.ok, f"verify failed for {d.get('receipt_id', '?')}: {result.errors}"


# =============================================================================
# Chain integrity
# =============================================================================


class TestChainIntegrity:

    def test_chain_across_two_calls(self, bridge, gov_dir):
        """Second receipt links to first via parent pointers."""
        bridge.emit(BridgeContext(session_id="s1", verdict="pass"))
        bridge.emit(BridgeContext(session_id="s1", verdict="block"))

        receipts = _read_receipts(gov_dir)
        assert len(receipts) == 2

        r1, r2 = receipts
        assert r1["chain"]["seq"] == 1
        assert r2["chain"]["seq"] == 2
        assert r2["chain"]["parent_receipt_id"] == r1["receipt_id"]
        assert r2["chain"]["parent_receipt_hash"] == r1["receipt_hash"]

    def test_chain_verify_passes(self, bridge, gov_dir):
        """Three-receipt chain passes verify_chain()."""
        for _ in range(3):
            bridge.emit(BridgeContext(session_id="s1", verdict="pass"))

        receipts = _read_receipts(gov_dir)
        result = verify_chain(receipts)
        assert result.ok, f"chain verify failed: {result.errors}"

    def test_separate_sessions_independent_chains(self, bridge, gov_dir):
        """Different session_ids get independent chain sequences."""
        bridge.emit(BridgeContext(session_id="a", verdict="pass"))
        bridge.emit(BridgeContext(session_id="b", verdict="pass"))
        bridge.emit(BridgeContext(session_id="a", verdict="block"))

        receipts = _read_receipts(gov_dir)
        assert len(receipts) == 3

        # Session A: seq 1, 2
        a_receipts = [r for r in receipts if r["actor"]["session_id"] == "a"]
        assert a_receipts[0]["chain"]["seq"] == 1
        assert a_receipts[1]["chain"]["seq"] == 2
        assert a_receipts[1]["chain"]["parent_receipt_id"] == a_receipts[0]["receipt_id"]

        # Session B: seq 1
        b_receipts = [r for r in receipts if r["actor"]["session_id"] == "b"]
        assert b_receipts[0]["chain"]["seq"] == 1
        assert "parent_receipt_id" not in b_receipts[0]["chain"]


# =============================================================================
# Chain tracker LRU
# =============================================================================


class TestChainTracker:

    def test_lru_eviction(self):
        tracker = _ChainTracker(max_sessions=2)
        tracker.advance("a", "id-a", "hash-a")
        tracker.advance("b", "id-b", "hash-b")
        tracker.advance("c", "id-c", "hash-c")  # evicts "a"

        assert tracker.get("a") is None
        assert tracker.get("b") is not None
        assert tracker.get("c") is not None

    def test_access_refreshes_lru(self):
        tracker = _ChainTracker(max_sessions=2)
        tracker.advance("a", "id-a", "hash-a")
        tracker.advance("b", "id-b", "hash-b")
        # Touch "a" to refresh it
        tracker.get("a")
        tracker.advance("c", "id-c", "hash-c")  # evicts "b" (oldest untouched)

        assert tracker.get("a") is not None
        assert tracker.get("b") is None
        assert tracker.get("c") is not None

    def test_evicted_session_starts_new_chain(self, bridge, gov_dir):
        """After LRU eviction, session starts fresh at seq=1."""
        small_bridge = ReceiptV1Bridge(
            gov_dir, enabled=True, max_sessions=1, fsync=False,
            instance_id="test-inst", deployment_id="test-dep",
        )
        small_bridge.emit(BridgeContext(session_id="a", verdict="pass"))
        small_bridge.emit(BridgeContext(session_id="b", verdict="pass"))  # evicts "a"
        small_bridge.emit(BridgeContext(session_id="a", verdict="pass"))  # fresh seq=1

        receipts = _read_receipts(gov_dir)
        a_receipts = [r for r in receipts if r["actor"]["session_id"] == "a"]
        # Both should be seq=1 (second one is a new chain)
        assert a_receipts[0]["chain"]["seq"] == 1
        assert a_receipts[1]["chain"]["seq"] == 1

    def test_evicted_session_stamped_with_chain_reset(self, gov_dir):
        """Eviction stamps ext.gov.chain_reset='lru_evict' on new chain."""
        small_bridge = ReceiptV1Bridge(
            gov_dir, enabled=True, max_sessions=1, fsync=False,
            instance_id="test-inst", deployment_id="test-dep",
        )
        small_bridge.emit(BridgeContext(session_id="a", verdict="pass"))
        small_bridge.emit(BridgeContext(session_id="b", verdict="pass"))  # evicts "a"
        small_bridge.emit(BridgeContext(session_id="a", verdict="pass"))  # reset

        receipts = _read_receipts(gov_dir)
        a_receipts = [r for r in receipts if r["actor"]["session_id"] == "a"]
        # First receipt: no chain_reset
        assert "ext" not in a_receipts[0] or "gov.chain_reset" not in a_receipts[0].get("ext", {})
        # Second receipt (after eviction): chain_reset stamped
        assert a_receipts[1]["ext"]["gov.chain_reset"] == "lru_evict"

    def test_chain_reset_cleared_after_first_receipt(self, gov_dir):
        """chain_reset only appears on the first receipt after eviction."""
        small_bridge = ReceiptV1Bridge(
            gov_dir, enabled=True, max_sessions=1, fsync=False,
            instance_id="test-inst", deployment_id="test-dep",
        )
        small_bridge.emit(BridgeContext(session_id="a", verdict="pass"))
        small_bridge.emit(BridgeContext(session_id="b", verdict="pass"))  # evicts "a"
        small_bridge.emit(BridgeContext(session_id="a", verdict="pass"))  # reset
        small_bridge.emit(BridgeContext(session_id="a", verdict="pass"))  # second in new chain

        receipts = _read_receipts(gov_dir)
        a_receipts = [r for r in receipts if r["actor"]["session_id"] == "a"]
        assert len(a_receipts) == 3
        # Only the first-after-eviction has chain_reset
        assert a_receipts[1]["ext"]["gov.chain_reset"] == "lru_evict"
        # Third receipt in session: no chain_reset
        assert "ext" not in a_receipts[2] or "gov.chain_reset" not in a_receipts[2].get("ext", {})


# =============================================================================
# Ext correlation
# =============================================================================


class TestExtCorrelation:

    def test_legacy_receipt_id_in_ext(self, bridge, gov_dir):
        bridge.emit(BridgeContext(
            verdict="pass",
            legacy_receipt_id="abc123def456",
        ))
        receipts = _read_receipts(gov_dir)
        assert receipts[0]["ext"]["gov.legacy_receipt_id"] == "abc123def456"

    def test_evidence_and_policy_hash_in_ext(self, bridge, gov_dir):
        bridge.emit(BridgeContext(
            verdict="pass",
            evidence_hash="e" * 64,
            policy_hash="p" * 64,
        ))
        r = _read_receipts(gov_dir)[0]
        assert r["ext"]["gov.evidence_hash"] == "e" * 64
        assert r["ext"]["gov.policy_hash"] == "p" * 64

    def test_no_ext_when_no_legacy_data(self, bridge, gov_dir):
        bridge.emit(BridgeContext(verdict="pass"))
        r = _read_receipts(gov_dir)[0]
        assert "ext" not in r  # omitted, not empty


# =============================================================================
# Field mapping
# =============================================================================


class TestFieldMapping:

    def test_tool_id_from_gate(self, bridge, gov_dir):
        bridge.emit(BridgeContext(gate="pre_commit", verdict="pass"))
        r = _read_receipts(gov_dir)[0]
        assert r["tool"]["tool_id"] == "gov.pre_commit"

    def test_tool_id_from_wrapper(self, bridge, gov_dir):
        bridge.emit(BridgeContext(gate="wrapper", verdict="block"))
        r = _read_receipts(gov_dir)[0]
        assert r["tool"]["tool_id"] == "gov.wrapper"

    def test_provenance_fields(self, bridge, gov_dir):
        bridge.emit(BridgeContext(verdict="pass"))
        r = _read_receipts(gov_dir)[0]
        assert r["provenance"]["deployment_id"] == "test-dep"
        assert r["provenance"]["instance_id"] == "test-inst"
        assert "governor_version" in r["provenance"]

    def test_receipt_version_is_1_0(self, bridge, gov_dir):
        bridge.emit(BridgeContext(verdict="pass"))
        r = _read_receipts(gov_dir)[0]
        assert r["receipt_version"] == "1.0"

    def test_timestamp_wall_utc(self, bridge, gov_dir):
        bridge.emit(BridgeContext(verdict="pass"))
        r = _read_receipts(gov_dir)[0]
        assert r["timestamp_wall"].endswith("Z")

    def test_auth_context_mapped(self, bridge, gov_dir):
        bridge.emit(BridgeContext(verdict="pass", auth_context="stdio"))
        r = _read_receipts(gov_dir)[0]
        assert r["actor"]["auth_context"] == "stdio"

    def test_invalid_auth_context_ignored(self, bridge, gov_dir):
        bridge.emit(BridgeContext(verdict="pass", auth_context="bogus"))
        r = _read_receipts(gov_dir)[0]
        assert "auth_context" not in r["actor"]

    def test_args_summary_mapped(self, bridge, gov_dir):
        bridge.emit(BridgeContext(
            verdict="pass",
            args_summary="Read /etc/config",
        ))
        r = _read_receipts(gov_dir)[0]
        assert r["tool"]["args_summary"] == "Read /etc/config"

    def test_call_id_mapped(self, bridge, gov_dir):
        bridge.emit(BridgeContext(verdict="pass", call_id="call-42"))
        r = _read_receipts(gov_dir)[0]
        assert r["tool"]["call_id"] == "call-42"


# =============================================================================
# Execution field
# =============================================================================


class TestExecution:

    def test_allow_with_execution(self, bridge, gov_dir):
        bridge.emit(BridgeContext(
            verdict="pass",
            execution_status="success",
            duration_ms=42,
            side_effects=["fs:read"],
        ))
        r = _read_receipts(gov_dir)[0]
        assert r["execution"]["status"] == "success"
        assert r["execution"]["duration_ms"] == 42
        assert r["execution"]["side_effects"] == ["fs:read"]

    def test_deny_no_execution(self, bridge, gov_dir):
        bridge.emit(BridgeContext(
            verdict="block",
            execution_status="failure",  # should be ignored for deny
        ))
        r = _read_receipts(gov_dir)[0]
        assert "execution" not in r

    def test_failure_with_error(self, bridge, gov_dir):
        bridge.emit(BridgeContext(
            verdict="pass",
            execution_status="failure",
            error="ENOENT: /etc/missing",
            attempt=2,
        ))
        r = _read_receipts(gov_dir)[0]
        assert r["execution"]["status"] == "failure"
        assert r["execution"]["error"] == "ENOENT: /etc/missing"
        assert r["execution"]["attempt"] == 2

    def test_retry_stable_call_id(self, bridge, gov_dir):
        """Same call_id across retries proves they're the same tool call."""
        for attempt in (1, 2):
            bridge.emit(BridgeContext(
                session_id="s1",
                verdict="pass",
                call_id="call-retry-test",
                execution_status="failure" if attempt == 1 else "success",
                attempt=attempt,
            ))

        receipts = _read_receipts(gov_dir)
        assert receipts[0]["tool"]["call_id"] == "call-retry-test"
        assert receipts[1]["tool"]["call_id"] == "call-retry-test"
        assert receipts[0]["execution"]["attempt"] == 1
        assert receipts[1]["execution"]["attempt"] == 2


# =============================================================================
# Fail-open / fail-closed
# =============================================================================


class TestFailBehavior:

    def test_fail_open_by_default(self, gov_dir):
        """Bridge errors are swallowed in fail-open mode."""
        b = ReceiptV1Bridge(gov_dir, enabled=True, fsync=False)
        # Make the sink path unwritable
        (gov_dir / "receipts").mkdir(parents=True, exist_ok=True)
        sink_path = gov_dir / "receipts" / "receipt_v1.jsonl"
        sink_path.touch()
        sink_path.chmod(0o000)

        try:
            result = b.emit(BridgeContext(verdict="pass"))
            # Should return None (failure swallowed), not raise
            assert result is None
        finally:
            sink_path.chmod(0o644)

    def test_fail_closed_raises(self, gov_dir):
        """Bridge errors raise in fail-closed mode."""
        b = ReceiptV1Bridge(gov_dir, enabled=True, fail_closed=True, fsync=False)
        (gov_dir / "receipts").mkdir(parents=True, exist_ok=True)
        sink_path = gov_dir / "receipts" / "receipt_v1.jsonl"
        sink_path.touch()
        sink_path.chmod(0o000)

        try:
            with pytest.raises(Exception):
                b.emit(BridgeContext(verdict="pass"))
        finally:
            sink_path.chmod(0o644)

    def test_fail_open_log_includes_context(self, gov_dir, caplog):
        """Fail-open warning log includes session_id, call_id, gate."""
        import logging
        b = ReceiptV1Bridge(gov_dir, enabled=True, fsync=False)
        (gov_dir / "receipts").mkdir(parents=True, exist_ok=True)
        sink_path = gov_dir / "receipts" / "receipt_v1.jsonl"
        sink_path.touch()
        sink_path.chmod(0o000)

        try:
            with caplog.at_level(logging.WARNING, logger="governor.receipt_v1_bridge"):
                b.emit(BridgeContext(
                    session_id="sess-ctx-test",
                    call_id="call-ctx-test",
                    gate="evidence_gate",
                    verdict="pass",
                ))
            assert "sess-ctx-test" in caplog.text
            assert "call-ctx-test" in caplog.text
            assert "evidence_gate" in caplog.text
        finally:
            sink_path.chmod(0o644)


# =============================================================================
# Verdict mapping completeness
# =============================================================================


class TestVerdictMapping:

    def test_all_verdicts_mapped(self):
        """All gate verdicts have a mapping."""
        for v in ("pass", "warn", "block"):
            assert v in _VERDICT_MAP

    def test_unknown_verdict_defaults_to_deny(self, bridge, gov_dir):
        """Unknown verdict falls back to deny/gov.unknown."""
        bridge.emit(BridgeContext(verdict="mystery"))
        r = _read_receipts(gov_dir)[0]
        assert r["decision"]["action"] == "deny"
        assert r["decision"]["reason_code"] == "gov.unknown"


# =============================================================================
# Integration: full lifecycle verify
# =============================================================================


class TestIntegration:

    def test_deny_allow_failure_retry_chain(self, bridge, gov_dir):
        """Real-ish 4-step trace: deny → allow → failure → retry success."""
        # 1. Deny (HARD claim lacks evidence)
        bridge.emit(BridgeContext(
            session_id="sess-demo",
            gate="evidence_gate",
            verdict="block",
            blocking_reasons=["HARD claim lacks evidence: 'tests pass'"],
            legacy_receipt_id="legacy-001",
        ))

        # 2. Allow (passthrough)
        bridge.emit(BridgeContext(
            session_id="sess-demo",
            gate="evidence_gate",
            verdict="pass",
            execution_status="success",
            duration_ms=150,
            side_effects=["fs:write"],
            call_id="call-42",
            legacy_receipt_id="legacy-002",
        ))

        # 3. Allow but execution failed
        bridge.emit(BridgeContext(
            session_id="sess-demo",
            gate="evidence_gate",
            verdict="pass",
            execution_status="failure",
            error="EACCES: /etc/shadow",
            call_id="call-43",
            attempt=1,
            legacy_receipt_id="legacy-003",
        ))

        # 4. Retry of call-43, succeeds
        bridge.emit(BridgeContext(
            session_id="sess-demo",
            gate="evidence_gate",
            verdict="pass",
            execution_status="success",
            call_id="call-43",
            attempt=2,
            duration_ms=80,
            legacy_receipt_id="legacy-004",
        ))

        receipts = _read_receipts(gov_dir)
        assert len(receipts) == 4

        # All receipts individually verify
        for i, d in enumerate(receipts):
            result = verify(d)
            assert result.ok, f"receipt [{i}] verify failed: {result.errors}"

        # Chain verifies
        result = verify_chain(receipts)
        assert result.ok, f"chain verify failed: {result.errors}"

        # Check structure
        assert receipts[0]["decision"]["action"] == "deny"
        assert receipts[1]["decision"]["action"] == "allow"
        assert receipts[1]["execution"]["status"] == "success"
        assert receipts[2]["execution"]["status"] == "failure"
        assert receipts[3]["execution"]["status"] == "success"
        assert receipts[3]["execution"]["attempt"] == 2

        # Chain seq
        for i, r in enumerate(receipts):
            assert r["chain"]["seq"] == i + 1

        # Legacy correlation
        assert receipts[0]["ext"]["gov.legacy_receipt_id"] == "legacy-001"
        assert receipts[3]["ext"]["gov.legacy_receipt_id"] == "legacy-004"
