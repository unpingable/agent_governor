# Cross-tool design note: rung activation is a four-office transaction

## Status

Design note for governor / Standing / Linear Accountant / NQ placement.
**PROVISIONAL — filed before any rung-activation (P3.1) build**, deliberately, so
the offices do not get accidentally fused while co-resident in AG.

Provenance: 2026-06-13 interferometry pass (ChatGPT/Claude over the actual repo
types) against `~/git/standing` (`README.md`, `GOVERNOR-CROSSWALK.md`) and
`~/git/linear_accountant` (`docs/architecture/ROLE.md`, `V0_BOUNDARY.md`). The
correction the pass produced: the "rung-activation gate" I specced in
GOV_GAP_RUNG_DEBT_COLLECTION_001 is not one gate — it is a transaction across
four offices that AG currently co-hosts. Composes with loop §11.2/§11.3,
`specs/gaps/GOV_GAP_RUNG_DEBT_COLLECTION_001.md`, `src/governor/
activation_preflight.py` (P3.0, the eligibility half), and the
`standing_client.py` / `linear_accountant_client.py` adapters.

This note records the intended ownership split while the governor-only pipeline
is still bootstrapping. The offices may be co-resident in AG for now, but their
authority must not collapse into one semantic verdict — factor along the
eligibility / spend / custody seams NOW while co-resident, or extracting Standing
and LA later is surgery instead of a move.

## Core doctrine

Rung activation is not a single gate. It is a transaction across four offices:

1. **Governor / Wicket — admissibility.** Is this transition allowed to be
   considered? Are the required claims, receipts, and preconditions present?
   Does it fit current loop policy?
2. **Standing — entitlement.** Is the asserting or acting principal entitled to
   bind consequence? Debt *classification* is an **assert-standing** surface;
   rung *activation* is an **act-standing** surface. Model agreement is
   attribution/evidence, never authority (model identity is attribution,
   workload/operator identity is authority).
3. **Linear Accountant — spend.** Activation is a linear spend. Eligibility may
   justify *asking* for spend, but is not the spend. No semantic verdict may mint
   or consume activation capacity. `activate:rung:N+1` must be exactly-once.
4. **NQ / receipts / continuity — custody.** The system must later prove what was
   activated, by whom, under which claim set, and whether replay was refused.
   Custody records the transaction; it does not make it valid.

## Non-negotiable rule

**`DebtClearVerdict` must never write `active_rung`.** Debt-clear is eligibility;
activation is spend. Clearing or deferring debt permits a request to *approach*
the activation register; it does not perform the activation. (No minting in the
semantic layer.)

## Assert-standing vs act-standing

> "This unresolved issue is future-rung debt, not activation-blocking debt."

is not analysis — it is an assertion affecting downstream consequence: an
**assert-standing** surface, made *earlier* during review of a prior slice.

> "Rung N+1 is now active."

is an **act-standing** surface plus an LA spend, made *now*. Different principals,
evidence, policies, and times. Builder/validator agreement may inform the record;
it cannot settle jurisdiction by itself. (Standing flags entitlement-to-assert as
roadmap-only — only a preflight `assert check` door exists — so §11.3's
agreement rule is currently a placeholder squatting on assert-standing Standing
hasn't shipped. When entitlement-to-assert lands, "agreement settles venue"
becomes "assert-standing settles venue," and model agreement reverts to evidence.)

## Freshness rule

**Deferral is cargo. Re-verification is standing.** A carried debt disposition,
eligibility digest, or deferral classification must not authorize activation
merely because it *exists*. The deferral "this is future-rung debt" was asserted
when rung N+1 was hypothetical; at activation N+1 is present — exactly when the
premise is relied on and exactly when it can be stale. Standing's own invariant:
re-verify at every consequence-bearing gate (admission, capacity/token
consumption, AND later mutation gates). Activation is a later mutation gate.

At activation, AG must either (1) **recompute** the claim set and debt
disposition at the gate, or (2) rely on a governed leased/fresh standing object
with explicit freshness semantics. Until assert-standing + Nightshift freshness
machinery exist, the bootstrap-safe substitute is **recompute at the gate**.

An `eligibility_ref` passed to LA is not proof of truth — it is a conservation
handle. LA must NOT parse it (the accountant stays a dumb cash register;
V0_BOUNDARY: a typed field carrying a claim the accountant cannot verify needs an
owner *outside* the accountant). Ownership split:

- **Eligibility truth / freshness:** Governor / Standing / Nightshift side.
- **Spend conservation:** Linear Accountant.
- **Custody and replay evidence:** NQ / receipt chain.

## Override rule

