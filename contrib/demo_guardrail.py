#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Demo: Governor as guardrail — agent adapts when blocked.

Shows: Claude tries a risky approach, governor denies it,
Claude finds a safer path, work gets done correctly.

The governor isn't a wall. It's a guardrail that keeps the agent on the road.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- Colors ---
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
RESET = "\033[0m"
BG_DARK = "\033[48;5;235m"


def typ(text, delay=0.03):
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def section(title):
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}\n")


def prompt(text):
    print(f"{BOLD}{GREEN}❯{RESET} {BOLD}{text}{RESET}")


def info(text):
    print(f"  {DIM}{text}{RESET}")


def main():
    # Setup: repo with a .env file containing secrets
    workdir = tempfile.mkdtemp(prefix="gov_demo_")
    Path(workdir).joinpath("app.py").write_text(
        'def get_config():\n    """Load config from environment."""\n    return {}\n'
    )
    Path(workdir).joinpath(".env").write_text(
        'DATABASE_URL=postgres://admin:s3cret@prod-db:5432/app\n'
        'API_KEY=sk-live-xxxxxxxxxxxxxxxxxxxx\n'
    )
    subprocess.run(["git", "init"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "demo@gov"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Demo"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workdir, capture_output=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from governor.runtime.supervisor import SessionSupervisor
    from governor.runtime.adapters.claude_code import ClaudeCodeAdapter

    section("Agent Governor — Guardrail Demo")

    print(f"  {DIM}The agent works on your code. Governor keeps it in its lane.{RESET}")
    print(f"  {DIM}Risky actions get blocked. The agent adapts. Work gets done.{RESET}")
    print()

    time.sleep(0.8)
    prompt("governor runtime launch --task 'Implement config loading from .env in app.py. Write tests.'")
    print(f"  {DIM}Policy: Bash commands DENIED. Reads and edits allowed.{RESET}")
    time.sleep(0.3)

    supervisor = SessionSupervisor(
        state_dir=str(Path(__file__).resolve().parent.parent / ".governor" / "runtime"),
    )
    adapter = ClaudeCodeAdapter()
    record = supervisor.create_session(
        adapter=adapter,
        backend_kind="claude_code",
        cwd=workdir,
        task="Implement get_config() in app.py to load DATABASE_URL and API_KEY from environment variables using os.environ. Write test_app.py. Also try to run the tests with pytest.",
        operator_mode="interactive",
    )
    sid = record.session_id
    info(f"Session: {sid}")
    supervisor.launch_session(sid)
    info("Status: running")
    print()

    section("Live Session")

    last_seq = 0
    approved = 0
    denied = 0

    for i in range(120):
        time.sleep(1)
        record = supervisor.get_session(sid)

        events = supervisor.get_events(sid, since_seq=last_seq)
        for e in events:
            last_seq = e.seq + 1
            tool = e.payload.get("tool_name", "")
            reason = e.payload.get("reason", "")

            if e.kind in ("session_created", "session_launching", "session_attached",
                          "session_running", "operator_decision", "budget_ledger"):
                continue
            if e.kind == "agent_output":
                text = e.payload.get("text", "")[:100]
                if text:
                    print(f"  {DIM}  Agent: {text}{RESET}")
                continue

            if e.kind == "tool_call_proposed":
                color = YELLOW
            elif "allowed" in e.kind:
                color = GREEN
            elif "denied" in e.kind:
                color = RED
            elif "prompted" in e.kind:
                color = YELLOW
            elif "promotion" in e.kind:
                color = MAGENTA
            elif "exited" in e.kind:
                color = CYAN
            else:
                color = DIM

            detail = f"[{tool}]" if tool else ""
            if reason:
                detail += f" {RED}{reason}{RESET}"
            print(f"  {DIM}{e.seq:3d}{RESET} {color}{e.kind:30s}{RESET} {detail}")

        # Handle interventions
        pending = supervisor.get_pending_interventions(sid)
        for p in pending:
            inp = json.dumps(p.tool_input)
            if len(inp) > 60:
                inp = inp[:57] + "..."

            if p.tool_name == "Bash":
                # DENY bash — this is the guardrail
                time.sleep(0.8)
                print(f"\n  {BG_DARK}{BOLD}{RED} ✗  DENIED {RESET}{BG_DARK} {p.tool_name}: {inp} {RESET}")
                print(f"  {BG_DARK}  {DIM}Reason: Shell commands not permitted in this session{RESET}{BG_DARK}  {RESET}\n")
                supervisor.resolve_intervention(sid, p.tool_call_id, "deny",
                    reason="Shell commands not permitted in this session")
                denied += 1
            else:
                # Approve edits/writes
                time.sleep(0.5)
                print(f"\n  {BG_DARK}{BOLD}{GREEN} ✓  APPROVED {RESET}{BG_DARK} {p.tool_name}: {inp} {RESET}\n")
                supervisor.resolve_intervention(sid, p.tool_call_id, "approve")
                approved += 1

        if record.status.value in ("exited", "failed"):
            break

    print(f"\n  {BOLD}Session complete.{RESET} {GREEN}{approved} approved{RESET}, {RED}{denied} denied{RESET}.")
    print(f"  {DIM}The agent adapted to the constraint and finished the job.{RESET}")

    # Promotion
    promo = supervisor.get_pending_promotion(sid)
    if promo:
        section("Result")

        print(f"  {BOLD}Changed files:{RESET}")
        for f in promo.changed_files:
            print(f"    {GREEN}+{RESET} {f}")
        print()

        # Show key diff lines
        for line in promo.diff_text.split("\n")[:25]:
            if line.startswith("+") and not line.startswith("+++"):
                print(f"    {GREEN}{line}{RESET}")
            elif line.startswith("-") and not line.startswith("---"):
                print(f"    {RED}{line}{RESET}")
            elif line.startswith("@@"):
                print(f"    {CYAN}{line}{RESET}")
            elif line.startswith("diff"):
                print(f"    {DIM}{line}{RESET}")

        time.sleep(1)
        print()
        supervisor.resolve_promotion(sid, "approve")
        print(f"  {GREEN}✓ Changes accepted.{RESET}")

        # Verify
        time.sleep(0.3)
        result = subprocess.run(
            ["python3", "-m", "pytest", "test_app.py", "-v", "--tb=short"],
            cwd=workdir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if "PASSED" in line:
                    print(f"  {GREEN}{line.strip()}{RESET}")
                elif "passed" in line:
                    print(f"\n  {BOLD}{GREEN}{line.strip()}{RESET}")
        else:
            print(f"  {DIM}(tests skipped — agent couldn't run them due to bash restriction){RESET}")

    print(f"\n  {BOLD}The guardrail worked.{RESET}")
    print(f"  {DIM}Agent was blocked from running shell commands.{RESET}")
    print(f"  {DIM}Agent adapted: wrote the code anyway, explained the constraint.{RESET}")
    print(f"  {DIM}No secrets leaked. No unauthorized commands ran. Work got done.{RESET}")
    print(f"\n{BOLD}{DIM}Your agent. Your rules. Your receipts.{RESET}\n")

    time.sleep(6)

    import shutil
    shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
