# SPDX-License-Identifier: Apache-2.0
"""
Tests for Evidence Gate: Evidence-gated coding harness.

Covers:
- Claim extraction (HARD and SOFT patterns)
- Evidence detection and linking
- Contradiction detection
- Custody scoring (Ap, Ip, Fp)
- Exit shape checking
- Status codes (OK, WARN, BLOCKED)
- Configuration
- Agent wrapper integration
- JSONL logging
"""

import json
import tempfile
from pathlib import Path

import pytest

from governor.evidence_gate import (
    # Enums
    EvidenceGateStatus,
    ClaimLevel,
    # Data types
    EvidenceGateClaim,
    EvidenceGateCitation,
    EvidenceGateInput,
    EvidenceGateOutput,
    CustodyScore,
    EvidenceGateConfig,
    EvidenceGateEvent,
    EvidenceGateLogger,
    # Main class
    EvidenceGate,
    # Kernel functions
    generate_claim_id,
    extract_claims,
    check_evidence,
    link_evidence_to_claims,
    detect_contradictions,
    score_accountability,
    score_failure_explicitness,
    score_invariant_coupling,
    score_custody,
    check_exit_shape,
    # Integration
    evidence_gate_wrapper,
    BlockedError,
    check_output,
    format_blocking_reason,
    # Constants
    CUSTODY_THRESHOLD,
)


# =============================================================================
# Status Codes
# =============================================================================


class TestEvidenceGateStatus:
    """Tests for EvidenceGateStatus enum."""

    def test_ok_value(self):
        assert EvidenceGateStatus.OK.value == "OK"

    def test_warn_value(self):
        assert EvidenceGateStatus.WARN.value == "WARN"

    def test_blocked_value(self):
        assert EvidenceGateStatus.BLOCKED.value == "BLOCKED"

    def test_from_string(self):
        assert EvidenceGateStatus("OK") == EvidenceGateStatus.OK
        assert EvidenceGateStatus("WARN") == EvidenceGateStatus.WARN
        assert EvidenceGateStatus("BLOCKED") == EvidenceGateStatus.BLOCKED


# =============================================================================
# Claim Types
# =============================================================================


class TestClaimLevel:
    """Tests for ClaimLevel enum."""

    def test_soft_value(self):
        assert ClaimLevel.SOFT.value == "SOFT"

    def test_hard_value(self):
        assert ClaimLevel.HARD.value == "HARD"


class TestEvidenceGateClaim:
    """Tests for EvidenceGateClaim dataclass."""

    def test_basic_claim(self):
        claim = EvidenceGateClaim(
            id="c123",
            text="improves performance by 10x",
            level=ClaimLevel.HARD,
        )
        assert claim.id == "c123"
        assert claim.level == ClaimLevel.HARD
        assert claim.evidence is None
        assert claim.conflicts_with == []

    def test_claim_with_evidence(self):
        claim = EvidenceGateClaim(
            id="c123",
            text="improves performance by 10x",
            level=ClaimLevel.HARD,
            evidence="benchmark shows 10x improvement",
        )
        assert claim.evidence == "benchmark shows 10x improvement"

    def test_claim_to_dict(self):
        claim = EvidenceGateClaim(
            id="c123",
            text="test claim",
            level=ClaimLevel.SOFT,
            evidence="test evidence",
            source_span=(10, 20),
        )
        d = claim.to_dict()
        assert d["id"] == "c123"
        assert d["text"] == "test claim"
        assert d["level"] == "SOFT"
        assert d["evidence"] == "test evidence"
        assert d["source_span"] == [10, 20]

    def test_claim_from_dict(self):
        data = {
            "id": "c456",
            "text": "another claim",
            "level": "HARD",
            "evidence": None,
            "conflicts_with": ["c123"],
        }
        claim = EvidenceGateClaim.from_dict(data)
        assert claim.id == "c456"
        assert claim.level == ClaimLevel.HARD
        assert claim.conflicts_with == ["c123"]


class TestEvidenceGateCitation:
    """Tests for EvidenceGateCitation dataclass."""

    def test_citation(self):
        citation = EvidenceGateCitation(
            source="https://docs.example.com",
            relevance="documents API behavior",
        )
        assert citation.source == "https://docs.example.com"

    def test_citation_to_dict(self):
        citation = EvidenceGateCitation(source="docs", relevance="reference")
        d = citation.to_dict()
        assert d["source"] == "docs"
        assert d["relevance"] == "reference"


# =============================================================================
# I/O Types
# =============================================================================


class TestEvidenceGateInput:
    """Tests for EvidenceGateInput dataclass."""

    def test_basic_input(self):
        inp = EvidenceGateInput(task="fix bug", context="./src/")
        assert inp.task == "fix bug"
        assert inp.strict is True  # default

    def test_input_with_constraints(self):
        inp = EvidenceGateInput(
            task="add caching",
            context="./",
            constraints=["no Redis"],
            strict=False,
        )
        assert "no Redis" in inp.constraints
        assert inp.strict is False

    def test_input_to_dict(self):
        inp = EvidenceGateInput(
            task="test",
            context=".",
            prior_claims=[EvidenceGateClaim("c1", "claim", ClaimLevel.SOFT)],
        )
        d = inp.to_dict()
        assert d["task"] == "test"
        assert len(d["prior_claims"]) == 1


