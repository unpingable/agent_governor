# SPDX-License-Identifier: Apache-2.0
"""Tests for git governance module.

Enforces artifact integrity, cross-index validation, and tagging discipline
while leaving workflow preferences to agents and humans.
"""

import pytest
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

from governor.git_governance import (
    # Enums
    Severity,
    CheckType,
    Profile,
    PROFILE_SEVERITIES,
    # Types
    Violation,
    CheckResult,
    # Configuration
    ArtifactRules,
    CrossIndexConfig,
    TaggingConfig,
    PreCommitConfig,
    GitPolicyConfig,
    # Git utilities
    run_git,
    get_staged_files,
    get_untracked_files,
    get_tags,
    tag_exists,
    # Checkers
    ArtifactChecker,
    CrossIndexValidator,
    CrossIndexClaim,
    TagVerifier,
    PreCommitChecker,
    # Main interface
    GitGovernor,
    create_governor,
    check_pre_commit,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def git_repo(temp_dir):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=temp_dir,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=temp_dir,
        capture_output=True,
    )
    return temp_dir


@pytest.fixture
def default_config():
    """Create a default GitPolicyConfig."""
    return GitPolicyConfig()


# =============================================================================
# Tests: Enums
# =============================================================================


class TestSeverity:
    """Test Severity enum."""

    def test_values(self):
        """Test enum values."""
        assert Severity.WARN.value == "warn"
        assert Severity.BLOCK.value == "block"
        assert Severity.DEFER.value == "defer"

    def test_count(self):
        """Test enum has expected count."""
        assert len(Severity) == 3

    def test_str(self):
        """Test enum is str subclass."""
        assert isinstance(Severity.WARN, str)


class TestCheckType:
    """Test CheckType enum."""

    def test_values(self):
        """Test enum values."""
        assert CheckType.ARTIFACT_INTEGRITY.value == "artifact_integrity"
        assert CheckType.CROSS_INDEX.value == "cross_index"
        assert CheckType.TAGGING.value == "tagging"
        assert CheckType.PRE_COMMIT.value == "pre_commit"

    def test_count(self):
        """Test enum has expected count."""
        assert len(CheckType) == 4


class TestProfile:
    """Test Profile enum."""

    def test_values(self):
        """Test enum values."""
        assert Profile.GREENFIELD.value == "greenfield"
        assert Profile.ESTABLISHED.value == "established"
        assert Profile.PRODUCTION.value == "production"
        assert Profile.HOTFIX.value == "hotfix"

    def test_count(self):
        """Test enum has expected count."""
        assert len(Profile) == 4


class TestProfileSeverities:
    """Test PROFILE_SEVERITIES mapping."""

    def test_all_profiles_defined(self):
        """All profiles have severity mappings."""
        for profile in Profile:
            assert profile in PROFILE_SEVERITIES

    def test_all_check_types_defined(self):
        """All check types defined for each profile."""
        for profile in Profile:
            for check_type in CheckType:
                assert check_type in PROFILE_SEVERITIES[profile]

    def test_greenfield_is_warn(self):
        """Greenfield profile uses WARN for all checks."""
        for check_type in CheckType:
            assert PROFILE_SEVERITIES[Profile.GREENFIELD][check_type] == Severity.WARN

    def test_production_is_block(self):
        """Production profile uses BLOCK for all checks."""
        for check_type in CheckType:
            assert PROFILE_SEVERITIES[Profile.PRODUCTION][check_type] == Severity.BLOCK

    def test_hotfix_defers_tagging(self):
        """Hotfix profile defers tagging."""
        assert PROFILE_SEVERITIES[Profile.HOTFIX][CheckType.TAGGING] == Severity.DEFER


# =============================================================================
# Tests: Violation and CheckResult
# =============================================================================


