#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""AG-on-AG maintenance — slice 1 (#1 verify-run receipt naming).

Operator-present manual dogfood (NOT a pytest). First self-hosting specimen:
a pinned host AG supervises a REAL inner `claude` worker that edits a DISPOSABLE
AG worktree (detached @ 76e79b6), gated by a real LA-backed write-capacity grant.

Topology:
    operator -> outer controller (this script, driven by AG-Claude)
             -> AG supervised runtime (SessionSupervisor + ClaudeCodeAdapter)
             -> real `claude` CLI inner worker
             -> bootstrap_lab LA-backed effect gate -> real la_cli -> Rust accountant
             -> disposable AG worktree (detached @ 76e79b6)

Boundaries (campaign card working/campaign-ag-on-ag-maintenance.md):
  - host AG checkout byte-unchanged (worktree is a separate detached checkout);
  - supervisor state OUTSIDE the worktree (GAP-N dirty gate trophy);
  - 8 WRITE units, NO mid-session top-up (exhaustion closes the specimen);
  - inner worker: read broadly first, cohesive edits, minimum honest surface,
    NO Bash (outer runs tests), state expected verification cmds, then stop;
  - P4 parked, ActiveTunableStore irrelevant, profile=bootstrap_lab, NO PUSH.

This driver drives the inner worker and captures the specimen (allowed/refused
effects + the worktree diff). It does NOT run tests and does NOT promote —
those are explicit OUTER steps the controller performs after inspection.
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
PINNED_BASE = "76e79b6"
DEADLINE_S = 600
SCOPE = "lab/agonag1"
ADMISSION = "adm_agonag1"
GRANT_UNITS = 8

TASK = (
    "You are editing a REAL Python codebase (the Agent Governor) checked out in "
    "this working directory. Fix ONE defect and stop.\n\n"
    "DEFECT (#1, verifier receipt naming): `governor verify-run -- <cmd>` emits a "
    "receipt file named `ci_wrap_unit_tests_<hash>.json` regardless of the wrapped "
    "command, because `verify_run` defaults `ci_kind='unit_tests'` (src/governor/"
    "verify.py) and the receipt filename is built from ci_kind (src/governor/ci.py, "
    "`_write_bundle` directory mode: `f\"ci_wrap_{kind}_{uid}.json\"`). So a Lean "
    "`lake build` is mislabeled 'unit_tests' in the trail.\n\n"
    "REQUIRED FIX:\n"
    "  1. Add an optional, operator-supplied receipt LABEL that is PREFERRED for "
    "the on-disk filename. Thread it through verify_run -> ci_wrap -> _write_bundle "
    "and expose a `--label/-l` option on the `verify-run` CLI command (src/governor/"
    "cli.py).\n"
    "  2. When no label is supplied, fall back to a CONSERVATIVE normalized slug of "
    "the command's program name: basename(argv[0]) lowercased, non-alphanumerics -> "
    "underscore, truncated. e.g. `lake build` -> `lake`, `cargo test -p x` -> "
    "`cargo`. This is NOT a shell-parsing engine — only argv[0]'s basename.\n"
    "  3. CRITICAL — preserve receipt identity: the label must affect ONLY the "
    "on-disk filename. It must NOT enter the hashed evidence bundle or subject "
    "bytes; `receipt_id`, `subject_bytes`, and `evidence_hash` must stay "
    "byte-identical to today. (The actual command is already recorded in evidence "
    "as `command_display`, so the trail is already self-describing in content; only "
    "the filename is wrong.)\n"
    "  4. PRESERVE the existing CI-lane behavior: `ci_wrap` callers that pass no "
    "label keep the current `ci_wrap_{ci_kind}_{uid}.json` filename. Do not change "
    "the closed `ci_kind` vocabulary.\n"
    "  5. Add focused tests (in the existing tests/ layout — find the right file by "
    "reading) covering: operator label preferred; command-basename fallback when no "
    "label; and that receipt_id/subject hash is unchanged by the label.\n\n"
    "DISCIPLINE (the supervisor gates your write effects against a small bounded "
    "capacity grant):\n"
    "  - READ BROADLY FIRST. Read verify.py, ci.py, the verify-run CLI command, and "
    "the relevant existing test file BEFORE your first edit. Reads are free.\n"
    "  - Make COHESIVE edits, not iterative nibbling. Each Edit/Write consumes one "
    "unit of a small grant; there is no top-up.\n"
    "  - Modify the MINIMUM honest surface. The files named above are a hypothesis, "
    "not a shopping list — change only what the fix actually requires.\n"
    "  - DO NOT run Bash or run the tests yourself. The outer controller runs the "
    "test suite. Spending capacity on a test run wastes the grant.\n"
    "  - Do NOT build any coverage-tracking or domain-specific (e.g. Lean axiom) "
    "verification features — those are separate filed gaps and OUT OF SCOPE here.\n"
    "  - When done: STATE the exact verification commands you expect the outer "
    "controller to run (e.g. the pytest targets), then STOP. Do not promote, "
    "commit, or push."
)


class _RecordingSink:
    def __init__(self):
        self.n = 0
        self.log = []

    def emit(self, gate, verdict, *a, **k):
        self.n += 1
        self.log.append((gate, verdict, f"rcpt_{self.n}"))
        return type("R", (), {"receipt_id": f"rcpt_{self.n}"})()


