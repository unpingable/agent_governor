# SPDX-License-Identifier: Apache-2.0
"""Tests for receipt sinks."""

from __future__ import annotations

import json
from pathlib import Path

from receipt_v1.receipt import ReceiptBuilder, ReceiptChain
from receipt_v1.sinks import FileSink, StdoutSink
from receipt_v1.types import Action, Actor, Chain, Provenance

ACTOR = Actor(agent_id="test-agent", session_id="test-session")
PROVENANCE = Provenance(
    deployment_id="test-dep", instance_id="test-inst",
    governor_version="2.3.0",
)


def _make_receipt(seq: int = 1, chain_obj: Chain | None = None):
    if chain_obj is None:
        chain_obj = Chain(seq=seq) if seq == 1 else None
    return (
        ReceiptBuilder()
        .actor(ACTOR)
        .tool("fs.read", {"path": "/etc/config"})
        .decision(Action.ALLOW, "gov.passthrough")
        .provenance(PROVENANCE)
        .build(chain_obj or Chain(seq=1))
    )


class TestFileSink:

    def test_write_and_read(self, tmp_path: Path):
        sink = FileSink(tmp_path / "receipts.jsonl", fsync=False)
        r = _make_receipt()
        sink.write(r)
        records = sink.read_all()
        assert len(records) == 1
        assert records[0]["receipt_id"] == r.receipt_id

    def test_append_multiple(self, tmp_path: Path):
        sink = FileSink(tmp_path / "receipts.jsonl", fsync=False)
        chain = ReceiptChain()
        r1 = _make_receipt(chain_obj=chain.next())
        chain.append(r1)
        sink.write(r1)
        r2 = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.write", {"path": "/tmp/out"})
            .decision(Action.ALLOW, "gov.passthrough")
            .provenance(PROVENANCE)
            .build(chain.next())
        )
        chain.append(r2)
        sink.write(r2)
        records = sink.read_all()
        assert len(records) == 2
        assert records[0]["chain"]["seq"] == 1
        assert records[1]["chain"]["seq"] == 2

    def test_creates_parent_dirs(self, tmp_path: Path):
        sink = FileSink(tmp_path / "deep" / "path" / "receipts.jsonl", fsync=False)
        r = _make_receipt()
        sink.write(r)
        assert sink.path.exists()

    def test_read_empty(self, tmp_path: Path):
        sink = FileSink(tmp_path / "nonexistent.jsonl", fsync=False)
        assert sink.read_all() == []

    def test_jsonl_format(self, tmp_path: Path):
        """Each receipt is exactly one line of valid JSON."""
        sink = FileSink(tmp_path / "receipts.jsonl", fsync=False)
        r = _make_receipt()
        sink.write(r)
        text = sink.path.read_text()
        lines = text.strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert "receipt_id" in parsed


class TestStdoutSink:

    def test_write(self, capsys):
        sink = StdoutSink()
        r = _make_receipt()
        sink.write(r)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed["receipt_id"] == r.receipt_id
