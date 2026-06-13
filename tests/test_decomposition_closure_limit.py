"""Pin the decomposition-completeness blind spot in account_boundaries.

`account_boundaries` (P1.1) is pure and total over the *admitted* boundary set:
it proves every admitted boundary got an honest disposition. It is structurally
BLIND to a real boundary that was never admitted at decompose — the omitted one
isn't there to be missed. This is the dual of the recomposition-laundering bug
P3.2 closed (a declared boundary silently dropped); the OPEN dual is a real
boundary that never entered jurisdiction.

These tests do not test a bug to fix in `account_boundaries` — that function's
contract is exactly "account the admitted set." They PIN the limit so a future
change that pretends `account_boundaries` (or an AG-alone receipt) proves
boundary-set CLOSURE is caught. Closure requires kernel-granted capabilities, not
plan-declared surfaces — see
`docs/cross-tool/decomposition-capability-closure-note.md` and
`specs/gaps/GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001.md`.

Doctrine: you cannot audit the absence of an omitted boundary; you can only make
omission unexecutable. Declared boundaries are pleadable; granted capabilities are
accountable.
"""

from __future__ import annotations

from governor.pipeline_types import (
    VERDICT_ADMISSIBLE,
    account_boundaries,
)


def test_omitted_boundary_is_invisible_to_account_boundaries() -> None:
    # The plan declared only A and B; both completed. A real boundary C existed
    # at execution but was NEVER admitted at decompose. account_boundaries sees
    # no missing disposition and reports admissible — the omitted boundary is
    # invisible. THIS IS THE BLIND SPOT, pinned: enumeration over the declared
    # set cannot detect an undeclared boundary.
    result = account_boundaries(["A", "B"], {"A": "completed", "B": "completed"})
    assert result.verdict == VERDICT_ADMISSIBLE
    assert result.unaccounted == ()  # C is not "unaccounted" — it is unseen
    assert result.admissible is True


def test_account_boundaries_only_closes_over_what_it_is_given() -> None:
    # Strengthen the pin: the verdict is identical whether or not an omitted real
    # boundary existed in the world. account_boundaries is a function of its
    # ARGUMENTS only; it has no channel to the real boundary universe. So a caller
    # that draws `admitted` from a plan declaration (omittable) gets a verdict
    # that cannot speak to closure — only to disposition over the declared set.
    declared_only = account_boundaries(
        ["A", "B"], {"A": "completed", "B": "completed"}
    )
    # Same call an honest decomposition WOULD have made, had it admitted C too:
    with_real_c = account_boundaries(
        ["A", "B", "C"],
        {"A": "completed", "B": "completed", "C": "completed"},
    )
    # Both admissible — but the first is admissible while blind to C. The verdicts
    # being equal is the point: account_boundaries cannot distinguish
    # "C was handled" from "C was never admitted". Closure is not its job.
    assert declared_only.verdict == with_real_c.verdict == VERDICT_ADMISSIBLE
    # And the receipt-level integrity (P3.2) recomputes over the SAME declared
    # set, so it inherits the blind spot — it cannot rescue closure either.
    assert declared_only.admitted_count == 2  # only what was declared


# --- Acceptance markers for the capability-closure work (NOT yet implemented) ---
#
# These are the negative tests the wiring slices must add once the receipt-shape
# fields + capability ledger exist (see the gap's acceptance matrix). They are
# recorded here as TODOs, NOT as skipped tests masquerading as coverage:
#
#   AC2: no AG-alone receipt may emit coverage=complete / decomposition=complete
#        without solver/theorem/operator evidence.
#   AC3: recomposition over a cap ledger accounts the GRANT set, not the declared
#        set (an omitted declared boundary cannot read clean).
#   AC4: a slice attempting an ungranted cap -> hard refusal + receipt.
#   AC5: composition of A and B without a seam(A,B) cap -> refused.
#   AC6: granted cap exercised without disposition -> denied; granted-not-exercised
#        -> pass-with-warning.
#   AC7/AC8: indecomposable gate blocks ingest; planner cannot self-clear it.
#   AC9/AC10: verifier.allowed is evidence not authority; Lean only as citation.
