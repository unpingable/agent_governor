#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""AG-on-AG maintenance — slice 2 (capacity_refused legibility). Two-phase.

Operator-present manual dogfood. Same fence as slice 1 (pinned host AG supervises
a real inner `claude` editing a disposable detached AG worktree, LA-backed write
capacity, host byte-unchanged, NO PUSH) — but with better choreography:

  phase 1  design   : 0-unit grant. Writes are mechanically refused (read-only
                      enforced by the gate, not just the prompt). The worker reads
                      and returns a concrete file-and-edit PLAN. No mutation.
  --- outer reviews the plan; opens mutation authority ONLY if it is concrete ---
  phase 2  implement: 8-unit grant, NO refill. The worker executes the APPROVED
                      plan. Outer then inspects the diff + runs tests.

Usage:
  python3 working/agonag_slice2_driver.py design
  python3 working/agonag_slice2_driver.py implement <worktree_path> <plan_file>

Ratified schema (operator 2026-06-17): one authoritative retry_disposition +
scoped terminal_scope, NOT four drifting booleans. Only the LA InsufficientCapacity
-> capacity_refused path gets new_authority_required / current_grant; every other
refusal class defaults conservatively to `unknown`.
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from governor.linear_accountant_client import LinearAccountantClient
from governor.runtime.adapters.claude_code import ClaudeCodeAdapter
from governor.runtime.events import EventKind
from governor.runtime.la_subprocess import DEFAULT_LA_CLI, LASubprocess
from governor.runtime.supervisor import SessionSupervisor

AG_REPO = Path("/home/jbeck/git/agent_gov")
DEADLINE_S = 600
ADMISSION = "adm_agonag2"

SCHEMA_SPEC = (
    "RATIFIED SCHEMA (do not invent variants):\n"
    "  reason            = capacity_refused          # UNCHANGED, must stay stable\n"
    "  retry_disposition = <enum>                    # NEW authoritative field\n"
    "  terminal_scope    = <scope or None>           # NEW scoped terminality\n"
    "  message           = <optional human text>     # must AGREE with the machine fields\n"
    "retry_disposition enum (closed): retry_same_authority | retry_after_delay | "
    "new_authority_required | operator_action_required | never_retry | unknown.\n"
    "MAPPING DISCIPLINE (load-bearing): ONLY the LA InsufficientCapacity -> "
    "capacity_refused path is assigned retry_disposition=new_authority_required, "
    "terminal_scope=current_grant, with the human message 'Write capacity for this "
    "grant is exhausted. Retrying under the same grant cannot succeed.' EVERY other "
    "refusal class (already_consumed, no_session_grant, anything novel/legacy) "
    "defaults to retry_disposition=unknown (NOT retry_after_delay) and is NOT given "
    "guessed semantics. Do not decree one retry policy for the whole bucket."
)

ACCEPTANCE = (
    "ACCEPTANCE: (1) existing `reason` values stay stable; (2) InsufficientCapacity "
    "becomes terminal under the current grant and explicitly requires new authority; "
    "(3) [validated later, live] a worker receiving the payload won't retry the same "
    "denied write; (4) other refusal classes get NO guessed retry semantics; "
    "(5) unknown/legacy default to `unknown`, not retry_after_delay; (6) machine "
    "fields and human text agree; (7) tests pin serialization + backward compat; "
    "(8) NO change to LA policy or P4."
)

