# Loop Protocol — governed orchestration FSM

Ratified 2026-06-11 (claude-web handoff + ChatGPT custody hardening + Fable
interface-discipline amendment + operator consolidation). This document is
**explanatory**; the canonical loop state is `.governor/loop.json`. When this
prose and that file disagree about protocol, this document wins; when
`loop.json` and repo reality disagree, **live probes win** (§6).

## Why this exists (diagnosis, kept short)

The plan→dispatch→execute→review→patch loop worked, then died during an intake
flood, because its state was **ambient** (in a session's context) rather than
**witnessed** (on disk with re-entry probes). A prose summary of the loop is
testimony without a re-entry procedure. The fix is the constellation's own
medicine, self-administered: the loop is a small governed FSM with durable
state, receipted transitions, and an audit phase. Self-reference as admission
control, not aesthetic.

The master-control instance's job is **dispatch-and-verify against ratified
documents, NOT re-planning**. Plans are written down (wire plan, launch plan,
specimen specs, zoning); the failure mode to guard is the master re-deriving
decisions that are already ratified.

## 1. The loop-state artifact

`.governor/loop.json` — canonical, boring, parseable. Fields:

```
phase                 PLAN | DISPATCH | EXECUTE | REVIEW | AUDIT
current_slice         id or null (null only while AUDIT/PLAN reconciles)
candidate_next_slice  typed quarantine for a suspect/unadjudicated proposal —
                      neither blessed nor deleted; the audit adjudicates it
slice_spec            path(s) to the ratified spec the slice implements
acceptance            pointer to acceptance criteria (usually the backlog item)
blocked_on            ratification | nothing | named dependency
next_action           the single first thing a cold session does
last_verified_commit  git sha loop-state was last verified against
last_updated          ISO timestamp + session_id
wip_limit             1 (see §8 for what counts)
dirty_tree_allowed    false; dirty_tree_scope names the load-bearing paths
                      (working/ notes are deliberately unstaged — out of scope)
re_entry_probes       commands a cold session runs to orient (≤5, mechanical)
```

Markdown projections of loop state, if any, are explanatory only. The JSON is
the head; the receipts (§6) are the custody trail.

## 2. FSM rules

- **WIP limit = 1.** One governed slice in flight. Everything else → backlog.
- **Each phase exits by receipt** (under `.governor/loop-receipts/`):
  PLAN → next slice selected FROM the ratified backlog (never invented fresh);
  DISPATCH → assignment recorded; EXECUTE → tests green or failure named;
  REVIEW → verdict recorded; AUDIT → conformance verdict (§9).
- **Session exit obligation:** NO session ends without updating loop-state.
  A session that doesn't is a silent conversion — the update is part of the
  work, not cleanup.
- **Intake lane:** new ideas, chat dumps, zoning candidates NEVER interrupt the
  in-flight slice. They get one backlog entry with a pointer; the slice
  continues. Bartleby posture: prefer not to, until the slice completes.
  Intake may append backlog entries ONLY. It may not change phase,
  current_slice, acceptance, or next_action. Intake claiming urgency must name
  the violated invariant and receive ratification; otherwise: parked. (The trap
  is not distraction; the trap is *relevance*.)

## 3. Worker dispatch

- Workers (sub-claude / codex / qwen) receive: slice spec path, acceptance
  tests, and the loop-state pointer. They return: diff + completion receipt
  (what passed, what's open). **They do not see the backlog.**
- Master verifies receipts against acceptance tests before REVIEW exits.
  Grep over trust — the standing house rule.
- **Exit codes are the verdict, and they must be *observed*.** A REVIEW or AUDIT
  may not claim tests green unless backed by the verifier's own exit status.
  Run the test/build/lint command **bare** (its exit code stands), or via
  `governor verify-run -- <cmd>` (runs the child directly, captures its real
  exit, emits a verifier receipt). **Never judge pass/fail from a pipeline whose
  last stage is `tail`/`head`/`grep`/`tee`/`sed`/`awk`** — a pipeline returns the
  *last* command's exit code, so `cargo test | tail` reports 0 even on failure.
  Shell pipelines are masked-exit risks unless they preserve the source
  (`set -o pipefail` / `${PIPESTATUS[0]}`); `governor verify-run` refuses an
  unpreserved pipe rather than mint a green from it. A "green" with no verifier
  receipt — or one whose receipt carries `masked_exit_risk: true` /
  `verifier_exit_observed: false` — is ceremonial green, not observed state, and
  AUDIT refuses it. (Scar 2026-06-12: migration 058 shipped with three red tests
  masked by `cargo test | tail`. Global rule: `~/.claude/CLAUDE.md` §
  Verification discipline.)

## 6. Custody hardening

- `.governor/loop.json` is canonical; markdown is explanatory.
- **State ≠ receipts.** The state file is the current head; append-only
  transition receipts under `.governor/loop-receipts/` are how we got here.
  (NOT `.governor/receipts/` — that name is the runtime governor's.)
- > **Loop-state is a claim. Re-entry probes are the admissibility test.**
- When loop-state and repo reality disagree, **live probes win**; update
  loop-state and emit a stale-state receipt. Not "code wins" — code can hold
  half-landed work and ceremonial green; what wins is observed repo state
  under declared probes.
- `last_verified_commit`: if HEAD differs on cold start, run re-entry probes
  before dispatch. Distinguishes accurate / stale / aspirational /
  raccoon-copied loop-state.

## 7. Interface discipline (amended)

> **Surfaces are not authority. Origin class and unit class are authority.**

- Agents MAY drive maude/phosphor/any TUI **when the surface is the object
  under test** (developing, debugging, drilling) — such sessions emit
  drill/cli-class dispatches through the origin fence and cannot confer
  operational consequence (enforced by the type split + spend wall, not by
  this paragraph).
- Loop ORCHESTRATION never runs through a UI session: loop state lives in
  `loop.json` + receipts only; orchestration dispatches go through the
  protocol surface with actor provenance. No loop transition may depend on
  TUI session state — anyone's.
- If a capability needed for orchestration exists only in a TUI, that is not
  permission to use the TUI; it is a slice to extract the capability to the
  shared dispatcher surface.
- Loop-as-governed-workflow (FSM in AG proper, ledger-backed) is filed as a
  W2 promotion under the wiring invariant: it replaces the loop.json mechanism
  without changing phases, probes, or receipts. The file-based loop is
  authoritative v0 until that promotion's forcing case.

## 8. Backlog protocol — constellation-wide

- **Single global governed backlog** under `.governor/backlog/`, one JSON file
  per admitted item:
  `{id, repo, kind, spec_ref?, forcing_case?, priority_tier, expires?, status}`.
- **WIP-1 is global for governed slices.** Raw intake, probes, and drill
  traffic may occur but may not mutate loop phase / current_slice /
  next_action. **The membrane is mutation, not size:** exempt activity is
  non-mutating by construction (probes read; drills are operationally inert
  through the origin fence; intake appends to backlog only). Anything that
  would mutate the governed plane — land a diff, alter a spec, touch loop
  state, change anything a receipt would need to explain — is admitted work,
  no minimum size. "It was just a probe" is how 400-line diffs arrive at 2am
  wearing a trench coat.
- **Slice kinds:**
  - `spec_slice`: input is doctrine / zoning text / incident notes / backlog
    ambiguity; output is a ratifiable gap spec with acceptance criteria.
  - `build_slice`: input is a ratified spec with acceptance criteria; output
    is diff + tests + receipt.
- **Admission:** build slices require a ratified gap spec. Doctrine without
  acceptance criteria enters only as a spec_slice. Unmodeled work is not
  admitted.
- **spec_slice acceptance signal — `fence_legibility_escape_count`** (adopted
  2026-06-12): run a cold flat-prompt validation pass (codex or equivalent;
  artifact only, no doctrine preamble) and count the validator's
  "what I'd build wrong" items that ESCAPE the spec's existing pins. Zero
  escapes = the spec teaches its own boundaries = ratifiable. Named
  ambiguities are patched as pins before the nod; the pass is recorded in the
  spec's validation-provenance section. (First instance:
  GOV_GAP_ACT_TWO_RECEIPT_INTERROGATION_001 — five ambiguities patched, zero
  escapes.)
- **Priority:**
  1. W1 items in ratified order until W1 exit criteria;
  2. forcing-case items (a named refusal that can't currently be expressed);
  3. expiring debt;
  4. ordinary debt;
  5. tidiness.
- PLAN auto-selects by this order. Operator ratification is required only for
  custody-affecting, cross-repo-schema, public-release, or Zenodo-touching
  slices — the existing ratification boundary, unchanged.

## 9. AUDIT phase — plan conformance, not QA

Cycle: `PLAN → DISPATCH → EXECUTE → REVIEW → AUDIT → PLAN`.
**Cold start is an AUDIT invocation** (re-entry unified with the cycle, not a
special case).

**Campaign discovery (cold start, added 2026-06-23).** Before asking the operator
for campaign context, a cold AUDIT inspects `.governor/campaigns/*.yaml` (inert
discovery manifests) and `docs/campaigns/*/STATUS.md`. Each manifest's `files:`
index points at that campaign's `CAMPAIGN`/`DECISIONS`/`GRANTS`/`REPLAY`/`STATUS`/
`NEXT`. **If a question matches a ratified decision in a capsule's `DECISIONS.md`,
apply its `default_action` and cite the decision ID — do not re-ask the operator**
unless the case falls outside that decision's `applies_when` or hits a
`requires_human_if`. These capsules are **inert metadata**: discovering one does NOT
make its campaign active, change `phase`, touch `current_slice`, or alter WIP-1
ownership — `loop.json` remains the single live program counter. (This rule is the
cold-start *protocol* form of the convention; the first capsule is
`docs/campaigns/ag-admit-self-build/`.)

AUDIT checks, mechanized where possible:

1. **State conformance** — `loop.json` claims vs live probes; HEAD vs
   `last_verified_commit` (else probes run before dispatch); dirty tree
   accounted for within `dirty_tree_scope`.
2. **Plan conformance** — the closed slice and the proposed next slice vs the
   ratified documents (W1 order, backlog priority rule). Deviation requires a
   **deviation receipt with named evidence**; drift with a receipt is a
   decision; drift without one is the thing that killed the loop. Undocumented
   deviation = HALT for operator ratification.
3. **Obligation conformance** (the Paper-27 check: reconciliation can restore
   desired state while silently degrading obligations) — required receipts
   exist; corpus/register updates exist where required; pinning/negative
   tests present and green; closed-world obligations intact. A successful
   patch that degraded evidence/custody is a **deviation, not a pass**.

Output: append-only audit receipt — `pass | deviations_named[] |
halt_for_ratification` — summarized in one compact block to the operator each
cycle (the loop's heartbeat). Probes are executed at audit time and their live
output recorded; transcribing earlier findings into receipt form is the
ceremonial-audit failure mode.

**Independence rule:** warm self-audit suffices for mechanized checks; at chunk
boundaries and before custody-affecting ratification, AUDIT runs in a fresh
context (new session; probes + ratified docs + receipts only, no warm
narrative). The instance that drifted is the instance least equipped to notice.

## 10. Restart seed + selection rule (2026-06-11 restart)

Seeded in AUDIT — not PLAN, not a pre-selected slice. The restart followed a
stale/contradictory recommendation, so the first durable state must not
pretend a slice was already selected; the first action is reconciliation, and
the suspect recommendation rides as `candidate_next_slice`, quarantined.

Selection rule after probes:
1. refused-spend script / show surface missing → `current_slice = W1 item 3`;
2. item 3 exists but proof seam missing/unwired → `current_slice = W1 item 4`;
3. both genuinely done with evidence → `current_slice = W1 item 5` (OPA shim);
4. ambiguous → `HALT_FOR_RATIFICATION` — ambiguity at selection time is where
   process drift breeds.

Item-4 acceptance gate (operator-ratified at plan review): item 4's acceptance
is not "proof_seam.py exists and tests pass" (cargo) but "the refusal class
maps to the Lean theorem that actually licenses it." A known doubt about that
mapping (`proof-seam-citation-reconciliation`) means item 4 is open *in the
acceptance sense* until resolved — selection branch 2 applies.

## 11. AUTO_RUN mode — bounded overnight execution (ratified 2026-06-12)

AUTO_RUN is a bounded runner for admitted work. It is not autonomous
ratification. Best-effort with receipts, not best-effort with vibes.

> Auto may continue through admitted, non-custody-affecting work when failures
> are classified. Auto may not invent scope, ratify ambiguity, or silently
> degrade obligations. The dangerous case is not failure; the dangerous case
> is **successful improvisation**.

**AUTO_RUN starts in AUDIT and ends in AUDIT.** The morning state is not "look
what I did while unsupervised"; it is "here is what was admitted, what ran,
what passed, what parked, and what I refused to fake."

Allowed: execute already-admitted `build_slice`s; draft candidate
`spec_slice`s from filed backlog items; run probes/tests/transcripts; emit
transition/audit/capacity/deviation receipts; park blocked work with named
reasons; select the next admitted item by ratified priority.

Forbidden: custody-affecting ratification; admitting candidate slices without
the admission gate; changing priority rules; cross-repo schema changes;
Zenodo/public-release mutations; guessing unanswered HitL clarifications;
treating fallback behavior as success unless the spec explicitly allows it.

Failure handling (classify, never improvise):

| Failure | Behavior |
|---|---|
| Recoverable test failure | Bounded local patch attempts, rerun |
| Missing dependency/tool | Record dependency gap; continue only on a spec-approved fallback |
| Usage/window exhaustion | `capacity_exhaustion` receipt, checkpoint loop state, halt |
| Custody ambiguity | Park; typed question into the next HitL batch |
| Spec contradiction / plan deviation | Deviation receipt; halt for ratification |
| Dirty/ambiguous repo state | Preserve evidence; halt |

**Patch mutation membrane (load-bearing):** patch attempts may not touch files
outside the slice's declared scope. A fix that needs to reach outside it —
another repo, a schema, the corpus, this protocol — is not a patch, it is a
deviation, and it parks. Without this line, "two patch attempts" quietly
becomes two scope expansions performed at 3am by a model with a budget and
good intentions.

Retry/capacity budget (metabolic cap — otherwise overnight mode is an
archaeological site by morning):

```yaml
auto_run_budget:
  max_slices_per_run: 3
  max_patch_attempts_per_slice: 2
  max_test_retries_per_failure: 2
  max_wall_clock_hours: 6
  halt_on_unclassified_failure: true
```

> **Retries may reduce uncertainty. Retries may not manufacture authority.**
> retry = uncertainty about transient state; refusal = certainty about
> inadmissible state. Exhausted retries classify (`exhaustion /
> retry_budget_spent`), they do not upgrade absence into failure semantics
> without evidence.

### 11.1 Backoff policy — epistemic, not rate-based (added 2026-06-12)

Classic backoff answers contention ("busy → wait → retry"). Loop backoff
answers confusion ("my action model is failing → stop mutating → observe").
Full reasoning record: `working/pipeline-doctrine-2026-06-12.md` §1.

> **When retries stop producing new evidence, retry is forbidden. When
> failures produce too many kinds of evidence, mutation is forbidden.**

- **Identical failure CLASS twice** (class match, never exact-string — strings
  rot): transient hypothesis dead → reclassify per the failure table; further
  retries forbidden.
- **Distinct failure classes across attempts**: model-mismatch signature →
  enter PROBE mode, emit a confusion receipt naming the failure classes.
- **PROBE mode is a mode switch, not a retry.** Invariants: no mutations, no
  commits, no generated fixes, no "while I'm here" — read-only commands,
  state inventory, receipt inspection, failure-class synthesis only. The wall
  is pinned mechanically: *probe sessions emit zero mutation receipts* is
  checkable from the receipt trail after the fact (backlog:
  `epistemic-backoff-mechanization`).
- **Burn-per-progress** (capacity consumed / slice-advancing receipts): soft
  threshold → mandatory PROBE downshift + confusion receipt; hard threshold →
  capacity checkpoint + halt for morning audit. Confusion spend is metabolic:
  it authorizes neither mutation nor continued retries; it triggers
  observation.
- **TIER ESCALATION IS ILLEGAL UNTIL AFTER A PROBE PASS.** Then: once,
  baseline+1 (§12), with recorded reason — never as a retry substitute.
- Ladder: `retry → probe → escalate-once → park (batched clarification) → halt`.
- **Correlated confusion check (morning audit obligation):** confusion
  receipts from multiple agents on unrelated slices in the same window =
  environment-level failure, not slice-level — escalate to environment
  diagnosis before any recomposition, and before any quorum over the
  diagnosis counts agreement as evidence.
- Confusion receipts feed the audit and, eventually, decomposer calibration:
  recurring mismatch on a slice CLASS means the slices are cut wrong, not the
  agents.

Exit obligation: AUTO_RUN ends by updating `.governor/loop.json` and writing a
compact heartbeat — slices attempted/completed, parked items,
failures/deviations, capacity exhaustion if any, exact next action for cold
restart.

### 11.2 Automation rungs — automate within, ratify before changing (ratified 2026-06-13)

Throughput is bounded by *authority class*, not effort. Automation may chain
slices that share an already-ratified authority rung; it must halt before any
transition that changes what the system is allowed to decide, mutate, enforce,
publish, or rely on.

> **Automation may advance work inside an already-ratified authority rung. It
> must halt before any transition that changes what the system is allowed to
> decide, mutate, enforce, publish, or rely on.**

Compact form: *automate within a rung; ratify before changing rungs.* Less
ceremonial: let the machines carry boxes down the hallway; don't let them decide
which walls are load-bearing.

| Safe to chain (same rung) | Must halt for ratification (rung change) |
|---|---|
| pure accounting → shadow emission → read-only observation → inert metadata | shadow → enforcement |
| | observation → candidate delta |
| | candidate delta → activation |
| | activation → promotion |
| | local-only → publication / push |
| | AG-local → cross-repo seam change |
| | docs-side doctrine → code-side enforcement of it |

Within a rung, bounded AUTO per slice is: build → targeted verify-run →
adversarial seam validation (a second agent challenges only that slice) → apply
only **blocking** findings → verify-run again → one local commit → continue only
if clean. **Chain fuse:** more than one refinement pass means the seam is murkier
than expected — halt. Stop immediately on enforcement/gating/mutation introduced,
unrelated files touched, validator fail, test fail, authority-boundary ambiguity,
or any LA/API/front-door/loop-FSM expansion. "Efficiency" here means fewer
operator interrupts, never reduced custody — the validator reduces involvement
but never becomes the operator.

### 11.3 Validator findings are rung-scoped — a halt needs jurisdiction (ratified 2026-06-13)

The §11.2 chain fuse ("more than one refinement pass → halt") shipped too blunt:
it treated "the current slice is unsafe" and "the validator found debt that only
matters at a higher rung" as the same siren. They are different fires. A halt
condition needs **jurisdiction**, not just a trigger.

> **A validator finding must be classified by the authority boundary it
> threatens. Halt only when the finding threatens the CURRENT rung's authority
> boundary.**

Every validator finding answers *"unsafe for what authority level?"* — not just
"I found a weird input." Classify each into exactly one venue:

| Finding class | Venue | Action |
|---|---|---|
| **Current-rung violation** | this slice's contract | **block** — fix before commit |
| **Future-rung requirement** | activation / enforcement / publication | mint/reference a **NonDischargeClaim in the DebtLedger** (target_rung, authorized_collector ≠ target_rung, discharge_witness, blocks_before) — never commit-body/plan prose; activation refuses while the claim is open; continue only if the current rung stays safe. *Named is not collected; carried is not collected either.* |
| **Defense-in-depth concern** | secondary tripwire, not the authority gate | fix once if cheap; else record and require before the higher rung |
| **Scope-expanding remedy** | changes what the slice is allowed to decide | **halt** for operator ratification |

The refined chain fuse: a second refinement pass halts **unless ALL hold** — no
apply/write/enforcement path exists, the authority boundary is separately closed
(and is not the failing mechanism), the finding is classified future-rung or
defense-in-depth, validator and builder **agree** on that classification, and the
accepted debt is minted as a **NonDischargeClaim in the DebtLedger** binding a
collector and blocking its higher rung (not recorded as commit-body prose — named
is not collected). Classification authority sits *above* the rung being decided:
builder/validator agreement is attribution, not the authority to reclassify a
current-rung blocker as deferrable.

> **Enforcement status (honesty about this rule itself):** the fuse is currently
> *practiced* by this loop, not *enforced* by the kernel — folklore with a README. A
> conscientious runner halts on its own, which makes the unencoded invariant look
> encoded; it breaks with a less-conscientious runner (a different model, an AUTO_RUN,
> a drifted controller). Making fuse-firing a structural absence of mutation caps
> (and re-arm operator-fiat) is `GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001`; the broader
> class — every place runner good-behavior is load-bearing — is
> `docs/cross-tool/conscientious-behavior-not-custody-note.md`. *Claude halting is
> weather; kernel refusal is verdict.*

**Always halt for operator ratification** (no auto-accept), regardless of pass
count: an actual write/apply/activate path appears; a surface/authority allowlist
leak; a genesis-class target reaching the authority boundary; LA/API/front-door
expansion; the validator says the *current* contract is violated; or builder and
validator **disagree** on the classification.

This prevents both failure modes: too lax ("eh, future-slice" hiding a real
current leak) and too strict (every future-hardening concern waking the operator
and killing throughput). Worked example (P2.1, 2026-06-13): a surface-allowlist
leak would have been a current-rung block; the genesis-detector leetspeak evasion
was future-rung debt (string denylist is leaky by nature; per-surface target
allowlists are required before activation); the forged-`hard_guards` case was a
cheap current-invariant hardening (fixed once). Same validator run, three
different venues.

**Known refinement (gap-tracked, not yet wired):** builder+validator *agreement*
settles a venue, but if the two share a provenance class the agreement is
correlated — the agent grading its own homework (NNC at the classification
layer). The fix is to make agreement independence-typed (`independence_class`),
with the floor rising with how much continuation the venue authorizes
(`future_rung_debt` / `false_positive` need the strictest). Until wired,
disagreement-halts and operator-fallback hold the line. See
`specs/gaps/GOV_GAP_RUNG_DEBT_COLLECTION_001.md` (the authority that clears X
cannot be X).

## 12. Model capacity policy (ratified 2026-06-12)

The forcing event: the loop's first master was Fable-tier and exhausted its
window mid-slice (receipt `2026-06-12T033659Z.capacity-exhaustion`). Model
brilliance is ambient attention — scarce, exhaustible, behavior-warping, and
governable. A bigger model is not monotonically better for loop work: it
burns window faster, notices more seams than the slice can admit, tempts
replanning, and turns routine dispatch into doctrine opera.

- **The master loop runs on the smallest model that can enforce the protocol.**
  Its job is bureaucratically boring: keep the program counter, enforce WIP-1,
  dispatch, verify, refuse drift. Large synthesis models are escalation
  resources, not default orchestration substrate.

| Capacity | Tier |
|---|---|
| PLAN selection / DISPATCH / REVIEW | controller (Opus-class) |
| EXECUTE implementation | worker (Sonnet/Codex/Qwen-class) |
| AUDIT, ordinary cycles | controller + mechanized probes |
| AUDIT at chunk/custody boundaries; doctrine synthesis; ratification advice; spec fence-legibility critique | synthesis (Fable-class) — appeals court, not shift supervisor |

- Synthesis-tier use in ordinary PLAN/DISPATCH/REVIEW requires a recorded
  reason why smaller models are insufficient. "It was available" is ambient
  capacity abuse — `refusal / model_tier_not_admitted` is policy, distinct
  from `exhaustion / model_window_exhausted` (spent the resource vs tried to
  spend the wrong resource for the phase).
- **Spend up one tier where mistakes compound; spend down where mistakes are
  contained.** Decomposition / diagnostic planning / recomposition audit
  default to baseline+1 (error-amplifier phases; one tier up is not luxury
  inference, it is avoiding downstream cleanup) with `max_attempts: 1` —
  a better first pass, not asking the owl until it writes a constitution.
  Ladder: baseline performs the task; baseline+1 notices the shape of likely
  mistakes; baseline+2 adjudicates ambiguous doctrine/custody.
- **No tier ratifies.** Tier changes advice quality, never authority class.
  Baseline+2 at a ratification boundary produces better ratification *advice*;
  the ratification is the operator's, every time, regardless of advisor size.
  Pinning obligation (when the loop FSM gets code): `model_tier` must never
  appear as the admission actor on any backlog transition.
- **Capacity exhaustion is a typed loop event, not an oops.** Emit the
  `capacity_exhaustion` receipt, checkpoint, downgrade the master, resume.
  The receipt is ALSO a **controller-transition receipt** (Paper-23 pin: a
  non-self-identical controller inherits the predecessor's *receipts*, never
  its warm intentions) — actor change recorded in loop.json, session lineage
  broken explicitly, resume in AUDIT mandatory *because* the controller
  changed. First instance: 2026-06-12 (fable → opus, mid-build-slice; the
  successor's resume-audit found the work intact and closed the slice from
  receipts alone).
- **The A/B is already running.** Fable-master arm: this week's receipt trail
  (token burn, exhaustion event, throughput). Opus-master arm: accumulating
  from 2026-06-12 under identical protocol. The comparison (escalation rate,
  window consumption, drift-catch parity) falls out of the ledger — model
  zoning ratified by its own receipts, not vendor pricing pages. Tier→model
  mapping is deployment config; the tier abstraction is the doctrine.

## Doctrine

| Verdict | Question |
|---|---|
| **Cargo verdict** | Did the slice pass? |
| **Process verdict** | Was this the slice the ratified plan allowed us to do next? |

> Cargo success must not launder process drift.

- *I would prefer not to* — the Bartleby posture: intake waits for the slice.
- *A gap is a difference between compatible clock witnesses, not numbers.*
- *Loop-state is a claim; re-entry probes are the admissibility test.*
- *Surfaces are not authority. Origin class and unit class are authority.*
- *Human review belongs at admission, boundary definition, budget setting,
  and audit — not necessarily inside every admissible action.* (operator,
  2026-06-12: the placement rule for HitL — the nod gates the envelope, not
  each step within it. Composes with §11 AUTO_RUN and the guvnah nod queue.)
