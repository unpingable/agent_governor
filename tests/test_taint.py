"""Tests for tainted claim similarity — recurrence detection."""

import json
import pytest
from pathlib import Path

from governor.taint import (
    # Enums
    TaintType,
    FingerprintMethod,
    TaintVerdict,
    # Functions
    normalize,
    tokenize,
    fingerprint,
    score,
    # Dataclasses
    Fingerprint,
    TaintedClaim,
    TaintMatch,
    TaintCheckResult,
    TaintEvent,
    TaintConfig,
    # Class
    TaintIndex,
    # Convenience
    create_taint_index,
    check_claim,
    taint_claim,
    # Constants
    MAX_NORMALIZE_LENGTH,
)


# =============================================================================
# Enums
# =============================================================================


class TestEnums:
    def test_taint_type_values(self):
        assert TaintType.CONTRADICTED == "contradicted"
        assert TaintType.RETRACTED == "retracted"

    def test_fingerprint_method_values(self):
        assert FingerprintMethod.TOKEN_JACCARD == "token_jaccard_v1"

    def test_taint_verdict_values(self):
        assert TaintVerdict.CLEAR == "clear"
        assert TaintVerdict.FLAGGED == "flagged"
        assert TaintVerdict.EXACT == "exact"
        assert TaintVerdict.TOO_SHORT == "too_short"


# =============================================================================
# Normalization
# =============================================================================


class TestNormalize:
    def test_lowercase(self):
        assert normalize("Hello WORLD") == "hello world"

    def test_unicode_nfkc(self):
        # fi ligature → fi
        assert "fi" in normalize("\ufb01nger")

    def test_strip_punctuation(self):
        result = normalize("hello, world! foo.")
        assert "," not in result
        assert "!" not in result
        assert "." not in result

    def test_collapse_whitespace(self):
        assert normalize("hello   world\t\nfoo") == "hello world foo"

    def test_cap_length(self):
        long_text = "word " * 1000
        result = normalize(long_text)
        assert len(result) <= MAX_NORMALIZE_LENGTH

    def test_stability_variants(self):
        """Same text with trivial variations should normalize identically."""
        a = normalize("The server crashed at 3pm!")
        b = normalize("the server crashed at 3pm")
        c = normalize("  The  Server  Crashed  At  3pm!!! ")
        assert a == b == c

    def test_empty_string(self):
        assert normalize("") == ""

    def test_only_punctuation(self):
        assert normalize("!!!...???") == ""


# =============================================================================
# Tokenize
# =============================================================================


class TestTokenize:
    def test_basic(self):
        tokens = tokenize("hello world foo bar")
        assert tokens == ["hello", "world", "foo", "bar"]

    def test_strip_stopwords(self):
        tokens = tokenize("the server is down", strip_stopwords=True)
        assert "the" not in tokens
        assert "is" not in tokens
        assert "server" in tokens
        assert "down" in tokens

    def test_no_strip_stopwords(self):
        tokens = tokenize("the server is down", strip_stopwords=False)
        assert "the" in tokens
        assert "is" in tokens

    def test_empty(self):
        assert tokenize("") == []


# =============================================================================
# Fingerprint
# =============================================================================


class TestFingerprint:
    def test_create(self):
        fp = fingerprint("The server crashed due to memory pressure")
        assert isinstance(fp, Fingerprint)
        assert len(fp.tokens) > 0
        assert len(fp.text_hash) == 64  # sha256 hex

    def test_method_is_token_jaccard(self):
        fp = fingerprint("test text")
        assert fp.method == FingerprintMethod.TOKEN_JACCARD

    def test_deterministic(self):
        fp1 = fingerprint("same text here")
        fp2 = fingerprint("same text here")
        assert fp1.text_hash == fp2.text_hash
        assert fp1.tokens == fp2.tokens

    def test_different_text_different_hash(self):
        fp1 = fingerprint("server crashed")
        fp2 = fingerprint("server recovered")
        assert fp1.text_hash != fp2.text_hash

    def test_to_dict_from_dict(self):
        fp = fingerprint("roundtrip test")
        d = fp.to_dict()
        fp2 = Fingerprint.from_dict(d)
        assert fp2.tokens == fp.tokens
        assert fp2.text_hash == fp.text_hash

    def test_strip_stopwords(self):
        fp = fingerprint("the server is completely down", strip_stopwords=True)
        assert "the" not in fp.tokens
        assert "is" not in fp.tokens


