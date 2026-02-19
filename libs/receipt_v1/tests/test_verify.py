# SPDX-License-Identifier: Apache-2.0
"""Tests for receipt verification."""

from __future__ import annotations

from receipt_v1.canonical import receipt_hash as compute_receipt_hash
from receipt_v1.receipt import ReceiptBuilder, ReceiptChain
from receipt_v1.types import Action, Actor, Chain, ExecutionStatus, Provenance
from receipt_v1.verify import verify, verify_chain, verify_hash, verify_structure

ACTOR = Actor(agent_id="test-agent", session_id="test-session")
PROVENANCE = Provenance(
    deployment_id="test-dep", instance_id="test-inst",
    governor_version="2.3.0",
)


def _make_receipt_dict(**overrides) -> dict:
    r = (
        ReceiptBuilder()
        .actor(ACTOR)
        .tool("fs.read", {"path": "/etc/config"})
        .decision(Action.ALLOW, "gov.passthrough")
        .provenance(PROVENANCE)
        .build(Chain(seq=1))
    )
    d = r.to_dict()
    d.update(overrides)
    return d


class TestVerifyStructure:

    def test_valid_receipt(self):
        d = _make_receipt_dict()
        result = verify_structure(d)
        assert result.valid
        assert result.ok

    def test_missing_required_field(self):
        d = _make_receipt_dict()
        del d["actor"]
        result = verify_structure(d)
        assert not result.valid
        assert any("actor" in e for e in result.errors)

    def test_invalid_version(self):
        d = _make_receipt_dict()
        d["receipt_version"] = "2.0"
        result = verify_structure(d)
        assert not result.valid

    def test_minor_version_warning(self):
        d = _make_receipt_dict()
        d["receipt_version"] = "1.1"
        result = verify_structure(d)
        assert result.valid
        assert any("1.1" in w for w in result.warnings)

    def test_invalid_hash_format(self):
        d = _make_receipt_dict()
        d["receipt_hash"] = "not-a-hash"
        result = verify_structure(d)
        assert not result.valid

    def test_invalid_reason_code(self):
        d = _make_receipt_dict()
        d["decision"]["reason_code"] = "bad format"
        result = verify_structure(d)
        assert not result.valid

    def test_unsorted_side_effects(self):
        d = _make_receipt_dict()
        d["execution"] = {
            "status": "success",
            "attempt": 1,
            "side_effects": ["fs:write", "fs:read"],  # not sorted
        }
        result = verify_structure(d)
        assert not result.valid
        assert any("sorted" in e for e in result.errors)

    def test_invalid_side_effect_format(self):
        d = _make_receipt_dict()
        d["execution"] = {
            "status": "success",
            "attempt": 1,
            "side_effects": ["BAD_FORMAT"],
        }
        result = verify_structure(d)
        assert not result.valid

    def test_secret_in_reason_human(self):
        d = _make_receipt_dict()
        d["decision"]["reason_human"] = "Failed: api_key=sk-1234567890abcdef"
        result = verify_structure(d)
        assert not result.valid
        assert any("secret" in e.lower() for e in result.errors)

    def test_empty_string_rejected(self):
        d = _make_receipt_dict()
        d["tool"]["tool_version"] = ""
        result = verify_structure(d)
        assert not result.valid

    def test_chain_seq1_with_parents(self):
        d = _make_receipt_dict()
        d["chain"]["parent_receipt_id"] = "abc"
        d["chain"]["parent_receipt_hash"] = "d" * 64
        result = verify_structure(d)
        assert not result.valid

    def test_chain_seq2_without_parents(self):
        d = _make_receipt_dict()
        d["chain"] = {"seq": 2}
        result = verify_structure(d)
        assert not result.valid


class TestVerifyHash:

    def test_valid_hash(self):
        d = _make_receipt_dict()
        result = verify_hash(d)
        assert result.valid

    def test_tampered_receipt(self):
        d = _make_receipt_dict()
        d["actor"]["agent_id"] = "evil-agent"  # tamper
        result = verify_hash(d)
        assert not result.valid
        assert any("mismatch" in e for e in result.errors)


class TestVerifyChain:

    def test_valid_chain(self):
        chain = ReceiptChain()
        r1 = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.read", {"path": "/a"})
            .decision(Action.ALLOW, "gov.passthrough")
            .provenance(PROVENANCE)
            .build(chain.next())
        )
        chain.append(r1)
        r2 = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.read", {"path": "/b"})
            .decision(Action.ALLOW, "gov.passthrough")
            .provenance(PROVENANCE)
            .build(chain.next())
        )
        chain.append(r2)

        result = verify_chain([r1.to_dict(), r2.to_dict()])
        assert result.valid

    def test_broken_parent_hash(self):
        chain = ReceiptChain()
        r1 = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.read", {"path": "/a"})
            .decision(Action.ALLOW, "gov.passthrough")
            .provenance(PROVENANCE)
            .build(chain.next())
        )
        chain.append(r1)
        r2 = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.read", {"path": "/b"})
            .decision(Action.ALLOW, "gov.passthrough")
            .provenance(PROVENANCE)
            .build(chain.next())
        )
        chain.append(r2)

        d2 = r2.to_dict()
        d2["chain"]["parent_receipt_hash"] = "0" * 64  # tamper
        result = verify_chain([r1.to_dict(), d2])
        assert not result.valid

    def test_empty_chain(self):
        result = verify_chain([])
        assert result.valid

    def test_seq_gap_warning(self):
        """Seq gap produces warning, not error."""
        chain = ReceiptChain()
        r1 = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.read", {"path": "/a"})
            .decision(Action.ALLOW, "gov.passthrough")
            .provenance(PROVENANCE)
            .build(chain.next())
        )
        chain.append(r1)
        # Skip seq 2, build seq 3 manually
        r3_chain = Chain(seq=3, parent_receipt_id=r1.receipt_id, parent_receipt_hash=r1.receipt_hash)
        r3 = (
            ReceiptBuilder()
            .actor(ACTOR)
            .tool("fs.read", {"path": "/c"})
            .decision(Action.ALLOW, "gov.passthrough")
            .provenance(PROVENANCE)
            .build(r3_chain)
        )
        result = verify_chain([r1.to_dict(), r3.to_dict()])
        # Seq gap is a warning, chain is still structurally valid (parent pointers correct)
        assert result.valid
        assert any("gap" in w.lower() for w in result.warnings)


class TestVerifyFull:

    def test_fully_valid(self):
        d = _make_receipt_dict()
        result = verify(d)
        assert result.ok

    def test_structure_failure_short_circuits(self):
        result = verify({"receipt_version": "1.0"})
        assert not result.valid
