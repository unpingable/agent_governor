"""Tests for the decomposition-completeness receipt shape (schema truth before
behavior truth). The valve is on BOTH axes; the scalar `decomposition_complete`
lie is unrepresentable; EVERY path to `complete` requires a structured evidence
object (not a bare enum/flag). This layer enforces the evidence SHAPE — genuine
provenance of the refs is a later custody-anchoring rung, not claimed here.

Pins, per the amended slice spec:
  declared != complete
  best_effort != discharged
  operator_ratified != self_asserted
  bare z3/lean strings != coverage complete
"""

from __future__ import annotations

import dataclasses

import pytest

from governor.decomposition_completeness import (
    CapabilityClosureEvidence,
    DecompositionCompleteness,
    OperatorRatification,
    OverclaimError,
    SolverCoverageEvidence,
    TheoremCoverageEvidence,
    PROOF_TIER_AG_ONLY,
    PROOF_TIER_BOUNDED_CONSTRAINT,
    PROOF_TIER_OPERATOR_RATIFIED,
    PROOF_TIER_THEOREM_CITED,
    VERIFIER_LEAN_CITATION,
    VERIFIER_Z3,
    ENUMERATION_BASIS_CAPABILITY_KERNEL,
    ENUMERATION_BASIS_DECLARED,
    ENUMERATION_COMPLETE,
    ENUMERATION_DECLARED,
    COVERAGE_BEST_EFFORT,
    COVERAGE_COMPLETE,
)


class TestAgAloneHonestBlock:
    def test_ag_alone_is_two_qualified_fields_zero_bare_completes(self) -> None:
        dc = DecompositionCompleteness.ag_alone()
        assert dc.enumeration == ENUMERATION_DECLARED
        assert dc.enumeration_basis == ENUMERATION_BASIS_DECLARED
        assert dc.coverage == COVERAGE_BEST_EFFORT
        assert dc.verifier == "absent"
        assert dc.proof_tier == PROOF_TIER_AG_ONLY
        # best_effort is obligation-bearing, not terminal.
        assert dc.coverage_upgrade_owed is True

    def test_no_bare_decomposition_complete_scalar_exists(self) -> None:
        # The scalar boolean lie is unrepresentable: there is no single
        # `decomposition_complete` / `complete` field. Completeness is always two
        # qualified axes, each with its own basis/evidence.
        fields = {f.name for f in dataclasses.fields(DecompositionCompleteness)}
        assert "decomposition_complete" not in fields
        assert "complete" not in fields
        assert {"enumeration", "coverage"} <= fields


class TestEnumerationValve:
    def test_ag_alone_cannot_emit_enumeration_complete(self) -> None:
        # Point 1: AG-alone (no closure evidence) may not claim enumeration=complete.
        with pytest.raises(OverclaimError, match="enumeration=complete requires"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_COMPLETE,
                enumeration_basis=ENUMERATION_BASIS_CAPABILITY_KERNEL,
                coverage=COVERAGE_BEST_EFFORT,
            )

    def test_enumeration_complete_needs_capability_kernel_basis(self) -> None:
        # Even WITH closure evidence, a declared-boundaries basis cannot back
        # complete (declared boundaries are not closure).
        with pytest.raises(OverclaimError, match="capability_kernel_grant_ledger"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_COMPLETE,
                enumeration_basis=ENUMERATION_BASIS_DECLARED,
                coverage=COVERAGE_BEST_EFFORT,
                closure_evidence=CapabilityClosureEvidence(grant_set_ref="g1"),
            )

    def test_enumeration_complete_reachable_only_with_structured_closure(self) -> None:
        # Point 3: the reserved value IS reachable when the (future) capability
        # kernel supplies structured grant-ledger evidence — proving the valve is
        # a reservation, not a permanent ban. NOTE: this constructs the evidence
        # object locally, which is the DOCUMENTED substrate limit (in-process
        # construction is not fenced; genuine provenance is custody-anchored in a
        # later rung). What this test pins is the SHAPE requirement — a structured
        # object, not a bare scalar — and that the reserved value is reachable
        # only WITH it.
        dc = DecompositionCompleteness(
            enumeration=ENUMERATION_COMPLETE,
            enumeration_basis=ENUMERATION_BASIS_CAPABILITY_KERNEL,
            coverage=COVERAGE_BEST_EFFORT,
            closure_evidence=CapabilityClosureEvidence(grant_set_ref="grant-set-001"),
        )
        assert dc.enumeration == ENUMERATION_COMPLETE

    def test_grant_set_ref_rejects_bare_flag(self) -> None:
        # A bool is not a grant-ledger reference (type hints aren't runtime checks).
        with pytest.raises(ValueError, match="grant_set_ref"):
            CapabilityClosureEvidence(grant_set_ref=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="grant_set_ref"):
            CapabilityClosureEvidence(grant_set_ref="   ")

    def test_declared_must_not_carry_closure_evidence(self) -> None:
        with pytest.raises(ValueError, match="only meaningful with enumeration=complete"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_BEST_EFFORT,
                closure_evidence=CapabilityClosureEvidence(grant_set_ref="g"),
            )

    def test_empty_grant_set_ref_refused(self) -> None:
        with pytest.raises(ValueError, match="grant_set_ref"):
            CapabilityClosureEvidence(grant_set_ref="")