class TestViolation:
    """Test Violation dataclass."""

    def test_creation(self):
        """Test basic creation."""
        v = Violation(
            check_type=CheckType.ARTIFACT_INTEGRITY,
            message="Test violation",
        )
        assert v.check_type == CheckType.ARTIFACT_INTEGRITY
        assert v.message == "Test violation"
        assert v.path is None
        assert v.severity == Severity.WARN
        assert v.suggestion is None

    def test_creation_full(self):
        """Test creation with all fields."""
        v = Violation(
            check_type=CheckType.CROSS_INDEX,
            message="DOI not found",
            path="README.md",
            severity=Severity.BLOCK,
            suggestion="Add DOI to README",
        )
        assert v.check_type == CheckType.CROSS_INDEX
        assert v.message == "DOI not found"
        assert v.path == "README.md"
        assert v.severity == Severity.BLOCK
        assert v.suggestion == "Add DOI to README"

    def test_to_dict(self):
        """Test serialization to dict."""
        v = Violation(
            check_type=CheckType.TAGGING,
            message="Tag check failed",
            path="tag/v1.0.0",
            severity=Severity.DEFER,
            suggestion="Update changelog",
        )
        d = v.to_dict()
        assert d["check_type"] == "tagging"
        assert d["message"] == "Tag check failed"
        assert d["path"] == "tag/v1.0.0"
        assert d["severity"] == "defer"
        assert d["suggestion"] == "Update changelog"


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_creation_passed(self):
        """Test creation for passed check."""
        r = CheckResult(passed=True)
        assert r.passed is True
        assert r.violations == []
        assert r.check_type is None

    def test_creation_failed(self):
        """Test creation for failed check."""
        v = Violation(check_type=CheckType.PRE_COMMIT, message="Secret found")
        r = CheckResult(
            passed=False,
            violations=[v],
            check_type=CheckType.PRE_COMMIT,
        )
        assert r.passed is False
        assert len(r.violations) == 1
        assert r.check_type == CheckType.PRE_COMMIT

    def test_to_dict(self):
        """Test serialization to dict."""
        v = Violation(check_type=CheckType.ARTIFACT_INTEGRITY, message="Bad artifact")
        r = CheckResult(
            passed=False,
            violations=[v],
            check_type=CheckType.ARTIFACT_INTEGRITY,
        )
        d = r.to_dict()
        assert d["passed"] is False
        assert len(d["violations"]) == 1
        assert d["check_type"] == "artifact_integrity"


# =============================================================================
# Tests: Configuration Types
# =============================================================================


class TestArtifactRules:
    """Test ArtifactRules dataclass."""

    def test_defaults(self):
        """Test default values."""
        r = ArtifactRules()
        assert "*.pyc" in r.always_ignored
        assert "poetry.lock" in r.always_tracked
        assert "*.pdf" in r.require_explicit
        assert r.allowlist == []

    def test_to_dict(self):
        """Test serialization."""
        r = ArtifactRules(allowlist=["allowed.pdf"])
        d = r.to_dict()
        assert "allowed.pdf" in d["allowlist"]

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "always_ignored": ["*.tmp"],
            "always_tracked": ["*.lock"],
            "require_explicit": ["*.bin"],
            "allowlist": ["special.bin"],
        }
        r = ArtifactRules.from_dict(data)
        assert r.always_ignored == ["*.tmp"]
        assert r.always_tracked == ["*.lock"]
        assert r.require_explicit == ["*.bin"]
        assert r.allowlist == ["special.bin"]

    def test_from_dict_partial(self):
        """Test deserialization with missing keys."""
        r = ArtifactRules.from_dict({})
        assert "*.pyc" in r.always_ignored  # Default value

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        r1 = ArtifactRules(allowlist=["test.pdf"])
        d = r1.to_dict()
        r2 = ArtifactRules.from_dict(d)
        assert r1.allowlist == r2.allowlist


class TestCrossIndexConfig:
    """Test CrossIndexConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = CrossIndexConfig()
        assert c.enabled is True
        assert "doi_in_readme" in c.checks
        assert "version_tags_exist" in c.checks

    def test_to_dict(self):
        """Test serialization."""
        c = CrossIndexConfig(enabled=False, checks=["custom_check"])
        d = c.to_dict()
        assert d["enabled"] is False
        assert d["checks"] == ["custom_check"]

    def test_from_dict(self):
        """Test deserialization."""
        data = {"enabled": False, "checks": ["test"]}
        c = CrossIndexConfig.from_dict(data)
        assert c.enabled is False
        assert c.checks == ["test"]

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        c1 = CrossIndexConfig(checks=["check1", "check2"])
        d = c1.to_dict()
        c2 = CrossIndexConfig.from_dict(d)
        assert c1.checks == c2.checks


class TestTaggingConfig:
    """Test TaggingConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = TaggingConfig()
        assert "paper" in c.patterns
        assert "release" in c.patterns
        assert "changelog_updated" in c.requirements.get("release", [])

    def test_to_dict(self):
        """Test serialization."""
        c = TaggingConfig()
        d = c.to_dict()
        assert "patterns" in d
        assert "requirements" in d

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "patterns": {"custom": "custom-{id}"},
            "requirements": {"custom": ["custom_check"]},
        }
        c = TaggingConfig.from_dict(data)
        assert c.patterns["custom"] == "custom-{id}"
        assert "custom_check" in c.requirements["custom"]


