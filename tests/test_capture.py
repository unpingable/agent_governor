"""Tests for governor.capture — Generic capture protocol + code/research classifiers.

Tests the base CaptureClassifier ABC, CodeCaptureClassifier, ResearchCaptureClassifier,
shared helpers, and the mode registry.
"""

import hashlib

import pytest

from governor.capture import (
    CapturedItem,
    CaptureReceipt,
    CaptureStatus,
    CodeCaptureClassifier,
    CodeCaptureKind,
    ResearchCaptureClassifier,
    ResearchCaptureKind,
    classify_skippable,
    dedup_captures,
    extract_proper_noun,
    get_classifier,
    split_into_statements,
    strip_question_tag,
)


# =============================================================================
# Shared helpers
# =============================================================================


class TestClassifySkippable:
    """Test the classify_skippable filter."""

    def test_plain_statement(self):
        assert classify_skippable("The API should return JSON") is None

    def test_question(self):
        assert classify_skippable("Is this the right approach?") == "question"

    def test_hypothetical(self):
        assert classify_skippable("What if we used a queue instead?") == "hypothetical"

    def test_should_we_is_hypothetical(self):
        # "Should we" is caught by hypothetical before question check
        assert classify_skippable("Should we use Redis?") == "hypothetical"

    def test_meta(self):
        assert classify_skippable("I'm thinking about switching frameworks") == "meta"

    def test_do_you_think_is_meta(self):
        # "Do you think" is caught by meta before question check
        assert classify_skippable("Do you think that's right?") == "meta"

    def test_maybe(self):
        assert classify_skippable("Maybe we should refactor that") == "hypothetical"

    def test_suppose(self):
        assert classify_skippable("Suppose we add caching") == "hypothetical"


class TestStripQuestionTag:
    """Test question-tagged assertion stripping."""

    def test_right_tag(self):
        assert strip_question_tag("The API returns JSON, right?") == "The API returns JSON"

    def test_yeah_tag(self):
        assert strip_question_tag("We use PostgreSQL, yeah?") == "We use PostgreSQL"

    def test_correct_tag(self):
        assert strip_question_tag("Magic costs blood, correct?") == "Magic costs blood"

    def test_isnt_it_tag(self):
        result = strip_question_tag("The bug is in auth, isn't it?")
        assert result is not None
        assert "auth" in result

    def test_pure_question_returns_none(self):
        assert strip_question_tag("What is the API format?") is None

    def test_no_tag_returns_none(self):
        assert strip_question_tag("Hello world") is None


class TestExtractProperNoun:
    """Test proper noun extraction."""

    def test_capitalized_name(self):
        assert extract_proper_noun("Redis is a database") == "Redis"

    def test_stopword_filtered(self):
        assert extract_proper_noun("The old man") is None

    def test_multi_word(self):
        result = extract_proper_noun("Red Hat makes Linux")
        assert result in ("Red Hat", "Linux")


class TestSplitStatements:
    """Test statement splitting with offset tracking."""

    def test_single_line(self):
        stmts = split_into_statements("Hello world")
        assert len(stmts) == 1
        assert stmts[0]["text"] == "Hello world"

    def test_multi_line(self):
        stmts = split_into_statements("Line one.\nLine two.")
        assert len(stmts) == 2

    def test_empty_string(self):
        stmts = split_into_statements("")
        assert len(stmts) == 0

    def test_offsets_point_to_original(self):
        text = "First line.\nSecond line."
        stmts = split_into_statements(text)
        for stmt in stmts:
            offset = stmt["offset"]
            assert text[offset:offset + len(stmt["text"])] == stmt["text"]


