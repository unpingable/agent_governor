"""Decomposition-completeness receipt shape — schema truth before behavior truth.

The first wiring seam of `GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001`
(`docs/cross-tool/decomposition-capability-closure-note.md`). It does NOT solve
capability closure; it prevents the repo from *lying* about having solved it —
killing the scalar boolean `decomposition_complete = True` before it grows a soul.

Completeness has two axes, and they are NOT the same claim:

* **enumeration** — is the boundary *set* closed? Closure holds only when
  boundaries are kernel-granted capabilities (boundary set == grant set). With
  merely *declared* boundaries (today, pre-capability-kernel) the honest value is
  ``declared``: "I accounted for every boundary I was *told about*" — which is not
  closure. ``enumeration=complete`` is reserved behind capability-kernel closure
  evidence, which AG-alone has no producer for. (An omitted boundary is an
  *enumeration* failure, not a coverage one — this is the axis the "oh hell" was
  about; see `tests/test_decomposition_closure_limit.py`.)
* **coverage** — do the boundaries/rules close over the plan's intent without gaps,
  contradictions, or out-of-scope composition? AG-alone is ``best_effort`` here;
  ``coverage=complete`` is reserved behind solver / theorem / operator evidence.

The valve is on BOTH axes, symmetric: EVERY path to ``complete`` requires a
*structured* evidence object carrying a provenance ref — a capability grant-set
ref (enumeration), a solver-verdict ref or a theorem-citation ref or an
operator-receipt ref (coverage) — never a bare verifier/proof-tier string. (Bare
enum strings reaching ``complete`` would be symbolic instruments as un-pleadable
witnesses implemented as two pleadable strings in a trench coat.) There is no bare
``decomposition_complete`` boolean anywhere — the type forces two qualified axes,
so the scalar lie is unrepresentable.

Honesty about the fence (same bootstrap-custody limit as P3.1): this slice fences
the SHAPE, not provenance. In one Python process a determined caller can construct
the evidence objects directly — the type cannot prove the grant-set ref came from
a real capability kernel, or the operator receipt from a real operator. Anchoring
those refs to a custodied receipt store is a later rung (it needs runtime wiring
this schema-only slice excludes). What is fenced HERE: the weak claim
(``declared`` / ``best_effort``) is the default and the only value reachable
without deliberately constructing a named evidence object, and the bare-scalar lie
is structurally impossible. Bootstrap evidence may be forgeable in-process; the
scalar overclaim is not even representable.

This module is schema + guard + serialization ONLY. No orchestrator wiring, no
capability kernel, no verifier integration, no prep-before-ingest — those are
later rungs behind their own forcing cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --------------------------------------------------------------------------- #
# Closed vocabularies (per axis)
# --------------------------------------------------------------------------- #

# enumeration — is the boundary set closed?
ENUMERATION_DECLARED = "declared"  # AG-alone honest value: accounted what it was told
ENUMERATION_COMPLETE = "complete"  # reserved: boundary set == kernel grant set
CLOSED_ENUMERATION = frozenset({ENUMERATION_DECLARED, ENUMERATION_COMPLETE})

# enumeration_basis — what licenses the enumeration value (each axis names its
# basis). declared_boundaries is weak (omittable); only the capability-kernel
# grant ledger is closure.
ENUMERATION_BASIS_DECLARED = "declared_boundaries"
ENUMERATION_BASIS_CAPABILITY_KERNEL = "capability_kernel_grant_ledger"
CLOSED_ENUMERATION_BASIS = frozenset(
    {ENUMERATION_BASIS_DECLARED, ENUMERATION_BASIS_CAPABILITY_KERNEL}
)

# coverage — do the rules close over the plan's intent?
COVERAGE_BEST_EFFORT = "best_effort"  # AG-alone honest value
COVERAGE_COMPLETE = "complete"  # reserved: solver / theorem / operator evidence
CLOSED_COVERAGE = frozenset({COVERAGE_BEST_EFFORT, COVERAGE_COMPLETE})

# verifier presence
VERIFIER_ABSENT = "absent"
VERIFIER_Z3 = "z3"
VERIFIER_LEAN_CITATION = "lean_citation"
CLOSED_VERIFIER = frozenset({VERIFIER_ABSENT, VERIFIER_Z3, VERIFIER_LEAN_CITATION})

# proof tier
PROOF_TIER_AG_ONLY = "ag_only"
PROOF_TIER_BOUNDED_CONSTRAINT = "bounded_constraint"  # z3
PROOF_TIER_THEOREM_CITED = "theorem_cited"  # lean citation
PROOF_TIER_OPERATOR_RATIFIED = "operator_ratified"  # operator receipt
CLOSED_PROOF_TIER = frozenset(
    {
        PROOF_TIER_AG_ONLY,
        PROOF_TIER_BOUNDED_CONSTRAINT,
        PROOF_TIER_THEOREM_CITED,
        PROOF_TIER_OPERATOR_RATIFIED,
    }
)


class OverclaimError(ValueError):
    """A decomposition-completeness block claimed a privileged ``complete`` without
    the structured evidence that licenses it. The scalar lie, refused at the type
    boundary."""


# --------------------------------------------------------------------------- #
# Structured evidence — every path to `complete` carries a structured evidence
# object with a provenance ref, never a bare enum/flag. These are evidence-shaped
# SOCKETS: the ref is required and validated here; whether the ref is GENUINE (a
# real kernel grant ledger, a real solver verdict, a real theorem, a real operator
# receipt) is custody-anchoring, a later producer-swap rung. In-process a caller
# can still construct these objects — that is the documented bootstrap-custody
# substrate limit (same as P3.1). What is enforced HERE: a structured object with
# a non-empty ref, not a bare scalar; and the bare-scalar lie is unrepresentable.
# --------------------------------------------------------------------------- #


def _require_ref(value: object, owner: str, field: str) -> None:
    """A provenance ref must be a non-empty STRING — not a bool/int/whitespace
    masquerading as a ref (type hints are not runtime checks; a bare ``True`` is a
    flag, not a reference)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{owner} requires a non-empty string {field} "
            "(a bare flag is not a provenance reference)"
        )


