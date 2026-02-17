# SPDX-License-Identifier: Apache-2.0
"""
Tests for CFI v0: Contextual Frame Intrusion detector for nonfiction.
"""

import pytest

from nonfiction_governor.cfi import (
    NonfictionFrame,
    Perspective,
    CFIFaultType,
    FrameSignal,
    PerspectiveSignal,
    CFIFault,
    CFICheckResult,
    CFIState,
    CFIConfig,
    CFIDetector,
    detect_frames,
    detect_perspective,
    check_cfi,
    FRAME_FEATURES,
    PERSPECTIVE_FEATURES,
    SCOPE_PATTERNS,
)


# =============================================================================
# Enums
# =============================================================================


class TestNonfictionFrame:
    def test_all_frames(self):
        assert len(NonfictionFrame) == 12

    def test_string_values(self):
        assert NonfictionFrame.CAPITALISM == "capitalism"
        assert NonfictionFrame.SOCIAL_JUSTICE == "social_justice"
        assert NonfictionFrame.TRAUMA == "trauma"
        assert NonfictionFrame.BOTH_SIDES == "both_sides"
        assert NonfictionFrame.EXPERTS_SAY == "experts_say"
        assert NonfictionFrame.PROGRESS == "progress"
        assert NonfictionFrame.SAFETY == "safety"
        assert NonfictionFrame.SYSTEMIC == "systemic"
        assert NonfictionFrame.INDIVIDUAL == "individual"
        assert NonfictionFrame.NATURAL == "natural"
        assert NonfictionFrame.TECHNOLOGICAL == "technological"
        assert NonfictionFrame.MORAL == "moral"

    def test_every_frame_has_patterns(self):
        for frame in NonfictionFrame:
            assert frame in FRAME_FEATURES, f"Missing patterns for {frame}"
            assert len(FRAME_FEATURES[frame]) >= 3, f"Too few patterns for {frame}"


class TestPerspective:
    def test_values(self):
        assert Perspective.DESCRIPTIVE == "descriptive"
        assert Perspective.NORMATIVE == "normative"
        assert Perspective.PRESCRIPTIVE == "prescriptive"
        assert Perspective.ANALYTICAL == "analytical"

    def test_all_perspectives_have_patterns(self):
        for p in Perspective:
            assert p in PERSPECTIVE_FEATURES


class TestCFIFaultType:
    def test_values(self):
        assert CFIFaultType.UNINVITED_FRAME == "uninvited_frame"
        assert CFIFaultType.FRAME_OVERUSE == "frame_overuse"
        assert CFIFaultType.NORMATIVE_CREEP == "normative_creep"
        assert CFIFaultType.SCOPE_VIOLATION == "scope_violation"


# =============================================================================
# Dataclasses
# =============================================================================


class TestFrameSignal:
    def test_basic(self):
        s = FrameSignal(frame=NonfictionFrame.CAPITALISM, confidence=0.8, matches=5)
        assert s.frame == NonfictionFrame.CAPITALISM
        assert s.confidence == 0.8
        assert s.matches == 5

    def test_to_dict(self):
        s = FrameSignal(frame=NonfictionFrame.TRAUMA, confidence=0.65, matches=3)
        d = s.to_dict()
        assert d["frame"] == "trauma"
        assert d["confidence"] == 0.65
        assert d["matches"] == 3

    def test_roundtrip(self):
        s = FrameSignal(frame=NonfictionFrame.SAFETY, confidence=0.5, matches=2)
        s2 = FrameSignal.from_dict(s.to_dict())
        assert s2.frame == s.frame
        assert s2.confidence == s.confidence
        assert s2.matches == s.matches


class TestPerspectiveSignal:
    def test_basic(self):
        p = PerspectiveSignal(perspective=Perspective.NORMATIVE, confidence=0.7)
        assert p.perspective == Perspective.NORMATIVE

    def test_roundtrip(self):
        p = PerspectiveSignal(perspective=Perspective.ANALYTICAL, confidence=0.9)
        p2 = PerspectiveSignal.from_dict(p.to_dict())
        assert p2.perspective == p.perspective
        assert p2.confidence == p.confidence


