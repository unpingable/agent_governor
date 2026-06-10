# Compelling-MVP Slice Plan — standing-before-spendability spine

**Status: planning artifact for the AG/constellation MVP. Hand to the Code session.**
**Provenance: authored 2026-06-09 by operator on claude-web (Fable access); filed locally 2026-06-09 as the canonical campaign card. Supersedes the prior local sketch that pinned the c0 slice while this was in flight.**

Scope basis: C0 as already chosen (standing-before-spendability forcing case). This
plan does not re-litigate C0; it sequences what turns C0 into a *compelling* MVP.

---

## 0. Definition of "compelling"

Minimal MVP: the C0 invariant test passes (missing standing → zero LA calls).

Compelling MVP: a stranger (Chris) watches **one real workload run six ways in
~90 seconds**: five runs refused at five different gates, one run that lands an
effect — every outcome receipted, and **one command** (`why <receipt-id>`) walks
any outcome back to the originating NQ finding.

The demo poster: **six runs, five refusals, one effect, one command explains
everything.** Refusal is the product. The happy path is the control group.

---

## 1. Ground rules (carried from doctrine; encode into every slice)

- **Grep-first.** No slice writes code before classifying the existing surface.
- **Teeth standard.** Every gate test asserts *call-count zero* on a mock of the
  next stage downstream of a refusal. Refusal that merely logs is not refusal.
- **Stage distinctness.** No-budget is an LA refusal, not a standing refusal;
  denied is not gap; expiry is a standing lifecycle state, not a new freshness
  primitive. Each refusal names its own gate.
- **No parked primitives.** No ArtifactKind/UseKind enums, no Z3, no grep-sentinel
  infra, no WLP transport, no Cantrip adapter, no generic typing passes.
- **Single box.** Everything is local SQLite + library calls. WLP envelopes only
  if an artifact actually crosses a system boundary in the demo (it should not).
- **Negative results are deliverables.** "Topological absence, not mechanical
  refusal" is an acceptable, citable slice outcome.

---

## 2. Spine slices

### C0 — standing-before-spendability forcing case  *(as specified; in flight)*
- **Invariant:** missing standing → no capacity request.
- **Q1 — Standing-path classification:**
  - A = LA unreachable from observation/testimony today
  - B = LA reachable only after standing
  - C = LA reachable without standing (forces local patch)
- **Q2 — Budget-authority classification** (sharpened 2026-06-09 per
  Gemini's "two live accountants is not technical debt; it is an active
  laundering surface"):
  - BA0 = no budget authority in AG
  - BA1 = display / accounting only, not authoritative for consequence
  - BA2 = directly LA-backed
  - **BA3 = internal authoritative budget/capacity ledger** ← **blocks MVP
    until bypassed or hard-shorted to LA.** A model will find the delta
    between two live ledgers; "deprecation target" framing is too soft. If
    any AG counter gates external consequence (mutation, action, real
    spending), MVP cannot proceed until that counter is removed from the
    consequence path or routed through LA.
- **DoD:** Q1 classification (A/B/C) + Q2 classification (BA0/BA1/BA2/BA3) +
  MVP-block check (BA3 anywhere = stop the spine). Code only if Q1=C OR
  Q2=BA3 (the latter requires a bypass/short, not invention).
- **Cadence:** HIGH (chatty-in-pipe + codex-exec adversarial review).
  Two basis questions; this is the load-bearing checkpoint.

### S1 — standing → wicket seam
- **Invariant:** no admission verdict without a standing receipt id in the cooked
  context. Caller cooks; wicket accounts — do not teach wicket to resolve
  standing, only to refuse when the cooked answer is missing/dangling.
- **Teeth:** missing `standing_receipt_id` → wicket never consulted on
  basis/precedence (or returns the standing-shaped refusal before dimensional
  evaluation — pick whichever the existing wicket SPEC.md licenses; grep first).
- **Preserve:** the soft/hard split. `gap` (OPEN_FINDING_ACCOUNTED) stays
  admissible-with-accounting; `denied` stays terminal. The demo uses both.
- **Cadence:** autopilot after C0 classifies.

### S2 — wicket → LA seam  (C0's other half)
- **Invariant:** no capacity request without an admission receipt.
- **Positive control:** standing + admission present, budget exhausted →
  LA refusal (`InsufficientStock`/equivalent), explicitly *not* a standing or
  admission refusal. This is the stage-distinctness test with teeth.
- **Cadence:** autopilot.

### S3 — LA → effect seam (the retry-storm kill)
- **Invariant:** effect requires a `Consumed` verdict; replay of the same
  consumption event id → `AlreadyConsumed`, effect count stays 1.
- **Note:** LA's 17 tests + WL-001 (a real `std::fs::write` gated by the
  accountant) already prove this *inside* LA. The slice is AG calling LA's
  contract, not re-proving linearity. Grep before writing anything.
- **Demo value:** this is the live "eligibility is contractible; spendability is
  linear" moment — same valid warrant cited twice, second spend refused.
- **Cadence:** autopilot.

### S4-lite — refusals are receipted (schema touch, deliberately minimal)
- **Invariant:** every refusal in S1–S3 lands in the AG ledger as a hash-chained
  receipt naming its gate.
- **Closed refusal-kind set** (ratified 2026-06-09 at the S4-lite naming
  checkpoint per codex adversarial nomenclature review; sealed against
  ontology drift — additions require explicit S4-lite reopen):
  ```
  standing_required
  standing_expired              (standing-layer expiry; NOT LA token expiry)
  admission_denied
  admission_gap_accounted
  capacity_refused              (LA InsufficientCapacity; AND LA Denied at request)
  already_consumed              (LA AlreadyConsumed; the replay-kill)
  dangling_receipt_reference    (AG-side admission_receipt_id miss)
  token_expired                 (LA Expired — distinct from standing_expired)
  token_revoked                 (LA Revoked)
  unknown_token                 (LA UnknownToken — distinct from dangling_receipt_reference)
  scope_mismatch                (LA ScopeMismatch — scope disagreement, not capacity)
  ```
  Eleven refusal kinds total. Each LA ConsumptionDecision failure variant
  gets its own kind because each is a SPEC-visible failure shape with its
  own receipt fields; collapsing under `capacity_refused` would have made
  S5 `why <receipt-id>` unable to distinguish capacity shortage from token
  expiry, revocation, unknown token, or scope mismatch.
