# SPDX-License-Identifier: Apache-2.0
"""Tests for the CLUD Clarity Sensor contract + harness."""

from __future__ import annotations

import inspect

import pytest

from governor.clud import (
    CLUD_SCHEMA_VERSION,
    DEFAULT_THRESHOLDS,
    DELTA_WEIGHTS,
    MIN_CLAIMS_FOR_DRIFT_FAIL,
    PADDING_SMELL_RATIO,
    THRESHOLD_BY_GOAL,
    ArtifactGoal,
    ClaimKind,
    CludClaim,
    CludContext,
    CludProtocolError,
    CludResult,
    CludSensor,
    CludStatus,
    DeltaClass,
    ThresholdSet,
    compute_drift_score,
    compute_verdict,
    count_sentences,
    thresholds_for,
)


# =============================================================================
# Fake pipeline implementations (keyed by fixture, not content hash)
# =============================================================================


def make_fake_extractor(fixture: dict[str, list[dict[str, str]]]):
    """Keyed by text, returns canned claims."""

    def extract(text: str, context: CludContext) -> list[dict[str, str]]:
        return fixture.get(text, [])

    return extract


def make_fake_compressor(
    overrides: dict[str, dict[str, str]] | None = None,
):
    """Default: compress to 'simple: {claim}'. Overrides by original text."""
    _overrides = overrides or {}

    def compress(claim: str, context: CludContext) -> dict[str, str]:
        if claim in _overrides:
            return _overrides[claim]
        return {"compressed": f"simple: {claim}"}

    return compress


def make_fake_surfacer(
    overrides: dict[str, str | None] | None = None,
):
    """Default: no uncertainty. Overrides by original text."""
    _overrides = overrides or {}

    def surface(original: str, compressed: str) -> str | None:
        return _overrides.get(original)

    return surface


def make_fake_delta_checker(
    overrides: dict[str, DeltaClass] | None = None,
):
    """Default: PRESERVED. Overrides by original text."""
    _overrides = overrides or {}

    def check(
        original: str,
        compressed: str | None,
        cannot_compress_reason: str | None,
    ) -> DeltaClass:
        return _overrides.get(original, DeltaClass.PRESERVED)

    return check


def make_fake_falsifier(
    overrides: dict[str, tuple[bool, str | None]] | None = None,
):
    """Default: falsifiable with description. Overrides by claim text."""
    _overrides = overrides or {}

    def check(claim: str, kind: ClaimKind) -> tuple[bool, str | None]:
        if claim in _overrides:
            return _overrides[claim]
        return (True, f"test: {claim}")

    return check


# =============================================================================
# Helper: build a CludClaim with defaults
# =============================================================================


def _claim(
    original: str = "X",
    kind: ClaimKind = ClaimKind.DESCRIPTIVE,
    compressed: str | None = "simple: X",
    cannot_compress_reason: str | None = None,
    uncertainty: str | None = None,
    delta: DeltaClass = DeltaClass.PRESERVED,
    falsifiable: bool = True,
    falsification: str | None = "test it",
) -> CludClaim:
    return CludClaim(
        original=original,
        kind=kind,
        compressed=compressed,
        cannot_compress_reason=cannot_compress_reason,
        uncertainty=uncertainty,
        delta=delta,
        falsifiable=falsifiable,
        falsification=falsification,
    )


# =============================================================================
# Tests: Enums
# =============================================================================


class TestEnums:
    def test_claim_kind_completeness(self):
        assert set(ClaimKind) == {
            ClaimKind.DESCRIPTIVE,
            ClaimKind.NORMATIVE,
            ClaimKind.PROCEDURAL,
        }

    def test_delta_class_completeness(self):
        assert set(DeltaClass) == {
            DeltaClass.PRESERVED,
            DeltaClass.INCOMPLETE,
            DeltaClass.AMBIGUOUS,
            DeltaClass.INFLATED,
        }

    def test_clud_status_completeness(self):
        assert set(CludStatus) == {
            CludStatus.PASS,
            CludStatus.WARN,
            CludStatus.FAIL,
        }

    def test_artifact_goal_completeness(self):
        assert set(ArtifactGoal) == {
            ArtifactGoal.PROSE,
            ArtifactGoal.POLICY,
            ArtifactGoal.RATIONALE,
            ArtifactGoal.SPEC,
            ArtifactGoal.COMMIT_MSG,
        }


