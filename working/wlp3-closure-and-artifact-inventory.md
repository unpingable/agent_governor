# WLP3 Closure + Artifact Inventory

**Filed:** 2026-06-09. **Status:** closure note for the freshness-unsettled refusal seam. Single retrievable receipt of the receipts. Read this first to land cold on the full path.

## The seam in one breath

Governor emits a v4 `GateReceipt` with `unsettled[freshness]`. Nightshift's packet displays a derived summary. MVP-A preserves both `ns_unsettled` and `governor_receipt_ids` into `transition.payload`. Wicket still classifies the packet (Intent + Outcome on disk). **NS refuses to mint a WLP `AuthorizationReceipt`** and emits `ns.wlp_refusal.v1` instead. The chain remains walkable; the warranty is intentionally absent.

## 1. What now happens on freshness-unsettled

End-to-end flow for a horizon-configured `watchbill` run where the horizon outcome is `Defer`:

```
NQ finding
  → Nightshift watchbill (--horizon-policy + --governor-socket)
  → reconcile_phase_with_horizon
  → apply_horizon_outcomes (Defer arm)
  → Governor record_receipt RPC
      → GateReceiptSystem.emit(unsettled=NonDischargeClaim{Freshness, ...})
      → v4 GateReceipt written to .governor/receipts/gate_receipts.jsonl
  → Nightshift packet built
      → packet.unsettled: Vec<UnsettledSummary> populated
      → packet.receipt_references.governor_receipts populated
      → packet YAML rendered: `unsettled:` block visible to operator
  → run_pipeline / MVP-A
      → cook_intent → Wicket Intent persisted
      → wicket::check → Wicket Outcome persisted
      → wlp3_refusal_triggering_kinds(packet) returns [Freshness]
      → write_wlp_refusal_artifact → ns.wlp_refusal.v1 persisted
      → skip wrap_authorization (no AuthorizationReceipt)
      → skip wlp::handle (no HandlingReceipt)
      → return MvpAResult::WlpAuthorizationRefused
  → CLI render arm prints the refusal summary to stderr
```

## 2. Artifacts that exist

| Artifact | Where | Carrying |
|---|---|---|
| Governor `GateReceipt` v4 | `.governor/receipts/gate_receipts.jsonl` | schema_version=4, receipt_role=authority, `unsettled: [{kind: "freshness", reason: ..., required_consumer?, required_witness?}]`, horizon block, content-addressed `receipt_id` (bound by unsettled hash) |
| Nightshift packet YAML | stdout from `watchbill run` (or persisted via run-ledger) | `receipt_references.governor_receipts: [<receipt_id>]`, `unsettled: [{kind, reason, receipt_id}]` (display summary) |
| NS posture packet | `ns-posture-{run_id}.json` | MVP-A NS-emitted posture packet (always emitted, both on cook + refuse paths) |
| Wicket Intent | `ns-wicket-intent-{run_id}.json` | NS-cooked Intent; classifies the packet successfully |
| Wicket Outcome | `ns-wicket-outcome-{run_id}.json` | Wicket's verdict on the Intent (classification surface preserved) |
| `ns.wlp_refusal.v1` | `ns-wlp-refusal-{run_id}.json` | reason_code, `unsettled_kinds: ["freshness"]`, `ns_unsettled` (full UnsettledSummary list), `governor_receipt_ids`, refs to Wicket Intent + Outcome paths, refused_at, nq_content_hash + nq_subject, ns_actor, ns_policy_ref |
| Golden fixture | `agent_gov/tests/fixtures/golden_traces/receipt_v4_with_unsettled.json` | frozen v4 receipt minted via the actual adapter path |

## 3. Artifacts intentionally absent on this path

| Artifact | Why absent |
|---|---|
| WLP `AuthorizationReceipt` (`ns-wlp-authorization-{run_id}.json`) | Receiver-side gate refused to mint a warranty while freshness remains unsettled. |
| WLP `HandlingReceipt` (`ns-wlp-handling-{run_id}.json`) | No AuthorizationReceipt to handle; `wlp::handle` is never called. |
| Continuity-persisted `HandlingReceipt` for this run | Continuity adapter has nothing to consume; this is correct behavior. |

## 4. What stayed unchanged

