# Tock 1 — supervised pre-tool gate fails closed

Campaign: `working/campaign-tick-tock-builder-ratchet.md`
Date: 2026-06-10
Forcing gap: **GAP-A** (`working/tick-01-nq-masthead.md`) — pre-tool hook abandoned
its supervisor wait after a hardcoded 30s and ALLOWED, making the write gate
advisory whenever the operator was slower than 30 seconds or absent.

**Exit state: shipped and drill-verified.**

## What changed (one capability, nothing else)

`src/governor/runtime/adapters/claude_code.py`:
- `_SUPERVISED_PRE_TOOL_SCRIPT` rewritten fail-closed: decision timeout, socket
  connect/IO error, missing `GOVERNOR_SUPERVISOR_SOCKET`, unparseable stdin,
  garbage or unrecognized supervisor response — every path DENIES with an explicit
  reason. Only a literal `{"decision": "allow"}` allows. Silence is never an allow.
- Hook wait = supervisor decision window (`GOVERNOR_DECISION_TIMEOUT` env) +
  `HOOK_WAIT_GRACE` (30s). Under normal operation the supervisor's own timeout
  watcher auto-denies at the window and answers over the socket; the hook deadline
  is purely a backstop for a hung/dead supervisor — and it too fails closed.
- Settings-level `PreToolUse` hook timeout raised from 30s to decision window +
  grace + 30s. This was a second, independent 30s fail-open: Claude Code treats a
  hook it kills at timeout as a non-blocking error and PROCEEDS with the tool call.
  The kill deadline now sits strictly behind the script's deny deadline.
- Settings construction extracted to `build_isolated_settings()` (testable).

`src/governor/runtime/supervisor.py`:
- `launch_session` threads `self._default_timeout` into `LaunchConfig.env` as
  `GOVERNOR_DECISION_TIMEOUT`, so backend-side gates wait at least as long as the
  supervisor's timeout watcher before failing closed.

Out of scope, deliberately (per the tock rule): GAP-B FSM transition, GAP-C
failed-session promotion, GAP-D ghost approvals, cwd wiring, spend metering,
promotion receipts, read fencing.

## Acceptance evidence

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | Timeout → deny w/ reason | unit `test_deny_on_decision_timeout`; live drill events 6–7, 10–11 |
| 2 | Socket error/unavailable → deny w/ reason | units `test_deny_on_unreachable_socket`, `test_deny_on_missing_socket_env` |
| 3 | Wait matches intervention timeout, not 30s | live drill denied at exactly proposed+300s; units `test_supervisor_threads_decision_timeout_into_launch_env`, `test_settings_hook_timeout_covers_decision_window` |
| 4 | Denial in event ledger | drill `tool_call_denied` + `operator_decision(reason="Intervention timeout")`; unit `test_intervention_timeout_denies_and_is_ledgered` |
| 5 | Agent receives denial, not silence | drill agent output: "drill.txt was **not** created. Both attempts… failed with an Intervention timeout"; deny JSON path unit-tested |
| 6 | Existing allow/deny flow unchanged | `test_allow_response_is_silent_allow`, `test_deny_response_carries_operator_reason`, golden trace 9/9, plus the live Tick 1 session earlier today |
| 7 | Nothing unrelated touched | diff = hook script + settings timeout + env threading + tests |

Tests: `tests/test_pre_tool_fail_closed.py` (12 tests, executes the real hook
script as a subprocess against real Unix sockets) + golden trace regression
(2 source-inspection tests repointed at `build_isolated_settings`, same pins).
Runtime-adjacent subset: 364 passed.

**Live drill** (`sess_b76328acde5b`, ledger at `.tick/tock01-drill-events.jsonl`):
operator absent throughout; Write proposed 15:00:18 → denied 15:05:18 (300s,
"Intervention timeout") → agent retried → denied again 15:10:31 → agent reported
the file was not created → clean exit (returncode 0, no FSM violation, because
the denial resolved the intervention before exit). Workspace untouched
(`git status` clean). This is GAP-A's reproduction scenario from smoke 1/2, with
the outcome inverted.

Observation (not a defect): after the first denial the agent retried the same
write, burning a second full 300s window. Unattended sessions with absent
operators now fail *slowly and safely* rather than quickly and unsafely; if the
slowness ever matters, that's a future tick's gap to name.

## Named during this tock (not fixed — needs its own citation)

**GAP-M — Gemini adapter has the identical fail-open.**
`src/governor/runtime/adapters/gemini_cli.py:69,90`: `settimeout(30)` +
`except: pass  # Socket error = allow (fail-open)`. Same failure class, now a
*known* class (scars-as-evidence: no need to re-step on the rake live); fix is
mechanical replication of this tock but must ride its own tock citation.

## Ratchet state

> Tick 1 shipped masthead/posture legend.
> GAP-A proved supervised control fails open.
> Tock 1 makes the supervisor gate fail closed — drill-verified.

Next tick can carry real cargo under a gate that holds when the operator walks away.
