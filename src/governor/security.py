# SPDX-License-Identifier: Apache-2.0
"""
Security verifier for detecting common vulnerabilities.

Checks for:
- Secrets in code (API keys, passwords, tokens)
- SQL injection patterns
- Command injection patterns
- XSS vulnerabilities
- Path traversal vulnerabilities
- Hardcoded credentials
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class VulnerabilityType(Enum):
    """Types of security vulnerabilities."""

    SECRET_LEAK = "secret_leak"
    """Exposed API key, password, token, or credential."""

    SQL_INJECTION = "sql_injection"
    """Potential SQL injection vulnerability."""

    COMMAND_INJECTION = "command_injection"
    """Potential command injection vulnerability."""

    XSS = "xss"
    """Potential cross-site scripting vulnerability."""

    PATH_TRAVERSAL = "path_traversal"
    """Potential path traversal vulnerability."""

    HARDCODED_CREDENTIAL = "hardcoded_credential"
    """Hardcoded username, password, or connection string."""

    INSECURE_RANDOM = "insecure_random"
    """Use of insecure random number generation."""

    INSECURE_HASH = "insecure_hash"
    """Use of weak hashing algorithm (MD5, SHA1 for security)."""

    INSECURE_DESERIALIZATION = "insecure_deserialization"
    """Potential insecure deserialization."""

    DEBUG_CODE = "debug_code"
    """Debug code that shouldn't be in production."""


class Severity(Enum):
    """Severity levels for vulnerabilities."""

    CRITICAL = "critical"
    """Must be fixed before commit."""

    HIGH = "high"
    """Should be fixed before commit."""

    MEDIUM = "medium"
    """Should be reviewed."""

    LOW = "low"
    """Informational, may be intentional."""


@dataclass
class SecurityFinding:
    """A security issue found in code."""

    vuln_type: VulnerabilityType
    severity: Severity
    file_path: str
    line_number: int
    line_content: str
    message: str
    pattern_matched: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vuln_type": self.vuln_type.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "line_content": self.line_content,
            "message": self.message,
            "pattern_matched": self.pattern_matched,
            "suggestion": self.suggestion,
        }


# Secret patterns - tuned to reduce false positives
SECRET_PATTERNS = [
    # API keys with common prefixes
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "API key"),
    (r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "Secret key"),
    (r'(?i)(access[_-]?token|accesstoken)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "Access token"),
    (r'(?i)(auth[_-]?token|authtoken)\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?', "Auth token"),

    # Provider-specific patterns
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9/+=]{40})["\']?', "AWS Secret Key"),
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key ID"),
    (r'(?i)github[_-]?token\s*[=:]\s*["\']?(ghp_[a-zA-Z0-9]{36})["\']?', "GitHub Token"),
    (r'(?i)github[_-]?token\s*[=:]\s*["\']?(gho_[a-zA-Z0-9]{36})["\']?', "GitHub OAuth Token"),
    (r'sk-[a-zA-Z0-9]{48}', "OpenAI API Key"),
    (r'(?i)stripe[_-]?(secret|api)[_-]?key\s*[=:]\s*["\']?(sk_live_[a-zA-Z0-9]{24,})["\']?', "Stripe Secret Key"),
    (r'(?i)slack[_-]?(token|webhook)\s*[=:]\s*["\']?(xox[baprs]-[a-zA-Z0-9\-]+)["\']?', "Slack Token"),

    # Generic high-entropy strings that look like secrets
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']([^"\']{8,})["\']', "Password"),
    (r'(?i)private[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9/+=]{40,})["\']?', "Private key"),

    # Connection strings
    (r'(?i)(mongodb|postgres|mysql|redis)://[^:]+:[^@]+@', "Database connection string with credentials"),
]

