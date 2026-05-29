# GOV_GAP_PHASE_WITNESS_MAPPING_001

## Title

Agent Governor lacks a typed mapping from its authority-bearing phases (intent compilation, evidence load, scope check, gate evaluation, egress check, provider/tool call, mutation authorization, receipt emission) to NQ's `workload_phase_observation` grammar. AG owns the mapping; NQ owns the grammar. The boundary is unstated.

## Status

Gap spec — containment vessel. **No emitter code, no wire shape, no schema change, and no enforcement behavior is ratified by this filing.** Names the mapping responsibility, the can/cannot-testify boundary, and the per-axis decomposition discipline that v1 must carry. Candidate, non-binding.

## Filed

2026-05-29. Forcing context: cross-repo coordination note dropped into the operator session naming AG's local responsibility for mapping Governor phases to workload-phase witnesses, and NQ's blocking gap (PHLR) preventing premature wire-shape ratification.

## Blocked-by

- NQ's `WORKLOAD_PHASE_WITNESSES.md` lifting from held v0 to v1.
- NQ's `PRESSURE_HARM_LOSS_RECOVERABILITY_GAP.md` ratification (axis decomposition of the v0 `harm` block).
- At least one Governor adopter forcing case (gate evaluation, egress check, provider call, or mutation authorization phase) that would justify shipping an emitter.

This gap does not unilaterally lift any held status. It records the AG-side mapping shape that v1 ratification must carry.

## Origin

Operator session 2026-05-29. Cross-repo coordination note named AG's local responsibility for mapping Governor's authority-bearing phases to the common workload-phase witness shape. NQ owns the grammar (`docs/integration/WORKLOAD_PHASE_WITNESSES.md`, held v0). AG owns the per-phase mapping.

The keeper from the coordination note:

> **Authority-bearing work needs phase witnesses because "the gate ran" and "the action was admissible" are not the same claim.**

The same-day PHLR gap (NQ, `PRESSURE_HARM_LOSS_RECOVERABILITY_GAP.md`) blocks the v1 lift-off of the integration draft. AG's mapping gap inherits the block: any v1 emitter must carry per-axis decomposition (pressure / harm / loss / recoverability), not the bundled v0 `harm` block.

## Problem Statement

AG has multiple surfaces that already emit phase-shaped observations:

| Surface | What it emits | Phase coverage |
|---------|---------------|----------------|
| `gate_receipt.py` | Content-addressed decision receipts (subject_hash, evidence_hash, policy_hash) | gate evaluation, egress check (partial), evidence load (partial) |
| `signals/` (GATE_CHECK_SUMMARY, VERIFY_SUMMARY, etc.) | SignalEnvelope per gate invocation | gate evaluation, verifier suite runs |
| `governed_activity.py` | FactObservation, PreconditionBundle, AttemptRecord, DriftCheckResult | mutation authorization (drift-gated retry), evidence load (precondition bundles) |
| `runtime/events.py` (CanonicalEvent) | JSONL-persisted event bus for supervised sessions | provider/tool call (via hook bus) |
| `egress_gate.py` | EgressResult + gate receipt | egress check |
| `intent_compiler.py` | Compilation receipts (IntentFormSchema, template selection) | intent compilation |
| `scope.py` | Scope grants, escalation receipts, usage log | scope check |
| `evidence_gate.py` | Evidence custody scoring, violation records | evidence load |

What's missing is **the common shape**: each surface emits in its own format, with its own provenance discipline, and no surface declares which authority-bearing phase it is testifying *about*. Cross-surface correlation today happens by reading receipts and signals separately and reconciling at consumer time.

The workload-phase witness contract (NQ-side) supplies the common shape. AG's gap is the mapping table — which phase each existing surface partially witnesses, what each surface can and cannot testify to, and what would need to be added (not invented, not refactored) when an adopter forcing case justifies emitter code.

## Failure Mode

The laundering path this gap names:

1. AG emits a gate receipt with `verdict: allowed` and a signal envelope with `count_block=0`.
2. A downstream consumer (NQ, an operator console, a postmortem) reads the receipt and treats it as testimony that the action was admissible.
3. The receipt testifies only that the gate ran with that evidence and produced that verdict at that time.
4. The action was admissible *only if* the evidence basis was qualified, the perturbation regime was the one the verdict was earned under, the substrate did not drift between gate and action, and the receipt itself was emitted (not silently dropped).
5. None of those qualifications were on the receipt. The downstream consumer launders gate-ran into action-admissible.