- **Plus one bypass-kind** (not a refusal; emitted when an AG-internal
  BA3 surface is suppressed during MVP runs to honor the
  `SpendabilityAuthority = LA_ONLY` contract from C0-resolved). Stays
  visibly weird by operator decree — it must not look like a denial.
  Emitted by the runtime supervisor / D0 harness at suppression time, NOT
  by the client modules:
  ```
  BA3_BYPASSED_FOR_MVP
  ```
- **Receipt storage path** (ratified 2026-06-09): use the existing
  `GateReceiptSystem` at `src/governor/gate_receipt.py`. Receipts go to
  `{root}/receipts/gate_receipts.jsonl` via `ReceiptStore`; evidence
  blobs to `{root}/evidence/{hash[:2]}/{hash}.json` via `EvidenceStore`.
  Already content-addressed, hash-chained, queryable by `receipt_id`,
  and separates evidence by `evidence_hash` — exactly the shape S5
  `why <receipt-id>` needs as a join surface. No new store; do not
  invent a parallel receipt path.
- **Out:** full cross-tool receipt schema unification, WLP envelopes,
  stop-binding clause redesign. Use each tool's native receipt + an AG ledger
  entry referencing it by id. Schema unification is v2.
- **Cadence:** HIGH checkpoint — receipt vocabulary is doctrine surface.
  These names become DB primitives in local SQLite; they must map cleanly
  to the output of `why <receipt-id>` (S5). One chatty/codex pass before
  they fossilize, then autopilot. Do not let this drift into schema
  engineering or vocabulary expansion.

### S5 — `why <receipt-id>` (the compelling query)
- **Goal:** extend `governor trace`/`governor receipts` to join across ledgers:
  AG receipt → admission receipt → standing receipt chain → originating NQ
  finding. Read-only. One command, full provenance, works on refusals too.
- **Teeth:** `why` on a refusal receipt terminates at the gate that refused and
  shows the absence (e.g., "no standing receipt cited") rather than a stack
  trace. Absence is rendered, not erred.
- **Cadence:** autopilot. This is a join, not a judgment.
- **Status: CLOSED for GateReceipt joins (standing→wicket→LA chain) 2026-06-09.**
- **Amended goal (2026-06-09):** extend/verify `why` reaches the
  **originating NQ finding**, not just the AG-side chain. This is the
  remaining S5 work and depends on D0-Origin landing the real NQ
  finding emission with drill provenance.

---

## 3. Demo slices (the compelling wrapper)

> **2026-06-09 amendment — D0 is the origin-custody slice, not the harness.**
>
> Originally D0 was framed as the show surface (compose harness + ticket
> display). After D0a closed (real refusal emission) and D0c-a closed (real
> admission emission), the better-doctrine shape became visible: the demo
> should *open at NQ*, not at a CLI invocation. **Observation enters the
> admissibility chain rather than living outside the stage directions.**
> The product sentence becomes: *an observation from the witness layer
> raised a standing question, and nothing could convert that observation
> into spend without passing four gates.* The harness work below is now
> sequenced as D0d/D0e *after* the origin and provenance slices land.

### D0-Origin — staged condition, authentic NQ observation, drill provenance minted
- Stage a real condition in a sandbox target (genuinely bloat a WAL file).
  NQ's evaluator observes it authentically — the *condition* is
  manufactured, but the observation is real. Fire drill with a real smoke
  machine.
- **Provenance rule (hard):** the finding is minted with `drill` provenance
  at the witness layer. Every downstream receipt inherits it. `why` on any
  drill receipt renders **DRILL** first.
