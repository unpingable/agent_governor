# SPDX-License-Identifier: Apache-2.0
"""A2: one live, non-operational traversal through the Rust transition-kernel.

A real cooked context (built by the real `run_drill` chain) is sent over real subprocess transport to the
Rust `transition-cli`; the decision is returned and recorded as a measurement receipt; then we STOP.

This exercises real orchestration + real transport WITHOUT live consequence:
- parity: the Rust decision agrees with the live Python `ChainResult` on all seven contract fields
  (the run_drill chain is the oracle);
- non-operational: `operational is False` under the drill origin (Wall-1 fence);
- no consume / no effect: the probe path holds no LinearAccountant client and records only a measurement
  receipt — the on-disk receipt store contains nothing but `transition_kernel_seam` measurements.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from governor.drill_runner import run_drill
from governor.gate_receipt import GateReceiptSystem
from governor.runtime.transition_subprocess import (
    DEFAULT_TRANSITION_CLI,
    TransitionSubprocess,
    record_transition_decision,
)

BINARY = os.environ.get("GOVERNOR_TRANSITION_CLI", DEFAULT_TRANSITION_CLI)

pytestmark = pytest.mark.skipif(
    not Path(BINARY).exists(),
    reason=f"transition-cli not built at {BINARY} (cargo build the transition-kernel)",
)


def _py_projection(result) -> dict:
    """The seven contract fields off the live Python DrillRunResult (the parity oracle)."""
    return {
        "outcome": result.outcome,
        "refusal_kind": result.refusal_kind,
        "refusing_seam": result.refusing_seam,
        "effect_count": result.effect_count,
        "consumed": result.chain_result.consumed,
        "operational": result.chain_result.operational,
        "proposal_packet_present": bool(result.proposal_packet),
    }


@pytest.mark.parametrize(
    "scenario",
    ["all-green", "wicket-denied", "replay-budget", "temporal-lapse", "temporal-lapse-twin"],
)
def test_transition_probe_agrees_with_live_chain_and_is_non_operational(scenario, tmp_path):
    # Parity oracle: the REAL Python chain over a real cooked context.
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir()
    result = run_drill(gov_dir=oracle_dir, scenario=scenario)
    py = _py_projection(result)

    # Real transport: send the cooked-context selector to the Rust kernel over a subprocess.
    probe = {"scenario": scenario, "origin_mode": "drill"}
    with TransitionSubprocess(binary_path=BINARY) as t:
        assert t.identity is not None and t.identity.binary_path == BINARY
        decision = t.decide(probe)

    assert decision is not None, "transport failed (fail-closed) — no decision"
    assert decision["decision"] in {"admit", "refuse", "escalate"}

    # Parity: the Rust decision reproduces the live Python chain, field for field.
    assert decision["verdict"] == py, f"{scenario}: Rust verdict diverged from live Python"

    # Non-operational fence: a drill origin can never be operational.
    assert decision["verdict"]["operational"] is False


def test_transition_probe_records_measurement_receipt_then_stops(tmp_path):
    probe = {"scenario": "all-green", "origin_mode": "drill"}
    with TransitionSubprocess(binary_path=BINARY) as t:
        decision = t.decide(probe)
    assert decision is not None and decision["decision"] == "admit"

    receipt_root = tmp_path / "receipts_root"
    receipt_root.mkdir()
    system = GateReceiptSystem(receipt_root)
    receipt = record_transition_decision(
        system, probe=probe, decision=decision, binary_path=BINARY
    )

    # A receipt was minted — as a MEASUREMENT (a witness), never authority.
    assert receipt.gate == "transition_kernel_seam"
    assert receipt.receipt_role == "measurement"
    assert receipt.verdict == "observe"  # admit -> observe (an observation, not a grant)

    # STOP / no consume: the only thing on disk is our transition measurement(s). No la_seam, no consume,
    # no token, no effect — the probe path holds no LA client and could not have spent anything.
    jsonl = receipt_root / "receipts" / "gate_receipts.jsonl"
    assert jsonl.exists(), "no gate receipt written"
    lines = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    assert lines, "receipt jsonl empty"
    assert all(r["gate"] == "transition_kernel_seam" for r in lines)
    assert all(r.get("receipt_role") == "measurement" for r in lines)

    # The operational fence is carried verbatim into the recorded evidence.
    assert decision["verdict"]["operational"] is False
