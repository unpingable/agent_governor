# Standing Before Spendability — the AG MVP Demo

> **The model may propose; it may not mint standing, admit itself, spend twice, or cite what was never witnessed.**

> This demo is a drill. The condition is staged; the observation path is not.
>
> **Refusal is the product. The happy path is the control group.**
>
> Ask the receipt.

---

## One-command demo

```
nightshift watchbill demo wal-bloat-review --drill
```

Night Shift owns the operator entry point (`crates/nightshiftd/src/drill.rs::run_demo_command`). It shells AG's `python3 -m governor.drill_poster` and prints the deterministic ticket-shaped poster on stdout. Exit code is nonzero iff any harness assertion fails.

The poster runs **seven invocations** against the same staged WAL-bloat condition:

- the six closed-set gauntlet scenarios in `src/governor/drill_runner.py::SUPPORTED_SCENARIOS`,
- the D3 confabulated-citation closing beat (`--confabulate-citation=standing` on top of the all-green chain).

Each scenario writes receipts through the real `GateReceiptSystem` (`src/governor/gate_receipt.py`) into its own per-scenario subdirectory under `$TMPDIR/nightshift-demo-wal-bloat-review/`. Any of those receipts can be walked with:

```
governor why <receipt-id>
```

## The poster — six runs, one effect, one closing beat

| # | Scenario | Outcome | Refusing gate (when refused) |
|---|---|---|---|
| 1 | `no-standing` | `refused` | `standing_seam` |
| 2 | `standing-expired` | `refused` | `standing_seam` |
| 3 | `wicket-denied` | `refused` | `la_seam` (admission verifier rejects) |
| 4 | `wicket-gap-accounted` | `↷ accounted_gap` | (chain proceeds with gap citation) |
| 5 | `replay-budget` | `already_consumed` | `la_seam` (second consume) |
| 6 | `all-green` | `effect` | (chain completes; proposal packet emitted) |
| D3 | `confabulated-citation` | `validator_refused (dangling_receipt_reference)` | `proposal_validator_seam` |

The six rows above the divider are the gauntlet. The seventh is the closing beat. Every outcome word in the table is drawn from the closed five-class outcome vocabulary in `src/governor/drill_poster.py::CLOSED_POSTER_OUTCOMES`. Nothing else is admitted.

## Outcomes, explained against ratified vocabulary

The closed outcome classes (from `src/governor/drill_poster.py`):

- **`refused`** — a gate refused before its callable was invoked, or the verifier of an upstream input rejected. Downstream call-count is zero past the refusing gate. The refusing seam emitted a `GateReceipt` whose `refusal_kind` is drawn from the eleven closed kinds in `src/governor/linear_accountant_client.py::CLOSED_REFUSAL_KINDS`.
- **`accounted_gap`** — wicket admission was incomplete in a way that maps to `admission_gap_accounted` (S4-lite). The chain **proceeds**. The proposal packet carries `gap_receipt_id` and `produced_under_gap=true`, citing the gap receipt verbatim. Run 4 is the only scenario in the gauntlet that demonstrates this; it is **not** a refusal and is not success-washed — the chain ran under acknowledged, receipted epistemic debt.
- **`already_consumed`** — LA's `ConsumptionDecision::AlreadyConsumed` fired on the second consume call with the same `consumption_event_id`. The downstream effect counter stays at 1; the second spend is refused; replay is dead.
- **`effect`** — the chain reached `Consumed` and emitted a deterministic proposal packet. **There is no `✓ effect` glyph**; the codex Phase 1 vocabulary review removed it because "success" is the control group, not the product. Effect is a noun here, not a check mark.
- **`validator_refused`** — the D3 proposal-validator seam refused a citation. In this demo the kind is always `dangling_receipt_reference` (the validator existence-check found no minted receipt at the cited id). The chain had already consumed budget; the failed citation cost real spendability before refusal landed.

## What "refusal is the product" means

Five of the seven invocations end in refusal. That is intentional. The thing the demo is selling is the **shape of refusal**:

- every refusal names its own gate (`standing_seam`, `wicket_seam`, `la_seam`, `proposal_validator_seam`);
- every refusal mints a content-addressed `GateReceipt` whose `evidence_bundle` carries the closed-vocabulary `refusal_kind` and a `parent_receipt_ids` link back through the chain;
- every refusal can be walked back to the originating NQ finding via `governor why <receipt-id>`;
- downstream callables past a refusing gate are invoked **zero times** (the test suite asserts the call count; see `tests/test_drill_runner_d0d1_scenarios.py`).

A system that merely logs "I would have refused, but I let it through" is not a refusal system. The receipts are the product because they are the only artifact a stranger can verify after the fact.

## What the happy path proves and does not prove

Run 6 (`all-green`) reaches `effect` and emits a deterministic proposal packet. That run **proves**:

- the chain composes — `standing_seam` → `wicket_seam` → `la_seam (granted)` → `la_seam (consumed)` produces four real receipts in the order the SPECs predict;
- the proposal-packet step is reachable when, and only when, the four prior gates allow it;
- `governor why <leaf>` walks four real `GateReceipt`s back to the NQ `finding_id` (no synthetic parents).

That run **does not prove**:

- that hallucination has been "prevented" — the system carries no such claim; the LLM is not invoked in the gauntlet runs at all (see `docs/architecture/claim-custody-spine.md` §LLM placement);
- that any mutation happened — the proposal packet is a citation-bearing text payload (`src/governor/drill_runner.py::build_proposal_packet`), not a write;
- that the staged condition was discovered by AG — the WAL-bloat condition was staged by `crates/nightshiftd/src/wal_bloat_stager.rs` and observed by NQ's production evaluator pipeline. The drill makes the condition; the observation path is unchanged from production.

## DRILL provenance

Every receipt in every run inherits `origin_mode=drill` from the NQ `FindingSnapshot`. The discriminator was minted by NQ migration 057 (`~/git/notquery/crates/nq-db/migrations/057_origin_mode_discriminator.sql`), survives the wire DTO verbatim, and is stamped onto every emitted `evidence_bundle` by `_OriginModeReceiptSink` in `src/governor/cooked_context_orchestrator.py`. `governor why` renders `DRILL` first on every node walked.

See `docs/architecture/origin-mode.md` for the full discriminator semantics. See `docs/demo/wal-bloat-drill-transcript.md` for the captured ticket output and `why` excerpts.

## Ask the receipt

Every claim above is grounded in a specific receipt id printed in the poster. To verify any outcome, pick its receipt from the poster table and run:

```
governor why <receipt-id>
```

The output is a deterministic render of the chain back to the originating NQ `finding_id`, including the closed-vocabulary `refusal_kind` (where applicable), the bypass markers for the four BA3 surfaces, and the `DRILL` prefix on every link. No narration. No model. The renderer is `src/governor/why.py::render_text`, called by the CLI binding in `src/governor/cli.py`.
