# SPDX-License-Identifier: Apache-2.0
"""D0d-a drill runner — all-green scenario tests.

Two load-bearing assertions:

1. **Origin-mode propagation:** the all-green scenario drives the chain
   end-to-end and produces exactly four GateReceipts (standing seam,
   wicket admission, LA request, LA consume). Every receipt's
   evidence_bundle carries ``origin_mode=drill``.

2. **Determinism:** two invocations against fresh tmp dirs with identical
   inputs produce byte-identical transcripts (and identical receipt ids,
   since receipt ids are content-addressed).

Plus discipline witnesses (closed-set, scenario gate, library shape):

3. The runner refuses scenarios outside the supported set (only
   ``all-green`` for D0d-a).
4. The leaf receipt's chain — when walked via ``governor.why`` — renders
   the ``DRILL`` prefix at the top of output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from governor.cooked_context_orchestrator import (
    EVIDENCE_KEY_ORIGIN_MODE,
    ORIGIN_MODE_DRILL,
)
from governor.drill_runner import (
    ALL_GREEN_CAPACITY_TOKEN_ID,
    ALL_GREEN_FINDING_ID,
    SCENARIO_ALL_GREEN,
    SUPPORTED_SCENARIOS,
    UnsupportedScenarioError,
    build_drill_finding_snapshot,
    run_drill,
    run_drill_and_render,
)
from governor.gate_receipt import GateReceiptSystem
from governor.why import render_text, walk_chain


# ---------------------------------------------------------------------------
# Origin-mode propagation.
# ---------------------------------------------------------------------------


def test_all_green_emits_chain_receipts_all_carrying_origin_mode_drill(tmp_path: Path):
    """The slice's load-bearing assertion.

    Drive the all-green drill; assert every emitted GateReceipt on the
    chain carries ``origin_mode=drill`` in its evidence_bundle.

    D0d-b: the all-green chain now produces FOUR receipts in emit
    order — standing_seam (verified), wicket_seam (admit), la_seam
    (granted), la_seam (consumed). D0d-a's "exactly one receipt"
    contract is superseded by the chain-completeness contract; the
    surfaced gap from D0d-a is closed by D0d-b's happy-path emissions
    on standing_client and linear_accountant_client.
    """
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)

    assert len(result.receipt_ids) >= 4, (
        "expected at least four chain receipts (standing, wicket admit, "
        f"la grant, la consume); got {len(result.receipt_ids)}"
    )

    system = GateReceiptSystem(tmp_path)
    for receipt_id in result.receipt_ids:
        receipt = system.receipt_store.get_by_id(receipt_id)
        assert receipt is not None, f"receipt {receipt_id} not found in store"
        assert receipt.gate in {"standing_seam", "wicket_seam", "la_seam"}, (
            f"receipt {receipt_id} has unexpected gate {receipt.gate!r}"
        )
        bundle = system.evidence_for(receipt)
        assert bundle is not None, (
            f"evidence bundle missing for receipt {receipt_id}"
        )
        assert bundle.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_DRILL, (
            f"receipt {receipt_id} (gate={receipt.gate}) missing "
            f"origin_mode=drill in evidence_bundle; got "
            f"{bundle.get(EVIDENCE_KEY_ORIGIN_MODE)!r}"
        )


def test_all_green_emits_four_chain_receipts_in_emit_order(tmp_path: Path):
    """D0d-b emission contract: the all-green chain mints FOUR positive
    happy-path receipts, in emit order:

      [0] standing_seam (verified)  — D0d-b
      [1] wicket_seam   (admit)     — D0c-a (admission)
      [2] la_seam       (granted)   — D0d-b
      [3] la_seam       (consumed)  — D0d-b

    Amended from the D0d-a contract (which expected exactly ONE wicket
    receipt). D0d-b extends emission to chain-completeness so every
    outcome on the happy path is receipted.

    Pinning the count here makes future drifts visible.
    """
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    assert len(result.receipt_ids) == 4, (
        "D0d-b current contract: four positive receipts on the "
        "all-green happy path (standing verified, wicket admit, la "
        "granted, la consumed). If this count changes, happy-path "
        "emission shape changed — update this test and the runner "
        f"transcript. Got receipt_ids: {result.receipt_ids}"
    )
    system = GateReceiptSystem(tmp_path)
    receipts_in_order = [
        system.receipt_store.get_by_id(rid) for rid in result.receipt_ids
    ]
    for receipt in receipts_in_order:
        assert receipt is not None
        assert receipt.verdict == "pass"
    gates_in_order = [r.gate for r in receipts_in_order]
    assert gates_in_order == [
        "standing_seam",
        "wicket_seam",
        "la_seam",
        "la_seam",
    ], f"unexpected gate order: {gates_in_order}"


def test_chain_result_consumed_with_token_id(tmp_path: Path):
    """All-green reaches Consumed; token id is the stable fixture value."""
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    assert result.chain_result.consumed is True
    # All-green drill is origin_mode=drill → non-operational: the chain
    # mechanically consumed (structure demonstrated) but the outcome is a
    # DemonstratedConsumed, NOT operational. Reach the LA result for the token.
    assert result.chain_result.operational is False
    consumed = result.chain_result.outcome.consumed_result
    assert consumed.token_id == ALL_GREEN_CAPACITY_TOKEN_ID


def test_proposal_packet_is_deterministic_stub(tmp_path: Path):
    """Proposal packet text is the fixed template (no LLM)."""
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    packet = result.proposal_packet
    assert packet["status"] == "emitted"
    # The fixed template; citing the finding id + capacity token id +
    # the deterministic observed_at.
    assert ALL_GREEN_FINDING_ID in packet["text"]
    assert ALL_GREEN_CAPACITY_TOKEN_ID in packet["text"]
    assert "2026-06-09T00:00:00Z" in packet["text"]
    # Citations include the finding id, the four receipt ids, and the
    # capacity token id.
    assert ALL_GREEN_FINDING_ID in packet["citations"]
    assert ALL_GREEN_CAPACITY_TOKEN_ID in packet["citations"]
    for rid in result.receipt_ids:
        assert rid in packet["citations"]


# ---------------------------------------------------------------------------
# Determinism.
# ---------------------------------------------------------------------------


def test_two_runs_produce_identical_receipt_ids(tmp_path: Path):
    """Receipt ids are content-addressed; identical inputs → identical ids."""
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"
    dir_a.mkdir()
    dir_b.mkdir()

    result_a = run_drill(gov_dir=dir_a, scenario=SCENARIO_ALL_GREEN)
    result_b = run_drill(gov_dir=dir_b, scenario=SCENARIO_ALL_GREEN)

    assert result_a.receipt_ids == result_b.receipt_ids, (
        "receipt ids should be identical across runs with identical "
        "inputs (content-addressed)"
    )


def test_two_runs_produce_byte_identical_transcripts(tmp_path: Path):
    """The load-bearing determinism assertion."""
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"
    dir_a.mkdir()
    dir_b.mkdir()

    _, transcript_a = run_drill_and_render(
        gov_dir=dir_a, scenario=SCENARIO_ALL_GREEN
    )
    _, transcript_b = run_drill_and_render(
        gov_dir=dir_b, scenario=SCENARIO_ALL_GREEN
    )

    assert transcript_a == transcript_b, (
        "transcripts should be byte-identical across runs with identical "
        f"inputs\n--- A ---\n{transcript_a}\n--- B ---\n{transcript_b}"
    )


# ---------------------------------------------------------------------------
# Scenario gate.
# ---------------------------------------------------------------------------


def test_only_all_green_is_supported(tmp_path: Path):
    """D0d-1 widened the closed scenario set to the six-scenario
    gauntlet ratified at campaign §3 D2; the temporal-lapse PAIR
    (2026-06-12, operator decision-grade) extended it to eight via the
    closed-world extension ceremony.

    The D0d-a single-scenario contract is superseded; this test pins the
    closed set. Legacy D0d-a era names (e.g. ``1_no_standing``) remain
    refused at construction time. B5 (2026-07-03) extended it to twelve via
    the closed-world extension ceremony (the LA-token quartet — each admitted
    to golden/corpus + MANIFEST + the transition-kernel mirror).
    """
    assert SUPPORTED_SCENARIOS == frozenset(
        {
            "no-standing",
            "standing-expired",
            "wicket-denied",
            "wicket-gap-accounted",
            "replay-budget",
            "all-green",
            "temporal-lapse",
            "temporal-lapse-twin",
            "scope-mismatch",
            "token-revoked",
            "token-expired",
            "unknown-token",
        }
    )

    # Legacy scenario names from D0d-a era are refused at construction.
    with pytest.raises(UnsupportedScenarioError):
        run_drill(gov_dir=tmp_path, scenario="1_no_standing")
    with pytest.raises(UnsupportedScenarioError):
        build_drill_finding_snapshot(scenario="6_all_green")


# ---------------------------------------------------------------------------
# `governor why` renders DRILL prefix on the leaf.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# D0d-b acceptance: transcript contains no ``(no-receipt-emitted)``;
# parent linkage is linear and resolvable; ``governor why`` on the final
# consumed receipt walks the full four-link chain back to the NQ finding.
# ---------------------------------------------------------------------------


def test_d0d_b_transcript_contains_no_no_receipt_emitted_placeholder(
    tmp_path: Path,
):
    """D0d-b acceptance #5: the transcript must contain no
    ``(no-receipt-emitted)`` placeholders. Every chain link is a real
    receipt id under the new emission contract."""
    _, transcript = run_drill_and_render(
        gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN
    )
    assert "(no-receipt-emitted)" not in transcript, (
        "D0d-b: transcript should not render any "
        "(no-receipt-emitted) placeholder — every chain link is a real "
        f"receipt id.\n--- transcript ---\n{transcript}"
    )


def test_d0d_b_parent_linkage_is_linear_and_resolvable(tmp_path: Path):
    """D0d-b acceptance #3: walk the four-link chain via the
    ``parent_receipt_ids`` recorded in each evidence_bundle. The chain
    is linear (each receipt has exactly one parent) and the parent of
    the standing receipt is the NQ finding id (not a GateReceipt — the
    chain head reaches the NQ origin)."""
    from governor.drill_runner import ALL_GREEN_FINDING_ID

    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    system = GateReceiptSystem(tmp_path)

    standing_rid, wicket_rid, la_grant_rid, la_consume_rid = (
        result.receipt_ids
    )

    def _parents(rid: str) -> list[str]:
        r = system.receipt_store.get_by_id(rid)
        assert r is not None
        bundle = system.evidence_for(r)
        assert bundle is not None
        return list(bundle.get("parent_receipt_ids", []))

    # Standing cites the NQ finding id as parent (chain head reaches
    # the NQ origin even though the finding is not itself a
    # GateReceipt yet — D0-Origin lands that).
    assert _parents(standing_rid) == [ALL_GREEN_FINDING_ID]
    # Wicket admit cites the standing receipt.
    assert _parents(wicket_rid) == [standing_rid]
    # LA granted cites the wicket admission.
    assert _parents(la_grant_rid) == [wicket_rid]
    # LA consumed cites the LA grant.
    assert _parents(la_consume_rid) == [la_grant_rid]


def test_d0d_b_governor_why_walks_full_chain_from_consume_receipt(
    tmp_path: Path,
):
    """D0d-b acceptance #4: ``governor why`` on the final consumed
    receipt walks back through all four links to the NQ finding origin
    (rendered as a MISSING tail link until D0-Origin lands a real NQ
    finding GateReceipt — the chain head reaches NQ semantics even
    though the finding GateReceipt does not yet exist)."""
    from governor.drill_runner import ALL_GREEN_FINDING_ID

    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    system = GateReceiptSystem(tmp_path)

    leaf_id = result.receipt_ids[-1]
    walk_result = walk_chain(system, leaf_id)
    # The walk yields four real chain links (one per emitted receipt)
    # plus one MISSING tail link for the cited-but-unminted NQ finding.
    statuses = [link.status for link in walk_result.links]
    assert statuses == [
        "resolved",  # la_seam consumed
        "resolved",  # la_seam granted
        "resolved",  # wicket_seam admit
        "resolved",  # standing_seam verified
        "receipt_missing",  # NQ finding (parent of standing; not a GateReceipt)
    ], f"unexpected walk shape: {statuses}"
    # The MISSING link cites the NQ finding id verbatim.
    missing_link = walk_result.links[-1]
    assert missing_link.cited_id == ALL_GREEN_FINDING_ID
    rendered = render_text(walk_result)
    # DRILL prefix is present (acceptance #2 / D0-Provenance).
    assert "DRILL" in rendered
    assert ALL_GREEN_FINDING_ID in rendered


def test_governor_why_renders_drill_prefix_on_leaf(tmp_path: Path):
    """Per slice requirement #5: ``governor why`` on the final receipt
    must walk back through the chain and render DRILL first."""
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    leaf_id = result.receipt_ids[-1]

    system = GateReceiptSystem(tmp_path)
    walk_result = walk_chain(system, leaf_id)
    rendered = render_text(walk_result)

    # The DRILL prefix line should appear before any chain link.
    assert "DRILL" in rendered, f"DRILL prefix missing from walk:\n{rendered}"
    # And specifically before any OK/REFUSED/BYPASS line.
    drill_idx = rendered.find("DRILL")
    ok_idx = rendered.find("OK ")
    assert ok_idx == -1 or drill_idx < ok_idx, (
        "DRILL prefix should render before any chain link header"
    )


# ---------------------------------------------------------------------------
# Subprocess (module-runnable) shape.
# ---------------------------------------------------------------------------


def test_python_m_governor_drill_runner_emits_json(tmp_path: Path):
    """The library entry point ``python3 -m governor.drill_runner`` emits
    deterministic JSON. Night Shift shells in via this boundary."""
    root = tmp_path / "subproc_root"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "governor.drill_runner",
            "--scenario",
            "all-green",
            "--root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["scenario"] == "all-green"
    assert payload["origin_mode"] == "drill"
    assert payload["finding"]["origin_mode"] == "drill"
    assert payload["finding"]["finding_id"] == ALL_GREEN_FINDING_ID
    # D0d-b: four positive receipts on the happy path (standing
    # verified, wicket admit, la granted, la consumed). See
    # test_all_green_emits_four_chain_receipts_in_emit_order.
    assert len(payload["receipt_ids"]) == 4
    assert payload["leaf_receipt_id"] == payload["receipt_ids"][-1]
    assert payload["proposal_packet"]["status"] == "emitted"
    assert "DRILL" in payload["transcript"]


def test_python_m_two_runs_produce_identical_json(tmp_path: Path):
    """Subprocess determinism — two independent invocations produce
    identical JSON payloads."""
    root_a = tmp_path / "subproc_a"
    root_b = tmp_path / "subproc_b"
    args_a = [
        sys.executable, "-m", "governor.drill_runner",
        "--scenario", "all-green", "--root", str(root_a),
    ]
    args_b = [
        sys.executable, "-m", "governor.drill_runner",
        "--scenario", "all-green", "--root", str(root_b),
    ]
    out_a = subprocess.run(args_a, capture_output=True, text=True, check=True)
    out_b = subprocess.run(args_b, capture_output=True, text=True, check=True)

    payload_a = json.loads(out_a.stdout)
    payload_b = json.loads(out_b.stdout)
    assert payload_a["receipt_ids"] == payload_b["receipt_ids"]
    assert payload_a["transcript"] == payload_b["transcript"]
