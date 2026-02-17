# SPDX-License-Identifier: Apache-2.0
"""Tests for fiction_governor.guardrails — consent, DSI, AII, constraints, penalties."""

import pytest
from fiction_governor.guardrails import (
    # Enums
    ConsentLevel,
    ConsentScope,
    HardConstraintId,
    SoftPenaltyId,
    SCOPE_ORDER,
    # Dataclasses
    ConsentPairState,
    GlobalConsentState,
    ValidityProfile,
    DSISignal,
    AIISignal,
    ConstraintViolation,
    PenaltyResult,
    GuardrailConfig,
    StateContext,
    GuardrailResult,
    # Classes
    ConsentLedger,
    DSIDetector,
    AIIDetector,
    FictionGuardrails,
    # Functions
    detect_sexual_content,
    detect_coercion,
    detect_proxy_dominance,
    detect_unearned_facts,
    create_consent_ledger,
    create_fiction_guardrails,
    create_guardrail_config,
    create_validity_profile,
    get_builtin_profiles,
    # Constants
    BUILTIN_PROFILES,
    DEMOGRAPHIC_MARKERS,
    CORRELATED_BUNDLES,
)


# ============================================================
# Enum tests
# ============================================================


class TestConsentLevel:
    def test_values(self):
        assert ConsentLevel.UNKNOWN.value == "unknown"
        assert ConsentLevel.NO.value == "no"
        assert ConsentLevel.YES.value == "yes"
        assert ConsentLevel.YES_EXPLICIT.value == "yes_explicit"


class TestConsentScope:
    def test_values(self):
        assert ConsentScope.FLIRT.value == "flirt"
        assert ConsentScope.TOUCH.value == "touch"
        assert ConsentScope.SEX.value == "sex"
        assert ConsentScope.KINK_COERCIVE_PLAY.value == "kink_coercive_play"

    def test_ordering(self):
        assert SCOPE_ORDER[ConsentScope.FLIRT] < SCOPE_ORDER[ConsentScope.TOUCH]
        assert SCOPE_ORDER[ConsentScope.TOUCH] < SCOPE_ORDER[ConsentScope.SEX]
        assert SCOPE_ORDER[ConsentScope.SEX] < SCOPE_ORDER[ConsentScope.KINK_COERCIVE_PLAY]


class TestHardConstraintId:
    def test_values(self):
        assert HardConstraintId.C1_CONSENT_GATE.value == "C1_consent_gate"
        assert HardConstraintId.C2_MODE_ESCALATION.value == "C2_mode_escalation"
        assert HardConstraintId.C3_ANACHRONISM_CAUSAL.value == "C3_anachronism_causal"


class TestSoftPenaltyId:
    def test_values(self):
        assert SoftPenaltyId.P1_DSI.value == "P1_dsi"
        assert SoftPenaltyId.P2_UNEARNED_FACT.value == "P2_unearned_fact"
        assert SoftPenaltyId.P3_REGISTER_DRIFT.value == "P3_register_drift"
        assert SoftPenaltyId.P4_PROXY_DOMINANCE.value == "P4_proxy_dominance"


# ============================================================
# Dataclass tests
# ============================================================


class TestConsentPairState:
    def test_defaults(self):
        s = ConsentPairState()
        assert s.get_level(ConsentScope.FLIRT) == ConsentLevel.UNKNOWN
        assert s.get_level(ConsentScope.SEX) == ConsentLevel.UNKNOWN

    def test_set_and_get(self):
        s = ConsentPairState()
        s.set_level(ConsentScope.FLIRT, ConsentLevel.YES)
        assert s.get_level(ConsentScope.FLIRT) == ConsentLevel.YES
        assert s.get_level(ConsentScope.TOUCH) == ConsentLevel.UNKNOWN

    def test_roundtrip(self):
        s = ConsentPairState()
        s.set_level(ConsentScope.SEX, ConsentLevel.YES_EXPLICIT)
        s.last_update_token = 500
        s.evidence_spans = ["span:123"]
        d = s.to_dict()
        s2 = ConsentPairState.from_dict(d)
        assert s2.get_level(ConsentScope.SEX) == ConsentLevel.YES_EXPLICIT
        assert s2.last_update_token == 500
        assert s2.evidence_spans == ["span:123"]


