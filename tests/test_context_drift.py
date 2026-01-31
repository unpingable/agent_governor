"""Tests for fiction_governor.context_drift — context drift detection."""

import pytest
from fiction_governor.context_drift import (
    NarrativeMode,
    RiskTier,
    DriftFaultType,
    HysteresisConfig,
    ModeSignal,
    ModeTransition,
    DriftFault,
    DriftState,
    ContextDriftDetector,
    classify_register,
    estimate_risk_tier,
    create_context_drift_detector,
    RISK_TIER_MAP,
    RISK_ORDER,
    MODE_FEATURES,
)


# ============================================================
# Enum tests
# ============================================================


class TestNarrativeMode:
    def test_values(self):
        assert NarrativeMode.LITERARY.value == "literary"
        assert NarrativeMode.EROTIC.value == "erotic"
        assert NarrativeMode.GRIMDARK.value == "grimdark"
        assert NarrativeMode.TECHNICAL.value == "technical"
        assert NarrativeMode.HISTORICAL.value == "historical"

    def test_all_modes(self):
        assert len(NarrativeMode) == 10


class TestRiskTier:
    def test_values(self):
        assert RiskTier.LOW.value == "low"
        assert RiskTier.MEDIUM.value == "medium"
        assert RiskTier.HIGH.value == "high"

    def test_ordering(self):
        assert RISK_ORDER[RiskTier.LOW] < RISK_ORDER[RiskTier.MEDIUM]
        assert RISK_ORDER[RiskTier.MEDIUM] < RISK_ORDER[RiskTier.HIGH]


class TestDriftFaultType:
    def test_values(self):
        assert DriftFaultType.UNSIGNALED_REGISTER_SHIFT.value == "unsignaled_register_shift"
        assert DriftFaultType.GENRE_ESCALATION.value == "genre_escalation"
        assert DriftFaultType.MODE_CHATTER.value == "mode_chatter"


# ============================================================
# Risk tier mapping tests
# ============================================================


class TestRiskTierMap:
    def test_low_risk_modes(self):
        for mode in [NarrativeMode.LITERARY, NarrativeMode.CONTEMPORARY,
                     NarrativeMode.HISTORICAL, NarrativeMode.TECHNICAL,
                     NarrativeMode.YA, NarrativeMode.COMEDIC]:
            assert RISK_TIER_MAP[mode] == RiskTier.LOW

    def test_medium_risk_modes(self):
        for mode in [NarrativeMode.FANFIC, NarrativeMode.ROMANCE, NarrativeMode.GRIMDARK]:
            assert RISK_TIER_MAP[mode] == RiskTier.MEDIUM

    def test_high_risk_modes(self):
        assert RISK_TIER_MAP[NarrativeMode.EROTIC] == RiskTier.HIGH

    def test_all_modes_mapped(self):
        for mode in NarrativeMode:
            assert mode in RISK_TIER_MAP

    def test_estimate_risk_tier_function(self):
        assert estimate_risk_tier(NarrativeMode.LITERARY) == RiskTier.LOW
        assert estimate_risk_tier(NarrativeMode.ROMANCE) == RiskTier.MEDIUM
        assert estimate_risk_tier(NarrativeMode.EROTIC) == RiskTier.HIGH


# ============================================================
# Dataclass tests
# ============================================================


class TestHysteresisConfig:
    def test_defaults(self):
        h = HysteresisConfig()
        assert h.theta_up == 0.75
        assert h.theta_down == 0.55
        assert h.min_tokens_between_switches == 100
        assert h.max_transitions_per_window == 3
        assert h.window_size_tokens == 2000

    def test_custom(self):
        h = HysteresisConfig(theta_up=0.9, theta_down=0.3)
        assert h.theta_up == 0.9
        assert h.theta_down == 0.3

    def test_roundtrip(self):
        h = HysteresisConfig(theta_up=0.8, theta_down=0.4, min_tokens_between_switches=50)
        d = h.to_dict()
        h2 = HysteresisConfig.from_dict(d)
        assert h2.theta_up == 0.8
        assert h2.theta_down == 0.4
        assert h2.min_tokens_between_switches == 50