- **Default `watchbill` (no `--horizon-policy` / `--governor-socket`)** remains governor-blind by design. Option 3 from the CLI reachability slice still holds; the refusal path is only reachable when the configured-horizon flags are set.
- **WLP, Wicket, and Continuity crates** are unchanged. Zero edits outside `~/git/agent_gov/src/governor/` and `~/git/scheduler/crates/nightshiftd/`.
- **Other `NonDischargeKind` values** (`Authority`, `EvidenceSufficiency`, `Scope`, `Standing`, `ConsumerReliance`) are carried-but-not-adjudicated. The closed enum still has six variants; only `Freshness` triggers WLP3 refusal.
- **A.5 refuse-to-cook path** (`ns.refusal.v1` schema, unverified NQ receipt) is unchanged. Distinct schema, distinct semantics: A.5 is upstream-data-unsuitable; WLP3 is downstream-receiver-side.
- **`packet_version`** is unchanged. The new `unsettled` field on `Packet` is additive with `skip_serializing_if = "Vec::is_empty"`; forward-compatible for parsers that ignore unknown keys.
- **`RECEIPT_SCHEMA_VERSION` bumped from 3 to 4 only.** The bump documents schema change; existing v3 receipts still load (`from_dict` preserves their version).
- **Pre-existing standing-validator bootstrap drift** is untouched. Unrelated to this seam.

## 5. Tests locking each boundary

| Boundary | Test | Location |
|---|---|---|
| v4 schema accepts typed claim | `TestNonDischargeClaim::test_accepts_each_valid_kind` (+ 5 siblings) | `agent_gov/tests/test_gate_receipt.py` |
| v4 schema rejects unknown kind | `TestNonDischargeClaim::test_rejects_unknown_kind` | `agent_gov/tests/test_gate_receipt.py` |
| v3 receipts still load with empty unsettled | `TestGateReceiptUnsettled::test_v3_gate_receipt_loads_with_empty_unsettled` | `agent_gov/tests/test_gate_receipt.py` |
| Empty unsettled stays out of receipt_id hash | `TestGateReceiptUnsettled::test_v4_receipt_with_empty_unsettled_hash_stable_against_horizon_pattern` | `agent_gov/tests/test_gate_receipt.py` |
| Non-empty unsettled binds into receipt_id | `TestGateReceiptUnsettled::test_v4_receipts_with_different_unsettled_have_different_ids` + golden fixture's `test_fixture_unsettled_participates_in_receipt_id` | `agent_gov/tests/test_gate_receipt.py` |
| Adapter forwards unsettled to GateReceipt | `TestRecordReceipt::test_unsettled_forwarded_to_receipt` | `agent_gov/tests/test_nightshift_adapter.py` |
| Wire JSON roundtrip preserves claim | `TestRecordReceipt::test_unsettled_roundtrips_through_from_dict` | `agent_gov/tests/test_nightshift_adapter.py` |
| Empty unsettled default backward compat | `TestRecordReceipt::test_unsettled_defaults_empty_when_not_supplied` | `agent_gov/tests/test_nightshift_adapter.py` |
| Golden fixture parses and content-addresses | 8 tests in `TestGoldenFixtureV4WithUnsettled` | `agent_gov/tests/test_gate_receipt.py` |
| Nightshift→Governor seam crosses on Defer | `horizon_packet_state::defer_makes_governor_receipt_observable_in_packet_and_ledger` | `scheduler/tests/horizon_packet_state.rs` |
| Defer emits exactly one record_receipt with freshness claim | `horizon_cross_run::tolerated_active_continues_to_defer_before_expiry` | `scheduler/tests/horizon_cross_run.rs` |
| Packet exposes `unsettled` in YAML to operator | `horizon_packet_state::defer_makes_governor_receipt_observable_in_packet_and_ledger` Surface 3 block | `scheduler/tests/horizon_packet_state.rs` |
| MVP-A preserves `ns_unsettled` + `governor_receipt_ids` in payload | `wlp1_observational_carry_forward_preserves_unsettled_and_receipts` | `scheduler/tests/mvp_a_pipeline.rs` |
| MVP-A empty unsettled emits empty arrays | `wlp1_empty_unsettled_emits_empty_array_not_missing_field` | `scheduler/tests/mvp_a_pipeline.rs` |
| WLP3 refusal: cook + classify preserved, warranty absent, artifact emitted | `wlp3_freshness_unsettled_refuses_authorization_but_preserves_wicket_chain` | `scheduler/tests/mvp_a_pipeline.rs` |
| WLP3 trap-avoidance: non-Freshness kinds DO NOT refuse | `wlp3_non_freshness_unsettled_does_not_refuse` | `scheduler/tests/mvp_a_pipeline.rs` |
| Default watchbill remains governor-blind | doc-only assertion in `scheduler/README.md` step 6 + CLI help text in `main.rs` `--horizon-policy` doc | (no test; CLI flag absence path) |

## 6. Explicit non-claims

This seam does NOT:

