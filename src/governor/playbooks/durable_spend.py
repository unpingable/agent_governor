# SPDX-License-Identifier: Apache-2.0
"""Durable, exactly-once playbook spend (Slice 5 — the first Track A pickup).

> Evidence is not authority. Authority is not spend. Spend is not execution.
> Durability is not permission.

This is the boundary where a playbook-governed spend stops being a harness story
and becomes runtime law: a spend that **survives process crash / replay / resume
without double-spending**. The boss fight is boring on purpose —

    Same playbook activation, retried after a crash/replay → does NOT double-spend.

Mechanism: the **write-ahead exactly-once ledger**, the ratified Office-3 pattern
from ``activation.py`` (``LocalSpendLedger`` — claim *before* the effect; a
replayed key refuses before any write). Ported here (the shape, not a shared base
class — the two ledgers are distinct subsystems with distinct files) rather than
reused directly, because ``activation.LocalSpendLedger`` hard-codes the
``activation_spend`` path and is documented as *that* office's substitute for LA.
The bias is deliberate and matches activation.py's Office 3: **never double-spend**
(write-ahead) over **always recover a crashed attempt** (a crashed/failed attempt
fail-closes its own retry — auditable via the claim record, the safe direction).

What this is NOT:
- It is not ``activate()``. That transaction is hard-fenced to one tunable
  (``decomposition_size/max_slices``); a playbook spend is a different specimen and
  must not widen it. This module reuses the *pattern*, not the gate.
- It is not execution. The spend is the LA consume; this gate decides only whether
  the spend may proceed exactly once. "Spend is not execution."
- It is not the spend basis. The spend basis is the wicket-seam *authority*
  admission (verdict="pass"); this gate binds that admission into the durable
  spend identity so a spend with a different step/effect/resource/principal/
  authority is a *different* key, and the *same* spend replayed is the same key.
"""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from governor.gate_receipt import canonical_json, content_hash

# Bump when the spend-key basis composition changes.
DURABLE_SPEND_BASIS_VERSION = "playbook-durable-spend.v0"

# Closed refusal vocabulary for this seam.
REFUSED_DURABLE_REPLAY = "playbook_spend_replayed"
REFUSED_INCOMPLETE_BASIS = "playbook_spend_basis_incomplete"
DURABLE_SPEND_REFUSALS = frozenset(
    {REFUSED_DURABLE_REPLAY, REFUSED_INCOMPLETE_BASIS}
)

# Gate + verdicts (GateReceipt closed vocabulary).
DURABLE_SPEND_GATE = "playbook_durable_spend"
DURABLE_SPEND_CLAIM_VERDICT = "observe"  # the claim is a reservation record...
DURABLE_SPEND_REFUSE_VERDICT = "block"   # ...the LA consume (verdict=pass) is the spend


@dataclass(frozen=True)
class PlaybookSpendIntent:
    """The caller-declared identity of *what* a playbook spend is for.

    Carries everything that makes a spend distinct EXCEPT the authority — the
    authority admission receipt id is minted during the chain and bound in at
    runtime (a caller cannot know it pre-admission). All fields are part of the
    durable spend key, so a different step / effect / resource / principal /
    playbook is a different spend (no key collision), and the same spend is the
    same key (replay refuses).
    """

    step_id: str           # the exact playbook step being spent for
    principal: str         # who spends (actor)
    effect: str            # what the spend does (action)
    resource: str          # what it acts on (scope/target)
    amount: int            # how much capacity
    playbook_spec_digest: str  # which playbook (Slice 0 digest)


