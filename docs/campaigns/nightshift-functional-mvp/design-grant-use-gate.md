# Design — Grant-use gate (approval compression), v0

> STATUS: CANDIDATE design, grounded in verified estate (2026-07-10). Operator
> ratified direction **B** (build compression before NS-2..6). Trust-labeled,
> arms nothing, escalation stays fail-closed. Sandwich before the live-seam
> slice lands. Pin: `candidate-approval-compression.md` (this dir).

## The one-sentence doctrine

**A use of standing is not a request for new standing.** Record every use;
interrupt only on enlargement.

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

## Slice plan

- **S1 — pure grant-use evaluation** (`runtime/grant_use_gate.py`): map tool
  call → effect request, check against RationCard, return `GrantUseResult`.
  Pure, no IO, exhaustively tested incl. the opaque-bash / unknown-tool
  fail-closed cases. Lands nothing into the live gate. *(this slice)*
- **S2 — supervisor wiring** (flag-gated, default off): call S1 after the
  continuation gate; `GrantUsed`→silent approve + receipt; `GrantRefused`→
  intervention (widening prompt); `NoVerifiedResult`→deny/prompt fail-closed.
  Composes with continuation. **Opus + adversarial sandwich mandatory.**
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

## Non-negotiable guardrails

- A grant NEVER lets a plan self-approve or auto-latch (born-candidate +
  witnessed approval stays).
- Novel effect class escalates by default (allowlist-bounded; fail-closed).
- "Compress" = fewer prompts for the SAME authority, never broader authority
  per prompt.
- The escalation (widening) prompt is the seam that must never soften.
