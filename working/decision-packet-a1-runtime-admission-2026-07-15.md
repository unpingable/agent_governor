# Decision packet A-1 — what admits a runtime session to effect-bearing execution?

**ID:** `a1-runtime-admission`
**Filed:** 2026-07-15 (operator-selected item 3/4 of the 2026-07-15 sequenced selection)
**Status:** **DRAFT — requires explicit operator ruling; authorizes no implementation**
**Parent:** `working/authority-seams-decision-packet-2026-07-14.md` §A-1
**Class:** canonical runtime-authorization semantics

## Confirmed current state (re-verified 2026-07-15 at AG `464efeb`)

1. `runtime.session.create` (daemon) and `SessionSupervisor.create_session` /
   `launch_session` consult **no authority artifact**: not `loop.json`, not a
   selected slice, not a Plan Review Agenda, not campaign ratification, not
   WorkContainer admission. Verified by sweep of `launch_session` — zero
   consultations (the only "loop" matches are event-loop plumbing).
2. Since A-7 (`443ff63`), `operator_mode` is a closed domain and the effect
   path fails closed: WRITE/COMMUNICATE prompt unless the record is exactly
   `autonomous`. **A-7 bounds *who approves each effect*; it does not decide
   *what admits the session*.**
3. The governed lane exists but is **opt-in, and `maude run` is BOTH lanes
   depending on the plan**: a governed plan (has a `governance` block) walks
   `admit_for_execution` (born-candidate refusal; witness-verified citations;
   S7 containment) → `runtime.grant.activate` (seam B since `5a0bca3`) → S2b
   compression. An **ungoverned** plan admits on the submitter's own act
   (M-2) and attaches **no grant** (`runner.py:169` gates on
   `admission.governed`; pinned by `test_ungoverned_run_attaches_no_grant`,
   maude `tests/test_plan_runner.py:335`). A plain `runtime launch` touches
   none of it.
4. **Autonomy and governedness are independent axes — this packet's first
   draft conflated them (caught by adversarial review, 2026-07-15).** Maude
   derives `operator_mode` from the SUBMITTER (`runner.py:111`: `human` →
   interactive, else → autonomous); the grant derives from the GOVERNANCE
   block. All four squares exist today as first-class inputs:
   interactive×governed (the NS dogfood), interactive×ungoverned,
   autonomous×governed (synthetic_agent + approved plan),
   **autonomous×ungoverned** — the last reachable both via a parser-blessed
   `synthetic_agent` ungoverned plan (maude `envelope.py:577-586`) and via
   the help-documented `governor runtime launch --mode autonomous`
   (`cli.py:20022-20035`), plus the direct-construction tests. That square —
   every write self-approving, no plan, no grant, no label — is the exposure
   this packet is actually about.

**Framing observation (drafter's, not a ruling):** the system as built is
already Option 4 in behavior — an ungoverned lane exists and launches freely —
but without Option 4's obligations (an explicit non-authority label and its
own stated effect rules). The question is whether to ratify that shape, or
close it.

## The four options (from the 2026-07-14 packet, elaborated)

### Option 1 — a selected loop slice is mandatory for every governed run

`runtime.session.create` refuses unless `.governor/loop.json` names a
`current_slice` and the request cites it.

- **Consequences:** binds runtime activity to the WIP-1 program counter.
  Kills all ad-hoc supervised work (one-off maude sessions, experiments,
  drills) or forces slice-minting ceremony for each. Test suites that
  construct sessions directly need a fixture slice or an exemption seam —
  and an exemption seam here is a second door.
- **Cost honestly stated:** the loop selector currently carries an
  UNRESOLVED selection-condition inconsistency (may PLAN auto-select?).
  Option 1 promotes that unresolved record into a load-bearing gate.
- **Acceptance tests:** create-without-slice refuses before state exists;
  create-citing-stale-slice (closed/superseded) refuses; the refusal names
  the missing artifact; fork inherits the parent's slice citation or refuses.

### Option 2 — an exact verified plan/Agenda is sufficient, independent of loop selection

Sessions admit iff they cite an approved plan (seam-B witness verified) or
an authorized Agenda. Loop selection stays reporting-only.

- **Consequences:** makes the S1–S7 grant lane the *only* lane. Every ad-hoc
  session needs a plan envelope — heavier than today's `maude run` for real
  packets, much heavier for "look at this quickly". The M-2 human path
  (ungoverned plans admit on the submitter's own authority) partially
  softens this, but then M-2 becomes the de-facto ungoverned lane —
  Option 4 wearing Option 2's clothes.
- **Acceptance tests:** create-without-plan refuses; create-with-candidate
  plan refuses (`governance_not_approved`); create-with-approved-plan admits
  and activates the grant atomically; witness replay across plans refuses
  (already pinned by seam B).

### Option 3 — both required for the governed lane

Selection (Option 1) AND exact plan approval (Option 2) to enter the
governed lane; anything else refuses.

- **Consequences:** strongest conjunction, largest ceremony. Inherits both
  options' costs plus their interaction (a selected slice whose plan lapsed;
  an approved plan whose slice was superseded). Only coherent if governed
  runs are rare, deliberate events — which contradicts the dogfood cadence
  (NS-2..6 want low-friction governed runs).
