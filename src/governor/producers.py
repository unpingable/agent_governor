# SPDX-License-Identifier: Apache-2.0
"""
Receipt producers: Functions that create receipts from real inputs.

Per NLAI: These are the ONLY way to create receipts. Agents provide
pointers (paths, commands), governor uses these producers to verify
and create receipts.
"""

import hashlib
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .receipts import FileSnapshot, CmdRun, DiffReceipt


def produce_file_snapshot(
    path: str | Path,
    base_path: str | Path | None = None,
    excerpt_spans: list[tuple[int, int]] | None = None,
) -> FileSnapshot:
    """
    Produce a FileSnapshot receipt by reading and hashing a file.

    Args:
        path: Path to the file (absolute or relative to base_path)
        base_path: Optional base directory. If provided, path is relative to it.
        excerpt_spans: Optional line ranges that are relevant to the claim.

    Returns:
        FileSnapshot receipt proving the file state at verification time.

    Raises:
        FileNotFoundError: If the file does not exist.
        IsADirectoryError: If the path is a directory, not a file.
        PermissionError: If the file cannot be read.
    """
    if base_path is not None:
        full_path = Path(base_path) / path
        stored_path = str(path)
    else:
        full_path = Path(path)
        stored_path = str(path)

    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {full_path}")

    if full_path.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {full_path}")

    content = full_path.read_bytes()
    blob_hash = hashlib.sha256(content).hexdigest()

    return FileSnapshot(
        path=stored_path,
        blob_hash=blob_hash,
        size_bytes=len(content),
        timestamp=datetime.now(timezone.utc),
        excerpt_spans=excerpt_spans,
    )


def produce_cmd_run(
    command: list[str] | tuple[str, ...],
    cwd: str | Path | None = None,
    timeout: int = 300,
) -> CmdRun:
    """
    Produce a CmdRun receipt by executing a command.

    Args:
        command: Command and arguments to run.
        cwd: Working directory for the command. Defaults to current directory.
        timeout: Maximum seconds to wait for command. Defaults to 300 (5 min).

    Returns:
        CmdRun receipt proving the command execution and result.

    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout.
        FileNotFoundError: If the command executable is not found.
    """
    if cwd is None:
        cwd = Path.cwd()
    else:
        cwd = Path(cwd)

    start_time = time.monotonic()

    result = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        timeout=timeout,
    )

    duration_ms = int((time.monotonic() - start_time) * 1000)

    stdout_hash = hashlib.sha256(result.stdout).hexdigest()
    stderr_hash = hashlib.sha256(result.stderr).hexdigest()

    return CmdRun(
        command=tuple(command),
        exit_code=result.returncode,
        stdout_hash=stdout_hash,
        stderr_hash=stderr_hash,
        cwd=str(cwd.resolve()),
        duration_ms=duration_ms,
        timestamp=datetime.now(timezone.utc),
    )


def produce_diff_receipt(
    patch_text: str,
    repo_root: str | Path | None = None,
) -> DiffReceipt:
    """
    Produce a DiffReceipt from unified diff text.

    Parses the diff to extract paths touched and line counts.
    If repo_root is a git repo, captures the current tree hash.

    Args:
        patch_text: Unified diff text.
        repo_root: Optional git repo root for tree hash. If not provided
                   or not a git repo, base_tree_hash will be empty.

    Returns:
        DiffReceipt proving the changeset content.
    """
    paths_touched = _parse_diff_paths(patch_text)
    additions, deletions = _count_diff_lines(patch_text)
    unified_diff_hash = hashlib.sha256(patch_text.encode()).hexdigest()

    base_tree_hash = ""
    if repo_root is not None:
        base_tree_hash = _get_git_tree_hash(repo_root)

    return DiffReceipt(
        paths_touched=tuple(paths_touched),
        unified_diff_hash=unified_diff_hash,
        base_tree_hash=base_tree_hash,
        additions=additions,
        deletions=deletions,
        timestamp=datetime.now(timezone.utc),
    )


def _parse_diff_paths(patch_text: str) -> list[str]:
    """Extract file paths from unified diff."""
    paths = []
    for line in patch_text.splitlines():
        # Handle +++ b/path/to/file format
        if line.startswith("+++ "):
            path = line[4:]
            # Remove b/ prefix if present (git diff format)
            if path.startswith("b/"):
                path = path[2:]
            # Skip /dev/null (deleted files use this)
            if path != "/dev/null":
                paths.append(path)
        # Handle --- a/path/to/file for deleted files
        elif line.startswith("--- "):
            path = line[4:]
            if path.startswith("a/"):
                path = path[2:]
            # Only add if it's a deletion (will have +++ /dev/null)
            # We track this via the +++ line, so skip here
    return paths


def _count_diff_lines(patch_text: str) -> tuple[int, int]:
    """Count additions and deletions in unified diff."""
    additions = 0
    deletions = 0

    in_hunk = False
    for line in patch_text.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk:
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

    return additions, deletions


def _get_git_tree_hash(repo_root: str | Path) -> str:
    """Get the current git tree hash, or empty string if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""