class TestGlobalConsentState:
    def test_defaults(self):
        g = GlobalConsentState()
        assert g.erotic_allowed is False
        assert g.coercive_play_allowed is False

    def test_roundtrip(self):
        g = GlobalConsentState(erotic_allowed=True, user_opt_in_evidence=["user said yes"])
        d = g.to_dict()
        g2 = GlobalConsentState.from_dict(d)
        assert g2.erotic_allowed is True
        assert g2.user_opt_in_evidence == ["user said yes"]


class TestValidityProfile:
    def test_create(self):
        p = ValidityProfile(
            name="test",
            valid_terms=["Tuscan", "Venetian"],
            invalid_terms=["Italian"],
            era_start=500,
            era_end=1500,
        )
        assert p.name == "test"

    def test_term_validity(self):
        p = ValidityProfile(
            name="test",
            valid_terms=["Tuscan"],
            invalid_terms=["Italian"],
        )
        assert p.is_term_valid("Tuscan") is True
        assert p.is_term_valid("Italian") is False
        assert p.is_term_valid("Venetian") is True  # Not in either list = valid

    def test_case_insensitive(self):
        p = ValidityProfile(name="test", invalid_terms=["Italian"])
        assert p.is_term_valid("italian") is False
        assert p.is_term_valid("ITALIAN") is False

    def test_covers_year(self):
        p = ValidityProfile(name="test", era_start=500, era_end=1500)
        assert p.covers_year(1000) is True
        assert p.covers_year(300) is False
        assert p.covers_year(1600) is False

    def test_covers_year_open_ended(self):
        p = ValidityProfile(name="test", era_start=500)
        assert p.covers_year(3000) is True
        assert p.covers_year(400) is False

    def test_roundtrip(self):
        p = ValidityProfile(
            name="medieval",
            valid_terms=["Frankish"],
            invalid_terms=["French"],
            era_start=500,
            era_end=1500,
            description="test profile",
        )
        d = p.to_dict()
        p2 = ValidityProfile.from_dict(d)
        assert p2.name == "medieval"
        assert p2.is_term_valid("Frankish") is True
        assert p2.is_term_valid("French") is False


class TestDSISignal:
    def test_create(self):
        s = DSISignal(
            demographic_marker="race_black",
            correlated_bundle="civil rights",
            has_local_trigger=False,
            score=1.0,
        )
        assert s.score == 1.0

    def test_roundtrip(self):
        s = DSISignal("race_asian", "math", True, 0.0)
        d = s.to_dict()
        s2 = DSISignal.from_dict(d)
        assert s2.demographic_marker == "race_asian"
        assert s2.has_local_trigger is True


class TestAIISignal:
    def test_create(self):
        s = AIISignal(
            identity_term="Italian",
            era="medieval_europe",
            used_causally=True,
            valid_for_era=False,
        )
        assert s.valid_for_era is False

    def test_roundtrip(self):
        s = AIISignal("Italian", "medieval_europe", True, False)
        d = s.to_dict()
        s2 = AIISignal.from_dict(d)
        assert s2.identity_term == "Italian"
        assert s2.valid_for_era is False


class TestConstraintViolation:
    def test_create(self):
        v = ConstraintViolation(
            constraint_id=HardConstraintId.C1_CONSENT_GATE,
            reason="coercive_play_not_opted_in",
            detail="test",
        )
        assert v.constraint_id == HardConstraintId.C1_CONSENT_GATE

    def test_roundtrip(self):
        v = ConstraintViolation(HardConstraintId.C3_ANACHRONISM_CAUSAL, "test", "detail")
        d = v.to_dict()
        v2 = ConstraintViolation.from_dict(d)
        assert v2.constraint_id == HardConstraintId.C3_ANACHRONISM_CAUSAL


