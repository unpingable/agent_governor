"""Tests for typed claims."""

import json

import pytest

from governor.claims import (
    Claim,
    ClaimType,
    ClaimValidationError,
    file_exists,
    symbol_defined,
    api_surface,
    claim_tests_pass,
    decision,
    changeset,
    work_reservation,
    intent,
)


class TestClaimType:
    """Test ClaimType enum."""

    def test_all_types_exist(self):
        """All expected claim types are defined."""
        assert ClaimType.FILE_EXISTS.value == "file_exists"
        assert ClaimType.SYMBOL_DEFINED.value == "symbol_defined"
        assert ClaimType.API_SURFACE.value == "api_surface"
        assert ClaimType.TESTS_PASS.value == "tests_pass"
        assert ClaimType.DECISION.value == "decision"
        assert ClaimType.CHANGESET.value == "changeset"
        # Multi-agent types
        assert ClaimType.WORK_RESERVATION.value == "work_reservation"
        assert ClaimType.INTENT.value == "intent"

    def test_from_string(self):
        """Can create ClaimType from string value."""
        assert ClaimType("file_exists") == ClaimType.FILE_EXISTS
        assert ClaimType("tests_pass") == ClaimType.TESTS_PASS


class TestClaimValidation:
    """Test claim validation rules."""

    def test_file_exists_requires_path(self):
        """FILE_EXISTS claim requires path."""
        with pytest.raises(ClaimValidationError, match="missing required.*path"):
            Claim(type=ClaimType.FILE_EXISTS)

    def test_file_exists_valid(self):
        """FILE_EXISTS claim with path is valid."""
        claim = Claim(type=ClaimType.FILE_EXISTS, path="src/main.py")
        assert claim.path == "src/main.py"

    def test_symbol_defined_requires_path_and_symbol(self):
        """SYMBOL_DEFINED claim requires path and symbol."""
        with pytest.raises(ClaimValidationError, match="missing required"):
            Claim(type=ClaimType.SYMBOL_DEFINED, path="src/main.py")

        with pytest.raises(ClaimValidationError, match="missing required"):
            Claim(type=ClaimType.SYMBOL_DEFINED, symbol="MyClass")

    def test_symbol_defined_valid(self):
        """SYMBOL_DEFINED claim with path and symbol is valid."""
        claim = Claim(
            type=ClaimType.SYMBOL_DEFINED,
            path="src/main.py",
            symbol="MyClass",
        )
        assert claim.path == "src/main.py"
        assert claim.symbol == "MyClass"

    def test_symbol_defined_with_span(self):
        """SYMBOL_DEFINED claim can include optional span."""
        claim = Claim(
            type=ClaimType.SYMBOL_DEFINED,
            path="src/main.py",
            symbol="MyClass",
            span=(10, 50),
        )
        assert claim.span == (10, 50)

    def test_api_surface_requires_path_and_symbol(self):
        """API_SURFACE claim requires path and symbol."""
        with pytest.raises(ClaimValidationError):
            Claim(type=ClaimType.API_SURFACE, path="api.py")

    def test_api_surface_valid(self):
        """API_SURFACE claim with path and symbol is valid."""
        claim = Claim(
            type=ClaimType.API_SURFACE,
            path="api.py",
            symbol="GET /users",
        )
        assert claim.symbol == "GET /users"

    def test_tests_pass_requires_command(self):
        """TESTS_PASS claim requires command."""
        with pytest.raises(ClaimValidationError, match="missing required.*command"):
            Claim(type=ClaimType.TESTS_PASS)

    def test_tests_pass_valid(self):
        """TESTS_PASS claim with command is valid."""
        claim = Claim(
            type=ClaimType.TESTS_PASS,
            command=("pytest", "-v"),
        )
        assert claim.command == ("pytest", "-v")

    def test_decision_requires_topic_and_choice(self):
        """DECISION claim requires topic and choice."""
        with pytest.raises(ClaimValidationError):
            Claim(type=ClaimType.DECISION, topic="framework")

        with pytest.raises(ClaimValidationError):
            Claim(type=ClaimType.DECISION, choice="react")

    def test_decision_valid(self):
        """DECISION claim with topic and choice is valid."""
        claim = Claim(
            type=ClaimType.DECISION,
            topic="framework",
            choice="react",
        )
        assert claim.topic == "framework"
        assert claim.choice == "react"

    def test_changeset_requires_diff(self):
        """CHANGESET claim requires diff."""
        with pytest.raises(ClaimValidationError, match="missing required.*diff"):
            Claim(type=ClaimType.CHANGESET)

    def test_changeset_valid(self):
        """CHANGESET claim with diff is valid."""
        diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new"
        claim = Claim(type=ClaimType.CHANGESET, diff=diff)
        assert claim.diff == diff

    def test_changeset_with_paths(self):
        """CHANGESET claim can include optional paths."""
        claim = Claim(
            type=ClaimType.CHANGESET,
            diff="...",
            paths=("a.py", "b.py"),
        )
        assert claim.paths == ("a.py", "b.py")


