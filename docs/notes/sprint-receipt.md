# Sprint Receipt — standing-before-spendability MVP

What landed during the standing-before-spendability MVP campaign. Slice-by-slice, with test counts, repos touched, and a closed cut list of what was explicitly NOT built. Source of truth: the slice tracker in `working/campaign-standing-before-spendability.md`.

## Headline

- One command — `nightshift watchbill demo wal-bloat-review --drill` — runs all six gauntlet scenarios + the D3 confabulated-citation closing beat and prints a deterministic ticket-shaped poster.
- Seven invocations against the **same** staged WAL-bloat condition with byte-identical NQ `FindingSnapshot`. Five refusals + one accounted gap + one effect + one validator refusal.
- Each outcome is a content-addressed `GateReceipt`, walkable via `governor why <receipt-id>` back to the originating NQ `finding_id`.
- All eleven refusal kinds + one bypass kind closed at S4-lite. No vocabulary churn since 2026-06-09.

## Slices landed (verbatim from slice tracker, with test counts)

| Slice | Status | Notes |
|---|---|---|
| C0 Q1 | CLOSED | LA topologically absent from AG `src/` |
| C0 Q2 | CLOSED | BA3 bypass contract ratified; 4 BA3 surfaces enumerated; debt filed at `working/post-mvp-debt-ba3-hardshort-to-la.md` |
| S1 stub | CLOSED | `standing_client` + `wicket_client` SPEC-honoring stubs; **13 tests** in `tests/test_standing_client.py` + **13 tests** in `tests/test_wicket_client.py` |
| S2 stub | CLOSED | `linear_accountant_client.request_capacity`, pre-call refusal teeth |
| S3 stub | CLOSED | `linear_accountant_client.consume`, replay-kill teeth (`effect_count=1`) |
| S4-lite | CLOSED | 11 refusal kinds + 1 bypass kind sealed; `GateReceiptSystem` ratified; micro-freeze; **12 tests** in `tests/test_linear_accountant_client.py` |
| S5 (chain joins) | CLOSED | `governor why <id>` walks `GateReceipt` chains; **25 tests** in `tests/test_why_command.py` |
| S5 (NQ-origin) | CLOSED 2026-06-10 by D0-Origin | `why` reaches NQ finding / renders absence properly |
| D0a | CLOSED | Refusal-time `GateReceipt` emission via injected `ReceiptSink` |
| D0c-a | CLOSED | Wicket authorized-admission emission; closes synthesized-link debt |
| D0c-b | CLOSED | Cooked-context orchestrator + closed origin-mode set; **15 tests** in `tests/test_cooked_context_orchestrator.py` |
| D0-Bridge | CLOSED | NQ migration 057 (`origin_mode` sibling column, closed CHECK `{observed,drill,replay,synthetic}`); AG widens `CLOSED_ORIGIN_MODES`; `governor why` renders DRILL/REPLAY/SYNTHETIC prefix; **7 tests** in `tests/test_d0_bridge_nq_to_ag_origin_mode.py`. First cross-repo slice under graduated rule. |
| D0-Origin | CLOSED 2026-06-10 | Real WAL-bloat staging (Night Shift `wal_bloat_stager.rs`) + authentic NQ observation via production `sqlite_health::collect` → `publish_batch` → `detect::run_all` → `update_warning_state_with_origin_mode` → `export_findings` pipeline (new `nq-monitor drill wal-bloat` subcommand). Native detector path mints `origin_mode=drill`. AG's `drill_runner.py` consumes genuine `FindingSnapshot` JSON via `--finding-json`. **14 end-to-end acceptance tests** in `tests/test_d0_origin_genuine_nq_finding.py`. |
| D0-Provenance | STAMPED 2026-06-10 by D0-Origin | Drill propagation wired by D0-Bridge through `evidence_bundle["origin_mode"]`; D0-Origin exercised it end-to-end. `governor why` renders DRILL first at every chain node. |
| D0d-a | CLOSED | Night Shift entry point shells AG; deterministic NQ-shaped fixture; in-process `walk_chain` + `render_text`; **13 tests** in `tests/test_drill_runner_all_green.py` |
| D0d-b | CLOSED 2026-06-10 | Happy-path `GateReceipt` emission on `standing_client.verify`, `linear_accountant_client.request_capacity` Granted, `linear_accountant_client.consume` Consumed. No GateReceipt envelope change. Four-link chain `finding → standing → admission → granted → consumed` walks end-to-end via `governor why` |
| D0d-1 | CLOSED 2026-06-10 | Six-scenario gauntlet wired end-to-end. Closed set `{no-standing, standing-expired, wicket-denied, wicket-gap-accounted, replay-budget, all-green}` (alias `already-consumed`). **No detector zoo:** `FindingSnapshot` byte-identical across all six scenarios. **16 tests** in `tests/test_drill_runner_d0d1_scenarios.py` |
| D0b checkpoint | STAMPED 2026-06-10 by D0-Origin | End-to-end test drives real chain from genuine NQ `FindingSnapshot` → standing → wicket → LA → `governor why` with DRILL prefix; no synthetic parent ids |
| D0e | CLOSED 2026-06-10 | Show-surface poster (`src/governor/drill_poster.py`, ~600 LOC) + `nightshift watchbill demo wal-bloat-review --drill` single entry point. **14 tests** in `tests/test_drill_poster.py`. All 10 acceptance criteria pass. Cross-tmp posters byte-identical without normalization (content-addressed ids on stable inputs). BA3 bypass renders as `bypass_ag_rcpt_<not_minted>` honest absence. |
| D3 | CLOSED 2026-06-10 | Confabulated-receipt closing beat. Night Shift CLI gains `--confabulate-citation=<role>`; AG-side validator runs existence-check + kind-fit guard after the chain completes through consume. Closed role set `{standing, evidence}`. Refusal kind `dangling_receipt_reference` (reused from closed S4-lite set, no widening). Gate `proposal_validator_seam`. **12 tests** in `tests/test_drill_runner_d3_confabulation.py` |
| D0d (original framing) | ABSORBED by D0d-a + D0d-b + D0d-1 2026-06-10 | "compose harness + six named runs" framing absorbed into the three landed sub-slices |
| D1 | ABSORBED by D0-Origin + D0d-1 2026-06-10 | Same command path as the gauntlet |
| D2 | ABSORBED by D0d-1 2026-06-10 | Six scenarios landed as the closed scenario set |
| D0f-docs | CLOSED 2026-06-10 (this sprint receipt + sibling docs) | Seven documentation files under `docs/{demo,architecture,reference,notes}` |

