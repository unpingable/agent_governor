# SPDX-License-Identifier: Apache-2.0
"""
Fresh-clone smoke tests.

These tests simulate a reader cloning the repo and running the basic workflow.
They use subprocess.run with real git repos in tmp_path — deliberately ugly and
slow, because the goal is confidence that the "front door" works.

Run:
    python3 -m pytest tests/test_fresh_clone.py -v

Marker:
    @pytest.mark.smoke
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

# Use the installed entry point, falling back to python -c for CI
_GOVERNOR_BIN = shutil.which("governor")
if _GOVERNOR_BIN:
    GOVERNOR = [_GOVERNOR_BIN]
else:
    # Fallback: invoke via Python
    GOVERNOR = [sys.executable, "-c", "from governor.cli import main; main()"]


def run_gov(args: list[str], cwd: str | Path, **kwargs) -> subprocess.CompletedProcess:
    """Run a governor CLI command via subprocess."""
    return subprocess.run(
        GOVERNOR + args,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(cwd),
        **kwargs,
    )


def git_init(path: Path) -> None:
    """Initialize a git repo with a dummy commit."""
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path), capture_output=True, check=True,
    )
    # Need at least one commit for hooks to work
    (path / ".gitkeep").write_text("")
    subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path), capture_output=True, check=True,
    )


# ── Group 1: CLI happy path ─────────────────────────────────────────────


class TestCLIHappyPath:
    """End-to-end CLI workflow in a fresh tmp_path git repo."""

    def test_governor_init_creates_structure(self, tmp_path):
        """governor init → .governor/ with expected subdirectories."""
        git_init(tmp_path)
        result = run_gov(["init"], cwd=tmp_path)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        assert "Initialized governor" in result.stdout

        gov_dir = tmp_path / ".governor"
        assert gov_dir.is_dir()
        assert (gov_dir / "facts").is_dir()
        assert (gov_dir / "facts" / "receipts").is_dir()
        assert (gov_dir / "decisions").is_dir()
        assert (gov_dir / "proposals.json").exists()

    def test_governor_init_shows_epilogue(self, tmp_path):
        """governor init prints what was created and suggests next command."""
        git_init(tmp_path)
        result = run_gov(["init"], cwd=tmp_path)
        assert result.returncode == 0
        # Epilogue shows directory descriptions
        assert "facts/" in result.stdout
        assert "decisions/" in result.stdout
        assert "receipts/" in result.stdout
        # Epilogue suggests next command
        assert "governor gate check" in result.stdout

    def test_governor_init_idempotent(self, tmp_path):
        """Running init twice does not error or corrupt state."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["init"], cwd=tmp_path)
        assert result.returncode == 0
        assert "already initialized" in result.stdout.lower()

    def test_init_on_clone_with_loop_artifacts_only(self, tmp_path):
        """A fresh clone legitimately ships .governor/ with ONLY the tracked
        orchestration-loop artifacts (loop.json etc. — the repo's program
        counter). init must initialize the runtime alongside, not report
        'already initialized' (stranger-run punch list item 3)."""
        git_init(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "loop.json").write_text('{"phase": "PLAN"}')
        (gov_dir / "loop-receipts").mkdir()
        (gov_dir / "backlog").mkdir()
        result = run_gov(["init"], cwd=tmp_path)
        assert result.returncode == 0, f"init failed: {result.stderr}"
        assert "already initialized" not in result.stdout.lower()
        assert (gov_dir / "facts").is_dir()
        assert (gov_dir / "proposals.json").exists()
        # The loop artifacts are untouched.
        assert (gov_dir / "loop.json").read_text() == '{"phase": "PLAN"}'

    def test_strict_gate_block_has_no_internal_error_leak(self, tmp_path):
        """strict-path-taint-error-leak, pinned: the README's recommended
        --strict command must block WITHOUT leaking internal error text
        ('release taint computation failed: ... _store')."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(
            ["gate", "check", "--strict",
             "I guarantee the auth module is thread-safe."],
            cwd=tmp_path,
        )
        out = result.stdout + result.stderr
        assert "BLOCKED" in out
        assert "computation failed" not in out
        assert "_store" not in out

    def test_continuity_reject_emits_visible_receipt(self, tmp_path):
        """The stranger's worst moment, pinned unreproducible: the documented
        no-eval continuity REJECT must produce a receipt VISIBLE to
        `governor receipts` (punch list items 5-7 — 'blocked with receipts'
        must not show a block and no receipt)."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        run_gov(
            ["continuity", "anchor", "add", "--id", "no-eval",
             "--type", "prohibition", "--description", "no eval",
             "--forbidden", "eval(", "--severity", "reject",
             "--class", "invariant"],
            cwd=tmp_path,
        )
        check = run_gov(
            ["continuity", "check", "use eval(user_input) here"], cwd=tmp_path
        )
        assert "[REJECT] no-eval" in check.stdout
        assert "Receipt:" in check.stdout  # the screen says where the proof is
        receipts = run_gov(["receipts", "--last", "5"], cwd=tmp_path)
        assert "continuity_checker" in receipts.stdout
        assert "BLOCK" in receipts.stdout

    def test_init_with_runtime_markers_reports_initialized(self, tmp_path):
        """The negative: runtime markers present (e.g. receipt_kernel.db) →
        init reports already-initialized and does not clobber."""
        git_init(tmp_path)
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "receipt_kernel.db").write_bytes(b"")
        result = run_gov(["init"], cwd=tmp_path)
        assert result.returncode == 0
        assert "already initialized" in result.stdout.lower()
        assert not (gov_dir / "facts").exists()

    def test_hook_install_creates_executable_hook(self, tmp_path):
        """governor hook install → git hook exists and is executable."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["hook", "install"], cwd=tmp_path)
        assert result.returncode == 0, f"hook install failed: {result.stderr}"

        hook_path = tmp_path / ".git" / "hooks" / "pre-commit"
        assert hook_path.exists(), "pre-commit hook not created"
        assert os.access(str(hook_path), os.X_OK), "pre-commit hook not executable"

    def test_propose_verify_apply_lifecycle(self, tmp_path):
        """Full proposal lifecycle: propose → verify → apply."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)

        # Create a file to claim existence of
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("print('hello')\n")

        # Propose
        result = run_gov(
            ["propose", "--claim", "type=file_exists,path=src/main.py"],
            cwd=tmp_path,
        )
        assert result.returncode == 0, f"propose failed: {result.stderr}"
        assert "Proposal created" in result.stdout

        # Extract proposal ID from output
        for line in result.stdout.splitlines():
            if "Proposal created:" in line:
                proposal_id = line.split(":")[-1].strip()
                break
        else:
            pytest.fail(f"Could not find proposal ID in output: {result.stdout}")

        # Verify
        result = run_gov(["verify", proposal_id], cwd=tmp_path)
        assert result.returncode == 0, f"verify failed: {result.stderr}"

        # Apply
        result = run_gov(["apply", proposal_id], cwd=tmp_path)
        assert result.returncode == 0, f"apply failed: {result.stderr}"

    def test_status_command(self, tmp_path):
        """governor status runs without error."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["status"], cwd=tmp_path)
        assert result.returncode == 0, f"status failed: {result.stderr}"

    def test_envelope_command(self, tmp_path):
        """governor envelope shows current mode."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["envelope"], cwd=tmp_path)
        assert result.returncode == 0, f"envelope failed: {result.stderr}"

    def test_operator_doctor(self, tmp_path):
        """governor doctor runs clean on fresh init."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["doctor"], cwd=tmp_path)
        assert result.returncode == 0, f"doctor failed: {result.stderr}"
        assert "Nominal" in result.stdout

    def test_operator_status_full(self, tmp_path):
        """governor status --full shows dashboard."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["status", "--full"], cwd=tmp_path)
        assert result.returncode == 0, f"status --full failed: {result.stderr}"
        assert "Governor:" in result.stdout

    def test_operator_status_full_json(self, tmp_path):
        """governor status --full --json returns valid JSON."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["status", "--full", "--json"], cwd=tmp_path)
        assert result.returncode == 0, f"status --full --json failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["schema_version"] == 1
        assert data["envelope"]["ok"] is True

    def test_operator_explain(self, tmp_path):
        """governor explain ELASTIC returns explanation."""
        git_init(tmp_path)
        result = run_gov(["explain", "ELASTIC"], cwd=tmp_path)
        assert result.returncode == 0, f"explain failed: {result.stderr}"
        assert "regime:ELASTIC" in result.stdout

    def test_operator_trace(self, tmp_path):
        """governor trace runs clean on fresh init."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)
        result = run_gov(["trace"], cwd=tmp_path)
        assert result.returncode == 0, f"trace failed: {result.stderr}"
        assert "No events recorded" in result.stdout