class TestClaimTypeValidation:
    """Test field type validation."""

    def test_span_must_be_tuple(self):
        """span must be a tuple of two ints."""
        with pytest.raises(ClaimValidationError, match="span must be a tuple"):
            Claim(
                type=ClaimType.FILE_EXISTS,
                path="x.py",
                span=[1, 2],  # type: ignore - testing wrong type
            )

    def test_span_must_have_two_elements(self):
        """span must have exactly two elements."""
        with pytest.raises(ClaimValidationError, match="span must be a tuple"):
            Claim(
                type=ClaimType.FILE_EXISTS,
                path="x.py",
                span=(1, 2, 3),  # type: ignore
            )

    def test_span_must_be_ints(self):
        """span values must be integers."""
        with pytest.raises(ClaimValidationError, match="span values must be integers"):
            Claim(
                type=ClaimType.FILE_EXISTS,
                path="x.py",
                span=("a", "b"),  # type: ignore
            )

    def test_command_must_be_tuple(self):
        """command must be a tuple."""
        with pytest.raises(ClaimValidationError, match="command must be a tuple"):
            Claim(
                type=ClaimType.TESTS_PASS,
                command=["pytest"],  # type: ignore - testing wrong type
            )

    def test_command_elements_must_be_strings(self):
        """command elements must be strings."""
        with pytest.raises(ClaimValidationError, match="command elements must be strings"):
            Claim(
                type=ClaimType.TESTS_PASS,
                command=(1, 2, 3),  # type: ignore
            )


class TestClaimSerialization:
    """Test claim serialization/deserialization."""

    def test_to_dict_file_exists(self):
        """FILE_EXISTS claim serializes correctly."""
        claim = Claim(type=ClaimType.FILE_EXISTS, path="src/main.py")
        data = claim.to_dict()

        assert data["type"] == "file_exists"
        assert data["path"] == "src/main.py"
        assert "symbol" not in data

    def test_to_dict_with_optional_fields(self):
        """Optional fields are included when present."""
        claim = Claim(
            type=ClaimType.SYMBOL_DEFINED,
            path="src/main.py",
            symbol="MyClass",
            span=(10, 20),
        )
        data = claim.to_dict()

        assert data["span"] == [10, 20]

    def test_from_dict_file_exists(self):
        """FILE_EXISTS claim deserializes correctly."""
        data = {"type": "file_exists", "path": "src/main.py"}
        claim = Claim.from_dict(data)

        assert claim.type == ClaimType.FILE_EXISTS
        assert claim.path == "src/main.py"

    def test_from_dict_with_command(self):
        """TESTS_PASS claim deserializes command as tuple."""
        data = {"type": "tests_pass", "command": ["pytest", "-v"]}
        claim = Claim.from_dict(data)

        assert claim.command == ("pytest", "-v")

    def test_round_trip(self):
        """Claim survives JSON round-trip."""
        original = Claim(
            type=ClaimType.SYMBOL_DEFINED,
            path="src/api.py",
            symbol="UserEndpoint",
            span=(100, 150),
        )

        json_str = json.dumps(original.to_dict())
        restored = Claim.from_dict(json.loads(json_str))

        assert restored == original

    def test_round_trip_decision(self):
        """DECISION claim survives round-trip."""
        original = Claim(
            type=ClaimType.DECISION,
            topic="database",
            choice="postgresql",
        )

        json_str = json.dumps(original.to_dict())
        restored = Claim.from_dict(json.loads(json_str))

        assert restored == original


