# SPDX-License-Identifier: Apache-2.0
"""Minimal promotions: end-of-session workspace diff → operator approve/reject.

A promotion is "do we accept this produced work?" — the bridge from
agent chatter to real work product. This is the smallest slice:
detect changes, show diff, let operator decide, emit receipt.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class DirtyWorktreeError(Exception):
    """Raised when a session is launched on a dirty working tree without
    explicit allow_dirty. Session-attributable custody (GAP-N) cannot be
    established when pre-existing uncommitted work is present, so the
    default is to refuse rather than risk over-capture on promote or
    destruction on reject."""

    def __init__(self, repo_path: str, dirty: list[str]):
        self.repo_path = repo_path
        self.dirty = dirty
        super().__init__(
            f"working tree at {repo_path} is dirty at session start "
            f"({len(dirty)} pre-existing path(s)); pass allow_dirty=True to "
            f"fence them from this session's promotion/rejection"
        )


@dataclass
class Promotion:
    """A pending workspace change awaiting operator decision."""

    promotion_id: str
    session_id: str
    created_at: str
    status: str  # pending | approved | rejected
    repo_path: str
    changed_files: list[str]
    diff_stat: str  # git diff --stat output
    diff_text: str  # unified diff
    decision_at: str | None = None
    decision_reason: str | None = None
    # GAP-N (Tock 2): paths that were already dirty at session start and are
    # therefore NOT attributable to this session. Excluded from the bundle,
    # never reverted on reject.
    excluded_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "promotion_id": self.promotion_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "status": self.status,
            "repo_path": self.repo_path,
            "changed_files": self.changed_files,
            "diff_stat": self.diff_stat,
            "decision_at": self.decision_at,
            "decision_reason": self.decision_reason,
            "excluded_files": self.excluded_files,
        }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


_JUNK_PATTERNS = {"__pycache__", ".pyc", ".pyo", ".egg-info", ".DS_Store", ".pytest_cache"}


def _is_junk(path: str) -> bool:
    return any(pat in path for pat in _JUNK_PATTERNS)


def snapshot_dirty_paths(repo_path: str | Path) -> list[str]:
    """Return the sorted set of dirty (tracked-modified) + untracked paths.

    The baseline primitive for session-attributable promotion: captured at
    session launch, then diffed against the end-of-session state so the
    promotion bundle contains only what THIS session produced. Junk-filtered.
    Returns [] on a clean tree or a non-git path.
    """
    repo = Path(repo_path)
    try:
        diff_names = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    paths = {f for f in diff_names.stdout.strip().split("\n") if f and not _is_junk(f)}
    paths |= {f for f in untracked.stdout.strip().split("\n") if f and not _is_junk(f)}
    return sorted(paths)


def detect_workspace_changes(
    repo_path: str | Path,
    baseline: list[str] | set[str] | None = None,
) -> Promotion | None:
    """Detect uncommitted workspace changes and create a pending promotion.

    Uses git to find modified/new files relative to HEAD. Returns None if the
    workspace is clean (after baseline exclusion) or not a git repo.

    GAP-N (Tock 2): when ``baseline`` is provided (the set of paths already
    dirty at session start), those paths are EXCLUDED from the promotion
    bundle — the bundle then contains only changes attributable to this
    session. The excluded paths are recorded on ``Promotion.excluded_files``.
    With ``baseline=None`` the behaviour is the legacy whole-tree diff.
    """
    repo = Path(repo_path)
    baseline_set = set(baseline or ())

    # Get changed tracked files
    try:
        diff_names = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    # Get untracked files (respects .gitignore via --exclude-standard)
    try:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    changed = [f for f in diff_names.stdout.strip().split("\n") if f and not _is_junk(f)]
    new = [f for f in untracked.stdout.strip().split("\n") if f and not _is_junk(f)]

    # GAP-N: fence pre-existing dirty paths out of the session bundle.
    excluded = sorted((set(changed) | set(new)) & baseline_set)
    changed = [f for f in changed if f not in baseline_set]
    new = [f for f in new if f not in baseline_set]
    all_files = changed + new

    if not all_files:
        return None

    # Get diff stat — scoped to this session's tracked changes only (GAP-N).
    try:
        stat_cmd = ["git", "diff", "--stat", "HEAD"]
        if changed:
            stat_cmd += ["--", *changed]
        stat_result = subprocess.run(
            stat_cmd, cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
        diff_stat = stat_result.stdout.strip() if changed else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        diff_stat = f"{len(all_files)} file(s) changed"

    # For untracked files, add them to the stat
    if new:
        new_lines = "\n".join(f" {f} (new file)" for f in new)
        if diff_stat:
            diff_stat = diff_stat + "\n" + new_lines
        else:
            diff_stat = new_lines

    # Get unified diff — scoped to this session's tracked changes only (GAP-N).
    diff_text = ""
    if changed:
        try:
            diff_result = subprocess.run(
                ["git", "diff", "HEAD", "--", *changed],
                cwd=str(repo), capture_output=True, text=True, timeout=10,
            )
            diff_text = diff_result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            diff_text = ""

    # For untracked files, append their content as pseudo-diff
    for f in new:
        fpath = repo / f
        if fpath.exists() and fpath.stat().st_size < 50_000:
            try:
                content = fpath.read_text()
                diff_text += f"\n--- /dev/null\n+++ b/{f}\n"
                for line in content.splitlines():
                    diff_text += f"+{line}\n"
            except (OSError, UnicodeDecodeError):
                pass

    return Promotion(
        promotion_id=f"prom_{uuid.uuid4().hex[:12]}",
        session_id="",  # Caller sets this
        created_at=_now_iso(),
        status="pending",
        repo_path=str(repo),
        changed_files=all_files,
        diff_stat=diff_stat,
        diff_text=diff_text,
        excluded_files=excluded,
    )


def approve_promotion(promotion: Promotion, reason: str | None = None) -> Promotion:
    """Mark a promotion as approved."""
    promotion.status = "approved"
    promotion.decision_at = _now_iso()
    promotion.decision_reason = reason
    return promotion


def reject_promotion(promotion: Promotion, reason: str | None = None) -> Promotion:
    """Mark a promotion as rejected. Reverts workspace changes."""
    promotion.status = "rejected"
    promotion.decision_at = _now_iso()
    promotion.decision_reason = reason
    return promotion


def revert_workspace(repo_path: str | Path) -> bool:
    """Revert ALL uncommitted changes in the workspace (whole-tree blast).

    DANGEROUS on a dirty-at-start tree — destroys pre-existing uncommitted
    work (this is GAP-N). The supervisor no longer calls this for rejection;
    use ``revert_paths`` to revert only session-attributable changes. Retained
    only for the clean-tree case and back-compat.
    """
    repo = Path(repo_path)
    try:
        # Reset tracked changes
        subprocess.run(
            ["git", "checkout", "--", "."],
            cwd=str(repo), capture_output=True, timeout=10,
        )
        # Remove untracked files
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=str(repo), capture_output=True, timeout=10,
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def revert_paths(repo_path: str | Path, paths: list[str]) -> bool:
    """Revert ONLY the given paths, leaving everything else untouched.

    Used to reject a session-attributable promotion (GAP-N / Tock 2):
    pre-existing dirty files are never in ``paths``, so this cannot destroy
    prior uncommitted work. Tracked-modified paths are restored via
    ``git checkout``; untracked paths are removed individually (no
    ``git clean -fd`` blast).
    """
    repo = Path(repo_path)
    if not paths:
        return True
    ok = True
    for p in paths:
        if _is_junk(p):
            continue
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", p],
                cwd=str(repo), capture_output=True, timeout=10,
            ).returncode == 0
            if tracked:
                subprocess.run(
                    ["git", "checkout", "--", p],
                    cwd=str(repo), capture_output=True, timeout=10,
                )
            else:
                fpath = repo / p
                if fpath.is_file() or fpath.is_symlink():
                    fpath.unlink()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
        except OSError:
            ok = False
    return ok
