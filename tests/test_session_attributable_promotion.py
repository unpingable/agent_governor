# SPDX-License-Identifier: Apache-2.0
"""Tock 2: session-attributable promotion (forcing gap GAP-N).

Tick 2 (working/tick-02-nq-host-detail.md) found that promotion/rejection
operated on the WHOLE working-tree diff, not on changes attributable to the
current session. On a dirty-at-start tree this means:
  - promote over-captures pre-existing uncommitted work, and
  - reject (git checkout -- . && git clean -fd) DESTROYS it.

These tests pin the fix: baseline snapshot at launch, refuse-dirty-by-default,
and — when allowed — fence the pre-existing set from both promote and reject.
"""

import subprocess
import time
from pathlib import Path
from typing import Any, Iterable

import pytest

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    LaunchConfig,
    NativeEvent,
)
from governor.runtime.events import EventKind, SourceLayer
from governor.runtime.promotion import (
    DirtyWorktreeError,
    detect_workspace_changes,
    revert_paths,
    snapshot_dirty_paths,
)
from governor.runtime.supervisor import SessionStatus, SessionSupervisor


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo), capture_output=True)
    (repo / "main.py").write_text("def main(): pass\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)
    return repo


class TestSnapshot:
    def test_clean_tree_is_empty(self, git_repo):
        assert snapshot_dirty_paths(git_repo) == []

    def test_modified_and_untracked_captured(self, git_repo):
        (git_repo / "main.py").write_text("def main(): return 1\n")
        (git_repo / "new.py").write_text("x = 1\n")
        assert snapshot_dirty_paths(git_repo) == ["main.py", "new.py"]

    def test_non_git_is_empty(self, tmp_path):
        assert snapshot_dirty_paths(tmp_path) == []


class TestBaselineScoping:
    def test_baseline_file_excluded_from_bundle(self, git_repo):
        # Pre-existing dirty file P, plus a session-attributable new file A.
        (git_repo / "preexisting.py").write_text("P = 1\n")
        baseline = snapshot_dirty_paths(git_repo)  # {preexisting.py}
        (git_repo / "session.py").write_text("A = 1\n")

        p = detect_workspace_changes(git_repo, baseline=baseline)
        assert p is not None
        assert p.changed_files == ["session.py"]
        assert p.excluded_files == ["preexisting.py"]

    def test_only_baseline_dirty_returns_none(self, git_repo):
        (git_repo / "preexisting.py").write_text("P = 1\n")
        baseline = snapshot_dirty_paths(git_repo)
        # No new changes beyond baseline → nothing session-attributable.
        assert detect_workspace_changes(git_repo, baseline=baseline) is None

    def test_no_baseline_is_legacy_whole_tree(self, git_repo):
        (git_repo / "main.py").write_text("def main(): return 2\n")
        p = detect_workspace_changes(git_repo)  # baseline=None
        assert p is not None and "main.py" in p.changed_files
        assert p.excluded_files == []


class TestRevertPaths:
    def test_reverts_tracked_modification_only(self, git_repo):
        (git_repo / "main.py").write_text("def main(): return 99\n")
        (git_repo / "other.py").write_text("keep = 1\n")  # NOT in revert list
        assert revert_paths(git_repo, ["main.py"]) is True
        assert (git_repo / "main.py").read_text() == "def main(): pass\n"  # restored
        assert (git_repo / "other.py").read_text() == "keep = 1\n"  # untouched

    def test_removes_untracked_in_list_only(self, git_repo):
        (git_repo / "a.py").write_text("a = 1\n")
        (git_repo / "b.py").write_text("b = 1\n")
        assert revert_paths(git_repo, ["a.py"]) is True
        assert not (git_repo / "a.py").exists()
        assert (git_repo / "b.py").exists()  # untouched

    def test_empty_paths_noop(self, git_repo):
        assert revert_paths(git_repo, []) is True


class TestGapNRegression:
    """The core GAP-N case: reject of a session-attributable promotion must
    NOT destroy pre-existing uncommitted work."""

    def test_reject_preserves_preexisting_work(self, git_repo):
        # Tick 1 residue: a modified tracked file + an untracked file, uncommitted.
        (git_repo / "main.py").write_text("def main(): return 'tick1'\n")
        (git_repo / "tick1_new.py").write_text("tick1 = True\n")
        baseline = snapshot_dirty_paths(git_repo)

        # Tick 2 (this session) produces its own files.
        (git_repo / "tick2.py").write_text("tick2 = True\n")

        p = detect_workspace_changes(git_repo, baseline=baseline)
        assert p is not None
        assert p.changed_files == ["tick2.py"]
        assert set(p.excluded_files) == {"main.py", "tick1_new.py"}

        # Reject Tick 2 — revert ONLY its files.
        assert revert_paths(git_repo, p.changed_files) is True

        # Tick 2's file is gone; Tick 1's work survives intact.
        assert not (git_repo / "tick2.py").exists()
        assert (git_repo / "main.py").read_text() == "def main(): return 'tick1'\n"
        assert (git_repo / "tick1_new.py").read_text() == "tick1 = True\n"


# --- supervisor-level: refuse-dirty-by-default ---

class _NoopAdapter:
    """Minimal adapter; launch() must NOT be reached when a dirty tree is refused."""

    def __init__(self):
        self.launched = False

    def capabilities(self):
        return AdapterCapabilities()

    def launch(self, config: LaunchConfig) -> BackendHandle:
        self.launched = True
        return BackendHandle(pid=4321)

    def iter_events(self, handle) -> Iterable[NativeEvent]:
        yield NativeEvent(kind="process_exit", payload={"returncode": 0})

    def send_control(self, handle, action: ControlAction) -> None:
        pass

    def shutdown(self, handle, graceful: bool = True) -> None:
        pass

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        return [{"kind": EventKind.SESSION_EXITED, "source_layer": SourceLayer.ADAPTER,
                 "payload": event.payload}]

    def is_alive(self, handle) -> bool:
        return False


class TestLaunchDirtyPolicy:
    def test_dirty_tree_refused_by_default(self, git_repo, tmp_path):
        (git_repo / "main.py").write_text("dirty = 1\n")  # dirty at start
        sup = SessionSupervisor(state_dir=tmp_path / "rt")
        adapter = _NoopAdapter()
        rec = sup.create_session(adapter, "claude_code", str(git_repo), task="t")
        with pytest.raises(DirtyWorktreeError):
            sup.launch_session(rec.session_id)
        assert adapter.launched is False  # refused BEFORE the backend ran
        assert sup.get_session(rec.session_id).status == SessionStatus.FAILED

    def test_allow_dirty_records_baseline_and_launches(self, git_repo, tmp_path):
        (git_repo / "main.py").write_text("dirty = 1\n")
        sup = SessionSupervisor(state_dir=tmp_path / "rt")
        adapter = _NoopAdapter()
        rec = sup.create_session(adapter, "claude_code", str(git_repo),
                                 task="t", allow_dirty=True)
        sup.launch_session(rec.session_id)
        assert adapter.launched is True
        assert sup.get_session(rec.session_id).baseline_dirty == ["main.py"]
        # let the (noop) event thread drain
        time.sleep(0.3)

    def test_clean_tree_launches_with_empty_baseline(self, git_repo, tmp_path):
        sup = SessionSupervisor(state_dir=tmp_path / "rt")
        adapter = _NoopAdapter()
        rec = sup.create_session(adapter, "claude_code", str(git_repo), task="t")
        sup.launch_session(rec.session_id)
        assert sup.get_session(rec.session_id).baseline_dirty == []
        time.sleep(0.3)
