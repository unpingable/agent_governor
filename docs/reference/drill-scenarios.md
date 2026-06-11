# Drill Scenarios

> **The model may propose; it may not mint standing, admit itself, spend twice, or cite what was never witnessed.**

This document enumerates the closed scenario set the drill runner accepts. Eight gauntlet scenarios (the original six + the temporal-lapse PAIR, ratified 2026-06-12) + the D3 confabulated-citation closing beat. Closed at construction (`drill_runner.SUPPORTED_SCENARIOS` and `CONFABULATION_ROLES`); unknown scenarios raise `UnsupportedScenarioError` / `InvalidConfabulationRoleError` rather than silently substituting.

Every scenario runs against the **same** NQ `FindingSnapshot` — byte-identical across all scenarios per `tests/test_drill_runner_d0d1_scenarios.py::test_finding_snapshot_byte_identical_across_all_scenarios` (parametrized over the full `SUPPORTED_SCENARIOS`). There is no detector zoo. Only the AG-side gate state varies; the workload (the genuine WAL-bloat finding) stays the same. The temporal-lapse pair adds no new finding — it varies only the two-clock window the standing-spendability gate evaluates.

## Closed scenario set

(Verbatim from `src/governor/drill_runner.py::SUPPORTED_SCENARIOS`. Operator-ratified alias `already-consumed` resolves to `replay-budget` via `SCENARIO_ALIASES`.)

```
no-standing
standing-expired
wicket-denied
wicket-gap-accounted
replay-budget          (alias: already-consumed)
all-green
temporal-lapse         (standing-spendability gate refuses: standing lapsed past horizon by exercise time)
temporal-lapse-twin    (the legitimate twin: same gauntlet, exercise within horizon, consumes)
```

D3 confabulation is a flag (`--confabulate-citation`) layered on top of `all-green`, with a closed role set:

```
standing               (existence-fail target)
evidence               (kind-fit-fail target)
```

## Per-scenario table

| Scenario | Refusing gate | Refusal kind | Outcome class | Test witness |
|----------|---------------|--------------|---------------|---------------|
| `no-standing` | `standing_seam` | `standing_required` | `refused` | `tests/test_drill_runner_d0d1_scenarios.py:58` `test_scenario_1_no_standing_refuses_at_standing_seam` |
| `standing-expired` | `standing_seam` | `standing_expired` | `refused` | `tests/test_drill_runner_d0d1_scenarios.py:79` `test_scenario_2_standing_expired_refuses_at_standing_seam` |
| `wicket-denied` | `la_seam` (admission verifier rejects) | `admission_denied` | `refused` | `tests/test_drill_runner_d0d1_scenarios.py:102` `test_scenario_3_wicket_denied_refuses_at_la_seam` |
| `wicket-gap-accounted` | (chain proceeds) | `admission_gap_accounted` | `accounted_gap` | `tests/test_drill_runner_d0d1_scenarios.py:123` `test_scenario_4_wicket_gap_accounted_proceeds_with_gap_citation` |
| `replay-budget` | `la_seam` (second consume) | `already_consumed` | `already_consumed` | `tests/test_drill_runner_d0d1_scenarios.py:151` `test_scenario_5_replay_budget_kills_second_consume` |
| `all-green` | (chain completes) | — | `effect` | `tests/test_drill_runner_d0d1_scenarios.py:177` `test_scenario_6_all_green_consumes_with_proposal_packet` |
| `temporal-lapse` | `standing_spendability_seam` | `standing_before_spendability_not_bounded` | `refused` | `tests/test_drill_temporal_lapse.py` `test_lapse_refuses_at_spendability_seam_without_spending` |
| `temporal-lapse-twin` | (chain completes) | — | `effect` | `tests/test_drill_temporal_lapse.py` `test_twin_runs_identical_gauntlet_to_a_real_consume` |
| D3 `confabulate-citation=standing` | `proposal_validator_seam` | `dangling_receipt_reference` (`citation_check="existence"`) | `validator_refused` | `tests/test_drill_runner_d3_confabulation.py:60` `test_d3_existence_fail_emits_dangling_receipt_reference_refusal` |
| D3 `confabulate-citation=evidence` | `proposal_validator_seam` | `dangling_receipt_reference` (`citation_check="kind_fit"`) | `validator_refused` | `tests/test_drill_runner_d3_confabulation.py:105` `test_d3_kind_fit_fail_distinguishes_from_existence_fail` |

## Per-scenario harness assertions

