# SPDX-License-Identifier: Apache-2.0
"""Claim-conversion normal form — the admission gate before reliance.

P0. Sits (conceptually) *after* witness/receipt capture and *before* anything is
consumed as evidence (`evaluate_promotion_from_evidence` / `derive_in_bounds` /
promotion eligibility). It does **not** decide truth. It decides whether a claimed
*epistemic promotion* is licensed — it refuses unlicensed conversion between
epistemic species.

> Arithmetic is cheap; individuation is expensive. ``3 = 3`` is worldless and free;
> "there are three roses" binds the formal three to a world-kind and pays a toll.
> Formal knowledge is invariant under representation; empirical knowledge is hostage
> to it. Admissibility lives at the hostage exchange.

**Two failure modes, two times** (the lesson this gate exists to encode):

* ``fail_closed`` applies at **reliance** time — a consumer trying to rely on an
  unlicensed conversion is **REFUSED**.
* ``quarantine`` applies at **exploration / naming** time — the same problematic
  claim, when no one is relying on it yet, is **QUARANTINED**: inspectable,
  discussable, testable, but it cannot promote.

So the default intent is ``EXPLORATION`` (do not fail closed at discovery), and only
``RELIANCE`` turns a tripped rule into a refusal. Only ``ADMITTED`` may feed governor
reliance.

**Not a truth oracle, not a theorem prover, not a policy language.** No plugins, no
reflection, no self-amendment. A total, pure conversion checker over a closed
vocabulary. The verdict is ``Normative<consistent-with-declared-order>``, never
``Observed<right>`` — whether the *order* is good is not decidable from inside (the
session's own result), and this module does not pretend otherwise.

**Naming fence:** this is NOT a "calculus" — that word is retired in the corpus
(`docs/constellation-zoning.md` = the refused-unification target). "Admission
Calculus" is a quarantined alias from scratch discussion, never canonical here.

Provenance: multi-model tooltheory exchange, 2026-06-15; theory frozen in
`~/git/papers/working/tooltheory/admission-gate-claim-conversion-normal-form.md`.
This is the executable P0, not a new kernel (the formal core is ContractionHinge /
standing-before-spendability generalized to "information vs authority").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ClaimSpecies(Enum):
    """What epistemic species a claim is — the axis the gate refuses to silently
    cross. Distinct from ``claims.ClaimType`` (that types structured *proposals*;
    this types *warrant*)."""

    FORMAL = "formal"  # true relative to axioms/rules; worldless until applied
    MODEL_BOUND = "model_bound"  # formal claim applied through a representation map
    OBSERVED = "observed"  # world claim mediated by witness/sensor
    TESTIMONIAL = "testimonial"  # world claim mediated by speaker/source
    NORMATIVE = "normative"  # valid under declared authority/order
    STIPULATED = "stipulated"  # root plank, named but not proven


class KindClaim(Enum):
    """Is the claim about a kind that exists independently of the instrument, or one
    the instrument participates in producing? Constructed-presented-as-stable is the
    battleground (the bureau swears creditworthiness is natural — insisting so is the
    move)."""

    STABLE = "stable"  # electron: tracked from outside
    CONSTRUCTED = "constructed"  # GDP/credit score: constituted by the measuring
    HYBRID = "hybrid"  # real substrate + constituted overlay (the dangerous one)
    UNSPECIFIED = "unspecified"


class InstrumentRole(Enum):
    """What the instrument *does* to its object. The load-bearing field: you don't
    get to call it measurement after the instrument starts issuing orders."""

    MEASURES = "measures"  # thermometer reads temperature
    CLASSIFIES = "classifies"  # labels applicant high-risk
    ALLOCATES = "allocates"  # score changes loan terms
    ENFORCES = "enforces"  # score blocks access
    CREATES = "creates"  # category exists because the institution treats it as one


class AdmissionIntent(Enum):
    """Why the claim is being classified. Drives the quarantine-vs-refuse split."""

    EXPLORATION = "exploration"  # discovery/naming — a tripped rule → QUARANTINED
    RELIANCE = "reliance"  # a consumer wants to rely/promote — a trip → REFUSED


class AdmissionStatus(Enum):
    CANDIDATE = "candidate"  # nothing wrong, but no reliance attempted yet
    QUARANTINED = "quarantined"  # problematic at exploration time; inspectable, no promote
    ADMITTED = "admitted"  # licensed for reliance by the consumer, within scope
    REFUSED = "refused"  # unlicensed conversion attempted at reliance time


# --- closed refusal vocabulary (the licensed conversions this gate refuses) -------
FORMAL_BOUND_TO_WORLD_WITHOUT_MODEL_FIDELITY = "formal_bound_to_world_without_model_fidelity"
CONSTRUCTED_OR_HYBRID_KIND_PRESENTED_AS_STABLE = "constructed_or_hybrid_kind_presented_as_stable"
ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT = (
    "allocating_or_enforcing_instrument_presented_as_measurement"
)
TESTIMONIAL_PROMOTED_TO_FACT = "testimonial_promoted_to_fact"
PROOF_RECEIPT_PROMOTED_TO_SYSTEM_SAFETY = "proof_receipt_promoted_to_system_safety"
MISSING_SCOPE = "missing_scope"
MISSING_FRESHNESS = "missing_freshness"
CONSUMER_SCOPE_MISMATCH = "consumer_scope_mismatch"

REFUSAL_REASONS = frozenset(
    {
        FORMAL_BOUND_TO_WORLD_WITHOUT_MODEL_FIDELITY,
        CONSTRUCTED_OR_HYBRID_KIND_PRESENTED_AS_STABLE,
        ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT,
        TESTIMONIAL_PROMOTED_TO_FACT,
        PROOF_RECEIPT_PROMOTED_TO_SYSTEM_SAFETY,
        MISSING_SCOPE,
        MISSING_FRESHNESS,
        CONSUMER_SCOPE_MISMATCH,
    }
)

# Canonical ordering so dual failures surface predictably (species rules first,
# then constitutivity, then reliance-context requirements).
_REASON_ORDER = (
    FORMAL_BOUND_TO_WORLD_WITHOUT_MODEL_FIDELITY,
    TESTIMONIAL_PROMOTED_TO_FACT,
    PROOF_RECEIPT_PROMOTED_TO_SYSTEM_SAFETY,
    CONSTRUCTED_OR_HYBRID_KIND_PRESENTED_AS_STABLE,
    ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT,
    CONSUMER_SCOPE_MISMATCH,
    MISSING_SCOPE,
    MISSING_FRESHNESS,
)

# Species whose admission for reliance requires a world-binding (scope, and freshness
# when the consumer needs it). Formal is worldless; Normative is authority-relative;
# Stipulated is a named root plank.
_WORLD_SPECIES = frozenset({ClaimSpecies.MODEL_BOUND, ClaimSpecies.OBSERVED, ClaimSpecies.TESTIMONIAL})


@dataclass(frozen=True)
class ClaimManifest:
    """A claim presented for admission, plus *how* it is being presented. The
    presentation flags are the overclaim surface — the gate compares what the claim
    *is* against what it is being *presented as*."""

    species: ClaimSpecies
    value: str = ""  # the claim text — opaque, for the record only
    scope: str | None = None  # what the claim is admitted over
    consumer: str | None = None  # who wants to rely (required for RELIANCE)
    evidence_refs: tuple[str, ...] = ()  # witness/observation receipts
    model_refs: tuple[str, ...] = ()  # model-fidelity / representation-binding receipts
    freshness: str | None = None  # freshness basis, when relevant
    freshness_required: bool = False  # does this consumer need freshness?
    kind_claim: KindClaim = KindClaim.UNSPECIFIED
    instrument_role: InstrumentRole | None = None
    does_not_claim: tuple[str, ...] = ()  # explicit scope-limits (required for proof admission)
    is_proof: bool = False  # a discharged formal proof artifact (Coq/Z3/Lean)
    # presentation (the overclaim surface) — how the claim is being asserted:
    presented_as_measurement: bool = False
    presented_as_stable_kind: bool = False
    presented_as_fact: bool = False
    presented_as_system_safety: bool = False


@dataclass(frozen=True)
class ClassificationResult:
    """The admission verdict. ``status == ADMITTED`` is the ONLY state that may feed
    governor reliance; everything else is non-promotable."""

    status: AdmissionStatus
    species: ClaimSpecies
    intent: AdmissionIntent
    reasons: tuple[str, ...] = ()
    scope: str | None = None

    @property
    def admitted(self) -> bool:
        return self.status is AdmissionStatus.ADMITTED


def _conversion_reasons(m: ClaimManifest) -> list[str]:
    """Species/kind/role conversion violations — intent-independent (a Formal claim
    bound to the world without a fidelity receipt is an unlicensed conversion whether
    or not anyone is relying on it yet)."""
    out: list[str] = []

    # R1 — a model-bound claim (formal applied through a representation) needs a
    # model-fidelity receipt. "nine servers" is the formal nine bound to a world-kind.
    if m.species is ClaimSpecies.MODEL_BOUND and not m.model_refs:
        out.append(FORMAL_BOUND_TO_WORLD_WITHOUT_MODEL_FIDELITY)

    # R4 — testimony presented as fact (a speaker/source promoted to settled truth).
    if m.species is ClaimSpecies.TESTIMONIAL and m.presented_as_fact:
        out.append(TESTIMONIAL_PROMOTED_TO_FACT)

    # R5 — a proof artifact presented as system safety without a bound scope + an
    # explicit does_not_claim ("Coq proved this system safe" ⇒ O-over-A only).
    if m.is_proof and m.presented_as_system_safety and not (m.scope and m.does_not_claim):
        out.append(PROOF_RECEIPT_PROMOTED_TO_SYSTEM_SAFETY)

    # R2 — a constructed/hybrid kind presented as a stable, independently-tracked kind
    # (the thermometer joined the weather; the score is the definition).
    if m.kind_claim in (KindClaim.CONSTRUCTED, KindClaim.HYBRID) and m.presented_as_stable_kind:
        out.append(CONSTRUCTED_OR_HYBRID_KIND_PRESENTED_AS_STABLE)

    # R3 — an allocating/enforcing/creating instrument presented as neutral
    # measurement. You don't get to call it measurement after it issues orders.
    if (
        m.instrument_role in (InstrumentRole.ALLOCATES, InstrumentRole.ENFORCES, InstrumentRole.CREATES)
        and m.presented_as_measurement
    ):
        out.append(ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT)

    return out


def _reliance_reasons(m: ClaimManifest) -> list[str]:
    """Requirements that only bite when a consumer is actually trying to rely:
    a consumer, a scope for world-bound species, and freshness when required."""
    out: list[str] = []
    if not m.consumer:
        out.append(CONSUMER_SCOPE_MISMATCH)
    if m.species in _WORLD_SPECIES:
        if not m.scope:
            out.append(MISSING_SCOPE)
        if m.freshness_required and not m.freshness:
            out.append(MISSING_FRESHNESS)
    return out


def _admit_scope(m: ClaimManifest) -> str:
    """The scope a clean claim is admitted over — never wider than the species earns.
    Formal admits worldless; testimony admits AS testimony (not as fact); the rest
    carry their declared scope."""
    if m.species is ClaimSpecies.FORMAL:
        return m.scope or "formal:worldless"
    if m.species is ClaimSpecies.TESTIMONIAL:
        return m.scope or "testimony"
    if m.species is ClaimSpecies.STIPULATED:
        return m.scope or "stipulated:root_plank"
    return m.scope or "unscoped"


def classify(
    manifest: ClaimManifest,
    *,
    intent: AdmissionIntent = AdmissionIntent.EXPLORATION,
) -> ClassificationResult:
    """Classify a claim's admissibility. Pure, total, refusal-native.

    A tripped rule yields ``QUARANTINED`` under ``EXPLORATION`` (inspectable, cannot
    promote) and ``REFUSED`` under ``RELIANCE`` (fail closed). A clean claim is
    ``ADMITTED`` under ``RELIANCE`` (the only promotable state) and ``CANDIDATE``
    under ``EXPLORATION`` (nothing wrong, but nothing relied upon yet).
    """
    reasons = set(_conversion_reasons(manifest))
    if intent is AdmissionIntent.RELIANCE:
        reasons.update(_reliance_reasons(manifest))

    ordered = tuple(r for r in _REASON_ORDER if r in reasons)

    if ordered:
        status = (
            AdmissionStatus.REFUSED
            if intent is AdmissionIntent.RELIANCE
            else AdmissionStatus.QUARANTINED
        )
        return ClassificationResult(
            status=status, species=manifest.species, intent=intent, reasons=ordered
        )

    if intent is AdmissionIntent.RELIANCE:
        return ClassificationResult(
            status=AdmissionStatus.ADMITTED,
            species=manifest.species,
            intent=intent,
            scope=_admit_scope(manifest),
        )
    return ClassificationResult(
        status=AdmissionStatus.CANDIDATE, species=manifest.species, intent=intent
    )


__all__ = [
    "ClaimSpecies",
    "KindClaim",
    "InstrumentRole",
    "AdmissionIntent",
    "AdmissionStatus",
    "ClaimManifest",
    "ClassificationResult",
    "classify",
    "REFUSAL_REASONS",
    "FORMAL_BOUND_TO_WORLD_WITHOUT_MODEL_FIDELITY",
    "CONSTRUCTED_OR_HYBRID_KIND_PRESENTED_AS_STABLE",
    "ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT",
    "TESTIMONIAL_PROMOTED_TO_FACT",
    "PROOF_RECEIPT_PROMOTED_TO_SYSTEM_SAFETY",
    "MISSING_SCOPE",
    "MISSING_FRESHNESS",
    "CONSUMER_SCOPE_MISMATCH",
]
