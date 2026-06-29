# Live-Adapter Allowlist Review — GATE before any live external-agent code

> **Ration card exists. No one has eaten with it yet.**
>
> **Passing this review authorizes a SANDBOX EXPERIMENT, not operational
> external-agent use.** "Operator reviewed the allowlist" is NOT "permission to
> eat the furniture." A reviewed card + a green sandbox slice is a demonstration
> of structure (origin `stub`/`drill` → `DemonstratedConsumed`, effect fenced by
> Wall 1); operational external-agent use is a *separate, later, separately-
> ratified* decision. The card is the contract; the sandbox is the cage; review
> ratifies the contract, not the conferral of real-world effect.

This is a **review gate**, not an implementation doc. Before a single line of
live-adapter code (a `RationedAgentRunner` backed by a real Claude Code / Gemini
runtime), the ration-card terms below must get a **fresh-eyes operator pass**.
"Mechanical wiring to live Claude Code" is the sentence engraved above many small
craters; the contract is done, but the *terms* are a human decision.

Scope of the first live slice (do NOT exceed): **live adapter binding, sandbox
only, one-shot only, no loop.** Bounded autopilot is explicitly NOT next.

The mechanism that enforces these terms already exists and is tested
(`src/governor/playbooks/ration_card.py`, `tests/test_ration_card_dispatch.py`).
This doc fills in the *values* the first real card will carry, and surfaces the
open questions. Each row is a decision to ratify, defer, or tighten.

**Operator pass completed 2026-06-29 (conservative defaults).** Every row below is
DECIDED and the four open questions are answered. The decisions prove *ration
consumption and refusal behavior*, not that a live agent can be trusted with
real-world effect. Full rationale per term follows the table.

| Term | S7 mechanism (already enforced) | Operator decision (2026-06-29) | |
|------|----------------------------------|--------------------------------|--|
| **Allowed agent** | `RationCard.agent_id`, exact match | Named adapter identity only; first slice `stub_origin` / `DemonstratedConsumed`. No registry / interface lookup. | ☑ |
| **Allowed commands** | `RationCard.allowed_shell_commands`, request ⊆ card | Exact-argv allowlist, `shell=False`. No shell strings, no user-supplied executable path, no templating beyond bounded in-sandbox input paths. | ☑ |
| **Allowed paths** | `RationCard.allowed_write_paths`, request ⊆ card AND agent output ⊆ card | Read-only input snapshot; writable only per-run output / transcript / receipt dirs. No write to the real checkout. | ☑ |
| **Forbidden writes** | absence-restrictive: anything not listed is refused | `.git/**`, doctrine/control-plane, credentials, `$HOME`, real checkout, CI/config, anything outside per-run writable dirs. **A forbidden-write attempt invalidates the run even on exit 0.** | ☑ |
| **Git** | `git_allowed` locked False by type | Locked-false-by-type; no override in this slice. No git commands, refs, index, credentials. Reading `.git` also denied. | ☑ (locked) |
| **Doctrine** | `doctrine_writes_allowed` locked False by type | Locked-false-by-type; no override. May produce a proposal; may not edit doctrine / governance state / gates / playbook defs / approval records. | ☑ (locked) |
| **Network** | `network_allowed` locked False by type | Locked-false-by-type; sandbox runs with no network. No installs, API calls, fetches, telemetry, plugin downloads, auth flows. | ☑ (locked) |
| **Transcript handling** | report carries `transcript_digest` only; raw text never in a receipt | Tainted audit-only, non-authoritative. May hash / archive / redact / display. May not be read as fact, decision, receipt, approval, or state transition. | ☑ |
| **Kill / refusal** | `refusal_check` consulted first; refusal wins before any spend | Fail-closed global + per-run kill switch (`PLAYBOOKS_RATION_KILL=1` and/or `.playbooks-kill` sentinel); checked before launch and during run; TERM-then-KILL; activation records a failed receipt. Adapter may not write/clear the switch. | ☑ |
| **Replay behavior** | durable spend gate refuses a replayed spend → `DispatchNotRun`, runner not called | Replay/stub preferred. Live requires explicit card + explicit operator approval + explicit live/sandbox mode. A replay fixture suppresses live execution unless the operator deliberately overrides. | ☑ |
| **Receipt expectations** | dispatch report is `verdict=observe`, `non_authoritative=True`, fails `is_authority_admission_receipt`, cites the LA consume as parent | Structured receipt required (fields below). **No valid receipt, no downstream consumption.** The report is the only artifact that escapes the dispatch, and it is inert. | ☑ |

