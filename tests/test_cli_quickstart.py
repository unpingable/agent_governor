# SPDX-License-Identifier: Apache-2.0
"""Tests for ``governor quickstart`` CLI command."""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

# Same pattern as test_fresh_clone.py
_GOVERNOR_BIN = shutil.which("governor")
if _GOVERNOR_BIN:
    GOVERNOR = [_GOVERNOR_BIN]
else:
    GOVERNOR = [sys.executable, "-c", "from governor.cli import main; main()"]


@pytest.fixture()
def fresh_dir(tmp_path, monkeypatch):
    """Provide a clean directory with no .governor/."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run_quickstart(cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        GOVERNOR + ["--root", str(cwd), "quickstart"],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestQuickstart:
    def test_runs_without_error(self, fresh_dir):
        result = _run_quickstart(fresh_dir)
        assert result.returncode == 0, result.stderr

    def test_creates_governor_dir(self, fresh_dir):
        _run_quickstart(fresh_dir)
        assert (fresh_dir / ".governor").is_dir()

    def test_shows_all_steps(self, fresh_dir):
        result = _run_quickstart(fresh_dir)
        output = result.stdout
        assert "Step 1/4" in output
        assert "Step 2/4" in output
        assert "Step 3/4" in output
        assert "Step 4/4" in output

    def test_shows_gate_check(self, fresh_dir):
        result = _run_quickstart(fresh_dir)
        assert "gate check" in result.stdout.lower() or "evidence gate" in result.stdout.lower()

    def test_shows_violation(self, fresh_dir):
        result = _run_quickstart(fresh_dir)
        assert "FAILED" in result.stdout or "REJECT" in result.stdout

    def test_shows_next_steps(self, fresh_dir):
        result = _run_quickstart(fresh_dir)
        assert "What next" in result.stdout

    def test_cleans_up_demo_anchor(self, fresh_dir):
        """Demo anchor is removed so quickstart is re-runnable."""
        _run_quickstart(fresh_dir)
        # Check anchor list — should not contain no-eval
        result = subprocess.run(
            GOVERNOR + ["--root", str(fresh_dir),
             "continuity", "anchor", "list"],
            capture_output=True, text=True, timeout=30,
        )
        assert "no-eval" not in result.stdout

    def test_idempotent(self, fresh_dir):
        """Running quickstart twice should work (not fail on existing .governor/)."""
        r1 = _run_quickstart(fresh_dir)
        assert r1.returncode == 0, r1.stderr
        r2 = _run_quickstart(fresh_dir)
        assert r2.returncode == 0, r2.stderr
        assert "already initialized" in r2.stdout.lower()

    def test_appears_in_help(self):
        """quickstart should appear in curated help output."""
        result = subprocess.run(
            GOVERNOR + ["--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert "quickstart" in result.stdout
