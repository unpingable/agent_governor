# Campaign: Constellation Tick/Tock Builder Ratchet

Opened: 2026-06-10
Operator authority: James (operator fiat is sufficient source authority for Tick 1; recorded as such — that fact itself is gap-list evidence).
Status: OPEN — Tick 1 SHIPPED and Tock 1 SHIPPED 2026-06-10. Next tick may open on operator-curated cargo.

## Question

Where does the current Maude/Fable supervised build pipeline leak authority, custody, or
safety when the work is genuinely **delegated** (operator not continuously present)?
Not "is the pipeline pleasant for pair-programming" — the audience is delegated work:
unattended runs, promotion boundaries, consequence boundaries, after-the-fact audit.

## Cadence rule

- **Tick** = run one real low-blast backlog item through the pipeline as-is. Tick ships
  or rejects real cargo, and records transcript, receipts, tests, and a gap list.
- **Tock** = add **exactly one** pipeline capability, cited to a specific gap a tick
  observed. No speculative pipeline primitives. No BuildPetition design yet.

## The builder loop (two-verdict ratchet)

Adopted 2026-06-10 after Tick/Tock 1. Simple tick/tock is good ratchet discipline but
collapses two different validations — *did the cargo work?* and *did the dogfood
pipeline behave?* Tick 1 proved they are distinct surfaces: the NQ patch shipped green
while the control plane was failing open. Cargo success, dogfood defect.

> We split the verdict because "the patch worked" must not launder "the process was
> unsafe."

The standard loop, every run:

0. **Groom / rake** — a lightweight pre-tick readiness pass (below). Selects cargo and
   surfaces dep hazards *before* execution.
1. **Plan** the cargo with a judgment model.
2. **Execute** the cargo through the current dogfood.
3. **Validate the dogfood:** did control, audit, custody, and spend behave?
4. **Validate the cargo:** did the patch/doc/procedure actually work?
5. **Accept/reject;** choose the next tock from dogfood gaps; choose whether to
   continue.

### Step 0: the pre-tick rake pass

Added 2026-06-10. Tick 1 proved cargo can move, but backlog *selection* was
under-groomed — the dependency map was implicit, so the fail-open Maude gate only
surfaced after running cargo. The rake makes a handful of dependency hazards knowable
*before* execution. A seven-field table, nothing more:

1. **Candidate cargo list** — a *handful* of plausible items. NOT the whole backlog.
2. **Dependency scan** — what does each item depend on / block? Any implicit deps?
3. **Blast-radius rating** — live stakes if it goes wrong.
4. **Revert path** — exactly how to undo.
5. **Test command** — the mechanical cargo-verdict check.
6. **Known blockers** — what's unconfirmed or in the way.
7. **Why this tick, why now** — the selection rationale.

Guardrails (load-bearing):
- **10–20 minutes, a table not a novella.** If it grows appendices, hit it with a
  shovel. If you find yourself enumerating all N backlog docs, you've already failed —
  rate a handful of *plausible* candidates, not the pile. This is the antidote to
  per-project backlog pain, not an instance of it.
- **Grooming selects cargo. It does not authorize speculative infrastructure.** A
  candidate that needs new infra to exist is a forcing-case question, not a tick.

Two nested layers:

- **Outer loop — campaign ratchet** (`PLAN → RUN → ACCEPT → NEXT`): decides what the
  system should become next.
- **Inner loop — dogfood trial** (`execution → validation → gap list → tock
  candidate`): decides whether the current toolchain actually supported the work.

**Ordering invariant: step 3 before step 4.** A passing patch hides a broken process.
Tick 1 would have read as pure success if the only question had been "did NQ tests
pass" — the fail-open gate was only visible because the dogfood got its own verdict.

> A tick is not successful merely because the cargo ships. It is successful if it also
> teaches the dogfood what to become next.

(Name breadcrumb: "Epicycles" was considered and rejected — it implies the loop
compensates for a wrong model. This loop separates validation surfaces Tick 1 proved
distinct. "Two-verdict ratchet" is boring enough to survive documentation.)

## Standing objectives