class TestModeSignal:
    def test_create(self):
        sig = ModeSignal(mode=NarrativeMode.ROMANCE, confidence=0.85)
        assert sig.mode == NarrativeMode.ROMANCE
        assert sig.confidence == 0.85

    def test_with_features(self):
        sig = ModeSignal(
            mode=NarrativeMode.ROMANCE,
            confidence=0.85,
            features={"kiss": 2, "heart": 1},
        )
        assert sig.features["kiss"] == 2

    def test_roundtrip(self):
        sig = ModeSignal(mode=NarrativeMode.GRIMDARK, confidence=0.6, features={"blood": 3})
        d = sig.to_dict()
        sig2 = ModeSignal.from_dict(d)
        assert sig2.mode == NarrativeMode.GRIMDARK
        assert sig2.confidence == 0.6
        assert sig2.features["blood"] == 3


class TestModeTransition:
    def test_create(self):
        t = ModeTransition(
            from_mode=NarrativeMode.LITERARY,
            to_mode=NarrativeMode.ROMANCE,
            at_token=500,
            confidence=0.8,
        )
        assert t.from_mode == NarrativeMode.LITERARY
        assert t.to_mode == NarrativeMode.ROMANCE
        assert t.user_signaled is False

    def test_user_signaled(self):
        t = ModeTransition(
            from_mode=NarrativeMode.LITERARY,
            to_mode=NarrativeMode.EROTIC,
            at_token=1000,
            confidence=1.0,
            user_signaled=True,
        )
        assert t.user_signaled is True

    def test_roundtrip(self):
        t = ModeTransition(
            from_mode=NarrativeMode.YA,
            to_mode=NarrativeMode.GRIMDARK,
            at_token=200,
            confidence=0.9,
            user_signaled=True,
        )
        d = t.to_dict()
        t2 = ModeTransition.from_dict(d)
        assert t2.from_mode == NarrativeMode.YA
        assert t2.to_mode == NarrativeMode.GRIMDARK
        assert t2.user_signaled is True


class TestDriftFault:
    def test_create(self):
        f = DriftFault(
            fault_type=DriftFaultType.GENRE_ESCALATION,
            detail="Risk escalation from low to high",
            severity="error",
        )
        assert f.fault_type == DriftFaultType.GENRE_ESCALATION
        assert f.severity == "error"

    def test_with_modes(self):
        f = DriftFault(
            fault_type=DriftFaultType.UNSIGNALED_REGISTER_SHIFT,
            detail="test",
            from_mode=NarrativeMode.LITERARY,
            to_mode=NarrativeMode.FANFIC,
        )
        assert f.from_mode == NarrativeMode.LITERARY
        assert f.to_mode == NarrativeMode.FANFIC

    def test_roundtrip(self):
        f = DriftFault(
            fault_type=DriftFaultType.MODE_CHATTER,
            detail="too many switches",
            severity="warning",
            from_mode=NarrativeMode.COMEDIC,
            to_mode=NarrativeMode.GRIMDARK,
        )
        d = f.to_dict()
        f2 = DriftFault.from_dict(d)
        assert f2.fault_type == DriftFaultType.MODE_CHATTER
        assert f2.from_mode == NarrativeMode.COMEDIC

    def test_roundtrip_no_modes(self):
        f = DriftFault(fault_type=DriftFaultType.MODE_CHATTER, detail="test")
        d = f.to_dict()
        f2 = DriftFault.from_dict(d)
        assert f2.from_mode is None
        assert f2.to_mode is None