## Operator decisions — full rationale

### 1. Allowed agent — named identity only, stub-origin first
Allowed agent is the explicitly configured `runtime.adapters.claude_code` adapter
identity, but the first post-review slice must demonstrate consumption through
`stub_origin` / `DemonstratedConsumed` only. No generic agent registry lookup, no
ambient "any adapter implementing interface X." Rationale: avoid *interface
laundering*, where anything that quacks like an agent gets authority.

### 2. Allowed commands — exact argv, no shell
Allowed command invocation must be exact-argv, adapter-owned, launched with
`shell=False`. No shell strings, no user-supplied executable path, no command
templating except bounded prompt/input file paths already inside the sandbox. **The
allowlist governs only the outer adapter process. It does not make subprocesses
safe; that safety must come from the sandbox cage.**

### 3. Allowed paths — read-only input, narrow writable run dir
Readable: sandboxed repo snapshot (read-only), the ration-card file, explicit
prompt/input files. Writable: per-run output dir, per-run transcript dir, per-run
receipt file. No writes to the real checkout, `.git`, doctrine/control-plane
material, `$HOME`, global config, caches, credentials, or parent directories.

### 4. Forbidden writes — hard fail, even on exit 0
Forbidden writes include `.git/**`, doctrine/control-plane paths,
network/configuration files, credentials, user home, the real repository checkout,
CI config, and any path outside the per-run sandbox output area. **A forbidden-write
attempt invalidates the run even if the process exits zero** — otherwise the
adapter can "succeed" while quietly taking a bite out of the furniture.

### 5. Git authority — locked false
Git authority remains locked-false-by-type. The adapter may not run git commands,
mutate refs, inspect credentials, write commits, change branches, or update the
index. Reading `.git` is also denied (no specific reason to allow it).

### 6. Doctrine authority — locked false
Doctrine/control-plane authority remains locked-false-by-type. The adapter may not
edit doctrine, governance state, gates, playbook definitions, policy docs, or
approval records. The live adapter can produce a *proposal*; it cannot update the
constitution.

