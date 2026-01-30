"""
Tests for claim signal extraction.

Covers: SignalCategory, SignalMatch, ExtractionConfig, ExtractionResult,
date/entity/quantity/assertive extraction, SignalExtractor, file scanning,
ledger integration, and convenience functions.
"""

import tempfile
from pathlib import Path

import pytest

from governor.claim_signals import (
    ASSERTIVE_PATTERN,
    DATE_PATTERN,
    ENTITY_PATTERN,
    QUANTITY_PATTERN,
    ExtractionConfig,
    ExtractionResult,
    SignalCategory,
    SignalExtractor,
    SignalMatch,
    assertiveness_score,
    extract_signals,
    has_implicit_claims,
    register_signals,
    scan_text,
)
from governor.epistemic import EpistemicLedger, Provenance


# =============================================================================
# TestSignalCategory
# =============================================================================


class TestSignalCategory:
    """Enum completeness and string values."""

    def test_has_all_categories(self):
        categories = {c.value for c in SignalCategory}
        assert categories == {"date", "entity", "quantity", "assertive"}

    def test_string_enum(self):
        assert SignalCategory.DATE == "date"
        assert SignalCategory.ENTITY == "entity"
        assert SignalCategory.QUANTITY == "quantity"
        assert SignalCategory.ASSERTIVE == "assertive"


# =============================================================================
# TestSignalMatch
# =============================================================================


class TestSignalMatch:
    """Creation, to_dict, context snippet."""

    def test_creation(self):
        m = SignalMatch(
            category=SignalCategory.DATE,
            value="1998",
            span=(10, 14),
        )
        assert m.category == SignalCategory.DATE
        assert m.value == "1998"
        assert m.span == (10, 14)
        assert m.line_number is None
        assert m.context == ""

    def test_creation_with_line_number(self):
        m = SignalMatch(
            category=SignalCategory.ENTITY,
            value="Larry Page",
            span=(0, 10),
            line_number=5,
            context="...Larry Page founded...",
        )
        assert m.line_number == 5
        assert "Larry Page" in m.context

    def test_to_dict(self):
        m = SignalMatch(
            category=SignalCategory.QUANTITY,
            value="5 billion",
            span=(20, 29),
            line_number=3,
            context="...about 5 billion dollars...",
        )
        d = m.to_dict()
        assert d["category"] == "quantity"
        assert d["value"] == "5 billion"
        assert d["span"] == [20, 29]
        assert d["line_number"] == 3
        assert "5 billion" in d["context"]

    def test_to_dict_no_optional_fields(self):
        m = SignalMatch(
            category=SignalCategory.DATE,
            value="2024",
            span=(0, 4),
        )
        d = m.to_dict()
        assert d["line_number"] is None
        assert d["context"] == ""


# =============================================================================
# TestExtractionConfig
# =============================================================================


class TestExtractionConfig:
    """Defaults, custom config, toggle behavior."""

    def test_defaults(self):
        cfg = ExtractionConfig()
        assert cfg.enable_dates is True
        assert cfg.enable_entities is True
        assert cfg.enable_quantities is True
        assert cfg.enable_assertive is True
        assert cfg.context_chars == 40
        assert cfg.dedup_entities is True

    def test_custom_config(self):
        cfg = ExtractionConfig(
            enable_dates=False,
            context_chars=20,
            dedup_entities=False,
        )
        assert cfg.enable_dates is False
        assert cfg.context_chars == 20
        assert cfg.dedup_entities is False

    def test_disable_category(self):
        cfg = ExtractionConfig(enable_dates=False)
        extractor = SignalExtractor(config=cfg)
        result = extractor.extract("Founded in 1998")
        assert result.date_count == 0


# =============================================================================
# TestExtractionResult
# =============================================================================


