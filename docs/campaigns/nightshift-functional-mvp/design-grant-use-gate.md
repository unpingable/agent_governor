# Design — Grant-use gate (approval compression), v0

> STATUS: CANDIDATE design, grounded in verified estate (2026-07-10). Operator
> ratified direction **B** (build compression before NS-2..6). Trust-labeled,
> arms nothing, escalation stays fail-closed. Sandwich before the live-seam
> slice lands. Pin: `candidate-approval-compression.md` (this dir).

## The one-sentence doctrine

**A use of standing is not a request for new standing.** Record every use;
interrupt only on enlargement.

## Build status (2026-07-10) — all LOCAL, unpushed (work hours)

- **S1 DONE** — pure grant-use classification (fail-closed; sandwich-fixed).
- **S2a DONE** — activation mint (deterministic/idempotent, axes locked).
- **S2b DONE** — supervisor wiring (innermost gate; passed independent refute).
- **S3 DONE** — `runtime.grant.activate`/`get` (witness-digest checkpoint,
  activation receipt). Registry 99→101.
- **S4a/S4b DONE** — maude projection + runner attaches the grant on an
  approved run, fail-safe, with the trust banner. The y-storm is dead.
- **S5a DONE** — live smoke: seam observed crossing the daemon boundary once,
  receipt continuity.
- **S5b DONE** — reusable harness + 9-scenario ops disposition corpus.
- **S5c DONE** — grant LEASE lifecycle: revocation (idempotent, receipted) +
  expiry (use-time, monotonic, no resurrection). `runtime.grant.revoke`
  (registry 101→102). Terminal disposition distinct from widening. 12 tests.
  Invariant closed: *used repeatedly, never past revocation or horizon.*
- **S4c-minimal DONE** — read-only `grant [session_id]` diagnostic in maude
  (state/scope/dispositions). Instrumentation, not the cathedral. 7 tests.
- **S6 DONE (2026-07-13)** — first-class `execution_request:` plan block; legacy
  `scope_allowlist` + ration-command inference RETIRED. Versioned-contract change
  via `plan_version` discriminator (operator ruling: version-discriminate +
  freeze NS-1, `design-s6-execution-request-schema.md`). v1 is the authoring
  surface; v0 decodes only for the frozen NS-1 `plan_ref`; missing/unknown
  refuse. maude: envelope schema + parser dispatch + projection rewrite + frozen
  decoder + `plan-envelope-v1.md` spec + refusal tests (full suite 336 pass).
  AG: daemon wire UNCHANGED (verified — the v1-projected request mints via the
  existing `activate_execution_grant`, zero daemon edits); NS-1 frozen; v1
  successor specimen `specimens/ns-1r-refusal-registry-v1/` with end-to-end
  integration evidence (`integration_check.py`: parse → admit → project → mint
  `sgr_969f042a…`). Doctrine: *approval attaches to plan bytes, not
  reconstructed intent; migration creates a successor, never revises a
  predecessor.* **Sandwich DONE** (codex gpt-5.5 vs frozen basis 6a35965 +
  dc0a383): Modes 3/5 SAFE; 3 mechanical findings FIXED (maude `a48df3b` —
  type-confusion, TOCTOU rehash, byte-exact frozen check; suite 342). Two
  Criticals were **pre-existing admission-model** gaps (§7 value-verification
  unbuilt; approval not bound to plan_ref) — inert while unarmed, filed for
  operator ruling in `GAP-s6-sandwich-authority-findings.md`, NOT folded into
  S6. S6 mechanical seam lands; the surrounding admission model is the named
  follow-up.
- **DEFERRED (post-S6, unless a consumer forces them):** S5d (multi-actor
  attribution), S4c-full (report dispositions, widening-prompt buttons, lease
  panel).

## Verified estate — B is composition, not a new authority model

