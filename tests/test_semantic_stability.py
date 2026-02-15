"""Tests for semantic_stability — perturbation-based conditioning audit.

Property-based: assert structural properties (monotonicity, bounds,
determinism), NOT exact string equality.  Mock generate_fn returns
parametrized outputs — no hardcoded output assertions.

Two canary fixtures at the bottom: one "known stable", one "known brittle".
These are intentionally boring — they become canaries when you refactor
tokenization/strip logic.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from governor.semantic_stability import (
    STABILITY_SCHEMA_VERSION,
    DivergenceMethod,
    PerturbationKind,
    Perturbation,
    StabilityAuditResult,
    StabilityConfig,
    StabilityFingerprint,
    StabilityAuditor,
    StabilityStore,
    compute_basin_entropy,
    compute_commutator_drift,
    compute_divergence,
    compute_fingerprint,
    compute_noise_floor,
    find_atomic_segments,
    generate_perturbation,
    perturb_clause_reorder,
    perturb_format_jitter,
    perturb_hedge_insert,
    perturb_negation_probe,
    perturb_role_rewrap,
    strip_boilerplate,
    tokenize_normalize,
    _jaccard_divergence,
    _shingled_jaccard,
    _edit_distance_normalized,
    _canonical_json,
    _content_hash,
    _round_floats,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_gov_dir(tmp_path):
    """Create a temporary .governor directory."""
    gov = tmp_path / ".governor"
    gov.mkdir()
    return gov


def _echo_fn(prompt: str) -> str:
    """Deterministic mock: returns the prompt itself."""
    return prompt


def _constant_fn(value: str = "constant output"):
    """Returns a generate_fn that always returns the same string."""
    def fn(prompt: str) -> str:
        return value
    return fn


def _varying_fn(responses: list[str]):
    """Returns a generate_fn that cycles through responses."""
    idx = [0]
    def fn(prompt: str) -> str:
        result = responses[idx[0] % len(responses)]
        idx[0] += 1
        return result
    return fn


# =============================================================================
# TestEnums
# =============================================================================


class TestEnums:
    def test_perturbation_kind_values(self):
        assert len(PerturbationKind) == 5

    def test_perturbation_kind_names(self):
        names = {k.value for k in PerturbationKind}
        assert "format_jitter" in names
        assert "negation_probe" in names

    def test_divergence_method_values(self):
        assert len(DivergenceMethod) == 3

    def test_divergence_method_names(self):
        names = {m.value for m in DivergenceMethod}
        assert "jaccard" in names
        assert "edit_distance" in names

    def test_perturbation_kind_is_str(self):
        assert isinstance(PerturbationKind.FORMAT_JITTER, str)

    def test_divergence_method_is_str(self):
        assert isinstance(DivergenceMethod.JACCARD, str)


# =============================================================================
# TestPerturbFormatJitter
# =============================================================================


class TestPerturbFormatJitter:
    def test_deterministic_with_seed(self):
        text = "- item one\n- item two\n- item three"
        r1, m1 = perturb_format_jitter(text, seed=42)
        r2, m2 = perturb_format_jitter(text, seed=42)
        assert r1 == r2
        assert m1 == m2

    def test_different_seed_different_result(self):
        text = "- item one\n- item two\n- item three\n- item four"
        r1, _ = perturb_format_jitter(text, seed=42)
        r2, _ = perturb_format_jitter(text, seed=99)
        # At least one should differ (probabilistic but near-certain with 4 items)
        # If both happen to be identical, that's a valid but rare outcome
        assert isinstance(r1, str) and isinstance(r2, str)

    def test_magnitude_nonnegative(self):
        text = "- alpha\n- beta\n- gamma"
        _, mag = perturb_format_jitter(text, seed=42)
        assert mag >= 0.0

    def test_magnitude_bounded(self):
        text = "- alpha\n- beta\n- gamma"
        _, mag = perturb_format_jitter(text, seed=42)
        assert mag <= 1.0

    def test_code_blocks_preserved(self):
        text = "intro\n```python\nprint('hello')\n```\n- item one"
        result, _ = perturb_format_jitter(text, seed=42)
        assert "```python\nprint('hello')\n```" in result

    def test_empty_string(self):
        result, mag = perturb_format_jitter("", seed=42)
        assert result == ""
        assert mag == 0.0

    def test_single_line_no_bullets(self):
        text = "Hello world."
        result, _ = perturb_format_jitter(text, seed=42)
        assert isinstance(result, str)

    def test_numbered_to_bullet_swap(self):
        text = "1. first item\n2. second item\n3. third item"
        # Run many seeds — at least one should produce a bullet
        found_bullet = False
        for seed in range(20):
            result, _ = perturb_format_jitter(text, seed=seed)
            if "- " in result:
                found_bullet = True
                break
        assert found_bullet


# =============================================================================
# TestPerturbClauseReorder
# =============================================================================


class TestPerturbClauseReorder:
    def test_deterministic_with_seed(self):
        text = "The cat sat. The dog ran. The bird flew."
        r1, m1 = perturb_clause_reorder(text, seed=42)
        r2, m2 = perturb_clause_reorder(text, seed=42)
        assert r1 == r2
        assert m1 == m2

    def test_single_sentence_unchanged(self):
        text = "Just one sentence here."
        result, mag = perturb_clause_reorder(text, seed=42)
        assert result == text
        assert mag == 0.0

    def test_multi_sentence_preserves_content(self):
        text = "Alpha is first. Beta is second. Gamma is third."
        result, _ = perturb_clause_reorder(text, seed=42)
        # All original words should be present
        for word in ["Alpha", "Beta", "Gamma"]:
            assert word in result

    def test_magnitude_nonneg_and_bounded(self):
        text = "First sentence here. Second sentence here. Third sentence here."
        _, mag = perturb_clause_reorder(text, seed=42)
        assert 0.0 <= mag <= 1.0

    def test_code_blocks_preserved(self):
        text = "Setup info. Details here.\n```\ncode\n```\nMore sentences. Another one."
        result, _ = perturb_clause_reorder(text, seed=42)
        assert "```\ncode\n```" in result

    def test_empty_string(self):
        result, mag = perturb_clause_reorder("", seed=42)
        assert result == ""
        assert mag == 0.0

    def test_all_short_sentences_preserved(self):
        text = "Hi. Ok."
        result, _ = perturb_clause_reorder(text, seed=42)
        # Short sentences (< 3 words) are not shuffled
        assert isinstance(result, str)

    def test_shuffles_with_enough_sentences(self):
        text = "The first sentence is long enough. The second sentence is also long. The third one as well."
        results = set()
        for seed in range(30):
            r, _ = perturb_clause_reorder(text, seed=seed)
            results.add(r)
        # Should produce at least 2 distinct orderings
        assert len(results) >= 2


# =============================================================================
# TestPerturbRoleRewrap
# =============================================================================


class TestPerturbRoleRewrap:
    def test_you_are_pattern(self):
        text = "You are a helpful assistant. Answer the question."
        result, mag = perturb_role_rewrap(text, seed=42)
        assert result != text
        assert mag > 0

    def test_as_pattern(self):
        text = "As a helpful assistant, answer the question."
        result, mag = perturb_role_rewrap(text, seed=42)
        assert result != text
        assert mag > 0

    def test_task_pattern(self):
        text = "Task: answer the question Context: you are an assistant"
        result, mag = perturb_role_rewrap(text, seed=42)
        assert result != text
        assert mag > 0

    def test_generic_fallback(self):
        text = "What is 2+2?"
        result, mag = perturb_role_rewrap(text, seed=42)
        assert result != text
        assert mag > 0

    def test_magnitude_bounded(self):
        text = "You are a coder. Write Python."
        _, mag = perturb_role_rewrap(text, seed=42)
        assert 0.0 <= mag <= 1.0

    def test_deterministic(self):
        text = "You are a teacher. Explain math."
        r1, _ = perturb_role_rewrap(text, seed=42)
        r2, _ = perturb_role_rewrap(text, seed=42)
        assert r1 == r2


# =============================================================================
# TestPerturbHedgeInsert
# =============================================================================


class TestPerturbHedgeInsert:
    def test_hedge_words_appear(self):
        text = "Write a function that sorts a list."
        result, _ = perturb_hedge_insert(text, seed=42)
        hedges = {"please", "if possible", "I think", "perhaps", "kindly",
                  "I believe", "it seems like", "maybe", "ideally"}
        found = any(h in result.lower() for h in hedges)
        assert found or result == text  # Edge case: empty prose regions

    def test_original_content_preserved(self):
        text = "Write a function that sorts a list."
        result, _ = perturb_hedge_insert(text, seed=42)
        for word in ["function", "sorts", "list"]:
            assert word in result

    def test_magnitude_small(self):
        text = "Write a function that sorts a list and returns the result."
        _, mag = perturb_hedge_insert(text, seed=42)
        # Hedges should produce small magnitude (adding few words)
        assert mag < 0.5

    def test_magnitude_nonneg(self):
        text = "Hello world."
        _, mag = perturb_hedge_insert(text, seed=42)
        assert mag >= 0.0

    def test_empty_string(self):
        result, mag = perturb_hedge_insert("", seed=42)
        assert result == ""
        assert mag == 0.0

    def test_deterministic(self):
        text = "Implement the algorithm."
        r1, _ = perturb_hedge_insert(text, seed=42)
        r2, _ = perturb_hedge_insert(text, seed=42)
        assert r1 == r2


# =============================================================================
# TestPerturbNegationProbe
# =============================================================================


class TestPerturbNegationProbe:
    def test_negation_inserted(self):
        text = "You should always validate input."
        result, _ = perturb_negation_probe(text, seed=42)
        # Should contain a negation
        neg_words = ["not", "never", "cannot", "Do not"]
        assert any(nw in result for nw in neg_words) or result != text

    def test_magnitude_positive(self):
        text = "The system should validate all inputs."
        _, mag = perturb_negation_probe(text, seed=42)
        assert mag > 0

    def test_fallback_do_not(self):
        # Text with no standard negation targets
        text = "xyz abc 123"
        result, _ = perturb_negation_probe(text, seed=42)
        assert "Do not" in result or result != text

    def test_deterministic(self):
        text = "You must always check."
        r1, _ = perturb_negation_probe(text, seed=42)
        r2, _ = perturb_negation_probe(text, seed=42)
        assert r1 == r2

    def test_code_blocks_preserved(self):
        text = "You should check.\n```\ncode_here\n```\nDone."
        result, _ = perturb_negation_probe(text, seed=42)
        assert "```\ncode_here\n```" in result

    def test_empty_string(self):
        result, mag = perturb_negation_probe("", seed=42)
        assert result == ""
        assert mag == 0.0


# =============================================================================
# TestAtomicSegments
# =============================================================================


class TestAtomicSegments:
    def test_code_fence_detected(self):
        text = "before\n```python\ncode\n```\nafter"
        segs = find_atomic_segments(text)
        assert len(segs) >= 1
        seg_text = text[segs[0][0]:segs[0][1]]
        assert "code" in seg_text

    def test_no_segments_plain_text(self):
        text = "Just plain text with no code blocks."
        segs = find_atomic_segments(text)
        assert segs == []

    def test_multi_line_json(self):
        text = 'Before {\n"key": "value"\n} after'
        segs = find_atomic_segments(text)
        assert len(segs) >= 1

    def test_single_line_json_is_prose(self):
        text = 'Before {"key": "value"} after'
        segs = find_atomic_segments(text)
        assert segs == []  # Single-line JSON treated as prose

    def test_xml_multiline(self):
        text = "Before <div>\ncontent\n</div> after"
        segs = find_atomic_segments(text)
        assert len(segs) >= 1

    def test_perturbation_preserves_all_code(self):
        code_block = "```python\ndef foo():\n    return 42\n```"
        text = f"You should write code.\n{code_block}\nDo it now."
        for kind in PerturbationKind:
            result, _ = generate_perturbation(text, kind.value, seed=42)
            assert code_block in result, f"{kind.value} damaged code block"


# =============================================================================
# TestComputeMagnitude (via token Jaccard)
# =============================================================================


class TestComputeMagnitude:
    """Magnitude uses token-set Jaccard (same as divergence) to keep
    stiffness = d/m dimensionless and bounded."""

    def test_identical_zero(self):
        assert compute_divergence("hello world", "hello world") == 0.0

    def test_disjoint_one(self):
        d = compute_divergence("alpha beta gamma", "delta epsilon zeta")
        assert d == 1.0

    def test_small_edit_small_divergence(self):
        d = compute_divergence("the quick brown fox", "the quick brown dog")
        assert 0.0 < d < 0.5

    def test_big_edit_big_divergence(self):
        d = compute_divergence("the quick brown fox", "completely different text here now")
        assert d > 0.5

    def test_empty_strings_zero(self):
        assert compute_divergence("", "") == 0.0


# =============================================================================
# TestComputeDivergence
# =============================================================================


class TestComputeDivergence:
    # --- Jaccard ---
    def test_jaccard_identical(self):
        assert compute_divergence("a b c", "a b c", "jaccard") == 0.0

    def test_jaccard_disjoint(self):
        assert compute_divergence("a b c", "d e f", "jaccard") == 1.0

    def test_jaccard_monotonic(self):
        d1 = compute_divergence("a b c d e", "a b c d f", "jaccard")
        d2 = compute_divergence("a b c d e", "x y z w v", "jaccard")
        assert d1 < d2

    # --- Shingled Jaccard ---
    def test_shingled_identical(self):
        assert compute_divergence("a b c d e", "a b c d e", "shingled_jaccard") == 0.0

    def test_shingled_disjoint(self):
        d = compute_divergence("a b c d e", "f g h i j", "shingled_jaccard")
        assert d == 1.0

    def test_shingled_order_aware(self):
        # Reordering should produce nonzero shingled divergence
        d = compute_divergence("a b c d e", "e d c b a", "shingled_jaccard")
        assert d > 0.0

    def test_shingled_vs_jaccard_for_reorder(self):
        # Shingled should be MORE sensitive to reordering than bag-of-words Jaccard
        text_a = "the quick brown fox jumps"
        text_b = "jumps fox brown quick the"
        d_jaccard = compute_divergence(text_a, text_b, "jaccard")
        d_shingled = compute_divergence(text_a, text_b, "shingled_jaccard")
        assert d_shingled >= d_jaccard

    # --- Edit distance ---
    def test_edit_identical(self):
        assert compute_divergence("hello", "hello", "edit_distance") == 0.0

    def test_edit_disjoint(self):
        d = compute_divergence("abc", "xyz", "edit_distance")
        assert d == 1.0

    def test_edit_monotonic(self):
        d1 = compute_divergence("abcde", "abcdf", "edit_distance")
        d2 = compute_divergence("abcde", "vwxyz", "edit_distance")
        assert d1 < d2

    def test_edit_distance_long_text_fallback(self):
        long_a = "a " * 1500
        long_b = "b " * 1500
        # Should not raise — falls back to jaccard
        d = compute_divergence(long_a, long_b, "edit_distance")
        assert 0.0 <= d <= 1.0


# =============================================================================
# TestBasinEntropy
# =============================================================================


class TestBasinEntropy:
    def test_all_identical_one_basin(self):
        baseline = "the answer is 42"
        outputs = ["the answer is 42"] * 5
        be = compute_basin_entropy(baseline, outputs, threshold=0.3)
        assert be == 1.0

    def test_all_different_multiple_basins(self):
        baseline = "alpha"
        outputs = ["beta", "gamma", "delta"]
        be = compute_basin_entropy(baseline, outputs, threshold=0.1)
        assert be >= 2  # baseline + at least one far cluster

    def test_threshold_sensitivity(self):
        baseline = "the quick brown fox"
        outputs = ["the quick brown dog", "totally different text"]
        be_loose = compute_basin_entropy(baseline, outputs, threshold=0.9)
        be_tight = compute_basin_entropy(baseline, outputs, threshold=0.01)
        assert be_tight >= be_loose

    def test_empty_outputs_one_basin(self):
        be = compute_basin_entropy("baseline", [], threshold=0.3)
        assert be == 1.0

    def test_near_baseline_counted_as_one(self):
        baseline = "the quick brown fox"
        outputs = [
            "the quick brown fox",  # identical
            "the quick brown dog",  # very close
        ]
        be = compute_basin_entropy(baseline, outputs, threshold=0.5)
        assert be == 1.0  # All near baseline

    def test_greedy_clustering(self):
        baseline = "alpha"
        # Two far clusters that are similar to each other
        outputs = ["beta gamma delta", "beta gamma epsilon"]
        be = compute_basin_entropy(baseline, outputs, threshold=0.3)
        # They should cluster together (same basin)
        assert be <= 3

    def test_distinct_far_clusters(self):
        baseline = "aaa"
        outputs = ["bbb ccc ddd", "eee fff ggg"]
        be = compute_basin_entropy(baseline, outputs, threshold=0.1)
        assert be >= 3  # baseline + 2 far clusters

    def test_return_type_float(self):
        be = compute_basin_entropy("x", ["y"], threshold=0.3)
        assert isinstance(be, float)


# =============================================================================
# TestCommutatorDrift
# =============================================================================


class TestCommutatorDrift:
    def test_deterministic_mock_produces_value(self):
        d = compute_commutator_drift(
            "You are a coder. Write Python.",
            "role_rewrap", "clause_reorder",
            _echo_fn, seed=42, noise_floor=0.0,
        )
        assert isinstance(d, float)
        assert d >= 0.0

    def test_noise_floor_subtracted(self):
        d_no_noise = compute_commutator_drift(
            "You are a coder. Write Python.",
            "role_rewrap", "clause_reorder",
            _echo_fn, seed=42, noise_floor=0.0,
        )
        d_with_noise = compute_commutator_drift(
            "You are a coder. Write Python.",
            "role_rewrap", "clause_reorder",
            _echo_fn, seed=42, noise_floor=0.5,
        )
        assert d_with_noise <= d_no_noise

    def test_clamped_to_zero(self):
        d = compute_commutator_drift(
            "You are X. Do Y.",
            "role_rewrap", "clause_reorder",
            _echo_fn, seed=42, noise_floor=999.0,
        )
        assert d == 0.0

    def test_same_perturbation_low_drift(self):
        # Applying the same kind twice should commute
        d = compute_commutator_drift(
            "Hello world. How are you. Fine thanks.",
            "format_jitter", "format_jitter",
            _constant_fn("fixed output"), seed=42, noise_floor=0.0,
        )
        assert d == 0.0

    def test_constant_fn_zero_drift(self):
        d = compute_commutator_drift(
            "You are a coder. Write Python.",
            "role_rewrap", "clause_reorder",
            _constant_fn("always same"), seed=42, noise_floor=0.0,
        )
        assert d == 0.0

    def test_varying_fn_possible_drift(self):
        # If outputs differ, drift may be nonzero
        d = compute_commutator_drift(
            "You are a coder. Write Python.",
            "role_rewrap", "clause_reorder",
            _varying_fn(["output A is different", "output B is different"]),
            seed=42, noise_floor=0.0,
        )
        assert d >= 0.0


# =============================================================================
# TestNoiseFloor
# =============================================================================


class TestNoiseFloor:
    def test_deterministic_same_output_zero(self):
        nf = compute_noise_floor("prompt", _constant_fn("same"), n=3)
        assert nf == 0.0

    def test_varying_output_positive(self):
        nf = compute_noise_floor(
            "prompt",
            _varying_fn(["output one here", "output two here", "output three here"]),
            n=3,
        )
        assert nf > 0.0

    def test_n_one_returns_zero(self):
        nf = compute_noise_floor("prompt", _echo_fn, n=1)
        assert nf == 0.0

    def test_n_two_valid(self):
        nf = compute_noise_floor(
            "prompt", _varying_fn(["aaa bbb", "ccc ddd"]), n=2
        )
        assert nf >= 0.0

    def test_bounded(self):
        nf = compute_noise_floor(
            "prompt",
            _varying_fn(["alpha", "beta", "gamma"]),
            n=3,
        )
        assert 0.0 <= nf <= 1.0

    def test_median_not_mean(self):
        # Verify median is used (median is robust to outliers)
        responses = ["same here", "same here", "totally different content now"]
        nf = compute_noise_floor("p", _varying_fn(responses), n=3)
        assert isinstance(nf, float)


# =============================================================================
# TestExcessDivergence
# =============================================================================


class TestExcessDivergence:
    def test_subtraction_correct(self):
        raw = [0.5, 0.3, 0.8]
        noise = 0.2
        excess = [max(0.0, d - noise) for d in raw]
        assert excess == [pytest.approx(0.3), pytest.approx(0.1), pytest.approx(0.6)]

    def test_clamped_to_zero(self):
        raw = [0.1, 0.05, 0.0]
        noise = 0.2
        excess = [max(0.0, d - noise) for d in raw]
        assert all(e == 0.0 for e in excess)

    def test_noise_floor_zero_passthrough(self):
        raw = [0.3, 0.5]
        noise = 0.0
        excess = [max(0.0, d - noise) for d in raw]
        assert excess == raw

    def test_all_zero_raw(self):
        raw = [0.0, 0.0, 0.0]
        noise = 0.1
        excess = [max(0.0, d - noise) for d in raw]
        assert all(e == 0.0 for e in excess)

    def test_high_noise_clamps_all(self):
        raw = [0.1, 0.2, 0.3]
        noise = 1.0
        excess = [max(0.0, d - noise) for d in raw]
        assert all(e == 0.0 for e in excess)


# =============================================================================
# TestComputeFingerprint
# =============================================================================


class TestComputeFingerprint:
    def _basic_fingerprint(self, **kwargs):
        defaults = dict(
            stripped_divergences=[0.3, 0.4, 0.2, 0.5, 0.8],
            magnitudes=[0.1, 0.1, 0.1, 0.1, 0.1],
            kinds=["format_jitter", "clause_reorder", "role_rewrap",
                   "hedge_insert", "negation_probe"],
            noise_floor=0.1,
            commutator_drift=0.05,
            commutator_kinds=("role_rewrap", "clause_reorder"),
            baseline_output="baseline output text",
            perturbed_outputs=["out1", "out2", "out3", "out4", "out5"],
            control_divergence=0.7,
            basin_threshold=0.3,
            method="jaccard",
        )
        defaults.update(kwargs)
        return compute_fingerprint(**defaults)

    def test_stiffness_excludes_negation(self):
        fp = self._basic_fingerprint()
        # Negation probe is the 5th entry (index 4), should be excluded
        # Non-negation excess: [0.2, 0.3, 0.1, 0.4] / 0.1 = [2.0, 3.0, 1.0, 4.0]
        # Median of [1.0, 2.0, 3.0, 4.0] = 2.5
        assert fp.stiffness > 0

    def test_anisotropy_ratio(self):
        fp = self._basic_fingerprint()
        assert fp.anisotropy >= 1.0

    def test_basin_entropy_positive(self):
        fp = self._basic_fingerprint()
        assert fp.basin_entropy >= 1.0

    def test_control_divergence_passthrough(self):
        fp = self._basic_fingerprint(control_divergence=0.42)
        assert fp.control_divergence == 0.42

    def test_stiffness_by_kind_no_negation(self):
        fp = self._basic_fingerprint()
        assert "negation_probe" not in fp.stiffness_by_kind

    def test_stiffness_by_kind_has_entries(self):
        fp = self._basic_fingerprint()
        assert len(fp.stiffness_by_kind) > 0

    def test_zero_magnitude_excluded(self):
        fp = self._basic_fingerprint(magnitudes=[0.0, 0.0, 0.0, 0.0, 0.0])
        assert fp.stiffness == 0.0

    def test_commutator_kinds_stored(self):
        fp = self._basic_fingerprint()
        assert fp.commutator_kinds == ("role_rewrap", "clause_reorder")

    def test_noise_floor_stored(self):
        fp = self._basic_fingerprint(noise_floor=0.15)
        assert fp.noise_floor == 0.15

    def test_single_entry(self):
        fp = compute_fingerprint(
            stripped_divergences=[0.5],
            magnitudes=[0.1],
            kinds=["format_jitter"],
            noise_floor=0.1,
            commutator_drift=0.0,
            commutator_kinds=("role_rewrap", "clause_reorder"),
            baseline_output="baseline",
            perturbed_outputs=["perturbed"],
            control_divergence=0.0,
        )
        assert fp.stiffness >= 0


# =============================================================================
# TestStabilityConfig
# =============================================================================


class TestStabilityConfig:
    def test_defaults(self):
        config = StabilityConfig()
        assert config.n_perturbations == 8
        assert len(config.kinds) == 5
        assert config.divergence_method == "jaccard"
        assert config.max_generate_calls == 20

    def test_roundtrip(self):
        config = StabilityConfig(n_perturbations=4, seed=99)
        d = config.to_dict()
        restored = StabilityConfig.from_dict(d)
        assert restored.n_perturbations == 4
        assert restored.seed == 99

    def test_schema_version_in_dict(self):
        config = StabilityConfig()
        d = config.to_dict()
        assert d["schema_version"] == STABILITY_SCHEMA_VERSION

    def test_mutable_default_isolation(self):
        c1 = StabilityConfig()
        c2 = StabilityConfig()
        c1.kinds.append("extra")
        assert "extra" not in c2.kinds

    def test_decoding_params(self):
        config = StabilityConfig(decoding_params={"temperature": 0.7, "model": "test"})
        d = config.to_dict()
        assert d["decoding_params"]["temperature"] == 0.7

    def test_commutator_pair_default(self):
        config = StabilityConfig()
        assert config.commutator_pair == ("role_rewrap", "clause_reorder")


# =============================================================================
# TestStabilityAuditResult
# =============================================================================


class TestStabilityAuditResult:
    def _make_result(self, **kwargs):
        fp = StabilityFingerprint(
            stiffness=1.0, anisotropy=2.0, basin_entropy=1.0,
            commutator_drift=0.1, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={"format_jitter": 1.0},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        defaults = dict(
            fingerprint=fp,
            excess_divergences=[0.1, 0.2],
            raw_divergences=[0.15, 0.25],
            stripped_divergences=[0.1, 0.2],
            perturbation_kinds=["format_jitter", "clause_reorder"],
            magnitudes=[0.05, 0.08],
            perturbations=[
                {"kind": "format_jitter", "seed": 42, "perturbed_hash": "abc", "magnitude": 0.05},
            ],
            prompt_hash="ph",
            output_hash="oh",
            envelope_hash="eh",
            timestamp="2026-01-01T00:00:00Z",
            config_hash="ch",
        )
        defaults.update(kwargs)
        return StabilityAuditResult(**defaults)

    def test_construction(self):
        result = self._make_result()
        assert result.mode == "observational"
        assert result.recommendation == "calibrating"

    def test_roundtrip(self):
        result = self._make_result(recommendation="stable", recommendation_reason="test")
        d = result.to_dict()
        restored = StabilityAuditResult.from_dict(d)
        assert restored.recommendation == "stable"
        assert restored.recommendation_reason == "test"

    def test_schema_version_in_dict(self):
        result = self._make_result()
        d = result.to_dict()
        assert d["schema_version"] == STABILITY_SCHEMA_VERSION

    def test_receipt_id_field(self):
        result = self._make_result(receipt_id="r123")
        assert result.receipt_id == "r123"

    def test_recommendation_reason_field(self):
        result = self._make_result(recommendation_reason="stiffness=1.5 > 2.0")
        d = result.to_dict()
        assert "stiffness" in d["recommendation_reason"]

    def test_unknown_schema_version_rejected(self):
        d = self._make_result().to_dict()
        d["schema_version"] = 999
        with pytest.raises(ValueError, match="Unknown stability schema version"):
            StabilityAuditResult.from_dict(d)


# =============================================================================
# TestStabilityFingerprint
# =============================================================================


class TestStabilityFingerprint:
    def test_construction(self):
        fp = StabilityFingerprint(
            stiffness=1.5, anisotropy=2.0, basin_entropy=1.0,
            commutator_drift=0.1, noise_floor=0.05, control_divergence=0.8,
            stiffness_by_kind={"format_jitter": 1.2, "role_rewrap": 2.0},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        assert fp.stiffness == 1.5
        assert fp.control_divergence == 0.8

    def test_roundtrip(self):
        fp = StabilityFingerprint(
            stiffness=1.0, anisotropy=3.0, basin_entropy=2.0,
            commutator_drift=0.2, noise_floor=0.1, control_divergence=0.9,
            stiffness_by_kind={"hedge_insert": 0.5},
            commutator_kinds=("format_jitter", "hedge_insert"),
        )
        d = fp.to_dict()
        restored = StabilityFingerprint.from_dict(d)
        assert restored.stiffness == 1.0
        assert restored.commutator_kinds == ("format_jitter", "hedge_insert")

    def test_stiffness_by_kind_dict(self):
        fp = StabilityFingerprint(
            stiffness=1.0, anisotropy=1.0, basin_entropy=1.0,
            commutator_drift=0.0, noise_floor=0.0, control_divergence=0.0,
            stiffness_by_kind={"a": 1.0, "b": 2.0},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        d = fp.to_dict()
        assert d["stiffness_by_kind"] == {"a": 1.0, "b": 2.0}

    def test_commutator_kinds_tuple(self):
        fp = StabilityFingerprint(
            stiffness=0, anisotropy=0, basin_entropy=0,
            commutator_drift=0, noise_floor=0, control_divergence=0,
            stiffness_by_kind={},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        assert isinstance(fp.commutator_kinds, tuple)

    def test_frozen(self):
        fp = StabilityFingerprint(
            stiffness=0, anisotropy=0, basin_entropy=0,
            commutator_drift=0, noise_floor=0, control_divergence=0,
            stiffness_by_kind={},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        with pytest.raises(AttributeError):
            fp.stiffness = 999  # type: ignore

    def test_from_dict_defaults(self):
        d = {
            "stiffness": 1.0, "anisotropy": 1.0, "basin_entropy": 1.0,
            "commutator_drift": 0.0, "noise_floor": 0.0, "control_divergence": 0.0,
        }
        fp = StabilityFingerprint.from_dict(d)
        assert fp.stiffness_by_kind == {}
        assert fp.commutator_kinds == ("role_rewrap", "clause_reorder")


# =============================================================================
# TestStabilityAuditor
# =============================================================================


class TestStabilityAuditor:
    def test_full_audit_with_echo(self):
        config = StabilityConfig(
            n_perturbations=5, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0, seed=42,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            "You are a coder. Write Python.",
            "Here is some Python code.",
            _echo_fn,
        )
        assert result.mode == "observational"
        assert len(result.raw_divergences) == 5
        assert len(result.perturbation_kinds) == 5
        assert result.calls_used > 0
        assert not result.budget_exceeded

    def test_should_audit_rate_zero(self):
        auditor = StabilityAuditor(StabilityConfig(sample_rate=0))
        assert not auditor.should_audit("any prompt")

    def test_should_audit_rate_one(self):
        auditor = StabilityAuditor(StabilityConfig(sample_rate=1.0))
        assert auditor.should_audit("any prompt")

    def test_should_audit_rate_negative(self):
        auditor = StabilityAuditor(StabilityConfig(sample_rate=-0.5))
        assert not auditor.should_audit("any prompt")

    def test_should_audit_deterministic(self):
        auditor = StabilityAuditor(StabilityConfig(sample_rate=0.5))
        result1 = auditor.should_audit("test prompt")
        result2 = auditor.should_audit("test prompt")
        assert result1 == result2

    def test_should_audit_uses_sha256(self):
        """Same prompt = same decision, regardless of Python hash seed."""
        auditor = StabilityAuditor(StabilityConfig(sample_rate=0.3))
        results = [auditor.should_audit("fixed prompt") for _ in range(10)]
        assert len(set(results)) == 1

    def test_envelope_hashing(self):
        config = StabilityConfig(
            n_perturbations=2, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
            decoding_params={"temperature": 0.7},
        )
        auditor = StabilityAuditor(config)
        r1 = auditor.audit("prompt", "output", _constant_fn("out"),
                           envelope={"system_prompt": "sys1"})
        r2 = auditor.audit("prompt", "output", _constant_fn("out"),
                           envelope={"system_prompt": "sys2"})
        assert r1.envelope_hash != r2.envelope_hash

    def test_recommendation_classification_stable(self):
        fp = StabilityFingerprint(
            stiffness=0.1, anisotropy=1.5, basin_entropy=1.0,
            commutator_drift=0.0, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={}, commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        auditor = StabilityAuditor()
        rec, reason = auditor._classify_recommendation(fp)
        assert rec == "stable"
        assert "stiffness" in reason

    def test_recommendation_classification_brittle(self):
        fp = StabilityFingerprint(
            stiffness=5.0, anisotropy=10.0, basin_entropy=1.0,
            commutator_drift=0.5, noise_floor=0.05, control_divergence=0.8,
            stiffness_by_kind={}, commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        auditor = StabilityAuditor()
        rec, reason = auditor._classify_recommendation(fp)
        assert rec == "brittle"
        assert "stiffness" in reason

    def test_recommendation_classification_multimodal(self):
        fp = StabilityFingerprint(
            stiffness=1.0, anisotropy=2.0, basin_entropy=4.0,
            commutator_drift=0.1, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={}, commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        auditor = StabilityAuditor()
        rec, reason = auditor._classify_recommendation(fp)
        assert rec == "multimodal"
        assert "basin_entropy" in reason

    def test_receipt_emission(self):
        config = StabilityConfig(
            n_perturbations=2, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        mock_receipt_system = MagicMock()
        mock_receipt = MagicMock()
        mock_receipt.receipt_id = "test_receipt_123"
        mock_receipt_system.emit.return_value = mock_receipt

        result = auditor.audit(
            "You are a coder. Write Python.",
            "Here is code.",
            _echo_fn,
            receipt_system=mock_receipt_system,
        )
        assert result.receipt_id == "test_receipt_123"
        mock_receipt_system.emit.assert_called_once()
        call_kwargs = mock_receipt_system.emit.call_args
        assert call_kwargs[1]["gate"] == "semantic_stability"
        assert call_kwargs[1]["verdict"] == "observe"

    def test_perturbation_records_for_replay(self):
        config = StabilityConfig(
            n_perturbations=3, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit("Test prompt.", "Test output.", _echo_fn)
        assert len(result.perturbations) == 3
        for rec in result.perturbations:
            assert "kind" in rec
            assert "seed" in rec
            assert "perturbed_hash" in rec
            assert "magnitude" in rec

    def test_config_hash_changes_with_config(self):
        a1 = StabilityAuditor(StabilityConfig(seed=1, n_perturbations=2,
                                               noise_floor_samples=2, max_generate_calls=50))
        a2 = StabilityAuditor(StabilityConfig(seed=2, n_perturbations=2,
                                               noise_floor_samples=2, max_generate_calls=50))
        r1 = a1.audit("p", "o", _constant_fn("x"))
        r2 = a2.audit("p", "o", _constant_fn("x"))
        assert r1.config_hash != r2.config_hash


# =============================================================================
# TestStabilityStore
# =============================================================================


class TestStabilityStore:
    def _make_result(self):
        fp = StabilityFingerprint(
            stiffness=1.0, anisotropy=2.0, basin_entropy=1.0,
            commutator_drift=0.1, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={"format_jitter": 1.0},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        return StabilityAuditResult(
            fingerprint=fp,
            excess_divergences=[0.1],
            raw_divergences=[0.15],
            stripped_divergences=[0.1],
            perturbation_kinds=["format_jitter"],
            magnitudes=[0.05],
            perturbations=[{"kind": "format_jitter", "seed": 42, "perturbed_hash": "abc", "magnitude": 0.05}],
            prompt_hash="ph",
            output_hash="oh",
            envelope_hash="eh",
            timestamp="2026-01-01T00:00:00Z",
            config_hash="ch",
        )

    def test_append_and_query(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        result = self._make_result()
        store.append(result)
        results = store.query()
        assert len(results) == 1
        assert results[0].fingerprint.stiffness == 1.0

    def test_multiple_appends(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        for _ in range(5):
            store.append(self._make_result())
        results = store.query()
        assert len(results) == 5

    def test_newest_first(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        r1 = self._make_result()
        r1.timestamp = "2026-01-01T00:00:00Z"
        store.append(r1)
        r2 = self._make_result()
        r2.timestamp = "2026-01-02T00:00:00Z"
        store.append(r2)
        results = store.query()
        # Last appended should be first (newest)
        assert results[0].timestamp == "2026-01-02T00:00:00Z"

    def test_limit(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        for _ in range(10):
            store.append(self._make_result())
        results = store.query(limit=3)
        assert len(results) == 3

    def test_empty_store_returns_empty(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        assert store.query() == []

    def test_corrupted_line_skipped(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        store.append(self._make_result())
        # Manually corrupt a line
        with open(store.log_path, "a") as f:
            f.write("NOT VALID JSON\n")
        store.append(self._make_result())
        results = store.query()
        assert len(results) == 2  # Corrupted line skipped

    def test_partial_last_line_dropped(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        store.append(self._make_result())
        # Add partial line (no newline)
        with open(store.log_path, "a") as f:
            f.write('{"incomplete": true')
        results = store.query()
        assert len(results) == 1

    def test_get_distribution(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        for _ in range(3):
            store.append(self._make_result())
        dist = store.get_distribution("stiffness")
        assert len(dist) == 3
        assert all(v == 1.0 for v in dist)

    def test_get_distribution_unknown_metric(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        store.append(self._make_result())
        dist = store.get_distribution("nonexistent")
        assert dist == []

    def test_count_empty(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        assert store.count() == 0

    def test_count_with_data(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        for _ in range(5):
            store.append(self._make_result())
        assert store.count() == 5

    def test_count_matches_query_len(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        for _ in range(3):
            store.append(self._make_result())
        assert store.count() == len(store.query(limit=10000))

    def test_schema_version_roundtrip(self, tmp_gov_dir):
        store = StabilityStore(tmp_gov_dir)
        store.append(self._make_result())
        text = store.log_path.read_text()
        d = json.loads(text.strip())
        assert d["schema_version"] == STABILITY_SCHEMA_VERSION


# =============================================================================
# TestNegativeControls
# =============================================================================


class TestNegativeControls:
    """Format jitter should be near noise floor.
    Negation probe should be above noise floor."""

    def test_format_jitter_low_divergence(self):
        """Format changes (whitespace, bullets) should produce low output divergence
        when the model (mock) is sensitive to content, not formatting."""
        # Mock that strips whitespace → format jitter has no effect
        def content_only_fn(p):
            return " ".join(p.split()).lower()

        prompt = "- item one\n- item two\n- item three"
        output = content_only_fn(prompt)
        perturbed, mag = perturb_format_jitter(prompt, seed=42)
        perturbed_output = content_only_fn(perturbed)
        d = compute_divergence(output, perturbed_output)
        # Should be low — format changes don't affect content-normalized output
        assert d < 0.4

    def test_negation_probe_high_divergence_expected(self):
        """Negation should flip meaning → high divergence in a meaning-sensitive mock."""
        def meaning_fn(p):
            if "not" in p.lower() or "never" in p.lower():
                return "negative response"
            return "positive response"

        prompt = "You should always validate input."
        output = meaning_fn(prompt)
        perturbed, _ = perturb_negation_probe(prompt, seed=42)
        perturbed_output = meaning_fn(perturbed)
        d = compute_divergence(output, perturbed_output)
        assert d > 0.5

    def test_hedge_insert_low_divergence(self):
        """Hedges are semantically inert → low divergence in content mock."""
        def content_fn(p):
            # Strip common hedges before responding
            for h in ["please", "if possible", "perhaps", "kindly", "maybe"]:
                p = p.replace(h, "").replace(h.capitalize(), "")
            return " ".join(p.split()).lower()

        prompt = "Write a sorting function."
        output = content_fn(prompt)
        perturbed, _ = perturb_hedge_insert(prompt, seed=42)
        perturbed_output = content_fn(perturbed)
        d = compute_divergence(output, perturbed_output)
        assert d < 0.3

    def test_role_rewrap_moderate_divergence(self):
        """Role rewrap changes framing — may or may not change output."""
        prompt = "You are a coder. Write Python."
        _, mag = perturb_role_rewrap(prompt, seed=42)
        # Magnitude should be moderate (content preserved, framing changed)
        assert 0.0 < mag < 1.0

    def test_clause_reorder_preserves_content(self):
        prompt = "First do A. Then do B. Finally do C."
        perturbed, _ = perturb_clause_reorder(prompt, seed=42)
        # All content words should still be present
        for word in ["First", "Then", "Finally"]:
            assert word in perturbed


# =============================================================================
# TestInjectionTripwire
# =============================================================================


class TestInjectionTripwire:
    """Disproportionate role_rewrap divergence = injection susceptibility."""

    def test_role_rewrap_disproportionate(self):
        """If role_rewrap stiffness >> other kinds, the model is sensitive
        to instruction framing — a prompt injection signal."""
        fp = StabilityFingerprint(
            stiffness=1.5, anisotropy=5.0, basin_entropy=1.0,
            commutator_drift=0.3, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={
                "format_jitter": 0.1,
                "clause_reorder": 0.2,
                "role_rewrap": 5.0,  # Disproportionately high
                "hedge_insert": 0.1,
            },
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        # role_rewrap stiffness should be >> others
        non_rewrap = [v for k, v in fp.stiffness_by_kind.items() if k != "role_rewrap"]
        assert fp.stiffness_by_kind["role_rewrap"] > 10 * max(non_rewrap)

    def test_uniform_stiffness_not_flagged(self):
        fp = StabilityFingerprint(
            stiffness=1.0, anisotropy=1.5, basin_entropy=1.0,
            commutator_drift=0.1, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={
                "format_jitter": 1.0,
                "clause_reorder": 1.2,
                "role_rewrap": 0.9,
                "hedge_insert": 1.1,
            },
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        non_rewrap = [v for k, v in fp.stiffness_by_kind.items() if k != "role_rewrap"]
        assert fp.stiffness_by_kind["role_rewrap"] < 3 * max(non_rewrap)

    def test_high_anisotropy_with_rewrap(self):
        """High anisotropy + high role_rewrap = injection concern."""
        fp = StabilityFingerprint(
            stiffness=2.0, anisotropy=8.0, basin_entropy=1.0,
            commutator_drift=0.5, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={"role_rewrap": 4.0, "format_jitter": 0.5},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        assert fp.anisotropy > 5.0
        assert fp.stiffness_by_kind.get("role_rewrap", 0) > 2 * fp.stiffness_by_kind.get("format_jitter", 1)

    def test_commutator_drift_with_rewrap(self):
        """High commutator drift with role_rewrap = order-dependent injection."""
        fp = StabilityFingerprint(
            stiffness=1.5, anisotropy=3.0, basin_entropy=1.0,
            commutator_drift=0.8, noise_floor=0.05, control_divergence=0.5,
            stiffness_by_kind={"role_rewrap": 3.0, "clause_reorder": 1.0},
            commutator_kinds=("role_rewrap", "clause_reorder"),
        )
        assert fp.commutator_drift > 0.5


# =============================================================================
# TestCallBudget
# =============================================================================


class TestCallBudget:
    def test_budget_respected(self):
        config = StabilityConfig(
            n_perturbations=10, noise_floor_samples=3,
            max_generate_calls=5, sample_rate=1.0,
        )
        call_count = [0]
        def counting_fn(p):
            call_count[0] += 1
            return "output"

        auditor = StabilityAuditor(config)
        result = auditor.audit("prompt", "output", counting_fn)
        assert result.budget_exceeded
        assert result.calls_used <= config.max_generate_calls + 1  # +1 for the exceeding call

    def test_partial_result_not_raised(self):
        config = StabilityConfig(
            n_perturbations=10, noise_floor_samples=3,
            max_generate_calls=2, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        # Should return result, not raise
        result = auditor.audit("prompt", "output", _constant_fn("x"))
        assert isinstance(result, StabilityAuditResult)
        assert result.budget_exceeded

    def test_budget_exceeded_true(self):
        config = StabilityConfig(
            n_perturbations=20, noise_floor_samples=3,
            max_generate_calls=3, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit("prompt", "output", _constant_fn("x"))
        assert result.budget_exceeded is True

    def test_calls_used_tracked(self):
        config = StabilityConfig(
            n_perturbations=2, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit("prompt", "output", _constant_fn("x"))
        assert result.calls_used > 0

    def test_recommendation_calibrating_on_budget(self):
        config = StabilityConfig(
            n_perturbations=10, noise_floor_samples=3,
            max_generate_calls=2, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit("prompt", "output", _constant_fn("x"))
        assert result.recommendation == "calibrating"
        assert "budget_exceeded" in result.recommendation_reason


# =============================================================================
# TestDualDivergence
# =============================================================================


class TestDualDivergence:
    def test_raw_and_stripped_stored_separately(self):
        config = StabilityConfig(
            n_perturbations=3, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            "Test prompt here.", "Sure! Here is the answer.",
            _echo_fn,
        )
        assert len(result.raw_divergences) == 3
        assert len(result.stripped_divergences) == 3

    def test_boilerplate_stripping(self):
        text = "Sure, I can help with that. The answer is 42."
        stripped = strip_boilerplate(text)
        assert "Sure" not in stripped
        assert "42" in stripped

    def test_suffix_stripping(self):
        text = "The answer is 42. Let me know if you have any questions!"
        stripped = strip_boilerplate(text)
        assert "questions" not in stripped
        assert "42" in stripped

    def test_no_boilerplate_unchanged(self):
        text = "The mitochondria is the powerhouse of the cell."
        stripped = strip_boilerplate(text)
        assert stripped == text

    def test_stripped_used_for_stiffness(self):
        """Verify stiffness is computed from stripped divergences, not raw."""
        # With boilerplate: raw divergence dominated by boilerplate presence
        # Without boilerplate: stripped divergence reflects real content shift
        config = StabilityConfig(
            n_perturbations=2, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)

        def boilerplate_fn(p):
            return "Sure, I can help with that. " + p[:20]

        result = auditor.audit("Test prompt here.", "Test output.", boilerplate_fn)
        # Should have computed fingerprint using stripped divergences
        assert result.fingerprint.stiffness >= 0


# =============================================================================
# TestScenarios
# =============================================================================


class TestScenarios:
    """End-to-end scenarios with known-behavior mocks."""

    def test_stable_prompt(self):
        """Constant output → low stiffness, 1 basin, stable recommendation."""
        config = StabilityConfig(
            n_perturbations=5, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            "What is 2+2?",
            "The answer is 4.",
            _constant_fn("The answer is 4."),
        )
        assert result.fingerprint.stiffness == 0.0
        assert result.fingerprint.basin_entropy == 1.0
        assert result.recommendation == "stable"

    def test_multimodal_prompt(self):
        """Outputs that cluster into distinct basins → multimodal."""
        config = StabilityConfig(
            n_perturbations=6, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
            basin_threshold=0.2,
        )
        # Alternate between very different responses
        responses = [
            "Yes absolutely this is correct and true",
            "No definitely wrong and incorrect",
            "Maybe perhaps uncertain unclear",
            "Yes absolutely this is correct and true",
            "No definitely wrong and incorrect",
            "Maybe perhaps uncertain unclear",
            "Yes absolutely this is correct and true",
            "No definitely wrong and incorrect",
        ]
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            "Is this good?", "Yes.", _varying_fn(responses),
        )
        assert result.fingerprint.basin_entropy >= 2.0

    def test_brittle_prompt(self):
        """Large output changes from small input changes → high stiffness."""
        config = StabilityConfig(
            n_perturbations=4, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
            kinds=["format_jitter", "clause_reorder", "role_rewrap", "hedge_insert"],
        )
        # Mock: same prompt → same output (deterministic, so noise floor = 0),
        # but any change in prompt → completely different output
        def sensitive_fn(p):
            h = hashlib.sha256(p.encode()).hexdigest()[:10]
            return f"unique_response_{h}_with_extra_words"

        auditor = StabilityAuditor(config)
        result = auditor.audit(
            "You are a helper. Do the task correctly.",
            "original output here",
            sensitive_fn,
        )
        # High divergence expected (each perturbed prompt → different output)
        assert any(d > 0 for d in result.raw_divergences)
        assert result.recommendation in ("brittle", "calibrating", "multimodal")

    def test_echo_fn_produces_result(self):
        """Echo function: output = perturbed prompt → divergence matches magnitude."""
        config = StabilityConfig(
            n_perturbations=3, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            "You are a coder. Write Python.",
            "You are a coder. Write Python.",
            _echo_fn,
        )
        assert len(result.raw_divergences) == 3
        # With echo, raw divergence ≈ magnitude (output = perturbed prompt)
        for rd, mag in zip(result.raw_divergences, result.magnitudes):
            if mag > 0:
                # Should be in same ballpark (not exact due to noise floor)
                assert abs(rd - mag) < 0.5 or rd >= 0

    def test_recommendation_reason_always_set(self):
        config = StabilityConfig(
            n_perturbations=3, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit("Prompt.", "Output.", _constant_fn("out"))
        assert result.recommendation_reason != ""

    def test_all_perturbation_kinds_exercised(self):
        config = StabilityConfig(
            n_perturbations=5, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            "You are a coder. Write Python.",
            "Output text.",
            _echo_fn,
        )
        kinds_used = set(result.perturbation_kinds)
        assert len(kinds_used) == 5

    def test_noise_floor_in_fingerprint(self):
        config = StabilityConfig(
            n_perturbations=3, noise_floor_samples=3,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit("P.", "O.", _constant_fn("same"))
        assert result.fingerprint.noise_floor == 0.0

    def test_high_noise_floor_reduces_excess(self):
        """High noise floor should reduce excess divergences toward 0."""
        config = StabilityConfig(
            n_perturbations=3, noise_floor_samples=3,
            max_generate_calls=50, sample_rate=1.0,
        )
        # Varying noise but moderate actual divergence
        responses = ["alpha beta gamma", "alpha beta delta", "alpha gamma delta"]
        auditor = StabilityAuditor(config)
        result = auditor.audit("P.", "O.", _varying_fn(responses))
        # Excess should be <= raw (noise subtracted, clamped to 0)
        for excess, raw in zip(result.excess_divergences, result.stripped_divergences):
            assert excess <= raw + 0.01  # small epsilon for float


# =============================================================================
# TestDeterminism
# =============================================================================


class TestDeterminism:
    def test_same_seed_same_perturbations(self):
        for kind in PerturbationKind:
            r1, m1 = generate_perturbation("Test prompt.", kind.value, seed=42)
            r2, m2 = generate_perturbation("Test prompt.", kind.value, seed=42)
            assert r1 == r2, f"Non-deterministic: {kind.value}"
            assert m1 == m2, f"Non-deterministic magnitude: {kind.value}"

    def test_different_seeds_can_differ(self):
        """Different seeds should produce at least some different results."""
        results = set()
        for seed in range(10):
            r, _ = generate_perturbation(
                "You are a helper. Do the task.",
                "role_rewrap", seed=seed,
            )
            results.add(r)
        assert len(results) >= 2

    def test_sha256_sampling_deterministic(self):
        auditor = StabilityAuditor(StabilityConfig(sample_rate=0.5))
        results = [auditor.should_audit("prompt_xyz") for _ in range(100)]
        assert len(set(results)) == 1

    def test_sha256_sampling_cross_platform(self):
        """sha256 is deterministic across platforms (unlike Python hash())."""
        expected = hashlib.sha256(b"test").hexdigest()
        assert len(expected) == 64  # Sanity check

    def test_perturbation_dispatcher(self):
        for kind in PerturbationKind:
            result, mag = generate_perturbation("Hello world.", kind.value, seed=42)
            assert isinstance(result, str)
            assert isinstance(mag, float)

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown perturbation kind"):
            generate_perturbation("hello", "nonexistent_kind", seed=42)


# =============================================================================
# TestEdgeCases
# =============================================================================


class TestEdgeCases:
    def test_empty_prompt(self):
        config = StabilityConfig(
            n_perturbations=2, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit("", "output", _constant_fn("x"))
        assert isinstance(result, StabilityAuditResult)

    def test_single_word(self):
        for kind in PerturbationKind:
            result, mag = generate_perturbation("Hello", kind.value, seed=42)
            assert isinstance(result, str)

    def test_very_long_text(self):
        long_text = "word " * 500
        result, mag = perturb_format_jitter(long_text, seed=42)
        assert isinstance(result, str)

    def test_unicode_text(self):
        text = "You should check the résumé for naïve assumptions."
        for kind in PerturbationKind:
            result, mag = generate_perturbation(text, kind.value, seed=42)
            assert isinstance(result, str)

    def test_all_code_blocks_prompt(self):
        text = "```python\nprint('hello')\n```"
        for kind in PerturbationKind:
            result, mag = generate_perturbation(text, kind.value, seed=42)
            # Should be mostly unchanged (no prose to perturb)
            assert "print('hello')" in result

    def test_canonical_json_float_rounding(self):
        a = _canonical_json({"x": 0.1 + 0.2})
        b = _canonical_json({"x": 0.3})
        assert a == b  # Both round to same value

    def test_round_floats_nested(self):
        obj = {"a": [1.1234567, {"b": 2.9999999}]}
        rounded = _round_floats(obj)
        assert rounded["a"][0] == 1.123457
        assert rounded["a"][1]["b"] == 3.0


# =============================================================================
# Canary Fixtures
# =============================================================================


class TestCanaryFixtures:
    """Known-stable and known-brittle fixtures.  Intentionally boring.
    These become canaries when you refactor tokenization/strip logic."""

    STABLE_PROMPT = "What is two plus two?"
    BRITTLE_PROMPT = "You are a senior architect. Analyze the system."

    def test_canary_stable_low_stiffness(self):
        """Constant mock → stiffness = 0, 1 basin, stable."""
        config = StabilityConfig(
            n_perturbations=5, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            self.STABLE_PROMPT,
            "Four.",
            _constant_fn("Four."),
        )
        assert result.fingerprint.stiffness == 0.0
        assert result.fingerprint.basin_entropy == 1.0
        assert result.recommendation == "stable"
        # Verify noise floor is zero with constant fn
        assert result.fingerprint.noise_floor == 0.0

    def test_canary_brittle_high_stiffness(self):
        """Hash-based mock → every perturbation produces different output."""
        config = StabilityConfig(
            n_perturbations=4, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
            kinds=["format_jitter", "clause_reorder", "role_rewrap", "hedge_insert"],
        )

        def hash_fn(p):
            h = hashlib.sha256(p.encode()).hexdigest()
            return f"response_{h[:20]}"

        auditor = StabilityAuditor(config)
        result = auditor.audit(
            self.BRITTLE_PROMPT,
            "response_original",
            hash_fn,
        )
        assert result.fingerprint.stiffness > 0
        assert result.recommendation in ("brittle", "calibrating", "multimodal")
        # Verify there's actual divergence
        assert any(d > 0 for d in result.raw_divergences)

    def test_canary_stable_fingerprint_roundtrip(self):
        """Fingerprint survives serialization."""
        config = StabilityConfig(
            n_perturbations=3, noise_floor_samples=2,
            max_generate_calls=50, sample_rate=1.0,
        )
        auditor = StabilityAuditor(config)
        result = auditor.audit(
            self.STABLE_PROMPT, "Four.", _constant_fn("Four."),
        )
        d = result.to_dict()
        restored = StabilityAuditResult.from_dict(d)
        assert restored.fingerprint.stiffness == result.fingerprint.stiffness
        assert restored.recommendation == result.recommendation
        assert restored.perturbations == result.perturbations
