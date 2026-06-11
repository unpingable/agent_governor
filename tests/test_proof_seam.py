# SPDX-License-Identifier: Apache-2.0
"""Proof seam (W1 item 4) — refusal class → Lean class-boundary theorem.

The tier discipline is the point: every cited theorem must be PUBLIC-SHIPPED and
a DIRECT class-boundary match (load-bearing), the honest class-not-instance
framing must be present, and refusal classes the kernel does not prove must say
so (None), never borrow an adjacent theorem.
"""

from __future__ import annotations

from governor.proof_seam import (
    CLASS_NOT_INSTANCE,
    CUSTODY_PUBLIC_SHIPPED,
    MATCH_DIRECT,
    NO_KERNEL_THEOREM,
    PROOF_SEAM,
    cite,
    render_proof_seam,
)


def test_hero_maps_to_expired_not_fresh():
    ref = cite("standing_before_spendability_not_bounded")
    assert ref is not None
    assert ref.lean_module == "Admissibility.Freshness"
    assert ref.theorem_name == "expired_not_fresh"
    assert ref.location == "LeanProofs/Admissibility/Freshness.lean:179"
    assert ref.custody_class == CUSTODY_PUBLIC_SHIPPED
    assert ref.match_strength == MATCH_DIRECT
    assert ref.is_load_bearing is True


def test_every_cited_theorem_is_load_bearing():
    # No annex/scratch theorem, no merely-supporting match, may be cited here.
    # If a future edit adds one, this fails — the seam stays [1.0]-direct only.
    for kind, ref in PROOF_SEAM.items():
        assert ref.custody_class == CUSTODY_PUBLIC_SHIPPED, (
            f"{kind} cites a non-PUBLIC-SHIPPED theorem ({ref.custody_class})"
        )
        assert ref.match_strength == MATCH_DIRECT, (
            f"{kind} cites a non-direct theorem ({ref.match_strength})"
        )
        assert ref.is_load_bearing is True


def test_cited_and_uncited_sets_are_disjoint():
    # A class is either licensed by a theorem OR honestly marked as having none
    # — never both (which would be citing and disclaiming the same thing).
    overlap = set(PROOF_SEAM) & set(NO_KERNEL_THEOREM)
    assert not overlap, f"classes both cited and marked uncited: {overlap}"


def test_uncited_classes_return_none_with_a_reason():
    for kind in NO_KERNEL_THEOREM:
        assert cite(kind) is None
        assert NO_KERNEL_THEOREM[kind]  # non-empty reason


def test_already_consumed_is_honestly_uncited():
    # Linearity/exactly-once has no direct kernel theorem; the seam must NOT
    # borrow corrective_no_authority_laundering to fake coverage.
    assert cite("already_consumed") is None
    assert "overclaim" in NO_KERNEL_THEOREM["already_consumed"]


def test_render_carries_honest_framing_for_cited_kinds():
    lines = render_proof_seam("standing_before_spendability_not_bounded")
    blob = "\n".join(lines)
    assert "expired_not_fresh" in blob
    assert "[1.0 PUBLIC-SHIPPED]" in blob
    assert CLASS_NOT_INSTANCE in blob
    # The disclaimer must explicitly refuse the production-safety overclaim.
    assert "does NOT assert that any deployed system is safe" in CLASS_NOT_INSTANCE


def test_render_is_plain_for_uncited_kinds():
    lines = render_proof_seam("already_consumed")
    blob = "\n".join(lines)
    assert "no direct kernel theorem" in blob


def test_observation_and_admission_classes_cite_authority_theorems():
    obs = cite("standing_required")
    assert obs is not None and obs.theorem_name == "no_standing_never_authorized"
    # dangling/expired share the observation≠standing citation.
    assert cite("dangling_receipt_reference") is obs
    assert cite("standing_expired") is obs
    adm = cite("admission_denied")
    assert adm is not None and adm.theorem_name == "no_basis_never_authorized"
