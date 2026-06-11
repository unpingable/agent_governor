# Witness: Gate Receipt Missing Unsettled Surface

**Filed:** 2026-06-09. **Scope:** one witness pass; not a fix. Follows the next-admissible action committed in [`nightshift-integration-sweater.md`](nightshift-integration-sweater.md).

## What was witnessed

**Schema gap is captured in artifact.** `gate_receipt.py` schema v3 emits receipts with no field in the `unsettled / non_discharge / unresolved / refuse / non_*` family. Witnessed comprehensively:

- 1,165 receipts in `~/git/agent_gov/.governor/receipts/gate_receipts.jsonl`
- Twelve distinct top-level fields across the entire history:
  `auth_method`, `evidence_hash`, `gate`, `policy_hash`, `principal_id`, `receipt_id`, `receipt_role`, `schema_version`, `subject_hash`, `tenant_id`, `timestamp`, `verdict`
- Zero matches for `unsettled`, `discharge`, `unresolved`, `refuse`, `non_*` across any receipt
- Representative v3 fixture: [`fixtures/witness-receipt-2026-06-09.json`](fixtures/witness-receipt-2026-06-09.json) (gate=`context_build`, verdict=`observe`, role=`measurement`)

The receipt can say *"this receipt played role X over subject/evidence/policy Y."* It cannot say *"this verdict does not authorize Z, does not settle A, does not convert B into C."*

## What was NOT witnessed (and why)

**The MVP path NQ → Nightshift → Governor → Receipt did not run end-to-end this pass.** Discovery sharpened the sweater's `sketched` tag on the Nightshift → Governor edge:

- `nightshiftd/src/pipeline.rs:323`: `governor: Option<&dyn GovernorClient>` — Governor is *optional* in the pipeline. No-Governor mode is first-class, not an oversight.
- Existing test surface bifurcates:
  - `closure_candidate.rs` runs `run_watchbill` against the `wal-bloat-review.yaml` fixture **without** Governor.
  - `governor_rpc_live.rs` exercises Nightshift → Governor RPC for `record_receipt` only, env-gated by `NIGHTSHIFT_GOVERNOR_SOCKET`.
  - No single test crosses the whole seam (NQ source → watchbill pipeline → GovernorClient → emitted gate receipt).
- The 1,165 existing receipts are from Governor's own gates (`context_build`, `stability_probe`, etc.), not from Nightshift-driven flows.

Per the three-state wiring rule:

> **built** = code path ran and emitted artifact
> **witnessed** = test/specimen proves boundary behavior
> **asserted** = comment, assumption, or human interpretation

The Nightshift → Governor edge is now `asserted` for wiring purposes, not `sketched`. Pipeline accepts a `GovernorClient`; no captured artifact proves the full path executes.

Running the full E2E specimen would require either (a) env-gating + Governor daemon spin-up + new test wiring `run_watchbill` with a `GovernorClient`, or (b) extending an existing test. Both are code-change moves and out of scope this pass per the no-"while we're here" discipline.

## CORRECTION (2026-06-09, same day, next slice)

The "Nightshift → Governor edge is asserted-for-wiring" claim above is **wrong**. A second sweep against the next-slice instruction discovered the seam witness already exists:

- `~/git/scheduler/crates/nightshiftd/tests/horizon_packet_state.rs` — 6 passing tests including `defer_makes_governor_receipt_observable_in_packet_and_ledger`. Exercises the full path: `capture_phase` (loads agenda + NQ snapshot) → `reconcile_phase_with_horizon` (with `Some(FixtureGovernorClient)` and `Some(FixtureHorizonPolicySource)`) → `apply_horizon_outcomes` (which calls `governor.record_receipt`). Asserts the resulting `record_receipt` call is observable in both the packet and the ledger.
- `~/git/scheduler/crates/nightshiftd/tests/horizon_cross_run.rs` — 5 passing tests using the wal-bloat-review agenda id literally (`const TEST_AGENDA: &str = "wal-bloat-review"`). Asserts `"Defer emits exactly one record_receipt"` (line ~202).

Both test files pass on this checkout (verified by `cargo test`). The first sweater pass missed them because the survey focused on the `closure_candidate.rs` / `governor_rpc_live.rs` pair and didn't enumerate the `horizon_*` test family.

### Revised tag