### 7. Network authority — locked false
Network remains locked-false-by-type. The sandbox must run without network access:
no package installs, API calls, remote fetches, telemetry, plugin downloads, or
auth flows. ("Helpfully install dependency" is the gateway drug to "why is my CI
token in Singapore?")

### 8. Transcript handling — audit-only, non-authoritative, tainted
The transcript may be stored for audit and debugging, but it is not authority.
Downstream code may hash, archive, redact, or display it. Downstream code may not
treat transcript claims as facts, decisions, receipts, approvals, or state
transitions. Any downstream use must cite a structured receipt or explicit output
artifact, not the model transcript.

### 9. Kill switch — fail-closed, global + per-run
The runner must check a global kill switch before launch and during execution where
practical. If tripped, it refuses new runs and terminates active runs with
TERM-then-KILL. Kill-switch activation records a failed receipt. Forms:
`PLAYBOOKS_RATION_KILL=1` and/or a sandbox sentinel file `.playbooks-kill`. The live
adapter may **not** write or clear the kill switch.

### 10. Replay bias — replay/stub preferred, live needs explicit mode
Default behavior prefers replay/stub origins. Live adapter execution must require an
explicit ration card, explicit operator approval, and explicit live/sandbox mode.
Presence of a replay fixture should suppress live execution unless the operator
deliberately overrides for an experiment. This prevents tests from "accidentally"
becoming live ops.

### 11. Receipt expectations — structured receipt required
No receipt means no run. Minimum receipt fields:

```text
run_id
origin_kind                  # stub/replay/live
agent_id
adapter_id
ration_card_hash
input_hash
transcript_hash
output_hash
sandbox_id
cwd
allowed_paths
write_manifest
forbidden_write_detected
command_argv_hash
started_at
ended_at
duration_ms
timeout_ms
exit_code
timed_out
killed
network_allowed=false
git_allowed=false
doctrine_allowed=false
result_status               # consumed/refused/failed/timed_out/killed
```

Rule: **no valid receipt, no downstream consumption.**

## Open questions — answered (2026-06-29)

### Q1. Sandbox boundary — what is the actual cage?
**Python is not the cage. Python is only the clerk.** The cage must be
OS/container-enforced: disposable per-run workspace, read-only mounted input
snapshot, narrow writable output/transcript directory, non-root user, no network,
no host credentials, no host `$HOME`, process/time limits, environment allowlist,
post-run write-manifest validation. Acceptable first backend: Docker / Podman /
bubblewrap-style abstraction, per environment. Contract: **the runner must not claim
sandbox safety unless the cage backend confirms isolation properties.** For the
first slice it is fine to stub/demonstrate the cage *contract*; it is **not** fine
to pretend `subprocess.run()` is containment.

### Q2. Transcript trust — is it read downstream?
Yes, but only as **tainted audit material.** Allowed: archive, hash, redact, display
to a human reviewer, debug a failed sandbox experiment. Forbidden: treating
transcript text as an approval or receipt, extracting state transitions from
transcript prose, using transcript claims to update doctrine/playbook/governance
state, feeding the transcript into an autonomous loop as authority. The structured
receipt is authoritative; the transcript is evidence at best.

### Q3. One-shot completion and timeout.
**One-shot = exactly one adapter invocation for one ration card**, producing at most
one receipt and one bounded output set. No recursive calls, no loop continuation, no
self-scheduling, no follow-up task queue, no "continue until done." A run is complete
only when: (1) the adapter process exits, times out, or is killed; (2) the sandbox is
sealed; (3) writes are inspected; (4) a receipt is emitted; (5) receipt validation
passes or records failure. A hung runner is forcibly terminated at the configured
per-run timeout (failed/`timed_out` receipt). First-slice timeout deliberately low
(**30–60 s**) — the point is proving control flow, not doing useful work. Partial
transcript/output may be retained as tainted audit material but cannot be consumed as
success.

### Q4. Origin mode — does the first slice stay `stub_origin` / `DemonstratedConsumed`?
**Yes. Firmly.** The first post-review implementation slice remains non-operational:
`stub_origin`, `DemonstratedConsumed`, no live Claude Code execution, no loop, no
git, no doctrine mutation, no network. It proves: *given a ration card, the runner
consumes/refuses it correctly and emits a receipt* — not *Claude Code can now roam
the enclosure.* A real operational dispatch (`observed` origin +
`confer_operational_effect`) is a separate, later, separately-ratified gate.

## What this gate does NOT cover

- The bounded autopilot loop (a separate, later, also-gated slice).
- Any card that opens git / doctrine / network / non-observe output (locked by type
  in this slice; opening them is a future ratified change with its own review).

## Exit of this review — PASSED 2026-06-29

Every row has an operator decision and the four open questions are answered, so the
live-adapter binding may now be written — and only then, sandbox-only, one-shot-only,
no loop. **A fully-passed review buys exactly one thing: a sandbox experiment.** It
does not buy operational external-agent use, a loop, or a widened card; each of those
is its own gate.

The decision doc *is* the slice (B-8); no runner code was written under it. The
ratified terms unlock the following sequence, each its own commit and its own stop:

- **B-9** — runner contract tests: missing/invalid card refuses; forbidden authority
  refuses; stub-origin card consumes; receipt emitted; timeout path emits failed
  receipt; kill switch refuses/kills. No live Claude Code.
- **B-10** — minimal `RationedAgentRunner`: smallest runner that passes B-9 using
  stub/demo origin. No live subprocess, loop, network, git, or doctrine writes.
- **B-11** — sandbox cage contract: cage interface + fake cage for tests; a real
  local backend only if it can prove no-network / read-only / write-dir behavior.
- **B-12** — live adapter sandbox experiment: one explicit manual experiment, one
  ration card, one sandbox, one adapter invocation, one receipt, stop.

**Bounded autopilot is NOT in this sequence.** It is a separate, later, separately-
ratified gate. The conveyor is `decision → spec test → implementation → receipt →
next gate` — no "continue," no "improve," no border-moving between slices.
