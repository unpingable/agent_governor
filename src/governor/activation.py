"""Scoped activation + rollback — one tunable, four offices (P3.1).

Workflow-kernel campaign, the first EFFECT-bearing rung. Per the four-office note
(`docs/cross-tool/rung-activation-four-office-note.md`), rung activation is a
transaction across four offices AG co-hosts in bootstrap:

    Governor/Wicket (admissibility) · Standing (act-standing) ·
    Linear Accountant (exactly-once spend) · NQ/receipts (custody)

Narrow by construction: it may activate EXACTLY ONE lowest-stakes tunable
(``decomposition_size / max_slices``). Any other tunable is refused. No generic
activation framework.

Invariants this slice holds (each was a current-rung blocker Codex caught):
- The config surface is mutated ONLY via a receipt — there is no bare ``set``,
  so a debt-clear / eligibility verdict alone can never write it.
- Freshness is recompute-at-the-gate: ``activate`` recomputes P3.0 eligibility
  over the LIVE claim set and refuses a presented digest that does not match the
  full live claim content (deferral is cargo; re-verification is standing).
- Spend is exactly-once (local ledger replay guard in both modes); replay refuses
  before any write.
- Mode honesty: ``standalone_degraded`` uses local substitutes (an explicit
  ``BootstrapStanding`` operator-fiat) and may NOT claim external Standing/LA/NQ
  backing; ``constellation`` consumes a VERIFIED Standing grant-use result
  (``GrantUsed``, D010 Model X — AG inherits Standing's verdict, never adjudicates)
  and requires external LA + NQ office receipts — no faking rich. The LA/NQ refs
  are carried, never parsed; the Standing basis is the verified receipt digest.
- Custody is durable: activation and rollback receipts are persisted; rollback
  restores topology (deletes a previously-absent key), never erases the
  activation receipt.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .activation_preflight import RungDebt, check_activation_eligibility
from .annealing import AnnealingDelta
from .debt_ledger import DebtLedger
from .gate_receipt import canonical_json, content_hash
from .standing_grant_use import (
    GrantRefused,
    GrantUsed,
    RECOGNIZED_REFUSAL_CLASSES,
    GrantUseResult,
    NoVerifiedResult,
)

# The single lowest-stakes tunable P3.1 may touch. Anything else refuses.
P31_SURFACE = "decomposition_size"
P31_TARGET = "max_slices"
P31_RUNG = "self_governance"

MODE_CONSTELLATION = "constellation"
MODE_STANDALONE_DEGRADED = "standalone_degraded"
CLOSED_MODES = frozenset({MODE_CONSTELLATION, MODE_STANDALONE_DEGRADED})


@dataclass(frozen=True)
class BootstrapStanding:
    """Operator-fiat standing for ``standalone_degraded`` (BOOTSTRAP grade).

    Explicit, not a bare bool: it makes the bootstrap substitute a *named* input
    that Office 2 can reject in constellation mode (presenting a fiat where a
    verified Standing grant-use is required = faking rich). ``granted=False`` is
    the honest "even the bootstrap stub denies standing" path. The real-Standing
    path uses a verified ``GrantUseResult`` instead (D010 Model X — AG inherits
    Standing's verdict, never adjudicates).
    """

    granted: bool

REFUSED_NOT_P31_TUNABLE = "refused_not_p31_tunable"
REFUSED_INELIGIBLE = "refused_ineligible"
REFUSED_STALE_DIGEST = "refused_stale_digest"
REFUSED_NO_STANDING = "refused_no_standing"
REFUSED_DEGRADED_CLAIMS_BACKING = "refused_degraded_claims_backing"
REFUSED_REPLAY = "refused_replay"
REFUSED_NO_ACTIVATION_RECEIPT = "refused_no_activation_receipt"
REFUSED_UNCUSTODIED_RECEIPT = "refused_uncustodied_receipt"

CLOSED_ACTIVATION_REFUSALS = frozenset(
    {
        REFUSED_NOT_P31_TUNABLE,
        REFUSED_INELIGIBLE,
        REFUSED_STALE_DIGEST,
        REFUSED_NO_STANDING,
        REFUSED_DEGRADED_CLAIMS_BACKING,
        REFUSED_REPLAY,
        REFUSED_NO_ACTIVATION_RECEIPT,
        REFUSED_UNCUSTODIED_RECEIPT,
    }
)


def live_claim_set_digest(
    debts: Sequence[RungDebt],
    parked_boundary_ids: frozenset[str] | None = None,
) -> str:
    """Content digest over the FULL eligibility input — every debt's content and
    the parked-boundary set — so a materially different live claim set yields a
    different digest. A stale carried digest is therefore detectable at the gate.
    """
    return content_hash(
        canonical_json(
            {
                "debts": sorted(
                    [canonical_json(d.to_dict()).decode() for d in debts]
                ),
                "parked": sorted(parked_boundary_ids or ()),
            }
        )
    )


# --------------------------------------------------------------------------- #
# Office 3 substrate — exactly-once local activation spend (standalone)
# --------------------------------------------------------------------------- #


class LocalSpendLedger:
    """Exactly-once local activation spend — the standalone substitute for LA,
    also a defense-in-depth replay guard in constellation mode. File-backed so
    replay refuses across calls. NOT LA: receipts using it are standalone-grade."""

    def __init__(self, root: Path | str):
        self._path = Path(root) / "activation_spend" / "ledger.json"

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()
        return set(json.loads(self._path.read_text()))

    @contextmanager
    def _exclusive(self):
        """Serialize the load-check-write so two concurrent activations with the
        same spend key cannot both observe it unspent (exactly-once under races)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_name(self._path.name + ".lock")
        with open(lock, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def consume(self, spend_key: str) -> bool:
        with self._exclusive():
            spent = self._load()
            if spend_key in spent:
                return False
            spent.add(spend_key)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(json.dumps(sorted(spent)))
            tmp.replace(self._path)
        return True


# --------------------------------------------------------------------------- #
# Receipts + refusal
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ActivationRefusal:
    code: str
    detail: str = ""
    offending: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.code not in CLOSED_ACTIVATION_REFUSALS:
            raise ValueError(
                f"code must be one of {sorted(CLOSED_ACTIVATION_REFUSALS)}, "
                f"got {self.code!r}"
            )


@dataclass(frozen=True)
class ActivationReceipt:
    actor: str
    target_rung: str
    surface: str
    target: str
    delta_id: str
    eligibility_verdict: str
    live_claim_set_digest: str
    mode: str
    standing_basis: str
    spend_ref: str
    la_spend_ref: str | None
    nq_custody_ref: str | None
    custody_basis: str
    prior_value: Any
    new_value: Any

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": "activation_receipt_v0",
            "actor": self.actor,
            "target_rung": self.target_rung,
            "surface": self.surface,
            "target": self.target,
            "delta_id": self.delta_id,
            "eligibility_verdict": self.eligibility_verdict,
            "live_claim_set_digest": self.live_claim_set_digest,
            "mode": self.mode,
            "standing_basis": self.standing_basis,
            "spend_ref": self.spend_ref,
            "la_spend_ref": self.la_spend_ref,
            "nq_custody_ref": self.nq_custody_ref,
            "custody_basis": self.custody_basis,
            "prior_value": self.prior_value,
            "new_value": self.new_value,
        }

    @property
    def activation_id(self) -> str:
        return content_hash(canonical_json(self.canonical_dict()))

    def to_dict(self) -> dict[str, Any]:
        payload = self.canonical_dict()
        payload["activation_id"] = self.activation_id
        return payload

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ActivationReceipt:
        return cls(
            actor=d["actor"],
            target_rung=d["target_rung"],
            surface=d["surface"],
            target=d["target"],
            delta_id=d["delta_id"],
            eligibility_verdict=d["eligibility_verdict"],
            live_claim_set_digest=d["live_claim_set_digest"],
            mode=d["mode"],
            standing_basis=d["standing_basis"],
            spend_ref=d["spend_ref"],
            la_spend_ref=d.get("la_spend_ref"),
            nq_custody_ref=d.get("nq_custody_ref"),
            custody_basis=d["custody_basis"],
            prior_value=d.get("prior_value"),
            new_value=d.get("new_value"),
        )


@dataclass(frozen=True)
class RollbackReceipt:
    activation_id: str
    surface: str
    target: str
    restored_value: Any
    reason: str
    mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "rollback_receipt_v0",
            "activation_id": self.activation_id,
            "surface": self.surface,
            "target": self.target,
            "restored_value": self.restored_value,
            "reason": self.reason,
            "mode": self.mode,
        }


