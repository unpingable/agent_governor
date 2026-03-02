# SPDX-License-Identifier: Apache-2.0
"""Sim → Signal pipeline adapter.

Post-run step: reads receipts produced during a sim run, derives signal
envelopes from them, emits via JsonlSink. Proves the instrumentation
spine is connected to blood flow.

MVP: one signal kind (EXPOSURE_PROXY) from receipt gate counts.
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

    # 1. Count receipts by gate
    system = GateReceiptSystem(gov_dir)
    components = count_from_receipts(system.receipt_store)

    if not components.has_any():
        logger.debug("sim run %s: no receipts, skipping signal derivation", ctx.run_id)
        return []

    # 2. Derive EXPOSURE_PROXY (pure function)
    #
    # Pin emitted_at to window_end so the same run context always produces
    # the same envelope → same content_hash → dedupe via INSERT OR IGNORE
    # in SignalStore. Without this, each derivation call gets a different
    # wall-clock timestamp and bypasses dedupe.
    envelope = derive_exposure_proxy(
        components,
        window_start=ctx.window_start,
        window_end=ctx.window_end,
        window_kind="sim_run",
        emitter="governor_sim.signal_adapter",
        emitter_version="1",
        session_id=ctx.session_id,
        source_streams=["sim"],
        source_versions={"scenario": ctx.scenario, "run_id": ctx.run_id},
        emitted_at=ctx.window_end,
    )

    # 3. Emit to signals JSONL (if directory exists)
    signals_dir = gov_dir / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    signals_jsonl = signals_dir / "signals.jsonl"

    sink = JsonlSink(signals_jsonl, validate=True, session_id=ctx.session_id)
    sink.emit(envelope)

    logger.debug(
        "sim run %s: emitted EXPOSURE_PROXY (value=%s, quality=%s)",
        ctx.run_id,
        envelope.value,
        envelope.quality_status,
    )

    return [envelope]
