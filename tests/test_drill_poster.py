# SPDX-License-Identifier: Apache-2.0
"""D0e — show-surface poster acceptance tests.

Per campaign §3 D0e + Phase 1 ratified vocabulary:

  * One command produces the ticket-shaped demo output.
  * Six scenarios render in stable order (1 → 6, then D3).
  * D3 confabulated receipt renders as closing beat (below the divider).
  * DRILL provenance visible on every run.
  * Run 4 carries gap_receipt_id + produced_under_gap=true.
  * Replay run shows AlreadyConsumed + effect_count=1.
  * BA3 bypass renders as debt, never denial.
  * Harness fails on injected BA3 denial (controlled fixture).
  * Byte-identical poster across two runs (determinism).
  * All existing slice tests still pass.

The ten acceptance tests below match the slice's acceptance list one-for-one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from governor.drill_poster import (
    ASSERT_D3_REFUSAL,
    ASSERT_FINDING_BYTE_IDENTICAL,
    ASSERT_NO_BA3_DENIAL,
    ASSERT_RUN_4_GAP,
    ASSERT_RUN_5_REPLAY,
    ASSERT_WHY_WALKS_CHAIN,
    BA3_BYPASS_HEADER,
    BA3_BYPASS_PLACEHOLDER,
    BA3_BYPASSED_GUARDS,
    D3_ROW,
    DRILL_PARAGRAPH_BODY,
    DRILL_PARAGRAPH_HEADER,
    HARNESS_ASSERTIONS_HEADER,
    OUTCOME_ACCOUNTED_GAP,
    OUTCOME_ALREADY_CONSUMED,
    OUTCOME_EFFECT,
    OUTCOME_REFUSED,
    OUTCOME_VALIDATOR_REFUSED,
    POSTER_HEADER,
    POSTER_INCIDENT,
    SIX_RUN_HEADER,
    SIX_RUN_ROWS,
    SPENDABILITY_AUTHORITY_LINE,
    PosterAggregate,
    build_json_envelope,
    render_poster,
    run_seven_invocations,
)
from governor.drill_runner import (
    SCENARIO_ALL_GREEN,
    SCENARIO_REPLAY_BUDGET,
    SCENARIO_WICKET_GAP_ACCOUNTED,
)


# ---------------------------------------------------------------------------
# Helper — invoke the subprocess entry; normalize for cross-tmp byte equality.
# ---------------------------------------------------------------------------


def _run_poster_subprocess(root: Path, fmt: str = "text") -> tuple[int, str, str]:
    """Run ``python3 -m governor.drill_poster --root <root>`` and return
    (returncode, stdout, stderr).
    """
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "governor.drill_poster",
            "--root",
            str(root),
            "--format",
            fmt,
        ],
        capture_output=True,
        text=True,
    )
    return out.returncode, out.stdout, out.stderr


def _normalize_poster(text: str) -> str:
    """Replace per-run receipt-id prefixes so two runs against fresh
    tmp dirs produce byte-identical normalized posters.

    The receipt ids are content-addressed and stable across runs with
    identical *inputs* (the drill_runner's _normalize_transcript path
    already proves this per-run); for the aggregate poster the
    cross-test determinism only requires that two runs of the SAME
    poster against the SAME inputs match. They will — the receipt ids
    are byte-identical given identical inputs to the chain. The
    normalization here is defensive: it strips any 12+-char hex
    substring after the ``ag_rcpt_`` prefix so a future renderer-level
    change to identifier truncation doesn't break the determinism
    contract.
    """
    import re

    # Replace ``ag_rcpt_<12+ hex>`` with ``ag_rcpt_<rid>``.
    return re.sub(r"ag_rcpt_[0-9a-f]{12,}", "ag_rcpt_<rid>", text)


# ---------------------------------------------------------------------------
# Acceptance test 1: one command produces the ticket-shaped output.
# ---------------------------------------------------------------------------


def test_acceptance_1_one_command_produces_ticket_shaped_output(tmp_path: Path):
    """The single CLI invocation produces the ticket frame on stdout."""
    code, stdout, stderr = _run_poster_subprocess(tmp_path)
    assert code == 0, f"poster exited {code}; stderr:\n{stderr}"
    # Top banner header lines.
    assert POSTER_HEADER in stdout
    assert POSTER_INCIDENT in stdout
    # SpendabilityAuthority + BA3 bypass section + six-run header +
    # harness assertions header all present.
    assert SPENDABILITY_AUTHORITY_LINE in stdout
    assert BA3_BYPASS_HEADER in stdout
    assert SIX_RUN_HEADER in stdout
    assert HARNESS_ASSERTIONS_HEADER in stdout


# ---------------------------------------------------------------------------
# Acceptance test 2: six scenarios render in stable order, then D3.
# ---------------------------------------------------------------------------


def test_acceptance_2_six_scenarios_in_stable_order_then_d3(tmp_path: Path):
    """Rows 1 → 6 appear in canonical order, with D3 strictly after."""
    code, stdout, _ = _run_poster_subprocess(tmp_path)
    assert code == 0
    # Find the index of each row's scenario_label in stdout. Each must
    # appear exactly once, in monotonically increasing order.
    indices: list[int] = []
    for spec in SIX_RUN_ROWS:
        # The row_num appears in a fixed-width column; we search for
        # ``  N  <label>`` to avoid matching the harness assertion text.
        marker = f"  {spec.row_num:<2} {spec.scenario_label:<30}"
        idx = stdout.find(marker)
        assert idx >= 0, (
            f"scenario {spec.scenario_label!r} (row {spec.row_num}) "
            f"missing from poster:\n{stdout}"
        )
        indices.append(idx)
    # Strictly increasing — rows in canonical order.
    assert indices == sorted(indices), (
        f"rows not in canonical order; indices={indices}"
    )
    # D3 row appears AFTER row 6.
    d3_marker = f"  {D3_ROW.row_num:<2} {D3_ROW.scenario_label:<30}"
    d3_idx = stdout.find(d3_marker)
    assert d3_idx > indices[-1], (
        f"D3 row at index {d3_idx} must follow row 6 at index {indices[-1]}"
    )


# ---------------------------------------------------------------------------
# Acceptance test 3: D3 confabulated receipt renders below divider.
# ---------------------------------------------------------------------------


def test_acceptance_3_d3_renders_as_closing_beat_below_divider(tmp_path: Path):
    """D3 row is strictly below the divider separating it from the six-run
    table."""
    code, stdout, _ = _run_poster_subprocess(tmp_path)
    assert code == 0
    # The divider between six runs and D3 is a long ``─`` rule. Find
    # the LAST one before the D3 row.
    d3_marker = f"  {D3_ROW.row_num:<2} {D3_ROW.scenario_label:<30}"
    d3_idx = stdout.find(d3_marker)
    assert d3_idx > 0
    # Slice from start to D3 row; the last line in that slice should
    # be a divider rule (``─`` chars).
    head = stdout[:d3_idx]
    head_lines = [ln for ln in head.splitlines() if ln.strip()]
    # The last non-empty line preceding D3 is the divider.
    assert "─" in head_lines[-1], (
        f"expected a ─ divider line immediately above D3; got:\n{head_lines[-1]!r}"
    )
    # D3 outcome text is the ratified phrasing.
    assert D3_ROW.outcome_text in stdout
    assert "validator_refused (dangling_receipt_reference)" in stdout


# ---------------------------------------------------------------------------
# Acceptance test 4: DRILL provenance visible on every run.
# ---------------------------------------------------------------------------


def test_acceptance_4_drill_provenance_paragraph_present(tmp_path: Path):
    """The DRILL paragraph beneath the table is the operator-visible
    provenance disclosure; codex-ratified text leads with
    ``origin_mode=drill minted at NQ``.
    """
    code, stdout, _ = _run_poster_subprocess(tmp_path)
    assert code == 0
    assert DRILL_PARAGRAPH_HEADER in stdout
    # Ratified body: leads with "origin_mode=drill minted at NQ".
    assert "origin_mode=drill minted at NQ" in stdout
    # Full paragraph body present (one sentence, codex Phase 1 output).
    assert DRILL_PARAGRAPH_BODY in stdout
    # Every per-run drill emitted with origin_mode=drill (the JSON
    # envelope assertion path corroborates).
    _, json_out, _ = _run_poster_subprocess(tmp_path, fmt="json")
    envelope = json.loads(json_out)
    for spec in SIX_RUN_ROWS:
        sub = envelope["six_runs"][spec.scenario_key]
        assert sub["finding_origin_mode"] == "drill", (
            f"scenario {spec.scenario_key} finding origin_mode != drill"
        )
    assert envelope["d3_run"]["finding_origin_mode"] == "drill"


# ---------------------------------------------------------------------------
# Acceptance test 5: run 4 visibly carries gap_receipt_id + produced_under_gap.
# ---------------------------------------------------------------------------


def test_acceptance_5_run4_carries_gap_citation(tmp_path: Path):
    """Run 4's proposal packet has gap_receipt_id + produced_under_gap=true
    (asserted via the JSON envelope, since the poster ticket row uses the
    codex-ratified shortened ``↷ accounted_gap`` text)."""
    code, json_out, stderr = _run_poster_subprocess(tmp_path, fmt="json")
    assert code == 0, f"poster exited {code}; stderr:\n{stderr}"
    envelope = json.loads(json_out)
    run4 = envelope["six_runs"][SCENARIO_WICKET_GAP_ACCOUNTED]
    assert run4["proposal_packet"]["produced_under_gap"] is True
    assert run4["proposal_packet"].get("gap_receipt_id")
    # The ticket row shows the ratified ↷ accounted_gap text.
    _, text_out, _ = _run_poster_subprocess(tmp_path)
    assert "↷ accounted_gap" in text_out


# ---------------------------------------------------------------------------
# Acceptance test 6: replay run shows AlreadyConsumed + effect_count=1.
# ---------------------------------------------------------------------------


def test_acceptance_6_replay_shows_already_consumed_effect_one(tmp_path: Path):
    """The replay scenario row shows ``already_consumed`` in the ticket
    table; the harness assertion line confirms ``effect_count = 1``."""
    code, text_out, stderr = _run_poster_subprocess(tmp_path)
    assert code == 0, f"poster exited {code}; stderr:\n{stderr}"
    # Ticket row outcome text — ratified label.
    assert "already_consumed" in text_out
    # Harness assertion line text — ratified label.
    assert ASSERT_RUN_5_REPLAY in text_out
    # Detail: it must be the ✓ form (not ✗) because the run passes.
    # Locate the line and verify a leading ✓ glyph.
    for line in text_out.splitlines():
        if ASSERT_RUN_5_REPLAY in line:
            assert "✓" in line, f"replay assertion did not pass: {line!r}"
            break
    # JSON envelope confirms effect_count = 1 + already_consumed.
    _, json_out, _ = _run_poster_subprocess(tmp_path, fmt="json")
    envelope = json.loads(json_out)
    run5 = envelope["six_runs"][SCENARIO_REPLAY_BUDGET]
    assert run5["refusal_kind"] == "already_consumed"
    assert run5["effect_count"] == 1


# ---------------------------------------------------------------------------
# Acceptance test 7: BA3 bypass renders as debt, never denial.
# ---------------------------------------------------------------------------


def test_acceptance_7_ba3_bypass_renders_as_debt_not_denial(tmp_path: Path):
    """The BA3 bypass section header carries the [BA3 — POST-MVP DEBT]
    tag; the section lines use ``bypass_ag_rcpt_`` prefixes; no
    ``refused`` or ``denied`` word appears in the bypass region."""
    code, text_out, _ = _run_poster_subprocess(tmp_path)
    assert code == 0
    # Section header carries the debt tag verbatim.
    assert "[BA3 — POST-MVP DEBT]" in text_out
    # All four guards listed.
    for guard in BA3_BYPASSED_GUARDS:
        assert guard in text_out, f"guard {guard!r} missing from bypass section"
    # Placeholder receipt-id form for each guard.
    assert BA3_BYPASS_PLACEHOLDER in text_out
    # Locate the bypass section: from BA3_BYPASS_HEADER to the next
    # blank line. No ``refused``/``denied`` words inside that region.
    start = text_out.index(BA3_BYPASS_HEADER)
    rest = text_out[start:]
    end = rest.index("\n\n")
    bypass_section = rest[:end]
    assert "refused" not in bypass_section.lower()
    assert "denied" not in bypass_section.lower()
    # Sanity: bypass kind name (S4-lite ratified) is not on the
    # bypass section either — it lives in the per-run evidence
    # bundles only, never on the public poster surface.
    assert "BA3_BYPASSED_FOR_MVP" not in bypass_section


# ---------------------------------------------------------------------------
# Acceptance test 8: harness fails on injected BA3 denial.
# ---------------------------------------------------------------------------


def test_acceptance_8_harness_fails_on_injected_ba3_denial(tmp_path: Path):
    """Inject a fake BA3-denial receipt into the all-green scenario's
    receipt store; the harness must detect it via
    ``_detect_ba3_denial_with_root``, the assertion fails, and the
    aggregate exits nonzero.

    Per the slice stop condition: this is a fixture/mock assertion
    (a real BA3 denial would defeat the bypass contract). We mint a
    receipt directly via GateReceiptSystem in the per-scenario subdir
    AFTER the aggregate run produces the natural chain, then re-run
    the BA3-denial detector with the live root and assert it surfaces.
    """
    from governor.drill_poster import _detect_ba3_denial_with_root
    from governor.gate_receipt import GateReceiptSystem
    from governor.linear_accountant_client import BYPASS_BA3_FOR_MVP

    # First produce the natural aggregate so the per-scenario subdir
    # exists and is populated.
    aggregate = run_seven_invocations(root=tmp_path)
    # Baseline: no BA3 denial detected on the natural run.
    assert _detect_ba3_denial_with_root(aggregate, tmp_path) is None
    # Inject a controlled fixture: mint a receipt under the all-green
    # subdir whose evidence_bundle.refusal_kind is the bypass
    # sentinel. The detector reads this as a BA3 bypass-as-denial.
    sub = tmp_path / SCENARIO_ALL_GREEN
    system = GateReceiptSystem(sub)
    system.emit(
        gate="ba3_fake_guard",
        verdict="block",
        subject_kind="test_fixture",
        subject_bytes=b"fixture-injected-ba3-denial",
        evidence_bundle={
            "refusal_kind": BYPASS_BA3_FOR_MVP,
            "detail": "test_acceptance_8 fixture",
        },
        gate_config={"seam": "ba3_fake_guard"},
    )
    detail = _detect_ba3_denial_with_root(aggregate, tmp_path)
    assert detail is not None
    assert "BA3 bypass-as-denial detected" in detail


# ---------------------------------------------------------------------------
# Acceptance test 9: byte-identical poster across two runs.
# ---------------------------------------------------------------------------


def test_acceptance_9_poster_byte_identical_after_normalization(tmp_path: Path):
    """Two runs against fresh tmp sandboxes produce byte-identical
    normalized posters.

    The receipt ids are content-addressed; per identical inputs the
    full receipt-id strings are byte-identical across runs (no
    normalization needed). The normalizer is defensive — it strips
    the receipt-id hex tail so a future renderer-level change to
    truncation length does not silently break determinism.
    """
    root_a = tmp_path / "run_a"
    root_b = tmp_path / "run_b"
    code_a, out_a, _ = _run_poster_subprocess(root_a)
    code_b, out_b, _ = _run_poster_subprocess(root_b)
    assert code_a == 0
    assert code_b == 0
    norm_a = _normalize_poster(out_a)
    norm_b = _normalize_poster(out_b)
    assert norm_a == norm_b, (
        "posters not byte-identical after normalization\n"
        f"--- A ---\n{norm_a}\n--- B ---\n{norm_b}"
    )


# ---------------------------------------------------------------------------
# Acceptance test 10: existing slice tests still pass.
# ---------------------------------------------------------------------------


def test_acceptance_10_existing_slice_tests_still_pass():
    """Run the 188 prior slice tests as a subprocess; assert green.

    Defensive guard: this slice MUST NOT regress any of the
    pre-existing 188 tests. We invoke pytest as a subprocess so a
    failure here is unambiguous.
    """
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_drill_runner_all_green.py",
            "tests/test_drill_runner_d0d1_scenarios.py",
            "tests/test_drill_runner_d3_confabulation.py",
            "tests/test_d0_origin_genuine_nq_finding.py",
            "tests/test_d0_bridge_nq_to_ag_origin_mode.py",
            "tests/test_why_command.py",
            "tests/test_standing_client.py",
            "tests/test_wicket_client.py",
            "tests/test_linear_accountant_client.py",
            "tests/test_cooked_context_orchestrator.py",
            "-q",
            "--no-header",
        ],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert out.returncode == 0, (
        f"pre-existing slice tests failed; exit={out.returncode}\n"
        f"stdout:\n{out.stdout}\nstderr:\n{out.stderr}"
    )
    assert "188 passed" in out.stdout, (
        f"expected 188 passed; got:\n{out.stdout}"
    )


# ---------------------------------------------------------------------------
# Supplementary harness coverage — these exercise the assertion engine
# rather than acceptance criteria. Not part of the 10 acceptance set,
# but they pin guard rails on the assertion module itself.
# ---------------------------------------------------------------------------


def test_aggregate_assertions_all_pass_on_clean_run(tmp_path: Path):
    """A natural seven-invocation run produces all-green assertions."""
    aggregate = run_seven_invocations(root=tmp_path)
    assert aggregate.aggregate_ok
    # Each ratified assertion label appears in the assertion list.
    labels = [a.label for a in aggregate.assertions]
    assert ASSERT_NO_BA3_DENIAL in labels
    assert ASSERT_FINDING_BYTE_IDENTICAL in labels
    assert ASSERT_RUN_4_GAP in labels
    assert ASSERT_RUN_5_REPLAY in labels
    assert ASSERT_D3_REFUSAL in labels
    assert ASSERT_WHY_WALKS_CHAIN in labels


def test_outcome_class_vocabulary_is_closed():
    """The five outcome classes are the only ones admitted in the poster.

    Operator: ``DO NOT widen`` the outcome vocabulary.
    """
    from governor.drill_poster import CLOSED_POSTER_OUTCOMES

    assert CLOSED_POSTER_OUTCOMES == frozenset(
        {
            OUTCOME_REFUSED,
            OUTCOME_ACCOUNTED_GAP,
            OUTCOME_ALREADY_CONSUMED,
            OUTCOME_EFFECT,
            OUTCOME_VALIDATOR_REFUSED,
        }
    )
    # Every row's outcome_class is in the closed set.
    for spec in SIX_RUN_ROWS:
        assert spec.outcome_class in CLOSED_POSTER_OUTCOMES
    assert D3_ROW.outcome_class in CLOSED_POSTER_OUTCOMES


def test_six_run_rows_are_in_canonical_scenario_order():
    """The SIX_RUN_ROWS tuple is ordered 1 → 6 by ratified scenario."""
    expected_order = [
        "no-standing",
        "standing-expired",
        "wicket-denied",
        "wicket-gap-accounted",
        "replay-budget",
        "all-green",
    ]
    actual = [spec.scenario_key for spec in SIX_RUN_ROWS]
    assert actual == expected_order


def test_codex_ratified_outcome_glyphs_verbatim():
    """Codex revisions 3, 4, 5: the outcome column uses ``↷`` (not ⚠),
    ``effect`` (not ✓ effect), and surfaces the dangling kind explicitly.
    """
    # Run 4 = "↷ accounted_gap" (not ⚠).
    row4 = next(r for r in SIX_RUN_ROWS if r.row_num == "4")
    assert row4.outcome_text == "↷ accounted_gap"
    assert "⚠" not in row4.outcome_text
    # Run 6 = "effect" (not ✓ effect).
    row6 = next(r for r in SIX_RUN_ROWS if r.row_num == "6")
    assert row6.outcome_text == "effect"
    assert "✓" not in row6.outcome_text
    # D3 = explicit dangling_receipt_reference parenthetical.
    assert D3_ROW.outcome_text == "validator_refused (dangling_receipt_reference)"