class TestClaimDescribe:
    """Test human-readable claim descriptions."""

    def test_describe_file_exists(self):
        """FILE_EXISTS description is readable."""
        claim = file_exists("src/main.py")
        assert claim.describe() == "File exists: src/main.py"

    def test_describe_symbol_defined(self):
        """SYMBOL_DEFINED description includes symbol."""
        claim = symbol_defined("src/main.py", "MyClass")
        assert "MyClass" in claim.describe()
        assert "src/main.py" in claim.describe()

    def test_describe_symbol_defined_with_span(self):
        """SYMBOL_DEFINED description includes span when present."""
        claim = symbol_defined("src/main.py", "MyClass", span=(10, 20))
        assert "(10, 20)" in claim.describe()

    def test_describe_claim_tests_pass(self):
        """TESTS_PASS description includes command."""
        claim = claim_tests_pass(["pytest", "-v"])
        assert "pytest -v" in claim.describe()

    def test_describe_decision(self):
        """DECISION description includes topic and choice."""
        claim = decision("framework", "react")
        desc = claim.describe()
        assert "framework" in desc
        assert "react" in desc

    def test_describe_changeset(self):
        """CHANGESET description includes size."""
        claim = changeset("x" * 100)
        assert "100 bytes" in claim.describe()


class TestConvenienceConstructors:
    """Test convenience constructor functions."""

    def test_file_exists_constructor(self):
        """file_exists() creates valid claim."""
        claim = file_exists("path/to/file.py")
        assert claim.type == ClaimType.FILE_EXISTS
        assert claim.path == "path/to/file.py"

    def test_file_exists_with_span(self):
        """file_exists() accepts optional span."""
        claim = file_exists("file.py", span=(1, 10))
        assert claim.span == (1, 10)

    def test_symbol_defined_constructor(self):
        """symbol_defined() creates valid claim."""
        claim = symbol_defined("file.py", "ClassName")
        assert claim.type == ClaimType.SYMBOL_DEFINED
        assert claim.path == "file.py"
        assert claim.symbol == "ClassName"

    def test_api_surface_constructor(self):
        """api_surface() creates valid claim."""
        claim = api_surface("api.py", "GET /users")
        assert claim.type == ClaimType.API_SURFACE
        assert claim.symbol == "GET /users"

    def test_tests_pass_constructor(self):
        """claim_tests_pass() creates valid claim and converts list to tuple."""
        claim = claim_tests_pass(["pytest", "-v", "--tb=short"])
        assert claim.type == ClaimType.TESTS_PASS
        assert claim.command == ("pytest", "-v", "--tb=short")

    def test_decision_constructor(self):
        """decision() creates valid claim."""
        claim = decision("styling", "tailwind")
        assert claim.type == ClaimType.DECISION
        assert claim.topic == "styling"
        assert claim.choice == "tailwind"

    def test_changeset_constructor(self):
        """changeset() creates valid claim."""
        diff = "--- a/x.py\n+++ b/x.py"
        claim = changeset(diff)
        assert claim.type == ClaimType.CHANGESET
        assert claim.diff == diff

    def test_changeset_with_paths(self):
        """changeset() accepts optional paths."""
        claim = changeset("diff...", paths=["a.py", "b.py"])
        assert claim.paths == ("a.py", "b.py")


class TestClaimImmutability:
    """Test that claims are immutable."""

    def test_claim_is_frozen(self):
        """Cannot modify claim after creation."""
        claim = file_exists("test.py")
        with pytest.raises(AttributeError):
            claim.path = "other.py"  # type: ignore