Added 2026-06-10 after Tick/Tock 1 (the first ratchet immediately produced a
resource-allocation lesson: bootstrapping it on Fable nearly ate a 4-hour usage window
on largely mechanical work).

- **Routing rule of thumb:** *Tick with whatever model moves cargo. Tock with the
  cheapest model that can satisfy the cited gap. Escalate to Fable only when the gap is
  conceptual (doctrine/vocabulary seams, laundering review, ratification, synthesis),
  not merely mechanical.* See [[feedback_model_tier_routing]].
- **Downgradeability ratchet goal:** *Task packets should become increasingly executable
  by cheaper/local models. Escalate to Fable only for conceptual seams, ratification, or
  failed weaker-model attempts.* Downgradeability is a maturity signal — the win is
  "better process lets weaker models do more ordinary work," not "better model does more
  magic." Intelligence moves out of the model and into the artifact boundary
  (`docs/reference/task-packet-template.md`).
- **Baby-steps discipline:** packet discipline now; no scheduler, no model taxonomy, no
  orchestration. Ladder-climbing (routing/lanes wiring) is a later ratchet leg, opened
  only after several ticks of recorded suitability evidence.

## Tick deliverables: three verdicts

Restructured 2026-06-10 under the two-verdict ratchet. (Tick 1's report used the older
deliverables 1–6 numbering; it is not retro-edited — mapping: cargo verdict absorbs
1–3, dogfood verdict absorbs 4–5, packet verdict is old deliverable 6 unchanged.)

**Cargo verdict — did the work land?** (validated SECOND, step 4)
- shipped / rejected / partial;
- tests — independently run by the supervising operator, not the executor's testimony
  (NLAI);
- diff summary;
- review/promote/revert record.

**Dogfood verdict — did the pipeline behave?** (validated FIRST, step 3)
- one of: **held / degraded / failed-open / failed-closed / unaudited** — prose
  vocabulary for working docs, NOT a code enum
  ([[feedback_kind_fit_is_guard_not_enum]] fires if anyone is tempted);
- operator interventions (count, and judgment calls vs. mechanical);
- control gaps; audit gaps;
- **next tock candidate, citing its forcing gap by name.**

**Packet verdict — could this have been cheaper?** (the model-suitability block;
feeds the downgradeability ratchet)
- model used (and surface: supervised backend / direct / operator);
- ambiguity encountered (where the packet was underspecified);
- was the task packet sufficient? (yes/no/what was missing);
- **downgrade candidate for next similar work** — could this packet go to Opus /
  Sonnet / local? yes / no / maybe, why, and the specific missing packet detail that
  would make a cheaper model safe.

Worked example (Tick/Tock 1 retro-cast):

| Verdict | Tick 1 |
|---------|--------|
| Cargo | shipped — tests green (independent run), 3-file diff promoted |
| Dogfood | audit **held**, control **failed-open** (GAP-A: 30s hook fail-open) |
| Packet | downgrade candidate **YES** (Sonnet-class; 3 missing packet fields named) |
| → Tock | fail-closed supervisor gate, forcing gap GAP-A — shipped, drill-verified |

## Tick 1 cargo

NQ dashboard masthead + posture legend (`~/git/notquery`, `crates/nq-monitor`).
Supervised Claude Code (Fable) session, cwd=notquery, driven unattended by AG-Claude
through Maude in tmux. Promotion exercised by AG-Claude as acting operator; NQ tree
left uncommitted for James.

## Invariants

1. Tick ships or rejects real cargo — no synthetic demo cargo.
2. Every tool call the supervised agent makes is approved/denied with recorded rationale.
3. Independent verification: AG-Claude runs `cargo test --all --locked` itself; the
   supervised agent's "tests pass" is testimony, not evidence (NLAI).
4. Tock may add exactly one capability, and must cite the forcing gap by name.
5. Gate-bearing code must not self-amend unattended.

## Allowed

- Drive governor daemon + Maude (tmux) + `governor runtime` CLI fallback.
- Approve/deny supervised tool calls; promote/reject workspace changes.
- Write tick artifacts in agent_gov `working/`; keep event JSONLs/receipts under
  `~/git/agent_gov/.tick/tick01-gov/`.

