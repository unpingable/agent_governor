# SPDX-License-Identifier: Apache-2.0
"""Secure receipt sinks for the MCP Governor Gateway.

RotatingFileSink: append-only JSONL with 0o600 permissions and size-based
rotation.  Creates files securely from the start (never chmod after).
Warns if an existing file has too-open permissions.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from receipt_v1.types import Receipt

# Default rotation: 10 MB per file, keep 5 files
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_KEEP_FILES = 5

# Receipt files are 0600: owner read/write only.
_FILE_MODE = 0o600


def _log(msg: str) -> None:
    print(f"[mcp-governor] {msg}", file=sys.stderr, flush=True)


def _check_permissions(path: Path) -> None:
    """Warn if an existing file has permissions more open than 0600."""
    try:
        st = os.stat(path)
        mode = st.st_mode & 0o777
        if mode != _FILE_MODE:
            _log(f"WARNING: Receipt file {path} has permissions {oct(mode)}, "
                 f"expected {oct(_FILE_MODE)}. Receipts may contain sensitive metadata.")
    except OSError:
        pass  # file doesn't exist yet — fine


class RotatingFileSink:
    """Append receipts as JSONL with secure permissions and size-based rotation.

    Security properties:
    - Files created with 0o600 (owner read/write only) from the start.
    - Existing files checked for too-open permissions (warns, doesn't fix).
    - Rotation by size: when current file exceeds ``max_bytes``, rotate.
    - Keeps at most ``keep_files`` rotated files (oldest deleted).

    Rotation naming: ``receipts.jsonl`` → ``receipts.jsonl.1`` → ``receipts.jsonl.2``
    (newest rotated is ``.1``).

    Args:
        path: File path for receipt storage.
        fsync: If True (default), flush + fsync per receipt for durability.
        max_bytes: Rotate when file exceeds this size. 0 = no rotation.
        keep_files: Number of rotated files to keep (not counting current).
    """

    def __init__(
        self,
        path: str | Path,
        *,
        fsync: bool = True,
        max_bytes: int = DEFAULT_MAX_BYTES,
        keep_files: int = DEFAULT_KEEP_FILES,
    ) -> None:
        self._path = Path(path)
        self._fsync = fsync
        self._max_bytes = max_bytes
        self._keep_files = keep_files
        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Check existing file permissions
        if self._path.exists():
            _check_permissions(self._path)

    @property
    def path(self) -> Path:
        return self._path

    def write(self, receipt: Receipt) -> None:
        """Append receipt as a single JSON line. Rotate if needed."""
        # Rotate before write if file is too large
        if self._max_bytes > 0 and self._path.exists():
            try:
                size = self._path.stat().st_size
                if size >= self._max_bytes:
                    self._rotate()
            except OSError:
                pass  # stat failed — write anyway

        line = json.dumps(
            receipt.to_dict(), separators=(",", ":"), sort_keys=True
        ) + "\n"
        data = line.encode("utf-8")

        # Open with O_CREAT: if file doesn't exist, create with 0o600.
        # If it does exist, mode arg is ignored (existing perms preserved).
        fd = os.open(
            str(self._path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            _FILE_MODE,
        )
        try:
            os.write(fd, data)
            if self._fsync:
                os.fsync(fd)
        finally:
            os.close(fd)

    def read_all(self) -> list[dict[str, Any]]:
        """Read all receipts from the current file. Returns list of dicts."""
        if not self._path.exists():
            return []
        receipts = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    receipts.append(json.loads(line))
        return receipts

    def _rotate(self) -> None:
        """Rotate files: current → .1, .1 → .2, etc. Delete oldest."""
        # Delete the oldest if at capacity
        oldest = self._path.with_name(f"{self._path.name}.{self._keep_files}")
        if oldest.exists():
            oldest.unlink()

        # Shift existing rotated files up by one
        for i in range(self._keep_files - 1, 0, -1):
            src = self._path.with_name(f"{self._path.name}.{i}")
            dst = self._path.with_name(f"{self._path.name}.{i + 1}")
            if src.exists():
                src.rename(dst)

        # Move current to .1
        dst = self._path.with_name(f"{self._path.name}.1")
        if self._path.exists():
            self._path.rename(dst)
