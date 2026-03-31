# SPDX-License-Identifier: Apache-2.0
"""Tests for Policy IR: control slots, vocabulary, renderers, validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.policy_ir import (
    CORE_VOCAB,
    ControlSlot,
    ControlVocabulary,
    MinimalRenderer,
    PolicyIRError,
    ProseRenderer,
    SlotSet,
    build_vocab,
    hash_slot_set,
    hash_vocab,
    make_slot_set,
    mode_slot_set,
    validate_slot_set,
)

FIXTURES = Path(__file__).parent / "fixtures" / "policy_ir"


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

class TestControlVocabulary:
    def test_all_slot_ids_unique(self):
        ids = [s.slot_id for s in CORE_VOCAB.slots]
        assert len(ids) == len(set(ids))

    def test_content_hash_deterministic(self):
        h1 = hash_vocab(CORE_VOCAB)
        h2 = hash_vocab(CORE_VOCAB)
        assert h1 == h2

    def test_content_hash_starts_with_sha256(self):
        assert CORE_VOCAB.content_hash.startswith("sha256:")

    def test_hash_excludes_description(self):
        """Changing description must NOT change vocab hash."""
        slot = ControlSlot("TEST", "behavioral", "original desc")
        v1 = build_vocab("test", "0.1", (slot,))

        slot2 = ControlSlot("TEST", "behavioral", "changed desc")
        v2 = build_vocab("test", "0.1", (slot2,))

        assert v1.content_hash == v2.content_hash

    def test_hash_includes_category(self):
        """Changing category MUST change vocab hash."""
        slot = ControlSlot("TEST", "behavioral", "desc")
        v1 = build_vocab("test", "0.1", (slot,))

        slot2 = ControlSlot("TEST", "epistemic", "desc")
        v2 = build_vocab("test", "0.1", (slot2,))

        assert v1.content_hash != v2.content_hash

    def test_slot_by_id_found(self):
        assert CORE_VOCAB.slot_by_id("GOVERNANCE_INVISIBLE") is not None

    def test_slot_by_id_not_found(self):
        assert CORE_VOCAB.slot_by_id("NONEXISTENT") is None

    def test_vocab_is_frozen(self):
        with pytest.raises(AttributeError):
            CORE_VOCAB.version = "999"  # type: ignore[misc]

    def test_core_vocab_has_22_slots(self):
        assert len(CORE_VOCAB.slots) == 22


# ---------------------------------------------------------------------------
# SlotSet
# ---------------------------------------------------------------------------

class TestSlotSet:
    def test_make_deduplicates_active(self):
        ss = make_slot_set("v", ("A", "B", "A", "C"))
        assert ss.active == ("A", "B", "C")

    def test_make_preserves_order(self):
        ss = make_slot_set("v", ("C", "A", "B"))
        assert ss.active == ("C", "A", "B")

    def test_make_sorts_parameters(self):
        ss = make_slot_set("v", ("A",), [("z", "1"), ("a", "2")])
        assert ss.parameters == (("a", "2"), ("z", "1"))

    def test_hash_deterministic(self):
        ss = make_slot_set("v", ("A", "B"), [("k", "v")])
        h1 = hash_slot_set(ss)
        h2 = hash_slot_set(ss)
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_different_order_different_hash(self):
        ss1 = make_slot_set("v", ("A", "B"))
        ss2 = make_slot_set("v", ("B", "A"))
        assert hash_slot_set(ss1) != hash_slot_set(ss2)

    def test_slot_set_is_frozen(self):
        ss = make_slot_set("v", ("A",))
        with pytest.raises(AttributeError):
            ss.active = ("B",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_slot_set_passes(self):
        ss = mode_slot_set("code")
        assert ss is not None
        validate_slot_set(ss, CORE_VOCAB)  # should not raise

    def test_unknown_slot_raises(self):
        ss = make_slot_set(CORE_VOCAB.vocab_id, ("NONEXISTENT",))
        with pytest.raises(PolicyIRError, match="Unknown slot"):
            validate_slot_set(ss, CORE_VOCAB)

    def test_vocab_mismatch_raises(self):
        ss = make_slot_set("wrong_vocab", ("GOVERNANCE_INVISIBLE",))
        with pytest.raises(PolicyIRError, match="Vocab ID mismatch"):
            validate_slot_set(ss, CORE_VOCAB)

    def test_missing_required_param_raises(self):
        ss = make_slot_set(
            CORE_VOCAB.vocab_id,
            ("AFFECT_REGIME_AWARE",),
            # no regime param
        )
        with pytest.raises(PolicyIRError, match="requires parameter"):
            validate_slot_set(ss, CORE_VOCAB)

    def test_required_param_provided_passes(self):
        ss = make_slot_set(
            CORE_VOCAB.vocab_id,
            ("AFFECT_REGIME_AWARE",),
            [("regime", "comedy")],
        )
        validate_slot_set(ss, CORE_VOCAB)  # should not raise

    def test_duplicate_detection(self):
        # Force duplicates by bypassing make_slot_set
        ss = SlotSet(
            vocab_id=CORE_VOCAB.vocab_id,
            active=("GOVERNANCE_INVISIBLE", "GOVERNANCE_INVISIBLE"),
        )
        with pytest.raises(PolicyIRError, match="Duplicate"):
            validate_slot_set(ss, CORE_VOCAB)


# ---------------------------------------------------------------------------
# Mode composition
# ---------------------------------------------------------------------------

class TestModeSlotSet:
    def test_unknown_mode_returns_none(self):
        assert mode_slot_set("nonexistent") is None

    def test_fiction_has_global_baseline(self):
        ss = mode_slot_set("fiction", regime="neutral")
        assert ss is not None
        assert "GOVERNANCE_INVISIBLE" in ss.active
        assert "EXIT_CLEAN" in ss.active
        assert "EVIDENCE_REQUIRED" in ss.active

    def test_fiction_has_mode_slots(self):
        ss = mode_slot_set("fiction", regime="neutral")
        assert ss is not None
        assert "CANON_AUTHORITY_BOUNDARY" in ss.active
        assert "AFFECT_REGIME_AWARE" in ss.active

    def test_code_has_global_baseline(self):
        ss = mode_slot_set("code")
        assert ss is not None
        assert "GOVERNANCE_INVISIBLE" in ss.active

    def test_code_has_mode_slots(self):
        ss = mode_slot_set("code")
        assert ss is not None
        assert "ARCHITECTURAL_COHERENCE" in ss.active
        assert "EPISTEMIC_CARE" in ss.active

    def test_nonfiction_has_mode_slots(self):
        ss = mode_slot_set("nonfiction")
        assert ss is not None
        assert "CLAIM_TAXONOMY" in ss.active
        assert "CLAIM_VELOCITY" in ss.active

    def test_research_has_mode_slots(self):
        ss = mode_slot_set("research")
        assert ss is not None
        assert "EPISTEMIC_DEBT_TRACKING" in ss.active
        assert "SOURCE_DISCIPLINE" in ss.active

    def test_fiction_regime_param(self):
        ss = mode_slot_set("fiction", regime="comedy")
        assert ss is not None
        assert ("regime", "comedy") in ss.parameters

    def test_all_modes_validate(self):
        for mode in ("fiction", "code", "nonfiction", "research"):
            params = {"regime": "neutral"} if mode == "fiction" else {}
            ss = mode_slot_set(mode, **params)
            assert ss is not None
            validate_slot_set(ss, CORE_VOCAB)


# ---------------------------------------------------------------------------
# ProseRenderer — byte-identical to incumbent
# ---------------------------------------------------------------------------

class TestProseRenderer:
    renderer = ProseRenderer()

    def test_fiction_matches_fixture(self):
        ss = mode_slot_set("fiction", regime="neutral")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        expected = (FIXTURES / "fiction.txt").read_text()
        assert result.text == expected

    def test_code_matches_fixture(self):
        ss = mode_slot_set("code")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        expected = (FIXTURES / "code.txt").read_text()
        assert result.text == expected

    def test_nonfiction_matches_fixture(self):
        ss = mode_slot_set("nonfiction")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        expected = (FIXTURES / "nonfiction.txt").read_text()
        assert result.text == expected

    def test_research_matches_fixture(self):
        ss = mode_slot_set("research")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        expected = (FIXTURES / "research_base.txt").read_text()
        assert result.text == expected

    def test_fiction_with_comedy_regime(self):
        ss = mode_slot_set("fiction", regime="comedy")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        assert "Current regime: comedy." in result.text

    def test_render_result_provenance(self):
        ss = mode_slot_set("code")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        assert result.renderer_id == "prose_v1"
        assert result.renderer_version == "0.1.0"
        assert result.vocab_id == "governor_core_v1"
        assert result.vocab_version == "0.1.0"
        assert result.vocab_hash == CORE_VOCAB.content_hash
        assert result.slot_set_hash.startswith("sha256:")
        assert result.content_hash.startswith("sha256:")
        assert len(result.slots_rendered) > 0


# ---------------------------------------------------------------------------
# MinimalRenderer — grammar compliance
# ---------------------------------------------------------------------------

class TestMinimalRenderer:
    renderer = MinimalRenderer()

    def test_code_output(self):
        ss = mode_slot_set("code")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        # Control line is first line, semicolon-delimited, lowercase
        control_line = result.text.split("\n")[0]
        assert ";" in control_line
        assert control_line.islower()
        assert " " not in control_line

    def test_code_has_output_expansion(self):
        ss = mode_slot_set("code")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        # Code mode has PATCH_OVER_ESSAY + OUTPUT_DISCIPLINE → expansion line
        assert "\n" in result.text
        expansion = result.text.split("\n", 1)[1]
        assert "code" in expansion.lower() or "diff" in expansion.lower() or "patch" in expansion.lower()

    def test_fiction_with_params(self):
        ss = mode_slot_set("fiction", regime="comedy")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        assert "affect_regime_aware(regime=comedy)" in result.text

    def test_all_tokens_valid_grammar(self):
        """Every token on the control line matches SLOT_ID or SLOT_ID(params)."""
        import re
        token_re = re.compile(r"^[a-z_]+(\([a-z_]+=[a-z0-9_]+(,[a-z_]+=[a-z0-9_]+)*\))?$")

        for mode in ("fiction", "code", "nonfiction", "research"):
            params = {"regime": "neutral"} if mode == "fiction" else {}
            ss = mode_slot_set(mode, **params)
            assert ss is not None
            result = self.renderer.render(ss, CORE_VOCAB)
            control_line = result.text.split("\n")[0]
            for token in control_line.split(";"):
                assert token_re.match(token), f"Invalid token in {mode}: {token!r}"

    def test_render_result_provenance(self):
        ss = mode_slot_set("code")
        assert ss is not None
        result = self.renderer.render(ss, CORE_VOCAB)
        assert result.renderer_id == "minimal_v1"
        assert result.renderer_version == "0.2.0"
        assert result.vocab_hash == CORE_VOCAB.content_hash

    def test_missing_param_raises(self):
        ss = make_slot_set(
            CORE_VOCAB.vocab_id,
            ("AFFECT_REGIME_AWARE",),
        )
        with pytest.raises(PolicyIRError, match="requires parameter"):
            self.renderer.render(ss, CORE_VOCAB)


# ---------------------------------------------------------------------------
# Completeness — every mode slot renderable by both renderers
# ---------------------------------------------------------------------------

class TestCompleteness:
    def test_all_modes_renderable_by_prose(self):
        renderer = ProseRenderer()
        for mode in ("fiction", "code", "nonfiction", "research"):
            params = {"regime": "neutral"} if mode == "fiction" else {}
            ss = mode_slot_set(mode, **params)
            assert ss is not None
            result = renderer.render(ss, CORE_VOCAB)
            assert result.text  # non-empty

    def test_all_modes_renderable_by_minimal(self):
        renderer = MinimalRenderer()
        for mode in ("fiction", "code", "nonfiction", "research"):
            params = {"regime": "neutral"} if mode == "fiction" else {}
            ss = mode_slot_set(mode, **params)
            assert ss is not None
            result = renderer.render(ss, CORE_VOCAB)
            assert result.text  # non-empty

    def test_same_slot_set_same_hash(self):
        """Same inputs → same content hash, regardless of renderer."""
        ss = mode_slot_set("code")
        assert ss is not None
        prose = ProseRenderer().render(ss, CORE_VOCAB)
        # Content hashes differ (different text), but slot_set_hash is same
        minimal = MinimalRenderer().render(ss, CORE_VOCAB)
        assert prose.slot_set_hash == minimal.slot_set_hash
        assert prose.content_hash != minimal.content_hash
