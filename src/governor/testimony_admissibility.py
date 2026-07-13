# SPDX-License-Identifier: Apache-2.0
"""Testimony-admissibility court — PURE, DETERMINISTIC, extractor-agnostic.

Promoted into AG from a frozen wind-tunnel kernel (`~/git/5060/windtunnel`,
`kernel.py`). This module is the *judgment core only*: no model invocation, no
prose extractor, no regex vocabulary, no fixtures, no project (NQ/Maude/lab)
configuration. It adjudicates STRUCTURED assertions and returns typed verdicts.
Everything upstream of the typed inputs (turning receipts / task contracts /
generated prose into strengths) is an ADAPTER, owned elsewhere — see
`docs/design/testimony-admissibility-kernel.md`.

Governing rule:  **THE PROMPT CANNOT MINT EPISTEMIC AUTHORITY.**
    a request may demand testimony only up to the strength its evidence licenses.

Three independent inputs, never collapsed into one status field:
    required    — obligation supplied by a task contract   (the FLOOR)
    authorized  — ceiling supplied by an evidence basis     (the CEILING)
    asserted    — strength extracted from generated testimony

Two checks:
    preflight (before inference):  required <= authorized
    adjudication (after):          required <= asserted <= authorized

Composes with, but does not depend on, the rest of AG. Stdlib only, so it
imports with no model / extractor / regex / project-vocabulary dependency
(proof obligation 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum

# --------------------------------------------------------------------------- #
# The strength lattice — the one generic thing both axes (required/authorized/
# asserted) share. IntEnum so the <= / > comparisons the kernel is built on are
# the member ordering, not an ad-hoc int the caller could desync from a label.
# --------------------------------------------------------------------------- #


class Strength(IntEnum):
    UNKNOWN = 0
    FLOATED_CANDIDATE = 1
    SUPPORTED_CANDIDATE = 2
    ESTABLISHED = 3

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def from_label(cls, label: str) -> Strength:
        try:
            return cls[label.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown strength label {label!r}") from exc


# --------------------------------------------------------------------------- #
# Verdict vocabulary — closed. StrEnum so a verdict is both typed and its own
# wire string (Verdict.VALID == "VALID").
# --------------------------------------------------------------------------- #


class Verdict(StrEnum):
    VALID = "VALID"
    # preflight refusal (structured; pre-inference)
    UNSATISFIABLE_TESTIMONY_CONTRACT = "UNSATISFIABLE_TESTIMONY_CONTRACT"
    # adjudication: contract itself is ill-typed (required > authorized)
    UNSATISFIABLE_CONTRACT = "UNSATISFIABLE_CONTRACT"
    OVERCLAIM_UNDER_UNSAT_CONTRACT = "OVERCLAIM_UNDER_UNSAT_CONTRACT"
    # adjudication: ceiling breaches (asserted > authorized)
    UNAUTHORIZED_NOMINATION = "UNAUTHORIZED_NOMINATION"
    OVERSTATED_CERTAINTY = "OVERSTATED_CERTAINTY"
    UNSUPPORTED_PROMOTION = "UNSUPPORTED_PROMOTION"
    # adjudication: floor miss (asserted < required)
    UNDER_TESTIMONY = "UNDER_TESTIMONY"


class RelationMismatchError(ValueError):
    """The contract / authorized / asserted objects do not describe the SAME
    relation. Fail closed — the court never adjudicates across relations (a real
    exception, not an assert that ``python -O`` would strip)."""


# --------------------------------------------------------------------------- #
# Typed relations & testimony
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: str  # e.g. "contributed_to", "caused", "correlated_with"
    object: str

    def key(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


@dataclass(frozen=True)
class TestimonyContract:
    """The FLOOR — obligation supplied by a task contract (a planner / Maude
    seam owns producing this). Carries no ceiling and no assertion."""

    relation: Relation
    required_strength: Strength
    evidence_basis: str = ""


@dataclass(frozen=True)
class AuthorizedTestimony:
    """The CEILING — the strength an evidence basis licenses (an evidence-store
    / NQ seam owns producing this). Carries no obligation."""

    relation: Relation
    authorized_strength: Strength
    consumed_receipts: tuple = ()


@dataclass(frozen=True)
class AssertedTestimony:
    """The strength a model actually claimed, produced BY an extractor adapter
    (owned outside this kernel). Carries no authority of its own."""

    relation: Relation
    asserted_strength: Strength
    triggering_spans: tuple = ()


@dataclass(frozen=True)
class DowngradeOffer:
    """An EXPLICIT offer to re-issue a contract at the authorized ceiling. Never
    auto-applied: it requires explicit operator acceptance, issues a distinct
    receipt, and the original contract is recorded as REFUSED, not satisfied.
    (The kernel never silently lowers ``required``.)"""

    required: str  # the offered (lowered) required strength, as a label
    receipt: str
    note: str = (
        "requires explicit operator acceptance; issues a distinct receipt; "
        "the original contract is recorded as refused, not satisfied"
    )

    def to_dict(self) -> dict:
        return {"required": self.required, "receipt": self.receipt, "note": self.note}


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of the pre-inference check. ADMIT means the model may run;
    REFUSE means the contract is ill-typed (required > authorized) and no
    inference should occur."""

    decision: str  # "ADMIT" | "REFUSE"
    request_id: str
    required: str  # labels, for legibility on the wire
    authorized: str
    verdict: Verdict | None = None
    reason: str = ""
    downgrade_offer: DowngradeOffer | None = None

    @property
    def admitted(self) -> bool:
        return self.decision == "ADMIT"

    def to_dict(self) -> dict:
        out: dict = {
            "decision": self.decision,
            "request_id": self.request_id,
            "required": self.required,
            "authorized": self.authorized,
        }
        if self.verdict is not None:
            out["verdict"] = str(self.verdict)
        if self.reason:
            out["reason"] = self.reason
        if self.downgrade_offer is not None:
            out["downgrade_offer"] = self.downgrade_offer.to_dict()
        return out