class TestDedupCaptures:
    """Test capture deduplication."""

    def test_same_kind_and_subject_merged(self):
        items = [
            CapturedItem(kind="character", confidence=0.7, subject_guess="Foo",
                         statement="is tall", field_guess="description",
                         evidence_spans=[(0, 10)]),
            CapturedItem(kind="character", confidence=0.8, subject_guess="Foo",
                         statement="is brave", field_guess="description",
                         evidence_spans=[(15, 25)]),
        ]
        result = dedup_captures(items)
        assert len(result) == 1
        assert result[0].confidence == 0.8  # Highest kept
        assert len(result[0].evidence_spans) == 2  # Merged

    def test_different_subjects_not_merged(self):
        items = [
            CapturedItem(kind="character", confidence=0.7, subject_guess="Foo",
                         statement="is tall", field_guess="description",
                         evidence_spans=[(0, 10)]),
            CapturedItem(kind="character", confidence=0.8, subject_guess="Bar",
                         statement="is brave", field_guess="description",
                         evidence_spans=[(15, 25)]),
        ]
        result = dedup_captures(items)
        assert len(result) == 2

    def test_different_kinds_not_merged(self):
        items = [
            CapturedItem(kind="character", confidence=0.7, subject_guess="Foo",
                         statement="is tall", field_guess="description",
                         evidence_spans=[(0, 10)]),
            CapturedItem(kind="constraint", confidence=0.8, subject_guess="Foo",
                         statement="would never", field_guess="wont",
                         evidence_spans=[(15, 25)]),
        ]
        result = dedup_captures(items)
        assert len(result) == 2


# =============================================================================
# CapturedItem serialization
# =============================================================================


class TestCapturedItemBase:
    """Test base CapturedItem with string kinds."""

    def test_roundtrip(self):
        item = CapturedItem(
            kind="work_item",
            confidence=0.72,
            subject_guess=None,
            statement="refactor the auth module",
            field_guess="task",
            evidence_spans=[(0, 30)],
            source_message_id="msg_1",
            status=CaptureStatus.PENDING,
            draft_payload={"task": "refactor the auth module"},
            subject_source="lets_verb",
        )
        data = item.to_dict()
        restored = CapturedItem.from_dict(data)
        assert restored.kind == "work_item"
        assert restored.confidence == 0.72
        assert restored.subject_source == "lets_verb"

    def test_default_status_pending(self):
        item = CapturedItem(
            kind="claim", confidence=0.5, subject_guess=None,
            statement="x", field_guess="y", evidence_spans=[],
        )
        assert item.status == CaptureStatus.PENDING


# =============================================================================
# Code Capture Classifier
# =============================================================================


