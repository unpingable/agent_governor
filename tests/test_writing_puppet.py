"""Tests for writing_puppet.py — Character constraints for authorial control."""

import pytest

from governor.writing_puppet import (
    CHEERFUL_SHOPKEEPER_CHARACTER,
    COMEDIC_SIDEKICK_AFFINITY,
    COMMITMENT_ORDER,
    DOCTOR_AUTHORITY,
    ELDER_AUTHORITY,
    ELDER_NORMATIVITY,
    FOOL_AFFINITY,
    FOOL_AUTHORITY,
    FOOL_CEILING,
    FOOL_CHARACTER,
    GRUFF_DETECTIVE_CHARACTER,
    NEUTRAL_NARRATOR_AFFINITY,
    NO_NORMATIVITY,
    PRESET_CHARACTERS,
    PROPHET_AUTHORITY,
    PROPHET_CEILING,
    PROPHET_NORMATIVITY,
    SHOPKEEPER_CEILING,
    TRAGIC_HERO_AFFINITY,
    WISE_ELDER_AFFINITY,
    WISE_ELDER_CHARACTER,
    AuthoritySource,
    CHARACTER_GOVERNANCE_LEAK_PATTERNS,
    CharacterAuthority,
    CharacterClaim,
    CharacterCommitment,
    CharacterDefinition,
    CharacterViolation,
    CharacterViolationType,
    CommitmentCeiling,
    CommitmentType,
    ConsistencyState,
    Contradiction,
    NormativityPermission,
    PuppetModeConfig,
    PuppetModeController,
    PuppetModeResult,
    PuppetTicketType,
    RecursiveDepth,
    RecursivePuppetConfig,
    RegimeAffinity,
    SceneContext,
    commitment_level,
    detect_character_governance_leak,
    get_preset_character,
    has_character_governance_leak,
    resolve_regime,
    validate_recursive_puppet,
)
from governor.writing_tone import ToneEnvelope, ToneVector


# =============================================================================
# AuthoritySource Tests
# =============================================================================


class TestAuthoritySource:
    def test_all_values(self):
        assert AuthoritySource.INSTITUTIONAL.value == "institutional"
        assert AuthoritySource.EXPERIENCE.value == "experience"
        assert AuthoritySource.MORAL.value == "moral"
        assert AuthoritySource.CRAFT.value == "craft"
        assert AuthoritySource.RITUAL.value == "ritual"
        assert AuthoritySource.NONE.value == "none"


# =============================================================================
# CommitmentType Tests
# =============================================================================


class TestCommitmentType:
    def test_all_values(self):
        assert CommitmentType.ATTENTION.value == "attention"
        assert CommitmentType.BELIEF.value == "belief"
        assert CommitmentType.ACTION.value == "action"
        assert CommitmentType.IDENTITY.value == "identity"

    def test_commitment_order(self):
        assert len(COMMITMENT_ORDER) == 4
        assert COMMITMENT_ORDER[0] == CommitmentType.ATTENTION
        assert COMMITMENT_ORDER[-1] == CommitmentType.IDENTITY

    def test_commitment_level(self):
        assert commitment_level(CommitmentType.ATTENTION) == 0
        assert commitment_level(CommitmentType.BELIEF) == 1
        assert commitment_level(CommitmentType.ACTION) == 2
        assert commitment_level(CommitmentType.IDENTITY) == 3


# =============================================================================
# RegimeAffinity Tests
# =============================================================================


class TestRegimeAffinity:
    def test_defaults(self):
        affinity = RegimeAffinity(primary="comedy")
        assert affinity.primary == "comedy"
        assert affinity.secondary is None
        assert affinity.forbidden == []
        assert affinity.override_strength == 0.5

    def test_allows_regime(self):
        affinity = RegimeAffinity(
            primary="comedy",
            forbidden=["tragedy", "liturgical"],
        )
        assert affinity.allows_regime("comedy")
        assert affinity.allows_regime("drama")
        assert not affinity.allows_regime("tragedy")
        assert not affinity.allows_regime("liturgical")

    def test_to_dict(self):
        affinity = RegimeAffinity(
            primary="comedy",
            secondary="sincerity",
            forbidden=["tragedy"],
            override_strength=0.7,
        )
        d = affinity.to_dict()
        assert d["primary"] == "comedy"
        assert d["secondary"] == "sincerity"
        assert d["forbidden"] == ["tragedy"]
        assert d["override_strength"] == 0.7

    def test_from_dict(self):
        d = {
            "primary": "tragedy",
            "secondary": "drama",
            "forbidden": ["comedy"],
            "override_strength": 0.8,
        }
        affinity = RegimeAffinity.from_dict(d)
        assert affinity.primary == "tragedy"
        assert affinity.secondary == "drama"
        assert affinity.forbidden == ["comedy"]
        assert affinity.override_strength == 0.8


