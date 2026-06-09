# SPDX-License-Identifier: Apache-2.0
"""Tests for gate_receipt module — content-addressed decision receipts."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from governor.gate_receipt import (
    RECEIPT_SCHEMA_VERSION,
    ROLE_MEASUREMENT,
    ROLE_RESET,
    UNSETTLED_AUTHORITY,
    UNSETTLED_EVIDENCE_SUFFICIENCY,
    UNSETTLED_FRESHNESS,
    VALID_NON_DISCHARGE_KINDS,
    VALID_RECEIPT_ROLES,
    EvidenceStore,
    GateReceipt,
    GateReceiptSystem,
    NonDischargeClaim,
    ReceiptStore,
    canonical_json,
    content_hash,
    create_receipt,
    policy_hash,
    subject_hash,
    _compute_receipt_id,
)


# =============================================================================
# Canonicalization
# =============================================================================


class TestCanonicalJson:
    def test_sorted_keys(self):
        a = canonical_json({"z": 1, "a": 2})
        b = canonical_json({"a": 2, "z": 1})
        assert a == b

    def test_compact_separators(self):
        result = canonical_json({"a": 1})
        assert result == b'{"a":1}'

    def test_nested_sorting(self):
        result = canonical_json({"b": {"z": 1, "a": 2}, "a": 3})
        assert result == b'{"a":3,"b":{"a":2,"z":1}}'

    def test_returns_bytes(self):
        result = canonical_json({"x": 1})
        assert isinstance(result, bytes)

    def test_ascii_safe(self):
        result = canonical_json({"emoji": "\u2603"})
        assert b"\\u2603" in result

    def test_stable_floats(self):
        """Same float → same bytes."""
        a = canonical_json({"v": 0.5})
        b = canonical_json({"v": 0.5})
        assert a == b

    def test_rejects_nan(self):
        """NaN is not valid JSON — canonical_json must reject it."""
        with pytest.raises(ValueError):
            canonical_json({"v": float("nan")})

    def test_rejects_infinity(self):
        """Infinity is not valid JSON — canonical_json must reject it."""
        with pytest.raises(ValueError):
            canonical_json({"v": float("inf")})

    def test_rejects_negative_infinity(self):
        with pytest.raises(ValueError):
            canonical_json({"v": float("-inf")})


class TestContentHash:
    def test_deterministic(self):
        assert content_hash(b"hello") == content_hash(b"hello")

    def test_different_input_different_hash(self):
        assert content_hash(b"hello") != content_hash(b"world")

    def test_returns_hex_string(self):
        h = content_hash(b"test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestSubjectHash:
    def test_kind_tag_matters(self):
        """Same bytes, different kind → different hash."""
        h1 = subject_hash("text", b"hello")
        h2 = subject_hash("diff", b"hello")
        assert h1 != h2

    def test_deterministic(self):
        h1 = subject_hash("text", b"hello")
        h2 = subject_hash("text", b"hello")
        assert h1 == h2

    def test_content_matters(self):
        h1 = subject_hash("text", b"hello")
        h2 = subject_hash("text", b"world")
        assert h1 != h2


class TestPolicyHash:
    def test_deterministic(self):
        config = {"strict": True, "custody_threshold": 0.5}
        h1 = policy_hash(config)
        h2 = policy_hash(config)
        assert h1 == h2

    def test_key_order_irrelevant(self):
        h1 = policy_hash({"a": 1, "b": 2})
        h2 = policy_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_config_different_hash(self):
        h1 = policy_hash({"strict": True})
        h2 = policy_hash({"strict": False})
        assert h1 != h2


# =============================================================================
# Receipt Identity
# =============================================================================


class TestReceiptIdentity:
    def test_content_addressed_not_event_addressed(self):
        """Same content at different times → same receipt_id."""
        r1 = create_receipt(
            gate="evidence_gate", verdict="pass",
            subject_kind="text", subject_bytes=b"hello",
            evidence_bundle={"claims": []}, gate_config={"strict": True},
            timestamp="2024-01-01T00:00:00Z",
        )
        r2 = create_receipt(
            gate="evidence_gate", verdict="pass",
            subject_kind="text", subject_bytes=b"hello",
            evidence_bundle={"claims": []}, gate_config={"strict": True},
            timestamp="2024-01-02T00:00:00Z",  # different timestamp
        )
        assert r1.receipt_id == r2.receipt_id
        assert r1.timestamp != r2.timestamp

    def test_different_subject_different_id(self):
        base = dict(gate="g", verdict="pass", subject_kind="text",
                    evidence_bundle={}, gate_config={})
        r1 = create_receipt(**base, subject_bytes=b"alpha")
        r2 = create_receipt(**base, subject_bytes=b"beta")
        assert r1.receipt_id != r2.receipt_id

    def test_different_evidence_different_id(self):
        base = dict(gate="g", verdict="pass", subject_kind="text",
                    subject_bytes=b"same", gate_config={})
        r1 = create_receipt(**base, evidence_bundle={"a": 1})
        r2 = create_receipt(**base, evidence_bundle={"a": 2})
        assert r1.receipt_id != r2.receipt_id

    def test_different_policy_different_id(self):
        base = dict(gate="g", verdict="pass", subject_kind="text",
                    subject_bytes=b"same", evidence_bundle={})
        r1 = create_receipt(**base, gate_config={"strict": True})
        r2 = create_receipt(**base, gate_config={"strict": False})
        assert r1.receipt_id != r2.receipt_id

    def test_different_gate_different_id(self):
        base = dict(verdict="pass", subject_kind="text",
                    subject_bytes=b"same", evidence_bundle={}, gate_config={})
        r1 = create_receipt(gate="evidence_gate", **base)
        r2 = create_receipt(gate="pre_commit", **base)
        assert r1.receipt_id != r2.receipt_id

    def test_verdict_not_in_id(self):
        """Verdict is NOT part of receipt_id — same check, different verdict
        should be impossible (deterministic gate), but if it happens we want
        different receipt rows, not silent dedup.

        Actually — verdict IS implicitly captured via evidence_bundle
        (blocking_reasons differ).  So same evidence + same subject + same
        policy + different verdict is structurally impossible unless evidence
        differs too.  We verify that the ID doesn't include verdict directly.
        """
        id1 = _compute_receipt_id(1, "g", "s", "e", "p")
        # The function doesn't take verdict — correct by construction
        assert len(id1) == 64

    def test_schema_version_in_id(self):
        id1 = _compute_receipt_id(1, "g", "s", "e", "p")
        id2 = _compute_receipt_id(2, "g", "s", "e", "p")
        assert id1 != id2


# =============================================================================
# GateReceipt serialization
# =============================================================================


class TestGateReceiptSerialization:
    def test_round_trip(self):
        r = create_receipt(
            gate="evidence_gate", verdict="block",
            subject_kind="text", subject_bytes=b"test output",
            evidence_bundle={"claims": [{"id": "c1"}]},
            gate_config={"strict": True},
        )
        d = r.to_dict()
        r2 = GateReceipt.from_dict(d)
        assert r == r2

    def test_to_json_parseable(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        parsed = json.loads(r.to_json())
        assert parsed["gate"] == "g"
        assert parsed["schema_version"] == RECEIPT_SCHEMA_VERSION

    def test_all_fields_present(self):
        r = create_receipt(
            gate="g", verdict="warn", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        d = r.to_dict()
        for field in ("receipt_id", "schema_version", "timestamp",
                      "gate", "verdict", "subject_hash", "evidence_hash",
                      "policy_hash", "principal_id", "tenant_id",
                      "auth_method"):
            assert field in d, f"Missing field: {field}"

    def test_frozen(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        with pytest.raises(AttributeError):
            r.gate = "other"  # type: ignore


# =============================================================================
# Principal / Tenant metadata
# =============================================================================


class TestPrincipalTenantMetadata:
    """Schema v2: principal_id, tenant_id, auth_method as no-op defaults."""

    def test_defaults(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        assert r.principal_id == "local"
        assert r.tenant_id == "default"
        assert r.auth_method == "none"

    def test_custom_values(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
            principal_id="user:alice", tenant_id="acme-corp",
            auth_method="api_key",
        )
        assert r.principal_id == "user:alice"
        assert r.tenant_id == "acme-corp"
        assert r.auth_method == "api_key"

    def test_round_trip(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
            principal_id="user:bob", tenant_id="tenant-42",
            auth_method="oauth",
        )
        d = r.to_dict()
        r2 = GateReceipt.from_dict(d)
        assert r2.principal_id == "user:bob"
        assert r2.tenant_id == "tenant-42"
        assert r2.auth_method == "oauth"

    def test_backward_compat_v1_receipt(self):
        """v1 receipts (without principal/tenant fields) deserialize with defaults."""
        v1_dict = {
            "receipt_id": "abc123",
            "schema_version": 1,
            "timestamp": "2024-01-01T00:00:00Z",
            "gate": "evidence_gate",
            "verdict": "pass",
            "subject_hash": "s",
            "evidence_hash": "e",
            "policy_hash": "p",
        }
        r = GateReceipt.from_dict(v1_dict)
        assert r.principal_id == "local"
        assert r.tenant_id == "default"
        assert r.auth_method == "none"

    def test_metadata_not_in_receipt_id(self):
        """principal_id/tenant_id do NOT affect receipt_id (metadata, not identity)."""
        base = dict(gate="g", verdict="pass", subject_kind="text",
                    subject_bytes=b"same", evidence_bundle={}, gate_config={})
        r1 = create_receipt(**base, principal_id="alice")
        r2 = create_receipt(**base, principal_id="bob")
        assert r1.receipt_id == r2.receipt_id

    def test_in_serialized_json(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        parsed = json.loads(r.to_json())
        assert parsed["principal_id"] == "local"
        assert parsed["tenant_id"] == "default"
        assert parsed["auth_method"] == "none"

    def test_schema_version_is_4(self):
        assert RECEIPT_SCHEMA_VERSION == 4

    def test_emit_passes_through(self, tmp_path):
        system = GateReceiptSystem(tmp_path)
        receipt = system.emit(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
            principal_id="user:carol", tenant_id="org-7",
            auth_method="mtls",
        )
        assert receipt.principal_id == "user:carol"
        assert receipt.tenant_id == "org-7"
        assert receipt.auth_method == "mtls"
        # Verify persisted
        found = system.receipt_store.get_by_id(receipt.receipt_id)
        assert found is not None
        assert found.principal_id == "user:carol"


# =============================================================================
# EvidenceStore
# =============================================================================


class TestEvidenceStore:
    def test_put_and_get(self, tmp_path):
        store = EvidenceStore(tmp_path)
        bundle = {"claims": [{"id": "c1", "text": "hello"}]}
        h = store.put(bundle)
        assert len(h) == 64
        retrieved = store.get(h)
        assert retrieved == bundle

    def test_dedup(self, tmp_path):
        store = EvidenceStore(tmp_path)
        bundle = {"x": 1}
        h1 = store.put(bundle)
        h2 = store.put(bundle)  # same content
        assert h1 == h2
        # Only one file should exist
        files = list((tmp_path / "evidence").rglob("*.json"))
        assert len(files) == 1

    def test_get_missing(self, tmp_path):
        store = EvidenceStore(tmp_path)
        assert store.get("nonexistent") is None

    def test_has(self, tmp_path):
        store = EvidenceStore(tmp_path)
        h = store.put({"a": 1})
        assert store.has(h) is True
        assert store.has("nonexistent") is False

    def test_key_order_dedup(self, tmp_path):
        """Different key order → same hash → same file."""
        store = EvidenceStore(tmp_path)
        h1 = store.put({"b": 2, "a": 1})
        h2 = store.put({"a": 1, "b": 2})
        assert h1 == h2

    def test_sharded_layout(self, tmp_path):
        store = EvidenceStore(tmp_path)
        h = store.put({"test": True})
        path = tmp_path / "evidence" / h[:2] / f"{h}.json"
        assert path.exists()


# =============================================================================
# ReceiptStore
# =============================================================================


class TestReceiptStore:
    def _make_receipt(self, gate="g", verdict="pass", content=b"x"):
        return create_receipt(
            gate=gate, verdict=verdict, subject_kind="text",
            subject_bytes=content, evidence_bundle={}, gate_config={},
        )

    def test_append_and_all(self, tmp_path):
        store = ReceiptStore(tmp_path)
        r = self._make_receipt()
        store.append(r)
        results = store.all()
        assert len(results) == 1
        assert results[0].receipt_id == r.receipt_id

    def test_empty_store(self, tmp_path):
        store = ReceiptStore(tmp_path)
        assert store.all() == []

    def test_query_by_gate(self, tmp_path):
        store = ReceiptStore(tmp_path)
        store.append(self._make_receipt(gate="a", content=b"1"))
        store.append(self._make_receipt(gate="b", content=b"2"))
        store.append(self._make_receipt(gate="a", content=b"3"))
        results = store.query(gate="a")
        assert len(results) == 2
        assert all(r.gate == "a" for r in results)

    def test_query_by_verdict(self, tmp_path):
        store = ReceiptStore(tmp_path)
        store.append(self._make_receipt(verdict="pass", content=b"1"))
        store.append(self._make_receipt(verdict="block", content=b"2"))
        store.append(self._make_receipt(verdict="block", content=b"3"))
        results = store.query(verdict="block")
        assert len(results) == 2

    def test_query_limit(self, tmp_path):
        store = ReceiptStore(tmp_path)
        for i in range(10):
            store.append(self._make_receipt(content=str(i).encode()))
        results = store.query(limit=3)
        assert len(results) == 3

    def test_query_newest_first(self, tmp_path):
        store = ReceiptStore(tmp_path)
        r1 = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"first", evidence_bundle={}, gate_config={},
            timestamp="2024-01-01T00:00:00Z",
        )
        r2 = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"second", evidence_bundle={}, gate_config={},
            timestamp="2024-01-02T00:00:00Z",
        )
        store.append(r1)
        store.append(r2)
        results = store.query()
        assert results[0].timestamp > results[1].timestamp

    def test_get_by_id(self, tmp_path):
        store = ReceiptStore(tmp_path)
        r = self._make_receipt()
        store.append(r)
        found = store.get_by_id(r.receipt_id)
        assert found is not None
        assert found.receipt_id == r.receipt_id

    def test_get_by_id_not_found(self, tmp_path):
        store = ReceiptStore(tmp_path)
        assert store.get_by_id("nonexistent") is None

    def test_jsonl_format(self, tmp_path):
        store = ReceiptStore(tmp_path)
        store.append(self._make_receipt(content=b"a"))
        store.append(self._make_receipt(content=b"b"))
        lines = store.path.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "receipt_id" in parsed


# =============================================================================
# GateReceiptSystem (combined)
# =============================================================================


class TestGateReceiptSystem:
    def test_emit_stores_both(self, tmp_path):
        system = GateReceiptSystem(tmp_path)
        bundle = {"claims": [{"id": "c1"}], "blocking_reasons": []}
        receipt = system.emit(
            gate="evidence_gate", verdict="pass",
            subject_kind="text", subject_bytes=b"output",
            evidence_bundle=bundle, gate_config={"strict": True},
        )
        # Receipt stored
        found = system.receipt_store.get_by_id(receipt.receipt_id)
        assert found is not None
        # Evidence stored
        evidence = system.evidence_for(receipt)
        assert evidence == bundle

    def test_query_delegates(self, tmp_path):
        system = GateReceiptSystem(tmp_path)
        system.emit(
            gate="g", verdict="block", subject_kind="text",
            subject_bytes=b"bad", evidence_bundle={"err": True},
            gate_config={},
        )
        system.emit(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"good", evidence_bundle={},
            gate_config={},
        )
        blocks = system.query(verdict="block")
        assert len(blocks) == 1
        assert blocks[0].verdict == "block"

    def test_evidence_dedup_across_receipts(self, tmp_path):
        system = GateReceiptSystem(tmp_path)
        bundle = {"same": "evidence"}
        system.emit(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"first", evidence_bundle=bundle,
            gate_config={},
        )
        system.emit(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"second", evidence_bundle=bundle,
            gate_config={},
        )
        # Same evidence hash → one blob file
        files = list((tmp_path / "evidence").rglob("*.json"))
        assert len(files) == 1


# =============================================================================
# EvidenceGate integration
# =============================================================================


class TestEvidenceGateIntegration:
    def test_check_emits_receipt(self, tmp_path):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        system = GateReceiptSystem(tmp_path)
        gate = EvidenceGate(
            config=EvidenceGateConfig(strict=False),
            receipt_system=system,
        )
        result = gate.check(
            task="test", context=".", output="This should work fine.",
        )
        receipts = system.query()
        assert len(receipts) == 1
        assert receipts[0].gate == "evidence_gate"
        assert receipts[0].verdict == "pass"

    def test_blocked_check_emits_block_receipt(self, tmp_path):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        system = GateReceiptSystem(tmp_path)
        gate = EvidenceGate(
            config=EvidenceGateConfig(strict=True),
            receipt_system=system,
        )
        result = gate.check(
            task="test", context=".",
            output="This guarantees perfect results and never fails.",
        )
        receipts = system.query(verdict="block")
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence is not None
        assert len(evidence["blocking_reasons"]) > 0

    def test_no_receipt_system_logs_suppressed(self, tmp_path):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        gate = EvidenceGate(config=EvidenceGateConfig(strict=False))
        result = gate.check(task="test", context=".", output="Hello world.")
        events = gate.get_log_events()
        suppressed = [e for e in events if e.get("event") == "receipt_suppressed"]
        assert len(suppressed) == 1
        assert suppressed[0]["reason"] == "no receipt system configured"

    def test_receipt_evidence_matches_output(self, tmp_path):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        system = GateReceiptSystem(tmp_path)
        gate = EvidenceGate(
            config=EvidenceGateConfig(strict=False),
            receipt_system=system,
        )
        gate.check(task="t", context=".", output="might improve performance")
        receipts = system.query()
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        # Evidence should contain extracted claims
        assert "claims" in evidence
        assert "warnings" in evidence

    def test_receipt_policy_hash_reflects_config(self, tmp_path):
        system = GateReceiptSystem(tmp_path)

        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        # Strict config
        gate1 = EvidenceGate(
            config=EvidenceGateConfig(strict=True),
            receipt_system=system,
        )
        gate1.check(task="t", context=".", output="safe text")

        # Permissive config
        gate2 = EvidenceGate(
            config=EvidenceGateConfig(strict=False),
            receipt_system=system,
        )
        gate2.check(task="t", context=".", output="safe text")

        receipts = system.query()
        assert len(receipts) == 2
        # Different policy → different policy_hash
        assert receipts[0].policy_hash != receipts[1].policy_hash

    def test_wrapper_with_receipt_system(self, tmp_path):
        from governor.evidence_gate import evidence_gate_wrapper

        system = GateReceiptSystem(tmp_path)

        def my_agent(task: str, context: str, **kw: object) -> str:
            return "The fix looks correct."

        wrapped = evidence_gate_wrapper(my_agent, receipt_system=system)
        result = wrapped("fix bug", "./src/")
        assert result == "The fix looks correct."

        receipts = system.query()
        assert len(receipts) == 1
        assert receipts[0].verdict == "pass"


# =============================================================================
# Schema Version Enforcement
# =============================================================================


class TestSchemaVersionEnforcement:
    """from_dict must reject future versions and handle legacy gracefully."""

    def _make_receipt_dict(self, **overrides: object) -> dict:
        base = {
            "receipt_id": "abc123",
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "gate": "evidence_gate",
            "verdict": "pass",
            "subject_hash": "a" * 64,
            "evidence_hash": "b" * 64,
            "policy_hash": "c" * 64,
        }
        base.update(overrides)
        return base

    def test_legacy_missing_schema_version(self):
        """Missing schema_version → defaults to 1, loads fine."""
        d = self._make_receipt_dict()
        del d["schema_version"]
        r = GateReceipt.from_dict(d)
        assert r.schema_version == 1

    def test_future_schema_version_rejected(self):
        """schema_version > current → ValueError."""
        d = self._make_receipt_dict(schema_version=RECEIPT_SCHEMA_VERSION + 1)
        with pytest.raises(ValueError, match="newer than supported"):
            GateReceipt.from_dict(d)

    def test_current_version_accepted(self):
        """Current schema_version loads without error."""
        d = self._make_receipt_dict(schema_version=RECEIPT_SCHEMA_VERSION)
        r = GateReceipt.from_dict(d)
        assert r.schema_version == RECEIPT_SCHEMA_VERSION

    def test_old_version_accepted(self):
        """schema_version < current loads fine (forward compat)."""
        d = self._make_receipt_dict(schema_version=1)
        r = GateReceipt.from_dict(d)
        assert r.schema_version == 1


# =============================================================================
# Receipt Role (3.x seam)
# =============================================================================


class TestReceiptRole:
    """receipt_role field — included in receipt_id, validated on create."""

    def test_default_is_measurement(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        assert r.receipt_role == ROLE_MEASUREMENT

    def test_custom_role_accepted(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
            receipt_role="reset",
        )
        assert r.receipt_role == "reset"

    def test_different_role_different_receipt_id(self):
        """Role is part of identity — same payload, different role = different id."""
        base = dict(gate="g", verdict="pass", subject_kind="text",
                    subject_bytes=b"same", evidence_bundle={}, gate_config={})
        r1 = create_receipt(**base, receipt_role="measurement")
        r2 = create_receipt(**base, receipt_role="reset")
        assert r1.receipt_id != r2.receipt_id

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="Invalid receipt_role"):
            create_receipt(
                gate="g", verdict="pass", subject_kind="text",
                subject_bytes=b"x", evidence_bundle={}, gate_config={},
                receipt_role="nonsense",
            )

    def test_serialization_round_trip(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
            receipt_role="authority",
        )
        d = r.to_dict()
        assert d["receipt_role"] == "authority"
        r2 = GateReceipt.from_dict(d)
        assert r2.receipt_role == "authority"
        assert r == r2

    def test_backwards_compat_missing_field(self):
        """Old receipts without receipt_role deserialize as 'measurement'."""
        d = {
            "receipt_id": "abc123",
            "schema_version": 2,
            "timestamp": "2026-01-01T00:00:00Z",
            "gate": "evidence_gate",
            "verdict": "pass",
            "subject_hash": "s",
            "evidence_hash": "e",
            "policy_hash": "p",
        }
        r = GateReceipt.from_dict(d)
        assert r.receipt_role == ROLE_MEASUREMENT

    def test_system_emit_accepts_role(self, tmp_path):
        system = GateReceiptSystem(tmp_path)
        receipt = system.emit(
            gate="system_reset_request", verdict="pass",
            subject_kind="reset", subject_bytes=b"regime",
            evidence_bundle={"target": "regime"}, gate_config={},
            receipt_role="reset",
        )
        assert receipt.receipt_role == "reset"
        found = system.receipt_store.get_by_id(receipt.receipt_id)
        assert found is not None
        assert found.receipt_role == "reset"

    def test_schema_version_bumped_for_role(self):
        """Schema v3: receipt_role added to identity hash. v4: unsettled added."""
        assert RECEIPT_SCHEMA_VERSION == 4


# =============================================================================
# Principal Ref (v3 placeholder)
# =============================================================================


class TestPrincipalRef:
    """principal_ref: content-addressed hash of authenticated principal."""

    def test_default_is_none(self):
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        assert r.principal_ref is None

    def test_none_survives_round_trip(self):
        """Default None survives to_dict/from_dict."""
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        d = r.to_dict()
        assert "principal_ref" not in d  # None omitted
        r2 = GateReceipt.from_dict(d)
        assert r2.principal_ref is None
        assert r == r2

    def test_populated_value_survives_round_trip(self):
        """sha256:<hex> value survives to_dict/from_dict."""
        ref = "sha256:" + "ab" * 32
        r = create_receipt(
            gate="g", verdict="pass", subject_kind="text",
            subject_bytes=b"x", evidence_bundle={}, gate_config={},
        )
        # Construct directly (create_receipt doesn't take principal_ref)
        r_with_ref = GateReceipt(
            receipt_id=r.receipt_id,
            schema_version=r.schema_version,
            timestamp=r.timestamp,
            gate=r.gate,
            verdict=r.verdict,
            subject_hash=r.subject_hash,
            evidence_hash=r.evidence_hash,
            policy_hash=r.policy_hash,
            principal_ref=ref,
        )
        d = r_with_ref.to_dict()
        assert d["principal_ref"] == ref
        r2 = GateReceipt.from_dict(d)
        assert r2.principal_ref == ref

    def test_malformed_principal_ref_rejected(self):
        """Junk principal_ref in from_dict raises ValueError."""
        d = {
            "receipt_id": "abc123",
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "timestamp": "2026-01-01T00:00:00Z",
            "gate": "g",
            "verdict": "pass",
            "subject_hash": "s",
            "evidence_hash": "e",
            "policy_hash": "p",
            "principal_ref": "not-a-valid-hash",
        }
        with pytest.raises(ValueError, match="principal_ref must match"):
            GateReceipt.from_dict(d)

    def test_principal_ref_not_in_receipt_id(self):
        """principal_ref is metadata — does NOT affect receipt_id."""
        ref = "sha256:" + "cd" * 32
        base = dict(gate="g", verdict="pass", subject_kind="text",
                    subject_bytes=b"same", evidence_bundle={}, gate_config={})
        r1 = create_receipt(**base)
        r2_dict = r1.to_dict()
        r2_dict["principal_ref"] = ref
        r2 = GateReceipt.from_dict(r2_dict)
        assert r1.receipt_id == r2.receipt_id


# =============================================================================
# Unsettled non-discharge claims (v4)
# =============================================================================
#
# Motivating witness: working/witness-2026-06-09-gate-receipt-unsettled-gap.md
# captured the v3 schema gap across 1,165 emitted receipts: zero matches for
# unsettled / discharge / unresolved / non_* in any of them. v4 closes that
# gap by adding a typed `unsettled` field that records what a verdict
# explicitly does NOT settle.


class TestNonDischargeClaim:
    """Typed non-discharge claim — closed kind enum, freeform reason."""

    def test_accepts_each_valid_kind(self):
        for kind in VALID_NON_DISCHARGE_KINDS:
            c = NonDischargeClaim(kind=kind, reason="for testing")
            assert c.kind == kind

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="Invalid non-discharge kind"):
            NonDischargeClaim(kind="misc_authority_vibes", reason="lol")

    def test_rejects_empty_string_kind(self):
        with pytest.raises(ValueError, match="Invalid non-discharge kind"):
            NonDischargeClaim(kind="", reason="forgot")

    def test_freeform_reason_does_not_participate_in_kind_validation(self):
        """Reason is prose; kind alone gates validity. Same reason text
        cannot rescue a bad kind, and reason content is not constrained."""
        with pytest.raises(ValueError):
            NonDischargeClaim(kind="not_a_kind", reason="authority")
        # Conversely, weird freeform reasons are fine with valid kind.
        c = NonDischargeClaim(
            kind=UNSETTLED_AUTHORITY,
            reason="🙃 explanation containing emoji and a citation [1]",
        )
        assert c.reason.startswith("🙃")

    def test_required_fields_optional(self):
        c = NonDischargeClaim(kind=UNSETTLED_FRESHNESS, reason="stale")
        assert c.required_consumer is None
        assert c.required_witness is None

    def test_roundtrip(self):
        original = NonDischargeClaim(
            kind=UNSETTLED_EVIDENCE_SUFFICIENCY,
            reason="evidence bundle missing signature",
            required_consumer="downstream-auditor",
            required_witness="signed-bundle-v2",
        )
        restored = NonDischargeClaim.from_dict(original.to_dict())
        assert restored == original


class TestGateReceiptUnsettled:
    """v4 receipt-level unsettled behavior + v3 backward compat."""

    def _base_kwargs(self):
        return dict(
            gate="evidence_gate",
            verdict="block",
            subject_kind="text",
            subject_bytes=b"agent output",
            evidence_bundle={"claims": []},
            gate_config={"strict": True},
        )

    def test_v4_gate_receipt_emits_unsettled_default_empty(self):
        """New v4 receipts always emit `unsettled: []` (positive claim:
        'no unsettled claims surfaced'), not silence."""
        r = create_receipt(**self._base_kwargs())
        assert r.schema_version == 4
        assert r.unsettled == ()
        d = r.to_dict()
        assert "unsettled" in d
        assert d["unsettled"] == []

    def test_gate_receipt_accepts_typed_non_discharge_claim(self):
        unsettled = (
            NonDischargeClaim(
                kind=UNSETTLED_AUTHORITY,
                reason="proposal cites upstream authority not validated by this gate",
                required_consumer="authorization-reviewer",
            ),
        )
        r = create_receipt(**self._base_kwargs(), unsettled=unsettled)
        assert len(r.unsettled) == 1
        assert r.unsettled[0].kind == UNSETTLED_AUTHORITY
        # Round-trips through JSON.
        d = r.to_dict()
        assert d["unsettled"][0]["kind"] == UNSETTLED_AUTHORITY
        restored = GateReceipt.from_dict(d)
        assert restored.unsettled == r.unsettled

    def test_gate_receipt_rejects_unknown_non_discharge_kind(self):
        """The kind enum is closed at the NonDischargeClaim layer;
        invalid kinds cannot reach a GateReceipt."""
        with pytest.raises(ValueError, match="Invalid non-discharge kind"):
            NonDischargeClaim(kind="misc_authority_vibes", reason="bad")

    def test_v3_gate_receipt_loads_with_empty_unsettled(self):
        """A v3 receipt dict (no `unsettled` field) loads cleanly and
        defaults unsettled to (). Preserves backward compat with the
        1,165 receipts already on disk."""
        v3_receipt = {
            "receipt_id": "362165328617543a38590f6adf8f5e001878468205aa1624e2c64fa780e2f3fc",
            "schema_version": 3,
            "timestamp": "2026-05-18T19:42:29.448715+00:00",
            "gate": "context_build",
            "verdict": "observe",
            "subject_hash": "d74258157b8c292dfbb2a7cd134906661a5831c190ac4c1092f3df74b96461a0",
            "evidence_hash": "71304e1c205b56e8aad6d24686d74c08a2c410b408dbe3a694fe3d373106047a",
            "policy_hash": "55e07aa892d732d737d4f17bc9520a0825e6430244cfdb4ba93e688d68d28fc9",
            "principal_id": "local",
            "tenant_id": "default",
            "auth_method": "none",
            "receipt_role": "measurement",
        }
        r = GateReceipt.from_dict(v3_receipt)
        assert r.schema_version == 3
        assert r.unsettled == ()
        # v3 receipt re-serialized stays v3 (preserves byte-level intent
        # for legacy receipts) — unsettled is NOT emitted for v3.
        out = r.to_dict()
        assert "unsettled" not in out

    def test_v4_receipts_with_different_unsettled_have_different_ids(self):
        """Two v4 receipts with identical payload but different unsettled
        sets are different decisions. The receipt_id must reflect that."""
        base = self._base_kwargs()
        r_empty = create_receipt(**base)
        r_with = create_receipt(
            **base,
            unsettled=(
                NonDischargeClaim(
                    kind=UNSETTLED_FRESHNESS,
                    reason="evidence is stale at action boundary",
                ),
            ),
        )
        assert r_empty.receipt_id != r_with.receipt_id

    def test_v4_receipt_with_empty_unsettled_hash_stable_against_horizon_pattern(self):
        """Empty unsettled does NOT bind into receipt_id (mirrors horizon).
        Two v4 receipts created with explicit `unsettled=()` and the default
        produce the same receipt_id when other fields match."""
        base = self._base_kwargs()
        r_default = create_receipt(**base)
        r_explicit_empty = create_receipt(**base, unsettled=())
        assert r_default.receipt_id == r_explicit_empty.receipt_id

    def test_v4_receipt_emit_via_system_persists_unsettled(self, tmp_path):
        system = GateReceiptSystem(tmp_path)
        unsettled = (
            NonDischargeClaim(
                kind=UNSETTLED_AUTHORITY,
                reason="upstream principal not authenticated by this gate",
                required_witness="signed-principal-ref",
            ),
        )
        receipt = system.emit(
            **self._base_kwargs(),
            unsettled=unsettled,
        )
        found = system.receipt_store.get_by_id(receipt.receipt_id)
        assert found is not None
        assert found.unsettled == unsettled


# =============================================================================
# Golden fixture — receipt_v4_with_unsettled.json
# =============================================================================
#
# Pins the cross-language wire shape: a v4 GateReceipt emitted via the actual
# nightshift_adapter.record_receipt path (NOT hand-crafted JSON) and frozen
# to disk. Tests below assert load + structure + receipt_id content-address
# stability. If the schema, the canonicalization, or the unsettled-hash
# binding drifts on either side of the seam, these tests fail loudly before
# production. Re-generated via: emit-once-and-freeze (see provenance below).


_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "golden_traces"
    / "receipt_v4_with_unsettled.json"
)


class TestGoldenFixtureV4WithUnsettled:
    """Golden GateReceipt v4 fixture — the label sewn onto the integration."""

    @pytest.fixture
    def fixture_data(self) -> dict:
        return json.loads(_FIXTURE_PATH.read_text())

    def test_fixture_file_exists(self):
        assert _FIXTURE_PATH.exists(), (
            f"Golden fixture missing: {_FIXTURE_PATH}. "
            f"Re-generate via: emit-once-and-freeze (see fixture provenance)."
        )

    def test_fixture_parses_as_v4_gate_receipt(self, fixture_data):
        receipt = GateReceipt.from_dict(fixture_data)
        assert receipt.schema_version == 4

    def test_fixture_carries_one_freshness_unsettled_claim(self, fixture_data):
        receipt = GateReceipt.from_dict(fixture_data)
        assert len(receipt.unsettled) == 1
        claim = receipt.unsettled[0]
        assert claim.kind == UNSETTLED_FRESHNESS
        assert claim.reason, "reason is informational but must not be empty"

    def test_fixture_receipt_role_is_authority(self, fixture_data):
        """Per the nightshift_adapter EventKind→role mapping,
        ACTION_AUTHORIZED maps to ROLE_AUTHORITY. The fixture was
        emitted via that path; the recorded role must match."""
        receipt = GateReceipt.from_dict(fixture_data)
        assert receipt.receipt_role == "authority"

    def test_fixture_horizon_is_present_and_hours(self, fixture_data):
        """The fixture represents a horizon-Defer receipt. The horizon
        block must be present with kind=hours per the emit path."""
        receipt = GateReceipt.from_dict(fixture_data)
        assert receipt.horizon is not None
        assert receipt.horizon.kind == "hours"

    def test_fixture_receipt_id_is_content_addressed(self, fixture_data):
        """Recompute receipt_id from the fixture's other fields and
        assert it matches the stored value. Proves the hash binding
        (schema_version + gate + subject + evidence + policy + role +
        horizon_hash + unsettled_hash) is stable and that the fixture's
        stored id is not stale."""
        receipt = GateReceipt.from_dict(fixture_data)
        horizon_hash = (
            receipt.horizon.content_hash() if receipt.horizon is not None else None
        )
        unsettled_hash = (
            content_hash(canonical_json([c.to_dict() for c in receipt.unsettled]))
            if receipt.unsettled
            else None
        )
        recomputed = _compute_receipt_id(
            receipt.schema_version,
            receipt.gate,
            receipt.subject_hash,
            receipt.evidence_hash,
            receipt.policy_hash,
            receipt.receipt_role,
            horizon_hash=horizon_hash,
            unsettled_hash=unsettled_hash,
        )
        assert recomputed == receipt.receipt_id, (
            f"fixture's stored receipt_id {receipt.receipt_id!r} does not match "
            f"recomputed {recomputed!r} — schema or canonicalization drift."
        )

    def test_fixture_roundtrips_through_from_dict_to_dict(self, fixture_data):
        """Load → to_dict → load again. The two GateReceipt objects
        must be equal; canonical JSON of their dicts must match
        byte-for-byte. This is the strongest no-drift assertion."""
        first = GateReceipt.from_dict(fixture_data)
        roundtripped = first.to_dict()
        second = GateReceipt.from_dict(roundtripped)
        assert first == second
        assert canonical_json(first.to_dict()) == canonical_json(second.to_dict())

    def test_fixture_unsettled_participates_in_receipt_id(self, fixture_data):
        """If we remove the unsettled claims from the fixture and
        recompute the receipt_id, it must differ. Proves the unsettled
        binding is NOT vestigial — two receipts with otherwise-identical
        fields but different unsettled sets are distinct decisions."""
        receipt = GateReceipt.from_dict(fixture_data)
        horizon_hash = (
            receipt.horizon.content_hash() if receipt.horizon is not None else None
        )
        without_unsettled = _compute_receipt_id(
            receipt.schema_version,
            receipt.gate,
            receipt.subject_hash,
            receipt.evidence_hash,
            receipt.policy_hash,
            receipt.receipt_role,
            horizon_hash=horizon_hash,
            unsettled_hash=None,  # empty would skip the fragment
        )
        assert without_unsettled != receipt.receipt_id, (
            "removing unsettled must change receipt_id; otherwise the "
            "binding is not active and the fixture proves nothing."
        )
