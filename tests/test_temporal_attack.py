"""Tests for temporal_attack — Δt-aware security analysis (AG2 Parallel Track)."""

import json
from pathlib import Path

import pytest

from governor.temporal_attack import (
    TemporalMarkerType,
    TemporalDomain,
    MarkerSeverity,
    TemporalMarker,
    ScanResult,
    TemporalScanState,
    FatigueSignals,
    MARKER_META,
    scan_toctou,
    scan_fail_open,
    scan_log_not_gate,
    scan_unbounded_retry,
    scan_catch_all,
    scan_type_ignore,
    scan_text,
    scan_file,
    scan_directory,
    make_temporal_event,
    make_scan_event,
    TemporalAttackStore,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_marker_types(self):
        assert len(TemporalMarkerType) == 18

    def test_domains(self):
        assert len(TemporalDomain) == 3

    def test_severities(self):
        assert len(MarkerSeverity) == 4

    def test_all_markers_have_meta(self):
        for mt in TemporalMarkerType:
            assert mt in MARKER_META, f"Missing meta for {mt}"

    def test_meta_has_required_keys(self):
        for mt, meta in MARKER_META.items():
            assert "domain" in meta
            assert "severity" in meta
            assert "delta_t" in meta
            assert "description" in meta


# ---------------------------------------------------------------------------
# TemporalMarker
# ---------------------------------------------------------------------------

class TestTemporalMarker:
    def test_create(self):
        m = TemporalMarker(
            TemporalMarkerType.TOCTOU_RACE, MarkerSeverity.HIGH,
            TemporalDomain.CODE, line=42, snippet="if os.path.exists(f):",
        )
        assert m.line == 42

    def test_roundtrip(self):
        m = TemporalMarker(
            TemporalMarkerType.FAIL_OPEN_DEFAULT, MarkerSeverity.HIGH,
            TemporalDomain.BOTH, line=10, file_path="test.py",
            snippet="except TimeoutError:", delta_t="fail-open",
        )
        d = m.to_dict()
        m2 = TemporalMarker.from_dict(d)
        assert m2.marker_type == TemporalMarkerType.FAIL_OPEN_DEFAULT
        assert m2.file_path == "test.py"

    def test_schema(self):
        m = TemporalMarker(
            TemporalMarkerType.LOG_NOT_GATE, MarkerSeverity.MEDIUM,
            TemporalDomain.BOTH,
        )
        d = m.to_dict()
        required = {"marker_type", "severity", "domain", "line", "column",
                     "file_path", "snippet", "delta_t", "description"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# ScanResult
# ---------------------------------------------------------------------------

class TestScanResult:
    def test_empty(self):
        r = ScanResult(file_path="test.py")
        assert r.marker_count == 0
        assert r.critical_count == 0
        assert r.high_count == 0

    def test_counts(self):
        r = ScanResult(file_path="test.py", markers=[
            TemporalMarker(TemporalMarkerType.TOCTOU_RACE, MarkerSeverity.HIGH, TemporalDomain.CODE),
            TemporalMarker(TemporalMarkerType.COMMIT_BEFORE_VERIFY, MarkerSeverity.CRITICAL, TemporalDomain.BOTH),
        ])
        assert r.marker_count == 2
        assert r.critical_count == 1
        assert r.high_count == 1

    def test_roundtrip(self):
        r = ScanResult(file_path="test.py", markers=[
            TemporalMarker(TemporalMarkerType.UNBOUNDED_RETRY, MarkerSeverity.MEDIUM, TemporalDomain.CODE),
        ])
        d = r.to_dict()
        r2 = ScanResult.from_dict(d)
        assert r2.marker_count == 1
        assert r2.markers[0].marker_type == TemporalMarkerType.UNBOUNDED_RETRY


# ---------------------------------------------------------------------------
# TemporalScanState
# ---------------------------------------------------------------------------

class TestTemporalScanState:
    def test_default(self):
        s = TemporalScanState()
        assert s.total_markers == 0

    def test_record(self):
        s = TemporalScanState()
        r = ScanResult("test.py", [
            TemporalMarker(TemporalMarkerType.TOCTOU_RACE, MarkerSeverity.HIGH, TemporalDomain.CODE),
            TemporalMarker(TemporalMarkerType.TOCTOU_RACE, MarkerSeverity.HIGH, TemporalDomain.CODE),
        ])
        s.record(r)
        assert s.total_markers == 2
        assert s.marker_counts["TOCTOU_RACE"] == 2

    def test_roundtrip(self):
        s = TemporalScanState()
        s.record(ScanResult("a.py", [
            TemporalMarker(TemporalMarkerType.LOG_NOT_GATE, MarkerSeverity.MEDIUM, TemporalDomain.BOTH),
        ]))
        d = s.to_dict()
        s2 = TemporalScanState.from_dict(d)
        assert s2.total_markers == 1
        assert len(s2.results) == 1


# ---------------------------------------------------------------------------
# scan_toctou
# ---------------------------------------------------------------------------

class TestScanToctou:
    def test_clean(self):
        lines = ["x = 1", "y = 2"]
        assert scan_toctou(lines) == []

    def test_exists_then_open(self):
        lines = [
            "if os.path.exists(path):",
            "    with open(path, 'w') as f:",
            "        f.write('data')",
        ]
        markers = scan_toctou(lines)
        assert len(markers) == 1
        assert markers[0].marker_type == TemporalMarkerType.TOCTOU_RACE

    def test_isfile_then_write(self):
        lines = [
            "if os.path.isfile(p):",
            "    data = open(p).write('x')",
        ]
        markers = scan_toctou(lines)
        assert len(markers) == 1

    def test_not_exists_then_create(self):
        lines = [
            "if not os.path.exists(path):",
            "    os.mkdir(path)",
        ]
        markers = scan_toctou(lines)
        assert len(markers) == 1

    def test_exists_without_action(self):
        lines = [
            "if os.path.exists(path):",
            "    print('exists')",
        ]
        assert scan_toctou(lines) == []


# ---------------------------------------------------------------------------
# scan_fail_open
# ---------------------------------------------------------------------------

class TestScanFailOpen:
    def test_clean(self):
        lines = ["try:", "    verify()", "except ValueError:", "    raise"]
        assert scan_fail_open(lines) == []

    def test_timeout_allow(self):
        lines = [
            "try:",
            "    verify(token)",
            "except TimeoutError:",
            "    allow()",
        ]
        markers = scan_fail_open(lines)
        assert len(markers) == 1
        assert markers[0].marker_type == TemporalMarkerType.FAIL_OPEN_DEFAULT

    def test_exception_continue(self):
        lines = [
            "try:",
            "    check()",
            "except Exception:",
            "    continue",
        ]
        markers = scan_fail_open(lines)
        assert len(markers) == 1


# ---------------------------------------------------------------------------
# scan_log_not_gate
# ---------------------------------------------------------------------------

class TestScanLogNotGate:
    def test_clean(self):
        lines = ["logger.info('all good')"]
        assert scan_log_not_gate(lines) == []

    def test_warn_then_apply(self):
        lines = [
            'logger.warning("rejected patch")',
            'apply_patch(patch)',
        ]
        markers = scan_log_not_gate(lines)
        assert len(markers) == 1
        assert markers[0].marker_type == TemporalMarkerType.LOG_NOT_GATE

    def test_warn_then_raise(self):
        lines = [
            'logger.warning("violation detected")',
            'raise GovernorError("blocked")',
        ]
        assert scan_log_not_gate(lines) == []


# ---------------------------------------------------------------------------
# scan_unbounded_retry
# ---------------------------------------------------------------------------

class TestScanUnboundedRetry:
    def test_clean(self):
        lines = ["for i in range(3):", "    try_thing()"]
        assert scan_unbounded_retry(lines) == []

    def test_while_true_no_guard(self):
        lines = [
            "while True:",
            "    try:",
            "        result = call_api()",
            "    except:",
            "        pass",
        ]
        markers = scan_unbounded_retry(lines)
        assert len(markers) == 1
        assert markers[0].marker_type == TemporalMarkerType.UNBOUNDED_RETRY

    def test_while_true_with_break(self):
        lines = [
            "while True:",
            "    result = call_api()",
            "    if result:",
            "        break",
        ]
        assert scan_unbounded_retry(lines) == []

    def test_while_true_with_max_retries(self):
        lines = [
            "while True:",
            "    if retry_count > max_retries:",
            "        break",
            "    try_thing()",
        ]
        assert scan_unbounded_retry(lines) == []


# ---------------------------------------------------------------------------
# scan_catch_all
# ---------------------------------------------------------------------------

class TestScanCatchAll:
    def test_clean(self):
        lines = ["except ValueError:", "    handle()"]
        assert scan_catch_all(lines) == []

    def test_bare_except_pass(self):
        lines = [
            "except:",
            "    pass",
        ]
        markers = scan_catch_all(lines)
        assert len(markers) == 1

    def test_exception_continue(self):
        lines = [
            "except Exception:",
            "    continue",
        ]
        markers = scan_catch_all(lines)
        assert len(markers) == 1

    def test_exception_with_handler(self):
        lines = [
            "except Exception:",
            "    logger.error('failed')",
        ]
        assert scan_catch_all(lines) == []


# ---------------------------------------------------------------------------
# scan_type_ignore
# ---------------------------------------------------------------------------

class TestScanTypeIgnore:
    def test_clean(self):
        lines = ["x: int = 1"]
        assert scan_type_ignore(lines) == []

    def test_bare_type_ignore(self):
        lines = ["x = foo()  # type: ignore"]
        markers = scan_type_ignore(lines)
        assert len(markers) == 1
        assert markers[0].marker_type == TemporalMarkerType.TYPE_IGNORE_NO_ISSUE

    def test_type_ignore_with_code(self):
        lines = ["x = foo()  # type: ignore[assignment]"]
        assert scan_type_ignore(lines) == []


# ---------------------------------------------------------------------------
# scan_text (composite)
# ---------------------------------------------------------------------------

class TestScanText:
    def test_clean_code(self):
        r = scan_text("x = 1\ny = 2\n")
        assert r.marker_count == 0

    def test_mixed_markers(self):
        code = """
if os.path.exists(path):
    with open(path, 'w') as f:
        pass

while True:
    try:
        call()
    except:
        pass

x = foo()  # type: ignore
"""
        r = scan_text(code, "test.py")
        assert r.marker_count >= 2  # TOCTOU + catch_all at minimum
        assert r.file_path == "test.py"

    def test_empty_text(self):
        r = scan_text("")
        assert r.marker_count == 0


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------

class TestScanFile:
    def test_missing_file(self, tmp_path):
        r = scan_file(tmp_path / "nope.py")
        assert r.marker_count == 0

    def test_real_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = foo()  # type: ignore\n")
        r = scan_file(f)
        assert r.marker_count == 1

    def test_clean_file(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text("def add(a, b):\n    return a + b\n")
        r = scan_file(f)
        assert r.marker_count == 0


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------

class TestScanDirectory:
    def test_empty_dir(self, tmp_path):
        results = scan_directory(tmp_path)
        assert results == []

    def test_with_findings(self, tmp_path):
        (tmp_path / "bad.py").write_text("x = foo()  # type: ignore\n")
        (tmp_path / "good.py").write_text("x = 1\n")
        results = scan_directory(tmp_path)
        assert len(results) == 1  # Only file with findings
        assert results[0].marker_count == 1

    def test_extension_filter(self, tmp_path):
        (tmp_path / "bad.py").write_text("x = foo()  # type: ignore\n")
        (tmp_path / "bad.txt").write_text("x = foo()  # type: ignore\n")
        results = scan_directory(tmp_path, extensions={".py"})
        assert len(results) == 1

    def test_missing_dir(self, tmp_path):
        results = scan_directory(tmp_path / "nope")
        assert results == []


# ---------------------------------------------------------------------------
# FatigueSignals
# ---------------------------------------------------------------------------

class TestFatigueSignals:
    def test_default(self):
        f = FatigueSignals()
        assert f.fatigue_score() == 0.0

    def test_high_queue(self):
        f = FatigueSignals(queue_depth=15)
        assert f.fatigue_score() > 0.0

    def test_rapid_approvals(self):
        f = FatigueSignals(approvals_per_hour=25, avg_review_time_seconds=10)
        score = f.fatigue_score()
        assert score >= 0.4

    def test_all_signals(self):
        f = FatigueSignals(
            queue_depth=20,
            similar_approvals_in_window=10,
            avg_review_time_seconds=5,
            approvals_per_hour=30,
        )
        assert f.fatigue_score() == 1.0

    def test_roundtrip(self):
        f = FatigueSignals(queue_depth=5, approvals_per_hour=10)
        d = f.to_dict()
        f2 = FatigueSignals.from_dict(d)
        assert f2.queue_depth == 5
        assert f2.approvals_per_hour == 10

    def test_schema(self):
        f = FatigueSignals()
        d = f.to_dict()
        required = {"queue_depth", "similar_approvals_in_window",
                     "avg_review_time_seconds", "approvals_per_hour", "fatigue_score"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_basic_event(self):
        e = make_temporal_event("scan", {"file": "test.py"})
        assert e["type"] == "temporal_attack_surface"
        assert e["ts"]

    def test_minimal_event(self):
        e = make_temporal_event("check")
        assert e["details"] == {}

    def test_scan_event(self):
        r = ScanResult("test.py", [
            TemporalMarker(TemporalMarkerType.TOCTOU_RACE, MarkerSeverity.HIGH, TemporalDomain.CODE),
        ])
        e = make_scan_event(r)
        assert e["action"] == "scan"
        assert e["details"]["marker_count"] == 1


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestStore:
    def test_save_load(self, tmp_path):
        store = TemporalAttackStore(governor_dir=tmp_path)
        state = TemporalScanState()
        state.record(ScanResult("test.py", [
            TemporalMarker(TemporalMarkerType.LOG_NOT_GATE, MarkerSeverity.MEDIUM, TemporalDomain.BOTH),
        ]))
        store.save(state, "run1")
        loaded = store.load("run1")
        assert loaded is not None
        assert loaded.total_markers == 1

    def test_load_missing(self, tmp_path):
        store = TemporalAttackStore(governor_dir=tmp_path)
        assert store.load("nope") is None

    def test_list_runs(self, tmp_path):
        store = TemporalAttackStore(governor_dir=tmp_path)
        store.save(TemporalScanState(), "a")
        store.save(TemporalScanState(), "b")
        assert "a" in store.list_runs()

    def test_default_dir(self):
        store = TemporalAttackStore()
        assert store.temporal_dir == Path(".governor") / "temporal_attack"


# ---------------------------------------------------------------------------
# Golden schemas
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_marker_schema(self):
        m = TemporalMarker(
            TemporalMarkerType.TOCTOU_RACE, MarkerSeverity.HIGH,
            TemporalDomain.CODE,
        )
        d = m.to_dict()
        required = {"marker_type", "severity", "domain", "line", "column",
                     "file_path", "snippet", "delta_t", "description"}
        assert required <= set(d.keys())

    def test_scan_result_schema(self):
        r = ScanResult("test.py")
        d = r.to_dict()
        required = {"file_path", "markers", "marker_count", "critical_count",
                     "high_count", "ts"}
        assert required <= set(d.keys())

    def test_state_schema(self):
        s = TemporalScanState()
        d = s.to_dict()
        required = {"results", "total_markers", "marker_counts"}
        assert required <= set(d.keys())


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        store = TemporalAttackStore(governor_dir=tmp_path)
        state = TemporalScanState()

        # Create a file with temporal antipatterns
        code_dir = tmp_path / "code"
        code_dir.mkdir()
        (code_dir / "vuln.py").write_text("""
if os.path.exists(path):
    with open(path, 'w') as f:
        f.write('data')

while True:
    try:
        call_api()
    except:
        pass

x = foo()  # type: ignore
""")

        results = scan_directory(code_dir)
        for r in results:
            state.record(r)

        assert state.total_markers >= 2

        store.save(state, "lifecycle")
        loaded = store.load("lifecycle")
        assert loaded is not None
        assert loaded.total_markers == state.total_markers


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_lines(self):
        r = scan_text("\n\n\n")
        assert r.marker_count == 0

    def test_very_long_line(self):
        line = "x = foo()  # type: ignore" + " " * 10000
        r = scan_text(line)
        assert r.marker_count == 1
        assert len(r.markers[0].snippet) <= 200  # Snippet truncated

    def test_binary_content(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_bytes(b"\x00\x01\x02\x03")
        r = scan_file(f)
        assert r.marker_count == 0