class TestRegimeAffinityPresets:
    def test_comedic_sidekick(self):
        assert COMEDIC_SIDEKICK_AFFINITY.primary == "comedy"
        assert "tragedy" in COMEDIC_SIDEKICK_AFFINITY.forbidden

    def test_tragic_hero(self):
        assert TRAGIC_HERO_AFFINITY.primary == "tragedy"
        assert "comedy" in TRAGIC_HERO_AFFINITY.forbidden

    def test_neutral_narrator(self):
        assert NEUTRAL_NARRATOR_AFFINITY.primary == "nonfiction"

    def test_wise_elder(self):
        assert WISE_ELDER_AFFINITY.primary == "sincerity"

    def test_fool(self):
        assert FOOL_AFFINITY.primary == "comedy"


# =============================================================================
# CharacterAuthority Tests
# =============================================================================


class TestCharacterAuthority:
    def test_defaults(self):
        auth = CharacterAuthority(primary=AuthoritySource.EXPERIENCE)
        assert auth.primary == AuthoritySource.EXPERIENCE
        assert auth.secondary is None
        assert auth.strength == 0.5
        assert auth.can_claim_without_demonstration is False

    def test_to_dict(self):
        auth = CharacterAuthority(
            primary=AuthoritySource.INSTITUTIONAL,
            secondary=AuthoritySource.EXPERIENCE,
            strength=0.7,
        )
        d = auth.to_dict()
        assert d["primary"] == "institutional"
        assert d["secondary"] == "experience"

    def test_from_dict(self):
        d = {
            "primary": "moral",
            "secondary": "ritual",
            "strength": 0.8,
            "can_claim_without_demonstration": True,
        }
        auth = CharacterAuthority.from_dict(d)
        assert auth.primary == AuthoritySource.MORAL
        assert auth.secondary == AuthoritySource.RITUAL


class TestAuthorityPresets:
    def test_doctor_authority(self):
        assert DOCTOR_AUTHORITY.primary == AuthoritySource.INSTITUTIONAL
        assert not DOCTOR_AUTHORITY.can_claim_without_demonstration

    def test_elder_authority(self):
        assert ELDER_AUTHORITY.primary == AuthoritySource.EXPERIENCE

    def test_fool_authority(self):
        assert FOOL_AUTHORITY.primary == AuthoritySource.CRAFT
        assert FOOL_AUTHORITY.can_claim_without_demonstration

    def test_prophet_authority(self):
        assert PROPHET_AUTHORITY.primary == AuthoritySource.MORAL


# =============================================================================
# CommitmentCeiling Tests
# =============================================================================


class TestCommitmentCeiling:
    def test_defaults(self):
        ceiling = CommitmentCeiling()
        assert ceiling.max_type == CommitmentType.BELIEF
        assert ceiling.max_intensity == 0.5

    def test_exceeds_type(self):
        ceiling = CommitmentCeiling(max_type=CommitmentType.BELIEF)
        assert not ceiling.exceeds(CommitmentType.ATTENTION, 0.5)
        assert not ceiling.exceeds(CommitmentType.BELIEF, 0.4)
        assert ceiling.exceeds(CommitmentType.ACTION, 0.5)
        assert ceiling.exceeds(CommitmentType.IDENTITY, 0.5)

    def test_exceeds_intensity(self):
        ceiling = CommitmentCeiling(max_type=CommitmentType.BELIEF, max_intensity=0.5)
        assert not ceiling.exceeds(CommitmentType.BELIEF, 0.4)
        assert not ceiling.exceeds(CommitmentType.BELIEF, 0.5)
        assert ceiling.exceeds(CommitmentType.BELIEF, 0.6)

    def test_to_dict_from_dict(self):
        ceiling = CommitmentCeiling(max_type=CommitmentType.ACTION, max_intensity=0.7)
        d = ceiling.to_dict()
        ceiling2 = CommitmentCeiling.from_dict(d)
        assert ceiling2.max_type == CommitmentType.ACTION
        assert ceiling2.max_intensity == 0.7


class TestCommitmentCeilingPresets:
    def test_shopkeeper_ceiling(self):
        assert SHOPKEEPER_CEILING.max_type == CommitmentType.BELIEF
        assert SHOPKEEPER_CEILING.max_intensity == 0.4

    def test_prophet_ceiling(self):
        assert PROPHET_CEILING.max_type == CommitmentType.IDENTITY

    def test_fool_ceiling(self):
        assert FOOL_CEILING.max_type == CommitmentType.ATTENTION


# =============================================================================
# NormativityPermission Tests
# =============================================================================


class TestNormativityPermission:
    def test_defaults(self):
        perm = NormativityPermission()
        assert perm.allowed is False
        assert perm.requires_foundation is True
        assert perm.authority_source is None

    def test_to_dict_from_dict(self):
        perm = NormativityPermission(
            allowed=True,
            requires_foundation=False,
            authority_source=AuthoritySource.MORAL,
        )
        d = perm.to_dict()
        perm2 = NormativityPermission.from_dict(d)
        assert perm2.allowed is True
        assert perm2.requires_foundation is False
        assert perm2.authority_source == AuthoritySource.MORAL


class TestNormativityPresets:
    def test_elder_normativity(self):
        assert ELDER_NORMATIVITY.allowed is True
        assert ELDER_NORMATIVITY.requires_foundation is True

    def test_prophet_normativity(self):
        assert PROPHET_NORMATIVITY.allowed is True
        assert PROPHET_NORMATIVITY.requires_foundation is False

    def test_no_normativity(self):
        assert NO_NORMATIVITY.allowed is False


