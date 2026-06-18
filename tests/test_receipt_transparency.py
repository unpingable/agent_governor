# SPDX-License-Identifier: Apache-2.0
"""Non-claim tests for ``receipt_transparency`` — the firewall, pinned.

The first green artifact of this layer is deliberately NOT "a Merkle proof
verifies" (commodity). It is the firewall:

    a structurally valid InclusionProof still confers no operational effect.

These tests also fence the scope of the unfreeze: the package is skeleton-only
(no accumulator / no proof verification). If that changes, a test here fails.
"""

from __future__ import annotations

import dataclasses

from governor import receipt_transparency as rt
from governor.receipt_transparency import (
    FIREWALL,
    NO_OPERATIONAL_EFFECT,
    AccumulatorKind,
    InclusionProof,
    InclusionVerdict,
    OrderingBasis,
    ReceiptEpochRoot,
    SequenceAuthority,
    operational_effect_of_inclusion,
    root_is_unsigned,
    timestamp_order_has_standing,
)


def _valid_inclusion_proof() -> InclusionProof:
    """A fully-populated, structurally well-formed inclusion proof. Structural
    validity is the strongest input the firewall must withstand."""
    return InclusionProof(
        receipt_id="sha256:" + "a" * 64,
        epoch_id="epoch-7",
        leaf_hash="sha256:" + "b" * 64,
        root_hash="sha256:" + "c" * 64,
        accumulator_kind=AccumulatorKind.MERKLE_V1,
        sibling_path=("sha256:" + "d" * 64, "sha256:" + "e" * 64),
    )


def test_valid_inclusion_proof_confers_no_operational_effect():
    # The soul of the layer: even a structurally valid proof + INCLUDED verdict
    # yields no operational permission. Inclusion is membership, not authority.
    _ = _valid_inclusion_proof()  # structurally valid; still powerless
    assert operational_effect_of_inclusion(InclusionVerdict.INCLUDED) == NO_OPERATIONAL_EFFECT

    # And it holds for EVERY verdict — inclusion never confers effect, period.
    for verdict in InclusionVerdict:
        assert operational_effect_of_inclusion(verdict) == NO_OPERATIONAL_EFFECT


def test_inclusion_proof_has_no_authority_surface():
    # Guard against a future field smuggling authority onto the proof itself.
    field_names = {f.name for f in dataclasses.fields(InclusionProof)}
    authority_words = {"operational", "authorized", "verdict", "grant", "permitted", "effect"}
    assert field_names.isdisjoint(authority_words), (
        f"InclusionProof must carry no authority surface; found {field_names & authority_words}"
    )


def test_timestamp_order_has_no_standing_without_declared_authority():
    # Firewall #3: timestamp order is not causality unless a declared authority
    # gives the clock basis standing. Absence is never a default.
    assert timestamp_order_has_standing(None) is False

    only_predecessors = SequenceAuthority(
        authority_id="seq-1", scope="lab", ordering_basis=(OrderingBasis.PREDECESSOR_EDGES,)
    )
    assert timestamp_order_has_standing(only_predecessors) is False, (
        "declaring predecessor edges does not give wall-clock ordering standing"
    )

    declared_clock = SequenceAuthority(
        authority_id="seq-2", scope="lab", ordering_basis=(OrderingBasis.EXTERNAL_CLOCK_WITNESS,)
    )
    assert timestamp_order_has_standing(declared_clock) is True


def _root(signature: str | None) -> ReceiptEpochRoot:
    return ReceiptEpochRoot(
        epoch_id="epoch-7",
        accumulator_kind=AccumulatorKind.MERKLE_V1,
        membership_rule="admitted-receipts-v1",
        ordering_rule="declared-sequence-only",
        receipt_count=3,
        receipt_set_root="sha256:" + "f" * 64,
        produced_by="ag:main",
        produced_at="2026-06-18T00:00:00Z",
        signature=signature,
    )


def test_unsigned_root_has_no_standing():
    # Firewall #4: an unsigned (or empty-signature) root has no standing.
    assert root_is_unsigned(_root(None)) is True
    assert root_is_unsigned(_root("")) is True
    # A present signature is NOT asserted valid here — the skeleton only refuses
    # the unsigned case; it never grants standing from a slot.
    assert root_is_unsigned(_root("ed25519:deadbeef")) is False


def test_firewall_disclaims_semantic_legitimacy():
    # The five-line firewall is pinned verbatim in length, and the final line
    # must disclaim every authority-flavored property.
    assert len(FIREWALL) == 5
    final = FIREWALL[-1]
    for word in ("legitimacy", "admissibility", "authority", "freshness", "operational"):
        assert word in final, f"firewall must disclaim {word!r}"


def test_layer_is_skeleton_only_no_accumulator():
    # Scope fence for the unfreeze warrant: no proof generation / verification /
    # signature checking has snuck in. If you add an accumulator, you must also
    # re-state the firewall against it — so this test failing is a prompt, not a
    # nuisance.
    for forbidden in ("verify_inclusion", "build_merkle_root", "merkle_root", "verify_signature"):
        assert not hasattr(rt, forbidden), (
            f"{forbidden!r} present — skeleton scope exceeded; re-pin the firewall before shipping it"
        )
