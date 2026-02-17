# SPDX-License-Identifier: Apache-2.0
"""
Tests for Phase A1: Invariants (mechanically verifiable rules).
"""

import pytest
from pathlib import Path

from governor.invariants import (
    InvariantType,
    InvariantResult,
    Invariant,
    InvariantSet,
    InvariantLibrary,
)


class TestInvariantType:
    def test_values(self):
        assert InvariantType.STRUCTURE == "structure"
        assert InvariantType.EVIDENCE == "evidence"
        assert InvariantType.TEST == "test"
        assert InvariantType.FORBIDDEN == "forbidden"

    def test_all_types_exist(self):
        expected = {"structure", "evidence", "architecture", "test", "consistency", "forbidden"}
        actual = {t.value for t in InvariantType}
        assert actual == expected


class TestInvariantResult:
    def test_passed(self):
        r = InvariantResult(passed=True, message="OK", invariant_id="test")
        assert r.passed is True
        assert r.invariant_id == "test"

    def test_failed(self):
        r = InvariantResult(
            passed=False,
            message="Tests failed",
            invariant_id="tests_must_pass",
            details={"returncode": 1},
        )
        assert r.passed is False
        assert r.details["returncode"] == 1

    def test_to_dict(self):
        r = InvariantResult(passed=True, message="OK", invariant_id="test")
        d = r.to_dict()
        assert d["passed"] is True
        assert d["invariant_id"] == "test"


class TestInvariant:
    def test_basic_check(self):
        inv = Invariant(
            id="always_pass",
            type=InvariantType.TEST,
            rule="Always passes",
            verify=lambda **kwargs: InvariantResult(
                passed=True, message="OK", invariant_id="always_pass"
            ),
        )
        result = inv.check()
        assert result.passed is True

    def test_failing_check(self):
        inv = Invariant(
            id="always_fail",
            type=InvariantType.TEST,
            rule="Always fails",
            verify=lambda **kwargs: InvariantResult(
                passed=False, message="FAIL", invariant_id="always_fail"
            ),
        )
        result = inv.check()
        assert result.passed is False

    def test_disabled_invariant_passes(self):
        inv = Invariant(
            id="disabled",
            type=InvariantType.TEST,
            rule="Disabled",
            verify=lambda **kwargs: InvariantResult(
                passed=False, message="FAIL", invariant_id="disabled"
            ),
            enabled=False,
        )
        result = inv.check()
        assert result.passed is True
        assert "disabled" in result.message.lower()

    def test_kwargs_passed_through(self):
        def verify_with_args(**kwargs):
            name = kwargs.get("name", "")
            return InvariantResult(
                passed=name == "test",
                message=f"name={name}",
                invariant_id="args_test",
            )

        inv = Invariant(
            id="args_test",
            type=InvariantType.STRUCTURE,
            rule="Check args",
            verify=verify_with_args,
        )
        assert inv.check(name="test").passed is True
        assert inv.check(name="other").passed is False

    def test_to_dict(self):
        inv = Invariant(
            id="test",
            type=InvariantType.FORBIDDEN,
            rule="No secrets",
            verify=lambda **kwargs: InvariantResult(passed=True, message="", invariant_id="test"),
            on_violation="block",
        )
        d = inv.to_dict()
        assert d["id"] == "test"
        assert d["type"] == "forbidden"
        assert d["on_violation"] == "block"

    def test_on_violation_default(self):
        inv = Invariant(
            id="test",
            type=InvariantType.TEST,
            rule="test",
            verify=lambda **kwargs: InvariantResult(passed=True, message="", invariant_id="test"),
        )
        assert inv.on_violation == "block"