# =============================================================================
# ConsistencyState Tests
# =============================================================================


class TestCharacterClaim:
    def test_to_dict_from_dict(self):
        claim = CharacterClaim(
            text="The sky is blue",
            topic="weather",
            certainty_expressed=0.8,
        )
        d = claim.to_dict()
        claim2 = CharacterClaim.from_dict(d)
        assert claim2.text == "The sky is blue"
        assert claim2.topic == "weather"
        assert claim2.certainty_expressed == 0.8


class TestCharacterCommitment:
    def test_to_dict_from_dict(self):
        commitment = CharacterCommitment(
            type="promise",
            content="I will help you",
        )
        d = commitment.to_dict()
        commitment2 = CharacterCommitment.from_dict(d)
        assert commitment2.type == "promise"
        assert commitment2.content == "I will help you"


class TestContradiction:
    def test_to_dict_from_dict(self):
        contradiction = Contradiction(
            claim_a="It's sunny",
            claim_b="It's raining",
            topic="weather",
        )
        d = contradiction.to_dict()
        contradiction2 = Contradiction.from_dict(d)
        assert contradiction2.claim_a == "It's sunny"
        assert contradiction2.claim_b == "It's raining"


class TestConsistencyState:
    def test_defaults(self):
        state = ConsistencyState()
        assert len(state.claims) == 0
        assert len(state.positions) == 0
        assert len(state.commitments) == 0

    def test_add_claim(self):
        state = ConsistencyState()
        claim = CharacterClaim(text="Hello", topic="greeting", certainty_expressed=0.5)
        result = state.add_claim(claim)
        assert result is None
        assert "greeting" in state.claims

    def test_add_claim_detects_contradiction(self):
        state = ConsistencyState()
        claim1 = CharacterClaim(text="I love it", topic="opinion", certainty_expressed=0.9)
        claim2 = CharacterClaim(text="I hate it", topic="opinion", certainty_expressed=0.2)

        state.add_claim(claim1)
        contradiction = state.add_claim(claim2)

        assert contradiction is not None
        assert len(state.get_unresolved_contradictions()) == 1

    def test_add_position(self):
        state = ConsistencyState()
        state.add_position("taxes", "pro")
        assert state.positions["taxes"] == "pro"

    def test_to_dict_from_dict(self):
        state = ConsistencyState()
        state.add_claim(CharacterClaim(text="Test", topic="test", certainty_expressed=0.5))
        state.add_position("issue", "stance")

        d = state.to_dict()
        state2 = ConsistencyState.from_dict(d)
        assert "test" in state2.claims
        assert state2.positions["issue"] == "stance"


# =============================================================================
# Character Governance Leak Detection Tests
# =============================================================================


class TestCharacterGovernanceLeakDetection:
    def test_patterns_compiled(self):
        assert len(CHARACTER_GOVERNANCE_LEAK_PATTERNS) > 0

    def test_detect_as_character(self):
        text = "As a character, I can't really do that."
        leaks = detect_character_governance_leak(text)
        assert len(leaks) > 0

    def test_detect_just_a(self):
        text = "I'm just a fictional person."
        leaks = detect_character_governance_leak(text)
        assert len(leaks) > 0

    def test_detect_my_author(self):
        text = "My author didn't write me that way."
        leaks = detect_character_governance_leak(text)
        assert len(leaks) > 0

    def test_detect_breaking_character(self):
        text = "I don't want to be breaking character here."
        leaks = detect_character_governance_leak(text)
        assert len(leaks) > 0

    def test_clean_text_no_leaks(self):
        text = "I'd need to run tests before I could say anything definitive."
        leaks = detect_character_governance_leak(text)
        assert len(leaks) == 0

    def test_has_governance_leak(self):
        assert has_character_governance_leak("As a character, I shouldn't say that.")
        assert not has_character_governance_leak("That's outside my area.")


# =============================================================================
# CharacterDefinition Tests
# =============================================================================


class TestCharacterDefinition:
    def test_defaults(self):
        char = CharacterDefinition(id="test", name="Test Character")
        assert char.id == "test"
        assert char.name == "Test Character"
        assert char.regime_affinity.primary == "neutral"
        assert char.certainty_ceiling == 0.7

    def test_to_dict(self):
        char = CharacterDefinition(
            id="test",
            name="Test",
            certainty_ceiling=0.5,
        )
        d = char.to_dict()
        assert d["id"] == "test"
        assert d["certainty_ceiling"] == 0.5

    def test_from_dict(self):
        d = {
            "id": "hero",
            "name": "Hero",
            "regime_affinity": {"primary": "drama"},
            "certainty_ceiling": 0.8,
        }
        char = CharacterDefinition.from_dict(d)
        assert char.id == "hero"
        assert char.regime_affinity.primary == "drama"
        assert char.certainty_ceiling == 0.8


# =============================================================================
# SceneContext Tests
# =============================================================================