# --------------------------------------------------------------------------- #
# Office 4 substrate — durable custody (activation + rollback receipts)
# --------------------------------------------------------------------------- #


class ActivationReceiptStore:
    """Durable custody: persists activation receipts (keyed by activation_id) and
    rollback receipts. Rollback never erases the activation record — its file
    remains; the rollback is an additional record."""

    def __init__(self, root: Path | str):
        self._dir = Path(root) / "activation_receipts"

    def put(self, receipt: ActivationReceipt) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{receipt.activation_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(receipt.to_dict(), sort_keys=True, indent=2))
        tmp.replace(path)
        return path

    def get(self, activation_id: str) -> ActivationReceipt | None:
        path = self._dir / f"{activation_id}.json"
        if not path.exists():
            return None
        return ActivationReceipt.from_dict(json.loads(path.read_text()))

    def has(self, activation_id: str) -> bool:
        return (self._dir / f"{activation_id}.json").exists()

    def put_rollback(self, rb: RollbackReceipt) -> Path:
        rb_dir = self._dir / "rollbacks"
        rb_dir.mkdir(parents=True, exist_ok=True)
        path = rb_dir / f"{rb.activation_id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(rb.to_dict(), sort_keys=True, indent=2))
        tmp.replace(path)
        return path


# --------------------------------------------------------------------------- #
# The config surface — active tunable values. Mutated ONLY via a receipt.
# --------------------------------------------------------------------------- #


