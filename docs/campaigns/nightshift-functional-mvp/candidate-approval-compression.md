# Candidate — Operator approval compression (the ration IS the grant)

> STATUS: CANDIDATE — pinned from the NS-1 first live run (2026-07-10). A
> handle for review, NOT authorization to build. Operator: "grants might be a
> good idea. bounded classes of actions. we'll have to pin that for later."

## The finding (NS-1 dogfood, operator + chatty)

Governance friction scales with **interaction count, not risk**. Twenty
low-risk `cargo test` approvals are worse than one consequential approval:
they destroy flow and train the operator to mash `y`. At that point the
control is ceremonial. This is real evidence — the kernel is being
demonstrated faithfully while the human factors are demonstrated almost
adversarially.

The governing rule (operator/chatty, and it's a good one):

> **Preserve distinct authority transitions. Compress everything that does
> not change authority.**

Three tiers the surface must distinguish:
- **authority class** — "may execute local Rust build/test commands"
- **invocation instance** — this exact `cargo test --lib pipeline::...`
- **material escalation** — network, filesystem expansion beyond
  scope_allowlist, destructive flags, credential access, new executable
  family, scope widening

Today the supervisor authorizes *instances with no memory*: `cargo test`,
`cargo build`, `cargo test --lib` each prompt as fresh authority.

## The reframe — don't build a grants system; honor the one you have

The bounded-class grant is **already expressed** in `RationCard`:
NS-1's `ration_card.json` carries `shell allowlist: [cargo test, cargo
build]`, `network: false`, locked axes, `observe_only: true`. The operator
**already granted that class** by approving the plan that cites the ration
(digest-bound). The supervised approve/deny loop is prompting per-invocation
*anyway* — re-asking for authority the ration already conferred.

So the fix is: the supervisor checks each proposed tool call against the
**already-approved envelope**:
- within the ration (matches shell allowlist, inside `scope_allowlist`, no
  locked-axis touch) → auto-proceed, or notify-with-veto-window (Δt), NOT a
  hard prompt.
- **material escalation beyond the ration** (network, path outside
  scope_allowlist, destructive flag, new executable family, credential
  access, scope widening) → hard prompt, the real authority transition.

This is the existing "auto-approve for read-only tools" mechanism
**generalized to "auto-approve within the approved envelope."** The ration
is the session grant; the loop just isn't reading it.

## Attention as a custody class (doctrine addition)

The sharp doctrinal contribution from this run: **operator attention is not
free substrate.** Governance-shaped toil is still toil, and it feels morally
load-bearing even when half of it is UI debt in a magistrate wig. The per-
approval interpretive labor (read rationale → distinguish product from
papercut → verify fix → inspect action → approve → later assess diff →
answer postmortem) is a custody cost that must be counted, not assumed free.
Compressing non-authority-changing transitions is how you spend it well.

## Grant issuance vs grant use — the four events (operator/chatty, 2026-07-10)

The axis is **issuance vs use**. Four distinct events:
1. **Approve the plan** — candidate → admitted workflow. Witnessed
   authority seam. KEEP unchanged.
2. **Mint an execution grant** — "this session may edit this repo and run
   local Rust build/test under these effect constraints." Issuance.
3. **Use the grant repeatedly** — every tool call checked against the grant,
   every use receipted, NO new human approval. Use.
4. **Escalate on authority delta** — new fs region, network, secrets,
   privilege elevation, destructive op, opaque shell, longer horizon.

> **The doctrine sentence: A use of standing is not a request for new
> standing.** (Maude form: *record every use; interrupt only on
> enlargement.*) Today every invocation is treated as grant *issuance* —
> which is why it feels like Codex with a parole officer. This is the AG
> directional kernel exactly: exercising conferred standing does not re-fire
> the conferral gate.

## Prior art to steal (anticipatory evidence — topology matches)

- **polkit** `auth_self_keep`/`auth_admin_keep` — retain authorization for a
  short window instead of re-asking. (The "lease" TTL.)
- **Vault leases** — explicit lease ID + TTL + renewal + expiry + revocation.
  Maps insultingly cleanly onto a session/plan execution grant.
- **Macaroons** — authority with contextual caveats (who/where/when/purpose).
  In Maude terms: session · workspace · action profile · effect boundary ·
  horizon. This is the grant object's shape.
- **Android runtime permissions** — request-in-context, one-time grant,
  check-before-prompt, don't re-dialog for related permissions. Consumer UX,
  but the lesson (repeated prompts destroy meaningful consent) is dead on.
- **Codex sandboxing / Claude Code allow·ask·deny** — the current standard
  shape: the sandbox defines what's autonomous; approval only on crossing it.

## Critical correction: the boundary is EFFECTS, not the word `cargo`

My earlier "the RationCard shell allowlist IS the grant" is half-right and
half-dangerous. `cargo test` compiles and executes test binaries AND
repository build scripts — `allow cargo *` is **not** a security boundary.
The real boundary is enforced **filesystem / network / env / secret /
process effects**. So the grant is not a command allowlist; it is a
**sandboxed execution profile** that happens to admit certain command
families. The RationCard's *locked axes* (network/git/doctrine=False,
observe_only) are the effect boundary; its *shell allowlist* is ergonomic
surface, not the fence. And **structured calls beat shell strings**:
`{program: cargo, argv: [...], cwd, env_delta}` is checkable; an opaque
`bash -lc "…"` must inherit the same hard sandbox or count as escalation.
"Shell strings are where authorization models go to become folklore."

## Sequencing crux: today's prompts are NOT enforcement (the part neither of us said)

Compression is safe only when effects are enforced by *something other than
the operator's eyeballs*. And here is the honest bit: **the current per-call
`y` is already not enforcement — it's rubber-stamping.** The toil actively
prevents scrutiny (a human mashing `y` is not inspecting each invocation's
effects). AG's real enforcement layer — SyntheticCage / C11 / seccomp — is
**unarmed** (documented bootstrap limit). So right now the operator's
approval is doing double duty as *consent* AND (theater of) *enforcement*,
and the enforcement half is fictional.

Consequence: compressing approvals **loses nothing real** versus the status
quo — both trust the declared ration; compression just stops pretending the
toil is a boundary. The two honest paths:
- **now, labeled trust-not-enforcement:** auto-proceed within the declared
  ration, receipt every use, hard-prompt on out-of-envelope escalation —
  explicitly "this trusts the ration until the cage is armed." Removes toil
  that is currently theater. Arms nothing. In-scope for the MVP (no C11).
- **later, real enforcement:** arm the effect sandbox so within-envelope
  auto-proceed is *enforced*, not trusted. Out of MVP scope (non-goal:
  nothing armed).

The escalation gate stays fail-closed either way — that is the seam that
must never soften.

## Estate reality — verified 2026-07-10 (the machinery exists; the wiring doesn't)

The operator/chatty design says "Maude should consume Nightshift's
activation/grant-use machinery." Grep corrects the attribution — and makes
the pin *stronger*, because the machinery already exists in the right place:

- **It's AG's, not Nightshift's.** `src/governor/standing_grant_use.py`
  carries the exact vocabulary: `GrantUseResult = GrantUsed | GrantRefused |
  NoVerifiedResult`, `StandingGrantUseClient`, `ResolvedBinary`, `RunOutcome`.
  `src/governor/activation.py` carries the four-office `activate()` /
  `ActivationReceipt` / `rollback()`. This is architecturally correct:
  Governor is the consequence/authority kernel; a work-source shouldn't own
  grant-use (constellation split — Continuity=standing, Governor=consequence).
- **Nightshift has NO grant-use lifecycle.** Its 61 "grant" hits are all
  `granted_in_run_id` / `granted_at` / `granted_s` — domain timestamp/
  provenance fields, not authority. No `ExecutionGrant`, no `GrantUse`, no
  `activate`. The "native vocabulary" is AG's.
- **The lifecycle is NOT wired to the supervised loop.** `standing_grant_use`
  is imported by neither `runtime/` nor `daemon.py`. So the supervisor's
  approve/deny gate does not consult grant-use at all — it re-prompts per
  call. THIS is the integration bug the operator identified, located: not
  "build a grant model," but "the operator surface treats every `GrantUse`
  as a fresh grant ceremony because the tool-gate never learned grant-use
  exists."
- **Caveat before assuming drop-in:** `StandingGrantUseClient` looks shaped
  for running a *standing-issued binary* under a grant, not yet for the
  general supervised tool-call gate. Needs a read before claiming it slots
  straight in. Verified: the *types* exist and are *unwired*; NOT verified:
  that they fit the supervised-tool flow without adaptation.

So the corrected direction: **Maude consumes AG's grant-use/activation
lifecycle via the daemon RPC it already speaks** — after (a) the runtime
supervisor's tool-gate is wired to check each tool call as a `GrantUse`
against an `activate()`-minted grant, and (b) that's exposed over RPC. No
second authority model in the TUI (operator's instinct is exactly right);
the one model is AG's, currently unconsumed.

## Composes with existing AG primitives (not greenfield)

- **Scope Governor** (`scope.py`) — locality-first, expanding rings,
  escalation = widen exactly one axis. The "material escalation" tier maps
  directly onto its axis-widening.
- **RationCard** (`playbooks/ration_card.py`) — absence-restrictive
  allowlists, locked axes. Already the grant object.
- **Overrides** (`overrides.py`) — scoped, time-limited, revocable leases
  with receipts. The "accumulated lease, clearly shown, revocable" UX the
  operator asked for is this, surfaced.
- **Runtime supervisor** auto-approve-read-only — the seam to generalize.

Escalation is the only new prompt; the grant, the lease, and the receipts
already exist. Wiring, not invention.

## maude operator-surface UX debt (separate from the authority model)

The display is producing "receipts from hell." Distinct from the grants
work; these are surface fixes:
- **Named tool lifecycle states** — `✓ ?` / `→ ?` convey activity without
  meaning. Need: `approved / running / completed / failed / superseded`.
- **Current decision dominates.** The one thing needing operator action
  should own the screen (a `CURRENT DECISION` pane), not compete with stale
  status noise.
- **Collapse by tool call.** Approval + execution + result + follow-up edits
  = one object, not scattered glyphs.
- **One-line arg summary, expandable to full JSON.** Raw payload fragments
  are audit-useful, scan-miserable.
- **Completion boundary.** Glanceable: progressing / stuck / waiting-on-you.
- **Separate audit/firehose pane.** The kernel stays maximally explicit; the
  operator surface should not cosplay `journalctl -f` during a gas leak.
- **Accumulated-lease panel** — show the session grant, let the operator
  revoke it.

Proposed main-pane shape (operator/chatty):
```
CURRENT DECISION
Edit packet.rs — replace refusal branch     [approve] [deny] [inspect]

RUNNING
cargo test --lib     18s elapsed

RECENT
✓ Edit pipeline.rs    ✓ cargo build    ✗ model lookup: claude-3-haiku
```

## Bug caught in passing (fix candidate, small)

Typing `Y` (uppercase) instead of `y` threw a model-lookup error naming
`claude-3-haiku` — a stale/wrong model id (the pin was `claude-haiku-4-5`).
Two defects: (a) the approve keystroke should be case-insensitive; (b) a
stale `claude-3-haiku` default lives somewhere and surfaced when `Y` fell
through the approve path. Worth a quick hunt independent of the grants work.

## Non-goals / guardrails (so compression ≠ weaker governance)

- A grant NEVER lets a plan self-approve or auto-latch. Born-candidate +
  witnessed approval stays. (Delete that and we've deleted the product.)
- Escalation triggers are an **allowlist-bounded** set; a novel action
  class escalates by default (fail-closed on the unknown).
- The lease is operator-declared and revocable, receipted like any override.
- "Compress" = fewer prompts for the *same* authority, never broader
  authority per prompt.