class TestSceneContext:
    def test_defaults(self):
        scene = SceneContext()
        assert scene.regime_hint is None
        assert scene.stakes == 0.5
        assert len(scene.other_characters) == 0

    def test_to_dict_from_dict(self):
        scene = SceneContext(
            regime_hint="drama",
            stakes=0.8,
            other_characters=["Alice", "Bob"],
        )
        d = scene.to_dict()
        scene2 = SceneContext.from_dict(d)
        assert scene2.regime_hint == "drama"
        assert scene2.stakes == 0.8


# =============================================================================
# Regime Resolution Tests
# =============================================================================


class TestResolveRegime:
    def test_character_dominates_when_forbidden(self):
        char = CharacterDefinition(
            id="test",
            name="Test",
            regime_affinity=RegimeAffinity(
                primary="tragedy",
                forbidden=["comedy"],
            ),
        )
        scene = SceneContext(regime_hint="comedy")
        assert resolve_regime(char, scene) == "tragedy"

    def test_high_override_uses_character(self):
        char = CharacterDefinition(
            id="test",
            name="Test",
            regime_affinity=RegimeAffinity(
                primary="comedy",
                override_strength=0.8,
            ),
        )
        scene = SceneContext(regime_hint="drama")
        assert resolve_regime(char, scene) == "comedy"

    def test_low_override_uses_scene_if_secondary(self):
        char = CharacterDefinition(
            id="test",
            name="Test",
            regime_affinity=RegimeAffinity(
                primary="comedy",
                secondary="drama",
                override_strength=0.3,
            ),
        )
        scene = SceneContext(regime_hint="drama")
        assert resolve_regime(char, scene) == "drama"

    def test_neutral_scene_allowed(self):
        char = CharacterDefinition(
            id="test",
            name="Test",
            regime_affinity=RegimeAffinity(
                primary="comedy",
                override_strength=0.3,
            ),
        )
        scene = SceneContext(regime_hint="neutral")
        assert resolve_regime(char, scene) == "neutral"

    def test_no_scene_hint_uses_neutral(self):
        char = CharacterDefinition(
            id="test",
            name="Test",
            regime_affinity=RegimeAffinity(primary="comedy"),
        )
        scene = SceneContext()  # No hint
        # With override_strength 0.5, balanced case prefers character
        assert resolve_regime(char, scene) == "comedy"


# =============================================================================
# CharacterViolation Tests
# =============================================================================


class TestCharacterViolation:
    def test_all_types(self):
        for vtype in CharacterViolationType:
            violation = CharacterViolation(type=vtype, description="test")
            assert violation.type == vtype

    def test_to_dict(self):
        violation = CharacterViolation(
            type=CharacterViolationType.GOVERNANCE_LEAK,
            description="Leaked strings",
            severity=0.8,
        )
        d = violation.to_dict()
        assert d["type"] == "governance_leak"
        assert d["severity"] == 0.8


class TestPuppetTicketType:
    def test_all_types(self):
        assert len(PuppetTicketType) == 9


# =============================================================================
# PuppetModeController Tests
# =============================================================================


class TestPuppetModeConfig:
    def test_defaults(self):
        char = CharacterDefinition(id="test", name="Test")
        config = PuppetModeConfig(character=char)
        assert config.consistency_tracking is True
        assert config.strict_mode is False


class TestPuppetModeController:
    def test_init(self):
        char = CharacterDefinition(id="test", name="Test")
        config = PuppetModeConfig(character=char)
        controller = PuppetModeController(config)
        assert controller._character.id == "test"

    def test_check_clean_text(self):
        char = CharacterDefinition(id="test", name="Test")
        config = PuppetModeConfig(character=char)
        controller = PuppetModeController(config)

        result = controller.check_text("Hello, how can I help you?")
        assert result.in_character is True
        assert len(result.violations) == 0

    def test_check_governance_leak(self):
        char = CharacterDefinition(id="test", name="Test")
        config = PuppetModeConfig(character=char)
        controller = PuppetModeController(config)

        result = controller.check_text("As a character, I can't do that.")
        assert result.in_character is False
        assert result.frame_breaks > 0
        assert any(v.type == CharacterViolationType.GOVERNANCE_LEAK for v in result.violations)

    def test_check_certainty_ceiling(self):
        char = CharacterDefinition(
            id="humble",
            name="Humble Character",
            certainty_ceiling=0.4,
        )
        config = PuppetModeConfig(character=char)
        controller = PuppetModeController(config)

        result = controller.check_text("I am absolutely certain this is true.")
        assert any(v.type == CharacterViolationType.CERTAINTY_CEILING for v in result.violations)

    def test_check_normativity_violation(self):
        char = CharacterDefinition(
            id="observer",
            name="Observer",
            normativity=NO_NORMATIVITY,
        )
        config = PuppetModeConfig(character=char)
        controller = PuppetModeController(config)

        result = controller.check_text("You should do the right thing.")
        assert any(v.type == CharacterViolationType.NORMATIVITY for v in result.violations)

    def test_normativity_allowed(self):
        char = CharacterDefinition(
            id="elder",
            name="Elder",
            normativity=ELDER_NORMATIVITY,
        )
        config = PuppetModeConfig(character=char)
        controller = PuppetModeController(config)

        result = controller.check_text("You should do the right thing.")
        # Normativity is allowed for elder
        assert not any(v.type == CharacterViolationType.NORMATIVITY for v in result.violations)

    def test_get_effective_regime(self):
        char = CharacterDefinition(
            id="test",
            name="Test",
            regime_affinity=RegimeAffinity(primary="comedy"),
        )
        scene = SceneContext(regime_hint="drama")
        config = PuppetModeConfig(character=char, scene=scene)
        controller = PuppetModeController(config)

        regime = controller.get_effective_regime()
        assert regime in ["comedy", "drama"]

    def test_update_scene(self):
        char = CharacterDefinition(id="test", name="Test")
        config = PuppetModeConfig(character=char)
        controller = PuppetModeController(config)

        new_scene = SceneContext(regime_hint="tragedy", stakes=0.9)
        controller.update_scene(new_scene)
        assert controller._scene.regime_hint == "tragedy"


