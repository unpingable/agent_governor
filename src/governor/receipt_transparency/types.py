# SPDX-License-Identifier: Apache-2.0
"""
Receipt transparency — skeleton types for a transparent receipt log.

Certificate-Transparency / Rekor-shaped, NOT blockchain. These are the
committed-set commitment, the compact membership proof, the history-extension /
split-view proofs, and the ordering-authority declaration. See
``specs/gaps/GOV_GAP_RECEIPT_TRANSPARENCY_001.md``.

This module is SKELETON ONLY: frozen dataclasses + closed enums + the firewall
guards. There is deliberately NO accumulator, NO proof generation, and NO
signature verification here. ``InclusionProof`` is a value, not a verifier;
``ReceiptEpochRoot.signature`` is a slot, not a checked signature. The real
machinery earns implementation on a forcing case (a consumer that must verify
witness-bundle membership without the full receipt substrate).

THE FIREWALL (proposed doctrine — the reason this module exists):

  1. Inclusion proves membership in a committed receipt set.
  2. Consistency proves one committed set extends another.
  3. Ordering proves only the declared sequence relation.
  4. Signatures prove custody over the signed artifact.
  5. None of the above proves semantic legitimacy, admissibility, authority,
     freshness, or operational permission.

Do NOT let a Merkle root start acting like it contains morality. Inclusion is
not admissibility; timestamp order is not causality; an unsigned root has no
standing. The guards below encode those non-claims; the tests pin them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# The five-line firewall, as data so a test can pin it verbatim.
FIREWALL: tuple[str, ...] = (
    "inclusion proves membership in a committed receipt set",
    "consistency proves one committed set extends another",
    "ordering proves only the declared sequence relation",
    "signatures prove custody over the signed artifact",
    "none of the above proves semantic legitimacy, admissibility, authority, "
    "freshness, or operational permission",
)

# The constant non-authority stance. Inclusion (even INCLUDED) returns this,
# always — it is the typed "no operational effect" sentinel.
NO_OPERATIONAL_EFFECT = "no_operational_effect"


class AccumulatorKind(str, Enum):
    """Closed set of accumulator kinds. Only ``merkle_v1`` is named; no logic
    backs it yet."""

    MERKLE_V1 = "merkle_v1"


class OrderingBasis(str, Enum):
    """How a :class:`SequenceAuthority` may declare ordering standing. A basis
    must be *declared* to carry standing — absence is not a default."""

    PREDECESSOR_EDGES = "predecessor_edges"
    MONOTONIC_SEQUENCE = "monotonic_sequence"
    SOURCE_SEQUENCE = "source_sequence"
    EXTERNAL_CLOCK_WITNESS = "external_clock_witness"


class InclusionVerdict(str, Enum):
    """The shape a future ``verify_inclusion`` would return. No code in this
    module produces it — it exists so the firewall can be stated over it."""

    INCLUDED = "included"
    NOT_INCLUDED = "not_included"
    MALFORMED = "malformed"


@dataclass(frozen=True)
class ReceiptEpochRoot:
    """The committed-set commitment for one epoch.

    The root proves committed *membership* only. It does not prove semantic
    validity. ``signature`` is a slot; this module does not verify it.
    """

    epoch_id: str
    accumulator_kind: AccumulatorKind
    membership_rule: str
    ordering_rule: str
    receipt_count: int
    receipt_set_root: str
    produced_by: str
    produced_at: str
    previous_epoch_id: str | None = None
    previous_root_hash: str | None = None
    signature: str | None = None


@dataclass(frozen=True)
class InclusionProof:
    """A compact "receipt R was in epoch E" proof. A value, not a verifier."""

    receipt_id: str
    epoch_id: str
    leaf_hash: str
    root_hash: str
    accumulator_kind: AccumulatorKind
    sibling_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConsistencyProof:
    """Proof that ``to_epoch`` extends ``from_epoch`` rather than replacing
    history. The accumulator analog of ``receipt_kernel``'s chain validity."""

    from_epoch: str
    to_epoch: str
    from_root: str
    to_root: str
    proof_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class ForkEvidenceReceipt:
    """Two incompatible roots for one epoch/lineage — split-view equivocation,
    recorded as admissible evidence. Forking becomes an accountable act."""

    epoch_id: str
    root_a: str
    root_b: str
    observed_by: str
    evidence: str


@dataclass(frozen=True)
class SequenceAuthority:
    """A declared authority over ordering for some receipt kinds. Ordering is
    custody: whoever sequences receipts can launder meaning by delay, omission,
    or rearrangement. A basis must be declared to carry standing."""

    authority_id: str
    scope: str
    ordering_basis: tuple[OrderingBasis, ...] = ()
    may_order_receipt_kinds: tuple[str, ...] = field(default_factory=tuple)


# --- firewall guards (the non-claims, as testable code) ------------------- #


def operational_effect_of_inclusion(verdict: InclusionVerdict) -> str:
    """Firewall #1/#5: inclusion proves membership, never operational permission.

    Returns :data:`NO_OPERATIONAL_EFFECT` for *every* verdict — including
    ``INCLUDED``. A valid inclusion proof still confers no effect; that crossing
    is the gate's to make, on standing, never the proof's.
    """
    return NO_OPERATIONAL_EFFECT


def timestamp_order_has_standing(authority: SequenceAuthority | None) -> bool:
    """Firewall #3: timestamp order is not causality unless a declared authority
    gives the clock basis standing.

    True only when ``authority`` is present AND has explicitly declared
    ``EXTERNAL_CLOCK_WITNESS`` in its ordering basis. No authority, or an
    authority that declared only (say) predecessor edges, means a wall-clock
    ordering carries no standing — absence is never a default.
    """
    return authority is not None and OrderingBasis.EXTERNAL_CLOCK_WITNESS in authority.ordering_basis


def root_is_unsigned(root: ReceiptEpochRoot) -> bool:
    """Firewall #4: an unsigned root has no standing.

    Returns True when the signature slot is empty. NOTE the asymmetry: a present
    signature is NOT asserted valid here (verification is later, forcing-case
    work) — this skeleton only refuses the unsigned case, it never grants
    standing.
    """
    return not root.signature