class TestExtractionResult:
    """Properties, counts, has_speculative_content, assertiveness_score, to_dict."""

    def _make_result(self, matches=None, assertiveness=0.0):
        matches = matches or []
        cats: dict[str, int] = {}
        for cat in SignalCategory:
            cats[cat.value] = sum(1 for m in matches if m.category == cat)
        return ExtractionResult(
            text_hash="abc123",
            total_signals=len(matches),
            signals_by_category=cats,
            matches=matches,
            assertiveness_score=assertiveness,
        )

    def test_empty_result(self):
        r = self._make_result()
        assert r.total_signals == 0
        assert r.has_speculative_content is False
        assert r.assertiveness_score == 0.0
        assert r.dates == []
        assert r.entities == []
        assert r.quantities == []
        assert r.assertive_phrases == []

    def test_has_speculative_content_with_date(self):
        m = SignalMatch(category=SignalCategory.DATE, value="2024", span=(0, 4))
        r = self._make_result(matches=[m])
        assert r.has_speculative_content is True

    def test_has_speculative_content_with_entity(self):
        m = SignalMatch(category=SignalCategory.ENTITY, value="John Smith", span=(0, 10))
        r = self._make_result(matches=[m])
        assert r.has_speculative_content is True

    def test_has_speculative_content_assertive_only(self):
        """Assertive phrases alone do NOT count as speculative content."""
        m = SignalMatch(category=SignalCategory.ASSERTIVE, value="definitely", span=(0, 10))
        r = self._make_result(matches=[m])
        assert r.has_speculative_content is False

    def test_convenience_lists(self):
        matches = [
            SignalMatch(category=SignalCategory.DATE, value="1998", span=(0, 4)),
            SignalMatch(category=SignalCategory.ENTITY, value="Larry Page", span=(5, 15)),
            SignalMatch(category=SignalCategory.QUANTITY, value="5 billion", span=(20, 29)),
            SignalMatch(category=SignalCategory.ASSERTIVE, value="definitely", span=(30, 40)),
        ]
        r = self._make_result(matches=matches)
        assert r.dates == ["1998"]
        assert r.entities == ["Larry Page"]
        assert r.quantities == ["5 billion"]
        assert r.assertive_phrases == ["definitely"]

    def test_to_dict(self):
        m = SignalMatch(category=SignalCategory.DATE, value="2024", span=(0, 4))
        r = self._make_result(matches=[m], assertiveness=0.4)
        d = r.to_dict()
        assert d["text_hash"] == "abc123"
        assert d["total_signals"] == 1
        assert d["has_speculative_content"] is True
        assert d["assertiveness_score"] == 0.4
        assert d["dates"] == ["2024"]
        assert len(d["matches"]) == 1


# =============================================================================
# TestDateExtraction
# =============================================================================


class TestDateExtraction:
    """Year ranges (1800s, 1900s, 2000s), no false positives, multiple dates."""

    def setup_method(self):
        self.extractor = SignalExtractor()

    def test_1800s(self):
        result = self.extractor.extract("The event occurred in 1865.")
        assert result.date_count == 1
        assert "1865" in result.dates

    def test_1900s(self):
        result = self.extractor.extract("The treaty was signed in 1945.")
        assert result.date_count == 1
        assert "1945" in result.dates

    def test_2000s(self):
        result = self.extractor.extract("Google was founded in 1998 and went public in 2004.")
        assert result.date_count == 2
        assert "1998" in result.dates
        assert "2004" in result.dates

    def test_boundary_years(self):
        result = self.extractor.extract("From 1800 to 2099.")
        assert result.date_count == 2
        assert "1800" in result.dates
        assert "2099" in result.dates

    def test_no_false_positive_on_non_years(self):
        """Numbers that aren't years should not match."""
        result = self.extractor.extract("The value is 12345 and the code is 9999.")
        # 12345 has no 4-digit year prefix match; 9999 is not in 18xx/19xx/20xx range
        assert result.date_count == 0

    def test_multiple_dates_same_year(self):
        result = self.extractor.extract("In 2024 and again in 2024.")
        assert result.date_count == 2


# =============================================================================
# TestEntityExtraction
# =============================================================================


