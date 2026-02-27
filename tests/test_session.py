# SPDX-License-Identifier: Apache-2.0
"""Tests for process-scoped session identity."""

from __future__ import annotations

import governor.session as session_mod
import pytest

from governor.session import get_session_id, new_session_id, set_session_id


class TestSessionId:

    def setup_method(self):
        # Reset process global before each test
        session_mod._process_session_id = None

    def test_get_generates_on_first_call(self):
        sid = get_session_id()
        assert sid.startswith("gov_")
        assert len(sid) == 16  # "gov_" + 12 hex chars

    def test_get_is_stable_within_process(self):
        s1 = get_session_id()
        s2 = get_session_id()
        assert s1 == s2

    def test_set_overrides(self):
        set_session_id("gov_custom12345")
        assert get_session_id() == "gov_custom12345"

    def test_new_does_not_set_global(self):
        original = get_session_id()
        fresh = new_session_id()
        assert fresh != original
        assert fresh.startswith("gov_")
        assert get_session_id() == original  # unchanged

    def test_new_generates_unique(self):
        ids = {new_session_id() for _ in range(100)}
        assert len(ids) == 100


class TestDaemonStateSessionId:

    def test_daemon_state_has_session_id(self, tmp_path):
        session_mod._process_session_id = None
        from governor.daemon import DaemonState
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        state = DaemonState(gov_dir)
        assert state.session_id.startswith("gov_")

    @pytest.mark.asyncio
    async def test_hello_includes_session_id(self, tmp_path):
        session_mod._process_session_id = None
        from governor.daemon import DaemonState, Dispatcher, register_handlers
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        state = DaemonState(gov_dir)
        dispatcher = Dispatcher()
        register_handlers(dispatcher, state)

        result = await dispatcher._handlers["governor.hello"]({})
        assert "session_id" in result["governor"]
        assert result["governor"]["session_id"] == state.session_id


class TestJsonlSinkSessionId:

    def test_sink_with_session_id(self, tmp_path):
        from governor.signals.emit import JsonlSink
        from governor.signals.envelope import SignalEnvelope, CURRENT_SCHEMA_VERSION

        jsonl = tmp_path / "signals.jsonl"
        sink = JsonlSink(jsonl, session_id="gov_test123456")

        # Emit a valid envelope
        env = SignalEnvelope(
            schema_version=CURRENT_SCHEMA_VERSION,
            emitted_at="2026-01-01T00:00:00Z",
            emitter="test",
            emitter_version="1",
            signal_id="TEST",
            signal_version=1,
            phase="2.5",
            derivation="direct",
            derivation_version="1",
            subject_type="session",
            value=1.0,
            quality_status="ok",
        )
        sink.emit(env)

        envs = sink.read_all()
        assert len(envs) == 1

    def test_emit_failed_carries_session_id(self, tmp_path, monkeypatch):
        import os
        from governor.signals.emit import JsonlSink
        from governor.signals.envelope import SignalEnvelope, CURRENT_SCHEMA_VERSION

        jsonl = tmp_path / "signals.jsonl"
        sink = JsonlSink(jsonl, session_id="gov_mysession00")

        call_count = 0
        original_open = os.open

        def failing_open(path, flags, mode=0o644):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("simulated disk error")
            return original_open(path, flags, mode)

        monkeypatch.setattr(os, "open", failing_open)

        env = SignalEnvelope(
            schema_version=CURRENT_SCHEMA_VERSION,
            emitted_at="2026-01-01T00:00:00Z",
            emitter="test",
            emitter_version="1",
            signal_id="DOOMED",
            signal_version=1,
            phase="2.5",
            derivation="direct",
            derivation_version="1",
            subject_type="session",
            value=1.0,
            quality_status="ok",
        )
        sink.emit(env)

        envs = sink.read_all()
        assert len(envs) == 1
        assert envs[0].signal_id == "SIGNAL_EMIT_FAILED"
        assert envs[0].session_id == "gov_mysession00"
