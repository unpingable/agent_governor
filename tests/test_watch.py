"""Tests for the watch mode."""

import pytest
import time
from pathlib import Path
from datetime import datetime, timezone

from governor.watch import (
    FileState,
    FileChange,
    WatchEvent,
    WatchConfig,
    FileWatcher,
    WatchSession,
)


class TestFileState:
    """Tests for FileState."""

    def test_create_from_file(self, tmp_path):
        """Test creating FileState from a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        state = FileState.from_file(test_file)

        assert state.path == str(test_file)
        assert state.size == len("hello world")
        assert state.content_hash is not None

    def test_content_hash_changes(self, tmp_path):
        """Test that content hash changes when file changes."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("version 1")
        state1 = FileState.from_file(test_file)

        test_file.write_text("version 2")
        state2 = FileState.from_file(test_file)

        assert state1.content_hash != state2.content_hash

    def test_serialization(self, tmp_path):
        """Test FileState serialization."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        state = FileState.from_file(test_file)
        data = state.to_dict()
        restored = FileState.from_dict(data)

        assert restored.path == state.path
        assert restored.size == state.size
        assert restored.content_hash == state.content_hash


class TestFileChange:
    """Tests for FileChange."""

    def test_create_change(self):
        """Test creating a file change."""
        change = FileChange(
            path="/path/to/file.py",
            change_type="created",
        )

        assert change.path == "/path/to/file.py"
        assert change.change_type == "created"
        assert change.timestamp is not None

    def test_serialization(self):
        """Test FileChange serialization."""
        change = FileChange(
            path="/path/to/file.py",
            change_type="modified",
        )

        data = change.to_dict()
        assert data["path"] == "/path/to/file.py"
        assert data["change_type"] == "modified"


class TestWatchEvent:
    """Tests for WatchEvent."""

    def test_create_event(self):
        """Test creating a watch event."""
        event = WatchEvent(
            event_type="change",
            message="File modified",
            data={"path": "/test.py"},
        )

        assert event.event_type == "change"
        assert event.message == "File modified"
        assert event.data["path"] == "/test.py"

    def test_serialization(self):
        """Test WatchEvent serialization."""
        event = WatchEvent(
            event_type="status",
            message="Watcher started",
        )

        data = event.to_dict()
        assert data["event_type"] == "status"
        assert "timestamp" in data


class TestWatchConfig:
    """Tests for WatchConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = WatchConfig()

        assert config.poll_interval == 1.0
        assert config.security_scan is True
        assert len(config.watch_patterns) > 0

    def test_serialization(self):
        """Test WatchConfig serialization."""
        config = WatchConfig(
            poll_interval=2.0,
            security_scan=False,
        )

        data = config.to_dict()
        restored = WatchConfig.from_dict(data)

        assert restored.poll_interval == 2.0
        assert restored.security_scan is False