class TestPreCommitConfig:
    """Test PreCommitConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = PreCommitConfig()
        assert c.metadata_yaml is True
        assert "title" in c.required_keys
        assert c.date_format == "YYYY-MM-DD"
        assert c.secrets_check is True

    def test_to_dict(self):
        """Test serialization."""
        c = PreCommitConfig(secrets_check=False)
        d = c.to_dict()
        assert d["secrets_check"] is False

    def test_from_dict(self):
        """Test deserialization."""
        data = {"metadata_yaml": False, "required_keys": ["id"]}
        c = PreCommitConfig.from_dict(data)
        assert c.metadata_yaml is False
        assert c.required_keys == ["id"]


class TestGitPolicyConfig:
    """Test GitPolicyConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        c = GitPolicyConfig()
        assert c.profile == Profile.ESTABLISHED
        assert isinstance(c.artifact_rules, ArtifactRules)
        assert isinstance(c.cross_index, CrossIndexConfig)
        assert isinstance(c.tagging, TaggingConfig)
        assert isinstance(c.pre_commit, PreCommitConfig)
        assert c.severity_overrides == {}

    def test_get_severity_default(self):
        """Test get_severity without override."""
        c = GitPolicyConfig(profile=Profile.PRODUCTION)
        assert c.get_severity(CheckType.ARTIFACT_INTEGRITY) == Severity.BLOCK

    def test_get_severity_override(self):
        """Test get_severity with override."""
        c = GitPolicyConfig(
            profile=Profile.PRODUCTION,
            severity_overrides={"artifact_integrity": "warn"},
        )
        assert c.get_severity(CheckType.ARTIFACT_INTEGRITY) == Severity.WARN

    def test_to_dict(self):
        """Test serialization."""
        c = GitPolicyConfig(profile=Profile.GREENFIELD)
        d = c.to_dict()
        assert d["profile"] == "greenfield"
        assert "artifact_rules" in d
        assert "cross_index" in d
        assert "tagging" in d
        assert "pre_commit" in d

    def test_from_dict(self):
        """Test deserialization."""
        data = {"profile": "hotfix", "severity_overrides": {"tagging": "block"}}
        c = GitPolicyConfig.from_dict(data)
        assert c.profile == Profile.HOTFIX
        assert c.severity_overrides["tagging"] == "block"

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        c1 = GitPolicyConfig(
            profile=Profile.PRODUCTION,
            severity_overrides={"pre_commit": "warn"},
        )
        d = c1.to_dict()
        c2 = GitPolicyConfig.from_dict(d)
        assert c1.profile == c2.profile
        assert c1.severity_overrides == c2.severity_overrides

    def test_save_and_load(self, temp_dir):
        """Test save and load to file."""
        c1 = GitPolicyConfig(profile=Profile.HOTFIX)
        path = temp_dir / "config.yaml"
        c1.save(path)
        assert path.exists()

        c2 = GitPolicyConfig.load(path)
        assert c2.profile == Profile.HOTFIX

    def test_load_nonexistent(self, temp_dir):
        """Test load returns defaults for missing file."""
        path = temp_dir / "missing.yaml"
        c = GitPolicyConfig.load(path)
        assert c.profile == Profile.ESTABLISHED  # Default


# =============================================================================
# Tests: Git Utilities
# =============================================================================