- Refuse on `unsettled[Authority]`, `unsettled[EvidenceSufficiency]`, `unsettled[Scope]`, `unsettled[Standing]`, or `unsettled[ConsumerReliance]`. Five `NonDischargeKind` values remain carried-but-not-adjudicated.
- Block the default `watchbill` invocation from anything. Default is governor-blind and emits no Governor receipts; the refusal path is unreachable from there.
- Mutate Governor's `gate_receipt.py` for any consumer other than the v4 schema bump.
- Adjust how Continuity persists artifacts. Continuity sees fewer artifacts on the refusal path; that's correct.
- Add programmatic receipt consumers downstream of operator inspection.
- Touch the `WLP_RECEIVER_GATE_CANDIDATE` doctrine doc in `~/git/wlp/`.
- Resolve the pre-existing standing-validator bootstrap drift.

## 7. Deferred candidates (named, not opened)

| Candidate | Why deferred | Forcing case if/when opened |
|---|---|---|
| `RunWlpAuthorizationRefused` ledger event kind | WLP2 audit named as design tension #3. Currently WLP3 refusal is visible via the artifact path + CLI render arm, not via the run-ledger. | Operator asks "why didn't this run produce a WLP authorization?" without spelunking sink paths. |
| Governor `receipts show <id>` text-mode rendering of `unsettled` | B0 audit candidate that didn't make B1 cut. Today the CLI dumps raw JSON unconditionally. | Audit workflow that doesn't have a packet on hand (post-hoc inspection). |
| Continuity fixture regeneration (`ns_wlp_*_sample.json`) | Existing fixtures are frozen 2026-05-28 artifacts. Forward-compat for the adapter; new MVP-A runs naturally carry the new fields. | When the Continuity adapter test surface starts asserting on `ns_unsettled` content. |
| Ratification for `Authority` / `EvidenceSufficiency` / `Scope` / `Standing` / `ConsumerReliance` refusal | One kind at a time per WLP3 invariant. | Each kind needs (a) a population path producing claims of that kind and (b) a doctrinal justification for refusal-to-warrant on that kind. Neither exists for any of the five today. |
| Standing-validator bootstrap drift fix | Unrelated to this seam; pre-existing across multiple sessions. | Separate session entirely. |

## 8. Witness trail (read in this order to retrace the path)

1. [`nightshift-integration-sweater.md`](nightshift-integration-sweater.md) — original integration map.
2. [`witness-2026-06-09-gate-receipt-unsettled-gap.md`](witness-2026-06-09-gate-receipt-unsettled-gap.md) — schema gap witnessed; lower seam promoted to `witnessed`.
3. [`witness-2026-06-09-cli-reachability-classification.md`](witness-2026-06-09-cli-reachability-classification.md) — verdict C Split; Option 3 preserved; default watchbill stays governor-blind.
4. [`witness-2026-06-09-unsettled-population-horizon-defer.md`](witness-2026-06-09-unsettled-population-horizon-defer.md) — first stitch: Defer → Freshness population, witnessed both ends.
5. [`fixtures/witness-receipt-2026-06-09.json`](fixtures/witness-receipt-2026-06-09.json) — pre-v4 receipt artifact (motivating gap).
6. [`nightshift-governor-unsettled-integration-state.md`](nightshift-governor-unsettled-integration-state.md) — running TL;DR + next-candidates index.
7. [`witness-2026-06-09-b0-rendering-audit.md`](witness-2026-06-09-b0-rendering-audit.md) — verdict B receipt-linked but not visible.
8. [`witness-2026-06-09-b1-packet-unsettled-summary.md`](witness-2026-06-09-b1-packet-unsettled-summary.md) — packet-side visibility landing.
9. [`witness-2026-06-09-wlp0-receiver-fit-audit.md`](witness-2026-06-09-wlp0-receiver-fit-audit.md) — verdict C: mvp_a is the receiver, ignores unsettled.
10. [`witness-2026-06-09-wlp1-carry-forward.md`](witness-2026-06-09-wlp1-carry-forward.md) — observational preservation in MVP-A payload.
11. [`witness-2026-06-09-wlp2-refusal-design-audit.md`](witness-2026-06-09-wlp2-refusal-design-audit.md) — verdict B1, WLP3 spec.
12. [`witness-2026-06-09-wlp3-refusal-implementation.md`](witness-2026-06-09-wlp3-refusal-implementation.md) — WLP3 landing: first refusal with teeth.

This file is the closure receipt for the whole chain.

## Provenance

Filed 2026-06-09, same day as the entire chain landed. The seam now reads end-to-end from one note. Future-you should not have to reconstruct the path from the witness trail and three repos worth of test files.

The gerbil is in the doctrinal terrarium. The terrarium has a label. The label has provenance. Provenance has commits coming next.
