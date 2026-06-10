# WAL-Bloat Drill — Transcript

> **This demo is a drill. The condition is staged; the observation path is not. The system discloses that distinction in the receipt chain.**
>
> Ask the receipt.

This page reproduces the deterministic poster output of `nightshift watchbill demo wal-bloat-review --drill` together with representative `governor why <receipt-id>` excerpts. Every byte below is mechanically derived from `src/governor/drill_poster.py::render_poster` and `src/governor/why.py::render_text`. No model is invoked. The transcript is a render of the ledger.

## DRILL — what `origin_mode=drill` means *before* you read the transcript

The condition is staged. The WAL-bloat is real bytes on a real SQLite file (`crates/nightshiftd/src/wal_bloat_stager.rs::stage_wal_bloat`). The observation is real — Night Shift invokes `nq-monitor drill wal-bloat` against the staged sandbox, which runs NQ's production evaluator pipeline (`sqlite_health::collect` → `publish_batch` → `detect::run_all` → `update_warning_state_with_origin_mode` → `export_findings`). NQ mints a real `FindingSnapshot` JSON via the native detector path.

What makes this a drill is **not** a fake observation — it is the `origin_mode=drill` discriminator stamped at mint, carried verbatim on the wire, and inherited by every downstream `evidence_bundle` via `_OriginModeReceiptSink` in `src/governor/cooked_context_orchestrator.py`. NQ migration 057 (`~/git/notquery/crates/nq-db/migrations/057_origin_mode_discriminator.sql`) defines the closed-vocabulary CHECK `{observed, drill, replay, synthetic}`. AG admits those four values verbatim.

`governor why <receipt-id>` renders `DRILL` first on every chain it walks. If the chain's `origin_mode` were `observed`, the prefix would be absent — and that absence would be the only difference between a drill chain and a production chain at this layer.

A drilled chain that is not stamped DRILL would be witness-layer laundering. See `docs/architecture/origin-mode.md`.

## The poster — captured

This is the literal output of `python3 -m governor.drill_poster --root <tmp> --format text`, byte-for-byte:

```
═══════════════════════════════════════════════════════════════════
  AG MVP Demo: Refusal Is a Product Surface
  Incident: WAL bloat review — DRILL
═══════════════════════════════════════════════════════════════════

SpendabilityAuthority: LA_ONLY
Bypassed AG-internal budget guards [BA3 — POST-MVP DEBT]:
  - RunBudgetLedger        bypass_ag_rcpt_<not_minted>
  - ExecutionBudget        bypass_ag_rcpt_<not_minted>
  - ExplorationBudget      bypass_ag_rcpt_<not_minted>
  - routing Budget         bypass_ag_rcpt_<not_minted>

───────────────────────────────────────────────────────────────────
  Six runs, one drill condition, byte-identical NQ finding
───────────────────────────────────────────────────────────────────

  #  Scenario                       Outcome                                                 Receipt
  ─  ────────                       ───────                                                 ───────
  1  no-standing                    refused                                                ag_rcpt_f163894842b52689
  2  standing-expired               refused                                                ag_rcpt_fab31654e129531d
  3  wicket-denied                  refused                                                ag_rcpt_6e302b9a5a5febcb
  4  wicket-gap-accounted           ↷ accounted_gap                                        ag_rcpt_2f8d461bc9bdf930
  5  replay-budget                  already_consumed                                       ag_rcpt_b2d85d5500c65e2b
  6  all-green                      effect                                                 ag_rcpt_2f8d461bc9bdf930
  ─────────────────────────────────────────────────────────────────────────────────────────
  D3 confabulated-citation          validator_refused (dangling_receipt_reference)         ag_rcpt_ca7cb285759f50e6

  DRILL  origin_mode=drill minted at NQ; inherited by every downstream receipt; visible at every node via `governor why <receipt-id>`.

───────────────────────────────────────────────────────────────────
  Harness assertions
───────────────────────────────────────────────────────────────────

  ✓ no BA3 denial fired during any spine run
  ✓ FindingSnapshot byte-identical across all six scenarios (no detector zoo)
  ✓ run 4 proposal carries gap_receipt_id + produced_under_gap=true
  ✓ run 5 replay: second consume → AlreadyConsumed; effect_count = 1
  ✓ D3 confabulated citation → dangling_receipt_reference; validator effect_count = 1; mutation refused
  ✓ `governor why` walks every chain back to NQ finding origin
```

## Reading the poster

