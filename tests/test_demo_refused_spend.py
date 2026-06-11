# SPDX-License-Identifier: Apache-2.0
"""Refused-spend show surface (W1 item 3) — the demo's Act-1 temporal contrast.

Pins the integrity tripwire (the impostor refuses for the RIGHT reason, spends no
capacity, ran the same gauntlet as the twin, neither run is operational), the
receipt-forward render, and determinism.
"""

from __future__ import annotations

from pathlib import Path

from governor.demo_refused_spend import (
    build_json_envelope,
    render_surface,
    run_contrast,
)


def test_contrast_passes_integrity_tripwire(tmp_path: Path):
    agg = run_contrast(root=tmp_path, now=0)
    assert agg.aggregate_ok is True
    # Every integrity assertion must hold — these ARE the tripwire.
    assert agg.assertions
    for label, ok, detail in agg.assertions:
        assert ok, f"integrity assertion failed: {label} ({detail})"


def test_impostor_refuses_for_the_right_reason(tmp_path: Path):
    agg = run_contrast(root=tmp_path, now=0)
    imp = agg.impostor
    assert imp is not None
    # Right seam, right kind, no capacity spent — not a hidden short-circuit.
    assert imp.outcome == "refused"
    assert imp.refusal_kind == "standing_before_spendability_not_bounded"
    assert imp.refusing_seam == "standing_spendability_seam"
    assert imp.effect_count == 0
    assert imp.downstream_call_counts.get("la_consume", 0) == 0


def test_twin_spends_cleanly(tmp_path: Path):
    agg = run_contrast(root=tmp_path, now=0)
    twin = agg.twin
    assert twin is not None
    assert twin.outcome == "consumed"
    assert twin.effect_count == 1
    # A system that only says no is a brick — the legitimate action passes.


def test_same_gauntlet_diverges_only_at_the_clock(tmp_path: Path):
    agg = run_contrast(root=tmp_path, now=0)
    twin, imp = agg.twin, agg.impostor
    assert twin is not None and imp is not None
    # Both verified standing AND were admitted by wicket; the ONLY divergence is
    # the spendability gate. Proof the refusal is the clock, not a worse credential.
    for run in (twin, imp):
        assert run.downstream_call_counts.get("standing_verify", 0) == 1
        assert run.downstream_call_counts.get("wicket_check", 0) == 1


def test_neither_run_is_operational(tmp_path: Path):
    # Running the public demo cannot mint a spendable/operational receipt.
    agg = run_contrast(root=tmp_path, now=0)
    assert agg.twin is not None and agg.impostor is not None
    assert agg.twin.chain_result.operational is False
    assert agg.impostor.chain_result.operational is False


def test_surface_is_receipt_forward(tmp_path: Path):
    agg = run_contrast(root=tmp_path, now=0)
    surface = render_surface(agg)
    # The Columbo beat: the refusal kind, both clocks, the gap, the basis.
    assert "standing_before_spendability_not_bounded" in surface
    assert "exercise_at=51" in surface
    assert "horizon_expires_at=50" in surface
    assert "gap=+1s" in surface
    assert "clock_basis=single_host_monotonic" in surface
    # Both halves of the contrast are present.
    assert "LEGITIMATE" in surface and "IMPOSTOR" in surface
    # Receipts are shown (the hero artifact).
    assert "ag_rcpt_" in surface


def test_surface_is_deterministic(tmp_path: Path):
    # Content-addressed receipts + deterministic runs → byte-identical surface
    # across fresh roots.
    a = render_surface(run_contrast(root=tmp_path / "a", now=0))
    b = render_surface(run_contrast(root=tmp_path / "b", now=0))
    assert a == b


def test_json_envelope_shape(tmp_path: Path):
    agg = run_contrast(root=tmp_path, now=0)
    env = build_json_envelope(agg, render_surface(agg))
    assert env["aggregate_ok"] is True
    assert env["impostor"]["refusal_kind"] == "standing_before_spendability_not_bounded"
    assert env["impostor"]["spendability_block"]["gap"] == 1
    assert env["twin"]["outcome"] == "consumed"
    assert isinstance(env["assertions"], list) and env["assertions"]