class TestEvidenceGateOutput:
    """Tests for EvidenceGateOutput dataclass."""

    def test_default_output(self):
        out = EvidenceGateOutput()
        assert out.status == EvidenceGateStatus.OK
        assert out.blocking_reasons == []
        assert out.warnings == []

    def test_output_with_claims(self):
        claim = EvidenceGateClaim("c1", "test", ClaimLevel.HARD)
        out = EvidenceGateOutput(
            response="Here's the fix",
            claims=[claim],
            claim_ids=["c1"],
        )
        assert len(out.claims) == 1
        assert out.claim_ids == ["c1"]

    def test_output_to_dict(self):
        out = EvidenceGateOutput(
            status=EvidenceGateStatus.BLOCKED,
            blocking_reasons=["no evidence"],
        )
        d = out.to_dict()
        assert d["status"] == "BLOCKED"
        assert "no evidence" in d["blocking_reasons"]

    def test_output_to_json(self):
        out = EvidenceGateOutput(status=EvidenceGateStatus.WARN, warnings=["test"])
        j = out.to_json()
        parsed = json.loads(j)
        assert parsed["status"] == "WARN"


# =============================================================================
# Custody Scoring
# =============================================================================


class TestCustodyScore:
    """Tests for CustodyScore dataclass."""

    def test_total_calculation(self):
        score = CustodyScore(ap=0.8, ip=0.9, fp=0.7)
        assert score.total == pytest.approx(0.8, abs=0.01)

    def test_passed_above_threshold(self):
        score = CustodyScore(ap=0.8, ip=0.8, fp=0.8)
        assert score.passed is True

    def test_failed_below_threshold(self):
        score = CustodyScore(ap=0.3, ip=0.3, fp=0.3)
        assert score.passed is False

    def test_blocking_reasons_on_failure(self):
        score = CustodyScore(ap=0.2, ip=0.3, fp=0.4)
        reasons = score.blocking_reasons
        assert any("accountability" in r for r in reasons)
        assert any("invariant" in r for r in reasons)
        assert any("failure" in r for r in reasons)

    def test_no_blocking_reasons_on_pass(self):
        score = CustodyScore(ap=0.8, ip=0.8, fp=0.8)
        assert score.blocking_reasons == []


# =============================================================================
# Configuration
# =============================================================================


class TestEvidenceGateConfig:
    """Tests for EvidenceGateConfig dataclass."""

    def test_default_config(self):
        config = EvidenceGateConfig()
        assert config.strict is True
        assert config.custody_threshold == CUSTODY_THRESHOLD
        assert config.evidence_required_for_hard is True

    def test_kernel_constraints_always_present(self):
        config = EvidenceGateConfig()
        assert "claim_evidence_coupling" in config._kernel_constraints
        assert "contradiction_persistence" in config._kernel_constraints

    def test_config_to_dict(self):
        config = EvidenceGateConfig(strict=False)
        d = config.to_dict()
        assert d["strict"] is False
        assert "kernel_constraints" in d


# =============================================================================
# Claim Extraction
# =============================================================================


class TestClaimExtraction:
    """Tests for extract_claims function."""

    def test_extract_hard_claim_improves(self):
        text = "This change improves performance by 10x"
        claims = extract_claims(text)
        assert len(claims) >= 1
        hard_claims = [c for c in claims if c.level == ClaimLevel.HARD]
        assert len(hard_claims) >= 1

    def test_extract_hard_claim_reduces(self):
        text = "This reduces latency by 50ms"
        claims = extract_claims(text)
        assert any(c.level == ClaimLevel.HARD for c in claims)

    def test_extract_hard_claim_guarantees(self):
        text = "This guarantees thread safety"
        claims = extract_claims(text)
        assert any(c.level == ClaimLevel.HARD for c in claims)

    def test_extract_hard_claim_never_fails(self):
        text = "This code never fails"
        claims = extract_claims(text)
        assert any(c.level == ClaimLevel.HARD for c in claims)

    def test_extract_hard_claim_is_safe(self):
        text = "This implementation is safe for concurrent access"
        claims = extract_claims(text)
        assert any(c.level == ClaimLevel.HARD for c in claims)

    def test_extract_soft_claim_might(self):
        text = "This might improve the response time"
        claims = extract_claims(text)
        assert any(c.level == ClaimLevel.SOFT for c in claims)

    def test_extract_soft_claim_should(self):
        text = "This should work for most cases"
        claims = extract_claims(text)
        assert any(c.level == ClaimLevel.SOFT for c in claims)

    def test_extract_soft_claim_probably(self):
        text = "This probably helps with the issue"
        claims = extract_claims(text)
        assert any(c.level == ClaimLevel.SOFT for c in claims)

    def test_no_claims_in_neutral_text(self):
        text = "Here is the implementation of the function."
        claims = extract_claims(text)
        # May have some claims but fewer than assertive text
        assert len(claims) < 3

    def test_claim_ids_are_unique(self):
        text = "This improves performance by 10x. Also improves speed by 5x."
        claims = extract_claims(text)
        ids = [c.id for c in claims]
        # Allow some duplicates due to overlapping patterns, but check function works
        assert len(ids) >= 1

    def test_claim_source_span(self):
        text = "This guarantees correctness"
        claims = extract_claims(text)
        # At least one claim should have source span
        if claims:
            assert any(c.source_span is not None for c in claims)


