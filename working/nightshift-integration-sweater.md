# Nightshift Integration Sweater

**Filed:** 2026-06-09. **Status:** integration map. NOT architecture, NOT doctrine, NOT a plan to execute. One pass, one context, one operator-facing map.

## Reading this doc

Every claim is tagged with one of:

- **built** — code path exists and has been run
- **sketched** — structure exists; not verified end-to-end this pass
- **asserted** — prose / design / memory claim only
- **missing** — no artifact yet

**Untagged claim = goblin.** If you find one, that's drift, not content.

Two operating tests:

> **Sword:** *If a component requires James to manually translate its claim into another component's input, that edge is missing.*
>
> **No "while we're here":** discovering a gap is a docket candidate, not an invitation to fix it in this doc.

This is *not* the docket. It generates docket candidates. Docket is a separate triage pass.

---

## 1. Component Inventory

### In MVP scope

The smallest cut required for one read-only live specimen: `NQ → Nightshift → Governor → Receipt`.

| Component | MVP role |
|---|---|
| **NQ** | Testifies about live operational state (findings as four-part proofs) |
| **Nightshift** | Interprets findings, assembles context, emits proposal packets; no direct authority |
| **Governor** | Gates proposal into permitted/denied action class; emits gate receipt |
| **Receipt Kernel** | Records what discharged what (hash-chained event ledger) |

### Out of MVP scope (with rationale)

| Component | State this pass | Rationale |
|---|---|---|
| **Wicket** | **sketched** — Rust modules (`cook.rs`, `grant.rs`, `verdict.rs`, `receipt.rs`, `rules.rs`) match SPEC.md | Preflight kernel, not decision surface; future Rust-kernel peer; crosswalked in §4 |
| **WLP** | **asserted** — protocol spec read; no live carrier verified this pass | Only needed if MVP crosses process/protocol boundary; shadow-mode single-host does not |
| **Lean kernels** | discovery substrate, not runtime | Per existing custody classes (PUBLIC-SHIPPED / ANNEX / UNRATIFIED-CANDIDATE / SCRATCH / DEPRECATED); promotion-gated |
| **Linear Accountant** | **frozen** / needs consumer | No MVP need for convertible spend / budget tokens yet |
| **Labelwatch** | active-only-with-consumer | No concrete reporting surface named for MVP |
| **Continuity / Cadence / Standing / Custody** | not in MVP path | None already load-bearing for the chosen read-only specimen |

---

## 2. Component Status Table

| Component | Status | Can witness | Refuses | Must NOT be claimed |
|---|---|---|---|---|
| **NQ** | **built** (live demo at nq.neutral.zone; production deployment per README) | failure classification (not just thresholds); recurring vs new; host-vanished suppression; observability-gap detection | silent collapse of distinctions; "service up substrate dying" laundering; "loss of observability = fabricated health" | NQ as authority over remediation; NQ self-observation (memory: candidate, not built); end-to-end wire to Nightshift verified this pass |
| **Nightshift** | **built** (`nightshiftd` Rust crate, 25+ integration tests including `mvp_a_pipeline.rs`, `governor_rpc_live.rs`, `nq_integration.rs`, `reconciler_pipeline.rs`, `liveness_pipeline.rs`) | proposal shape; agenda binding; `GovernorBinding` (declares Governor RPC required above `AuthorityLevel::Stage`); run-ledger-vs-authority-receipt separation (asserted in `ledger.rs` comment: *"Run-ledger events are NOT authority receipts. Governor emits…"*) | direct effectful action; promoting run-ledger event to authority receipt | Nightshift as authority source; MVP A pipeline as proven-wired to production NQ + production Governor end-to-end (test names imply structure; not deep-read this pass) |
| **Governor** | **built** (alpha; 14,600+ tests; daemon, runtime supervisor for Claude Code / Gemini CLI, gate_receipt wired across 10+ modules including `chain_gate`, `constraint_gate`, `evidence_gate`, `ci`, `daemon`) | NLAI (language is a proposal, not an authority); permit/deny verdicts; content-addressed gate receipts with `receipt_role` field (`measurement` / `proposal` / `authority` / `recovery_plan` / `reset`); supervisor-mediated tool calls; egress gate | self-mint of authority; advisory logging that bypasses the gate; agent-supplied evidence | non-discharge field is currently emitted by default (**confirmed gap this pass** — receipt has `receipt_role` but no `non_discharge` field; see §4 item 3) |
| **Receipt Kernel** | **built** (`libs/receipt_kernel/`, 6 constitutional invariants, SQLite WAL, hash-chained event ledger, retention policy, redaction hook) | append-only hash-chained event stream; content-addressed blob store with TTL/expiry; 6 invariants (ledger.chain_valid, receipt.completeness, evaluation.completeness, finalization.completeness, run.single_finalize, run.stage_required_path); UNKNOWN verdict treated as failure | silent downgrade; missing finalize; illegal stage transitions | unified emission with Governor's `gate_receipt`: today they are *parallel* per `receipt_bridge.py`, not a single store |

