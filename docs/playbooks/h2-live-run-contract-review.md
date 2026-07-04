# H2 Live-Run Contract Review — the smallest one-shot actor invocation

> **OPENED 2026-06-30. Status: PASSED 2026-06-30 (operator pass — contract shape only).**
> This is a **review gate**, not an implementation doc. It defines the *contract* for the
> smallest one-shot external-actor invocation a **future real cage backend** would be
> allowed to run. **It authorizes nothing to execute.** No runner is built, no actor is
> run, no execution method is added, under it.
>
> **Operator pass recorded below ("Operator pass — recorded decisions").** The four
> permanent invariants are ratified; the five decisions are recorded. The pass approves
> the **contract shape only** — not H2 implementation, not a real cage backend, not
> bubblewrap, not any live actor run.

## What is NOT being authorized (read first)

- **Not H2 execution.** No live actor runs. This gate produces a *contract*, reviewed and
  ratified, that a *later* H2-implementation gate would build against.
- **Not a real cage backend.** That is a separate, earlier prerequisite gate (bubblewrap
  named, not authorized). Until it exists and truthfully attests live isolation, the
  invocation contract below is **unreachable by construction** — every shipped cage
  refuses (`harness/cage.py: RefusingCage`).
- **Not operational effect.** Even a perfectly successful future live run stays
  **non-operational** on AG's side (see invariant I-1). H2 makes the *actor* real; it does
  **not** make AG operational.

## Dependency posture (why this is reachable to *review* but not to *run*)

```
cage-design slice (DONE)      → contract + RefusingCage (refuses live)         [shipped]
real cage backend (FUTURE)    → truthfully attests live isolation              [unbuilt gate]
H2 live-run CONTRACT (THIS)   → defines the one-shot invocation shape          [review only]
H2 IMPLEMENTATION (FUTURE)    → builds run_once_under_cage, still no autopilot  [unbuilt gate]
operational effect (FUTURE)   → observed origin + confer_operational_effect     [separate, later]
```

This review fills the **third** line only. It can be ratified before the real cage
exists because a contract is a shape, not a keycard.

## What is already true (cite, do not re-decide)

- **The cage gate exists and refuses live.** `harness/cage.py`: `HarnessCage` is a
  `Protocol` with **no execution method**; `evaluate_live_admission` admits a live actor
  **only** under an attestation that `confirms_isolation` in `live` scope;
  `require_live_admission()` raises the typed `LiveAdmissionRefused` otherwise. No shipped
  backend attests live isolation, so `LiveAdmission(admitted=True)` is unreachable today.
- **The AG-ingest wall is one inert artifact.** `assert_ag_ingestible()` admits only
  `actor_output.v0`; `ActorOutput.from_dict` parses it fail-closed; S7 (Model B) maps
  actor claims to `not_run`; S5 refuses an actor-claimed passing test. Only an AG-owned
  independent verifier greens a test.
- **The audit store is outside AG.** `audit_store_root()` →
  `$XDG_STATE_HOME/agent-gov/harness-runs/` (fallback `~/.local/state/...`); AG never
  crawls it.
- **AG's operational fence.** `OperationalConsumed` (origin `observed`) vs
  `DemonstratedConsumed` (drill / synthetic / stub); `confer_operational_effect` accepts
  only `OperationalConsumed`. Nothing on the H2 path produces `observed`.

## Inherited constraints (carried forward, binding)

The 11 ration-card terms and the harness-cage terms apply unchanged. The invocation
contract below does not loosen any of them; it specifies how a single invocation sits
*inside* them.

## Permanent invariants (NOT up for the operator pass — they bound it)

- **I-1. H2 ≠ operational.** A live actor's output is still testimony. The run stays
  `DemonstratedConsumed` / non-operational on AG's side; `confer_operational_effect`
  stays refused; actor claims stay claims; a real green still needs an independent AG
  verifier. *captured output ≠ verifier receipt.*
- **I-2. One invocation, one artifact.** Exactly one actor process, one handoff, one
  `actor_output.v0`. No loop, no continuation, no self-scheduling, no follow-up queue.
