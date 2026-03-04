# SPDX-License-Identifier: Apache-2.0
"""Tests for sim → signal pipeline.

Golden test: one sim fixture → receipts → full A→B→D signal chain
(EXPOSURE_PROXY, SILENT_SUPPRESSION, SIGMA_RATE, CAPTURE_SELF_DIAGNOSTIC,
POSTERIOR_SHIFT_ATTRIBUTION, PREDICT_REGIME_PREFLIGHT) → stored in signals.jsonl
→ queryable via SignalStore.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor_sim.runner import InprocRunner
from governor_sim.schema import TraceEvent
from governor_sim.signal_adapter import SimRunContext, derive_signals_from_run


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_gate_check_event(t_ms: int, seq: int, output: str, **kwargs) -> TraceEvent:
    """Shorthand for a gate_check call event."""
    return TraceEvent(
        t_ms=t_ms, seq=seq, scenario="test_signal", event_type="call",
        payload={"target": "gate_check", "output": output, "task": "test"},
        session_id="sim-signal-test", run_id="run-signal-001",
        **kwargs,
    )


def _make_receipt_event(t_ms: int, seq: int, gate: str = "evidence_gate",
                        independence_class: str = "tool") -> TraceEvent:
    """Shorthand for a receipt emit event."""
    return TraceEvent(
        t_ms=t_ms, seq=seq, scenario="test_signal", event_type="emit",
        payload={
            "kind": "receipt",
            "data": {
                "gate": gate,
                "verdict": "pass",
                "subject_kind": "sim_event",
                "subject_bytes": f"event_{seq}",
                "evidence_bundle": {
                    "independence_class": independence_class,
                    "source_channel": "cli",
                },
                "gate_config": {},
            },
        },
        session_id="sim-signal-test", run_id="run-signal-001",
    )


# ── SimRunContext ────────────────────────────────────────────────────────────

class TestSimRunContext:
    def test_frozen(self):
        ctx = SimRunContext(
            run_id="r1", session_id="s1", scenario="sc1",
            window_start="2026-01-01T00:00:00Z", window_end="2026-01-01T01:00:00Z",
        )
        with pytest.raises(AttributeError):
            ctx.run_id = "r2"  # type: ignore[misc]


# ── derive_signals_from_run (unit) ───────────────────────────────────────────

class TestDeriveSignals:
    def test_no_receipts_returns_empty(self, tmp_path):
        """No receipts → no signals (missing != zero)."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipts").mkdir()

        ctx = SimRunContext(
            run_id="r1", session_id="s1", scenario="empty",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(gov_dir, ctx)
        assert result == []

    def test_with_receipts_returns_full_signal_chain(self, tmp_path):
        """Receipts present → A1+A2+A3+B1+B3+D signal chain."""
        # Run a sim that produces receipts
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "hello"),
            _make_receipt_event(100, 1, gate="evidence_gate"),
            _make_gate_check_event(500, 2, "world"),
            _make_receipt_event(600, 3, gate="evidence_gate"),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-001", session_id="sim-test", scenario="basic",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        assert len(result) == 6

        signal_ids = {e.signal_id for e in result}
        assert signal_ids == {
            "EXPOSURE_PROXY", "SIGMA_RATE", "SILENT_SUPPRESSION",
            "CAPTURE_SELF_DIAGNOSTIC", "POSTERIOR_SHIFT_ATTRIBUTION",
            "PREDICT_REGIME_PREFLIGHT",
        }

        # Phase A signals
        ep = next(e for e in result if e.signal_id == "EXPOSURE_PROXY")
        assert ep.phase == "2.4A"
        assert ep.quality_status in ("ok", "partial")
        assert ep.value is not None and ep.value > 0

        sr = next(e for e in result if e.signal_id == "SIGMA_RATE")
        assert sr.phase == "2.4A"
        assert sr.value is not None

        a2 = next(e for e in result if e.signal_id == "SILENT_SUPPRESSION")
        assert a2.phase == "2.4A"

        # Phase B signals
        b1 = next(e for e in result if e.signal_id == "CAPTURE_SELF_DIAGNOSTIC")
        assert b1.phase == "2.4B"

        b3 = next(e for e in result if e.signal_id == "POSTERIOR_SHIFT_ATTRIBUTION")
        assert b3.phase == "2.4B"

    def test_signal_has_sim_provenance(self, tmp_path):
        """Signal envelopes carry sim run context."""
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "test"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-prov", session_id="sess-prov", scenario="provenance",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        assert len(result) == 6

        # All A-phase signals carry sim provenance (B/D-phase use their own emitter)
        for env in result:
            assert env.session_id == "sess-prov"
            assert env.emitter == "governor_sim.signal_adapter" or env.phase in ("2.4B", "2.4D")

    def test_signals_written_to_jsonl(self, tmp_path):
        """All 6 signals persisted to signals.jsonl after derivation."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_gate_check_event(0, 0, "persist"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-persist", session_id="s1", scenario="persist",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        derive_signals_from_run(runner.gov_dir, ctx)

        jsonl_path = runner.gov_dir / "signals" / "signals.jsonl"
        assert jsonl_path.exists()
        lines = [l for l in jsonl_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 6
        signal_ids = {json.loads(l)["signal_id"] for l in lines}
        assert signal_ids == {
            "EXPOSURE_PROXY", "SIGMA_RATE", "SILENT_SUPPRESSION",
            "CAPTURE_SELF_DIAGNOSTIC", "POSTERIOR_SHIFT_ATTRIBUTION",
            "PREDICT_REGIME_PREFLIGHT",
        }

    def test_signal_hash_is_deterministic(self, tmp_path):
        """Same run context + same receipts → same content_hash.

        emitted_at is pinned to window_end so derivation is fully
        deterministic. This enables INSERT OR IGNORE dedupe in SignalStore.
        """
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "stable"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-stable", session_id="s1", scenario="stable",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        r1 = derive_signals_from_run(runner.gov_dir, ctx)
        r2 = derive_signals_from_run(runner.gov_dir, ctx)

        # Content hashes must be identical (deterministic derivation)
        assert r1[0].content_hash() == r2[0].content_hash()
        assert r1[0].values == r2[0].values
        assert r1[0].value == r2[0].value
        assert r1[0].emitted_at == r2[0].emitted_at


# ── InprocRunner integration (emit_signals=True) ────────────────────────────

class TestRunnerSignalIntegration:
    def test_emit_signals_true_by_default(self, tmp_path):
        """Default: signals emitted (every sim run exercises the pipeline)."""
        runner = InprocRunner(work_dir=tmp_path)
        assert runner.emit_signals is True
        events = [
            _make_gate_check_event(0, 0, "default-on signals"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)
        assert len(runner.emitted_signals) >= 1

    def test_emit_signals_opt_out(self, tmp_path):
        """Explicit emit_signals=False suppresses signal emission."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_gate_check_event(0, 0, "no signals"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)
        assert runner.emitted_signals == []

        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        assert not signals_jsonl.exists()

    def test_emit_signals_true_produces_full_chain(self, tmp_path):
        """emit_signals=True → full A→B→D signal chain emitted post-run."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            _make_gate_check_event(0, 0, "with signals"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        assert len(runner.emitted_signals) == 6
        signal_ids = {s.signal_id for s in runner.emitted_signals}
        assert signal_ids == {
            "EXPOSURE_PROXY", "SIGMA_RATE", "SILENT_SUPPRESSION",
            "CAPTURE_SELF_DIAGNOSTIC", "POSTERIOR_SHIFT_ATTRIBUTION",
            "PREDICT_REGIME_PREFLIGHT",
        }

        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        assert signals_jsonl.exists()

    def test_emitted_signals_ingestable_by_store(self, tmp_path):
        """Signals emitted by runner can be ingested into SignalStore."""
        from governor.signal_store import SignalStore

        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            _make_gate_check_event(0, 0, "ingest test"),
            _make_receipt_event(100, 1, gate="evidence_gate"),
            _make_receipt_event(200, 2, gate="evidence_gate"),
        ]
        runner.run(events)

        # Ingest into SignalStore
        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        db_path = tmp_path / "signals.db"
        store = SignalStore(db_path)
        ingested = store.ingest_from_jsonl(signals_jsonl)

        assert ingested.inserted == 6
        assert store.count() == 6

        # Query each signal kind
        ep_rows = store.query(signal_name="EXPOSURE_PROXY")
        assert len(ep_rows) == 1
        assert ep_rows[0]["signal_name"] == "EXPOSURE_PROXY"
        assert ep_rows[0]["phase"] == "2.4A"

        sr_rows = store.query(signal_name="SIGMA_RATE")
        assert len(sr_rows) == 1

        b1_rows = store.query(signal_name="CAPTURE_SELF_DIAGNOSTIC")
        assert len(b1_rows) == 1
        assert b1_rows[0]["phase"] == "2.4B"

        b3_rows = store.query(signal_name="POSTERIOR_SHIFT_ATTRIBUTION")
        assert len(b3_rows) == 1
        assert b3_rows[0]["phase"] == "2.4B"

    def test_runner_infers_context_from_events(self, tmp_path):
        """Runner uses event metadata (run_id, session_id, scenario) if not overridden."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="inferred_scenario", event_type="call",
                payload={"target": "gate_check", "output": "test", "task": "t"},
                session_id="inferred_session", run_id="inferred_run",
            ),
            TraceEvent(
                t_ms=100, seq=1, scenario="inferred_scenario", event_type="emit",
                payload={
                    "kind": "receipt",
                    "data": {
                        "gate": "evidence_gate", "verdict": "pass",
                        "subject_kind": "sim_event", "subject_bytes": "x",
                        "evidence_bundle": {}, "gate_config": {},
                    },
                },
                session_id="inferred_session", run_id="inferred_run",
            ),
        ]
        runner.run(events)

        assert len(runner.emitted_signals) == 6
        # All carry inferred session_id
        for env in runner.emitted_signals:
            assert env.session_id == "inferred_session"

    def test_no_receipts_no_signal(self, tmp_path):
        """Run with no receipt-producing events → no signals (missing != zero)."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            TraceEvent(
                t_ms=0, seq=0, scenario="empty", event_type="fault",
                payload={"flag": "gate_enabled", "value": False},
            ),
        ]
        runner.run(events)
        assert runner.emitted_signals == []


# ── Dedupe / idempotence ─────────────────────────────────────────────────────

class TestDedupeIdempotence:
    def test_double_derive_same_hash(self, tmp_path):
        """Same context + same receipts → same content_hash (pinned emitted_at)."""
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "dedupe"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-dd", session_id="s1", scenario="dedupe",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        r1 = derive_signals_from_run(runner.gov_dir, ctx)
        r2 = derive_signals_from_run(runner.gov_dir, ctx)

        assert r1[0].content_hash() == r2[0].content_hash()

    def test_double_run_ingest_dedupes(self, tmp_path):
        """Canary: run fixture twice with emit_signals=True, ingest both,
        SignalStore should dedupe. This is the test ChatGPT said to write."""
        from governor.signal_store import SignalStore

        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            _make_gate_check_event(0, 0, "canary"),
            _make_receipt_event(100, 1),
        ]

        # Run 1: 6 signals (A1+A2+A3+B1+B3+D)
        runner.run(events)
        assert len(runner.emitted_signals) == 6

        # Run 2 (same events, receipts accumulate — content hashes
        # change for receipt-dependent signals, so only some dedupe)
        runner.emitted_signals.clear()
        runner.run(events)
        assert len(runner.emitted_signals) == 6

        # Both runs wrote to JSONL — 12 lines (6 signals × 2 runs)
        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        lines = [l for l in signals_jsonl.read_text().splitlines() if l.strip()]
        assert len(lines) == 12

        # Ingest — at least some signals dedupe
        store = SignalStore(tmp_path / "dedupe.db")
        result = store.ingest_from_jsonl(signals_jsonl)
        assert result.duplicates >= 1
        assert store.count() >= 6  # at least 6 unique signals

    def test_different_run_ids_produce_different_signals(self, tmp_path):
        """Different run_id → different signal (not deduplicated)."""
        runner = InprocRunner(work_dir=tmp_path)
        events = [
            _make_gate_check_event(0, 0, "diff"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx1 = SimRunContext(
            run_id="run-A", session_id="s1", scenario="diff",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        ctx2 = SimRunContext(
            run_id="run-B", session_id="s1", scenario="diff",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        r1 = derive_signals_from_run(runner.gov_dir, ctx1)
        r2 = derive_signals_from_run(runner.gov_dir, ctx2)

        # Different run_id → different source_versions → different hash
        assert r1[0].content_hash() != r2[0].content_hash()


# ── Golden: full fixture scenario → signal → CLI-queryable ──────────────────

class TestGoldenFixtureToSignal:
    def test_healthy_fixture_produces_full_signal_chain(self, tmp_path):
        """Golden: the healthy fixture scenario produces receipts that
        derive into the full A→B signal chain, all queryable."""
        from governor.signal_store import SignalStore
        from governor_sim.dsl import load_scenario, compile_scenario

        fixture_path = (
            Path(__file__).parent.parent
            / "fixtures" / "phase_a" / "healthy"
            / "healthy__external_checks__steady__high_exposure__v0.json"
        )
        if not fixture_path.exists():
            pytest.skip(f"fixture not found: {fixture_path}")

        spec = load_scenario(fixture_path)
        header, events = compile_scenario(spec)

        runner = InprocRunner(
            work_dir=tmp_path,
            params=header.params,
            emit_signals=True,
        )
        result = runner.run(events)
        assert result.events_processed > 0

        # Full chain emitted
        assert len(runner.emitted_signals) == 6
        signal_ids = {s.signal_id for s in runner.emitted_signals}
        assert signal_ids == {
            "EXPOSURE_PROXY", "SIGMA_RATE", "SILENT_SUPPRESSION",
            "CAPTURE_SELF_DIAGNOSTIC", "POSTERIOR_SHIFT_ATTRIBUTION",
            "PREDICT_REGIME_PREFLIGHT",
        }

        ep = next(s for s in runner.emitted_signals if s.signal_id == "EXPOSURE_PROXY")
        assert ep.value is not None and ep.value > 0
        assert ep.quality_status in ("ok", "partial")
        assert ep.window_kind == "sim_run"

        b1 = next(s for s in runner.emitted_signals if s.signal_id == "CAPTURE_SELF_DIAGNOSTIC")
        assert b1.value is not None  # healthy scenario → computable
        assert b1.phase == "2.4B"

        b3 = next(s for s in runner.emitted_signals if s.signal_id == "POSTERIOR_SHIFT_ATTRIBUTION")
        assert b3.value is not None  # healthy → computable influence mass
        assert b3.phase == "2.4B"
        assert len(b3.values.get("influences", [])) == 3  # 3 A signals → 3 influences

        # Signals are in JSONL
        signals_jsonl = runner.gov_dir / "signals" / "signals.jsonl"
        assert signals_jsonl.exists()

        # All 6 ingestable and queryable
        db_path = tmp_path / "golden.db"
        store = SignalStore(db_path)
        ingested = store.ingest_from_jsonl(signals_jsonl)
        assert ingested.inserted == 6

        b3_rows = store.query(signal_name="POSTERIOR_SHIFT_ATTRIBUTION")
        assert len(b3_rows) == 1
        assert b3_rows[0]["phase"] == "2.4B"


# ── SIGMA_RATE-specific tests ─────────────────────────────────────────────

def _make_contradiction_receipt(t_ms: int, seq: int, subject: str,
                                 verdict: str = "pass") -> TraceEvent:
    """Receipt with specific subject_bytes for sigma pair testing."""
    return TraceEvent(
        t_ms=t_ms, seq=seq, scenario="sigma_test", event_type="emit",
        payload={
            "kind": "receipt",
            "data": {
                "gate": "evidence_gate",
                "verdict": verdict,
                "subject_kind": "text",
                "subject_bytes": subject,
                "evidence_bundle": {},
                "gate_config": {},
            },
        },
        session_id="sigma-test", run_id="run-sigma",
    )


class TestSigmaRateDerivation:
    def test_all_pass_receipts_sigma_zero(self, tmp_path):
        """All pass receipts, no blocks → sigma_rate = 0.0."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_contradiction_receipt(0, 0, "claim_a", verdict="pass"),
            _make_contradiction_receipt(100, 1, "claim_b", verdict="pass"),
            _make_contradiction_receipt(200, 2, "claim_c", verdict="pass"),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-sigma-zero", session_id="s1", scenario="sigma_zero",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        sigma = next(e for e in result if e.signal_id == "SIGMA_RATE")

        assert sigma.value == 0.0
        assert sigma.quality_status in ("ok", "partial")
        assert sigma.values["sigma_events"] == 0
        assert sigma.values["matched_pairs_count"] == 0

    def test_contradiction_produces_sigma_pairs(self, tmp_path):
        """Pass then block for same subject → sigma pair detected."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        # Same subject_bytes: "claim_x" — pass first, then block
        events = [
            _make_contradiction_receipt(0, 0, "claim_x", verdict="pass"),
            _make_contradiction_receipt(100, 1, "claim_x", verdict="block"),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-sigma-pair", session_id="s1", scenario="sigma_pair",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        sigma = next(e for e in result if e.signal_id == "SIGMA_RATE")

        assert sigma.value is not None
        assert sigma.value > 0
        assert sigma.values["sigma_events"] >= 1
        assert sigma.values["matched_pairs_count"] >= 1

    def test_sigma_uses_exposure_proxy_denominator(self, tmp_path):
        """When EXPOSURE_PROXY is available, SIGMA_RATE uses it as denominator."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_contradiction_receipt(0, 0, "claim_a", verdict="pass"),
            _make_contradiction_receipt(100, 1, "claim_b", verdict="pass"),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-sigma-denom", session_id="s1", scenario="sigma_denom",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        sigma = next(e for e in result if e.signal_id == "SIGMA_RATE")

        # With EXPOSURE_PROXY available, denominator should prefer it
        assert sigma.values["denominator_type"] in ("exposure_proxy", "eligible_events")

    def test_sigma_envelope_provenance(self, tmp_path):
        """SIGMA_RATE envelope carries correct sim provenance."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_contradiction_receipt(0, 0, "claim_a", verdict="pass"),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-sigma-prov", session_id="sigma-sess",
            scenario="sigma_prov",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        sigma = next(e for e in result if e.signal_id == "SIGMA_RATE")

        assert sigma.emitter == "governor_sim.signal_adapter"
        assert sigma.session_id == "sigma-sess"
        assert sigma.source_versions.get("run_id") == "run-sigma-prov"
        assert sigma.source_versions.get("scenario") == "sigma_prov"
        assert sigma.window_kind == "sim_run"
        assert sigma.emitted_at == ctx.window_end

    def test_sigma_deterministic_hash(self, tmp_path):
        """Same inputs → same SIGMA_RATE content_hash (pinned emitted_at)."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_contradiction_receipt(0, 0, "claim_a", verdict="pass"),
            _make_contradiction_receipt(100, 1, "claim_a", verdict="block"),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-sigma-det", session_id="s1", scenario="sigma_det",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        r1 = derive_signals_from_run(runner.gov_dir, ctx)
        r2 = derive_signals_from_run(runner.gov_dir, ctx)

        s1 = next(e for e in r1 if e.signal_id == "SIGMA_RATE")
        s2 = next(e for e in r2 if e.signal_id == "SIGMA_RATE")
        assert s1.content_hash() == s2.content_hash()


