"""
Receipt-producing verifiers.

Per NLAI: Agents provide pointers, Governor produces receipts.
Verifiers take claims and produce receipts if verification succeeds.

This replaces the v0.1 validators.py with proper receipt-based verification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .claims import Claim, ClaimType
from .producers import (
    produce_file_snapshot,
    produce_cmd_run,
    produce_diff_receipt,
)
from .receipts import Receipt, FileSnapshot, CmdRun, DiffReceipt


@dataclass
class VerificationResult:
    """Result of verifying a claim."""

    success: bool
    receipt: Receipt | None = None
    error: str | None = None

    @classmethod
    def ok(cls, receipt: Receipt) -> "VerificationResult":
        """Create a successful result."""
        return cls(success=True, receipt=receipt)

    @classmethod
    def fail(cls, error: str) -> "VerificationResult":
        """Create a failed result."""
        return cls(success=False, error=error)


class Verifier(ABC):
    """Base class for claim verifiers."""

    @abstractmethod
    def can_verify(self, claim: Claim) -> bool:
        """Check if this verifier can handle the given claim type."""
        pass

    @abstractmethod
    def verify(self, claim: Claim) -> VerificationResult:
        """
        Verify a claim and produce a receipt if successful.

        Returns VerificationResult with receipt on success, or error on failure.
        """
        pass


class FileVerifier(Verifier):
    """
    Verifies FILE_EXISTS and SYMBOL_DEFINED claims.

    Produces FileSnapshot receipts.
    """

    def __init__(self, base_path: Path | str):
        self.base_path = Path(base_path)

    def can_verify(self, claim: Claim) -> bool:
        """Can verify file-related claims."""
        return claim.type in (ClaimType.FILE_EXISTS, ClaimType.SYMBOL_DEFINED)

    def verify(self, claim: Claim) -> VerificationResult:
        """Verify file exists and optionally contains symbol."""
        if claim.path is None:
            return VerificationResult.fail("Claim has no path")

        try:
            snapshot = produce_file_snapshot(
                claim.path,
                base_path=self.base_path,
                excerpt_spans=claim.span and [claim.span],
            )
        except FileNotFoundError:
            return VerificationResult.fail(f"File not found: {claim.path}")
        except IsADirectoryError:
            return VerificationResult.fail(f"Path is a directory: {claim.path}")
        except PermissionError:
            return VerificationResult.fail(f"Permission denied: {claim.path}")

        # For SYMBOL_DEFINED, check the symbol exists in the file
        if claim.type == ClaimType.SYMBOL_DEFINED and claim.symbol:
            full_path = self.base_path / claim.path
            try:
                content = full_path.read_text()
                if claim.symbol not in content:
                    return VerificationResult.fail(
                        f"Symbol '{claim.symbol}' not found in {claim.path}"
                    )
            except Exception as e:
                return VerificationResult.fail(f"Error reading file: {e}")

        return VerificationResult.ok(snapshot)


class CommandVerifier(Verifier):
    """
    Verifies TESTS_PASS claims by running the test command.

    Produces CmdRun receipts.
    """

    def __init__(
        self,
        base_path: Path | str,
        timeout: int = 300,
        require_exit_zero: bool = True,
    ):
        self.base_path = Path(base_path)
        self.timeout = timeout
        self.require_exit_zero = require_exit_zero

    def can_verify(self, claim: Claim) -> bool:
        """Can verify test claims."""
        return claim.type == ClaimType.TESTS_PASS

    def verify(self, claim: Claim) -> VerificationResult:
        """Run tests and verify they pass."""
        if claim.command is None:
            return VerificationResult.fail("TESTS_PASS claim has no command")

        try:
            cmd_run = produce_cmd_run(
                command=claim.command,
                cwd=self.base_path,
                timeout=self.timeout,
            )
        except FileNotFoundError:
            cmd_name = claim.command[0] if claim.command else "unknown"
            return VerificationResult.fail(f"Command not found: {cmd_name}")
        except Exception as e:
            if "TimeoutExpired" in type(e).__name__:
                return VerificationResult.fail(
                    f"Command timed out after {self.timeout}s"
                )
            return VerificationResult.fail(f"Command execution failed: {e}")

        if self.require_exit_zero and cmd_run.exit_code != 0:
            return VerificationResult.fail(
                f"Tests failed with exit code {cmd_run.exit_code}"
            )

        return VerificationResult.ok(cmd_run)


class DiffVerifier(Verifier):
    """
    Verifies CHANGESET claims by checking the diff is valid.

    Produces DiffReceipt receipts.
    """

    def __init__(self, base_path: Path | str):
        self.base_path = Path(base_path)

    def can_verify(self, claim: Claim) -> bool:
        """Can verify changeset claims."""
        return claim.type == ClaimType.CHANGESET

    def verify(self, claim: Claim) -> VerificationResult:
        """Verify the diff is valid and can be applied."""
        if claim.diff is None:
            return VerificationResult.fail("CHANGESET claim has no diff")

        if not claim.diff.strip():
            return VerificationResult.fail("Diff is empty")

        try:
            diff_receipt = produce_diff_receipt(
                patch_text=claim.diff,
                repo_root=self.base_path,
            )
        except Exception as e:
            return VerificationResult.fail(f"Error processing diff: {e}")

        # Basic validation: diff should touch at least one file
        # (unless it's a deletion-only diff)
        if not diff_receipt.paths_touched and diff_receipt.deletions == 0:
            return VerificationResult.fail("Diff touches no files")

        return VerificationResult.ok(diff_receipt)


class DecisionVerifier(Verifier):
    """
    Verifies DECISION claims.

    Decisions are normative (policy choices), not empirical, so verification
    always succeeds. This verifier exists to handle decision claims in the
    pipeline. Returns a stub FileSnapshot receipt.
    """

    def can_verify(self, claim: Claim) -> bool:
        """Can verify decision claims."""
        return claim.type == ClaimType.DECISION

    def verify(self, claim: Claim) -> VerificationResult:
        """Decisions always pass - they're normative choices, not facts."""
        from datetime import datetime, timezone

        # Create a stub receipt to satisfy the FSM
        # Decisions don't have real receipts - they're policy, not evidence
        stub_receipt = FileSnapshot(
            path=f"decision:{claim.topic}",
            blob_hash="decision",
            size_bytes=0,
            timestamp=datetime.now(timezone.utc),
        )
        return VerificationResult.ok(stub_receipt)


