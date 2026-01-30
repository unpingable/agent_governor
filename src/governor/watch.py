"""
Watch mode for continuous file monitoring and verification.

Monitors a directory for changes and automatically verifies them
against governor rules.
"""

import hashlib
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .security import SecurityVerifier, SecurityFinding, SecurityConfig


@dataclass
class FileState:
    """Cached state of a file."""

    path: str
    mtime: float
    size: int
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "mtime": self.mtime,
            "size": self.size,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileState":
        return cls(
            path=data["path"],
            mtime=data["mtime"],
            size=data["size"],
            content_hash=data["content_hash"],
        )

    @classmethod
    def from_file(cls, file_path: Path) -> "FileState":
        """Create file state from actual file."""
        stat = file_path.stat()
        content = file_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()[:16]

        return cls(
            path=str(file_path),
            mtime=stat.st_mtime,
            size=stat.st_size,
            content_hash=content_hash,
        )


@dataclass
class FileChange:
    """A detected file change."""

    path: str
    change_type: str  # "created", "modified", "deleted"
    old_state: FileState | None = None
    new_state: FileState | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "old_state": self.old_state.to_dict() if self.old_state else None,
            "new_state": self.new_state.to_dict() if self.new_state else None,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class WatchEvent:
    """An event from the watcher."""

    event_type: str  # "change", "security", "error", "status"
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


@dataclass
class WatchConfig:
    """Configuration for the file watcher."""

    # Directories/patterns to watch
    watch_patterns: list[str] = field(default_factory=lambda: ["**/*.py", "**/*.js", "**/*.ts"])

    # Directories/patterns to ignore
    ignore_patterns: list[str] = field(default_factory=lambda: [
        ".git", ".governor", "__pycache__", "node_modules", ".venv", "venv",
        "*.pyc", "*.pyo", ".DS_Store", "*.swp", "*.swo",
    ])

    # Polling interval in seconds
    poll_interval: float = 1.0

    # Enable security scanning
    security_scan: bool = True

    # Security config
    security_config: SecurityConfig = field(default_factory=SecurityConfig)

    # Callbacks
    on_change: Callable[[FileChange], None] | None = None
    on_security_finding: Callable[[SecurityFinding], None] | None = None
    on_event: Callable[[WatchEvent], None] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "watch_patterns": self.watch_patterns,
            "ignore_patterns": self.ignore_patterns,
            "poll_interval": self.poll_interval,
            "security_scan": self.security_scan,
            "security_config": self.security_config.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WatchConfig":
        security_config = SecurityConfig.from_dict(data.get("security_config", {}))
        return cls(
            watch_patterns=data.get("watch_patterns", ["**/*.py", "**/*.js", "**/*.ts"]),
            ignore_patterns=data.get("ignore_patterns", []),
            poll_interval=data.get("poll_interval", 1.0),
            security_scan=data.get("security_scan", True),
            security_config=security_config,
        )


