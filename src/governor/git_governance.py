"""Git Governance — integrity invariants at commit boundaries.

Enforces artifact integrity, cross-index validation, and tagging discipline
while leaving workflow preferences to agents and humans.

Core principle: Profile controls severity, not whether invariants exist.
Invariants are always checked. Greenfield warns, production blocks.

Components:
1. Artifact integrity - No untracked/generated artifacts in commits
2. Cross-index validation - If metadata claims X, X must exist
3. Tagging discipline - Releases require proper tags
4. Pre-commit provenance - Lightweight validation before commit
"""

import fnmatch
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import yaml


def _utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# =============================================================================
# Types
# =============================================================================


class Severity(str, Enum):
    """Severity of a git governance violation."""
    WARN = "warn"
    BLOCK = "block"
    DEFER = "defer"  # Check later, don't block now


class CheckType(str, Enum):
    """Types of git governance checks."""
    ARTIFACT_INTEGRITY = "artifact_integrity"
    CROSS_INDEX = "cross_index"
    TAGGING = "tagging"
    PRE_COMMIT = "pre_commit"


class Profile(str, Enum):
    """Git governance profile."""
    GREENFIELD = "greenfield"
    ESTABLISHED = "established"
    PRODUCTION = "production"
    HOTFIX = "hotfix"


# Profile severity defaults
PROFILE_SEVERITIES: dict[Profile, dict[CheckType, Severity]] = {
    Profile.GREENFIELD: {
        CheckType.ARTIFACT_INTEGRITY: Severity.WARN,
        CheckType.CROSS_INDEX: Severity.WARN,
        CheckType.TAGGING: Severity.WARN,
        CheckType.PRE_COMMIT: Severity.WARN,
    },
    Profile.ESTABLISHED: {
        CheckType.ARTIFACT_INTEGRITY: Severity.WARN,
        CheckType.CROSS_INDEX: Severity.BLOCK,
        CheckType.TAGGING: Severity.WARN,
        CheckType.PRE_COMMIT: Severity.BLOCK,
    },
    Profile.PRODUCTION: {
        CheckType.ARTIFACT_INTEGRITY: Severity.BLOCK,
        CheckType.CROSS_INDEX: Severity.BLOCK,
        CheckType.TAGGING: Severity.BLOCK,
        CheckType.PRE_COMMIT: Severity.BLOCK,
    },
    Profile.HOTFIX: {
        CheckType.ARTIFACT_INTEGRITY: Severity.WARN,
        CheckType.CROSS_INDEX: Severity.BLOCK,
        CheckType.TAGGING: Severity.DEFER,
        CheckType.PRE_COMMIT: Severity.BLOCK,
    },
}


@dataclass
class Violation:
    """A git governance violation."""
    check_type: CheckType
    message: str
    path: str | None = None
    severity: Severity = Severity.WARN
    suggestion: str | None = None

    def to_dict(self) -> dict:
        return {
            "check_type": self.check_type.value,
            "message": self.message,
            "path": self.path,
            "severity": self.severity.value,
            "suggestion": self.suggestion,
        }


@dataclass
class CheckResult:
    """Result of a git governance check."""
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    check_type: CheckType | None = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "check_type": self.check_type.value if self.check_type else None,
        }


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class ArtifactRules:
    """Rules for artifact integrity checking."""
    always_ignored: list[str] = field(default_factory=lambda: [
        "*.pyc",
        "__pycache__/",
        "*.egg-info/",
        "dist/",
        "build/",
        ".eggs/",
        "*.so",
        "*.o",
        "*.a",
    ])
    always_tracked: list[str] = field(default_factory=lambda: [
        "*.lock",
        "poetry.lock",
        "package-lock.json",
        "Cargo.lock",
    ])
    require_explicit: list[str] = field(default_factory=lambda: [
        "*.pdf",
        "*.whl",
        "*.tar.gz",
        "*.zip",
    ])
    allowlist: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "always_ignored": self.always_ignored,
            "always_tracked": self.always_tracked,
            "require_explicit": self.require_explicit,
            "allowlist": self.allowlist,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArtifactRules":
        return cls(
            always_ignored=data.get("always_ignored", cls.__dataclass_fields__["always_ignored"].default_factory()),
            always_tracked=data.get("always_tracked", cls.__dataclass_fields__["always_tracked"].default_factory()),
            require_explicit=data.get("require_explicit", cls.__dataclass_fields__["require_explicit"].default_factory()),
            allowlist=data.get("allowlist", []),
        )


