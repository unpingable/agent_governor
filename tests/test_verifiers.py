# SPDX-License-Identifier: Apache-2.0
"""Tests for receipt-producing verifiers."""

import pytest

from governor.claims import (
    Claim,
    ClaimType,
    file_exists,
    symbol_defined,
    api_surface,
    claim_tests_pass,
    changeset,
)
from governor.receipts import FileSnapshot, CmdRun, DiffReceipt
from governor.verifiers import (
    VerificationResult,
    FileVerifier,
    CommandVerifier,
    DiffVerifier,
    ApiVerifier,
    CompositeVerifier,
    create_default_verifiers,
)


class TestVerificationResult:
    """Test VerificationResult dataclass."""

    def test_ok_result(self):
        """Can create successful result."""
        receipt = FileSnapshot(
            path="test.py",
            blob_hash="abc",
            size_bytes=100,
            timestamp=pytest.importorskip("datetime").datetime.now(
                pytest.importorskip("datetime").timezone.utc
            ),
        )

        result = VerificationResult.ok(receipt)

        assert result.success is True
        assert result.receipt == receipt
        assert result.error is None

    def test_fail_result(self):
        """Can create failed result."""
        result = VerificationResult.fail("Something went wrong")

        assert result.success is False
        assert result.receipt is None
        assert result.error == "Something went wrong"


class TestFileVerifier:
    """Test FileVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a FileVerifier."""
        return FileVerifier(tmp_path)

    def test_can_verify_file_exists(self, verifier):
        """Can verify FILE_EXISTS claims."""
        claim = file_exists("test.py")
        assert verifier.can_verify(claim) is True

    def test_can_verify_symbol_defined(self, verifier):
        """Can verify SYMBOL_DEFINED claims."""
        claim = symbol_defined("test.py", "MyClass")
        assert verifier.can_verify(claim) is True

    def test_cannot_verify_tests_pass(self, verifier):
        """Cannot verify TESTS_PASS claims."""
        claim = claim_tests_pass(["pytest"])
        assert verifier.can_verify(claim) is False

    def test_verify_existing_file(self, verifier, tmp_path):
        """Successfully verifies existing file."""
        test_file = tmp_path / "main.py"
        test_file.write_text("print('hello')")

        claim = file_exists("main.py")
        result = verifier.verify(claim)

        assert result.success is True
        assert isinstance(result.receipt, FileSnapshot)
        assert result.receipt.path == "main.py"

    def test_verify_missing_file(self, verifier):
        """Fails for missing file."""
        claim = file_exists("nonexistent.py")
        result = verifier.verify(claim)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_verify_directory_fails(self, verifier, tmp_path):
        """Fails when path is a directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        claim = file_exists("subdir")
        result = verifier.verify(claim)

        assert result.success is False
        assert "directory" in result.error.lower()

    def test_verify_symbol_present(self, verifier, tmp_path):
        """Successfully verifies symbol in file."""
        test_file = tmp_path / "models.py"
        test_file.write_text("class UserModel:\n    pass\n")

        claim = symbol_defined("models.py", "UserModel")
        result = verifier.verify(claim)

        assert result.success is True
        assert isinstance(result.receipt, FileSnapshot)

    def test_verify_symbol_missing(self, verifier, tmp_path):
        """Fails when symbol not in file."""
        test_file = tmp_path / "models.py"
        test_file.write_text("class OtherModel:\n    pass\n")

        claim = symbol_defined("models.py", "UserModel")
        result = verifier.verify(claim)

        assert result.success is False
        assert "UserModel" in result.error
        assert "not found" in result.error.lower()

    def test_claim_validation_prevents_no_path(self):
        """Claim validation prevents FILE_EXISTS without path."""
        # This test documents that the claim layer prevents invalid claims,
        # so the verifier doesn't need to handle this case
        from governor.claims import ClaimValidationError

        with pytest.raises(ClaimValidationError):
            Claim(type=ClaimType.FILE_EXISTS, path=None)


class TestCommandVerifier:
    """Test CommandVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a CommandVerifier."""
        return CommandVerifier(tmp_path, timeout=30)

    def test_can_verify_tests_pass(self, verifier):
        """Can verify TESTS_PASS claims."""
        claim = claim_tests_pass(["pytest"])
        assert verifier.can_verify(claim) is True

    def test_cannot_verify_file_exists(self, verifier):
        """Cannot verify FILE_EXISTS claims."""
        claim = file_exists("test.py")
        assert verifier.can_verify(claim) is False

    def test_verify_passing_command(self, verifier):
        """Successfully verifies passing command."""
        claim = claim_tests_pass(["true"])  # Unix command that always succeeds
        result = verifier.verify(claim)

        assert result.success is True
        assert isinstance(result.receipt, CmdRun)
        assert result.receipt.exit_code == 0

    def test_verify_failing_command(self, verifier):
        """Fails for command with non-zero exit."""
        claim = claim_tests_pass(["false"])  # Unix command that always fails
        result = verifier.verify(claim)

        assert result.success is False
        assert "exit code" in result.error.lower()

    def test_verify_command_not_found(self, verifier):
        """Fails for missing command."""
        claim = claim_tests_pass(["nonexistent_command_xyz"])
        result = verifier.verify(claim)

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_verify_allows_nonzero_when_configured(self, tmp_path):
        """Can allow non-zero exit codes."""
        verifier = CommandVerifier(tmp_path, require_exit_zero=False)

        claim = claim_tests_pass(["false"])
        result = verifier.verify(claim)

        assert result.success is True
        assert result.receipt.exit_code != 0


class TestDiffVerifier:
    """Test DiffVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a DiffVerifier."""
        return DiffVerifier(tmp_path)

    SAMPLE_DIFF = """\
diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 line1
+added
 line2
 line3
"""

    def test_can_verify_changeset(self, verifier):
        """Can verify CHANGESET claims."""
        claim = changeset(self.SAMPLE_DIFF)
        assert verifier.can_verify(claim) is True

    def test_cannot_verify_file_exists(self, verifier):
        """Cannot verify FILE_EXISTS claims."""
        claim = file_exists("test.py")
        assert verifier.can_verify(claim) is False

    def test_verify_valid_diff(self, verifier):
        """Successfully verifies valid diff."""
        claim = changeset(self.SAMPLE_DIFF)
        result = verifier.verify(claim)

        assert result.success is True
        assert isinstance(result.receipt, DiffReceipt)
        assert "test.py" in result.receipt.paths_touched

    def test_verify_empty_diff(self, verifier):
        """Fails for empty diff."""
        claim = changeset("")
        result = verifier.verify(claim)

        assert result.success is False
        assert "empty" in result.error.lower()

    def test_verify_whitespace_only_diff(self, verifier):
        """Fails for whitespace-only diff."""
        claim = changeset("   \n\n   ")
        result = verifier.verify(claim)

        assert result.success is False
        assert "empty" in result.error.lower()

    def test_verify_multiple_files(self, verifier):
        """Verifies diff touching multiple files."""
        multi_diff = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1,2 @@
 existing
+new
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1,2 @@
 existing
+new
"""
        claim = changeset(multi_diff)
        result = verifier.verify(claim)

        assert result.success is True
        assert len(result.receipt.paths_touched) == 2