# =============================================================================
# Tests: Sentence splitter
# =============================================================================


class TestSentenceSplitter:
    def test_single_sentence(self):
        assert count_sentences("The cache invalidates after 60s.") == 1

    def test_multiple_sentences_mixed_punctuation(self):
        text = "First sentence. Second sentence! Third? Fourth."
        assert count_sentences(text) == 4

    def test_empty_or_whitespace(self):
        assert count_sentences("") == 1
        assert count_sentences("   ") == 1


# =============================================================================
# Tests: Drift score
# =============================================================================


class TestDriftScore:
    def test_empty_claims(self):
        assert compute_drift_score([]) == 0.0

    def test_all_preserved(self):
        claims = [_claim(delta=DeltaClass.PRESERVED) for _ in range(3)]
        assert compute_drift_score(claims) == 0.0

    def test_all_inflated(self):
        claims = [_claim(delta=DeltaClass.INFLATED) for _ in range(3)]
        assert compute_drift_score(claims) == 1.0

    def test_mixed_bag(self):
        claims = [
            _claim(delta=DeltaClass.PRESERVED),  # 0.0
            _claim(delta=DeltaClass.INCOMPLETE),  # 0.4
            _claim(delta=DeltaClass.AMBIGUOUS),  # 0.7
            _claim(delta=DeltaClass.INFLATED),  # 1.0
        ]
        expected = (0.0 + 0.4 + 0.7 + 1.0) / 4
        assert abs(compute_drift_score(claims) - expected) < 1e-9

    def test_single_cannot_compress(self):
        """cannot_compress forces delta=INFLATED → weight 1.0."""
        claims = [
            _claim(
                delta=DeltaClass.INFLATED,
                compressed=None,
                cannot_compress_reason="too entangled",
            )
        ]
        assert compute_drift_score(claims) == 1.0


# =============================================================================
# Tests: Verdict
# =============================================================================