class TestPuppetModeResult:
    def test_to_dict(self):
        result = PuppetModeResult(
            text="Hello",
            character_id="test",
            effective_regime="comedy",
            in_character=True,
        )
        d = result.to_dict()
        assert d["text"] == "Hello"
        assert d["in_character"] is True


# =============================================================================
# Recursive Puppet Mode Tests
# =============================================================================


class TestRecursiveDepth:
    def test_values(self):
        assert RecursiveDepth.EMULATE.value == "emulate"
        assert RecursiveDepth.EXPOSE.value == "expose"


class TestRecursivePuppetConfig:
    def test_valid_config(self):
        config = RecursivePuppetConfig(
            target_voice="test_voice",
            depth=RecursiveDepth.EMULATE,
            diagnostic_only=True,
        )
        assert config.is_valid() is True

    def test_invalid_config(self):
        config = RecursivePuppetConfig(
            target_voice="test_voice",
            diagnostic_only=False,  # Not allowed
        )
        assert config.is_valid() is False


class TestValidateRecursivePuppet:
    def test_valid(self):
        config = RecursivePuppetConfig(target_voice="test", diagnostic_only=True)
        valid, reason = validate_recursive_puppet(config)
        assert valid is True

    def test_invalid_not_diagnostic(self):
        config = RecursivePuppetConfig(target_voice="test", diagnostic_only=False)
        valid, reason = validate_recursive_puppet(config)
        assert valid is False
        assert "diagnostic" in reason.lower()


# =============================================================================
# Preset Characters Tests
# =============================================================================


class TestPresetCharacters:
    def test_wise_elder(self):
        assert WISE_ELDER_CHARACTER.id == "wise_elder"
        assert WISE_ELDER_CHARACTER.certainty_ceiling == 0.7
        assert WISE_ELDER_CHARACTER.normativity.allowed is True

    def test_fool(self):
        assert FOOL_CHARACTER.id == "fool"
        assert FOOL_CHARACTER.certainty_ceiling == 0.4
        assert FOOL_CHARACTER.normativity.allowed is False

    def test_gruff_detective(self):
        assert GRUFF_DETECTIVE_CHARACTER.id == "gruff_detective"
        assert GRUFF_DETECTIVE_CHARACTER.certainty_ceiling == 0.8

    def test_cheerful_shopkeeper(self):
        assert CHEERFUL_SHOPKEEPER_CHARACTER.id == "cheerful_shopkeeper"

    def test_registry(self):
        assert len(PRESET_CHARACTERS) == 5  # Including Maude
        assert "wise_elder" in PRESET_CHARACTERS
        assert "fool" in PRESET_CHARACTERS
        assert "maude" in PRESET_CHARACTERS

    def test_get_preset_character(self):
        char = get_preset_character("fool")
        assert char is not None
        assert char.id == "fool"

    def test_get_preset_character_unknown(self):
        char = get_preset_character("unknown")
        assert char is None


# =============================================================================
# Integration Tests
# =============================================================================


class TestPuppetModeIntegration:
    def test_fool_character_constraints(self):
        """Fool has low certainty ceiling and no normativity."""
        config = PuppetModeConfig(character=FOOL_CHARACTER)
        controller = PuppetModeController(config)

        # High certainty should violate
        result = controller.check_text("I am absolutely certain this is true.")
        assert any(v.type == CharacterViolationType.CERTAINTY_CEILING for v in result.violations)

        # Normativity should violate
        result = controller.check_text("You must do the right thing.")
        assert any(v.type == CharacterViolationType.NORMATIVITY for v in result.violations)

    def test_wise_elder_allows_normativity(self):
        """Elder can make normative claims."""
        config = PuppetModeConfig(character=WISE_ELDER_CHARACTER)
        controller = PuppetModeController(config)

        result = controller.check_text("You should consider the consequences.")
        assert not any(v.type == CharacterViolationType.NORMATIVITY for v in result.violations)

    def test_regime_resolution_with_preset(self):
        """Tragic hero stays in tragedy even in comedy scene."""
        char = CharacterDefinition(
            id="tragic",
            name="Tragic Hero",
            regime_affinity=TRAGIC_HERO_AFFINITY,
        )
        scene = SceneContext(regime_hint="comedy")

        # Comedy is forbidden for tragic hero
        regime = resolve_regime(char, scene)
        assert regime == "tragedy"