DESIGN_TASK = (
    "You are doing a READ-ONLY DESIGN PASS on a real Python codebase (the Agent "
    "Governor) in this directory. DO NOT EDIT ANY FILE. (Write/Edit are gated to "
    "zero capacity and will be refused — that is intentional; your job is a plan, "
    "not a change.)\n\n"
    "GOAL: design how to make a `capacity_refused` tool denial an intelligible "
    "control signal. Today the worker-facing deny payload carries `la_kind` + a "
    "prose `reason`; a worker can't tell 'retry later' from 'this authority is "
    "exhausted'.\n\n" + SCHEMA_SPEC + "\n\n" + ACCEPTANCE + "\n\n"
    "READ (free) at least: src/governor/runtime/lab_gate.py (LabEffectDecision, "
    "decide_write_effect), src/governor/runtime/supervisor.py (the TOOL_CALL_DENIED "
    "payload + the deny ControlAction, ~lines 600-640), "
    "src/governor/linear_accountant_client.py (the la_kind / refusal variants), and "
    "the relevant tests under tests/.\n\n"
    "RETURN A CONCRETE FILE-AND-EDIT PLAN identifying:\n"
    "  1. exactly where LA's decision becomes AG's worker-facing deny payload;\n"
    "  2. whether distinct LA refusal variants are already preserved (and where);\n"
    "  3. the MINIMUM schema-bearing object to carry retry_disposition/terminal_scope "
    "and how it reaches the worker;\n"
    "  4. backward-compatibility implications for existing clients/tests;\n"
    "  5. the specific files + the specific edits (function/class by name) you would "
    "make, and the tests you would add.\n"
    "Be concrete enough that another engineer could execute it. Then STOP — do not "
    "edit, commit, or push."
)


class _RecordingSink:
    def __init__(self):
        self.n = 0

    def emit(self, gate, verdict, *a, **k):
        self.n += 1
        return type("R", (), {"receipt_id": f"rcpt_{self.n}"})()


def _make_client(bridge, scope, units):
    bridge.deposit(scope, units)
    return LinearAccountantClient(
        request_capacity_callable=bridge.request_capacity,
        consume_callable=bridge.consume,
        admission_verifier=lambda rid: rid == ADMISSION,
        receipt_sink=_RecordingSink(),
    )


def _ctx(client, scope, units, identity):
    return {"bootstrap_lab": {
        "la_client": client, "actor": "inner_claude", "scope": scope,
        "requested_capacity": units, "admission_receipt_id": ADMISSION,
        "eligibility_valid_until": 1_000_000, "expires_after": 1_000_000, "now": 0,
        "la_boundary": identity.to_dict(),
    }}


def _run_session(wt: Path, task: str, scope: str, units: int):
    bridge = LASubprocess(DEFAULT_LA_CLI)
    identity = bridge.start()
    client = _make_client(bridge, scope, units)
    print(f"[outer] LA boundary: {identity.to_dict()['version']} repo={identity.to_dict().get('repo_commit','?')[:8]}")
    print(f"[outer] deposited {units} units into {scope!r} (NO top-up)")

    rt_dir = Path(tempfile.mkdtemp(prefix="agonag2_rt_"))
    sup = SessionSupervisor(state_dir=rt_dir)
    adapter = ClaudeCodeAdapter()
    record = sup.create_session(
        adapter, "claude_code", str(wt), task=task,
        operator_mode="autonomous", policy_context=_ctx(client, scope, units, identity),
    )
    print(f"[outer] session {record.session_id}; launching real claude…")
    sup.launch_session(record.session_id)

    start = time.monotonic()
    last_seq = 0
    exited = False
    while time.monotonic() - start < DEADLINE_S:
        for e in sup.get_events(record.session_id, since_seq=last_seq, limit=300):
            last_seq = max(last_seq, getattr(e, "seq", last_seq))
            print(f"  [evt] {e.kind} :: {json.dumps(e.payload)[:240]}")
            if e.kind in (EventKind.SESSION_EXITED, EventKind.SESSION_FAILED):
                exited = True
        if exited:
            break
        time.sleep(3)
    if not exited:
        print("[outer] deadline — killing inner session.")
        try:
            sup.kill_session(record.session_id)
        except Exception as ex:
            print(f"[outer] kill raised: {ex}")

    events = sup.get_events(record.session_id, since_seq=0, limit=3000)
    bridge.close()
    return sup, record, events, rt_dir


def _summarize(events):
    allowed = [e for e in events if e.kind == EventKind.TOOL_CALL_ALLOWED and e.payload.get("profile") == "bootstrap_lab"]
    denied = [e for e in events if e.kind == EventKind.TOOL_CALL_DENIED and e.payload.get("profile") == "bootstrap_lab"]
    return allowed, denied


