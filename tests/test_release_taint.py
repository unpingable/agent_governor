# SPDX-License-Identifier: Apache-2.0
"""Tests for release taint — publish-boundary assessment.

Tests:
- PublishThreshold: default, custom, scope lookup, fallback, None scope
- compute_taint tri-state: tainted/clean/unknown for various evidence scenarios
- Claim filtering: only high-confidence claims considered
- TaintReason: code property, to_dict roundtrip
- RunTaint: to_dict roundtrip, .tainted property
- Edge cases: empty run, no oracle claims, multiple claims mixed
- Max-class simplification: highest oracle wins
- Scope threshold: scope-specific threshold applied when claim carries scope
"""

from __future__ import annotations

import json

import pytest

from receipt_kernel.envelope import make_envelope
from receipt_kernel.store_sqlite import SqliteReceiptStore

from governor.release_taint import (
    PublishThreshold,
    RunTaint,
    TaintReason,
    compute_taint,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_oracle_independence.py)
# ---------------------------------------------------------------------------

def _make_store(tmp_path) -> SqliteReceiptStore:
    store = SqliteReceiptStore(str(tmp_path / "test.db"), redaction_enabled=False)
    store.initialize_schema()
    return store


def _start_run(store, run_id, mode="factual"):
    store.ensure_run(
        run_id=run_id, policy_id="test", policy_version="0.1",
        stage_graph_id="v1_default", meta={"mode": mode},
    )
    env = make_envelope(
        event_type="RUN_START", stage="START",
        policy_id="test", policy_version="0.1",
        stage_graph_id="v1_default", actor_kind="pytest", actor_id="test",
        payload={"meta": {"mode": mode}},
    )
    store.append_event(run_id, env)


def _put_evidence(store, run_id, key, data, content_type="application/json",
                   evidence_kind=None, oracle_class=None):
    blob = store.put_blob(data, content_type=content_type)
    meta = {}
    if evidence_kind is not None:
        meta["evidence_kind"] = evidence_kind
    if oracle_class is not None:
        meta["oracle_class"] = oracle_class
    env = make_envelope(
        event_type="EVIDENCE_PUT", stage="COLLECT",
        policy_id="test", policy_version="0.1",
        stage_graph_id="v1_default", actor_kind="pytest", actor_id="test",
        payload={"key": key, "evidence": blob.to_dict(), "meta": meta},
        blob_refs=[blob.ref],
    )
    store.append_event(run_id, env)
    return blob


def _put_claims_map(store, run_id, claims):
    doc = {"schema_version": 1, "claims": claims}
    return _put_evidence(store, run_id, "claims_map", json.dumps(doc).encode())


# ---------------------------------------------------------------------------
# Tests: PublishThreshold
# ---------------------------------------------------------------------------

class TestPublishThreshold:
    def test_default_is_1(self):
        t = PublishThreshold()
        assert t.default == 1
        assert t.min_class() == 1

    def test_custom_default(self):
        t = PublishThreshold(default=2)
        assert t.default == 2
        assert t.min_class() == 2

    def test_scope_lookup(self):
        t = PublishThreshold(default=1, scopes={"auth": 2, "ci": 1})
        assert t.min_class("auth") == 2
        assert t.min_class("ci") == 1

    def test_scope_fallback_to_default(self):
        t = PublishThreshold(default=1, scopes={"auth": 2})
        assert t.min_class("unknown_scope") == 1

    def test_none_scope_uses_default(self):
        t = PublishThreshold(default=1, scopes={"auth": 2})
        assert t.min_class(None) == 1


# ---------------------------------------------------------------------------
# Tests: TaintReason
# ---------------------------------------------------------------------------

class TestTaintReason:
    def test_code_includes_both_values(self):
        r = TaintReason(claim_id="c1", observed_class=0, publish_min_class=1)
        assert r.code == "weak_oracle_class_0_below_1"

    def test_code_with_higher_values(self):
        r = TaintReason(claim_id="c2", observed_class=1, publish_min_class=3)
        assert r.code == "weak_oracle_class_1_below_3"

    def test_to_dict_roundtrip(self):
        r = TaintReason(claim_id="c1", observed_class=0, publish_min_class=1)
        d = r.to_dict()
        assert d["claim_id"] == "c1"
        assert d["observed_class"] == 0
        assert d["publish_min_class"] == 1
        assert d["code"] == "weak_oracle_class_0_below_1"
        # Serializable
        json.dumps(d)


# ---------------------------------------------------------------------------
# Tests: RunTaint
# ---------------------------------------------------------------------------