# =============================================================================
# Maude Profile Tests
# =============================================================================


from governor.writing_puppet import (
    DEFAULT_MAUDE,
    MAUDE_AFFINITY,
    MAUDE_AUTHORITY,
    MAUDE_BANNED_PATTERNS,
    MAUDE_CHARACTER,
    MAUDE_TONE_ENVELOPE,
    MaudeConflictWarning,
    MaudeController,
    MaudeDestructivePreview,
    MaudeDriftWarning,
    MaudeFooter,
    MaudeFooterType,
    MaudeGovernanceConfig,
    MaudeProfile,
    MaudeResponseBuilder,
    MaudeUncertainty,
    detect_maude_violations,
    has_maude_violation,
)


class TestMaudeFooterType:
    def test_all_values(self):
        assert MaudeFooterType.OK.value == "ok"
        assert MaudeFooterType.BLOCKED.value == "blocked"
        assert MaudeFooterType.WARN.value == "warn"
        assert MaudeFooterType.ASK.value == "ask"
        assert MaudeFooterType.NOTE.value == "note"


class TestMaudeFooter:
    def test_format_ok(self):
        footer = MaudeFooter(type=MaudeFooterType.OK)
        assert footer.format() == "Maude: OK"

    def test_format_blocked_with_fix(self):
        footer = MaudeFooter(
            type=MaudeFooterType.BLOCKED,
            reason="missing evidence (citation needed)",
            fix="provide source",
        )
        result = footer.format()
        assert "Maude: BLOCKED" in result
        assert "missing evidence" in result
        assert "To proceed: provide source." in result

    def test_format_blocked_without_fix(self):
        footer = MaudeFooter(
            type=MaudeFooterType.BLOCKED,
            reason="invalid config",
        )
        result = footer.format()
        assert "Maude: BLOCKED" in result
        assert "To proceed:" not in result

    def test_format_warn(self):
        footer = MaudeFooter(
            type=MaudeFooterType.WARN,
            reason="conflicts with prior constraint",
            fix="reconcile",
        )
        result = footer.format()
        assert "Maude: WARN" in result
        assert "Recommendation: reconcile." in result

    def test_format_ask(self):
        footer = MaudeFooter(
            type=MaudeFooterType.ASK,
            reason="confirm destructive action?",
        )
        result = footer.format()
        assert "Maude: ASK" in result
        assert "confirm" in result

    def test_format_note(self):
        footer = MaudeFooter(
            type=MaudeFooterType.NOTE,
            reason="this approach works but see alternatives",
        )
        result = footer.format()
        assert "Maude: NOTE" in result


class TestMaudeToneEnvelope:
    def test_values(self):
        # From maude.md spec
        assert MAUDE_TONE_ENVELOPE.formality == (0.5, 0.7)
        assert MAUDE_TONE_ENVELOPE.temperature == (0.2, 0.4)
        assert MAUDE_TONE_ENVELOPE.density == (0.6, 0.8)
        assert MAUDE_TONE_ENVELOPE.velocity == (0.4, 0.6)
        assert MAUDE_TONE_ENVELOPE.distance == (0.5, 0.7)
        assert MAUDE_TONE_ENVELOPE.certainty == (0.5, 0.8)


class TestMaudeBannedPatterns:
    def test_patterns_compiled(self):
        assert len(MAUDE_BANNED_PATTERNS) > 0

    def test_detects_great_question(self):
        assert has_maude_violation("Great question!")

    def test_detects_happy_to_help(self):
        assert has_maude_violation("I'd be happy to help with that!")

    def test_detects_absolutely(self):
        assert has_maude_violation("That is absolutely correct.")

    def test_detects_let_me(self):
        assert has_maude_violation("Let me just check that for you.")

    def test_detects_performed_uncertainty(self):
        assert has_maude_violation("I'm not sure, but I think maybe it's X.")

    def test_detects_excessive_hedging(self):
        assert has_maude_violation("I could be wrong, but this looks off.")

    def test_detects_motivation_speak(self):
        assert has_maude_violation("You've got this!")
        assert has_maude_violation("Don't worry, it'll be fine.")

    def test_clean_text_passes(self):
        # Maude's actual voice - direct, no filler
        clean_texts = [
            "The config is invalid — missing required field.",
            "Latency estimate: 30ms. Confidence: moderate.",
            "This conflicts with constraint #47.",
        ]
        for text in clean_texts:
            assert not has_maude_violation(text), f"'{text}' should pass"


class TestDetectMaudeViolations:
    def test_returns_pattern(self):
        violations = detect_maude_violations("Great question! Let me help.")
        assert len(violations) >= 2

    def test_returns_empty_for_clean(self):
        violations = detect_maude_violations("Check failed. Fix: add timeout.")
        assert len(violations) == 0