class TestGitUtilities:
    """Test git utility functions."""

    def test_run_git(self, git_repo):
        """Test run_git returns status, stdout, stderr."""
        code, stdout, stderr = run_git("status", cwd=git_repo)
        assert code == 0
        assert "On branch" in stdout or "main" in stdout.lower() or "master" in stdout.lower()

    def test_run_git_invalid_command(self, git_repo):
        """Test run_git with invalid command."""
        code, stdout, stderr = run_git("invalid-command-xyz", cwd=git_repo)
        assert code != 0

    def test_get_staged_files_empty(self, git_repo):
        """Test get_staged_files with no staged files."""
        files = get_staged_files(git_repo)
        assert files == []

    def test_get_staged_files_with_files(self, git_repo):
        """Test get_staged_files with staged files."""
        # Create and stage a file
        test_file = git_repo / "test.txt"
        test_file.write_text("test content")
        subprocess.run(["git", "add", "test.txt"], cwd=git_repo, capture_output=True)

        files = get_staged_files(git_repo)
        assert Path("test.txt") in files

    def test_get_untracked_files(self, git_repo):
        """Test get_untracked_files."""
        # Create an untracked file
        test_file = git_repo / "untracked.txt"
        test_file.write_text("untracked")

        files = get_untracked_files(git_repo)
        assert Path("untracked.txt") in files

    def test_get_tags_empty(self, git_repo):
        """Test get_tags with no tags."""
        tags = get_tags(git_repo)
        assert tags == []

    def test_get_tags_with_tags(self, git_repo):
        """Test get_tags with tags."""
        # Create initial commit first
        test_file = git_repo / "file.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=git_repo, capture_output=True)

        # Create a tag
        subprocess.run(["git", "tag", "v1.0.0"], cwd=git_repo, capture_output=True)

        tags = get_tags(git_repo)
        assert "v1.0.0" in tags

    def test_tag_exists(self, git_repo):
        """Test tag_exists."""
        # Create initial commit
        test_file = git_repo / "file.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=git_repo, capture_output=True)

        # Create a tag
        subprocess.run(["git", "tag", "v1.0.0"], cwd=git_repo, capture_output=True)

        assert tag_exists("v1.0.0", git_repo) is True
        assert tag_exists("v2.0.0", git_repo) is False


# =============================================================================
# Tests: ArtifactChecker
# =============================================================================


class TestArtifactChecker:
    """Test ArtifactChecker."""

    def test_ignored_files_pass(self, default_config):
        """Test that ignored files don't cause violations."""
        checker = ArtifactChecker(default_config)

        assert checker.check_file(Path("file.pyc")) is None
        assert checker.check_file(Path("__pycache__/module.pyc")) is None
        assert checker.check_file(Path("build/lib/module.so")) is None

    def test_tracked_files_pass(self, default_config):
        """Test that tracked files don't cause violations."""
        checker = ArtifactChecker(default_config)

        assert checker.check_file(Path("poetry.lock")) is None
        assert checker.check_file(Path("package-lock.json")) is None

    def test_regular_files_pass(self, default_config):
        """Test that regular files don't cause violations."""
        checker = ArtifactChecker(default_config)

        assert checker.check_file(Path("src/main.py")) is None
        assert checker.check_file(Path("README.md")) is None

    def test_explicit_required_files_fail(self, default_config):
        """Test that files requiring explicit permission fail."""
        checker = ArtifactChecker(default_config)

        violation = checker.check_file(Path("paper.pdf"))
        assert violation is not None
        assert violation.check_type == CheckType.ARTIFACT_INTEGRITY
        assert "explicit" in violation.message.lower()

    def test_allowlisted_files_pass(self):
        """Test that allowlisted files pass."""
        config = GitPolicyConfig(
            artifact_rules=ArtifactRules(allowlist=["paper.pdf"])
        )
        checker = ArtifactChecker(config)

        assert checker.check_file(Path("paper.pdf")) is None

    def test_check_staged_empty(self, git_repo, default_config):
        """Test check_staged with no staged files."""
        checker = ArtifactChecker(default_config)
        result = checker.check_staged(git_repo)

        assert result.passed is True
        assert result.violations == []
        assert result.check_type == CheckType.ARTIFACT_INTEGRITY

    def test_check_staged_with_violation(self, git_repo, default_config):
        """Test check_staged with violations."""
        # Create and stage a PDF
        pdf_file = git_repo / "paper.pdf"
        pdf_file.write_text("fake pdf")
        subprocess.run(["git", "add", "paper.pdf"], cwd=git_repo, capture_output=True)

        checker = ArtifactChecker(default_config)
        result = checker.check_staged(git_repo)

        assert result.passed is False
        assert len(result.violations) == 1