class TestPenaltyResult:
    def test_create(self):
        p = PenaltyResult(
            penalty_id=SoftPenaltyId.P1_DSI,
            score=2.0,
            detail="intrusion detected",
        )
        assert p.score == 2.0

    def test_roundtrip(self):
        p = PenaltyResult(SoftPenaltyId.P4_PROXY_DOMINANCE, 1.5, "proxy")
        d = p.to_dict()
        p2 = PenaltyResult.from_dict(d)
        assert p2.penalty_id == SoftPenaltyId.P4_PROXY_DOMINANCE
        assert p2.score == 1.5


class TestGuardrailConfig:
    def test_defaults(self):
        c = GuardrailConfig()
        assert c.block_coercive_without_opt_in is True
        assert c.lambda_dsi == 2.0

    def test_custom(self):
        c = GuardrailConfig(lambda_dsi=5.0, block_anachronistic_causal=False)
        assert c.lambda_dsi == 5.0
        assert c.block_anachronistic_causal is False

    def test_roundtrip(self):
        c = GuardrailConfig(lambda_proxy=3.0)
        d = c.to_dict()
        c2 = GuardrailConfig.from_dict(d)
        assert c2.lambda_proxy == 3.0


class TestStateContext:
    def test_defaults(self):
        ctx = StateContext()
        assert ctx.world_year is None
        assert ctx.current_register == "literary"
        assert ctx.erotic_allowed is False

    def test_custom(self):
        ctx = StateContext(
            world_year=1200,
            era_tags=["medieval"],
            character_facts={"Erin": ["grew up in Florence"]},
        )
        assert ctx.world_year == 1200

    def test_roundtrip(self):
        ctx = StateContext(world_year=1200, era_tags=["medieval"])
        d = ctx.to_dict()
        ctx2 = StateContext.from_dict(d)
        assert ctx2.world_year == 1200
        assert ctx2.era_tags == ["medieval"]


class TestGuardrailResult:
    def test_pass(self):
        r = GuardrailResult()
        assert r.passed is True
        assert r.total_penalty == 0.0

    def test_fail(self):
        v = ConstraintViolation(HardConstraintId.C1_CONSENT_GATE, "test", "detail")
        r = GuardrailResult(violations=[v], passed=False)
        assert r.passed is False

    def test_roundtrip(self):
        p = PenaltyResult(SoftPenaltyId.P1_DSI, 1.0, "test")
        r = GuardrailResult(penalties=[p], total_penalty=2.0)
        d = r.to_dict()
        r2 = GuardrailResult.from_dict(d)
        assert r2.total_penalty == 2.0
        assert len(r2.penalties) == 1


# ============================================================
# Detection function tests
# ============================================================


class TestDetectSexualContent:
    def test_clean_text(self):
        assert detect_sexual_content("The cat sat on the mat.") is False

    def test_kiss(self):
        assert detect_sexual_content("He kissed her softly.") is True

    def test_explicit(self):
        assert detect_sexual_content("She moaned with arousal and climax.") is True

    def test_body_parts(self):
        assert detect_sexual_content("Her bare breast was visible.") is True


class TestDetectCoercion:
    def test_clean_text(self):
        assert detect_coercion("They walked together in the park.") is False

    def test_forced(self):
        assert detect_coercion("He forced her to stay.") is True

    def test_against_will(self):
        assert detect_coercion("It happened against her will.") is True

    def test_pinned_down(self):
        assert detect_coercion("He pinned her down on the bed.") is True

    def test_struggle(self):
        assert detect_coercion("She struggled against the restraints.") is True

    def test_helpless(self):
        assert detect_coercion("She was helplessly trapped.") is True


class TestDetectProxyDominance:
    def test_clean_text(self):
        assert detect_proxy_dominance("She liked coffee.") == []

    def test_statistically(self):
        matches = detect_proxy_dominance("Statistically, people like him tend to...")
        assert len(matches) >= 1

    def test_studies_show(self):
        matches = detect_proxy_dominance("Studies show that this is common.")
        assert len(matches) >= 1

    def test_culturally(self):
        matches = detect_proxy_dominance("Culturally, they were expected to honor elders.")
        assert len(matches) >= 1