@dataclass(frozen=True)
class PlaybookSpendBasis:
    """A complete, authority-bound spend identity: the intent + the authority
    admission receipt that authorized it. The durable spend key is derived from
    ALL of this. ``authority_admission_receipt_id`` MUST be a wicket-seam pass
    admission (the orchestrator threads it; the LA spend basis is never the
    observe evidence record — that wall is enforced upstream)."""

    authority_admission_receipt_id: str
    intent: PlaybookSpendIntent

    @classmethod
    def from_intent(
        cls, intent: PlaybookSpendIntent, *, authority_admission_receipt_id: str
    ) -> "PlaybookSpendBasis":
        return cls(
            authority_admission_receipt_id=authority_admission_receipt_id,
            intent=intent,
        )

    def is_complete(self) -> bool:
        """Every binding field present — no spend without exact step/effect/
        resource/principal/authority binding."""
        i = self.intent
        return bool(
            self.authority_admission_receipt_id
            and i.step_id
            and i.principal
            and i.effect
            and i.resource
            and i.playbook_spec_digest
            and isinstance(i.amount, int)
            and i.amount > 0
        )


def durable_spend_key(basis: PlaybookSpendBasis) -> str:
    """SHA-256 over the version-bound, authority-bound spend identity. Stable and
    content-addressed: the same spend yields the same key (replay detectable);
    any change to authority / step / effect / resource / principal / amount /
    playbook yields a different key (a different spend)."""
    i = basis.intent
    return content_hash(
        canonical_json(
            {
                "basis_version": DURABLE_SPEND_BASIS_VERSION,
                "authority_admission_receipt_id": basis.authority_admission_receipt_id,
                "principal": i.principal,
                "effect": i.effect,
                "resource": i.resource,
                "amount": i.amount,
                "playbook_spec_digest": i.playbook_spec_digest,
                "step_id": i.step_id,
            }
        )
    )