Nightshift → Governor edge: **`witnessed`** (not `asserted-for-wiring`). Evidence: existing `horizon_packet_state::defer_makes_governor_receipt_observable_in_packet_and_ledger` + `horizon_cross_run::tolerated_active_continues_to_defer_before_expiry`. The seam crosses; record_receipt fires; the fixture captures the call.

### Subtler remaining gap

`run_watchbill` (top-level entry point — `nightshiftd/src/pipeline.rs:102`) does **not** take a `governor` parameter. Its delegate `run_watchbill_with_liveness` (`:118`) also doesn't. Both call `reconcile_phase` (`:290`), which passes `None` for both `horizon_policy` and `governor` to `reconcile_phase_with_horizon`. So:

- Pipeline crossing via `capture_phase` + `reconcile_phase_with_horizon` directly: **witnessed**.
- Pipeline crossing via `run_watchbill` (the public entry the CLI's `run_watchbill_cmd` likely uses): **structurally cannot cross** in current state — governor is not threaded through.

This is a real and narrower finding than "the seam is asserted." The seam crosses for direct pipeline-function callers; it does not cross for top-level `run_watchbill` callers because the parameter isn't there. Whether the CLI's `run_watchbill_cmd` constructs its own `JsonRpcGovernorClient` and calls the lower-level functions, or uses governor-blind `run_watchbill`, is the next thing to check — *not this session*.

### What this session did NOT do

- **Did not** write a new seam-witness test. The sword fired the other way: the test already exists; writing another would be padding.
- **Did not** investigate the CLI question (governor-blind `run_watchbill` vs. composed lower-level call). Docket candidate, not work this pass.
- **Did not** revise the sweater's broader tagging beyond this one edge. Other tags stand pending their own forcing-case inspection.

## What this licenses

One docket candidate, scoped tight, *not opened as work this pass*:

> Governor receipts must expose unsettled authority claims as typed non-discharge entries:
> - receipt field name: `unsettled`
> - item type: `NonDischargeClaim`
> - classification: closed `NonDischargeKind` enum (initial values: `AUTHORITY`, `EVIDENCE_SUFFICIENCY`, `FRESHNESS`, `SCOPE`, `STANDING`, `CONSUMER_RELIANCE`)
> - `reason: str` freeform only because it is prose-for-humans, not a matching key
> - new kinds require ratification, not ad-hoc strings (cf. C4 discipline on `Check.basis`)
> - schema bump `RECEIPT_SCHEMA_VERSION 3 → 4` because field addition changes the content-address surface

Justifying artifact: the captured fixture + this note.

## What this does NOT license

- **Patching the schema yet.** The witness justifies the docket item. The patch is its own pass with its own acceptance criteria (existing receipts still parse; new field optional during transition; content-address hash inputs adjusted).
- **Skipping the wiring witness.** Schema gap being captured does NOT make the Nightshift → Governor edge `witnessed`. That promotion still requires running the full path with Governor configured. Separate docket item.
- **Assuming Nightshift would emit `unsettled` correctly once Governor schema supports it.** Even with the field, Nightshift needs a code path that populates it on proposal evaluation. Third docket item.
- **Opening a consumer question.** Receipt → Consumer edge stays `asserted`. Frontier marker per the sweater. Premature without a worth-consuming receipt to point at.

## Provenance

Filed 2026-06-09 following the sweater's next-admissible-action commitment + the previous turn's three-state wiring rule. Directly read this pass:

- `~/git/agent_gov/src/governor/gate_receipt.py` (schema definition)
- `~/git/agent_gov/.governor/receipts/gate_receipts.jsonl` (1,165 emitted receipts; field-universe enumerated)
- `~/git/scheduler/crates/nightshiftd/src/pipeline.rs` (lines 33, 286, 323 — `GovernorClient` optionality)
- `~/git/scheduler/crates/nightshiftd/tests/closure_candidate.rs` (watchbill against wal-bloat-review fixture, no Governor)
- `~/git/scheduler/crates/nightshiftd/tests/governor_rpc_live.rs` (RPC test, env-gated, record_receipt only)
- `~/git/scheduler/tests/fixtures/wal-bloat-review.yaml` (existence confirmed; contents not deep-read)

No code changed. No schema patched. No tests written. No new specimens run.

Sword overhead. No effectful writes. No "while we're here."