class TestDetectUnearnedFacts:
    def test_clean_text(self):
        assert detect_unearned_facts("She liked coffee.") == []

    def test_medical_unearned(self):
        text = "Her parents both had high blood pressure."
        unearned = detect_unearned_facts(text)
        assert len(unearned) >= 1

    def test_medical_earned(self):
        text = "Her parents both had high blood pressure."
        facts = {"Erin": ["parents have high blood pressure"]}
        unearned = detect_unearned_facts(text, facts)
        assert len(unearned) == 0

    def test_trauma_unearned(self):
        text = "She suffered from PTSD after the incident."
        unearned = detect_unearned_facts(text)
        assert len(unearned) >= 1

    def test_addiction_unearned(self):
        text = "His alcoholism destroyed his family."
        unearned = detect_unearned_facts(text)
        assert len(unearned) >= 1


# ============================================================
# ConsentLedger tests
# ============================================================


class TestConsentLedger:
    def test_create(self):
        l = ConsentLedger()
        assert l.global_state.erotic_allowed is False

    def test_update_and_get(self):
        l = ConsentLedger()
        l.update_consent("Alice", "Bob", ConsentScope.FLIRT, ConsentLevel.YES)
        assert l.get_consent("Alice", "Bob", ConsentScope.FLIRT) == ConsentLevel.YES

    def test_pair_key_is_canonical(self):
        l = ConsentLedger()
        l.update_consent("Alice", "Bob", ConsentScope.TOUCH, ConsentLevel.YES)
        # Should be same regardless of order
        assert l.get_consent("Bob", "Alice", ConsentScope.TOUCH) == ConsentLevel.YES

    def test_unknown_pair(self):
        l = ConsentLedger()
        assert l.get_consent("X", "Y", ConsentScope.SEX) == ConsentLevel.UNKNOWN

    def test_get_pair_state(self):
        l = ConsentLedger()
        l.update_consent("A", "B", ConsentScope.FLIRT, ConsentLevel.YES, token=100, evidence="span:1")
        pair = l.get_pair_state("A", "B")
        assert pair is not None
        assert pair.last_update_token == 100
        assert "span:1" in pair.evidence_spans

    def test_get_pair_state_missing(self):
        l = ConsentLedger()
        assert l.get_pair_state("X", "Y") is None

    def test_check_escalation_ok(self):
        l = ConsentLedger()
        l.update_consent("A", "B", ConsentScope.SEX, ConsentLevel.YES_EXPLICIT)
        violation = l.check_escalation("A", "B", ConsentScope.SEX)
        assert violation is None

    def test_check_escalation_blocked_unknown(self):
        l = ConsentLedger()
        # SEX requires explicit consent
        violation = l.check_escalation("A", "B", ConsentScope.SEX)
        assert violation is not None
        assert violation.constraint_id == HardConstraintId.C1_CONSENT_GATE

    def test_check_escalation_blocked_no(self):
        l = ConsentLedger()
        l.update_consent("A", "B", ConsentScope.TOUCH, ConsentLevel.NO)
        violation = l.check_escalation("A", "B", ConsentScope.TOUCH)
        assert violation is not None
        assert "explicitly denied" in violation.detail

    def test_check_escalation_flirt_unknown_ok(self):
        l = ConsentLedger()
        # FLIRT is low scope — unknown is OK
        violation = l.check_escalation("A", "B", ConsentScope.FLIRT)
        assert violation is None

    def test_set_global(self):
        l = ConsentLedger()
        l.set_global(erotic_allowed=True, evidence="user asked for mature content")
        assert l.global_state.erotic_allowed is True
        assert "user asked for mature content" in l.global_state.user_opt_in_evidence

    def test_roundtrip(self):
        l = ConsentLedger()
        l.update_consent("A", "B", ConsentScope.FLIRT, ConsentLevel.YES)
        l.set_global(erotic_allowed=True)
        d = l.to_dict()
        l2 = ConsentLedger.from_dict(d)
        assert l2.get_consent("A", "B", ConsentScope.FLIRT) == ConsentLevel.YES
        assert l2.global_state.erotic_allowed is True