class DurableSpendLedger:
    """Write-ahead exactly-once spend ledger — survives process crash/restart.

    Ported shape from ``activation.LocalSpendLedger`` (Office 3): file-backed,
    flock-serialized claim-or-refuse, atomic tmp-replace. ``consume(key)`` returns
    ``True`` the first time a key is claimed and ``False`` on every replay — the
    claim is write-ahead, so a replayed spend refuses before any LA call.
    """

    def __init__(self, root: Path | str):
        self._path = Path(root) / "playbook_spend" / "ledger.json"

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()
        return set(json.loads(self._path.read_text()))

    @contextmanager
    def _exclusive(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_name(self._path.name + ".lock")
        with open(lock, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def consume(self, key: str) -> bool:
        """Claim ``key`` exactly once. ``True`` on first claim; ``False`` on replay."""
        with self._exclusive():
            spent = self._load()
            if key in spent:
                return False
            spent.add(key)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(json.dumps(sorted(spent)))
            tmp.replace(self._path)
        return True

    def is_claimed(self, key: str) -> bool:
        """Read-only check (no claim). For inspection / tests."""
        with self._exclusive():
            return key in self._load()


@dataclass(frozen=True)
class DurableSpendClaim:
    """The durable spend key was claimed write-ahead for the first time; the chain
    may proceed to the LA spend. ``receipt_id`` is the claim-record receipt id
    (when a sink is wired)."""

    spend_key: str
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None


@dataclass(frozen=True)
class DurableSpendRefusal:
    """The durable spend gate refused. ``refusal_kind`` is in
    ``DURABLE_SPEND_REFUSALS``: ``playbook_spend_replayed`` (the key was already
    claimed — replay) or ``playbook_spend_basis_incomplete`` (the spend was not
    bound to an exact step/effect/resource/principal/authority)."""

    refusal_kind: str
    detail: str
    spend_key: Optional[str] = None
    receipt_id: Optional[str] = None
    parent_receipt_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.refusal_kind not in DURABLE_SPEND_REFUSALS:
            raise ValueError(
                f"refusal_kind {self.refusal_kind!r} not in "
                f"{sorted(DURABLE_SPEND_REFUSALS)}"
            )


class DurablePlaybookSpendGate:
    """The durable, exactly-once spend gate. Composed by the orchestrator at the
    post-admission / pre-LA-request edge. Refuses an incomplete basis and a
    replayed spend; otherwise claims the durable key write-ahead and lets the
    chain proceed to the LA consume.

    Mirrors ``StandingSpendabilityGate``'s composition shape (optional, emits a
    receipt on both paths, cites the admission receipt as parent).
    """

    def __init__(self, ledger: DurableSpendLedger, receipt_sink: Any | None = None):
        if ledger is None:
            raise ValueError("DurablePlaybookSpendGate requires a DurableSpendLedger")
        self._ledger = ledger
        self._receipt_sink = receipt_sink

    def check(
        self,
        basis: PlaybookSpendBasis,
        *,
        parent_receipt_ids: tuple[str, ...] = (),
    ) -> DurableSpendClaim | DurableSpendRefusal:
        parent = parent_receipt_ids[0] if parent_receipt_ids else None

        # Bind-completeness: no spend without an exact step/effect/resource/
        # principal/authority binding.
        if not basis.is_complete():
            detail = "playbook spend basis is not fully bound (missing field)"
            rid = self._emit(
                verdict=DURABLE_SPEND_REFUSE_VERDICT,
                basis=basis,
                spend_key=None,
                extra={"refusal_kind": REFUSED_INCOMPLETE_BASIS, "detail": detail},
                parent_receipt_id=parent,
            )
            return DurableSpendRefusal(
                refusal_kind=REFUSED_INCOMPLETE_BASIS,
                detail=detail,
                spend_key=None,
                receipt_id=rid,
                parent_receipt_id=parent,
            )

        key = durable_spend_key(basis)

        # Write-ahead claim. False ⇒ this exact spend was already claimed ⇒ replay.
        if not self._ledger.consume(key):
            detail = (
                "durable spend key already claimed; this playbook spend was "
                "already consumed (replay refused before any LA call)"
            )
            rid = self._emit(
                verdict=DURABLE_SPEND_REFUSE_VERDICT,
                basis=basis,
                spend_key=key,
                extra={"refusal_kind": REFUSED_DURABLE_REPLAY, "detail": detail},
                parent_receipt_id=parent,
            )
            return DurableSpendRefusal(
                refusal_kind=REFUSED_DURABLE_REPLAY,
                detail=detail,
                spend_key=key,
                receipt_id=rid,
                parent_receipt_id=parent,
            )

        # First claim — record it and let the chain proceed to the spend.
        rid = self._emit(
            verdict=DURABLE_SPEND_CLAIM_VERDICT,
            basis=basis,
            spend_key=key,
            extra={"record_kind": "playbook_durable_spend_claim"},
            parent_receipt_id=parent,
        )
        return DurableSpendClaim(
            spend_key=key, receipt_id=rid, parent_receipt_id=parent
        )

    def _emit(
        self,
        *,
        verdict: str,
        basis: PlaybookSpendBasis,
        spend_key: Optional[str],
        extra: dict[str, Any],
        parent_receipt_id: Optional[str],
    ) -> Optional[str]:
        if self._receipt_sink is None:
            return None
        i = basis.intent
        evidence_bundle: dict[str, Any] = {
            "authority_admission_receipt_id": basis.authority_admission_receipt_id,
            "principal": i.principal,
            "effect": i.effect,
            "resource": i.resource,
            "amount": i.amount,
            "playbook_spec_digest": i.playbook_spec_digest,
            "step_id": i.step_id,
            "spend_key": spend_key,
            "parent_receipt_ids": [parent_receipt_id] if parent_receipt_id else [],
        }
        evidence_bundle.update(extra)
        subject_bytes = (spend_key or "incomplete").encode("utf-8")
        receipt = self._receipt_sink.emit(
            gate=DURABLE_SPEND_GATE,
            verdict=verdict,
            subject_kind="playbook_durable_spend",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config={"seam": "S5_durable_spend", "basis": DURABLE_SPEND_BASIS_VERSION},
        )
        return receipt.receipt_id


__all__ = [
    "DURABLE_SPEND_BASIS_VERSION",
    "REFUSED_DURABLE_REPLAY",
    "REFUSED_INCOMPLETE_BASIS",
    "DURABLE_SPEND_REFUSALS",
    "DURABLE_SPEND_GATE",
    "PlaybookSpendIntent",
    "PlaybookSpendBasis",
    "durable_spend_key",
    "DurableSpendLedger",
    "DurableSpendClaim",
    "DurableSpendRefusal",
    "DurablePlaybookSpendGate",
]