This is the cut the workload-phase witness grammar exists to refuse. The packet says what was observed; the consumer classifies. AG's mapping responsibility is to make each Governor phase emit in a shape that survives that boundary — observation-side, with explicit `cannot_testify` for the obligations the phase did not certify.

The structural risk is not that gate verdicts are wrong. The structural risk is **scope creep on what a gate's testimony covers** when its output is reused across boundaries (gate-ran → action-admissible is the canonical case; receipt-emitted → mutation-safe is another).

## Authority-Bearing Phases (AG Mapping Target)

The eight phases named in the coordination note, each with the AG surface(s) that partially witness it today:

| Phase | Existing AG surface(s) | What AG can testify | What AG cannot testify |
|-------|------------------------|---------------------|------------------------|
| **intent compilation** | `intent_compiler.py` (IntentFormSchema, template) | form selected, schema hash, compilation succeeded/failed | operator's intent was correctly captured; downstream interpretation will preserve intent |
| **evidence load** | `evidence_gate.py`, `governed_activity.py` (precondition bundles), `signals/` provenance labels | which evidence kinds were sampled in window, custody score, label provenance | evidence was semantically correct; substrate state remained as evidence claimed after load |
| **scope check** | `scope.py` (grants, escalations, usage log) | scope grant present, escalation path taken, axis match/mismatch | scope was the right scope for the operator's actual intent |
| **gate evaluation** | `gate_receipt.py`, `signals/gate_check_summary.py` | gate ran with these inputs, produced this verdict, with this policy hash | verdict was globally correct; verdict generalizes to a wider perturbation regime (see `GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001`) |
| **egress check** | `egress_gate.py` + gate receipt | classification produced, rule fired, sensitivity hash | destination behaved truthfully; payload was semantically what classifier inferred |
| **provider/tool call** | `runtime/events.py` (hook bus events), `chat_bridge.py` (backend dispatch) | call dispatched, response observed, latency window | provider returned correct content; tool call did what its name implied |
| **mutation authorization** | `governed_activity.py` (AttemptRecord, DriftCheckResult), `wrapper.py`, hooks | mutation authorized at decision time, drift verdict at attempt time | mutation was semantically safe; future state remains authorized after substrate drift |
| **receipt emission** | `gate_receipt.py` (ReceiptStore), `signals/emit.py` (JsonlSink) | receipt persisted to store at time T, blob retrievable | receipt was actually consumed; receipt was the correct receipt for the decision |

Each row's `cannot_testify` is structural, not exhaustive. The minimum NQ-side refusals (`semantic_correctness`, `future_stability`, `global_health`, `user_or_product_truth`, `root_cause`, `external_party_truthfulness`) compose with the per-phase refusals above.

## PHLR Refinement (Inherited Block)

