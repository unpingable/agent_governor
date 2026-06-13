# GOV_GAP_OFFICE_COLLAPSE_AND_RECEIPT_SOVEREIGNTY_001

## Title

Office-collapse and receipt-sovereignty guardrails — the conversion refusals that
must hold before further decompose/recompose work, so the next pass cannot
launder a cross-level transition into authority it didn't earn.

## Status

**Candidate — doctrine anchor + acceptance/negative-test markers; NOT a build.**
Filed 2026-06-13. The integration (microkernel, capability IPC, self-annealing as
controller transition) is future and partly custody-affecting (touches the
receipt kernel's invariants — supersession ceremony, not ordinary work). This gap
exists to install the *refusals* now. Notes:
`docs/cross-tool/receipt-sovereignty-microkernel-note.md` (capstone),
`docs/cross-tool/rung-activation-four-office-note.md` (offices + verifier +
continuity placement). Composes with loop §11.2/§11.3,
GOV_GAP_RUNG_DEBT_COLLECTION_001, GOV_GAP_ANNEALING_DELTA_001.

## Why now (it crosses levels)

The doctrine crosses several levels at once; landing it before more decomp/recomp
saves refactoring and makes cleaner design now. Each level owns one refusal:

| Level | Doctrine |
|---|---|
| Architecture | Receipts/kernel govern; Governor implements. The sovereign cannot be semantic. |
| Deployment | Standalone vs federated is placement, not authority. |
| Tool boundary | Co-location is allowed; conversion is the crime. |
| Rung activation | Debt-clear eligibility ≠ activation spend. |
| Continuity | Reliance is computed at query time, not remembered. |
| Verifier | Inference check, not world/freshness oracle. |
| Standing | Actor entitlement is never minted by the actor. |
| LA | Spend is exactly-once; semantic validity cannot mint capacity. |
| Self-annealing | Controller transition, not privileged internal rewrite. |

The decompose/recompose pipeline is exactly where laundering sneaks in — every
arrow is a possible crime scene:

```
finding → claim → debt disposition → eligibility → activation request
       → spend → mutation → receipt → future reliance
```

## The rule

> **Every cross-level transition must name the office that owns the conversion.
> If no office owns it, the transition is forbidden.**
> Integrate freely, but every bridge must be typed, receipted, and owned.

## Forbidden conversions (refuse these)

```
DebtClearVerdict          ->  active_rung write          (debt-clear is eligibility only)
Continuity.rely_ok=true   ->  authority                   (reliance is a fact, not authority)
Verifier.allowed          ->  authority                   (inference check, not authorization)
eligibility_ref present   ->  freshness                   (presence is not currency)
builder/validator agree   ->  assert-standing settled     (attribution, not authority)
operator override         ->  debt deletion               (override is custodial deposit)
AG local stub             ->  real Standing grant         (non-convertible by construction)
Governor                  ->  the microkernel             (sovereign cannot be semantic)
Governor self-anneal      ->  privileged internal rewrite (it is a controller transition)
observation               ->  committed reliance          (commit is a separate, classed act)
co-location               ->  authority conversion        (placement is not authority)
```

## Required instead

```
Debt disposition  -> eligibility only
Deferral          -> recompute at gate OR Continuity rely_ok=true w/ hard premises + expires_at
Activation        -> Standing act-check / operator-stub + LA exactly-once spend
Override          -> custodial waiver deposit + Δh/pressure evidence + LA spend still required
Verifier          -> hook over freshly assembled IR, never a fact oracle
Standalone AG     -> typed office co-hosting with explicit non-convertible stubs
Self-annealing    -> proposal → kernel admits shape → above-Governor ratify → cap-holder mints
                     → successor inherits receipts not warm intent → fresh-context AUDIT
```

## Acceptance / negative-test markers (NOT implemented here)

(See the two cross-tool notes for the full lists; the load-bearing ones:)
- no `DebtClearVerdict` → `active_rung` write;
- activation recomputes or rely-checks carried deferrals (no carried-digest-as-fresh);
- `rely_ok` / `verifier.allowed` / builder-agreement never convert to authority;
- standalone Standing stub is non-convertible (typed, operator-fiat basis);
- no controller transition without above-Governor ratification, and that
  ratification rule is a **receipt-kernel invariant**, not Governor policy;
- a service cannot widen its own caps; an ungranted bridge is untraversable.

## Precondition for further decompose/recompose

> This phase may continue decompose/recompose work only if the implementation
> preserves: receipt sovereignty over Governor semantics; no Governor-as-kernel
> path; no `DebtClearVerdict → active_rung` write; no `rely_ok` / `verifier.allowed`
> / builder-agreement → authority conversion; no local Standing stub presented as
> a real grant; no controller transition without above-Governor (kernel-invariant)
> ratification.

## Non-goals

- NOT building the microkernel / capability IPC / self-annealing now.
- NOT modifying the receipt-kernel invariants (that is supersession-ceremony,
  custody-affecting work; this gap only names that the ratification rule must
  eventually live there).
- NOT merging the sibling repos into Governor's address space.

## Doctrine line

> Design now so extraction later is a deployment change, not a constitutional
> crisis.
