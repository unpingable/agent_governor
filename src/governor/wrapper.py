"""
Agent wrapper: Intercepts file writes and routes through governor.

The wrapper monitors file changes made by an agent and ensures they go
through the governor approval workflow before being persisted.

Usage:
    governor wrap -- <agent-command>

Example:
    governor wrap -- claude-code
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .claims import file_exists, changeset, Claim
from .envelopes import get_current_envelope
from .fsm import ProposalFSM, ProposalState, create_proposal, Proposal
from .verifiers import create_default_verifiers


class WrapperError(Exception):
    """Raised when the wrapper encounters an error."""
    pass


class FileChange:
    """Represents a file change detected by the wrapper."""

    def __init__(
        self,
        path: str,
        change_type: str,  # "created", "modified", "deleted"
        old_hash: str | None = None,
        new_hash: str | None = None,
        old_content: bytes | None = None,
        new_content: bytes | None = None,
    ):
        self.path = path
        self.change_type = change_type
        self.old_hash = old_hash
        self.new_hash = new_hash
        self.old_content = old_content
        self.new_content = new_content

    def __repr__(self) -> str:
        return f"FileChange({self.path!r}, {self.change_type!r})"


class DirectorySnapshot:
    """Snapshot of a directory's file state."""

    def __init__(self, root: Path, exclude_patterns: list[str] | None = None):
        self.root = root
        self.exclude_patterns = exclude_patterns or [".git", ".governor", "__pycache__", ".pytest_cache"]
        self.files: dict[str, tuple[str, bytes]] = {}  # path -> (hash, content)
        self._take_snapshot()

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        for pattern in self.exclude_patterns:
            if pattern in path.parts:
                return True
        return False

    def _take_snapshot(self) -> None:
        """Take a snapshot of all files."""
        for file_path in self.root.rglob("*"):
            if file_path.is_file() and not self._should_exclude(file_path.relative_to(self.root)):
                try:
                    content = file_path.read_bytes()
                    file_hash = hashlib.sha256(content).hexdigest()
                    rel_path = str(file_path.relative_to(self.root))
                    self.files[rel_path] = (file_hash, content)
                except (PermissionError, OSError):
                    pass

    def diff(self, other: "DirectorySnapshot") -> list[FileChange]:
        """
        Compare this snapshot to another and return changes.

        Returns changes that would transform `self` into `other`.
        """
        changes = []

        # Find created and modified files
        for path, (new_hash, new_content) in other.files.items():
            if path not in self.files:
                changes.append(FileChange(
                    path=path,
                    change_type="created",
                    new_hash=new_hash,
                    new_content=new_content,
                ))
            else:
                old_hash, old_content = self.files[path]
                if old_hash != new_hash:
                    changes.append(FileChange(
                        path=path,
                        change_type="modified",
                        old_hash=old_hash,
                        new_hash=new_hash,
                        old_content=old_content,
                        new_content=new_content,
                    ))

        # Find deleted files
        for path, (old_hash, old_content) in self.files.items():
            if path not in other.files:
                changes.append(FileChange(
                    path=path,
                    change_type="deleted",
                    old_hash=old_hash,
                    old_content=old_content,
                ))

        return changes