class TestMaudeGovernanceConfig:
    def test_defaults(self):
        config = MaudeGovernanceConfig()
        assert config.always_surface_status is True
        assert config.status_footer is True
        assert config.require_confirm_for_destructive is True
        assert config.require_preview_for_bulk_ops is True
        assert config.cite_decisions_when_conflicting is True
        assert config.never_claim_execution_without_record is True


class TestMaudeProfile:
    def test_defaults(self):
        profile = MaudeProfile()
        assert profile.id == "maude_default"
        assert profile.display_name == "Maude"
        assert profile.tagline == "Proposal is cheap. Commitment isn't."
        assert profile.register == "dry"
        assert profile.default_regime == "nonfiction"

    def test_domain_affinities(self):
        profile = MaudeProfile()
        assert "debugging" in profile.domain_affinities
        assert "ops" in profile.domain_affinities

    def test_domain_deflections(self):
        profile = MaudeProfile()
        assert "therapy" in profile.domain_deflections
        assert "motivation" in profile.domain_deflections

    def test_to_dict(self):
        profile = MaudeProfile()
        d = profile.to_dict()
        assert d["id"] == "maude_default"
        assert d["tagline"] == "Proposal is cheap. Commitment isn't."
        assert d["tone"]["register"] == "dry"

    def test_from_dict(self):
        d = {
            "id": "custom_maude",
            "display_name": "Custom Maude",
            "tagline": "Custom tagline",
            "tone": {"register": "formal"},
            "style_bans": ["emoji"],
        }
        profile = MaudeProfile.from_dict(d)
        assert profile.id == "custom_maude"
        assert profile.tagline == "Custom tagline"


class TestMaudeAffinity:
    def test_primary_nonfiction(self):
        assert MAUDE_AFFINITY.primary == "nonfiction"

    def test_forbidden_regimes(self):
        assert "comedy" in MAUDE_AFFINITY.forbidden
        assert "advocacy" in MAUDE_AFFINITY.forbidden
        assert "marketing" in MAUDE_AFFINITY.forbidden


class TestMaudeAuthority:
    def test_experience_based(self):
        assert MAUDE_AUTHORITY.primary == AuthoritySource.EXPERIENCE
        assert MAUDE_AUTHORITY.secondary == AuthoritySource.CRAFT

    def test_must_demonstrate(self):
        assert MAUDE_AUTHORITY.can_claim_without_demonstration is False


class TestMaudeCharacter:
    def test_in_preset_registry(self):
        assert "maude" in PRESET_CHARACTERS

    def test_character_properties(self):
        assert MAUDE_CHARACTER.id == "maude"
        assert MAUDE_CHARACTER.name == "Maude"
        assert MAUDE_CHARACTER.certainty_ceiling == 0.8
        assert MAUDE_CHARACTER.normativity.allowed is True

    def test_tone_envelope(self):
        assert MAUDE_CHARACTER.tone_envelope == MAUDE_TONE_ENVELOPE


class TestMaudeUncertainty:
    def test_format(self):
        uncertainty = MaudeUncertainty(
            estimate="2-4 hours",
            confidence="low",
            missing=["row count", "index size"],
        )
        result = uncertainty.format()
        assert "Estimate: 2-4 hours." in result
        assert "Confidence: low." in result
        assert "row count" in result

    def test_format_no_missing(self):
        uncertainty = MaudeUncertainty(
            estimate="30ms",
            confidence="high",
            missing=[],
        )
        result = uncertainty.format()
        assert "Missing:" not in result


class TestMaudeDriftWarning:
    def test_format(self):
        warning = MaudeDriftWarning(
            threads=["Redis timeout config", "Log rotation policy", "Deployment"]
        )
        result = warning.format()
        assert "3 threads" in result
        assert "1. Redis" in result
        assert "Pick one" in result


class TestMaudeDestructivePreview:
    def test_format(self):
        preview = MaudeDestructivePreview(
            actions=[
                "Delete 3 files in /var/log/old/",
                "Modify permissions on /etc/app/",
            ],
            backup_path="/tmp/maude-backup/",
        )
        result = preview.format()
        assert "This would:" in result
        assert "Delete 3 files" in result
        assert "Backup will be created" in result

    def test_format_no_backup(self):
        preview = MaudeDestructivePreview(
            actions=["Remove container"],
        )
        result = preview.format()
        assert "Backup" not in result


class TestMaudeConflictWarning:
    def test_format(self):
        warning = MaudeConflictWarning(
            constraint_id="47",
            constraint_type="HARD",
            constraint_date="2026-01-15",
            constraint_summary="Stick to Postgres for all new services",
            options=[
                "Override #47 with rationale",
                "Revise #47 to allow exceptions",
                "Use Postgres instead",
            ],
        )
        result = warning.format()
        assert "conflicts with your earlier constraint" in result
        assert "#47" in result
        assert "HARD" in result
        assert "Options:" in result