class TestCodeCapture:
    """Test CodeCaptureClassifier patterns."""

    @pytest.fixture
    def classifier(self):
        return CodeCaptureClassifier()

    # --- Work items ---

    def test_todo_prefix(self, classifier):
        items, _ = classifier.scan("TODO: clean up the error handling")
        assert len(items) >= 1
        work_items = [i for i in items if i.kind == CodeCaptureKind.WORK_ITEM]
        assert len(work_items) >= 1
        assert work_items[0].confidence >= 0.85

    def test_fixme_prefix(self, classifier):
        items, _ = classifier.scan("FIXME: race condition in the queue")
        work_items = [i for i in items if i.kind == CodeCaptureKind.WORK_ITEM]
        assert len(work_items) >= 1

    def test_need_to(self, classifier):
        items, _ = classifier.scan("We need to add authentication to the API")
        work_items = [i for i in items if i.kind == CodeCaptureKind.WORK_ITEM]
        assert len(work_items) >= 1

    def test_lets_refactor(self, classifier):
        items, _ = classifier.scan("Let's refactor the database layer")
        work_items = [i for i in items if i.kind == CodeCaptureKind.WORK_ITEM]
        assert len(work_items) >= 1

    # --- Hypotheses ---

    def test_bug_is_in(self, classifier):
        items, _ = classifier.scan("The bug is in the auth middleware")
        hyp_items = [i for i in items if i.kind == CodeCaptureKind.HYPOTHESIS]
        assert len(hyp_items) >= 1

    def test_i_think_because(self, classifier):
        items, _ = classifier.scan("I think it's because the cache is stale")
        hyp_items = [i for i in items if i.kind == CodeCaptureKind.HYPOTHESIS]
        assert len(hyp_items) >= 1

    def test_hypothesis_prefix(self, classifier):
        items, _ = classifier.scan("Hypothesis: the OOM is caused by unbounded retry")
        hyp_items = [i for i in items if i.kind == CodeCaptureKind.HYPOTHESIS]
        assert len(hyp_items) >= 1
        assert hyp_items[0].confidence >= 0.85

    # --- Decisions ---

    def test_should_use(self, classifier):
        items, _ = classifier.scan("We should use PostgreSQL for the database")
        dec_items = [i for i in items if i.kind == CodeCaptureKind.DECISION]
        assert len(dec_items) >= 1

    def test_decision_prefix(self, classifier):
        items, _ = classifier.scan("Decision: we will use JWT for auth tokens")
        dec_items = [i for i in items if i.kind == CodeCaptureKind.DECISION]
        assert len(dec_items) >= 1
        assert dec_items[0].confidence >= 0.85

    def test_api_should(self, classifier):
        items, _ = classifier.scan("The API should return paginated results")
        dec_items = [i for i in items if i.kind == CodeCaptureKind.DECISION]
        assert len(dec_items) >= 1

    # --- Patch intents ---

    def test_add_to(self, classifier):
        items, _ = classifier.scan("Add rate limiting to the API gateway")
        intent_items = [i for i in items if i.kind == CodeCaptureKind.PATCH_INTENT]
        assert len(intent_items) >= 1

    def test_change_to(self, classifier):
        items, _ = classifier.scan("Change the response format to JSON")
        intent_items = [i for i in items if i.kind == CodeCaptureKind.PATCH_INTENT]
        assert len(intent_items) >= 1

    # --- Negative cases ---

    def test_question_skipped(self, classifier):
        items, _ = classifier.scan("What framework should we use?")
        assert len(items) == 0

    def test_hypothetical_skipped(self, classifier):
        items, _ = classifier.scan("What if we used GraphQL instead?")
        assert len(items) == 0

    def test_empty_text(self, classifier):
        items, _ = classifier.scan("")
        assert len(items) == 0

    # --- Receipt ---

    def test_forensic_version(self, classifier):
        _, receipt = classifier.scan("TODO: fix the tests")
        assert receipt.classifier_version == "code@1.0.0"
        assert "@" in receipt.classifier_version

    def test_receipt_deterministic(self, classifier):
        text = "The bug is in the parser"
        _, r1 = classifier.scan(text)
        _, r2 = classifier.scan(text)
        assert r1.content_hash == r2.content_hash
        assert len(r1.pattern_hits) == len(r2.pattern_hits)

    # --- Question-tagged assertions ---

    def test_question_tag_reduced_confidence(self, classifier):
        items, _ = classifier.scan("The bug is in the parser, right?")
        if items:
            assert all(i.confidence < 0.72 for i in items)


# =============================================================================
# Research Capture Classifier
# =============================================================================


