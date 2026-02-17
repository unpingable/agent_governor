# SPDX-License-Identifier: Apache-2.0
"""Tests for code interferometry — code-specific divergence analysis."""

import pytest

from governor.code_interferometry import (
    AnchorConflict,
    AnchorConflictType,
    CodeArtifact,
    CodeDivergenceReport,
    CodeInterferometryConfig,
    MARKER_CATEGORIES,
    RiskCategory,
    RiskMarker,
    RiskMarkerType,
    check_anchor_compatibility,
    code_divergence_to_findings,
    compute_code_divergence,
    determine_tier,
    extract_code_blocks,
    extract_risk_markers,
    format_tier1_banner,
    _compute_marker_union_and_unique,
)
from governor.continuity import Anchor, AnchorType, ConstraintClass, Severity
from governor.interferometry import (
    ClaimAlignment,
    AlignmentType,
    InterferometryRun,
    InterferometrySignals,
    ModelRun,
    RunMode,
)
from governor.taint import fingerprint


# ============================================================================
# Helpers
# ============================================================================


def _make_irun(
    runs: list[ModelRun] | None = None,
    disagreement_rate: float = 0.0,
) -> InterferometryRun:
    """Create a minimal InterferometryRun for testing."""
    if runs is None:
        runs = []
    return InterferometryRun(
        id="test-run-001",
        prompt="test prompt",
        mode=RunMode.PARALLEL,
        runs=runs,
        shared=[],
        unique=[],
        conflicts=[],
        signals=InterferometrySignals(
            disagreement_rate=disagreement_rate,
            specifics_conflict_count=0,
            unique_count=0,
            shared_count=0,
            conflict_count=0,
            total_claims=0,
        ),
    )


def _make_model_run(model_id: str, response: str) -> ModelRun:
    """Create a minimal ModelRun."""
    return ModelRun(
        model_id=model_id,
        backend_type="test",
        response=response,
    )


def _make_anchor(
    anchor_id: str = "test-anchor",
    forbidden: list[str] | None = None,
    required: list[str] | None = None,
    constraint_class: ConstraintClass = ConstraintClass.INVARIANT,
) -> Anchor:
    return Anchor(
        id=anchor_id,
        anchor_type=AnchorType.PROHIBITION if forbidden else AnchorType.REQUIREMENT,
        description=f"Test anchor {anchor_id}",
        forbidden_patterns=forbidden or [],
        required_patterns=required or [],
        severity=Severity.REJECT,
        constraint_class=constraint_class,
    )


# ============================================================================
# TestRiskMarkerType
# ============================================================================


class TestRiskMarkerType:
    def test_security_count(self):
        security = [m for m, c in MARKER_CATEGORIES.items() if c == RiskCategory.SECURITY]
        assert len(security) == 8

    def test_edge_case_count(self):
        edge = [m for m, c in MARKER_CATEGORIES.items() if c == RiskCategory.EDGE_CASE]
        assert len(edge) == 6

    def test_architectural_count(self):
        arch = [m for m, c in MARKER_CATEGORIES.items() if c == RiskCategory.ARCHITECTURAL]
        assert len(arch) == 5

    def test_all_markers_categorized(self):
        assert len(MARKER_CATEGORIES) == len(RiskMarkerType)
        for mt in RiskMarkerType:
            assert mt in MARKER_CATEGORIES


# ============================================================================
# TestRiskMarker
# ============================================================================


class TestRiskMarker:
    def test_creation(self):
        m = RiskMarker(
            marker_type=RiskMarkerType.SQL_INJECTION,
            category=RiskCategory.SECURITY,
            model_id="claude",
            file_path="app.py",
            line_number=10,
            message="Possible SQL injection",
        )
        assert m.marker_type == RiskMarkerType.SQL_INJECTION
        assert m.category == RiskCategory.SECURITY
        assert m.suggestion is None

    def test_to_dict(self):
        m = RiskMarker(
            marker_type=RiskMarkerType.BOUNDARY,
            category=RiskCategory.EDGE_CASE,
            model_id="gpt",
            file_path="util.py",
            line_number=5,
            message="Off-by-one",
            suggestion="Use <= instead of <",
        )
        d = m.to_dict()
        assert d["marker_type"] == "boundary"
        assert d["category"] == "edge_case"
        assert d["suggestion"] == "Use <= instead of <"


# ============================================================================
# TestAnchorConflict
# ============================================================================