- **The grant object is NOT the RationCard** (estate correction while building
  S1). `RationCard.__post_init__` **hard-locks** the card observe-only (refuses
  git/network/doctrine/non-observe) — it is the *synthetic-conveyor* envelope
  (produces review packets), and gating a live build against it would refuse
  every edit. The live-run grant is a small **`ExecutionGrant`** (write_paths /
  shell_commands / network·git locked) **assembled from the approved plan**:
  `scope_allowlist` → write_paths, the declared shell allowlist →
  shell_commands. `RationCard`'s request-vs-allowed check (`match_ration_card`)
  is exact-set-membership, not path containment — also wrong for concrete
  per-call paths. S1 defines `ExecutionGrant` + concrete-path containment.
- **The result vocabulary already exists — `standing_grant_use.py`**:
  `GrantUseResult = GrantUsed | GrantRefused | NoVerifiedResult`
  (`GrantUsed` carries `action`/`target`/`subject` — generic, not tuning-
  specific). Reuse the *types*; the `StandingGrantUseClient` itself dispatches
  to the **external `standing` binary** (remote standing) — that is the *later*
  real-enforcement path, NOT this slice.
- **Escalation semantics already exist — `scope.py`** Scope Governor:
  absence-restrictive, `widen` one axis, locality ladder. "Requested effects
  widen the grant" = scope escalation.
- **The gate already exists (and is intricate) — `supervisor.py:637`**
  `_handle_tool_call_proposal`: budget gate → `classify_action` (READ < WRITE
  < COMMUNICATE) → GAP-2 **continuation gate** (C2 observe / C3 enforce, with
  its own grant/burn) → intervention/auto-approve-read-only. A grant-use check
  must **compose** with this, not fight it.

## The two gates are orthogonal (must not be conflated)

- **Continuation gate (C2/C3, existing):** *per-step earn* — "does the agent
  get ANOTHER governed step?" Burns a single-use continuation grant.
- **Grant-use gate (this design):** *per-effect scope* — "does THIS effect
  fall inside the approved RationCard envelope, or does it widen?"

Both fail-closed; they answer different questions and stack. Grant-use sits as
the per-effect scope check; a `GrantUsed` is what lets the existing
auto-approve path proceed silently (generalizing "auto-approve read-only" to
"auto-approve within the approved envelope").

## Design decision (trust-labeled local gate now; enforcement later)

The *now* path is a **local** grant-use check: map the supervised tool call to
an effect request, check it against the plan-approved RationCard, emit a
`GrantUseResult`. It is honestly **trust-not-enforcement**: it enforces the
*declared* scope by matching, but the *substrate* effects are not armed
(SyntheticCage/C11/seccomp unarmed — documented bootstrap limit). Since today's
per-call `y` is already rubber-stamping (not enforcement), this **loses nothing
real** and removes the confounding toil.

The surface must say so verbatim: **"declared scope enforced by gate; substrate
effects not yet armed."**

## Acceptance criteria (chatty's bounded spec — this IS the contract)

- `activate()` mints the grant (bootstrap-grade, local receipt).
- Supervisor tool-gate submits every call as a `GrantUse`.
- `GrantUsed` → proceeds **silently** + emits a receipt.
- `GrantRefused` → prompts **only** when requested effects **widen**.
- `NoVerifiedResult` → **fails closed**.
- RPC carries: grant ID, disposition, scope delta, receipt reference.
- Maude **renders** the result; stores **no** authority state.
- No command-string permission cache sneaks in wearing novelty glasses.

## The delicate part — tool→effect mapping (where the security lives)

chatty's warnings are load-bearing:
- `allow cargo *` is NOT a boundary — cargo runs test binaries AND build
  scripts. The grant is an **effect profile**, not a command allowlist.
- `bash -lc "…"` is **opaque** — it either inherits the same hard sandbox or
  counts as escalation. Shell strings are where authz becomes folklore.

Mapping rule for v0 (conservative, fail-closed on ambiguity):
- read-only tools (Read/Grep/Glob/…) → within `output_is_observe_only` →
  `GrantUsed`.