class TestApiVerifier:
    """Test ApiVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create an ApiVerifier."""
        return ApiVerifier(tmp_path)

    def test_can_verify_api_surface(self, verifier):
        """Can verify API_SURFACE claims."""
        claim = api_surface("routes.py", "GET /users")
        assert verifier.can_verify(claim) is True

    def test_cannot_verify_file_exists(self, verifier):
        """Cannot verify FILE_EXISTS claims."""
        claim = file_exists("test.py")
        assert verifier.can_verify(claim) is False

    def test_verify_api_present(self, verifier, tmp_path):
        """Successfully verifies API in file."""
        routes_file = tmp_path / "routes.py"
        routes_file.write_text(
            '@app.route("/users")\n'
            'def get_users():\n'
            '    return users\n'
        )

        claim = api_surface("routes.py", "/users")
        result = verifier.verify(claim)

        assert result.success is True
        assert isinstance(result.receipt, FileSnapshot)

    def test_verify_api_missing(self, verifier, tmp_path):
        """Fails when API not in file."""
        routes_file = tmp_path / "routes.py"
        routes_file.write_text(
            '@app.route("/products")\n'
            'def get_products():\n'
            '    return products\n'
        )

        claim = api_surface("routes.py", "/users")
        result = verifier.verify(claim)

        assert result.success is False
        assert "/users" in result.error
        assert "not found" in result.error.lower()

    def test_verify_file_missing(self, verifier):
        """Fails when file doesn't exist."""
        claim = api_surface("nonexistent.py", "/api")
        result = verifier.verify(claim)

        assert result.success is False
        assert "not found" in result.error.lower()


class TestCompositeVerifier:
    """Test CompositeVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a CompositeVerifier with all types."""
        return CompositeVerifier([
            FileVerifier(tmp_path),
            CommandVerifier(tmp_path),
            DiffVerifier(tmp_path),
        ])

    def test_can_verify_delegates(self, verifier):
        """can_verify delegates to appropriate verifier."""
        assert verifier.can_verify(file_exists("test.py")) is True
        assert verifier.can_verify(claim_tests_pass(["pytest"])) is True
        assert verifier.can_verify(changeset("diff...")) is True

    def test_verify_delegates_to_file_verifier(self, verifier, tmp_path):
        """Delegates FILE_EXISTS to FileVerifier."""
        test_file = tmp_path / "app.py"
        test_file.write_text("# app")

        result = verifier.verify(file_exists("app.py"))

        assert result.success is True
        assert isinstance(result.receipt, FileSnapshot)

    def test_verify_delegates_to_test_verifier(self, verifier):
        """Delegates TESTS_PASS to TestVerifier."""
        result = verifier.verify(claim_tests_pass(["true"]))

        assert result.success is True
        assert isinstance(result.receipt, CmdRun)

    def test_verify_delegates_to_diff_verifier(self, verifier):
        """Delegates CHANGESET to DiffVerifier."""
        diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1,2 @@\n a\n+b\n"
        result = verifier.verify(changeset(diff))

        assert result.success is True
        assert isinstance(result.receipt, DiffReceipt)

    def test_verify_all_multiple_claims(self, verifier, tmp_path):
        """verify_all handles multiple claims."""
        test_file = tmp_path / "main.py"
        test_file.write_text("# main")

        claims = [
            file_exists("main.py"),
            claim_tests_pass(["true"]),
        ]

        results = verifier.verify_all(claims)

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_verify_all_partial_failure(self, verifier, tmp_path):
        """verify_all returns results for each claim."""
        test_file = tmp_path / "exists.py"
        test_file.write_text("# exists")

        claims = [
            file_exists("exists.py"),
            file_exists("missing.py"),
        ]

        results = verifier.verify_all(claims)

        assert len(results) == 2
        assert results[0].success is True
        assert results[1].success is False

    def test_no_verifier_available(self, tmp_path):
        """Returns error when no verifier can handle claim."""
        # Empty composite
        verifier = CompositeVerifier([])

        result = verifier.verify(file_exists("test.py"))

        assert result.success is False
        assert "no verifier" in result.error.lower()


class TestCreateDefaultVerifiers:
    """Test create_default_verifiers factory."""

    def test_creates_composite(self, tmp_path):
        """Creates a CompositeVerifier."""
        verifier = create_default_verifiers(tmp_path)

        assert isinstance(verifier, CompositeVerifier)

    def test_has_all_verifier_types(self, tmp_path):
        """Has verifiers for all claim types."""
        verifier = create_default_verifiers(tmp_path)

        assert verifier.can_verify(file_exists("x.py"))
        assert verifier.can_verify(claim_tests_pass(["pytest"]))
        assert verifier.can_verify(changeset("diff"))
        assert verifier.can_verify(api_surface("x.py", "GET /api"))
