# C4 — B5 unlock adjudication

**Verdict: Q-B3 RESOLVED. B5 corpus-authoring is PARTIALLY BLOCKED — and the
blocker is NOT custody.** (2026-07-02 night, adjudicated record.)

## Q-B3 — resolved

The packet's success condition is met:
- corpus has an explicit custody model (custody-model.md: taxonomy + admission
  source/mirror + admission/mutation rule);
- at least one executable guard exists (`tests/test_corpus_custody.py` +
  `golden/corpus/MANIFEST.json`), verified `governor verify-run` [pass],
  including a live mirror byte-identity check against
  `~/git/transition-kernel/vectors/legacy`;
- B5 can be started with KNOWN admission rules instead of vibes.

Custody recommendation (overturns the earlier "transition-kernel owns it"):
**AG `golden/corpus/` is the admission source; transition-kernel
`vectors/legacy/` is a conformance mirror that must prove byte-identity and may
not mutate expected behavior locally.** Later migration to a neutral registry is
allowed but would be a custody EVENT, not housekeeping. → pickup DECISIONS Q-B3.

## The reframe B5 needs

A golden/corpus case freezes `input → expected_verdict`, and the contract test
asserts the verdict against what the LIVE cooked-context chain (`run_drill` /
`_classify_chain_outcome`) actually produces. **You cannot freeze a verdict the
reference implementation cannot yet produce.** The corpus chain today produces
exactly six refusal kinds: `standing_required`, `standing_expired`,
`admission_denied`, `admission_gap_accounted`, `already_consumed`,
`standing_before_spendability_not_bounded` (SUPPORTED_SCENARIOS, drill_runner).

None of B5's nine target verdicts are among them. So "add 9 B5 corpus cases" was
mis-scoped: for most of them the first step is **build the scenario / produce the
refusal in the live chain**, and only THEN freeze + admit. Corpus authoring is
the last step, not the task.

## Per-case adjudication (all would be `custody_class: contract` when admitted)

| B5 case | producible by corpus chain today? | real prerequisite | status |
|---|---|---|---|
| scope_mismatch (non-consuming) | NO — lives on the Standing store / activation Office 2 path (Slice 1b), not the run_drill gauntlet | a `SCENARIO_SCOPE_MISMATCH` in drill_runner + a chain path that reaches it (or a decision to corpus it on the activation surface instead) | BLOCKED on scenario construction |
| token_revoked | NO | drill scenario putting the LA seam in a revoked state + `_classify_chain_outcome` mapping | BLOCKED on scenario |
| token_expired | NO (distinct from standing_expired) | drill scenario for LA token TTL | BLOCKED on scenario |
| unknown_token | NO | drill scenario for unrecognized token_id | BLOCKED on scenario |
| freshness not_yet_valid | NO — the chain collapses freshness to the single `standing_before_spendability_not_bounded` | a DESIGN decision: split the AG freshness refusal into the 4 Lean-typed variants, or accept the single kind. **Do not mint typed kinds without operator** (the "no 13th refusal kind" discipline) | BLOCKED on refusal-typing decision |
| freshness incoherent_interval | NO | same freshness-typing decision | BLOCKED on decision |
| request-side linearity (F-A3b-2) | NO | the cross-repo fence design (LA frozen v0); gap stub `admission-receipt-linearity` | BLOCKED on prior gap |
| stale-basis (NQ BASIS_STALE) | NO | the mapping design — does stale map to `admission_gap_accounted` or refuse upstream; gap stub for a 13th-kind question | BLOCKED on prior gap + operator |
| promote a continuation specimen | N/A to golden/corpus.v1 | it is a transition-kernel FRONTIER case (`transition_kernel.frontier.gap3.v1`-style, different verdict shape), not a golden/corpus decision case | OUT of golden/corpus scope — mirror-repo frontier, its own custody |

## What is UNBLOCKED right now

- The custody DISCIPLINE for adding any future case: build the scenario → live
  chain produces the verdict → freeze the golden → add to MANIFEST as
  `contract` with its hash → mirror syncs (guard proves identity). No case
  enters as scripture; each is admitted by the coverage ceremony + the manifest.
- A first genuinely-addable case would be any NEW scenario whose refusal the
  chain already produces — none of the B5 nine qualify, so B5 proper waits on
  scenario/refusal work, tracked as its own slices (not this packet).

## Recommendation to the operator

1. Accept the Q-B3 resolution + the sovereign/mirror model (pickup DECISIONS).
2. Re-scope B5 from "author 9 corpus cases" to "build 4 drill scenarios
   (scope_mismatch, token_revoked/expired/unknown) + make 1 freshness-typing
   decision + resolve 2 prior gaps (F-A3b-2, stale-basis) — freezing each verdict
   as it becomes producible." Corpus authoring rides along, gated by the guard.
3. Route the continuation specimen to the transition-kernel frontier corpus, not
   golden/corpus.
