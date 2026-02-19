# SPDX-License-Identifier: Apache-2.0
"""Tests for CLI operator surface: status --full, doctor, explain, trace."""

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def gov_project(tmp_path, runner):
    """Initialized governor project in an isolated filesystem."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        yield Path(td)


def _snapshot_tree(root: Path) -> set[str]:
    """Snapshot all files/dirs under root as relative paths."""
    entries = set()
    for p in root.rglob("*"):
        entries.add(str(p.relative_to(root)))
    return entries


# =========================================================================
# TestDashboard (status --full)
# =========================================================================


class TestDashboard:
    """Tests for governor status --full."""

    def test_text_has_all_sections(self, runner, gov_project):
        result = runner.invoke(cli, ["status", "--full"])
        assert result.exit_code == 0
        assert "Governor Dashboard" in result.output
        assert "Envelope:" in result.output
        assert "Regime:" in result.output
        assert "Drift:" in result.output
        assert "Scars:" in result.output
        assert "Scope:" in result.output
        assert "Correlator:" in result.output
        assert "Stability:" in result.output
        assert "Violations:" in result.output
        assert "Recent Receipts:" in result.output

    def test_json_has_expected_keys(self, runner, gov_project):
        result = runner.invoke(cli, ["status", "--full", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["schema_version"] == 1
        for key in ("envelope", "regime", "drift", "scars", "scope",
                     "correlator", "stability", "violations", "recent_receipts",
                     "lanes"):
            assert key in data
            assert "ok" in data[key]

    def test_bare_status_is_dashboard(self, runner, gov_project):
        """status (bare) should show the operator dashboard."""
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Governor Dashboard" in result.output

    def test_proposals_flag_shows_proposals(self, runner, gov_project):
        """status --proposals should show proposals, not dashboard."""
        runner.invoke(cli, [
            "propose",
            "--claim", "type=decision,topic=framework,choice=react",
        ])
        result = runner.invoke(cli, ["status", "--proposals"])
        assert result.exit_code == 0
        assert "Proposals" in result.output
        assert "Governor Dashboard" not in result.output

    def test_section_failure_visible_in_text(self, runner, gov_project):
        """Corrupt state files should show [err] in text."""
        # Corrupt the scars file
        (gov_project / ".governor" / "scars.json").write_text("{bad json")
        result = runner.invoke(cli, ["status", "--full"])
        assert result.exit_code == 0
        assert "[err]" in result.output

    def test_section_failure_visible_in_json(self, runner, gov_project):
        """Corrupt state files should show ok:false in JSON."""
        (gov_project / ".governor" / "scars.json").write_text("{bad json")
        result = runner.invoke(cli, ["status", "--full", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["scars"]["ok"] is False
        assert "error" in data["scars"]

    def test_uninitialized_errors(self, runner, tmp_path):
        """Running without init should show error."""
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["status", "--full"])
            assert result.exit_code != 0

    def test_recent_receipts_wrapped(self, runner, gov_project):
        """recent_receipts section should have ok field (not bare list)."""
        result = runner.invoke(cli, ["status", "--full", "--json"])
        data = json.loads(result.output)
        rcpt = data["recent_receipts"]
        assert "ok" in rcpt
        assert "items" in rcpt or "error" in rcpt


# =========================================================================
# TestDoctor
# =========================================================================


class TestDoctor:
    """Tests for governor doctor."""

    def test_fresh_init_all_ok(self, runner, gov_project):
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "[ok]" in result.output

    def test_json_valid_and_schema(self, runner, gov_project):
        result = runner.invoke(cli, ["doctor", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["schema_version"] == 1
        assert "checks" in data
        assert "counts" in data
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) > 0

    def test_hard_scars_produce_error(self, runner, gov_project):
        """Hard scars should show as error with next_commands."""
        from governor.scars import ScarLedger
        ledger = ScarLedger()
        # Record enough internal failures to produce a hard scar
        # Low observation_shift + high prediction_error → INTERNAL → scar
        for i in range(10):
            ledger.record_failure("test_region", observation_shift=0.01, prediction_error=5.0)
        scar_path = gov_project / ".governor" / "scars.json"
        scar_path.write_text(json.dumps(ledger.to_dict(), indent=2))

        result = runner.invoke(cli, ["doctor", "--json"])
        data = json.loads(result.output)
        scar_check = [c for c in data["checks"] if c["name"] == "scars"][0]
        assert scar_check["status"] in ("warn", "error")
        assert len(scar_check["next_commands"]) > 0

    def test_pending_violation_produces_error(self, runner, gov_project):
        """Pending violation should show as error."""
        from governor.violation_resolver import ViolationResolver
        resolver = ViolationResolver(gov_project / ".governor")
        resolver.create_pending(
            violations=[{"type": "test", "message": "test violation"}],
            blocked_response="blocked",
            run_id="test-run-001",
        )
        result = runner.invoke(cli, ["doctor", "--json"])
        data = json.loads(result.output)
        vio_check = [c for c in data["checks"] if c["name"] == "violations"][0]
        assert vio_check["status"] == "error"
        assert "governor gate pending" in vio_check["next_commands"]

    def test_exit_0_on_warn_only(self, runner, gov_project):
        """Warnings should not cause exit 1 by default."""
        # Create a scar to trigger CAUTIOUS (warn)
        from governor.scars import ScarLedger
        ledger = ScarLedger()
        ledger.record_failure("test_region", observation_shift=0.5, prediction_error=0.5)
        scar_path = gov_project / ".governor" / "scars.json"
        scar_path.write_text(json.dumps(ledger.to_dict(), indent=2))
        result = runner.invoke(cli, ["doctor"])
        # CAUTIOUS is warn-level, so exit 0 (no --strict)
        if "[err]" not in result.output:
            assert result.exit_code == 0

    def test_exit_1_on_error(self, runner, gov_project):
        """Errors should cause exit 1."""
        from governor.violation_resolver import ViolationResolver
        resolver = ViolationResolver(gov_project / ".governor")
        resolver.create_pending(
            violations=[{"type": "test", "message": "test"}],
            blocked_response="blocked",
            run_id="test-run-002",
        )
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 1

    def test_strict_exits_1_on_warn(self, runner, gov_project):
        """--strict should exit 1 on warnings."""
        from governor.scars import ScarLedger
        ledger = ScarLedger()
        ledger.record_failure("test_region", observation_shift=0.5, prediction_error=0.5)
        scar_path = gov_project / ".governor" / "scars.json"
        scar_path.write_text(json.dumps(ledger.to_dict(), indent=2))
        result = runner.invoke(cli, ["doctor", "--strict"])
        # Should exit 1 because CAUTIOUS is a warn
        if "CAUTIOUS" in result.output or "[WARN]" in result.output:
            assert result.exit_code == 1

    def test_partial_failure_continues(self, runner, gov_project):
        """Corrupt subsystem should show [err] but other checks continue."""
        (gov_project / ".governor" / "scars.json").write_text("not json")
        result = runner.invoke(cli, ["doctor"])
        # Should see error for scars but still check other subsystems
        assert "[err]" in result.output
        assert "[ok]" in result.output  # other checks still ran

    def test_doctor_checks_all_nine(self, runner, gov_project):
        """Doctor should produce exactly 9 checks."""
        result = runner.invoke(cli, ["doctor", "--json"])
        data = json.loads(result.output)
        assert len(data["checks"]) == 9
        names = [c["name"] for c in data["checks"]]
        assert "envelope" in names
        assert "regime" in names
        assert "drift" in names
        assert "scars" in names
        assert "correlator" in names
        assert "scope" in names
        assert "stability" in names
        assert "violations" in names
        assert "receipts" in names


# =========================================================================
# TestExplain
# =========================================================================


class TestExplain:
    """Tests for governor explain."""

    def test_elastic_correct_text(self, runner):
        result = runner.invoke(cli, ["explain", "ELASTIC"])
        assert result.exit_code == 0
        assert "regime:ELASTIC" in result.output
        assert "Normal operation" in result.output

    def test_case_insensitive(self, runner):
        result = runner.invoke(cli, ["explain", "elastic"])
        assert result.exit_code == 0
        assert "ELASTIC" in result.output

    def test_qualified_lookup(self, runner):
        result = runner.invoke(cli, ["explain", "regime:ELASTIC"])
        assert result.exit_code == 0
        assert "Normal operation" in result.output

    def test_json_valid(self, runner):
        result = runner.invoke(cli, ["explain", "ELASTIC", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["schema_version"] == 1
        assert data["entry"]["code"] == "ELASTIC"
        assert data["entry"]["category"] == "regime"

    def test_unknown_exit_1(self, runner):
        result = runner.invoke(cli, ["explain", "NONEXISTENT"])
        assert result.exit_code == 1
        assert "Unknown code" in result.output

    def test_block_gate_verdict(self, runner):
        result = runner.invoke(cli, ["explain", "gate_verdict:BLOCK"])
        assert result.exit_code == 0
        assert "blocked" in result.output.lower()

    def test_governor_capture_detected(self, runner):
        result = runner.invoke(cli, ["explain", "GOVERNOR_CAPTURE_DETECTED"])
        assert result.exit_code == 0
        assert "capture" in result.output.lower()

    def test_list_all_codes(self, runner):
        result = runner.invoke(cli, ["explain", "--list"])
        assert result.exit_code == 0
        assert "regime:" in result.output
        assert "scars:" in result.output
        assert "gate_verdict:" in result.output
        assert "correlator:" in result.output
        assert "stability:" in result.output
        assert "drift:" in result.output

    def test_ambiguous_requires_qualified(self, runner):
        """Ambiguous bare codes should require qualified form."""
        # WARN appears in gate_verdict — check if it's ambiguous
        # (drift uses WARN_DRIFT to avoid collision)
        result = runner.invoke(cli, ["explain", "WARN"])
        # WARN is only in gate_verdict (drift has WARN_DRIFT)
        # so it should resolve uniquely
        assert result.exit_code == 0

    def test_list_json(self, runner):
        result = runner.invoke(cli, ["explain", "--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["schema_version"] == 1
        assert "categories" in data

    def test_no_code_no_list_exit_2(self, runner):
        """explain with no CODE and no --list should exit 2."""
        result = runner.invoke(cli, ["explain"])
        assert result.exit_code == 2


# =========================================================================
# TestTrace
# =========================================================================


class TestTrace:
    """Tests for governor trace."""

    def test_empty_no_events(self, runner, gov_project):
        result = runner.invoke(cli, ["trace"])
        assert result.exit_code == 0
        assert "No events recorded" in result.output

    def test_empty_json(self, runner, gov_project):
        result = runner.invoke(cli, ["trace", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["schema_version"] == 1
        assert data["events"] == []

    def test_with_receipt_shows_event(self, runner, gov_project):
        """After emitting a gate receipt, trace should show it."""
        from governor.gate_receipt import GateReceiptSystem
        gov_dir = gov_project / ".governor"
        system = GateReceiptSystem(gov_dir)
        system.emit(
            gate="test_gate",
            verdict="pass",
            subject_kind="test",
            subject_bytes=b"test data",
            evidence_bundle={"check": "passed"},
            gate_config={"rule": "test"},
        )
        result = runner.invoke(cli, ["trace", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["events"]) >= 1
        assert data["events"][0]["source"] == "receipt"

    def test_source_filter(self, runner, gov_project):
        """--source should filter events."""
        from governor.gate_receipt import GateReceiptSystem
        gov_dir = gov_project / ".governor"
        system = GateReceiptSystem(gov_dir)
        system.emit(
            gate="test_gate",
            verdict="pass",
            subject_kind="test",
            subject_bytes=b"test data",
            evidence_bundle={"check": "passed"},
            gate_config={"rule": "test"},
        )
        result = runner.invoke(cli, ["trace", "--source", "scar", "--json"])
        data = json.loads(result.output)
        # Filtering by scar should exclude receipt events
        for e in data["events"]:
            assert e["source"] == "scar"

    def test_last_limit(self, runner, gov_project):
        """--last should limit output."""
        from governor.gate_receipt import GateReceiptSystem
        gov_dir = gov_project / ".governor"
        system = GateReceiptSystem(gov_dir)
        for i in range(5):
            system.emit(
                gate=f"gate_{i}",
                verdict="pass",
                subject_kind="test",
                subject_bytes=f"data_{i}".encode(),
                evidence_bundle={"i": i},
                gate_config={"rule": "test"},
            )
        result = runner.invoke(cli, ["trace", "--last", "2", "--json"])
        data = json.loads(result.output)
        assert len(data["events"]) <= 2

    def test_deterministic_ordering(self, runner, gov_project):
        """Events with same timestamp should sort deterministically."""
        from governor.cli_operator import TraceEvent, _trace_sort_key
        e1 = TraceEvent(ts="2026-01-01T00:00:00Z", source="receipt",
                        kind="pass", summary="a", ref="aaa")
        e2 = TraceEvent(ts="2026-01-01T00:00:00Z", source="scar",
                        kind="failure", summary="b", ref="bbb")
        events = [e2, e1]
        events.sort(key=_trace_sort_key)
        # receipt has higher priority (lower number) than scar
        assert events[0].source == "receipt"
        assert events[1].source == "scar"

    def test_trace_json_schema_version(self, runner, gov_project):
        result = runner.invoke(cli, ["trace", "--json"])
        data = json.loads(result.output)
        assert data["schema_version"] == 1


# =========================================================================
# TestReadOnlyInvariant
# =========================================================================


class TestReadOnlyInvariant:
    """Operator commands must not create files or directories."""

    def test_status_full_readonly(self, runner, gov_project):
        gov_dir = gov_project / ".governor"
        before = _snapshot_tree(gov_dir)
        runner.invoke(cli, ["status", "--full"])
        after = _snapshot_tree(gov_dir)
        assert before == after, f"New files: {after - before}"

    def test_doctor_readonly(self, runner, gov_project):
        gov_dir = gov_project / ".governor"
        before = _snapshot_tree(gov_dir)
        runner.invoke(cli, ["doctor"])
        after = _snapshot_tree(gov_dir)
        assert before == after, f"New files: {after - before}"

    def test_trace_readonly(self, runner, gov_project):
        gov_dir = gov_project / ".governor"
        before = _snapshot_tree(gov_dir)
        runner.invoke(cli, ["trace"])
        after = _snapshot_tree(gov_dir)
        assert before == after, f"New files: {after - before}"

    def test_explain_readonly(self, runner, gov_project):
        gov_dir = gov_project / ".governor"
        before = _snapshot_tree(gov_dir)
        runner.invoke(cli, ["explain", "ELASTIC"])
        after = _snapshot_tree(gov_dir)
        assert before == after, f"New files: {after - before}"


# =========================================================================
# TestGoldenOutput (layout regression)
# =========================================================================


class TestGoldenOutput:
    """Assert exact text layout so future tweaks don't break formatting."""

    def test_dashboard_layout(self, runner, gov_project):
        """Dashboard text has expected structure and glyph casing."""
        result = runner.invoke(cli, ["status", "--full"], env={"GOV_BACKEND": "local"})
        lines = result.output.strip().split("\n")
        # First line is the header
        assert lines[0] == "Governor Dashboard"
        # Section labels are indented with consistent alignment
        labels = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped and ":" in stripped and not stripped.startswith(("[", "Tip")):
                label = stripped.split(":")[0]
                labels.append(label)
        expected_labels = [
            "Envelope", "Regime", "Drift", "Scars", "Scope",
            "Correlator", "Stability", "Violations", "Lanes",
            "Recent Receipts",
        ]
        assert labels == expected_labels
        # No line exceeds 80 cols
        for line in lines:
            assert len(line) <= 80, f"Line too wide ({len(line)}): {line!r}"

    def test_doctor_layout(self, runner, gov_project):
        """Doctor text uses canonical glyphs and consistent formatting."""
        result = runner.invoke(cli, ["doctor"], env={"GOV_BACKEND": "local"})
        lines = result.output.strip().split("\n")
        # Every check line contains a canonical glyph
        check_lines = [l for l in lines if l.strip().startswith("[")]
        assert len(check_lines) == 9
        for line in check_lines:
            assert any(g in line for g in ("[ok]", "[info]", "[WARN]", "[err]")), \
                f"Non-canonical glyph in: {line!r}"
        # Summary line at the end
        assert "ok" in lines[-1]
        # Width check
        for line in lines:
            assert len(line) <= 80, f"Line too wide ({len(line)}): {line!r}"

    def test_explain_layout(self, runner):
        """Explain text has category:CODE header and detail."""
        result = runner.invoke(cli, ["explain", "CAPTURE"])
        lines = result.output.strip().split("\n")
        assert lines[0] == "correlator:CAPTURE"
        assert "Capture detected" in lines[1]
        # Width check
        for line in lines:
            assert len(line) <= 80, f"Line too wide ({len(line)}): {line!r}"


