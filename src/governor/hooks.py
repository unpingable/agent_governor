"""
Git hooks for enforcing governor approval.

The pre-commit hook ensures that file mutations go through the governor workflow.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .fsm import Proposal, ProposalState


# Hook script template - installed to .git/hooks/pre-commit
PRE_COMMIT_HOOK = '''\
#!/bin/sh
# Governor pre-commit hook
# Ensures file changes have been approved through the governor workflow

# Run the governor hook check
exec governor hook pre-commit "$@"
'''


class HookError(Exception):
    """Raised when a hook check fails."""
    pass


def get_git_root(path: Path | None = None) -> Path | None:
    """Find the git repository root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path or Path.cwd(),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None


def get_staged_files(git_root: Path) -> list[str]:
    """Get list of files staged for commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=git_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return files


def load_proposals(gov_dir: Path) -> dict[str, dict]:
    """Load proposals from the governor directory."""
    proposals_path = gov_dir / "proposals.json"
    if not proposals_path.exists():
        return {}
    return json.loads(proposals_path.read_text())


def get_recent_applied_proposals(
    gov_dir: Path,
    max_age_hours: int = 24,
) -> list[Proposal]:
    """Get proposals that were recently applied."""
    proposals_data = load_proposals(gov_dir)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    applied = []
    for data in proposals_data.values():
        proposal = Proposal.from_dict(data)
        if proposal.state == ProposalState.APPLIED:
            if proposal.applied_at and proposal.applied_at > cutoff:
                applied.append(proposal)

    return applied


def get_approved_files(gov_dir: Path, max_age_hours: int = 24) -> set[str]:
    """Get set of file paths that have been approved via governor."""
    proposals = get_recent_applied_proposals(gov_dir, max_age_hours)

    approved = set()
    for proposal in proposals:
        for claim in proposal.claims:
            # File-based claims approve their paths
            if claim.path:
                approved.add(claim.path)
            # Changeset claims approve the touched paths
            if claim.paths:
                approved.update(claim.paths)

    return approved


def check_staged_files(
    git_root: Path,
    gov_dir: Path,
    max_age_hours: int = 24,
) -> tuple[list[str], list[str]]:
    """
    Check if staged files have been approved.

    Returns (approved_files, unapproved_files).
    """
    staged = get_staged_files(git_root)
    approved = get_approved_files(gov_dir, max_age_hours)

    approved_list = []
    unapproved_list = []

    for file in staged:
        if file in approved:
            approved_list.append(file)
        else:
            # Check if the file is in the .governor directory (always allowed)
            if file.startswith(".governor/"):
                approved_list.append(file)
            else:
                unapproved_list.append(file)

    return approved_list, unapproved_list


def _emit_pre_commit_receipt(
    gov_dir: Path,
    verdict: str,
    staged: list[str],
    approved: list[str],
    unapproved: list[str],
) -> None:
    """Emit a gate receipt for the pre-commit check."""
    try:
        from .gate_receipt import GateReceiptSystem
    except ImportError:
        return

    if not gov_dir.exists():
        return

    system = GateReceiptSystem(gov_dir)

    evidence_bundle = {
        "staged_files": staged,
        "approved_files": approved,
        "unapproved_files": unapproved,
    }

    gate_config = {
        "gate": "pre_commit",
    }

    subject_bytes = "\n".join(sorted(staged)).encode("utf-8")

    try:
        system.emit(
            gate="pre_commit",
            verdict=verdict,
            subject_kind="staged_files",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config=gate_config,
        )
    except Exception:
        pass  # fail-open on receipt emission


def run_pre_commit_check(
    git_root: Path | None = None,
    bypass: bool = False,
    max_age_hours: int = 24,
) -> tuple[bool, str]:
    """
    Run the pre-commit check.

    Returns (success, message).
    """
    if bypass:
        return True, "Bypassed governor check (--no-verify)"

    if git_root is None:
        git_root = get_git_root()

    if git_root is None:
        return False, "Not in a git repository"

    gov_dir = git_root / ".governor"
    if not gov_dir.exists():
        # Governor not initialized - allow commits
        return True, "Governor not initialized, allowing commit"

    # Check for bypass file (for emergency commits)
    bypass_file = gov_dir / ".bypass"
    if bypass_file.exists():
        bypass_file.unlink()  # One-time bypass
        return True, "One-time bypass used"

    staged = get_staged_files(git_root)
    if not staged:
        return True, "No files staged"

    approved, unapproved = check_staged_files(git_root, gov_dir, max_age_hours)

    if not unapproved:
        _emit_pre_commit_receipt(gov_dir, "pass", staged, approved, unapproved)
        return True, f"All {len(approved)} file(s) approved by governor"

    # Emit block receipt before returning rejection
    _emit_pre_commit_receipt(gov_dir, "block", staged, approved, unapproved)

    # Build rejection message
    msg_lines = [
        "COMMIT BLOCKED: Files not approved by governor",
        "",
        "Unapproved files:",
    ]
    for f in unapproved[:10]:  # Show first 10
        msg_lines.append(f"  - {f}")
    if len(unapproved) > 10:
        msg_lines.append(f"  ... and {len(unapproved) - 10} more")

    msg_lines.extend([
        "",
        "To commit these changes:",
        "  1. Create a proposal: governor propose --claim 'type=file_exists,path=<file>'",
        "  2. Verify it: governor verify <proposal-id>",
        "  3. Apply it: governor apply <proposal-id>",
        "  4. Then commit",
        "",
        "Or bypass with: git commit --no-verify (not recommended)",
        "Or create bypass: touch .governor/.bypass (one-time)",
    ])

    return False, "\n".join(msg_lines)


def install_hook(git_root: Path) -> tuple[bool, str]:
    """
    Install the pre-commit hook.

    Returns (success, message).
    """
    hooks_dir = git_root / ".git" / "hooks"

    if not hooks_dir.exists():
        return False, f"Git hooks directory not found: {hooks_dir}"

    hook_path = hooks_dir / "pre-commit"

    # Check for existing hook
    if hook_path.exists():
        content = hook_path.read_text()
        if "governor" in content.lower():
            return True, "Governor hook already installed"

        # Back up existing hook
        backup_path = hooks_dir / "pre-commit.backup"
        hook_path.rename(backup_path)
        return_msg = f"Existing hook backed up to {backup_path}"
    else:
        return_msg = ""

    # Write the hook
    hook_path.write_text(PRE_COMMIT_HOOK)
    hook_path.chmod(0o755)  # Make executable

    if return_msg:
        return True, f"Hook installed. {return_msg}"
    return True, "Hook installed successfully"


def uninstall_hook(git_root: Path) -> tuple[bool, str]:
    """
    Uninstall the pre-commit hook.

    Returns (success, message).
    """
    hooks_dir = git_root / ".git" / "hooks"
    hook_path = hooks_dir / "pre-commit"

    if not hook_path.exists():
        return True, "No pre-commit hook to remove"

    content = hook_path.read_text()
    if "governor" not in content.lower():
        return False, "Pre-commit hook is not a governor hook"

    hook_path.unlink()

    # Restore backup if exists
    backup_path = hooks_dir / "pre-commit.backup"
    if backup_path.exists():
        backup_path.rename(hook_path)
        return True, "Hook removed, previous hook restored from backup"

    return True, "Hook removed"


def get_hook_status(git_root: Path) -> dict[str, Any]:
    """Get the current hook status."""
    hooks_dir = git_root / ".git" / "hooks"
    hook_path = hooks_dir / "pre-commit"

    status = {
        "installed": False,
        "is_governor_hook": False,
        "has_backup": False,
        "executable": False,
    }

    if hook_path.exists():
        status["installed"] = True
        content = hook_path.read_text()
        status["is_governor_hook"] = "governor" in content.lower()
        status["executable"] = hook_path.stat().st_mode & 0o111 != 0

    backup_path = hooks_dir / "pre-commit.backup"
    status["has_backup"] = backup_path.exists()

    return status
