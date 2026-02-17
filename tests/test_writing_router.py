# SPDX-License-Identifier: Apache-2.0
"""Tests for writing_router.py — Language Domain Toggle + Fiction Type Selection."""

import pytest

from governor.writing_router import (
    CODE_POLARITY,
    FICTION_TYPE_WEIGHTS,
    PROSE_POLARITY,
    CodeRegime,
    FictionType,
    LanguageDomain,
    PolarityProfile,
    ProseMode,
    RouterConfig,
    RouterInput,
    RouterOutput,
    WritingRouter,
    create_code_router,
    create_fiction_router,
    create_prose_router,
    detect_domain_hint,
    get_hybrid_components,
    get_polarity,
    get_regime_weights,
    is_hybrid_type,
    validate_fiction_type_transition,
)


# =============================================================================
# LanguageDomain Tests
# =============================================================================


class TestLanguageDomain:
    def test_prose_value(self):
        assert LanguageDomain.PROSE.value == "prose"

    def test_code_value(self):
        assert LanguageDomain.CODE.value == "code"

    def test_from_string(self):
        assert LanguageDomain("prose") == LanguageDomain.PROSE
        assert LanguageDomain("code") == LanguageDomain.CODE


# =============================================================================
# FictionType Tests
# =============================================================================


class TestFictionType:
    def test_pure_types(self):
        assert FictionType.COMEDY.value == "comedy"
        assert FictionType.TRAGEDY.value == "tragedy"
        assert FictionType.DRAMA.value == "drama"
        assert FictionType.SINCERITY.value == "sincerity"

    def test_hybrid_types(self):
        assert FictionType.DRAMEDY.value == "dramedy"
        assert FictionType.TRAGICOMEDY.value == "tragicomedy"
        assert FictionType.SINCERE_DRAMA.value == "sincere_drama"

    def test_neutral(self):
        assert FictionType.NEUTRAL.value == "neutral"

    def test_all_types_have_weights(self):
        for ft in FictionType:
            assert ft in FICTION_TYPE_WEIGHTS


class TestFictionTypeWeights:
    def test_comedy_pure(self):
        weights = FICTION_TYPE_WEIGHTS[FictionType.COMEDY]
        assert weights["comedy"] == 1.0
        assert weights["tragedy"] == 0.0
        assert weights["drama"] == 0.0
        assert weights["sincerity"] == 0.0

    def test_tragedy_pure(self):
        weights = FICTION_TYPE_WEIGHTS[FictionType.TRAGEDY]
        assert weights["tragedy"] == 1.0
        assert weights["comedy"] == 0.0

    def test_dramedy_hybrid(self):
        weights = FICTION_TYPE_WEIGHTS[FictionType.DRAMEDY]
        assert weights["drama"] == 0.6
        assert weights["comedy"] == 0.4
        assert weights["tragedy"] == 0.0

    def test_tragicomedy_hybrid(self):
        weights = FICTION_TYPE_WEIGHTS[FictionType.TRAGICOMEDY]
        assert weights["tragedy"] == 0.6
        assert weights["comedy"] == 0.4

    def test_neutral_balanced(self):
        weights = FICTION_TYPE_WEIGHTS[FictionType.NEUTRAL]
        assert weights["comedy"] == 0.25
        assert weights["tragedy"] == 0.25
        assert weights["sincerity"] == 0.25
        assert weights["drama"] == 0.25

    def test_get_regime_weights(self):
        weights = get_regime_weights(FictionType.COMEDY)
        assert weights["comedy"] == 1.0

    def test_get_regime_weights_unknown(self):
        # Should return neutral weights for any unknown type
        weights = get_regime_weights(FictionType.NEUTRAL)
        assert sum(weights.values()) == pytest.approx(1.0)


# =============================================================================
# ProseMode Tests
# =============================================================================


class TestProseMode:
    def test_fiction_value(self):
        assert ProseMode.FICTION.value == "fiction"

    def test_nonfiction_value(self):
        assert ProseMode.NONFICTION.value == "nonfiction"


# =============================================================================
# CodeRegime Tests
# =============================================================================


class TestCodeRegime:
    def test_dev_value(self):
        assert CodeRegime.DEV.value == "dev"

    def test_sre_value(self):
        assert CodeRegime.SRE.value == "sre"

    def test_analysis_value(self):
        assert CodeRegime.ANALYSIS.value == "analysis"


# =============================================================================
# PolarityProfile Tests
# =============================================================================