- Edit/Write → write to path → `GrantUsed` iff path ⊆ `allowed_write_paths`,
  else `GrantRefused` (widening: new fs region).
- Bash/exec → **only** a recognized, argv-structured command whose program +
  subcommand match `allowed_shell_commands` AND touches no denied axis →
  `GrantUsed`; an opaque/compound/unrecognized shell string →
  `NoVerifiedResult` (fail closed → prompt). We do NOT string-match our way to
  a yes.
- network / git / secret / new-executable-family signals → `GrantRefused`
  (material escalation) if the axis is denied.
- unknown tool → `NoVerifiedResult` (fail closed).

## Activation boundary — RATIFIED 2026-07-10 (operator)

A plan **requests** execution scope; only **activation** may **mint** a grant.
Putting `execution_grant:` in the plan envelope would seat authority on the
wrong side of the seam. So:

```
approved plan
   ↓ deterministic projection
ExecutionRequest            (what the plan asks for — no authority)
   ↓ activate() + witnessed approval
ExecutionGrant  [first-class artifact]
   ↓ repeated checked uses (this gate)
GrantUsed / GrantRefused / NoVerifiedResult
```

- **S2 keeps the existing approved-plan fields as compatibility input** —
  `scope_allowlist` → write_paths, declared command surface → structured
  `CommandGrant`s. `activate()` mints + receipts a **first-class grant
  artifact**; the supervisor consumes ONLY that artifact (never re-reads the
  plan). Activation receipt shape:
  ```
  grant_id, source_plan_digest, approval_witness_digest,
  derivation_version: execution-grant/v1,
  write_paths: [...], commands: [{program: cargo, argv_prefix: [test]}, ...],
  network: denied, secrets: denied, privilege: denied,
  horizon: run, enforcement: declared-effects-only
  ```
  (`enforcement: declared-effects-only` IS the honest trust label on the wire.)
- **The `execution_request:` plan block + legacy retirement is a SEPARATE
  later schema slice (S6), NOT S2.** Adding it during the seam wiring drags
  parser / canonicalization / corpus / witness digests / migration + precedence
  rules into a delicate slice — "precedence rules are where authority models
  quietly begin breeding in the walls." Project the existing fields
  deterministically now; introduce the first-class request block and retire the
  scattered declarations cleanly later, with no two-sources-of-truth window.
- Commands are **structured** (`CommandGrant(program, argv_prefix)`), never
  shell strings — S1 already matches on parsed tokens.

## Slice plan

- **S1 — pure grant-use evaluation** (`runtime/grant_use_gate.py`): map tool
  call → effect request, check against RationCard, return `GrantUseResult`.
  Pure, no IO, exhaustively tested incl. the opaque-bash / unknown-tool
  fail-closed cases. Lands nothing into the live gate. *(this slice)*
- **S2 — activation + supervisor wiring** (flag-gated, default off): project
  the approved plan → `ExecutionRequest`; `activate()` mints + receipts the
  first-class `ExecutionGrant` artifact; the supervisor tool-gate (after the
  continuation gate) calls S1 against the artifact — `GrantUsed`→silent approve
  + receipt; `GrantRefused`→widening intervention; `NoVerifiedResult`→
  deny/prompt fail-closed. Composes with continuation. **Opus + adversarial
  sandwich mandatory.**
- **S3 — daemon RPC**: expose grant activation + per-use disposition (grant id,
  disposition, scope delta, receipt ref).
- **S4 — maude render**: `grant use: accepted / sgr_…`; widening prompt
  `[extend grant] [deny use] [abort run]`; lease panel; the trust-label banner.
  Stores no authority state.
- **S5 — sandwich + synthetic-ops validation**: not "agent edits Rust" —
  ops shapes: repeated read/diagnostic under one grant, observe→mutate
  crossing, path/host expansion, secret/network request, horizon expiry mid-run,
  revocation after state change, partial completion with meaningful receipts,
  multi-actor steps. This is where "use ≠ new request" becomes the product.