class TestMaudeResponseBuilder:
    def test_build_simple(self):
        builder = MaudeResponseBuilder()
        result = builder.add_line("30 seconds in redis-py.").ok().build()
        assert "30 seconds" in result
        assert "Maude: OK" in result

    def test_build_with_notes(self):
        builder = MaudeResponseBuilder()
        result = (
            builder
            .add_line("Config is invalid.")
            .add_note("Default was 60s in v2.x")
            .add_note("See migration guide")
            .blocked("invalid config", "add timeout field")
            .build()
        )
        assert "Notes:" in result
        assert "Default was 60s" in result
        assert "Maude: BLOCKED" in result

    def test_filters_banned_patterns(self):
        builder = MaudeResponseBuilder()
        # This line has a banned pattern - should not appear
        result = builder.add_line("Great question! Here's the answer.").ok().build()
        # Maude wouldn't say "Great question!"
        assert "Great question" not in result

    def test_warn_footer(self):
        builder = MaudeResponseBuilder()
        result = (
            builder
            .add_line("This conflicts with prior constraint.")
            .warn("conflicts with #47", "reconcile")
            .build()
        )
        assert "Maude: WARN" in result

    def test_ask_footer(self):
        builder = MaudeResponseBuilder()
        result = builder.ask("confirm deletion?").build()
        assert "Maude: ASK" in result


class TestMaudeController:
    def test_init_default_profile(self):
        controller = MaudeController()
        assert controller.profile.id == "maude_default"

    def test_check_clean_text(self):
        controller = MaudeController()
        result = controller.check_text("The config is invalid. Fix: add timeout.")
        assert result.in_character is True
        assert len([v for v in result.violations if v.severity > 0.5]) == 0

    def test_check_detects_banned_patterns(self):
        controller = MaudeController()
        result = controller.check_text("Great question! I'd love to help!")
        violations = [v for v in result.violations if "banned pattern" in v.description]
        assert len(violations) > 0

    def test_check_detects_governance_leak(self):
        controller = MaudeController()
        result = controller.check_text("As a character, I can't do that.")
        assert result.in_character is False

    def test_create_response(self):
        controller = MaudeController()
        builder = controller.create_response()
        assert isinstance(builder, MaudeResponseBuilder)

    def test_format_uncertainty(self):
        controller = MaudeController()
        result = controller.format_uncertainty(
            estimate="30ms",
            confidence="moderate",
            missing=["benchmark data"],
        )
        assert "Estimate: 30ms" in result
        assert "Confidence: moderate" in result

    def test_format_drift_warning(self):
        controller = MaudeController()
        result = controller.format_drift_warning(["A", "B", "C"])
        assert "3 threads" in result

    def test_format_destructive_preview(self):
        controller = MaudeController()
        result = controller.format_destructive_preview(
            actions=["Delete file"],
            backup_path="/tmp/backup",
        )
        assert "Delete file" in result

    def test_format_conflict_warning(self):
        controller = MaudeController()
        result = controller.format_conflict_warning(
            constraint_id="1",
            constraint_type="HARD",
            constraint_date="2026-01-01",
            constraint_summary="Use Postgres",
            options=["Override", "Revise"],
        )
        assert "conflicts" in result

    def test_should_deflect(self):
        controller = MaudeController()
        assert controller.should_deflect("therapy") is True
        assert controller.should_deflect("motivation") is True
        assert controller.should_deflect("debugging") is False

    def test_has_affinity(self):
        controller = MaudeController()
        assert controller.has_affinity("debugging") is True
        assert controller.has_affinity("ops") is True
        assert controller.has_affinity("therapy") is False


class TestDefaultMaude:
    def test_exists(self):
        assert DEFAULT_MAUDE is not None
        assert isinstance(DEFAULT_MAUDE, MaudeController)

    def test_profile(self):
        assert DEFAULT_MAUDE.profile.tagline == "Proposal is cheap. Commitment isn't."


class TestMaudeIntegration:
    """Integration tests for Maude as a puppet profile."""

    def test_maude_in_puppet_controller(self):
        """Maude character can be used in PuppetModeController."""
        config = PuppetModeConfig(character=MAUDE_CHARACTER)
        controller = PuppetModeController(config)

        result = controller.check_text("Check failed. Missing: timeout config.")
        assert result.in_character is True

    def test_maude_regime_resolution(self):
        """Maude stays in nonfiction/instruction regimes."""
        scene = SceneContext(regime_hint="comedy")
        regime = resolve_regime(MAUDE_CHARACTER, scene)
        # Comedy is forbidden for Maude
        assert regime == "nonfiction"

    def test_maude_certainty_ceiling(self):
        """Maude has high certainty ceiling (0.8) - can be confident."""
        config = PuppetModeConfig(character=MAUDE_CHARACTER)
        controller = PuppetModeController(config)

        # High certainty is OK for Maude (ceiling is 0.8)
        result = controller.check_text("I am certain this is correct.")
        certainty_violations = [
            v for v in result.violations
            if v.type == CharacterViolationType.CERTAINTY_CEILING
        ]
        assert len(certainty_violations) == 0

    def test_maude_can_make_normative_claims(self):
        """Maude can make normative claims about process."""
        config = PuppetModeConfig(character=MAUDE_CHARACTER)
        controller = PuppetModeController(config)

        result = controller.check_text("You should run tests before deploying.")
        normativity_violations = [
            v for v in result.violations
            if v.type == CharacterViolationType.NORMATIVITY
        ]
        assert len(normativity_violations) == 0