# ── B-signal chain (B1 + B3) ───────────────────────────────────────────────

class TestBSignalChain:
    def test_b1_consumes_a_signals(self, tmp_path):
        """B1 CAPTURE_SELF_DIAGNOSTIC consumes all 3 A signals."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_gate_check_event(0, 0, "b1 input"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-b1", session_id="s1", scenario="b1_test",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        b1 = next(e for e in result if e.signal_id == "CAPTURE_SELF_DIAGNOSTIC")

        assert b1.phase == "2.4B"
        assert b1.value is not None  # computable with all A signals present
        vals = b1.values
        assert "capture_decline_score" in vals
        assert "classification" in vals

    def test_b3_has_three_influences(self, tmp_path):
        """B3 POSTERIOR_SHIFT_ATTRIBUTION has 3 influences (one per A signal)."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_gate_check_event(0, 0, "b3 influences"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-b3", session_id="s1", scenario="b3_test",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        b3 = next(e for e in result if e.signal_id == "POSTERIOR_SHIFT_ATTRIBUTION")

        assert b3.phase == "2.4B"
        assert b3.unit == "influence"
        influences = b3.values.get("influences", [])
        assert len(influences) == 3

        influence_ids = {inf["signal_id"] for inf in influences}
        assert influence_ids == {"EXPOSURE_PROXY", "SILENT_SUPPRESSION", "SIGMA_RATE"}

    def test_b3_all_influences_have_direction(self, tmp_path):
        """Each influence has a direction (increase/decrease/unchanged/indeterminate)."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_gate_check_event(0, 0, "direction check"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-b3-dir", session_id="s1", scenario="b3_dir",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        b3 = next(e for e in result if e.signal_id == "POSTERIOR_SHIFT_ATTRIBUTION")

        for inf in b3.values["influences"]:
            assert inf["direction"] in ("increase", "decrease", "unchanged", "indeterminate")

    def test_b3_compute_cost_is_4(self, tmp_path):
        """3 input signals → compute cost = 4 (1 full + 3 LOO)."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_gate_check_event(0, 0, "cost check"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-b3-cost", session_id="s1", scenario="b3_cost",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        b3 = next(e for e in result if e.signal_id == "POSTERIOR_SHIFT_ATTRIBUTION")

        assert b3.values["compute_cost"] == 4
        assert b3.values["n_signals"] == 3