def cmd_design():
    base = Path(tempfile.mkdtemp(prefix="agonag2_wt_"))
    wt = base / "ag"
    head = subprocess.run(["git", "-C", str(AG_REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(AG_REPO), "worktree", "add", "--detach", str(wt), head], check=True)
    print(f"[outer] DESIGN PASS — read-only (0-unit grant). worktree {wt} @ {head[:8]}")

    sup, record, events, rt_dir = _run_session(wt, DESIGN_TASK, "lab/agonag2-design", 0)
    allowed, denied = _summarize(events)
    plan = "\n".join(e.payload.get("text", "") for e in events if e.kind == "agent_output")
    plan_path = AG_REPO / "working" / "slice2_design_plan_raw.md"
    plan_path.write_text(plan)

    print("\n==================== SLICE 2 DESIGN PASS ====================")
    print(f"ALLOWED write effects (must be 0 — read-only): {len(allowed)}")
    print(f"REFUSED write effects (gate backstop if it tried): {len(denied)}")
    print(f"worktree (KEEP for implement): {wt}")
    print(f"raw plan text -> {plan_path} ({len(plan)} chars)")
    print("OUTER NEXT: review the plan; if concrete, write the approved plan to a")
    print("file and run:  python3 working/agonag_slice2_driver.py implement", wt, "<plan_file>")
    print("============================================================")
    return 0


def cmd_implement(wt_arg: str, plan_file: str):
    wt = Path(wt_arg)
    if not wt.exists():
        print(f"ENVIRONMENTAL BLOCK: worktree {wt} not found (run design first).")
        return 3
    plan = Path(plan_file).read_text()
    dirty = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    print(f"[outer] IMPLEMENT PASS — worktree {wt} (clean={not dirty})")

    task = (
        "You are editing a real Python codebase (the Agent Governor) in this "
        "directory. Execute the APPROVED plan below to make a `capacity_refused` "
        "denial an intelligible control signal. Make COHESIVE edits (a small grant "
        "gates each Edit; there is NO top-up). Modify the MINIMUM surface. DO NOT run "
        "Bash or tests (the outer controller runs them). When done, STATE the exact "
        "verification commands you expect, then STOP.\n\n"
        + SCHEMA_SPEC + "\n\n" + ACCEPTANCE + "\n\n"
        "APPROVED PLAN:\n" + plan
    )
    sup, record, events, rt_dir = _run_session(wt, task, "lab/agonag2-impl", 8)
    allowed, denied = _summarize(events)
    diff = subprocess.run(["git", "-C", str(wt), "diff"], capture_output=True, text=True).stdout
    changed = subprocess.run(["git", "-C", str(wt), "diff", "--name-only"], capture_output=True, text=True).stdout.strip()
    untracked = subprocess.run(["git", "-C", str(wt), "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True).stdout.strip()
    diff_path = AG_REPO / "working" / "agonag_slice2_worktree.diff"
    diff_path.write_text(diff)

    print("\n==================== SLICE 2 IMPLEMENT SPECIMEN ====================")
    print(f"ALLOWED effects: {len(allowed)} (consumes {[e.payload.get('consume_receipt_id') for e in allowed]})")
    print(f"REFUSED effects: {len(denied)}")
    for e in denied:
        print(f"   deny: la_kind={e.payload.get('la_kind')} reason={e.payload.get('reason')}")
    print(f"changed (tracked): {changed or '(none)'}")
    print(f"untracked: {untracked or '(none)'}")
    print(f"diff -> {diff_path} ({len(diff)} bytes); transcript {rt_dir}")
    print("OUTER NEXT: inspect diff -> run tests in worktree (PYTHONPATH={}/src) -> promote/reject. NO PUSH.".format(wt))
    print("===================================================================")
    return 0


def main():
    if not Path(DEFAULT_LA_CLI).exists():
        print(f"ENVIRONMENTAL BLOCK: la_cli not built at {DEFAULT_LA_CLI}.")
        return 3
    if len(sys.argv) < 2 or sys.argv[1] not in ("design", "implement"):
        print(__doc__)
        return 2
    if sys.argv[1] == "design":
        return cmd_design()
    if len(sys.argv) != 4:
        print("usage: implement <worktree_path> <plan_file>")
        return 2
    return cmd_implement(sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    sys.exit(main())
