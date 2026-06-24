"""P3.1 lifecycle drill — prove the effect-bearing rung can activate, account,
and retreat WITHOUT widening authority, before any enforcement (P3.2) is gated on.

This is not a unit specimen (those live in ``test_activation.py``). It is the
single end-to-end walk the four-office transaction must survive once:

    propose delta
    → eligibility from the LIVE DebtLedger
    → activate exactly one tunable (decomposition_size/max_slices, self_governance)
    → observe the active effect + the four-office receipts
    → replay refuses (exactly-once spend)
    → rollback the SAME tunable (references the persisted activation receipt)
    → observe the restored surface
    → forged / off-surface activation and rollback remain refused

Doctrine: *before enforcing recomposition, prove the effect-bearing rung can
activate, account, and retreat without widening authority.* Receipts are
inspected on disk, not just in memory, because custody must be durable.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.activation import (
    MODE_STANDALONE_DEGRADED,
    P31_RUNG,
    BootstrapStanding,
    P31_SURFACE,
    P31_TARGET,
    REFUSED_INELIGIBLE,
    REFUSED_REPLAY,
    REFUSED_UNCUSTODIED_RECEIPT,
    ActivationReceipt,
    ActivationReceiptStore,
    ActivationRefusal,
    ActiveTunableStore,
    LocalSpendLedger,
    RollbackReceipt,
    activate,
    live_claim_set_digest,
    rollback,
)
from governor.annealing import AnnealingDelta, propose_delta
from governor.debt_ledger import DebtLedger
from governor.activation_preflight import RungDebt

_HASH = "a" * 64
_KEY = f"{P31_SURFACE}/{P31_TARGET}"


def _delta() -> AnnealingDelta:
    d = propose_delta(
        surface=P31_SURFACE,
        target=P31_TARGET,
        change_summary="lower the decomposition cap from 8 to 4",
        baseline_id="cb_drill",
        expiry="2026-06-30T00:00:00Z",
        rollback_trigger="refusal_rate>0.2",
    )
    assert isinstance(d, AnnealingDelta)
    return d


def _open_debt(debt_id: str = "drill_debt") -> RungDebt:
    return RungDebt(
        debt_id=debt_id,
        target_rung=P31_RUNG,
        authorized_collector="operator",
        discharge_witness="operator confirms the cap change is reviewed",
        blocks_before="any self_governance activation",
        source_boundary_id=_HASH,
        discharged=False,
    )


def _digest(dledger: DebtLedger) -> str:
    return live_claim_set_digest(dledger.open_claims(P31_RUNG))


def test_p31_activation_lifecycle_drill(tmp_path: Path) -> None:
    # STAGE 0 — four offices, co-hosted (standalone_degraded). Seed a concrete
    # prior (max_slices = 8) so "active effect" and "restored surface" are both
    # observable values, not just presence/absence.
    spend = LocalSpendLedger(tmp_path)
    tunables = ActiveTunableStore(tmp_path, initial={_KEY: 8})
    receipts = ActivationReceiptStore(tmp_path)
    debts = DebtLedger(tmp_path)
    delta = _delta()
    assert tunables.get(P31_SURFACE, P31_TARGET) == 8

    # STAGE 1 — eligibility comes from the LIVE DebtLedger, recomputed at the gate.
    # An open debt on the rung blocks activation; only its discharge unblocks.
    debts.record(_open_debt())
    blocked = activate(
        delta,
        new_value=4,
        actor="operator",
        mode=MODE_STANDALONE_DEGRADED,
        spend_ledger=spend,
        tunable_store=tunables,
        receipt_store=receipts,
        debt_ledger=debts,
        standing=BootstrapStanding(granted=True),
        presented_claim_digest=_digest(debts),  # honest digest over the live set
    )
    assert isinstance(blocked, ActivationRefusal)
    assert blocked.code == REFUSED_INELIGIBLE
    assert tunables.get(P31_SURFACE, P31_TARGET) == 8  # nothing written
    # No activation receipt was minted for the refused attempt.
    assert not (receipts._dir.exists() and list(receipts._dir.glob("*.json")))

    debts.discharge("drill_debt")  # operator clears the gate (eligibility, not spend)

    # STAGE 2 — activate exactly one tunable.
    receipt = activate(
        delta,
        new_value=4,
        actor="operator",
        mode=MODE_STANDALONE_DEGRADED,
        spend_ledger=spend,
        tunable_store=tunables,
        receipt_store=receipts,
        debt_ledger=debts,
        standing=BootstrapStanding(granted=True),
        presented_claim_digest=_digest(debts),  # now over the discharged (empty) set
    )
    assert isinstance(receipt, ActivationReceipt)
    assert (receipt.surface, receipt.target) == (P31_SURFACE, P31_TARGET)
    assert receipt.mode == MODE_STANDALONE_DEGRADED
    # Mode honesty: standalone claims no external office backing.
    assert receipt.custody_basis == "local_receipt_chain"
    assert receipt.standing_basis == "bootstrap_substitute"
    assert receipt.la_spend_ref is None and receipt.nq_custody_ref is None
    assert receipt.prior_value == 8 and receipt.new_value == 4

    # STAGE 3 — observe the active effect + the four-office receipts on disk.
    assert tunables.get(P31_SURFACE, P31_TARGET) == 4  # the effect
    # Custody (office 4) durable on disk.
    act_file = receipts._dir / f"{receipt.activation_id}.json"
    assert act_file.exists()
    assert receipts.has(receipt.activation_id)
    assert receipts.get(receipt.activation_id) == receipt
    # Spend (office 3) recorded — the exactly-once ledger holds this delta's key.
    spend_file = tmp_path / "activation_spend" / "ledger.json"
    assert spend_file.exists()
    spent = json.loads(spend_file.read_text())
    assert any(delta.delta_id in key for key in spent)

    # STAGE 4 — replay refuses (exactly-once spend). A re-issued activation for the
    # same delta cannot re-mutate the tunable.
    replay = activate(
        delta,
        new_value=2,  # would lower further if it slipped through
        actor="operator",
        mode=MODE_STANDALONE_DEGRADED,
        spend_ledger=spend,
        tunable_store=tunables,
        receipt_store=receipts,
        debt_ledger=debts,
        standing=BootstrapStanding(granted=True),
        presented_claim_digest=_digest(debts),
    )
    assert isinstance(replay, ActivationRefusal)
    assert replay.code == REFUSED_REPLAY
    assert tunables.get(P31_SURFACE, P31_TARGET) == 4  # unchanged — not 2

    # STAGE 5 — rollback the SAME tunable; the rollback references the persisted
    # activation receipt and is itself custodied.
    rb = rollback(
        receipt,
        reason="drill: retreat after observing effect",
        tunable_store=tunables,
        receipt_store=receipts,
    )
    assert isinstance(rb, RollbackReceipt)
    assert rb.activation_id == receipt.activation_id  # references the activation
    rb_file = receipts._dir / "rollbacks" / f"{receipt.activation_id}.json"
    assert rb_file.exists()

    # STAGE 6 — observe the restored surface; the activation receipt is NOT erased.
    assert tunables.get(P31_SURFACE, P31_TARGET) == 8  # prior restored (topology)
    assert receipts.has(receipt.activation_id)  # custody record survives rollback
    assert act_file.exists()

    # STAGE 7 — the authority boundary did not widen during the loop. Forged and
    # off-surface writes remain refused even now (re-proven in the drill context).
    forged_offsurface = ActivationReceipt(
        actor="x", target_rung=P31_RUNG, surface="routing", target="lane_weights",
        delta_id="d", eligibility_verdict="eligible", live_claim_set_digest="x",
        mode=MODE_STANDALONE_DEGRADED, standing_basis="b", spend_ref="s",
        la_spend_ref=None, nq_custody_ref=None, custody_basis="local_receipt_chain",
        prior_value=None, new_value=999,
    )
    receipts.put(forged_offsurface)  # bootstrap custody is forgeable...
    with pytest.raises(ValueError, match="off-surface"):  # ...but the effect is fenced
        tunables.apply_activation(forged_offsurface, receipt_store=receipts)
    forged_rb = RollbackReceipt(
        activation_id=forged_offsurface.activation_id, surface="routing",
        target="lane_weights", restored_value=0, reason="x",
        mode=MODE_STANDALONE_DEGRADED,
    )
    with pytest.raises(ValueError, match="off-surface"):
        tunables.apply_rollback(forged_rb, receipt_store=receipts)
    # An uncustodied activation receipt cannot drive a rollback at all.
    never_custodied = ActivationReceipt(
        actor="x", target_rung=P31_RUNG, surface=P31_SURFACE, target=P31_TARGET,
        delta_id="ghost", eligibility_verdict="eligible", live_claim_set_digest="x",
        mode=MODE_STANDALONE_DEGRADED, standing_basis="b", spend_ref="s",
        la_spend_ref=None, nq_custody_ref=None, custody_basis="local_receipt_chain",
        prior_value=1, new_value=2,
    )
    ghost = rollback(
        never_custodied, reason="x", tunable_store=tunables, receipt_store=receipts,
    )
    assert isinstance(ghost, ActivationRefusal)
    assert ghost.code == REFUSED_UNCUSTODIED_RECEIPT
    # The real tunable is untouched by any of stage 7's attempts.
    assert tunables.get(P31_SURFACE, P31_TARGET) == 8
    assert tunables.get("routing", "lane_weights") is None
