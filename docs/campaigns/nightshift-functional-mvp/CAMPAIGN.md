# Campaign: Nightshift Functional MVP (+ the maude dogfood)

> **Ratified by operator 2026-07-05** ("get nightshift to actually work…
> use maude to build it using smaller models to dogfood the pipeline").
> Post-RC hardening — the ops-workflow lane, not new shiny.
> Work lands in `~/git/nightshift` in ITS idiom; this card + specimens live
> here because AG/maude carry the pipeline. Two campaigns run under this
> ruling; the sibling is `docs/campaigns/docs-professionalization/`.

## v0.1 claim (the ONLY lane)

> Nightshift can hold a deferred agent work item, bind it to witness
> freshness/receipts, refuse stale or missing testimony, and hand a
> governed promotion candidate to AG/Maude.

**Deferred does not mean trusted later.** It means "held until
admissibility conditions can be checked."

## Non-goals (kill on sight)

No autonomous execution. No schedule-as-consent. No agent self-promotion.
No plugin system. No production-daemon promises. No cron empire.
Anything that smells like "sleep while agents fix prod" → obstruction note.

## Where nightshift actually is (gap assessment 2026-07-05, full report in session transcript)

~24K LOC single crate, 168 unit tests + AG-subprocess drills. **~65% of the
lane exists:** liveness gate + typed verdicts (Fresh/Stale/Skewed), refusal
packet on stale witness (the README specimen), packet emission (16-field
Packet, sqlite ledger: agendas/runs/run_events/bundles/packets/
tolerance_state/attention_state), MVP-A drill handoff (posture → wicket →
WLP artifacts). Gaps are **vocabulary and integration, not architecture**:
witness binding is NQ-liveness-hardcoded; "candidate" is implicit in
authority ceilings; refusal reasons are free-text strings; no
plan-envelope export; no programmatic create verb.

## Build packets (order = pipeline-shakeout first, then dependency)

| # | Packet | Size | Worker | Notes |
|---|---|---|---|---|
| NS-0 | **Model-pinning verification** (AG/maude side) | S | integrator | Prove `--model <small>` threads maude → `runtime.session.create` RPC → supervisor → `LaunchConfig.args` → claude CLI (`claude_code.py:345` extends cmd). If any hop drops args, smallest fix. Precondition for the whole dogfood. |
| NS-1 | **Refusal receipt type registry** | S | small model under maude | Closed enum `RefusalKind {LivenessStale{age_s,threshold_s}, BasisInvalidated, PreflightHeld, …}`; typed `refusal:` field on Packet; `liveness_gate_failed()` populates. Free-text stays as display. First REAL packet deliberately small — it shakes the pipeline. |
| NS-2 | **Candidate authority level** | S | small model under maude | Name the split "fresh enough to run" vs "approved to promote": explicit `Candidate` (or documented Advise-as-candidate semantics) between Advise and Stage; ceiling downgrade rule; docs line: "fresh → candidate; Governor approval → stage/apply". |
| NS-3 | **Generic witness trait + gate refactor** | M | small model under maude, Opus review | `trait Witness { state() → Fresh/Stale/Missing; next_recheck() }`; capture-phase gate takes `&dyn Witness`; NQ liveness becomes the first impl; agenda binds witness list (v1 gate-level). Touches the fail-closed gate → sandwich mandatory. |
| NS-4 | **`watchbill create` (deferred-work verb)** | M | small model under maude | Expose capture-phase as `watchbill create <agenda> --finding <key>` → open run_id, JSON out; enables split capture/reconcile. |
| NS-5 | **Plan-envelope exporter** | M | small model under maude, Opus review | `Packet → plan-envelope-v0` shim (`plan_envelope.rs`): objectives/actions/risks/witness_bindings; posture map Advisory→candidate, Stage→approved, Escalate→blocked; schema-enforced; `--export-plan-envelope <dir>`. THE handoff — this is where NS vocabulary meets maude vocabulary; translation shim lives NS-side, imports no AG code. |
| NS-6 | **Witness-binding validation + docs** | S | small model under maude | Agenda-load validation (declared sources vs wired witnesses); GAP doc for per-step binding (v2+, named not built). |

Exit demo (cargo verdict): one command sequence a stranger can run —
stale witness → typed refusal packet; fresh witness → candidate packet →
`--export-plan-envelope` → maude `report`/render shows the candidate with
authority accounting. Plus the drill suite still green.

## The dogfood mechanics (this is half the point)

Every NS-1..6 packet is executed as a **governed maude run by a smaller
model**, CD-4 machinery end to end:

1. Integrator authors `specimens/ns-<n>/` in THIS dir: `plan.md` (M-1
   envelope; objectives = the packet table row; citations = gap-assessment
   digest + the nightshift files touched), queue item, ration card
   (observe-only axes, path-fenced to `~/git/nightshift`).
2. **Operator acts per packet:** queue latch + plan promotion (approval
   witness file). Batched at wave boundaries.
3. `maude run specimens/ns-<n>/plan.md` → supervised claude_code session
   **pinned to a smaller model** (NS-0 proves the pin; tier: haiku for S
   packets, sonnet for M packets — cheapest model satisfying the gap).
4. Tool calls approved/denied from the maude queue (auto-approve
   read-only; writes fenced to the nightshift tree).
5. Session ends → ReviewPacket → maude M-4 `report` → operator (or
   authorized integrator, CD-4B-style) keep/discard. `cargo test` runs via
   `governor verify-run` inside the session — exit codes are the verdict.
6. Commits land in nightshift's lane with its idiom; push per its rules.

**Dogfood verdict per packet (recorded in STATUS):** did the small model
carry the Rust work? where did maude's surface bind? every friction line
is M-series/GS fuel. If a small model fails a packet twice, escalate the
MODEL (haiku→sonnet→opus), never the authority.

## Verifiers & receipts

- Mechanical: `cargo test` bare exit per packet (verify-run receipt).
- NS-3/NS-5 get the adversarial sandwich (fail-closed gate + vocabulary
  boundary respectively).
- Actor never greens its own gate: the session's ReviewPacket is validated
  by the landed validator; keep/discard is an operator-lane act.
- Receipts per packet in `specimens/ns-<n>/` (queue, witness, packet,
  verify-run IDs) — same corpus discipline as CD-4.

## Stop conditions / obstruction

Any packet that (a) needs AG vocabulary inside nightshift, (b) weakens the
liveness gate, (c) adds an execution path, or (d) exceeds its ration →
obstruction note in STATUS, work halts in that lane. Model-capability
obstructions escalate the model, not the fence.