# =============================================================================
# Score
# =============================================================================


class TestScore:
    def test_identical(self):
        fp = fingerprint("identical text here")
        assert score(fp, fp) == 1.0

    def test_completely_different(self):
        fp1 = fingerprint("alpha beta gamma")
        fp2 = fingerprint("delta epsilon zeta")
        assert score(fp1, fp2) == 0.0

    def test_partial_overlap(self):
        fp1 = fingerprint("the server crashed due to memory")
        fp2 = fingerprint("the server failed due to disk")
        s = score(fp1, fp2)
        assert 0.0 < s < 1.0

    def test_empty_fingerprints(self):
        fp1 = Fingerprint(tokens=frozenset(), text_hash="a")
        fp2 = Fingerprint(tokens=frozenset(), text_hash="b")
        assert score(fp1, fp2) == 0.0

    def test_subset(self):
        fp1 = Fingerprint(tokens=frozenset({"a", "b", "c"}), text_hash="x")
        fp2 = Fingerprint(tokens=frozenset({"a", "b", "c", "d"}), text_hash="y")
        assert score(fp1, fp2) == 3 / 4  # 0.75

    def test_symmetry(self):
        fp1 = fingerprint("server memory crash")
        fp2 = fingerprint("memory server disk")
        assert score(fp1, fp2) == score(fp2, fp1)


# =============================================================================
# TaintedClaim
# =============================================================================


class TestTaintedClaim:
    def test_create(self):
        fp = fingerprint("bad claim text")
        tc = TaintedClaim(
            claim_id="c1",
            taint_type=TaintType.CONTRADICTED,
            fingerprint=fp,
            normalized_text="bad claim text",
            timestamp="2025-01-01T00:00:00Z",
        )
        assert tc.claim_id == "c1"
        assert tc.taint_type == TaintType.CONTRADICTED

    def test_to_dict_from_dict(self):
        fp = fingerprint("test claim")
        tc = TaintedClaim(
            claim_id="c2",
            taint_type=TaintType.RETRACTED,
            fingerprint=fp,
            normalized_text="test claim",
            timestamp="2025-06-01T00:00:00Z",
            metadata={"reason": "wrong"},
        )
        d = tc.to_dict()
        tc2 = TaintedClaim.from_dict(d)
        assert tc2.claim_id == "c2"
        assert tc2.taint_type == TaintType.RETRACTED
        assert tc2.metadata["reason"] == "wrong"


# =============================================================================
# TaintMatch
# =============================================================================


class TestTaintMatch:
    def test_create(self):
        m = TaintMatch(
            tainted_claim_id="c1",
            taint_type=TaintType.CONTRADICTED,
            similarity=0.85,
            method=FingerprintMethod.TOKEN_JACCARD,
            threshold=0.8,
        )
        assert m.similarity == 0.85
        assert not m.exact

    def test_to_dict_from_dict(self):
        m = TaintMatch(
            tainted_claim_id="c1",
            taint_type=TaintType.RETRACTED,
            similarity=1.0,
            method=FingerprintMethod.TOKEN_JACCARD,
            threshold=0.8,
            exact=True,
        )
        d = m.to_dict()
        m2 = TaintMatch.from_dict(d)
        assert m2.exact is True
        assert m2.similarity == 1.0


# =============================================================================
# TaintCheckResult
# =============================================================================