class TestResearchCapture:
    """Test ResearchCaptureClassifier patterns."""

    @pytest.fixture
    def classifier(self):
        return ResearchCaptureClassifier()

    # --- Claims ---

    def test_causes(self, classifier):
        items, _ = classifier.scan("Sleep deprivation causes cognitive decline")
        claim_items = [i for i in items if i.kind == ResearchCaptureKind.CLAIM]
        assert len(claim_items) >= 1

    def test_leads_to(self, classifier):
        items, _ = classifier.scan("Increased temperature leads to faster reaction rates")
        claim_items = [i for i in items if i.kind == ResearchCaptureKind.CLAIM]
        assert len(claim_items) >= 1

    def test_claim_prefix(self, classifier):
        items, _ = classifier.scan("Claim: the model overfits on small datasets")
        claim_items = [i for i in items if i.kind == ResearchCaptureKind.CLAIM]
        assert len(claim_items) >= 1
        assert claim_items[0].confidence >= 0.85

    def test_finding_prefix(self, classifier):
        items, _ = classifier.scan("Finding: dropout improves generalization")
        claim_items = [i for i in items if i.kind == ResearchCaptureKind.CLAIM]
        assert len(claim_items) >= 1

    def test_evidence_shows(self, classifier):
        items, _ = classifier.scan("Evidence suggests that larger batch sizes reduce noise")
        claim_items = [i for i in items if i.kind == ResearchCaptureKind.CLAIM]
        assert len(claim_items) >= 1

    # --- Citations ---

    def test_per_source(self, classifier):
        items, _ = classifier.scan("Per the original paper, the method requires O(n) time")
        cite_items = [i for i in items if i.kind == ResearchCaptureKind.CITATION]
        assert len(cite_items) >= 1

    def test_according_to(self, classifier):
        items, _ = classifier.scan("According to the benchmark results, model A outperforms B")
        cite_items = [i for i in items if i.kind == ResearchCaptureKind.CITATION]
        assert len(cite_items) >= 1

    def test_author_showed(self, classifier):
        items, _ = classifier.scan("Vaswani et al. showed that attention mechanisms are sufficient")
        cite_items = [i for i in items if i.kind == ResearchCaptureKind.CITATION]
        assert len(cite_items) >= 1

    # --- Experiments ---

    def test_try_whether(self, classifier):
        items, _ = classifier.scan("Try whether increasing the learning rate helps convergence")
        exp_items = [i for i in items if i.kind == ResearchCaptureKind.EXPERIMENT]
        assert len(exp_items) >= 1

    def test_test_if(self, classifier):
        items, _ = classifier.scan("Test if the model generalizes to unseen domains")
        exp_items = [i for i in items if i.kind == ResearchCaptureKind.EXPERIMENT]
        assert len(exp_items) >= 1

    def test_experiment_prefix(self, classifier):
        items, _ = classifier.scan("Experiment: run ablation on the attention heads")
        exp_items = [i for i in items if i.kind == ResearchCaptureKind.EXPERIMENT]
        assert len(exp_items) >= 1
        assert exp_items[0].confidence >= 0.85

    # --- Assumptions ---

    def test_assuming(self, classifier):
        items, _ = classifier.scan("Assuming normal distribution of the residuals")
        assn_items = [i for i in items if i.kind == ResearchCaptureKind.ASSUMPTION]
        assert len(assn_items) >= 1

    def test_given_that(self, classifier):
        items, _ = classifier.scan("Given that the dataset is balanced across classes")
        assn_items = [i for i in items if i.kind == ResearchCaptureKind.ASSUMPTION]
        assert len(assn_items) >= 1

    def test_assumption_prefix(self, classifier):
        items, _ = classifier.scan("Assumption: the samples are IID")
        assn_items = [i for i in items if i.kind == ResearchCaptureKind.ASSUMPTION]
        assert len(assn_items) >= 1
        assert assn_items[0].confidence >= 0.85

    # --- Negative cases ---

    def test_question_skipped(self, classifier):
        items, _ = classifier.scan("What causes overfitting?")
        assert len(items) == 0

    def test_hypothetical_skipped(self, classifier):
        items, _ = classifier.scan("What if we used a different loss function?")
        assert len(items) == 0

    def test_empty_text(self, classifier):
        items, _ = classifier.scan("")
        assert len(items) == 0

    # --- Receipt ---

    def test_forensic_version(self, classifier):
        _, receipt = classifier.scan("Claim: X is true")
        assert receipt.classifier_version == "research@1.0.0"

    def test_receipt_deterministic(self, classifier):
        text = "Evidence suggests X causes Y"
        _, r1 = classifier.scan(text)
        _, r2 = classifier.scan(text)
        assert r1.content_hash == r2.content_hash


# =============================================================================
# Registry
# =============================================================================


class TestRegistry:
    """Test the mode-based classifier registry."""

    def test_fiction_mode(self):
        clf = get_classifier("fiction")
        from fiction_governor.canon_capture import CanonCaptureClassifier
        assert isinstance(clf, CanonCaptureClassifier)

    def test_code_mode(self):
        clf = get_classifier("code")
        assert isinstance(clf, CodeCaptureClassifier)

    def test_research_mode(self):
        clf = get_classifier("research")
        assert isinstance(clf, ResearchCaptureClassifier)

    def test_nonfiction_mode_aliases_research(self):
        clf = get_classifier("nonfiction")
        assert isinstance(clf, ResearchCaptureClassifier)

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="No capture classifier"):
            get_classifier("unknown_mode")

    def test_max_captures_passed_through(self):
        clf = get_classifier("code", max_captures=3)
        assert clf.max_captures == 3