class ApiVerifier(Verifier):
    """
    Verifies API_SURFACE claims by checking file contains the API definition.

    Produces FileSnapshot receipts.
    """

    def __init__(self, base_path: Path | str):
        self.base_path = Path(base_path)

    def can_verify(self, claim: Claim) -> bool:
        """Can verify API claims."""
        return claim.type == ClaimType.API_SURFACE

    def verify(self, claim: Claim) -> VerificationResult:
        """Verify API is defined in the file."""
        if claim.path is None:
            return VerificationResult.fail("API_SURFACE claim has no path")

        if claim.symbol is None:
            return VerificationResult.fail("API_SURFACE claim has no symbol")

        full_path = self.base_path / claim.path

        if not full_path.exists():
            return VerificationResult.fail(f"File not found: {claim.path}")

        try:
            content = full_path.read_text()
        except Exception as e:
            return VerificationResult.fail(f"Error reading file: {e}")

        # Check if the API symbol/pattern exists in the file
        if claim.symbol not in content:
            return VerificationResult.fail(
                f"API '{claim.symbol}' not found in {claim.path}"
            )

        try:
            snapshot = produce_file_snapshot(
                claim.path,
                base_path=self.base_path,
                excerpt_spans=claim.span and [claim.span],
            )
        except Exception as e:
            return VerificationResult.fail(f"Error producing snapshot: {e}")

        return VerificationResult.ok(snapshot)


class CompositeVerifier(Verifier):
    """
    Combines multiple verifiers, delegating to the appropriate one.
    """

    def __init__(self, verifiers: list[Verifier]):
        self.verifiers = verifiers

    def can_verify(self, claim: Claim) -> bool:
        """Check if any verifier can handle the claim."""
        return any(v.can_verify(claim) for v in self.verifiers)

    def verify(self, claim: Claim) -> VerificationResult:
        """Delegate to the first verifier that can handle the claim."""
        for verifier in self.verifiers:
            if verifier.can_verify(claim):
                return verifier.verify(claim)

        return VerificationResult.fail(
            f"No verifier available for claim type: {claim.type.value}"
        )

    def verify_all(self, claims: list[Claim]) -> list[VerificationResult]:
        """Verify multiple claims, returning results for each."""
        return [self.verify(claim) for claim in claims]


def create_default_verifiers(base_path: Path | str) -> CompositeVerifier:
    """
    Create a CompositeVerifier with all default verifiers.

    Args:
        base_path: The project root path.

    Returns:
        A CompositeVerifier configured with all verifier types.
    """
    return CompositeVerifier([
        FileVerifier(base_path),
        CommandVerifier(base_path),
        DiffVerifier(base_path),
        ApiVerifier(base_path),
        DecisionVerifier(),
    ])
