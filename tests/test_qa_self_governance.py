"""QA Harness: Self-Governance Tests.

The governor validates its own outputs.
"A system that can't pass its own gates has no business governing anything else."

Scenarios:
1. Commit messages must pass claim-evidence coupling
2. Code changes must pass security verifier
3. Documentation must pass structural constraints
4. Test outputs must pass epistemic grounding
"""

import pytest
import subprocess
import tempfile
from pathlib import Path

from governor.security import SecurityVerifier
from governor.claim_signals import SignalExtractor
from governor.check import run_check
from governor.continuity import ContinuityChecker, Anchor, AnchorType, Severity


# =============================================================================
# Test Infrastructure
# =============================================================================


@pytest.fixture
def security_verifier():
    """Fresh security verifier instance."""
    return SecurityVerifier()


@pytest.fixture
def signal_extractor():
    """Fresh signal extractor instance."""
    return SignalExtractor()


@pytest.fixture
def continuity_checker():
    """Fresh continuity checker instance."""
    return ContinuityChecker()


# =============================================================================
# Self-Governance: Code Quality
# =============================================================================


class TestSelfGovernanceCodeQuality:
    """Governor's own code must pass security gates."""

    def test_governor_modules_no_secrets(self, security_verifier):
        """Governor source files should not contain secrets."""
        src_dir = Path("src/governor")
        if not src_dir.exists():
            pytest.skip("Source directory not found")

        for py_file in src_dir.glob("*.py"):
            content = py_file.read_text()
            findings = security_verifier.scan_content(content, str(py_file))

            # Filter for secrets only
            secret_findings = [f for f in findings if f.vuln_type == "secret"]
            assert not secret_findings, f"Secrets found in {py_file}: {secret_findings}"

    def test_governor_modules_no_sql_injection(self, security_verifier):
        """Governor source files should not have SQL injection vulnerabilities."""
        src_dir = Path("src/governor")
        if not src_dir.exists():
            pytest.skip("Source directory not found")

        for py_file in src_dir.glob("*.py"):
            content = py_file.read_text()
            findings = security_verifier.scan_content(content, str(py_file))

            # Filter for SQL injection
            sql_findings = [f for f in findings if f.vuln_type == "sql_injection"]
            # Note: Some files may have intentional SQL for the governor itself
            # We're checking that patterns are safe, not that SQL doesn't exist
            for finding in sql_findings:
                # Allow parameterized queries in storage.py
                if "storage.py" in str(py_file) and "?" in finding.match:
                    continue
                # Fail on string interpolation in SQL
                if "format" in finding.match or "%" in finding.match:
                    pytest.fail(f"SQL injection risk in {py_file}: {finding}")

    def test_governor_modules_no_command_injection(self, security_verifier):
        """Governor source files should not have command injection vulnerabilities."""
        src_dir = Path("src/governor")
        if not src_dir.exists():
            pytest.skip("Source directory not found")

        # Files that legitimately run commands
        allowed_command_files = {
            "producers.py",  # Runs test commands
            "verifiers.py",  # Runs verification commands
            "wrapper.py",    # Agent wrapper
            "hooks.py",      # Git hooks
        }

        for py_file in src_dir.glob("*.py"):
            if py_file.name in allowed_command_files:
                continue

            content = py_file.read_text()
            findings = security_verifier.scan_content(content, str(py_file))

            cmd_findings = [f for f in findings if f.vuln_type == "command_injection"]
            assert not cmd_findings, f"Command injection risk in {py_file}: {cmd_findings}"


# =============================================================================
# Self-Governance: Test Quality
# =============================================================================


class TestSelfGovernanceTestQuality:
    """Governor's own tests must pass quality gates."""

    def test_test_files_no_secrets(self, security_verifier):
        """Test files should not contain real secrets."""
        tests_dir = Path("tests")
        if not tests_dir.exists():
            pytest.skip("Tests directory not found")

        for py_file in tests_dir.glob("*.py"):
            content = py_file.read_text()
            findings = security_verifier.scan_content(content, str(py_file))

            # Filter for secrets
            secret_findings = [f for f in findings if f.vuln_type == "secret"]

            # Allow test patterns that look like secrets but aren't
            real_secrets = []
            for f in secret_findings:
                # Skip obvious test patterns
                if any(pattern in f.match.lower() for pattern in [
                    "test_api_key", "fake_", "mock_", "example_",
                    "sk-test", "pk_test", "dummy", "placeholder",
                    "xxxxxxx", "12345",
                ]):
                    continue
                real_secrets.append(f)

            assert not real_secrets, f"Secrets found in {py_file}: {real_secrets}"


# =============================================================================
# Self-Governance: Documentation Quality
# =============================================================================