class TestAnchorConflict:
    def test_hard_conflict(self):
        c = AnchorConflict(
            anchor_id="a1",
            conflict_type=AnchorConflictType.HARD,
            model_id="claude",
            description="Violates invariant",
        )
        assert c.conflict_type == AnchorConflictType.HARD

    def test_soft_conflict(self):
        c = AnchorConflict(
            anchor_id="a2",
            conflict_type=AnchorConflictType.SOFT,
            model_id="gpt",
            description="Style divergence",
        )
        assert c.conflict_type == AnchorConflictType.SOFT

    def test_to_dict(self):
        c = AnchorConflict(
            anchor_id="a3",
            conflict_type=AnchorConflictType.HARD,
            model_id="ollama",
            description="Test",
            evidence="line 5",
        )
        d = c.to_dict()
        assert d["conflict_type"] == "hard"
        assert d["evidence"] == "line 5"


# ============================================================================
# TestExtractCodeBlocks
# ============================================================================


class TestExtractCodeBlocks:
    def test_single_block(self):
        text = "Here is code:\n```python\nprint('hello')\n```\nDone."
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "python"
        assert "print('hello')" in blocks[0]["content"]

    def test_multiple_blocks(self):
        text = "```python\na = 1\n```\ntext\n```javascript\nvar b = 2;\n```"
        blocks = extract_code_blocks(text)
        assert len(blocks) == 2
        assert blocks[0]["language"] == "python"
        assert blocks[1]["language"] == "javascript"

    def test_no_blocks(self):
        text = "No code here, just prose."
        blocks = extract_code_blocks(text)
        assert len(blocks) == 0

    def test_language_detection(self):
        text = "```\nunknown lang\n```"
        blocks = extract_code_blocks(text)
        assert len(blocks) == 1
        assert blocks[0]["language"] == "unknown"


# ============================================================================
# TestExtractRiskMarkers
# ============================================================================


class TestExtractRiskMarkers:
    def test_sql_injection(self):
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'
        markers = extract_risk_markers(code, model_id="claude")
        sql_markers = [m for m in markers if m.marker_type == RiskMarkerType.SQL_INJECTION]
        assert len(sql_markers) > 0
        assert sql_markers[0].category == RiskCategory.SECURITY

    def test_command_injection(self):
        code = 'import subprocess\nos.system(f"rm {user_input}")'
        markers = extract_risk_markers(code, model_id="gpt")
        shell_markers = [m for m in markers if m.marker_type == RiskMarkerType.SHELL_EXEC]
        assert len(shell_markers) > 0

    def test_edge_case_null(self):
        code = 'if x is None:\n    return default'
        markers = extract_risk_markers(code, model_id="ollama")
        null_markers = [m for m in markers if m.marker_type == RiskMarkerType.NULL_UNHANDLED]
        assert len(null_markers) > 0
        assert null_markers[0].category == RiskCategory.EDGE_CASE

    def test_edge_case_boundary(self):
        code = 'items[len(items)-1]'
        markers = extract_risk_markers(code, model_id="ollama")
        boundary_markers = [m for m in markers if m.marker_type == RiskMarkerType.BOUNDARY]
        assert len(boundary_markers) > 0

    def test_clean_code(self):
        code = 'x = 1 + 2\ny = x * 3'
        markers = extract_risk_markers(code, model_id="claude")
        # Clean arithmetic code should have no markers
        assert len(markers) == 0


# ============================================================================
# TestCheckAnchorCompatibility
# ============================================================================


class TestCheckAnchorCompatibility:
    def test_no_anchors(self):
        conflicts = check_anchor_compatibility("any code here", [], "claude")
        assert len(conflicts) == 0

    def test_invariant_produces_hard_conflict(self):
        anchor = _make_anchor(
            anchor_id="no-eval",
            forbidden=["eval("],
            constraint_class=ConstraintClass.INVARIANT,
        )
        code = 'result = eval(user_input)'
        conflicts = check_anchor_compatibility(code, [anchor], "claude")
        assert len(conflicts) > 0
        assert conflicts[0].conflict_type == AnchorConflictType.HARD

    def test_preference_produces_soft_conflict(self):
        anchor = _make_anchor(
            anchor_id="prefer-snake",
            forbidden=["camelCase"],
            constraint_class=ConstraintClass.PREFERENCE,
        )
        code = 'myVar = camelCase(x)'
        conflicts = check_anchor_compatibility(code, [anchor], "gpt")
        assert len(conflicts) > 0
        assert conflicts[0].conflict_type == AnchorConflictType.SOFT

    def test_no_violations(self):
        anchor = _make_anchor(
            anchor_id="no-eval",
            forbidden=["eval("],
        )
        code = 'result = safe_function(x)'
        conflicts = check_anchor_compatibility(code, [anchor], "claude")
        assert len(conflicts) == 0