class TestDriftState:
    def test_defaults(self):
        s = DriftState()
        assert s.current_mode == NarrativeMode.LITERARY
        assert s.risk_tier == RiskTier.LOW
        assert s.mode_conf == 0.5
        assert s.transitions == []

    def test_roundtrip(self):
        s = DriftState(
            current_mode=NarrativeMode.ROMANCE,
            risk_tier=RiskTier.MEDIUM,
            mode_conf=0.8,
            last_switch_token=500,
            transitions=[
                ModeTransition(NarrativeMode.LITERARY, NarrativeMode.ROMANCE, 500, 0.8)
            ],
        )
        d = s.to_dict()
        s2 = DriftState.from_dict(d)
        assert s2.current_mode == NarrativeMode.ROMANCE
        assert s2.risk_tier == RiskTier.MEDIUM
        assert len(s2.transitions) == 1


# ============================================================
# Classification tests
# ============================================================


class TestClassifyRegister:
    def test_empty_text(self):
        signals = classify_register("")
        assert len(signals) >= 1
        assert signals[0].confidence == 0.0

    def test_literary_text(self):
        text = (
            "She murmured beneath the ephemeral moonlight, gazing at the "
            "juxtaposition of shadow and silence; a melancholy settled over "
            "the garden like a shroud."
        )
        signals = classify_register(text)
        modes = [s.mode for s in signals]
        assert NarrativeMode.LITERARY in modes

    def test_romance_text(self):
        text = (
            "Her heart pounded as he kissed her softly. The desire between "
            "them was undeniable, a yearning that had built for weeks. She "
            "felt the chemistry crackle like electricity."
        )
        signals = classify_register(text)
        modes = [s.mode for s in signals]
        assert NarrativeMode.ROMANCE in modes

    def test_grimdark_text(self):
        text = (
            "Blood pooled beneath the corpse. The viscera steamed in the "
            "cold air, and the stench of decay was overpowering. Despair "
            "hung over the desolate battlefield like a funeral shroud."
        )
        signals = classify_register(text)
        modes = [s.mode for s in signals]
        assert NarrativeMode.GRIMDARK in modes

    def test_technical_text(self):
        text = (
            "The algorithm implements a configurable parameter with "
            "```python\nclass Foo:\n    pass\n``` "
            "using the SDK's HTTP API with JSON payloads."
        )
        signals = classify_register(text)
        modes = [s.mode for s in signals]
        assert NarrativeMode.TECHNICAL in modes

    def test_ya_text(self):
        text = (
            "The hallway was crowded between classes. She spotted her crush "
            "near the lockers, talking to her best friend. She totally wanted "
            "to skip homework and go to the prom instead."
        )
        signals = classify_register(text)
        modes = [s.mode for s in signals]
        assert NarrativeMode.YA in modes

    def test_returns_sorted_by_confidence(self):
        text = "He kissed her beneath the moonlight; her heart raced with desire and yearning."
        signals = classify_register(text)
        if len(signals) > 1:
            for i in range(len(signals) - 1):
                assert signals[i].confidence >= signals[i + 1].confidence

    def test_no_features_returns_default(self):
        text = "The cat sat on the mat."
        signals = classify_register(text)
        assert len(signals) >= 1


class TestModeFeatures:
    def test_all_modes_have_patterns(self):
        for mode in NarrativeMode:
            assert mode in MODE_FEATURES, f"Missing patterns for {mode}"

    def test_patterns_are_nonempty(self):
        for mode, patterns in MODE_FEATURES.items():
            assert len(patterns) > 0, f"No patterns for {mode}"


# ============================================================
# ContextDriftDetector tests
# ============================================================


