"""
Typed claims: Structured vocabulary for agent assertions.

Per NLAI: Stop letting agents make prose assertions. Define the vocabulary.
Claims are structured and machine-checkable, not free-form strings.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ClaimType(Enum):
    """
    Enumeration of valid claim types.

    Each type has specific required fields and semantics.
    If a claim doesn't fit these types, add a new type to the enum first.
    """

    FILE_EXISTS = "file_exists"
    """Claim that a file exists at a path. Requires: path"""

    SYMBOL_DEFINED = "symbol_defined"
    """Claim that a symbol is defined at a location. Requires: path, symbol. Optional: span"""

    API_SURFACE = "api_surface"
    """Claim about an API endpoint or signature. Requires: path, symbol"""

    TESTS_PASS = "tests_pass"
    """Claim that tests pass. Requires: command"""

    DECISION = "decision"
    """Normative choice (framework, style, etc). Requires: topic, choice"""

    CHANGESET = "changeset"
    """Proposed file mutations. Requires: diff"""


# Define required fields for each claim type
_REQUIRED_FIELDS: dict[ClaimType, set[str]] = {
    ClaimType.FILE_EXISTS: {"path"},
    ClaimType.SYMBOL_DEFINED: {"path", "symbol"},
    ClaimType.API_SURFACE: {"path", "symbol"},
    ClaimType.TESTS_PASS: {"command"},
    ClaimType.DECISION: {"topic", "choice"},
    ClaimType.CHANGESET: {"diff"},
}

# Define optional fields for each claim type
_OPTIONAL_FIELDS: dict[ClaimType, set[str]] = {
    ClaimType.FILE_EXISTS: {"span"},
    ClaimType.SYMBOL_DEFINED: {"span"},
    ClaimType.API_SURFACE: {"span"},
    ClaimType.TESTS_PASS: set(),
    ClaimType.DECISION: set(),
    ClaimType.CHANGESET: {"paths"},  # Optional list of affected paths
}


class ClaimValidationError(ValueError):
    """Raised when a claim fails validation."""

    def __init__(self, claim_type: ClaimType, message: str):
        self.claim_type = claim_type
        super().__init__(f"Invalid {claim_type.value} claim: {message}")


@dataclass(frozen=True)
class Claim:
    """
    A typed claim made by an agent.

    Claims are structured assertions that can be verified by the governor.
    Each claim type requires specific fields - validation happens at creation.

    Examples:
        # File exists claim
        Claim(type=ClaimType.FILE_EXISTS, path="src/main.py")

        # Tests pass claim
        Claim(type=ClaimType.TESTS_PASS, command=("pytest", "-v"))

        # Decision claim
        Claim(type=ClaimType.DECISION, topic="framework", choice="react")

        # Changeset claim
        Claim(type=ClaimType.CHANGESET, diff="--- a/x.py\\n+++ b/x.py\\n...")
    """

    type: ClaimType

    # Type-specific payload fields
    path: str | None = None
    symbol: str | None = None
    span: tuple[int, int] | None = None
    command: tuple[str, ...] | None = None  # tuple for immutability
    topic: str | None = None
    choice: str | None = None
    diff: str | None = None
    paths: tuple[str, ...] | None = None  # for changeset

    def __post_init__(self) -> None:
        """Validate that required fields are present for this claim type."""
        self._validate()

    def _validate(self) -> None:
        """Check that all required fields for this claim type are present."""
        required = _REQUIRED_FIELDS.get(self.type, set())

        missing = []
        for field in required:
            value = getattr(self, field)
            if value is None:
                missing.append(field)

        if missing:
            raise ClaimValidationError(
                self.type,
                f"missing required field(s): {', '.join(missing)}",
            )

        # Validate field types
        if self.path is not None and not isinstance(self.path, str):
            raise ClaimValidationError(self.type, "path must be a string")

        if self.symbol is not None and not isinstance(self.symbol, str):
            raise ClaimValidationError(self.type, "symbol must be a string")

        if self.span is not None:
            if not isinstance(self.span, tuple) or len(self.span) != 2:
                raise ClaimValidationError(
                    self.type, "span must be a tuple of (start, end)"
                )
            if not all(isinstance(x, int) for x in self.span):
                raise ClaimValidationError(
                    self.type, "span values must be integers"
                )

        if self.command is not None:
            if not isinstance(self.command, tuple):
                raise ClaimValidationError(
                    self.type, "command must be a tuple of strings"
                )
            if not all(isinstance(x, str) for x in self.command):
                raise ClaimValidationError(
                    self.type, "command elements must be strings"
                )

        if self.topic is not None and not isinstance(self.topic, str):
            raise ClaimValidationError(self.type, "topic must be a string")

        if self.choice is not None and not isinstance(self.choice, str):
            raise ClaimValidationError(self.type, "choice must be a string")

        if self.diff is not None and not isinstance(self.diff, str):
            raise ClaimValidationError(self.type, "diff must be a string")

    def to_dict(self) -> dict[str, Any]:
        """Serialize claim to dict."""
        data: dict[str, Any] = {"type": self.type.value}

        if self.path is not None:
            data["path"] = self.path
        if self.symbol is not None:
            data["symbol"] = self.symbol
        if self.span is not None:
            data["span"] = list(self.span)
        if self.command is not None:
            data["command"] = list(self.command)
        if self.topic is not None:
            data["topic"] = self.topic
        if self.choice is not None:
            data["choice"] = self.choice
        if self.diff is not None:
            data["diff"] = self.diff
        if self.paths is not None:
            data["paths"] = list(self.paths)

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Claim":
        """Deserialize claim from dict."""
        claim_type = ClaimType(data["type"])

        return cls(
            type=claim_type,
            path=data.get("path"),
            symbol=data.get("symbol"),
            span=tuple(data["span"]) if data.get("span") else None,
            command=tuple(data["command"]) if data.get("command") else None,
            topic=data.get("topic"),
            choice=data.get("choice"),
            diff=data.get("diff"),
            paths=tuple(data["paths"]) if data.get("paths") else None,
        )

    def describe(self) -> str:
        """Return a human-readable description of this claim."""
        if self.type == ClaimType.FILE_EXISTS:
            return f"File exists: {self.path}"
        elif self.type == ClaimType.SYMBOL_DEFINED:
            loc = f"{self.path}:{self.span}" if self.span else self.path
            return f"Symbol '{self.symbol}' defined at {loc}"
        elif self.type == ClaimType.API_SURFACE:
            return f"API '{self.symbol}' at {self.path}"
        elif self.type == ClaimType.TESTS_PASS:
            cmd = " ".join(self.command) if self.command else ""
            return f"Tests pass: {cmd}"
        elif self.type == ClaimType.DECISION:
            return f"Decision [{self.topic}]: {self.choice}"
        elif self.type == ClaimType.CHANGESET:
            return f"Changeset ({len(self.diff or '')} bytes)"
        else:
            return f"Claim: {self.type.value}"


# Convenience constructors
def file_exists(path: str, span: tuple[int, int] | None = None) -> Claim:
    """Create a FILE_EXISTS claim."""
    return Claim(type=ClaimType.FILE_EXISTS, path=path, span=span)


def symbol_defined(
    path: str,
    symbol: str,
    span: tuple[int, int] | None = None,
) -> Claim:
    """Create a SYMBOL_DEFINED claim."""
    return Claim(
        type=ClaimType.SYMBOL_DEFINED, path=path, symbol=symbol, span=span
    )


def api_surface(
    path: str,
    symbol: str,
    span: tuple[int, int] | None = None,
) -> Claim:
    """Create an API_SURFACE claim."""
    return Claim(
        type=ClaimType.API_SURFACE, path=path, symbol=symbol, span=span
    )


def claim_tests_pass(command: list[str] | tuple[str, ...]) -> Claim:
    """Create a TESTS_PASS claim."""
    return Claim(type=ClaimType.TESTS_PASS, command=tuple(command))


def decision(topic: str, choice: str) -> Claim:
    """Create a DECISION claim."""
    return Claim(type=ClaimType.DECISION, topic=topic, choice=choice)


def changeset(diff: str, paths: list[str] | tuple[str, ...] | None = None) -> Claim:
    """Create a CHANGESET claim."""
    return Claim(
        type=ClaimType.CHANGESET,
        diff=diff,
        paths=tuple(paths) if paths else None,
    )