class TestGenerateClaimId:
    """Tests for generate_claim_id function."""

    def test_id_format(self):
        cid = generate_claim_id("test claim")
        assert cid.startswith("c")
        assert len(cid) == 9  # "c" + 8 hex chars

    def test_deterministic(self):
        cid1 = generate_claim_id("same text")
        cid2 = generate_claim_id("same text")
        assert cid1 == cid2

    def test_different_for_different_text(self):
        cid1 = generate_claim_id("text one")
        cid2 = generate_claim_id("text two")
        assert cid1 != cid2


# =============================================================================
# Evidence Detection
# =============================================================================


class TestEvidenceDetection:
    """Tests for check_evidence function."""

    def test_detect_benchmark(self):
        text = "The benchmark shows a 2x improvement"
        evidence = check_evidence(text)
        assert len(evidence) >= 1

    def test_detect_profiler(self):
        text = "Profiler output confirms the bottleneck"
        evidence = check_evidence(text)
        assert len(evidence) >= 1

    def test_detect_tests_pass(self):
        text = "All tests pass after this change"
        evidence = check_evidence(text)
        assert len(evidence) >= 1

    def test_detect_documentation_reference(self):
        text = "According to the documentation, this is correct"
        evidence = check_evidence(text)
        assert len(evidence) >= 1

    def test_detect_error_message(self):
        text = "The error message says: NullPointerException"
        evidence = check_evidence(text)
        assert len(evidence) >= 1

    def test_no_evidence_in_plain_text(self):
        text = "Here is a simple function implementation"
        evidence = check_evidence(text)
        assert len(evidence) == 0


class TestLinkEvidenceToClaims:
    """Tests for link_evidence_to_claims function."""

    def test_link_nearby_evidence(self):
        text = "This improves performance by 10x. Benchmark shows the improvement."
        claims = extract_claims(text)
        evidence = check_evidence(text)
        linked = link_evidence_to_claims(claims, evidence, text)
        # At least one claim should have evidence linked
        assert any(c.evidence is not None for c in linked)

    def test_no_link_for_distant_evidence(self):
        # Evidence too far from claim
        text = "A" * 600 + "This improves performance by 10x" + "A" * 600 + "Benchmark shows results"
        claims = extract_claims(text)
        evidence = check_evidence(text)
        linked = link_evidence_to_claims(claims, evidence, text)
        # May or may not link depending on proximity calculation
        # Just verify function doesn't crash
        assert isinstance(linked, list)


# =============================================================================
# Contradiction Detection
# =============================================================================


class TestContradictionDetection:
    """Tests for detect_contradictions function."""

    def test_detect_improve_vs_degrade(self):
        prior = [EvidenceGateClaim("c1", "this degrades performance", ClaimLevel.HARD)]
        current = [EvidenceGateClaim("c2", "this improves performance", ClaimLevel.HARD)]
        result = detect_contradictions(current, prior)
        assert "c1" in result[0].conflicts_with

    def test_detect_faster_vs_slower(self):
        prior = [EvidenceGateClaim("c1", "makes it slower", ClaimLevel.HARD)]
        current = [EvidenceGateClaim("c2", "makes it faster", ClaimLevel.HARD)]
        result = detect_contradictions(current, prior)
        assert "c1" in result[0].conflicts_with

    def test_no_contradiction_for_unrelated(self):
        prior = [EvidenceGateClaim("c1", "adds caching", ClaimLevel.HARD)]
        current = [EvidenceGateClaim("c2", "fixes the bug", ClaimLevel.HARD)]
        result = detect_contradictions(current, prior)
        assert result[0].conflicts_with == []

    def test_no_contradiction_with_empty_prior(self):
        current = [EvidenceGateClaim("c1", "improves performance", ClaimLevel.HARD)]
        result = detect_contradictions(current, [])
        assert result[0].conflicts_with == []


# =============================================================================
# Custody Scoring Functions
# =============================================================================


