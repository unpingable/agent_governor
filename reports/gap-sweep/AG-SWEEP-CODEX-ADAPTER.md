verdict: contradicted

# AG-SWEEP-CODEX-ADAPTER

Pinned revision: `fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2`.

## Adjudication

The detected closure language is not a closure or shipment claim for this gap. In
`specs/gaps/GOV_GAP_CODEX_ADAPTER_001.md`, the words “closed” at lines 13 and
35–36 describe upstream GitHub issues #12683 and #14203. The gap's own operative
language says `Gap spec (parked — requires Rust fork of openai/codex)` at lines
6–7, makes the adapter conditional on a future fork at lines 93–100, and ends
`Parked` with revisit conditions at lines 102–107. Thus, if the sweep's
“closure language” is treated as a claim that this gap is closed or shipped,
that claim is contradicted at the pinned revision.

This is also recorded independently in
`working/gap-backlog-triage-2026-06-10.md:127`:

```text
GOV_GAP_CODEX_ADAPTER_001 — WRONG — parked/open; inventory said closed
```

The repository does not show a stale open gap whose implementation later
shipped. It shows the expected parked gap and a post-hoc Codex integration that
does not provide the gap's generic blocking lifecycle hooks.

## Named repository evidence

- `specs/gaps/GOV_GAP_CODEX_ADAPTER_001.md:6-7,25-29,51-79,93-107` — the
  target remains parked; it names the missing pre-mutation hook,
  pre-completion hook, and tool-generic payload, then describes an unexecuted
  three-phase private-fork patch plan.
- `src/governor/codex_hooks.py:3-11` — the module says Codex has no native
  pre-tool hook and labels its implementation “full post-hoc audit.”
- `src/governor/codex_hooks.py:171-264` — `run_codex_governed` runs the Codex
  subprocess to completion before the post-snapshot diff and receipt emission.
- `src/governor/codex_hooks.py:267-313` — `_emit_receipt` evaluates already
  observed file changes, records `"enforcement": "posthoc"`, and catches every
  receipt error fail-open. A receipt whose verdict string is `block` therefore
  does not establish a pre-mutation veto.
- `src/governor/runtime/adapters/` — contains Claude Code and Gemini CLI
  adapters, but no Codex supervised-runtime adapter.
- `src/governor/daemon.py:3415-3422,3734-3747,3845-3852` and
  `src/governor/cli.py:19991-19999,20044-20052` — supervised runtime selection
  is wired only for `claude_code` and `gemini_cli`.
- `docs/AGENT_INTEGRATION.md:118-138,293-305` — documents no pre-tool
  blocking, post-hoc accountability, direct writes appearing ungoverned, and
  an MCP proxy as the future closure path.
- `docs/constellation-wire-plan.md:106-112` — classifies Codex as “audit only,
  no gating” and identifies only Claude Code and Gemini CLI as live runtime
  supervisor adapters.
- `working/CODEX_RATCHET_STANDING_GAP.md:19-29,85-95` — says the Codex
  supervised executor is missing and keeps that candidate parked.
- No `codex-rs/` tree or any of the Rust patch-plan paths named by the gap is
  present in this repository.

## Tests

`tests/test_codex_hooks.py` has 50 passing tests for the shipped post-hoc
wrapper. Relevant named tests are:

- `TestRunCodexGoverned::test_file_changes_detected` — supplies a post-run
  snapshot diff and confirms the already-created change is observed.
- `TestRunCodexGoverned::test_audit_trail_written` — confirms completed NDJSON
  events are logged.
- `TestEmitReceipt::test_unapproved_changes_block` — directly supplies an
  existing `FileChange` and confirms the resulting receipt's verdict string is
  `block`; it does not test prevention of the change.

There is no test in `tests/test_codex_hooks.py` for `PreToolUse`,
`PostToolUse`, `HookToolInput`, a real tool name/generic payload, MCP mutation
veto, pre-completion veto, or `tool_call_proposed`/`tool_call_completed`
supervisor mapping.

## Commands run and outputs

```text
$ git rev-parse HEAD
fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2
```

```text
$ find src/governor/runtime/adapters -maxdepth 1 -type f -printf '%f\n' | sort
__init__.py
antigravity_probe.py
antigravity_runner.py
claude_code.py
gemini_cli.py
```

```text
$ find . -type d -name codex-rs -print
(no output; exit 0)
```

```text
$ rg -n "PreToolUse|PostToolUse|HookToolInput|AfterToolUse|dispatch_any|hook_tool_kind|pre-mutation|pre-completion|stop_hook|tool_call_proposed|tool_call_completed" src/governor/codex_hooks.py tests/test_codex_hooks.py
(no output; exit 1: no matches)
```

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider --basetemp=/tmp/ag-sweep-codex-adapter-pytest tests/test_codex_hooks.py -q
..................................................                       [100%]
50 passed in 0.83s
```

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -p no:cacheprovider --basetemp=/tmp/ag-sweep-codex-adapter-focused tests/test_codex_hooks.py::TestRunCodexGoverned::test_file_changes_detected tests/test_codex_hooks.py::TestRunCodexGoverned::test_audit_trail_written tests/test_codex_hooks.py::TestEmitReceipt::test_unapproved_changes_block -vv
collected 3 items
tests/test_codex_hooks.py::TestRunCodexGoverned::test_file_changes_detected PASSED [ 33%]
tests/test_codex_hooks.py::TestRunCodexGoverned::test_audit_trail_written PASSED [ 66%]
tests/test_codex_hooks.py::TestEmitReceipt::test_unapproved_changes_block PASSED [100%]
3 passed in 0.78s
```

```text
$ git status --short
(no output; worktree clean before this report was created)
```

## What could not be verified

- The current state of upstream `openai/codex`, GitHub issues #12683/#14203,
  and the gap's v0.117.0 internal-schema assertions could not be verified from
  this pinned repository because upstream source is not vendored or pinned
  here.
- No external/private Codex fork is present, so its existence or behavior
  could not be verified.
- The tests mock the Codex subprocess; they do not verify behavior against a
  live Codex binary or prove an end-to-end pre-mutation/pre-completion veto.
- The decision that two backends are “sufficient for now” is normative and is
  not mechanically verifiable. It is not evidence that the Codex adapter
  shipped.
