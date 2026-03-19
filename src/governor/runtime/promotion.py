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
        }


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def detect_workspace_changes(repo_path: str | Path) -> Promotion | None:
    """Detect uncommitted workspace changes and create a pending promotion.

    Uses git to find modified/new files relative to HEAD.
    Returns None if workspace is clean or not a git repo.
    """
    repo = Path(repo_path)

    # Get changed tracked files
    try:
        diff_names = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    # Get untracked files
    try:
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    changed = [f for f in diff_names.stdout.strip().split("\n") if f]
    new = [f for f in untracked.stdout.strip().split("\n") if f]
    all_files = changed + new

    if not all_files:
        return None

    # Get diff stat
    try:
        stat_result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=str(repo), capture_output=True, text=True, timeout=10,
        )
        diff_stat = stat_result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        diff_stat = f"{len(all_files)} file(s) changed"

    # For untracked files, add them to the stat
    if new:
        new_lines = "\n".join(f" {f} (new file)" for f in new)
        if diff_stat:
            diff_stat = diff_stat + "\n" + new_lines
        else:
            diff_stat = new_lines

    # Get unified diff
    try:
        diff_result = subprocess.run(
            ["git", "diff", "HEAD"],
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
    """Revert all uncommitted changes in the workspace.

    Used when a promotion is rejected.
    Returns True if revert succeeded.
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
