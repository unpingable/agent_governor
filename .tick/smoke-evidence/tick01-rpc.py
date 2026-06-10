#!/usr/bin/env python3
"""Tick 1 operator helper: daemon RPC via Maude's client library.

Exists because Maude's `supervised launch` cannot pass cwd (gap evidence).
Usage: tick01-rpc.py <socket> <cmd> [args...]
  create <cwd> <task-file>     -> prints session_id
  launch <session_id>
  list
  events <session_id> [since]
  interventions <session_id>
  approve <session_id> <tool_call_id>
  deny <session_id> <tool_call_id> <reason>
  promotion <session_id>
  diff <session_id>
  promote <session_id>
  reject <session_id>
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/jbeck/git/maude/src")
from maude.client.rpc import GovernorClient  # noqa: E402


async def main() -> None:
    sock, cmd = sys.argv[1], sys.argv[2]
    client = GovernorClient(socket_path=sock)
    try:
        if cmd == "create":
            cwd, task_file = sys.argv[3], sys.argv[4]
            task = Path(task_file).read_text()
            result = await client.runtime_session_create(
                backend_kind="claude_code", cwd=cwd, task=task,
                operator_mode="interactive",
            )
            print(json.dumps(result, indent=2))
        elif cmd == "launch":
            print(json.dumps(await client.runtime_session_launch(sys.argv[3]), indent=2))
        elif cmd == "list":
            print(json.dumps(await client.runtime_session_list(), indent=2))
        elif cmd == "events":
            since = int(sys.argv[4]) if len(sys.argv) > 4 else 0
            events = await client.runtime_session_events(sys.argv[3], since_seq=since, limit=100)
            for e in events:
                print(json.dumps(e))
        elif cmd == "interventions":
            print(json.dumps(await client.runtime_intervention_list(sys.argv[3]), indent=2))
        elif cmd == "approve":
            print(json.dumps(await client.runtime_intervention_resolve(sys.argv[3], sys.argv[4], "approve"), indent=2))
        elif cmd == "deny":
            print(json.dumps(await client.runtime_intervention_resolve(sys.argv[3], sys.argv[4], "deny", reason=sys.argv[5]), indent=2))
        elif cmd == "promotion":
            print(json.dumps(await client.runtime_promotion_get(sys.argv[3]), indent=2))
        elif cmd == "diff":
            result = await client.runtime_promotion_diff(sys.argv[3])
            print(result.get("diff_text", "") if isinstance(result, dict) else result)
        elif cmd == "promote":
            print(json.dumps(await client.runtime_promotion_resolve(sys.argv[3], "approve"), indent=2))
        elif cmd == "reject":
            print(json.dumps(await client.runtime_promotion_resolve(sys.argv[3], "reject"), indent=2))
        else:
            print(f"unknown cmd {cmd}", file=sys.stderr)
            sys.exit(2)
    finally:
        close = getattr(client, "close", None)
        if close:
            result = close()
            if asyncio.iscoroutine(result):
                await result


asyncio.run(main())