@dataclass(frozen=True)
class CapabilityClosureEvidence:
    """Structured evidence shape for boundary-set closure (boundary set == the
    kernel-granted capability set). Intended to be produced by the future
    capability kernel; AG-alone has no honest producer, so its own code never
    constructs one (``ag_alone()`` does not). This type does NOT prove provenance —
    in one process a caller can construct it directly (the documented substrate
    limit). It enforces the *shape*: ``enumeration=complete`` requires this object
    with a non-empty grant-set ref, never a bare flag.
    """

    grant_set_ref: str  # non-empty string ref to the kernel grant record

    def __post_init__(self) -> None:
        _require_ref(self.grant_set_ref, "CapabilityClosureEvidence", "grant_set_ref")


@dataclass(frozen=True)
class SolverCoverageEvidence:
    """Structured evidence shape for coverage completeness discharged by a bounded
    solver (Z3/SMT). Carries a ref to the solver verdict/proof (e.g. a verifier
    receipt id + input/proof hash). Reference-carrying record ONLY — this module
    runs no solver; the real verifier integration is a producer swap, not a
    semantic retrofit (`docs/cross-tool/symbolic-instrument-witness-note.md`)."""

    solver_verdict_ref: str  # non-empty ref to the bounded solver verdict/proof

    def __post_init__(self) -> None:
        _require_ref(
            self.solver_verdict_ref, "SolverCoverageEvidence", "solver_verdict_ref"
        )