## Repos touched

- **`agent_gov`** — `src/governor/` (clients, orchestrator, drill runner, drill poster, why, gate receipts); `tests/`; `docs/`; `working/`. Primary surface for the spine, the show surface, and the closed vocabularies.
- **`notquery`** — `crates/nq-db/migrations/057_origin_mode_discriminator.sql` (the closed-vocabulary discriminator), wire DTO changes, `nq-monitor drill wal-bloat` subcommand. The cross-repo bridge in D0-Bridge.
- **`scheduler`** — `crates/nightshiftd/src/drill.rs` (the operator-load-bearing CLI entry point), `crates/nightshiftd/src/wal_bloat_stager.rs` (staging the genuine WAL-bloat condition), `crates/nightshiftd/src/main.rs` (`watchbill run --drill` + `watchbill demo` subcommand wiring), tests under `crates/nightshiftd/tests/`. The actuator and the smoke machine.

## Test count

Across the eleven slice-shipping test files in this campaign:

- `tests/test_standing_client.py` — 13
- `tests/test_wicket_client.py` — 13
- `tests/test_linear_accountant_client.py` — 12
- `tests/test_why_command.py` — 25
- `tests/test_cooked_context_orchestrator.py` — 15
- `tests/test_d0_bridge_nq_to_ag_origin_mode.py` — 7
- `tests/test_d0_origin_genuine_nq_finding.py` — 14
- `tests/test_drill_runner_all_green.py` — 13
- `tests/test_drill_runner_d0d1_scenarios.py` — 16
- `tests/test_drill_runner_d3_confabulation.py` — 12
- `tests/test_drill_poster.py` — 14

