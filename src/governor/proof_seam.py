# SPDX-License-Identifier: Apache-2.0
"""Proof seam — refusal CLASS → Lean class-boundary theorem (the demo's Act 3).

W1 item 4. This is the "necessity" descent: a refusal is not a discretionary
policy denial; it is the refusal *required* by a custody discipline whose class
boundary is proved in the Lean kernel (`~/git/lean/LeanProofs/Admissibility/`).

The honest framing is load-bearing (launch plan; the "blazer-shaped grave"):

  * The **theorem** proves the CLASS BOUNDARY / admissibility invariant
    (e.g. "an observation past its horizon is not fresh").
  * The **receipt** proves the INSTANCE facts (this standing, these two clocks,
    this gap).
  * This citation is the LINK between them — NOT a claim that Lean proved any
    deployed system safe, nor that this instance was machine-checked. Only that
    the refusal CLASS is the one the kernel licenses.

A receipt has no theorem stored on it; the link is DERIVED from the receipt's
`refusal_kind` via this seam (the theorem is about the class, identical across
every instance of that kind — storing it per-receipt would be redundant and
would risk implying the instance itself was proved).

Citation discipline (`memory/feedback_lean_citation_tiers`): only PUBLIC-SHIPPED
([1.0] stable) theorems are cited as load-bearing; ANNEX is "compiled, not
promised" and may only inform. Every theorem here was verified 2026-06-12 against
the lean repo: exact name, complete proof (no `sorry`), PUBLIC-SHIPPED custody
class. Where the kernel has NO direct theorem for a refusal class, this seam says
so plainly (``NO_KERNEL_THEOREM``) rather than stretch an adjacent theorem to fit
— the absence is itself honest evidence about coverage.

Not a citation source: ``~/git/rkl`` (the Refusal Kernel *Lab*) pokes these same
boundaries across substrates — it has a freshness-expiry specimen (the hero's
shape) and the ``unmodeled-is-never-admitted`` invariant (the operational fence's
allowlist shape). But RKL is a playground by its own banner ("not proof, not a
source of truth, no consumer promise") — [scratch] tier. It may *inform*; it may
not *license*. Nothing here cites it; the load-bearing citations are the Lean
PUBLIC-SHIPPED theorems only.
"""

from __future__ import annotations

from dataclasses import dataclass

# Custody classes mirrored from the lean repo's per-file "Custody-Class:" header.
CUSTODY_PUBLIC_SHIPPED = "PUBLIC-SHIPPED"  # [1.0] stable — may anchor a claim
CUSTODY_ANNEX = "ANNEX"  # compiled, not promised — informs, does not ratify

# Match strength of the class→theorem link. "direct" = the theorem's statement
# IS the refusal class boundary; "supporting" = adjacent/complementary.
MATCH_DIRECT = "direct"
MATCH_SUPPORTING = "supporting"

# The honest-framing sentence the Act-3 render carries verbatim.
CLASS_NOT_INSTANCE = (
    "The theorem proves the refusal CLASS boundary; the receipt proves the "
    "INSTANCE facts; this citation is the link. It does NOT assert that any "
    "deployed system is safe or correct, nor that this instance was "
    "machine-checked — only that this refusal is the one the kernel licenses."
)


@dataclass(frozen=True)
class TheoremRef:
    """A citation to a Lean class-boundary theorem. All fields verified against
    the lean repo on the date in ``verified_at`` — re-verify before bumping."""

    lean_module: str  # e.g. "Admissibility.Freshness"
    theorem_name: str  # e.g. "expired_not_fresh"
    location: str  # repo-relative path:line
    custody_class: str  # CUSTODY_* (only PUBLIC-SHIPPED is load-bearing)
    statement: str  # the Lean proposition, as written
    proves: str  # the class boundary in words
    match_strength: str  # MATCH_*
    verified_at: str = "2026-06-12"

    @property
    def is_load_bearing(self) -> bool:
        """True iff this citation may anchor a claim (PUBLIC-SHIPPED + direct)."""
        return (
            self.custody_class == CUSTODY_PUBLIC_SHIPPED
            and self.match_strength == MATCH_DIRECT
        )