def generate_unified_diff(changes: list[FileChange]) -> str:
    """Generate a unified diff from file changes."""
    diff_lines = []

    for change in changes:
        if change.change_type == "created":
            diff_lines.append("--- /dev/null")
            diff_lines.append(f"+++ b/{change.path}")
            if change.new_content:
                try:
                    content = change.new_content.decode("utf-8")
                    lines = content.splitlines()
                    diff_lines.append(f"@@ -0,0 +1,{len(lines)} @@")
                    for line in lines:
                        diff_lines.append(f"+{line}")
                except UnicodeDecodeError:
                    diff_lines.append("+[binary file]")

        elif change.change_type == "deleted":
            diff_lines.append(f"--- a/{change.path}")
            diff_lines.append("+++ /dev/null")
            if change.old_content:
                try:
                    content = change.old_content.decode("utf-8")
                    lines = content.splitlines()
                    diff_lines.append(f"@@ -1,{len(lines)} +0,0 @@")
                    for line in lines:
                        diff_lines.append(f"-{line}")
                except UnicodeDecodeError:
                    diff_lines.append("-[binary file]")

        elif change.change_type == "modified":
            diff_lines.append(f"--- a/{change.path}")
            diff_lines.append(f"+++ b/{change.path}")
            # Simple diff - show old and new
            if change.old_content and change.new_content:
                try:
                    old_lines = change.old_content.decode("utf-8").splitlines()
                    new_lines = change.new_content.decode("utf-8").splitlines()
                    diff_lines.append(f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@")
                    for line in old_lines:
                        diff_lines.append(f"-{line}")
                    for line in new_lines:
                        diff_lines.append(f"+{line}")
                except UnicodeDecodeError:
                    diff_lines.append("-[binary file]")
                    diff_lines.append("+[binary file]")

    return "\n".join(diff_lines)


def rollback_changes(root: Path, changes: list[FileChange]) -> None:
    """Rollback changes to restore the original state."""
    for change in changes:
        file_path = root / change.path

        if change.change_type == "created":
            # Delete the created file
            if file_path.exists():
                file_path.unlink()
            # Clean up empty parent directories
            parent = file_path.parent
            while parent != root:
                try:
                    parent.rmdir()
                    parent = parent.parent
                except OSError:
                    break

        elif change.change_type == "deleted":
            # Restore the deleted file
            if change.old_content is not None:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(change.old_content)

        elif change.change_type == "modified":
            # Restore the original content
            if change.old_content is not None:
                file_path.write_bytes(change.old_content)


def create_claims_from_changes(changes: list[FileChange]) -> list[Claim]:
    """Create claims from detected file changes."""
    claims = []

    for change in changes:
        if change.change_type in ("created", "modified"):
            claims.append(file_exists(change.path))

    # If we have changes, also create a changeset claim
    if changes:
        diff_text = generate_unified_diff(changes)
        paths = tuple(c.path for c in changes)
        claims.append(changeset(diff_text, paths=paths))

    return claims


class AgentWrapper:
    """
    Wrapper for running agents with governor enforcement.

    Monitors file changes made by the agent and ensures they go
    through the governor approval workflow.
    """

    def __init__(
        self,
        root: Path,
        gov_dir: Path,
        auto_approve: bool = False,
        on_changes: Callable[[list[FileChange]], bool] | None = None,
    ):
        """
        Initialize the wrapper.

        Args:
            root: The project root directory
            gov_dir: The governor directory
            auto_approve: If True, automatically approve changes in exploratory mode
            on_changes: Optional callback when changes are detected.
                       Return True to approve, False to reject.
        """
        self.root = root
        self.gov_dir = gov_dir
        self.auto_approve = auto_approve
        self.on_changes = on_changes

    def run(self, command: list[str], env: dict[str, str] | None = None) -> tuple[int, list[FileChange]]:
        """
        Run an agent command and track file changes.

        Returns (exit_code, changes).
        """
        # Take snapshot before
        before = DirectorySnapshot(self.root)

        # Run the command
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        # Set environment variable to indicate we're in a wrapper
        merged_env["GOVERNOR_WRAPPED"] = "1"

        result = subprocess.run(
            command,
            cwd=self.root,
            env=merged_env,
        )

        # Take snapshot after
        after = DirectorySnapshot(self.root)

        # Detect changes
        changes = before.diff(after)

        return result.returncode, changes

    def _emit_receipt(
        self,
        verdict: str,
        changes: list[FileChange],
        command: list[str],
    ) -> None:
        """Emit a gate receipt for wrapper enforcement."""
        try:
            from .gate_receipt import GateReceiptSystem
        except ImportError:
            return

        if not self.gov_dir.exists():
            return

        system = GateReceiptSystem(self.gov_dir)

        evidence_bundle = {
            "changes": [
                {"path": c.path, "type": c.change_type}
                for c in changes
            ],
            "command": command[:5],  # Truncate to avoid huge receipts
        }

        gate_config = {
            "gate": "wrapper",
            "auto_approve": self.auto_approve,
        }

        subject_bytes = "\n".join(
            sorted(c.path for c in changes)
        ).encode("utf-8")

        try:
            system.emit(
                gate="wrapper",
                verdict=verdict,
                subject_kind="file_changes",
                subject_bytes=subject_bytes,
                evidence_bundle=evidence_bundle,
                gate_config=gate_config,
            )
        except Exception:
            pass  # fail-open on receipt emission

    def run_with_enforcement(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        """
        Run an agent command with governor enforcement.

        Returns (exit_code, message).
        """
        exit_code, changes = self.run(command, env)

        if not changes:
            return exit_code, "No file changes detected"

        # Get current envelope
        envelope = get_current_envelope(self.gov_dir)

        # Check if we should auto-approve
        should_approve = False
        if self.auto_approve and not envelope.require_receipts:
            should_approve = True
        elif self.on_changes:
            should_approve = self.on_changes(changes)

        if should_approve:
            # Create and auto-apply proposal
            claims = create_claims_from_changes(changes)
            fsm = create_proposal(claims)
            fsm.propose()

            # Verify
            verifier = create_default_verifiers(self.root)
            results = verifier.verify_all(claims)

            receipts = [r.receipt for r in results if r.success]
            if receipts or not envelope.require_receipts:
                # Use stub receipts if in exploratory mode
                if not receipts:
                    from .receipts import FileSnapshot
                    receipts = [
                        FileSnapshot(
                            path="wrapper:auto",
                            blob_hash="auto",
                            size_bytes=0,
                            timestamp=datetime.now(timezone.utc),
                        )
                    ]
                fsm.verify(receipts)
                fsm.apply()

                # Save proposal
                self._save_proposal(fsm.proposal)

                self._emit_receipt("pass", changes, command)
                return exit_code, f"Approved {len(changes)} file change(s)"

        # Not approved - rollback
        rollback_changes(self.root, changes)
        self._emit_receipt("block", changes, command)
        return 1, f"Blocked {len(changes)} file change(s) - not approved by governor"

    def _save_proposal(self, proposal: Proposal) -> None:
        """Save a proposal to the proposals file."""
        proposals_path = self.gov_dir / "proposals.json"
        if proposals_path.exists():
            proposals = json.loads(proposals_path.read_text())
        else:
            proposals = {}

        proposals[str(proposal.id)] = proposal.to_dict()
        proposals_path.write_text(json.dumps(proposals, indent=2))


def wrap_agent(
    command: list[str],
    root: Path | None = None,
    auto_approve: bool = False,
) -> tuple[int, str]:
    """
    Wrap an agent command with governor enforcement.

    Args:
        command: The command to run
        root: The project root (defaults to cwd)
        auto_approve: If True, auto-approve in exploratory mode

    Returns:
        (exit_code, message)
    """
    if root is None:
        root = Path.cwd()

    gov_dir = root / ".governor"

    if not gov_dir.exists():
        # Run without enforcement if governor not initialized
        result = subprocess.run(command, cwd=root)
        return result.returncode, "Governor not initialized, ran without enforcement"

    wrapper = AgentWrapper(root, gov_dir, auto_approve=auto_approve)
    return wrapper.run_with_enforcement(command)
