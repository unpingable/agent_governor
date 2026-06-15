# SPDX-License-Identifier: Apache-2.0
"""P0 claim-conversion normal form — the five refusal specimens + the quarantine/
reliance split.

The gate decides whether an epistemic *promotion* is licensed, never whether the
claim is true. The load-bearing behavioral lesson: a tripped rule QUARANTINES at
exploration time and REFUSES at reliance time — fail quarantined until reliance is
attempted, and only ADMITTED may promote.
"""

from __future__ import annotations

from governor.normal_form import (
    ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT,
    CONSTRUCTED_OR_HYBRID_KIND_PRESENTED_AS_STABLE,
    CONSUMER_SCOPE_MISMATCH,
    FORMAL_BOUND_TO_WORLD_WITHOUT_MODEL_FIDELITY,
    MISSING_FRESHNESS,
    MISSING_SCOPE,
    PROOF_RECEIPT_PROMOTED_TO_SYSTEM_SAFETY,
    REFUSAL_REASONS,
    TESTIMONIAL_PROMOTED_TO_FACT,
    AdmissionIntent,
    AdmissionStatus,
    ClaimManifest,
    ClaimSpecies,
    InstrumentRole,
    KindClaim,
    classify,
)

RELY = AdmissionIntent.RELIANCE
EXPLORE = AdmissionIntent.EXPLORATION


# --- Specimen 1: 3*3=9 → admitted as Formal ---------------------------------------


def test_formal_arithmetic_admitted():
    m = ClaimManifest(species=ClaimSpecies.FORMAL, value="3*3=9", consumer="governor")
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.ADMITTED
    assert r.admitted
    assert r.scope == "formal:worldless"
    assert r.reasons == ()


# --- Specimen 2: "there are 9 servers" → refused without model binding -------------