# refusal_kind -> the kernel theorem whose statement IS that class boundary.
# Verified 2026-06-12: each is PUBLIC-SHIPPED with a complete proof (no sorry).
PROOF_SEAM: dict[str, TheoremRef] = {
    "standing_before_spendability_not_bounded": TheoremRef(
        lean_module="Admissibility.Freshness",
        theorem_name="expired_not_fresh",
        location="LeanProofs/Admissibility/Freshness.lean:179",
        custody_class=CUSTODY_PUBLIC_SHIPPED,
        statement="(h : ¬ (now ≤ expires + skew)) : ¬ Fresh now issued expires skew maxDiv",
        proves=(
            "An observation whose exercise time is past the (skewed) expiry "
            "horizon is not Fresh — standing valid when observed does not "
            "license a spend after its horizon. Post-validated ≠ pre-authorized."
        ),
        match_strength=MATCH_DIRECT,
    ),
    "standing_required": TheoremRef(
        lean_module="Admissibility.Authority",
        theorem_name="no_standing_never_authorized",
        location="LeanProofs/Admissibility/Authority.lean:109",
        custody_class=CUSTODY_PUBLIC_SHIPPED,
        statement="authorityVerdict b p StandingVerdict.noStanding ≠ AuthorityVerdict.authorized",
        proves=(
            "With no standing, no combination of basis/precedence yields an "
            "authorized verdict — observation does not mint authority."
        ),
        match_strength=MATCH_DIRECT,
    ),
    "admission_denied": TheoremRef(
        lean_module="Admissibility.Authority",
        theorem_name="no_basis_never_authorized",
        location="LeanProofs/Admissibility/Authority.lean:89",
        custody_class=CUSTODY_PUBLIC_SHIPPED,
        statement="authorityVerdict BasisVerdict.noBasis p s ≠ AuthorityVerdict.authorized",
        proves=(
            "With no admissible basis, no combination of precedence/standing "
            "yields an authorized verdict — standing does not mint admissibility."
        ),
        match_strength=MATCH_DIRECT,
    ),
}

# The standing seam emits `dangling_receipt_reference`; the scenario layer
# surfaces it as `standing_expired` / `standing_required`. Both are the
# observation≠standing class, so they share the citation.
PROOF_SEAM["dangling_receipt_reference"] = PROOF_SEAM["standing_required"]
PROOF_SEAM["standing_expired"] = PROOF_SEAM["standing_required"]

# Refusal classes for which the kernel has NO direct class-boundary theorem
# today. Recorded honestly — the seam does not stretch an adjacent theorem to
# cover them. Value = why (so the gap is legible, not silent).
NO_KERNEL_THEOREM: dict[str, str] = {
    "already_consumed": (
        "linearity / exactly-once / no-double-spend has no direct kernel "
        "theorem yet; it is the metabolic-conservation territory (LA-side), "
        "not currently formalized. Corrective.corrective_no_authority_laundering "
        "is adjacent (a corrective step cannot widen authority) but is NOT a "
        "linearity proof — citing it here would overclaim."
    ),
    "origin_not_operational": (
        "the operational fence (simulated may not confer operational "
        "consequence) is an AG-side closed-world allowlist, not a kernel "
        "theorem. WitnessInvariance is adjacent but does not state this boundary."
    ),
}


def cite(refusal_kind: str) -> TheoremRef | None:
    """The class-boundary theorem for a refusal kind, or None when the kernel
    has no direct theorem (check ``NO_KERNEL_THEOREM`` for why)."""
    return PROOF_SEAM.get(refusal_kind)


def render_proof_seam(refusal_kind: str) -> list[str]:
    """The Act-3 'necessity' descent for a refusal kind, as text lines.

    Honest by construction: cites the theorem with its custody class, states
    what it proves (the class), and carries the class-not-instance disclaimer.
    For a kind with no kernel theorem, says so plainly.
    """
    ref = cite(refusal_kind)
    if ref is None:
        why = NO_KERNEL_THEOREM.get(refusal_kind, "no mapping recorded")
        return [
            f"  refusal class: {refusal_kind}",
            f"  no direct kernel theorem — {why}",
        ]
    tier = (
        "[1.0 PUBLIC-SHIPPED]"
        if ref.custody_class == CUSTODY_PUBLIC_SHIPPED
        else f"[{ref.custody_class}]"
    )
    return [
        f"  refusal class: {refusal_kind}",
        f"  licensed by:   {ref.lean_module}.{ref.theorem_name} {tier}",
        f"  at:            {ref.location}  (verified {ref.verified_at}, proof complete)",
        f"  theorem:       {ref.statement}",
        f"  proves:        {ref.proves}",
        f"  honest:        {CLASS_NOT_INSTANCE}",
    ]