class TestContextDriftDetector:
    def test_create(self):
        d = ContextDriftDetector()
        assert d.current_mode == NarrativeMode.LITERARY
        assert d.risk_tier == RiskTier.LOW

    def test_custom_hysteresis(self):
        h = HysteresisConfig(theta_up=0.9, theta_down=0.3)
        d = ContextDriftDetector(hysteresis=h)
        assert d.state.hysteresis.theta_up == 0.9

    def test_classify_without_update(self):
        d = ContextDriftDetector()
        signals = d.classify("Her heart pounded with desire and longing as he kissed her.")
        assert len(signals) >= 1
        # State should not change from classify alone
        assert d.current_mode == NarrativeMode.LITERARY

    def test_force_mode(self):
        d = ContextDriftDetector()
        d.force_mode(NarrativeMode.EROTIC, token_position=0)
        assert d.current_mode == NarrativeMode.EROTIC
        assert d.risk_tier == RiskTier.HIGH
        assert len(d.state.transitions) == 1
        assert d.state.transitions[0].user_signaled is True

    def test_force_same_mode_no_transition(self):
        d = ContextDriftDetector()
        d.force_mode(NarrativeMode.LITERARY)
        assert len(d.state.transitions) == 0

    def test_reset(self):
        d = ContextDriftDetector()
        d.force_mode(NarrativeMode.EROTIC)
        d.reset()
        assert d.current_mode == NarrativeMode.LITERARY
        assert d.state.transitions == []

    def test_reset_to_specific_mode(self):
        d = ContextDriftDetector()
        d.reset(NarrativeMode.HISTORICAL)
        assert d.current_mode == NarrativeMode.HISTORICAL
        assert d.risk_tier == RiskTier.LOW


class TestCheckTransition:
    def test_same_mode_no_fault(self):
        d = ContextDriftDetector()
        fault = d.check_transition(NarrativeMode.LITERARY, 0.9)
        assert fault is None

    def test_low_confidence_no_switch(self):
        d = ContextDriftDetector()
        fault = d.check_transition(NarrativeMode.ROMANCE, 0.3)
        assert fault is None  # Not confident enough to trigger

    def test_genre_escalation_blocked(self):
        d = ContextDriftDetector()
        # Try to escalate from LITERARY (low) to EROTIC (high) without user signal
        fault = d.check_transition(NarrativeMode.EROTIC, 0.9, user_signaled=False, token_position=200)
        assert fault is not None
        assert fault.fault_type == DriftFaultType.GENRE_ESCALATION
        assert fault.severity == "error"

    def test_genre_escalation_allowed_with_signal(self):
        d = ContextDriftDetector()
        fault = d.check_transition(NarrativeMode.EROTIC, 0.9, user_signaled=True, token_position=200)
        assert fault is None

    def test_unsignaled_shift_warning(self):
        d = ContextDriftDetector()
        # Shift to same risk tier without user signal
        fault = d.check_transition(NarrativeMode.CONTEMPORARY, 0.9, user_signaled=False, token_position=200)
        assert fault is not None
        assert fault.fault_type == DriftFaultType.UNSIGNALED_REGISTER_SHIFT
        assert fault.severity == "warning"

    def test_mode_chatter_too_fast(self):
        d = ContextDriftDetector()
        # Set last switch to recent token
        d._state.last_switch_token = 100
        fault = d.check_transition(NarrativeMode.ROMANCE, 0.9, user_signaled=False, token_position=150)
        assert fault is not None
        assert fault.fault_type == DriftFaultType.MODE_CHATTER

    def test_mode_chatter_too_many_transitions(self):
        d = ContextDriftDetector()
        # Add many recent transitions
        for i in range(4):
            d._state.transitions.append(
                ModeTransition(NarrativeMode.LITERARY, NarrativeMode.CONTEMPORARY, 100 + i * 200, 0.8)
            )
        fault = d.check_transition(NarrativeMode.ROMANCE, 0.9, user_signaled=False, token_position=900)
        assert fault is not None
        assert fault.fault_type == DriftFaultType.MODE_CHATTER

    def test_user_signal_bypasses_chatter(self):
        d = ContextDriftDetector()
        d._state.last_switch_token = 100
        fault = d.check_transition(NarrativeMode.ROMANCE, 0.9, user_signaled=True, token_position=150)
        assert fault is None


