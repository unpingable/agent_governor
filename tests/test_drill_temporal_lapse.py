# SPDX-License-Identifier: Apache-2.0
"""Drill-level temporal-lapse pair — the demo's Act-1 contrast end to end.

The corpus contract pins the verdict + block; these pin the chain-shape
invariants the corpus does not: on lapse the standing-spendability gate refuses
BEFORE LA is touched (the lapse costs no budget), and the legitimate twin runs
the identical gauntlet to a real consume.
"""

from __future__ import annotations

from pathlib import Path

from governor.drill_runner import (
    SCENARIO_TEMPORAL_LAPSE,
    SCENARIO_TEMPORAL_LAPSE_TWIN,
    run_drill,
)


def test_lapse_refuses_at_spendability_seam_without_spending(tmp_path: Path):
    r = run_drill(gov_dir=tmp_path, scenario=SCENARIO_TEMPORAL_LAPSE)
    assert r.outcome == "refused"
    assert r.refusal_kind == "standing_before_spendability_not_bounded"
    assert r.refusing_seam == "standing_spendability_seam"
    # The lapse must not cost budget: no effect, and LA is never invoked.
    assert r.effect_count == 0
    assert r.downstream_call_counts.get("la_request_capacity", 0) == 0
    assert r.downstream_call_counts.get("la_consume", 0) == 0
    # Standing + wicket DID fire (the chain reached the gate, then refused).
    assert r.downstream_call_counts.get("standing_verify", 0) == 1
    assert r.downstream_call_counts.get("wicket_check", 0) == 1
    # Both clocks and the gap are on the refusal block.
    assert r.spendability_block is not None
    assert r.spendability_block["gap"] == 1
    assert r.spendability_block["clock_basis"] == "single_host_monotonic"
    # No proposal packet on a refusal.
    assert r.proposal_packet == {}


def test_twin_runs_identical_gauntlet_to_a_real_consume(tmp_path: Path):
    r = run_drill(gov_dir=tmp_path, scenario=SCENARIO_TEMPORAL_LAPSE_TWIN)
    assert r.outcome == "consumed"
    assert r.refusal_kind is None
    assert r.effect_count == 1
    # The twin reaches LA and consumes exactly once.
    assert r.downstream_call_counts.get("la_request_capacity", 0) == 1
    assert r.downstream_call_counts.get("la_consume", 0) == 1
    assert r.proposal_packet  # non-empty
    # Drill origin: consumed but fenced non-operational (Wall 1 holds here too).
    assert r.chain_result.consumed is True
    assert r.chain_result.operational is False


def test_lapse_block_is_deterministic(tmp_path: Path):
    a = run_drill(gov_dir=tmp_path / "a", scenario=SCENARIO_TEMPORAL_LAPSE)
    b = run_drill(gov_dir=tmp_path / "b", scenario=SCENARIO_TEMPORAL_LAPSE)
    assert a.spendability_block == b.spendability_block