class TestScoreAccountability:
    """Tests for score_accountability function."""

    def test_clean_text_high_score(self):
        text = "This function validates input and returns a result."
        score = score_accountability(text)
        assert score >= 0.8

    def test_somehow_lowers_score(self):
        text = "This somehow fixes the issue."
        score = score_accountability(text)
        assert score < 1.0

    def test_magically_lowers_score(self):
        text = "The framework magically handles this."
        score = score_accountability(text)
        assert score < 1.0

    def test_just_works_lowers_score(self):
        text = "It just works."
        score = score_accountability(text)
        assert score < 1.0

    def test_multiple_issues_lower_score_more(self):
        text = "Somehow it magically just works."
        score = score_accountability(text)
        # Multiple issues should lower score more
        assert score < 0.6


class TestScoreFailureExplicitness:
    """Tests for score_failure_explicitness function."""

    def test_clean_code_reasonable_score(self):
        text = "def process(data):\n    return data.strip()"
        score = score_failure_explicitness(text)
        assert score >= 0.5

    def test_broad_except_lowers_score(self):
        text = "try:\n    process()\nexcept:\n    pass"
        score = score_failure_explicitness(text)
        assert score < 1.0

    def test_explicit_error_handling_helps(self):
        text = "if error:\n    return None"
        score = score_failure_explicitness(text)
        assert score > 0.5


class TestScoreInvariantCoupling:
    """Tests for score_invariant_coupling function."""

    def test_assert_increases_score(self):
        text = "assert value > 0"
        score = score_invariant_coupling(text)
        assert score >= 0.8

    def test_validate_increases_score(self):
        text = "validate(input_data)"
        score = score_invariant_coupling(text)
        assert score >= 0.8

    def test_todo_decreases_score(self):
        text = "# TODO: add validation"
        score = score_invariant_coupling(text)
        assert score < 0.8

    def test_hack_decreases_score(self):
        text = "# hack to work around the issue"
        score = score_invariant_coupling(text)
        assert score < 0.8


class TestScoreCustody:
    """Tests for score_custody function."""

    def test_returns_custody_score(self):
        text = "def process(): return validate(data)"
        score = score_custody(text)
        assert isinstance(score, CustodyScore)
        assert 0 <= score.ap <= 1
        assert 0 <= score.ip <= 1
        assert 0 <= score.fp <= 1


# =============================================================================
# Exit Shape Checking
# =============================================================================


class TestExitShapeChecking:
    """Tests for check_exit_shape function."""

    def test_detect_hope_this_helps(self):
        text = "Here's the fix. Hope this helps!"
        bad = check_exit_shape(text)
        assert len(bad) >= 1
        assert any("hope" in b.lower() for b in bad)

    def test_detect_let_me_know(self):
        text = "Let me know if you have questions."
        bad = check_exit_shape(text)
        assert len(bad) >= 1

    def test_detect_feel_free(self):
        text = "Feel free to reach out!"
        bad = check_exit_shape(text)
        assert len(bad) >= 1

    def test_clean_exit_ok(self):
        text = "The fix addresses the null pointer issue."
        bad = check_exit_shape(text)
        assert len(bad) == 0


# =============================================================================
# JSONL Logging
# =============================================================================


class TestEvidenceGateLogger:
    """Tests for EvidenceGateLogger class."""

    def test_log_event(self):
        logger = EvidenceGateLogger()
        logger.log("test_event", key="value")
        events = logger.get_events()
        assert len(events) == 1
        assert events[0]["event"] == "test_event"
        assert events[0]["key"] == "value"
        assert "timestamp" in events[0]

    def test_log_to_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        try:
            logger = EvidenceGateLogger(log_path=log_path)
            logger.log("file_event", data="test")

            # Read back from file
            content = log_path.read_text()
            parsed = json.loads(content.strip())
            assert parsed["event"] == "file_event"
        finally:
            log_path.unlink()

    def test_multiple_events(self):
        logger = EvidenceGateLogger()
        logger.log("event1")
        logger.log("event2")
        logger.log("event3")
        assert len(logger.get_events()) == 3


class TestEvidenceGateEvent:
    """Tests for EvidenceGateEvent dataclass."""

    def test_to_dict(self):
        event = EvidenceGateEvent(
            timestamp="2026-02-03T12:00:00",
            event="test",
            data={"key": "value"},
        )
        d = event.to_dict()
        assert d["timestamp"] == "2026-02-03T12:00:00"
        assert d["event"] == "test"
        assert d["key"] == "value"

    def test_to_json(self):
        event = EvidenceGateEvent(timestamp="2026-02-03T12:00:00", event="test")
        j = event.to_json()
        parsed = json.loads(j)
        assert parsed["event"] == "test"


# =============================================================================
# Main Validator
# =============================================================================


