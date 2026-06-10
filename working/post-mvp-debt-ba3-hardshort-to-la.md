# Post-MVP Debt — Hard-Short BA3 Surfaces to LA

**Status: named debt obligation. Not a gap spec. Not a roadmap. Not
authorization to implement during MVP work.**

Filed 2026-06-09 as the long-term resolution path for the BA3 surfaces
that C0 identified and that the MVP harness bypasses-and-receipts. The
bypass is explicitly noncanonical; this artifact is the surface where
that debt lives until paid.

## The debt in one sentence

> Every AG-internal BA3 budget surface (`RunBudgetLedger`,
> `ExecutionBudget`, `ExplorationBudget`, routing `Budget`) must be
> hard-shorted to Linear Accountant (`~/git/linearaccountant`) once LA
> wires into AG, so that AG carries no internal authoritative
> spendability ledger after MVP.

## Why the debt exists

Per `working/campaign-standing-before-spendability.md` C0-resolved:
the MVP harness runs with `SpendabilityAuthority = LA_ONLY`, all BA3
surfaces are bypassed in spine runs, and the bypass is receipted.
That is the **MVP-shaped** answer; it is not the canonical answer.

The canonical answer is: AG has **zero** authoritative budget surfaces.
LA is the sole spendability authority. Every "consume" / "spend" /
"reserve" call in AG either:
- delegates to LA via the linear_accountant client / handoff, or
- is documented as explicitly intra-controller energy with no
  consequence-gating role, or
- is removed.

Two live accountants is a laundering surface even in MVP — and the
MVP bypass is only acceptable because it is loud about the
noncanonical choice. Post-MVP, the bypass must end.

## Surfaces to address

| Surface                  | Hard-short shape                                                                                      |
| ------------------------ | ----------------------------------------------------------------------------------------------------- |
| `RunBudgetLedger`        | Replace internal projection with LA `CapacityRequest` per tool call. Refusal becomes `capacity_refused` from LA, not AG. |
| `ExecutionBudget`        | Two paths possible: (a) treat session-iteration cap as intra-AG control (BA1 by scope), document explicitly and remove gating role; (b) delegate to LA per iteration. Decision deferred. |
| `ExplorationBudget`      | Likely BA1-by-scope (homeostat intra-controller energy). Document the boundary; remove any role in gating external action. |
| routing `Budget` / `BudgetManager` | Delegate model-choice cost to LA. Hard-refusal path becomes LA refusal. |

## Pre-conditions for paying the debt

- LA wired into AG (the "convertible spend path appears" trigger named
  in `memory/linearaccountant_repo.md`).
- LA contract for `CapacityRequest` / `Grant` / `Consume` /
  `AlreadyConsumed` stabilized.
- S1/S2/S3 spine landed and the bypass-receipt vocabulary in S4-lite
  ratified.

## What this debt is NOT

- Not authorization to start replacing BA3 surfaces today.
  RunBudgetLedger replacement before LA wires would create a
  capacity-shaped hole.
- Not authorization to reclassify any BA3 downward without LA backing.
  "Arguably intra-AG control" is how the dual-ledger crime gets
  committed in a blazer.
- Not a substitute for the canonical doctrine in
  `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md`. That gap
  spec carries the validity/spendability invariant; this debt artifact
  carries the surface-by-surface implementation obligation downstream
  of it.

## Cross-references

- `working/campaign-standing-before-spendability.md` — MVP campaign
  this debt sits downstream of; C0-resolved entry names the bypass
  contract.
- `working/witness-2026-06-09-c0-standing-before-spendability.md` —
  Q2 exit ticket carries the BA3 surface enumeration with file:line
  evidence from the codex adversarial pass.
- `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md` — parent
  validity/spendability invariant.
- `working/directional-invariants.md` — invariant 2 (capacity is
  downstream of entitlement; capacity cannot cure lack of standing).
- `working/linear-accountant-handoff.md` — in-flight cross-repo work
  that gates the trigger.
- `memory/linearaccountant_repo.md` — LA boundary + packet shape.
