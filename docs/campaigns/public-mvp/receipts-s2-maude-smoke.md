# Sprint 2 · Packet 2.5 — Maude desk-surfaces LIVE-DAEMON smoke

**Campaign:** public-mvp (`docs/campaigns/public-mvp/CAMPAIGN.md`)
**Date:** 2026-07-05
**Gap closed:** maude readiness survey flagged *"desk screens verified offline only."*
This packet drives the three desk screens against a **real** governor daemon.

## Verdict

| Layer | Verdict | Evidence |
|-------|---------|----------|
| Daemon RPC (shell-contract surface) | **PASS** | `governor.hello`, `rpc list` (99 methods), `operator.decisions.list`, `runtime.adapters.list`, `runtime.session.list` all exit 0 with well-formed responses |
| Maude desk screens (live render) | **PASS** | QUEUE / SESSIONS / ADAPTERS all mounted + refreshed against the live socket, rendered live data (2 empty, 1 populated) with **zero exceptions**; corroborated by maude's own live-integration suite (32 passed / 1 skipped, exit 0) |

Both layers green. No source modified in either repo. No supervised Claude Code session launched.

## Setup (RAN)

- `governor`, version **2.8.1** (installed at `~/.local/bin/governor`, source `/home/jbeck/git/agent_gov`).
- Scratch workspace: `<scratch>/maude-smoke/`, `governor init` → exit 0.
- Daemon: `governor serve --socket /run/user/1000/governor-bcdfdbbc643f.sock` (PID 3541692), background.
  - **Note:** the originally-suggested `<scratch>/gov.sock` path exceeds the `AF_UNIX`
    108-char limit (`OSError: AF_UNIX path too long`) — the scratch dir path alone is ~95 chars.
    Fell back to a short `/run/user/1000/…` socket, which is also where the daemon's own
    `default_socket_path()` places sockets. Chose the **gov_dir-derived default name** so
    `governor rpc` (which computes the socket from gov_dir, no `--socket` flag) resolves it natively.
  - Socket path derivation confirmed: `default_socket_path(<scratch>/.governor)` →
    `/run/user/1000/governor-bcdfdbbc643f.sock`.

## Layer 1 — Daemon RPC smoke (RAN)

All calls via `governor rpc call <method>` from the scratch gov_dir against the live daemon.

**`governor.hello`** — exit **0**:
```json
{ "protocol_version": "1.0",
  "capabilities": { "chat": true, "streaming": true, "sessions": true, "intent": true,
                    "receipts": true, "scars": true, "commit": true, "signals_preflight": true,
                    "backend": { "type": "claude-code", "connected": true } },
  "governor": { "context_id": "default", "mode": "general", "initialized": true,
                "session_id": "gov_9383222628fe" },
  "standing": { "required": false, "secret_configured": false, "audience": "standing" } }
```

**`rpc list --json`** — exit **0**, `count: 99`. Shell-contract methods maude consumes, presence check:
```
YES operator.decisions.list      YES operator.watch
YES runtime.adapters.list        YES operator.decisions.resolve
YES governor.hello               YES runtime.autopilot.get
YES why.chain                    NO  session.get   (maude uses runtime.session.list instead; not a gap)
```

**`operator.decisions.list`** — exit **0**: `{"items": [], "count": 0}` (fresh workspace, empty feed — expected).

**`runtime.adapters.list`** — exit **0**, `count: 2`:
```json
{ "adapters": [
    { "backend_kind": "claude_code",
      "capabilities": { "supports_pause": false, "supports_resume": false,
        "supports_native_tool_hooks": true, "supports_structured_events": true,
        "supports_input_injection": true, "supports_graceful_shutdown": true } },
    { "backend_kind": "gemini_cli",
      "capabilities": { "supports_pause": false, "supports_resume": false,
        "supports_native_tool_hooks": true, "supports_structured_events": true,
        "supports_input_injection": false, "supports_graceful_shutdown": true } } ],
  "count": 2 }
```

**`runtime.session.list`** — exit **0**: `[]` (no supervised sessions — expected; none launched).

## Layer 2 — Maude desk screens, live render (RAN)