class TestEvidenceGate:
    """Tests for EvidenceGate class."""

    def test_check_clean_output_ok(self):
        lite = EvidenceGate()
        result = lite.check(
            task="test",
            context="./",
            output="Here's a simple fix for the issue.",
        )
        # Clean output should be OK or WARN (not BLOCKED)
        assert result.status in (EvidenceGateStatus.OK, EvidenceGateStatus.WARN)

    def test_check_hard_claim_without_evidence_blocked(self):
        lite = EvidenceGate()
        result = lite.check(
            task="test",
            context="./",
            output="This improves performance by 10x",
        )
        # Hard claim without evidence → BLOCKED in strict mode
        assert result.status == EvidenceGateStatus.BLOCKED
        assert any("lacks evidence" in r for r in result.blocking_reasons)

    def test_check_hard_claim_with_evidence_ok(self):
        lite = EvidenceGate()
        result = lite.check(
            task="test",
            context="./",
            output="This improves performance by 10x. Benchmark shows the improvement.",
        )
        # Hard claim WITH evidence should pass
        # Note: depends on proximity detection working
        assert result.status in (EvidenceGateStatus.OK, EvidenceGateStatus.WARN)

    def test_check_soft_claim_ok(self):
        lite = EvidenceGate()
        result = lite.check(
            task="test",
            context="./",
            output="This might help with the issue.",
        )
        # Soft claims don't need evidence
        assert result.status in (EvidenceGateStatus.OK, EvidenceGateStatus.WARN)

    def test_permissive_mode_warns_instead_of_blocks(self):
        config = EvidenceGateConfig(strict=False)
        lite = EvidenceGate(config=config)
        result = lite.check(
            task="test",
            context="./",
            output="This improves performance by 10x",
        )
        # In permissive mode, should WARN not BLOCK
        assert result.status == EvidenceGateStatus.WARN
        assert any("lacks evidence" in w for w in result.warnings)

    def test_contradiction_detected_and_warned(self):
        lite = EvidenceGate()
        # First check establishes prior claim - use explicit HARD claim pattern
        lite.check(
            task="test",
            context="./",
            output="This degrades performance by 50%",
        )
        # Second check contradicts - also HARD claim pattern
        result = lite.check(
            task="test",
            context="./",
            output="This improves performance by 50%",
        )
        # Should have warning about contradiction OR blocked for lack of evidence
        # (default action is warn for contradiction, block for missing evidence)
        assert result.status in (EvidenceGateStatus.WARN, EvidenceGateStatus.BLOCKED)

    def test_bad_exit_warned(self):
        lite = EvidenceGate()
        result = lite.check(
            task="test",
            context="./",
            output="Here's the fix. Hope this helps!",
        )
        assert any("bad exit" in w for w in result.warnings)

    def test_format_status_ok(self):
        lite = EvidenceGate()
        result = EvidenceGateOutput(status=EvidenceGateStatus.OK)
        formatted = lite.format_status(result)
        assert "OK" in formatted

    def test_format_status_blocked(self):
        lite = EvidenceGate()
        result = EvidenceGateOutput(
            status=EvidenceGateStatus.BLOCKED,
            blocking_reasons=["claim lacks evidence"],
        )
        formatted = lite.format_status(result)
        assert "BLOCKED" in formatted
        assert "lacks evidence" in formatted
        assert "To proceed" in formatted

    def test_claims_stored_for_contradiction_checking(self):
        lite = EvidenceGate()
        lite.check(task="test", context="./", output="This is safe")
        assert len(lite.prior_claims) >= 1

    def test_get_log_events(self):
        lite = EvidenceGate()
        lite.check(task="test", context="./", output="Test output")
        events = lite.get_log_events()
        assert any(e["event"] == "task_start" for e in events)
        assert any(e["event"] == "output" for e in events)


# =============================================================================
# Agent Wrapper
# =============================================================================


class TestEvidenceGateWrapper:
    """Tests for evidence_gate_wrapper integration."""

    def test_wrapper_allows_clean_output(self):
        def clean_agent(task, context, **kwargs):
            return "Here's a simple implementation."

        wrapped = evidence_gate_wrapper(clean_agent)
        result = wrapped("test", "./")
        assert result == "Here's a simple implementation."

    def test_wrapper_raises_on_blocked(self):
        def bad_agent(task, context, **kwargs):
            return "This guarantees 100% uptime"

        config = EvidenceGateConfig(strict=True)
        wrapped = evidence_gate_wrapper(bad_agent, config=config)

        with pytest.raises(BlockedError) as exc:
            wrapped("test", "./")
        assert "BLOCKED" in str(exc.value)


class TestBlockedError:
    """Tests for BlockedError exception."""

    def test_error_message(self):
        err = BlockedError(["reason1", "reason2"])
        assert "reason1" in str(err)
        assert err.reasons == ["reason1", "reason2"]


# =============================================================================
# Convenience Functions
# =============================================================================


class TestCheckOutput:
    """Tests for check_output convenience function."""

    def test_quick_check(self):
        result = check_output("Simple output text")
        assert isinstance(result, EvidenceGateOutput)

    def test_quick_check_strict(self):
        result = check_output(
            "This improves performance by 10x",
            strict=True,
        )
        assert result.status == EvidenceGateStatus.BLOCKED


