"""
Invariants: Mechanically verifiable rules for autonomous execution.

Key insight: if you can't verify it mechanically, it's a guideline, not an invariant.
Invariants are hard gates — they produce receipts, not opinions.

Phase A1: Core types and invariant library.
Phase A2: Integration with autonomous executor (future).
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
import json
import subprocess


class InvariantType(str, Enum):
    """Categories of mechanically verifiable invariants."""

    STRUCTURE = "structure"        # File/directory structure
    EVIDENCE = "evidence"          # Claims must have evidence
    ARCHITECTURE = "architecture"  # Component boundaries
    TEST = "test"                  # Tests must pass
    CONSISTENCY = "consistency"    # No contradictions
    FORBIDDEN = "forbidden"        # Forbidden operations


@dataclass
class InvariantResult:
    """Result of checking a single invariant."""

    passed: bool
    message: str
    invariant_id: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "message": self.message,
            "invariant_id": self.invariant_id,
            "details": self.details,
        }


@dataclass
class Invariant:
    """
    A mechanically verifiable rule.

    The `verify` callable takes keyword arguments and returns an InvariantResult.
    What it checks depends on the invariant type.
    """

    id: str
    type: InvariantType
    rule: str  # Human-readable description
    verify: Callable[..., InvariantResult]
    on_violation: str = "block"  # "block" | "warn"
    enabled: bool = True

    def check(self, **kwargs: Any) -> InvariantResult:
        """Run the invariant check."""
        if not self.enabled:
            return InvariantResult(
                passed=True,
                message=f"Invariant '{self.id}' is disabled",
                invariant_id=self.id,
            )
        return self.verify(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "rule": self.rule,
            "on_violation": self.on_violation,
            "enabled": self.enabled,
        }


@dataclass
class InvariantSet:
    """A collection of invariants to check together."""

    invariants: list[Invariant] = field(default_factory=list)

    def add(self, invariant: Invariant) -> None:
        self.invariants.append(invariant)

    def remove(self, invariant_id: str) -> bool:
        before = len(self.invariants)
        self.invariants = [i for i in self.invariants if i.id != invariant_id]
        return len(self.invariants) < before

    def get(self, invariant_id: str) -> Invariant | None:
        for i in self.invariants:
            if i.id == invariant_id:
                return i
        return None

    def check_all(self, **kwargs: Any) -> list[InvariantResult]:
        """Check all invariants. Returns list of results."""
        return [inv.check(**kwargs) for inv in self.invariants if inv.enabled]

    def blocking_violations(self, **kwargs: Any) -> list[InvariantResult]:
        """Check all invariants, return only blocking failures."""
        results = self.check_all(**kwargs)
        blocking = []
        for result in results:
            if not result.passed:
                inv = self.get(result.invariant_id)
                if inv and inv.on_violation == "block":
                    blocking.append(result)
        return blocking

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariants": [i.to_dict() for i in self.invariants],
        }


# =============================================================================
# Built-in Invariant Library
# =============================================================================


class InvariantLibrary:
    """Factory methods for common invariants."""

    @staticmethod
    def tests_must_pass(
        command: str = "pytest",
        args: list[str] | None = None,
        cwd: Path | None = None,
        invariant_id: str = "tests_must_pass",
    ) -> Invariant:
        """Tests must pass (exit code 0)."""
        cmd_args = args or []

        def verify(**kwargs: Any) -> InvariantResult:
            try:
                result = subprocess.run(
                    [command] + cmd_args,
                    capture_output=True,
                    text=True,
                    cwd=str(cwd) if cwd else None,
                    timeout=300,
                )
                if result.returncode == 0:
                    return InvariantResult(
                        passed=True,
                        message="Tests passed",
                        invariant_id=invariant_id,
                        details={"returncode": 0},
                    )
                return InvariantResult(
                    passed=False,
                    message=f"Tests failed (exit code {result.returncode})",
                    invariant_id=invariant_id,
                    details={
                        "returncode": result.returncode,
                        "stdout_tail": result.stdout[-500:] if result.stdout else "",
                        "stderr_tail": result.stderr[-500:] if result.stderr else "",
                    },
                )
            except FileNotFoundError:
                return InvariantResult(
                    passed=False,
                    message=f"Test command not found: {command}",
                    invariant_id=invariant_id,
                )
            except subprocess.TimeoutExpired:
                return InvariantResult(
                    passed=False,
                    message=f"Tests timed out after 300s",
                    invariant_id=invariant_id,
                )

        return Invariant(
            id=invariant_id,
            type=InvariantType.TEST,
            rule=f"Command '{command} {' '.join(cmd_args)}' must exit 0",
            verify=verify,
        )

    @staticmethod
    def file_must_exist(
        path: str,
        invariant_id: str | None = None,
    ) -> Invariant:
        """A specific file must exist."""
        inv_id = invariant_id or f"file_exists_{path.replace('/', '_')}"

        def verify(**kwargs: Any) -> InvariantResult:
            root = kwargs.get("root", Path("."))
            full_path = root / path
            if full_path.exists():
                return InvariantResult(
                    passed=True,
                    message=f"File exists: {path}",
                    invariant_id=inv_id,
                )
            return InvariantResult(
                passed=False,
                message=f"Required file missing: {path}",
                invariant_id=inv_id,
                details={"path": path},
            )

        return Invariant(
            id=inv_id,
            type=InvariantType.STRUCTURE,
            rule=f"File '{path}' must exist",
            verify=verify,
        )

    @staticmethod
    def directory_must_exist(
        path: str,
        invariant_id: str | None = None,
    ) -> Invariant:
        """A specific directory must exist."""
        inv_id = invariant_id or f"dir_exists_{path.replace('/', '_')}"

        def verify(**kwargs: Any) -> InvariantResult:
            root = kwargs.get("root", Path("."))
            full_path = root / path
            if full_path.is_dir():
                return InvariantResult(
                    passed=True,
                    message=f"Directory exists: {path}",
                    invariant_id=inv_id,
                )
            return InvariantResult(
                passed=False,
                message=f"Required directory missing: {path}",
                invariant_id=inv_id,
                details={"path": path},
            )

        return Invariant(
            id=inv_id,
            type=InvariantType.STRUCTURE,
            rule=f"Directory '{path}' must exist",
            verify=verify,
        )

    @staticmethod
    def forbidden_pattern(
        pattern: str,
        description: str = "",
        invariant_id: str | None = None,
    ) -> Invariant:
        """Files matching a pattern must not be created/modified."""
        inv_id = invariant_id or f"forbidden_{pattern.replace('*', 'star').replace('/', '_')}"

        def verify(**kwargs: Any) -> InvariantResult:
            import re as _re
            files = kwargs.get("files_touched", [])
            # Convert glob to regex
            regex_str = pattern.replace(".", r"\.").replace("*", ".*").replace("?", ".")
            regex = _re.compile(f"^{regex_str}$")
            matches = [f for f in files if regex.match(f)]
            if matches:
                return InvariantResult(
                    passed=False,
                    message=f"Forbidden files touched: {', '.join(matches)}",
                    invariant_id=inv_id,
                    details={"pattern": pattern, "matches": matches},
                )
            return InvariantResult(
                passed=True,
                message=f"No forbidden files touched",
                invariant_id=inv_id,
            )

        return Invariant(
            id=inv_id,
            type=InvariantType.FORBIDDEN,
            rule=description or f"Files matching '{pattern}' must not be touched",
            verify=verify,
        )

    @staticmethod
    def no_secrets(
        invariant_id: str = "no_secrets",
    ) -> Invariant:
        """No files that look like secrets."""
        secret_patterns = [
            ".env", ".env.*", "*.pem", "*.key", "*.secret",
            "credentials.*", "secrets.*", "*password*",
        ]

        def verify(**kwargs: Any) -> InvariantResult:
            import re as _re
            files = kwargs.get("files_touched", [])
            violations = []
            for pattern in secret_patterns:
                regex_str = pattern.replace(".", r"\.").replace("*", ".*")
                regex = _re.compile(f"^(.*/)?{regex_str}$")
                for f in files:
                    if regex.match(f):
                        violations.append(f)
            if violations:
                return InvariantResult(
                    passed=False,
                    message=f"Potential secrets detected: {', '.join(violations)}",
                    invariant_id=invariant_id,
                    details={"violations": violations},
                )
            return InvariantResult(
                passed=True,
                message="No secrets detected",
                invariant_id=invariant_id,
            )

        return Invariant(
            id=invariant_id,
            type=InvariantType.FORBIDDEN,
            rule="No secret/credential files may be created or modified",
            verify=verify,
        )

    @staticmethod
    def max_file_size(
        max_kb: int = 500,
        invariant_id: str = "max_file_size",
    ) -> Invariant:
        """No file should exceed a size limit."""

        def verify(**kwargs: Any) -> InvariantResult:
            root = kwargs.get("root", Path("."))
            files = kwargs.get("files_touched", [])
            violations = []
            for f in files:
                full_path = root / f
                if full_path.exists():
                    size_kb = full_path.stat().st_size / 1024
                    if size_kb > max_kb:
                        violations.append(f"{f} ({size_kb:.0f}KB)")
            if violations:
                return InvariantResult(
                    passed=False,
                    message=f"Files exceed {max_kb}KB: {', '.join(violations)}",
                    invariant_id=invariant_id,
                    details={"max_kb": max_kb, "violations": violations},
                )
            return InvariantResult(
                passed=True,
                message=f"All files under {max_kb}KB",
                invariant_id=invariant_id,
            )

        return Invariant(
            id=invariant_id,
            type=InvariantType.STRUCTURE,
            rule=f"No file may exceed {max_kb}KB",
            verify=verify,
        )