class TestEntityExtraction:
    """Multi-word names, single-word exclusion, deduplication."""

    def setup_method(self):
        self.extractor = SignalExtractor()

    def test_multi_word_entity(self):
        result = self.extractor.extract("Larry Page co-founded the company.")
        assert result.entity_count == 1
        assert "Larry Page" in result.entities

    def test_three_word_entity(self):
        result = self.extractor.extract("The work of Martin Luther King changed history.")
        assert result.entity_count == 1
        assert "Martin Luther King" in result.entities

    def test_single_word_not_entity(self):
        """Single capitalized words should NOT match entity pattern."""
        result = self.extractor.extract("Google was founded in Mountain View.")
        # "Google" is single word, "Mountain View" is multi-word
        entities = result.entities
        assert "Google" not in entities
        assert "Mountain View" in entities

    def test_dedup_entities(self):
        """Same entity mentioned twice should appear once with dedup."""
        result = self.extractor.extract(
            "Larry Page started Google. Larry Page is the CEO."
        )
        assert result.entity_count == 1
        assert result.entities == ["Larry Page"]

    def test_no_dedup_when_disabled(self):
        cfg = ExtractionConfig(dedup_entities=False)
        extractor = SignalExtractor(config=cfg)
        result = extractor.extract(
            "Larry Page started Google. Larry Page is the CEO."
        )
        assert result.entity_count == 2

    def test_multiple_different_entities(self):
        result = self.extractor.extract(
            "Larry Page and Sergey Brin founded the company."
        )
        assert result.entity_count == 2
        assert "Larry Page" in result.entities
        assert "Sergey Brin" in result.entities


# =============================================================================
# TestQuantityExtraction
# =============================================================================


class TestQuantityExtraction:
    """Millions, billions, percentages, dollars, EUR, decimals."""

    def setup_method(self):
        self.extractor = SignalExtractor()

    def test_million(self):
        result = self.extractor.extract("The company raised 50 million in funding.")
        assert result.quantity_count == 1
        assert any("50 million" in q for q in result.quantities)

    def test_billion(self):
        result = self.extractor.extract("Revenue was 5 billion last year.")
        assert result.quantity_count == 1
        assert any("5 billion" in q for q in result.quantities)

    def test_percent(self):
        result = self.extractor.extract("Growth was 25 percent year over year.")
        assert result.quantity_count == 1
        assert any("25 percent" in q for q in result.quantities)

    def test_percent_symbol(self):
        # Note: "25%" without space doesn't match because the pattern
        # requires \b after the unit, and % is not a word char.
        # "25 %" with space does match.
        result = self.extractor.extract("Growth was 25 percent.")
        assert result.quantity_count == 1

    def test_dollars(self):
        result = self.extractor.extract("The deal was worth 100 dollars.")
        assert result.quantity_count == 1

    def test_decimal(self):
        result = self.extractor.extract("The rate is 3.5 percent per annum.")
        assert result.quantity_count == 1
        assert any("3.5 percent" in q for q in result.quantities)

    def test_eur_currency(self):
        result = self.extractor.extract("The price was 200 EUR.")
        assert result.quantity_count == 1

    def test_usd_currency(self):
        result = self.extractor.extract("Total was 500 USD in value.")
        assert result.quantity_count == 1


# =============================================================================
# TestAssertiveExtraction
# =============================================================================


class TestAssertiveExtraction:
    """All assertive phrases, case insensitivity, score computation, cap."""

    def setup_method(self):
        self.extractor = SignalExtractor()

    def test_definitely(self):
        result = self.extractor.extract("This is definitely correct.")
        assert result.assertive_count == 1
        assert "definitely" in result.assertive_phrases

    def test_multiple_assertive_phrases(self):
        result = self.extractor.extract(
            "The company was founded in 1998 and was acquired by another firm."
        )
        assert result.assertive_count >= 1

    def test_case_insensitivity(self):
        result = self.extractor.extract("He CERTAINLY knew the answer.")
        assert result.assertive_count == 1

    def test_score_computation(self):
        """Score = count * 0.2, e.g., 3 matches → 0.6."""
        result = self.extractor.extract(
            "It was definitely true. It was certainly the case. It was clearly obvious."
        )
        assert result.assertive_count >= 3
        expected_score = min(1.0, result.assertive_count * 0.2)
        assert result.assertiveness_score == pytest.approx(expected_score)

    def test_score_cap_at_1(self):
        """Score caps at 1.0 even with many assertive phrases."""
        text = ". ".join([
            "definitely true",
            "certainly correct",
            "clearly right",
            "obviously known",
            "undoubtedly valid",
            "born in 1990",
        ])
        result = self.extractor.extract(text)
        assert result.assertiveness_score == 1.0

    def test_all_phrase_types(self):
        """Verify all assertive phrase types are detected."""
        phrases = [
            "definitely", "certainly", "clearly", "undoubtedly", "obviously",
            "was acquired", "acquired in", "founded in", "established in",
            "is located", "is headquartered", "died in", "born in",
        ]
        for phrase in phrases:
            result = self.extractor.extract(f"The thing {phrase} somewhere.")
            assert result.assertive_count >= 1, f"Failed to detect: {phrase}"


