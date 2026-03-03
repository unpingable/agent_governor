# SPDX-License-Identifier: Apache-2.0
"""Sim → Signal pipeline adapter.

Post-run step: reads receipts produced during a sim run, derives signal
envelopes from them, emits via JsonlSink. Proves the instrumentation
spine is connected to blood flow.

Five signal kinds (full A→B chain):
  Phase A:
    - EXPOSURE_PROXY (A1): weighted denominator from receipt gate counts
    - SILENT_SUPPRESSION (A2): healthy indicator (sim is running)
    - SIGMA_RATE (A3): endorsement→invalidation rate from receipt pairs
  Phase B:
    - CAPTURE_SELF_DIAGNOSTIC (B1): advisory diagnostic from A signals
    - POSTERIOR_SHIFT_ATTRIBUTION (B3): LOO influence on B1
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SimRunContext:
    """Identity for a sim run — enough to correlate signals back to source."""

    run_id: str
    session_id: str
    scenario: str
    window_start: str  # ISO 8601 UTC (sim start time)
    window_end: str  # ISO 8601 UTC (sim end time)


def derive_signals_from_run(
    gov_dir: Path,
    ctx: SimRunContext,
) -> list[Any]:
    """Derive signal envelopes from a completed sim run's receipts.

    Reads the receipt store from gov_dir, counts by gate, derives
    EXPOSURE_PROXY via the existing pure derivation function.

    Returns list of SignalEnvelope (for testing). Also emits to
    the signals JSONL if the signals directory exists.
    """
    from governor.gate_receipt import GateReceiptSystem
    from governor.signals.emit import JsonlSink
    from governor.signals.exposure_proxy import (
        count_from_receipts,
        derive_exposure_proxy,
    )
    from governor.signals.sigma_rate import (
        ReceiptEvent,
        derive_sigma_rate,
        match_sigma_pairs,
    )
    from governor.signals.silent_suppression import (
        SuppressionIndicators,
        derive_silent_suppression,
    )
    from governor.signals.capture_self_diagnostic import (
        DiagnosticInputs,
        derive_capture_self_diagnostic,
    )
    from governor.signals.posterior_shift import derive_posterior_shift

    # 1. Load receipts
    system = GateReceiptSystem(gov_dir)
    all_receipts = system.receipt_store.all()

    if not all_receipts:
        logger.debug("sim run %s: no receipts, skipping signal derivation", ctx.run_id)
        return []

    # Shared provenance overrides for sim-derived signals
    sim_source_versions = {"scenario": ctx.scenario, "run_id": ctx.run_id}
    sim_kwargs: dict[str, Any] = {
        "window_start": ctx.window_start,
        "window_end": ctx.window_end,
        "window_kind": "sim_run",
        "emitter": "governor_sim.signal_adapter",
        "emitter_version": "1",
        "session_id": ctx.session_id,
        "source_streams": ["sim"],
        "source_versions": sim_source_versions,
        "emitted_at": ctx.window_end,
    }

    envelopes: list[Any] = []

    # 2. Derive EXPOSURE_PROXY from receipt gate counts
    components = count_from_receipts(system.receipt_store)
    if components.has_any():
        ep_envelope = derive_exposure_proxy(components, **sim_kwargs)
        envelopes.append(ep_envelope)
        logger.debug(
            "sim run %s: emitted EXPOSURE_PROXY (value=%s, quality=%s)",
            ctx.run_id,
            ep_envelope.value,
            ep_envelope.quality_status,
        )

    # 3. Derive SIGMA_RATE from endorsement→invalidation pairs
    receipt_events = [
        ReceiptEvent(
            receipt_id=r.receipt_id,
            timestamp=r.timestamp,
            verdict=r.verdict,
            subject_hash=r.subject_hash,
            gate=r.gate,
        )
        for r in all_receipts
    ]
    match_result = match_sigma_pairs(receipt_events)
    sigma_envelope = derive_sigma_rate(
        match_result,
        exposure_proxy_value=envelopes[0].value if envelopes else None,
        **sim_kwargs,
    )
    envelopes.append(sigma_envelope)
    logger.debug(
        "sim run %s: emitted SIGMA_RATE (value=%s, quality=%s, pairs=%d)",
        ctx.run_id,
        sigma_envelope.value,
        sigma_envelope.quality_status,
        len(match_result.pairs),
    )

    # 4. Derive SILENT_SUPPRESSION (A2) — sim is running, so healthy
    a2_indicators = SuppressionIndicators(
        activity_observed=True,
        in_path_evidence_present=len(all_receipts) > 0,
        daemon_reachable=True,  # sim harness is the "daemon"
    )
    a2_envelope = derive_silent_suppression(
        a2_indicators,
        source_receipt_ids=[r.receipt_id for r in all_receipts[:1]],
        **sim_kwargs,
    )
    envelopes.append(a2_envelope)
    logger.debug(
        "sim run %s: emitted SILENT_SUPPRESSION (value=%s, quality=%s)",
        ctx.run_id,
        a2_envelope.value,
        a2_envelope.quality_status,
    )

    # 5. Derive CAPTURE_SELF_DIAGNOSTIC (B1) from A signals
    a1_envelope = envelopes[0] if envelopes and envelopes[0].signal_id == "EXPOSURE_PROXY" else None
    a3_envelope = next((e for e in envelopes if e.signal_id == "SIGMA_RATE"), None)

    b1_inputs = DiagnosticInputs(
        a1_exposure_proxy=a1_envelope,
        a2_silent_suppression=a2_envelope,
        a3_sigma_rate=a3_envelope,
    )
    b1_envelope = derive_capture_self_diagnostic(
        b1_inputs,
        window_start=ctx.window_start,
        window_end=ctx.window_end,
        window_kind="sim_run",
        emitter="governor_sim.signal_adapter",
        emitter_version="1",
        session_id=ctx.session_id,
        emitted_at=ctx.window_end,
    )
    envelopes.append(b1_envelope)
    logger.debug(
        "sim run %s: emitted CAPTURE_SELF_DIAGNOSTIC (value=%s, quality=%s)",
        ctx.run_id,
        b1_envelope.value,
        b1_envelope.quality_status,
    )

    # 6. Derive POSTERIOR_SHIFT_ATTRIBUTION (B3) from A signals
    b3_envelope = derive_posterior_shift(
        a1_envelope, a2_envelope, a3_envelope,
        window_start=ctx.window_start,
        window_end=ctx.window_end,
        window_kind="sim_run",
        emitter="governor_sim.signal_adapter",
        emitter_version="1",
        session_id=ctx.session_id,
        emitted_at=ctx.window_end,
    )
    envelopes.append(b3_envelope)
    logger.debug(
        "sim run %s: emitted POSTERIOR_SHIFT_ATTRIBUTION (value=%s, quality=%s, n_influences=%d)",
        ctx.run_id,
        b3_envelope.value,
        b3_envelope.quality_status,
        len(b3_envelope.values.get("influences", [])),
    )

    # 7. Emit all envelopes to signals JSONL
    signals_dir = gov_dir / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    signals_jsonl = signals_dir / "signals.jsonl"

    sink = JsonlSink(signals_jsonl, validate=True, session_id=ctx.session_id)
    for env in envelopes:
        sink.emit(env)

    return envelopes
