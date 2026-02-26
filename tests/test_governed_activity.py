# SPDX-License-Identifier: Apache-2.0
"""Tests for governed_activity module — drift-gated retry substrate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import logging

from governor.governed_activity import (
    ACTIVITY_DRIFT_GATE,
    DIVERGENCE_DETECTED,
    ActivityOutcome,
    AttemptRecord,
    AttemptStore,
    DriftCheckResult,
    DriftVerdict,
    FactObservation,
    IdempotencyStrategy,
    PreconditionBundle,
    RetryClass,
    _VERDICT_TO_GATE,
    _VERDICT_TO_RETRY,
    drift_check,
    drift_check_stored,
    on_attempt,
    record_attempt,
)
from governor.gate_receipt import (
    GateReceiptSystem,
    canonical_json,
    content_hash,
)


# =============================================================================
# Helpers
# =============================================================================


def _fact(
    fact_type: str = "DescribeASG",
    subject: str | None = "asg/prod",
    observed_at: str = "2026-02-26T12:00:00+00:00",
    request_fingerprint: str | None = "req_abc",
    response_fingerprint: str | None = "resp_xyz",
    etag_or_version: str | None = None,
    freshness_s: int | None = 30,
    confidence: str | None = "high",
    source: str | None = "AWS",
) -> FactObservation:
    return FactObservation(
        fact_type=fact_type,
        observed_at=observed_at,
        subject=subject,
        request_fingerprint=request_fingerprint,
        response_fingerprint=response_fingerprint,
        etag_or_version=etag_or_version,
        freshness_s=freshness_s,
        confidence=confidence,
        source=source,
    )


def _bundle(*facts: FactObservation) -> PreconditionBundle:
    return PreconditionBundle(list(facts))


# =============================================================================
# FactObservation (10 tests)
# =============================================================================


class TestFactObservation:
    def test_construction_minimal(self):
        f = FactObservation(fact_type="GetPod", observed_at="2026-01-01T00:00:00Z")
        assert f.fact_type == "GetPod"
        assert f.subject is None

    def test_construction_full(self):
        f = _fact()
        assert f.fact_type == "DescribeASG"
        assert f.subject == "asg/prod"
        assert f.source == "AWS"

    def test_frozen(self):
        f = _fact()
        with pytest.raises(AttributeError):
            f.fact_type = "other"  # type: ignore[misc]

    def test_fingerprint_dict_all_fields_present(self):
        """All 6 fingerprint fields always present, never dropped."""
        f = FactObservation(fact_type="X", observed_at="t")
        fp = f.fingerprint_dict()
        assert set(fp.keys()) == {
            "fact_type", "subject", "source",
            "request_fingerprint", "response_fingerprint", "etag_or_version",
        }

    def test_fingerprint_dict_none_normalized_to_empty(self):
        """Optional strings normalize to '' in fingerprint_dict."""
        f = FactObservation(fact_type="X", observed_at="t")
        fp = f.fingerprint_dict()
        assert fp["subject"] == ""
        assert fp["source"] == ""
        assert fp["request_fingerprint"] == ""
        assert fp["response_fingerprint"] == ""
        assert fp["etag_or_version"] == ""

    def test_fingerprint_excludes_volatile(self):
        """observed_at, confidence, freshness_s excluded from fingerprint."""
        f1 = _fact(observed_at="2026-01-01T00:00:00Z", confidence="low", freshness_s=10)
        f2 = _fact(observed_at="2026-12-31T23:59:59Z", confidence="high", freshness_s=300)
        assert f1.fingerprint() == f2.fingerprint()

    def test_fingerprint_includes_world_state(self):
        """Different world state → different fingerprint."""
        f1 = _fact(response_fingerprint="aaa")
        f2 = _fact(response_fingerprint="bbb")
        assert f1.fingerprint() != f2.fingerprint()

    def test_etag_key_format(self):
        f = _fact(fact_type="GetPod", subject="pod/x", source="k8s")
        assert f.etag_key() == "GetPod:pod/x:k8s"

    def test_etag_key_none_subject(self):
        f = _fact(subject=None, source=None)
        assert f.etag_key() == "DescribeASG::"

    def test_to_dict_roundtrip(self):
        f = _fact(etag_or_version="v42")
        d = f.to_dict()
        f2 = FactObservation.from_dict(d)
        assert f == f2

    def test_to_dict_omits_none_fields(self):
        """to_dict omits None optional fields (compact serialization)."""
        f = FactObservation(fact_type="X", observed_at="t")
        d = f.to_dict()
        assert "subject" not in d
        assert "source" not in d


# =============================================================================
# PreconditionBundle (14 tests)
# =============================================================================


class TestPreconditionBundle:
    def test_empty_bundle(self):
        b = PreconditionBundle()
        assert b.observations == ()
        assert isinstance(b.fingerprint(), str)

    def test_sorted_on_construction(self):
        """Observations are sorted by sort key on construction."""
        f_b = _fact(fact_type="B")
        f_a = _fact(fact_type="A")
        b = _bundle(f_b, f_a)
        assert b.observations[0].fact_type == "A"
        assert b.observations[1].fact_type == "B"

    def test_sort_tie_breaker_subject(self):
        f1 = _fact(fact_type="X", subject="aaa")
        f2 = _fact(fact_type="X", subject="bbb")
        b = _bundle(f2, f1)
        assert b.observations[0].subject == "aaa"

    def test_sort_tie_breaker_source(self):
        f1 = _fact(fact_type="X", subject="s", source="AWS")
        f2 = _fact(fact_type="X", subject="s", source="k8s")
        b = _bundle(f2, f1)
        assert b.observations[0].source == "AWS"

    def test_sort_none_normalized(self):
        """None values treated as '' for sorting."""
        f1 = _fact(fact_type="X", subject=None)
        f2 = _fact(fact_type="X", subject="aaa")
        b = _bundle(f2, f1)
        # "" < "aaa"
        assert b.observations[0].subject is None

    def test_fingerprint_stability(self):
        """Same observations in different order → same fingerprint."""
        f_a = _fact(fact_type="A")
        f_b = _fact(fact_type="B")
        b1 = _bundle(f_a, f_b)
        b2 = _bundle(f_b, f_a)
        assert b1.fingerprint() == b2.fingerprint()

    def test_fingerprint_different_content(self):
        f1 = _fact(response_fingerprint="aaa")
        f2 = _fact(response_fingerprint="bbb")
        b1 = _bundle(f1)
        b2 = _bundle(f2)
        assert b1.fingerprint() != b2.fingerprint()

    def test_frozen(self):
        b = PreconditionBundle()
        with pytest.raises(AttributeError):
            b.observations = ()  # type: ignore[misc]

    def test_etag_snapshot_no_etags(self):
        b = _bundle(_fact(etag_or_version=None))
        assert b.etag_snapshot() == {}

    def test_etag_snapshot_with_etags(self):
        f = _fact(fact_type="GetPod", subject="pod/x", source="k8s", etag_or_version="v5")
        b = _bundle(f)
        snap = b.etag_snapshot()
        assert snap == {"GetPod:pod/x:k8s": "v5"}

    def test_etag_snapshot_multiple(self):
        f1 = _fact(fact_type="A", subject="s1", source="AWS", etag_or_version="e1")
        f2 = _fact(fact_type="B", subject="s2", source="k8s", etag_or_version="e2")
        b = _bundle(f1, f2)
        snap = b.etag_snapshot()
        assert len(snap) == 2
        assert snap["A:s1:AWS"] == "e1"
        assert snap["B:s2:k8s"] == "e2"

    def test_has_etags(self):
        assert not _bundle(_fact()).has_etags()
        assert _bundle(_fact(etag_or_version="v1")).has_etags()

    def test_to_dict_roundtrip(self):
        b = _bundle(_fact(), _fact(fact_type="B"))
        d = b.to_dict()
        b2 = PreconditionBundle.from_dict(d)
        assert b.fingerprint() == b2.fingerprint()

    def test_accepts_tuple_input(self):
        """Constructor accepts tuple as well as list."""
        f = _fact()
        b = PreconditionBundle(observations=(f,))
        assert len(b.observations) == 1


# =============================================================================
# drift_check — full bundles (10 tests)
# =============================================================================


class TestDriftCheck:
    def test_identical_bundles_no_drift(self):
        b = _bundle(_fact())
        assert drift_check(b, b) == DriftVerdict.NO_DRIFT

    def test_different_fingerprint_diverged(self):
        b1 = _bundle(_fact(response_fingerprint="aaa"))
        b2 = _bundle(_fact(response_fingerprint="bbb"))
        assert drift_check(b1, b2) == DriftVerdict.FINGERPRINT_DIVERGED

    def test_etag_match_no_drift(self):
        """Matching etags + matching fingerprint → no drift."""
        f1 = _fact(etag_or_version="v1")
        f2 = _fact(etag_or_version="v1")
        assert drift_check(_bundle(f1), _bundle(f2)) == DriftVerdict.NO_DRIFT

    def test_etag_diverged(self):
        """Different etag values → etag_diverged (etag tier wins)."""
        f1 = _fact(etag_or_version="v1")
        f2 = _fact(etag_or_version="v2")
        assert drift_check(_bundle(f1), _bundle(f2)) == DriftVerdict.ETAG_DIVERGED

    def test_etag_diverged_takes_precedence(self):
        """Etag divergence takes precedence over fingerprint match."""
        f1 = _fact(etag_or_version="v1")
        f2 = _fact(etag_or_version="v2")
        # Even if fingerprints happen to match on other dimensions
        assert drift_check(_bundle(f1), _bundle(f2)) == DriftVerdict.ETAG_DIVERGED

    def test_continuity_lost_prior_has_etags_current_does_not(self):
        f1 = _fact(etag_or_version="v1")
        f2 = _fact(etag_or_version=None)
        assert drift_check(_bundle(f1), _bundle(f2)) == DriftVerdict.CONTINUITY_LOST

    def test_continuity_lost_current_has_etags_prior_does_not(self):
        f1 = _fact(etag_or_version=None)
        f2 = _fact(etag_or_version="v1")
        assert drift_check(_bundle(f1), _bundle(f2)) == DriftVerdict.CONTINUITY_LOST

    def test_no_etags_either_side_fingerprint_match(self):
        """Neither side has etags, fingerprints match → no drift."""
        b = _bundle(_fact())
        assert drift_check(b, b) == DriftVerdict.NO_DRIFT

    def test_no_etags_either_side_fingerprint_mismatch(self):
        """Neither side has etags, fingerprints differ → fingerprint_diverged."""
        b1 = _bundle(_fact(response_fingerprint="a"))
        b2 = _bundle(_fact(response_fingerprint="b"))
        assert drift_check(b1, b2) == DriftVerdict.FINGERPRINT_DIVERGED

    def test_disjoint_etag_keys_continuity_lost(self):
        """Completely different etag key sets → continuity_lost."""
        f1 = _fact(fact_type="A", subject="x", source="s1", etag_or_version="v1")
        f2 = _fact(fact_type="B", subject="y", source="s2", etag_or_version="v2")
        assert drift_check(_bundle(f1), _bundle(f2)) == DriftVerdict.CONTINUITY_LOST


# =============================================================================
# drift_check_stored (6 tests)
# =============================================================================


class TestDriftCheckStored:
    def test_matching_stored(self):
        b = _bundle(_fact())
        fp = b.fingerprint()
        assert drift_check_stored(fp, {}, b) == DriftVerdict.NO_DRIFT

    def test_fingerprint_mismatch_stored(self):
        b = _bundle(_fact())
        assert drift_check_stored("wrong_fp", {}, b) == DriftVerdict.FINGERPRINT_DIVERGED

    def test_etag_match_stored(self):
        f = _fact(fact_type="X", subject="s", source="src", etag_or_version="v1")
        b = _bundle(f)
        fp = b.fingerprint()
        etags = b.etag_snapshot()
        assert drift_check_stored(fp, etags, b) == DriftVerdict.NO_DRIFT

    def test_etag_diverged_stored(self):
        f = _fact(fact_type="X", subject="s", source="src", etag_or_version="v2")
        b = _bundle(f)
        prior_etags = {"X:s:src": "v1"}
        assert drift_check_stored("any", prior_etags, b) == DriftVerdict.ETAG_DIVERGED

    def test_continuity_lost_prior_etags_current_none(self):
        b = _bundle(_fact())  # no etags
        prior_etags = {"X:s:src": "v1"}
        assert drift_check_stored("any", prior_etags, b) == DriftVerdict.CONTINUITY_LOST

    def test_continuity_lost_current_etags_prior_none(self):
        f = _fact(etag_or_version="v1")
        b = _bundle(f)
        assert drift_check_stored("any", {}, b) == DriftVerdict.CONTINUITY_LOST


# =============================================================================
# AttemptRecord (8 tests)
# =============================================================================


class TestAttemptRecord:
    def test_construction(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        )
        assert r.call_id == "c1"
        assert r.error_class is None
        assert r.created_at is None

    def test_frozen(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        )
        with pytest.raises(AttributeError):
            r.call_id = "other"  # type: ignore[misc]

    def test_to_dict_basic(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={"k": "v"},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.SAFE_TRANSIENT,
        )
        d = r.to_dict()
        assert d["call_id"] == "c1"
        assert d["etag_snapshot"] == {"k": "v"}
        assert d["outcome"] == "success"
        assert d["retry_class"] == "safe_transient"

    def test_to_dict_omits_none_optionals(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        )
        d = r.to_dict()
        assert "error_class" not in d
        assert "error_message" not in d
        assert "receipt_hash" not in d
        assert "created_at" not in d

    def test_to_dict_includes_error_fields(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.BUSINESS_FAILURE,
            retry_class=RetryClass.UNSAFE,
            error_class=DIVERGENCE_DETECTED,
            error_message="preconditions changed",
        )
        d = r.to_dict()
        assert d["error_class"] == DIVERGENCE_DETECTED
        assert d["error_message"] == "preconditions changed"

    def test_roundtrip(self):
        r = AttemptRecord(
            call_id="c1", attempt=2,
            precondition_fingerprint="fp_hash",
            etag_snapshot={"X:s:src": "v3"},
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.OPERATOR_REQUIRED,
            error_class="Timeout",
            error_message="timed out after 30s",
            receipt_hash="rh_abc",
            idempotency_strategy=IdempotencyStrategy.CAS_BINDING,
            created_at="2026-02-26T12:00:00+00:00",
        )
        d = r.to_dict()
        r2 = AttemptRecord.from_dict(d)
        assert r2.call_id == r.call_id
        assert r2.etag_snapshot == r.etag_snapshot
        assert r2.outcome == r.outcome
        assert r2.idempotency_strategy == IdempotencyStrategy.CAS_BINDING

    def test_json_serialization(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        )
        j = r.to_json()
        parsed = json.loads(j)
        assert parsed["call_id"] == "c1"

    def test_idempotency_strategy_default_omitted(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        )
        d = r.to_dict()
        # IdempotencyStrategy.NONE is the default, omitted from serialization
        assert "idempotency_strategy" not in d


# =============================================================================
# AttemptStore (12 tests)
# =============================================================================


class TestAttemptStore:
    def test_empty_store(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        assert store.all() == []

    def test_append_and_read(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp1",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        )
        store.append(r)
        records = store.all()
        assert len(records) == 1
        assert records[0].call_id == "c1"

    def test_multiple_records(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        for i in range(3):
            store.append(AttemptRecord(
                call_id="c1", attempt=i + 1,
                precondition_fingerprint=f"fp{i}",
                etag_snapshot={},
                outcome=ActivityOutcome.SUCCESS,
                retry_class=RetryClass.NONE,
            ))
        assert len(store.all()) == 3

    def test_jsonl_format(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        ))
        content = store.path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["call_id"] == "c1"

    def test_get_prior_basic(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        for i in range(3):
            store.append(AttemptRecord(
                call_id="c1", attempt=i + 1,
                precondition_fingerprint=f"fp{i}",
                etag_snapshot={},
                outcome=ActivityOutcome.SUCCESS,
                retry_class=RetryClass.NONE,
            ))
        prior = store.get_prior("c1", 3)
        assert prior is not None
        assert prior.attempt == 2

    def test_get_prior_gap_tolerant(self, tmp_path: Path):
        """get_prior finds latest prior even with gaps in attempt numbers."""
        store = AttemptStore(tmp_path)
        # Only attempts 1 and 5 exist
        for attempt in [1, 5]:
            store.append(AttemptRecord(
                call_id="c1", attempt=attempt,
                precondition_fingerprint=f"fp{attempt}",
                etag_snapshot={},
                outcome=ActivityOutcome.SUCCESS,
                retry_class=RetryClass.NONE,
            ))
        prior = store.get_prior("c1", 5)
        assert prior is not None
        assert prior.attempt == 1

    def test_get_prior_no_prior(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        ))
        assert store.get_prior("c1", 1) is None

    def test_get_prior_wrong_call_id(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        ))
        assert store.get_prior("c2", 2) is None

    def test_get_latest(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        for i in range(3):
            store.append(AttemptRecord(
                call_id="c1", attempt=i + 1,
                precondition_fingerprint=f"fp{i}",
                etag_snapshot={},
                outcome=ActivityOutcome.SUCCESS,
                retry_class=RetryClass.NONE,
            ))
        latest = store.get_latest("c1")
        assert latest is not None
        assert latest.attempt == 3

    def test_get_latest_no_records(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        assert store.get_latest("c1") is None

    def test_malformed_line_skipped(self, tmp_path: Path):
        """Malformed trailing line (partial write from crash) is skipped."""
        store = AttemptStore(tmp_path)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        ))
        # Append malformed line (simulating crash mid-write)
        with open(store.path, "a") as f:
            f.write('{"call_id": "c1", "attempt": 2, "broken\n')
        records = store.all()
        assert len(records) == 1
        assert records[0].attempt == 1

    def test_query_by_call_id(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        ))
        store.append(AttemptRecord(
            call_id="c2", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        ))
        assert len(store.query("c1")) == 1
        assert len(store.query("c2")) == 1
        assert len(store.query("c3")) == 0


# =============================================================================
# on_attempt (15 tests)
# =============================================================================


class TestOnAttempt:
    def test_first_attempt_no_store(self):
        b = _bundle(_fact())
        result = on_attempt("c1", 1, b)
        assert result.verdict == DriftVerdict.NO_PRIOR
        assert result.retry_class == RetryClass.SAFE_TRANSIENT
        assert result.prior_fingerprint is None
        assert result.current_fingerprint == b.fingerprint()

    def test_first_attempt_with_store(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        result = on_attempt("c1", 1, b, store=store)
        assert result.verdict == DriftVerdict.NO_PRIOR

    def test_no_prior_in_store(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        result = on_attempt("c1", 2, b, store=store)
        assert result.verdict == DriftVerdict.NO_PRIOR

    def test_retry_no_drift(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        # Record attempt 1
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b.fingerprint(),
            etag_snapshot=b.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        # Retry with same bundle
        result = on_attempt("c1", 2, b, store=store)
        assert result.verdict == DriftVerdict.NO_DRIFT
        assert result.retry_class == RetryClass.SAFE_TRANSIENT
        assert result.prior_fingerprint == b.fingerprint()

    def test_retry_fingerprint_diverged(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b1 = _bundle(_fact(response_fingerprint="aaa"))
        b2 = _bundle(_fact(response_fingerprint="bbb"))
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot=b1.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b2, store=store)
        assert result.verdict == DriftVerdict.FINGERPRINT_DIVERGED
        assert result.retry_class == RetryClass.UNSAFE

    def test_retry_etag_diverged(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        f1 = _fact(etag_or_version="v1")
        f2 = _fact(etag_or_version="v2")
        b1 = _bundle(f1)
        b2 = _bundle(f2)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot=b1.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b2, store=store)
        assert result.verdict == DriftVerdict.ETAG_DIVERGED
        assert result.retry_class == RetryClass.UNSAFE
        assert result.etag_tier_used is True

    def test_retry_continuity_lost(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        f1 = _fact(etag_or_version="v1")
        f2 = _fact(etag_or_version=None)
        b1 = _bundle(f1)
        b2 = _bundle(f2)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot=b1.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b2, store=store)
        assert result.verdict == DriftVerdict.CONTINUITY_LOST
        assert result.retry_class == RetryClass.OPERATOR_REQUIRED
        assert result.etag_tier_used is True

    def test_receipt_emission(self, tmp_path: Path):
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        result = on_attempt("c1", 1, b, receipt_system=receipt_sys)
        assert result.receipt_hash is not None
        # Verify receipt was actually stored
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert len(receipts) == 1
        assert receipts[0].verdict == "observe"  # NO_PRIOR → observe

    def test_receipt_emission_block_on_divergence(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        receipt_sys = GateReceiptSystem(tmp_path)
        b1 = _bundle(_fact(response_fingerprint="aaa"))
        b2 = _bundle(_fact(response_fingerprint="bbb"))
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot=b1.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b2, store=store, receipt_system=receipt_sys)
        assert result.verdict == DriftVerdict.FINGERPRINT_DIVERGED
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert len(receipts) == 1
        assert receipts[0].verdict == "block"

    def test_receipt_emission_pass_on_no_drift(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b.fingerprint(),
            etag_snapshot=b.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b, store=store, receipt_system=receipt_sys)
        assert result.verdict == DriftVerdict.NO_DRIFT
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert len(receipts) == 1
        assert receipts[0].verdict == "pass"

    def test_drift_authoritative_without_receipt(self, tmp_path: Path):
        """Drift verdict is authoritative even without receipt system."""
        store = AttemptStore(tmp_path)
        b1 = _bundle(_fact(response_fingerprint="aaa"))
        b2 = _bundle(_fact(response_fingerprint="bbb"))
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot=b1.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b2, store=store, receipt_system=None)
        assert result.verdict == DriftVerdict.FINGERPRINT_DIVERGED
        assert result.receipt_hash is None

    def test_attempt_zero_treated_as_first(self):
        """attempt <= 1 treated as first attempt."""
        b = _bundle(_fact())
        result = on_attempt("c1", 0, b)
        assert result.verdict == DriftVerdict.NO_PRIOR

    def test_etag_tier_not_used_for_fingerprint(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b1 = _bundle(_fact(response_fingerprint="aaa"))
        b2 = _bundle(_fact(response_fingerprint="bbb"))
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot={},
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b2, store=store)
        assert result.etag_tier_used is False

    def test_gap_tolerant_prior_lookup(self, tmp_path: Path):
        """on_attempt uses gap-tolerant prior lookup (not attempt-1)."""
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        # Record attempt 1 only
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b.fingerprint(),
            etag_snapshot=b.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        # Jump to attempt 5 (gap: 2, 3, 4 missing)
        result = on_attempt("c1", 5, b, store=store)
        assert result.verdict == DriftVerdict.NO_DRIFT
        assert result.prior_fingerprint == b.fingerprint()


# =============================================================================
# record_attempt (6 tests)
# =============================================================================


class TestRecordAttempt:
    def test_basic_recording(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        record = record_attempt(
            call_id="c1", attempt=1,
            precondition_bundle=b,
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
            store=store,
        )
        assert record.call_id == "c1"
        assert record.precondition_fingerprint == b.fingerprint()
        assert record.created_at is not None

    def test_persisted_to_store(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        record_attempt(
            call_id="c1", attempt=1,
            precondition_bundle=b,
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
            store=store,
        )
        records = store.all()
        assert len(records) == 1

    def test_error_fields(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        record = record_attempt(
            call_id="c1", attempt=1,
            precondition_bundle=b,
            outcome=ActivityOutcome.BUSINESS_FAILURE,
            retry_class=RetryClass.UNSAFE,
            store=store,
            error_class=DIVERGENCE_DETECTED,
            error_message="preconditions changed",
        )
        assert record.error_class == DIVERGENCE_DETECTED
        assert record.error_message == "preconditions changed"

    def test_etag_snapshot_captured(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        f = _fact(fact_type="GetPod", subject="p", source="k8s", etag_or_version="v5")
        b = _bundle(f)
        record = record_attempt(
            call_id="c1", attempt=1,
            precondition_bundle=b,
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
            store=store,
        )
        assert record.etag_snapshot == {"GetPod:p:k8s": "v5"}

    def test_idempotency_strategy(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        record = record_attempt(
            call_id="c1", attempt=1,
            precondition_bundle=b,
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
            store=store,
            idempotency_strategy=IdempotencyStrategy.CAS_BINDING,
        )
        assert record.idempotency_strategy == IdempotencyStrategy.CAS_BINDING

    def test_receipt_hash_passthrough(self, tmp_path: Path):
        store = AttemptStore(tmp_path)
        b = _bundle(_fact())
        record = record_attempt(
            call_id="c1", attempt=1,
            precondition_bundle=b,
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
            store=store,
            receipt_hash="rh_abc123",
        )
        assert record.receipt_hash == "rh_abc123"


# =============================================================================
# Enum coverage (5 tests)
# =============================================================================


class TestEnums:
    def test_activity_outcome_values(self):
        assert len(ActivityOutcome) == 3
        assert ActivityOutcome.SUCCESS.value == "success"
        assert ActivityOutcome.BUSINESS_FAILURE.value == "business_failure"
        assert ActivityOutcome.SYSTEM_FAILURE.value == "system_failure"

    def test_retry_class_values(self):
        assert len(RetryClass) == 5
        assert RetryClass.OPERATOR_REQUIRED.value == "operator_required"

    def test_drift_verdict_values(self):
        assert len(DriftVerdict) == 5
        assert DriftVerdict.CONTINUITY_LOST.value == "continuity_lost"

    def test_idempotency_strategy_values(self):
        assert len(IdempotencyStrategy) == 4

    def test_verdict_to_retry_complete(self):
        """Every DriftVerdict maps to a RetryClass."""
        for v in DriftVerdict:
            assert v in _VERDICT_TO_RETRY

    def test_verdict_to_gate_complete(self):
        """Every DriftVerdict maps to a gate verdict."""
        for v in DriftVerdict:
            assert v in _VERDICT_TO_GATE


# =============================================================================
# Canonicalization (8 tests)
# =============================================================================


class TestCanonicalization:
    def test_fingerprint_dict_uses_canonical_json(self):
        """Fingerprint uses canonical_json (sorted keys, compact, ASCII)."""
        f = _fact()
        fp_dict = f.fingerprint_dict()
        raw = canonical_json(fp_dict)
        # Verify sorted keys
        parsed = json.loads(raw)
        assert list(parsed.keys()) == sorted(parsed.keys())

    def test_ensure_ascii(self):
        """Non-ASCII characters are escaped in canonical JSON."""
        f = _fact(subject="\u2603")
        fp_dict = f.fingerprint_dict()
        raw = canonical_json(fp_dict)
        assert b"\\u2603" in raw

    def test_fingerprint_stability_across_none_vs_empty(self):
        """None and '' produce the same fingerprint (normalization)."""
        f1 = _fact(subject=None)
        f2 = _fact(subject="")
        assert f1.fingerprint_dict() == f2.fingerprint_dict()
        assert f1.fingerprint() == f2.fingerprint()

    def test_sort_stability(self):
        """Same facts in different order → same bundle fingerprint."""
        facts = [_fact(fact_type=c) for c in "DCBA"]
        b1 = PreconditionBundle(facts)
        b2 = PreconditionBundle(list(reversed(facts)))
        assert b1.fingerprint() == b2.fingerprint()

    def test_fingerprint_format_hex(self):
        """Fingerprint is a hex string."""
        f = _fact()
        fp = f.fingerprint()
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_bundle_fingerprint_wraps_observations(self):
        """Bundle fingerprint wraps observation dicts in canonical structure."""
        f = _fact()
        b = _bundle(f)
        expected = content_hash(canonical_json({
            "observations": [f.fingerprint_dict()]
        }))
        assert b.fingerprint() == expected

    def test_no_floats_in_fingerprint(self):
        """Fingerprint dict contains only strings — no floats."""
        f = _fact()
        fp = f.fingerprint_dict()
        for v in fp.values():
            assert isinstance(v, str)

    def test_all_fingerprint_fields_present(self):
        """All 6 fingerprint fields always present in fingerprint dict."""
        f = FactObservation(fact_type="X", observed_at="t")
        fp = f.fingerprint_dict()
        expected_keys = {"fact_type", "subject", "source",
                         "request_fingerprint", "response_fingerprint",
                         "etag_or_version"}
        assert set(fp.keys()) == expected_keys


# =============================================================================
# GateReceiptSystem integration (6 tests)
# =============================================================================


class TestGateReceiptIntegration:
    def test_emit_receipt_on_no_prior(self, tmp_path: Path):
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        result = on_attempt("c1", 1, b, receipt_system=receipt_sys)
        assert result.receipt_hash is not None
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert len(receipts) == 1

    def test_receipt_gate_name(self, tmp_path: Path):
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        on_attempt("c1", 1, b, receipt_system=receipt_sys)
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert receipts[0].gate == ACTIVITY_DRIFT_GATE

    def test_receipt_evidence_bundle_keys(self, tmp_path: Path):
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        on_attempt("c1", 1, b, receipt_system=receipt_sys)
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        evidence = receipt_sys.evidence_for(receipts[0])
        assert evidence is not None
        assert "call_id" in evidence
        assert "attempt" in evidence
        assert "drift_verdict" in evidence
        assert "precondition_fingerprint" in evidence

    def test_receipt_verdict_mapping_observe(self, tmp_path: Path):
        """NO_PRIOR → observe verdict on receipt."""
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        on_attempt("c1", 1, b, receipt_system=receipt_sys)
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert receipts[0].verdict == "observe"

    def test_receipt_verdict_mapping_block(self, tmp_path: Path):
        """FINGERPRINT_DIVERGED → block verdict on receipt."""
        store = AttemptStore(tmp_path)
        receipt_sys = GateReceiptSystem(tmp_path)
        b1 = _bundle(_fact(response_fingerprint="a"))
        b2 = _bundle(_fact(response_fingerprint="b"))
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot={},
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        on_attempt("c1", 2, b2, store=store, receipt_system=receipt_sys)
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert receipts[0].verdict == "block"

    def test_receipt_verdict_mapping_warn(self, tmp_path: Path):
        """CONTINUITY_LOST → warn verdict on receipt."""
        store = AttemptStore(tmp_path)
        receipt_sys = GateReceiptSystem(tmp_path)
        f1 = _fact(etag_or_version="v1")
        f2 = _fact(etag_or_version=None)
        b1 = _bundle(f1)
        b2 = _bundle(f2)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b1.fingerprint(),
            etag_snapshot=b1.etag_snapshot(),
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        on_attempt("c1", 2, b2, store=store, receipt_system=receipt_sys)
        receipts = receipt_sys.query(gate=ACTIVITY_DRIFT_GATE)
        assert receipts[0].verdict == "warn"


# =============================================================================
# Receipt emission observability (7 tests)
# =============================================================================


class TestReceiptEmissionObservability:
    def test_emission_ok_with_receipt_system(self, tmp_path: Path):
        """receipt_emission_ok=True when receipt system succeeds."""
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        result = on_attempt("c1", 1, b, receipt_system=receipt_sys)
        assert result.receipt_emission_ok is True
        assert result.receipt_emission_error is None

    def test_emission_ok_none_without_receipt_system(self):
        """receipt_emission_ok=None when no receipt system configured."""
        b = _bundle(_fact())
        result = on_attempt("c1", 1, b, receipt_system=None)
        assert result.receipt_emission_ok is None
        assert result.receipt_emission_error is None
        assert result.receipt_hash is None

    def test_emission_ok_on_drift_check(self, tmp_path: Path):
        """receipt_emission_ok tracks success on retry path too."""
        store = AttemptStore(tmp_path)
        receipt_sys = GateReceiptSystem(tmp_path)
        b = _bundle(_fact())
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint=b.fingerprint(),
            etag_snapshot={},
            outcome=ActivityOutcome.SYSTEM_FAILURE,
            retry_class=RetryClass.SAFE_TRANSIENT,
        ))
        result = on_attempt("c1", 2, b, store=store, receipt_system=receipt_sys)
        assert result.receipt_emission_ok is True

    def test_attempt_record_emission_fields_roundtrip(self):
        """receipt_emission_ok and receipt_emission_error serialize/deserialize."""
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
            receipt_emission_ok=True,
        )
        d = r.to_dict()
        assert d["receipt_emission_ok"] is True
        r2 = AttemptRecord.from_dict(d)
        assert r2.receipt_emission_ok is True

    def test_attempt_record_emission_error_roundtrip(self):
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
            receipt_emission_ok=False,
            receipt_emission_error="OSError: disk full",
        )
        d = r.to_dict()
        assert d["receipt_emission_error"] == "OSError: disk full"
        r2 = AttemptRecord.from_dict(d)
        assert r2.receipt_emission_ok is False
        assert r2.receipt_emission_error == "OSError: disk full"

    def test_attempt_record_emission_fields_default_omitted(self):
        """receipt_emission_ok/error omitted from dict when None."""
        r = AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        )
        d = r.to_dict()
        assert "receipt_emission_ok" not in d
        assert "receipt_emission_error" not in d

    def test_drift_result_emission_fields(self):
        """DriftCheckResult carries emission tracking fields."""
        result = DriftCheckResult(
            verdict=DriftVerdict.NO_PRIOR,
            retry_class=RetryClass.SAFE_TRANSIENT,
            receipt_emission_ok=True,
        )
        assert result.receipt_emission_ok is True
        assert result.receipt_emission_error is None


# =============================================================================
# Malformed JSONL warning (2 tests)
# =============================================================================


class TestMalformedLineWarning:
    def test_malformed_line_emits_warning(self, tmp_path: Path, caplog):
        """Malformed JSONL line emits a logger.warning, not silent skip."""
        store = AttemptStore(tmp_path)
        store.append(AttemptRecord(
            call_id="c1", attempt=1,
            precondition_fingerprint="fp",
            etag_snapshot={},
            outcome=ActivityOutcome.SUCCESS,
            retry_class=RetryClass.NONE,
        ))
        with open(store.path, "a") as f:
            f.write('{"broken json\n')
        with caplog.at_level(logging.WARNING, logger="governor.governed_activity"):
            records = store.all()
        assert len(records) == 1
        assert any("malformed" in r.message.lower() for r in caplog.records)

    def test_multiple_malformed_lines_each_warned(self, tmp_path: Path, caplog):
        """Each malformed line gets its own warning."""
        store = AttemptStore(tmp_path)
        with open(store.path, "w") as f:
            f.write('{"broken1\n')
            f.write('{"broken2\n')
        with caplog.at_level(logging.WARNING, logger="governor.governed_activity"):
            records = store.all()
        assert len(records) == 0
        warning_msgs = [r for r in caplog.records if "malformed" in r.message.lower()]
        assert len(warning_msgs) == 2