class TestPolarityProfile:
    def test_prose_polarity(self):
        assert PROSE_POLARITY.governance_visible is False
        assert PROSE_POLARITY.silence_is_restraint is True
        assert PROSE_POLARITY.repetition_is_good is False
        assert PROSE_POLARITY.retry_strategy == "rephrase"
        assert "Ep" in PROSE_POLARITY.load_bearing_vars

    def test_code_polarity(self):
        assert CODE_POLARITY.governance_visible is True
        assert CODE_POLARITY.silence_is_restraint is False
        assert CODE_POLARITY.repetition_is_good is True
        assert CODE_POLARITY.retry_strategy == "augment"
        assert "Ap" in CODE_POLARITY.load_bearing_vars

    def test_polarity_inversion(self):
        # Key insight: code and prose are polar opposites
        assert PROSE_POLARITY.governance_visible != CODE_POLARITY.governance_visible
        assert PROSE_POLARITY.silence_is_restraint != CODE_POLARITY.silence_is_restraint
        assert PROSE_POLARITY.repetition_is_good != CODE_POLARITY.repetition_is_good

    def test_get_polarity_prose(self):
        polarity = get_polarity(LanguageDomain.PROSE)
        assert polarity == PROSE_POLARITY

    def test_get_polarity_code(self):
        polarity = get_polarity(LanguageDomain.CODE)
        assert polarity == CODE_POLARITY


# =============================================================================
# RouterConfig Tests
# =============================================================================


class TestRouterConfig:
    def test_defaults(self):
        config = RouterConfig()
        assert config.domain == LanguageDomain.PROSE
        assert config.prose_mode == ProseMode.NONFICTION
        assert config.fiction_type == FictionType.NEUTRAL
        assert config.code_regime == CodeRegime.DEV
        assert config.allow_hybrids is True
        assert config.lock_fiction_type is False

    def test_to_dict(self):
        config = RouterConfig(
            domain=LanguageDomain.CODE,
            code_regime=CodeRegime.SRE,
        )
        d = config.to_dict()
        assert d["domain"] == "code"
        assert d["code_regime"] == "sre"

    def test_from_dict(self):
        d = {
            "domain": "prose",
            "prose_mode": "fiction",
            "fiction_type": "comedy",
            "lock_fiction_type": True,
        }
        config = RouterConfig.from_dict(d)
        assert config.domain == LanguageDomain.PROSE
        assert config.prose_mode == ProseMode.FICTION
        assert config.fiction_type == FictionType.COMEDY
        assert config.lock_fiction_type is True

    def test_from_dict_defaults(self):
        config = RouterConfig.from_dict({})
        assert config.domain == LanguageDomain.PROSE
        assert config.prose_mode == ProseMode.NONFICTION

    def test_roundtrip(self):
        config = RouterConfig(
            domain=LanguageDomain.PROSE,
            prose_mode=ProseMode.FICTION,
            fiction_type=FictionType.DRAMEDY,
        )
        d = config.to_dict()
        config2 = RouterConfig.from_dict(d)
        assert config2.domain == config.domain
        assert config2.prose_mode == config.prose_mode
        assert config2.fiction_type == config.fiction_type


# =============================================================================
# RouterInput/Output Tests
# =============================================================================


class TestRouterInput:
    def test_minimal(self):
        input = RouterInput(text="Hello world")
        assert input.text == "Hello world"
        assert input.intent is None
        assert input.config is None
        assert input.context == {}

    def test_with_config(self):
        config = RouterConfig(domain=LanguageDomain.CODE)
        input = RouterInput(text="def foo():", config=config)
        assert input.config.domain == LanguageDomain.CODE


class TestRouterOutput:
    def test_fields(self):
        output = RouterOutput(
            domain=LanguageDomain.PROSE,
            polarity=PROSE_POLARITY,
            controller="regime",
            controller_config={"fiction_type": "comedy"},
            regime_name="comedy",
            regime_weights={"comedy": 1.0},
        )
        assert output.domain == LanguageDomain.PROSE
        assert output.controller == "regime"
        assert output.regime_name == "comedy"


# =============================================================================
# WritingRouter Tests
# =============================================================================


class TestWritingRouter:
    def test_default_config(self):
        router = WritingRouter()
        assert router.config.domain == LanguageDomain.PROSE
        assert router.config.prose_mode == ProseMode.NONFICTION

    def test_custom_config(self):
        config = RouterConfig(domain=LanguageDomain.CODE)
        router = WritingRouter(config)
        assert router.config.domain == LanguageDomain.CODE


