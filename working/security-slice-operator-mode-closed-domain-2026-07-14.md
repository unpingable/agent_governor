# Security slice — close the `operator_mode` domain and fail closed

**ID:** `operator-mode-closed-domain-fail-closed`  
**Filed:** 2026-07-14  
**Status:** **RULED 2026-07-15 (operator) — IMPLEMENTED, local, unpushed**  
**Class:** runtime authority seam / write-effect fail-open

## Disposition (2026-07-15)

Ruled and implemented as filed. Both fences landed; no scope was added.

| Repair | Site | Receipt |
|---|---|---|
| 1. Closed domain at ingress | `runtime/supervisor.py` `OPERATOR_MODES` + `create_session` | refuses before session ID or event file exists |
| 2. Fail-closed at the effect point | `runtime/supervisor.py` — `!= "autonomous"` replaces `== "interactive"` | a forged/restored record prompts instead of auto-approving |
| 3. CLI closed choice (optional) | `cli.py` `runtime launch --mode` | `click.Choice(case_sensitive=True)`; ergonomics, not the boundary |

Tests: `tests/test_operator_mode_closed_domain.py` — 21 pass, all seven
acceptance items covered. Full AG suite 16935 passed / 0 failed.

**Both fences were falsified before being trusted.** Reverting the effect point
to `== "interactive"` fails exactly the two malformed-record tests and nothing
else; removing the ingress validation fails the ingress, daemon-RPC, and fork
tests. The failing sets are disjoint, so neither fence is decorative.

**The reproduction now refuses at ingress**
(`ValueError: operator_mode must be one of 'interactive', 'autonomous'`) and so
exits 1 where it exited 0 at filing commit `e52355c`. That inversion is the
proof for fence 1. The script is retained unmodified as filed evidence; it can
no longer demonstrate fence 2, which is why acceptance tests 3–5 forge the
stored record directly rather than going through `create_session`.

Unrelated pre-existing flake observed while verifying, NOT touched:
`tests/test_runtime_golden.py::TestGoldenTrace::test_golden_event_sequence`
fails under full-suite CPU contention (bare `time.sleep(1)`), passes in
isolation and on a clean full-suite re-run. It uses only `interactive` and
`autonomous`, the two values where this slice's change is provably a no-op.

## Confirmed finding

`operator_mode` is accepted as an unvalidated value by
`runtime.session.create` (`src/governor/daemon.py:3401-3431`) and by
`SessionSupervisor.create_session` (`src/governor/runtime/supervisor.py:273-306`).
The effect path prompts for `WRITE` and `COMMUNICATE` only when the stored value
is exactly `"interactive"` (`supervisor.py:960-964`). Every other value reaches
the generic auto-approve branch (`supervisor.py:1075-1092`).

The bounded paired reproduction in
`working/repro-operator-mode-fail-open.py` uses a fake adapter whose write is
materialized only after it receives `ControlAction(kind="approve")`:

```text
interactive:
  prompted=1 pending=1 allowed=0 controls=[] write_exists=false
not-a-real-mode:
  prompted=0 pending=0 allowed=1 controls=[approve] write_exists=true auto=[true]
```

Run from the repository root:

```bash
python3 working/repro-operator-mode-fail-open.py
git status --short
```

The reproduction writes only below a temporary directory. At filing commit
`e52355c`, it exited 0 and left the tracked tree unchanged.

The real adapters make the result effect-bearing rather than merely cosmetic:
Claude Code and Gemini translate `approve` into a hook allow decision
(`runtime/adapters/claude_code.py:521-530`,
`runtime/adapters/gemini_cli.py:381-390`).

## Smallest proposed repair

This section is a proposal, not authority to implement.

1. At `SessionSupervisor.create_session`, before allocating a session ID or
   writing an event file, require `operator_mode` to be a string and exactly one
   of `{interactive, autonomous}`. Otherwise raise `ValueError` naming the
   allowed values. This is the authoritative construction point and covers RPC,
   CLI, test, and direct callers.
2. Add a defense at the effect point: `WRITE` and `COMMUNICATE` require a prompt
   whenever `record.operator_mode != "autonomous"`. A malformed, restored, or
   forged record therefore cannot fail open. Existing exact-grant compression
   remains inside the current interactive path.
3. Optional ingress ergonomics only: make any CLI mode option a case-sensitive
   closed choice. CLI validation is not the security boundary.

## Compatibility impact

- Exact `interactive` behavior is unchanged.
- Exact `autonomous` behavior is unchanged. This slice does not decide whether
  autonomous mode itself is legitimate.
- Repository callers and documented surfaces use those two values; no supported
  third mode was found.
- Typos, case variants, surrounding whitespace, non-strings, and private custom
  modes change from silent de-facto autonomy to explicit refusal. That is the
  intentional breaking change.
- No `SessionRecord` wire migration is proposed. A malformed legacy in-memory
  record prompts for `WRITE`/`COMMUNICATE` rather than auto-approving.
- Reads remain auto-approved. Execution-grant, continuation, transition, LA,
  promotion, and canonical selection semantics are unchanged.

## Exact acceptance tests

1. `test_create_session_rejects_invalid_operator_mode_before_state_write`
   parametrizes `not-a-real-mode`, the empty string, `Interactive`, a padded
   `autonomous`, `None`, `1`, and `{}`; each refuses before creating a session or
   event file.
2. `test_daemon_runtime_session_create_rejects_invalid_operator_mode` proves the
   RPC reports the error and creates no session.
3. `test_malformed_session_record_write_fails_closed` mutates an otherwise valid
   stored record to a typo and proves: no write, no approve control, one prompt,
   one pending intervention, zero allow events.
4. `test_malformed_session_record_communicate_fails_closed` proves the same for
   a communication-class call such as `git push`.
5. `test_malformed_session_record_read_remains_auto_approved` prevents a blanket
   session deadlock.
6. Regression pins retain exact `interactive` prompting, exact `autonomous`
   auto-approval, and interactive in-envelope ExecutionGrant compression.
7. If the CLI choice is included, its invalid-mode test proves refusal occurs
   before supervisor construction.

## Non-goals and stop lines

- No change to autonomous execution semantics.
- No coupling to `NEXT`, campaigns, or portfolio state.
- No wiring of Plan Review, ScopeGrant, WorkContainer, or governed dispatch.
- No approval consumption, revocation, or successor semantics.
- No new operator mode.

Implementation requires an explicit ruling of this packet. The 2026-07-14
custody-reconciliation authorization permits this finding and packet only; it
does not authorize the repair.