class ActiveTunableStore:
    """The config surface activation mutates. There is NO bare ``set`` — the only
    writers are :meth:`apply_activation` and :meth:`apply_rollback`, each of which
    takes the receipt that authorizes the write. So a debt-clear / eligibility
    verdict alone cannot reach the effect.

    ``initial`` seeds pre-existing config (the value before any activation).
    Rollback to a ``None`` prior value DELETES the key (restores absence
    topology), rather than writing a null.
    """

    def __init__(self, root: Path | str, initial: Mapping[str, Any] | None = None):
        self._path = Path(root) / "active_tunables" / "values.json"
        if initial:
            self._save(dict(initial))

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _save(self, values: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(dict(values), sort_keys=True))
        tmp.replace(self._path)

    def get(self, surface: str, target: str) -> Any:
        return self._load().get(f"{surface}/{target}")

    def apply_activation(
        self, receipt: ActivationReceipt, *, receipt_store: "ActivationReceiptStore"
    ) -> None:
        # Custody-anchor: honor ONLY a receipt that the real activation path
        # persisted. A directly-constructed (forged) receipt is not in custody,
        # so it cannot drive a write. (Forge+put+apply is still possible to a
        # determined in-process caller — Python has no private methods — so this
        # raises the bar rather than eliminating it; bootstrap-acceptable.)
        if not isinstance(receipt, ActivationReceipt):
            raise TypeError("apply_activation requires an ActivationReceipt")
        if not receipt_store.has(receipt.activation_id):
            raise ValueError(
                "uncustodied receipt: apply_activation refuses a receipt not "
                "persisted by the activation path"
            )
        # Effect-surface fence: even a forged-but-custodied receipt (put+apply
        # bypassing the office) may only ever write the one admitted P3.1 tunable.
        # Bootstrap custody may be forgeable (Python has no private methods); the
        # admitted effect surface must still be fenced — an off-surface write is a
        # local authority-boundary leak, a different class from the substrate limit.
        if receipt.surface != P31_SURFACE or receipt.target != P31_TARGET:
            raise ValueError(
                "off-surface write refused: apply_activation may only touch "
                f"{P31_SURFACE}/{P31_TARGET}, not {receipt.surface}/{receipt.target}"
            )
        values = self._load()
        values[f"{receipt.surface}/{receipt.target}"] = receipt.new_value
        self._save(values)

    def apply_rollback(
        self, rb: RollbackReceipt, *, receipt_store: "ActivationReceiptStore"
    ) -> None:
        if not isinstance(rb, RollbackReceipt):
            raise TypeError("apply_rollback requires a RollbackReceipt")
        # Derive the write AUTHORITATIVELY from the custodied activation receipt,
        # NOT from the rb's claimed surface/target/value. A forged rb pointing at
        # a real activation_id but a different surface cannot redirect the write —
        # it restores exactly the surface/target/prior the custodied activation
        # recorded. (Closes "one real activation_id rewrites any tunable".)
        act = receipt_store.get(rb.activation_id)
        if act is None:
            raise ValueError(
                "uncustodied rollback: the activation it reverts is not in custody"
            )
        # Same effect-surface fence as apply_activation: even reverting a
        # forged-but-custodied off-surface activation may not write outside the
        # one admitted P3.1 tunable.
        if act.surface != P31_SURFACE or act.target != P31_TARGET:
            raise ValueError(
                "off-surface rollback refused: apply_rollback may only touch "
                f"{P31_SURFACE}/{P31_TARGET}, not {act.surface}/{act.target}"
            )
        values = self._load()
        key = f"{act.surface}/{act.target}"
        if act.prior_value is None:
            values.pop(key, None)  # restore absence topology, not a null
        else:
            values[key] = act.prior_value
        self._save(values)