class TestWritingRouterRoute:
    def test_route_prose_nonfiction(self):
        router = WritingRouter()
        input = RouterInput(text="The research shows...")
        output = router.route(input)

        assert output.domain == LanguageDomain.PROSE
        assert output.controller == "nonfiction"
        assert output.regime_name == "nonfiction"
        assert output.polarity.governance_visible is False

    def test_route_prose_fiction_comedy(self):
        config = RouterConfig(
            domain=LanguageDomain.PROSE,
            prose_mode=ProseMode.FICTION,
            fiction_type=FictionType.COMEDY,
        )
        router = WritingRouter(config)
        input = RouterInput(text="Once upon a time...")
        output = router.route(input)

        assert output.domain == LanguageDomain.PROSE
        assert output.controller == "regime"
        assert output.regime_name == "comedy"
        assert output.regime_weights is not None
        assert output.regime_weights["comedy"] == 1.0

    def test_route_prose_fiction_tragedy(self):
        config = RouterConfig(
            domain=LanguageDomain.PROSE,
            prose_mode=ProseMode.FICTION,
            fiction_type=FictionType.TRAGEDY,
        )
        router = WritingRouter(config)
        output = router.route(RouterInput(text="..."))

        assert output.regime_name == "tragedy"
        assert output.regime_weights["tragedy"] == 1.0

    def test_route_prose_fiction_dramedy(self):
        config = RouterConfig(
            domain=LanguageDomain.PROSE,
            prose_mode=ProseMode.FICTION,
            fiction_type=FictionType.DRAMEDY,
        )
        router = WritingRouter(config)
        output = router.route(RouterInput(text="..."))

        # Primary component is drama
        assert output.regime_name == "drama"
        # But weights reflect hybrid
        assert output.regime_weights["drama"] == 0.6
        assert output.regime_weights["comedy"] == 0.4

    def test_route_code_dev(self):
        config = RouterConfig(
            domain=LanguageDomain.CODE,
            code_regime=CodeRegime.DEV,
        )
        router = WritingRouter(config)
        input = RouterInput(text="def process():")
        output = router.route(input)

        assert output.domain == LanguageDomain.CODE
        assert output.controller == "custody"
        assert output.regime_name == "code_dev"
        assert output.polarity.governance_visible is True

    def test_route_code_sre(self):
        config = RouterConfig(
            domain=LanguageDomain.CODE,
            code_regime=CodeRegime.SRE,
        )
        router = WritingRouter(config)
        output = router.route(RouterInput(text="kubectl apply"))

        assert output.regime_name == "code_sre"
        assert output.controller_config["regime"] == "sre"

    def test_input_config_overrides_router_config(self):
        router = WritingRouter()  # Default prose/nonfiction
        input_config = RouterConfig(domain=LanguageDomain.CODE)
        input = RouterInput(text="...", config=input_config)
        output = router.route(input)

        # Input config wins
        assert output.domain == LanguageDomain.CODE


class TestWritingRouterSetters:
    def test_set_domain(self):
        router = WritingRouter()
        router.set_domain(LanguageDomain.CODE)
        assert router.config.domain == LanguageDomain.CODE

    def test_set_prose_mode(self):
        router = WritingRouter()
        router.set_prose_mode(ProseMode.FICTION)
        assert router.config.prose_mode == ProseMode.FICTION

    def test_set_fiction_type(self):
        router = WritingRouter()
        router.set_fiction_type(FictionType.TRAGEDY)
        assert router.config.fiction_type == FictionType.TRAGEDY

    def test_set_code_regime(self):
        router = WritingRouter()
        router.set_code_regime(CodeRegime.SRE)
        assert router.config.code_regime == CodeRegime.SRE

    def test_lock_fiction_type(self):
        router = WritingRouter()
        router.lock_fiction_type(True)
        assert router.config.lock_fiction_type is True


# =============================================================================
# Convenience Factory Tests
# =============================================================================


class TestConvenienceFactories:
    def test_create_prose_router_default(self):
        router = create_prose_router()
        assert router.config.domain == LanguageDomain.PROSE
        assert router.config.prose_mode == ProseMode.NONFICTION

    def test_create_prose_router_fiction(self):
        router = create_prose_router(
            mode=ProseMode.FICTION,
            fiction_type=FictionType.COMEDY,
        )
        assert router.config.prose_mode == ProseMode.FICTION
        assert router.config.fiction_type == FictionType.COMEDY

    def test_create_fiction_router(self):
        router = create_fiction_router(FictionType.DRAMA)
        assert router.config.prose_mode == ProseMode.FICTION
        assert router.config.fiction_type == FictionType.DRAMA

    def test_create_fiction_router_locked(self):
        router = create_fiction_router(FictionType.COMEDY, lock_type=True)
        assert router.config.lock_fiction_type is True

    def test_create_code_router_default(self):
        router = create_code_router()
        assert router.config.domain == LanguageDomain.CODE
        assert router.config.code_regime == CodeRegime.DEV

    def test_create_code_router_sre(self):
        router = create_code_router(CodeRegime.SRE)
        assert router.config.code_regime == CodeRegime.SRE


# =============================================================================
# Hybrid Type Tests
# =============================================================================