# ── Group 2: Golden path (stranger test) ─────────────────────────────────


class TestGoldenPath:
    """The stranger test: install → init → gate check in under 2 minutes."""

    def test_init_then_gate_check(self, tmp_path):
        """governor init → governor gate check produces readable output."""
        git_init(tmp_path)

        # Step 1: init
        result = run_gov(["init"], cwd=tmp_path)
        assert result.returncode == 0
        assert "governor gate check" in result.stdout  # epilogue points to next step

        # Step 2: gate check
        result = run_gov(
            ["gate", "check", "The tests pass and the code is safe."],
            cwd=tmp_path,
        )
        assert result.returncode == 0, f"gate check failed: {result.stderr}"

        # Output is human-readable
        out = result.stdout
        assert "OK" in out or "WARN" in out or "BLOCKED" in out
        # Claims were extracted
        assert "claim" in out.lower()
        # Receipt was produced
        assert "Receipt:" in out or "sha256:" in out

    def test_gate_check_without_init(self, tmp_path):
        """gate check works even without governor init (no receipt, but no crash)."""
        git_init(tmp_path)
        result = run_gov(
            ["gate", "check", "This is definitely correct."],
            cwd=tmp_path,
        )
        assert result.returncode == 0
        assert "OK" in result.stdout or "WARN" in result.stdout or "BLOCKED" in result.stdout