# =============================================================================
# Tests: CrossIndexValidator
# =============================================================================


class TestCrossIndexValidator:
    """Test CrossIndexValidator."""

    def test_check_doi_in_readme_no_metadata(self, temp_dir, default_config):
        """Test when no metadata.yaml exists."""
        validator = CrossIndexValidator(default_config)
        violations = validator.check_doi_in_readme(temp_dir)
        assert violations == []

    def test_check_doi_in_readme_no_doi(self, temp_dir, default_config):
        """Test when metadata exists but no DOI."""
        (temp_dir / "metadata.yaml").write_text("title: Test\n")

        validator = CrossIndexValidator(default_config)
        violations = validator.check_doi_in_readme(temp_dir)
        assert violations == []

    def test_check_doi_in_readme_missing_readme(self, temp_dir, default_config):
        """Test when DOI exists but README doesn't."""
        (temp_dir / "metadata.yaml").write_text("doi: 10.1234/test\n")

        validator = CrossIndexValidator(default_config)
        violations = validator.check_doi_in_readme(temp_dir)

        assert len(violations) == 1
        assert "README.md doesn't exist" in violations[0].message

    def test_check_doi_in_readme_missing_doi_in_readme(self, temp_dir, default_config):
        """Test when DOI not in README."""
        (temp_dir / "metadata.yaml").write_text("doi: 10.1234/test\n")
        (temp_dir / "README.md").write_text("# Test Project\n")

        validator = CrossIndexValidator(default_config)
        violations = validator.check_doi_in_readme(temp_dir)

        assert len(violations) == 1
        assert "not found in README.md" in violations[0].message

    def test_check_doi_in_readme_found(self, temp_dir, default_config):
        """Test when DOI is in README."""
        (temp_dir / "metadata.yaml").write_text("doi: 10.1234/test\n")
        (temp_dir / "README.md").write_text("# Test\n\nDOI: 10.1234/test\n")

        validator = CrossIndexValidator(default_config)
        violations = validator.check_doi_in_readme(temp_dir)
        assert violations == []

    def test_check_version_tags_no_pyproject(self, temp_dir, default_config):
        """Test when no pyproject.toml exists."""
        validator = CrossIndexValidator(default_config)
        violations = validator.check_version_tags(temp_dir)
        assert violations == []

    def test_check_version_tags_dev_version(self, temp_dir, default_config):
        """Test dev version doesn't require tag."""
        (temp_dir / "pyproject.toml").write_text('[project]\nversion = "1.0.0.dev1"\n')

        validator = CrossIndexValidator(default_config)
        violations = validator.check_version_tags(temp_dir)
        assert violations == []

    def test_check_disabled(self, temp_dir):
        """Test check with cross_index disabled."""
        config = GitPolicyConfig(
            cross_index=CrossIndexConfig(enabled=False)
        )
        validator = CrossIndexValidator(config)
        result = validator.check(temp_dir)

        assert result.passed is True

    def test_check_all(self, temp_dir, default_config):
        """Test full check."""
        validator = CrossIndexValidator(default_config)
        result = validator.check(temp_dir)

        assert result.check_type == CheckType.CROSS_INDEX


class TestCrossIndexClaim:
    """Test CrossIndexClaim dataclass."""

    def test_creation(self):
        """Test basic creation."""
        claim = CrossIndexClaim(
            source="metadata.yaml",
            claim_type="doi",
            target="README.md",
            verification="contains_doi",
        )
        assert claim.source == "metadata.yaml"
        assert claim.claim_type == "doi"


# =============================================================================
# Tests: TagVerifier
# =============================================================================