# ============================================================================
# TestComputeCodeDivergence
# ============================================================================


class TestComputeCodeDivergence:
    def test_from_run(self):
        runs = [
            _make_model_run("claude", "```python\nprint('hello')\n```"),
            _make_model_run("gpt", "```python\nprint('world')\n```"),
        ]
        irun = _make_irun(runs=runs)
        report = compute_code_divergence(irun)
        assert report.interferometry_run_id == "test-run-001"
        assert len(report.artifacts) == 2

    def test_union_dedup(self):
        # Both models flag the same issue → union should deduplicate
        code = '```python\nquery = f"SELECT * FROM {table}"\n```'
        runs = [
            _make_model_run("claude", code),
            _make_model_run("gpt", code),
        ]
        irun = _make_irun(runs=runs)
        report = compute_code_divergence(irun)
        # Union should not double-count identical markers
        assert len(report.risk_marker_union) <= len(report.risk_markers)

    def test_per_model_unique(self):
        safe_code = '```python\nx = 1\n```'
        risky_code = '```python\nquery = f"SELECT * FROM {table}"\n```'
        runs = [
            _make_model_run("claude", safe_code),
            _make_model_run("gpt", risky_code),
        ]
        irun = _make_irun(runs=runs)
        report = compute_code_divergence(irun)
        # Only gpt should have unique markers
        if report.risk_marker_unique:
            assert "claude" not in report.risk_marker_unique or len(report.risk_marker_unique.get("claude", [])) == 0

    def test_empty_run(self):
        irun = _make_irun(runs=[])
        report = compute_code_divergence(irun)
        assert len(report.risk_markers) == 0
        assert len(report.artifacts) == 0
        assert report.tier == 0


# ============================================================================
# TestDetermineTier
# ============================================================================


class TestDetermineTier:
    def test_tier_0_no_issues(self):
        report = CodeDivergenceReport(interferometry_run_id="r1")
        tier, reasons = determine_tier(report)
        assert tier == 0
        assert len(reasons) == 0

    def test_tier_1_divergence_threshold(self):
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            divergence_entropy=0.5,
        )
        tier, reasons = determine_tier(report)
        assert tier == 1
        assert any("Divergence entropy" in r for r in reasons)

    def test_tier_1_risk_markers(self):
        marker = RiskMarker(
            marker_type=RiskMarkerType.SQL_INJECTION,
            category=RiskCategory.SECURITY,
            model_id="claude",
            file_path="app.py",
            line_number=1,
            message="sql injection",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_marker_union=[marker],
        )
        tier, reasons = determine_tier(report)
        assert tier == 1
        assert any("Risk markers" in r for r in reasons)

    def test_tier_1_anchor_conflicts(self):
        conflict = AnchorConflict(
            anchor_id="a1",
            conflict_type=AnchorConflictType.HARD,
            model_id="gpt",
            description="test",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            anchor_conflicts=[conflict],
        )
        tier, reasons = determine_tier(report)
        assert tier == 1
        assert any("Anchor conflicts" in r for r in reasons)

    def test_config_disable_markers(self):
        marker = RiskMarker(
            marker_type=RiskMarkerType.BOUNDARY,
            category=RiskCategory.EDGE_CASE,
            model_id="claude",
            file_path="x.py",
            line_number=1,
            message="edge",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_marker_union=[marker],
        )
        config = CodeInterferometryConfig(risk_markers_trigger=False)
        tier, reasons = determine_tier(report, config)
        assert tier == 0  # Markers disabled → no trigger


# ============================================================================
# TestCodeDivergenceToFindings
# ============================================================================


