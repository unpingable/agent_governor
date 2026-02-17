# SPDX-License-Identifier: Apache-2.0
"""Oracle: pytest_log — non-linguistic evidence from real test execution.

Runs pytest as a subprocess, captures stdout/stderr + junit.xml, produces
a content-addressed OraclePytestLog summary with hashes of all artifacts.

evidence_kind: oracle:pytest_log (STRONG)
oracle_class: 0 (local — same host/session)

The model cannot narrate this into existence. Either pytest ran and
produced artifacts, or it didn't. Hashes don't lie.

Usage:
    runner = PytestRunner()
    log = runner.run(["tests/test_foo.py"], cwd="/path/to/repo")

    # Attach to evidence gate check
    gate = EvidenceGate(config=config, kernel_bridge=bridge)
    result = gate.check(task=task, context=ctx, output=out,
                        oracle_evidence=[log])
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# =============================================================================
# Schema: OraclePytestLog
# =============================================================================


@dataclass(frozen=True)
class PytestFailure:
    """A single test failure/error."""
    nodeid: str
    message: str  # truncated to MAX_FAILURE_MSG_LEN


@dataclass(frozen=True)
class OraclePytestLog:
    """Summary of a real pytest run — the non-linguistic evidence.

    This is what gets stored as a kernel evidence blob. The raw log
    and junit.xml are stored separately as content-addressed artifacts.
    """
    schema_version: int  # 1
    kind: str  # "oracle:pytest_log"
    oracle_class: int  # 0..3 (see ETHICAL_HARDENING.md)
    run_id: str  # ties to kernel run

    # Execution
    cmd: list[str]
    cwd: str
    start_ts: float
    end_ts: float
    duration_s: float
    exit_code: int

    # Artifact hashes (content-addressed)
    junit_xml_sha256: str
    log_sha256: str

    # Parsed summary (derived from junit, not from model narration)
    tests_total: int
    tests_passed: int
    tests_failed: int
    tests_errored: int
    tests_skipped: int

    # Truncated failure details
    failures: list[PytestFailure]

    # Environment snapshot
    environment: dict[str, str]

    # Git state (if available)
    git: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind,
            "oracle_class": self.oracle_class,
            "run_id": self.run_id,
            "cmd": list(self.cmd),
            "cwd": self.cwd,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "duration_s": self.duration_s,
            "exit_code": self.exit_code,
            "junit_xml_sha256": self.junit_xml_sha256,
            "log_sha256": self.log_sha256,
            "tests_total": self.tests_total,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_errored": self.tests_errored,
            "tests_skipped": self.tests_skipped,
            "failures": [
                {"nodeid": f.nodeid, "message": f.message}
                for f in self.failures
            ],
            "environment": dict(self.environment),
            "git": dict(self.git),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def to_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")

    @property
    def all_passed(self) -> bool:
        return self.exit_code == 0 and self.tests_failed == 0 and self.tests_errored == 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> OraclePytestLog:
        failures = [
            PytestFailure(nodeid=f["nodeid"], message=f["message"])
            for f in d.get("failures", [])
        ]
        return cls(
            schema_version=d["schema_version"],
            kind=d["kind"],
            oracle_class=d.get("oracle_class", 0),
            run_id=d["run_id"],
            cmd=d["cmd"],
            cwd=d["cwd"],
            start_ts=d["start_ts"],
            end_ts=d["end_ts"],
            duration_s=d["duration_s"],
            exit_code=d["exit_code"],
            junit_xml_sha256=d["junit_xml_sha256"],
            log_sha256=d["log_sha256"],
            tests_total=d["tests_total"],
            tests_passed=d["tests_passed"],
            tests_failed=d["tests_failed"],
            tests_errored=d["tests_errored"],
            tests_skipped=d["tests_skipped"],
            failures=failures,
            environment=d.get("environment", {}),
            git=d.get("git", {}),
        )


# =============================================================================
# Constants
# =============================================================================

MAX_FAILURE_MSG_LEN = 500  # Truncate failure messages to prevent log-as-instructions
PYTEST_TIMEOUT_S = 300  # 5 minutes max per run


# =============================================================================
# JUnit XML parser
# =============================================================================


def parse_junit_xml(xml_bytes: bytes) -> dict[str, Any]:
    """Parse pytest's junit.xml into structured counts + failures.

    We parse junit (not raw output) to avoid treating log text as
    instructions. The XML schema is stable and machine-generated.
    """
    root = ET.fromstring(xml_bytes)

    # Handle both <testsuites><testsuite>... and <testsuite>... formats
    if root.tag == "testsuites":
        suites = list(root)
    elif root.tag == "testsuite":
        suites = [root]
    else:
        return {
            "tests_total": 0, "tests_passed": 0, "tests_failed": 0,
            "tests_errored": 0, "tests_skipped": 0, "failures": [],
        }

    total = 0
    failed = 0
    errored = 0
    skipped = 0
    failures: list[PytestFailure] = []

    for suite in suites:
        total += int(suite.get("tests", "0"))
        failed += int(suite.get("failures", "0"))
        errored += int(suite.get("errors", "0"))
        skipped += int(suite.get("skipped", "0"))

        for testcase in suite.findall("testcase"):
            nodeid = testcase.get("classname", "") + "::" + testcase.get("name", "")

            failure_el = testcase.find("failure")
            error_el = testcase.find("error")

            if failure_el is not None:
                msg = (failure_el.get("message") or failure_el.text or "")[:MAX_FAILURE_MSG_LEN]
                failures.append(PytestFailure(nodeid=nodeid, message=msg))
            elif error_el is not None:
                msg = (error_el.get("message") or error_el.text or "")[:MAX_FAILURE_MSG_LEN]
                failures.append(PytestFailure(nodeid=nodeid, message=msg))

    passed = total - failed - errored - skipped

    return {
        "tests_total": total,
        "tests_passed": max(0, passed),
        "tests_failed": failed,
        "tests_errored": errored,
        "tests_skipped": skipped,
        "failures": failures,
    }


# =============================================================================
# Environment + git snapshot
# =============================================================================


def _capture_environment() -> dict[str, str]:
    """Capture current environment for reproducibility."""
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def _capture_git_state(cwd: str) -> dict[str, str]:
    """Capture git state (best-effort, never fails)."""
    result: dict[str, str] = {}
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if commit.returncode == 0:
            result["commit"] = commit.stdout.strip()

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if branch.returncode == 0:
            result["branch"] = branch.stdout.strip()

        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD"],
            capture_output=True, cwd=cwd, timeout=5,
        )
        result["dirty"] = str(dirty.returncode != 0).lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return result


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# =============================================================================
# Runner
# =============================================================================


class PytestRunner:
    """Run pytest and produce an OraclePytestLog artifact.

    The runner invokes pytest as a subprocess, captures all output,
    and parses junit.xml for structured results. The model never
    touches the raw output — it's evidence bytes referenced by hash.
    """

    def __init__(
        self,
        *,
        oracle_class: int = 0,
        timeout: int = PYTEST_TIMEOUT_S,
        extra_args: list[str] | None = None,
    ):
        self.oracle_class = oracle_class
        self.timeout = timeout
        self.extra_args = extra_args or []

    def run(
        self,
        test_paths: list[str],
        *,
        cwd: str | None = None,
        run_id: str = "",
    ) -> PytestRunResult:
        """Execute pytest and return structured results.

        Args:
            test_paths: Paths to test files/dirs (e.g. ["tests/test_foo.py"])
            cwd: Working directory for pytest
            run_id: Kernel run ID to bind this evidence to

        Returns:
            PytestRunResult with log, artifacts, and parsed summary
        """
        cwd = cwd or os.getcwd()
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            junit_path = Path(tmpdir) / "junit.xml"

            cmd = [
                "python3", "-m", "pytest",
                "-q",
                "--disable-warnings",
                f"--junitxml={junit_path}",
                *self.extra_args,
                *test_paths,
            ]

            start_ts = time.time()
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    cwd=cwd,
                    timeout=self.timeout,
                )
                end_ts = time.time()
                log_bytes = proc.stdout + proc.stderr
                exit_code = proc.returncode
            except subprocess.TimeoutExpired as e:
                end_ts = time.time()
                log_bytes = (e.stdout or b"") + (e.stderr or b"") + b"\n[TIMEOUT]\n"
                exit_code = -1

            # Read junit.xml (may not exist on catastrophic failure)
            if junit_path.exists():
                junit_bytes = junit_path.read_bytes()
            else:
                junit_bytes = b'<testsuite tests="0" failures="0" errors="0" />'

            # Parse junit for structured counts
            parsed = parse_junit_xml(junit_bytes)

            # Hash artifacts
            log_sha = _sha256(log_bytes)
            junit_sha = _sha256(junit_bytes)

            # Capture environment
            env = _capture_environment()
            git = _capture_git_state(cwd)

            duration = end_ts - start_ts

            log = OraclePytestLog(
                schema_version=1,
                kind="oracle:pytest_log",
                oracle_class=self.oracle_class,
                run_id=run_id,
                cmd=cmd,
                cwd=cwd,
                start_ts=start_ts,
                end_ts=end_ts,
                duration_s=round(duration, 3),
                exit_code=exit_code,
                junit_xml_sha256=junit_sha,
                log_sha256=log_sha,
                tests_total=parsed["tests_total"],
                tests_passed=parsed["tests_passed"],
                tests_failed=parsed["tests_failed"],
                tests_errored=parsed["tests_errored"],
                tests_skipped=parsed["tests_skipped"],
                failures=parsed["failures"],
                environment=env,
                git=git,
            )

            return PytestRunResult(
                log=log,
                log_bytes=log_bytes,
                junit_bytes=junit_bytes,
            )


@dataclass
class PytestRunResult:
    """Raw result from a pytest run — log + artifacts + summary."""
    log: OraclePytestLog
    log_bytes: bytes  # raw stdout+stderr
    junit_bytes: bytes  # raw junit.xml
