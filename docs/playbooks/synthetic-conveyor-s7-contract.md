# Synthetic conveyor — S7 contract note (RATIFIED + IMPLEMENTED)

> **Status: RATIFIED + LANDED (2026-06-30).** Operator ratified **Model B** and the
> minimal `ActorOutput` schema; S7 shipped as
> `src/governor/playbooks/actor_output_normalizer.py` (+16 tests, commit `ba11c7e` on
> `feat/playbooks-synthetic-conveyor`). This note is kept as the design record.
> Original status was CANDIDATE — written and stopped at, per the operator's S7 fence,
> precisely because the actor-output shape was undefined and the custody fork (below)
> was unresolved. Both are now closed.

## Naming hazard (read first)

There are **two unrelated "S7"s** in this repo:

- **Track B S7** (`feat/playbooks-gov-loop`, DONE) — ration-card dispatch of one
  *live external agent* (`docs/playbooks/slice-7-exit-ticket.md`). This is the
  live-adapter / bounded-autopilot lane, gated behind the allowlist review. **NOT this.**
- **Conveyor S7** (`feat/playbooks-synthetic-conveyor`, this note) — a pure, inert
  *normalizer*. No actor is run. AG never touches the actor; the external H-series
  harness runs it OUTSIDE AG and hands AG a static record.

S7 must not jump tracks into the Track B / live-adapter lane.

## Where S7 sits on the conveyor

```
S4 PlaybookQueue ── S6 render_handoff ──▶ HandoffPacket (sealed instruction)
                                              │
                            [ OUTSIDE AG: H-harness runs the actor ]
                                              │ returns raw, messy output
                                              ▼
                                   ┌──────────────────────┐
                                   │  S7 normalizer (NEW)  │  ← this note
                                   └──────────────────────┘
                                              │ emits
                                              ▼
S3 ReviewPacket ──▶ S5 review_packet_validator ──▶ (operator review)
```

S7 is the inverse of S6: S6 turns a request into a sealed instruction; S7 turns an
actor's *messy reply* into the inert evidence artifact (a ReviewPacket) the rest of the
conveyor already knows how to validate and review.

---

## The four-point contract

### 1. What existing S1–S6 artifact it consumes

- **The S6 `HandoffPacket`** — for binding + provenance. The normalized output must
  carry the handoff `seal` so a ReviewPacket can be tied to the exact sealed request it
  answers (and a forged/mismatched reply rejected).
- **A NEW inert input: `ActorOutput`** (S7 must define it — *this is the undefined
  shape, and the reason this is a contract note not a slice*). It is **not** the live
  actor and **not** a transcript stream; it is a static, already-captured description
  the external harness produces. Proposed fields (all inert; strings/refs only):
  - `handoff_id`, `handoff_seal` — binds to the S6 packet.
  - `actor_kind` — claude | codex (closed, from S6).
  - `claimed_status` — the actor's self-reported outcome (advisory).
  - `claimed_files_changed` — list of path strings (declared, not read).
  - `diff_artifact` — a **reference** (path + sha256), never inline patch content.
  - `claimed_test_results` — list of (command, claimed_status, exit?, summary?).
  - `notes` / `risks` — freeform advisory text.
  - `raw_authority_claims` — anything the actor asserted as authority (to be refused).

  Open question: is `ActorOutput` JSON the H-harness emits, or does AG parse a looser
  actor reply? **Recommend: AG accepts only a typed `ActorOutput` (fail-closed parse,
  closed vocab, hostile-input discipline like `StandingReceipt.from_dict`).** Loose
  free-text parsing is a later, hotter concern.

### 2. What new inert artifact it emits

- **An S3 `ReviewPacket`** (schema reused **unchanged**), populated from `ActorOutput`
  and the `HandoffPacket`, ready for the S5 validator. Bound to the handoff seal via
  an artifact reference / design note (provenance).
- Optionally a small **normalization report** (`verdict=observe`) recording what was
  downgraded or refused (which authority claims stripped, which claimed results not
  admitted). Inert; fails `is_authority_admission_receipt`.
- **No file writes** (`to_file_map`-style strings only), no execution, no git.

### 3. What authority it explicitly cannot create