# SQL injection patterns
SQL_INJECTION_PATTERNS = [
    # String concatenation in queries
    (r'(?i)(execute|cursor\.execute|query)\s*\(\s*["\'].*?["\']\s*\+', "String concatenation in SQL query"),
    (r'(?i)(execute|cursor\.execute|query)\s*\(\s*f["\']', "f-string in SQL query"),
    (r'(?i)(execute|cursor\.execute|query)\s*\(\s*["\'].*?%s', "%-formatting in SQL query"),
    (r'(?i)(execute|cursor\.execute|query)\s*\(\s*["\'].*?\.format\s*\(', ".format() in SQL query"),

    # Raw SQL with user input indicators
    (r'(?i)SELECT\s+.*\s+WHERE\s+.*["\']\s*\+', "Unparameterized WHERE clause"),
    (r'(?i)INSERT\s+INTO\s+.*\s+VALUES\s*\([^)]*\+', "Unparameterized INSERT"),
]

# Command injection patterns
COMMAND_INJECTION_PATTERNS = [
    (r'(?i)os\.system\s*\(\s*["\'].*?["\']\s*\+', "String concatenation in os.system()"),
    (r'(?i)os\.system\s*\(\s*f["\']', "f-string in os.system()"),
    (r'(?i)subprocess\.(call|run|Popen)\s*\(\s*["\'].*?["\']\s*\+', "String concatenation in subprocess"),
    (r'(?i)subprocess\.(call|run|Popen)\s*\(\s*f["\']', "f-string in subprocess"),
    (r'(?i)shell\s*=\s*True', "shell=True in subprocess (review for injection)"),
    (r'(?i)eval\s*\(\s*[^)]*\+', "String concatenation in eval()"),
    (r'(?i)exec\s*\(\s*[^)]*\+', "String concatenation in exec()"),
]

# XSS patterns
XSS_PATTERNS = [
    (r'(?i)innerHTML\s*=\s*[^;]*\+', "String concatenation in innerHTML"),
    (r'(?i)document\.write\s*\(\s*[^)]*\+', "String concatenation in document.write()"),
    (r'(?i)\.html\s*\(\s*[^)]*\+', "String concatenation in .html()"),
    (r'(?i)dangerouslySetInnerHTML', "dangerouslySetInnerHTML usage (review for XSS)"),
    (r'\|\s*safe\s*}}', "Django |safe filter (review for XSS)"),
    (r'mark_safe\s*\(', "Django mark_safe() (review for XSS)"),
]

# Path traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    (r'(?i)open\s*\(\s*[^)]*\+\s*[^)]*\)', "String concatenation in file open"),
    (r'(?i)Path\s*\(\s*[^)]*\+\s*[^)]*\)', "String concatenation in Path()"),
    (r'(?i)(os\.path\.join|pathlib)\s*\([^)]*request\.[^)]*\)', "User input in path construction"),
]

# Hardcoded credentials
HARDCODED_CREDENTIAL_PATTERNS = [
    (r'(?i)(username|user)\s*[=:]\s*["\']admin["\']', "Hardcoded admin username"),
    (r'(?i)(username|user)\s*[=:]\s*["\']root["\']', "Hardcoded root username"),
    (r'(?i)password\s*[=:]\s*["\']password["\']', "Hardcoded password 'password'"),
    (r'(?i)password\s*[=:]\s*["\']123456["\']', "Hardcoded password '123456'"),
    (r'(?i)password\s*[=:]\s*["\']admin["\']', "Hardcoded password 'admin'"),
]

# Insecure patterns
INSECURE_PATTERNS = [
    (r'(?i)random\.random\s*\(', "random.random() for security (use secrets module)", VulnerabilityType.INSECURE_RANDOM),
    (r'(?i)random\.randint\s*\(', "random.randint() for security (use secrets module)", VulnerabilityType.INSECURE_RANDOM),
    (r'(?i)hashlib\.md5\s*\(', "MD5 for security hashing (use SHA-256+)", VulnerabilityType.INSECURE_HASH),
    (r'(?i)hashlib\.sha1\s*\(', "SHA1 for security hashing (use SHA-256+)", VulnerabilityType.INSECURE_HASH),
    (r'(?i)pickle\.loads?\s*\(', "pickle.load() on untrusted data", VulnerabilityType.INSECURE_DESERIALIZATION),
    (r'(?i)yaml\.load\s*\([^)]*\)(?!\s*,\s*Loader\s*=)', "yaml.load() without safe Loader", VulnerabilityType.INSECURE_DESERIALIZATION),
]

