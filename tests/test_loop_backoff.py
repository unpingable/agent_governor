# SPDX-License-Identifier: Apache-2.0
"""Tests for epistemic backoff (loop-protocol §11.1 mechanization).

Backlog `epistemic-backoff-mechanization` names four acceptance criteria;
each has a section below: (1) the probe wall audits itself from the receipt
trail; (2) the confusion receipt carries the §1 schema verbatim; (3) the
correlated-confusion audit flags environment-level failure; (4) failure
matching is by CLASS, never exact string.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.gate_receipt import EvidenceStore, ReceiptStore
from governor.loop_backoff import (
    Attempt,
    BackoffThresholds,
    FailureClass,
    Mode,
    build_confusion_bundle,
    burn_per_progress,
    correlated_confusion_audit,
    emit_confusion_receipt,
    evaluate_backoff,
    probe_wall_audit,
)


def _attempt(cls: FailureClass, spent: float = 1.0, receipts: int = 1) -> Attempt:
    return Attempt(
        slice_id="slice-x",
        failure_class=cls,
        capacity_spent=spent,
        slice_advancing_receipts=receipts,
    )


class TestLadder:
    def test_single_failure_allows_one_retry(self):
        verdict = evaluate_backoff([_attempt(FailureClass.TEST_FAILURE)])
        assert verdict.prescribed_next_mode == Mode.RETRY
        assert not verdict.confusion_receipt_required

    def test_same_class_twice_forbids_retry(self):
        """A third try is superstition — the transient hypothesis is dead."""
        verdict = evaluate_backoff(
            [_attempt(FailureClass.TEST_FAILURE), _attempt(FailureClass.TEST_FAILURE)]
        )
        assert verdict.prescribed_next_mode == Mode.PROBE
        assert verdict.inferred_signature == "dead_transient_hypothesis"
        assert verdict.confusion_receipt_required

    def test_distinct_classes_is_model_mismatch(self):
        verdict = evaluate_backoff(
            [_attempt(FailureClass.TEST_FAILURE), _attempt(FailureClass.TOOL_ERROR)]
        )
        assert verdict.prescribed_next_mode == Mode.PROBE
        assert verdict.inferred_signature == "model_mismatch"
        assert verdict.confusion_receipt_required

    def test_burn_soft_forces_probe_even_on_single_failure(self):
        verdict = evaluate_backoff(
            [_attempt(FailureClass.TEST_FAILURE, spent=5.0, receipts=1)],
            thresholds=BackoffThresholds(burn_soft=3.0, burn_hard=10.0),
        )
        assert verdict.prescribed_next_mode == Mode.PROBE
        assert verdict.inferred_signature == "capacity_flail_soft"

    def test_burn_hard_halts_over_everything(self):
        verdict = evaluate_backoff(
            [_attempt(FailureClass.TEST_FAILURE, spent=50.0, receipts=1)],
            probe_completed=True,  # even the post-probe ladder yields to hard burn
        )
        assert verdict.prescribed_next_mode == Mode.HALT
        assert verdict.inferred_signature == "capacity_flail_hard"

    def test_spend_with_zero_progress_is_infinite_burn(self):
        assert burn_per_progress([_attempt(FailureClass.TOOL_ERROR, 2.0, 0)]) == float("inf")
        verdict = evaluate_backoff([_attempt(FailureClass.TOOL_ERROR, 2.0, 0)])
        assert verdict.prescribed_next_mode == Mode.HALT

    def test_no_spend_is_no_burn_signal(self):
        assert burn_per_progress([_attempt(FailureClass.TOOL_ERROR, 0.0, 0)]) is None

    def test_escalation_illegal_until_probe_pass(self):
        """Tier escalation is never a retry substitute."""
        verdict = evaluate_backoff(
            [_attempt(FailureClass.TEST_FAILURE), _attempt(FailureClass.TEST_FAILURE)],
            probe_completed=False,
        )
        assert verdict.prescribed_next_mode != Mode.ESCALATE_ONCE

    def test_post_probe_escalates_exactly_once_then_parks(self):
        attempts = [_attempt(FailureClass.TEST_FAILURE), _attempt(FailureClass.TOOL_ERROR)]
        first = evaluate_backoff(attempts, probe_completed=True, escalation_used=False)
        assert first.prescribed_next_mode == Mode.ESCALATE_ONCE
        second = evaluate_backoff(attempts, probe_completed=True, escalation_used=True)
        assert second.prescribed_next_mode == Mode.PARK

    def test_empty_attempts_refuses(self):
        with pytest.raises(ValueError):
            evaluate_backoff([])


class TestClassNotString:
    """Acceptance 4 — matching is by CLASS, never exact string."""

    def test_attempt_carries_no_free_string_to_match_on(self):
        """Structural: the Attempt record has no message/detail field, so
        string matching is unrepresentable, not merely discouraged."""
        fields = {f for f in Attempt.__dataclass_fields__}
        assert fields == {
            "slice_id", "failure_class", "capacity_spent",
            "slice_advancing_receipts", "at",
        }

    def test_failure_class_is_a_closed_enum_with_honest_unknown(self):
        assert FailureClass("unclassified") is FailureClass.UNCLASSIFIED
        with pytest.raises(ValueError):
            FailureClass("weird_new_failure")

    def test_unclassified_repeats_count_like_any_class(self):
        """Two unknowns in a row are still 'the same thing keeps happening'."""
        verdict = evaluate_backoff(
            [_attempt(FailureClass.UNCLASSIFIED), _attempt(FailureClass.UNCLASSIFIED)]
        )
        assert verdict.prescribed_next_mode == Mode.PROBE
        assert verdict.inferred_signature == "dead_transient_hypothesis"


class TestConfusionReceipt:
    """Acceptance 2 — the §1 schema, verbatim."""

    REQUIRED_FIELDS = {
        "slice_id", "attempt_count", "failure_classes_seen",
        "repeated_count", "distinct_count", "capacity_spent",
        "slice_advancing_receipts", "burn_per_progress",
        "inferred_signature", "prescribed_next_mode",
    }

    def _bundle(self):
        attempts = [
            _attempt(FailureClass.TEST_FAILURE, spent=2.0, receipts=1),
            _attempt(FailureClass.TOOL_ERROR, spent=3.0, receipts=0),
        ]
        verdict = evaluate_backoff(attempts)
        return build_confusion_bundle("slice-x", attempts, verdict)

    def test_bundle_carries_every_schema_field(self):
        bundle = self._bundle()
        assert self.REQUIRED_FIELDS <= set(bundle)
        assert bundle["schema"] == "confusion-receipt/v1"
        assert bundle["attempt_count"] == 2
        assert bundle["failure_classes_seen"] == ["test_failure", "tool_error"]
        assert bundle["capacity_spent"] == 5.0
        assert bundle["prescribed_next_mode"] == "probe"

    def test_infinite_burn_serializes_explicitly(self):
        attempts = [_attempt(FailureClass.TOOL_ERROR, spent=2.0, receipts=0)]
        verdict = evaluate_backoff(attempts)
        bundle = build_confusion_bundle("slice-x", attempts, verdict)
        assert bundle["burn_per_progress"] == "inf"

    def test_emission_gives_custody_and_round_trips(self, tmp_path: Path):
        receipt_store = ReceiptStore(tmp_path)
        evidence_store = EvidenceStore(tmp_path)
        bundle = self._bundle()

        receipt = emit_confusion_receipt(
            bundle, receipt_store=receipt_store, evidence_store=evidence_store
        )

        assert receipt.gate == "loop_backoff"
        assert receipt.verdict == "observe"  # a confusion receipt authorizes nothing
        stored = evidence_store.get(receipt.evidence_hash)
        assert stored == bundle  # content-addressed round trip
        assert len(receipt_store.all()) == 1


class TestProbeWall:
    """Acceptance 1 — probe sessions emit zero mutation receipts,
    checkable mechanically from the trail after the fact."""

    W0, W1 = "2026-07-15T10:00:00Z", "2026-07-15T11:00:00Z"

    def _event(self, kind: str, ts: str, action_class: str | None = None):
        payload = {"action_class": action_class} if action_class else {}
        return {"kind": kind, "ts": ts, "payload": payload}

    def test_read_only_probe_window_is_clean(self):
        events = [
            self._event("tool_call_allowed", "2026-07-15T10:10:00Z", "read"),
            self._event("tool_call_proposed", "2026-07-15T10:20:00Z", "write"),
        ]
        result = probe_wall_audit(events, window_start=self.W0, window_end=self.W1)
        assert result.clean
        assert result.breach_count == 0

    def test_probe_that_patched_something_is_evidenced_after_the_fact(self):
        events = [self._event("tool_call_allowed", "2026-07-15T10:30:00Z", "write")]
        result = probe_wall_audit(events, window_start=self.W0, window_end=self.W1)
        assert not result.clean
        assert result.breach_count == 1
        assert result.mutation_events[0]["payload"]["action_class"] == "write"

    def test_communicate_breaches_the_wall_too(self):
        events = [self._event("tool_call_allowed", "2026-07-15T10:30:00Z", "communicate")]
        result = probe_wall_audit(events, window_start=self.W0, window_end=self.W1)
        assert not result.clean

    def test_mutation_outside_the_window_is_not_a_breach(self):
        events = [
            self._event("tool_call_allowed", "2026-07-15T09:59:59Z", "write"),
            self._event("tool_call_allowed", "2026-07-15T11:00:00Z", "write"),  # end exclusive
        ]
        result = probe_wall_audit(events, window_start=self.W0, window_end=self.W1)
        assert result.clean

    def test_a_proposal_is_not_a_mutation(self):
        """Proposed-but-never-allowed writes did not cross the gate."""
        events = [self._event("tool_call_proposed", "2026-07-15T10:30:00Z", "write")]
        result = probe_wall_audit(events, window_start=self.W0, window_end=self.W1)
        assert result.clean


class TestCorrelatedConfusion:
    """Acceptance 3 — N>=2 principals on unrelated slices in one window
    flags environment-level diagnosis (morning-audit obligation)."""

    def _emit(self, tmp_path: Path, slice_id: str, principal: str, ts: str):
        attempts = [
            Attempt(slice_id, FailureClass.TOOL_ERROR),
            Attempt(slice_id, FailureClass.TIMEOUT),
        ]
        verdict = evaluate_backoff(attempts)
        bundle = build_confusion_bundle(slice_id, attempts, verdict)
        emit_confusion_receipt(
            bundle,
            receipt_store=ReceiptStore(tmp_path),
            evidence_store=EvidenceStore(tmp_path),
            principal_id=principal,
            timestamp=ts,
        )

    def test_two_principals_two_slices_one_window_flags_environment(self, tmp_path):
        self._emit(tmp_path, "slice-a", "agent-1", "2026-07-15T10:00:00+00:00")
        self._emit(tmp_path, "slice-b", "agent-2", "2026-07-15T10:20:00+00:00")

        findings = correlated_confusion_audit(
            tmp_path / "receipts" / "gate_receipts.jsonl", tmp_path
        )
        assert len(findings) == 1
        assert findings[0].principal_ids == ("agent-1", "agent-2")
        assert set(findings[0].slice_ids) == {"slice-a", "slice-b"}
        assert "environment-level" in findings[0].describe()

    def test_same_slice_does_not_correlate(self, tmp_path):
        """Two agents confused on the SAME slice is a slice problem."""
        self._emit(tmp_path, "slice-a", "agent-1", "2026-07-15T10:00:00+00:00")
        self._emit(tmp_path, "slice-a", "agent-2", "2026-07-15T10:20:00+00:00")
        assert correlated_confusion_audit(
            tmp_path / "receipts" / "gate_receipts.jsonl", tmp_path
        ) == []

    def test_one_principal_does_not_correlate(self, tmp_path):
        self._emit(tmp_path, "slice-a", "agent-1", "2026-07-15T10:00:00+00:00")
        self._emit(tmp_path, "slice-b", "agent-1", "2026-07-15T10:20:00+00:00")
        assert correlated_confusion_audit(
            tmp_path / "receipts" / "gate_receipts.jsonl", tmp_path
        ) == []

    def test_outside_window_does_not_correlate(self, tmp_path):
        self._emit(tmp_path, "slice-a", "agent-1", "2026-07-15T10:00:00+00:00")
        self._emit(tmp_path, "slice-b", "agent-2", "2026-07-15T12:00:01+00:00")
        assert correlated_confusion_audit(
            tmp_path / "receipts" / "gate_receipts.jsonl", tmp_path,
            window_seconds=3600,
        ) == []

    def test_missing_trail_is_empty_not_error(self, tmp_path):
        assert correlated_confusion_audit(
            tmp_path / "receipts" / "gate_receipts.jsonl", tmp_path
        ) == []


class TestMorningAuditWiring:
    """Acceptance 3, second half — the audit RUNS as part of --check."""

    def test_correlated_confusion_surfaces_as_a_consistency_finding(self, tmp_path):
        import governor.portfolio_audit as audit

        root = tmp_path / "ag"
        gov = root / ".governor"
        (gov / "backlog").mkdir(parents=True)
        (gov / "loop.json").write_text("{}")

        for slice_id, principal, ts in (
            ("slice-a", "agent-1", "2026-07-15T10:00:00+00:00"),
            ("slice-b", "agent-2", "2026-07-15T10:20:00+00:00"),
        ):
            attempts = [
                Attempt(slice_id, FailureClass.TOOL_ERROR),
                Attempt(slice_id, FailureClass.TIMEOUT),
            ]
            bundle = build_confusion_bundle(
                slice_id, attempts, evaluate_backoff(attempts)
            )
            emit_confusion_receipt(
                bundle,
                receipt_store=ReceiptStore(gov),
                evidence_store=EvidenceStore(gov),
                principal_id=principal,
                timestamp=ts,
            )

        findings = audit.collect_consistency_findings(root)
        codes = [f.code for f in findings]
        assert "correlated_confusion_environmental" in codes
        hit = next(f for f in findings if f.code == "correlated_confusion_environmental")
        assert "environment-level" in hit.ground_truth

    def test_quiet_trail_adds_no_finding(self, tmp_path):
        import governor.portfolio_audit as audit

        root = tmp_path / "ag"
        (root / ".governor" / "backlog").mkdir(parents=True)
        (root / ".governor" / "loop.json").write_text("{}")

        codes = {f.code for f in audit.collect_consistency_findings(root)}
        assert "correlated_confusion_environmental" not in codes
