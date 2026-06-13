# Cross-tool design note: hot paths and governance granularity

## Status

**PROVISIONAL design note — durable doctrine, authorizes no build.** Filed
2026-06-13 (operator + interferometry). Names the hot paths and the one rule that
keeps governance overhead in the noise floor. Composes with
`receipt-sovereignty-microkernel-note.md` (the two substrate hot paths are the
bill those two choices pull forward), `decomposition-capability-closure-note.md`
and `symbolic-instrument-witness-note.md` (semantic conversion seams), and the
loop's WIP-1 / island discipline.

## Two altitudes of hot path

Hot paths live at two altitudes, with different failure modes. Both matter; do not
collapse them.

**Substrate hot paths** — created by the architecture itself, not by any one
office. They became visible only *after* the sovereign-receipts and microkernel
choices; they are the tradeoff arriving on schedule, not a walkback.

**Semantic conversion hot paths** — the moments where one kind of thing becomes
another kind of thing (evidence→authority, eligibility→spend, claim→non-blocking).
The conversion-path audit (`working/audit-conversion-paths-2026-06-13.md`) swept
these; this note adds the one the audit under-weighted: **discharge**.

| Hot path | Class | Failure if wrong |
|---|---|---|
| Receipt append / hash chain | substrate / serialization | sovereign receipts become the bottleneck |
| Kernel-mediated IPC | substrate / latency | federation becomes round-trip soup (SOA with a PhD and no friends) |
| Standing re-check at gates | substrate + authority | every gate blocks on remote entitlement |
| **Claim discharge / waiver / deferral** | semantic | a bogus unblock silently poisons every future gate |
| Policy / rule promotion | semantic | doctrine becomes authority without ratification |
| Receipt adoption into reliance | semantic | emitted evidence becomes a premise without `rely` |
| Stub→real upgrade | semantic / migration | weak old receipts reinterpreted as strong |
| Symbolic encoding admission | semantic | a proof of the wrong formalization becomes authority |
| Rollback | semantic / custody | undo erases *why* the thing happened |
| Rung activation / LA spend | semantic | (already fenced — P3.1/P3.2) |

## The substrate hot paths (the bill for the two big moves)

1. **Receipt append is universal.** "Receipts govern" puts receipt-append on the
   path of *everything*, and a `prev_hash` chain is a total order by construction —
   you cannot append two receipts to one chain concurrently without serializing
   them. So the sovereign chain is a serialization point. **The fix already
   exists: island discipline + per-scope DBs.** The master spine is serial anyway
   under WIP-1, so its chain being serial costs nothing — but high-volume receipts
   (worker observations, telemetry) MUST island away from the spine or the spine
   becomes the bottleneck.

2. **Microkernel IPC is the message path.** Going microkernel makes the
   cross-office message path the hot one (the whole L4/seL4 lineage is "make IPC
   cheap enough that the microkernel was worth it"). The microkernel is still
   right — it makes the seams mechanical — but the work it pulls forward is fast
   typed IPC and *minimizing round-trips per action*. The fix is not "don't do
   microkernel"; it is **one meaningful action = one bundled transaction
   envelope** (facts + premises + standing request + verifier IR + spend request +
   receipt intents in one typed message), not a synchronous
   Governor→Standing→Continuity→Verifier→LA→NQ→Governor round-trip chain. Cap
   discipline, not RPC cosplay.

3. **Standing re-check is uncacheable by construction.** "Re-verify at every
   consequence-bearing gate" means a synchronous round-trip per gate in federated
   mode. Standing is doubly the awkward office: the one you cannot honestly
   self-host (authority), *and* the one most expensive to federate (latency on
   every gate). Keep it closest and fastest. Standalone: explicit operator-stub /
   local fast path / non-convertible. Federated: close, cached only as **lease
   metadata for routing**, never **cached as authority** — the lease helps you
   find/check; it does not replace re-verification.

## The granularity rule (what keeps all three cheap)

The real latency hot path is **model inference**: a Codex turn is seconds; a
hash-append, a Z3 call, a standing check are milliseconds. Governance sits in the
noise floor — *as long as it fires at action granularity, not implementation
granularity*. The only way governance flips from noise to dominant is firing
per-token / per-syscall / per-helper / per-telemetry-row instead of per-meaningful-
action.

> **Governance granularity matches action granularity. Gate the spend, not the
> syscall.**

| Fire governance HERE (meaningful) | NOT here (implementation) |
|---|---|
| receipt every consequence-bearing transition | receipt every token |
| Standing check every gate | standing check every helper function |
| LA spend every linear capacity consumption | IPC every micro-step |
| Continuity `rely` every premise adoption | continuity rely every internal read |
| Verifier every claim-emission seam | verifier every line |

## Spine vs island (what chains where)

```
spine chain (serial, sovereign, WIP-1):     island chains (sharded, high-volume):
  controller transitions                       worker observations
  rung activation                              telemetry
  cap grant / revoke                           pass receipts
  LA spend                                     bulk witness noise
  standing / override deposits                 local diagnostics
  policy promotion
  claim discharge / waiver / deferral
  receipt adoption into reliance
```

The spine stays serial without becoming the sewer pipe for every squirrel fart in
the system.

> **Do not put telemetry on the throne.**

## Discharge — the hidden hot path

Activation gates are obvious; discharge feels like cleanup, and cleanup is where
systems hide state changes wearing sweatpants. But the moment a `NonDischargeClaim`
goes open → discharged/deferred/waived, the system changes what future gates may
do. So:

> **A claim becoming non-blocking is consequence-bearing.**

Forbidden conversion:

```
test_passed / doc_added / reviewer_agreed  ->  claim_discharged
```

Required shape:

```
evidence produced
  -> verifier/check/adjudication MAY support discharge
  -> AUTHORIZED discharge decision (standing/operator basis)
  -> discharge receipt
  -> future gates recompute eligibility from LIVE debt state
```

Negative-test family (markers for a future discharge-hardening slice — NOT built
here):

- a test pass alone cannot discharge a claim;
- doc presence alone cannot discharge a claim;
- builder/validator agreement cannot discharge without assert-standing/operator basis;
- a waiver does not DELETE the claim;
- a deferral does not DISCHARGE the claim;
- a discharged claim retains provenance and is auditable as a prior blocker.

(Note: today's `DebtLedger.discharge()` flips a flag and is not called by
activation — the audit found no live conversion — but the *authority basis* for
discharge is the future-rung obligation this names.)

## Doctrine lines

- Receipts are sovereign, so receipt append is a hot path.
- The microkernel mediates authority, so IPC is a hot path.
- Standing is uncacheable authority, so gate re-check is a hot path.
- A claim becoming non-blocking is consequence-bearing.
- Governance fires at action granularity, not implementation granularity.
- Meaningful actions chain on the spine; noise chains on islands.
- One meaningful action = one bundled transaction envelope.
- Do not put telemetry on the throne.

## The pickup rule (admission, not footer)

> **Every future wiring slice must state whether it touches the spine, an island,
> IPC, a Standing-gate, or a semantic-conversion hot path** — and if a
> semantic-conversion path, which office owns the conversion. Hot-path awareness is
> part of a slice's admission, not a decorative afterthought.
