"""Tests for the security verifier."""

import pytest
from pathlib import Path

from governor.security import (
    VulnerabilityType,
    Severity,
    SecurityFinding,
    SecurityConfig,
    SecurityVerifier,
    quick_scan,
)


class TestSecurityTypes:
    """Tests for security types."""

    def test_vulnerability_types_exist(self):
        """Test that all vulnerability types are defined."""
        assert VulnerabilityType.SECRET_LEAK
        assert VulnerabilityType.SQL_INJECTION
        assert VulnerabilityType.COMMAND_INJECTION
        assert VulnerabilityType.XSS
        assert VulnerabilityType.PATH_TRAVERSAL
        assert VulnerabilityType.HARDCODED_CREDENTIAL
        assert VulnerabilityType.INSECURE_RANDOM
        assert VulnerabilityType.INSECURE_HASH
        assert VulnerabilityType.INSECURE_DESERIALIZATION
        assert VulnerabilityType.DEBUG_CODE

    def test_severity_ordering(self):
        """Test severity ordering."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"

    def test_security_finding_to_dict(self):
        """Test SecurityFinding serialization."""
        finding = SecurityFinding(
            vuln_type=VulnerabilityType.SECRET_LEAK,
            severity=Severity.CRITICAL,
            file_path="test.py",
            line_number=10,
            line_content="api_key = 'sk-1234'",
            message="API key detected",
            pattern_matched="api_key = 'sk-1234'",
            suggestion="Use environment variables",
        )

        data = finding.to_dict()
        assert data["vuln_type"] == "secret_leak"
        assert data["severity"] == "critical"
        assert data["file_path"] == "test.py"
        assert data["line_number"] == 10


class TestSecurityConfig:
    """Tests for SecurityConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = SecurityConfig()
        assert config.check_secrets is True
        assert config.check_sql_injection is True
        assert config.min_severity == Severity.LOW

    def test_config_serialization(self):
        """Test config serialization."""
        config = SecurityConfig(
            check_secrets=False,
            min_severity=Severity.HIGH,
        )

        data = config.to_dict()
        restored = SecurityConfig.from_dict(data)

        assert restored.check_secrets is False
        assert restored.min_severity == Severity.HIGH


class TestSecurityVerifier:
    """Tests for SecurityVerifier."""

    def test_detect_api_key(self):
        """Test detection of API keys."""
        content = '''
api_key = "sk-1234567890abcdefghij1234567890abcdefghij12345678"
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.SECRET_LEAK for f in findings)

    def test_detect_aws_key(self):
        """Test detection of AWS keys."""
        content = '''
aws_access_key = "AKIAIOSFODNN7EXAMPLE"
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any("AWS" in f.message for f in findings)

    def test_detect_openai_key(self):
        """Test detection of OpenAI keys."""
        content = '''
openai_key = "sk-abcdefghijklmnopqrstuvwxyz12345678901234567890AB"
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1

    def test_detect_password_in_code(self):
        """Test detection of hardcoded passwords."""
        content = '''
password = "admin"
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.HARDCODED_CREDENTIAL for f in findings)

    def test_detect_sql_injection(self):
        """Test detection of SQL injection."""
        content = '''
def get_user(name):
    cursor.execute("SELECT * FROM users WHERE name = '" + name + "'")
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.SQL_INJECTION for f in findings)

    def test_detect_sql_injection_fstring(self):
        """Test detection of SQL injection with f-strings."""
        content = '''
def get_user(name):
    cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.SQL_INJECTION for f in findings)

    def test_detect_command_injection(self):
        """Test detection of command injection."""
        content = '''
import os
os.system("ls " + user_input)
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.COMMAND_INJECTION for f in findings)

    def test_detect_eval(self):
        """Test detection of eval with user input."""
        content = '''
result = eval(user_input + "more code")
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.COMMAND_INJECTION for f in findings)

    def test_detect_shell_true(self):
        """Test detection of shell=True."""
        content = '''
subprocess.run(cmd, shell=True)
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        # shell=True is medium severity (may be intentional)
        assert any(f.severity == Severity.MEDIUM for f in findings)

    def test_detect_xss_innerhtml(self):
        """Test detection of XSS via innerHTML."""
        content = '''
element.innerHTML = userInput + "</div>";
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.js")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.XSS for f in findings)

    def test_detect_dangerously_set_inner_html(self):
        """Test detection of dangerouslySetInnerHTML."""
        content = '''
<div dangerouslySetInnerHTML={{__html: content}} />
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "component.jsx")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.XSS for f in findings)

    def test_detect_insecure_random(self):
        """Test detection of insecure random."""
        content = '''