- The four bypass lines under **SpendabilityAuthority: LA_ONLY** are not refusals. They are **honest absence** — the four BA3 surfaces (`RunBudgetLedger`, `ExecutionBudget`, `ExplorationBudget`, routing `Budget`) are not wired into the drill path at all. `bypass_ag_rcpt_<not_minted>` is the operator-default placeholder per the "default to (a)" rule in `src/governor/drill_poster.py::BA3_BYPASS_PLACEHOLDER`. Adding real BA3 emission paths is post-MVP debt (`working/post-mvp-debt-ba3-hardshort-to-la.md`); see `docs/reference/refusal-and-outcome-vocabulary.md` §BA3.
- Receipt ids are content-addressed (`src/governor/gate_receipt.py::receipt_id`); identical inputs reproduce identical ids. Cross-tmp poster invocations produce byte-identical ticket tables.
- The harness assertion line `no BA3 denial fired during any spine run` is the operator-load-bearing invariant from C0-resolved: any AG-internal BA3 denial during a spine run **fails the demo**. The detector is `_detect_ba3_denial_with_root` in `src/governor/drill_poster.py`.

## D3 — closing beat (reproduced exactly)

The D3 row is the confabulated-citation closing beat. It runs `--scenario=all-green --confabulate-citation=standing`. The chain reaches `Consumed`; `_EffectCounter` increments to 1; **then** the proposal-validator seam validates citations and detects that `BOGUS_STANDING_RECEIPT_ID` (defined in `src/governor/drill_runner.py`) was never minted by any seam in the chain. The validator emits a `dangling_receipt_reference` refusal receipt; the proposal packet is **not** emitted; `effect_count` stays at 1.

The receipt id printed for D3 in the poster (`ag_rcpt_ca7cb285759f50e6` in this capture) is the validator-emitted refusal receipt itself, not a forged standing receipt. `governor why` on that id walks the refusal → consume → grant → admission → standing chain. The bogus cited id is surfaced in the evidence bundle under `bogus_cited_id`; calling `governor why` on the bogus id renders absence via the existing S5 unknown-receipt path (`tests/test_drill_runner_d3_confabulation.py::test_d3_governor_why_on_bogus_citation_renders_absence_not_traceback`).

D3 is **deterministic-control**, not prompted fabrication. The runner injects a fixed bogus id under operator control; the LLM is not invoked. See `docs/reference/drill-scenarios.md` §D3 and `docs/architecture/claim-custody-spine.md` §LLM placement.

## Sample `governor why <receipt-id>` excerpts

### Happy-path leaf (run 6, all-green)

Captured from `python3 -m governor.drill_runner --scenario=all-green` (transcript normalized — `<rcpt:N>` placeholders stand in for the content-addressed receipt-id prefixes; `<finding_id>` is the NQ finding key URL-encoding-stable):

```
why <rcpt:4>
──────────────────────
DRILL  chain origin: 'drill' (NQ-side mint provenance — receipt does NOT carry an observed-condition witness)
──────────────────────
OK       verdict=pass  gate=la_seam  id=<rcpt:4>...
  OK       verdict=pass  gate=la_seam  id=<rcpt:3>...
    OK       verdict=pass  gate=wicket_seam  id=<rcpt:2>...
      OK       verdict=pass  gate=standing_seam  id=<rcpt:1>...
        MISSING  no receipt found for cited id <finding_id>
          ! no receipt found for cited parent <finding_id>; chain terminates at this gap
```

The four `OK verdict=pass` lines are the four real `GateReceipt`s minted on the chain. The `MISSING` terminal line is the chain reaching the NQ `finding_id` — there is no AG-side receipt for the NQ finding (NQ owns its own receipts), so the walk renders absence honestly rather than synthesizing a parent. The DRILL prefix at the top is the closed-vocabulary render from `src/governor/why.py::NON_OBSERVED_RENDER_PREFIX`.

### Terminal refusal (run 1, no-standing)

A refusal leaf renders the same shape, with `REFUSED` in place of `OK` and the closed-vocabulary `refusal_kind` printed alongside the gate (see `src/governor/why.py::_classify_link` + S5 tests at `tests/test_why_command.py`). The walk terminates at the seam that refused; downstream gates are never invoked, so the chain has no further parents past the refusing seam's own receipt.

### Confabulated citation (D3)

`governor why <D3 refusal receipt id>` walks back through `proposal_validator_seam` → `la_seam (consumed)` → `la_seam (granted)` → `wicket_seam` → `standing_seam` → NQ `finding_id` (`MISSING`). `governor why <bogus_cited_id>` renders `receipt id not found` — not a traceback. The closed S5 absence-rendering path handles both.

## Provenance of this transcript

- Captured by running `python3 -m governor.drill_poster --root /tmp/d0f-docs-poster-snapshot --format text` on 2026-06-10 against this repository's `main` branch.
- `governor why` excerpts captured by running `python3 -m governor.drill_runner --root /tmp/d0f-docs-why-snapshot --scenario all-green` and reading the embedded walk from the JSON envelope's `transcript` field; the walk renders are identical to invoking the CLI on the same receipt ids.
- Determinism is mechanically guaranteed by content-addressed receipt ids (`src/governor/gate_receipt.py`) and the transcript normalizer (`src/governor/drill_runner.py::_normalize_transcript`). Re-running on a fresh tmp directory produces a byte-identical poster.
