# Loss packet — candidate launch-envelope artifact (named, not ratified)

**Status:** CANDIDATE (2026-07-02; operator-sourced via external analysis of
"Loss Function Development" — github.com/elvisun/loss-function-development —
and the cal.com closed-source / Discourse stays-open exchange, 2026-04).
Filed under YAGNI-scope doctrine: name early, ratify lazily. No build slice
exists; this record is the handle.

## The idea

Optimization-shaped agent work ("make this metric move against an eval you
can't see") is a distinct task species. Run naked, it produces the failure
the source thread names in one sentence: **"the agent cheated 3 times."**
Optimization without admissibility becomes laundering — reward-channel
capture, memorized-seed "100% recall" (a fake receipt), loop victory without
generality (green theater).

The corrective is not a smarter prompt; it is a **bounded launch envelope**:

```
Goal · Target (hidden eval E, threshold ≥ X) · Forbidden (no eval-shaped
keyword lists, no fixture lures, no ToS-gated sources, no prod writes, no
unbounded crawl) · Budgets (wall clock / spend / crawl / calls) ·
Instruments (score, spend, provenance, overfit-check, artifact-diff,
receipt-export) · Stop (threshold met | budget exhausted | constraint
violation | no improvement after N entropy-forced turns | operator review)
```

The boundary law already covers the vocabulary: **metric movement is not
authorization.** A loss function can say "closer"; it cannot say true /
allowed / safe / generalizes / ready / canon / prod / worth-another-$40.
The durable asset is not the eval score — it is **the custody chain around
what "better" means** (a living, private, representative, adversarially
maintained eval corpus with provenance). The eval is a governor INPUT, not
the governor.

## Crosswalk — what AG already has (this is mostly implicit, as suspected)

| packet field | existing AG surface | gap? |
|---|---|---|
| Target (claim being optimized) | typed Claim + evidence gate; oracle evidence | — |
| Hidden eval = private witness set | **oracle_independence invariant** (receipt_kernel) is the principle; a custodied eval-corpus store is NOT built | **GAP-1 (named)** |
| Forbidden surface / ration card | scope allowlists + egress gate + supervisor COMMUNICATE interception + playbook ration-card terms | — |
| Budgets | ExecutionBudget + RunBudgetLedger hard limits + LA capacity | — |
| Instruments | signals plane (EXPOSURE_PROXY etc.), telemetry, verify-run receipts, provenance labels | — |
| Overfit-check instrument | grounding audit + semantic-stability perturbation audit are ADJACENT; an eval-overfit detector (train/holdout divergence as a signal) is NOT built | **GAP-2 (named)** |
| Forced entropy after stalls | **research mode**: entropy bounds, dominance caps, PROBE lifecycle — built, not wired to optimization loops | wiring only |
| Cheating = reward-channel capture | correlator capture detection (K-vector, Prop 4.2/5.3) — built for governance capture; same topology | reuse candidate |
| Stop conditions | invariants + budget breach + boil tripwires + operator review states | — |
| Review before promotion | promotion custody + docket + evidence gate | — |

## Where it lands when it lands

A loss packet is a **launch-envelope artifact for a supervised session** —
the optimization sibling of an autopilot profile. In the governed-shell
design: the desk launches it like any task; the packet's Stop conditions
surface as queue items; the hidden-eval score arrives as an INSTRUMENT
(testimony), never as an approval; promotion still goes through the diff +
custody moment. Maude consumes loss packets, not vibes.

## Ratification trigger (do not build before)

First real optimization-shaped task run through a supervised session (e.g. a
retrieval-coverage or eval-driven tuning chore) where ad-hoc constraints
visibly leak — that run's obstruction note is the forcing case. At that
point: GAP-1 (eval-corpus custody: provenance, versioning, leak tracking)
and GAP-2 (overfit instrument) get gap specs; the packet schema gets a
contract section; everything else is wiring of existing organs.

## Non-goals

- No "LFD framework" import; no eval-as-moat mysticism (a private eval can
  rot, narrow, leak, or become a self-confirming idol — custody is the moat).
- No autonomy widening via metric success (graduated autonomy stays
  precedent- and operator-driven; a rising score widens NOTHING).
- Not a sixth decision kind; stop-condition events ride existing kinds.