class TestCodeDivergenceToFindings:
    def test_security_finding_is_error(self):
        marker = RiskMarker(
            marker_type=RiskMarkerType.SQL_INJECTION,
            category=RiskCategory.SECURITY,
            model_id="claude",
            file_path="app.py",
            line_number=10,
            message="SQL injection",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_marker_union=[marker],
        )
        findings = code_divergence_to_findings(report)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].source == "interferometry"

    def test_edge_case_finding_is_warning(self):
        marker = RiskMarker(
            marker_type=RiskMarkerType.NULL_UNHANDLED,
            category=RiskCategory.EDGE_CASE,
            model_id="gpt",
            file_path="x.py",
            line_number=5,
            message="Null not handled",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_marker_union=[marker],
        )
        findings = code_divergence_to_findings(report)
        assert findings[0].severity == "warning"

    def test_hard_anchor_conflict_is_error(self):
        conflict = AnchorConflict(
            anchor_id="no-eval",
            conflict_type=AnchorConflictType.HARD,
            model_id="claude",
            description="Uses eval()",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            anchor_conflicts=[conflict],
        )
        findings = code_divergence_to_findings(report)
        assert findings[0].severity == "error"

    def test_source_field(self):
        marker = RiskMarker(
            marker_type=RiskMarkerType.BOUNDARY,
            category=RiskCategory.EDGE_CASE,
            model_id="gpt",
            file_path="x.py",
            line_number=1,
            message="boundary",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_marker_union=[marker],
        )
        findings = code_divergence_to_findings(report)
        assert all(f.source == "interferometry" for f in findings)


# ============================================================================
# TestFormatTier1Banner
# ============================================================================


class TestFormatTier1Banner:
    def test_no_markers_tier0(self):
        report = CodeDivergenceReport(interferometry_run_id="r1", tier=0)
        assert format_tier1_banner(report) == ""

    def test_security_banner(self):
        marker = RiskMarker(
            marker_type=RiskMarkerType.SQL_INJECTION,
            category=RiskCategory.SECURITY,
            model_id="claude",
            file_path="app.py",
            line_number=1,
            message="sql",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_marker_union=[marker],
            tier=1,
        )
        banner = format_tier1_banner(report)
        assert "security" in banner.lower()
        assert "Models disagreed" in banner

    def test_multiple_categories(self):
        markers = [
            RiskMarker(
                marker_type=RiskMarkerType.SQL_INJECTION,
                category=RiskCategory.SECURITY,
                model_id="claude", file_path="a.py", line_number=1, message="sql",
            ),
            RiskMarker(
                marker_type=RiskMarkerType.NULL_UNHANDLED,
                category=RiskCategory.EDGE_CASE,
                model_id="gpt", file_path="b.py", line_number=2, message="null",
            ),
        ]
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_marker_union=markers,
            tier=1,
        )
        banner = format_tier1_banner(report)
        assert "security" in banner.lower()
        assert "edge-case" in banner.lower()


# ============================================================================
# TestCodeInterferometryConfig
# ============================================================================


class TestCodeInterferometryConfig:
    def test_defaults(self):
        config = CodeInterferometryConfig()
        assert config.divergence_threshold == 0.3
        assert config.risk_markers_trigger is True
        assert config.anchor_conflicts_trigger is True

    def test_roundtrip(self):
        config = CodeInterferometryConfig(
            divergence_threshold=0.5,
            risk_markers_trigger=False,
            anchor_conflicts_trigger=True,
        )
        d = config.to_dict()
        restored = CodeInterferometryConfig.from_dict(d)
        assert restored.divergence_threshold == 0.5
        assert restored.risk_markers_trigger is False
        assert restored.anchor_conflicts_trigger is True


# ============================================================================
# TestCodeDivergenceReport
# ============================================================================


class TestCodeDivergenceReport:
    def test_to_dict(self):
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            tier=1,
            tier_reasons=["test"],
        )
        d = report.to_dict()
        assert d["interferometry_run_id"] == "r1"
        assert d["tier"] == 1
        assert d["tier_reasons"] == ["test"]

    def test_has_security_markers(self):
        marker = RiskMarker(
            marker_type=RiskMarkerType.SQL_INJECTION,
            category=RiskCategory.SECURITY,
            model_id="claude", file_path="a.py", line_number=1, message="sql",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            risk_markers=[marker],
        )
        assert report.has_security_markers() is True

        empty_report = CodeDivergenceReport(interferometry_run_id="r2")
        assert empty_report.has_security_markers() is False

    def test_has_hard_conflicts(self):
        conflict = AnchorConflict(
            anchor_id="a1",
            conflict_type=AnchorConflictType.HARD,
            model_id="gpt",
            description="test",
        )
        report = CodeDivergenceReport(
            interferometry_run_id="r1",
            anchor_conflicts=[conflict],
        )
        assert report.has_hard_conflicts() is True

        soft_report = CodeDivergenceReport(
            interferometry_run_id="r2",
            anchor_conflicts=[AnchorConflict(
                anchor_id="a2",
                conflict_type=AnchorConflictType.SOFT,
                model_id="gpt",
                description="style",
            )],
        )
        assert soft_report.has_hard_conflicts() is False