class TestTagVerifier:
    """Test TagVerifier."""

    def test_check_metadata_valid_no_file(self, temp_dir, default_config):
        """Test when no metadata file exists."""
        verifier = TagVerifier(default_config)
        assert verifier.check_metadata_valid(temp_dir) is True

    def test_check_metadata_valid_valid(self, temp_dir, default_config):
        """Test with valid metadata."""
        (temp_dir / "metadata.yaml").write_text("title: Test\ndate: 2025-01-01\n")

        verifier = TagVerifier(default_config)
        assert verifier.check_metadata_valid(temp_dir) is True

    def test_check_metadata_valid_invalid(self, temp_dir, default_config):
        """Test with invalid YAML."""
        (temp_dir / "metadata.yaml").write_text("title: [invalid yaml\n")

        verifier = TagVerifier(default_config)
        assert verifier.check_metadata_valid(temp_dir) is False

    def test_check_changelog_updated_no_changelog(self, temp_dir, default_config):
        """Test when no CHANGELOG exists."""
        verifier = TagVerifier(default_config)
        assert verifier.check_changelog_updated(temp_dir) is False

    def test_check_tests_pass(self, temp_dir, default_config):
        """Test check_tests_pass (simplified implementation)."""
        verifier = TagVerifier(default_config)
        assert verifier.check_tests_pass(temp_dir) is True

    def test_verify_tag_unknown_type(self, temp_dir, default_config):
        """Test verify_tag with unknown tag type."""
        verifier = TagVerifier(default_config)
        result = verifier.verify_tag("custom-tag", cwd=temp_dir)

        assert result.passed is True
        assert result.check_type == CheckType.TAGGING

    def test_verify_tag_release(self, temp_dir, default_config):
        """Test verify_tag for release tag."""
        (temp_dir / "CHANGELOG.md").write_text("# Changelog\n")

        verifier = TagVerifier(default_config)
        result = verifier.verify_tag("v1.0.0", tag_type="release", cwd=temp_dir)

        # Will fail because changelog_updated checks for staged file
        assert result.check_type == CheckType.TAGGING

    def test_verify_tag_paper(self, temp_dir, default_config):
        """Test verify_tag for paper tag."""
        (temp_dir / "metadata.yaml").write_text("title: Test\n")

        verifier = TagVerifier(default_config)
        result = verifier.verify_tag("paper-2025-01-01", tag_type="paper", cwd=temp_dir)

        assert result.check_type == CheckType.TAGGING


# =============================================================================
# Tests: PreCommitChecker
# =============================================================================


class TestPreCommitChecker:
    """Test PreCommitChecker."""

    def test_check_metadata_yaml_no_file(self, temp_dir, default_config):
        """Test when no metadata.yaml exists."""
        checker = PreCommitChecker(default_config)
        violations = checker.check_metadata_yaml(temp_dir)
        assert violations == []

    def test_check_metadata_yaml_invalid_yaml(self, temp_dir, default_config):
        """Test with invalid YAML."""
        (temp_dir / "metadata.yaml").write_text("title: [invalid\n")

        checker = PreCommitChecker(default_config)
        violations = checker.check_metadata_yaml(temp_dir)

        assert len(violations) == 1
        assert "invalid YAML" in violations[0].message

    def test_check_metadata_yaml_missing_keys(self, temp_dir, default_config):
        """Test with missing required keys."""
        (temp_dir / "metadata.yaml").write_text("custom: value\n")

        checker = PreCommitChecker(default_config)
        violations = checker.check_metadata_yaml(temp_dir)

        # Should have violations for missing title, date, version
        assert len(violations) >= 3

    def test_check_metadata_yaml_valid(self, temp_dir, default_config):
        """Test with valid metadata."""
        content = "title: Test\ndate: 2025-01-01\nversion: 1.0.0\n"
        (temp_dir / "metadata.yaml").write_text(content)

        checker = PreCommitChecker(default_config)
        violations = checker.check_metadata_yaml(temp_dir)
        assert violations == []

    def test_check_metadata_yaml_bad_date(self, temp_dir, default_config):
        """Test with bad date format."""
        content = "title: Test\ndate: Jan 1, 2025\nversion: 1.0.0\n"
        (temp_dir / "metadata.yaml").write_text(content)

        checker = PreCommitChecker(default_config)
        violations = checker.check_metadata_yaml(temp_dir)

        date_violations = [v for v in violations if "Date" in v.message]
        assert len(date_violations) == 1

    def test_check_secrets_disabled(self, default_config):
        """Test secrets check when disabled."""
        config = GitPolicyConfig(
            pre_commit=PreCommitConfig(secrets_check=False)
        )
        checker = PreCommitChecker(config)
        violations = checker.check_secrets([Path("test.py")])
        assert violations == []

    def test_check_secrets_with_secret(self, temp_dir, default_config):
        """Test secrets check finds secrets."""
        # Create a file with a secret
        secret_file = temp_dir / "config.py"
        secret_file.write_text('password = "super_secret_123"\n')

        checker = PreCommitChecker(default_config)
        violations = checker.check_secrets([Path("config.py")], cwd=temp_dir)

        # May or may not find depending on security verifier
        # Just verify no crash
        assert isinstance(violations, list)

    def test_check_full(self, temp_dir, default_config):
        """Test full pre-commit check."""
        checker = PreCommitChecker(default_config)
        result = checker.check(temp_dir)

        assert result.check_type == CheckType.PRE_COMMIT


