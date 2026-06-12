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
    # The monotonic gap and its named basis are on the refusal block.
    assert r.spendability_block is not None
    b = r.spendability_block
    assert b["gap_ns"] == 11_000_000_000  # observed→exercise = 11s
    assert b["bound_ns"] == 10_000_000_000  # freshness budget = 10s
    assert b["overage_ns"] == 1_000_000_000  # one second past the horizon
    assert b["gap_basis"]["kind"] == "monotonic"
    assert b["gap_basis"]["source"] == "process_monotonic"
    assert b["gap_basis"]["epoch"] == "boot:demo-single-host"
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


def test_leaf_receipt_is_the_refusal_not_the_wicket_pass(tmp_path: Path):
    # refusal-receipt-id-mismatch (found by the stranger-gate RERUN): the
    # spendability seam was missing from the chain-gates filter, so on the
    # lapse receipt_ids[-1] was the WICKET pass and every leaf surface
    # (Act-1 render, printed interrogation command, JSON envelope) pointed
    # interrogation at the wrong receipt. Pin: the leaf id's verdict is
    # block on the lapse, and the twin's leaf stays the LA consume.
    import json

    r = run_drill(gov_dir=tmp_path / "lapse", scenario=SCENARIO_TEMPORAL_LAPSE)
    receipts = {
        rec["receipt_id"]: rec
        for line in (tmp_path / "lapse" / "receipts" / "gate_receipts.jsonl").open()
        for rec in [json.loads(line)]
    }
    leaf = receipts[r.receipt_ids[-1]]
    assert leaf["verdict"] == "block"
    assert leaf["gate"] == "standing_spendability_seam"
    # Order preserved: standing → wicket → spendability.
    assert [receipts[i]["gate"] for i in r.receipt_ids] == [
        "standing_seam", "wicket_seam", "standing_spendability_seam",
    ]

    t = run_drill(gov_dir=tmp_path / "twin", scenario=SCENARIO_TEMPORAL_LAPSE_TWIN)
    receipts_t = {
        rec["receipt_id"]: rec
        for line in (tmp_path / "twin" / "receipts" / "gate_receipts.jsonl").open()
        for rec in [json.loads(line)]
    }
    leaf_t = receipts_t[t.receipt_ids[-1]]
    assert leaf_t["gate"] == "la_seam"
    assert leaf_t["verdict"] == "pass"
    # The twin's spendability PASS receipt is now in the chain too.
    assert "standing_spendability_seam" in [
        receipts_t[i]["gate"] for i in t.receipt_ids
    ]


def test_refusal_is_not_an_orphan(tmp_path: Path):
    # Lineage at emission (Act-Two spec, ratified rider): the refusal receipt's
    # evidence cites the wicket receipt as parent, so `governor why` walks
    # refusal → wicket → standing → finding-terminus, same as the consume path.
    import json

    run_drill(gov_dir=tmp_path, scenario=SCENARIO_TEMPORAL_LAPSE)
    receipts = [
        json.loads(line)
        for line in (tmp_path / "receipts" / "gate_receipts.jsonl").open()
    ]
    by_gate = {r["gate"]: r for r in receipts}
    refusal = by_gate["standing_spendability_seam"]
    assert refusal["verdict"] == "block"
    ev_hash = refusal["evidence_hash"]
    bundle = json.loads(
        (tmp_path / "evidence" / ev_hash[:2] / f"{ev_hash}.json").read_text()
    )
    assert bundle["parent_receipt_ids"] == [by_gate["wicket_seam"]["receipt_id"]]
