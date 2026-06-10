#!/usr/bin/env python3
"""Tick 1 operator supervision loop.

Polls the governor daemon for pending interventions on one supervised
session and resolves each against the declared Tick 1 scope fence,
fast enough to beat the 30s pre-tool-hook fail-open (GAP-A).

Actuation: primary path sends the approve/deny command through the Maude
TUI (screen stuff) so the operator console is the surface of record;
verification + fallback go through the daemon RPC directly. Every
decision is logged to a JSONL ledger with rationale.

Exits when the session reaches a terminal state.
"""
import asyncio
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/jbeck/git/maude/src")
from maude.client.rpc import GovernorClient  # noqa: E402

SOCKET = sys.argv[1]
SESSION_ID = sys.argv[2]
SCREEN = sys.argv[3] if len(sys.argv) > 3 else "maude-tick"
LEDGER = Path("/home/jbeck/git/agent_gov/.tick/tick02-decisions.jsonl")

NQ = "/home/jbeck/git/notquery"
SCOPE_PREFIX = f"{NQ}/crates/nq-db/"

ALLOWED_CARGO = re.compile(r"^\s*cargo\s+(test|build|check|fmt|clippy)\b")
READONLY_BASH = re.compile(
    r"^\s*(rg|grep|ls|cat|head|tail|find|wc|tree|git\s+(diff|status|log|show)|cargo\s+metadata)\b"
)
# Tick 1 GAP-H fix: the old r">>?" flagged "2>&1" / ">/dev/null" as file writes.
# Strip safe stderr/null redirects first, THEN look for a real file-write redirect.
SAFE_REDIRECT = re.compile(r"2>&1|&>\s*/dev/null|2?>>?\s*/dev/null")
FILE_WRITE_REDIRECT = re.compile(r">>?")
FORBIDDEN_BASH = re.compile(
    r"(\brm\b|\bmv\b|\bcp\b|\bcurl\b|\bwget\b|\btee\b|\bchmod\b|"
    r"git\s+(commit|push|checkout|clean|add|reset)|\bsed\s+-i|\bpip\b|\bnpm\b)"
)


def classify(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """Return (decision, rationale) for one proposed tool call."""
    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = tool_input.get("file_path", "")
        if path.startswith(SCOPE_PREFIX):
            return "approve", f"file edit inside scope fence: {path}"
        return "deny", f"file edit outside Tick 2 scope fence (crates/nq-db): {path}"
    if tool_name == "TodoWrite":
        return "approve", "agent-internal todo bookkeeping, no workspace mutation"
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if FORBIDDEN_BASH.search(cmd):
            return "deny", f"forbidden pattern for Tick 2 (mutation/egress/git): {cmd[:120]}"
        if FILE_WRITE_REDIRECT.search(SAFE_REDIRECT.sub("", cmd)):
            return "deny", f"file-write redirect outside the Edit gate: {cmd[:120]}"
        if ALLOWED_CARGO.search(cmd):
            return "approve", f"cargo verification command: {cmd[:120]}"
        if READONLY_BASH.search(cmd):
            return "approve", f"read-only inspection command: {cmd[:120]}"
        return "deny", f"bash command not on Tick 2 allowlist: {cmd[:120]}"
    if tool_name in ("WebFetch", "WebSearch"):
        return "deny", "network egress out of scope for Tick 2"
    return "deny", f"tool {tool_name} not on Tick 2 allowlist"


def log_decision(record: dict) -> None:
    record["at"] = datetime.now(timezone.utc).isoformat()
    with LEDGER.open("a") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps({k: record[k] for k in ("decision", "tool_name", "rationale")}),
          flush=True)


async def resolve(client: GovernorClient, tcid: str, decision: str, rationale: str,
                  tool_name: str) -> None:
    # Tick 2 drives via daemon RPC directly. Maude console drivability was already
    # dogfooded in Tick 1 (GAP-E/F/G); the downgrade experiment targets the
    # fail-closed gate + packet + cheap model, so RPC-direct keeps the run clean.
    await client.runtime_intervention_resolve(
        SESSION_ID, tcid, decision,
        reason=rationale if decision == "deny" else None)
    log_decision({
        "tool_call_id": tcid, "tool_name": tool_name,
        "decision": decision, "rationale": rationale, "actuation": "rpc-direct",
    })


async def main() -> None:
    client = GovernorClient(socket_path=SOCKET)
    seen: set[str] = set()
    start = time.monotonic()
    while True:
        try:
            pending = await client.runtime_intervention_list(SESSION_ID)
        except Exception as exc:  # daemon hiccup: report, retry
            print(f"POLL_ERROR {exc}", flush=True)
            await asyncio.sleep(3)
            continue
        for item in pending:
            tcid = item["tool_call_id"]
            if tcid in seen:
                continue
            seen.add(tcid)
            decision, rationale = classify(item["tool_name"], item.get("tool_input", {}))
            await resolve(client, tcid, decision, rationale, item["tool_name"])
        sessions = await client.runtime_session_list()
        rec = next((s for s in sessions if s["session_id"] == SESSION_ID), None)
        if rec and rec["status"] in ("exited", "failed", "killed"):
            print(f"SESSION_TERMINAL {rec['status']}", flush=True)
            return
        if time.monotonic() - start > 3300:
            print("LOOP_TIMEOUT 55min", flush=True)
            return
        await asyncio.sleep(2)


asyncio.run(main())
