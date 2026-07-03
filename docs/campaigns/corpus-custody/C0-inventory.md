# C0 — corpus surface inventory (executed 2026-07-02 night)

Agent-gathered, operator-verified. **One agent over-claim was checked and
corrected** (see §Corrections) — recorded per the A9 discipline: don't amplify
an unverified "biggest risk."

## The surfaces

| surface | repo | consumer(s) | encodes | authority |
|---|---|---|---|---|
| `golden/corpus/*.json` (9) | agent_gov | `test_corpus_contract.py` (LIVE cooked-context chain per case) | frozen input→verdict, schema `agent_governor.corpus.v1`, 7 closed VERDICT_FIELDS, optional receipt block | EXPLICIT schema tag; **IMPLICIT membership** (no custody_class) |
| `vectors/legacy/*.json` (9) | transition-kernel | `differential.py` (Rust≡frozen), `conformance.rs` | **byte-identical copy** of the above | EXPLICIT schema; IMPLICIT membership; **no sovereign/sync declaration** |
| `golden/README.md` | agent_gov | humans | doctrine prose ("corpus not Python is the contract"; "grows by ceremony") | NONE (prose, no executable consequence) |
| `test_corpus_contract.py` | agent_gov | pytest | schema-validate + live-verdict-match + closed-world coverage + Wall-1 non-operational | the STRONGEST guard of the three harnesses |
| `conformance.rs` | transition-kernel | cargo test | glob + **hardcoded `assert_eq!(cases, 9)`** + accepted-divergence path | count-gate is brittle (not derived) |
| `differential.py` | transition-kernel | CI | glob, Rust-vs-frozen, no count gate | weakest harness |
| `drill_runner.SUPPORTED_SCENARIOS` (8) + `_classify_chain_outcome()` | agent_gov | the live chain the corpus tests against | scenario vocabulary + scenario→(outcome,refusal,seam) mapping | LIVE code — see §Co-drift limit |
| `_used_packet()` / `_refused_packet()` / `FakeRunner` | agent_gov (test_standing_grant_use.py) | unit tests | the `standing.grant_use.v1` packet SHAPE | **helper-as-hidden-authority** (real; MEDIUM) |
| `vectors/frontier/gap3/*.json` | transition-kernel | frontier_gap3 test | typed-memory custody vectors, schema `transition_kernel.frontier.gap3.v1` | **EXPLICIT + SEPARATED** — never grandfathered into legacy (a good precedent) |

## Where contract authority actually lives today

Split across three layers, no single custody model:
1. **The JSON** — frozen, schema-tagged, but membership-is-authority (no
   custody_class). The 9 are contract only by being in the glob + covered.
2. **The harnesses** — three of them, unequal: AG's Python test is
   schema+coverage-guarded; conformance.rs leans on a hardcoded count;
   differential.py on neither. AG holds the strongest guard AND the
   live-behavior validation → reinforces AG-as-sovereign (custody-model.md).
3. **The live vocabularies** — SUPPORTED_SCENARIOS + `_classify_chain_outcome`
   are code, not frozen data.

## Confirmed custody gaps (the packet's actual targets)

- **G1 — no `custody_class`.** All 9 cases carry identical implicit authority;
  contract-by-membership is the launderable rule. → C1/C3 close this.
- **G2 — two byte-identical copies, no sovereign, no sync guard.** Edit one and
  they diverge silently. → C2 names AG sovereign; C3 guards byte-identity.
- **G3 — helper-as-hidden-authority (MEDIUM).** `_used_packet`/`_refused_packet`
  encode the `standing.grant_use.v1` packet schema in a helper's return dict;
  changing it changes the schema with no admission signal. → named follow-up
  `packet-schema-custody` (NOT fixed this packet — it's the packet SCHEMA, a
  distinct object from the decision corpus; over-reaching would be scope creep).

## Co-drift limit (real, bounded — not a crisis)

The corpus freezes input→verdict, but `_classify_chain_outcome()` (the code that
turns a chain result into outcome/refusal_kind/refusing_seam) is LIVE. The
contract test catches code that drifts AWAY from a frozen verdict — but a commit
that changes the classifier AND the golden together co-moves past the guard.
This is inherent to a golden-corpus-against-live-chain design (the golden proves
"code still produces this verdict," not "this verdict is eternally right"). The
mutation rule (C2) is exactly the mitigation: changing a `contract` verdict must
be a deliberate, attributed, reviewed act — so a co-drift commit is loud and
cited, not silent. Recorded as a known property, not a new machine.

## Corrections to the agent inventory (A9 discipline)

- The agent flagged `operational_admission()` as "the fence living in a test
  file — the single biggest risk." **Verified FALSE:** the fence is defined in
  production at `src/governor/cooked_context_orchestrator.py:270`; the test file
  `test_origin_admission_fence.py` IMPORTS and PINS it (27 mandatory tests).
  Production fence, test-pinned — the healthy shape, not the risk. Downgraded.
- The agent referenced a `divergence_manifest.json` ("operator-approved, not yet
  used"). **Not present on disk** — it's referenced by the harnesses as a future
  divergence-acceptance mechanism, not a populated artifact. Recorded as a
  named-not-built admission hook, not an existing custody signal.

## Stop-conditions — checked, NOT triggered

- "Authority spread across repos, no single model possible" — **not triggered**:
  the copies are byte-identical (one content), and one side (AG) clearly holds
  the live-behavior validation. A single sovereign+mirror model covers both.
- "Expected verdicts encoded only in helpers, not cases" — **not triggered for
  the decision corpus** (verdicts ARE in the golden cases). It IS true for the
  standing.grant_use.v1 PACKET schema (G3), which is a different object → named
  follow-up, not a blocker for the decision-corpus custody model.