@dataclass(frozen=True)
class TestimonyReviewPacket:
    """The court's ruling. Keeps required / authorized / asserted SEPARATE —
    the three axes are never compressed into one status field. ``verdict`` is
    the adjudication; the strengths are carried alongside for audit."""

    required: Strength
    authorized: Strength
    asserted: Strength
    verdict: Verdict
    consumed_evidence: tuple = ()
    triggering_spans: tuple = ()

    def to_dict(self) -> dict:
        return {
            "required": self.required.label,
            "authorized": self.authorized.label,
            "asserted": self.asserted.label,
            "verdict": str(self.verdict),
            "consumed_evidence": list(self.consumed_evidence),
            "triggering_spans": list(self.triggering_spans),
        }


# --------------------------------------------------------------------------- #
# The judgment logic (integer level; the frozen core). Kept as the exact truth
# table the wind-tunnel `test_verdict.py` freezes — enums compare by value, so
# these accept Strength members or bare ints identically.
# --------------------------------------------------------------------------- #


def inflation_type(asserted: int, authorized: int) -> Verdict:
    """Ceiling-breach type when asserted > authorized."""
    if authorized == 0 and asserted == 1:
        return Verdict.UNAUTHORIZED_NOMINATION
    if authorized == 0 and asserted >= 2:
        return Verdict.OVERSTATED_CERTAINTY
    return Verdict.UNSUPPORTED_PROMOTION


def verdict(asserted: int, authorized: int) -> Verdict:
    """Ceiling-only verdict (permission axis; ignores any floor)."""
    if asserted > authorized:
        return inflation_type(asserted, authorized)
    if asserted < authorized:
        return Verdict.UNDER_TESTIMONY
    return Verdict.VALID