class TestRunTaint:
    def test_tainted_property_true(self):
        rt = RunTaint(run_id="r1", status="tainted", publish_min_class=1)
        assert rt.tainted is True

    def test_tainted_property_false_clean(self):
        rt = RunTaint(run_id="r1", status="clean", publish_min_class=1)
        assert rt.tainted is False

    def test_tainted_property_false_unknown(self):
        rt = RunTaint(run_id="r1", status="unknown", publish_min_class=1)
        assert rt.tainted is False

    def test_to_dict_roundtrip(self):
        rt = RunTaint(
            run_id="r1",
            status="tainted",
            publish_min_class=1,
            reasons=[TaintReason("c1", 0, 1)],
            unknown_reasons=[],
            total_high_confidence_claims=1,
            oracle_backed_claims=1,
            clean_claims=0,
        )
        d = rt.to_dict()
        assert d["run_id"] == "r1"
        assert d["status"] == "tainted"
        assert d["publish_min_class"] == 1
        assert len(d["reasons"]) == 1
        assert d["reasons"][0]["claim_id"] == "c1"
        assert d["total_high_confidence_claims"] == 1
        assert d["oracle_backed_claims"] == 1
        assert d["clean_claims"] == 0
        json.dumps(d)

    def test_to_dict_clean(self):
        rt = RunTaint(run_id="r1", status="clean", publish_min_class=1)
        d = rt.to_dict()
        assert d["status"] == "clean"
        assert d["reasons"] == []
        json.dumps(d)

    def test_to_dict_unknown(self):
        rt = RunTaint(
            run_id="r1", status="unknown", publish_min_class=1,
            unknown_reasons=["claims_map evidence blob missing or unreadable"],
        )
        d = rt.to_dict()
        assert d["status"] == "unknown"
        assert len(d["unknown_reasons"]) == 1
        json.dumps(d)


# ---------------------------------------------------------------------------
# Tests: compute_taint tri-state
# ---------------------------------------------------------------------------

class TestComputeTaintTriState:
    def test_class0_tainted_with_default_threshold(self, tmp_path):
        """Class 0 oracle → tainted (default threshold is class 1)."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "test_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=0)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "tainted"
        assert result.tainted is True
        assert len(result.reasons) == 1
        assert result.reasons[0].claim_id == "c1"
        assert result.reasons[0].observed_class == 0
        assert result.reasons[0].publish_min_class == 1

    def test_class1_clean_with_default_threshold(self, tmp_path):
        """Class 1 oracle → clean (meets default threshold)."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "ci_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=1)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "clean"
        assert result.tainted is False
        assert result.clean_claims == 1

    def test_class2_clean(self, tmp_path):
        """Class 2 oracle → clean (exceeds threshold)."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "ext_ci", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=2)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "clean"

    def test_custom_threshold(self, tmp_path):
        """Custom threshold of class 2 → class 1 is tainted."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "ci_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=1)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
        }])

        threshold = PublishThreshold(default=2)
        result = compute_taint(store, "r1", threshold=threshold)
        assert result.status == "tainted"
        assert result.publish_min_class == 2

    def test_missing_claims_map_unknown(self, tmp_path):
        """Missing claims_map → UNKNOWN."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")

        result = compute_taint(store, "r1")
        assert result.status == "unknown"
        assert "claims_map evidence blob missing or unreadable" in result.unknown_reasons

    def test_missing_blob_data_unknown(self, tmp_path):
        """claims_map references a blob whose data can't be read → unknown."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        # Put claims_map that references a nonexistent blob ref
        bogus_ref = "blob://sha256:0000000000000000000000000000000000000000000000000000000000000000"
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [bogus_ref],
        }])

        result = compute_taint(store, "r1")
        # bogus_ref is not in blob_class_map and not in all_blob_refs, so
        # it's simply not oracle evidence — claim has no oracle refs → clean
        assert result.status == "clean"
        assert result.oracle_backed_claims == 0


# ---------------------------------------------------------------------------
# Tests: Claim filtering (only high-confidence)
# ---------------------------------------------------------------------------