class TestVerdict:
    def test_all_preserved_falsifiable(self):
        claims = [_claim(delta=DeltaClass.PRESERVED, falsifiable=True)]
        assert compute_verdict(claims, 0.0) == CludStatus.PASS

    def test_empty_claims(self):
        assert compute_verdict([], 0.0) == CludStatus.PASS

    def test_one_ambiguous_is_warn(self):
        """Single ambiguous claim → WARN, not FAIL.

        drift_score=0.7 exceeds fail_drift, but with only 1 claim the
        min_claims guard prevents drift-based FAIL.  The ambiguous count
        itself triggers WARN.
        """
        claims = [_claim(delta=DeltaClass.AMBIGUOUS)]
        score = compute_drift_score(claims)  # 0.7
        assert score >= DEFAULT_THRESHOLDS.fail_drift
        assert len(claims) < DEFAULT_THRESHOLDS.min_claims_for_drift_fail
        assert compute_verdict(claims, score) == CludStatus.WARN

    def test_one_incomplete_is_warn(self):
        """Single incomplete claim → WARN, not FAIL."""
        claims = [_claim(delta=DeltaClass.INCOMPLETE)]
        score = compute_drift_score(claims)  # 0.4
        assert len(claims) < DEFAULT_THRESHOLDS.min_claims_for_drift_fail
        assert compute_verdict(claims, score) == CludStatus.WARN

    def test_one_unfalsifiable(self):
        claims = [_claim(delta=DeltaClass.PRESERVED, falsifiable=False)]
        assert compute_verdict(claims, 0.0) == CludStatus.WARN

    def test_inflated_always_fails_even_single_claim(self):
        """INFLATED is a hard signal — always FAIL, no minimum claims."""
        claims = [_claim(delta=DeltaClass.INFLATED)]
        score = compute_drift_score(claims)
        assert compute_verdict(claims, score) == CludStatus.FAIL

    def test_inflated_beats_ambiguous(self):
        """Severity ceiling: INFLATED → FAIL even if ambiguous present."""
        claims = [
            _claim(delta=DeltaClass.INFLATED),
            _claim(delta=DeltaClass.AMBIGUOUS),
        ]
        score = compute_drift_score(claims)
        assert compute_verdict(claims, score) == CludStatus.FAIL

    def test_drift_fails_with_enough_claims(self):
        """drift_score >= fail_drift triggers FAIL when enough claims."""
        # 3 ambiguous claims → drift=0.7, count=3 >= min_claims
        claims = [_claim(delta=DeltaClass.AMBIGUOUS) for _ in range(MIN_CLAIMS_FOR_DRIFT_FAIL)]
        score = compute_drift_score(claims)
        assert score >= DEFAULT_THRESHOLDS.fail_drift
        assert compute_verdict(claims, score) == CludStatus.FAIL

    def test_drift_does_not_fail_below_min_claims(self):
        """drift_score >= fail_drift but too few claims → WARN only."""
        claims = [_claim(delta=DeltaClass.AMBIGUOUS)]
        score = compute_drift_score(claims)  # 0.7
        assert score >= DEFAULT_THRESHOLDS.fail_drift
        assert compute_verdict(claims, score) == CludStatus.WARN

    def test_drift_boundary_at_min_minus_one(self):
        """n=min-1 with max non-inflated drift (all ambiguous=0.7) → WARN.

        This is the critical boundary: drift=0.7 well above fail_drift=0.4,
        but n=2 < min_claims=3, so drift alone cannot trigger FAIL.
        No INFLATED claims, so the hard FAIL path is not taken.
        """
        n = MIN_CLAIMS_FOR_DRIFT_FAIL - 1
        assert n >= 1, "test needs min_claims >= 2"
        claims = [_claim(delta=DeltaClass.AMBIGUOUS) for _ in range(n)]
        score = compute_drift_score(claims)  # 0.7 (all ambiguous)
        assert score >= DEFAULT_THRESHOLDS.fail_drift
        assert compute_verdict(claims, score) == CludStatus.WARN

    def test_cannot_compress_implies_fail(self):
        """cannot_compress → delta=INFLATED → hard FAIL."""
        claims = [
            _claim(
                delta=DeltaClass.INFLATED,
                compressed=None,
                cannot_compress_reason="recursive definition",
            )
        ]
        score = compute_drift_score(claims)
        assert compute_verdict(claims, score) == CludStatus.FAIL


# =============================================================================
# Tests: Serialization roundtrip
# =============================================================================


class TestSerialization:
    def test_claim_roundtrip(self):
        claim = _claim(
            original="cache expires in 60s",
            kind=ClaimKind.DESCRIPTIVE,
            compressed="cache: 60s expiry",
            delta=DeltaClass.PRESERVED,
            falsifiable=True,
            falsification="check TTL header",
        )
        restored = CludClaim.from_dict(claim.to_dict())
        assert restored == claim

    def test_result_roundtrip(self):
        result = CludResult(
            schema_version=CLUD_SCHEMA_VERSION,
            status=CludStatus.WARN,
            claims=[
                _claim(delta=DeltaClass.INCOMPLETE, falsifiable=False),
            ],
            drift_score=0.4,
            hidden_assumptions=["assumes UTC"],
            missing_definitions=[],
            unfalsifiable_claims=[("X", ClaimKind.DESCRIPTIVE)],
            padded_or_implicit=False,
            sentence_count=1,
            claim_count=1,
            summary="test summary",
        )
        restored = CludResult.from_dict(result.to_dict())
        assert restored.schema_version == result.schema_version
        assert restored.status == result.status
        assert restored.drift_score == result.drift_score
        assert restored.hidden_assumptions == result.hidden_assumptions
        assert restored.unfalsifiable_claims == result.unfalsifiable_claims
        assert restored.summary == result.summary
        assert len(restored.claims) == 1
        assert restored.claims[0] == result.claims[0]

    def test_context_roundtrip(self):
        ctx = CludContext(
            glossary={"TTL": "time to live"},
            audience="operator",
            artifact_goal="policy",
            must_preserve=("v2.1", "RFC 7231"),
        )
        restored = CludContext.from_dict(ctx.to_dict())
        assert restored == ctx

    def test_future_schema_rejected(self):
        data = {
            "schema_version": CLUD_SCHEMA_VERSION + 1,
            "status": "pass",
            "drift_score": 0.0,
            "padded_or_implicit": False,
            "sentence_count": 1,
            "claim_count": 0,
        }
        with pytest.raises(ValueError, match="Schema version"):
            CludResult.from_dict(data)

    def test_context_normalizes_goal_case(self):
        """CludContext normalizes artifact_goal string to lowercase enum."""
        ctx = CludContext(artifact_goal="POLICY")
        assert ctx.artifact_goal == ArtifactGoal.POLICY
        ctx2 = CludContext(artifact_goal="Spec")
        assert ctx2.artifact_goal == ArtifactGoal.SPEC

    def test_context_rejects_unknown_goal(self):
        with pytest.raises(ValueError, match="Unknown artifact_goal"):
            CludContext(artifact_goal="vibes")

    def test_context_accepts_enum_directly(self):
        ctx = CludContext(artifact_goal=ArtifactGoal.COMMIT_MSG)
        assert ctx.artifact_goal == ArtifactGoal.COMMIT_MSG