# ============================================================
# DSIDetector tests
# ============================================================


class TestDSIDetector:
    def test_create(self):
        d = DSIDetector()
        assert d is not None

    def test_clean_text(self):
        d = DSIDetector()
        signals = d.detect("The cat sat on the mat.")
        assert len(signals) == 0

    def test_detect_black_civil_rights(self):
        d = DSIDetector()
        text = "Marcus, a Black man, thought about the civil rights movement as he made breakfast."
        signals = d.detect(text)
        assert len(signals) >= 1
        assert signals[0].demographic_marker == "race_black"
        assert signals[0].has_local_trigger is False
        assert signals[0].score > 0

    def test_detect_with_local_trigger(self):
        d = DSIDetector()
        text = "Marcus, a Black man, reflected on the civil rights march he attended."
        facts = {"Marcus": ["attended a civil rights march in 1965"]}
        signals = d.detect(text, facts)
        # Should find it but with local trigger
        triggered = [s for s in signals if s.has_local_trigger]
        assert len(triggered) >= 1

    def test_detect_asian_math(self):
        d = DSIDetector()
        text = "Li, a Chinese student, excelled at math and played the violin."
        signals = d.detect(text)
        assert len(signals) >= 1
        assert any(s.demographic_marker == "race_asian" for s in signals)

    def test_detect_italian_mafia(self):
        d = DSIDetector()
        text = "Tony, an Italian man from Brooklyn, thought about the mafia connections in his neighborhood."
        signals = d.detect(text)
        assert len(signals) >= 1
        assert any(s.demographic_marker == "nationality_italian" for s in signals)

    def test_no_demographic_marker(self):
        d = DSIDetector()
        text = "She thought about civil rights movements throughout history."
        signals = d.detect(text)
        # No demographic marker present, so no DSI
        assert len(signals) == 0

    def test_custom_bundles(self):
        d = DSIDetector(custom_bundles={"race_black": [r"\bcustom_pattern\b"]})
        text = "Marcus, a Black man, encountered a custom_pattern."
        signals = d.detect(text)
        assert len(signals) >= 1

    def test_medical_unearned_with_race(self):
        d = DSIDetector()
        text = "Keisha, a Black woman, worried about her high blood pressure at dinner."
        signals = d.detect(text)
        assert len(signals) >= 1
        assert any("blood pressure" in s.correlated_bundle.lower() or "hypertension" in s.correlated_bundle.lower()
                    for s in signals)


# ============================================================
# AIIDetector tests
# ============================================================


class TestAIIDetector:
    def test_create(self):
        d = AIIDetector()
        assert d is not None

    def test_no_temporal_context(self):
        d = AIIDetector()
        signals = d.detect("because he's Italian, he was passionate", world_year=None)
        assert len(signals) == 0  # No profile matched

    def test_medieval_italian_blocked(self):
        d = AIIDetector()
        text = "because he's Italian, he was passionate about cooking"
        signals = d.detect(text, world_year=1200)
        invalid = [s for s in signals if not s.valid_for_era]
        assert len(invalid) >= 1
        assert invalid[0].identity_term.lower() == "italian"

    def test_medieval_tuscan_allowed(self):
        d = AIIDetector()
        text = "being Tuscan, he was proud of his city"
        signals = d.detect(text, world_year=1200)
        for s in signals:
            if s.identity_term.lower() == "tuscan":
                assert s.valid_for_era is True

    def test_modern_era_italian_ok(self):
        d = AIIDetector()
        text = "because he's Italian, he loved pasta"
        # Year 2000 — no profile covers this
        signals = d.detect(text, world_year=2000)
        assert len(signals) == 0

    def test_era_tags(self):
        d = AIIDetector()
        text = "as a German knight, he rode into battle"
        signals = d.detect(text, era_tags=["medieval"])
        invalid = [s for s in signals if not s.valid_for_era]
        assert len(invalid) >= 1

    def test_custom_profile(self):
        custom = ValidityProfile(
            name="test_era",
            valid_terms=["Spartan"],
            invalid_terms=["Greek"],
            era_start=-1000,
            era_end=-300,
        )
        d = AIIDetector(profiles=[custom])
        text = "because he's Greek, he was philosophical"
        signals = d.detect(text, world_year=-500)
        invalid = [s for s in signals if not s.valid_for_era]
        assert len(invalid) >= 1

    def test_non_causal_not_detected(self):
        d = AIIDetector()
        text = "The Italian merchants were present at the market."
        # No causal pattern — just a descriptor
        signals = d.detect(text, world_year=1200)
        assert len(signals) == 0  # No causal usage detected

    def test_as_a_pattern(self):
        d = AIIDetector()
        text = "As a French woman, she carried herself with grace."
        signals = d.detect(text, world_year=1200)
        invalid = [s for s in signals if not s.valid_for_era]
        assert len(invalid) >= 1


