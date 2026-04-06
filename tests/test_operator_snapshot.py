# SPDX-License-Identifier: Apache-2.0
"""Tests for operator_snapshot: shared doctor/trace logic + daemon RPC."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from governor.operator_snapshot import (
    CheckItem,
    TraceEvent,
    _safe_parse_ts,
    _trace_sort_key,
    classify_overall_state,
    classify_rollup,
    collect_trace_events,
    count_checks,
)
from governor.status_rollup import StatusRollup, ROLLUP_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def gov_project(tmp_path, runner):
    """Initialized governor project."""
    from governor.cli import cli
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        yield Path(td)


def _make_ok_rollup() -> StatusRollup:
    """Build a StatusRollup where every section is ok."""
    return StatusRollup(
        schema_version=ROLLUP_SCHEMA_VERSION,
        envelope={"ok": True, "mode": "strict"},
        regime={"ok": True, "name": "elastic", "warnings": []},
        drift={"ok": True, "alert_level": "none", "quarantined": 0},
        scars={"ok": True, "health": "NOMINAL", "hard": 0, "soft": 0},
        scope={"ok": True, "configured": False, "level": None,
               "grants": 0, "escalations_allowed": 0, "escalations_denied": 0},
        correlator={"ok": True, "regime": "leverage", "capture": False,
                    "indicators": []},
        stability={"ok": True, "recommendation": "no audits", "stiffness": None},
        violations={"ok": True, "pending": 0},
        recent_receipts={"ok": True, "items": []},
        lanes={"ok": True, "autopilot_level": 0, "policy_version": 1,
               "budget_total_usd": 0.0, "artifact_count": 0},
        override_pressure={"ok": True, "total": 0, "high": 0, "medium": 0,
                           "records": []},
    )


def _make_error_rollup() -> StatusRollup:
    """Build a StatusRollup with error conditions."""
    return StatusRollup(
        schema_version=ROLLUP_SCHEMA_VERSION,
        envelope={"ok": False, "error": "missing .envelope"},
        regime={"ok": True, "name": "unstable", "warnings": []},
        drift={"ok": True, "alert_level": "quarantine", "quarantined": 3},
        scars={"ok": True, "health": "CONSTRAINED", "hard": 2, "soft": 1},
        scope={"ok": True, "configured": True, "level": 2,
               "grants": 1, "escalations_allowed": 1, "escalations_denied": 5},
        correlator={"ok": True, "regime": "shear", "capture": True,
                    "indicators": ["mode_per_exposure"]},
        stability={"ok": True, "recommendation": "brittle", "stiffness": 0.8},
        violations={"ok": True, "pending": 2},
        recent_receipts={"ok": True, "items": [
            {"gate": "test", "verdict": "block", "receipt_id": "abc", "timestamp": "2026-01-01"},
        ]},
        lanes={"ok": True, "autopilot_level": 1, "policy_version": 2,
               "budget_total_usd": 10.0, "artifact_count": 5},
        override_pressure={"ok": True, "total": 2, "high": 1, "medium": 1,
                           "records": [
                               {"scope_key": "src/**", "anchor_id": "no-eval",
                                "override_count": 7, "pressure": "high",
                                "renewal_rate": 0.6},
                           ]},
    )


# ---------------------------------------------------------------------------
# CheckItem / TraceEvent dataclass tests
# ---------------------------------------------------------------------------

class TestCheckItem:
    def test_to_dict_roundtrip(self):
        c = CheckItem("test", "ok", "all good", ["governor status"])
        d = c.to_dict()
        c2 = CheckItem.from_dict(d)
        assert c2.name == c.name
        assert c2.status == c.status
        assert c2.summary == c.summary
        assert c2.next_commands == c.next_commands

    def test_from_dict_defaults(self):
        c = CheckItem.from_dict({"name": "x", "status": "ok", "summary": "y"})
        assert c.next_commands == []


class TestTraceEvent:
    def test_to_dict_roundtrip(self):
        e = TraceEvent("2026-01-01T00:00:00Z", "receipt", "pass",
                       "test: pass", "abc123", {"gate": "test"})
        d = e.to_dict()
        e2 = TraceEvent.from_dict(d)
        assert e2.ts == e.ts
        assert e2.source == e.source
        assert e2.detail == e.detail

    def test_from_dict_defaults(self):
        e = TraceEvent.from_dict({
            "ts": "t", "source": "s", "kind": "k", "summary": "m", "ref": "r"
        })
        assert e.detail == {}


# ---------------------------------------------------------------------------
# classify_rollup tests
# ---------------------------------------------------------------------------

class TestClassifyRollup:
    def test_all_ok_rollup_all_ok_or_info(self):
        """All-ok rollup produces only ok/info checks."""
        rollup = _make_ok_rollup()
        checks = classify_rollup(rollup)
        assert len(checks) == 9
        for c in checks:
            assert c.status in ("ok", "info"), f"{c.name}: {c.status}"

    def test_error_conditions_produce_errors(self):
        """Error rollup produces error/warn checks."""
        rollup = _make_error_rollup()
        checks = classify_rollup(rollup)
        assert len(checks) == 10  # 9 base + 1 override pressure
        statuses = {c.name: c.status for c in checks}
        assert statuses["envelope"] == "error"
        assert statuses["regime"] == "error"  # UNSTABLE
        assert statuses["drift"] == "error"   # QUARANTINE
        assert statuses["scars"] == "error"   # CONSTRAINED
        assert statuses["correlator"] == "error"  # CAPTURE
        assert statuses["stability"] == "warn"  # brittle
        assert statuses["violations"] == "error"  # pending
        assert statuses["receipts"] == "warn"  # recent blocks
        assert statuses["scope"] == "warn"  # high denial rate

    def test_error_checks_have_next_commands(self):
        """Error/warn checks include suggested next commands."""
        rollup = _make_error_rollup()
        checks = classify_rollup(rollup)
        for c in checks:
            if c.status in ("error", "warn"):
                assert len(c.next_commands) > 0, f"{c.name} missing next_commands"

    def test_regime_warm_is_warn(self):
        rollup = _make_ok_rollup()
        rollup = StatusRollup(**{**rollup.to_dict(), "regime": {"ok": True, "name": "warm", "warnings": []}})
        checks = classify_rollup(rollup)
        regime = [c for c in checks if c.name == "regime"][0]
        assert regime.status == "warn"

    def test_regime_ductile_is_error(self):
        rollup = _make_ok_rollup()
        rollup = StatusRollup(**{**rollup.to_dict(), "regime": {"ok": True, "name": "ductile", "warnings": []}})
        checks = classify_rollup(rollup)
        regime = [c for c in checks if c.name == "regime"][0]
        assert regime.status == "error"

    def test_scope_unconfigured_is_info(self):
        rollup = _make_ok_rollup()
        checks = classify_rollup(rollup)
        scope = [c for c in checks if c.name == "scope"][0]
        assert scope.status == "info"  # not configured


class TestCountChecks:
    def test_counts_match(self):
        checks = [
            CheckItem("a", "ok", ""),
            CheckItem("b", "warn", ""),
            CheckItem("c", "error", ""),
            CheckItem("d", "ok", ""),
        ]
        counts = count_checks(checks)
        assert counts == {"ok": 2, "info": 0, "warn": 1, "error": 1}


class TestClassifyOverallState:
    def test_all_ok_is_nominal(self):
        assert classify_overall_state({"ok": 5, "info": 1, "warn": 0, "error": 0}) == "Nominal"

    def test_warn_is_degraded(self):
        assert classify_overall_state({"ok": 3, "info": 0, "warn": 2, "error": 0}) == "Degraded"

    def test_error_is_unsafe(self):
        assert classify_overall_state({"ok": 3, "info": 0, "warn": 1, "error": 1}) == "Unsafe"

    def test_error_takes_priority_over_warn(self):
        """Error overrides warn — the state is Unsafe, not Degraded."""
        assert classify_overall_state({"ok": 0, "info": 0, "warn": 5, "error": 1}) == "Unsafe"

    def test_empty_counts_is_nominal(self):
        assert classify_overall_state({}) == "Nominal"


# ---------------------------------------------------------------------------
# Golden output tests: rendering regression anchors
# ---------------------------------------------------------------------------

class TestGoldenRendering:
    """Pin the exact text layout for doctor and status renderers.

    Three scenarios: Nominal, Degraded, Unsafe.
    These serve as regression anchors — if the format changes,
    update these fixtures deliberately.
    """

    def test_doctor_nominal(self, capsys):
        """Nominal: no findings shown, just summary."""
        from governor.cli_operator import _render_doctor_text
        rollup = _make_ok_rollup()
        checks = classify_rollup(rollup)
        counts = count_checks(checks)
        # Scope is "info" (not configured), so not fully clean
        # Override scope to ok for a truly clean test
        clean_rollup = StatusRollup(**{
            **rollup.to_dict(),
            "scope": {"ok": True, "configured": True, "level": 1,
                      "grants": 0, "escalations_allowed": 0,
                      "escalations_denied": 0},
        })
        checks = classify_rollup(clean_rollup)
        counts = count_checks(checks)
        _render_doctor_text(checks, counts)
        out = capsys.readouterr().out
        assert out.startswith("Governor Doctor: Nominal")
        assert "All checks passed (9 ok)" in out
        assert "Findings:" not in out

    def test_doctor_degraded(self, capsys):
        """Degraded: warn findings shown with Run: commands."""
        from governor.cli_operator import _render_doctor_text
        rollup = StatusRollup(**{
            **_make_ok_rollup().to_dict(),
            "regime": {"ok": True, "name": "warm", "warnings": []},
        })
        checks = classify_rollup(rollup)
        counts = count_checks(checks)
        _render_doctor_text(checks, counts)
        out = capsys.readouterr().out
        assert out.startswith("Governor Doctor: Degraded")
        assert "Findings:" in out
        assert "[WARN]" in out
        assert "Run:" in out
        assert "[err]" not in out

    def test_doctor_unsafe(self, capsys):
        """Unsafe: error findings sorted first, then warn, then info."""
        from governor.cli_operator import _render_doctor_text
        rollup = _make_error_rollup()
        checks = classify_rollup(rollup)
        counts = count_checks(checks)
        _render_doctor_text(checks, counts)
        out = capsys.readouterr().out
        assert out.startswith("Governor Doctor: Unsafe")
        assert "Findings:" in out
        # Errors come before warnings in the listing
        err_pos = out.index("[err]")
        warn_pos = out.index("[WARN]")
        assert err_pos < warn_pos

    def test_status_nominal(self):
        """Nominal status: compact state line, no findings, details pointer."""
        from governor.status_rollup import render_text
        rollup = StatusRollup(**{
            **_make_ok_rollup().to_dict(),
            "scope": {"ok": True, "configured": True, "level": 1,
                      "grants": 0, "escalations_allowed": 0,
                      "escalations_denied": 0},
        })
        text = render_text(rollup)
        assert text.startswith("Governor: Nominal")
        assert "envelope=strict" in text
        assert "regime=ELASTIC" in text
        assert "No findings." in text
        assert "Findings:" not in text
        assert "Details: governor status --json" in text

    def test_status_degraded(self):
        """Degraded: findings + Next: section."""
        from governor.status_rollup import render_text
        rollup = StatusRollup(**{
            **_make_ok_rollup().to_dict(),
            "regime": {"ok": True, "name": "warm", "warnings": []},
        })
        text = render_text(rollup)
        assert text.startswith("Governor: Degraded")
        assert "Findings:" in text
        assert "Next:" in text
        assert "governor regime status" in text

    def test_status_unsafe(self):
        """Unsafe: errors dominate findings + Next: section."""
        from governor.status_rollup import render_text
        rollup = _make_error_rollup()
        text = render_text(rollup)
        assert text.startswith("Governor: Unsafe")
        assert "Findings:" in text
        assert "Next:" in text
        # Error findings listed before warn findings
        err_pos = text.index("[err]")
        warn_pos = text.index("[WARN]")
        assert err_pos < warn_pos
        # Next section has commands from error-level findings (not info)
        next_section = text[text.index("Next:"):]
        cmds = [l.strip() for l in next_section.split("\n")
                if l.strip().startswith("governor")]
        assert len(cmds) >= 1
        # All Next commands should come from error/warn findings, not info
        assert not any("scope set" in c for c in cmds)

    def test_status_next_deduplicates(self):
        """Next: section deduplicates identical commands."""
        from governor.status_rollup import render_text
        rollup = _make_error_rollup()
        text = render_text(rollup)
        next_section = text[text.index("Next:"):]
        # Each command appears at most once
        cmds = [l.strip() for l in next_section.split("\n")
                if l.strip().startswith("governor")]
        assert len(cmds) == len(set(cmds)), f"Duplicate Next: commands: {cmds}"

    def test_status_next_capped_at_3(self):
        """Next: section shows at most 3 commands."""
        from governor.status_rollup import render_text
        rollup = _make_error_rollup()
        text = render_text(rollup)
        next_section = text[text.index("Next:"):]
        cmds = [l.strip() for l in next_section.split("\n")
                if l.strip().startswith("governor")]
        assert len(cmds) <= 3

    def test_width_invariant_status(self):
        """No line in status text exceeds 80 columns."""
        from governor.status_rollup import render_text
        text = render_text(_make_error_rollup())
        for line in text.split("\n"):
            assert len(line) <= 80, f"Line too wide ({len(line)}): {line!r}"

    def test_width_invariant_doctor(self, capsys):
        """No line in doctor text exceeds 80 columns."""
        from governor.cli_operator import _render_doctor_text
        checks = classify_rollup(_make_error_rollup())
        counts = count_checks(checks)
        _render_doctor_text(checks, counts)
        out = capsys.readouterr().out
        for line in out.split("\n"):
            assert len(line) <= 80, f"Line too wide ({len(line)}): {line!r}"


# ---------------------------------------------------------------------------
# render_bare tests (bare invocation "what now")
# ---------------------------------------------------------------------------

class TestRenderBare:
    def test_nominal_shows_no_findings(self):
        from governor.status_rollup import render_bare
        rollup = StatusRollup(**{
            **_make_ok_rollup().to_dict(),
            "scope": {"ok": True, "configured": True, "level": 1,
                      "grants": 0, "escalations_allowed": 0,
                      "escalations_denied": 0},
        })
        text = render_bare(rollup)
        assert text.startswith("Governor: Nominal")
        assert "No findings." in text
        assert "governor status --full" in text

    def test_degraded_shows_findings_and_next(self):
        from governor.status_rollup import render_bare
        rollup = StatusRollup(**{
            **_make_ok_rollup().to_dict(),
            "regime": {"ok": True, "name": "warm", "warnings": []},
        })
        text = render_bare(rollup)
        assert text.startswith("Governor: Degraded")
        assert "[WARN]" in text
        assert "regime" in text
        assert "governor regime status" in text

    def test_unsafe_shows_errors_first(self):
        from governor.status_rollup import render_bare
        text = render_bare(_make_error_rollup())
        assert text.startswith("Governor: Unsafe")
        assert "[err]" in text

    def test_bare_at_most_two_findings(self):
        from governor.status_rollup import render_bare
        text = render_bare(_make_error_rollup())
        # Count finding lines (lines containing [err] or [WARN] or [info])
        finding_lines = [l for l in text.split("\n")
                         if "[err]" in l or "[WARN]" in l or "[info]" in l]
        assert len(finding_lines) <= 2

    def test_bare_one_next_command(self):
        from governor.status_rollup import render_bare
        text = render_bare(_make_error_rollup())
        # Only one command line (starts with governor)
        cmd_lines = [l.strip() for l in text.split("\n")
                     if l.strip().startswith("governor")]
        assert len(cmd_lines) == 1

    def test_width_invariant_bare(self):
        """No line in bare text exceeds 80 columns."""
        from governor.status_rollup import render_bare
        text = render_bare(_make_error_rollup())
        for line in text.split("\n"):
            assert len(line) <= 80, f"Line too wide ({len(line)}): {line!r}"


# ---------------------------------------------------------------------------
# collect_trace_events tests
# ---------------------------------------------------------------------------

class TestCollectTraceEvents:
    def test_empty_gov_dir(self, gov_project):
        gov_dir = gov_project / ".governor"
        events = collect_trace_events(gov_dir)
        assert isinstance(events, list)

    def test_with_receipts(self, gov_project):
        """After emitting a receipt, collect should find it."""
        gov_dir = gov_project / ".governor"
        from governor.gate_receipt import GateReceiptSystem
        system = GateReceiptSystem(gov_dir)
        system.emit(
            gate="test_gate",
            verdict="pass",
            subject_kind="test",
            subject_bytes=b"data",
            evidence_bundle={"k": "v"},
            gate_config={"r": "t"},
        )
        events = collect_trace_events(gov_dir)
        assert len(events) >= 1
        assert events[0].source == "receipt"

    def test_source_filter(self, gov_project):
        """Source filter excludes non-matching events."""
        gov_dir = gov_project / ".governor"
        from governor.gate_receipt import GateReceiptSystem
        system = GateReceiptSystem(gov_dir)
        system.emit(
            gate="test_gate",
            verdict="pass",
            subject_kind="test",
            subject_bytes=b"data",
            evidence_bundle={"k": "v"},
            gate_config={"r": "t"},
        )
        events = collect_trace_events(gov_dir, source="scar")
        for e in events:
            assert e.source == "scar"

    def test_limit(self, gov_project):
        """Limit caps the number of returned events."""
        gov_dir = gov_project / ".governor"
        from governor.gate_receipt import GateReceiptSystem
        system = GateReceiptSystem(gov_dir)
        for i in range(5):
            system.emit(
                gate=f"gate_{i}",
                verdict="pass",
                subject_kind="test",
                subject_bytes=f"data_{i}".encode(),
                evidence_bundle={"i": i},
                gate_config={"r": "t"},
            )
        events = collect_trace_events(gov_dir, limit=2)
        assert len(events) <= 2

    def test_sorted_newest_first(self, gov_project):
        """Events are returned newest first."""
        gov_dir = gov_project / ".governor"
        from governor.gate_receipt import GateReceiptSystem
        system = GateReceiptSystem(gov_dir)
        for i in range(3):
            system.emit(
                gate=f"gate_{i}",
                verdict="pass",
                subject_kind="test",
                subject_bytes=f"data_{i}".encode(),
                evidence_bundle={"i": i},
                gate_config={"r": "t"},
            )
        events = collect_trace_events(gov_dir, limit=10)
        if len(events) >= 2:
            for a, b in zip(events, events[1:]):
                ts_a = _safe_parse_ts(a.ts)
                ts_b = _safe_parse_ts(b.ts)
                assert ts_a >= ts_b


# ---------------------------------------------------------------------------
# Trace sort key
# ---------------------------------------------------------------------------

class TestTraceSortKey:
    def test_receipt_before_scar_same_timestamp(self):
        e1 = TraceEvent(ts="2026-01-01T00:00:00Z", source="receipt",
                        kind="pass", summary="a", ref="aaa")
        e2 = TraceEvent(ts="2026-01-01T00:00:00Z", source="scar",
                        kind="failure", summary="b", ref="bbb")
        events = [e2, e1]
        events.sort(key=_trace_sort_key)
        assert events[0].source == "receipt"

    def test_safe_parse_ts_handles_garbage(self):
        dt = _safe_parse_ts("not-a-date")
        assert dt.year == 1970

    def test_safe_parse_ts_handles_z_suffix(self):
        dt = _safe_parse_ts("2026-01-15T12:00:00Z")
        assert dt.year == 2026


# ---------------------------------------------------------------------------
# Parity test: local classify matches daemon snapshot shape
# ---------------------------------------------------------------------------

class TestParity:
    def test_classify_matches_snapshot_shape(self, gov_project):
        """classify_rollup produces the same shape as operator.snapshot would.

        This is the tripwire: if daemon and CLI disagree on check structure,
        this test fails.
        """
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"

        rollup = build_status_rollup(gov_dir)
        checks = classify_rollup(rollup)
        counts = count_checks(checks)

        # Simulate what the daemon would return
        snapshot = {
            "checks": [c.to_dict() for c in checks],
            "counts": counts,
        }

        # Reconstruct from dict (as CLI would do from RPC)
        reconstructed = [CheckItem.from_dict(c) for c in snapshot["checks"]]
        assert len(reconstructed) == len(checks)
        for orig, recon in zip(checks, reconstructed):
            assert orig.name == recon.name
            assert orig.status == recon.status
            assert orig.summary == recon.summary
            assert orig.next_commands == recon.next_commands

    def test_snapshot_json_roundtrip(self, gov_project):
        """Snapshot data survives JSON serialization (no Paths/Enums/floats)."""
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"

        rollup = build_status_rollup(gov_dir)
        checks = classify_rollup(rollup)
        counts = count_checks(checks)

        result = {
            "schema": "operator-snapshot/1",
            "rollup": rollup.to_dict(),
            "checks": [c.to_dict() for c in checks],
            "counts": counts,
        }

        # Must survive JSON roundtrip
        serialized = json.dumps(result)
        deserialized = json.loads(serialized)
        assert deserialized == result


# ---------------------------------------------------------------------------
# Daemon handler tests (unit — no real socket)
# ---------------------------------------------------------------------------

class TestDaemonHandlers:
    @pytest.fixture
    def tmp_gov_dir(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "sessions").mkdir()
        (gov_dir / "sessions" / "index.json").write_text(
            json.dumps({"sessions": {}, "mainline": None})
        )
        return gov_dir

    @pytest.fixture
    def dispatcher_and_state(self, tmp_gov_dir):
        from governor.daemon import DaemonState, Dispatcher, register_handlers
        state = DaemonState(tmp_gov_dir, mode="general")
        d = Dispatcher()
        register_handlers(d, state)
        return d, state

    def test_operator_snapshot_returns_expected_keys(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        request = {"jsonrpc": "2.0", "method": "operator.snapshot", "id": 1, "params": {}}
        response = asyncio.run(d.dispatch(request))
        assert response is not None
        result = response["result"]
        assert result["schema"] == "operator-snapshot/1"
        assert "generated_at" in result
        assert result["backend"] == "daemon"
        assert "gov_dir" in result
        assert "rollup" in result
        assert "checks" in result
        assert "counts" in result
        assert "suggestions" in result
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) == 9

    def test_trace_tail_returns_events(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        request = {"jsonrpc": "2.0", "method": "trace.tail", "id": 2,
                    "params": {"limit": 5}}
        response = asyncio.run(d.dispatch(request))
        assert response is not None
        result = response["result"]
        assert "events" in result
        assert isinstance(result["events"], list)

    def test_trace_tail_with_source_filter(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        request = {"jsonrpc": "2.0", "method": "trace.tail", "id": 3,
                    "params": {"limit": 10, "source": "receipt"}}
        response = asyncio.run(d.dispatch(request))
        result = response["result"]
        for e in result["events"]:
            assert e["source"] == "receipt"

    def test_operator_snapshot_counts_add_up(self, dispatcher_and_state):
        d, state = dispatcher_and_state
        request = {"jsonrpc": "2.0", "method": "operator.snapshot", "id": 4, "params": {}}
        response = asyncio.run(d.dispatch(request))
        result = response["result"]
        total = sum(result["counts"].values())
        assert total == len(result["checks"])


# ---------------------------------------------------------------------------
# Fallback banner
# ---------------------------------------------------------------------------

class TestFallbackBanner:
    def test_banner_prints_in_auto_mode(self, capsys, monkeypatch):
        monkeypatch.setenv("GOV_BACKEND", "auto")
        from governor.cli_operator import _print_fallback_banner
        _print_fallback_banner("local", as_json=False)
        captured = capsys.readouterr()
        assert "daemon unreachable" in captured.err

    def test_banner_suppressed_in_json_mode(self, capsys, monkeypatch):
        monkeypatch.setenv("GOV_BACKEND", "auto")
        from governor.cli_operator import _print_fallback_banner
        _print_fallback_banner("local", as_json=True)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_banner_suppressed_when_local_forced(self, capsys, monkeypatch):
        monkeypatch.setenv("GOV_BACKEND", "local")
        from governor.cli_operator import _print_fallback_banner
        _print_fallback_banner("local", as_json=False)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_banner_prints_when_rpc_forced_but_unreachable(self, capsys, monkeypatch):
        monkeypatch.setenv("GOV_BACKEND", "rpc")
        from governor.cli_operator import _print_fallback_banner
        _print_fallback_banner("local", as_json=False)
        captured = capsys.readouterr()
        assert "daemon unreachable" in captured.err
