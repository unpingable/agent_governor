# SPDX-License-Identifier: Apache-2.0
"""Golden-corpus contract test — the decision kernel's frozen `input → verdict`
pairs (`golden/corpus/*.json`).

This is the contract `memory/rust_kernel_port_ruling` names: the corpus, not the
Python, is the kernel contract. This test runs the live cooked-context chain for
each frozen input and asserts the verdict matches — so a code change that alters
a decision breaks here, and updating a golden becomes a deliberate reviewed act
(never a silent regeneration). The eventual Rust kernel is checked against the
same JSON.

It freezes the DECISION, not the artifacts: receipt ids are content-addressed
and environment-shaped, so they are excluded; outcome / refusal_kind /
refusing_seam (closed vocabularies), effect_count (linearity), and the consumed /
operational / proposal_packet_present booleans are the contract.

Two corpus-wide invariants are pinned alongside the per-case checks:
  * Fence (Wall 1): every case runs under a non-observed origin, so `operational`
    is false in all of them — even the ones that mechanically consume.
  * Coverage: every SUPPORTED_SCENARIO has a frozen entry (closed-world; a new
    decision cannot ship without freezing its verdict).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from governor.drill_runner import (
    SUPPORTED_SCENARIOS,
    DrillRunResult,
    build_drill_finding_snapshot,
    run_drill,
)

CORPUS_SCHEMA = "agent_governor.corpus.v1"
CORPUS_DIR = Path(__file__).parent.parent / "golden" / "corpus"

# The verdict fields that constitute the contract. Order is the canonical
# comparison order; receipt ids are deliberately absent (content-addressed).
VERDICT_FIELDS = (
    "outcome",
    "refusal_kind",
    "refusing_seam",
    "effect_count",
    "consumed",
    "operational",
    "proposal_packet_present",
)


def _load_corpus() -> list[tuple[str, dict[str, Any]]]:
    entries = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        entries.append((path.name, json.loads(path.read_text())))
    return entries


CORPUS = _load_corpus()


def _live_verdict(entry: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    """Run the live chain for a corpus input and project the verdict tuple."""
    inp = entry["input"]
    scenario = inp["scenario"]
    confab = inp.get("confabulate_citation")

    finding = None
    override = inp.get("override_origin_mode")
    if override is not None:
        # The synthetic-fence case: rebuild the scenario's finding with the
        # overridden origin_mode so the fence sees a non-drill simulated origin.
        finding = dict(build_drill_finding_snapshot(scenario))
        finding["origin_mode"] = override

    result: DrillRunResult = run_drill(
        gov_dir=tmp_path,
        scenario=scenario,
        finding=finding,
        confabulate_citation=confab,
    )
    return {
        "outcome": result.outcome,
        "refusal_kind": result.refusal_kind,
        "refusing_seam": result.refusing_seam,
        "effect_count": result.effect_count,
        "consumed": result.chain_result.consumed,
        "operational": result.chain_result.operational,
        "proposal_packet_present": bool(result.proposal_packet),
    }


def test_corpus_is_non_empty():
    # A guard against a glob that silently matches nothing (then every
    # parametrized test below would vacuously "pass").
    assert CORPUS, f"no corpus entries found under {CORPUS_DIR}"


@pytest.mark.parametrize("name,entry", CORPUS, ids=[n for n, _ in CORPUS])
def test_corpus_entry_schema(name: str, entry: dict[str, Any]):
    assert entry.get("schema") == CORPUS_SCHEMA, (
        f"{name}: schema must be {CORPUS_SCHEMA!r}, got {entry.get('schema')!r}"
    )
    assert "case" in entry and "input" in entry and "expected_verdict" in entry
    assert set(entry["expected_verdict"]) == set(VERDICT_FIELDS), (
        f"{name}: expected_verdict keys {sorted(entry['expected_verdict'])} "
        f"!= contract fields {sorted(VERDICT_FIELDS)}"
    )


@pytest.mark.parametrize("name,entry", CORPUS, ids=[n for n, _ in CORPUS])
def test_corpus_entry_verdict_matches_live_chain(
    name: str, entry: dict[str, Any], tmp_path: Path
):
    expected = entry["expected_verdict"]
    actual = _live_verdict(entry, tmp_path)
    # Field-by-field so a mismatch reads as a precise diff, not a dict dump.
    for field in VERDICT_FIELDS:
        assert actual[field] == expected[field], (
            f"{name}: verdict drift on {field!r}: "
            f"corpus={expected[field]!r} live={actual[field]!r}. "
            f"If this change is intended, update the golden deliberately."
        )


@pytest.mark.parametrize("name,entry", CORPUS, ids=[n for n, _ in CORPUS])
def test_every_case_is_fenced_non_operational(name: str, entry: dict[str, Any]):
    # Wall 1, corpus-wide: every case runs under a simulated origin (drill /
    # synthetic), so none may be operational — not even the ones that consume.
    assert entry["expected_verdict"]["operational"] is False, (
        f"{name}: a corpus case claims operational=True. Every corpus input is "
        f"a simulated origin; an operational case would mean a demo/test receipt "
        f"could confer real effect. That is the exact thing the fence forbids."
    )


def test_corpus_covers_every_supported_scenario():
    # Closed-world coverage: a new decision scenario cannot ship without a
    # frozen verdict here. (The synthetic case reuses all-green, so cover is by
    # the set of input scenarios, not by file count.)
    covered = {entry["input"]["scenario"] for _, entry in CORPUS}
    missing = set(SUPPORTED_SCENARIOS) - covered
    assert not missing, (
        f"SUPPORTED_SCENARIOS without a frozen corpus verdict: {sorted(missing)}. "
        f"Add a golden/corpus entry freezing each new scenario's decision."
    )


def test_demo_trio_present():
    # The launch demo's three narrated beats each have a corpus anchor. (The
    # two-clock temporal-lapse hero specimen is a known gap — see golden/README;
    # custody_refusal stands in for the impostor beat until it lands.)
    roles = {entry.get("demo_role") for _, entry in CORPUS}
    for role in ("valid_passes", "custody_refusal", "synthetic_fenced"):
        assert role in roles, f"demo_role {role!r} has no corpus anchor"