@dataclass(frozen=True)
class TheoremCoverageEvidence:
    """Structured evidence shape for coverage completeness licensed by a cited,
    already-proven theorem (Lean). Carries a ref to the theorem/citation. Reference
    only — Lean is cited, never live-proven on this path (heavy tier contributes
    citations, never latency)."""

    theorem_ref: str  # non-empty ref to the cited theorem / refusal class

    def __post_init__(self) -> None:
        _require_ref(self.theorem_ref, "TheoremCoverageEvidence", "theorem_ref")


@dataclass(frozen=True)
class OperatorRatification:
    """An operator's ratification of coverage completeness, carried as a receipt
    REFERENCE — not a bare ``operator_ratified=True`` flag a pleadable component
    could set on itself (that is the "model is not principal" hole in the one
    branch allowed to reach ``complete``). Full custody-anchoring of the ref
    (proving it is genuinely operator-provenanced) is a later rung; this slice
    requires the structured ref and refuses the bare-flag path.
    """

    operator_receipt_ref: str  # non-empty string ref to operator-provenance receipt

    def __post_init__(self) -> None:
        _require_ref(
            self.operator_receipt_ref, "OperatorRatification", "operator_receipt_ref"
        )


# --------------------------------------------------------------------------- #
# The completeness block
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DecompositionCompleteness:
    """Two qualified completeness axes for a decomposition check. There is no bare
    ``decomposition_complete`` boolean: completeness is always two qualified values
    (enumeration, coverage), each with its evidence, so a scalar overclaim cannot
    be represented.

    The valve (``__post_init__``) — EVERY path to ``complete`` carries a structured
    evidence object, never a bare enum/flag:

    * ``enumeration=complete`` requires :class:`CapabilityClosureEvidence`.
    * ``coverage=complete`` requires one of: ``z3`` + ``bounded_constraint`` +
      :class:`SolverCoverageEvidence`; ``lean_citation`` + ``theorem_cited`` +
      :class:`TheoremCoverageEvidence`; or ``operator_ratified`` +
      :class:`OperatorRatification`. (Bare ``verifier``/``proof_tier`` strings are
      never sufficient — symbolic instruments as un-pleadable witnesses, not two
      pleadable strings in a trench coat.)

    ``coverage_upgrade_owed`` is the obligation slot (amendment): a
    ``best_effort`` coverage *owes* a real verifier/proof pass. Carrying the slot
    now (default ``True`` for best_effort, set False only when complete) keeps
    ``best_effort`` from silently becoming the permanent comfortable state — the
    future-rung-debt escape hatch. The obligation is NOT discharged or enforced in
    this slice; the shape just does not foreclose it.
    """

    enumeration: str
    coverage: str
    enumeration_basis: str = ENUMERATION_BASIS_DECLARED
    verifier: str = VERIFIER_ABSENT
    proof_tier: str = PROOF_TIER_AG_ONLY
    closure_evidence: CapabilityClosureEvidence | None = None
    solver_evidence: SolverCoverageEvidence | None = None
    theorem_evidence: TheoremCoverageEvidence | None = None
    operator_ratification: OperatorRatification | None = None
    coverage_upgrade_owed: bool = True

    def __post_init__(self) -> None:
        if self.enumeration not in CLOSED_ENUMERATION:
            raise ValueError(
                f"enumeration must be one of {sorted(CLOSED_ENUMERATION)}, "
                f"got {self.enumeration!r}"
            )
        if self.enumeration_basis not in CLOSED_ENUMERATION_BASIS:
            raise ValueError(
                f"enumeration_basis must be one of {sorted(CLOSED_ENUMERATION_BASIS)}, "
                f"got {self.enumeration_basis!r}"
            )
        if self.coverage not in CLOSED_COVERAGE:
            raise ValueError(
                f"coverage must be one of {sorted(CLOSED_COVERAGE)}, "
                f"got {self.coverage!r}"
            )
        if self.verifier not in CLOSED_VERIFIER:
            raise ValueError(
                f"verifier must be one of {sorted(CLOSED_VERIFIER)}, "
                f"got {self.verifier!r}"
            )
        if self.proof_tier not in CLOSED_PROOF_TIER:
            raise ValueError(
                f"proof_tier must be one of {sorted(CLOSED_PROOF_TIER)}, "
                f"got {self.proof_tier!r}"
            )

        # Valve A — enumeration=complete reserved behind capability-kernel closure
        # evidence. AG-alone, with merely declared boundaries, must emit `declared`.
        # The basis is symmetric with the value: declared <-> declared_boundaries
        # (weak, omittable), complete <-> capability_kernel_grant_ledger (closure).
        if self.enumeration == ENUMERATION_COMPLETE:
            if not isinstance(self.closure_evidence, CapabilityClosureEvidence):
                raise OverclaimError(
                    "enumeration=complete requires CapabilityClosureEvidence "
                    "(boundary set == kernel grant set). AG-alone has merely DECLARED "
                    "boundaries and no closure producer — emit enumeration=declared."
                )
            if self.enumeration_basis != ENUMERATION_BASIS_CAPABILITY_KERNEL:
                raise OverclaimError(
                    "enumeration=complete requires "
                    f"enumeration_basis={ENUMERATION_BASIS_CAPABILITY_KERNEL!r}, "
                    f"not {self.enumeration_basis!r} (declared boundaries are not closure)"
                )
        else:
            # declared: weak basis only, and no closure evidence on the weak claim.
            if self.enumeration_basis != ENUMERATION_BASIS_DECLARED:
                raise ValueError(
                    "enumeration=declared must carry "
                    f"enumeration_basis={ENUMERATION_BASIS_DECLARED!r} "
                    "(declared != complete; do not dress the weak claim as closure)"
                )
            if self.closure_evidence is not None:
                raise ValueError(
                    "closure_evidence is only meaningful with enumeration=complete; "
                    "a declared enumeration must not carry it"
                )

        # Valve B — coverage=complete reserved behind a STRUCTURED evidence object
        # on each path (bare verifier/proof_tier strings are never sufficient).
        if self.coverage == COVERAGE_COMPLETE:
            licensed = (
                (
                    self.verifier == VERIFIER_Z3
                    and self.proof_tier == PROOF_TIER_BOUNDED_CONSTRAINT
                    and isinstance(self.solver_evidence, SolverCoverageEvidence)
                )
                or (
                    self.verifier == VERIFIER_LEAN_CITATION
                    and self.proof_tier == PROOF_TIER_THEOREM_CITED
                    and isinstance(self.theorem_evidence, TheoremCoverageEvidence)
                )
                or (
                    self.proof_tier == PROOF_TIER_OPERATOR_RATIFIED
                    and isinstance(self.operator_ratification, OperatorRatification)
                )
            )
            if not licensed:
                raise OverclaimError(
                    "coverage=complete requires a STRUCTURED evidence object on one "
                    "path: z3+bounded_constraint+SolverCoverageEvidence, "
                    "lean_citation+theorem_cited+TheoremCoverageEvidence, or "
                    "operator_ratified+OperatorRatification. Bare verifier/proof_tier "
                    "strings are not evidence; AG-alone may emit only coverage=best_effort."
                )
            if self.coverage_upgrade_owed:
                raise ValueError(
                    "coverage=complete cannot also owe an upgrade "
                    "(set coverage_upgrade_owed=False when complete)"
                )
        else:
            # best_effort is OBLIGATION-BEARING, not terminal: it owes a real
            # verifier/proof pass. Forcing the flag True keeps best_effort from
            # silently becoming the permanent comfortable state (best_effort !=
            # discharged; the future-rung-debt escape hatch is closed in the shape).
            if not self.coverage_upgrade_owed:
                raise ValueError(
                    "coverage=best_effort is obligation-bearing and must carry "
                    "coverage_upgrade_owed=True (best_effort != discharged); only "
                    "coverage=complete may clear the obligation"
                )
            # best_effort must not masquerade as ratified/solved.
            if self.operator_ratification is not None:
                raise ValueError(
                    "operator_ratification is only meaningful with coverage=complete"
                )
            if self.solver_evidence is not None or self.theorem_evidence is not None:
                raise ValueError(
                    "solver_evidence / theorem_evidence are only meaningful with "
                    "coverage=complete (best_effort owes the pass, it does not have it)"
                )
            if self.proof_tier != PROOF_TIER_AG_ONLY and self.verifier == VERIFIER_ABSENT:
                raise ValueError(
                    "best_effort coverage with no verifier must carry proof_tier=ag_only"
                )

        # An operator_ratification only makes sense under the operator tier.
        if (
            self.operator_ratification is not None
            and self.proof_tier != PROOF_TIER_OPERATOR_RATIFIED
        ):
            raise ValueError(
                "operator_ratification requires proof_tier=operator_ratified"
            )
        # Each coverage evidence object belongs to exactly its own path — no
        # attaching solver evidence to a lean/operator combo, or vice versa.
        if self.solver_evidence is not None and not (
            self.coverage == COVERAGE_COMPLETE
            and self.verifier == VERIFIER_Z3
            and self.proof_tier == PROOF_TIER_BOUNDED_CONSTRAINT
        ):
            raise ValueError(
                "solver_evidence requires coverage=complete with z3+bounded_constraint"
            )
        if self.theorem_evidence is not None and not (
            self.coverage == COVERAGE_COMPLETE
            and self.verifier == VERIFIER_LEAN_CITATION
            and self.proof_tier == PROOF_TIER_THEOREM_CITED
        ):
            raise ValueError(
                "theorem_evidence requires coverage=complete with "
                "lean_citation+theorem_cited"
            )
        # Operator ratification is NOT a solver run: the operator tier must not
        # also claim a verifier engine (incoherent mixed evidence).
        if (
            self.proof_tier == PROOF_TIER_OPERATOR_RATIFIED
            and self.verifier != VERIFIER_ABSENT
        ):
            raise ValueError(
                "proof_tier=operator_ratified requires verifier=absent "
                "(operator ratification is not a solver run)"
            )

    @classmethod
    def ag_alone(cls) -> DecompositionCompleteness:
        """The honest AG-alone block: declared enumeration, best-effort coverage,
        no verifier, ag_only tier, upgrade owed. Two qualified fields, zero bare
        completes. This is the only completeness AG-alone may assert today."""
        return cls(
            enumeration=ENUMERATION_DECLARED,
            enumeration_basis=ENUMERATION_BASIS_DECLARED,
            coverage=COVERAGE_BEST_EFFORT,
            verifier=VERIFIER_ABSENT,
            proof_tier=PROOF_TIER_AG_ONLY,
            coverage_upgrade_owed=True,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializable form for receipt embedding."""
        out: dict[str, Any] = {
            "schema": "decomposition_completeness_v0",
            "enumeration": self.enumeration,
            "enumeration_basis": self.enumeration_basis,
            "coverage": self.coverage,
            "verifier": self.verifier,
            "proof_tier": self.proof_tier,
            "coverage_upgrade_owed": self.coverage_upgrade_owed,
        }
        if self.closure_evidence is not None:
            out["closure_evidence"] = {"grant_set_ref": self.closure_evidence.grant_set_ref}
        if self.solver_evidence is not None:
            out["solver_evidence"] = {
                "solver_verdict_ref": self.solver_evidence.solver_verdict_ref
            }
        if self.theorem_evidence is not None:
            out["theorem_evidence"] = {
                "theorem_ref": self.theorem_evidence.theorem_ref
            }
        if self.operator_ratification is not None:
            out["operator_ratification"] = {
                "operator_receipt_ref": self.operator_ratification.operator_receipt_ref
            }
        return out
