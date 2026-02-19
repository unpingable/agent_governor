# SPDX-License-Identifier: Apache-2.0
"""Tests for receipt_v1.store — read-side receipt store abstraction."""

import json
import os
from pathlib import Path

import pytest

from receipt_v1 import (
    Action,
    Actor,
    AuthContext,
    Chain,
    Decision,
    JsonlStore,
    Provenance,
    Receipt,
    ReceiptBuilder,
    ReceiptChain,
    ReceiptStore,
)
from receipt_v1.sinks import FileSink


def _make_receipt(
    chain: ReceiptChain,
    *,
    session_id: str = "s1",
    tool_id: str = "echo",
) -> Receipt:
    """Build a minimal valid receipt."""
    return (
        ReceiptBuilder()
        .actor(Actor(agent_id="test", session_id=session_id, auth_context=AuthContext.STDIO))
        .tool(tool_id, {"text": "hi"}, call_id=str(chain.seq + 1))
        .decision(Action.ALLOW, "gov.policy_allow")
        .provenance(Provenance(
            deployment_id="test", instance_id="test-1", governor_version="0.1.0"))
        .build(chain.next())
    )


def _write_receipts(path: Path, receipts: list[Receipt]) -> None:
    """Write receipts to JSONL file."""
    sink = FileSink(path, fsync=False)
    for r in receipts:
        sink.write(r)


# ── Protocol conformance ──────────────────────────────────────────


class TestProtocol:
    def test_jsonl_store_satisfies_protocol(self):
        """JsonlStore satisfies the ReceiptStore protocol."""
        store: ReceiptStore = JsonlStore("/tmp/fake.jsonl")
        # If this compiles and runs, the protocol is satisfied
        assert hasattr(store, "iter_receipts")
        assert hasattr(store, "get_receipt")
        assert hasattr(store, "verify_chain")


# ── Single-file basics ────────────────────────────────────────────


class TestSingleFile:
    def test_empty_store(self, tmp_path):
        """Empty / nonexistent file returns no receipts."""
        store = JsonlStore(tmp_path / "nonexistent.jsonl")
        assert list(store.iter_receipts()) == []
        assert store.get_receipt("anything") is None

    def test_iter_receipts_newest_first(self, tmp_path):
        """Receipts are returned newest first."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for _ in range(5):
            r = _make_receipt(chain)
            chain.append(r)
            receipts.append(r)
        _write_receipts(path, receipts)

        store = JsonlStore(path)
        result = list(store.iter_receipts())
        assert len(result) == 5
        # Newest first: seq should be 5, 4, 3, 2, 1
        seqs = [r.chain.seq for r in result]
        assert seqs == [5, 4, 3, 2, 1]

    def test_get_receipt_by_id(self, tmp_path):
        """Can retrieve a specific receipt by ID."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for _ in range(3):
            r = _make_receipt(chain)
            chain.append(r)
            receipts.append(r)
        _write_receipts(path, receipts)

        store = JsonlStore(path)
        target = receipts[1]
        found = store.get_receipt(target.receipt_id)
        assert found is not None
        assert found.receipt_id == target.receipt_id
        assert found.chain.seq == target.chain.seq

    def test_get_receipt_not_found(self, tmp_path):
        """Returns None for unknown receipt ID."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        r = _make_receipt(chain)
        chain.append(r)
        _write_receipts(path, [r])

        store = JsonlStore(path)
        assert store.get_receipt("nonexistent-id") is None

    def test_verify_chain_valid(self, tmp_path):
        """Valid chain verifies successfully."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for _ in range(4):
            r = _make_receipt(chain)
            chain.append(r)
            receipts.append(r)
        _write_receipts(path, receipts)

        store = JsonlStore(path)
        result = store.verify_chain()
        assert result.ok, f"Chain verification failed: {result.errors}"

    def test_verify_chain_empty(self, tmp_path):
        """Empty store verifies successfully (trivially)."""
        store = JsonlStore(tmp_path / "empty.jsonl")
        result = store.verify_chain()
        assert result.ok


# ── Filtering ──────────────────────────────────────────────────────