---

## 3. Edge Contract Table

| Edge | Needed for MVP? | Status | Input | Output | Refusal mode | Receipt / non-discharge behavior |
|---|:-:|---|---|---|---|---|
| **NQ → Nightshift** | yes | **sketched** — `nq_integration.rs` + `nq_cli.rs` tests exist; `Governor` enum variant in agenda; shape contract NOT verified end-to-end this pass | NQ finding (four-part proof) | Nightshift agenda item / proposal context | insufficient classification / stale / no NQ coverage | not currently receipted as a cross-system event; Nightshift run-ledger captures locally |
| **Nightshift → Governor** | yes | **witnessed (at pipeline-function level)** — `horizon_packet_state::defer_makes_governor_receipt_observable_in_packet_and_ledger` + `horizon_cross_run::tolerated_active_continues_to_defer_before_expiry` exercise `capture_phase` + `reconcile_phase_with_horizon` with `FixtureGovernorClient`; both pass. **`run_watchbill` top-level entry does NOT thread governor** — sub-edge `sketched`, see witness file CORRECTION section. | proposal packet (Advisory or higher) | permit/deny → Governor verdict + receipt | proposal-not-authority; promotion ceiling exceeds binding without Governor RPC | Governor gate receipt fires on Defer outcomes (verified); non-discharge field still NOT emitted today (gap remains) |
| **Governor → Receipt Kernel** | yes | **sketched** — `receipt_bridge.py` exists for parallel emission; daemon-path gate receipts emit; bridge wiring for Nightshift-path verdicts NOT verified this pass | gate verdict + evidence bundle | hash-chained event in receipt_kernel SQLite | no discharge / no authority / evidence type mismatch | yes (parallel emission today; unification deferred — not MVP-blocking) |
| **Receipt → Consumer (operator inspection)** | yes | **asserted** — operator reads receipts via CLI / daemon RPC; no automated programmatic consumer named for MVP | receipt id / query | scoped reliance (advisory display only) | wrong consumer / stale / out of scope | receipt-of-reading is not captured; **candidate docket item** |
| **WLP boundary preservation** | no (shadow mode is single-host) | **missing** (correctly — not in MVP path) | n/a | n/a | n/a | n/a |
| **Wicket preflight peer** | no (Governor is MVP carrier) | **sketched / not on MVP path** | n/a (deferred) | n/a (deferred) | n/a | n/a |
| **NQ → Receipt Kernel direct** | no | **missing** — NQ writes its own SQLite; not bridged to Receipt Kernel today | n/a | n/a | n/a | candidate gap, deferred (no consumer for this edge yet) |

### Edges where the sword fires

> *If a component requires James to manually translate its claim into another component's input, that edge is missing.*

- **NQ → Nightshift**: whether NQ finding JSON has a stable shape Nightshift consumes without James-side reshaping is the open verification. Test name implies a contract; conversion code not witnessed this pass. **Edge marked `sketched`, not `built`, on that basis.**
- **Receipt → Consumer**: today "I read the receipt" is a James action with no programmatic consumer. **Edge marked `asserted`.** The receipt has *roles* in principle (audit, downstream ratification) but no MVP-named caller.