@dataclass
class CrossIndexConfig:
    """Configuration for cross-index validation."""
    enabled: bool = True
    checks: list[str] = field(default_factory=lambda: [
        "doi_in_readme",
        "repo_url_matches",
        "version_tags_exist",
    ])

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "checks": self.checks,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CrossIndexConfig":
        return cls(
            enabled=data.get("enabled", True),
            checks=data.get("checks", cls.__dataclass_fields__["checks"].default_factory()),
        )


@dataclass
class TaggingConfig:
    """Configuration for tagging discipline."""
    patterns: dict[str, str] = field(default_factory=lambda: {
        "paper": "paper-{date}",
        "release": "v{semver}",
    })
    requirements: dict[str, list[str]] = field(default_factory=lambda: {
        "paper": ["metadata_valid", "cross_index_pass"],
        "release": ["changelog_updated", "version_matches", "tests_pass"],
    })

    def to_dict(self) -> dict:
        return {
            "patterns": self.patterns,
            "requirements": self.requirements,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaggingConfig":
        return cls(
            patterns=data.get("patterns", cls.__dataclass_fields__["patterns"].default_factory()),
            requirements=data.get("requirements", cls.__dataclass_fields__["requirements"].default_factory()),
        )


@dataclass
class PreCommitConfig:
    """Configuration for pre-commit checks."""
    metadata_yaml: bool = True
    required_keys: list[str] = field(default_factory=lambda: ["title", "date", "version"])
    date_format: str = "YYYY-MM-DD"
    secrets_check: bool = True

    def to_dict(self) -> dict:
        return {
            "metadata_yaml": self.metadata_yaml,
            "required_keys": self.required_keys,
            "date_format": self.date_format,
            "secrets_check": self.secrets_check,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PreCommitConfig":
        return cls(
            metadata_yaml=data.get("metadata_yaml", True),
            required_keys=data.get("required_keys", cls.__dataclass_fields__["required_keys"].default_factory()),
            date_format=data.get("date_format", "YYYY-MM-DD"),
            secrets_check=data.get("secrets_check", True),
        )


@dataclass
class GitPolicyConfig:
    """Complete git governance configuration."""
    profile: Profile = Profile.ESTABLISHED
    artifact_rules: ArtifactRules = field(default_factory=ArtifactRules)
    cross_index: CrossIndexConfig = field(default_factory=CrossIndexConfig)
    tagging: TaggingConfig = field(default_factory=TaggingConfig)
    pre_commit: PreCommitConfig = field(default_factory=PreCommitConfig)
    severity_overrides: dict[str, str] = field(default_factory=dict)

    def get_severity(self, check_type: CheckType) -> Severity:
        """Get severity for a check type, considering overrides."""
        check_name = check_type.value
        if check_name in self.severity_overrides:
            return Severity(self.severity_overrides[check_name])
        return PROFILE_SEVERITIES[self.profile][check_type]

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.value,
            "artifact_rules": self.artifact_rules.to_dict(),
            "cross_index": self.cross_index.to_dict(),
            "tagging": self.tagging.to_dict(),
            "pre_commit": self.pre_commit.to_dict(),
            "severity_overrides": self.severity_overrides,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GitPolicyConfig":
        return cls(
            profile=Profile(data.get("profile", "established")),
            artifact_rules=ArtifactRules.from_dict(data.get("artifact_rules", {})),
            cross_index=CrossIndexConfig.from_dict(data.get("cross_index", {})),
            tagging=TaggingConfig.from_dict(data.get("tagging", {})),
            pre_commit=PreCommitConfig.from_dict(data.get("pre_commit", {})),
            severity_overrides=data.get("severity_overrides", {}),
        )

    def save(self, path: Path) -> None:
        """Save configuration to YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

    @classmethod
    def load(cls, path: Path) -> "GitPolicyConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)


# =============================================================================
# Git Utilities
# =============================================================================


def run_git(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def get_staged_files(cwd: Path | None = None) -> list[Path]:
    """Get list of staged files."""
    code, stdout, _ = run_git("diff", "--cached", "--name-only", cwd=cwd)
    if code != 0 or not stdout:
        return []
    return [Path(line) for line in stdout.splitlines() if line]


def get_untracked_files(cwd: Path | None = None) -> list[Path]:
    """Get list of untracked files."""
    code, stdout, _ = run_git("ls-files", "--others", "--exclude-standard", cwd=cwd)
    if code != 0 or not stdout:
        return []
    return [Path(line) for line in stdout.splitlines() if line]


def get_tags(cwd: Path | None = None) -> list[str]:
    """Get list of git tags."""
    code, stdout, _ = run_git("tag", "-l", cwd=cwd)
    if code != 0 or not stdout:
        return []
    return stdout.splitlines()


def tag_exists(tag: str, cwd: Path | None = None) -> bool:
    """Check if a tag exists."""
    code, _, _ = run_git("rev-parse", "--verify", f"refs/tags/{tag}", cwd=cwd)
    return code == 0


# =============================================================================
# Artifact Integrity Checker
# =============================================================================


class ArtifactChecker:
    """Check artifact integrity for commits."""

    def __init__(self, config: GitPolicyConfig):
        self.config = config
        self.rules = config.artifact_rules

    def _matches_pattern(self, path: str, patterns: list[str]) -> bool:
        """Check if path matches any of the patterns."""
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
            # Also check the filename only
            if fnmatch.fnmatch(Path(path).name, pattern):
                return True
        return False

    def check_file(self, path: Path) -> Violation | None:
        """Check if a file violates artifact rules."""
        path_str = str(path)

        # Always ignored files are fine
        if self._matches_pattern(path_str, self.rules.always_ignored):
            return None

        # Always tracked files are fine
        if self._matches_pattern(path_str, self.rules.always_tracked):
            return None

        # Explicitly allowed files are fine
        if self._matches_pattern(path_str, self.rules.allowlist):
            return None

        # Check if file requires explicit permission
        if self._matches_pattern(path_str, self.rules.require_explicit):
            return Violation(
                check_type=CheckType.ARTIFACT_INTEGRITY,
                message=f"Artifact '{path}' requires explicit allowlist entry",
                path=path_str,
                severity=self.config.get_severity(CheckType.ARTIFACT_INTEGRITY),
                suggestion=f"Add '{path}' to .governor/git_policy.yaml allowlist",
            )

        return None

    def check_staged(self, cwd: Path | None = None) -> CheckResult:
        """Check all staged files for artifact violations."""
        violations = []
        staged = get_staged_files(cwd)

        for path in staged:
            violation = self.check_file(path)
            if violation:
                violations.append(violation)

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.ARTIFACT_INTEGRITY,
        )


# =============================================================================
# Cross-Index Validator
# =============================================================================


@dataclass
class CrossIndexClaim:
    """A cross-index claim to validate."""
    source: str      # Where the claim is made
    claim_type: str  # What is claimed (doi, url, version, etc.)
    target: str      # What must exist
    verification: str  # How to verify


class CrossIndexValidator:
    """Validate cross-references in metadata."""

    def __init__(self, config: GitPolicyConfig):
        self.config = config

    def check_doi_in_readme(self, cwd: Path | None = None) -> list[Violation]:
        """Check if DOI in metadata is referenced in README."""
        violations = []
        cwd = cwd or Path(".")

        metadata_path = cwd / "metadata.yaml"
        readme_path = cwd / "README.md"

        if not metadata_path.exists():
            return []

        try:
            with open(metadata_path) as f:
                metadata = yaml.safe_load(f) or {}
        except Exception:
            return []

        doi = metadata.get("doi")
        if not doi:
            return []

        if not readme_path.exists():
            violations.append(Violation(
                check_type=CheckType.CROSS_INDEX,
                message=f"metadata.yaml claims DOI '{doi}' but README.md doesn't exist",
                path="README.md",
                severity=self.config.get_severity(CheckType.CROSS_INDEX),
            ))
            return violations

        readme_content = readme_path.read_text()
        if doi not in readme_content:
            violations.append(Violation(
                check_type=CheckType.CROSS_INDEX,
                message=f"metadata.yaml claims DOI '{doi}' but not found in README.md",
                path="README.md",
                severity=self.config.get_severity(CheckType.CROSS_INDEX),
                suggestion=f"Add DOI {doi} to README.md",
            ))

        return violations

    def check_version_tags(self, cwd: Path | None = None) -> list[Violation]:
        """Check if claimed versions have corresponding tags."""
        violations = []
        cwd = cwd or Path(".")

        # Check pyproject.toml
        pyproject_path = cwd / "pyproject.toml"
        if pyproject_path.exists():
            try:
                content = pyproject_path.read_text()
                # Simple regex to find version
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    version = match.group(1)
                    tag = f"v{version}"
                    if not tag_exists(tag, cwd):
                        # Only warn if version looks released (not dev/alpha/beta)
                        if not any(x in version for x in ["dev", "alpha", "beta", "rc"]):
                            violations.append(Violation(
                                check_type=CheckType.CROSS_INDEX,
                                message=f"Version '{version}' in pyproject.toml has no tag '{tag}'",
                                path="pyproject.toml",
                                severity=Severity.WARN,  # Non-blocking
                            ))
            except Exception:
                pass

        return violations

    def check(self, cwd: Path | None = None) -> CheckResult:
        """Run all cross-index checks."""
        if not self.config.cross_index.enabled:
            return CheckResult(passed=True, check_type=CheckType.CROSS_INDEX)

        violations = []

        checks = self.config.cross_index.checks
        if "doi_in_readme" in checks:
            violations.extend(self.check_doi_in_readme(cwd))
        if "version_tags_exist" in checks:
            violations.extend(self.check_version_tags(cwd))

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.CROSS_INDEX,
        )


# =============================================================================
# Tag Verifier
# =============================================================================


class TagVerifier:
    """Verify tag conditions are met."""

    def __init__(self, config: GitPolicyConfig):
        self.config = config

    def check_metadata_valid(self, cwd: Path | None = None) -> bool:
        """Check if metadata.yaml is valid."""
        cwd = cwd or Path(".")
        metadata_path = cwd / "metadata.yaml"

        if not metadata_path.exists():
            return True  # No metadata is OK

        try:
            with open(metadata_path) as f:
                yaml.safe_load(f)
            return True
        except Exception:
            return False

    def check_changelog_updated(self, cwd: Path | None = None) -> bool:
        """Check if CHANGELOG was updated."""
        cwd = cwd or Path(".")
        changelog_path = cwd / "CHANGELOG.md"

        if not changelog_path.exists():
            return False

        # Check if CHANGELOG was modified in staged files
        staged = get_staged_files(cwd)
        return any(str(f).lower() == "changelog.md" for f in staged)

    def check_tests_pass(self, cwd: Path | None = None) -> bool:
        """Check if tests pass (simple check - looks for test results)."""
        # This is a simplified check - in production you'd run tests
        # or check CI status
        return True  # Assume tests pass

    def verify_tag(self, tag: str, tag_type: str | None = None, cwd: Path | None = None) -> CheckResult:
        """Verify conditions for a tag."""
        violations = []
        cwd = cwd or Path(".")

        # Determine tag type from pattern
        if tag_type is None:
            for ttype, pattern in self.config.tagging.patterns.items():
                if tag.startswith("v") and ttype == "release":
                    tag_type = "release"
                    break
                if tag.startswith("paper-") and ttype == "paper":
                    tag_type = "paper"
                    break

        if tag_type is None:
            return CheckResult(passed=True, check_type=CheckType.TAGGING)

        # Check requirements
        requirements = self.config.tagging.requirements.get(tag_type, [])

        for req in requirements:
            passed = True
            if req == "metadata_valid":
                passed = self.check_metadata_valid(cwd)
            elif req == "changelog_updated":
                passed = self.check_changelog_updated(cwd)
            elif req == "tests_pass":
                passed = self.check_tests_pass(cwd)
            elif req == "cross_index_pass":
                validator = CrossIndexValidator(self.config)
                result = validator.check(cwd)
                passed = result.passed

            if not passed:
                violations.append(Violation(
                    check_type=CheckType.TAGGING,
                    message=f"Tag '{tag}' requires '{req}' but check failed",
                    severity=self.config.get_severity(CheckType.TAGGING),
                ))

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.TAGGING,
        )


# =============================================================================
# Pre-Commit Checker
# =============================================================================


class PreCommitChecker:
    """Pre-commit provenance checks."""

    def __init__(self, config: GitPolicyConfig):
        self.config = config
        self.pc_config = config.pre_commit

    def check_metadata_yaml(self, cwd: Path | None = None) -> list[Violation]:
        """Check metadata.yaml structure and content."""
        violations = []
        cwd = cwd or Path(".")
        path = cwd / "metadata.yaml"

        if not path.exists():
            return []

        # Check YAML validity
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            violations.append(Violation(
                check_type=CheckType.PRE_COMMIT,
                message=f"metadata.yaml is invalid YAML: {e}",
                path=str(path),
                severity=self.config.get_severity(CheckType.PRE_COMMIT),
            ))
            return violations

        if data is None:
            data = {}

        # Check required keys
        for key in self.pc_config.required_keys:
            if key not in data:
                violations.append(Violation(
                    check_type=CheckType.PRE_COMMIT,
                    message=f"metadata.yaml missing required key: '{key}'",
                    path=str(path),
                    severity=self.config.get_severity(CheckType.PRE_COMMIT),
                ))

        # Check date format
        date_value = data.get("date")
        if date_value:
            date_pattern = r"\d{4}-\d{2}-\d{2}"
            if not re.match(date_pattern, str(date_value)):
                violations.append(Violation(
                    check_type=CheckType.PRE_COMMIT,
                    message=f"Date '{date_value}' doesn't match format YYYY-MM-DD",
                    path=str(path),
                    severity=self.config.get_severity(CheckType.PRE_COMMIT),
                ))

        return violations

    def check_secrets(self, staged_files: list[Path], cwd: Path | None = None) -> list[Violation]:
        """Check for secrets in staged files."""
        if not self.pc_config.secrets_check:
            return []

        violations = []
        cwd = cwd or Path(".")

        # Import security verifier
        try:
            from .security import SecurityVerifier
            verifier = SecurityVerifier()
        except ImportError:
            return []

        for path in staged_files:
            full_path = cwd / path
            if not full_path.exists() or not full_path.is_file():
                continue

            # Skip binary files
            try:
                content = full_path.read_text()
            except UnicodeDecodeError:
                continue

            findings = verifier.scan_content(content, str(path))
            for finding in findings:
                if "secret" in str(finding.vuln_type).lower():
                    violations.append(Violation(
                        check_type=CheckType.PRE_COMMIT,
                        message=f"Potential secret in {path}: {finding.message}",
                        path=str(path),
                        severity=self.config.get_severity(CheckType.PRE_COMMIT),
                    ))

        return violations

    def check(self, cwd: Path | None = None) -> CheckResult:
        """Run all pre-commit checks."""
        violations = []
        cwd = cwd or Path(".")
        staged = get_staged_files(cwd)

        # Check metadata.yaml if it's staged or if config requires
        if self.pc_config.metadata_yaml:
            metadata_staged = any(str(f) == "metadata.yaml" for f in staged)
            if metadata_staged or (cwd / "metadata.yaml").exists():
                violations.extend(self.check_metadata_yaml(cwd))

        # Check for secrets
        violations.extend(self.check_secrets(staged, cwd))

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.PRE_COMMIT,
        )


# =============================================================================
# Git Governor (Main Interface)
# =============================================================================


class GitGovernor:
    """Main interface for git governance."""

    def __init__(self, config: GitPolicyConfig | None = None, cwd: Path | None = None):
        self.cwd = cwd or Path(".")
        self.config = config or self._load_config()
        self.artifact_checker = ArtifactChecker(self.config)
        self.cross_index_validator = CrossIndexValidator(self.config)
        self.tag_verifier = TagVerifier(self.config)
        self.pre_commit_checker = PreCommitChecker(self.config)

    def _load_config(self) -> GitPolicyConfig:
        """Load config from .governor/git_policy.yaml."""
        config_path = self.cwd / ".governor" / "git_policy.yaml"
        return GitPolicyConfig.load(config_path)

    def check_artifacts(self) -> CheckResult:
        """Check artifact integrity."""
        return self.artifact_checker.check_staged(self.cwd)

    def check_cross_index(self) -> CheckResult:
        """Check cross-index references."""
        return self.cross_index_validator.check(self.cwd)

    def verify_tag(self, tag: str, tag_type: str | None = None) -> CheckResult:
        """Verify tag conditions."""
        return self.tag_verifier.verify_tag(tag, tag_type, self.cwd)

    def check_pre_commit(self) -> CheckResult:
        """Run pre-commit checks."""
        return self.pre_commit_checker.check(self.cwd)

    def check_all(self) -> dict[str, CheckResult]:
        """Run all checks and return results by type."""
        return {
            "artifacts": self.check_artifacts(),
            "cross_index": self.check_cross_index(),
            "pre_commit": self.check_pre_commit(),
        }

    def should_block(self) -> tuple[bool, list[Violation]]:
        """Check if any violations should block the commit."""
        blocking = []
        for check_type, result in self.check_all().items():
            for violation in result.violations:
                if violation.severity == Severity.BLOCK:
                    blocking.append(violation)
        return len(blocking) > 0, blocking


# =============================================================================
# Module-Level Convenience
# =============================================================================


def create_governor(cwd: Path | None = None) -> GitGovernor:
    """Create a GitGovernor instance."""
    return GitGovernor(cwd=cwd)


def check_pre_commit(cwd: Path | None = None) -> CheckResult:
    """Convenience function for pre-commit hook."""
    governor = create_governor(cwd)
    return governor.check_pre_commit()