class TestBuiltinProfiles:
    def test_medieval_europe_exists(self):
        assert "medieval_europe" in BUILTIN_PROFILES

    def test_renaissance_europe_exists(self):
        assert "renaissance_europe" in BUILTIN_PROFILES

    def test_ancient_world_exists(self):
        assert "ancient_world" in BUILTIN_PROFILES

    def test_colonial_era_exists(self):
        assert "colonial_era" in BUILTIN_PROFILES

    def test_medieval_italian_invalid(self):
        p = BUILTIN_PROFILES["medieval_europe"]
        assert p.is_term_valid("Italian") is False
        assert p.is_term_valid("Tuscan") is True

    def test_medieval_covers_1200(self):
        p = BUILTIN_PROFILES["medieval_europe"]
        assert p.covers_year(1200) is True
        assert p.covers_year(1600) is False

    def test_ancient_world_covers_minus_500(self):
        p = BUILTIN_PROFILES["ancient_world"]
        assert p.covers_year(-500) is True

    def test_all_have_description(self):
        for name, profile in BUILTIN_PROFILES.items():
            assert profile.description, f"Missing description for {name}"


# ============================================================
# FictionGuardrails tests
# ============================================================


class TestFictionGuardrails:
    def test_create(self):
        g = FictionGuardrails()
        assert g.config.block_coercive_without_opt_in is True

    def test_clean_text_passes(self):
        g = FictionGuardrails()
        ctx = StateContext()
        result = g.check("The cat sat on the mat.", ctx)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_c1_coercion_blocked(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = "He kissed her neck then forced her to stay, pinning her down despite her protest."
        result = g.check(text, ctx)
        assert result.passed is False
        assert any(v.constraint_id == HardConstraintId.C1_CONSENT_GATE for v in result.violations)

    def test_c1_coercion_allowed_with_opt_in(self):
        g = FictionGuardrails()
        g.consent.set_global(coercive_play_allowed=True)
        ctx = StateContext(coercive_play_allowed=True)
        text = "He forced her to stay, pinning her down despite her protest. She moaned."
        result = g.check(text, ctx)
        # With opt-in, C1 should not fire
        c1_violations = [v for v in result.violations if v.constraint_id == HardConstraintId.C1_CONSENT_GATE]
        assert len(c1_violations) == 0

    def test_c2_mode_escalation_blocked(self):
        g = FictionGuardrails()
        ctx = StateContext(current_risk_tier="low")
        text = "She moaned with arousal as the orgasm built and she writhed with climax."
        result = g.check(text, ctx)
        assert result.passed is False
        assert any(v.constraint_id == HardConstraintId.C2_MODE_ESCALATION for v in result.violations)

    def test_c2_mode_escalation_allowed_with_enable(self):
        g = FictionGuardrails()
        ctx = StateContext(current_risk_tier="low", erotic_allowed=True)
        text = "She moaned with arousal as the orgasm built."
        result = g.check(text, ctx)
        c2_violations = [v for v in result.violations if v.constraint_id == HardConstraintId.C2_MODE_ESCALATION]
        assert len(c2_violations) == 0

    def test_c2_mode_escalation_allowed_in_high_risk(self):
        g = FictionGuardrails()
        ctx = StateContext(current_risk_tier="high")
        text = "She moaned with arousal as the orgasm built."
        result = g.check(text, ctx)
        c2_violations = [v for v in result.violations if v.constraint_id == HardConstraintId.C2_MODE_ESCALATION]
        assert len(c2_violations) == 0

    def test_c3_anachronism_blocked(self):
        g = FictionGuardrails()
        ctx = StateContext(world_year=1200, era_tags=["medieval"])
        text = "because he's Italian, he was passionate about the food"
        result = g.check(text, ctx)
        assert result.passed is False
        assert any(v.constraint_id == HardConstraintId.C3_ANACHRONISM_CAUSAL for v in result.violations)

    def test_c3_anachronism_not_triggered_for_valid(self):
        g = FictionGuardrails()
        ctx = StateContext(world_year=1200, era_tags=["medieval"])
        text = "being Tuscan, he was proud of his city's traditions"
        result = g.check(text, ctx)
        c3_violations = [v for v in result.violations if v.constraint_id == HardConstraintId.C3_ANACHRONISM_CAUSAL]
        assert len(c3_violations) == 0

    def test_c3_disabled(self):
        config = GuardrailConfig(block_anachronistic_causal=False)
        g = FictionGuardrails(config=config)
        ctx = StateContext(world_year=1200, era_tags=["medieval"])
        text = "because he's Italian, he loved pasta"
        result = g.check(text, ctx)
        c3_violations = [v for v in result.violations if v.constraint_id == HardConstraintId.C3_ANACHRONISM_CAUSAL]
        assert len(c3_violations) == 0


class TestSoftPenalties:
    def test_p1_dsi_fires(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = "Marcus, a Black man, thought about the civil rights struggle as he cooked dinner."
        result = g.check(text, ctx)
        p1 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P1_DSI]
        assert len(p1) == 1
        assert p1[0].score > 0

    def test_p1_dsi_with_local_trigger(self):
        g = FictionGuardrails()
        ctx = StateContext(character_facts={"Marcus": ["civil rights activist"]})
        text = "Marcus, a Black man, thought about the civil rights struggle."
        result = g.check(text, ctx)
        p1 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P1_DSI]
        assert len(p1) == 1
        # With local trigger, score should be 0
        assert p1[0].score == 0.0

    def test_p2_unearned_fires(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = "She found out her father had high blood pressure and diabetes."
        result = g.check(text, ctx)
        p2 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P2_UNEARNED_FACT]
        assert len(p2) == 1
        assert p2[0].score > 0

    def test_p2_earned_fact_no_penalty(self):
        g = FictionGuardrails()
        ctx = StateContext(character_facts={"Anna": ["father has high blood pressure"]})
        text = "She found out her father had high blood pressure."
        result = g.check(text, ctx)
        p2 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P2_UNEARNED_FACT]
        assert len(p2) == 1
        assert p2[0].score == 0.0

    def test_p3_drift_no_penalty_when_signaled(self):
        g = FictionGuardrails()
        ctx = StateContext(user_signaled_mode=True)
        result = g.check("text", ctx)
        p3 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P3_REGISTER_DRIFT]
        assert len(p3) == 1
        assert p3[0].score == 0.0

    def test_p3_drift_with_score(self):
        g = FictionGuardrails()
        ctx = StateContext(drift_score=0.7)
        result = g.check("text", ctx)
        p3 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P3_REGISTER_DRIFT]
        assert len(p3) == 1
        assert p3[0].score == 0.7

    def test_p4_proxy_fires(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = "Statistically, people like him tend to be more aggressive."
        result = g.check(text, ctx)
        p4 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P4_PROXY_DOMINANCE]
        assert len(p4) == 1
        assert p4[0].score > 0

    def test_p4_no_proxy(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = "He was angry because his dog ran away."
        result = g.check(text, ctx)
        p4 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P4_PROXY_DOMINANCE]
        assert len(p4) == 1
        assert p4[0].score == 0.0