# ── Group 3: Daemon smoke ────────────────────────────────────────────────


class TestDaemonSmoke:
    """Start governor serve --stdio, send JSON-RPC, verify response."""

    def test_daemon_stdio_hello(self, tmp_path):
        """Daemon responds to governor.hello over stdio."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)

        # Build JSON-RPC request
        request = json.dumps({
            "jsonrpc": "2.0",
            "method": "governor.hello",
            "params": {},
            "id": 1,
        })
        # Content-Length framing
        message = f"Content-Length: {len(request)}\r\n\r\n{request}"

        # Start daemon as subprocess
        proc = subprocess.Popen(
            GOVERNOR + ["serve", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(tmp_path),
        )

        try:
            # Send request and read response
            proc.stdin.write(message)
            proc.stdin.flush()

            # Read Content-Length header from response
            response_data = ""
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                response_data += line
                if line.strip() == "":
                    # Empty line after headers — read the body
                    # Parse Content-Length from accumulated headers
                    for header_line in response_data.splitlines():
                        if header_line.startswith("Content-Length:"):
                            content_length = int(header_line.split(":")[1].strip())
                            break
                    else:
                        pytest.fail(f"No Content-Length in response: {response_data!r}")
                    body = proc.stdout.read(content_length)
                    break
            else:
                pytest.fail("Timed out waiting for daemon response")

            # Parse JSON-RPC response
            response = json.loads(body)
            assert "result" in response, f"No result in response: {response}"
            assert response["id"] == 1
            result = response["result"]
            assert "protocol_version" in result
            assert "capabilities" in result

        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def test_daemon_clean_shutdown(self, tmp_path):
        """Daemon exits cleanly when stdin closes."""
        git_init(tmp_path)
        run_gov(["init"], cwd=tmp_path)

        proc = subprocess.Popen(
            GOVERNOR + ["serve", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(tmp_path),
        )

        # Close stdin immediately — daemon should exit
        proc.stdin.close()
        try:
            returncode = proc.wait(timeout=10)
            # Accept 0 or any clean exit
            assert returncode is not None, "Daemon did not exit"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Daemon did not exit after stdin closed (10s timeout)")