class TestTaintCheckResult:
    def test_clear(self):
        r = TaintCheckResult(verdict=TaintVerdict.CLEAR)
        assert not r.is_flagged

    def test_flagged(self):
        r = TaintCheckResult(verdict=TaintVerdict.FLAGGED)
        assert r.is_flagged

    def test_exact(self):
        r = TaintCheckResult(verdict=TaintVerdict.EXACT)
        assert r.is_flagged

    def test_too_short(self):
        r = TaintCheckResult(verdict=TaintVerdict.TOO_SHORT)
        assert not r.is_flagged

    def test_to_dict_from_dict(self):
        m = TaintMatch(
            tainted_claim_id="x",
            taint_type=TaintType.CONTRADICTED,
            similarity=0.9,
            method=FingerprintMethod.TOKEN_JACCARD,
            threshold=0.8,
        )
        r = TaintCheckResult(
            verdict=TaintVerdict.FLAGGED,
            matches=[m],
            best_score=0.9,
            checked_against=5,
            input_token_count=10,
        )
        d = r.to_dict()
        r2 = TaintCheckResult.from_dict(d)
        assert r2.verdict == TaintVerdict.FLAGGED
        assert len(r2.matches) == 1
        assert r2.best_score == 0.9


# =============================================================================
# TaintEvent
# =============================================================================


class TestTaintEvent:
    def test_create(self):
        e = TaintEvent(
            new_claim_id="new1",
            matched_claim_id="old1",
            similarity=0.85,
            taint_type=TaintType.CONTRADICTED,
        )
        assert e.event_type == "tainted_similarity_hit"

    def test_to_dict_from_dict(self):
        e = TaintEvent(
            new_claim_id="a",
            matched_claim_id="b",
            similarity=0.9,
            threshold=0.8,
            exact=True,
        )
        d = e.to_dict()
        e2 = TaintEvent.from_dict(d)
        assert e2.exact is True
        assert e2.similarity == 0.9


# =============================================================================
# TaintConfig
# =============================================================================


class TestTaintConfig:
    def test_defaults(self):
        c = TaintConfig()
        assert c.jaccard_threshold == 0.8
        assert c.min_tokens == 6
        assert c.strip_stopwords is False

    def test_custom(self):
        c = TaintConfig(jaccard_threshold=0.9, min_tokens=4)
        assert c.jaccard_threshold == 0.9

    def test_to_dict_from_dict(self):
        c = TaintConfig(jaccard_threshold=0.7, strip_stopwords=True)
        d = c.to_dict()
        c2 = TaintConfig.from_dict(d)
        assert c2.jaccard_threshold == 0.7
        assert c2.strip_stopwords is True


# =============================================================================
# TaintIndex — Core
# =============================================================================


