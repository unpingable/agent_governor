# Live-Adapter Allowlist Review — GATE before any live external-agent code

> ## ⛔ SUPERSEDED 2026-06-30 — FOSSIL. Do not act on this gate.
>
> **Operator ratified path (B) on 2026-06-30.** This gate reviewed an **in-AG** live
> adapter (`runtime.adapters.claude_code`, B-9..B-12). The architecture moved: H1
> established that live/offline actor execution belongs **outside AG**, in the H-series
> harness, and AG ingests only the inert `actor_output.v0` artifact. A passed-but-stale
> in-AG gate must not authorize the moved experiment.
>
> **This document is preserved as historical evidence only.** Its 11 ration-card terms
> are carried forward as *inherited constraints* by the successor gate. Do not build
> B-9..B-12; do not build an in-AG live adapter.
>
> **Successor gate (the real next one):** `docs/playbooks/harness-cage-review.md` —
> the H-series harness-cage review. Read that, not this, for any live-actor question.
>
> *(The full fresh-eyes reconciliation that produced this decision is the dated section
> "Fresh-eyes re-review (2026-06-30)" near the end of this file.)*

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

---

## Fresh-eyes re-review (2026-06-30) — the subject of this gate moved

> A review can pass and still go stale if the thing it authorized is no longer the
> thing you would build. This is additive: the 2026-06-29 record stands; this section
> reconciles it with what landed afterward. Review only — no code was written.

### A. The 11 terms are sound, and the locks are now CODE-VERIFIED (not just asserted)

The 2026-06-29 table is ratified and carries forward unchanged. Fresh-eyes added one
thing the original lacked: a read of the enforcing code. The dangerous axes are locked
closed by **three independent walls**, defense-in-depth, not one guard:

1. **Card construction** — `RationCard.__post_init__` (`ration_card.py`) *raises* on
   `git_allowed` / `doctrine_writes_allowed` / `network_allowed` / non-observe output.
   A card that opens them cannot be constructed.
2. **Request match** — `match_ration_card()` refuses `requested_git` / `requested_network`
   and any write/shell ⊄ card. The card is the allowlist at request time too.
3. **Origin admission** — `RationedAgentRunner.run()` refuses any `origin_kind ∉
   {stub, synthetic}` *before anything runs*; `admit_origin_under_cage()`
   (`sandbox_cage.py`) admits a live origin **only** under attested live isolation, and
   the only shipped cages (`NullCage`, `SyntheticCage`) attest **nothing** —
   `live_admission_permitted` is unconstructable for synthetic scope by
   `CageSafetyVerdict.__post_init__`.

Precise wording for the operator's "locked false by type" check: it is locked false by
**construction invariant + defense in depth** (the fields are `bool`, but no admissible
`RationCard` instance can hold `True`, and two further walls refuse it downstream). That
is *stronger* than the casual "by type" phrasing, and it is exercised by tests
(`tests/test_ration_card_dispatch.py`, `rationed_runner` / `sandbox_cage` suites).
**Confirmed: git / doctrine / network remain locked false.**

### B. The material change: live execution left AG