class TestCoverageValve:
    def test_ag_alone_cannot_emit_coverage_complete(self) -> None:
        # Point 4 / the original "oh hell": bare coverage=complete with no evidence.
        with pytest.raises(OverclaimError, match="coverage=complete requires"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
            )

    def test_coverage_complete_licensed_by_z3_with_solver_evidence(self) -> None:
        dc = DecompositionCompleteness(
            enumeration=ENUMERATION_DECLARED,
            coverage=COVERAGE_COMPLETE,
            verifier=VERIFIER_Z3,
            proof_tier=PROOF_TIER_BOUNDED_CONSTRAINT,
            solver_evidence=SolverCoverageEvidence(solver_verdict_ref="z3-run-1"),
            coverage_upgrade_owed=False,
        )
        assert dc.coverage == COVERAGE_COMPLETE

    def test_z3_bounded_without_solver_evidence_refused(self) -> None:
        # The core fix: bare verifier=z3 + proof_tier=bounded_constraint strings
        # are NOT evidence (two pleadable strings in a trench coat).
        with pytest.raises(OverclaimError, match="STRUCTURED evidence object"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                verifier=VERIFIER_Z3,
                proof_tier=PROOF_TIER_BOUNDED_CONSTRAINT,
                coverage_upgrade_owed=False,
            )

    def test_coverage_complete_licensed_by_lean_with_theorem_evidence(self) -> None:
        dc = DecompositionCompleteness(
            enumeration=ENUMERATION_DECLARED,
            coverage=COVERAGE_COMPLETE,
            verifier=VERIFIER_LEAN_CITATION,
            proof_tier=PROOF_TIER_THEOREM_CITED,
            theorem_evidence=TheoremCoverageEvidence(theorem_ref="Freshness.expired"),
            coverage_upgrade_owed=False,
        )
        assert dc.coverage == COVERAGE_COMPLETE

    def test_lean_theorem_without_theorem_evidence_refused(self) -> None:
        with pytest.raises(OverclaimError, match="STRUCTURED evidence object"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                verifier=VERIFIER_LEAN_CITATION,
                proof_tier=PROOF_TIER_THEOREM_CITED,
                coverage_upgrade_owed=False,
            )

    def test_coverage_evidence_empty_ref_refused(self) -> None:
        with pytest.raises(ValueError, match="solver_verdict_ref"):
            SolverCoverageEvidence(solver_verdict_ref="")
        with pytest.raises(ValueError, match="solver_verdict_ref"):
            SolverCoverageEvidence(solver_verdict_ref=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="theorem_ref"):
            TheoremCoverageEvidence(theorem_ref="  ")

    def test_solver_evidence_on_wrong_path_refused(self) -> None:
        # solver_evidence cannot be smuggled onto a best_effort or a lean/operator
        # combo — each evidence object belongs to exactly its own path.
        with pytest.raises(ValueError, match="solver_evidence requires"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                verifier=VERIFIER_LEAN_CITATION,
                proof_tier=PROOF_TIER_THEOREM_CITED,
                theorem_evidence=TheoremCoverageEvidence(theorem_ref="t"),
                solver_evidence=SolverCoverageEvidence(solver_verdict_ref="z"),
                coverage_upgrade_owed=False,
            )

    def test_coverage_complete_mismatched_verifier_and_tier_refused(self) -> None:
        # z3 verifier but theorem_cited tier is not a licensed pairing.
        with pytest.raises(OverclaimError):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                verifier=VERIFIER_Z3,
                proof_tier=PROOF_TIER_THEOREM_CITED,
                coverage_upgrade_owed=False,
            )

    def test_coverage_complete_cannot_also_owe_upgrade(self) -> None:
        # Point 5: complete is discharged, not owed — the obligation flag must be
        # cleared when complete (best_effort != discharged, and vice versa).
        with pytest.raises(ValueError, match="cannot also owe an upgrade"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                verifier=VERIFIER_Z3,
                proof_tier=PROOF_TIER_BOUNDED_CONSTRAINT,
                solver_evidence=SolverCoverageEvidence(solver_verdict_ref="z3-run-2"),
                coverage_upgrade_owed=True,
            )

    def test_best_effort_must_bear_the_obligation(self) -> None:
        # The dual of the above (the escape hatch): best_effort may NOT clear the
        # obligation flag. best_effort that owes nothing is the permanent
        # comfortable state the slot exists to prevent.
        with pytest.raises(ValueError, match="obligation-bearing"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_BEST_EFFORT,
                coverage_upgrade_owed=False,
            )


