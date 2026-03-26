#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Demo script: run a real supervised session with pretty console output.

Usage:
    python3 contrib/demo_session.py

Records with asciinema:
    asciinema rec demo.cast -c "python3 contrib/demo_session.py"

Then convert to GIF:
    agg demo.cast demo.gif --theme monokai
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
    """Simulate typing."""
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


def event(seq, kind, detail=""):
    color = GREEN if "allowed" in kind or "approved" in kind else \
            RED if "denied" in kind else \
            YELLOW if "prompted" in kind or "proposed" in kind else \
            MAGENTA if "promotion" in kind else DIM
    print(f"  {DIM}{seq:3d}{RESET} {color}{kind:30s}{RESET} {detail}")


def intervention_card(tool_name, tool_input, remaining):
    print(f"\n  {BG_DARK}{BOLD}{YELLOW} ⚠  INTERVENTION {RESET}")
    print(f"  {BG_DARK}  Tool: {BOLD}{tool_name}{RESET}{BG_DARK}  Remaining: {remaining}s  {RESET}")
    inp_str = json.dumps(tool_input)
    if len(inp_str) > 80:
        inp_str = inp_str[:77] + "..."
    print(f"  {BG_DARK}  {DIM}{inp_str}{RESET}{BG_DARK}  {RESET}")
    print(f"  {BG_DARK}  {GREEN}[a]{RESET}{BG_DARK}pprove  {RED}[d]{RESET}{BG_DARK}eny  {DIM}[i]{RESET}{BG_DARK}nspect  {RESET}")
    print()


def main():
    # Setup scratch repo
    workdir = tempfile.mkdtemp(prefix="gov_demo_")
    Path(workdir).joinpath("users.py").write_text(
        'def get_user(user_id):\n    return {"id": user_id, "name": "unknown"}\n'
    )
    subprocess.run(["git", "init"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "demo@gov"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Demo"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=workdir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=workdir, capture_output=True)

    # Import governor
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from governor.runtime.supervisor import SessionSupervisor
    from governor.runtime.adapters.claude_code import ClaudeCodeAdapter

    section("Agent Governor — Supervised Session")

    print(f"  {DIM}Governor controls what the agent can do.{RESET}")
    print(f"  {DIM}Every tool call requires approval. Every change requires promotion.{RESET}")
    print()

    time.sleep(0.8)
    prompt("governor runtime launch --task 'Add input validation to get_user and write tests'")
    time.sleep(0.3)

    supervisor = SessionSupervisor(
        state_dir=str(Path(__file__).resolve().parent.parent / ".governor" / "runtime"),
    )
    adapter = ClaudeCodeAdapter()
    record = supervisor.create_session(
        adapter=adapter,
        backend_kind="claude_code",
        cwd=workdir,
        task="Add input validation to get_user (raise ValueError for non-positive IDs) and write test_users.py with tests. Run the tests.",
        operator_mode="interactive",
    )
    sid = record.session_id

    info(f"Session: {sid}")
    supervisor.launch_session(sid)
    record = supervisor.get_session(sid)
    info(f"PID: {record.pid}")
    info(f"Status: {record.status.value}")
    print()

    section("Live Session — Tool Interception")
    last_seq = 0
    approved_count = 0

    for i in range(120):
        time.sleep(1)
        record = supervisor.get_session(sid)

        # Show new events
        events = supervisor.get_events(sid, since_seq=last_seq)
        for e in events:
            last_seq = e.seq + 1
            tool = e.payload.get("tool_name", "")
            if e.kind in ("session_created", "session_launching", "session_attached", "session_running"):
                continue  # skip lifecycle noise
            if e.kind == "agent_output":
                continue  # show later
            if e.kind == "budget_ledger":
                continue
            detail = f"[{tool}]" if tool else ""
            event(e.seq, e.kind, detail)

        # Handle interventions
        pending = supervisor.get_pending_interventions(sid)
        for p in pending:
            intervention_card(p.tool_name, p.tool_input, int(p.remaining))
            time.sleep(1)  # Simulate operator reading

            typ(f"  {GREEN}→ approve{RESET}", delay=0.04)
            supervisor.resolve_intervention(sid, p.tool_call_id, "approve")
            approved_count += 1
            time.sleep(0.3)

        if record.status.value in ("exited", "failed"):
            break

    print(f"\n  {BOLD}Session complete.{RESET} {approved_count} tools approved.")

    # Show promotion
    promo = supervisor.get_pending_promotion(sid)
    if promo:
        section("Promotion Review")

        print(f"  {BOLD}Changed files:{RESET}")
        for f in promo.changed_files:
            print(f"    {GREEN}+{RESET} {f}")
        print()
        print(f"  {BOLD}Diff:{RESET}")
        for line in promo.diff_text.split("\n")[:30]:
            if line.startswith("+") and not line.startswith("+++"):
                print(f"    {GREEN}{line}{RESET}")
            elif line.startswith("-") and not line.startswith("---"):
                print(f"    {RED}{line}{RESET}")
            elif line.startswith("@@"):
                print(f"    {CYAN}{line}{RESET}")
            else:
                print(f"    {DIM}{line}{RESET}")

        time.sleep(1.5)
        print()
        prompt("governor runtime promote")
        time.sleep(0.3)
        supervisor.resolve_promotion(sid, "approve", reason="LGTM")
        print(f"  {GREEN}✓ Changes accepted.{RESET}")

        # Run tests
        time.sleep(0.5)
        print()
        prompt("python3 -m pytest test_users.py -v")
        result = subprocess.run(
            ["python3", "-m", "pytest", "test_users.py", "-v", "--tb=short"],
            cwd=workdir, capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().split("\n"):
            if "PASSED" in line:
                print(f"  {GREEN}{line.strip()}{RESET}")
            elif "FAILED" in line:
                print(f"  {RED}{line.strip()}{RESET}")
            elif "passed" in line:
                print(f"\n  {BOLD}{GREEN}{line.strip()}{RESET}")
            elif line.strip():
                print(f"  {DIM}{line.strip()}{RESET}")

    # Budget
    budget = supervisor.get_budget(sid)
    if budget:
        section("Budget")
        spend = budget.get("total_spend", {})
        print(f"  Steps:      {budget['total_steps']}")
        print(f"  Tool calls: {spend.get('tool_calls', 0)}")
        tokens = spend.get("total_tokens")
        print(f"  Tokens:     {tokens if tokens is not None else 'n/a (adapter limit)'}")
        violations = budget.get("violations", [])
        if violations:
            print(f"  {RED}Violations:  {len(violations)}{RESET}")
        else:
            print(f"  Violations: {GREEN}none{RESET}")

    print(f"\n{BOLD}{DIM}Agents propose. Governors verify. Receipts don't lie.{RESET}\n")

    # Hold for GIF loop point
    time.sleep(6)

    # Cleanup
    import shutil
    shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