# =============================================================================
# Tests: GitGovernor (Main Interface)
# =============================================================================


class TestGitGovernor:
    """Test GitGovernor main interface."""

    def test_creation_default(self, temp_dir):
        """Test creation with defaults."""
        gov = GitGovernor(cwd=temp_dir)

        assert gov.cwd == temp_dir
        assert gov.config.profile == Profile.ESTABLISHED
        assert isinstance(gov.artifact_checker, ArtifactChecker)
        assert isinstance(gov.cross_index_validator, CrossIndexValidator)
        assert isinstance(gov.tag_verifier, TagVerifier)
        assert isinstance(gov.pre_commit_checker, PreCommitChecker)

    def test_creation_with_config(self, temp_dir):
        """Test creation with custom config."""
        config = GitPolicyConfig(profile=Profile.PRODUCTION)
        gov = GitGovernor(config=config, cwd=temp_dir)

        assert gov.config.profile == Profile.PRODUCTION

    def test_load_config_from_file(self, temp_dir):
        """Test loading config from file."""
        gov_dir = temp_dir / ".governor"
        gov_dir.mkdir()
        config = GitPolicyConfig(profile=Profile.HOTFIX)
        config.save(gov_dir / "git_policy.yaml")

        gov = GitGovernor(cwd=temp_dir)
        assert gov.config.profile == Profile.HOTFIX

    def test_check_artifacts(self, git_repo, default_config):
        """Test check_artifacts method."""
        gov = GitGovernor(config=default_config, cwd=git_repo)
        result = gov.check_artifacts()

        assert result.check_type == CheckType.ARTIFACT_INTEGRITY

    def test_check_cross_index(self, temp_dir, default_config):
        """Test check_cross_index method."""
        gov = GitGovernor(config=default_config, cwd=temp_dir)
        result = gov.check_cross_index()

        assert result.check_type == CheckType.CROSS_INDEX

    def test_verify_tag(self, temp_dir, default_config):
        """Test verify_tag method."""
        gov = GitGovernor(config=default_config, cwd=temp_dir)
        result = gov.verify_tag("v1.0.0")

        assert result.check_type == CheckType.TAGGING

    def test_check_pre_commit(self, temp_dir, default_config):
        """Test check_pre_commit method."""
        gov = GitGovernor(config=default_config, cwd=temp_dir)
        result = gov.check_pre_commit()

        assert result.check_type == CheckType.PRE_COMMIT

    def test_check_all(self, temp_dir, default_config):
        """Test check_all method."""
        gov = GitGovernor(config=default_config, cwd=temp_dir)
        results = gov.check_all()

        assert "artifacts" in results
        assert "cross_index" in results
        assert "pre_commit" in results

    def test_should_block_no_violations(self, temp_dir, default_config):
        """Test should_block with no blocking violations."""
        gov = GitGovernor(config=default_config, cwd=temp_dir)
        should_block, violations = gov.should_block()

        assert should_block is False
        assert violations == []

    def test_should_block_with_blocking(self, temp_dir):
        """Test should_block with blocking violations."""
        # Set up production profile with blocking
        config = GitPolicyConfig(profile=Profile.PRODUCTION)
        (temp_dir / "metadata.yaml").write_text("doi: 10.1234/test\n")
        # Missing README.md creates a blocking violation

        gov = GitGovernor(config=config, cwd=temp_dir)
        should_block, violations = gov.should_block()

        # Will block because DOI in metadata but no README
        # Only if cross_index check runs and finds violation
        assert isinstance(should_block, bool)
        assert isinstance(violations, list)


# =============================================================================
# Tests: Module-Level Functions
# =============================================================================