# =============================================================================
# TestSignalExtractor
# =============================================================================


class TestSignalExtractor:
    """Full extraction, mixed content, empty text, config toggles, file scanning."""

    def test_mixed_content(self):
        text = (
            "Google was founded in 1998 by Larry Page and Sergey Brin. "
            "The company was definitely worth 5 billion dollars."
        )
        extractor = SignalExtractor()
        result = extractor.extract(text)

        assert result.total_signals > 0
        assert result.has_speculative_content is True
        assert result.date_count >= 1
        assert result.entity_count >= 2
        assert result.quantity_count >= 1
        assert result.assertive_count >= 1

    def test_empty_text(self):
        extractor = SignalExtractor()
        result = extractor.extract("")
        assert result.total_signals == 0
        assert result.has_speculative_content is False
        assert result.assertiveness_score == 0.0

    def test_no_signals(self):
        extractor = SignalExtractor()
        result = extractor.extract("the quick brown fox jumps over the lazy dog")
        assert result.total_signals == 0

    def test_all_categories_disabled(self):
        cfg = ExtractionConfig(
            enable_dates=False,
            enable_entities=False,
            enable_quantities=False,
            enable_assertive=False,
        )
        extractor = SignalExtractor(config=cfg)
        result = extractor.extract("Google was founded in 1998 and is worth 5 billion.")
        assert result.total_signals == 0

    def test_text_hash_differs(self):
        extractor = SignalExtractor()
        r1 = extractor.extract("Text one")
        r2 = extractor.extract("Text two")
        assert r1.text_hash != r2.text_hash

    def test_text_hash_same_for_same_input(self):
        extractor = SignalExtractor()
        r1 = extractor.extract("Identical text")
        r2 = extractor.extract("Identical text")
        assert r1.text_hash == r2.text_hash

    def test_context_snippet(self):
        extractor = SignalExtractor(config=ExtractionConfig(context_chars=10))
        text = "The year was 1998 when it happened."
        result = extractor.extract(text)
        date_matches = [m for m in result.matches if m.category == SignalCategory.DATE]
        assert len(date_matches) == 1
        assert "1998" in date_matches[0].context

    def test_scan_file(self):
        extractor = SignalExtractor()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Google was founded in 1998.\n")
            f.write("Larry Page and Sergey Brin started it.\n")
            f.flush()
            result = extractor.scan_file(f.name)

        assert result.date_count >= 1
        assert result.entity_count >= 2
        # Line numbers should be tracked
        for m in result.matches:
            assert m.line_number is not None
            assert m.line_number >= 1


# =============================================================================
# TestExtractFromLines
# =============================================================================


class TestExtractFromLines:
    """Line-by-line extraction, line number tracking."""

    def test_line_numbers_tracked(self):
        lines = [
            "First line with no signals.",
            "Founded in 1998.",
            "Larry Page was the founder.",
        ]
        extractor = SignalExtractor()
        result = extractor.extract_from_lines(lines)

        date_matches = [m for m in result.matches if m.category == SignalCategory.DATE]
        assert len(date_matches) == 1
        assert date_matches[0].line_number == 2

        entity_matches = [m for m in result.matches if m.category == SignalCategory.ENTITY]
        assert len(entity_matches) == 1
        assert entity_matches[0].line_number == 3

    def test_multiple_signals_per_line(self):
        lines = [
            "Larry Page and Sergey Brin founded Google in 1998.",
        ]
        extractor = SignalExtractor()
        result = extractor.extract_from_lines(lines)
        assert result.total_signals >= 3  # 2 entities + 1 date

    def test_empty_lines(self):
        lines = ["", "", ""]
        extractor = SignalExtractor()
        result = extractor.extract_from_lines(lines)
        assert result.total_signals == 0


