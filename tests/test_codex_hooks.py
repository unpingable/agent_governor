# SPDX-License-Identifier: Apache-2.0
"""Tests for Codex CLI hooks integration."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from governor.codex_hooks import (
    CodexHookConfig,
    parse_codex_event,
    classify_event,
    extract_response_text,
    extract_usage,
    extract_error,
    log_codex_event,
    run_codex_governed,
    get_codex_status,
    install_codex_config,
    uninstall_codex_config,
    _emit_receipt,
    _log_file_changes,
)


# ── CodexHookConfig ────────────────────────────────────────────────────────


class TestCodexHookConfig:
    def test_defaults(self):
        c = CodexHookConfig()
        assert c.audit is True
        assert c.model == "o4-mini"
        assert c.codex_path == "codex"

    def test_roundtrip(self):
        c = CodexHookConfig(model="o3", codex_path="/usr/bin/codex")
        d = c.to_dict()
        c2 = CodexHookConfig.from_dict(d)
        assert c2.model == "o3"
        assert c2.codex_path == "/usr/bin/codex"

    def test_from_dict_defaults(self):
        c = CodexHookConfig.from_dict({})
        assert c.audit is True
        assert c.model == "o4-mini"


# ── parse_codex_event ──────────────────────────────────────────────────────


class TestParseCodexEvent:
    def test_valid_json(self):
        result = parse_codex_event('{"type": "thread.started"}')
        assert result == {"type": "thread.started"}

    def test_empty_line(self):
        assert parse_codex_event("") is None

    def test_whitespace_only(self):
        assert parse_codex_event("   \n") is None

    def test_malformed_json(self):
        assert parse_codex_event("{bad json") is None

    def test_strips_whitespace(self):
        result = parse_codex_event('  {"type": "test"}  ')
        assert result == {"type": "test"}


# ── classify_event ─────────────────────────────────────────────────────────


class TestClassifyEvent:
    def test_thread_started(self):
        assert classify_event({"type": "thread.started"}) == "session_start"

    def test_agent_message(self):
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}
        assert classify_event(event) == "response"

    def test_item_completed_non_agent(self):
        event = {"type": "item.completed", "item": {"type": "something_else"}}
        assert classify_event(event) == "unknown"

    def test_turn_completed(self):
        assert classify_event({"type": "turn.completed"}) == "turn_end"

    def test_error(self):
        assert classify_event({"type": "error"}) == "error"

    def test_turn_failed(self):
        assert classify_event({"type": "turn.failed"}) == "error"

    def test_unknown(self):
        assert classify_event({"type": "weird.event"}) == "unknown"


# ── extract_response_text ──────────────────────────────────────────────────


class TestExtractResponseText:
    def test_agent_message(self):
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": "hello"}}
        assert extract_response_text(event) == "hello"

    def test_non_agent_item(self):
        event = {"type": "item.completed", "item": {"type": "other"}}
        assert extract_response_text(event) is None

    def test_wrong_event_type(self):
        assert extract_response_text({"type": "turn.completed"}) is None


# ── extract_usage ──────────────────────────────────────────────────────────


class TestExtractUsage:
    def test_turn_completed(self):
        event = {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 50}}
        usage = extract_usage(event)
        assert usage == {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    def test_wrong_event(self):
        assert extract_usage({"type": "item.completed"}) is None

    def test_missing_usage(self):
        usage = extract_usage({"type": "turn.completed"})
        assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


# ── extract_error ──────────────────────────────────────────────────────────


class TestExtractError:
    def test_error_event(self):
        assert extract_error({"type": "error", "message": "bad"}) == "bad"

    def test_turn_failed(self):
        assert extract_error({"type": "turn.failed", "error": {"message": "oops"}}) == "oops"

    def test_non_error(self):
        assert extract_error({"type": "item.completed"}) is None


# ── log_codex_event ────────────────────────────────────────────────────────


class TestLogCodexEvent:
    def test_logs_to_audit(self, tmp_path):
        log_codex_event(tmp_path, {"type": "thread.started"})
        audit = tmp_path / "tool_audit.jsonl"
        assert audit.exists()
        entries = [json.loads(l) for l in audit.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["source"] == "codex"
        assert entries[0]["event_type"] == "thread.started"

    def test_session_start_also_notifies(self, tmp_path):
        log_codex_event(tmp_path, {"type": "thread.started"})
        notif = tmp_path / "notifications.jsonl"
        assert notif.exists()
        entries = [json.loads(l) for l in notif.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["event_type"] == "codex.session_start"

    def test_response_does_not_notify(self, tmp_path):
        event = {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}
        log_codex_event(tmp_path, event)
        notif = tmp_path / "notifications.jsonl"
        assert not notif.exists()

    def test_error_notifies(self, tmp_path):
        log_codex_event(tmp_path, {"type": "error", "message": "bad"})
        notif = tmp_path / "notifications.jsonl"
        assert notif.exists()

    def test_multiple_events_append(self, tmp_path):
        log_codex_event(tmp_path, {"type": "thread.started"})
        log_codex_event(tmp_path, {"type": "turn.completed"})
        audit = tmp_path / "tool_audit.jsonl"
        entries = [json.loads(l) for l in audit.read_text().strip().splitlines()]
        assert len(entries) == 2


# ── run_codex_governed ─────────────────────────────────────────────────────


class _FakeSnapshot:
    """Test helper: injectable snapshot class for run_codex_governed."""
    _instances: list = []
    _diff_result: list = []

    def __init__(self, root):
        self.root = root
        _FakeSnapshot._instances.append(self)

    def diff(self, other):
        return _FakeSnapshot._diff_result


class TestRunCodexGoverned:
    def _make_codex_output(self, events: list[dict]) -> str:
        """Build NDJSON output from event dicts."""
        return "\n".join(json.dumps(e) for e in events) + "\n"

    def setup_method(self):
        _FakeSnapshot._instances = []
        _FakeSnapshot._diff_result = []

    @patch("governor.codex_hooks.subprocess.run")
    def test_basic_execution(self, mock_run, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        events = [
            {"type": "thread.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
        ]
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_codex_output(events),
            stderr="",
        )

        exit_code, response, changes = run_codex_governed(
            tmp_path, "test prompt", _snapshot_cls=_FakeSnapshot,
        )

        assert exit_code == 0
        assert response == "done"
        assert changes == []

    @patch("governor.codex_hooks.subprocess.run")
    def test_file_changes_detected(self, mock_run, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        from governor.wrapper import FileChange

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_codex_output([
                {"type": "item.completed", "item": {"type": "agent_message", "text": "created file"}},
                {"type": "turn.completed"},
            ]),
            stderr="",
        )

        _FakeSnapshot._diff_result = [
            FileChange(path="new_file.py", change_type="created", new_hash="abc123"),
        ]

        exit_code, response, changes = run_codex_governed(
            tmp_path, "create file", _snapshot_cls=_FakeSnapshot,
        )
        assert len(changes) == 1
        assert changes[0].path == "new_file.py"

    @patch("governor.codex_hooks.subprocess.run")
    def test_codex_not_found(self, mock_run, tmp_path):
        (tmp_path / ".governor").mkdir()
        mock_run.side_effect = FileNotFoundError("codex not found")

        exit_code, response, changes = run_codex_governed(tmp_path, "test")
        assert exit_code == 127
        assert "not found" in response

    @patch("governor.codex_hooks.subprocess.run")
    def test_error_event(self, mock_run, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=self._make_codex_output([
                {"type": "error", "message": "rate limit exceeded"},
            ]),
            stderr="",
        )

        exit_code, response, changes = run_codex_governed(
            tmp_path, "test", _snapshot_cls=_FakeSnapshot,
        )
        assert exit_code == 1
        assert "rate limit" in response

    @patch("governor.codex_hooks.subprocess.run")
    def test_audit_trail_written(self, mock_run, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_codex_output([
                {"type": "thread.started"},
                {"type": "turn.completed"},
            ]),
            stderr="",
        )

        run_codex_governed(tmp_path, "test", _snapshot_cls=_FakeSnapshot)

        audit = gov_dir / "tool_audit.jsonl"
        assert audit.exists()
        entries = [json.loads(l) for l in audit.read_text().strip().splitlines()]
        assert len(entries) >= 2
        assert all(e["source"] == "codex" for e in entries)

    @patch("governor.codex_hooks.subprocess.run")
    def test_no_audit_when_disabled(self, mock_run, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        config = CodexHookConfig(audit=False, snapshot_changes=False)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=self._make_codex_output([
                {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
            ]),
            stderr="",
        )

        exit_code, response, changes = run_codex_governed(
            tmp_path, "test", config=config,
        )
        assert exit_code == 0
        assert response == "hi"
        assert not (gov_dir / "tool_audit.jsonl").exists()

    @patch("governor.codex_hooks.subprocess.run")
    def test_custom_model(self, mock_run, tmp_path):
        (tmp_path / ".governor").mkdir()
        config = CodexHookConfig(model="o3")

        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr="",
        )

        run_codex_governed(
            tmp_path, "test", config=config, _snapshot_cls=_FakeSnapshot,
        )

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "-m" in cmd
        model_idx = cmd.index("-m")
        assert cmd[model_idx + 1] == "o3"


# ── _emit_receipt ──────────────────────────────────────────────────────────


class TestEmitReceipt:
    def test_no_changes_pass(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        # Should not raise
        _emit_receipt(gov_dir, [], CodexHookConfig())

    def test_unapproved_changes_block(self, tmp_path):
        from governor.wrapper import FileChange

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "approved_files.json").write_text('["safe.py"]')

        changes = [FileChange(path="evil.py", change_type="created")]
        _emit_receipt(gov_dir, changes, CodexHookConfig())

        # Receipt should exist
        receipt_file = gov_dir / "receipts" / "gate_receipts.jsonl"
        assert receipt_file.exists()
        receipts = [json.loads(l) for l in receipt_file.read_text().strip().splitlines()]
        assert len(receipts) == 1
        assert receipts[0]["verdict"] == "block"

    def test_approved_changes_pass(self, tmp_path):
        from governor.wrapper import FileChange

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "approved_files.json").write_text('["safe.py"]')

        changes = [FileChange(path="safe.py", change_type="modified")]
        _emit_receipt(gov_dir, changes, CodexHookConfig())

        receipt_file = gov_dir / "receipts" / "gate_receipts.jsonl"
        receipts = [json.loads(l) for l in receipt_file.read_text().strip().splitlines()]
        assert receipts[0]["verdict"] == "pass"


# ── get_codex_status ───────────────────────────────────────────────────────


class TestGetCodexStatus:
    def test_no_config(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        with patch("governor.codex_hooks.shutil.which", return_value=None):
            status = get_codex_status(tmp_path)
            assert status["config_exists"] is False
            assert status["codex_available"] is False

    def test_with_config(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "codex_hooks.json").write_text(
            json.dumps({"codex_path": "codex", "model": "o4-mini"})
        )
        with patch("shutil.which", return_value="/usr/bin/codex"):
            status = get_codex_status(tmp_path)
            assert status["config_exists"] is True
            assert status["codex_available"] is True

    def test_with_audit_files(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "tool_audit.jsonl").write_text("{}\n")
        status = get_codex_status(tmp_path)
        assert "tool_audit.jsonl" in status["audit_files"]


# ── install/uninstall ──────────────────────────────────────────────────────


class TestInstallUninstall:
    def test_install_creates_config(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        success, msg = install_codex_config(tmp_path)
        assert success
        config_path = tmp_path / ".governor" / "codex_hooks.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["model"] == "o4-mini"

    def test_install_warns_if_binary_missing(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        with patch("shutil.which", return_value=None):
            success, msg = install_codex_config(tmp_path)
            assert success
            assert "not found" in msg

    def test_install_no_governor_dir(self, tmp_path):
        success, msg = install_codex_config(tmp_path)
        assert not success
        assert "governor init" in msg

    def test_install_custom_config(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        config = CodexHookConfig(model="o3", codex_path="/opt/codex")
        success, _ = install_codex_config(tmp_path, config)
        assert success
        data = json.loads((tmp_path / ".governor" / "codex_hooks.json").read_text())
        assert data["model"] == "o3"
        assert data["codex_path"] == "/opt/codex"

    def test_uninstall(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "codex_hooks.json").write_text("{}")
        success, msg = uninstall_codex_config(tmp_path)
        assert success
        assert not (gov_dir / "codex_hooks.json").exists()

    def test_uninstall_already_missing(self, tmp_path):
        (tmp_path / ".governor").mkdir()
        success, msg = uninstall_codex_config(tmp_path)
        assert success
        assert "No codex hooks" in msg


# ── _log_file_changes ─────────────────────────────────────────────────────


class TestLogFileChanges:
    def test_logs_changes(self, tmp_path):
        from governor.wrapper import FileChange

        changes = [
            FileChange(path="a.py", change_type="created"),
            FileChange(path="b.py", change_type="modified"),
        ]
        _log_file_changes(tmp_path, changes)

        audit = tmp_path / "tool_audit.jsonl"
        entries = [json.loads(l) for l in audit.read_text().strip().splitlines()]
        assert len(entries) == 2
        assert entries[0]["raw"]["path"] == "a.py"

    def test_empty_changes_noop(self, tmp_path):
        _log_file_changes(tmp_path, [])
        assert not (tmp_path / "tool_audit.jsonl").exists()