def _disposable_ag_worktree() -> tuple[Path, Path]:
    """Detached AG worktree @ PINNED_BASE. Host checkout untouched."""
    base = Path(tempfile.mkdtemp(prefix="agonag_wt_"))
    target = base / "ag"
    subprocess.run(
        ["git", "-C", str(AG_REPO), "worktree", "add", "--detach", str(target), PINNED_BASE],
        check=True,
    )
    return base, target


def main():
    if not Path(DEFAULT_LA_CLI).exists():
        print(f"ENVIRONMENTAL BLOCK: la_cli not built at {DEFAULT_LA_CLI}.")
        return 3

    base, wt = _disposable_ag_worktree()
    head = subprocess.run(["git", "-C", str(wt), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    print(f"[outer] disposable AG worktree: {wt} @ {head} (clean={not dirty})")

    bridge = LASubprocess(DEFAULT_LA_CLI)
    identity = bridge.start()
    print(f"[outer] LA boundary: {identity.to_dict()}")
    bridge.deposit(SCOPE, GRANT_UNITS)
    print(f"[outer] deposited {GRANT_UNITS} units into scope {SCOPE!r} (NO top-up)")

    sink = _RecordingSink()
    client = LinearAccountantClient(
        request_capacity_callable=bridge.request_capacity,
        consume_callable=bridge.consume,
        admission_verifier=lambda rid: rid == ADMISSION,
        receipt_sink=sink,
    )
    ctx = {"bootstrap_lab": {
        "la_client": client, "actor": "inner_claude", "scope": SCOPE,
        "requested_capacity": GRANT_UNITS, "admission_receipt_id": ADMISSION,
        "eligibility_valid_until": 1_000_000, "expires_after": 1_000_000, "now": 0,
        "la_boundary": identity.to_dict(),
    }}

    rt_dir = Path(tempfile.mkdtemp(prefix="agonag_rt_"))  # state OUTSIDE the worktree
    sup = SessionSupervisor(state_dir=rt_dir)
    adapter = ClaudeCodeAdapter()
    record = sup.create_session(
        adapter, "claude_code", str(wt), task=TASK,
        operator_mode="autonomous", policy_context=ctx,
    )
    print(f"[outer] session {record.session_id} created; launching real claude…")
    sup.launch_session(record.session_id)

    start = time.monotonic()
    last_seq = 0
    exited = False
    while time.monotonic() - start < DEADLINE_S:
        for e in sup.get_events(record.session_id, since_seq=last_seq, limit=200):
            last_seq = max(last_seq, getattr(e, "seq", last_seq))
            print(f"  [evt] {e.kind} :: {json.dumps(e.payload)[:240]}")
            if e.kind in (EventKind.SESSION_EXITED, EventKind.SESSION_FAILED):
                exited = True
        if exited:
            break
        time.sleep(3)

    if not exited:
        print("[outer] deadline reached — STEERING: killing the inner session.")
        try:
            sup.kill_session(record.session_id)
        except Exception as ex:
            print(f"[outer] kill_session raised: {ex}")

    # ---- inspect the specimen ----
    events = sup.get_events(record.session_id, since_seq=0, limit=2000)
    allowed = [e for e in events if e.kind == EventKind.TOOL_CALL_ALLOWED
               and e.payload.get("profile") == "bootstrap_lab"]
    denied = [e for e in events if e.kind == EventKind.TOOL_CALL_DENIED
              and e.payload.get("profile") == "bootstrap_lab"]
    boundary = [e for e in events if e.kind == "la_boundary"]

    diff = subprocess.run(["git", "-C", str(wt), "diff", PINNED_BASE],
                          capture_output=True, text=True).stdout
    changed = subprocess.run(["git", "-C", str(wt), "diff", "--name-only", PINNED_BASE],
                             capture_output=True, text=True).stdout.strip()
    untracked = subprocess.run(["git", "-C", str(wt), "ls-files", "--others", "--exclude-standard"],
                               capture_output=True, text=True).stdout.strip()
    diff_path = AG_REPO / "working" / "agonag_slice1_worktree.diff"
    diff_path.write_text(diff)

    print("\n==================== AG-on-AG SLICE 1 SPECIMEN ====================")
    print(f"worktree: {wt} @ {head}")
    print(f"bootstrap_lab ALLOWED effects: {len(allowed)}")
    for e in allowed:
        print(f"   allow: tcid={e.payload.get('tool_call_id')} tool={e.payload.get('tool_name')} "
              f"la_kind={e.payload.get('la_kind')} consume={e.payload.get('consume_receipt_id')} "
              f"remaining={e.payload.get('remaining_capacity')}")
    print(f"bootstrap_lab REFUSED effects: {len(denied)}")
    for e in denied:
        print(f"   deny: tcid={e.payload.get('tool_call_id')} la_kind={e.payload.get('la_kind')} "
              f"reason={e.payload.get('reason')}")
    print(f"la_boundary: {[ (e.payload.get('version'), e.payload.get('commit')) for e in boundary ]}")
    print(f"get_budget (must be None — no BA3): {sup.get_budget(record.session_id)}")
    print(f"changed (tracked) files vs {PINNED_BASE}:\n{changed or '  (none)'}")
    print(f"untracked (new) files:\n{untracked or '  (none)'}")
    print(f"diff written to: {diff_path} ({len(diff)} bytes)")
    print(f"transcript: {rt_dir}")
    print("===================================================================")
    print("OUTER NEXT (manual): inspect the diff -> run targeted then broad tests "
          "in the worktree (PYTHONPATH={}/src) -> promote or reject. NO PUSH.".format(wt))

    bridge.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