class TestInvariantSet:
    def _make_invariant(self, inv_id: str, passes: bool) -> Invariant:
        return Invariant(
            id=inv_id,
            type=InvariantType.TEST,
            rule=f"Invariant {inv_id}",
            verify=lambda passes=passes, inv_id=inv_id, **kwargs: InvariantResult(
                passed=passes, message="OK" if passes else "FAIL", invariant_id=inv_id
            ),
        )

    def test_empty_set(self):
        inv_set = InvariantSet()
        results = inv_set.check_all()
        assert len(results) == 0

    def test_add_and_check(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_invariant("a", True))
        inv_set.add(self._make_invariant("b", True))
        results = inv_set.check_all()
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_mixed_results(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_invariant("pass", True))
        inv_set.add(self._make_invariant("fail", False))
        results = inv_set.check_all()
        assert len(results) == 2
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]
        assert len(passed) == 1
        assert len(failed) == 1

    def test_remove(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_invariant("a", True))
        inv_set.add(self._make_invariant("b", True))
        assert inv_set.remove("a") is True
        assert len(inv_set.check_all()) == 1

    def test_remove_nonexistent(self):
        inv_set = InvariantSet()
        assert inv_set.remove("nope") is False

    def test_get(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_invariant("a", True))
        assert inv_set.get("a") is not None
        assert inv_set.get("b") is None

    def test_blocking_violations(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_invariant("pass", True))
        blocker = self._make_invariant("blocker", False)
        blocker.on_violation = "block"
        inv_set.add(blocker)
        warner = self._make_invariant("warner", False)
        warner.on_violation = "warn"
        inv_set.add(warner)

        blocking = inv_set.blocking_violations()
        assert len(blocking) == 1
        assert blocking[0].invariant_id == "blocker"

    def test_disabled_skipped(self):
        inv_set = InvariantSet()
        disabled = self._make_invariant("disabled", False)
        disabled.enabled = False
        inv_set.add(disabled)
        inv_set.add(self._make_invariant("enabled", True))
        results = inv_set.check_all()
        assert len(results) == 1  # Only enabled one runs

    def test_to_dict(self):
        inv_set = InvariantSet()
        inv_set.add(self._make_invariant("a", True))
        d = inv_set.to_dict()
        assert len(d["invariants"]) == 1


class TestInvariantLibraryFileExists:
    def test_file_exists_passes(self, tmp_path):
        (tmp_path / "main.py").write_text("# code")
        inv = InvariantLibrary.file_must_exist("main.py")
        result = inv.check(root=tmp_path)
        assert result.passed is True

    def test_file_missing_fails(self, tmp_path):
        inv = InvariantLibrary.file_must_exist("missing.py")
        result = inv.check(root=tmp_path)
        assert result.passed is False
        assert "missing" in result.message.lower()

    def test_custom_id(self):
        inv = InvariantLibrary.file_must_exist("a.py", invariant_id="custom")
        assert inv.id == "custom"


class TestInvariantLibraryDirExists:
    def test_dir_exists_passes(self, tmp_path):
        (tmp_path / "src").mkdir()
        inv = InvariantLibrary.directory_must_exist("src")
        result = inv.check(root=tmp_path)
        assert result.passed is True

    def test_dir_missing_fails(self, tmp_path):
        inv = InvariantLibrary.directory_must_exist("missing")
        result = inv.check(root=tmp_path)
        assert result.passed is False


class TestInvariantLibraryForbiddenPattern:
    def test_no_matches_passes(self):
        inv = InvariantLibrary.forbidden_pattern("*.secret")
        result = inv.check(files_touched=["main.py", "README.md"])
        assert result.passed is True

    def test_match_fails(self):
        inv = InvariantLibrary.forbidden_pattern("*.secret")
        result = inv.check(files_touched=["db.secret"])
        assert result.passed is False
        assert "forbidden" in result.message.lower()

    def test_path_pattern(self):
        inv = InvariantLibrary.forbidden_pattern("credentials/*")
        result = inv.check(files_touched=["credentials/api.key"])
        assert result.passed is False


class TestInvariantLibraryNoSecrets:
    def test_clean_files_pass(self):
        inv = InvariantLibrary.no_secrets()
        result = inv.check(files_touched=["main.py", "src/app.py"])
        assert result.passed is True

    def test_env_file_fails(self):
        inv = InvariantLibrary.no_secrets()
        result = inv.check(files_touched=[".env"])
        assert result.passed is False

    def test_key_file_fails(self):
        inv = InvariantLibrary.no_secrets()
        result = inv.check(files_touched=["server.key"])
        assert result.passed is False

    def test_pem_file_fails(self):
        inv = InvariantLibrary.no_secrets()
        result = inv.check(files_touched=["cert.pem"])
        assert result.passed is False

    def test_nested_secret_fails(self):
        inv = InvariantLibrary.no_secrets()
        result = inv.check(files_touched=["config/secrets.yaml"])
        assert result.passed is False


class TestInvariantLibraryMaxFileSize:
    def test_small_files_pass(self, tmp_path):
        (tmp_path / "small.txt").write_text("hello")
        inv = InvariantLibrary.max_file_size(max_kb=10)
        result = inv.check(root=tmp_path, files_touched=["small.txt"])
        assert result.passed is True

    def test_large_file_fails(self, tmp_path):
        (tmp_path / "large.bin").write_bytes(b"x" * 600_000)  # ~600KB
        inv = InvariantLibrary.max_file_size(max_kb=500)
        result = inv.check(root=tmp_path, files_touched=["large.bin"])
        assert result.passed is False

    def test_nonexistent_file_passes(self, tmp_path):
        inv = InvariantLibrary.max_file_size(max_kb=500)
        result = inv.check(root=tmp_path, files_touched=["nope.txt"])
        assert result.passed is True  # File doesn't exist, no size to check
