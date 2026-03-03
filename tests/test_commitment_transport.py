# SPDX-License-Identifier: Apache-2.0
"""Tests for Commitment Transport (AG2 Layer 2, Item #5)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from governor.commitment_transport import (
    Modality,
    CommitmentKind,
    TransportOutcome,
    MODALITY_WEIGHT,
    OUTCOME_SHEAR,
    Commitment,
    CommitmentTransport,
    ShearReport,
    TransportHistory,
    extract_commitments,
    validate_transport,
    check_transport,
    validate_compaction_transport,
    validate_bridge_transport,
    validate_constraint_transport,
    make_transport_event,
    _make_commitment_id,
    _detect_modality,
    _detect_kind,
    _detect_scope,
    _token_jaccard,
    _find_best_match,
    _classify_transport,
    _split_sentences,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestModality:
    def test_values(self):
        assert Modality.MUST.value == "must"
        assert Modality.SHOULD.value == "should"
        assert Modality.MAY.value == "may"
        assert Modality.MUST_NOT.value == "must_not"

    def test_count(self):
        assert len(Modality) == 4


class TestCommitmentKind:
    def test_values(self):
        assert CommitmentKind.INVARIANT.value == "invariant"
        assert CommitmentKind.PROHIBITION.value == "prohibition"
        assert CommitmentKind.BOUNDARY.value == "boundary"
        assert CommitmentKind.DEPENDENCY.value == "dependency"
        assert CommitmentKind.EXCLUSION.value == "exclusion"
        assert CommitmentKind.REQUIREMENT.value == "requirement"

    def test_count(self):
        assert len(CommitmentKind) == 6


class TestTransportOutcome:
    def test_values(self):
        assert TransportOutcome.PRESERVED.value == "preserved"
        assert TransportOutcome.WEAKENED.value == "weakened"
        assert TransportOutcome.DROPPED.value == "dropped"
        assert TransportOutcome.CONTRADICTED.value == "contradicted"

    def test_count(self):
        assert len(TransportOutcome) == 4


class TestWeightsAndShear:
    def test_modality_weights(self):
        assert MODALITY_WEIGHT[Modality.MUST] == 1.0
        assert MODALITY_WEIGHT[Modality.MUST_NOT] == 1.0
        assert MODALITY_WEIGHT[Modality.SHOULD] == 0.7
        assert MODALITY_WEIGHT[Modality.MAY] == 0.3

    def test_outcome_shear(self):
        assert OUTCOME_SHEAR[TransportOutcome.PRESERVED] == 0.0
        assert OUTCOME_SHEAR[TransportOutcome.WEAKENED] == 0.5
        assert OUTCOME_SHEAR[TransportOutcome.DROPPED] == 1.0
        assert OUTCOME_SHEAR[TransportOutcome.CONTRADICTED] == 1.0


# ---------------------------------------------------------------------------
# Modality Detection
# ---------------------------------------------------------------------------


class TestDetectModality:
    def test_must(self):
        assert _detect_modality("You must use HTTPS for all API calls") == Modality.MUST

    def test_shall(self):
        assert _detect_modality("The system shall validate all inputs") == Modality.MUST

    def test_required(self):
        assert _detect_modality("Authentication is required for all endpoints") == Modality.MUST

    def test_always(self):
        assert _detect_modality("Always use parameterized queries") == Modality.MUST

    def test_must_not(self):
        assert _detect_modality("You must not store plaintext passwords") == Modality.MUST_NOT

    def test_never(self):
        assert _detect_modality("Never expose internal error details to users") == Modality.MUST_NOT

    def test_forbidden(self):
        assert _detect_modality("Direct database access is forbidden") == Modality.MUST_NOT

    def test_should(self):
        assert _detect_modality("You should prefer immutable data structures") == Modality.SHOULD

    def test_recommended(self):
        assert _detect_modality("It is recommended to use TypeScript") == Modality.SHOULD

    def test_may(self):
        assert _detect_modality("You may use optional chaining here") == Modality.MAY

    def test_optional(self):
        assert _detect_modality("Logging is optional in development") == Modality.MAY

    def test_no_modality(self):
        assert _detect_modality("This is a regular sentence about code") is None

    def test_must_not_before_must(self):
        """must not should be detected before must."""
        assert _detect_modality("You must not skip validation") == Modality.MUST_NOT

    def test_shall_not(self):
        assert _detect_modality("The system shall not expose secrets") == Modality.MUST_NOT


# ---------------------------------------------------------------------------
# Kind Detection
# ---------------------------------------------------------------------------


class TestDetectKind:
    def test_invariant(self):
        assert _detect_kind("Tests must always pass before merge", Modality.MUST) == CommitmentKind.INVARIANT

    def test_prohibition(self):
        assert _detect_kind("Never store passwords in plaintext", Modality.MUST_NOT) == CommitmentKind.PROHIBITION

    def test_boundary(self):
        assert _detect_kind("This only applies to src/auth/ directory", Modality.MUST) == CommitmentKind.BOUNDARY

    def test_dependency(self):
        assert _detect_kind("If the user is admin then skip validation", Modality.MUST) == CommitmentKind.DEPENDENCY

    def test_exclusion(self):
        assert _detect_kind("React and Vue are mutually exclusive", Modality.MUST) == CommitmentKind.EXCLUSION

    def test_requirement(self):
        assert _detect_kind("A valid API key is required", Modality.MUST) == CommitmentKind.REQUIREMENT

    def test_fallback_must(self):
        """Unknown kind with MUST modality defaults to REQUIREMENT."""
        assert _detect_kind("The service accepts JSON", Modality.MUST) == CommitmentKind.REQUIREMENT

    def test_fallback_must_not(self):
        """Unknown kind with MUST_NOT modality defaults to PROHIBITION."""
        assert _detect_kind("The service rejects XML", Modality.MUST_NOT) == CommitmentKind.PROHIBITION


# ---------------------------------------------------------------------------
# Scope Detection
# ---------------------------------------------------------------------------


class TestDetectScope:
    def test_only_applies_to(self):
        scope = _detect_scope("This rule only applies to src/auth/ directory")
        assert scope is not None
        assert "src/auth" in scope

    def test_limited_to(self):
        scope = _detect_scope("Access is limited to admin users")
        assert scope is not None
        assert "admin" in scope

    def test_restricted_to(self):
        scope = _detect_scope("Writes are restricted to the data layer")
        assert scope is not None
        assert "data layer" in scope

    def test_no_scope(self):
        assert _detect_scope("All inputs must be validated") is None

    def test_except_when(self):
        scope = _detect_scope("Always validate except when in test mode")
        assert scope is not None
        assert "test mode" in scope


# ---------------------------------------------------------------------------
# Commitment ID
# ---------------------------------------------------------------------------


class TestMakeCommitmentId:
    def test_deterministic(self):
        id1 = _make_commitment_id("You must use HTTPS")
        id2 = _make_commitment_id("You must use HTTPS")
        assert id1 == id2

    def test_case_insensitive(self):
        id1 = _make_commitment_id("You MUST use HTTPS")
        id2 = _make_commitment_id("you must use https")
        assert id1 == id2

    def test_length(self):
        cid = _make_commitment_id("Test obligation")
        assert len(cid) == 12


# ---------------------------------------------------------------------------
# Sentence Splitting
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_simple(self):
        sentences = _split_sentences("First sentence. Second sentence.")
        assert len(sentences) >= 2

    def test_with_offsets(self):
        text = "You must validate. Never skip auth."
        sentences = _split_sentences(text)
        for sent, start, end in sentences:
            assert text[start:end].strip() == sent.strip() or sent.strip() in text[start:end]

    def test_empty(self):
        assert _split_sentences("") == []

    def test_skips_short_fragments(self):
        sentences = _split_sentences("OK. Yes. This is a real sentence with content.")
        # Short fragments like "OK" and "Yes" should be skipped
        texts = [s[0] for s in sentences]
        assert any("real sentence" in t for t in texts)


# ---------------------------------------------------------------------------
# Token Jaccard
# ---------------------------------------------------------------------------


class TestTokenJaccard:
    def test_identical(self):
        assert _token_jaccard("hello world", "hello world") == 1.0

    def test_no_overlap(self):
        assert _token_jaccard("hello world", "foo bar") == 0.0

    def test_partial_overlap(self):
        score = _token_jaccard("must use HTTPS for API", "must use HTTPS for security")
        assert 0.4 < score < 0.9

    def test_empty(self):
        assert _token_jaccard("", "") == 0.0

    def test_case_insensitive(self):
        assert _token_jaccard("Hello World", "hello world") == 1.0


# ---------------------------------------------------------------------------
# Commitment Dataclass
# ---------------------------------------------------------------------------


class TestCommitment:
    def test_roundtrip(self):
        c = Commitment(
            commitment_id="abc123",
            text="You must validate all inputs",
            modality=Modality.MUST,
            kind=CommitmentKind.REQUIREMENT,
            scope="src/api/",
            source_span=(10, 45),
        )
        d = c.to_dict()
        c2 = Commitment.from_dict(d)
        assert c2.commitment_id == c.commitment_id
        assert c2.modality == c.modality
        assert c2.kind == c.kind
        assert c2.scope == c.scope

    def test_is_hard(self):
        assert Commitment("id", "text", Modality.MUST, CommitmentKind.REQUIREMENT).is_hard
        assert Commitment("id", "text", Modality.MUST_NOT, CommitmentKind.PROHIBITION).is_hard
        assert not Commitment("id", "text", Modality.SHOULD, CommitmentKind.REQUIREMENT).is_hard
        assert not Commitment("id", "text", Modality.MAY, CommitmentKind.REQUIREMENT).is_hard

    def test_weight(self):
        assert Commitment("id", "text", Modality.MUST, CommitmentKind.REQUIREMENT).weight == 1.0
        assert Commitment("id", "text", Modality.SHOULD, CommitmentKind.REQUIREMENT).weight == 0.7
        assert Commitment("id", "text", Modality.MAY, CommitmentKind.REQUIREMENT).weight == 0.3

    def test_no_scope(self):
        c = Commitment("id", "text", Modality.MUST, CommitmentKind.REQUIREMENT)
        d = c.to_dict()
        assert "scope" not in d


# ---------------------------------------------------------------------------
# CommitmentTransport Dataclass
# ---------------------------------------------------------------------------


class TestCommitmentTransport:
    def test_roundtrip(self):
        c = Commitment("id1", "You must validate", Modality.MUST, CommitmentKind.REQUIREMENT)
        t = CommitmentTransport(
            commitment=c,
            outcome=TransportOutcome.PRESERVED,
            detail="Preserved (similarity=0.95)",
            similarity=0.95,
        )
        d = t.to_dict()
        t2 = CommitmentTransport.from_dict(d)
        assert t2.outcome == TransportOutcome.PRESERVED
        assert t2.similarity == 0.95

    def test_is_blocking_dropped_must(self):
        c = Commitment("id", "text", Modality.MUST, CommitmentKind.REQUIREMENT)
        t = CommitmentTransport(c, TransportOutcome.DROPPED, "gone")
        assert t.is_blocking

    def test_is_blocking_contradicted_should(self):
        c = Commitment("id", "text", Modality.SHOULD, CommitmentKind.REQUIREMENT)
        t = CommitmentTransport(c, TransportOutcome.CONTRADICTED, "negated")
        assert t.is_blocking

    def test_not_blocking_dropped_may(self):
        c = Commitment("id", "text", Modality.MAY, CommitmentKind.REQUIREMENT)
        t = CommitmentTransport(c, TransportOutcome.DROPPED, "gone")
        assert not t.is_blocking

    def test_not_blocking_preserved(self):
        c = Commitment("id", "text", Modality.MUST, CommitmentKind.REQUIREMENT)
        t = CommitmentTransport(c, TransportOutcome.PRESERVED, "ok")
        assert not t.is_blocking

    def test_not_blocking_contradicted_may(self):
        c = Commitment("id", "text", Modality.MAY, CommitmentKind.REQUIREMENT)
        t = CommitmentTransport(c, TransportOutcome.CONTRADICTED, "negated")
        assert not t.is_blocking


# ---------------------------------------------------------------------------
# Commitment Extraction
# ---------------------------------------------------------------------------


class TestExtractCommitments:
    def test_must_obligation(self):
        text = "You must use HTTPS for all API calls."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        assert commitments[0].modality == Modality.MUST

    def test_prohibition(self):
        text = "You must not store plaintext passwords."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        assert commitments[0].modality == Modality.MUST_NOT

    def test_never(self):
        text = "Never expose internal error details to users."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        assert commitments[0].modality == Modality.MUST_NOT

    def test_should(self):
        text = "You should prefer immutable data structures."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        assert commitments[0].modality == Modality.SHOULD

    def test_may(self):
        text = "You may use optional chaining for convenience."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        assert commitments[0].modality == Modality.MAY

    def test_multiple_commitments(self):
        text = (
            "You must validate all inputs. "
            "Never store passwords in plaintext. "
            "You should prefer TypeScript over JavaScript."
        )
        commitments = extract_commitments(text)
        assert len(commitments) >= 3

    def test_empty_text(self):
        assert extract_commitments("") == []
        assert extract_commitments("   ") == []

    def test_no_obligations(self):
        text = "This is a normal sentence about writing code."
        commitments = extract_commitments(text)
        assert len(commitments) == 0

    def test_deduplication(self):
        text = "You must validate inputs. You must validate inputs."
        commitments = extract_commitments(text)
        assert len(commitments) == 1

    def test_scope_detection(self):
        text = "Validation is required, limited to the src/api/ directory."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        has_scope = any(c.scope is not None for c in commitments)
        assert has_scope

    def test_kind_detection_invariant(self):
        text = "Tests must always pass before any merge to main."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        assert commitments[0].kind == CommitmentKind.INVARIANT

    def test_kind_detection_prohibition(self):
        text = "Direct database access is forbidden in the API layer."
        commitments = extract_commitments(text)
        assert len(commitments) >= 1
        assert commitments[0].kind == CommitmentKind.PROHIBITION

    def test_source_spans(self):
        text = "You must validate. You should log."
        commitments = extract_commitments(text)
        for c in commitments:
            assert c.source_span[0] >= 0
            assert c.source_span[1] > c.source_span[0]


# ---------------------------------------------------------------------------
# Transport Classification
# ---------------------------------------------------------------------------


class TestClassifyTransport:
    def test_preserved(self):
        before = Commitment("id", "You must validate inputs", Modality.MUST, CommitmentKind.REQUIREMENT)
        after = Commitment("id", "You must validate inputs", Modality.MUST, CommitmentKind.REQUIREMENT)
        outcome, detail = _classify_transport(before, after, 1.0)
        assert outcome == TransportOutcome.PRESERVED

    def test_dropped(self):
        before = Commitment("id", "You must validate inputs", Modality.MUST, CommitmentKind.REQUIREMENT)
        outcome, detail = _classify_transport(before, None, 0.0)
        assert outcome == TransportOutcome.DROPPED

    def test_weakened_modality(self):
        before = Commitment("id", "You must validate inputs", Modality.MUST, CommitmentKind.REQUIREMENT)
        after = Commitment("id", "You should validate inputs", Modality.SHOULD, CommitmentKind.REQUIREMENT)
        outcome, detail = _classify_transport(before, after, 0.9)
        assert outcome == TransportOutcome.WEAKENED
        assert "modality" in detail.lower() or "softened" in detail.lower()

    def test_weakened_scope_loss(self):
        before = Commitment("id", "Validate only in src/api/", Modality.MUST, CommitmentKind.BOUNDARY, scope="src/api/")
        after = Commitment("id", "Validate inputs everywhere", Modality.MUST, CommitmentKind.REQUIREMENT, scope=None)
        outcome, detail = _classify_transport(before, after, 0.6)
        assert outcome == TransportOutcome.WEAKENED

    def test_contradicted_prohibition_to_permission(self):
        before = Commitment("id", "You must not store plaintext", Modality.MUST_NOT, CommitmentKind.PROHIBITION)
        after = Commitment("id", "You may store in any format", Modality.MAY, CommitmentKind.REQUIREMENT)
        outcome, detail = _classify_transport(before, after, 0.5)
        assert outcome == TransportOutcome.CONTRADICTED

    def test_weakened_low_similarity(self):
        before = Commitment("id", "Validate all user inputs thoroughly", Modality.MUST, CommitmentKind.REQUIREMENT)
        after = Commitment("id", "Check the data when possible", Modality.MUST, CommitmentKind.REQUIREMENT)
        outcome, detail = _classify_transport(before, after, 0.3)
        assert outcome == TransportOutcome.WEAKENED


# ---------------------------------------------------------------------------
# Transport Validation
# ---------------------------------------------------------------------------


class TestValidateTransport:
    def test_all_preserved(self):
        before = [
            Commitment("id1", "You must validate", Modality.MUST, CommitmentKind.REQUIREMENT),
            Commitment("id2", "You should log errors", Modality.SHOULD, CommitmentKind.REQUIREMENT),
        ]
        after = [
            Commitment("id1", "You must validate", Modality.MUST, CommitmentKind.REQUIREMENT),
            Commitment("id2", "You should log errors", Modality.SHOULD, CommitmentKind.REQUIREMENT),
        ]
        report = validate_transport(before, after)
        assert not report.blocking
        assert report.shear_score == 0.0

    def test_one_dropped(self):
        before = [
            Commitment("id1", "You must validate", Modality.MUST, CommitmentKind.REQUIREMENT),
            Commitment("id2", "You should log errors", Modality.SHOULD, CommitmentKind.REQUIREMENT),
        ]
        after = [
            Commitment("id2", "You should log errors", Modality.SHOULD, CommitmentKind.REQUIREMENT),
        ]
        report = validate_transport(before, after)
        assert report.blocking  # MUST commitment dropped
        assert report.shear_score > 0

    def test_all_dropped(self):
        before = [
            Commitment("id1", "You must validate", Modality.MUST, CommitmentKind.REQUIREMENT),
        ]
        report = validate_transport(before, [])
        assert report.blocking
        assert report.shear_score == 1.0

    def test_empty_before(self):
        report = validate_transport([], [])
        assert not report.blocking
        assert report.shear_score == 0.0

    def test_report_id_deterministic(self):
        before = [Commitment("id1", "You must validate", Modality.MUST, CommitmentKind.REQUIREMENT)]
        r1 = validate_transport(before, [])
        r2 = validate_transport(before, [])
        assert r1.report_id == r2.report_id


# ---------------------------------------------------------------------------
# ShearReport
# ---------------------------------------------------------------------------


class TestShearReport:
    def _make_report(self, outcomes: list[tuple[Modality, TransportOutcome]]) -> ShearReport:
        transports = []
        for i, (mod, out) in enumerate(outcomes):
            c = Commitment(f"id{i}", f"Commitment {i}", mod, CommitmentKind.REQUIREMENT)
            transports.append(CommitmentTransport(c, out, f"detail {i}"))
        return ShearReport(report_id="test", transports=transports)

    def test_shear_score_all_preserved(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.PRESERVED),
            (Modality.SHOULD, TransportOutcome.PRESERVED),
        ])
        assert report.shear_score == 0.0

    def test_shear_score_all_dropped(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.DROPPED),
        ])
        assert report.shear_score == 1.0

    def test_shear_score_mixed(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.PRESERVED),
            (Modality.SHOULD, TransportOutcome.DROPPED),
        ])
        # shear = (0.0*1.0 + 1.0*0.7) / (1.0 + 0.7) = 0.7/1.7 ≈ 0.4118
        assert 0.4 < report.shear_score < 0.42

    def test_hard_shear(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.DROPPED),
            (Modality.SHOULD, TransportOutcome.PRESERVED),
            (Modality.MUST_NOT, TransportOutcome.PRESERVED),
        ])
        # 1 of 2 hard commitments sheared
        assert report.hard_shear == 0.5

    def test_hard_shear_no_hard(self):
        report = self._make_report([
            (Modality.SHOULD, TransportOutcome.DROPPED),
        ])
        assert report.hard_shear == 0.0

    def test_blocking(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.DROPPED),
        ])
        assert report.blocking

    def test_not_blocking(self):
        report = self._make_report([
            (Modality.SHOULD, TransportOutcome.DROPPED),
        ])
        assert not report.blocking

    def test_outcome_counts(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.PRESERVED),
            (Modality.SHOULD, TransportOutcome.DROPPED),
            (Modality.MAY, TransportOutcome.WEAKENED),
        ])
        counts = report.outcome_counts
        assert counts["preserved"] == 1
        assert counts["dropped"] == 1
        assert counts["weakened"] == 1
        assert counts["contradicted"] == 0

    def test_hard_commitments(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.DROPPED),
            (Modality.SHOULD, TransportOutcome.DROPPED),
            (Modality.MUST_NOT, TransportOutcome.PRESERVED),
        ])
        hard = report.hard_commitments
        assert len(hard) == 1
        assert hard[0].modality == Modality.MUST

    def test_roundtrip(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.PRESERVED),
            (Modality.SHOULD, TransportOutcome.DROPPED),
        ])
        d = report.to_dict()
        r2 = ShearReport.from_dict(d)
        assert r2.report_id == report.report_id
        assert len(r2.transports) == 2
        assert r2.transports[0].outcome == TransportOutcome.PRESERVED

    def test_to_summary(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.DROPPED),
        ])
        summary = report.to_summary()
        assert "Blocking: True" in summary
        assert "BLOCKED" in summary

    def test_to_markdown(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.DROPPED),
        ])
        md = report.to_markdown()
        assert "# Shear Report" in md
        assert "YES" in md  # blocking = YES

    def test_content_hash(self):
        report = self._make_report([
            (Modality.MUST, TransportOutcome.PRESERVED),
        ])
        h = report.dedup_fingerprint
        assert len(h) == 16

    def test_empty(self):
        report = ShearReport(report_id="empty", transports=[])
        assert report.shear_score == 0.0
        assert report.hard_shear == 0.0
        assert not report.blocking


# ---------------------------------------------------------------------------
# check_transport (end-to-end convenience)
# ---------------------------------------------------------------------------


class TestCheckTransport:
    def test_identical_text(self):
        text = "You must validate all inputs. Never store passwords in plaintext."
        report = check_transport(text, text)
        assert report.shear_score == 0.0

    def test_dropped_obligation(self):
        before = "You must validate all inputs. Never store passwords in plaintext."
        after = "The system handles data processing."
        report = check_transport(before, after)
        assert report.shear_score > 0
        assert len(report.transports) >= 2

    def test_mixed_preservation(self):
        before = "You must validate inputs. You should log errors. You may cache results."
        after = "You must validate inputs. Logging is optional."
        report = check_transport(before, after)
        # At least must is preserved
        preserved = [t for t in report.transports if t.outcome == TransportOutcome.PRESERVED]
        assert len(preserved) >= 1

    def test_transform_type(self):
        report = check_transport("You must validate.", "You must validate.", "compaction")
        assert report.transform_type == "compaction"

    def test_negative_commitment_drop(self):
        """Negative commitments (MUST NOT) are high-risk for dropping."""
        before = "You must not expose internal error details to users. Secrets are forbidden in logs."
        after = "The system handles errors gracefully."
        report = check_transport(before, after)
        assert report.blocking  # Hard prohibitions dropped


# ---------------------------------------------------------------------------
# Transport History
# ---------------------------------------------------------------------------


class TestTransportHistory:
    def test_save_and_load(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        history = TransportHistory(gov_dir)

        report = ShearReport(
            report_id="test123",
            transports=[],
            transform_type="test",
        )
        path = history.save_report(report)
        assert path is not None
        assert path.exists()

        loaded = history.load_report("test123")
        assert loaded is not None
        assert loaded.report_id == "test123"

    def test_load_missing(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        history = TransportHistory(gov_dir)
        assert history.load_report("nonexistent") is None

    def test_list_reports(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        history = TransportHistory(gov_dir)

        for i in range(3):
            report = ShearReport(report_id=f"r{i}", transports=[], transform_type=f"t{i}")
            history.save_report(report)

        reports = history.list_reports()
        assert len(reports) == 3

    def test_stats(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        history = TransportHistory(gov_dir)

        # Save some reports with varying shear
        c = Commitment("id", "Must validate", Modality.MUST, CommitmentKind.REQUIREMENT)
        t1 = CommitmentTransport(c, TransportOutcome.PRESERVED, "ok")
        t2 = CommitmentTransport(c, TransportOutcome.DROPPED, "gone")

        history.save_report(ShearReport("r1", [t1], "t1"))
        history.save_report(ShearReport("r2", [t2], "t2"))

        stats = history.stats()
        assert stats["total_reports"] == 2
        assert stats["blocking_count"] == 1

    def test_stats_empty(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        history = TransportHistory(gov_dir)
        stats = history.stats()
        assert stats["total_reports"] == 0

    def test_no_governor_dir(self):
        history = TransportHistory()
        assert history.save_report(ShearReport("r", [], "t")) is None
        assert history.load_report("r") is None
        assert history.list_reports() == []


# ---------------------------------------------------------------------------
# Integration Wrappers
# ---------------------------------------------------------------------------


class TestValidateCompactionTransport:
    def test_preserved(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        before = "You must validate all user inputs before processing."
        after = "You must validate all user inputs before processing."
        report = validate_compaction_transport(before, after, gov_dir)
        assert report.transform_type == "compaction"
        assert not report.blocking

    def test_dropped(self):
        before = "You must validate all inputs. Never store secrets in logs."
        after = "The system processes data."
        report = validate_compaction_transport(before, after)
        assert report.blocking


class TestValidateBridgeTransport:
    def test_preserved(self):
        source = "Characters must always speak in their established voice."
        anchors = ["Characters must always speak in their established voice."]
        report = validate_bridge_transport(source, anchors, "fiction_bridge")
        assert report.transform_type == "fiction_bridge"
        assert not report.blocking

    def test_dropped(self):
        source = "Characters must never break the fourth wall. The tone must always be dark."
        anchors = ["Story has characters."]
        report = validate_bridge_transport(source, anchors, "fiction_bridge")
        assert report.shear_score > 0


class TestValidateConstraintTransport:
    def test_preserved(self):
        full = "You must use HTTPS. You should prefer JSON."
        summarized = "You must use HTTPS. JSON is preferred."
        report = validate_constraint_transport(full, summarized)
        assert report.transform_type == "constraint_projection"


# ---------------------------------------------------------------------------
# Telemetry Event
# ---------------------------------------------------------------------------


class TestMakeTransportEvent:
    def test_basic(self):
        report = ShearReport(report_id="test", transports=[], transform_type="test")
        event = make_transport_event(report)
        assert event["type"] == "commitment_transport"
        assert event["report_id"] == "test"
        assert "timestamp" in event
        assert event["shear_score"] == 0.0


# ---------------------------------------------------------------------------
# Golden Schema Tests
# ---------------------------------------------------------------------------


class TestGoldenSchemas:
    def test_commitment_schema(self):
        c = Commitment("id", "text", Modality.MUST, CommitmentKind.REQUIREMENT)
        d = c.to_dict()
        required = {"commitment_id", "text", "modality", "kind", "source_span"}
        assert required.issubset(d.keys())

    def test_transport_schema(self):
        c = Commitment("id", "text", Modality.MUST, CommitmentKind.REQUIREMENT)
        t = CommitmentTransport(c, TransportOutcome.PRESERVED, "ok", similarity=0.9)
        d = t.to_dict()
        required = {"commitment", "outcome", "detail", "similarity"}
        assert required.issubset(d.keys())

    def test_shear_report_schema(self):
        report = ShearReport(report_id="test", transports=[], transform_type="test")
        d = report.to_dict()
        required = {
            "report_id", "transports", "transform_type", "created_at",
            "shear_score", "hard_shear", "blocking", "outcome_counts",
            "total_commitments",
        }
        assert required == set(d.keys())

    def test_transport_event_schema(self):
        report = ShearReport(report_id="test", transports=[], transform_type="test")
        event = make_transport_event(report)
        required = {
            "type", "report_id", "transform_type", "shear_score",
            "hard_shear", "blocking", "outcome_counts",
            "total_commitments", "timestamp",
        }
        assert required == set(event.keys())


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_realistic_compaction(self, tmp_path):
        """Simulate realistic compaction that drops edge-case commitments."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        before = (
            "The API must validate all inputs before processing. "
            "Never expose internal error details to external users. "
            "Authentication is required for all endpoints. "
            "Rate limiting should be applied to prevent abuse. "
            "Logging is optional in development environments. "
            "The validation only applies to the src/api/ directory. "
        )

        # Compaction drops the negative commitment and the scope boundary
        after = (
            "The API must validate all inputs. "
            "Authentication is required. "
            "Rate limiting should be applied. "
        )

        report = validate_compaction_transport(before, after, gov_dir)

        # Should detect losses
        assert len(report.transports) >= 4
        assert report.shear_score > 0

        # History should be saved
        history = TransportHistory(gov_dir)
        reports = history.list_reports()
        assert len(reports) == 1

    def test_full_lifecycle(self, tmp_path):
        """Full lifecycle: extract → transform → validate → persist → query."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # 1. Original text with obligations
        original = (
            "You must use HTTPS for all API calls. "
            "Never store plaintext passwords. "
            "You should prefer immutable data structures. "
        )

        # 2. Extract commitments
        before_commitments = extract_commitments(original)
        assert len(before_commitments) >= 3

        # 3. Simulate lossy transform (compaction)
        compressed = "Use HTTPS for API calls. Data structures should be immutable."

        # 4. Extract from compressed
        after_commitments = extract_commitments(compressed)

        # 5. Validate transport
        report = validate_transport(
            before_commitments, after_commitments,
            transform_type="compaction",
        )

        # 6. Check results
        assert report.blocking  # "Never store plaintext passwords" was dropped

        # 7. Persist
        history = TransportHistory(gov_dir)
        history.save_report(report)

        # 8. Query
        loaded = history.load_report(report.report_id)
        assert loaded is not None
        assert loaded.blocking

        # 9. Stats
        stats = history.stats()
        assert stats["total_reports"] == 1
        assert stats["blocking_count"] == 1

    def test_no_obligations_no_shear(self):
        """Text without obligations produces zero shear."""
        before = "This is a regular paragraph about software architecture."
        after = "Software architecture is important."
        report = check_transport(before, after)
        assert report.shear_score == 0.0
        assert len(report.transports) == 0