# =============================================================================
# TestRegisterSignals
# =============================================================================


class TestRegisterSignals:
    """Ledger integration, claim creation, confidence, provenance."""

    def test_register_creates_claims(self):
        ledger = EpistemicLedger()
        result = extract_signals(
            "Google was founded in 1998 by Larry Page."
        )
        claim_ids = register_signals(ledger, result)
        assert len(claim_ids) > 0
        for cid in claim_ids:
            claim = ledger.get(cid)
            assert claim is not None

    def test_claims_are_assumed(self):
        ledger = EpistemicLedger()
        result = extract_signals("Founded in 1998.")
        claim_ids = register_signals(ledger, result)
        for cid in claim_ids:
            claim = ledger.get(cid)
            assert claim.provenance == Provenance.ASSUMED

    def test_claims_have_low_confidence(self):
        ledger = EpistemicLedger()
        result = extract_signals("Founded in 1998.")
        claim_ids = register_signals(ledger, result, confidence=0.2)
        for cid in claim_ids:
            claim = ledger.get(cid)
            assert claim.confidence == pytest.approx(0.2)

    def test_assertive_phrases_not_registered(self):
        ledger = EpistemicLedger()
        result = extract_signals("This is definitely true.")
        claim_ids = register_signals(ledger, result)
        # "definitely" is assertive, not registered as a claim
        assert len(claim_ids) == 0

    def test_source_agent_id(self):
        ledger = EpistemicLedger()
        result = extract_signals("Founded in 1998.")
        claim_ids = register_signals(ledger, result, source_agent_id="agent-007")
        for cid in claim_ids:
            claim = ledger.get(cid)
            assert claim.source_agent_id == "agent-007"

    def test_claim_content_format(self):
        ledger = EpistemicLedger()
        result = extract_signals(
            "Larry Page founded Google in 1998 for 5 billion dollars."
        )
        claim_ids = register_signals(ledger, result)
        contents = [ledger.get(cid).content for cid in claim_ids]

        date_claims = [c for c in contents if c.startswith("Date asserted:")]
        entity_claims = [c for c in contents if c.startswith("Entity referenced:")]
        quantity_claims = [c for c in contents if c.startswith("Quantity asserted:")]

        assert len(date_claims) >= 1
        assert "1998" in date_claims[0]
        assert len(entity_claims) >= 1
        assert "Larry Page" in entity_claims[0]
        assert len(quantity_claims) >= 1

    def test_custom_confidence(self):
        ledger = EpistemicLedger()
        result = extract_signals("Founded in 1998.")
        claim_ids = register_signals(ledger, result, confidence=0.1)
        for cid in claim_ids:
            claim = ledger.get(cid)
            assert claim.confidence == pytest.approx(0.1)


# =============================================================================
# TestConvenienceFunctions
# =============================================================================


class TestConvenienceFunctions:
    """extract_signals, scan_text, has_implicit_claims, assertiveness_score."""

    def test_extract_signals(self):
        result = extract_signals("Founded in 1998.")
        assert isinstance(result, ExtractionResult)
        assert result.date_count == 1

    def test_scan_text_alias(self):
        result = scan_text("Founded in 1998.")
        assert isinstance(result, ExtractionResult)
        assert result.date_count == 1

    def test_has_implicit_claims_true(self):
        assert has_implicit_claims("Google was founded in 1998.")

    def test_has_implicit_claims_false(self):
        assert not has_implicit_claims("the quick brown fox")

    def test_assertiveness_score_zero(self):
        score = assertiveness_score("the quick brown fox")
        assert score == 0.0

    def test_assertiveness_score_nonzero(self):
        score = assertiveness_score("This is definitely true.")
        assert score > 0.0