**Override is custodial deposit, not reversal.** An operator override does not
erase blocking debt and does not convert debt into absence. It creates a new
scoped waiver/deposit with: actor, standing basis, target rung, affected claims,
policy basis, sunset/review condition, receipt chain. Activation still requires
LA spend. Repeated waiver/override must accrue Standing pressure / hysteresis
(Δh) — otherwise repeated "future-rung debt, operator-waived" is laundering with
a signature, and the pressure metric is the only thing that makes recurrence
visible.

## Bootstrap implementation shape

```text
activation_gate(rung = N+1, now):

  live_claim_set =
    collect_open_non_discharge_claims(targeting = N+1, at = now)

  live_debt_disposition =
    classify_claims_now(
      claim_set = live_claim_set, target_rung = N+1,
      policy = current_policy, evidence = current_receipts)

  require:
    live_debt_disposition.has_no_activation_blockers
    live_debt_disposition.deferrals_are_fresh
    classifier_has_assert_authority_or_bootstrap_substitute

  act_standing =
    standing.check_now(
      principal = workload/operator, action = activate_rung,
      target = N+1, effect = binding_mutation)
  require act_standing.allow

  activation_eligibility =
    derive_now(
      rung = N+1, live_claim_set_digest, live_debt_disposition_digest,
      standing_receipt, policy_hash, valid_until)

  activation_spend =
    la.consume(
      spend_key = activate:rung:N+1:campaign:X,
      eligibility_ref = activation_eligibility.digest)
  require activation_spend.consumed_once

  write active_rung = N+1
```

In gov-only bootstrap, AG co-hosts all four offices — fine to run, but the
factoring above must hold even co-resident. The rung-activation spend is a clean
candidate for LA's consumer trigger (LA is frozen until a real stack wants
`consume()` at its dispatcher; a denied activation through LA's preflight door is
the on-record evidence that thaws the spend path).

## Standalone / degraded mode (federation without hostage-taking)

The four-office split is **semantic, not a hard runtime dependency** — the same
invariant as the LA standalone rule (`docs/doctrine/annealing_and_recomposition.md`
§5: *AG may run poor without LA; it must not run blind, and it must not fake being
rich*), now generalized to all four offices. Standalone mode preserves office
**separation** by using local/degraded substitutes, NOT by collapsing the offices
into one verdict. AG may run alone; it may not pretend the other offices were
present.

```text
ActivationMode:
  constellation       — Standing / LA / NQ online; external receipts required
  standalone_degraded — local substitutes; marked degraded

standalone_degraded ALLOWS:
  recompute live claim set · derive fresh eligibility ·
  bootstrap standing substitute · local exactly-once spend ledger ·
  local receipt/custody chain · refuse replay locally

standalone_degraded FORBIDS:
  claiming LA-backed spend · claiming external Standing entitlement ·
  claiming NQ custody · publishing as constellation-grade activation
```

The difference must be **visible in the receipt** (`activation_mode:
standalone_degraded`). A degraded activation may be valid for AG-local
control-plane purposes, but later promotion / publication / reliance may require
reconciliation or re-attestation by the missing offices.

> AG may activate locally without the other offices, but it must mark the
> activation as locally witnessed, locally spent, and locally entitled.
> Standalone mode may run poor. It may not forge rich paperwork.

This keeps federation without making AG a hostage to the federation — the only
sane bootstrap path. Composes with the model-substrate forcing case
(`working/forcing-case-degraded-model-availability.md`): same "witnessed
substrate, degrade-don't-fake" shape, one axis over.

## Required negative tests (for P3.1, when it is built)

1. A stale debt disposition must not activate if a new NonDischargeClaim appeared
   after the disposition was computed.
2. A carried eligibility digest must not activate unless the live claim set still
   matches the digest basis (or the eligibility object has explicit freshness
   governance).
3. Builder/validator agreement must not settle debt venue unless the classifier
   principal has assert-standing or a bootstrap substitute is explicitly recorded.
4. `DebtClearVerdict` must not directly mutate `active_rung`.
5. Operator override must not delete or discharge debt by implication.
6. Operator override must still require activation spend.
7. Repeated override must leave visible Standing pressure / hysteresis evidence.
8. LA must not parse claim semantics; an `eligibility_ref`'s truth/freshness is
   owned elsewhere.

## Doctrine lines

- Debt-clear is eligibility.
- Deferral is cargo. Re-verification is standing.
- Activation is spend. Clearing the debt is not the spend.
- Override is custodial deposit, not reversal. Repeated override accrues pressure.
- No carried artifact may authorize activation unless the artifact is itself
  governed as a fresh leased standing object. Otherwise recompute at the gate.
- The paperwork permits approach to the register. It does not remain valid merely
  because it was laminated.