## Forbidden

- BuildPetition or any new pipeline primitive design during a tick.
- git commit / merge / push in notquery or maude. Push default-off everywhere.
- Merge authority of any kind (promote = accept working-tree changes only).
- Fixing pipeline defects mid-tick — record as gaps; fixes are tock candidates.
- Expanding cargo scope into NQ's adjacent scoped proposals
  (DASHBOARD_HEADER_SEVERITY_URGENCY_SPLIT, DASHBOARD_ORDERING_SLICE_PACKET).

## Gap rubric (binding for the tick report)

a. **Source authority** — was anything more than "James said so" attachable to the work item?
b. **Spend metering** — which tool calls should have been budgeted and weren't?
c. **Scope containment** — could the supervisor *express* the file fence, or did it live
   only in the supervising operator's head?
d. **Citation-needing claims** — did the session assert results with receipts or testimony?
e. **Promotion custody** — what did promote actually record? Would it survive audit?
f. **Walk-away safety** — what breaks if the operator never returns (timeouts, orphaned
   sessions, half-applied edits)?
g. **Operator-surface friction** — Maude-specific drivability/visibility gaps.

## Exit states

- **tick-shipped** — cargo promoted, tests green, report filed.
- **tick-rejected** — cargo refused with receipts; still a valid tick.
- **tick-aborted** — pipeline itself broken; the failure report IS the tick output.

## Ledger

| Leg | State | Artifact |
|-----|-------|----------|
| Tick 1 | **tick-shipped** | `working/tick-01-nq-masthead.md` — promoted `prom_0734338a4b27`, 12 gaps (A–L), NQ tree uncommitted for James. Deliverable 6 (model-suitability) retro-filled: downgrade candidate = YES |
| Tock 1 | **shipped, drill-verified** | `working/tock-01-fail-closed-gate.md` — pre-tool gate fails closed; forcing gap GAP-A; drill `sess_b76328acde5b` (absent operator → deny at 300s, workspace untouched). Named GAP-M (gemini adapter same class, unfixed, needs own citation) |
| Model-tier delegation (interlude) | **shipped** | Standing objectives + deliverable 6 added (above); `docs/reference/task-packet-template.md` (PROVISIONAL); Tier-0 ollama appliance on mac mini `192.168.69.15:11435`, egress receipt `3c6b1d029d04…`, `working/tier0-appliance-mini.md`. Not a tick — infrastructure for cheaper-model ticks. |
| Tick 2 (first downgrade experiment) | **tick-shipped** | `working/tick-02-nq-host-detail.md` — Sonnet drove (45 transcript msgs, all `claude-sonnet-4-6`). **Cargo:** shipped green (independent `cargo test -p nq-db`, new test passes, no regression). **Dogfood:** control+audit HELD (fail-closed gate held under weaker executor; GAP-H fix held), promotion custody DEGRADED — **GAP-N** (bundle = whole-tree diff, over-captured Tick 1 residue; neither promote nor reject safe on a dirty tree). **Packet:** downgrade **SUCCESS** — 9 decisions all approve, zero denies/stop-asks; the 3 added packet fields demonstrably helped. → Tock candidate: scope promotion to session-attributable changes (GAP-N). |

## Next tick candidate

**First downgrade experiment**, run under the five-step loop:

1. *Plan:* judgment model authors a **template-grade packet**
   (`docs/reference/task-packet-template.md`) for fenced/test-pinned/mechanical cargo
   (Tick 1 class), carrying the three fields Tick 1 was missing (additive-tests clause,
   expected-verify baseline, rollback line).
2. *Execute:* hand it to a *cheaper* model — Sonnet via the supervised backend, or a
   LOCAL-tier slice to the mini appliance — through the now-fail-closed dogfood.
3. *Validate dogfood first:* did the fail-closed gate, ledger, and promotion behave
   with a weaker executor pushing on them?
4. *Validate cargo:* independent test run, diff review.
5. *Accept/reject;* the packet verdict answers whether the packet (not the model)
   carried the work — the first real test of the downgradeability ratchet.

Not yet opened.