class TestFiltering:
    def test_filter_by_session_id(self, tmp_path):
        """iter_receipts filters by session_id."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for i in range(4):
            sid = "session-a" if i % 2 == 0 else "session-b"
            r = _make_receipt(chain, session_id=sid)
            chain.append(r)
            receipts.append(r)
        _write_receipts(path, receipts)

        store = JsonlStore(path)
        a_receipts = list(store.iter_receipts(session_id="session-a"))
        b_receipts = list(store.iter_receipts(session_id="session-b"))
        assert len(a_receipts) == 2
        assert len(b_receipts) == 2
        assert all(r.actor.session_id == "session-a" for r in a_receipts)
        assert all(r.actor.session_id == "session-b" for r in b_receipts)

    def test_filter_by_limit(self, tmp_path):
        """iter_receipts respects limit."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for _ in range(10):
            r = _make_receipt(chain)
            chain.append(r)
            receipts.append(r)
        _write_receipts(path, receipts)

        store = JsonlStore(path)
        result = list(store.iter_receipts(limit=3))
        assert len(result) == 3
        # Newest first
        assert result[0].chain.seq == 10

    def test_filter_by_since(self, tmp_path):
        """iter_receipts filters by since timestamp."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for _ in range(3):
            r = _make_receipt(chain)
            chain.append(r)
            receipts.append(r)
        _write_receipts(path, receipts)

        store = JsonlStore(path)
        # Use a far-future timestamp to get nothing
        result = list(store.iter_receipts(since="2099-01-01T00:00:00Z"))
        assert len(result) == 0

        # Use a far-past timestamp to get everything
        result = list(store.iter_receipts(since="2000-01-01T00:00:00Z"))
        assert len(result) == 3

    def test_verify_chain_by_session(self, tmp_path):
        """verify_chain filters by session_id.

        When sessions have independent chains, per-session verification
        should work. When receipts share a single chain but different
        sessions, per-session filtering will show gaps/mismatches — that's
        correct behavior (the chain was interleaved).
        """
        path = tmp_path / "receipts.jsonl"

        # Build two independent chains (separate sessions, separate chains)
        chain_a = ReceiptChain()
        chain_b = ReceiptChain()
        all_receipts: list[Receipt] = []

        for _ in range(3):
            r = _make_receipt(chain_a, session_id="session-a")
            chain_a.append(r)
            all_receipts.append(r)

        for _ in range(3):
            r = _make_receipt(chain_b, session_id="session-b")
            chain_b.append(r)
            all_receipts.append(r)

        _write_receipts(path, all_receipts)

        store = JsonlStore(path)
        # Each session's chain should verify independently
        result_a = store.verify_chain(session_id="session-a")
        assert result_a.ok, f"Session-a chain failed: {result_a.errors}"

        result_b = store.verify_chain(session_id="session-b")
        assert result_b.ok, f"Session-b chain failed: {result_b.errors}"


# ── Rotation handling ─────────────────────────────────────────────


class TestRotation:
    def _write_rotated(self, base_path: Path, file_receipts: dict[str, list[Receipt]]):
        """Write receipts to base file and rotated files.

        file_receipts: {"": [r1,r2], ".1": [r3,r4], ".2": [r5,r6]}
        where "" is the current file, ".1" is newest rotated, etc.
        """
        for suffix, receipts in file_receipts.items():
            if suffix == "":
                p = base_path
            else:
                p = base_path.with_name(base_path.name + suffix)
            sink = FileSink(p, fsync=False)
            for r in receipts:
                sink.write(r)

    def test_reads_rotated_files(self, tmp_path):
        """Store reads across base + rotated files."""
        base = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()

        # Oldest receipts in .2
        old = []
        for _ in range(2):
            r = _make_receipt(chain)
            chain.append(r)
            old.append(r)

        # Middle receipts in .1
        mid = []
        for _ in range(2):
            r = _make_receipt(chain)
            chain.append(r)
            mid.append(r)

        # Newest receipts in current file
        new = []
        for _ in range(2):
            r = _make_receipt(chain)
            chain.append(r)
            new.append(r)

        self._write_rotated(base, {".2": old, ".1": mid, "": new})

        store = JsonlStore(base)
        result = list(store.iter_receipts())
        assert len(result) == 6
        # Newest first: seq 6, 5, 4, 3, 2, 1
        seqs = [r.chain.seq for r in result]
        assert seqs == [6, 5, 4, 3, 2, 1]

    def test_verify_chain_across_rotated(self, tmp_path):
        """Chain verification works across rotated files."""
        base = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()

        old = []
        for _ in range(3):
            r = _make_receipt(chain)
            chain.append(r)
            old.append(r)

        new = []
        for _ in range(3):
            r = _make_receipt(chain)
            chain.append(r)
            new.append(r)

        self._write_rotated(base, {".1": old, "": new})

        store = JsonlStore(base)
        result = store.verify_chain()
        assert result.ok, f"Chain verification failed: {result.errors}"

    def test_get_receipt_from_rotated(self, tmp_path):
        """Can find a receipt in a rotated file."""
        base = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()

        old = []
        for _ in range(2):
            r = _make_receipt(chain)
            chain.append(r)
            old.append(r)

        new = []
        for _ in range(2):
            r = _make_receipt(chain)
            chain.append(r)
            new.append(r)

        self._write_rotated(base, {".1": old, "": new})

        store = JsonlStore(base)
        # Find a receipt from the rotated file
        target = old[0]
        found = store.get_receipt(target.receipt_id)
        assert found is not None
        assert found.receipt_id == target.receipt_id

    def test_limit_across_rotated(self, tmp_path):
        """Limit works correctly across rotated files."""
        base = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()

        old = []
        for _ in range(5):
            r = _make_receipt(chain)
            chain.append(r)
            old.append(r)

        new = []
        for _ in range(5):
            r = _make_receipt(chain)
            chain.append(r)
            new.append(r)

        self._write_rotated(base, {".1": old, "": new})

        store = JsonlStore(base)
        result = list(store.iter_receipts(limit=3))
        assert len(result) == 3
        # Should get the 3 newest (seq 10, 9, 8)
        seqs = [r.chain.seq for r in result]
        assert seqs == [10, 9, 8]

    def test_no_rotated_files(self, tmp_path):
        """Works fine when there are no rotated files."""
        base = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        r = _make_receipt(chain)
        chain.append(r)
        _write_receipts(base, [r])

        store = JsonlStore(base)
        result = list(store.iter_receipts())
        assert len(result) == 1

    def test_only_rotated_no_current(self, tmp_path):
        """Works when current file doesn't exist but rotated do."""
        base = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for _ in range(3):
            r = _make_receipt(chain)
            chain.append(r)
            receipts.append(r)

        # Write only to .1 (no current file)
        rotated = base.with_name(base.name + ".1")
        sink = FileSink(rotated, fsync=False)
        for r in receipts:
            sink.write(r)

        store = JsonlStore(base)
        result = list(store.iter_receipts())
        assert len(result) == 3


# ── Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_malformed_line_skipped(self, tmp_path):
        """Malformed JSON lines are skipped gracefully."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        r = _make_receipt(chain)
        chain.append(r)
        _write_receipts(path, [r])

        # Append a garbage line
        with open(path, "a") as f:
            f.write("this is not json\n")

        store = JsonlStore(path)
        # Should get the valid receipt, skip the garbage
        result = list(store.iter_receipts())
        assert len(result) == 1

    def test_path_property(self, tmp_path):
        """Store exposes its path."""
        path = tmp_path / "receipts.jsonl"
        store = JsonlStore(path)
        assert store.path == path

    def test_combined_filters(self, tmp_path):
        """Multiple filters compose correctly."""
        path = tmp_path / "receipts.jsonl"
        chain = ReceiptChain()
        receipts = []
        for i in range(6):
            sid = "s1" if i < 3 else "s2"
            r = _make_receipt(chain, session_id=sid)
            chain.append(r)
            receipts.append(r)
        _write_receipts(path, receipts)

        store = JsonlStore(path)
        result = list(store.iter_receipts(session_id="s1", limit=2))
        assert len(result) == 2
        assert all(r.actor.session_id == "s1" for r in result)