class TestTaintIndex:
    def test_add_tainted(self):
        idx = TaintIndex()
        claim = idx.add_tainted("c1", "The server crashed due to OOM", TaintType.CONTRADICTED)
        assert claim.claim_id == "c1"
        assert idx.count() == 1

    def test_add_multiple(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Server crash OOM", TaintType.CONTRADICTED)
        idx.add_tainted("c2", "Database timeout error", TaintType.RETRACTED)
        assert idx.count() == 2

    def test_remove_tainted(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Bad claim text here", TaintType.CONTRADICTED)
        assert idx.remove_tainted("c1") is True
        assert idx.count() == 0
        assert idx.remove_tainted("c1") is False

    def test_get_tainted(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Some tainted claim", TaintType.RETRACTED)
        tc = idx.get_tainted("c1")
        assert tc is not None
        assert tc.taint_type == TaintType.RETRACTED
        assert idx.get_tainted("missing") is None

    def test_list_tainted(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "claim one text here for testing", TaintType.CONTRADICTED)
        idx.add_tainted("c2", "claim two text here for testing", TaintType.RETRACTED)
        claims = idx.list_tainted()
        assert len(claims) == 2

    def test_stats(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "claim one here", TaintType.CONTRADICTED)
        idx.add_tainted("c2", "claim two here", TaintType.RETRACTED)
        s = idx.stats()
        assert s["total_tainted"] == 2
        assert s["by_type"]["contradicted"] == 1
        assert s["by_type"]["retracted"] == 1


# =============================================================================
# TaintIndex — Check (the important tests)
# =============================================================================


class TestTaintIndexCheck:
    def test_exact_match(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The deployment failed because of memory pressure on node seven", TaintType.CONTRADICTED)
        result = idx.check("The deployment failed because of memory pressure on node seven", "new1")
        assert result.verdict == TaintVerdict.EXACT
        assert result.matches[0].exact is True
        assert result.best_score == 1.0

    def test_near_duplicate_flagged(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The server crashed because of insufficient memory allocation", TaintType.CONTRADICTED)
        # Very similar but not identical
        result = idx.check("The server crashed because of insufficient memory usage", "new1")
        # High overlap — should be flagged or at least have high score
        assert result.best_score > 0.5

    def test_clearly_different_clear(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The server crashed because of insufficient memory allocation", TaintType.CONTRADICTED)
        result = idx.check("Python three point twelve introduces new typing features and performance gains", "new1")
        assert result.verdict == TaintVerdict.CLEAR

    def test_too_short(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Short claim text for testing purposes here", TaintType.CONTRADICTED)
        result = idx.check("hello", "new1")
        assert result.verdict == TaintVerdict.TOO_SHORT

    def test_empty_index_clear(self):
        idx = TaintIndex()
        result = idx.check("Some claim that should be checked against empty index", "new1")
        assert result.verdict == TaintVerdict.CLEAR
        assert result.checked_against == 0

    def test_threshold_boundary(self):
        """Claims just below threshold should not be flagged."""
        idx = TaintIndex(config=TaintConfig(jaccard_threshold=0.95))
        idx.add_tainted("c1", "The database connection pool exhausted all available connections", TaintType.CONTRADICTED)
        result = idx.check("The database connection pool exhausted most available connections", "new1")
        # "most" vs "all" — should be high but potentially below 0.95
        if result.verdict == TaintVerdict.FLAGGED:
            assert result.best_score >= 0.95
        else:
            assert result.best_score < 0.95

    def test_events_emitted_on_flag(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The server crashed due to memory pressure on the primary node", TaintType.CONTRADICTED)
        idx.check("The server crashed due to memory pressure on the primary node", "new1")
        events = idx.events()
        assert len(events) >= 1
        assert events[0].event_type == "tainted_similarity_hit"
        assert events[0].new_claim_id == "new1"
        assert events[0].matched_claim_id == "c1"

    def test_no_events_on_clear(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Server crashed from memory pressure on primary node", TaintType.CONTRADICTED)
        idx.check("Python typing improvements in version three twelve are significant", "new1")
        flagged_events = [e for e in idx.events() if e.similarity >= e.threshold]
        assert len(flagged_events) == 0

    def test_multiple_tainted_claims(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The server crashed due to memory pressure in production", TaintType.CONTRADICTED)
        idx.add_tainted("c2", "The database failed due to connection pool exhaustion", TaintType.RETRACTED)
        # Similar to c1
        result = idx.check("The server crashed due to memory pressure in staging", "new1")
        if result.matches:
            # Best match should be c1
            best = max(result.matches, key=lambda m: m.similarity)
            assert best.tainted_claim_id == "c1"

    def test_clear_events(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Tainted claim text here for testing the event system", TaintType.CONTRADICTED)
        idx.check("Tainted claim text here for testing the event system", "new1")
        assert len(idx.events()) > 0
        count = idx.clear_events()
        assert count > 0
        assert len(idx.events()) == 0


# =============================================================================
# TaintIndex — Normalization Stability
# =============================================================================


class TestNormalizationStability:
    def test_case_insensitive(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The Server CRASHED Due To Memory Pressure", TaintType.CONTRADICTED)
        result = idx.check("the server crashed due to memory pressure", "new1")
        assert result.verdict == TaintVerdict.EXACT

    def test_punctuation_insensitive(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The server crashed, causing an outage! Total downtime: 2 hours.", TaintType.CONTRADICTED)
        result = idx.check("The server crashed causing an outage Total downtime 2 hours", "new1")
        assert result.verdict == TaintVerdict.EXACT

    def test_whitespace_insensitive(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "The  server   crashed\tdue\nto   memory", TaintType.CONTRADICTED)
        result = idx.check("The server crashed due to memory", "new1")
        assert result.verdict == TaintVerdict.EXACT


# =============================================================================
# TaintIndex — Persistence
# =============================================================================


class TestTaintIndexPersistence:
    def test_disk_roundtrip(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        idx = TaintIndex(governor_dir=gov_dir)
        idx.add_tainted("c1", "Persisted tainted claim for disk roundtrip testing", TaintType.CONTRADICTED)
        idx.check("Persisted tainted claim for disk roundtrip testing", "new1")

        # Reload
        idx2 = TaintIndex(governor_dir=gov_dir)
        assert idx2.count() == 1
        assert idx2.get_tainted("c1") is not None
        assert len(idx2.events()) >= 1

    def test_remove_persists(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        idx = TaintIndex(governor_dir=gov_dir)
        idx.add_tainted("c1", "Will be removed from persistence test", TaintType.RETRACTED)
        idx.remove_tainted("c1")

        idx2 = TaintIndex(governor_dir=gov_dir)
        assert idx2.count() == 0

    def test_to_dict_from_dict(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Claim for serialization roundtrip testing here", TaintType.CONTRADICTED)
        idx.check("Claim for serialization roundtrip testing here", "new1")

        d = idx.to_dict()
        idx2 = TaintIndex.from_dict(d)
        assert idx2.count() == 1
        assert len(idx2.events()) >= 1


# =============================================================================
# TaintIndex — Config Variations
# =============================================================================


class TestTaintIndexConfig:
    def test_high_threshold(self):
        """With very high threshold, only exact matches flag."""
        config = TaintConfig(jaccard_threshold=0.99)
        idx = TaintIndex(config=config)
        idx.add_tainted("c1", "The server completely crashed due to total memory exhaustion", TaintType.CONTRADICTED)
        result = idx.check("The server partially crashed due to partial memory exhaustion", "new1")
        # Not an exact match — should be CLEAR with 0.99 threshold
        if result.verdict == TaintVerdict.FLAGGED:
            assert result.best_score >= 0.99

    def test_low_threshold(self):
        """With low threshold, more matches are flagged."""
        config = TaintConfig(jaccard_threshold=0.3)
        idx = TaintIndex(config=config)
        idx.add_tainted("c1", "The primary server crashed due to memory pressure today", TaintType.CONTRADICTED)
        result = idx.check("The secondary server restarted after memory recovery today", "new1")
        # With low threshold, partial overlaps flag
        if result.best_score >= 0.3:
            assert result.verdict == TaintVerdict.FLAGGED

    def test_min_tokens_filter(self):
        config = TaintConfig(min_tokens=10)
        idx = TaintIndex(config=config)
        idx.add_tainted("c1", "Short claim here", TaintType.CONTRADICTED)
        result = idx.check("Short claim here", "new1")
        assert result.verdict == TaintVerdict.TOO_SHORT

    def test_stopword_stripping(self):
        config = TaintConfig(strip_stopwords=True, min_tokens=3)
        idx = TaintIndex(config=config)
        idx.add_tainted("c1", "the server is down because of the memory", TaintType.CONTRADICTED)
        # With stopwords stripped, "server down because memory" is the token set
        tc = idx.get_tainted("c1")
        assert "the" not in tc.fingerprint.tokens
        assert "is" not in tc.fingerprint.tokens

    def test_below_threshold_recording(self):
        """Near-misses should be recorded when config allows."""
        config = TaintConfig(
            jaccard_threshold=0.8,
            record_below_threshold=True,
            below_threshold_min=0.3,
        )
        idx = TaintIndex(config=config)
        idx.add_tainted("c1", "The database connection pool was completely exhausted causing failures", TaintType.CONTRADICTED)
        result = idx.check("The database replication lag increased causing timeout failures", "new1")
        # Some overlap but probably below 0.8 — should still appear in matches if above 0.3
        if result.matches:
            below_threshold = [m for m in result.matches if m.similarity < 0.8]
            # These are recorded for debugging
            for m in below_threshold:
                assert m.similarity >= 0.3

    def test_no_below_threshold_recording(self):
        config = TaintConfig(record_below_threshold=False)
        idx = TaintIndex(config=config)
        idx.add_tainted("c1", "Completely unique tainted claim text for testing purposes only", TaintType.CONTRADICTED)
        result = idx.check("Entirely different subject about weather patterns and forecasting", "new1")
        # With recording off, no matches unless above threshold
        for m in result.matches:
            assert m.similarity >= config.jaccard_threshold


# =============================================================================
# Convenience Functions
# =============================================================================


class TestConvenience:
    def test_create_taint_index(self):
        idx = create_taint_index()
        assert isinstance(idx, TaintIndex)

    def test_create_with_config(self):
        config = TaintConfig(jaccard_threshold=0.9)
        idx = create_taint_index(config=config)
        assert idx.config.jaccard_threshold == 0.9

    def test_check_claim(self):
        idx = create_taint_index()
        idx.add_tainted("c1", "Bad claim about server memory causing production outages", TaintType.CONTRADICTED)
        result = check_claim(idx, "Bad claim about server memory causing production outages", "new1")
        assert result.verdict == TaintVerdict.EXACT

    def test_taint_claim(self):
        idx = create_taint_index()
        tc = taint_claim(idx, "c1", "Tainted claim text here", TaintType.RETRACTED)
        assert tc.claim_id == "c1"
        assert idx.count() == 1

    def test_create_with_governor_dir(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        idx = create_taint_index(governor_dir=gov_dir)
        idx.add_tainted("c1", "Persisted claim for convenience function test", TaintType.CONTRADICTED)
        idx2 = create_taint_index(governor_dir=gov_dir)
        assert idx2.count() == 1


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    def test_empty_text(self):
        idx = TaintIndex()
        result = idx.check("", "new1")
        assert result.verdict == TaintVerdict.TOO_SHORT

    def test_only_stopwords(self):
        config = TaintConfig(strip_stopwords=True, min_tokens=3)
        idx = TaintIndex(config=config)
        result = idx.check("the is a an the", "new1")
        assert result.verdict == TaintVerdict.TOO_SHORT

    def test_unicode_text(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Der Server ist abgestürzt wegen Speichermangel im System", TaintType.CONTRADICTED)
        result = idx.check("Der Server ist abgestürzt wegen Speichermangel im System", "new1")
        assert result.verdict == TaintVerdict.EXACT

    def test_duplicate_add(self):
        """Adding the same claim_id twice overwrites."""
        idx = TaintIndex()
        idx.add_tainted("c1", "Original claim text for duplicate test here", TaintType.CONTRADICTED)
        idx.add_tainted("c1", "Replacement claim text for duplicate test here", TaintType.RETRACTED)
        assert idx.count() == 1
        tc = idx.get_tainted("c1")
        assert tc.taint_type == TaintType.RETRACTED

    def test_check_after_remove(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "Claim that will be removed then checked against index", TaintType.CONTRADICTED)
        idx.remove_tainted("c1")
        result = idx.check("Claim that will be removed then checked against index", "new1")
        assert result.verdict != TaintVerdict.EXACT

    def test_many_tainted_claims(self):
        """Index works with many entries."""
        idx = TaintIndex()
        for i in range(50):
            idx.add_tainted(f"c{i}", f"Unique tainted claim number {i} about topic {i * 7}", TaintType.CONTRADICTED)
        assert idx.count() == 50
        result = idx.check("Unique tainted claim number 25 about topic 175", "new1")
        assert result.verdict == TaintVerdict.EXACT

    def test_inverted_index_cleanup_on_remove(self):
        idx = TaintIndex()
        idx.add_tainted("c1", "alpha beta gamma delta epsilon zeta eta", TaintType.CONTRADICTED)
        idx.remove_tainted("c1")
        # Inverted index should have no entries pointing to c1
        for token_set in idx._inverted.values():
            assert "c1" not in token_set