---

## 4. Governor Up-to-Spec Section

**Discipline reminder:** none of these are new doctrine. All seven are already present in NLAI + the receipt discipline + the corpus's existing Lean kernels. The work is making them mechanically check-able at Governor's code surface for the Nightshift integration path. **Phrasing any of them as "discovered" would launder existing doctrine into "tomorrow's findings."**

1. **Proposal ≠ authority.** Nightshift submits proposals; Governor decides admissibility. Governor's API should make it impossible to "execute" a proposal without an intervening verdict. **Status:** built (NLAI is core; supervisor enforces; `evidence_gate` blocks).
2. **Permit/deny ≠ discharged claim.** A Governor permit means *"admissible to proceed"* — it does not certify the upstream claim. Discharge of a claim requires evidence linked at the gate. **Status:** sketched (receipt schema includes `receipt_role`; evidence linking exists; explicit "verdict ≠ discharge" semantic is implicit, not codified at the surface).
3. **Receipt records non-discharge.** *Load-bearing.* When Governor denies an effectful action OR permits an advisory display without certifying upstream claims, the receipt must record *what the verdict did NOT settle*. **Status: MISSING.** `gate_receipt.py` (schema v3) has `receipt_role`, `subject_hash`, `evidence_hash`, `policy_hash` — but no `non_discharge` field. **This is the single highest-value docket item the sweater surfaces.** Without it, the integration is allow/deny logging with extra steps.
4. **Custody visibility is scoped.** A receipt visible to consumer X does not imply visibility to consumer Y. **Status:** built (scope governor + custody classes exist).
5. **Consumer reliance does not globalize.** That consumer A relied on a receipt does not make the receipt's claim true for consumer B. **Status:** sketched (doctrine is named; per-consumer reliance tracking not surfaced in the gate receipt today).
6. **Current evidence required at action boundary.** Receipt minted at t₀ does not automatically discharge at t₁; freshness applies. **Status:** built (Freshness.lean is in the 1.0 surface; need to verify the Python evidence_gate consults it for cross-time discharge).
7. **No effectful write in shadow mode.** Shadow mode permits advisory / read-only paths only. **Status:** built at runtime supervisor layer (intervention queue gates writes); needs MVP-pass explicit assertion as a hard fence.

**Encoding move (NOT implementation this pass):** each item maps either to an existing Governor code surface (cited above) or to a candidate docket item. Items 2, 3, 5 are the strongest candidates for the docket; item 3 is the load-bearing one.

---

## 5. Rust Kernel Future Section

**Do not implement.** Sketch only. The eventual Rust kernel boundary, if/when promoted under a forcing case (Nightshift integration could become that trigger; not yet):

```rust
// Pure decision boundary. No I/O. No network. No DB. No "agent."
//
// Python harness owns: transport, receipt persistence, tool dispatch, RPC,
// supervisor lifecycle, content-addressed receipt store, daemon.
// Rust core owns: the decision shape.

enum ProposalKind {
    Advisory,
    ReadOnlyInspection,
    EffectfulWrite,
    Remediation,
}

enum EvidenceStatus {
    Witnessed,
    Asserted,
    Stale,
    Missing,
    OutOfScope,
}

enum Decision {
    PermitAdvisory,
    PermitReadOnly,
    DenyEffectful,
    RequireWitness,
    RefuseOutOfScope,
}

struct NonDischarge {
    claim: String,
    reason: String,
    required: Vec<String>,
}

fn decide(
    p: Proposal,
    e: EvidenceBundle,
    pc: PolicyContext,
) -> (Decision, Option<NonDischarge>);
```

Python harness wraps this for receipts, transport, tool dispatch. **Until parity exists, Python is the running carrier.**

**Open question NOT resolved this pass:** is the future Rust core *Wicket evolved* or *a sibling Rust artifact alongside Wicket*? Both packets that fed this pass leave the question open. The sweater inherits the ambiguity. Resolution requires a forcing case neither pass has yet — most likely either (a) the non-discharge field gap above becomes load-bearing enough to motivate a port, or (b) Wicket grows a forcing case beyond preflight legibility.