class TestTotalPenalty:
    def test_clean_text_zero_penalty(self):
        g = FictionGuardrails()
        ctx = StateContext()
        result = g.check("The cat sat on the mat.", ctx)
        assert result.total_penalty == 0.0

    def test_penalty_weighted(self):
        g = FictionGuardrails()
        ctx = StateContext(drift_score=1.0)
        result = g.check("The cat sat on the mat.", ctx)
        # drift_score=1.0 with lambda_drift=1.0 should contribute 1.0
        assert result.total_penalty >= 1.0

    def test_multiple_penalties_sum(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = (
            "Marcus, a Black man, worried about civil rights and his high blood pressure. "
            "Statistically, people like him tend to have health issues."
        )
        result = g.check(text, ctx)
        assert result.total_penalty > 0.0
        active_penalties = [p for p in result.penalties if p.score > 0]
        assert len(active_penalties) >= 2


class TestGuardrailsSerialization:
    def test_roundtrip(self):
        g = FictionGuardrails(config=GuardrailConfig(lambda_dsi=5.0))
        g.consent.update_consent("A", "B", ConsentScope.FLIRT, ConsentLevel.YES)
        d = g.to_dict()
        g2 = FictionGuardrails.from_dict(d)
        assert g2.config.lambda_dsi == 5.0
        assert g2.consent.get_consent("A", "B", ConsentScope.FLIRT) == ConsentLevel.YES


# ============================================================
# Convenience function tests
# ============================================================


class TestConvenience:
    def test_create_consent_ledger(self):
        l = create_consent_ledger()
        assert isinstance(l, ConsentLedger)

    def test_create_fiction_guardrails(self):
        g = create_fiction_guardrails()
        assert isinstance(g, FictionGuardrails)

    def test_create_guardrail_config(self):
        c = create_guardrail_config(lambda_dsi=10.0)
        assert c.lambda_dsi == 10.0

    def test_create_validity_profile(self):
        p = create_validity_profile(
            name="test",
            valid_terms=["Spartan"],
            invalid_terms=["Greek"],
            era_start=-1000,
        )
        assert p.name == "test"
        assert p.is_term_valid("Spartan") is True
        assert p.is_term_valid("Greek") is False

    def test_get_builtin_profiles(self):
        profiles = get_builtin_profiles()
        assert "medieval_europe" in profiles
        assert "ancient_world" in profiles


# ============================================================
# Edge case tests
# ============================================================


class TestEdgeCases:
    def test_empty_text(self):
        g = FictionGuardrails()
        ctx = StateContext()
        result = g.check("", ctx)
        assert result.passed is True

    def test_no_character_facts(self):
        g = FictionGuardrails()
        ctx = StateContext(character_facts={})
        text = "She had high blood pressure."
        result = g.check(text, ctx)
        p2 = [p for p in result.penalties if p.penalty_id == SoftPenaltyId.P2_UNEARNED_FACT]
        assert p2[0].score > 0

    def test_all_hard_disabled(self):
        config = GuardrailConfig(
            block_coercive_without_opt_in=False,
            block_high_risk_without_enable=False,
            block_anachronistic_causal=False,
        )
        g = FictionGuardrails(config=config)
        ctx = StateContext(world_year=1200)
        text = "He forced her to stay because he's Italian. She moaned with arousal."
        result = g.check(text, ctx)
        assert result.passed is True  # All hard constraints disabled

    def test_multiple_violations(self):
        g = FictionGuardrails()
        ctx = StateContext(world_year=1200, era_tags=["medieval"], current_risk_tier="low")
        text = (
            "Because he's Italian, he forced her to stay. "
            "She kissed him and moaned with arousal as the orgasm built."
        )
        result = g.check(text, ctx)
        assert len(result.violations) >= 2

    def test_unicode_text(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = "Elle murmura doucement, 'Je t'aime,' et l'embrassa."
        result = g.check(text, ctx)
        assert result.passed is True

    def test_very_long_text(self):
        g = FictionGuardrails()
        ctx = StateContext()
        text = "The cat sat on the mat. " * 1000
        result = g.check(text, ctx)
        assert result.passed is True