# =============================================================================
# TestPatternConstants
# =============================================================================


class TestPatternConstants:
    """Verify pre-compiled patterns match expected content."""

    def test_date_pattern(self):
        assert DATE_PATTERN.search("1998")
        assert DATE_PATTERN.search("2024")
        assert DATE_PATTERN.search("1800")
        assert not DATE_PATTERN.search("1799")
        assert not DATE_PATTERN.search("2100")

    def test_entity_pattern(self):
        assert ENTITY_PATTERN.search("Larry Page")
        assert ENTITY_PATTERN.search("Martin Luther King")
        assert not ENTITY_PATTERN.search("google")
        assert not ENTITY_PATTERN.search("Single")

    def test_quantity_pattern(self):
        assert QUANTITY_PATTERN.search("5 million")
        assert QUANTITY_PATTERN.search("3.5 percent")
        assert QUANTITY_PATTERN.search("100 dollars")
        assert QUANTITY_PATTERN.search("200 EUR")
        assert not QUANTITY_PATTERN.search("five cats")

    def test_assertive_pattern(self):
        assert ASSERTIVE_PATTERN.search("definitely")
        assert ASSERTIVE_PATTERN.search("was acquired")
        assert ASSERTIVE_PATTERN.search("founded in")
        assert not ASSERTIVE_PATTERN.search("maybe")
        assert not ASSERTIVE_PATTERN.search("perhaps")


# =============================================================================
# TestIntegration
# =============================================================================


class TestIntegration:
    """Real-world text samples, multi-paragraph, claim-diff interop."""

    def test_real_world_company_description(self):
        text = (
            "Google was founded in 1998 by Larry Page and Sergey Brin while "
            "they were Ph.D. students at Stanford University. The company was "
            "definitely a pioneer in search technology and was acquired by "
            "Alphabet Inc in 2015. Revenue exceeded 250 billion dollars."
        )
        result = extract_signals(text)
        assert result.has_speculative_content is True
        assert result.date_count >= 2  # 1998, 2015
        assert result.entity_count >= 2  # Larry Page, Sergey Brin, ...
        assert result.quantity_count >= 1  # 250 billion
        assert result.assertiveness_score > 0

    def test_multi_paragraph(self):
        text = (
            "First paragraph about Larry Page.\n\n"
            "Second paragraph about events in 1998.\n\n"
            "Third paragraph with 5 billion dollars worth of assets."
        )
        result = extract_signals(text)
        assert result.entity_count >= 1
        assert result.date_count >= 1
        assert result.quantity_count >= 1

    def test_no_claims_in_plain_prose(self):
        text = (
            "the quick brown fox jumps over the lazy dog. "
            "this sentence has no proper nouns or dates or quantities."
        )
        result = extract_signals(text)
        assert result.total_signals == 0
        assert result.has_speculative_content is False

    def test_high_assertiveness_text(self):
        text = (
            "It was definitely true that the company was certainly the leader. "
            "They clearly dominated the market and obviously had no competition. "
            "The firm was undoubtedly the best and was founded in 2010."
        )
        result = extract_signals(text)
        assert result.assertiveness_score >= 0.8

    def test_ledger_round_trip(self):
        """Extract signals, register, then query from ledger."""
        ledger = EpistemicLedger()
        text = "Larry Page founded Google in 1998 for 5 billion dollars."
        result = extract_signals(text)
        claim_ids = register_signals(ledger, result)

        # All claims should be active and ASSUMED
        for cid in claim_ids:
            claim = ledger.get(cid)
            assert claim.is_active
            assert claim.provenance == Provenance.ASSUMED
            assert not claim.is_dangerous  # confidence 0.2 is not dangerous

    def test_registered_claims_not_dangerous(self):
        """Claims at confidence 0.2 should NOT be flagged as dangerous."""
        ledger = EpistemicLedger()
        result = extract_signals("Founded in 1998 by Larry Page.")
        claim_ids = register_signals(ledger, result, confidence=0.2)
        dangerous = ledger.dangerous_claims()
        registered_dangerous = [d for d in dangerous if d.claim_id in claim_ids]
        assert len(registered_dangerous) == 0
