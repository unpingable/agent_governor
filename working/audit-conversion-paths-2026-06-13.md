# Conversion-path audit — 2026-06-13

Step 1 of the decomposition-completeness sequence (document → **audit** →
negative tests → stub receipts → real wiring). Read-only audit of the 11
conversion crimes the doctrine forbids — turning **evidence into authority,
eligibility into spend, memory into reliance, or declaration into closure without
naming the owning office**. Two independent agents, grounded in file:line, not the
builder's priors.

Verdict vocabulary: ABSENT · SAFE_STUB (present but typed/fenced/non-convertible)
· DOC_ONLY_GAP (named gap, no runtime path) · LIVE_RISK (a path can convert) ·
BLOCKER (LIVE_RISK that must be fixed before more decomp/recomp).

## Result: 0 BLOCKER · 0 LIVE_RISK · 2 DOC_ONLY_GAP · 7 SAFE_STUB · 2 ABSENT

| # | Crime | Verdict | Fence / evidence |
|---|---|---|---|
| 1 | `DebtClearVerdict → active_rung` | SAFE_STUB | `debt_ledger.py:99` discharge flips a flag only (never called by activation); `activation.py:390-510` requires four offices + custodied, surface-fenced receipt; `ActiveTunableStore` has no bare `set` |
| 2 | `account_boundaries → decomposition_complete` | DOC_ONLY_GAP | `pipeline_types.py:140-205` total over the *given* admitted set; no `coverage:complete`/`decomposition_complete` emitted (grep empty); pinned `tests/test_decomposition_closure_limit.py`; gap filed |
| 3 | `declared_boundaries → closed boundary set` | DOC_ONLY_GAP | `cooked_context_orchestrator.py:779` accounts the declared plan, never asserts it as the universe; capability-kernel (closed-by-construction) is named future work |
| 4 | `A.allowed ∧ B.allowed → A;B.allowed` | SAFE_STUB | `_run_chain` (orchestrator) is real sequential traversal threading each minted receipt id into the next + short-circuit on refusal; recomposition only ADDS a laundering refusal; reified `seam(A,B)` named future |
| 5 | `operator_override → debt discharged` | ABSENT | `overrides.py` keys on continuity `anchor_id`/`scope` only; never imports debt/spend/activation; already a custodial-waiver pattern |
| 6 | `builder_validator_agree → assert-standing` | SAFE_STUB | `interferometry.py:470-507` agreement → `Provenance.DERIVED` epistemic-ledger claim at confidence; no path to standing/authority/spend |
| 7 | `verifier.allowed → authority` | SAFE_STUB | `constraint_gate.py:164-168`/`verifier_gate.py:87-92` map verifier `allowed`→gate verdict `pass` only; effect requires `confer_operational_effect`'s `isinstance(OperationalConsumed)` wall (`cooked_context_orchestrator.py:491`) |
| 8 | `continuity.rely_ok → authority` | SAFE_STUB | `doctrine.py:3-11,264` reads `rely_ok` fresh at query time into a value type, "does NOT authorize"; sole consumer prints it (`cli.py:19804`) |
| 9 | `eligibility_ref_exists → freshness` | SAFE_STUB | `linear_accountant_client.py:608-653` gates on *resolvable*, not fresh; staleness delegated to LA (`capacity_refused`); `standing_spendability.py:185-210` enforces the two-clock monotonic gap vs horizon |
| 10 | `local_standing_stub → real grant` | SAFE_STUB | `activation.py:459-504` `REFUSED_DEGRADED_CLAIMS_BACKING` blocks external backing in standalone; grade stamped (`standing_basis="bootstrap_substitute"`, `custody_basis="local_receipt_chain"`) — permanently distinguishable |
| 11 | `governor_policy → kernel invariant` | ABSENT | receipt-kernel invariant set is a fixed import list (`libs/receipt_kernel/.../invariants/__init__.py:26-33`); no governor module constructs a kernel `Invariant`; `receipt_bridge.py` emits events only; standing validator is a *separate* kernel w/ its own supersession ceremony |

## Bottom line

The decompose/recompose work is **not gated by any live conversion crime.** The
two open items (crimes 2 & 3) are exactly the decomposition-completeness gap
(`GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001`) — doctrine-level, no
runtime overclaim, already fenced by the closure note + the pinned limit test. The
other nine are fenced by existing structural walls (mostly P3.1/P3.2: the
four-office activation, the `isinstance(OperationalConsumed)` spend wall, the
standalone-grade receipt stamping) or absent by construction.

**Regression radar (the two load-bearing fences):** the
`isinstance(OperationalConsumed)` spend wall (`cooked_context_orchestrator.py:491`)
and the standalone-grade receipt stamping (`activation.py:496-504`) — both keep
crimes 7 and 10 from going live. Any refactor touching them must re-run the
negative pinning tests (`tests/test_operational_spend_fence.py`, the activation
refusal tests) with REAL exit codes (verify-run).

## Next (step 2 — wiring, smallest first)

Because the audit is clean, wiring is additive, not remedial. The one open seam
that matters is the receipt-shape discipline for crimes 2 & 3 — AC1/AC2 of the
decomposition gap:

- a decomposition check emits `enumeration` + `coverage` separately;
- AG-alone may emit `enumeration: complete` but only `coverage: best_effort`
  (`verifier: absent`, `proof_tier: ag_only`);
- a guard refuses `coverage: complete` / `decomposition: complete` without
  solver/theorem/operator evidence (the "no bare `complete: true`" valve).

That is the smallest mechanical enforcement seam, and it converts the DOC_ONLY_GAP
into a structurally-guarded one before any capability kernel exists. Gated on
operator go (doc→code transition).
