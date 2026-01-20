"""
Receipt types: Governor-produced evidence of verification.

Per NLAI: Agents provide pointers, Governor produces receipts.
These are the ONLY valid evidence types. Agents cannot produce these directly.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FileSnapshot:
    """
    Receipt proving file state at verification time.

    Produced by governor when verifying file existence/content claims.
    The blob_hash ensures the receipt is tied to specific file content.
    """
    path: str
    blob_hash: str  # SHA256 of content
    size_bytes: int
    timestamp: datetime
    excerpt_spans: list[tuple[int, int]] | None = None  # line ranges if relevant

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "file_snapshot",
            "path": self.path,
            "blob_hash": self.blob_hash,
            "size_bytes": self.size_bytes,
            "timestamp": self.timestamp.isoformat(),
            "excerpt_spans": self.excerpt_spans,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileSnapshot":
        return cls(
            path=data["path"],
            blob_hash=data["blob_hash"],
            size_bytes=data["size_bytes"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            excerpt_spans=[tuple(span) for span in data["excerpt_spans"]]
                if data.get("excerpt_spans") else None,
        )


@dataclass(frozen=True)
class CmdRun:
    """
    Receipt proving command execution.

    Produced by governor when verifying test/command claims.
    Hashes stdout/stderr rather than storing full output (can be large).
    """
    command: tuple[str, ...]  # immutable for frozen dataclass
    exit_code: int
    stdout_hash: str
    stderr_hash: str
    cwd: str
    duration_ms: int
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "cmd_run",
            "command": list(self.command),
            "exit_code": self.exit_code,
            "stdout_hash": self.stdout_hash,
            "stderr_hash": self.stderr_hash,
            "cwd": self.cwd,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CmdRun":
        return cls(
            command=tuple(data["command"]),
            exit_code=data["exit_code"],
            stdout_hash=data["stdout_hash"],
            stderr_hash=data["stderr_hash"],
            cwd=data["cwd"],
            duration_ms=data["duration_ms"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass(frozen=True)
class DiffReceipt:
    """
    Receipt proving changeset content.

    Produced by governor when verifying proposed patches.
    The base_tree_hash ties the receipt to a specific repo state.
    """
    paths_touched: tuple[str, ...]  # immutable for frozen dataclass
    unified_diff_hash: str
    base_tree_hash: str  # git tree hash before patch
    additions: int
    deletions: int
    timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "diff_receipt",
            "paths_touched": list(self.paths_touched),
            "unified_diff_hash": self.unified_diff_hash,
            "base_tree_hash": self.base_tree_hash,
            "additions": self.additions,
            "deletions": self.deletions,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiffReceipt":
        return cls(
            paths_touched=tuple(data["paths_touched"]),
            unified_diff_hash=data["unified_diff_hash"],
            base_tree_hash=data["base_tree_hash"],
            additions=data["additions"],
            deletions=data["deletions"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


# Type alias for any receipt type
Receipt = FileSnapshot | CmdRun | DiffReceipt


def receipt_from_dict(data: dict[str, Any]) -> Receipt:
    """Deserialize a receipt from its dict representation."""
    receipt_type = data.get("type")
    if receipt_type == "file_snapshot":
        return FileSnapshot.from_dict(data)
    elif receipt_type == "cmd_run":
        return CmdRun.from_dict(data)
    elif receipt_type == "diff_receipt":
        return DiffReceipt.from_dict(data)
    else:
        raise ValueError(f"Unknown receipt type: {receipt_type}")