token = random.random()
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.INSECURE_RANDOM for f in findings)

    def test_detect_md5(self):
        """Test detection of MD5 for security."""
        content = '''
hash = hashlib.md5(password.encode()).hexdigest()
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.INSECURE_HASH for f in findings)

    def test_detect_pickle_load(self):
        """Test detection of pickle.load."""
        content = '''
data = pickle.load(untrusted_file)
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.INSECURE_DESERIALIZATION for f in findings)

    def test_detect_debug_code(self):
        """Test detection of debug code."""
        content = '''
console.log(secret);
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.js")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.DEBUG_CODE for f in findings)

    def test_detect_breakpoint(self):
        """Test detection of breakpoint()."""
        content = '''
breakpoint()
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) >= 1
        assert any(f.vuln_type == VulnerabilityType.DEBUG_CODE for f in findings)

    def test_nosec_comment_ignored(self):
        """Test that nosec comments are ignored."""
        content = '''
password = "admin"  # nosec
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        # Should not flag the password
        assert len(findings) == 0

    def test_severity_filter(self):
        """Test severity filtering."""
        content = '''
console.log(debug);
api_key = "sk-1234567890abcdefghij1234567890abcdefghij12345678"
'''
        # Only high and above
        config = SecurityConfig(min_severity=Severity.HIGH)
        verifier = SecurityVerifier(config)
        findings = verifier.scan_content(content, "test.js")

        # Should find the API key (critical) but not the console.log (low)
        assert all(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in findings)

    def test_disable_checks(self):
        """Test disabling specific checks."""
        content = '''
console.log(debug);
'''
        config = SecurityConfig(check_debug_code=False)
        verifier = SecurityVerifier(config)
        findings = verifier.scan_content(content, "test.js")

        assert len(findings) == 0

    def test_scan_clean_code(self):
        """Test that clean code has no findings."""
        content = '''
import os

def get_env_var(name):
    return os.environ.get(name)

def hello(name):
    return f"Hello, {name}!"
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_content(content, "test.py")

        assert len(findings) == 0


class TestSecurityVerifierFiles:
    """Tests for file and directory scanning."""

    def test_scan_file(self, tmp_path):
        """Test scanning a single file."""
        test_file = tmp_path / "test.py"
        test_file.write_text('api_key = "sk-1234567890abcdefghij1234567890abcdefghij12345678"')

        verifier = SecurityVerifier()
        findings = verifier.scan_file(test_file)

        assert len(findings) >= 1

    def test_scan_directory(self, tmp_path):
        """Test scanning a directory."""
        (tmp_path / "file1.py").write_text('password = "admin"')
        (tmp_path / "file2.py").write_text('api_key = "sk-1234567890abcdefghij1234567890abcdefghij12345678"')
        (tmp_path / "clean.py").write_text('print("hello")')

        verifier = SecurityVerifier()
        findings = verifier.scan_directory(tmp_path)

        assert len(findings) >= 2

    def test_skip_non_scannable_files(self, tmp_path):
        """Test that non-scannable files are skipped."""
        (tmp_path / "image.png").write_bytes(b'\x89PNG\r\n\x1a\n')
        (tmp_path / "data.bin").write_bytes(b'\x00\x01\x02\x03')

        verifier = SecurityVerifier()
        findings = verifier.scan_directory(tmp_path)

        assert len(findings) == 0

    def test_skip_node_modules(self, tmp_path):
        """Test that node_modules is skipped."""
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.py").write_text('password = "admin"')

        verifier = SecurityVerifier()
        findings = verifier.scan_directory(tmp_path)

        assert len(findings) == 0


class TestSecurityVerifierDiff:
    """Tests for diff scanning."""

    def test_scan_diff(self):
        """Test scanning a unified diff."""
        diff = '''
diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -1,3 +1,4 @@
 import os
+API_KEY = "sk-1234567890abcdefghij1234567890abcdefghij12345678"

 def get_config():
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_diff(diff)

        assert len(findings) >= 1
        assert any("config.py" in f.file_path for f in findings)

    def test_scan_diff_ignores_removed_lines(self):
        """Test that removed lines are not flagged."""
        diff = '''
diff --git a/config.py b/config.py
--- a/config.py
+++ b/config.py
@@ -1,4 +1,3 @@
 import os
-API_KEY = "sk-1234567890abcdefghij1234567890abcdefghij12345678"

 def get_config():
'''
        verifier = SecurityVerifier()
        findings = verifier.scan_diff(diff)

        # Removed lines should not be flagged
        assert len(findings) == 0


class TestQuickScan:
    """Tests for quick_scan function."""

    def test_quick_scan(self):
        """Test quick_scan convenience function."""
        content = 'password = "admin"'
        findings = quick_scan(content, "test.py")

        assert len(findings) >= 1
