"""Prep-before-ingest indecomposable-gate blocker (P3.4).

The smallest runtime behavior that USES the decomposition-completeness receipt
shape (P3.3) without pretending the sibling tools exist. Cashes one line of
doctrine into behavior: a plan whose decomposition admits an indecomposable gate
is **inadmissible to ingest** until that gate is discharged by an authorized
party. Ingest is a rung transition (the plan's 0→1), so this is the rung-activation
gate pointed at the plan boundary (`docs/cross-tool/decomposition-capability-
closure-note.md` §Prep-before-ingest).

Hot-path class (campaign ground rule 14): **semantic-conversion / gate-admission**.
It also installs the first guard on the DISCHARGE hot path
(`docs/cross-tool/hotpath-and-granularity-note.md`): *a claim becoming non-blocking
is consequence-bearing.*

Scope discipline — **a clearance socket, not a discharge subsystem.** This module
owns ONE claim kind (`indecomposable_gate`) and ONE operator-gated discharge
socket. It does NOT touch `DebtLedger.discharge()` (which stays a generic flag-flip,
not made generally safe), and there is NO non-operator discharge path for this
claim kind. What P3.4 does NOT do: decide *whether* a gate is decomposable (that
judgment is operator/verifier — assert-standing, future); verifier wiring; the
capability kernel; seam-cap composition; general collector-binding/provenance
hardening (that stays `GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001`).

The planner may PROPOSE a decomposition; it may not certify that judgment vanished
— so re-running prep never clears an open claim, and the only clearance is an
operator-receipted discharge.
"""

from __future__ import annotations

import fcntl
import json
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .gate_receipt import canonical_json, content_hash

INDECOMPOSABLE_GATE = "indecomposable_gate"
INGEST_TARGET = "plan_ingest"

_LEDGER_DIRNAME = "prep_ingest_ledger"


def _ref_ok(ref: object) -> bool:
    return isinstance(ref, str) and bool(ref.strip())


def _record_cleared(record: dict) -> bool:
    """A stored claim is non-blocking ONLY if it is discharged AND carries a real
    operator receipt ref. A ``discharged=True`` record with no/empty operator ref
    is malformed or tampered — it is treated as STILL BLOCKING (fail-closed): a
    claim becomes non-blocking exclusively through an operator-receipted discharge,
    so the READER enforces that invariant, not just the write API."""
    return bool(record.get("discharged")) and _ref_ok(record.get("operator_receipt_ref"))


# --------------------------------------------------------------------------- #
# Operator discharge evidence — structured, smells like P3.3's evidence sockets
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OperatorDischargeEvidence:
    """An operator's clearance of one indecomposable-gate claim, carried as a
    receipt REFERENCE — not a bare ``operator_cleared=True`` flag a pleadable
    component could set on itself (model is not principal). Same anti-forgery
    shape as P3.3's evidence objects: a non-empty STRING ref, never a bool/
    whitespace. Genuine provenance of the ref is the later custody-anchoring rung
    (`GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001`); this socket enforces the shape."""

    operator_receipt_ref: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.operator_receipt_ref, str)
            or not self.operator_receipt_ref.strip()
        ):
            raise ValueError(
                "OperatorDischargeEvidence requires a non-empty string "
                "operator_receipt_ref (a bare flag is not an operator clearance; "
                "model is not principal)"
            )


# --------------------------------------------------------------------------- #
# Plan gates (input) + the claim
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PlanGate:
    """A declared gate in a plan's decomposition. ``decomposable`` is an UPSTREAM
    classification (operator/verifier judgment — NOT decided here). P3.4 records a
    blocking claim for each gate declared indecomposable; it does not adjudicate
    the flag."""

    gate_id: str
    decomposable: bool
    reason: str = ""