# Debug code patterns
DEBUG_PATTERNS = [
    (r'(?i)console\.log\s*\(', "console.log() in production code"),
    (r'(?i)print\s*\(\s*["\']?debug', "Debug print statement"),
    (r'(?i)debugger\s*;', "JavaScript debugger statement"),
    (r'(?i)import\s+pdb', "pdb import (debugger)"),
    (r'(?i)breakpoint\s*\(\s*\)', "breakpoint() call"),
    (r'(?i)DEBUG\s*=\s*True', "DEBUG = True"),
]

# File extensions to scan
SCANNABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".rs", ".swift", ".kt",
    ".sql", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".env.example", ".env.local",
}

# Files to always skip
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "Cargo.lock", "poetry.lock",
    "go.sum", "Gemfile.lock",
}

# Directories to skip
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", "dist", "build",
    ".tox", ".nox", "target", "vendor",
}


@dataclass
class SecurityConfig:
    """Configuration for security scanning."""

    check_secrets: bool = True
    check_sql_injection: bool = True
    check_command_injection: bool = True
    check_xss: bool = True
    check_path_traversal: bool = True
    check_hardcoded_creds: bool = True
    check_insecure_patterns: bool = True
    check_debug_code: bool = True

    # Minimum severity to report
    min_severity: Severity = Severity.LOW

    # Custom patterns to add
    custom_secret_patterns: list[tuple[str, str]] = field(default_factory=list)
    custom_ignore_patterns: list[str] = field(default_factory=list)

    # Files/paths to ignore
    ignore_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_secrets": self.check_secrets,
            "check_sql_injection": self.check_sql_injection,
            "check_command_injection": self.check_command_injection,
            "check_xss": self.check_xss,
            "check_path_traversal": self.check_path_traversal,
            "check_hardcoded_creds": self.check_hardcoded_creds,
            "check_insecure_patterns": self.check_insecure_patterns,
            "check_debug_code": self.check_debug_code,
            "min_severity": self.min_severity.value,
            "custom_secret_patterns": self.custom_secret_patterns,
            "custom_ignore_patterns": self.custom_ignore_patterns,
            "ignore_paths": self.ignore_paths,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SecurityConfig":
        return cls(
            check_secrets=data.get("check_secrets", True),
            check_sql_injection=data.get("check_sql_injection", True),
            check_command_injection=data.get("check_command_injection", True),
            check_xss=data.get("check_xss", True),
            check_path_traversal=data.get("check_path_traversal", True),
            check_hardcoded_creds=data.get("check_hardcoded_creds", True),
            check_insecure_patterns=data.get("check_insecure_patterns", True),
            check_debug_code=data.get("check_debug_code", True),
            min_severity=Severity(data.get("min_severity", "low")),
            custom_secret_patterns=data.get("custom_secret_patterns", []),
            custom_ignore_patterns=data.get("custom_ignore_patterns", []),
            ignore_paths=data.get("ignore_paths", []),
        )