class TestFileWatcher:
    """Tests for FileWatcher."""

    def test_initialize(self, tmp_path):
        """Test watcher initialization."""
        (tmp_path / "file1.py").write_text("# test")
        (tmp_path / "file2.py").write_text("# test")

        watcher = FileWatcher(tmp_path)
        watcher.initialize()

        # Should have tracked the files
        assert len(watcher._file_states) == 2

    def test_detect_created_file(self, tmp_path):
        """Test detecting a created file."""
        (tmp_path / "existing.py").write_text("# existing")

        watcher = FileWatcher(tmp_path)
        watcher.initialize()

        # Create a new file
        (tmp_path / "new.py").write_text("# new file")

        changes, _ = watcher.check_once()

        assert len(changes) == 1
        assert changes[0].change_type == "created"
        assert "new.py" in changes[0].path

    def test_detect_modified_file(self, tmp_path):
        """Test detecting a modified file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# version 1")

        watcher = FileWatcher(tmp_path)
        watcher.initialize()

        # Modify the file
        test_file.write_text("# version 2")

        changes, _ = watcher.check_once()

        assert len(changes) == 1
        assert changes[0].change_type == "modified"
        assert "test.py" in changes[0].path

    def test_detect_deleted_file(self, tmp_path):
        """Test detecting a deleted file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("# will be deleted")

        watcher = FileWatcher(tmp_path)
        watcher.initialize()

        # Delete the file
        test_file.unlink()

        changes, _ = watcher.check_once()

        assert len(changes) == 1
        assert changes[0].change_type == "deleted"
        assert "test.py" in changes[0].path

    def test_ignore_patterns(self, tmp_path):
        """Test that ignore patterns work."""
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.pyc").write_text("bytecode")

        config = WatchConfig(ignore_patterns=["__pycache__", "*.pyc"])
        watcher = FileWatcher(tmp_path, config)
        watcher.initialize()

        assert len(watcher._file_states) == 0

    def test_watch_patterns(self, tmp_path):
        """Test that watch patterns filter files."""
        (tmp_path / "file.py").write_text("# python")
        (tmp_path / "file.txt").write_text("text")

        config = WatchConfig(watch_patterns=["**/*.py"])
        watcher = FileWatcher(tmp_path, config)
        watcher.initialize()

        # Should only track .py files
        assert len(watcher._file_states) == 1
        assert any(".py" in path for path in watcher._file_states)

    def test_security_scan_on_change(self, tmp_path):
        """Test security scanning on file changes."""
        watcher = FileWatcher(tmp_path)
        watcher.initialize()

        # Create a file with a security issue
        (tmp_path / "config.py").write_text('password = "admin"')

        changes, findings = watcher.check_once()

        assert len(changes) == 1
        assert len(findings) >= 1

    def test_no_security_scan_when_disabled(self, tmp_path):
        """Test that security scan can be disabled."""
        config = WatchConfig(security_scan=False)
        watcher = FileWatcher(tmp_path, config)
        watcher.initialize()

        # Create a file with a security issue
        (tmp_path / "config.py").write_text('password = "admin"')

        changes, findings = watcher.check_once()

        assert len(changes) == 1
        assert len(findings) == 0  # No security scan

    def test_callbacks(self, tmp_path):
        """Test that callbacks are called."""
        changes_received = []
        events_received = []

        config = WatchConfig(
            on_change=lambda c: changes_received.append(c),
            on_event=lambda e: events_received.append(e),
            security_scan=False,
        )
        watcher = FileWatcher(tmp_path, config)
        watcher.initialize()

        # Should have received initialization event
        assert any(e.event_type == "status" for e in events_received)

        # Create a file
        (tmp_path / "new.py").write_text("# new")
        watcher.check_once()

        assert len(changes_received) == 1


class TestWatchSession:
    """Tests for WatchSession."""

    def test_session_start(self, tmp_path):
        """Test starting a watch session."""
        (tmp_path / "test.py").write_text("# test")

        session = WatchSession(tmp_path)
        session.start()

        assert session._start_time is not None

    def test_session_tracks_changes(self, tmp_path):
        """Test that session tracks changes."""
        session = WatchSession(tmp_path)
        session.start()

        # Create some files
        (tmp_path / "file1.py").write_text("# 1")
        session.check()

        (tmp_path / "file2.py").write_text("# 2")
        session.check()

        assert len(session.changes) == 2

    def test_session_summary(self, tmp_path):
        """Test session summary."""
        session = WatchSession(tmp_path)
        session.start()

        (tmp_path / "created.py").write_text("# new")
        session.check()

        summary = session.get_summary()

        assert summary["total_changes"] == 1
        assert summary["changes_by_type"]["created"] == 1
        assert "created.py" in summary["files_changed"][0]

    def test_session_tracks_security_findings(self, tmp_path):
        """Test that session tracks security findings."""
        session = WatchSession(tmp_path)
        session.start()

        # Create a file with security issue
        (tmp_path / "config.py").write_text('api_key = "sk-1234567890abcdefghij1234567890abcdefghij12345678"')
        session.check()

        assert len(session.findings) >= 1

        summary = session.get_summary()
        assert summary["total_findings"] >= 1