# --------------------------------------------------------------------------- #
# The activation transaction
# --------------------------------------------------------------------------- #


def activate(
    delta: AnnealingDelta,
    *,
    new_value: Any,
    actor: str,
    mode: str,
    spend_ledger: LocalSpendLedger,
    tunable_store: ActiveTunableStore,
    receipt_store: ActivationReceiptStore,
    debt_ledger: DebtLedger,
    standing: GrantUseResult | BootstrapStanding,
    presented_claim_digest: str,
    external_la_spend_ref: str | None = None,
    external_nq_custody_ref: str | None = None,
) -> ActivationReceipt | ActivationRefusal:
    """The four-office activation transaction. Mutates the tunable ONLY at the
    end, via a receipt, after all four offices pass. Returns an ActivationReceipt
    or a typed ActivationRefusal."""
    if mode not in CLOSED_MODES:
        raise ValueError(f"mode must be one of {sorted(CLOSED_MODES)}, got {mode!r}")

    # Office 0 — scope: exactly one tunable. No activation framework.
    if delta.surface != P31_SURFACE or delta.target != P31_TARGET:
        return ActivationRefusal(
            REFUSED_NOT_P31_TUNABLE,
            f"P3.1 may activate only {P31_SURFACE}/{P31_TARGET}, "
            f"not {delta.surface}/{delta.target}",
            (f"{delta.surface}/{delta.target}",),
        )

    # Office 1 — admissibility: read the LIVE claim set from the authoritative
    # DebtLedger (recompute at the gate — NOT a caller-supplied param), then
    # reject a presented digest that does not match it (the caller's basis must
    # agree with the ledger; a new claim recorded since the caller looked changes
    # the digest and refuses). This is the office that the parked draft was
    # missing — caller-supplied claims were an alibi, not a live gate.
    live = debt_ledger.open_claims(P31_RUNG)
    real_digest = live_claim_set_digest(live)
    if presented_claim_digest != real_digest:
        return ActivationRefusal(
            REFUSED_STALE_DIGEST,
            "presented claim digest does not match the live DebtLedger claim set",
            (presented_claim_digest,),
        )
    # No caller-supplied parked set: open_claims are all un-discharged, so the
    # discharged-only handoff-identity gate never fires here. Handoff identity is
    # checked at the DISCHARGE seam, not the activation gate.
    elig = check_activation_eligibility(
        surface=delta.surface,
        target=delta.target,
        target_rung=P31_RUNG,
        debts=live,
    )
    if not elig.eligible:
        return ActivationRefusal(
            REFUSED_INELIGIBLE, f"P3.0 gate refused: {elig.verdict}", elig.offending
        )

    # Office 2 — standing, mode-honest. D010 Model X: AG INHERITS Standing's
    # grant-use verdict; it never adjudicates scope/expiry/spend/replay/subject.
    # Constellation consumes a VERIFIED ``GrantUseResult`` (the carried-not-parsed
    # receipt is gone); standalone_degraded carries an explicit operator-fiat
    # ``BootstrapStanding`` ("run poor, don't fake rich"). ``standing_basis`` is
    # the verified receipt digest (constellation) or "bootstrap_substitute".
    standing_basis: str
    if mode == MODE_CONSTELLATION:
        if isinstance(standing, BootstrapStanding):
            return ActivationRefusal(
                REFUSED_DEGRADED_CLAIMS_BACKING,
                "constellation mode requires a verified Standing grant-use result, "
                "not a bootstrap fiat",
            )
        if isinstance(standing, GrantRefused):
            # Standing's own typed refusal, inherited verbatim (never synthesized)
            # — but only a class from the CLOSED set may be recorded as a Standing
            # refusal. The client parser enforces this for subprocess-verified
            # results; re-checking here fences in-process construction (shape
            # fence, consumption side). Unrecognized text is "cannot verify",
            # never a claim that Standing refused for that reason.
            if standing.refusal_class not in RECOGNIZED_REFUSAL_CLASSES:
                return ActivationRefusal(
                    REFUSED_NO_STANDING,
                    "no_verified_result:unrecognized_refusal_class",
                )
            return ActivationRefusal(
                REFUSED_NO_STANDING, f"standing_refused:{standing.refusal_class}"
            )
        if isinstance(standing, NoVerifiedResult):
            # Could not verify Standing — NOT a claim that Standing refused.
            return ActivationRefusal(
                REFUSED_NO_STANDING, f"no_verified_result:{standing.reason}"
            )
        # POSITIVE type check — the mint branch admits GrantUsed and nothing
        # else. A duck-typed object carrying `receipt_digest` is not a verified
        # Standing result. (Known bootstrap limit: in-process construction of a
        # real GrantUsed remains possible — these fences fence SHAPE, not
        # provenance; provenance fencing is the documented future custody work.)
        if not isinstance(standing, GrantUsed):
            return ActivationRefusal(
                REFUSED_NO_STANDING,
                "no_verified_result:unrecognized_standing_result_type",
            )
        if not (isinstance(standing.receipt_digest, str) and standing.receipt_digest):
            return ActivationRefusal(
                REFUSED_NO_STANDING, "no_verified_result:missing_receipt_digest"
            )
        # GrantUsed: constellation also requires the LA + NQ office receipts.
        if not (external_la_spend_ref and external_nq_custody_ref):
            return ActivationRefusal(
                REFUSED_NO_STANDING,
                "constellation mode requires external LA + NQ receipts alongside "
                "the verified Standing grant-use; absent any, declare "
                "standalone_degraded instead of faking rich",
            )
        standing_basis = standing.receipt_digest
    else:  # MODE_STANDALONE_DEGRADED
        if not isinstance(standing, BootstrapStanding):
            return ActivationRefusal(
                REFUSED_DEGRADED_CLAIMS_BACKING,
                "standalone_degraded may not present a constellation Standing "
                "result (run poor, don't fake rich)",
            )
        if external_la_spend_ref or external_nq_custody_ref:
            return ActivationRefusal(
                REFUSED_DEGRADED_CLAIMS_BACKING,
                "standalone_degraded may not claim external LA/NQ backing "
                "(run poor, don't fake rich)",
            )
        if not standing.granted:
            return ActivationRefusal(
                REFUSED_NO_STANDING, "act-standing not granted for activate_rung"
            )
        standing_basis = "bootstrap_substitute"

    # Office 3 — spend: exactly-once. Replay refuses BEFORE any write, so a
    # replayed activation cannot re-mutate the tunable.
    spend_key = (
        f"activate:{P31_RUNG}:{delta.surface}:{delta.target}:{delta.delta_id}"
    )
    if not spend_ledger.consume(spend_key):
        return ActivationRefusal(
            REFUSED_REPLAY,
            "activation spend already consumed for this delta (replay refused)",
            (spend_key,),
        )

    # Office 4 — custody (durable) THEN effect. Build the receipt, persist it,
    # then mutate the tunable through it. The LA ref is carried, never parsed.
    prior_value = tunable_store.get(delta.surface, delta.target)
    receipt = ActivationReceipt(
        actor=actor,
        target_rung=P31_RUNG,
        surface=delta.surface,
        target=delta.target,
        delta_id=delta.delta_id,
        eligibility_verdict=elig.verdict,
        live_claim_set_digest=real_digest,
        mode=mode,
        standing_basis=standing_basis,
        spend_ref=external_la_spend_ref if mode == MODE_CONSTELLATION else spend_key,
        la_spend_ref=external_la_spend_ref,
        nq_custody_ref=external_nq_custody_ref,
        custody_basis=(
            f"constellation:{external_nq_custody_ref}"
            if mode == MODE_CONSTELLATION
            else "local_receipt_chain"
        ),
        prior_value=prior_value,
        new_value=new_value,
    )
    receipt_store.put(receipt)  # durable custody, before the effect
    tunable_store.apply_activation(receipt, receipt_store=receipt_store)  # effect
    return receipt