- **S6 — schema slice (LATER, not on the seam-wiring path):** introduce a
  first-class plan block `execution_request:` / `requested_effects:` and retire
  the scattered `scope_allowlist` / shell declarations in one move — no
  precedence rules, no two-sources-of-truth window. Drags parser /
  canonicalization / corpus / witness digests / migration; kept out of S2 on
  purpose.

## S2b composition safety (verified 2026-07-10)

The grant-use check is the **innermost** gate in `_handle_tool_call_proposal`,
placed inside `if needs_approval:`. Every deny-gate ahead of it **returns
before** `needs_approval` is evaluated:
- budget breach → deny + return (`supervisor.py:672`)
- continuation C3 enforce non-grant → deny + return (`:833`)
- transition-probe hold + kernel-refuse → deny + return (`:864`)
- lab_gate WRITE (LA-backed) → allow OR deny, **both return** (`:955`/`:932`)

So grant-use is reached ONLY when every prior gate passed, and it only ever
downgrades a would-be *prompt* into a silent approve for a WithinGrant call —
it can **never** override a denial (denials already returned) nor widen
authority. When a lab_gate is active it handles WRITE and returns first, so
grant-use never bypasses LA enforcement. Inert until S3 attaches a grant.

## Adversarial sandwich — 2026-07-10 (independent refute agent)

An independent refuter attacked the seam on five modes. Verdict + dispositions:
- **Mode 3 gate ordering — PASS.** Confirmed: every deny-gate returns before
  `needs_approval`; no would-be-deny reaches auto-approve.
- **Mode 4 axis leak — PASS.** network/git hardcoded denied; cannot reach
  `allowed=True`. **Digest binding — fixed (contract):** `activate()` is a pure
  mint, NOT an authority checkpoint; docstring now says loudly that the caller
  (S3) must verify the plan/witness admission before minting.
- **Mode 1 argv smuggling — FIXED.** `cargo test --target-dir=/etc` /
  `--config runner=…` prefix-matched yet relocated effects. Added a named,
  documented, non-exhaustive effect-escaping-flag denylist (`-C`, `--config`,
  `--target-dir`, `--out-dir`, `--manifest-path`, `--home`) → `Unverifiable`
  (prompt). Scoped honestly: an allowlisted program still runs arbitrary code
  (`cargo test`); the command allowlist is not an effect boundary — the cage is.
- **Mode 2 path containment — FIXED (`dir/*`) + disclosed (symlink).** `dir/*`
  now means single-level (was collapsing to a prefix, admitting `dir/a/b/c`);
  `dir/**` = any depth. Symlink escape is inherent to a pure string classifier
  (the armed cage enforces real fs) — disclosed in the module docstring.
- **Mode 5 read reclassification — FIXED.** `_READ_TOOLS` dropped the divergent
  `ls` (supervisor classified it WRITE → gate silently auto-approved it as a
  read). Pinned by `test_read_tools_are_reads_for_the_supervisor` (every gate
  read tool must be a supervisor READ). Unbounded *reads* of arbitrary paths
  are a **pre-existing** supervisor behavior (reads auto-approve before
  grant-use), not a regression; read-scoping is future work.

Scoped claim after fixes: the gate bounds **program+subcommand+known-escape-
flags** and **declared write paths**; it does not bound what admitted code does
internally, nor follow symlinks — that is the cage (`declared-effects-only`).
All fixes pinned by regression tests (94 across the three suites).

## Non-negotiable guardrails

- A grant NEVER lets a plan self-approve or auto-latch (born-candidate +
  witnessed approval stays).
- Novel effect class escalates by default (allowlist-bounded; fail-closed).
- "Compress" = fewer prompts for the SAME authority, never broader authority
  per prompt.
- The escalation (widening) prompt is the seam that must never soften.