- **Acceptance tests:** the pairwise matrix (slice×plan: 00/01/10/11) with
  only 11 admitting; each refusal names which conjunct failed.

### Option 4 — an explicitly labeled ungoverned lane (two variants — the split is the honest part)

Ratify the current shape and close its honesty gap: sessions may launch
without slice or plan, but the lane is explicit, closed-domain (same law as
`operator_mode`), and propagates to every receipt/event/promotion the
session emits. **The label need not be a new field:** the grant's presence
(`SessionRecord.execution_grant`, set only via seam-B activation) is already
the mechanical lane discriminator, and `policy_context` already threads
through create/fork/launch — the ruling should say whether the lane is a
*derived projection* of grant presence or a *declared field*; declaring what
can be derived creates a second home for one fact.

**4a — label + restriction (strict).** Additionally refuse
ungoverned×autonomous at create. This closes the exposed square but is
**NOT zero-breakage** (the first draft claimed it was; refuted):
`governor runtime launch --mode autonomous` (help-documented, no plan, no
grant) refuses outright; maude's parser-blessed `synthetic_agent` ungoverned
plans stop launching; the direct-construction autonomous tests need
fixtures or a lab exemption — and an exemption seam is a second door. This
is a real, deliberate breaking change to a documented surface.

**4b — label only (observe first).** Lane labeling + receipt propagation,
no behavioral change. The exposed square keeps working but stops being
invisible: every effect receipt from an ungoverned autonomous session says
so. Measurable denominator for a later squeeze; zero breakage genuinely
holds here, and 4a remains available as a follow-up ruling with usage data
in hand.

- **Acceptance tests (both variants):** lane visible on the session record +
  every emitted event; lane immutable post-create; governed lane (approved
  plan) admits autonomous + grants exactly as today. **4a adds:**
  ungoverned×autonomous refuses at create before state exists (CLI, RPC, and
  direct construction); ungoverned session attempting `runtime.grant.activate`
  refuses. **4b adds:** the ungoverned×autonomous square emits lane-labeled
  receipts distinguishable in the trail.

## Drafter's recommendation (one paragraph, severable — REVISED after refute)

The first draft recommended Option 4 with the restriction, claiming zero
breakage; adversarial review refuted that (the restriction breaks a
documented CLI path, a parser-blessed maude path, and the autonomous test
fixtures — and the leak framing conflated the autonomy and governance axes).
Revised recommendation: **Option 4b now** (labels, observe-only, genuinely
zero-breakage), with **4a as a named follow-up ruling** once the labeled
trail shows who actually uses the ungoverned×autonomous square. That is the
same observe-then-arm posture the estate already uses everywhere else
(Phase A signals, egress gate, playbooks landing). Options 1–3 each convert
an unresolved or heavyweight artifact into a mandatory gate and would be
fought by every existing caller including the dogfood.

## Compatibility questions the ruling must answer

- Existing direct RPC callers and tests constructing sessions: default-label
  (4) or fixture ceremony (1/2/3)?
- Fork/recovery: does a fork inherit the parent's lane/citation, and may an
  ungoverned parent fork at all?
- Maude plain runs (non-`run` commands that open sessions): which lane?
- External clients with no loop identity: refused (1/3) or labeled (4)?

## Adversarial review record (2026-07-15)

The draft was refuted before filing (Opus-refute pass; codex on quota hold).
Findings, all verified at source by the drafter before amendment:

1. **FATAL — "zero breakage" was false.** `runtime launch --mode autonomous`
   (cli.py:20022) and the direct-construction autonomous tests are exactly
   the square the restriction refuses. → Option 4 split into 4a/4b;
   recommendation moved to 4b.
2. **FATAL — the leak model conflated two axes.** Maude autonomy = submitter
   axis (`runner.py:111`); grants = governance axis (`runner.py:169`).
   `autonomous ⇒ ungoverned` was wrong in both directions. → Confirmed-state
   item 4 rewritten as the four-square model.
3. **MATERIAL — `maude run` is both lanes**, not the governed lane
   (`test_ungoverned_run_attaches_no_grant`). The NS-2 specimen survives any
   option via the submitter axis (`submitter_kind: human`), not for the
   reason the draft gave. → State item 3 corrected.
4. **MATERIAL — field duplication risk.** `execution_grant` presence already
   discriminates the lane mechanically; `policy_context` already threads
   create/fork/launch. → The derived-vs-declared question is now part of the
   ruling ask (single canonical home per fact).

## Stop lines (unchanged from the parent packet)

- Do not wire Plan Review, ScopeGrant, WorkContainer, or governed dispatch
  as an incidental answer.
- No approval consumption/revocation semantics ride along (that is A-3).
- No change to what `receipt_role=authority` means (that is A-5).
- Implementation requires an explicit ruling of THIS packet; the 2026-07-15
  selection act authorized the draft only.
