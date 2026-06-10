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

## Tick deliverables

Every tick report carries deliverables 1–5 (patch outcome, test result, review/promote
record, gap list, Tock recommendation) **plus**:

6. **Model-suitability block** — feeds the downgradeability ratchet:
   - model used (and surface: supervised backend / direct / operator);
   - ambiguity encountered (where the packet was underspecified);
   - operator interventions (count + whether any were judgment calls vs. mechanical);
   - was the task packet sufficient? (yes/no/what was missing);
   - **downgrade candidate for next similar work** — yes / no / maybe, why, and the
     specific missing packet detail that would make a cheaper model safe.

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

## Next tick candidate

**First downgrade experiment:** run a tick whose cargo is fenced/test-pinned/mechanical
(Tick 1 class) but hand it to a *cheaper* model — Sonnet via the supervised backend, or
a LOCAL-tier slice to the mini appliance — from a **template-grade packet**
(`docs/reference/task-packet-template.md`) carrying the three fields Tick 1 was missing
(additive-tests clause, expected-verify baseline, rollback line). The tick's
deliverable-6 block answers whether the packet (not the model) carried the work. This is
the first real test of the downgradeability ratchet, not yet opened.