- **I-3. Refuse-live until truthfully attested.** No invocation proceeds unless a real
  cage backend returns `LiveAdmission(admitted=True)`. The contract is gated on
  `require_live_admission`, which every shipped cage fails.
- **I-4. The cage is the containment.** The allowlist/contract is not safety; only the
  cage's enforced isolation + post-run write-manifest validation is.

## The one-shot invocation contract (the center of this review)

Proposed shape — **a spec, not code.** A future H2 slice would implement, in the
`harness/` lane (never AG), the smallest one-shot entry point:

```text
run_once_under_cage(
    cage:        HarnessCage,        # must attest live isolation (real backend)
    handoff:     <sealed S6 HandoffPacket manifest>,   # seal verified before use
    *,
    actor_kind:  "claude" | "codex", # must match the handoff
    run_id:      <safe single segment>,                # -> audit run_dir(run_id)
    timeout_s:   int,                # low; one-shot
    armed_live:  bool,               # explicit operator arming; default False
) -> ActorOutput                     # exactly one actor_output.v0
```

| # | Decision | Proposed default (awaiting ratification) | Status |
|---|----------|-------------------------------------------|--------|
| 1 | **Preconditions** before a single invocation | Conjunctive, fail-closed. (a) real cage `admit_live(...).admitted` True via `require_live_admission`; (b) `armed_live=True` — a **second** key, never a substitute for (a); no replay fixture overriding; (c) kill switch clear; (d) handoff seal verified, item operator-approved, all 8 authority axes prohibited; (e) `actor_kind` matches handoff. Any miss → typed refusal, no launch. | RATIFIED |
| 2 | **One-shot semantics** | One actor process, one handoff, at most one `actor_output.v0`. No recursion, loop, continuation, follow-up queue, or "continue until done." Complete only when: process exits/times-out/killed → sandbox sealed → writes inspected → `actor_output.v0` captured. | RATIFIED (I-2) |
| 3 | **What the invocation may touch** | Read-only repo snapshot + the sealed handoff (PROMPT.md/handoff.json) + the per-run writable dir (scratch/output/transcript) inside the cage. Nothing else: no real checkout, `.git`, host `$HOME`, network, creds. Enforced by the cage, validated post-run. | RATIFIED |
| 4 | **Timeout / kill** | Default `timeout_s = 30`, **hard maximum 60**; kill switch checked before launch and polled during; TERM-then-KILL; hung actor terminated. A timeout yields a captured refusal/failure artifact or no artifact — **never verifier results**. Outcome recorded as descriptive metadata in the audit run dir + (descriptive only) in `actor_output.v0`. | RATIFIED |
| 5 | **Output + capture** | Exactly one `actor_output.v0` via `capture_from_handoff`, stored in `run_dir(run_id)`. Raw transcript/logs stay in the run dir (tainted audit); only the envelope (or its `captured_text` field) crosses to AG. Forbidden-write detected → run invalid even on exit 0. | PROPOSE |
| 6 | **What never crosses** | Only `actor_output.v0`. No transcript stream, no inline diff, no verifier result, no `ReviewTestResult`, no executable, no process handle, no auxiliary bundle. (`assert_ag_ingestible`.) | RATIFIED (cage slice) |
| 7 | **Origin / operational posture** | `capture_origin` descriptive; AG stays `DemonstratedConsumed` / non-operational. Operational effect (`observed` + `confer_operational_effect`) is a separate, even-later gate. | RATIFIED (I-1) |
| 8 | **Replay / arming** | Replay/stub is the default. Live needs **both** `armed_live=True` **and** a successful `require_live_admission` — `armed_live` is a *second* key, **never a substitute** for cage admission (a lone `--armed-live` flag must never admit live). A replay fixture suppresses live unless deliberately overridden. Tests never go live by accident. | RATIFIED |

## Rationale (per proposed default)

**1. Preconditions are conjunctive and fail-closed.** Every one must hold or the
invocation refuses before launch — this is a guarantee-typed seam, so one missing
precondition voids the run. The load-bearing one is (a): `require_live_admission` against
a *real* cage. Today it always raises, which is correct — H2 is unreachable until the cage
gate is separately passed.