def rollback(
    activation_receipt: ActivationReceipt | None,
    *,
    reason: str,
    tunable_store: ActiveTunableStore,
    receipt_store: ActivationReceiptStore,
) -> RollbackReceipt | ActivationRefusal:
    """Roll back an activation: restore the tunable to its prior value (topology,
    not history) and persist a typed rollback receipt. Refuses without a custodied
    activation receipt; re-checks the P3.1 scope; never erases the activation
    receipt. ``mode`` is inherited from the activation receipt, not caller-supplied
    (a rollback cannot forge a different mode than the activation it reverts)."""
    if not isinstance(activation_receipt, ActivationReceipt):
        return ActivationRefusal(
            REFUSED_NO_ACTIVATION_RECEIPT,
            "rollback requires the activation receipt it reverts",
        )
    if (
        activation_receipt.surface != P31_SURFACE
        or activation_receipt.target != P31_TARGET
    ):
        return ActivationRefusal(
            REFUSED_NOT_P31_TUNABLE,
            f"rollback may only touch {P31_SURFACE}/{P31_TARGET}, not "
            f"{activation_receipt.surface}/{activation_receipt.target}",
            (f"{activation_receipt.surface}/{activation_receipt.target}",),
        )
    # Custody-anchor: a forged (directly-constructed) activation receipt that was
    # never persisted by the activation path cannot drive a rollback write.
    if not receipt_store.has(activation_receipt.activation_id):
        return ActivationRefusal(
            REFUSED_UNCUSTODIED_RECEIPT,
            "rollback refuses an activation receipt not in custody (never "
            "persisted by the activation path)",
            (activation_receipt.activation_id,),
        )
    rb = RollbackReceipt(
        activation_id=activation_receipt.activation_id,
        surface=activation_receipt.surface,
        target=activation_receipt.target,
        restored_value=activation_receipt.prior_value,
        reason=reason,
        mode=activation_receipt.mode,  # inherited, not caller-forged
    )
    receipt_store.put_rollback(rb)  # custody — the activation record remains
    tunable_store.apply_rollback(rb, receipt_store=receipt_store)  # restore topology
    return rb
