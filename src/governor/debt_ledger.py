"""DebtLedger — authoritative store of rung debts / NonDischargeClaims (P3.0b).

Workflow-kernel campaign, the precondition P3.1 was missing: an effect-bearing
activation gate must recompute the live claim set from an AUTHORITATIVE source,
not a caller-supplied param (a caller-supplied claim set is an alibi, not a live
gate). This is that source.

A dumb record store — it does NOT activate, apply, roll back, mutate config, or
adjudicate authority. (The conservation invariant ``authorized_collector !=
target_rung`` is enforced on the ``RungDebt`` itself; the ledger only records,
indexes, and reports.) It:

- records ``RungDebt`` claims, keyed by ``debt_id``;
- refuses **duplicate-id masking** — a different claim under an existing id is a
  hard error (the P3.0 masking bug, refused at the source);
- preserves source-boundary identity verbatim;
- distinguishes open vs discharged, and returns OPEN claims targeting a rung;
- supports the open→discharged transition as a sanctioned, separate operation
  (NOT a re-record).

P3.1 will read ``live_claim_set = ledger.open_claims(target_rung=...)`` at the
activation gate.
"""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path

from .activation_preflight import RungDebt

_LEDGER_DIRNAME = "debt_ledger"


class DuplicateClaimError(ValueError):
    """A different claim was recorded under an existing debt_id — a masking
    attempt. The debt_id is the claim's identity; one id, one claim."""


class DebtLedger:
    """File-per-store authoritative claim ledger under ``<root>/debt_ledger/``."""

    def __init__(self, root: Path | str):
        self._path = Path(root) / _LEDGER_DIRNAME / "claims.json"

    def _load(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _save(self, claims: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(claims, sort_keys=True, indent=2))
        tmp.replace(self._path)

    @contextmanager
    def _exclusive(self):
        """Serialize read-modify-write across writers (the authoritative source
        must not let two records race past the duplicate-id check)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_name(self._path.name + ".lock")
        with open(lock, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def record(self, debt: RungDebt) -> RungDebt:
        """Record a claim OPEN. Idempotent for an identical re-record; refuses a
        DIFFERENT claim under an existing id (no masking); refuses a
        born-discharged claim (claims are recorded open — discharge() is the only
        path to discharged, so a record cannot hide an open claim at creation)."""
        if not isinstance(debt, RungDebt):
            raise TypeError("record requires a RungDebt")
        if debt.discharged:
            raise ValueError(
                "claims are recorded OPEN; use discharge() for the "
                "open->discharged transition (a born-discharged record could "
                "hide an open claim from open_claims at creation)"
            )
        with self._exclusive():
            claims = self._load()
            existing = claims.get(debt.debt_id)
            if existing is not None:
                if existing == debt.to_dict():
                    return debt  # idempotent
                raise DuplicateClaimError(
                    f"debt_id {debt.debt_id!r} already records a different claim; "
                    "one id maps to one claim (no duplicate-id masking)"
                )
            claims[debt.debt_id] = debt.to_dict()
            self._save(claims)
        return debt

    def discharge(self, debt_id: str) -> RungDebt | None:
        """Sanctioned open→discharged transition (NOT a re-record). Returns the
        discharged claim, or None if the id is unknown. Idempotent if already
        discharged. Does not adjudicate WHO may discharge — that authority lives
        at the activation/rung-transition layer."""
        with self._exclusive():
            claims = self._load()
            record = claims.get(debt_id)
            if record is None:
                return None
            if record.get("discharged", False):
                return RungDebt.from_dict(record)
            discharged = RungDebt.from_dict({**record, "discharged": True})
            claims[debt_id] = discharged.to_dict()
            self._save(claims)
        return discharged

    def get(self, debt_id: str) -> RungDebt | None:
        record = self._load().get(debt_id)
        return RungDebt.from_dict(record) if record is not None else None

    def open_claims(self, target_rung: str) -> tuple[RungDebt, ...]:
        """OPEN claims targeting ``target_rung``, sorted by debt_id. The live set
        an activation gate recomputes against."""
        return tuple(
            sorted(
                (
                    RungDebt.from_dict(r)
                    for r in self._load().values()
                    if r.get("target_rung") == target_rung
                    and not r.get("discharged", False)
                ),
                key=lambda d: d.debt_id,
            )
        )

    def all_claims(self, target_rung: str) -> tuple[RungDebt, ...]:
        """All claims (open AND discharged) targeting ``target_rung``."""
        return tuple(
            sorted(
                (
                    RungDebt.from_dict(r)
                    for r in self._load().values()
                    if r.get("target_rung") == target_rung
                ),
                key=lambda d: d.debt_id,
            )
        )