**2. One-shot is the whole point.** The first live run proves *control flow*, not
autonomy. No loop, no continuation. A run is one process and one artifact; "continue until
done" is the autopilot gate, far downstream and separately ratified.

**3–5. Reach, timeout, capture sit inside the cage.** The actor reads a read-only snapshot
+ its handoff and writes only into the per-run dir; the cage enforces it and a post-run
write-manifest validates it (forbidden write → invalid even on exit 0). The harness owns
timeout/kill because the harness owns the process. Output is one `actor_output.v0` in the
audit store; transcripts stay tainted-audit; only the envelope crosses.

**6–7. The walls already built do not move.** One artifact, testimony only, non-operational
— these are inherited as ratified, not re-opened. H2 changes *who produces the testimony*
(a real actor instead of a supplied string), not *what AG does with it*.

**8. Live is opt-in and loud.** Explicit arming + replay-suppresses-live keeps "run the
tests" from becoming "run a live agent." The arming signal's exact form is an open
question below.

## Operator pass — recorded decisions (2026-06-30)

The four permanent invariants are **ratified as written** (I-1 H2 ≠ operational; I-2
one invocation / one artifact / no loop; I-3 refuse-live until truthfully attested; I-4
the cage is the containment). The five open questions are decided:

### 1. First actor kind — the smallest inert actor
The first live actor is the **smallest inert kind**: an `offline_echo_actor` /
`captured_reply_actor` equivalent. It may produce text for capture and **nothing else** —
no repo write, no git, no doctrine, no network, no verifier, no patch authority. (This is
*not* `claude`/`codex`; it is the most powerless thing that still counts as "a live
process produced text." Adding such a kind to the harness `ACTOR_KINDS` vocabulary is part
of the future H2-*implementation* gate — named here, not built.)

### 2. Timeout — 30 s default, 60 s hard max
`timeout_s = 30` by default; **hard maximum 60**. A timeout produces a captured
refusal/failure artifact, or no artifact, per the contract — **never verifier results.**

### 3. Invocation module — `harness/run.py`, harness lane only
The future `run_once_under_cage` lives in `harness/run.py`, the **external harness lane
only** — never AG / governor internals, never `runtime.adapters.claude_code`. (This review
does not build it.)

### 4. Arming — two keys, neither sufficient alone
A live invocation requires **both** `armed_live=True` **and** a successful
`require_live_admission(cage, ...)`. Both necessary; **neither alone sufficient.**
`armed_live` is a *second* key, **never a substitute for cage admission** — a lone
`--armed-live` flag must never admit live. (CLI flags are the traditional source of
constitutional crises; this one is fenced.) With the currently shipped cages this stays
**unreachable**, because they refuse live admission.

### 5. I-1 — hard confirmed
Hard confirmed. Even a fully successful live run stays `DemonstratedConsumed` /
non-operational; `confer_operational_effect` stays refused; actor claims stay claims;
required tests still need an independent AG verifier. **H2 changes who produces testimony,
not what AG can admit.**

## Exit — PASSED 2026-06-30 (contract shape only)

All eight contract rows are ratified (6/7 inherited; 1–5/8 by this pass) and the four
invariants confirmed. **This pass approves the H2 contract shape and nothing more.**

It does **NOT** authorize:

- H2 implementation (no `harness/run.py`, no `run_once_under_cage`, no runner) — gated on
  a **real cage backend that exists and is separately reviewed**;
- a real cage backend, or bubblewrap implementation;
- any live actor run;
- loops, transcript streaming, diff references, verifier results, `ReviewTestResult`,
  operational effect, or any AG-internal live-adapter work.

The gate stack, unchanged and all gated, in order:

```
real cage backend (bubblewrap, UNBUILT — separate review)
  → H2 contract (THIS — PASSED, shape only)
    → H2 implementation (UNBUILT — separate gate, needs the real cage first)
      → operational effect (UNBUILT — separate, even later)
```

The contract is ratified. Running it waits on (i) a real cage backend gate and (ii) a
separate H2-implementation gate. The shape has a constitution; it still has no keycard.