class TestOperatorRatificationAntiForgery:
    def test_coverage_complete_via_genuine_operator_receipt(self) -> None:
        dc = DecompositionCompleteness(
            enumeration=ENUMERATION_DECLARED,
            coverage=COVERAGE_COMPLETE,
            proof_tier=PROOF_TIER_OPERATOR_RATIFIED,
            operator_ratification=OperatorRatification(operator_receipt_ref="op-rcpt-7"),
            coverage_upgrade_owed=False,
        )
        assert dc.coverage == COVERAGE_COMPLETE

    def test_operator_ratified_tier_without_receipt_refused(self) -> None:
        # Point 6 / the fake-mustache hole: the one branch allowed to reach
        # complete cannot be reached by claiming the tier with no operator receipt.
        with pytest.raises(OverclaimError, match="coverage=complete requires"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                proof_tier=PROOF_TIER_OPERATOR_RATIFIED,
                operator_ratification=None,  # "operator_ratified=true" with no principal
                coverage_upgrade_owed=False,
            )

    def test_operator_ratification_requires_nonempty_receipt_ref(self) -> None:
        # The structured ratification cannot be a hollow shell either: a model is
        # not a principal, and an empty ref is no receipt.
        with pytest.raises(ValueError, match="operator_receipt_ref"):
            OperatorRatification(operator_receipt_ref="")

    def test_operator_ratification_rejects_bare_flag_ref(self) -> None:
        # operator_receipt_ref=True is the fake-mustache hole: a bare flag wearing
        # a string's clothes. A bool / whitespace ref is refused.
        with pytest.raises(ValueError, match="operator_receipt_ref"):
            OperatorRatification(operator_receipt_ref=True)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="operator_receipt_ref"):
            OperatorRatification(operator_receipt_ref="   ")

    def test_operator_tier_cannot_also_claim_a_verifier(self) -> None:
        # Operator ratification is not a solver run: claiming both is incoherent
        # mixed evidence.
        with pytest.raises(ValueError, match="not a solver run"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                verifier=VERIFIER_Z3,
                proof_tier=PROOF_TIER_OPERATOR_RATIFIED,
                operator_ratification=OperatorRatification(operator_receipt_ref="op-1"),
                coverage_upgrade_owed=False,
            )

    def test_operator_ratification_only_under_operator_tier(self) -> None:
        # Licensed via z3+solver_evidence, but ALSO carrying an operator_ratification
        # under the wrong tier — the coherence check refuses the mixed claim.
        with pytest.raises(ValueError, match="proof_tier=operator_ratified"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_COMPLETE,
                verifier=VERIFIER_Z3,
                proof_tier=PROOF_TIER_BOUNDED_CONSTRAINT,
                solver_evidence=SolverCoverageEvidence(solver_verdict_ref="z3-run-3"),
                operator_ratification=OperatorRatification(operator_receipt_ref="x"),
                coverage_upgrade_owed=False,
            )

    def test_best_effort_cannot_carry_operator_ratification(self) -> None:
        with pytest.raises(ValueError, match="only meaningful with coverage=complete"):
            DecompositionCompleteness(
                enumeration=ENUMERATION_DECLARED,
                coverage=COVERAGE_BEST_EFFORT,
                proof_tier=PROOF_TIER_OPERATOR_RATIFIED,
                operator_ratification=OperatorRatification(operator_receipt_ref="x"),
            )


class TestSerialization:
    def test_to_dict_carries_both_axes_and_bases(self) -> None:
        d = DecompositionCompleteness.ag_alone().to_dict()
        assert d["schema"] == "decomposition_completeness_v0"
        assert d["enumeration"] == ENUMERATION_DECLARED
        assert d["enumeration_basis"] == ENUMERATION_BASIS_DECLARED
        assert d["coverage"] == COVERAGE_BEST_EFFORT
        assert d["coverage_upgrade_owed"] is True
        # No bare scalar completeness leaks into the serialized form.
        assert "decomposition_complete" not in d