The temporal-lapse pair is in the closed scenario set and the golden corpus (`golden/corpus/08-temporal-lapse-refused.json`, `09-temporal-lapse-twin-passes.json`) but is **not yet in the D0e show-surface poster** below — wiring the hero specimen into the poster is W1 item 3 (refused-spend script + show surface). The poster's "seven invocations" remain the original six + D3.

In addition to the per-scenario tests above, the show-surface poster asserts six aggregate invariants over all seven invocations (`src/governor/drill_poster.py::_evaluate_assertions`):

1. `no BA3 denial fired during any spine run` — no emitted receipt anywhere carries `refusal_kind == BYPASS_BA3_FOR_MVP`. Detector: `_detect_ba3_denial_with_root`.
2. `FindingSnapshot byte-identical across all six scenarios (no detector zoo)` — JSON-canonical serialization of the finding is identical across runs 1–6.
3. `run 4 proposal carries gap_receipt_id + produced_under_gap=true` — verified against `run4.proposal_packet`.
4. `run 5 replay: second consume → AlreadyConsumed; effect_count = 1` — verified against `run5.refusal_kind` and `run5.effect_count`.
5. `D3 confabulated citation → dangling_receipt_reference; validator effect_count = 1; mutation refused` — verified against the D3 run's `refusal_kind`, `refusing_seam`, `effect_count`, and empty `proposal_packet`.
6. `` `governor why` walks every chain back to NQ finding origin `` — every run's finding carries `origin_mode=drill`; every leaf receipt's evidence bundle inherits it.

## D3 — deterministic-control, not prompted fabrication

D3 is the confabulated-citation closing beat. It runs `--scenario=all-green` and **then** injects a single bogus citation into the proposal-packet step.

The chain runs to completion first:

1. `standing_seam` verifies — real receipt minted.
2. `wicket_seam` admits — real receipt minted.
3. `la_seam` grants — real receipt minted.
4. `la_seam` consumes — real receipt minted; `_EffectCounter` increments to 1; **real budget spent**.
5. `proposal_validator_seam` runs `_validate_standing_citation` against the cited id:
   - `confabulate-citation=standing` cites `BOGUS_STANDING_RECEIPT_ID` — a constant defined in `drill_runner.py` that no seam ever mints. The existence check fails. `citation_check = "existence"`.
   - `confabulate-citation=evidence` cites the real LA grant receipt id (which exists, but `gate="la_seam"` and the `verified_standing` marker is absent). The kind-fit check fails. `citation_check = "kind_fit"`.
6. The validator emits a `dangling_receipt_reference` refusal `GateReceipt` whose parent is the consume receipt; the proposal packet is **not** emitted; `effect_count` stays at 1.

The runner injects a known-bogus id under operator control via the `--confabulate-citation` flag (`src/governor/drill_runner.py::CONFABULATION_ROLES`). **The LLM is never invoked.** This is the deterministic-control mode described in `working/campaign-standing-before-spendability.md` §3b: every demo, every run, the validator fires reliably and reproducibly because the input is fixed.

A live mode (running the proposal step against an impoverished evidence bundle and reporting whether confabulation emerges) is documented in §3b as architectural intent; the MVP does not invoke it. Staging the model into fabrication "to make the demo work" would be the founding crime inside the demo — the same shape D0-Bridge was built to refuse.

## Refused-at-construction guarantees

The runner refuses at construction time rather than silently substituting:

- Unknown scenario name → `UnsupportedScenarioError`. (`tests/test_drill_runner_d0d1_scenarios.py:281` `test_unknown_scenario_raises_at_construction`.)
- Legacy D0d-a era names like `1_no_standing` / `6_all_green` → `UnsupportedScenarioError` (not aliased).
- `--confabulate-citation=<role>` with `<role>` outside `{standing, evidence}` → `InvalidConfabulationRoleError`. (`tests/test_drill_runner_d3_confabulation.py:376` `test_d3_invalid_role_raises_at_construction`.)
- `--confabulate-citation` paired with any scenario other than `all-green` → `InvalidConfabulationRoleError`. (`tests/test_drill_runner_d3_confabulation.py:387` `test_d3_confabulation_with_non_all_green_scenario_raises`.) Only `all-green` reaches the proposal-packet step.

The single normalization site for the `already-consumed` → `replay-budget` alias is `_canonical_scenario` in `drill_runner.py`; the same alias is accepted by Night Shift's CLI gate (`crates/nightshiftd/src/drill.rs::is_supported_scenario`).