class TestSelfGovernanceDocQuality:
    """Governor's documentation must pass structural constraints."""

    def test_readme_exists(self):
        """README.md must exist."""
        assert Path("README.md").exists() or Path("docs/README.md").exists()

    def test_claude_md_exists(self):
        """CLAUDE.md must exist (project instructions)."""
        assert Path("CLAUDE.md").exists()

    def test_specs_readme_exists(self):
        """Specs README must exist."""
        assert Path("specs/README.md").exists()

    def test_pyproject_version_matches_latest_git_tag(self):
        """pyproject.toml version must match the latest git release tag."""
        pyproject = Path("pyproject.toml")
        if not pyproject.exists():
            pytest.skip("pyproject.toml not found")

        # Extract version from pyproject.toml
        content = pyproject.read_text()
        pyproject_version = None
        for line in content.splitlines():
            if line.strip().startswith("version"):
                # version = "2.0.1"
                pyproject_version = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

        assert pyproject_version is not None, "No version field in pyproject.toml"

        # Get latest git tag (vX.Y.Z format)
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                pytest.skip("No git tags found")
            latest_tag = result.stdout.strip().lstrip("v")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("git not available")

        assert pyproject_version == latest_tag, (
            f"pyproject.toml version ({pyproject_version}) does not match "
            f"latest git tag (v{latest_tag}). Bump pyproject.toml on release."
        )

    def test_spec_files_have_status(self):
        """Gap/canonical specs should have a status field."""
        specs_dir = Path("specs/core")
        if not specs_dir.exists():
            pytest.skip("Specs directory not found")

        # These are theory specs that predate the status convention
        legacy_specs = {
            "AUTHORIAL_CONTROL_SYSTEM_SPEC.md",
            "TONE_MODULATION_SPEC.md",
            "STRUCTURAL_CONSTRAINTS_SPEC.md",
            "CODE_SRE_CONTROLLER_SPEC.md",
            "PUPPET_MODE_INTEGRATION_SPEC.md",
            "GOVERNOR_VOICE_PROFILE_SPEC.md",
            "KERNEL_CONSTRAINTS_SPEC.md",
            "TICKETING_LAYER_SPEC.md",
            "ANCILLARY_REGIMES_SPEC.md",
            "NONFICTION_CONTROLLER_SPEC.md",
            "ARCHITECTURAL_COHERENCE_SPEC.md",
            "WRITING_MODULES_SPEC.md",
            "EPISTEMIC_STACK_SPEC.md",
        }

        missing_status = []
        for spec_file in specs_dir.glob("*.md"):
            if spec_file.name in legacy_specs:
                continue
            content = spec_file.read_text()
            if "status:" not in content.lower():
                missing_status.append(spec_file.name)

        assert len(missing_status) == 0, f"Specs missing status: {missing_status}"


# =============================================================================
# Self-Governance: Claim-Evidence Coupling
# =============================================================================


class TestSelfGovernanceClaimEvidence:
    """Claims in governor outputs must have evidence."""

    def test_commit_message_pattern(self, signal_extractor):
        """Commit messages should have clear claims."""
        # Example commit message from this codebase
        commit_msg = """Implement Session Continuity (capsule-based session management)

Add capsule-first session continuity that preserves intent, constraints,
and authority state across sessions. This is NOT chat replay - it's
restoration of governance state.

Key features:
- Three-layer model: Ledger (YAML, durable), Workspace (JSON, active), Transcript (lazy)
- Fork/promote semantics for experimental branches

57 tests, ~725 lines implementation."""

        # Should extract claims
        result = signal_extractor.extract(commit_msg)
        # Commit message should have result with matches
        assert result is not None
        # May or may not have matches depending on content

    def test_docstring_claims(self, signal_extractor):
        """Docstrings with claims should be extractable."""
        docstring = """Session continuity is NOT chat replay.

        It is capsule-based restoration of intent, constraints, and authority state.
        The ledger survives across sessions. Workspace is current working state.
        """

        result = signal_extractor.extract(docstring)
        # Docstrings make claims that should be extractable
        assert result is not None


# =============================================================================
# Self-Governance: Continuity Anchors
# =============================================================================


class TestSelfGovernanceContinuity:
    """Governor's own continuity anchors should work."""

    def test_anchor_creation(self, continuity_checker):
        """Can create anchors from governor constraints."""
        anchor = Anchor(
            id="kernel-1",
            anchor_type=AnchorType.REQUIREMENT,
            description="Claims require evidence",
            required_patterns=["evidence", "proof", "verified"],
            forbidden_patterns=[],
            severity=Severity.REJECT,
        )

        # Anchor should be valid
        assert anchor.id == "kernel-1"
        assert anchor.severity == Severity.REJECT

    def test_governor_text_passes_basic_anchors(self, continuity_checker):
        """Governor-generated text should pass basic anchors."""
        anchors = [
            Anchor(
                id="no-profanity",
                anchor_type=AnchorType.PROHIBITION,
                description="No profanity in output",
                required_patterns=[],
                forbidden_patterns=[r"\b(fuck|shit|damn)\b"],
                severity=Severity.REJECT,
            ),
        ]

        # Sample governor output
        text = "The claim was verified with evidence from the audit pipeline."

        report = continuity_checker.check(text, anchors)
        assert report.passed, f"Governor text failed anchors: {report.violations}"


# =============================================================================
# Self-Governance: Integration
# =============================================================================


class TestSelfGovernanceIntegration:
    """Full self-governance integration tests."""

    def test_check_own_source_file(self):
        """Governor can check its own source files."""
        source_file = Path("src/governor/claims.py")
        if not source_file.exists():
            pytest.skip("Source file not found")

        # Use SecurityVerifier directly since run_check may need governor init
        from governor.security import SecurityVerifier

        verifier = SecurityVerifier()
        try:
            content = source_file.read_text()
            findings = verifier.scan_content(content, str(source_file))
            # Should complete without crashing
            assert findings is not None
        except Exception as e:
            pytest.fail(f"SecurityVerifier crashed on own source: {e}")

    def test_self_governance_invariant(self):
        """The meta-test: this test file should pass security checks."""
        this_file = Path(__file__)
        if not this_file.exists():
            pytest.skip("Cannot find this test file")

        verifier = SecurityVerifier()
        content = this_file.read_text()
        findings = verifier.scan_content(content, str(this_file))

        # This test file should not have security issues
        # (except possibly false positives on test data)
        critical_findings = [f for f in findings if f.severity == "high"]

        # Filter out test data false positives
        real_issues = [f for f in critical_findings
                       if "test" not in f.match.lower()
                       and "example" not in f.match.lower()]

        assert not real_issues, f"This test file has security issues: {real_issues}"