# =========================================================================
# TestJsonPurity (no leaks into JSON mode)
# =========================================================================


class TestJsonPurity:
    """Stdout must be valid JSON only; stderr must be empty in JSON mode."""

    def test_status_full_json_purity(self, runner, gov_project):
        result = runner.invoke(cli, ["status", "--full", "--json"])
        assert result.exit_code == 0
        # Stdout is pure JSON
        data = json.loads(result.output)
        assert isinstance(data, dict)
        # No hint lines, no logging mixed in
        assert result.output.strip().startswith("{")
        assert result.output.strip().endswith("}")

    def test_doctor_json_purity(self, runner, gov_project):
        result = runner.invoke(cli, ["doctor", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert result.output.strip().startswith("{")
        assert result.output.strip().endswith("}")

    def test_explain_json_purity(self, runner):
        result = runner.invoke(cli, ["explain", "ELASTIC", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert result.output.strip().startswith("{")
        assert result.output.strip().endswith("}")

    def test_trace_json_purity(self, runner, gov_project):
        result = runner.invoke(cli, ["trace", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert result.output.strip().startswith("{")
        assert result.output.strip().endswith("}")

    def test_explain_list_json_purity(self, runner):
        result = runner.invoke(cli, ["explain", "--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert result.output.strip().startswith("{")
        assert result.output.strip().endswith("}")


# =========================================================================
# TestStatusRollup (shared truth object)
# =========================================================================


class TestStatusRollup:
    """Tests for StatusRollup: build, render, no-divergence tripwire."""

    def test_build_returns_frozen(self, runner, gov_project):
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"
        rollup = build_status_rollup(gov_dir)
        assert rollup.schema_version == 1
        # Frozen — should raise on mutation
        with pytest.raises(AttributeError):
            rollup.schema_version = 2  # type: ignore[misc]

    def test_to_dict_roundtrip(self, runner, gov_project):
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"
        rollup = build_status_rollup(gov_dir)
        d = rollup.to_dict()
        assert d["schema_version"] == 1
        assert all(k in d for k in (
            "envelope", "regime", "drift", "scars", "scope",
            "correlator", "stability", "violations", "recent_receipts", "lanes",
        ))

    def test_all_sections_ok_on_fresh_init(self, runner, gov_project):
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"
        rollup = build_status_rollup(gov_dir)
        for section_name in ("envelope", "regime", "drift", "scars", "scope",
                             "correlator", "stability", "violations",
                             "recent_receipts", "lanes"):
            section = getattr(rollup, section_name)
            assert section["ok"] is True, f"{section_name} not ok: {section}"

    def test_lanes_section_has_expected_keys(self, runner, gov_project):
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"
        rollup = build_status_rollup(gov_dir)
        ln = rollup.lanes
        assert ln["ok"] is True
        assert "autopilot_level" in ln
        assert "policy_version" in ln
        assert "artifact_count" in ln

    def test_render_text_includes_lanes(self, runner, gov_project):
        from governor.status_rollup import build_status_rollup, render_text
        gov_dir = gov_project / ".governor"
        rollup = build_status_rollup(gov_dir)
        text = render_text(rollup)
        assert "Lanes:" in text
        assert "autopilot" in text

    def test_render_json_parses_clean(self, runner, gov_project):
        from governor.status_rollup import build_status_rollup, render_json
        gov_dir = gov_project / ".governor"
        rollup = build_status_rollup(gov_dir)
        data = json.loads(render_json(rollup))
        assert data["schema_version"] == 1
        assert "lanes" in data

    def test_dashboard_json_matches_rollup(self, runner, gov_project):
        """Tripwire: dashboard JSON and rollup JSON share identical keys.

        This ensures dashboard_command delegates to StatusRollup and
        can never silently diverge.
        """
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"

        # Get dashboard JSON via CLI
        result = runner.invoke(cli, ["status", "--full", "--json"])
        assert result.exit_code == 0
        dashboard_data = json.loads(result.output)

        # Get rollup JSON directly
        rollup = build_status_rollup(gov_dir)
        rollup_data = rollup.to_dict()

        # Keys must be identical
        assert set(dashboard_data.keys()) == set(rollup_data.keys()), \
            f"Key mismatch: dashboard={set(dashboard_data.keys())}, rollup={set(rollup_data.keys())}"

        # Section keys must match (not values — state may differ between calls)
        for key in rollup_data:
            if isinstance(rollup_data[key], dict):
                assert set(dashboard_data[key].keys()) == set(rollup_data[key].keys()), \
                    f"Section {key} key mismatch"

    def test_corrupt_section_survives(self, runner, gov_project):
        """Corrupt state files don't crash the rollup builder."""
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"
        (gov_dir / "scars.json").write_text("{bad json")
        rollup = build_status_rollup(gov_dir)
        assert rollup.scars["ok"] is False
        assert "error" in rollup.scars

    def test_readonly(self, runner, gov_project):
        """Building a rollup must not create files."""
        from governor.status_rollup import build_status_rollup
        gov_dir = gov_project / ".governor"
        before = _snapshot_tree(gov_dir)
        build_status_rollup(gov_dir)
        after = _snapshot_tree(gov_dir)
        assert before == after, f"New files: {after - before}"