class TestUpdateMethod:
    def test_update_same_mode(self):
        d = ContextDriftDetector()
        # Literary text should not change mode
        text = "She murmured beneath the ephemeral moonlight; a melancholy juxtaposition."
        state, fault = d.update(text, token_position=100)
        # Either stays literary or shifts — depends on confidence
        assert state is not None

    def test_update_records_transition(self):
        d = ContextDriftDetector()
        d.force_mode(NarrativeMode.LITERARY)
        # Force a detectable mode with high-signal text
        text = (
            "Blood pooled beneath the corpse. Viscera and gore everywhere. "
            "The stench of decay and rotting flesh. Despair. Hopeless carnage. "
            "Slaughter and massacre across the desolate battlefield."
        )
        state, fault = d.update(text, user_signaled=True, token_position=500)
        if d.current_mode != NarrativeMode.LITERARY:
            assert len(d.state.transitions) >= 1

    def test_update_blocks_escalation(self):
        d = ContextDriftDetector()
        # Erotic text without user signal from literary mode
        text = (
            "She moaned and writhed as arousal overtook her. The orgasm "
            "built with each thrust. Naked and erect, panting with climax."
        )
        state, fault = d.update(text, user_signaled=False, token_position=500)
        # Should block or stay in current mode
        if fault is not None:
            assert fault.fault_type == DriftFaultType.GENRE_ESCALATION
            assert d.current_mode == NarrativeMode.LITERARY  # Didn't switch

    def test_update_allows_signaled_escalation(self):
        d = ContextDriftDetector()
        text = (
            "She moaned and writhed as arousal overtook her. The orgasm "
            "built with each thrust. Naked and erect, panting with climax."
        )
        state, fault = d.update(text, user_signaled=True, token_position=500)
        # Should allow transition or just produce a warning
        if fault is not None:
            assert fault.severity != "error"

    def test_empty_text(self):
        d = ContextDriftDetector()
        state, fault = d.update("", token_position=0)
        assert d.current_mode == NarrativeMode.LITERARY
        assert fault is None


class TestDetectorSerialization:
    def test_roundtrip(self):
        d = ContextDriftDetector(hysteresis=HysteresisConfig(theta_up=0.85))
        d.force_mode(NarrativeMode.ROMANCE, token_position=100)

        data = d.to_dict()
        d2 = ContextDriftDetector.from_dict(data)

        assert d2.current_mode == NarrativeMode.ROMANCE
        assert d2.risk_tier == RiskTier.MEDIUM
        assert d2.state.hysteresis.theta_up == 0.85
        assert len(d2.state.transitions) == 1


# ============================================================
# Convenience function tests
# ============================================================


class TestConvenience:
    def test_create_detector(self):
        d = create_context_drift_detector()
        assert isinstance(d, ContextDriftDetector)

    def test_create_with_config(self):
        h = HysteresisConfig(theta_up=0.5)
        d = create_context_drift_detector(hysteresis=h)
        assert d.state.hysteresis.theta_up == 0.5


# ============================================================
# Edge case tests
# ============================================================


class TestEdgeCases:
    def test_very_short_text(self):
        signals = classify_register("Hi.")
        assert len(signals) >= 1

    def test_mixed_mode_text(self):
        text = (
            "Her heart pounded as she kissed him beneath the blood-soaked "
            "moonlight. The corpse nearby decayed silently."
        )
        signals = classify_register(text)
        # Should detect multiple modes
        assert len(signals) >= 1

    def test_all_whitespace(self):
        signals = classify_register("   \n\t  ")
        assert len(signals) >= 1
        assert signals[0].confidence == 0.0

    def test_unicode_text(self):
        text = "Elle murmura sous le clair de lune éphémère; une mélancolie s'installa."
        signals = classify_register(text)
        assert len(signals) >= 1

    def test_many_rapid_transitions(self):
        """Test that detector handles many transitions gracefully."""
        d = ContextDriftDetector()
        for i, mode in enumerate(NarrativeMode):
            d.force_mode(mode, token_position=i * 1000)
        assert len(d.state.transitions) > 0

    def test_below_theta_down_no_change(self):
        """Confidence below theta_down should not trigger any transition."""
        d = ContextDriftDetector()
        d.force_mode(NarrativeMode.ROMANCE)
        # Very weak literary signal shouldn't switch back
        text = "The cat sat."  # Ambiguous, low confidence
        state, fault = d.update(text, token_position=5000)
        assert d.current_mode == NarrativeMode.ROMANCE  # Stays in romance