class FileWatcher:
    """
    Watches a directory for file changes.

    Uses polling for cross-platform compatibility.
    """

    def __init__(
        self,
        root_dir: Path,
        config: WatchConfig | None = None,
    ):
        self.root_dir = root_dir.resolve()
        self.config = config or WatchConfig()

        self._file_states: dict[str, FileState] = {}
        self._running = False
        self._security_verifier: SecurityVerifier | None = None

        if self.config.security_scan:
            self._security_verifier = SecurityVerifier(self.config.security_config)

    def _should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        str_path = str(path)
        rel_path = str(path.relative_to(self.root_dir)) if path.is_relative_to(self.root_dir) else str_path

        for pattern in self.config.ignore_patterns:
            # Simple glob-like matching
            if pattern.startswith("*"):
                if rel_path.endswith(pattern[1:]):
                    return True
            elif pattern in str_path or pattern in rel_path:
                return True

        return False

    def _matches_watch_pattern(self, path: Path) -> bool:
        """Check if a path matches watch patterns."""
        if not self.config.watch_patterns:
            return True

        rel_path = str(path.relative_to(self.root_dir)) if path.is_relative_to(self.root_dir) else str(path)

        for pattern in self.config.watch_patterns:
            # Simple suffix matching for **/*.ext patterns
            if pattern.startswith("**/*."):
                ext = pattern[4:]
                if rel_path.endswith(ext):
                    return True
            elif pattern.endswith("*"):
                prefix = pattern[:-1]
                if rel_path.startswith(prefix):
                    return True
            elif pattern in rel_path:
                return True

        return False

    def _get_watchable_files(self) -> list[Path]:
        """Get all files that should be watched."""
        files = []

        for file_path in self.root_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if self._should_ignore(file_path):
                continue
            if not self._matches_watch_pattern(file_path):
                continue
            files.append(file_path)

        return files

    def _emit_event(self, event: WatchEvent) -> None:
        """Emit a watch event."""
        if self.config.on_event:
            self.config.on_event(event)

    def _scan_for_changes(self) -> list[FileChange]:
        """Scan for file changes since last check."""
        changes: list[FileChange] = []
        current_files: dict[str, FileState] = {}

        # Check all watchable files
        for file_path in self._get_watchable_files():
            str_path = str(file_path)
            try:
                new_state = FileState.from_file(file_path)
                current_files[str_path] = new_state

                old_state = self._file_states.get(str_path)

                if old_state is None:
                    # New file
                    changes.append(FileChange(
                        path=str_path,
                        change_type="created",
                        new_state=new_state,
                    ))
                elif old_state.content_hash != new_state.content_hash:
                    # Modified file
                    changes.append(FileChange(
                        path=str_path,
                        change_type="modified",
                        old_state=old_state,
                        new_state=new_state,
                    ))
            except Exception:
                # File may have been deleted or inaccessible
                pass

        # Check for deleted files
        for str_path, old_state in self._file_states.items():
            if str_path not in current_files:
                changes.append(FileChange(
                    path=str_path,
                    change_type="deleted",
                    old_state=old_state,
                ))

        # Update state
        self._file_states = current_files

        return changes

    def _process_change(self, change: FileChange) -> list[SecurityFinding]:
        """Process a file change and return any security findings."""
        findings: list[SecurityFinding] = []

        # Notify callback
        if self.config.on_change:
            self.config.on_change(change)

        # Security scan for created/modified files
        if self._security_verifier and change.change_type in ("created", "modified"):
            try:
                file_path = Path(change.path)
                findings = self._security_verifier.scan_file(file_path)

                for finding in findings:
                    if self.config.on_security_finding:
                        self.config.on_security_finding(finding)
            except Exception:
                pass

        return findings

    def initialize(self) -> None:
        """Initialize watcher by scanning current state."""
        self._file_states = {}

        for file_path in self._get_watchable_files():
            try:
                state = FileState.from_file(file_path)
                self._file_states[str(file_path)] = state
            except Exception:
                pass

        self._emit_event(WatchEvent(
            event_type="status",
            message=f"Initialized watcher with {len(self._file_states)} files",
            data={"file_count": len(self._file_states)},
        ))

    def check_once(self) -> tuple[list[FileChange], list[SecurityFinding]]:
        """Check for changes once and return results."""
        all_changes: list[FileChange] = []
        all_findings: list[SecurityFinding] = []

        changes = self._scan_for_changes()
        for change in changes:
            all_changes.append(change)
            findings = self._process_change(change)
            all_findings.extend(findings)

        return all_changes, all_findings

    def run(self) -> None:
        """Run the watcher continuously."""
        self._running = True

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum: int, frame: Any) -> None:
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self._emit_event(WatchEvent(
            event_type="status",
            message="Watcher started",
            data={"root_dir": str(self.root_dir)},
        ))

        while self._running:
            try:
                changes, findings = self.check_once()

                # Emit events for changes
                for change in changes:
                    self._emit_event(WatchEvent(
                        event_type="change",
                        message=f"{change.change_type}: {change.path}",
                        data=change.to_dict(),
                    ))

                # Emit events for findings
                for finding in findings:
                    self._emit_event(WatchEvent(
                        event_type="security",
                        message=f"{finding.severity.value}: {finding.message}",
                        data=finding.to_dict(),
                    ))

                time.sleep(self.config.poll_interval)

            except Exception as e:
                self._emit_event(WatchEvent(
                    event_type="error",
                    message=str(e),
                ))
                time.sleep(self.config.poll_interval)

        self._emit_event(WatchEvent(
            event_type="status",
            message="Watcher stopped",
        ))

    def stop(self) -> None:
        """Stop the watcher."""
        self._running = False


class WatchSession:
    """
    A watch session that tracks changes over time.

    Useful for aggregating changes during a development session.
    """

    def __init__(self, root_dir: Path, config: WatchConfig | None = None):
        self.root_dir = root_dir
        self.config = config or WatchConfig()
        self.watcher = FileWatcher(root_dir, self.config)

        self._changes: list[FileChange] = []
        self._findings: list[SecurityFinding] = []
        self._events: list[WatchEvent] = []
        self._start_time: datetime | None = None

    def start(self) -> None:
        """Start the watch session."""
        self._start_time = datetime.now(timezone.utc)
        self._changes = []
        self._findings = []
        self._events = []

        # Set up callbacks
        self.config.on_change = lambda c: self._changes.append(c)
        self.config.on_security_finding = lambda f: self._findings.append(f)
        self.config.on_event = lambda e: self._events.append(e)

        self.watcher.initialize()

    def check(self) -> tuple[list[FileChange], list[SecurityFinding]]:
        """Check for changes."""
        return self.watcher.check_once()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the session."""
        return {
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "duration_seconds": (datetime.now(timezone.utc) - self._start_time).total_seconds() if self._start_time else 0,
            "total_changes": len(self._changes),
            "changes_by_type": {
                "created": sum(1 for c in self._changes if c.change_type == "created"),
                "modified": sum(1 for c in self._changes if c.change_type == "modified"),
                "deleted": sum(1 for c in self._changes if c.change_type == "deleted"),
            },
            "total_findings": len(self._findings),
            "findings_by_severity": {
                "critical": sum(1 for f in self._findings if f.severity.value == "critical"),
                "high": sum(1 for f in self._findings if f.severity.value == "high"),
                "medium": sum(1 for f in self._findings if f.severity.value == "medium"),
                "low": sum(1 for f in self._findings if f.severity.value == "low"),
            },
            "files_changed": list(set(c.path for c in self._changes)),
        }

    @property
    def changes(self) -> list[FileChange]:
        return self._changes

    @property
    def findings(self) -> list[SecurityFinding]:
        return self._findings

    @property
    def events(self) -> list[WatchEvent]:
        return self._events


def create_default_watcher(root_dir: Path) -> FileWatcher:
    """Create a watcher with default configuration."""
    return FileWatcher(root_dir)


def watch_directory(
    root_dir: Path,
    callback: Callable[[WatchEvent], None] | None = None,
    poll_interval: float = 1.0,
) -> None:
    """
    Watch a directory for changes.

    Blocks until interrupted.
    """
    config = WatchConfig(
        poll_interval=poll_interval,
        on_event=callback,
    )
    watcher = FileWatcher(root_dir, config)
    watcher.initialize()
    watcher.run()