# =============================================================================
# Tests: Sensor orchestrator
# =============================================================================


class TestSensorOrchestrator:
    def test_full_pipeline(self):
        """Full pipeline with fakes → correct result shape."""
        text = "The cache expires. It uses LRU."
        fixture = {
            text: [
                {"original": "The cache expires", "kind": "descriptive"},
                {"original": "It uses LRU", "kind": "descriptive"},
            ]
        }
        sensor = CludSensor(
            extractor=make_fake_extractor(fixture),
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze(text)

        assert result.schema_version == CLUD_SCHEMA_VERSION
        assert result.status == CludStatus.PASS
        assert result.claim_count == 2
        assert result.sentence_count == 2
        assert result.drift_score == 0.0
        assert not result.padded_or_implicit
        assert len(result.claims) == 2
        for c in result.claims:
            assert c.compressed is not None
            assert c.delta == DeltaClass.PRESERVED
            assert c.falsifiable

    def test_padded_or_implicit(self):
        """claims << sentences → padded_or_implicit=True."""
        # 5 sentences but only 1 claim extracted
        text = "Sent one. Sent two. Sent three. Sent four. Sent five."
        fixture = {
            text: [
                {"original": "Sent one", "kind": "descriptive"},
            ]
        }
        sensor = CludSensor(
            extractor=make_fake_extractor(fixture),
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze(text)

        assert result.sentence_count == 5
        assert result.claim_count == 1
        # 1 < 5 * 0.5 = 2.5 → padded
        assert result.padded_or_implicit

    def test_empty_text(self):
        """Empty text → PASS with zero claims."""
        sensor = CludSensor(
            extractor=make_fake_extractor({}),
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze("")

        assert result.status == CludStatus.PASS
        assert result.claim_count == 0
        assert result.drift_score == 0.0

    def test_protocol_violation_missing_keys(self):
        """Extractor returning bad dicts → CludProtocolError."""

        def bad_extractor(text, context):
            return [{"original": "claim"}]  # missing 'kind'

        sensor = CludSensor(
            extractor=bad_extractor,
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        with pytest.raises(CludProtocolError, match="missing 'original' or 'kind'"):
            sensor.analyze("some text")

    def test_protocol_violation_bad_kind(self):
        """Extractor returning unknown kind → CludProtocolError."""

        def bad_extractor(text, context):
            return [{"original": "claim", "kind": "bogus"}]

        sensor = CludSensor(
            extractor=bad_extractor,
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        with pytest.raises(CludProtocolError, match="unknown kind"):
            sensor.analyze("some text")

    def test_protocol_violation_compressor_both_keys(self):
        """Compressor returning both keys → CludProtocolError."""
        text = "A claim."
        fixture = {text: [{"original": "A claim", "kind": "descriptive"}]}

        def bad_compressor(claim, context):
            return {"compressed": "simple", "cannot_compress_reason": "nope"}

        sensor = CludSensor(
            extractor=make_fake_extractor(fixture),
            compressor=bad_compressor,
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        with pytest.raises(CludProtocolError, match="exactly one of"):
            sensor.analyze(text)

    def test_cannot_compress_forces_inflated(self):
        """cannot_compress_reason forces delta=INFLATED regardless of checker."""
        text = "Opaque claim."
        fixture = {
            text: [{"original": "Opaque claim", "kind": "normative"}]
        }
        sensor = CludSensor(
            extractor=make_fake_extractor(fixture),
            compressor=make_fake_compressor(
                overrides={
                    "Opaque claim": {
                        "cannot_compress_reason": "self-referential"
                    }
                }
            ),
            surfacer=make_fake_surfacer(),
            # Checker would say PRESERVED, but cannot_compress overrides
            delta_checker=make_fake_delta_checker(
                overrides={"Opaque claim": DeltaClass.PRESERVED}
            ),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze(text)

        assert result.claims[0].delta == DeltaClass.INFLATED
        assert result.claims[0].cannot_compress_reason == "self-referential"
        assert result.status == CludStatus.FAIL

    def test_hidden_assumptions_collected(self):
        """Uncertainty surfacer output collected in hidden_assumptions."""
        text = "Deploys are safe."
        fixture = {
            text: [{"original": "Deploys are safe", "kind": "descriptive"}]
        }
        sensor = CludSensor(
            extractor=make_fake_extractor(fixture),
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(
                overrides={"Deploys are safe": "assumes no concurrent deploys"}
            ),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze(text)

        assert "assumes no concurrent deploys" in result.hidden_assumptions

    def test_unfalsifiable_collected(self):
        """Unfalsifiable claims collected with kind."""
        text = "Code quality matters."
        fixture = {
            text: [{"original": "Code quality matters", "kind": "normative"}]
        }
        sensor = CludSensor(
            extractor=make_fake_extractor(fixture),
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(
                overrides={"Code quality matters": (False, None)}
            ),
        )
        result = sensor.analyze(text)

        assert result.status == CludStatus.WARN
        assert ("Code quality matters", ClaimKind.NORMATIVE) in result.unfalsifiable_claims

    def test_default_context_used(self):
        """analyze() with no context uses default CludContext."""
        sensor = CludSensor(
            extractor=make_fake_extractor({}),
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze("no claims here", context=None)
        assert result.status == CludStatus.PASS


# =============================================================================
# Tests: No LLM imports
# =============================================================================


class TestThresholdSets:
    def test_all_goals_have_thresholds(self):
        """Every ArtifactGoal enum value has an entry."""
        for goal in ArtifactGoal:
            ts = thresholds_for(goal)
            assert isinstance(ts, ThresholdSet)

    def test_string_lookup_normalized(self):
        """String goals are case-insensitive."""
        assert thresholds_for("POLICY") == THRESHOLD_BY_GOAL[ArtifactGoal.POLICY]
        assert thresholds_for("Spec") == THRESHOLD_BY_GOAL[ArtifactGoal.SPEC]

    def test_unknown_goal_gets_defaults(self):
        ts = thresholds_for("mystery_goal")
        assert ts == DEFAULT_THRESHOLDS

    def test_custom_thresholds_override_verdict(self):
        """Harsh thresholds (low fail_drift, min_claims=1) fail a single ambiguous."""
        harsh = ThresholdSet(warn_drift=0.1, fail_drift=0.3, min_claims_for_drift_fail=1)
        claims = [_claim(delta=DeltaClass.AMBIGUOUS)]
        score = compute_drift_score(claims)  # 0.7
        assert compute_verdict(claims, score, harsh) == CludStatus.FAIL

    def test_lenient_thresholds_pass_more(self):
        """Lenient thresholds (high fail_drift) keep moderate drift at WARN."""
        lenient = ThresholdSet(warn_drift=0.1, fail_drift=0.9, min_claims_for_drift_fail=1)
        claims = [_claim(delta=DeltaClass.AMBIGUOUS) for _ in range(3)]
        score = compute_drift_score(claims)  # 0.7
        assert compute_verdict(claims, score, lenient) == CludStatus.WARN

    def test_thresholds_roundtrip_in_result(self):
        result = CludResult(
            schema_version=CLUD_SCHEMA_VERSION,
            status=CludStatus.PASS,
            claims=[],
            drift_score=0.0,
            hidden_assumptions=[],
            missing_definitions=[],
            unfalsifiable_claims=[],
            padded_or_implicit=False,
            sentence_count=1,
            claim_count=0,
            summary="",
            thresholds_used=ThresholdSet(warn_drift=0.2, fail_drift=0.5, min_claims_for_drift_fail=5),
        )
        restored = CludResult.from_dict(result.to_dict())
        assert restored.thresholds_used == result.thresholds_used

    def test_sensor_records_thresholds_used(self):
        """Orchestrator records which ThresholdSet was used."""
        sensor = CludSensor(
            extractor=make_fake_extractor({}),
            compressor=make_fake_compressor(),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze("", context=CludContext(artifact_goal=ArtifactGoal.POLICY))
        assert result.thresholds_used == THRESHOLD_BY_GOAL[ArtifactGoal.POLICY]


# =============================================================================
# Tests: Meta — run clud against its own spec claims
# =============================================================================


class TestMetaSelfCheck:
    """Run the harness against claims from the CLUD spec itself.

    These are hardcoded fixtures (no LLM), but they force the meta-test
    pathway to stay alive so it doesn't rot.
    """

    SPEC_TEXT = (
        "Compress claims to plain language. "
        "Measure what's lost. "
        "Score the loss."
    )

    SPEC_CLAIMS = [
        {"original": "Compress claims to plain language", "kind": "procedural"},
        {"original": "Measure what's lost", "kind": "procedural"},
        {"original": "Score the loss", "kind": "procedural"},
    ]

    def test_spec_meta_sentence_passes(self):
        """The spec's own simple-version summary should PASS clud."""
        sensor = CludSensor(
            extractor=make_fake_extractor({self.SPEC_TEXT: self.SPEC_CLAIMS}),
            compressor=make_fake_compressor({
                # These are already simple — compression preserves them
                "Compress claims to plain language": {"compressed": "Simplify claims"},
                "Measure what's lost": {"compressed": "Measure loss"},
                "Score the loss": {"compressed": "Score the loss"},
            }),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),  # all PRESERVED
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze(self.SPEC_TEXT)

        assert result.status == CludStatus.PASS
        assert result.claim_count == 3
        assert result.drift_score == 0.0

    def test_spec_inflated_claim_detected(self):
        """An inflated version of the spec should FAIL."""
        bloated = (
            "The system leverages advanced compression-based analytical "
            "techniques to facilitate the identification of semantic drift."
        )
        sensor = CludSensor(
            extractor=make_fake_extractor({
                bloated: [
                    {"original": bloated, "kind": "descriptive"},
                ]
            }),
            compressor=make_fake_compressor(
                overrides={bloated: {"cannot_compress_reason": "performative jargon"}}
            ),
            surfacer=make_fake_surfacer(),
            delta_checker=make_fake_delta_checker(),
            falsifier=make_fake_falsifier(),
        )
        result = sensor.analyze(bloated)

        assert result.status == CludStatus.FAIL
        assert result.claims[0].delta == DeltaClass.INFLATED


# =============================================================================
# Tests: No LLM imports
# =============================================================================


class TestNoLLMImport:
    def test_module_has_no_llm_imports(self):
        """The clud module must not import any LLM plumbing."""
        import governor.clud as mod

        source = inspect.getsource(mod)
        banned = [
            "import anthropic",
            "import openai",
            "from anthropic",
            "from openai",
            "import ollama",
            "from ollama",
            "import litellm",
            "from litellm",
        ]
        for pattern in banned:
            assert pattern not in source, (
                f"clud.py must not contain '{pattern}' — "
                f"LLM backends are deferred to 3.x"
            )