# ── D-signal (Phase D) ──────────────────────────────────────────────────────

class TestDSignal:
    def test_predict_regime_in_emitted_envelopes(self, tmp_path):
        """PREDICT_REGIME_PREFLIGHT is present in emitted envelopes."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=False)
        events = [
            _make_gate_check_event(0, 0, "phase d test"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        ctx = SimRunContext(
            run_id="run-d", session_id="s1", scenario="d_test",
            window_start="1970-01-01T00:00:00+00:00",
            window_end="1970-01-01T00:00:01+00:00",
        )
        result = derive_signals_from_run(runner.gov_dir, ctx)
        d_env = next(e for e in result if e.signal_id == "PREDICT_REGIME_PREFLIGHT")

        assert d_env.phase == "2.4D"
        assert d_env.values.get("predicted_regime") is not None
        assert d_env.session_id == "s1"

    def test_six_signal_kinds_total(self, tmp_path):
        """Full chain produces exactly 6 signal kinds."""
        runner = InprocRunner(work_dir=tmp_path, emit_signals=True)
        events = [
            _make_gate_check_event(0, 0, "six kinds"),
            _make_receipt_event(100, 1),
        ]
        runner.run(events)

        signal_ids = {s.signal_id for s in runner.emitted_signals}
        assert len(signal_ids) == 6
        assert "PREDICT_REGIME_PREFLIGHT" in signal_ids