class SecurityVerifier:
    """Verifier for security vulnerabilities."""

    def __init__(self, config: SecurityConfig | None = None):
        self.config = config or SecurityConfig()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        self._secret_patterns = [
            (re.compile(p), desc) for p, desc in SECRET_PATTERNS
        ]
        self._secret_patterns.extend([
            (re.compile(p), desc) for p, desc in self.config.custom_secret_patterns
        ])

        self._sql_patterns = [(re.compile(p), desc) for p, desc in SQL_INJECTION_PATTERNS]
        self._cmd_patterns = [(re.compile(p), desc) for p, desc in COMMAND_INJECTION_PATTERNS]
        self._xss_patterns = [(re.compile(p), desc) for p, desc in XSS_PATTERNS]
        self._path_patterns = [(re.compile(p), desc) for p, desc in PATH_TRAVERSAL_PATTERNS]
        self._cred_patterns = [(re.compile(p), desc) for p, desc in HARDCODED_CREDENTIAL_PATTERNS]
        self._insecure_patterns = [(re.compile(p), desc, vtype) for p, desc, vtype in INSECURE_PATTERNS]
        self._debug_patterns = [(re.compile(p), desc) for p, desc in DEBUG_PATTERNS]

        self._ignore_patterns = [
            re.compile(p) for p in self.config.custom_ignore_patterns
        ]

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        # Check filename
        if file_path.name in SKIP_FILES:
            return True

        # Check extension
        if file_path.suffix.lower() not in SCANNABLE_EXTENSIONS:
            return True

        # Check if in skip directory
        for part in file_path.parts:
            if part in SKIP_DIRS:
                return True

        # Check ignore paths
        str_path = str(file_path)
        for ignore_path in self.config.ignore_paths:
            if ignore_path in str_path:
                return True

        return False

    def _should_ignore_line(self, line: str) -> bool:
        """Check if line should be ignored."""
        # Skip comments that look like documentation
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            # But don't skip if it contains actual secrets
            if not any(p[0].search(line) for p in self._secret_patterns[:4]):
                return True

        # Check custom ignore patterns
        for pattern in self._ignore_patterns:
            if pattern.search(line):
                return True

        # Skip lines with nosec or noqa comments
        if "nosec" in line.lower() or "noqa" in line.lower() or "pragma: allowlist" in line.lower():
            return True

        return False

    def scan_content(
        self,
        content: str,
        file_path: str = "<unknown>",
    ) -> list[SecurityFinding]:
        """Scan content for security issues."""
        findings: list[SecurityFinding] = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            if self._should_ignore_line(line):
                continue

            # Check secrets
            if self.config.check_secrets:
                for pattern, desc in self._secret_patterns:
                    if match := pattern.search(line):
                        findings.append(SecurityFinding(
                            vuln_type=VulnerabilityType.SECRET_LEAK,
                            severity=Severity.CRITICAL,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=f"Potential {desc} detected",
                            pattern_matched=match.group(0)[:50] + "..." if len(match.group(0)) > 50 else match.group(0),
                            suggestion="Use environment variables or a secrets manager",
                        ))

            # Check SQL injection
            if self.config.check_sql_injection:
                for pattern, desc in self._sql_patterns:
                    if match := pattern.search(line):
                        findings.append(SecurityFinding(
                            vuln_type=VulnerabilityType.SQL_INJECTION,
                            severity=Severity.HIGH,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=desc,
                            pattern_matched=match.group(0)[:50],
                            suggestion="Use parameterized queries",
                        ))

            # Check command injection
            if self.config.check_command_injection:
                for pattern, desc in self._cmd_patterns:
                    if match := pattern.search(line):
                        # shell=True is medium severity (may be intentional)
                        severity = Severity.MEDIUM if "shell=True" in desc else Severity.HIGH
                        findings.append(SecurityFinding(
                            vuln_type=VulnerabilityType.COMMAND_INJECTION,
                            severity=severity,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=desc,
                            pattern_matched=match.group(0)[:50],
                            suggestion="Use subprocess with list arguments, avoid shell=True",
                        ))

            # Check XSS
            if self.config.check_xss:
                for pattern, desc in self._xss_patterns:
                    if match := pattern.search(line):
                        findings.append(SecurityFinding(
                            vuln_type=VulnerabilityType.XSS,
                            severity=Severity.HIGH,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=desc,
                            pattern_matched=match.group(0)[:50],
                            suggestion="Sanitize user input, use safe templating",
                        ))

            # Check path traversal
            if self.config.check_path_traversal:
                for pattern, desc in self._path_patterns:
                    if match := pattern.search(line):
                        findings.append(SecurityFinding(
                            vuln_type=VulnerabilityType.PATH_TRAVERSAL,
                            severity=Severity.HIGH,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=desc,
                            pattern_matched=match.group(0)[:50],
                            suggestion="Validate paths, use realpath() and check prefix",
                        ))

            # Check hardcoded credentials
            if self.config.check_hardcoded_creds:
                for pattern, desc in self._cred_patterns:
                    if match := pattern.search(line):
                        findings.append(SecurityFinding(
                            vuln_type=VulnerabilityType.HARDCODED_CREDENTIAL,
                            severity=Severity.HIGH,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=desc,
                            pattern_matched=match.group(0)[:50],
                            suggestion="Use environment variables or config files",
                        ))

            # Check insecure patterns
            if self.config.check_insecure_patterns:
                for pattern, desc, vtype in self._insecure_patterns:
                    if match := pattern.search(line):
                        findings.append(SecurityFinding(
                            vuln_type=vtype,
                            severity=Severity.MEDIUM,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=desc,
                            pattern_matched=match.group(0)[:50],
                        ))

            # Check debug code
            if self.config.check_debug_code:
                for pattern, desc in self._debug_patterns:
                    if match := pattern.search(line):
                        findings.append(SecurityFinding(
                            vuln_type=VulnerabilityType.DEBUG_CODE,
                            severity=Severity.LOW,
                            file_path=file_path,
                            line_number=line_num,
                            line_content=line.strip()[:100],
                            message=desc,
                            pattern_matched=match.group(0)[:50],
                            suggestion="Remove debug code before commit",
                        ))

        # Filter by minimum severity
        severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
        min_idx = severity_order.index(self.config.min_severity)
        findings = [f for f in findings if severity_order.index(f.severity) <= min_idx]

        return findings

    def scan_file(self, file_path: Path) -> list[SecurityFinding]:
        """Scan a single file for security issues."""
        if self._should_skip_file(file_path):
            return []

        try:
            content = file_path.read_text(errors="ignore")
            return self.scan_content(content, str(file_path))
        except Exception:
            return []

    def scan_directory(
        self,
        directory: Path,
        recursive: bool = True,
    ) -> list[SecurityFinding]:
        """Scan a directory for security issues."""
        findings: list[SecurityFinding] = []

        if recursive:
            files = directory.rglob("*")
        else:
            files = directory.glob("*")

        for file_path in files:
            if file_path.is_file():
                findings.extend(self.scan_file(file_path))

        return findings

    def scan_diff(self, diff_content: str) -> list[SecurityFinding]:
        """Scan a unified diff for security issues (only added lines)."""
        findings: list[SecurityFinding] = []
        current_file = "<unknown>"
        line_num = 0

        for line in diff_content.split("\n"):
            # Track file changes
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            elif line.startswith("@@ "):
                # Parse line number from @@ -x,y +a,b @@
                match = re.search(r'\+(\d+)', line)
                if match:
                    line_num = int(match.group(1)) - 1
                continue

            # Only check added lines
            if line.startswith("+") and not line.startswith("+++"):
                line_num += 1
                added_content = line[1:]  # Remove the + prefix
                file_findings = self.scan_content(added_content, current_file)
                for finding in file_findings:
                    finding.line_number = line_num
                findings.extend(file_findings)
            elif not line.startswith("-"):
                line_num += 1

        return findings


def create_default_verifier() -> SecurityVerifier:
    """Create a security verifier with default configuration."""
    return SecurityVerifier()


def quick_scan(content: str, file_path: str = "<unknown>") -> list[SecurityFinding]:
    """Quick scan of content for security issues."""
    verifier = create_default_verifier()
    return verifier.scan_content(content, file_path)