@dataclass(frozen=True)
class IndecomposableGateClaim:
    """A NonDischargeClaim of kind ``indecomposable_gate`` blocking ``plan_ingest``.
    Content-addressed by ``(kind, plan_id, gate_id)`` — the ``plan_id`` namespace is
    load-bearing: two DIFFERENT plans sharing a ``gate_id`` must NOT collapse into
    one claim (else clearing one plan's gate would clear the other's). Re-detecting
    the same gate in the same plan yields the same claim (idempotent, no duplicate,
    no silent clear). When discharged it is NOT deleted — it remains auditable as a
    prior blocker, carrying the operator receipt ref that cleared it."""

    plan_id: str
    gate_id: str
    reason: str = ""
    kind: str = INDECOMPOSABLE_GATE
    target: str = INGEST_TARGET
    discharged: bool = False
    operator_receipt_ref: str | None = None

    def __post_init__(self) -> None:
        # Identity fields are part of custody, not decoration. A blank plan_id or
        # gate_id is an INVALID claim identity — not "the same gate" — and would
        # collapse distinct blockers into one claim_id (one discharge clearing
        # several). Refused at construction (covers prep_detect, record, from_dict).
        if not _ref_ok(self.plan_id):
            raise ValueError(
                "IndecomposableGateClaim requires a non-empty string plan_id"
            )
        if not _ref_ok(self.gate_id):
            raise ValueError(
                "IndecomposableGateClaim requires a non-empty string gate_id "
                "(a blank gate is not the same gate — it is an invalid claim identity)"
            )

    @property
    def is_cleared(self) -> bool:
        """Public semantic predicate: a claim is non-blocking ONLY if discharged
        AND carrying a real operator receipt ref. The raw ``discharged`` flag is
        storage; this is the semantics (fail-closed — a discharged-without-ref
        claim is NOT cleared). Audit callers should read this, not the raw flag."""
        return self.discharged and _ref_ok(self.operator_receipt_ref)

    @property
    def claim_id(self) -> str:
        return content_hash(
            canonical_json(
                {"kind": self.kind, "plan_id": self.plan_id, "gate_id": self.gate_id}
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "kind": self.kind,
            "target": self.target,
            "plan_id": self.plan_id,
            "gate_id": self.gate_id,
            "reason": self.reason,
            "discharged": self.discharged,
            "operator_receipt_ref": self.operator_receipt_ref,
        }

    @classmethod
    def from_dict(cls, d: dict) -> IndecomposableGateClaim:
        return cls(
            plan_id=d["plan_id"],
            gate_id=d["gate_id"],
            reason=d.get("reason", ""),
            kind=d.get("kind", INDECOMPOSABLE_GATE),
            target=d.get("target", INGEST_TARGET),
            discharged=d.get("discharged", False),
            operator_receipt_ref=d.get("operator_receipt_ref"),
        )


class IngestRefused(Exception):
    """Plan ingest refused: one or more indecomposable-gate claims are open.
    Carries the offending claim ids so the refusal is walkable."""

    def __init__(self, open_claim_ids: tuple[str, ...]):
        super().__init__(
            f"plan ingest refused: {len(open_claim_ids)} indecomposable-gate "
            f"claim(s) open ({', '.join(open_claim_ids)})"
        )
        self.open_claim_ids = open_claim_ids


# --------------------------------------------------------------------------- #
# The ledger — operator-gated discharge ONLY (no generic flag-flip)
# --------------------------------------------------------------------------- #


class PrepIngestLedger:
    """File-backed store for indecomposable-gate claims under
    ``<root>/prep_ingest_ledger/``. The ONLY discharge path is operator-gated
    (``operator_discharge`` requires :class:`OperatorDischargeEvidence`) — there is
    deliberately no generic ``discharge(id)`` flag-flip for this claim kind."""

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
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_name(self._path.name + ".lock")
        with open(lock, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def record(self, claim: IndecomposableGateClaim) -> IndecomposableGateClaim:
        """Record a claim OPEN. Idempotent on claim_id — re-recording the same gate
        does NOT create a duplicate and does NOT clear an existing (open or
        discharged) claim. Refuses a born-discharged record (only operator_discharge
        may move open→discharged)."""
        if not isinstance(claim, IndecomposableGateClaim):
            raise TypeError("record requires an IndecomposableGateClaim")
        if claim.discharged or claim.operator_receipt_ref is not None:
            raise ValueError(
                "claims are recorded OPEN; use operator_discharge() for the "
                "open->discharged transition"
            )
        with self._exclusive():
            claims = self._load()
            if claim.claim_id not in claims:
                claims[claim.claim_id] = claim.to_dict()
                self._save(claims)
            # else: an existing claim (open OR discharged) is left untouched —
            # re-running prep cannot resurrect, duplicate, or clear it.
            return IndecomposableGateClaim.from_dict(claims[claim.claim_id])

    def get(self, claim_id: str) -> IndecomposableGateClaim | None:
        record = self._load().get(claim_id)
        return IndecomposableGateClaim.from_dict(record) if record else None

    def open_claims(self) -> tuple[IndecomposableGateClaim, ...]:
        """Blocking claims — those NOT cleared by an operator-receipted discharge.
        Uses the fail-closed predicate, so a malformed discharged-without-ref
        record reads as blocking (never silently admits ingest)."""
        return tuple(
            sorted(
                (
                    IndecomposableGateClaim.from_dict(r)
                    for r in self._load().values()
                    if not _record_cleared(r)
                ),
                key=lambda c: c.claim_id,
            )
        )

    def all_claims(self) -> tuple[IndecomposableGateClaim, ...]:
        """Every claim, open AND discharged — discharged ones remain auditable as
        prior blockers."""
        return tuple(
            sorted(
                (IndecomposableGateClaim.from_dict(r) for r in self._load().values()),
                key=lambda c: c.claim_id,
            )
        )

    def operator_discharge(
        self, claim_id: str, evidence: OperatorDischargeEvidence
    ) -> IndecomposableGateClaim:
        """The ONE clearance socket. Requires structured operator evidence; marks
        the claim discharged WITHOUT deleting it (retains the operator receipt ref
        for audit). Refuses a non-evidence / unknown claim. This is the only path
        a claim of this kind becomes non-blocking — there is no generic flag-flip."""
        if not isinstance(evidence, OperatorDischargeEvidence):
            raise ValueError(
                "operator_discharge requires OperatorDischargeEvidence; a generic "
                "discharge without operator evidence is refused for this claim kind"
            )
        with self._exclusive():
            claims = self._load()
            record = claims.get(claim_id)
            if record is None:
                raise KeyError(f"unknown indecomposable-gate claim {claim_id!r}")
            if _record_cleared(record):
                # Idempotent ONLY when properly cleared (discharged + real ref). A
                # malformed discharged-without-ref record is NOT cleared, so it
                # falls through and a genuine operator receipt repairs/re-clears it.
                return IndecomposableGateClaim.from_dict(record)
            discharged = IndecomposableGateClaim.from_dict(
                {
                    **record,
                    "discharged": True,
                    "operator_receipt_ref": evidence.operator_receipt_ref,
                }
            )
            claims[claim_id] = discharged.to_dict()
            self._save(claims)
        return discharged

    def ingest_admissible(self) -> bool:
        """True iff no indecomposable-gate claim is open."""
        return not self.open_claims()


# --------------------------------------------------------------------------- #
# Prep + the ingest gate
# --------------------------------------------------------------------------- #


def prep_detect(
    plan_id: str, plan_gates: Sequence[PlanGate], ledger: PrepIngestLedger
) -> tuple[IndecomposableGateClaim, ...]:
    """Record a blocking claim for every gate declared INDECOMPOSABLE in plan
    ``plan_id``. Returns the claims for this plan's indecomposable gates (open or
    already-discharged). Claims are namespaced by ``plan_id`` so two plans sharing
    a gate_id do not collide. NEVER discharges — a re-run where the planner now
    declares a gate decomposable does NOT clear an existing claim (the planner may
    propose, not self-certify)."""
    if not _ref_ok(plan_id):
        raise ValueError("prep_detect requires a non-empty plan_id namespace")
    out: list[IndecomposableGateClaim] = []
    for gate in plan_gates:
        if gate.decomposable:
            continue
        out.append(
            ledger.record(
                IndecomposableGateClaim(
                    plan_id=plan_id, gate_id=gate.gate_id, reason=gate.reason
                )
            )
        )
    return tuple(out)


def assert_ingest_admissible(ledger: PrepIngestLedger) -> None:
    """Raise :class:`IngestRefused` if any indecomposable-gate claim is open. The
    plan does not enter the workflow while its decomposition admits a gate it
    cannot decompose."""
    open_claims = ledger.open_claims()
    if open_claims:
        raise IngestRefused(tuple(c.claim_id for c in open_claims))
