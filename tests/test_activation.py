"""Specimens for scoped activation + rollback (P3.1, resumed).

The first effect-bearing rung — a four-office transaction for exactly ONE tunable
(decomposition_size/max_slices), now reading the LIVE claim set from the
authoritative DebtLedger at the gate (not a caller-supplied param) and honoring
only custodied receipts for writes. The negatives prove activation is unreachable
by caller-asserted claims, a stale/replayed/forged artifact, a forged mode, or
any other tunable; custody is durable; rollback restores topology + re-checks scope.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.activation import (
    MODE_CONSTELLATION,
    MODE_STANDALONE_DEGRADED,
    P31_RUNG,
    BootstrapStanding,
    REFUSED_DEGRADED_CLAIMS_BACKING,
    REFUSED_INELIGIBLE,
    REFUSED_NOT_P31_TUNABLE,
    REFUSED_NO_ACTIVATION_RECEIPT,
    REFUSED_NO_STANDING,
    REFUSED_REPLAY,
    REFUSED_STALE_DIGEST,
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
from governor.activation_preflight import RungDebt, check_activation_eligibility
from governor.annealing import AnnealingDelta, propose_delta
from governor.debt_ledger import DebtLedger
from governor.standing_grant_use import GrantRefused, GrantUsed, NoVerifiedResult

_HASH = "a" * 64
_KEY = "decomposition_size/max_slices"


def _used(digest: str = "standing_digest_1", action: str = "set", target: str = "max_slices"):
    """A verified Standing grant-use result for constellation-mode tests."""
    return GrantUsed(
        grant_id="g-1",
        receipt_digest=digest,
        action=action,
        target=target,
        subject="subj-1",
        raw={},
    )


def _delta(surface="decomposition_size", target="max_slices"):
    d = propose_delta(
        surface=surface,
        target=target,
        change_summary="lower the decomposition cap",
        baseline_id="cb_x",
        expiry="2026-06-30T00:00:00Z",
        rollback_trigger="refusal_rate>0.2",
    )
    assert isinstance(d, AnnealingDelta)
    return d


def _open_debt(debt_id="d1"):
    return RungDebt(
        debt_id=debt_id,
        target_rung=P31_RUNG,
        authorized_collector="operator",
        discharge_witness="w",
        blocks_before="any activation",
        source_boundary_id=_HASH,
        discharged=False,
    )


def _stores(tmp_path, initial=None):
    return (
        LocalSpendLedger(tmp_path),
        ActiveTunableStore(tmp_path, initial=initial),
        ActivationReceiptStore(tmp_path),
        DebtLedger(tmp_path),
    )


def _activate(tmp_path, *, stores=None, delta=None, **over):
    ledger, store, rstore, dledger = stores or _stores(tmp_path)
    base = dict(
        new_value=2,
        actor="operator",
        mode=MODE_STANDALONE_DEGRADED,
        spend_ledger=ledger,
        tunable_store=store,
        receipt_store=rstore,
        debt_ledger=dledger,
        standing=BootstrapStanding(granted=True),
        presented_claim_digest=live_claim_set_digest(dledger.open_claims(P31_RUNG)),
    )
    base.update(over)
    d = delta or _delta()
    return activate(d, **base), ledger, store, rstore, dledger


# --------------------------------------------------------------------------- #
# Happy path + modes
# --------------------------------------------------------------------------- #


class TestHappyPath:
    def test_standalone_activation_writes_and_custodies(self, tmp_path) -> None:
        res, _l, store, rstore, _d = _activate(tmp_path)
        assert isinstance(res, ActivationReceipt)
        assert res.mode == MODE_STANDALONE_DEGRADED
        assert res.custody_basis == "local_receipt_chain"
        assert store.get("decomposition_size", "max_slices") == 2
        assert rstore.has(res.activation_id)

    def test_constellation_requires_all_three_offices(self, tmp_path) -> None:
        # Verified Standing (GrantUsed) + LA, but no NQ → still refused.
        res, *_ = _activate(
            tmp_path,
            mode=MODE_CONSTELLATION,
            standing=_used(),
            external_la_spend_ref="la",
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_NO_STANDING

    def test_constellation_with_all_three_carries_refs(self, tmp_path) -> None:
        res, *_ = _activate(
            tmp_path,
            mode=MODE_CONSTELLATION,
            standing=_used(digest="standing_1"),
            external_la_spend_ref="la_spend_1",
            external_nq_custody_ref="nq_1",
        )
        assert isinstance(res, ActivationReceipt)
        assert res.la_spend_ref == "la_spend_1"
        assert res.custody_basis == "constellation:nq_1"
        # The verified Standing receipt digest is the standing_basis (not a
        # carried-not-parsed string) — the D010 Model X pickup.
        assert res.standing_basis == "standing_1"


# --------------------------------------------------------------------------- #
# Authoritative claim source (the office P3.1 was parked to build first)
# --------------------------------------------------------------------------- #


class TestClaimsFromLedger:
    def test_caller_claims_cannot_activate_without_ledger_agreement(
        self, tmp_path
    ) -> None:
        ledger, store, rstore, dledger = _stores(tmp_path)
        dledger.record(_open_debt())
        res, *_ = _activate(
            tmp_path,
            stores=(ledger, store, rstore, dledger),
            presented_claim_digest=live_claim_set_digest(()),  # caller's empty view
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_STALE_DIGEST
        assert store.get("decomposition_size", "max_slices") is None

    def test_open_ledger_claim_refuses_activation(self, tmp_path) -> None:
        ledger, store, rstore, dledger = _stores(tmp_path)
        dledger.record(_open_debt())
        res, *_ = _activate(tmp_path, stores=(ledger, store, rstore, dledger))
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_INELIGIBLE
        assert store.get("decomposition_size", "max_slices") is None

    def test_new_claim_after_basis_makes_digest_stale(self, tmp_path) -> None:
        ledger, store, rstore, dledger = _stores(tmp_path)
        stale = live_claim_set_digest(dledger.open_claims(P31_RUNG))  # empty
        dledger.record(_open_debt())  # a claim appears after the caller looked
        res, *_ = _activate(
            tmp_path,
            stores=(ledger, store, rstore, dledger),
            presented_claim_digest=stale,
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_STALE_DIGEST

    def test_discharged_claim_does_not_block(self, tmp_path) -> None:
        ledger, store, rstore, dledger = _stores(tmp_path)
        dledger.record(_open_debt())
        dledger.discharge("d1")
        res, *_ = _activate(tmp_path, stores=(ledger, store, rstore, dledger))
        assert isinstance(res, ActivationReceipt)  # discharged → not in open set


# --------------------------------------------------------------------------- #
# Custody-anchored writes (forged receipts cannot drive the effect)
# --------------------------------------------------------------------------- #


class TestCustodyAnchor:
    def _forged_receipt(self):
        return ActivationReceipt(
            actor="x", target_rung=P31_RUNG, surface="decomposition_size",
            target="max_slices", delta_id="d", eligibility_verdict="eligible",
            live_claim_set_digest="x", mode=MODE_STANDALONE_DEGRADED,
            standing_basis="b", spend_ref="s", la_spend_ref=None,
            nq_custody_ref=None, custody_basis="local_receipt_chain",
            prior_value=None, new_value=999,
        )

    def test_apply_activation_refuses_uncustodied_receipt(self, tmp_path) -> None:
        _l, store, rstore, _d = _stores(tmp_path)
        with pytest.raises(ValueError, match="uncustodied"):
            store.apply_activation(self._forged_receipt(), receipt_store=rstore)
        assert store.get("decomposition_size", "max_slices") is None

    def test_rollback_refuses_uncustodied_receipt(self, tmp_path) -> None:
        _l, store, rstore, _d = _stores(tmp_path)
        res = rollback(
            self._forged_receipt(), reason="x", tunable_store=store,
            receipt_store=rstore,
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_UNCUSTODIED_RECEIPT

    def test_apply_rollback_uses_custodied_activation_not_rb_fields(
        self, tmp_path
    ) -> None:
        # A forged RollbackReceipt with a REAL activation_id but a different
        # surface/target cannot redirect the write — apply_rollback restores the
        # custodied activation's own surface/target/prior, ignoring the rb's claim.
        stores = (
            LocalSpendLedger(tmp_path),
            ActiveTunableStore(tmp_path, initial={_KEY: 3}),
            ActivationReceiptStore(tmp_path),
            DebtLedger(tmp_path),
        )
        receipt, _l, store, rstore, _d = _activate(tmp_path, stores=stores)
        assert isinstance(receipt, ActivationReceipt)
        forged_rb = RollbackReceipt(
            activation_id=receipt.activation_id,  # real, custodied
            surface="routing", target="lane_weights", restored_value=999,
            reason="redirect attempt", mode=MODE_STANDALONE_DEGRADED,
        )
        store.apply_rollback(forged_rb, receipt_store=rstore)
        # The custodied P3.1 activation was restored (to 3); routing untouched.
        assert store.get("decomposition_size", "max_slices") == 3
        assert store.get("routing", "lane_weights") is None

    def _forged_offsurface_receipt(self):
        return ActivationReceipt(
            actor="x", target_rung=P31_RUNG, surface="routing",
            target="lane_weights", delta_id="d", eligibility_verdict="eligible",
            live_claim_set_digest="x", mode=MODE_STANDALONE_DEGRADED,
            standing_basis="b", spend_ref="s", la_spend_ref=None,
            nq_custody_ref=None, custody_basis="local_receipt_chain",
            prior_value=None, new_value=999,
        )

    def test_forge_put_apply_cannot_write_offsurface(self, tmp_path) -> None:
        # Effect-surface fence: bootstrap custody IS forgeable (put() is public,
        # Python has no private methods), but a forged-AND-custodied off-surface
        # activation still may not write outside the one admitted P3.1 tunable.
        _l, store, rstore, _d = _stores(tmp_path)
        forged = self._forged_offsurface_receipt()
        rstore.put(forged)  # mint bootstrap custody — the acknowledged limit
        assert rstore.has(forged.activation_id)  # custody is real now
        with pytest.raises(ValueError, match="off-surface"):
            store.apply_activation(forged, receipt_store=rstore)
        assert store.get("routing", "lane_weights") is None

    def test_forge_put_rollback_cannot_write_offsurface(self, tmp_path) -> None:
        # Same fence on the sibling writer: reverting a forged-but-custodied
        # off-surface activation may not write outside the admitted tunable either.
        _l, store, rstore, _d = _stores(tmp_path)
        forged = self._forged_offsurface_receipt()
        rstore.put(forged)
        rb = RollbackReceipt(
            activation_id=forged.activation_id, surface="routing",
            target="lane_weights", restored_value=0, reason="x",
            mode=MODE_STANDALONE_DEGRADED,
        )
        with pytest.raises(ValueError, match="off-surface"):
            store.apply_rollback(rb, receipt_store=rstore)
        assert store.get("routing", "lane_weights") is None


# --------------------------------------------------------------------------- #
# Other negatives
# --------------------------------------------------------------------------- #


class TestNegatives:
    def test_debt_clear_alone_cannot_write(self, tmp_path) -> None:
        _l, store, _r, _d = _stores(tmp_path)
        elig = check_activation_eligibility(
            surface="decomposition_size", target="max_slices", target_rung=P31_RUNG
        )
        assert elig.eligible
        assert store.get("decomposition_size", "max_slices") is None
        assert not hasattr(ActiveTunableStore, "set")  # no bare write

    def test_replay_refused_no_double_write(self, tmp_path) -> None:
        stores = _stores(tmp_path)
        delta = _delta()
        first, _l, store, _r, _d = _activate(tmp_path, stores=stores, delta=delta)
        assert isinstance(first, ActivationReceipt)
        second, *_ = _activate(tmp_path, stores=stores, delta=delta, new_value=99)
        assert isinstance(second, ActivationRefusal)
        assert second.code == REFUSED_REPLAY
        assert store.get("decomposition_size", "max_slices") == 2  # not 99

    def test_standalone_cannot_claim_external_backing(self, tmp_path) -> None:
        # Presenting a constellation Standing result (a verified GrantUsed) in
        # standalone_degraded is faking rich → refused.
        res, *_ = _activate(tmp_path, standing=_used())
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_DEGRADED_CLAIMS_BACKING

    def test_cannot_target_other_tunable(self, tmp_path) -> None:
        res, _l, store, *_ = _activate(
            tmp_path, delta=_delta(surface="routing", target="lane_weights")
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_NOT_P31_TUNABLE
        assert store.get("routing", "lane_weights") is None

    def test_no_standing_refused(self, tmp_path) -> None:
        res, *_ = _activate(tmp_path, standing=BootstrapStanding(granted=False))
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_NO_STANDING

    def test_constellation_inherits_standing_refusal(self, tmp_path) -> None:
        # D010 Model X: AG inherits Standing's typed refusal verbatim — it does
        # not synthesize scope authority, and it records the class as cause.
        res, *_ = _activate(
            tmp_path,
            mode=MODE_CONSTELLATION,
            standing=GrantRefused(grant_id="g", refusal_class="scope_mismatch", detail=None, raw={}),
            external_la_spend_ref="la",
            external_nq_custody_ref="nq",
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_NO_STANDING
        assert "standing_refused:scope_mismatch" in res.detail

    def test_constellation_no_verified_result_is_not_a_standing_refusal_claim(self, tmp_path) -> None:
        # Transport ≠ refusal: AG could not verify Standing, so it refuses to mint
        # but must NOT claim Standing refused (it records no_verified_result).
        res, *_ = _activate(
            tmp_path,
            mode=MODE_CONSTELLATION,
            standing=NoVerifiedResult(reason="standing_unknown_custody"),
            external_la_spend_ref="la",
            external_nq_custody_ref="nq",
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_NO_STANDING
        assert "no_verified_result:standing_unknown_custody" in res.detail
        assert "standing_refused" not in res.detail

    def test_constellation_rejects_bootstrap_fiat(self, tmp_path) -> None:
        res, *_ = _activate(
            tmp_path,
            mode=MODE_CONSTELLATION,
            standing=BootstrapStanding(granted=True),
            external_la_spend_ref="la",
            external_nq_custody_ref="nq",
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_DEGRADED_CLAIMS_BACKING

    def test_rollback_without_receipt_refused(self, tmp_path) -> None:
        _l, store, rstore, _d = _stores(tmp_path)
        res = rollback(
            None, reason="x", tunable_store=store, receipt_store=rstore,
        )
        assert isinstance(res, ActivationRefusal)
        assert res.code == REFUSED_NO_ACTIVATION_RECEIPT


# --------------------------------------------------------------------------- #
# Rollback (restores topology, durable non-erasure)
# --------------------------------------------------------------------------- #


class TestRollback:
    def test_restores_prior_value(self, tmp_path) -> None:
        stores = (
            LocalSpendLedger(tmp_path),
            ActiveTunableStore(tmp_path, initial={_KEY: 3}),
            ActivationReceiptStore(tmp_path),
            DebtLedger(tmp_path),
        )
        receipt, _l, store, rstore, _d = _activate(tmp_path, stores=stores)
        assert store.get("decomposition_size", "max_slices") == 2
        assert receipt.prior_value == 3
        rb = rollback(
            receipt, reason="trip", tunable_store=store, receipt_store=rstore,
        )
        assert isinstance(rb, RollbackReceipt)
        assert store.get("decomposition_size", "max_slices") == 3
        assert rstore.has(receipt.activation_id)  # not erased

    def test_rollback_to_absence_deletes_key_not_null(self, tmp_path) -> None:
        receipt, _l, store, rstore, _d = _activate(tmp_path)  # prior None → 2
        rb = rollback(
            receipt, reason="trip", tunable_store=store, receipt_store=rstore,
        )
        assert isinstance(rb, RollbackReceipt)
        assert store.get("decomposition_size", "max_slices") is None
        raw = json.loads((tmp_path / "active_tunables" / "values.json").read_text())
        assert _KEY not in raw