class TestCFIFault:
    def test_basic(self):
        f = CFIFault(
            fault_type=CFIFaultType.UNINVITED_FRAME,
            detail="Frame 'capitalism' detected",
            frame=NonfictionFrame.CAPITALISM,
        )
        assert f.severity == "warning"  # Always warning in v0
        assert f.frame == NonfictionFrame.CAPITALISM

    def test_roundtrip(self):
        f = CFIFault(
            fault_type=CFIFaultType.NORMATIVE_CREEP,
            detail="Normative drift",
        )
        f2 = CFIFault.from_dict(f.to_dict())
        assert f2.fault_type == f.fault_type
        assert f2.detail == f.detail
        assert f2.frame is None

    def test_with_frame(self):
        f = CFIFault(
            fault_type=CFIFaultType.FRAME_OVERUSE,
            detail="Overuse",
            frame=NonfictionFrame.BOTH_SIDES,
        )
        d = f.to_dict()
        assert d["frame"] == "both_sides"


class TestCFICheckResult:
    def test_empty(self):
        r = CFICheckResult()
        assert r.has_faults is False
        assert r.frames_detected == []
        assert r.faults == []

    def test_with_faults(self):
        r = CFICheckResult(faults=[
            CFIFault(fault_type=CFIFaultType.UNINVITED_FRAME, detail="test"),
        ])
        assert r.has_faults is True

    def test_to_dict(self):
        r = CFICheckResult(
            frames_detected=[FrameSignal(NonfictionFrame.MORAL, 0.6, 2)],
            perspective=PerspectiveSignal(Perspective.NORMATIVE, 0.8),
            scope_risk=0.3,
        )
        d = r.to_dict()
        assert len(d["frames_detected"]) == 1
        assert d["perspective"]["perspective"] == "normative"
        assert d["scope_risk"] == 0.3
        assert d["has_faults"] is False


# =============================================================================
# CFIState
# =============================================================================


class TestCFIState:
    def test_default(self):
        s = CFIState()
        assert s.frame_counts == {}
        assert s.total_checks == 0
        assert s.total_faults == 0

    def test_record_frames(self):
        s = CFIState()
        s.record_frames([
            FrameSignal(NonfictionFrame.CAPITALISM, 0.8, 3),
            FrameSignal(NonfictionFrame.SAFETY, 0.5, 1),
        ])
        assert s.frame_counts["capitalism"] == 1
        assert s.frame_counts["safety"] == 1
        s.record_frames([
            FrameSignal(NonfictionFrame.CAPITALISM, 0.6, 2),
        ])
        assert s.frame_counts["capitalism"] == 2

    def test_record_perspective(self):
        s = CFIState()
        s.record_perspective(PerspectiveSignal(Perspective.DESCRIPTIVE, 0.8))
        s.record_perspective(PerspectiveSignal(Perspective.NORMATIVE, 0.7))
        assert len(s.perspective_history) == 2
        assert s.perspective_history[0] == "descriptive"
        assert s.perspective_history[1] == "normative"

    def test_perspective_history_capped(self):
        s = CFIState()
        for i in range(25):
            s.record_perspective(PerspectiveSignal(Perspective.DESCRIPTIVE, 0.5))
        assert len(s.perspective_history) == 20

    def test_dominant_frame(self):
        s = CFIState(frame_counts={"capitalism": 5, "safety": 2, "moral": 3})
        assert s.dominant_frame() == "capitalism"

    def test_dominant_frame_empty(self):
        s = CFIState()
        assert s.dominant_frame() is None

    def test_frame_ratio(self):
        s = CFIState(frame_counts={"capitalism": 3}, total_checks=10)
        assert s.frame_ratio("capitalism") == 0.3
        assert s.frame_ratio("safety") == 0.0

    def test_frame_ratio_zero_checks(self):
        s = CFIState()
        assert s.frame_ratio("capitalism") == 0.0

    def test_roundtrip(self):
        s = CFIState(
            frame_counts={"capitalism": 5},
            total_checks=10,
            total_faults=2,
            expected_frames=["capitalism", "safety"],
            expected_perspective="descriptive",
        )
        s2 = CFIState.from_dict(s.to_dict())
        assert s2.frame_counts == s.frame_counts
        assert s2.total_checks == s.total_checks
        assert s2.expected_frames == s.expected_frames
        assert s2.expected_perspective == s.expected_perspective


