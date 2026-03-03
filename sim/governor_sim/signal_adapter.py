# SPDX-License-Identifier: Apache-2.0
"""Sim → Signal pipeline adapter.

Post-run step: reads receipts produced during a sim run, derives signal
envelopes from them, emits via JsonlSink. Proves the instrumentation
spine is connected to blood flow.

Two signal kinds:
  - EXPOSURE_PROXY: weighted denominator from receipt gate counts
  - SIGMA_RATE: endorsement→invalidation rate from receipt pairs
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

    # 4. Emit all envelopes to signals JSONL
    signals_dir = gov_dir / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    signals_jsonl = signals_dir / "signals.jsonl"

    sink = JsonlSink(signals_jsonl, validate=True, session_id=ctx.session_id)
    for env in envelopes:
        sink.emit(env)

    return envelopes