When AG eventually emits workload-phase witnesses, the v0 `harm` block must already carry the PHLR decomposition (per NQ's `PRESSURE_HARM_LOSS_RECOVERABILITY_GAP.md`). The mapping for AG-relevant cases:

- **pressure** — gate evaluation timed out and was bypassed; signal store fell behind; receipt store fcntl backed off; daemon RPC queue depth grew.
- **harm** — mutation authorized without evidence basis; egress check bypassed by hook configuration drift; intent compilation degraded to template-only due to validation failure.
- **loss** — receipt failed to emit; signal envelope dropped; gate verdict computed but not persisted; evidence binding lost to substrate failure.
- **recoverability** — receipt store JSONL still readable (recoverable by rebuild); signal plane SQLite stale but reconstructable from JSONL (recoverable by `governor signals rebuild`); evidence blob purged past retention (not recoverable); gate verdict recomputable from logged inputs (recoverable by replay if inputs intact).

Each axis carries its own `cannot_testify` boundary. Silent absence of an axis block is the laundering shape PHLR refuses.

The recoverability axis has special weight for AG: many Governor surfaces have replay or rebuild paths (signal plane rebuild, receipt store reconstruction from blobs, semantic stability re-derivation). Recoverability is not a single boolean — it depends on whether the source window is still open, whether the substrate has been compacted, and whether the policy version is still pinned.

## Existing Governor Coverage (What Already Survives Roughly)

| Capability | Where | What it gives toward phase witnesses |
|------------|-------|---------------------------------------|
| Content-addressed receipts | `gate_receipt.py` | subject/evidence/policy hashes; timestamp metadata; not phase-tagged |
| Append-only signal JSONL + SQLite projection | `signals/emit.py`, `signal_store.py` | window-bounded observation history; query by name/session/phase tag (phase tag exists but is signal-phase, not workload-phase — naming collision) |
| Session identity | `session.py` | process-scoped session_id for cross-receipt/signal correlation |
| Canonical event bus | `runtime/events.py` | JSONL persistence of supervised session activity |
| Drift-gated retry observations | `governed_activity.py` | FactObservation + DriftVerdict — closest existing analogue to phase witness shape |

The closest existing AG surface to a workload-phase witness is `governed_activity.py`'s `FactObservation` + `PreconditionBundle` + `AttemptRecord` triple. That subsystem already separates observation-time, precondition-time, and attempt-time facts with explicit drift verdicts. It is not phase-tagged in the workload-phase witness sense, but its shape composes naturally with that grammar.

## Naming Collision Warning

AG's `signals/` module already uses `phase` as a field name (`phase="2.4C"` etc.) referring to the *instrumentation phase* (Phase A / Phase B / Phase C / Phase D of the v2.4 spine). NQ's workload-phase witness `phase` field refers to a **named application phase** (`derive_update_author_day`, `gate_evaluation`, etc.). Same word, different semantics.

If AG ever ships a workload-phase emitter, the field naming must not collide. Candidate disambiguations: `workload_phase`, `app_phase`, or a separate envelope type with its own grammar. This filing does not prescribe; it warns.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. Names the mapping responsibility — AG maps Governor phases to NQ's workload-phase grammar; NQ owns the grammar.
2. Identifies the eight authority-bearing phases and what each existing AG surface can/cannot testify to. (The table above is the candidate; not ratified.)
3. Records the can/cannot-testify boundary at the phase level, not just at the receipt level.
4. Identifies the PHLR refinement as the required v1 axis discipline (pressure / harm / loss / recoverability with per-axis `cannot_testify`).
5. Names the `phase` field collision with `signals/` and what disambiguation rules an adopter document would need.
6. Identifies forcing cases that would justify shipping an emitter: a gate evaluation phase that was later treated as testimony for action-admissibility when its receipt did not carry that claim; an egress check whose bypass under hook drift was not visible at the workload-phase boundary; a mutation authorized at T whose substrate drifted before action without phase-witness signal.
7. Does not specify the wire shape. The eventual adopter document at `docs/integration/NQ_WORKLOAD_PHASE_WITNESS.md` (Governor side) is implementation territory and waits for v1 ratification of the NQ-side grammar.

## Doctrine (proposed; not yet ratified)

> **Authority-bearing work needs phase witnesses because "the gate ran" and "the action was admissible" are not the same claim.**

> **NQ owns the grammar. AG owns the phase map. Governor's receipts and signals testify to what they observed in the phase; consumers classify.**

> **A gate receipt is testimony, not absolution. The phase witness layer makes that line visible at the wire boundary, not at the consumer's interpretation step.**

Candidate doctrine until forcing cases promote.

## Non-goals

- **Not a refactor of `gate_receipt.py`, `signals/`, `governed_activity.py`, `runtime/events.py`, or any other AG surface.** Each is correct as a phase-observation primitive on its own axis; the gap is the missing common shape, not a wrong shape on any existing surface.
- **Not a new daemon, broker, or schema registry.** v0 of the NQ-side grammar is append-only JSONL; any AG emitter must follow the same posture.
- **Not authorization of an AG-side emitter.** This filing names the mapping; it does not ship emitter code. The adopter document at `docs/integration/NQ_WORKLOAD_PHASE_WITNESS.md` waits for both NQ v1 ratification and a forcing case.
- **Not a substitute for host telemetry.** CPU/disk/memory/net witnesses observe substrate levels; workload-phase witnesses observe what Governor was doing at the substrate. AG does not own the substrate-telemetry surface.
- **Not a global health rollup.** No `healthy / degraded / down` verdict field. Per-phase observation only; classification lives in NQ or operator surfaces.
- **Not a binding of `phase` semantics across `signals/` and a future workload-phase emitter.** The naming collision is real; this filing warns but does not prescribe a fix.
- **Not a lift of NQ's `WORKLOAD_PHASE_WITNESSES.md` from held to v1.** That call is operator-strategic and waits on PHLR.

## Relationship to Other Gaps / Specs

- **NQ `WORKLOAD_PHASE_WITNESSES.md`** — The grammar AG maps to. Held v0. v1 lift-off blocked by PHLR.
- **NQ `PRESSURE_HARM_LOSS_RECOVERABILITY_GAP.md`** — Forces the harm-block axis decomposition that any AG emitter must inherit.
- **`GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001`** — Sibling-shaped. That gap names qualification-vs-drift at the per-witness level. This gap names phase-level testimony scope at the per-phase level. Compose at the gate evaluation row of the table above: a gate verdict is a witness whose qualification regime is what the phase observation must declare.
- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Sibling-shaped. That gap names missing content-semantic enforcement on `admissibility_check`. This gap names missing phase-level testimony shape. Both pick up boundaries Governor has vocabulary for but no typed surface against.
- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — Adjacent. Receipt kernel ≠ authority kernel; complementary not parallel. Phase witnesses sit on the boundary between them — the gate ran (receipt kernel territory) is not the action was admissible (authority kernel territory).
- **`gate_receipt.py`, `signals/`, `governed_activity.py`, `runtime/events.py`, `egress_gate.py`, `intent_compiler.py`, `scope.py`, `evidence_gate.py`** — The eight existing surfaces under the mapping table. None is wrong; the gap is the common shape across them.

## Open Questions

1. **What is the minimum AG-side adopter shape that survives PHLR ratification?** Until PHLR lands, the v1 packet spine is unstable. Any AG emitter spec drafted now risks lock-in.
2. **Does AG need a new emitter module, or do existing surfaces decorate?** If `gate_receipt.py` adds a `workload_phase` field, the receipt becomes the witness. If a new module emits, the receipt is one substrate attachment in the witness. Both are coherent; neither is committed.
3. **Where does the `phase` field collision get resolved?** Renaming `phase` in `signals/` is a breaking change to the SQLite projection schema. Renaming the workload-phase field in the AG adopter is a breaking divergence from NQ's grammar. Neither is committed.
4. **Does Governor's session identity (`get_session_id()`) map to the workload-phase witness's correlation key, or does the workload-phase layer want its own correlation surface?** Both are coherent; collapse-or-keep-separate is implementation territory.
5. **Is the eight-phase enumeration stable, or does it grow with Governor surfaces?** Future surfaces (verifier gate, semantic stability audit, runtime supervisor promotion) may want phase coverage. The enumeration is a candidate, not a closed list.
6. **Does Governor's existing `policy_hash` axis on gate receipts already approximate the perturbation-regime declaration that `GOV_GAP_WITNESS_INVARIANCE_QUALIFICATION_001` calls for?** If yes, the phase witness layer inherits regime-binding for free at the gate-evaluation row. If no, that's a separate refinement.

## Provenance

Filed 2026-05-29 immediately after NQ filed `PRESSURE_HARM_LOSS_RECOVERABILITY_GAP.md` and the integration amendment to `WORKLOAD_PHASE_WITNESSES.md`. The operator session began with a cross-repo coordination note naming AG's local responsibility for mapping Governor's authority-bearing phases to the workload-phase witness grammar. Initial impulse was to file the AG-side spec immediately; the operator caught the draft mid-flight and held it pending NQ's PHLR refinement.

Filing now (against the post-PHLR shape) preserves the keeper distinction from the v0 keeper text (*the gate ran ≠ the action was admissible*) while inheriting the axis-decomposition discipline (*pressure ≠ harm ≠ loss ≠ unrecoverability*). Filing pre-PHLR would have locked in the bundled `harm` block that v1 must refuse.

This gap is a containment vessel. It does not authorize an emitter, ratify a wire shape, or commit AG to a specific mapping. It names the responsibility boundary (AG maps, NQ owns the grammar), the eight phases, the per-phase testimony scope, and the PHLR refinement that any v1 emitter must carry.

Promotion to adopter document (`docs/integration/NQ_WORKLOAD_PHASE_WITNESS.md`) waits on: NQ-side v1 ratification, PHLR ratification, and at least one Governor-side forcing case that would justify the emitter code.