class TestHybridTypes:
    def test_is_hybrid_type_true(self):
        assert is_hybrid_type(FictionType.DRAMEDY) is True
        assert is_hybrid_type(FictionType.TRAGICOMEDY) is True
        assert is_hybrid_type(FictionType.SINCERE_DRAMA) is True

    def test_is_hybrid_type_false(self):
        assert is_hybrid_type(FictionType.COMEDY) is False
        assert is_hybrid_type(FictionType.TRAGEDY) is False
        assert is_hybrid_type(FictionType.DRAMA) is False
        assert is_hybrid_type(FictionType.SINCERITY) is False
        assert is_hybrid_type(FictionType.NEUTRAL) is False

    def test_get_hybrid_components_dramedy(self):
        components = get_hybrid_components(FictionType.DRAMEDY)
        assert FictionType.DRAMA in components
        assert FictionType.COMEDY in components

    def test_get_hybrid_components_tragicomedy(self):
        components = get_hybrid_components(FictionType.TRAGICOMEDY)
        assert FictionType.TRAGEDY in components
        assert FictionType.COMEDY in components

    def test_get_hybrid_components_pure_type(self):
        components = get_hybrid_components(FictionType.COMEDY)
        assert components == [FictionType.COMEDY]


class TestFictionTypeTransition:
    def test_normal_transition_allowed(self):
        allowed, reason = validate_fiction_type_transition(
            FictionType.COMEDY, FictionType.DRAMA
        )
        assert allowed is True
        assert "Transition allowed" in reason

    def test_major_shift_warning(self):
        allowed, reason = validate_fiction_type_transition(
            FictionType.COMEDY, FictionType.TRAGEDY
        )
        assert allowed is True
        assert "Warning" in reason
        assert "tonal shift" in reason

    def test_reverse_major_shift_warning(self):
        allowed, reason = validate_fiction_type_transition(
            FictionType.TRAGEDY, FictionType.COMEDY
        )
        assert allowed is True
        assert "Warning" in reason

    def test_hybrid_not_allowed(self):
        allowed, reason = validate_fiction_type_transition(
            FictionType.COMEDY,
            FictionType.DRAMEDY,
            allow_hybrids=False,
        )
        assert allowed is False
        assert "Hybrid types not allowed" in reason

    def test_hybrid_allowed(self):
        allowed, reason = validate_fiction_type_transition(
            FictionType.COMEDY,
            FictionType.DRAMEDY,
            allow_hybrids=True,
        )
        assert allowed is True


# =============================================================================
# Domain Detection Hint Tests
# =============================================================================


class TestDetectDomainHint:
    def test_no_hint_for_prose(self):
        text = "The quick brown fox jumps over the lazy dog."
        hint = detect_domain_hint(text)
        assert hint is None

    def test_code_hint_for_python(self):
        text = """
import typing

def process_data(items):
    class Item:
        pass
    return items
        """
        hint = detect_domain_hint(text)
        assert hint == LanguageDomain.CODE

    def test_code_hint_for_javascript(self):
        text = """
function processData(items) {
    const result = items.filter(x => x.valid);
    return result;
}
        """
        hint = detect_domain_hint(text)
        assert hint == LanguageDomain.CODE

    def test_code_hint_for_markdown_code_block(self):
        text = """
Here's how to do it:

```python
def example():
    pass
```
        """
        hint = detect_domain_hint(text)
        # Has ``` and def, but only 2 indicators
        # Need 3+ for strong signal
        assert hint is None or hint == LanguageDomain.CODE

    def test_weak_signal_returns_none(self):
        text = "The function of art is to imitate nature."
        hint = detect_domain_hint(text)
        assert hint is None


# =============================================================================
# Integration Tests
# =============================================================================


class TestRouterIntegration:
    def test_fiction_comedy_to_tragedy(self):
        """Test switching fiction type maintains routing."""
        router = create_fiction_router(FictionType.COMEDY)
        output1 = router.route(RouterInput(text="..."))
        assert output1.regime_name == "comedy"

        router.set_fiction_type(FictionType.TRAGEDY)
        output2 = router.route(RouterInput(text="..."))
        assert output2.regime_name == "tragedy"

    def test_prose_to_code_switch(self):
        """Test domain switch inverts polarity."""
        router = WritingRouter()
        prose_output = router.route(RouterInput(text="..."))
        assert prose_output.polarity.governance_visible is False

        router.set_domain(LanguageDomain.CODE)
        code_output = router.route(RouterInput(text="..."))
        assert code_output.polarity.governance_visible is True

    def test_locked_fiction_type_in_config(self):
        """Test lock_fiction_type is passed through."""
        router = create_fiction_router(FictionType.COMEDY, lock_type=True)
        output = router.route(RouterInput(text="..."))
        assert output.controller_config["lock_type"] is True

    def test_controller_config_passed_through(self):
        """Test controller receives relevant config."""
        router = create_code_router(CodeRegime.SRE)
        output = router.route(RouterInput(text="..."))
        assert output.controller_config["regime"] == "sre"
        assert output.controller_config["custody_scoring"] is True