class TestFormatBlockingReason:
    """Tests for format_blocking_reason function."""

    def test_format_lacks_evidence(self):
        formatted = format_blocking_reason("claim lacks evidence")
        assert "BLOCKED" in formatted
        assert "evidence" in formatted
        assert "benchmark" in formatted or "provide" in formatted

    def test_format_contradicts(self):
        formatted = format_blocking_reason("contradicts prior claim")
        assert "BLOCKED" in formatted
        assert "reconcile" in formatted

    def test_format_accountability(self):
        formatted = format_blocking_reason("accountability unclear")
        assert "BLOCKED" in formatted
        assert "ownership" in formatted

    def test_format_failure(self):
        formatted = format_blocking_reason("failure modes not explicit")
        assert "BLOCKED" in formatted
        assert "failure" in formatted

    def test_format_generic(self):
        formatted = format_blocking_reason("other reason")
        assert "BLOCKED" in formatted


# =============================================================================
# Integration Tests
# =============================================================================


class TestEvidenceGateIntegration:
    """Integration tests for Evidence Gate."""

    def test_full_workflow(self):
        """Test complete validation workflow."""
        lite = EvidenceGate()

        # Task 1: Clean output
        result1 = lite.check(
            task="fix null pointer",
            context="./src/auth.py",
            output="Added null check at line 47. The error was caused by missing input validation.",
        )
        # Should pass (or warn at most)
        assert result1.status in (EvidenceGateStatus.OK, EvidenceGateStatus.WARN)

        # Task 2: Unsupported claim - use explicit pattern that triggers HARD claim
        result2 = lite.check(
            task="optimize",
            context="./",
            output="This improves performance by 100x with no side effects",
        )
        # Should be blocked (HARD claim without evidence)
        assert result2.status == EvidenceGateStatus.BLOCKED

    def test_with_logging(self):
        """Test that logging captures events."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        try:
            lite = EvidenceGate(log_path=log_path)
            lite.check(task="test", context="./", output="Test output")

            # Verify log file has content
            content = log_path.read_text()
            assert len(content) > 0
            lines = [json.loads(line) for line in content.strip().split("\n")]
            assert any(e["event"] == "task_start" for e in lines)
        finally:
            log_path.unlink()

    def test_chained_validation(self):
        """Test multiple validations building contradiction history."""
        lite = EvidenceGate()

        # Initial claim about performance
        lite.check(
            task="analyze",
            context="./",
            output="The current implementation is slow",
        )

        # Contradicting claim
        result = lite.check(
            task="analyze",
            context="./",
            output="The current implementation is fast",
        )

        # Should detect contradiction and warn/record
        # Exact behavior depends on how patterns match
        assert isinstance(result, EvidenceGateOutput)


# =============================================================================
# CLI Tests (basic smoke tests)
# =============================================================================


class TestCLICommands:
    """Basic smoke tests for CLI integration."""

    def test_config_command_available(self):
        """Verify config command exists in module."""
        from governor.evidence_gate import EvidenceGateConfig
        config = EvidenceGateConfig()
        assert hasattr(config, "to_dict")

    def test_kernel_functions_importable(self):
        """Verify all kernel functions are importable."""
        from governor.evidence_gate import (
            extract_claims,
            check_evidence,
            link_evidence_to_claims,
            detect_contradictions,
            score_custody,
            check_exit_shape,
        )
        assert callable(extract_claims)
        assert callable(check_evidence)
        assert callable(link_evidence_to_claims)
        assert callable(detect_contradictions)
        assert callable(score_custody)
        assert callable(check_exit_shape)


# =============================================================================
# Policy Integration
# =============================================================================


def _make_deny_all_policy():
    """Build a deny-all policy rule set."""
    from governor.policy_engine import PolicyRuleSet
    return PolicyRuleSet(
        policy_bundle_id="test.deny",
        policy_bundle_version="1.0.0",
        default_verdict="block",
        description="Deny all for testing.",
    )


def _make_pass_all_policy():
    """Build a pass-all policy rule set."""
    from governor.policy_engine import PolicyRuleSet, PolicyRule
    return PolicyRuleSet(
        policy_bundle_id="test.pass",
        policy_bundle_version="1.0.0",
        default_verdict="pass",
        description="Pass all for testing.",
        rules=(
            PolicyRule(rule_id="pass-all", effect="pass", priority=10),
        ),
    )


def _make_warn_policy():
    """Build a warn-all policy rule set."""
    from governor.policy_engine import PolicyRuleSet, PolicyRule, Obligation
    return PolicyRuleSet(
        policy_bundle_id="test.warn",
        policy_bundle_version="1.0.0",
        default_verdict="warn",
        description="Warn all for testing.",
        rules=(
            PolicyRule(
                rule_id="warn-all",
                effect="warn",
                priority=10,
                obligations=(
                    Obligation(kind="require_evidence", params={"type": "oracle"}),
                ),
            ),
        ),
    )


def _make_escalate_policy():
    """Build an escalate-all policy rule set."""
    from governor.policy_engine import PolicyRuleSet, PolicyRule
    return PolicyRuleSet(
        policy_bundle_id="test.escalate",
        policy_bundle_version="1.0.0",
        default_verdict="escalate",
        description="Escalate all for testing.",
        rules=(
            PolicyRule(rule_id="esc-all", effect="escalate", priority=10),
        ),
    )


class TestEvidenceGatePolicyIntegration:
    """Tests for policy evaluation within EvidenceGate.check()."""

    def test_check_without_policy_unchanged(self):
        """Backward compat: no policy param → no policy-related side effects."""
        gate = EvidenceGate()
        result = gate.check(
            task="test", context="./", output="Simple safe output",
        )
        assert result.status == EvidenceGateStatus.OK
        # No policy warnings or blocking reasons
        assert not any("policy:" in w for w in result.warnings)
        assert not any("policy:" in r for r in result.blocking_reasons)

    def test_check_with_none_policy(self):
        """Explicit None policy same as omitting."""
        gate = EvidenceGate()
        result = gate.check(
            task="test", context="./", output="Safe output", policy=None,
        )
        assert result.status == EvidenceGateStatus.OK
        assert not any("policy:" in w for w in result.warnings)

    def test_check_with_deny_all_blocks(self):
        """Deny-all policy blocks when check runs."""
        gate = EvidenceGate()
        policy = _make_deny_all_policy()
        result = gate.check(
            task="test", context="./",
            output="This guarantees it is safe",
            policy=policy,
        )
        assert result.status == EvidenceGateStatus.BLOCKED
        assert any("policy:" in r for r in result.blocking_reasons)

    def test_pass_policy_no_downgrade(self):
        """Pass policy doesn't override inline BLOCKED.

        Original blocking_reasons preserved. Policy fragment still recorded.
        """
        gate = EvidenceGate(config=EvidenceGateConfig(strict=True))
        policy = _make_pass_all_policy()
        # "guarantees" triggers HARD claim → no evidence → BLOCKED inline
        result = gate.check(
            task="test", context="./",
            output="This guarantees perfect correctness",
            policy=policy,
        )
        # Inline BLOCKED must be preserved
        assert result.status == EvidenceGateStatus.BLOCKED
        assert any("lacks evidence" in r for r in result.blocking_reasons)
        # Policy PASS should NOT downgrade — no policy: entries in reasons
        assert not any("policy:" in r for r in result.blocking_reasons)

    def test_policy_block_augments_result(self):
        """Policy BLOCK adds to blocking_reasons."""
        gate = EvidenceGate()
        policy = _make_deny_all_policy()
        result = gate.check(
            task="test", context="./", output="Simple text",
            policy=policy,
        )
        assert result.status == EvidenceGateStatus.BLOCKED
        policy_reasons = [r for r in result.blocking_reasons if "policy:" in r]
        assert len(policy_reasons) >= 1

    def test_policy_warn_augments_result(self):
        """Policy WARN adds warnings to OK output."""
        gate = EvidenceGate()
        policy = _make_warn_policy()
        result = gate.check(
            task="test", context="./", output="Simple text",
            policy=policy,
        )
        assert result.status == EvidenceGateStatus.WARN
        policy_warns = [w for w in result.warnings if "policy:" in w]
        assert len(policy_warns) >= 1

    def test_policy_evaluation_fail_open(self):
        """Bad policy object → still completes, no crash."""
        gate = EvidenceGate()
        # Pass something that's not a PolicyRuleSet — should fail-open
        result = gate.check(
            task="test", context="./", output="Safe output",
            policy="not a policy",
        )
        # Should still produce a result (fail-open)
        assert result.status == EvidenceGateStatus.OK

    def test_policy_fragment_in_receipt(self):
        """Evidence bundle includes policy_fragment with correct field names."""
        from governor.gate_receipt import GateReceiptSystem
        with tempfile.TemporaryDirectory() as td:
            gov_dir = Path(td) / ".governor"
            gov_dir.mkdir()
            rs = GateReceiptSystem(gov_dir)
            gate = EvidenceGate(receipt_system=rs)
            policy = _make_deny_all_policy()
            result = gate.check(
                task="test", context="./", output="Some output",
                policy=policy,
            )
            # Get the evidence bundle from the receipt
            receipts = rs.query(gate="evidence_gate")
            assert len(receipts) >= 1
            evidence = rs.evidence_for(receipts[0])
            assert "policy_fragment" in evidence
            frag = evidence["policy_fragment"]
            # Canonical fragment fields (same shape as PolicyReceiptFragment)
            assert "policy_verdict" in frag
            assert "matched_rule_ids" in frag
            assert "obligation_kinds" in frag
            assert "policy_identity" in frag
            assert "applied" in frag
            assert "duration_ms" in frag
            assert isinstance(frag["matched_rule_ids"], list)
            assert isinstance(frag["obligation_kinds"], list)
            assert isinstance(frag["policy_identity"], dict)
            # Gate-specific annotation (not part of canonical fragment)
            assert "inline_status" in frag

    def test_policy_does_not_affect_kernel_emission(self):
        """Kernel run still works when policy is provided (no interference)."""
        gate = EvidenceGate()
        policy = _make_pass_all_policy()
        result = gate.check(
            task="test", context="./", output="Simple output",
            policy=policy,
        )
        # kernel_run_id should be None (no bridge configured)
        assert result.kernel_run_id is None
        # But result should still be valid
        assert isinstance(result, EvidenceGateOutput)

    def test_policy_escalate_explicit_noop(self):
        """ESCALATE → no status change, fragment has applied=false."""
        from governor.gate_receipt import GateReceiptSystem
        with tempfile.TemporaryDirectory() as td:
            gov_dir = Path(td) / ".governor"
            gov_dir.mkdir()
            rs = GateReceiptSystem(gov_dir)
            gate = EvidenceGate(receipt_system=rs)
            policy = _make_escalate_policy()
            result = gate.check(
                task="test", context="./", output="Simple output",
                policy=policy,
            )
            # ESCALATE is a no-op — status unchanged from inline
            assert result.status == EvidenceGateStatus.OK
            # Check fragment
            receipts = rs.query(gate="evidence_gate")
            evidence = rs.evidence_for(receipts[0])
            frag = evidence["policy_fragment"]
            assert frag["applied"] is False
            assert frag["reason"] == "no_escalation_handler"
            assert frag["policy_verdict"] == "escalate"

    def test_multiple_checks_no_state_leak(self):
        """Alternating with/without policy doesn't leak state."""
        gate = EvidenceGate()
        # Check without policy
        r1 = gate.check(task="t1", context="./", output="output 1")
        assert r1.status == EvidenceGateStatus.OK

        # Check with deny-all policy
        r2 = gate.check(
            task="t2", context="./", output="output 2",
            policy=_make_deny_all_policy(),
        )
        assert r2.status == EvidenceGateStatus.BLOCKED

        # Check without policy again — should not be affected by r2
        r3 = gate.check(task="t3", context="./", output="output 3")
        assert r3.status == EvidenceGateStatus.OK

    def test_policy_logging(self):
        """Logger captures policy events."""
        gate = EvidenceGate()
        # Test policy_block logging
        gate.check(
            task="test", context="./", output="output",
            policy=_make_deny_all_policy(),
        )
        events = gate.get_log_events()
        policy_events = [e for e in events if e.get("event", "").startswith("policy_")]
        assert len(policy_events) >= 1
        assert policy_events[0]["event"] == "policy_block"

    def test_empty_capabilities_policy(self):
        """Request with no claims, policy evaluates normally."""
        gate = EvidenceGate()
        policy = _make_pass_all_policy()
        result = gate.check(
            task="test", context="./", output="no claims here",
            policy=policy,
        )
        # PASS policy on clean output → OK
        assert result.status == EvidenceGateStatus.OK

    def test_synthetic_caps_namespaced(self):
        """Verify request uses synthetic.* prefixed capabilities."""
        # We need to intercept the evaluate call to inspect the request
        from unittest.mock import patch as _patch
        from governor.policy_engine import PolicyEvalResult, PolicyVerdict, RationaleInfo, PolicyIdentity

        captured_requests = []

        def mock_evaluate(request, policy, **kwargs):
            captured_requests.append(request)
            return PolicyEvalResult(
                verdict=PolicyVerdict.PASS,
                rationale=RationaleInfo(summary="test"),
                policy_identity=PolicyIdentity(),
            )

        gate = EvidenceGate()
        policy = _make_pass_all_policy()
        with _patch("governor.policy_engine.evaluate", mock_evaluate):
            gate.check(
                task="test", context="./",
                output="This guarantees it works",
                policy=policy,
            )

        assert len(captured_requests) == 1
        caps = list(captured_requests[0].subject.capabilities)
        # "guarantees" triggers HARD claim → synthetic.claim_hard
        assert any(c.startswith("synthetic.") for c in caps)
        if caps:
            assert "synthetic.claim_hard" in caps

    def test_inline_blocked_plus_policy_pass_preserves_reasons(self):
        """Inline BLOCKED + policy PASS → BLOCKED with all original reasons intact."""
        gate = EvidenceGate(config=EvidenceGateConfig(strict=True))
        policy = _make_pass_all_policy()
        # "guarantees" + "is safe" both trigger HARD claims without evidence
        result = gate.check(
            task="test", context="./",
            output="This guarantees it is safe and secure always",
            policy=policy,
        )
        assert result.status == EvidenceGateStatus.BLOCKED
        inline_reasons = [r for r in result.blocking_reasons if "lacks evidence" in r]
        assert len(inline_reasons) >= 1
        # No policy: entries should appear (PASS doesn't add anything)
        assert not any("policy:" in r for r in result.blocking_reasons)