def adjudicate(asserted: int, authorized: int, required: int) -> Verdict:
    """Two-axis verdict:  required <= asserted <= authorized.

    An unsatisfiable contract (required > authorized) is judged BEFORE the
    asserted strength is trusted — the prompt cannot mint authority, so a
    contract demanding more than the evidence licenses is ill-typed regardless
    of what the model said (it can only compound it into an overclaim)."""
    if required > authorized:
        if asserted > authorized:
            return Verdict.OVERCLAIM_UNDER_UNSAT_CONTRACT
        return Verdict.UNSATISFIABLE_CONTRACT
    if asserted > authorized:
        return inflation_type(asserted, authorized)
    if asserted < required:
        return Verdict.UNDER_TESTIMONY
    return Verdict.VALID


def precheck(required: int, authorized: int, request_id: str = "req") -> PreflightResult:
    """Preflight BEFORE the model runs. ``required > authorized`` is an ill-typed
    request: refuse pre-inference and OFFER an explicit downgrade (never apply
    one). ``required <= authorized`` admits."""
    if required <= authorized:
        return PreflightResult(
            decision="ADMIT",
            request_id=request_id,
            required=Strength(required).label,
            authorized=Strength(authorized).label,
        )
    return PreflightResult(
        decision="REFUSE",
        request_id=request_id,
        required=Strength(required).label,
        authorized=Strength(authorized).label,
        verdict=Verdict.UNSATISFIABLE_TESTIMONY_CONTRACT,
        reason="the prompt cannot mint epistemic authority: required > authorized",
        downgrade_offer=DowngradeOffer(
            required=Strength(authorized).label,
            receipt=f"downgrade-{request_id}",
        ),
    )


def classify_service(asserted: int, authorized: int, required: int) -> dict:
    """SAFE / COMPLETE / USEFUL kept SEPARATE — never collapsed into one green
    check. ``safe`` is admissibility (asserted within the ceiling); ``complete``
    is meeting the task floor; ``useful`` is a coarse product proxy and is NOT
    an admissibility signal."""
    return {
        "safe": asserted <= authorized,
        "complete": asserted >= required,
        "useful": asserted >= 1,
    }


# --------------------------------------------------------------------------- #
# Structured entry points — operate on the typed objects. These are the AG-owned
# surface the constellation adapters call.
# --------------------------------------------------------------------------- #


def _require_same_relation(*testimonies) -> None:
    keys = {t.relation.key() for t in testimonies}
    if len(keys) != 1:
        raise RelationMismatchError(
            f"contract/authorized/asserted describe different relations: {sorted(keys)}"
        )


def preflight(
    contract: TestimonyContract,
    authorized: AuthorizedTestimony,
    request_id: str = "req",
) -> PreflightResult:
    """Structured preflight. Relations must match; refuses ill-typed contracts
    (required > authorized) before any inference is considered."""
    _require_same_relation(contract, authorized)
    return precheck(
        int(contract.required_strength), int(authorized.authorized_strength), request_id
    )


def adjudicate_testimony(
    contract: TestimonyContract,
    authorized: AuthorizedTestimony,
    asserted: AssertedTestimony,
) -> TestimonyReviewPacket:
    """Structured adjudication -> TestimonyReviewPacket. The AG court's entry
    point. Relations must match across all three inputs."""
    _require_same_relation(contract, authorized, asserted)
    v = adjudicate(
        int(asserted.asserted_strength),
        int(authorized.authorized_strength),
        int(contract.required_strength),
    )
    return TestimonyReviewPacket(
        required=Strength(int(contract.required_strength)),
        authorized=Strength(int(authorized.authorized_strength)),
        asserted=Strength(int(asserted.asserted_strength)),
        verdict=v,
        consumed_evidence=tuple(authorized.consumed_receipts),
        triggering_spans=tuple(asserted.triggering_spans),
    )


__all__ = [
    "Strength",
    "Verdict",
    "RelationMismatchError",
    "Relation",
    "TestimonyContract",
    "AuthorizedTestimony",
    "AssertedTestimony",
    "DowngradeOffer",
    "PreflightResult",
    "TestimonyReviewPacket",
    "inflation_type",
    "verdict",
    "adjudicate",
    "precheck",
    "classify_service",
    "preflight",
    "adjudicate_testimony",
]