Method: a scratch driver (`<scratch>/maude-smoke/probe_text.py`, **not** committed to either repo, no
source modified) constructs a real `maude.client.rpc.GovernorClient(socket_path=<live sock>)`, mounts
each desk screen in a throwaway Textual `App` via `App.run_test()` (the same Pilot harness maude's own
screen tests use), pauses to let `on_mount → _do_refresh()` hit the live daemon, then reads the rendered
`Static` widget text. Screen→RPC wiring (from maude source): QueueScreen → `operator.decisions.list`,
BoardScreen → `runtime.session.list`, AdaptersScreen → `runtime.adapters.list`.

Rendered widget text captured from the live mount (exit **0**, no exceptions):

```
== QUEUE (operator.decisions.list) ==
  title  : 'QUEUE'
  status : '↑/↓ select · ctrl+r refresh · esc back'
  body[0]: 'No pending decisions.'            <- empty-state widget, matches count=0

== SESSIONS BOARD (runtime.session.list) ==
  title  : 'SESSIONS'
  status : '0 session(s) · ctrl+r refresh · esc back'
  body[0]: 'No active sessions.'              <- empty-state widget, matches []

== ADAPTERS (runtime.adapters.list) ==
  title  : 'ADAPTERS'
  status : '2 adapter(s) · ctrl+r refresh · esc back'
  body[0]: 'claude_code   ✗ pause  ✗ resume  ✓ steer  ✓ tool-hooks  ✓ events  ✓ graceful-stop'
  body[1]: 'gemini_cli   ✗ pause  ✗ resume  ✗ steer  ✓ tool-hooks  ✓ events  ✓ graceful-stop'
```

**Cross-check (load-bearing):** the ADAPTERS rows reflect the raw RPC exactly — `claude_code`
`supports_input_injection: true` → `✓ steer`; `gemini_cli` `false` → `✗ steer`. The screen is
rendering the daemon's live capability payload, not a fixture.

A separate driver (`drive_screens.py`) that additionally exercises each screen's explicit
`action_refresh_*` against the live socket returned `queue: PASS / board: PASS / adapters: PASS`,
`DRIVER_EXIT=0`.

**Corroboration — maude's own live-integration suite** against the same daemon:
```
GOVERNOR_SOCKET=<live sock> GOVERNOR_DIR=<scratch>/.governor \
  python3 -m pytest tests/test_operator_client.py tests/test_integration.py -q
32 passed, 1 skipped in 0.09s          PYTEST_EXIT=0
```
(The 1 skip is a backend/chat-dependent case; no real LLM backend was driven — token spend not authorized.)

## Obstructions

None blocking. One environment friction, worked around:

1. **AF_UNIX path-length limit vs. deep scratch dir.**
   - *What blocked:* `governor serve --socket <scratch>/gov.sock` → `OSError: AF_UNIX path too long`
     (kernel ~108-char limit; the scratch prefix alone is ~95 chars).
   - *Smallest unblock:* none needed for this packet — put the socket under `/run/user/1000`
     (short, and already the daemon's own default location). Documented here so the next
     operator running a live smoke from a deep scratch dir doesn't lose time to it.
   - *Lane:* environment/operational, not a code defect in either repo. (If a repo wanted to
     harden this, `agent_gov`'s `serve` could emit a clearer diagnostic than the raw `OSError`
     — minor, `agent_gov` lane.)

## RAN vs READ split

**RAN (executed against the live daemon):**
- `governor init`; `governor serve` (daemon up, PID 3541692); `governor rpc call governor.hello`;
  `governor rpc list --json`; `governor rpc call operator.decisions.list`;
  `governor rpc call runtime.adapters.list`; `governor rpc call runtime.session.list` — all exit 0.
- Scratch Textual drivers mounting QUEUE/SESSIONS/ADAPTERS screens against the live socket
  (`probe_text.py`, `drive_screens.py`) — exit 0, rendered text captured above.
- `pytest tests/test_operator_client.py tests/test_integration.py` against the live socket — exit 0.

**READ (inspected, not executed):**
- `governor` CLI `serve`/`rpc` help + `cli.py`/`daemon.py` socket-path derivation (`default_socket_path`).
- maude `client/rpc.py` socket resolution (`--socket` / `GOVERNOR_SOCKET` / gov_dir hash),
  screen sources (`screens/{queue,board,adapters,base}.py`), bindings in `app.py`
  (ctrl+g queue / ctrl+b sessions / ctrl+o adapters), `conftest.py`, `test-with-governor.sh`.

## Teardown

Scratch daemon (PID 3541692) killed and socket removed at end of packet. Scratch workspace left in
place under the session scratchpad. No changes to `agent_gov` or `maude` source.