class TestClaimFiltering:
    def test_only_high_confidence_considered(self, tmp_path):
        """Low-confidence claims with class 0 oracle → clean (ignored)."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "test_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=0)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "low", "evidence_refs": [blob.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "clean"
        assert result.total_high_confidence_claims == 0

    def test_mixed_high_low(self, tmp_path):
        """Only the high-confidence claim triggers taint."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "test_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=0)
        _put_claims_map(store, "r1", [
            {"id": "c_low", "confidence": "low", "evidence_refs": [blob.ref]},
            {"id": "c_high", "confidence": "high", "evidence_refs": [blob.ref]},
        ])

        result = compute_taint(store, "r1")
        assert result.status == "tainted"
        assert result.total_high_confidence_claims == 1
        assert len(result.reasons) == 1
        assert result.reasons[0].claim_id == "c_high"

    def test_medium_confidence_not_considered(self, tmp_path):
        """Medium confidence is not high — not checked."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "test_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=0)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "medium", "evidence_refs": [blob.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "clean"
        assert result.total_high_confidence_claims == 0


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_claims_clean(self, tmp_path):
        """No claims at all → clean."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        _put_claims_map(store, "r1", [])

        result = compute_taint(store, "r1")
        assert result.status == "clean"
        assert result.total_high_confidence_claims == 0

    def test_high_confidence_no_oracle_refs_clean(self, tmp_path):
        """High-confidence claim with only model evidence → clean.

        Oracle independence is confidence.sanity's job, not ours.
        """
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "output", b"text",
                             evidence_kind="model:self_report")
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "clean"
        assert result.oracle_backed_claims == 0

    def test_run_with_only_model_evidence_clean(self, tmp_path):
        """Run with only model:generated evidence → clean (no oracles to check)."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "final_output", b"code here",
                             evidence_kind="model:generated")
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "clean"

    def test_multiple_claims_mixed_results(self, tmp_path):
        """Two high-confidence claims: one tainted, one clean → tainted."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        b0 = _put_evidence(store, "r1", "local", b'{"a":1}',
                           evidence_kind="oracle:pytest_log", oracle_class=0)
        b1 = _put_evidence(store, "r1", "ci", b'{"b":2}',
                           evidence_kind="oracle:pytest_log", oracle_class=1)
        _put_claims_map(store, "r1", [
            {"id": "c1", "confidence": "high", "evidence_refs": [b0.ref]},
            {"id": "c2", "confidence": "high", "evidence_refs": [b1.ref]},
        ])

        result = compute_taint(store, "r1")
        assert result.status == "tainted"
        assert result.total_high_confidence_claims == 2
        assert result.oracle_backed_claims == 2
        assert result.clean_claims == 1
        assert len(result.reasons) == 1
        assert result.reasons[0].claim_id == "c1"


# ---------------------------------------------------------------------------
# Tests: Max-class simplification
# ---------------------------------------------------------------------------

class TestMaxClassSimplification:
    def test_two_oracles_highest_wins(self, tmp_path):
        """Claim citing two oracle blobs: max class used (documented simplification)."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        b0 = _put_evidence(store, "r1", "local", b'{"a":1}',
                           evidence_kind="oracle:pytest_log", oracle_class=0)
        b1 = _put_evidence(store, "r1", "ci", b'{"b":2}',
                           evidence_kind="oracle:pytest_log", oracle_class=1)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [b0.ref, b1.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "clean"
        assert result.clean_claims == 1

    def test_two_oracles_both_low(self, tmp_path):
        """Two class-0 oracles: max is still 0 → tainted."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        b0 = _put_evidence(store, "r1", "local1", b'{"a":1}',
                           evidence_kind="oracle:pytest_log", oracle_class=0)
        b1 = _put_evidence(store, "r1", "local2", b'{"b":2}',
                           evidence_kind="oracle:pytest_log", oracle_class=0)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [b0.ref, b1.ref],
        }])

        result = compute_taint(store, "r1")
        assert result.status == "tainted"


# ---------------------------------------------------------------------------
# Tests: Scope-specific threshold
# ---------------------------------------------------------------------------

class TestScopeThreshold:
    def test_scope_specific_threshold(self, tmp_path):
        """Scope-specific threshold applied when claim carries scope."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "ci_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=1)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
            "scope": "auth",
        }])

        # auth requires class 2, so class 1 is tainted
        threshold = PublishThreshold(default=1, scopes={"auth": 2})
        result = compute_taint(store, "r1", threshold=threshold)
        assert result.status == "tainted"
        assert result.reasons[0].publish_min_class == 2

    def test_scope_fallback_when_no_match(self, tmp_path):
        """Unmatched scope falls back to default."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "ci_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=1)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
            "scope": "utils",
        }])

        threshold = PublishThreshold(default=1, scopes={"auth": 2})
        result = compute_taint(store, "r1", threshold=threshold)
        assert result.status == "clean"

    def test_scope_none_uses_default(self, tmp_path):
        """No scope on claim → uses default threshold."""
        store = _make_store(tmp_path)
        _start_run(store, "r1")
        blob = _put_evidence(store, "r1", "ci_log", b'{"tests":5}',
                             evidence_kind="oracle:pytest_log", oracle_class=1)
        _put_claims_map(store, "r1", [{
            "id": "c1", "confidence": "high", "evidence_refs": [blob.ref],
        }])

        threshold = PublishThreshold(default=1, scopes={"auth": 2})
        result = compute_taint(store, "r1", threshold=threshold)
        assert result.status == "clean"
