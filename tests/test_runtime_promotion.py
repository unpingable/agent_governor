# SPDX-License-Identifier: Apache-2.0
"""Tests for the promotion system: workspace diff → approve/reject."""

import subprocess
from pathlib import Path

import pytest

from governor.runtime.promotion import (
    Promotion,
    approve_promotion,
    detect_workspace_changes,
    reject_promotion,
    revert_workspace,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo with one committed file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True)
    (repo / "main.py").write_text("def main(): pass\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)
    return repo


class TestDetectWorkspaceChanges:
    def test_clean_workspace_returns_none(self, git_repo):
        assert detect_workspace_changes(git_repo) is None

    def test_modified_file_detected(self, git_repo):
        (git_repo / "main.py").write_text("def main(): return 42\n")
        p = detect_workspace_changes(git_repo)
        assert p is not None
        assert p.status == "pending"
        assert "main.py" in p.changed_files
        assert p.diff_text  # has unified diff
        assert p.diff_stat  # has stat summary

    def test_new_file_detected(self, git_repo):
        (git_repo / "test_main.py").write_text("def test_main(): pass\n")
        p = detect_workspace_changes(git_repo)
        assert p is not None
        assert "test_main.py" in p.changed_files
        assert "(new file)" in p.diff_stat

    def test_mixed_changes(self, git_repo):
        (git_repo / "main.py").write_text("def main(): return 42\n")
        (git_repo / "utils.py").write_text("def helper(): pass\n")
        p = detect_workspace_changes(git_repo)
        assert p is not None
        assert len(p.changed_files) == 2

    def test_promotion_id_format(self, git_repo):
        (git_repo / "main.py").write_text("changed\n")
        p = detect_workspace_changes(git_repo)
        assert p.promotion_id.startswith("prom_")

    def test_not_a_git_repo(self, tmp_path):
        (tmp_path / "file.py").write_text("x = 1\n")
        p = detect_workspace_changes(tmp_path)
        # Should return None or handle gracefully
        assert p is None


class TestApproveReject:
    def test_approve(self, git_repo):
        (git_repo / "main.py").write_text("changed\n")
        p = detect_workspace_changes(git_repo)
        approve_promotion(p, reason="Looks good")
        assert p.status == "approved"
        assert p.decision_at is not None
        assert p.decision_reason == "Looks good"

    def test_reject(self, git_repo):
        (git_repo / "main.py").write_text("changed\n")
        p = detect_workspace_changes(git_repo)
        reject_promotion(p, reason="Bad code")
        assert p.status == "rejected"
        assert p.decision_reason == "Bad code"


class TestRevertWorkspace:
    def test_revert_modified(self, git_repo):
        (git_repo / "main.py").write_text("CHANGED CONTENT\n")
        assert revert_workspace(git_repo)
        assert (git_repo / "main.py").read_text() == "def main(): pass\n"

    def test_revert_removes_untracked(self, git_repo):
        (git_repo / "new_file.py").write_text("should be removed\n")
        assert revert_workspace(git_repo)
        assert not (git_repo / "new_file.py").exists()

    def test_revert_mixed(self, git_repo):
        (git_repo / "main.py").write_text("CHANGED\n")
        (git_repo / "extra.py").write_text("new\n")
        assert revert_workspace(git_repo)
        assert (git_repo / "main.py").read_text() == "def main(): pass\n"
        assert not (git_repo / "extra.py").exists()


class TestPromotionToDict:
    def test_serialization(self, git_repo):
        (git_repo / "main.py").write_text("changed\n")
        p = detect_workspace_changes(git_repo)
        p.session_id = "sess_test"
        d = p.to_dict()
        assert d["promotion_id"].startswith("prom_")
        assert d["session_id"] == "sess_test"
        assert d["status"] == "pending"
        assert "main.py" in d["changed_files"]
        # diff_text intentionally excluded from to_dict (can be large)
        assert "diff_text" not in d


class TestSupervisorPromotion:
    """Test promotion integration with the supervisor."""

    def test_session_exit_detects_promotion(self, tmp_path):
        """When a session exits with workspace changes, a promotion is created."""
        import time
        from governor.runtime.supervisor import SessionSupervisor
        from governor.runtime.adapter import BackendHandle, AdapterCapabilities, LaunchConfig, NativeEvent, ControlAction
        from governor.runtime.events import EventKind

        # Create a git repo
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), capture_output=True)
        (repo / "code.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)

        # Adapter that modifies the workspace then exits
        class ModifyingAdapter:
            def capabilities(self):
                return AdapterCapabilities()
            def launch(self, config):
                # Simulate agent modifying a file
                (repo / "code.py").write_text("x = 42\n")
                return BackendHandle(pid=1)
            def iter_events(self, handle):
                yield NativeEvent(kind="process_exit", payload={"returncode": 0})
            def send_control(self, handle, action): pass
            def shutdown(self, handle, graceful=True): pass
            def map_event(self, event):
                return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter", "payload": event.payload}]
            def is_alive(self, handle): return False

        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        adapter = ModifyingAdapter()
        record = supervisor.create_session(adapter, "test", str(repo), operator_mode="autonomous")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        # Should have a pending promotion
        p = supervisor.get_pending_promotion(record.session_id)
        assert p is not None
        assert p.status == "pending"
        assert "code.py" in p.changed_files

        # Events should include promotion_required
        events = supervisor.get_events(record.session_id)
        kinds = [e.kind for e in events]
        assert EventKind.PROMOTION_REQUIRED in kinds

    def test_approve_promotion(self, tmp_path):
        """Approving a promotion keeps workspace changes."""
        import time
        from governor.runtime.supervisor import SessionSupervisor
        from governor.runtime.adapter import BackendHandle, AdapterCapabilities, NativeEvent
        from governor.runtime.events import EventKind

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), capture_output=True)
        (repo / "code.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)

        class ModifyingAdapter:
            def capabilities(self): return AdapterCapabilities()
            def launch(self, config):
                (repo / "code.py").write_text("x = 42\n")
                return BackendHandle(pid=1)
            def iter_events(self, handle):
                yield NativeEvent(kind="process_exit", payload={"returncode": 0})
            def send_control(self, h, a): pass
            def shutdown(self, h, g=True): pass
            def map_event(self, e):
                return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter", "payload": e.payload}]
            def is_alive(self, h): return False

        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        record = supervisor.create_session(ModifyingAdapter(), "test", str(repo), operator_mode="autonomous")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        p = supervisor.resolve_promotion(record.session_id, "approve", reason="LGTM")
        assert p.status == "approved"
        # File should still be changed
        assert (repo / "code.py").read_text() == "x = 42\n"

        events = supervisor.get_events(record.session_id)
        kinds = [e.kind for e in events]
        assert EventKind.PROMOTION_RESOLVED in kinds

    def test_reject_promotion_reverts(self, tmp_path):
        """Rejecting a promotion reverts workspace changes."""
        import time
        from governor.runtime.supervisor import SessionSupervisor
        from governor.runtime.adapter import BackendHandle, AdapterCapabilities, NativeEvent
        from governor.runtime.events import EventKind

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), capture_output=True)
        (repo / "code.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)

        class ModifyingAdapter:
            def capabilities(self): return AdapterCapabilities()
            def launch(self, config):
                (repo / "code.py").write_text("x = 42\n")
                (repo / "new.py").write_text("new file\n")
                return BackendHandle(pid=1)
            def iter_events(self, handle):
                yield NativeEvent(kind="process_exit", payload={"returncode": 0})
            def send_control(self, h, a): pass
            def shutdown(self, h, g=True): pass
            def map_event(self, e):
                return [{"kind": EventKind.SESSION_EXITED, "source_layer": "adapter", "payload": e.payload}]
            def is_alive(self, h): return False

        supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
        record = supervisor.create_session(ModifyingAdapter(), "test", str(repo), operator_mode="autonomous")
        supervisor.launch_session(record.session_id)
        time.sleep(0.5)

        p = supervisor.resolve_promotion(record.session_id, "reject", reason="Bad code")
        assert p.status == "rejected"
        # Files should be reverted
        assert (repo / "code.py").read_text() == "x = 1\n"
        assert not (repo / "new.py").exists()