class TestMultiAgentClaims:
    """Test multi-agent coordination claims."""

    def test_work_reservation_requires_scope_and_task(self):
        """WORK_RESERVATION requires scope and task."""
        with pytest.raises(ClaimValidationError, match="missing required"):
            Claim(type=ClaimType.WORK_RESERVATION)

        with pytest.raises(ClaimValidationError, match="missing required"):
            Claim(type=ClaimType.WORK_RESERVATION, scope=("a.py",))

        with pytest.raises(ClaimValidationError, match="missing required"):
            Claim(type=ClaimType.WORK_RESERVATION, task="implement feature")

    def test_work_reservation_valid(self):
        """WORK_RESERVATION with scope and task is valid."""
        claim = Claim(
            type=ClaimType.WORK_RESERVATION,
            scope=("src/api.py", "tests/test_api.py"),
            task="implement /users endpoint",
        )
        assert claim.scope == ("src/api.py", "tests/test_api.py")
        assert claim.task == "implement /users endpoint"

    def test_work_reservation_with_eta(self):
        """WORK_RESERVATION can include eta_minutes."""
        claim = Claim(
            type=ClaimType.WORK_RESERVATION,
            scope=("src/api.py",),
            task="implement feature",
            eta_minutes=30,
        )
        assert claim.eta_minutes == 30

    def test_work_reservation_constructor(self):
        """work_reservation() creates valid claim."""
        claim = work_reservation(
            task="implement feature",
            scope=["src/api.py", "tests/test_api.py"],
            eta_minutes=30,
        )
        assert claim.type == ClaimType.WORK_RESERVATION
        assert claim.scope == ("src/api.py", "tests/test_api.py")
        assert claim.task == "implement feature"
        assert claim.eta_minutes == 30

    def test_intent_requires_scope_and_task(self):
        """INTENT requires scope and task."""
        with pytest.raises(ClaimValidationError, match="missing required"):
            Claim(type=ClaimType.INTENT)

    def test_intent_valid(self):
        """INTENT with scope and task is valid."""
        claim = Claim(
            type=ClaimType.INTENT,
            scope=("src/api.py",),
            task="refactor authentication",
        )
        assert claim.scope == ("src/api.py",)
        assert claim.task == "refactor authentication"

    def test_intent_constructor(self):
        """intent() creates valid claim."""
        claim = intent(
            task="refactor authentication",
            scope=["src/api.py"],
        )
        assert claim.type == ClaimType.INTENT
        assert claim.scope == ("src/api.py",)
        assert claim.task == "refactor authentication"

    def test_work_reservation_describe(self):
        """WORK_RESERVATION description includes task and scope."""
        claim = work_reservation(
            task="implement feature",
            scope=["src/api.py", "tests/test_api.py"],
        )
        desc = claim.describe()
        assert "implement feature" in desc
        assert "src/api.py" in desc

    def test_intent_describe(self):
        """INTENT description includes task and scope."""
        claim = intent(
            task="refactor auth",
            scope=["src/auth.py"],
        )
        desc = claim.describe()
        assert "refactor auth" in desc
        assert "src/auth.py" in desc

    def test_work_reservation_round_trip(self):
        """WORK_RESERVATION survives serialization round-trip."""
        original = work_reservation(
            task="implement feature",
            scope=["src/api.py"],
            eta_minutes=30,
        )
        restored = Claim.from_dict(original.to_dict())
        assert restored == original

    def test_intent_round_trip(self):
        """INTENT survives serialization round-trip."""
        original = intent(
            task="refactor",
            scope=["src/api.py", "src/utils.py"],
        )
        restored = Claim.from_dict(original.to_dict())
        assert restored == original

    def test_scope_must_be_tuple(self):
        """scope must be a tuple."""
        with pytest.raises(ClaimValidationError, match="scope must be a tuple"):
            Claim(
                type=ClaimType.WORK_RESERVATION,
                scope="not a tuple",  # type: ignore
                task="task",
            )

    def test_scope_elements_must_be_strings(self):
        """scope elements must be strings."""
        with pytest.raises(ClaimValidationError, match="scope elements must be strings"):
            Claim(
                type=ClaimType.WORK_RESERVATION,
                scope=(1, 2, 3),  # type: ignore
                task="task",
            )
