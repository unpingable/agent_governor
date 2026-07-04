# B5 work-order — corpus-case build order (from the 2026-07-03 producibility reduction)

Turns "add 9 B5 corpus cases" into a precise build order. Gated by the Packet C
custody model: each case is admitted by the coverage ceremony (live chain
produces the verdict) + manifest listing + hash, and — because the mirror guard
requires byte-identity — **each new golden case must land in BOTH
`golden/corpus/` (sovereign) and transition-kernel `vectors/legacy/` (mirror),
identical bytes.** That cross-repo, constitutional-corpus growth is why B5 is an
attended build, not an overnight loop.

## Buildable now (4 cases — identical mechanical pattern)  **[SHIPPED 2026-07-03 as B5 A-1..A-4 — corpus cases 10–13; table kept for the build-pattern record]**

The LA client already MAPS these ConsumptionDecisions to refusal kinds
(`linear_accountant_client.py:922-937`); the drill just needs scenarios that
make its LA stub return them. Pattern per case, all in
`src/governor/drill_runner.py`:
1. add `SCENARIO_<NAME>` constant (~line 162) + to `SUPPORTED_SCENARIOS` (~267);
2. scenario-aware branch in the `_la_consume` stub (~1091-1114) returning the LA
   decision;
3. branch in `_classify_chain_outcome` (~1216-1249) → `("refused", "<kind>", "la_seam")`;
4. freeze `golden/corpus/NN-<name>.json` from the live verdict (run the chain,
   copy what it produces — never hand-write the verdict);
5. `golden/corpus/MANIFEST.json`: add the case (custody_class `contract` + sha256);
6. copy the identical file to transition-kernel `vectors/legacy/`;
7. verify: `governor verify-run -- pytest tests/test_corpus_contract.py tests/test_corpus_custody.py`;
8. sandwich-review (codex-exec), commit both repos.

| order | scenario | LA decision returned | refusal kind | note |
|---|---|---|---|---|
| 1 | `scope-mismatch` | `ScopeMismatch` | `scope_mismatch` | the ratified D010 Model X decision's own regression on the gauntlet (LA-side variant; distinct from the Slice-1b Standing-store scope_mismatch) |
| 2 | `token-revoked` | `Revoked` | `token_revoked` | |
| 3 | `token-expired` | `Expired` | `token_expired` | distinct from `standing_expired` |
| 4 | `unknown-token` | `UnknownToken` | `unknown_token` | |

## Blocked — need an operator decision or a prior gap (do NOT build unattended)

| case | blocker |
|---|---|
| freshness `not_yet_valid` | **operator decision**: split AG's single `standing_before_spendability_not_bounded` into the 4 Lean-typed freshness variants, or keep the one kind? No 13th+ refusal kind minted without you. |
| freshness `incoherent_interval` | same freshness-typing decision |
| request-side linearity (F-A3b-2) | cross-repo fence design (LA v0 frozen; `eligibility_reference` reuse unrefused) — gap stub `admission-receipt-linearity` |
| stale-basis (NQ BASIS_STALE) | mapping design: does stale map to `admission_gap_accounted` at cook time or refuse upstream? gap stub; no new kind without you |

## Out of scope for golden/corpus

The continuation specimen (`NoFreeContinuation`) is a transition-kernel FRONTIER
case (`transition_kernel.frontier.gap3.v1`-shaped, different verdict shape) — its
custody belongs to the mirror repo's frontier corpus, not AG golden/corpus.

## Source

Reduction agent, 2026-07-03, verified against `drill_runner.py`,
`linear_accountant_client.py`, `standing_spendability.py`. The 4 buildable cases'
LA mappings are already wired (`linear_accountant_client.py:922-937`); only the
drill stub + classifier branches + the frozen goldens are missing.