This review was passed for an **in-AG** live adapter — "a `RationedAgentRunner` backed
by a real Claude Code / Gemini runtime" (B-9..B-12), `allowed agent =
runtime.adapters.claude_code`, B-12 = "live adapter sandbox experiment ... one adapter
invocation." Since 2026-06-29:

- **The synthetic overnight conveyor (S1–S7) + H1 landed.** Doctrine: *the overnight
  system may create EVIDENCE, never FACTS.* The actor that actually runs now lives in
  the **external H-series harness, OUTSIDE AG** (`harness/`, H1 = `aa147c8`). AG never
  runs the actor; it ingests an inert `actor_output.v0` artifact (S7 → S5), and an
  actor-claimed passing test is still refused.
- **The in-AG runner structurally refuses live origins** (Wall 3 above). `rationed_runner.py`
  will never run a live actor — by construction, a live origin "requires a confirmed-safe
  cage, a future separately-gated slice" that does not exist.
- **B-12 was reframed as a decoy gate** (operator, 2026-06-29; `docs/REENTRY.md`):
  radioactive, operator-manual, blocked on a real cage backend, *not next*.
- **The current task constraints forbid the in-AG path outright**: no
  `runtime.adapters.claude_code`, no subprocess runner, no Claude Code run from inside
  AG, no live adapter.

So the experiment this review authorizes (in-AG, B-12) is no longer the experiment the
architecture points at. The terms are fine; the **home** changed.

### C. The four gate questions, re-answered

- **Q1 — What is the sandbox cage?** *Answer relocates.* The 2026-06-29 answer (OS/
  container cage wrapping an AG-internal subprocess; "Python is not the cage") is still
  the right *shape* — but the subprocess it would cage now lives in the **external
  harness**, not AG. AG's side has no live runner to cage. So Q1 is no longer AG's
  question to answer here; it becomes the **harness's** cage review (a future doc). The
  shipped `SyntheticCage`/`NullCage` honestly confirm nothing and admit no live origin —
  correct for AG's inert side.
- **Q2 — Downstream transcript discipline?** *Unchanged and already enforced.* H1's
  `actor_output.v0` carries `captured_text` as advisory only; S7 routes it to
  `design_notes`/`risks`, never to a passing test or authority; the structured
  ReviewPacket/receipt is the only authoritative artifact. Tainted-audit discipline holds.
- **Q3 — One-shot completion / hung-runner timeout?** *Unchanged as a term; lives where
  the runner lives.* The one-shot + low-timeout (30–60 s) + TERM-then-KILL + failed
  receipt rule is correct. Today the only in-AG runner (`rationed_runner`) already honors
  timeout/kill against no-process origins; a live timeout belongs to the harness when/if
  a live slice is authorized there.
- **Q4 — Does the first live slice stay `stub_origin` / `DemonstratedConsumed` /
  non-operational?** **Yes — firmly, and now over-determined.** AG cannot mint a live
  (`observed`) consumption on this path: the runner refuses live origins, and the H1
  ingest path is observe-only. `confer_operational_effect` (Wall 1) still requires
  `OperationalConsumed` (`observed` origin), which nothing on either side produces. The
  first slice is non-operational by construction, not by promise.

### D. The one unresolved decision (operator's to make)

Everything above is ratified or confirmed except **where a future live experiment
runs**. This is the only thing blocking a clean "authorize/refuse," and it is custody-
affecting (it changes a ratified gate's conclusion), so it is not mine to decide:

> **Decision needed:** Is the first live experiment (A) **in-AG**, behind a future
> confirmed cage + a live-origin runner — the original B-12 path, now *contradicted* by
> the current constraints and the H-series — or (B) **in the external H-series harness**,
> consistent with H1, in which case *this* in-AG review is **superseded** and the next
> gate is a **harness-cage review** (Q1 re-asked about the harness, not AG)?

The 11 ration-card terms apply unchanged to whichever home is chosen — they are the
contract AG enforces on what it dispatches or ingests, regardless of where the actor
runs. Only the cage/runner location is open.

### E. Recommendation

**NEEDS OPERATOR DECISION — do not authorize an in-AG sandbox live-adapter experiment
as written.** Not a refusal of the terms (they are sound and code-verified) — a refusal
to let a passed-but-stale gate green an experiment the architecture has moved.

Fresh-eyes lean: **(B).** The operator's own H-series design runs the live actor outside
AG; the in-AG runner refuses live origins by construction; the current constraints forbid
an in-AG live adapter. The coherent path is to mark the **in-AG** live experiment
(B-9..B-12) **superseded by the H-series**, keep these terms as the carried-forward
contract, and open a **separate harness-cage review** as the real next gate before any
live actor runs anywhere. Until the operator ratifies (A) or (B), no live-adapter slice —
in-AG or in-harness — is authorized.

This buys nothing new today: H1 stays parked, H2+ stays gated, no live adapter, no
autopilot, no in-AG Claude Code. The gate stays shut; it just now names the right door.