- **Prefer Option A (stage condition).** Option B (inject synthetic
  finding into NQ's witness layer) is acceptable only as an audited
  fallback, and only if injected findings remain distinguishably-DRILL
  end-to-end. If injection creates testimony indistinguishable from
  observation, that is an *AG-side claim-kind laundering bug in NQ
  itself* — fix lands before the demo, and the fix is itself demo
  material (signed ≠ witnessed).
- **DoD:** real NQ finding emitted with `drill` provenance against a
  staged WAL-bloat condition; the finding id is retrievable as the chain
  origin.

### D0-Provenance — drill propagation through every downstream receipt
- Every receipt downstream of a drill NQ finding (standing, wicket,
  LA, effect) inherits `drill` provenance.
- `why` rendering: DRILL prefix at top of output; same for `--json` output
  (a top-level `drill: true` field).
- **DoD:** end-to-end drill provenance survives the chain; `why` on a
  drill chain renders DRILL on every node walked back to the NQ origin.

### D0c-a — Wicket authorized-admission GateReceipt emission *(CLOSED 2026-06-09)*
- Status: closed. See D0c-a entry under §Slice tracker.

### D0b checkpoint — no synthetic parent ids; `why` walks real NQ → standing → wicket → LA chain
- One verification stamp, not a coding slice. Asserts:
  - real NQ finding (drill provenance)
  - real standing seam receipt citing finding id
  - real wicket admission receipt citing standing id
  - real LA refusal/consume receipt citing admission id
  - `governor why` walks all four links with no synthetic fixture ids
- **DoD:** one CliRunner-driven test that drives the chain through real
  client emissions (no `sink.emit(...)` shortcuts), asserts each parent
  link is a real-emitted id, and `governor why` renders DRILL first.

### D0c-b — cooked-context orchestrator
- Assembles standing → wicket → LA in one call path. Produces
  `CookedCapacityRequest`. Threads `WicketVerdict.receipt_id` into
  `CookedCapacityRequest.admission_receipt_id`. Preserves refusal vs.
  bypass distinction.
- **DoD:** one orchestrator function/class that, given an NQ finding,
  runs the full chain and returns either a refusal receipt id (at
  whichever gate fired) or a `Consumed` verdict + effect-allowed signal.

### D0d — compose harness + six named runs
- Docker compose / Makefile entry. Six named runs as scripts inside the
  harness (per §D2 below). Receipts written to real `GateReceiptSystem`.
  `governor why` works inside container and from host.
- **DoD:** `make demo` runs all six scenarios end-to-end; transcript
  written to `demo/out/transcript.md`.

## §3b. Actuation & LLM placement (pinned 2026-06-09; constrains D0d/D1/D2/D3, do not implement separately)

> Pinned per operator: *"don't let this delay us, but I mean, we're
> going to have to put a pin in this before we call it 'complete'."*
> §3b is a constraint that binds D0d, D1, D2, D3 when they fire — not
> an independent slice. Land it verbatim now so the constraint is
> visible from every downstream slice's prompt.

**Actuator:** a deterministic drill runner, nightshift-owned (one entry point:
`nightshift watchbill run wal-bloat-review --drill --scenario=<run>`). It stages
or selects the finding, injects scenario controls (expired standing, denied
basis, exhausted budget, replayed spend), calls the real gates, writes receipts,
renders the transcript. Game-day controller, not an agent: it makes no
discretionary claims. **Jurisdictional clarity:** nightshift owns workflows;
governor owns gates; the drill is a workflow. Two entry points would mint
ownership ambiguity — one entry point only.

**LLM placement:** late and narrow — a bounded proposal generator invoked only
after standing + admission + capacity have all passed. Input: the finding +
admitted context bundle. Output: a diagnosis/repair proposal packet citing
receipt/evidence ids. The system validates citations and emits the packet;
nothing executes.

**The LLM must not be:**
1. the origin of the finding
2. the standing decider
3. the wicket judge
4. the accountant
5. the validator of its own output
6. the mutator
7. **the drill narrator** (the transcript is a receipt render, deterministic
   from the ledger — never a model summary; narrative laundering at the
   presentation layer would undo every gate beneath it, invisibly)
8. **its own retry authority** (the runner owns re-invocation)

**Per-run invocation (operator-ratified table):**

| Run | LLM invoked? | Why |
|-----|--------------|-----|
| 1. No standing | **No** | downstream call-count zero |
| 2. Standing expired | **No** | terminal lifecycle refusal |
| 3. Wicket denied | **No** | inadmissible basis |
| 4. Wicket gap accounted | **YES** (corrected from Maybe) | The point of `gap` vs `denied` is that gap proceeds. Proposal packet MUST carry the gap: *"produced under OPEN_FINDING_ACCOUNTED, gap receipt id X"*. Consequence-bearing work under acknowledged, receipted epistemic debt. Subtle showpiece — no other demo shows this. |
| 5. Replay / budget | **No on second spend** | spendability refusal; first spend was already accounted |
| 6. All green | **YES** | control group; happy-path proposal packet |
| 7. D3 confabulated receipt | Optional/adversarial (see two-mode below) | tiny courtroom |

**Citation validation is two-sided** (both required):
1. **Existence check** — cited id was minted. Catches fabrication (D3 closing
   beat).
2. **Kind-fit check** — cited receipt's structural kind matches the use.
   Catches laundering-with-valid-hashes: a standing receipt offered where
   evidence is required, a drill receipt cited as live observation.

> **Kind-fit is a GUARD, NOT the parked `ArtifactKind` / `UseKind` enum.**
> Receipts already carry their kind structurally (different tables, different
> shapes). Kind-fit validates against that existing structural distinction.
> **Do not generalize this into typed kind enums.** Anti-smuggling tripwire.
> See `memory/feedback_kind_fit_is_guard_not_enum.md`.

**Retry economics (decided now, demoed in D2/D3):**
- One LLM invocation per capacity consumption.
- Failed citation validation → refusal receipt (closed kind:
  `dangling_receipt_reference` for existence-fail; same kind also covers
  kind-fit fail in MVP — operator may sharpen at S4-lite reopen).
- Re-attempt requires new spend. No free retries.
- **Demo beat:** the confabulated citation consumed real budget and bought a
  refusal. Failure is accounted, not free. No agent framework currently
  demonstrates this.

**D3 staging honesty — two modes, both shipped:**
- *Deterministic control:* runner injects a known-bogus citation into an
  otherwise valid packet, receipted as an *injected control*. Proves the
  validator fires reliably, every demo. Reproducible.
- *Live mode:* proposal step run with an impoverished evidence bundle +
  citation-required schema. Confabulation emerges under pressure or it
  doesn't — report honestly either way. **Never prompt the model to
  fabricate:** staged testimony would be the founding crime inside the
  demo (the same shape D0-Bridge was built to refuse).
- *Fixture rule:* the first naturally occurring confabulation in normal
  operation is preserved as a replayable case file with full receipts. Don't
  stage the crime; keep the evidence.

**Doctrine survives intact:**
> *The model may propose. It may not mint standing, admit itself, spend
> twice, or cite what was never witnessed.*

Every clause now has a call-count assertion and a ledger entry behind it.

## §3c. D0f-docs — sprint closure documentation (pinned 2026-06-10; fires immediately after D0e closes)

> Pinned per operator: *"After D0e, documentation is not cleanup. It is
> the witness stand. The docs should not explain 'how cool the system
> is.' They should make the demo impossible to misdescribe."*

**Goal:** document the compelling MVP so a stranger can understand,
run, and audit the demo without the operator narrating it live.

**Discipline (same as code):**
- No aspirational claims.
- Every claim points to a command, receipt, test, or file.
- No "AI agent decided" language.
- No "the system prevents hallucination" slop.
- Doctrine sentence belongs near the top: *"The model may propose; it
  may not mint standing, admit itself, spend twice, or cite what was
  never witnessed."*
- README-level barb (verbatim from operator): *"This demo is a drill.
  The condition is staged; the observation path is not. The system
  discloses that distinction in the receipt chain."* — followed by
  *"Ask the receipt."*

**Required docs (closed list, do not expand):**

1. `docs/demo/standing-before-spendability.md` — poster sentence,
   one-command demo, six-runs table, expected outcomes, what
   refusal-as-product means, what the happy path proves and does not
   prove.
2. `docs/demo/wal-bloat-drill-transcript.md` — normalized transcript
   from D0e, six ticket outputs, D3 closing beat, sample `governor why
   <receipt-id>` excerpts.
3. `docs/architecture/claim-custody-spine.md` — NQ observation →
   `origin_mode=drill`, standing, wicket, LA grant/consume, proposal
   validator, receipt chain / parent linkage, where the LLM enters and
   what it is forbidden to do.
4. `docs/architecture/origin-mode.md` — `origin_source` vs `origin_mode`,
   observed / drill / replay / synthetic, why D0-Bridge existed, why
   AG-side fake provenance is laundering.
5. `docs/reference/refusal-and-outcome-vocabulary.md` — closed refusal
   kinds, bypass kind, positive receipt markers, outcome classes,
   accounted-gap semantics, BA3 bypass-as-debt rendering.
6. `docs/reference/drill-scenarios.md` — the six scenarios + confabulated
   citation mode.
7. `docs/notes/sprint-receipt.md` — what landed, test counts, repos
   touched, what was explicitly not built, v2 scheduled-drill note.

**Acceptance criteria (operator-ratified, verbatim):**
1. A new reader can run the demo from one command.
2. A new reader can explain each of the six outcomes.
3. A new reader can locate the final receipt id for each run.
4. A new reader can run `governor why <receipt-id>` and understand the output.
5. The D3 confabulated citation beat is documented as deterministic-control, not prompted fabrication.
6. The LLM placement constraint is explicit.
7. DRILL provenance is explained before any transcript.
8. BA3 bypass is documented as debt/bypass, never denial.
9. v2 scheduled drill is captured but clearly out of MVP scope.
10. Docs do not claim mutation/repair execution; proposal packet only.

**Cadence:** tier 2 (descriptive copy — one careful review pass each).
The doctrine surfaces inside the docs (refusal vocabulary, outcome
vocabulary, LLM placement table) are tier 3 but already ratified —
documentation copies the ratified text verbatim.

### D0e — show surface (ticket display + harness assertions)
- Ticket-style receipt display (deadpan operational menace, not
  wizard-themed). DRILL prefix on every receipt line. Bypass kind
  (`BA3_BYPASSED_FOR_MVP`) rendered as bypass/debt with pointer to
  post-MVP debt file, **never** as refusal/denial.
- Harness assertions: no BA3 denial fires during the spine runs; if any
  of `RunBudgetLedger`/`ExecutionBudget`/`ExplorationBudget`/routing
  `Budget` denies during a run, the demo is invalid.
- **DoD:** transcript renders ticket-shaped, DRILL-prefixed, with bypass
  rendered as bypass; `LA_ONLY` startup banner; full harness assertions
  green on the all-six-runs script.

### D0 — demo harness (original framing) *(SUPERSEDED)*

The original D0 — `docker compose up` + `make demo` + ticket display —
is preserved as historical context but superseded by the origin-custody
slicing above. Its content is now distributed across D0d (compose + runs)
and D0e (show surface); D0-Origin and D0-Provenance are the conceptual
inversions that the original framing missed.

The original framing (below) is retained for diff legibility:

#### Original D0 — demo harness (the show surface)

The MVP needs a *show surface*, not just a morally upright call graph.
Two-layer split:

```text
docker compose up      # environment comes alive
make demo              # six-run gauntlet with receipts
make story             # pretty transcript / HTML / TUI
```

**Compose shape (boring on purpose):**

```text
services:
  nq:                  # emits/replays finding fixture
  standing:            # grants/refuses standing receipts
  wicket:              # admission verdicts
  linear-accountant:   # capacity reserve/consume
  governor:            # orchestrates run
  nightshift:          # assembles workload/proposal packet
  demo-ui:             # optional, reads receipts + renders story
```

Seeded SQLite volumes / mounted fixtures. No live dependency hell. The
point is the receipt chain, not summoning Beelzebub over mDNS.

**Concrete incident (deadpan operational menace, not wizard-themed):**

```text
AG MVP Demo: Refusal Is the Product

Incident: WAL bloat review
Goal:     produce one bounded repair proposal
Rule:     no standing, no admission, no budget, no effect
```

**Six named runs** (D2 scenario scripts live inside this harness):

```text
1_no_standing
2_standing_expired
3_wicket_denied
4_gap_accounted
5_replay_blocked
6_all_green
```

**Receipt ids printed like tickets** (deadpan, scannable):

```text
✖ standing_required       ag_rcpt_01H...
✖ standing_expired        ag_rcpt_01H...
✖ admission_denied        ag_rcpt_01H...
⚠ gap_accounted           ag_rcpt_01H...
✖ already_consumed        ag_rcpt_01H...
✓ proposal_packet_landed  ag_rcpt_01H...
```

**Hard requirement (LA_ONLY enforcement at harness level):**

Compose startup prints:

```text
SpendabilityAuthority: LA_ONLY
Bypassed internal AG budget guards:
  - RunBudgetLedger        receipt: bypass_...
  - ExecutionBudget        receipt: bypass_...
  - ExplorationBudget      receipt: bypass_...
  - RoutingBudget          receipt: bypass_...
```

Harness assertion: if any of the four BA3 surfaces emits a denial
during *any* of the six runs, the demo fails. This is the same
contract from C0-resolved enforced at the harness boundary.

**DoD:**
- `docker compose up` starts all required local services.
- Seeded fixture produces wal-bloat finding.
- Demo runner executes the six runs (D2 scripts).
- Receipts written to mounted `demo/out/`.
- `governor why <receipt-id>` works both inside container and from host.
- Generated artifact at `demo/out/transcript.md` (optionally
  `demo/out/index.html`).
- Harness asserts `LA_ONLY` and *fails* if any internal BA3 guard fires.

**Cadence:** autopilot, but it's the largest single slice in the
campaign by code volume (compose file, fixtures, runner script,
transcript renderer, assertion harness).

### D1 — wal-bloat watchbill, fully gated
- One real workload: NQ wal-bloat finding (live instance or replayed fixture) →
  nightshift assembles context → standing question → grant → wicket admission →
  LA capacity → bounded diagnosis → repair *proposal packet* (no mutation, per
  nightshift doctrine) → receipts throughout.
- **DoD:** `nightshift watchbill run wal-bloat-review` completes with the full
  receipt chain queryable via S5.

### D2 — the gauntlet (four refusals + one accounted gap + one effect)
Naming hygiene (per 2026-06-09 review): the poster groups outcomes into
*terminal refusals*, *accounted gaps*, *happy path* — calling the gap
run a "refusal" muddies the punchline when it proceeds. Demo poster:

> **Six runs: four refusals, one accounted gap, one effect — one command
> explains all six.**

D2 lives inside the D0 harness. Six named runs, scripted, against the
WAL-bloat workload:

1. `1_no_standing` → `standing_required` (terminal); downstream call count zero.
2. `2_standing_expired` → `standing_expired` (terminal); standing's native
   expire state, no new freshness machinery.
3. `3_wicket_denied` → `admission_denied` (terminal); structurally inadmissible basis.
4. `4_gap_accounted` → `admission_gap_accounted` (*accounted gap, not refusal*);
   proceeds with the gap receipted (refusal-discipline is not maximal
   blocking — doctrine-rich, cheap).
5. `5_replay_blocked` → `already_consumed` (terminal) on second spend of a
   valid warrant. (Pure budget-exhausted variant = `capacity_refused`; the
   replay variant is the demo case because it dramatizes linearity.)
6. `6_all_green` → proposal packet lands; effect receipted.

- **DoD:** one script, one transcript, every run ends in a receipt id that S5
  can explain. Harness asserts no BA3 denial fires; failure = invalid run.

### D3 — the confabulated receipt (the story that travels)
- Agent cites a `standing_receipt_id` / evidence id that does not exist →
  refusal names the dangling reference. Content-addressed ids make this a
  lookup-miss, ~trivial to implement, and it is the live re-enactment of the
  manufactured-receipts incident: *the model can claim anything; it cannot cite
  what was never minted.*
- This is the demo's closing beat and the essay's opening anecdote. Highest
  narrative value per line of code in the entire plan.

---

## 4. Cadence map (the autopilot answer)

HIGH (chatty-in-pipe + codex-exec, sequential): **C0 classification**
(complete), **S4-lite naming pass**. Two checkpoints, both
vocabulary/basis boundaries. Codex caught a critical BA3 miss at C0
that chatty-in-pipe would have shipped; default to codex for HIGH
basis questions.

AUTOPILOT (ultraplan-able, parallelizable after C0): S1, S2, S3, S5,
D0, D1, D2, D3. Each has a closed DoD, call-count teeth, and touches
no parked vocabulary. D0 is the largest single autopilot slice by
code volume (harness + compose + scripts).

Rough shape: ~80% of slices autopilot by count (after D0 is folded in),
but the two HIGH checkpoints are load-bearing and must not be batched
into the autopilot stream.

## 5. Cut list (explicitly out of MVP — refuse smuggling)

ArtifactKind/UseKind typing · Z3 · grep-sentinel infra · WLP transport / TCP-UDP
modes (design note only) · cross-tool receipt schema unification (v2) · Cantrip
adapter · continuity premise-revocation wiring (continuity may receive receipts
as observations; `rely` integration is post-MVP) · generated seam inventory /
linter (separate track, already scheduled) · Lean in the runtime path (merge
gate only) · any new kernel work (jurisdiction: outOfScope).

## 6. Sizing / sequence

- **Minimal compelling** (if time pressure bites): C0 → S2 → S3 → D0
  (harness, scoped to runs 1/5/6) → D2 runs 1/5/6 → D3. That alone
  demos refusal-as-product + retry-kill + confabulation, with a
  one-command launch.
- **Full compelling:** + S1, S4-lite, S5, D0 (full harness), D1, D2
  complete. S5 is the highest value-per-effort addition — `why` is
  the thing people remember.
- **Order of operations** (canonical): C0 (HIGH) → S1‖S2‖S3 (autopilot) →
  S4-lite naming checkpoint (HIGH) → S5‖D0 (autopilot) → D1 → D2 → D3.
  D0 may parallelize with S5; D1/D2/D3 require D0 first.
- **Order of operations** (narrative-first variant, per Chatty 2026-06-09):
  C0 → S2/S3 first → D0 early (minimal harness) → D3 → S1 → S4-lite →
  S5 → D1 → D2 wrapper. Reason: D3 validates the narrative before the
  whole cathedral is wired. If dangling-receipt refusal lands cheaply
  inside a minimal D0, it gives the demo soul immediately. Take this
  path if repo topology doesn't demand S1 first.

---

## Slice tracker (local execution state)

### Slice status table (2026-06-09)

> Inventory, not introspection. Read this instead of guessing where the work is.

| Slice            | Status     | Notes                                                                              |
| ---------------- | ---------- | ---------------------------------------------------------------------------------- |
| C0 Q1            | CLOSED     | LA topologically absent from AG src/                                               |
| C0 Q2            | CLOSED     | BA3 bypass contract ratified; 4 BA3 surfaces enumerated; debt filed                |
| S1 stub          | CLOSED     | standing_client + wicket_client SPEC-honoring stubs, 13 tests                      |
| S2 stub          | CLOSED     | linear_accountant_client.request_capacity, pre-call refusal teeth                  |
| S3 stub          | CLOSED     | linear_accountant_client.consume, replay-kill teeth (effect_count=1)               |
| S4-lite          | CLOSED     | 11 refusal kinds + 1 bypass kind sealed; GateReceiptSystem ratified; micro-freeze  |
| S5 (chain joins) | CLOSED     | `governor why <id>` walks GateReceipt chains; 21 tests + 4 negatives               |
| **S5 (NQ-origin)** | **CLOSED 2026-06-10 by D0-Origin** | Amended goal: `why` reaches NQ finding / renders absence properly. D0-Origin proves the real bridge end-to-end and the right absence semantics. Formally closed (operator: "ghost dependencies become haunted furniture"). |
| D0 (harness)     | SUPERSEDED | Superseded by origin-custody slicing; content absorbed into D0d + D0e              |
| Provenance audit | CLOSED     | 2026-06-09 codex pass; **recommendation D — NQ custody gap**; see audit witness    |
| ~~NQ custody gap (origin discriminator)~~ | ABSORBED   | Absorbed into D0-Bridge below 2026-06-09 (nq-claude stood down, this Claude crosses repos per new custody-seam rule)            |
| D0-Origin        | **CLOSED 2026-06-10** | Real WAL-bloat staging (Night Shift `wal_bloat_stager.rs`) + authentic NQ observation via production `sqlite_health::collect` → `publish_batch` → `detect::run_all` → `update_warning_state_with_origin_mode` → `export_findings` pipeline (new `nq-monitor drill wal-bloat` subcommand). Native detector path now mints `origin_mode=drill` via new symmetric plumbing in `publish.rs`. AG's `drill_runner.py` consumes genuine FindingSnapshot JSON via `--finding-json`. 14 end-to-end acceptance tests (`tests/test_d0_origin_genuine_nq_finding.py`). All 8 acceptance criteria pass; transcript determinism preserved via normalization of timestamps/paths/finding_ids/receipt-id prefixes. |
| D0-Provenance    | **STAMPED 2026-06-10 by D0-Origin** | Drill propagation already wired by D0-Bridge through `evidence_bundle["origin_mode"]`; D0-Origin exercised it end-to-end with a genuine NQ finding. `governor why` renders DRILL first at every chain node. Acceptance test `test_acceptance_7_why_renders_drill_first` is the witness. |
| D0a              | CLOSED     | Refusal-time GateReceipt emission via injected ReceiptSink                         |
| D0c-a            | CLOSED     | Wicket authorized-admission emission; closes synthesized-link debt                 |
| D0c-b            | CLOSED     | Cooked-context orchestrator + closed origin-mode set {cli/stub}; 22 new tests, 128 pass |
| **D0-Bridge**    | **CLOSED**    | NQ migration 057 (`origin_mode` sibling column, closed CHECK `{observed,drill,replay,synthetic}`); AG widens `CLOSED_ORIGIN_MODES = AG_INTERNAL ∪ NQ_ORIGIN_MODES`; `governor why` renders DRILL/REPLAY/SYNTHETIC prefix; load-bearing end-to-end test drives NQ-shaped FindingSnapshot → real chain → `governor why` rendering. First cross-repo slice under graduated rule. |
| **D0d-a**        | **CLOSED with surfaced gap** | Night Shift entry point: `nightshift watchbill run wal-bloat-review --drill --scenario=all-green` shells `python3 -m governor.drill_runner`; deterministic NQ-shaped fixture; in-process `walk_chain`+`render_text` embeds DRILL prefix; 9 AG + 4 scheduler tests; byte-identical determinism proven. **Surfaced gap:** only the wicket admission receipt emits today (per D0c-a); standing.verify success, LA.request_capacity granted, LA.consume consumed all skip emission. Runner correctly renders `(no-receipt-emitted)` for the three missing links rather than synthesizing fakes. Architecture decision recorded: Night Shift (Rust) shells subprocess to AG (Python) via the `-m` module entry. |
| **D0d-b**        | **CLOSED 2026-06-10** | Happy-path GateReceipt emission landed on `standing_client.verify` success (`_emit_verified_receipt`, side-channel `_last_verified_receipt_id`), `linear_accountant_client.request_capacity` Granted (`_emit_grant_receipt`), `linear_accountant_client.consume` Consumed (`_emit_consume_receipt`). Parallel-to-D0c-a addition; no GateReceipt envelope change; no widening of `CLOSED_REFUSAL_KINDS`; no typed positive-verdict enum (descriptive markers `verified_standing` / `la_outcome` only). `finding_id` plumbed: orchestrator → `WicketClient.check` → `StandingClient.verify`. Four-link chain `finding → standing → admission → granted → consumed` walks end-to-end via `governor why`; transcript renders four real chain links with no `(no-receipt-emitted)` placeholders. 130 affected tests pass (88 directly affected + 42 adjacent). |
| **D0d-1**        | **CLOSED 2026-06-10** | Six-scenario gauntlet wired end-to-end. Night Shift CLI widened to closed set `{no-standing, standing-expired, wicket-denied, wicket-gap-accounted, replay-budget, all-green}` (alias `already-consumed` for replay-budget). AG-side scenario factory dispatch in `drill_runner.py`: per-scenario verifier + injected callables + `_EffectCounter` for replay-kill + `_classify_chain_outcome` closed-vocab mapping. **No detector zoo:** FindingSnapshot byte-identical across all six scenarios (asserted by dedicated test); only gate state varies. Run 4 proposal packet gains `gap_receipt_id` + `produced_under_gap=true` (deterministic stub, no LLM). Run 5 replay: second consume returns AlreadyConsumed → `already_consumed` refusal; effect_count remains 1. Honest-absence markers in transcript (`not invoked — refused at <gate>`). 31 new AG tests + 3 new Night Shift tests; 158 total slice tests pass. No HIGH escalation, no schema change, no vocabulary movement. |
| D0b checkpoint   | **STAMPED 2026-06-10 by D0-Origin** | D0-Origin's end-to-end test `test_d0_origin_genuine_nq_finding.py` drives a real chain from genuine NQ FindingSnapshot → standing → wicket → LA → `governor why` with DRILL prefix. No synthetic parent ids — the standing receipt cites NQ's actual `finding_key` and `why` walks four real GateReceipts back to the (correctly) missing NQ origin. |
| ~~D0c-b (duplicate row)~~ | SUPERSEDED | Duplicate of the CLOSED D0c-b row above; preserved for diff legibility. |
| D0d              | **ABSORBED by D0d-a + D0d-b + D0d-1 2026-06-10** | Original "compose harness + six named runs" framing absorbed into the three landed sub-slices: D0d-a (runner skeleton), D0d-b (happy-path emissions), D0d-1 (six-scenario gauntlet). No remaining engineering work under this row. |
| D0e              | **CLOSED 2026-06-10** | Show surface complete. Phase 1 codex vocabulary review applied four revisions verbatim (header "Refusal Is a Product Surface", incident "WAL bloat review — DRILL", run 4 "↷ accounted_gap", run 6 "effect" no ✓, D3 "validator_refused (dangling_receipt_reference)" + matching harness assertion, DRILL paragraph leading with "origin_mode=drill minted at NQ"). Phase 2 landed `src/governor/drill_poster.py` (~600 LOC poster + assertion engine + `python3 -m` entry) + `nightshift watchbill demo wal-bloat-review --drill` single entry point that shells AG; 14 new poster tests + 3 Night Shift smoke tests; 202 total slice tests pass; cross-tmp posters byte-identical without normalization (content-addressed ids on stable inputs). BA3 bypass renders as `bypass_ag_rcpt_<not_minted>` honest absence (option a, operator default). All 10 acceptance criteria pass. No HIGH escalation. |
| **D0f-docs**     | **CLOSED 2026-06-10** | Sprint closure documentation. Seven docs landed under `docs/{demo,architecture,reference,notes}`: standing-before-spendability.md, wal-bloat-drill-transcript.md, claim-custody-spine.md, origin-mode.md, refusal-and-outcome-vocabulary.md, drill-scenarios.md, sprint-receipt.md. All 10 operator acceptance criteria met using verbatim ratified vocabulary copied from drill_runner / drill_poster / linear_accountant_client / cooked_context_orchestrator. No source/test changes; 202 slice tests still pass. Tier-2 cadence held (one careful review pass per doc; no doctrine re-litigation). |
| D1               | **ABSORBED by D0-Origin + D0d-1 2026-06-10** | Same command path as the gauntlet; D0d-1 confirmed no distinct transcript needed. D1 is now documentation/demo labeling, not a separate engineering slice. |
| D2               | **ABSORBED by D0d-1 2026-06-10** | Six scenarios landed as the closed scenario set in D0d-1; "scripts inside D0d" framing is now `--scenario=<value>` dispatch.                            |
| **D3**           | **CLOSED 2026-06-10** | Confabulated-receipt closing beat. Night Shift CLI gains `--confabulate-citation=<role>` (closed roles include `standing`); confabulation requires `all-green` scenario (D0d-1's six-set stays closed; rejection at construction for non-all-green). AG-side validator in `drill_runner.py` runs after the chain completes through consume: existence-check + kind-fit guard against receipts' existing structural attributes (NOT a typed enum — `feedback_kind_fit_is_guard_not_enum` discipline held). Failed validation emits real refusal receipt via existing GateReceiptSystem path. **Gate name choice (tier 3):** `proposal_validator_seam` (mirrors the established `*_seam` convention). Refusal kind: `dangling_receipt_reference` (reused from closed S4-lite set, no widening). Parent linkage cites the consume receipt id so chain walks back. `effect_count` remains 1 (the consume happened — real budget was spent; the demo beat). `governor why <refusal_id>` walks the chain back AND renders the bogus citation as absence per existing S5 negative-test path. 13 D3 tests + 175 prior slice tests = 188 total pass. No HIGH escalation; no schema change; no vocabulary movement. |
| v2 (cron drill)  | CAPTURED   | Scheduled gauntlet drill as recurring negative control. NOT in scope today.        |

### Smallest next coding slice (state as of 2026-06-09 post-audit)

> **The provenance-field audit closed with recommendation D — NQ custody
> gap.** No AG-side coding slice can authentically advance D0-Origin until
> NQ ratifies an origin-mode discriminator distinguishing drilled /
> synthetic / replayed findings from observed ones. Full obligation
> at `working/nq-custody-gap-origin-discriminator.md`.
>
> Two operator paths from here:
>
> **Path 1 — pause the NQ-origin amendment, return to CLI-origin demo
> spine.** D0c-b (cooked-context orchestrator) is NOT gated by the NQ
> gap; D0d/D0e can run against stubs. Demo lands without the cinematic
> NQ-fired opening; D0-Origin / D0-Provenance / D1 sit OPEN-GATED.
> Acceptable per the campaign's "minimal compelling" framing.
>
> **Path 2 — hand the NQ-side obligation across the fence.** Operator
> dispatches NQ-side ratification work in a separate session. AG-side
> work continues on D0c-b in parallel. When NQ ships the discriminator,
> AG plumbs it through evidence bundles + adds a DRILL-first branch to
> `why.py`, and D0-Origin can land authentically.
>
> Either path is doctrinally clean. Inventing an AG-side discriminator
> NQ doesn't mint is NOT a path — that's laundering one level deeper.

### Per-slice history (chronological)

- **C0 Q1 — observation→LA path?** Complete 2026-06-09. Classification
  **A** (negative grounding; LA structurally absent from AG). See
  `working/witness-2026-06-09-c0-standing-before-spendability.md`.
- **C0 Q2 — budget-authority classification (BA0/BA1/BA2/BA3).** Complete
  2026-06-09 via codex adversarial review. **Classification: MVP-BLOCK
  (yes).** Four BA3 surfaces found, including one the soft witness
  missed entirely:
  - ExecutionBudget (BA3) — gates autonomous step
  - ExplorationBudget (BA3) — gates exploration mode
  - routing Budget (BA3) — gates model choice, hard-refusal incomplete
  - **`RunBudgetLedger` in runtime/supervisor.py (BA3)** ⚠️ — gates
    actual agent tool calls (writes / network) via adapter `deny`.
    The witness missed this entirely; codex caught it. This is the
    unambiguous BA3 that breaks the demo's invariant.
  See witness exit-ticket Q2-revised for full classification table.
- **C0 — RESOLVED (bypass-for-demo contract, operator-ratified
  2026-06-09).** The MVP harness runs with
  `SpendabilityAuthority = LA_ONLY`; every bypassed AG-internal budget
  authority emits a visible bypass receipt; **any AG-internal budget
  denial during a spine run is a test failure** because refusal
  occurred at the wrong authority. Critical distinctions:
    - The bypass is allowed because it is **explicitly noncanonical
      and receipted**.
    - Not allowed to pretend BA3s are harmless.
    - Not allowed to downgrade them by prose.
    - Not allowed to coexist silently with LA.
  Hard-short-to-LA filed as post-MVP debt at
  `working/post-mvp-debt-ba3-hardshort-to-la.md`.
- **S1, S2, S3** — ran 2026-06-09 in parallel autopilot. First pass:
  all three topological absence. Operator lifted preflight narrowly
  for SPEC-honoring stubs (loud labels, injectable downstreams, no
  transport abstraction, no semantic invention). Second pass: stubs
  landed.
    - **S1 — landed:** `src/governor/standing_client.py`,
      `src/governor/wicket_client.py`, `tests/test_standing_client.py`
      (7 tests), `tests/test_wicket_client.py` (6 tests). CookedContext
      mirrors wicket SPEC §4 verbatim. Pre-call refusal teeth verified
      (zero wicket-check invocations on missing/empty/dangling
      standing_receipt_id). No HIGH escalation.
    - **S2 — landed:** `src/governor/linear_accountant_client.py`
      `request_capacity`, with pre-call refusal on missing/dangling
      `admission_receipt_id`. Tests in
      `tests/test_linear_accountant_client.py` (14 tests covering S2
      and S3). LA Denied → `capacity_refused`.
    - **S3 — landed:** same file, `consume` method. Replay-kill teeth
      verified (LA invoked twice, effect counter exactly 1).
      AlreadyConsumed → `already_consumed`.
    - **HIGH escalation (S2/S3 → S4-lite):** ConsumptionDecision
      variants `Expired`, `Revoked`, `UnknownToken`, `ScopeMismatch`
      have NO SPEC-defined AG-side mapping. Stub provisionally routes
      all four → `capacity_refused` to preserve no-crash + closed-set
      invariants. Operator ratification at S4-lite vocabulary
      checkpoint required. Candidate refinements: `UnknownToken` →
      `dangling_receipt_reference`; `Expired` may want a distinct kind
      or stay under capacity_refused; `Revoked` and `ScopeMismatch`
      likely stay under capacity_refused.
- **S4-lite — closed 2026-06-09** via manual operator pass with codex
  adversarial nomenclature review. Three close items all landed:
    - LA-variant → refusal-kind mapping ratified: four new distinct
      kinds (`token_expired`, `token_revoked`, `unknown_token`,
      `scope_mismatch`) replace the provisional `capacity_refused`
      collapse. Applied to `linear_accountant_client.py` and
      `test_linear_accountant_client.py`; all 27 client tests pass.
    - Closed refusal-kind set finalized: 11 refusal kinds + 1 bypass
      kind (`BA3_BYPASSED_FOR_MVP`, emitted by runtime supervisor /
      D0 harness, not by clients). See S4-lite section above.
    - Receipt storage path ratified: `GateReceiptSystem`
      (`src/governor/gate_receipt.py`) — ReceiptStore JSONL +
      EvidenceStore content-addressed blobs. Already hash-chained
      and queryable by `receipt_id`.
- **S5 — landed 2026-06-09** as autopilot per operator sequence
  ("accounting before stage show"). `governor why <receipt-id>
  [--json] [--max-depth N]` joins ReceiptStore → EvidenceStore via
  the existing `GateReceiptSystem`. New module
  `src/governor/why.py` (chain walker + closed-vocab classifier +
  text/JSON renderers + BA3 debt pointer); CLI wired in `cli.py`;
  21 tests at `tests/test_why_command.py`, all pass; 48 tests pass
  across the four slice modules (S1+S2+S3 clients + S5).
    - All four operator-required negatives covered: unknown receipt
      id, missing evidence blob, malformed kind, stale vocabulary
      (each renders the absence, exits nonzero, no traceback).
    - Bypass rendering verified: `BA3_BYPASSED_FOR_MVP` renders with
      `BYPASS` prefix + pointer to
      `working/post-mvp-debt-ba3-hardshort-to-la.md`, visibly distinct
      from any refusal kind.
    - Chain walker handles dangling parent + cycle detection +
      max_depth bound.
    - No HIGH escalation; micro-freeze rule respected (no renames
      surfaced, no vocabulary additions).
- **Micro-freeze active** (operator-ratified post-S5): receipt
  explainability substrate is ratified. No further vocabulary changes
  before D0 unless a real join ambiguity forces reopen.
- **D0c-a — landed 2026-06-09** (autopilot, hard-fenced). Wicket
  authorized-admission emits real GateReceipt via `_emit_admission_receipt`
  (`verdict="pass"`, `gate="wicket_seam"`, no GateReceiptSystem schema
  change). WicketVerdict carries `receipt_id` + `parent_receipt_id`
  (cites standing). 106 tests pass (102 baseline + 4 new). Load-bearing
  invariant proven: `governor why` walks LA-refusal → real
  wicket-emitted admission → standing seam through actually-emitted
  receipts, no synthetic ids. **The synthesized-link debt D0a flagged
  is closed.**
- **D0a — landed 2026-06-09** as autopilot under operator hard fence
  (refusal-time emission only; harness/orchestrator/scenarios reserved
  for D0b/c/d/e). Standing/wicket/LA refusal paths now emit real
  GateReceipts via injected ReceiptSink at refusal time. Every
  emitted receipt carries `receipt_id`, `refusal_kind` from the
  closed S4-lite set, parent linkage in `evidence_bundle.parent_receipt_ids`
  (matches the `why._parent_ids` contract — no GateReceipt schema
  change), and a runtime closed-vocab assertion. The load-bearing
  test drives a real WicketClient/StandingClient refusal chain
  end-to-end and asserts `governor why <receipt-id>` walks
  wicket_seam → standing_seam through actually-emitted receipts (not
  synthetic).
    - 24 new D0a tests; 72 pass across the four slice files; 102 pass
      including cli_group guardrails.
    - Closing patch: registered `why` in cli_group `CATEGORIES`
      (Operator) and bumped `FROZEN_CURATED_COMMANDS` from 21→22 with
      provenance comment. S5 had left this guardrail tripped; cleaned
      up at the S5→D0a transition.
    - No HIGH escalation; no semantic invention; vocabulary frozen.
- **Synthesized-link debt CLOSED 2026-06-09** by D0c-a (above).
- **D0 reframed as origin-custody slice 2026-06-09** (see §3
  amendment). New sub-slices:
    - D0-Origin (staged WAL-bloat + authentic NQ observation +
      `drill` provenance minted) — OPEN
    - D0-Provenance (drill propagation through every downstream
      receipt; `why` renders DRILL first) — OPEN
    - D0c-a (wicket authorized admission) — CLOSED
    - D0b checkpoint (no synthetic parent ids; `why` walks real
      NQ→standing→wicket→LA chain) — OPEN
    - D0c-b (cooked-context orchestrator) — OPEN
    - D0d (compose harness + six named runs) — OPEN
    - D0e (show surface — ticket display + harness assertions +
      DRILL prefix + BA3 bypass as debt) — OPEN
- **D1, D2, D3** — OPEN. Now run from NQ-origin, not CLI-origin.
- **v2 capture (not scope today, do not build):** the gauntlet as a
  *scheduled* drill. A gate you have never seen refuse is an
  unvalidated gate; refusal paths rot like untested backup restores.
  Cron the six-run drill weekly; "when did this gate last refuse,
  receipt attached" becomes a question no incumbent can answer.
  Cron, not new machinery.
  Precondition still applies to all spine runs when they land:
    - run with `SpendabilityAuthority = LA_ONLY`
    - emit `BA3_BYPASSED_FOR_MVP` receipt per bypassed BA3 surface
    - assert no AG-internal budget denial fires during spine run
      (`RunBudgetLedger`, `ExecutionBudget`, `ExplorationBudget`,
      routing `Budget`) — any such denial fails the demo harness.
  `BA3_BYPASSED_FOR_MVP` enters S4-lite's closed-vocabulary set as a
  bypass receipt kind (not a refusal kind; queryable via `why`).
- **D0 — demo harness** added 2026-06-09 as the show surface
  (docker-compose + `make demo` + `make story`, with LA_ONLY assertion
  at the harness boundary). D2 scenario scripts live inside D0.