# =============================================================================
# CFIConfig
# =============================================================================


class TestCFIConfig:
    def test_defaults(self):
        c = CFIConfig()
        assert c.frame_threshold == 0.3
        assert c.overuse_threshold == 0.6
        assert c.min_checks_for_overuse == 5

    def test_roundtrip(self):
        c = CFIConfig(frame_threshold=0.5, overuse_threshold=0.8)
        c2 = CFIConfig.from_dict(c.to_dict())
        assert c2.frame_threshold == 0.5
        assert c2.overuse_threshold == 0.8


# =============================================================================
# Frame Detection
# =============================================================================


class TestClassifyFrames:
    def test_capitalism_frame(self):
        text = (
            "The neoliberal commodification of education has led to "
            "privatization of public goods. Market forces and the profit motive "
            "drive exploitation of workers under capitalism."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        frame_names = [f.frame for f in frames]
        assert NonfictionFrame.CAPITALISM in frame_names

    def test_social_justice_frame(self):
        text = (
            "Systemic racism and white privilege create intersectional "
            "barriers for marginalized communities. Power dynamics and "
            "patriarchal hegemony perpetuate oppression."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        frame_names = [f.frame for f in frames]
        assert NonfictionFrame.SOCIAL_JUSTICE in frame_names

    def test_both_sides_frame(self):
        text = (
            "Critics argue that the policy is harmful. On the other hand, "
            "supporters say it creates jobs. The debate is polarizing, "
            "with both sides presenting valid points."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        frame_names = [f.frame for f in frames]
        assert NonfictionFrame.BOTH_SIDES in frame_names

    def test_experts_say_frame(self):
        text = (
            "Experts say the vaccine is safe. Studies show that the risk "
            "is minimal. According to researchers, the evidence indicates "
            "that it is widely accepted by the scientific consensus."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        frame_names = [f.frame for f in frames]
        assert NonfictionFrame.EXPERTS_SAY in frame_names

    def test_neutral_text_no_strong_frames(self):
        text = (
            "The bridge was completed in 1934. It spans 1,280 meters "
            "across the strait. The total cost was approximately four "
            "million dollars at the time of construction."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        # Factual text should have few or no strong frames
        high_conf = [f for f in frames if f.confidence >= 0.5]
        assert len(high_conf) == 0

    def test_moral_frame(self):
        text = (
            "It is our moral imperative to address this crisis. The situation "
            "is ethically wrong and unconscionable. We must act with virtue "
            "to fulfill our moral duty and obligation."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        frame_names = [f.frame for f in frames]
        assert NonfictionFrame.MORAL in frame_names

    def test_safety_frame(self):
        text = (
            "There are potential dangers associated with this approach. "
            "A thorough risk assessment reveals alarming unintended consequences. "
            "Safeguarding against the worst case scenario requires precautionary measures."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        frame_names = [f.frame for f in frames]
        assert NonfictionFrame.SAFETY in frame_names

    def test_technological_frame(self):
        text = (
            "AI will disrupt every industry through digital transformation. "
            "This cutting-edge innovation represents a paradigm shift. "
            "Scalable machine learning enables next generation automation."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        frame_names = [f.frame for f in frames]
        assert NonfictionFrame.TECHNOLOGICAL in frame_names

    def test_frames_sorted_by_confidence(self):
        text = (
            "Experts say capitalism is morally wrong and represents a systemic "
            "failure. Studies show the profit motive drives exploitation."
        )
        detector = CFIDetector()
        frames = detector.classify_frames(text)
        if len(frames) >= 2:
            for i in range(len(frames) - 1):
                assert frames[i].confidence >= frames[i + 1].confidence

    def test_threshold_filtering(self):
        text = "A simple factual sentence about bridge construction."
        detector = CFIDetector(config=CFIConfig(frame_threshold=0.0))
        # With threshold 0, everything shows up
        frames_low = detector.classify_frames(text)
        detector2 = CFIDetector(config=CFIConfig(frame_threshold=0.9))
        frames_high = detector2.classify_frames(text)
        assert len(frames_low) >= len(frames_high)


# =============================================================================
# Perspective Detection
# =============================================================================


class TestClassifyPerspective:
    def test_descriptive(self):
        text = (
            "The population was approximately 3.2 million as of 2020. "
            "Data shows that the average temperature was recorded at 15 degrees. "
            "According to the survey, roughly 40% of respondents reported satisfaction."
        )
        detector = CFIDetector()
        p = detector.classify_perspective(text)
        assert p.perspective == Perspective.DESCRIPTIVE

    def test_normative(self):
        text = (
            "We should protect the environment. It is morally wrong to "
            "destroy habitats. Society ought to value ethical behavior. "
            "These actions are unjust and unacceptable."
        )
        detector = CFIDetector()
        p = detector.classify_perspective(text)
        assert p.perspective == Perspective.NORMATIVE

    def test_prescriptive(self):
        text = (
            "We recommend implementing the following best practices. "
            "First, establish a protocol for deployment. Second, adopt "
            "these guidelines. The recommended procedure is advisable."
        )
        detector = CFIDetector()
        p = detector.classify_perspective(text)
        assert p.perspective == Perspective.PRESCRIPTIVE

    def test_analytical(self):
        text = (
            "The mechanism explains why this process causes the observed effect. "
            "Therefore, the contributing factors correlate with the result. "
            "Consequently, the causal relationship accounts for the impact."
        )
        detector = CFIDetector()
        p = detector.classify_perspective(text)
        assert p.perspective == Perspective.ANALYTICAL


# =============================================================================
# Scope Detection
# =============================================================================


class TestCheckScope:
    def test_no_scope_violation(self):
        text = "The bridge was built in 1934 and spans the strait."
        detector = CFIDetector()
        risk = detector.check_scope(text)
        assert risk < 0.3

    def test_scope_violation(self):
        text = (
            "This proves that every society always behaves this way. "
            "People are universally inclined to this behavior without exception. "
            "It is undeniably true that all people share this trait."
        )
        detector = CFIDetector()
        risk = detector.check_scope(text)
        assert risk >= 0.3


# =============================================================================
# Full CFI Check
# =============================================================================


class TestCFICheck:
    def test_clean_text(self):
        text = (
            "The building was constructed in 1952 using reinforced concrete. "
            "It stands 45 meters tall and contains 12 floors."
        )
        detector = CFIDetector()
        result = detector.check(text)
        assert result.has_faults is False
        assert result.perspective is not None

    def test_uninvited_frame(self):
        detector = CFIDetector()
        detector.set_expected_frames([NonfictionFrame.SAFETY])
        text = (
            "The neoliberal commodification of education and profit motive "
            "capitalism drives the privatization of public goods under "
            "market forces and exploitation."
        )
        result = detector.check(text)
        uninvited = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.UNINVITED_FRAME
        ]
        assert len(uninvited) > 0

    def test_no_fault_when_frame_expected(self):
        detector = CFIDetector()
        detector.set_expected_frames([NonfictionFrame.CAPITALISM])
        text = (
            "The neoliberal commodification of education drives "
            "privatization under capitalism and market forces."
        )
        result = detector.check(text)
        uninvited = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.UNINVITED_FRAME
            and f.frame == NonfictionFrame.CAPITALISM
        ]
        assert len(uninvited) == 0

    def test_normative_creep(self):
        detector = CFIDetector()
        detector.set_expected_perspective(Perspective.DESCRIPTIVE)
        text = (
            "We should protect the environment. It is morally wrong to "
            "destroy natural habitats. Society ought to value ethical "
            "responsibility. These actions are unjust and unacceptable."
        )
        result = detector.check(text)
        creep = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.NORMATIVE_CREEP
        ]
        assert len(creep) > 0

    def test_no_normative_creep_when_expected(self):
        detector = CFIDetector()
        detector.set_expected_perspective(Perspective.NORMATIVE)
        text = (
            "We should protect the environment. It is morally wrong to "
            "destroy habitats. Society ought to value ethics."
        )
        result = detector.check(text)
        creep = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.NORMATIVE_CREEP
        ]
        assert len(creep) == 0

    def test_scope_violation_in_check(self):
        text = (
            "This proves that every single person always behaves exactly "
            "this way. It is universally true without exception. "
            "All people unquestionably share this trait."
        )
        detector = CFIDetector()
        result = detector.check(text)
        scope = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.SCOPE_VIOLATION
        ]
        assert len(scope) > 0

    def test_check_returns_frames_and_perspective(self):
        text = (
            "Experts say this is widely accepted. Studies show the evidence "
            "indicates a clear consensus. According to researchers, "
            "the data has been recorded and observed."
        )
        detector = CFIDetector()
        result = detector.check(text)
        assert len(result.frames_detected) > 0
        assert result.perspective is not None


# =============================================================================
# Record (stateful)
# =============================================================================


class TestCFIRecord:
    def test_record_updates_state(self):
        detector = CFIDetector()
        text = (
            "Experts say this is widely accepted. Studies show consensus. "
            "According to researchers, evidence indicates agreement."
        )
        result = detector.record(text)
        assert detector.state.total_checks == 1
        assert len(detector.state.perspective_history) == 1

    def test_record_accumulates(self):
        detector = CFIDetector()
        for _ in range(3):
            detector.record("Experts say studies show evidence indicates.")
        assert detector.state.total_checks == 3

    def test_frame_overuse_after_threshold(self):
        detector = CFIDetector(config=CFIConfig(
            min_checks_for_overuse=3,
            overuse_threshold=0.5,
        ))
        # Record several passages with the same frame
        text = (
            "Experts say this is true. Studies show the data. "
            "According to researchers, evidence indicates this. "
            "It is widely accepted by the scientific consensus."
        )
        for _ in range(4):
            detector.record(text)

        # Now check again — should flag overuse
        result = detector.check(text)
        overuse = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.FRAME_OVERUSE
        ]
        assert len(overuse) > 0

    def test_normative_creep_windowed(self):
        detector = CFIDetector(config=CFIConfig(normative_creep_window=4))
        detector.set_expected_perspective(Perspective.DESCRIPTIVE)

        # Feed several normative passages
        normative = (
            "We should act. Society ought to change. It is morally wrong. "
            "These actions are unjust and unacceptable."
        )
        for _ in range(4):
            detector.record(normative)

        # Now check a mildly normative text — windowed creep should fire
        mild = "The building was constructed in 1952. We should preserve it."
        result = detector.check(mild)
        creep = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.NORMATIVE_CREEP
        ]
        assert len(creep) > 0


# =============================================================================
# Stats & Reset
# =============================================================================


class TestCFIStats:
    def test_stats_empty(self):
        detector = CFIDetector()
        s = detector.stats()
        assert s["total_checks"] == 0
        assert s["fault_rate"] == 0.0
        assert s["dominant_frame"] is None

    def test_stats_after_records(self):
        detector = CFIDetector()
        detector.record("Experts say studies show evidence.")
        detector.record("Experts say studies show evidence.")
        s = detector.stats()
        assert s["total_checks"] == 2

    def test_reset(self):
        detector = CFIDetector()
        detector.set_expected_frames([NonfictionFrame.CAPITALISM])
        detector.set_expected_perspective(Perspective.DESCRIPTIVE)
        detector.record("Experts say things.")
        detector.reset()
        assert detector.state.total_checks == 0
        assert detector.state.frame_counts == {}
        # Expected frames/perspective preserved
        assert detector.state.expected_frames == ["capitalism"]
        assert detector.state.expected_perspective == "descriptive"


# =============================================================================
# Serialization
# =============================================================================


class TestCFISerialization:
    def test_detector_roundtrip(self):
        detector = CFIDetector(config=CFIConfig(frame_threshold=0.5))
        detector.set_expected_frames([NonfictionFrame.SAFETY, NonfictionFrame.MORAL])
        detector.record("Experts say studies show data.")
        detector.record("Moral imperative demands ethical action.")

        d = detector.to_dict()
        detector2 = CFIDetector.from_dict(d)
        assert detector2.config.frame_threshold == 0.5
        assert detector2.state.total_checks == 2
        assert "safety" in detector2.state.expected_frames


# =============================================================================
# Convenience functions
# =============================================================================


class TestConvenienceFunctions:
    def test_detect_frames(self):
        text = (
            "The neoliberal commodification under capitalism and profit motive "
            "drives market forces and exploitation of workers."
        )
        frames = detect_frames(text)
        assert len(frames) > 0

    def test_detect_perspective(self):
        text = "The data was observed and recorded. Approximately 40% reported satisfaction."
        p = detect_perspective(text)
        assert p.perspective in list(Perspective)

    def test_check_cfi_basic(self):
        result = check_cfi("A simple factual sentence about construction.")
        assert isinstance(result, CFICheckResult)

    def test_check_cfi_with_expectations(self):
        result = check_cfi(
            "The neoliberal commodification of education and profit motive "
            "capitalism drives privatization. Market forces create exploitation "
            "under the capitalist economic system.",
            expected_frames=[NonfictionFrame.SAFETY],
            expected_perspective=Perspective.DESCRIPTIVE,
        )
        # Should detect uninvited capitalism frame
        assert result.has_faults


# =============================================================================
# Edge cases
# =============================================================================


class TestEdgeCases:
    def test_empty_text(self):
        detector = CFIDetector()
        result = detector.check("")
        assert not result.has_faults

    def test_very_short_text(self):
        detector = CFIDetector()
        result = detector.check("Hello.")
        assert isinstance(result, CFICheckResult)

    def test_no_expected_frames_no_uninvited_faults(self):
        detector = CFIDetector()  # No expected frames set
        text = (
            "The neoliberal commodification under capitalism drives "
            "privatization and exploitation."
        )
        result = detector.check(text)
        uninvited = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.UNINVITED_FRAME
        ]
        assert len(uninvited) == 0  # No expected = nothing uninvited

    def test_no_expected_perspective_no_creep(self):
        detector = CFIDetector()  # No expected perspective set
        text = "We should protect the environment. It is morally wrong."
        result = detector.check(text)
        creep = [
            f for f in result.faults
            if f.fault_type == CFIFaultType.NORMATIVE_CREEP
        ]
        assert len(creep) == 0  # No expected = no creep detected

    def test_all_severity_is_warning(self):
        """v0: all faults are warnings, never errors."""
        detector = CFIDetector()
        detector.set_expected_frames([NonfictionFrame.SAFETY])
        detector.set_expected_perspective(Perspective.DESCRIPTIVE)
        text = (
            "The neoliberal capitalism exploitation drives commodification. "
            "We should morally oppose this. It is always true for everyone."
        )
        result = detector.check(text)
        for fault in result.faults:
            assert fault.severity == "warning"