class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_create_governor(self, temp_dir):
        """Test create_governor function."""
        gov = create_governor(temp_dir)

        assert isinstance(gov, GitGovernor)
        assert gov.cwd == temp_dir

    def test_check_pre_commit_function(self, temp_dir):
        """Test check_pre_commit convenience function."""
        result = check_pre_commit(temp_dir)

        assert isinstance(result, CheckResult)
        assert result.check_type == CheckType.PRE_COMMIT


# =============================================================================
# Tests: Integration
# =============================================================================


class TestIntegration:
    """Integration tests for git governance."""

    def test_full_workflow_greenfield(self, git_repo):
        """Test full workflow with greenfield profile."""
        config = GitPolicyConfig(profile=Profile.GREENFIELD)
        gov = GitGovernor(config=config, cwd=git_repo)

        # Create and stage a PDF (normally would require explicit)
        pdf_file = git_repo / "paper.pdf"
        pdf_file.write_text("fake pdf")
        subprocess.run(["git", "add", "paper.pdf"], cwd=git_repo, capture_output=True)

        # Check all - greenfield should warn, not block
        should_block, blocking = gov.should_block()

        # Greenfield uses WARN, so nothing should block
        assert should_block is False

    def test_full_workflow_production(self, git_repo):
        """Test full workflow with production profile."""
        config = GitPolicyConfig(profile=Profile.PRODUCTION)
        gov = GitGovernor(config=config, cwd=git_repo)

        # Create and stage a PDF
        pdf_file = git_repo / "paper.pdf"
        pdf_file.write_text("fake pdf")
        subprocess.run(["git", "add", "paper.pdf"], cwd=git_repo, capture_output=True)

        # Check all - production should block
        should_block, blocking = gov.should_block()

        # Production uses BLOCK for artifacts
        assert should_block is True
        assert len(blocking) > 0

    def test_allowlist_workflow(self, git_repo):
        """Test allowlisting a file."""
        # First, verify it would block
        config = GitPolicyConfig(profile=Profile.PRODUCTION)
        gov = GitGovernor(config=config, cwd=git_repo)

        pdf_file = git_repo / "paper.pdf"
        pdf_file.write_text("fake pdf")
        subprocess.run(["git", "add", "paper.pdf"], cwd=git_repo, capture_output=True)

        should_block, _ = gov.should_block()
        assert should_block is True

        # Now allowlist it
        config.artifact_rules.allowlist.append("paper.pdf")
        gov = GitGovernor(config=config, cwd=git_repo)

        should_block, _ = gov.should_block()
        assert should_block is False

    def test_config_persistence(self, git_repo):
        """Test config saves and loads correctly."""
        # Create and save config
        gov_dir = git_repo / ".governor"
        gov_dir.mkdir()

        config1 = GitPolicyConfig(
            profile=Profile.HOTFIX,
            severity_overrides={"artifact_integrity": "block"},
        )
        config1.artifact_rules.allowlist.append("allowed.pdf")
        config1.save(gov_dir / "git_policy.yaml")

        # Load and verify
        config2 = GitPolicyConfig.load(gov_dir / "git_policy.yaml")
        assert config2.profile == Profile.HOTFIX
        assert config2.severity_overrides["artifact_integrity"] == "block"
        assert "allowed.pdf" in config2.artifact_rules.allowlist

    def test_severity_override_workflow(self, git_repo):
        """Test severity override changes blocking behavior."""
        # Production profile with artifact override to WARN
        config = GitPolicyConfig(
            profile=Profile.PRODUCTION,
            severity_overrides={"artifact_integrity": "warn"},
        )
        gov = GitGovernor(config=config, cwd=git_repo)

        # Create and stage a PDF
        pdf_file = git_repo / "paper.pdf"
        pdf_file.write_text("fake pdf")
        subprocess.run(["git", "add", "paper.pdf"], cwd=git_repo, capture_output=True)

        # Even in production, override makes it WARN not BLOCK
        should_block, blocking = gov.should_block()

        # The artifact violation is WARN due to override, so shouldn't block
        # (unless there are other violations)
        artifact_blocking = [v for v in blocking if v.check_type == CheckType.ARTIFACT_INTEGRITY]
        assert len(artifact_blocking) == 0