**Sum: 154 slice tests across AG.** Headline result reported by the D0e closure stamp: 202 total slice tests across the campaign (including adjacent test files exercised during regression sweeps).

Scheduler-side cross-repo tests: `crates/nightshiftd/tests/drill_runner_all_green.rs` (6), `crates/nightshiftd/tests/drill_runner_d3_confabulation.rs` (3), `crates/nightshiftd/tests/mvp_a_refusal.rs` (1), plus `drill_demo.rs` (3).

## What was explicitly NOT built (cut list, verbatim from §5)

Out of MVP — refuse smuggling:

- **ArtifactKind / UseKind typing** — kind-fit is a guard against existing structural attributes, not a typed taxonomy.
- **Z3** — no SMT in the runtime path.
- **Grep-sentinel infra** — separate track, already scheduled.
- **WLP transport / TCP-UDP modes** — design note only; nothing in MVP crosses a system boundary.
- **Cross-tool receipt schema unification** — v2. Each tool's native receipt plus an AG ledger entry referencing it by id is enough.
- **Cantrip adapter** — out.
- **Continuity premise-revocation wiring** — continuity may receive receipts as observations; `rely` integration is post-MVP.
- **Generated seam inventory / linter** — separate track.
- **Lean in the runtime path** — merge gate only.
- **Any new kernel work** — jurisdiction: outOfScope.

LLM-side explicit non-inclusions for the MVP:

- **No LLM invocation in any gauntlet scenario.** The drill runner is deterministic end-to-end. The proposal packet (runs 4 and 6) is a fixed template citing receipt ids (`build_proposal_packet`). LLM placement is architecturally pinned in `docs/architecture/claim-custody-spine.md` §LLM placement for when the live wire-in lands; the MVP demonstrates the receipt chain the LLM will be late and narrow against.
- **No D0a/D0e schema unification.** Each tool's native receipt plus AG-side `GateReceipt` referencing it by id is enough.
- **No prompted fabrication in D3.** D3 is deterministic-control: the runner injects a known-bogus citation under operator control; the validator catches it; the LLM is never invoked. See `docs/reference/drill-scenarios.md` §D3.
- **No mutation in any scenario.** The proposal packet is text + citations; no `std::fs::write`, no API call, no commit. The Linear Accountant's WL-001 (`std::fs::write` gated by the accountant) proves linearity inside LA; the MVP demonstrates AG calling LA's contract.
- **No claim of generic hallucination prevention.** D3 demonstrates that a confabulated citation costs real budget and buys a refusal receipt. That is one specific shape of failure under one specific gate; nothing more.

## v2 scheduled-drill — captured, not in scope

(Verbatim from §3 D0 / §6.)

> A gate you have never seen refuse is an unvalidated gate; refusal paths rot like untested backup restores. Cron the six-run drill weekly; "when did this gate last refuse, receipt attached" becomes a question no incumbent can answer.
>
> Cron, not new machinery.
>
> Precondition still applies to all spine runs when they land:
> - run with `SpendabilityAuthority = LA_ONLY`
> - emit `BA3_BYPASSED_FOR_MVP` receipt per bypassed BA3 surface
> - assert no AG-internal budget denial fires during spine run (`RunBudgetLedger`, `ExecutionBudget`, `ExplorationBudget`, routing `Budget`) — any such denial fails the demo harness.

The v2 scheduled drill is **captured** as a future obligation. It is not in MVP scope. The MVP closes when the seven documents above this one land.