**Crosswalk: Wicket vs. future Rust kernel**

| Concept | Governor (Python today) | Wicket (Rust today) | Future Rust core (sketch) |
|---|---|---|---|
| Proposal | agent/tool action request | admission input / intent | `Proposal` enum (read-only / advisory / effectful) |
| Evidence | receipt bundle / witness refs | `basis` dimension | `EvidenceBundle` + `EvidenceStatus` enum |
| Authority check | policy/gate decision | `basis × precedence × standing` | `PolicyContext` |
| Verdict | permit / deny / refuse | three-dimensional projection | `Decision` enum |
| Receipt | existing content-addressed `gate_receipt.py` | `receipt.rs` (per SPEC.md) | (left to Python harness) |
| MVP role | **carrier** | crosswalked peer | future / not built |

*"Wicket may classify and gate. Wicket may not become the source of authority"* (Wicket README). Same discipline applies to the future Rust core: it decides admissibility; it does not act.

---

## 6. First Live Specimen Path

Identify only. **Do not execute this pass.**

```
NQ live finding (e.g., WAL-bloat per Nightshift README example)
  → Nightshift advisory proposal (via existing nq_integration code path)
  → Governor permits Advisory / denies Effectful (via Nightshift's GovernorBinding RPC)
  → Receipt records: witness ref, proposal, decision, AND non-discharge
                                                       └─ depends on §4 item 3 landing
```

**Concrete next-admissible action** (single docket candidate the sweater commits to, per the no-WIP-inflation discipline):

- Pick one already-occurring NQ finding kind (the README cites `wal-bloat-review`).
- Run Nightshift's existing MVP A pipeline against that finding in shadow mode.
- Verify Governor's verdict path emits the gate receipt.
- **Verify whether the receipt carries non-discharge information.** If it doesn't (per §4 item 3, it currently doesn't), this becomes the first concrete *code-level* docket item, scoped tightly: add `non_discharge: Optional[NonDischargeReport]` to `GateReceipt`, populated at gate.check().
- Stop. No remediation. No proposal upgrade beyond Advisory. No second specimen path until the first one is witnessed end-to-end.

---

## 7. What This Does NOT Prove

- **Does not** prove the MVP path works end-to-end. Identifies the path; tags status. Running the path is the next session.
- **Does not** ratify the seven Governor up-to-spec invariants as currently encoded. Items 2, 3, 5 have known gaps or sketched-only encoding.
- **Does not** verify NQ → Nightshift shape contract end-to-end. Test names imply structure; conversion code not deep-read this pass.
- **Does not** verify Nightshift MVP A pipeline is wired to production NQ + production Governor. Test names imply integration; production wiring not witnessed.
- **Does not** decide whether the future Rust kernel = Wicket-evolved or = sibling. Forcing case absent.
- **Does not** name a programmatic consumer for the receipt downstream of operator inspection. Deferred edge.
- **Does not** authorize any effectful write. Shadow mode hard fence.
- **Does not** propose new theory, new Lean kernel, new doctrine, or new project name.
- **Does not** include WLP. Correctly absent — shadow-mode single-host does not cross a wire boundary.
- **Does not** become the docket. Surfaces candidates (the next-admissible action above; the three sketched-or-missing up-to-spec items; the deferred Receipt → Consumer edge; the open Rust kernel ambiguity). Docket is a separate triage pass.

---

## Provenance

Filed 2026-06-09. Inputs:

- Multi-session planning trail (2026-06-08): "knit ugly" packet + Governor-as-carrier consolidation + Damocles framing + project-custodian preflight.
- Direct reads this pass: agent_gov README, NQ README, Nightshift README, Wicket README + module listing, WLP README, agent_gov `gate_receipt.py` head, Nightshift Rust source greps for `Governor`, Nightshift test file listing.
- Memory pointers used (not re-witnessed this pass): NQ classification SECRET marker, Linear Accountant frozen/needs-consumer, Lean custody class scheme, Receipt Kernel constitutional invariants count.

The doc is ugly. Both arms may be on the same side. That is allowed. Unwitnessed elegance is how the goblin gets in.
