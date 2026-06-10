# SPDX-License-Identifier: Apache-2.0
"""D0d-1 — six-scenario gauntlet acceptance + cross-scenario invariants.

Per campaign §3 D2: the demo runs ONE workload (WAL-bloat finding) six
ways. Five refusals, one accounted gap, one effect. This file holds the
AG-side acceptance proofs:

  1. Six per-scenario acceptance tests — each runs the gauntlet for that
     scenario and asserts the per-scenario outcome.
  2. Per-refusal scenarios assert downstream call counts past the
     refusing gate are zero (the campaign §1 "teeth standard" — refusal
     that merely logs is not refusal).
  3. Run 5 replay invariant: ``_EffectCounter`` stays at 1 across the
     two consume invocations (linearity).
  4. Per-scenario determinism: byte-identical normalized transcripts
     across two runs of the same scenario.
  5. Scenario closed-vocab guard: invalid scenarios raise
     ``UnsupportedScenarioError`` at construction (mirrors the
     D0c-b ``InvalidOriginModeError`` pattern).

Critical guardrail honored verbatim: scenario variation lives in the
injected callables and verifier state. The NQ finding is BYTE-IDENTICAL
across all six scenarios. No detector zoo. Tests assert this directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.cooked_context_orchestrator import (
    EVIDENCE_KEY_ORIGIN_MODE,
    ORIGIN_MODE_DRILL,
)
from governor.drill_runner import (
    SCENARIO_ALIAS_ALREADY_CONSUMED,
    SCENARIO_ALL_GREEN,
    SCENARIO_NO_STANDING,
    SCENARIO_REPLAY_BUDGET,
    SCENARIO_STANDING_EXPIRED,
    SCENARIO_WICKET_DENIED,
    SCENARIO_WICKET_GAP_ACCOUNTED,
    SUPPORTED_SCENARIOS,
    UnsupportedScenarioError,
    build_drill_finding_snapshot,
    run_drill,
    run_drill_and_render,
)
from governor.gate_receipt import GateReceiptSystem


# ---------------------------------------------------------------------------
# Per-scenario acceptance tests.
# ---------------------------------------------------------------------------


def test_scenario_1_no_standing_refuses_at_standing_seam(tmp_path: Path):
    """Scenario 1: empty standing_receipt_id → standing_required refusal.

    Downstream call counts past standing_seam must be zero. The
    proposal packet is NOT emitted.
    """
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_NO_STANDING)
    assert result.outcome == "refused"
    assert result.refusal_kind == "standing_required"
    assert result.refusing_seam == "standing_seam"
    # Teeth standard: every gate past the refusing seam is invoked 0 times.
    assert result.downstream_call_counts["wicket_check"] == 0
    assert result.downstream_call_counts["la_request_capacity"] == 0
    assert result.downstream_call_counts["la_consume"] == 0
    # Standing seam emits a refusal receipt; no proposal packet.
    assert len(result.receipt_ids) >= 1
    assert result.proposal_packet == {}
    # Effect count: zero — chain never reached LA.
    assert result.effect_count == 0


def test_scenario_2_standing_expired_refuses_at_standing_seam(tmp_path: Path):
    """Scenario 2: standing digest the verifier rejects → refusal.

    The seam emits ``dangling_receipt_reference`` per its closed
    vocabulary; the scenario layer surfaces ``standing_expired`` to
    the operator (per the §3 D2 table). Downstream calls past
    standing_seam must be zero.
    """
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_STANDING_EXPIRED)
    assert result.outcome == "refused"
    assert result.refusal_kind == "standing_expired"
    assert result.refusing_seam == "standing_seam"
    # The verifier was consulted exactly once (the standing client
    # invokes it after the pre-call non-empty check).
    assert result.downstream_call_counts["standing_verify"] == 1
    # Past the refusing seam: zero invocations.
    assert result.downstream_call_counts["wicket_check"] == 0
    assert result.downstream_call_counts["la_request_capacity"] == 0
    assert result.downstream_call_counts["la_consume"] == 0
    assert result.proposal_packet == {}
    assert result.effect_count == 0


def test_scenario_3_wicket_denied_refuses_at_la_seam(tmp_path: Path):
    """Scenario 3: admission verifier returns False → LA-seam refusal.

    Standing emits, wicket admits, LA-request fires the refusal.
    LA.consume must be invoked 0 times.
    """
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_WICKET_DENIED)
    assert result.outcome == "refused"
    assert result.refusal_kind == "admission_denied"
    assert result.refusing_seam == "la_seam"
    # Standing + wicket fire on the happy path before LA refuses.
    assert result.downstream_call_counts["standing_verify"] == 1
    assert result.downstream_call_counts["wicket_check"] == 1
    # LA.request_capacity is NEVER invoked — admission verification
    # fails the pre-call gate, so the LA callable is short-circuited.
    assert result.downstream_call_counts["la_request_capacity"] == 0
    assert result.downstream_call_counts["la_consume"] == 0
    assert result.proposal_packet == {}
    assert result.effect_count == 0


def test_scenario_4_wicket_gap_accounted_proceeds_with_gap_citation(tmp_path: Path):
    """Scenario 4: gap is NOT a refusal; chain proceeds; proposal
    packet carries gap citation (gap_receipt_id + produced_under_gap).

    No LLM invocation — gap citation is a deterministic field.
    """
    result = run_drill(
        gov_dir=tmp_path, scenario=SCENARIO_WICKET_GAP_ACCOUNTED
    )
    assert result.outcome == "gap_accounted"
    assert result.refusal_kind == "admission_gap_accounted"
    assert result.refusing_seam == "wicket_seam"
    # Full chain fires (gap proceeds).
    assert result.downstream_call_counts["standing_verify"] == 1
    assert result.downstream_call_counts["wicket_check"] == 1
    assert result.downstream_call_counts["la_request_capacity"] == 1
    assert result.downstream_call_counts["la_consume"] == 1
    # Four chain receipts (standing, wicket admit, LA grant, LA consume).
    assert len(result.receipt_ids) == 4
    # Proposal packet is emitted WITH the gap citation surface.
    assert result.proposal_packet.get("status") == "emitted"
    assert result.proposal_packet.get("produced_under_gap") is True
    # gap_receipt_id is the wicket-admit receipt (index 1 in the chain).
    assert result.proposal_packet.get("gap_receipt_id") == result.receipt_ids[1]
    # Effect count: 1 (LA.consume succeeded once).
    assert result.effect_count == 1


def test_scenario_5_replay_budget_kills_second_consume(tmp_path: Path):
    """Scenario 5: two consume invocations with the same event id.

    First call returns Consumed (effect_count++); second call returns
    AlreadyConsumed → refusal kind ``already_consumed``; effect_count
    must remain at 1 (linearity invariant — same valid warrant cited
    twice, second spend refused).
    """
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_REPLAY_BUDGET)
    assert result.outcome == "refused"
    assert result.refusal_kind == "already_consumed"
    assert result.refusing_seam == "la_seam"
    # LA.consume called TWICE.
    assert result.downstream_call_counts["la_consume"] == 2
    # But only ONE effect — the second call returned AlreadyConsumed.
    assert result.effect_count == 1, (
        "Replay scenario: effect_count must remain at 1 across two "
        "consume invocations. The downstream effect counter MUST NOT "
        "advance on the AlreadyConsumed verdict — this is the "
        "linearity invariant the demo proves."
    )
    # Chain receipts: standing, wicket admit, LA grant, LA consume,
    # plus a fifth receipt for the refused second consume.
    assert len(result.receipt_ids) == 5


def test_scenario_6_all_green_consumes_with_proposal_packet(tmp_path: Path):
    """Scenario 6: the existing happy path. Full chain + proposal packet."""
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    assert result.outcome == "consumed"
    assert result.refusal_kind is None
    assert result.refusing_seam is None
    # Full chain fires.
    assert result.downstream_call_counts["standing_verify"] == 1
    assert result.downstream_call_counts["wicket_check"] == 1
    assert result.downstream_call_counts["la_request_capacity"] == 1
    assert result.downstream_call_counts["la_consume"] == 1
    # Four chain receipts.
    assert len(result.receipt_ids) == 4
    # Proposal packet emitted; no gap citation.
    assert result.proposal_packet.get("status") == "emitted"
    assert "produced_under_gap" not in result.proposal_packet
    assert result.effect_count == 1


# ---------------------------------------------------------------------------
# Cross-scenario invariants.
# ---------------------------------------------------------------------------


def test_finding_snapshot_byte_identical_across_all_scenarios():
    """Operator-load-bearing guardrail: per-scenario variation lives on
    the AG side, not in the NQ finding. The FindingSnapshot dict must
    be byte-identical for all six scenarios. If this breaks, somebody
    is building a detector zoo.
    """
    findings = [
        build_drill_finding_snapshot(scenario=s)
        for s in sorted(SUPPORTED_SCENARIOS)
    ]
    # All six findings must be byte-identical when canonicalized.
    import json
    serialized = [json.dumps(f, sort_keys=True) for f in findings]
    first = serialized[0]
    for i, s in enumerate(serialized[1:], start=1):
        assert s == first, (
            "Finding snapshot diverged across scenarios — the workload "
            "must stay identical; only the gate state varies. "
            f"Scenario {sorted(SUPPORTED_SCENARIOS)[i]} differs from "
            f"{sorted(SUPPORTED_SCENARIOS)[0]}."
        )


@pytest.mark.parametrize("scenario", sorted(SUPPORTED_SCENARIOS))
def test_per_scenario_determinism(tmp_path: Path, scenario: str):
    """Two runs of the same scenario against fresh tmp dirs produce
    byte-identical normalized transcripts."""
    dir_a = tmp_path / f"run_a_{scenario}"
    dir_b = tmp_path / f"run_b_{scenario}"
    dir_a.mkdir()
    dir_b.mkdir()
    _, transcript_a = run_drill_and_render(gov_dir=dir_a, scenario=scenario)
    _, transcript_b = run_drill_and_render(gov_dir=dir_b, scenario=scenario)
    assert transcript_a == transcript_b, (
        f"Scenario {scenario}: transcripts diverged across runs. "
        f"Determinism per-scenario is a slice acceptance criterion.\n"
        f"--- A ---\n{transcript_a}\n--- B ---\n{transcript_b}"
    )


@pytest.mark.parametrize("scenario", sorted(SUPPORTED_SCENARIOS))
def test_every_emitted_receipt_carries_origin_mode_drill(
    tmp_path: Path, scenario: str
):
    """Per-scenario receipts inherit origin_mode=drill on every emit."""
    result = run_drill(gov_dir=tmp_path, scenario=scenario)
    system = GateReceiptSystem(tmp_path)
    for rid in result.receipt_ids:
        receipt = system.receipt_store.get_by_id(rid)
        assert receipt is not None, (
            f"receipt {rid} (scenario {scenario}) should be retrievable"
        )
        bundle = system.evidence_for(receipt)
        assert bundle is not None
        assert bundle.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_DRILL, (
            f"receipt {rid} on scenario {scenario} missing "
            f"origin_mode=drill in evidence bundle"
        )


@pytest.mark.parametrize("scenario", sorted(SUPPORTED_SCENARIOS))
def test_every_scenario_ends_in_at_least_one_real_receipt(
    tmp_path: Path, scenario: str
):
    """Slice requirement: each scenario ends in a real receipt id."""
    result = run_drill(gov_dir=tmp_path, scenario=scenario)
    assert len(result.receipt_ids) >= 1, (
        f"Scenario {scenario} produced no receipts — every scenario "
        f"must end in at least one real receipt id."
    )
    # The leaf is what ``governor why`` will walk.
    leaf = result.receipt_ids[-1]
    assert leaf, "leaf receipt id must be non-empty"


# ---------------------------------------------------------------------------
# Scenario closed-vocab guards.
# ---------------------------------------------------------------------------


def test_unknown_scenario_raises_at_construction(tmp_path: Path):
    """Mirrors the D0c-b ``InvalidOriginModeError`` pattern: refuse
    at construction, never silently substitute."""
    with pytest.raises(UnsupportedScenarioError, match="closed scenario set"):
        run_drill(gov_dir=tmp_path, scenario="not-a-scenario")
    with pytest.raises(UnsupportedScenarioError):
        build_drill_finding_snapshot(scenario="bogus")
    # Legacy D0d-a era names still rejected (operator-load-bearing).
    with pytest.raises(UnsupportedScenarioError):
        run_drill(gov_dir=tmp_path, scenario="1_no_standing")
    with pytest.raises(UnsupportedScenarioError):
        run_drill(gov_dir=tmp_path, scenario="6_all_green")


def test_alias_already_consumed_resolves_to_replay_budget(tmp_path: Path):
    """Operator-ratified alias: ``already-consumed`` → ``replay-budget``.

    The alias resolves at construction. The result's ``scenario`` field
    is the canonical name (``replay-budget``) — the alias is only
    accepted at the entry point.
    """
    result = run_drill(
        gov_dir=tmp_path, scenario=SCENARIO_ALIAS_ALREADY_CONSUMED
    )
    assert result.scenario == SCENARIO_REPLAY_BUDGET
    # Same shape as the canonical replay test.
    assert result.refusal_kind == "already_consumed"
    assert result.effect_count == 1


# ---------------------------------------------------------------------------
# Per-scenario transcript shape.
# ---------------------------------------------------------------------------


def test_refusal_scenarios_render_honest_absence_not_no_receipt_emitted(
    tmp_path: Path,
):
    """Refusal scenarios render skipped gates as ``(not invoked —
    refused at <seam>)``, not ``(no-receipt-emitted)`` (which would be
    ambiguous — it was the D0d-a placeholder for happy-path emissions
    that were silently dropped). Honest absence — per the slice spec."""
    _, transcript = run_drill_and_render(
        gov_dir=tmp_path, scenario=SCENARIO_NO_STANDING
    )
    assert "(not invoked — refused at standing_seam)" in transcript
    assert "(no-receipt-emitted)" not in transcript


def test_gap_accounted_transcript_carries_gap_citation(tmp_path: Path):
    """Run 4 transcript shows the gap citation in the proposal packet
    section. No LLM invocation; the field is a deterministic addition
    to the stub template."""
    _, transcript = run_drill_and_render(
        gov_dir=tmp_path, scenario=SCENARIO_WICKET_GAP_ACCOUNTED
    )
    assert "produced_under_gap: true" in transcript
    assert "gap_receipt_id:" in transcript


def test_replay_transcript_shows_fifth_refused_line(tmp_path: Path):
    """Run 5 transcript renders five chain lines — the four happy-path
    receipts plus a refused second consume tagged ``already_consumed``."""
    _, transcript = run_drill_and_render(
        gov_dir=tmp_path, scenario=SCENARIO_REPLAY_BUDGET
    )
    assert "la_seam (replay)" in transcript
    assert "refused=already_consumed" in transcript


def test_all_green_transcript_unchanged_in_shape(tmp_path: Path):
    """Scenario 6 (all-green) transcript still renders the four chain
    links + proposal packet. D0d-1 added scenario-aware fields
    (outcome, effect_count, etc.) but the all-green path's chain and
    proposal packet sections must still appear with the same
    structure.

    The transcript is the normalized form (finding_id → ``<finding_id>``
    so the receipt-content-addressed bytes don't drift across
    NQ-supplied path differences). We assert structural presence here.
    """
    _, transcript = run_drill_and_render(
        gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN
    )
    assert "standing_seam" in transcript
    assert "wicket_seam (admit)" in transcript
    assert "la_seam (granted)" in transcript
    assert "la_seam (consumed)" in transcript
    assert "proposal_packet:" in transcript
    # The proposal packet carries the deterministic template. After
    # normalization, the finding id is rendered as ``<finding_id>``.
    assert "<finding_id>" in transcript
    assert "outcome: consumed" in transcript
    # No gap citation on all-green.
    assert "produced_under_gap" not in transcript
