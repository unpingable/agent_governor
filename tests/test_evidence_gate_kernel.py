# SPDX-License-Identifier: Apache-2.0
"""Tests for evidence_gate ↔ receipt_kernel integration.

Verifies that EvidenceGate.check() emits a complete kernel run
and that the 12 invariants can evaluate the resulting events.

Key invariant: kernel write failures must be visible (never silent green).
"""

from __future__ import annotations

import json

import pytest

from governor.evidence_gate import (
    ClaimLevel,
    CustodyScore,
    EvidenceGate,
    EvidenceGateConfig,
    EvidenceGateClaim,
    EvidenceGateOutput,
    EvidenceGateStatus,
    STATUS_TO_KERNEL_VERDICT,
)
from governor.receipt_bridge import ReceiptKernelBridge

from receipt_kernel.store_sqlite import SqliteReceiptStore
from receipt_kernel.types import Verdict

# All 12 invariants
from receipt_kernel.invariants import (
    # Structural
    LedgerChainValidInvariant,
    ReceiptCompletenessInvariant,
    EvaluationCompletenessInvariant,
    FinalizationCompletenessInvariant,
    SingleFinalizeInvariant,
    StageRequiredPathInvariant,
    # Hallucination
    ClaimsEvidenceBindingInvariant,
    ToolTraceConsistencyInvariant,
    EpistemicModeRequirementsInvariant,
    RefsClosedWorldInvariant,
    OutputBoundToClaimsInvariant,
    ConfidenceSanityInvariant,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def store(tmp_path):
    """Fresh SQLite receipt store."""
    s = SqliteReceiptStore(str(tmp_path / "test.db"), redaction_enabled=False)
    s.initialize_schema()
    yield s
    s.close()


@pytest.fixture
def bridge(store):
    """Bridge configured with a real store."""
    return ReceiptKernelBridge(
        store=store,
        policy_id="evidence_gate",
        policy_version="0.1.0",
        stage_graph_id="v1_default",
        actor_kind="test",
        actor_id="pytest",
    )


@pytest.fixture
def gate(bridge):
    """EvidenceGate with kernel bridge wired."""
    return EvidenceGate(
        config=EvidenceGateConfig(strict=False),
        kernel_bridge=bridge,
    )


@pytest.fixture
def strict_gate(bridge):
    """EvidenceGate in strict mode with kernel bridge."""
    return EvidenceGate(
        config=EvidenceGateConfig(strict=True),
        kernel_bridge=bridge,
    )


def _all_invariants():
    """Instantiate all 12 invariants."""
    return [
        LedgerChainValidInvariant(),
        ReceiptCompletenessInvariant(),
        EvaluationCompletenessInvariant(),
        FinalizationCompletenessInvariant(),
        SingleFinalizeInvariant(),
        StageRequiredPathInvariant(["START", "COLLECT", "EVALUATE", "DECIDE", "FINALIZE"]),
        ClaimsEvidenceBindingInvariant(),
        ToolTraceConsistencyInvariant(),
        EpistemicModeRequirementsInvariant(),
        RefsClosedWorldInvariant(),
        OutputBoundToClaimsInvariant(),
        ConfidenceSanityInvariant(),
    ]


# =============================================================================
# Verdict mapping (single source of truth)
# =============================================================================


class TestVerdictMapping:
    """STATUS_TO_KERNEL_VERDICT must cover all statuses with no drift."""

    def test_all_statuses_mapped(self):
        for status in EvidenceGateStatus:
            assert status.value in STATUS_TO_KERNEL_VERDICT, (
                f"{status.value} has no kernel verdict mapping"
            )

    def test_blocked_maps_to_fail(self):
        """BLOCKED is a definitive rejection, not UNKNOWN."""
        assert STATUS_TO_KERNEL_VERDICT["BLOCKED"] == "fail"

    def test_ok_maps_to_pass(self):
        assert STATUS_TO_KERNEL_VERDICT["OK"] == "pass"

    def test_warn_maps_to_warn(self):
        assert STATUS_TO_KERNEL_VERDICT["WARN"] == "warn"


# =============================================================================
# Basic wiring
# =============================================================================


class TestKernelWiring:
    """check() emits kernel events when bridge is configured."""

    def test_check_emits_kernel_run(self, gate, store):
        result = gate.check(
            task="test task",
            context="./",
            output="The function validates input correctly.",
        )
        assert result.kernel_run_id is not None
        assert result.kernel_ok is True

        # Verify events were written
        events = store.get_events(result.kernel_run_id)
        assert len(events) > 0

        # Must have RUN_START and RUN_FINALIZE
        types = [e["event_type"] for e in events]
        assert "RUN_START" in types
        assert "RUN_FINALIZE" in types

    def test_check_without_bridge_still_works(self):
        """Backward compatibility: no bridge = no kernel fields."""
        gate = EvidenceGate()
        result = gate.check(task="t", context="c", output="hello")
        assert result.kernel_run_id is None
        assert result.kernel_ok is None

    def test_kernel_run_id_in_to_dict(self, gate):
        result = gate.check(task="t", context="c", output="hello")
        d = result.to_dict()
        assert "kernel_run_id" in d
        assert d["kernel_ok"] is True

    def test_no_kernel_fields_in_dict_when_no_bridge(self):
        gate = EvidenceGate()
        result = gate.check(task="t", context="c", output="hello")
        d = result.to_dict()
        assert "kernel_run_id" not in d


# =============================================================================
# Event structure
# =============================================================================


class TestEventStructure:
    """Verify the emitted events have the right shape."""

    def test_event_sequence(self, gate, store):
        result = gate.check(task="t", context="c", output="output text")
        events = store.get_events(result.kernel_run_id)
        types = [e["event_type"] for e in events]

        # Expected: START, ADVANCE, 3x EVIDENCE_PUT, ADVANCE, EVAL, ADVANCE, DECISION, ADVANCE, FINALIZE
        assert types[0] == "RUN_START"
        assert types[-1] == "RUN_FINALIZE"
        assert types.count("EVIDENCE_PUT") == 3
        assert types.count("EVALUATION") == 1
        assert types.count("DECISION") == 1

    def test_run_start_has_mode(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        starts = store.get_events(result.kernel_run_id, event_type="RUN_START")
        assert len(starts) == 1
        meta = starts[0]["payload"]["meta"]
        assert meta["mode"] == "mixed"  # strict=False → mixed

    def test_strict_mode_records_factual(self, strict_gate, store):
        result = strict_gate.check(task="t", context="c", output="text")
        starts = store.get_events(result.kernel_run_id, event_type="RUN_START")
        assert starts[0]["payload"]["meta"]["mode"] == "factual"

    def test_evidence_blobs_stored(self, gate, store):
        result = gate.check(task="t", context="c", output="some output")
        ev_puts = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        keys = [e["payload"]["key"] for e in ev_puts]
        assert "final_output" in keys
        assert "claims_map" in keys
        assert "tool_trace" in keys

    def test_final_output_blob_retrievable(self, gate, store):
        output_text = "This is the checked output."
        result = gate.check(task="t", context="c", output=output_text)
        ev_puts = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        output_ev = [e for e in ev_puts if e["payload"]["key"] == "final_output"][0]
        sha = output_ev["payload"]["evidence"]["sha256"]
        blob_data = store.get_blob(sha)
        assert blob_data is not None
        assert blob_data.decode("utf-8") == output_text

    def test_claims_map_structure(self, gate, store):
        output = "This guarantees thread safety. Tests show it works."
        result = gate.check(task="t", context="c", output=output)
        ev_puts = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        cm_ev = [e for e in ev_puts if e["payload"]["key"] == "claims_map"][0]
        sha = cm_ev["payload"]["evidence"]["sha256"]
        raw = store.get_blob(sha)
        claims_map = json.loads(raw.decode("utf-8"))

        assert claims_map["schema_version"] == 1
        assert isinstance(claims_map["claims"], list)
        assert claims_map["output_ref"] is not None
        assert claims_map["output_sha256"] is not None

    def test_tool_trace_absent_system(self, gate, store):
        """Empty tool_trace with system='none' — not claiming tool integration."""
        result = gate.check(task="t", context="c", output="text")
        ev_puts = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        tt_ev = [e for e in ev_puts if e["payload"]["key"] == "tool_trace"][0]
        sha = tt_ev["payload"]["evidence"]["sha256"]
        raw = store.get_blob(sha)
        trace = json.loads(raw.decode("utf-8"))
        assert trace["system"] == "none"
        assert trace["calls"] == []
        # evidence_kind must be WEAK — no tool system means no oracle
        assert tt_ev["payload"]["meta"]["evidence_kind"] == "model:self_report"

    def test_evidence_kind_tags(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        ev_puts = store.get_events(result.kernel_run_id, event_type="EVIDENCE_PUT")
        kind_map = {}
        for e in ev_puts:
            key = e["payload"]["key"]
            kind = e["payload"]["meta"]["evidence_kind"]
            kind_map[key] = kind
        assert kind_map["final_output"] == "model:generated"
        assert kind_map["claims_map"] == "oracle:static_analysis"
        # tool_trace is model:self_report because evidence_gate has no tool
        # system — "no tools" is not an oracle statement, it's an absence.
        assert kind_map["tool_trace"] == "model:self_report"

    def test_evaluation_has_custody(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        evals = store.get_events(result.kernel_run_id, event_type="EVALUATION")
        assert len(evals) == 1
        payload = evals[0]["payload"]
        assert "results" in payload
        assert "overall_verdict" in payload
        # Custody score is in eval results
        custody_results = [r for r in payload["results"] if r["check"] == "custody_score"]
        assert len(custody_results) == 1

    def test_finalize_has_summary(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        fins = store.get_events(result.kernel_run_id, event_type="RUN_FINALIZE")
        assert len(fins) == 1
        summary = fins[0]["payload"]["summary"]
        assert "claim_count" in summary
        assert "status" in summary


# =============================================================================
# Claims mapping
# =============================================================================


class TestClaimsMapping:
    """Claims extracted by evidence_gate map correctly to kernel claims_map."""

    def test_hard_claim_maps_to_high_confidence(self, gate, store):
        output = "This guarantees data integrity."
        result = gate.check(task="t", context="c", output=output)
        claims_map = self._get_claims_map(store, result.kernel_run_id)
        hard_claims = [c for c in claims_map["claims"] if c["confidence"] == "high"]
        assert len(hard_claims) > 0

    def test_soft_claim_maps_to_low_confidence(self, gate, store):
        output = "This should improve performance."
        result = gate.check(task="t", context="c", output=output)
        claims_map = self._get_claims_map(store, result.kernel_run_id)
        low_claims = [c for c in claims_map["claims"] if c["confidence"] == "low"]
        assert len(low_claims) > 0

    def test_all_claims_reference_output_blob(self, gate, store):
        output = "This guarantees safety. It should improve speed."
        result = gate.check(task="t", context="c", output=output)
        claims_map = self._get_claims_map(store, result.kernel_run_id)
        for claim in claims_map["claims"]:
            assert len(claim["evidence_refs"]) > 0
            assert claim["evidence_refs"][0].startswith("blob://sha256:")

    def test_output_binding_matches_actual_blob(self, gate, store):
        output = "Some output text."
        result = gate.check(task="t", context="c", output=output)
        claims_map = self._get_claims_map(store, result.kernel_run_id)

        # output_ref must point to the final_output blob
        output_ref = claims_map["output_ref"]
        assert output_ref is not None
        sha = output_ref.replace("blob://sha256:", "")
        blob = store.get_blob(sha)
        assert blob is not None
        assert blob.decode("utf-8") == output

    def test_no_claims_produces_empty_list(self, gate, store):
        output = "Simple text with no claims."
        result = gate.check(task="t", context="c", output=output)
        claims_map = self._get_claims_map(store, result.kernel_run_id)
        assert claims_map["claims"] == []

    @staticmethod
    def _get_claims_map(store, run_id):
        ev_puts = store.get_events(run_id, event_type="EVIDENCE_PUT")
        cm_ev = [e for e in ev_puts if e["payload"]["key"] == "claims_map"][0]
        sha = cm_ev["payload"]["evidence"]["sha256"]
        return json.loads(store.get_blob(sha).decode("utf-8"))


# =============================================================================
# Structural invariants pass
# =============================================================================


class TestStructuralInvariants:
    """The 6 structural invariants must PASS on a properly emitted run."""

    def test_chain_valid(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        inv = LedgerChainValidInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_receipt_completeness(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        inv = ReceiptCompletenessInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_evaluation_completeness(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        inv = EvaluationCompletenessInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_finalization_completeness(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        inv = FinalizationCompletenessInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_single_finalize(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        inv = SingleFinalizeInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_stage_required_path(self, gate, store):
        result = gate.check(task="t", context="c", output="text")
        inv = StageRequiredPathInvariant(["START", "COLLECT", "EVALUATE", "DECIDE", "FINALIZE"])
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS


# =============================================================================
# Hallucination invariants
# =============================================================================


class TestHallucinationInvariants:
    """Hallucination invariants evaluate honestly against evidence_gate runs."""

    def test_claims_evidence_binding_passes_for_clean_output(self, gate, store):
        """Claims with evidence_refs (pointing to output blob) pass binding."""
        result = gate.check(task="t", context="c", output="Simple text.")
        inv = ClaimsEvidenceBindingInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        # No claims = PASS (nothing to bind)
        assert r.verdict == Verdict.PASS

    def test_claims_binding_with_claims(self, gate, store):
        """Output with claims — all refs point to output blob → binding passes."""
        output = "This guarantees thread safety."
        result = gate.check(task="t", context="c", output=output)
        inv = ClaimsEvidenceBindingInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_mode_requirements_pass(self, gate, store):
        """Mixed mode with claims_map present → mode requirements pass."""
        result = gate.check(task="t", context="c", output="text")
        inv = EpistemicModeRequirementsInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_refs_closed_world_pass(self, gate, store):
        """All evidence_refs come from this run's EVIDENCE_PUT events."""
        output = "This is safe and secure."
        result = gate.check(task="t", context="c", output=output)
        inv = RefsClosedWorldInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_output_bound_to_claims_pass(self, gate, store):
        """claims_map has valid output_ref/output_sha256."""
        output = "Some output."
        result = gate.check(task="t", context="c", output=output)
        inv = OutputBoundToClaimsInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_tool_trace_with_no_tools(self, gate, store):
        """Empty tool_trace + no tool_call_ids in claims → pass."""
        result = gate.check(task="t", context="c", output="text")
        inv = ToolTraceConsistencyInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_confidence_sanity_no_claims(self, gate, store):
        """No claims → confidence sanity passes trivially."""
        result = gate.check(task="t", context="c", output="Simple text.")
        inv = ConfidenceSanityInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS

    def test_confidence_sanity_flags_hard_claims(self, gate, store):
        """HARD claims → high confidence + model:generated evidence = FAIL.

        This is correct: the kernel honestly reports that evidence_gate's
        claims are backed by weak (model self-report) evidence. The fix
        path is to attach real oracle evidence (test results, profiler output).
        """
        output = "This guarantees thread safety."
        result = gate.check(task="t", context="c", output=output)
        inv = ConfidenceSanityInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.FAIL
        assert any(
            reason.code == "HIGH_CONFIDENCE_WEAK_EVIDENCE"
            for reason in r.reasons
        )

    def test_confidence_sanity_soft_claims_pass(self, gate, store):
        """SOFT claims → low confidence → no sanity issue."""
        output = "This should improve performance slightly."
        result = gate.check(task="t", context="c", output=output)

        # Verify we got soft claims
        assert any(c.level == ClaimLevel.SOFT for c in result.claims)
        # Verify no hard claims
        assert not any(c.level == ClaimLevel.HARD for c in result.claims)

        inv = ConfidenceSanityInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        # All-low confidence in mixed mode may WARN, but not FAIL
        assert r.verdict in (Verdict.PASS, Verdict.WARN)


# =============================================================================
# Full 12-invariant pass (no-claims run)
# =============================================================================


class TestFullInvariantSuite:
    """Run all 12 invariants against a real evidence_gate check."""

    def test_clean_output_passes_all_12(self, gate, store):
        """Simple output with no claims passes all 12 invariants."""
        result = gate.check(
            task="fix the login bug",
            context="./src/",
            output="Fixed the null check in auth.py line 42.",
        )
        assert result.kernel_ok is True

        ctx = {"store": store, "run_id": result.kernel_run_id}
        for inv in _all_invariants():
            r = inv.evaluate(ctx)
            assert r.verdict in (Verdict.PASS, Verdict.WARN), (
                f"{inv.invariant_id} failed: {r.verdict.value} — "
                f"{[reason.code for reason in r.reasons]}"
            )

    def test_multiple_checks_get_separate_runs(self, gate, store):
        """Each check() gets its own run_id."""
        r1 = gate.check(task="t1", context="c", output="first output")
        r2 = gate.check(task="t2", context="c", output="second output")
        assert r1.kernel_run_id != r2.kernel_run_id
        assert r1.kernel_ok is True
        assert r2.kernel_ok is True

        # Both runs have valid chains
        inv = LedgerChainValidInvariant()
        for run_id in [r1.kernel_run_id, r2.kernel_run_id]:
            r = inv.evaluate({"store": store, "run_id": run_id})
            assert r.verdict == Verdict.PASS


# =============================================================================
# Write failure protection
# =============================================================================


class TestWriteFailureProtection:
    """Kernel write failures must be visible — never silent green."""

    def test_write_failure_blocks_in_strict_mode(self, tmp_path):
        """In strict/factual mode, kernel write failure → BLOCKED."""

        class BrokenStore:
            """Store that raises on every write."""
            def ensure_run(self, *a, **kw):
                raise RuntimeError("DB write failed")

        bridge = ReceiptKernelBridge(
            store=BrokenStore(),
            policy_id="test",
            policy_version="0",
            stage_graph_id="v1_default",
        )
        original_available = type(bridge).available
        type(bridge).available = property(lambda self: True)

        try:
            gate = EvidenceGate(
                config=EvidenceGateConfig(strict=True),
                kernel_bridge=bridge,
            )
            result = gate.check(task="t", context="c", output="text")

            # In strict mode, kernel failure → BLOCKED (unverifiable = inadmissible)
            assert result.status == EvidenceGateStatus.BLOCKED
            assert result.kernel_ok is False
            assert any("kernel write failed" in r for r in result.blocking_reasons)
        finally:
            type(bridge).available = original_available

    def test_write_failure_warns_in_mixed_mode(self, tmp_path):
        """In mixed mode, kernel write failure → WARN (acceptable uncertainty)."""

        class BrokenStore:
            def ensure_run(self, *a, **kw):
                raise RuntimeError("DB write failed")

        bridge = ReceiptKernelBridge(
            store=BrokenStore(),
            policy_id="test",
            policy_version="0",
            stage_graph_id="v1_default",
        )
        original_available = type(bridge).available
        type(bridge).available = property(lambda self: True)

        try:
            gate = EvidenceGate(
                config=EvidenceGateConfig(strict=False),
                kernel_bridge=bridge,
            )
            result = gate.check(task="t", context="c", output="text")

            # In mixed mode, kernel failure → WARN (not BLOCKED)
            assert result.status == EvidenceGateStatus.WARN
            assert result.kernel_ok is False
            assert any("kernel write failed" in w for w in result.warnings)
        finally:
            type(bridge).available = original_available

    def test_write_failure_logged(self, tmp_path):
        """Write failure must appear in the event log."""

        class BrokenStore:
            def ensure_run(self, *a, **kw):
                raise RuntimeError("disk full")

        bridge = ReceiptKernelBridge(
            store=BrokenStore(),
            policy_id="test",
            policy_version="0",
            stage_graph_id="v1_default",
        )
        original_available = type(bridge).available
        type(bridge).available = property(lambda self: True)

        try:
            gate = EvidenceGate(
                config=EvidenceGateConfig(strict=False),
                kernel_bridge=bridge,
            )
            result = gate.check(task="t", context="c", output="text")

            events = gate.get_log_events()
            write_fail_events = [
                e for e in events if e.get("event") == "kernel_write_failed"
            ]
            assert len(write_fail_events) == 1
            assert "disk full" in write_fail_events[0]["error"]
        finally:
            type(bridge).available = original_available

    def test_disabled_bridge_skips_cleanly(self):
        """Bridge with no store → no kernel run, no error."""
        bridge = ReceiptKernelBridge(
            store=None, policy_id="test", policy_version="0",
            stage_graph_id="v1_default",
        )
        gate = EvidenceGate(kernel_bridge=bridge)
        result = gate.check(task="t", context="c", output="text")
        assert result.kernel_run_id is None
        assert result.kernel_ok is None


# =============================================================================
# Blocked output
# =============================================================================


class TestBlockedOutput:
    """Kernel records blocked runs honestly."""

    def test_blocked_output_records_fail_verdict(self, strict_gate, store):
        """BLOCKED status → kernel records 'fail' verdict."""
        output = "This guarantees zero downtime. Always works."
        result = strict_gate.check(task="t", context="c", output=output)
        assert result.status == EvidenceGateStatus.BLOCKED

        fins = store.get_events(result.kernel_run_id, event_type="RUN_FINALIZE")
        assert len(fins) == 1
        assert fins[0]["payload"]["overall_verdict"] == "fail"

    def test_blocked_output_still_has_valid_chain(self, strict_gate, store):
        """Even blocked runs have a valid hash chain."""
        output = "This guarantees zero downtime."
        result = strict_gate.check(task="t", context="c", output=output)
        inv = LedgerChainValidInvariant()
        r = inv.evaluate({"store": store, "run_id": result.kernel_run_id})
        assert r.verdict == Verdict.PASS