def test_model_bound_without_fidelity_refused():
    # The formal nine bound to a world-kind (servers) with no model-fidelity receipt.
    m = ClaimManifest(
        species=ClaimSpecies.MODEL_BOUND,
        value="there are 9 servers",
        consumer="governor",
        scope="inventory:rack-7",  # scope present — isolates the binding refusal
        model_refs=(),  # the missing piece
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.REFUSED
    assert FORMAL_BOUND_TO_WORLD_WITHOUT_MODEL_FIDELITY in r.reasons
    assert not r.admitted


def test_model_bound_with_fidelity_admitted():
    m = ClaimManifest(
        species=ClaimSpecies.MODEL_BOUND,
        value="there are 9 servers",
        consumer="governor",
        scope="inventory:rack-7",
        model_refs=("receipt:inventory-binding@v3",),
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.ADMITTED


# --- Specimen 3: "credit score measures creditworthiness" → constitutivity refusal -


def test_constructed_instrument_presented_as_measurement_refused():
    m = ClaimManifest(
        species=ClaimSpecies.OBSERVED,
        value="credit score measures creditworthiness",
        consumer="lender",
        scope="population:applicants",  # scope present — isolates the constitutivity refusals
        kind_claim=KindClaim.HYBRID,
        instrument_role=InstrumentRole.ALLOCATES,
        presented_as_measurement=True,
        presented_as_stable_kind=True,
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.REFUSED
    # Both knives bite: the instrument issues orders, and a hybrid wears a stable hat.
    assert ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT in r.reasons
    assert CONSTRUCTED_OR_HYBRID_KIND_PRESENTED_AS_STABLE in r.reasons


def test_constructed_instrument_disclosed_admitted():
    # Same instrument, honestly disclosed: not presented as neutral measurement,
    # not presented as a stable kind. The gate records the assertion; honest
    # disclosure passes.
    m = ClaimManifest(
        species=ClaimSpecies.OBSERVED,
        value="credit score allocates loan terms",
        consumer="lender",
        scope="population:applicants",
        kind_claim=KindClaim.HYBRID,
        instrument_role=InstrumentRole.ALLOCATES,
        presented_as_measurement=False,
        presented_as_stable_kind=False,
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.ADMITTED


# --- Specimen 4: "Reddit consensus says X" → testimony yes, fact no ----------------


def test_testimonial_as_fact_refused():
    m = ClaimManifest(
        species=ClaimSpecies.TESTIMONIAL,
        value="Reddit consensus says X",
        consumer="answer_engine",
        scope="forum:reddit",
        presented_as_fact=True,
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.REFUSED
    assert TESTIMONIAL_PROMOTED_TO_FACT in r.reasons


def test_testimonial_as_discovery_admitted_as_testimony():
    m = ClaimManifest(
        species=ClaimSpecies.TESTIMONIAL,
        value="Reddit consensus says X",
        consumer="answer_engine",
        scope="forum:reddit",
        presented_as_fact=False,
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.ADMITTED
    assert r.scope == "forum:reddit"  # admitted AS testimony, not as fact


# --- Specimen 5: "Coq proved system safe" → scoped-or-refused ---------------------


def test_proof_promoted_to_system_safety_refused():
    m = ClaimManifest(
        species=ClaimSpecies.FORMAL,
        value="Coq proved the system safe",
        consumer="governor",
        is_proof=True,
        presented_as_system_safety=True,
        # no scope, no does_not_claim → the unlicensed jump from O-over-A to "safe"
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.REFUSED
    assert PROOF_RECEIPT_PROMOTED_TO_SYSTEM_SAFETY in r.reasons


def test_proof_scoped_with_does_not_claim_admitted():
    m = ClaimManifest(
        species=ClaimSpecies.FORMAL,
        value="Coq discharged O over A",
        consumer="governor",
        is_proof=True,
        presented_as_system_safety=True,
        scope="O over A",
        does_not_claim=("system safety", "model fidelity of A to the world"),
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.ADMITTED


# --- The load-bearing lesson: quarantine at discovery, fail-closed at reliance -----


def test_same_violation_quarantines_at_exploration_refuses_at_reliance():
    # Consumer + scope supplied so the ONLY finding is the conversion rule — holding
    # the reliance-context requirements constant isolates the quarantine/refuse split.
    m = ClaimManifest(
        species=ClaimSpecies.OBSERVED,
        value="credit score measures creditworthiness",
        consumer="lender",
        scope="population:applicants",
        kind_claim=KindClaim.HYBRID,
        instrument_role=InstrumentRole.ENFORCES,
        presented_as_measurement=True,
    )
    explored = classify(m, intent=EXPLORE)
    relied = classify(m, intent=RELY)

    # Exploration: quarantined — inspectable, carries the reason, but cannot promote.
    assert explored.status is AdmissionStatus.QUARANTINED
    assert not explored.admitted
    assert ALLOCATING_OR_ENFORCING_INSTRUMENT_PRESENTED_AS_MEASUREMENT in explored.reasons
    # Reliance: the SAME finding now fails closed — identical reason, different consequence.
    assert relied.status is AdmissionStatus.REFUSED
    assert explored.reasons == relied.reasons


def test_clean_claim_at_exploration_is_candidate_not_admitted():
    m = ClaimManifest(species=ClaimSpecies.FORMAL, value="3*3=9")
    r = classify(m, intent=EXPLORE)
    # Nothing wrong, but nothing relied upon — Candidate, and NOT promotable.
    assert r.status is AdmissionStatus.CANDIDATE
    assert not r.admitted


# --- Reliance-context requirements + closed-vocab property ------------------------


def test_reliance_requires_consumer():
    m = ClaimManifest(species=ClaimSpecies.FORMAL, value="3*3=9", consumer=None)
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.REFUSED
    assert CONSUMER_SCOPE_MISMATCH in r.reasons


def test_world_species_reliance_requires_scope_and_freshness():
    m = ClaimManifest(
        species=ClaimSpecies.OBSERVED,
        value="disk at 91%",
        consumer="governor",
        model_refs=("receipt:smart-binding",),
        scope=None,  # missing
        freshness_required=True,
        freshness=None,  # missing
    )
    r = classify(m, intent=RELY)
    assert r.status is AdmissionStatus.REFUSED
    assert MISSING_SCOPE in r.reasons
    assert MISSING_FRESHNESS in r.reasons


def test_only_admitted_promotes_and_reasons_are_closed_vocab():
    # Exhaustive over the specimen set: only ADMITTED carries .admitted, and every
    # reason emitted is from the closed refusal vocabulary.
    cases = [
        classify(ClaimManifest(species=ClaimSpecies.FORMAL, consumer="g"), intent=RELY),
        classify(ClaimManifest(species=ClaimSpecies.MODEL_BOUND, consumer="g", scope="s"), intent=RELY),
        classify(ClaimManifest(species=ClaimSpecies.FORMAL), intent=EXPLORE),
    ]
    for r in cases:
        assert r.admitted == (r.status is AdmissionStatus.ADMITTED)
        for reason in r.reasons:
            assert reason in REFUSAL_REASONS