The normalizer is pure translation. It runs nothing, applies nothing, admits nothing.
Specifically it must NOT:

- run a test, spawn a subprocess, touch the network, read/apply the diff, inspect git,
  mutate the repo, or invoke an actor;
- create a new origin enum, a new ration-card type, or any multi-gov;
- flip `operator_review_required` off — it stays **True** by construction;
- propagate actor authority claims — `raw_authority_claims`
  (`tests_pass`/`safe_to_commit`/`authority_granted`/...) are **stripped and refused**,
  exactly like `local_candidate._detect_authority_claims`; the emitted packet still
  fails the authority predicate.

**Preserved rule:** synthetic / stub / actor-claimed evidence may be *observed,
rendered, normalized, queued* — never *admitted as authority*.

### 3a. The custody fork to resolve before building (exhibit both, do not axiomatize)

**Does an actor's *claimed* test pass become `ReviewTestResult.status="passed"`?**
S5's `required_test_not_passing` check reads `ReviewPacket.tests[*].status`. If S7 maps
a claimed pass to `passed`, the actor's *unverified word* silently satisfies a required-
test gate. That is laundering — the exact failure this conveyor exists to refuse.

- **Model A — preserve claimed status.** `claimed pass → status=passed`. Convenient;
  S5 goes green on actor testimony alone. **Rejected** under NLAI ("never trust
  agent-provided evidence").
- **Model B — fail-closed (recommended).** Actor-claimed outcomes are recorded as
  *advisory text only* (`design_notes` / `risks` / the normalization report). The
  ReviewPacket's `tests` are emitted as `not_run` (or omitted), so an S7-normalized
  packet **cannot** satisfy S5's required-test check on actor testimony. Only an
  independent verifier receipt (the existing `verifier_gate` / a future conveyor slice)
  may move a test to `passed`. The actor's claim never closes its own gate.

  Wrinkle: `REVIEW_TEST_STATUSES` has no `claimed`/`unverified` value. Model B avoids
  an S3 schema change by routing claims to advisory text + `not_run`. Adding a
  `claimed` status to S3 is a **hotter, ratification-worthy** change (it touches the
  S3/S5 contract) — name it; don't slip it in.

**Recommendation:** Model B. It keeps "claimed ≠ verified" structural and leaves the S3
schema untouched.

### 4. What tests prove the fence

- **seal binding:** normalized packet carries the handoff seal; an `ActorOutput` whose
  `handoff_seal` ≠ the packet's is refused (typed, closed code).
- **authority stripped:** any `raw_authority_claims` → 0 propagated; emitted packet
  fails `is_authority_admission_receipt`; a smuggled `tests_pass:true` is refused.
- **review stays required:** `operator_review_required is True` for every output.
- **anti-laundering (the load-bearing test):** an `ActorOutput` claiming all required
  tests passed, fed S7 → S5, **still** trips `required_test_missing` /
  `required_test_not_passing` (Model B) — actor testimony cannot green the S5 gate.
- **inert:** no IO / subprocess / network / git (monkeypatch tripwire or pure-call
  assertion); diff is a reference (path+sha256), never applied.
- **scope honesty:** `claimed_files_changed` outside `allowed_paths` are NOT silently
  dropped — they surface to S5's path-fence checks.
- **determinism:** same `ActorOutput` + `HandoffPacket` → byte-identical ReviewPacket.

---

## Recommended decision before coding

1. **Ratify the `ActorOutput` schema** (the undefined input) — closed-vocab, fail-closed
   parse. (Custody-adjacent: it defines what AG will accept from an external actor.)
2. **Ratify Model B** (claimed ≠ verified; no S3 schema change).

Both are small but they are *real seam decisions*, not mechanical implementation. Once
ratified, S7 is "the smallest green slice with tests" — a pure `normalize(actor_output,
handoff) -> ReviewPacket` + the fence tests above. Until then this stays CANDIDATE.

## Non-goals (S7 stays on the conveyor)

- No live Claude Code adapter; no `runtime.adapters.claude_code` execution.
- No subprocess sandbox / OS-container cage; no bounded autopilot.
- No git / doctrine / network authority; no repo mutation beyond the S7 slice.
- The H-series external harness stays OUTSIDE AG. AG is the courthouse, not the
  getaway car.
