# H2 Live-Run Contract Review — the smallest one-shot actor invocation

> **OPENED 2026-06-30. Status: DRAFT — awaiting operator pass.**
> This is a **review gate**, not an implementation doc. It defines the *contract* for the
> smallest one-shot external-actor invocation a **future real cage backend** would be
> allowed to run. **It authorizes nothing to execute.** No runner is built, no actor is
> run, no execution method is added, under it. Each row is a decision to ratify, defer,
> or tighten in the operator pass.

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
| 1 | **Preconditions** before a single invocation | (a) real cage `admit_live(...).admitted` True via `require_live_admission`; (b) `armed_live=True` (explicit operator arming) and no replay fixture overriding; (c) kill switch clear; (d) handoff seal verified, item operator-approved, all 8 authority axes prohibited; (e) `actor_kind` matches handoff. Any miss → typed refusal, no launch. | PROPOSE |
| 2 | **One-shot semantics** | One actor process, one handoff, at most one `actor_output.v0`. No recursion, loop, continuation, follow-up queue, or "continue until done." Complete only when: process exits/times-out/killed → sandbox sealed → writes inspected → `actor_output.v0` captured. | PROPOSE (I-2) |
| 3 | **What the invocation may touch** | Read-only repo snapshot + the sealed handoff (PROMPT.md/handoff.json) + the per-run writable dir (scratch/output/transcript) inside the cage. Nothing else: no real checkout, `.git`, host `$HOME`, network, creds. Enforced by the cage, validated post-run. | PROPOSE |
| 4 | **Timeout / kill** | Low first timeout (**30–60 s** — control-flow, not work); kill switch checked before launch and polled during; TERM-then-KILL; hung actor terminated. Outcome recorded as descriptive metadata in the audit run dir + (descriptive only) in `actor_output.v0`. | PROPOSE |
| 5 | **Output + capture** | Exactly one `actor_output.v0` via `capture_from_handoff`, stored in `run_dir(run_id)`. Raw transcript/logs stay in the run dir (tainted audit); only the envelope (or its `captured_text` field) crosses to AG. Forbidden-write detected → run invalid even on exit 0. | PROPOSE |
| 6 | **What never crosses** | Only `actor_output.v0`. No transcript stream, no inline diff, no verifier result, no `ReviewTestResult`, no executable, no process handle, no auxiliary bundle. (`assert_ag_ingestible`.) | RATIFIED (cage slice) |
| 7 | **Origin / operational posture** | `capture_origin` descriptive; AG stays `DemonstratedConsumed` / non-operational. Operational effect (`observed` + `confer_operational_effect`) is a separate, even-later gate. | RATIFIED (I-1) |
| 8 | **Replay / arming** | Replay/stub is the default; live needs explicit `armed_live` + a live-mode signal; a replay fixture suppresses live unless deliberately overridden. Tests never go live by accident. | PROPOSE |

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

## Open questions for the operator pass

1. **Actor kind for the first live run** — one only (claude *or* codex), or either? (Lean:
   pick one — narrower blast radius for the first real invocation.)
2. **Timeout** — 30 s or 60 s for the first run; and is there a wall-clock hard cap
   independent of the actor's own exit?
3. **Where the invocation lives** — confirm a future `harness/` execution module (e.g.
   `harness/run.py`) carrying `run_once_under_cage`, gated on `require_live_admission`,
   never in AG. (This review does not build it.)
4. **Arming signal** — env var, CLI flag, and/or an explicit live-mode field on the card?
   What exactly flips `armed_live` to True?
5. **Confirm I-1 firmly** — even a successful live run stays `DemonstratedConsumed`;
   operational effect is a separate, even-later gate. (Lean: yes.)

## Exit (to be completed by the operator pass)

> Pending. When the operator completes the pass, record per-row decisions + answers to the
> open questions, and the recommendation (authorize an H2-*implementation* slice against a
> real cage backend / refuse / defer). Until then: **no H2 implementation, no runner, no
> live actor.** This review, even when passed, buys exactly one thing — a ratified
> contract — and *not* permission to run it; running waits on (i) a real cage backend gate
> and (ii) a separate H2-implementation gate.
