# SPDX-License-Identifier: Apache-2.0
"""D3 — confabulated-receipt closing beat acceptance tests.

Per campaign §3 D3 and §3b: after standing → wicket → LA grant → LA
consume have all succeeded on the all-green chain, an injected bogus
citation at the proposal-packet step triggers the validator. The
validator refuses with ``dangling_receipt_reference`` (S4-lite-ratified
kind; not widened); ``effect_count`` stays at 1 (real budget was already
spent — failure is accounted, not free); the proposal packet is NOT
emitted; ``governor why`` walks the full chain back through the refusal
and the bogus citation renders as honest absence.

The line this slice proves:

  > claimed receipt ≠ minted receipt.

Two failure modes, both shipped, both producing the same refusal kind:

  * Existence-fail: ``--confabulate-citation=standing`` injects a fixed
    bogus standing_receipt_id never minted in any seam.
  * Kind-fit-fail: ``--confabulate-citation=evidence`` cites the LA
    token id (a real string from the consume bundle) in the standing
    slot — receipt exists but its structural kind is wrong.

Both surface the same closed-vocab kind ``dangling_receipt_reference``
distinguished by the ``citation_check`` evidence-bundle marker
(``existence`` / ``kind_fit``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.cli import cli
from governor.drill_runner import (
    BOGUS_STANDING_RECEIPT_ID,
    CITATION_CHECK_EXISTENCE,
    CITATION_CHECK_KIND_FIT,
    CONFABULATION_ROLE_EVIDENCE,
    CONFABULATION_ROLE_STANDING,
    PROPOSAL_VALIDATOR_SEAM_GATE,
    SCENARIO_ALL_GREEN,
    SCENARIO_NO_STANDING,
    InvalidConfabulationRoleError,
    run_drill,
    run_drill_and_render,
)
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import CLOSED_REFUSAL_KINDS


# ---------------------------------------------------------------------------
# Test 1 — Deterministic-control mode: existence-fail.
# ---------------------------------------------------------------------------


def test_d3_existence_fail_emits_dangling_receipt_reference_refusal(
    tmp_path: Path,
):
    """The bogus standing_receipt_id is content-addressed and never
    minted — validator detects the existence-fail and emits a real
    refusal GateReceipt with kind ``dangling_receipt_reference``."""
    result = run_drill(
        gov_dir=tmp_path,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_STANDING,
    )
    # Operator-facing classification flipped from consumed to refused.
    assert result.outcome == "refused"
    assert result.refusal_kind == "dangling_receipt_reference"
    assert result.refusing_seam == PROPOSAL_VALIDATOR_SEAM_GATE
    # The kind IS in the existing closed S4-lite set — no widening.
    assert "dangling_receipt_reference" in CLOSED_REFUSAL_KINDS
    # D3 fields populated.
    assert result.confabulation_role == CONFABULATION_ROLE_STANDING
    assert result.bogus_cited_id == BOGUS_STANDING_RECEIPT_ID
    assert result.citation_check == CITATION_CHECK_EXISTENCE
    # Chain receipts: standing, wicket admit, LA grant, LA consume,
    # plus the validator refusal — 5 in total.
    assert len(result.receipt_ids) == 5

    # The leaf receipt's evidence bundle records the bogus id + check
    # tag so machine readers can branch without parsing prose.
    system = GateReceiptSystem(tmp_path)
    leaf = system.receipt_store.get_by_id(result.receipt_ids[-1])
    assert leaf is not None
    assert leaf.gate == PROPOSAL_VALIDATOR_SEAM_GATE
    assert leaf.verdict == "block"
    bundle = system.evidence_for(leaf)
    assert bundle is not None
    assert bundle["refusal_kind"] == "dangling_receipt_reference"
    assert bundle["citation_check"] == CITATION_CHECK_EXISTENCE
    assert bundle["citation_role"] == CONFABULATION_ROLE_STANDING
    assert bundle["bogus_cited_id"] == BOGUS_STANDING_RECEIPT_ID


# ---------------------------------------------------------------------------
# Test 2 — Kind-fit-fail: real id cited in wrong role.
# ---------------------------------------------------------------------------


def test_d3_kind_fit_fail_distinguishes_from_existence_fail(tmp_path: Path):
    """Cite the LA token_id in the standing slot. The id resolves to a
    real receipt — but that receipt's structural kind (gate name + the
    ``verified_standing`` marker) is wrong for the slot. Validator
    catches the structural mismatch; same refusal kind, different
    citation_check tag.

    Kind-fit is a guard against structural attributes, not a typed
    ArtifactKind enum — the validator reads ``receipt.gate`` and
    ``evidence_bundle["verified_standing"]`` on the cited receipt.
    """
    result = run_drill(
        gov_dir=tmp_path,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_EVIDENCE,
    )
    assert result.outcome == "refused"
    # SAME closed-vocab kind for both failure modes.
    assert result.refusal_kind == "dangling_receipt_reference"
    assert result.refusing_seam == PROPOSAL_VALIDATOR_SEAM_GATE
    # DIFFERENT failure-mode tag distinguishes existence vs kind-fit.
    assert result.confabulation_role == CONFABULATION_ROLE_EVIDENCE
    assert result.citation_check == CITATION_CHECK_KIND_FIT
    # The bogus id is the real LA token id — a string that DOES appear
    # in the receipts (inside the consume bundle's token_id_repr), but
    # was never minted AS a receipt id.
    assert result.bogus_cited_id is not None
    assert result.bogus_cited_id != BOGUS_STANDING_RECEIPT_ID

    # The leaf is the validator-emitted refusal receipt.
    assert len(result.receipt_ids) == 5
    system = GateReceiptSystem(tmp_path)
    leaf = system.receipt_store.get_by_id(result.receipt_ids[-1])
    assert leaf is not None
    bundle = system.evidence_for(leaf)
    assert bundle is not None
    assert bundle["citation_check"] == CITATION_CHECK_KIND_FIT
    assert bundle["citation_role"] == CONFABULATION_ROLE_EVIDENCE


# ---------------------------------------------------------------------------
# Test 3 — `governor why` walks the chain AND surfaces bogus citation
# as absence (S5 unknown-receipt-id path).
# ---------------------------------------------------------------------------


def _make_gov_dir(tmp_path: Path) -> Path:
    """Initialize a minimal .governor/ tree at tmp_path/.governor so
    the `governor` CLI's ensure_initialized check passes. Mirrors the
    gov_dir fixture in test_why_command.py."""
    gd = tmp_path / ".governor"
    gd.mkdir()
    (gd / "facts").mkdir()
    (gd / "facts" / "receipts").mkdir()
    (gd / "facts" / "index.json").write_text("[]")
    (gd / "decisions").mkdir()
    (gd / "decisions" / "index.json").write_text("[]")
    (gd / "proposals.json").write_text("{}")
    (gd / "receipts").mkdir()
    return gd


def test_d3_governor_why_walks_back_through_chain(tmp_path: Path):
    """`governor why <refusal-id>` walks back through the validator →
    consume → grant → admission → standing chain. No traceback. The
    chain origin is the standing seam (the chain head)."""
    gov_dir = _make_gov_dir(tmp_path)
    result = run_drill(
        gov_dir=gov_dir,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_STANDING,
    )
    runner = CliRunner()
    cli_result = runner.invoke(
        cli, ["-r", str(tmp_path), "why", result.receipt_ids[-1]]
    )
    assert cli_result.exit_code == 0, (
        f"why on the D3 refusal should walk cleanly; output:\n{cli_result.output}"
    )
    assert "Traceback" not in cli_result.output
    # The refusal kind is rendered.
    assert "dangling_receipt_reference" in cli_result.output
    # The validator seam is named.
    assert PROPOSAL_VALIDATOR_SEAM_GATE in cli_result.output
    # The chain walks back through the consume + grant + admission +
    # standing receipts.
    assert "la_seam" in cli_result.output
    assert "wicket_seam" in cli_result.output
    assert "standing_seam" in cli_result.output
    # Cross-repo bridge: chain origin_mode is drill.
    assert "DRILL" in cli_result.output


def test_d3_governor_why_on_bogus_citation_renders_absence_not_traceback(
    tmp_path: Path,
):
    """`governor why <bogus-id>` (the bogus citation itself) renders as
    'receipt id not found' via the existing S5 unknown-receipt-id path.
    No new render logic. Per the slice spec hard rule #4 + the existing
    S5 negative test pattern."""
    gov_dir = _make_gov_dir(tmp_path)
    result = run_drill(
        gov_dir=gov_dir,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_STANDING,
    )
    assert result.bogus_cited_id == BOGUS_STANDING_RECEIPT_ID
    runner = CliRunner()
    cli_result = runner.invoke(
        cli, ["-r", str(tmp_path), "why", result.bogus_cited_id]
    )
    # Per the S5 unknown-receipt-id test: nonzero exit on unknown id,
    # absence rendered, no traceback.
    assert cli_result.exit_code != 0
    assert "receipt id not found" in cli_result.output
    assert "Traceback" not in cli_result.output


# ---------------------------------------------------------------------------
# Test 4 — effect_count stays at 1 (failure cost real budget).
# ---------------------------------------------------------------------------


def test_d3_effect_count_remains_at_1_after_validation_refusal(tmp_path: Path):
    """Per §3b retry economics: LA.consume already fired before the
    validator runs. ``_EffectCounter`` is at 1. The validator refuses;
    ``effect_count`` MUST remain at 1 — failure cost real budget."""
    result = run_drill(
        gov_dir=tmp_path,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_STANDING,
    )
    assert result.effect_count == 1, (
        "Confabulation refused but the chain reached Consumed first; "
        "the downstream effect counter MUST stay at 1 — failure is "
        "accounted, not free. This is the slice's retry-economics beat."
    )
    # Downstream consume was invoked exactly once (the chain reached
    # Consumed cleanly; the validator-refusal is downstream of LA).
    assert result.downstream_call_counts["la_consume"] == 1
    # Proposal packet was NOT emitted — the refusal IS the closing beat.
    assert result.proposal_packet == {}


# ---------------------------------------------------------------------------
# Test 5 — refusal receipt's parent_receipt_ids cites the consume receipt id.
# ---------------------------------------------------------------------------


def test_d3_refusal_receipt_parent_is_consume_receipt(tmp_path: Path):
    """The validator's emitted refusal receipt MUST cite the consume
    receipt as its sole parent — that is the latest non-refusal receipt
    in the chain. Chain walkability invariant: ``governor why`` must be
    able to traverse refusal → consume → ... → finding."""
    result = run_drill(
        gov_dir=tmp_path,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_STANDING,
    )
    system = GateReceiptSystem(tmp_path)
    validator_receipt = system.receipt_store.get_by_id(result.receipt_ids[-1])
    assert validator_receipt is not None
    bundle = system.evidence_for(validator_receipt)
    assert bundle is not None
    parents = bundle["parent_receipt_ids"]
    assert len(parents) == 1
    consume_id = result.receipt_ids[3]  # standing, wicket, grant, consume
    assert parents[0] == consume_id
    # And the cited parent is itself the consume receipt (la_seam, with
    # la_outcome=consumed in the evidence bundle).
    cited = system.receipt_store.get_by_id(parents[0])
    assert cited is not None
    assert cited.gate == "la_seam"
    cited_bundle = system.evidence_for(cited)
    assert cited_bundle is not None
    assert cited_bundle.get("la_outcome") == "consumed"


# ---------------------------------------------------------------------------
# Test 6 — retry economics: re-attempt requires a NEW chain spend.
# ---------------------------------------------------------------------------


def test_d3_re_attempt_requires_new_chain_spend(tmp_path: Path):
    """Replaying the same chain without re-consuming is NOT how retry
    works — retry IS a new chain. Two D3 runs against fresh receipt
    roots each consume independently (each produces its own
    ``_EffectCounter=1``). Replaying within the same gov_dir would
    require a fresh consume + fresh chain — the runner does not
    retry-in-place.

    Operator-load-bearing demo beat: "the confabulated citation consumed
    real budget and bought a refusal. Failure is accounted, not free. No
    agent framework currently demonstrates this."
    """
    dir_a = tmp_path / "attempt_a"
    dir_b = tmp_path / "attempt_b"
    dir_a.mkdir()
    dir_b.mkdir()

    result_a = run_drill(
        gov_dir=dir_a,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_STANDING,
    )
    result_b = run_drill(
        gov_dir=dir_b,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=CONFABULATION_ROLE_STANDING,
    )
    # Each attempt's chain reached Consumed once — each paid its own
    # budget.
    assert result_a.effect_count == 1
    assert result_b.effect_count == 1
    assert result_a.downstream_call_counts["la_consume"] == 1
    assert result_b.downstream_call_counts["la_consume"] == 1
    # And each attempt produced its own validator-emitted refusal.
    assert result_a.refusing_seam == PROPOSAL_VALIDATOR_SEAM_GATE
    assert result_b.refusing_seam == PROPOSAL_VALIDATOR_SEAM_GATE
    # Re-attempt is a new chain, not a free replay of the prior one.
    # The chain leaf is the validator refusal for both, but the
    # underlying chain receipts (standing, wicket, grant, consume) are
    # independently emitted on each run — neither inherits state.
    assert len(result_a.receipt_ids) == 5
    assert len(result_b.receipt_ids) == 5


# ---------------------------------------------------------------------------
# Test 7 — transcript determinism preserved in confabulation mode.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [CONFABULATION_ROLE_STANDING, CONFABULATION_ROLE_EVIDENCE],
)
def test_d3_transcript_determinism_across_runs(tmp_path: Path, role: str):
    """Two D3 runs of the same role against fresh tmp dirs produce
    byte-identical normalized transcripts. The bogus_cited_id is
    constant per role (standing → BOGUS_STANDING_RECEIPT_ID;
    evidence → the stable ``tok_drill_all_green_001`` token id) so
    no additional normalization is required."""
    dir_a = tmp_path / f"run_a_{role}"
    dir_b = tmp_path / f"run_b_{role}"
    dir_a.mkdir()
    dir_b.mkdir()
    _, transcript_a = run_drill_and_render(
        gov_dir=dir_a,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=role,
    )
    _, transcript_b = run_drill_and_render(
        gov_dir=dir_b,
        scenario=SCENARIO_ALL_GREEN,
        confabulate_citation=role,
    )
    assert transcript_a == transcript_b, (
        f"D3 role={role}: transcripts diverged across runs. "
        f"Determinism is a slice acceptance criterion.\n"
        f"--- A ---\n{transcript_a}\n--- B ---\n{transcript_b}"
    )
    # Sanity: the transcript actually surfaces the confabulation.
    assert "proposal_validator" in transcript_a
    assert "dangling_receipt_reference" in transcript_a


# ---------------------------------------------------------------------------
# Test 8 — closed scenario set untouched + closed role set guard.
# ---------------------------------------------------------------------------


def test_d3_invalid_role_raises_at_construction(tmp_path: Path):
    """Per the construction-time refusal pattern: an invalid role
    raises InvalidConfabulationRoleError before any chain runs."""
    with pytest.raises(InvalidConfabulationRoleError, match="closed set"):
        run_drill(
            gov_dir=tmp_path,
            scenario=SCENARIO_ALL_GREEN,
            confabulate_citation="not-a-role",
        )


def test_d3_confabulation_with_non_all_green_scenario_raises(tmp_path: Path):
    """Per the slice tier-3 fence: confabulation only makes sense at
    the proposal-packet step; only all-green reaches it. Pairing the
    flag with any other scenario raises at construction time."""
    with pytest.raises(InvalidConfabulationRoleError, match="all-green"):
        run_drill(
            gov_dir=tmp_path,
            scenario=SCENARIO_NO_STANDING,
            confabulate_citation=CONFABULATION_ROLE_STANDING,
        )


# ---------------------------------------------------------------------------
# Test 9 — JSON envelope carries D3 fields under their own keys.
# ---------------------------------------------------------------------------


def test_d3_json_envelope_surfaces_confabulation_fields(tmp_path: Path):
    """The CLI's JSON output carries confabulation_role + bogus_cited_id
    + citation_check under their own keys so Night Shift can assert
    without parsing transcript prose."""
    import json
    import subprocess
    import sys

    root = tmp_path / "ag_root"
    root.mkdir()
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "governor.drill_runner",
            "--scenario",
            SCENARIO_ALL_GREEN,
            "--root",
            str(root),
            "--confabulate-citation",
            CONFABULATION_ROLE_STANDING,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    envelope = json.loads(out.stdout)
    assert envelope["outcome"] == "refused"
    assert envelope["refusal_kind"] == "dangling_receipt_reference"
    assert envelope["refusing_seam"] == PROPOSAL_VALIDATOR_SEAM_GATE
    assert envelope["confabulation_role"] == CONFABULATION_ROLE_STANDING
    assert envelope["bogus_cited_id"] == BOGUS_STANDING_RECEIPT_ID
    assert envelope["citation_check"] == CITATION_CHECK_EXISTENCE
    # Effect counter stays at 1.
    assert envelope["effect_count"] == 1
    # Proposal packet is empty (mutation did not happen).
    assert envelope["proposal_packet"] == {}
    # Five chain receipts.
    assert len(envelope["receipt_ids"]) == 5


# ---------------------------------------------------------------------------
# Test 10 — non-D3 runs unchanged. Backward compatibility guard.
# ---------------------------------------------------------------------------


def test_d3_non_d3_all_green_run_unchanged(tmp_path: Path):
    """A normal all-green run (no confabulation flag) MUST be byte-for-
    byte the same shape as before D3 landed. D3 fields are all None."""
    result = run_drill(gov_dir=tmp_path, scenario=SCENARIO_ALL_GREEN)
    assert result.outcome == "consumed"
    assert result.refusal_kind is None
    assert result.refusing_seam is None
    assert result.confabulation_role is None
    assert result.bogus_cited_id is None
    assert result.citation_check is None
    # Four chain receipts — validator never fired.
    assert len(result.receipt_ids) == 4
    # Proposal packet emitted.
    assert result.proposal_packet.get("status") == "emitted"
    assert result.effect_count == 1
