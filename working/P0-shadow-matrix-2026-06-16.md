# P0 shadow matrix — does normal_form observe a real seam, or restate doctrine? (2026-06-16)

Ran the shadow over **every distinct promotion-evidence bundle shape** the suite
contains (11 shapes: the happy path + 9 the gate refuses for domain reasons + the empty
chamber), side-by-side with the real gate verdict. Read-only analysis; no wiring.

## The matrix (classification is constant per receipt type — see below)

| receipt type | projected species | claimed target/use | classification | rule triggered | looks correct? |
|---|---|---|---|---|---|
| `ActivationReceipt` | `OBSERVED` | the activation act, as promotion evidence | **ADMITTED** (always) | none | species ✓ / **blind to `trial_value`, `prior_baseline_value`** |
| `LiveSurvivalObservationReceipt` | `OBSERVED` | survival evidence | **ADMITTED** (always) | none | species ✓ / **blind to `in_bounds`, `disqualifying_events`** |
| `ReplayHoldoutReceipt` | `OBSERVED` | non-regression witness | **ADMITTED** (always) | none | ✓ as mechanical obs / **blind to `passed`; hardcoded `is_proof=False` disarms R5** |
| `OperatorBasisReceipt` | `NORMATIVE` | promotion authority | **ADMITTED** (always) | none | charitable ✓ / **blind to `explicitly_not_auto_baseline` (the red line)** |

**Reachability probe:** the set of classifications the shadow produces for any *present*
real receipt, across all 11 shapes, is exactly `{admitted}`. The gate refuses 9 of 11
shapes; the shadow refuses **0 of 11**. The shadow is, on current AG receipt shapes, a
constant function: present → ADMITTED, absent → absent.

## The four things you asked me to look for

**1. False refusals from over-broad species mapping — NONE.** No well-formed receipt is
falsely refused. But note *why*: the projectors hardcode `consumer="promotion"`, copy
`scope` from an always-present field, and copy `freshness` from the receipt's reading. The
reliance-context rules (`MISSING_SCOPE` / `MISSING_FRESHNESS` / `CONSUMER_SCOPE_MISMATCH`)
can't fire because the adapter pre-supplies everything they check. Clean — but cheaply so.

**2. Rules unreachable from any real receipt shape — ALL EIGHT.**

| rule | needs | why unreachable today |
|---|---|---|
| `formal_bound_to_world_without_model_fidelity` | `MODEL_BOUND` species | no projector emits it |
| `testimonial_promoted_to_fact` | `TESTIMONIAL` + `presented_as_fact` | no projector emits `TESTIMONIAL` |
| `proof_receipt_promoted_to_system_safety` | `is_proof` + `presented_as_system_safety` | replay hardcodes both False |
| `constructed_or_hybrid_kind_presented_as_stable` | `kind_claim ∈ {CONSTRUCTED,HYBRID}` | no projector sets `kind_claim` |
| `allocating_or_enforcing_instrument_presented_as_measurement` | `instrument_role` set | no projector sets it |
| `missing_scope` | world-species w/o scope | scope always copied from a present field |
| `missing_freshness` | freshness-required w/o freshness | observation always carries `observed_at` |
| `consumer_scope_mismatch` | no consumer | consumer hardcoded `"promotion"` |

The shadow's **entire refusal vocabulary is dead code** against current AG shapes.

**3. Evidence fields the projection silently discards** — precisely the domain-verdict
fields: activation drops `trial_value`/`prior_baseline_value` (*what* is being promoted);
observation drops `in_bounds`/`disqualifying_events` (*the bounds verdict — the whole
point*); replay drops `passed` (*did it pass?!*), `falsification_basis`,
`comparator_baseline_id`; operator-basis drops `explicitly_not_auto_baseline` (*the red
line*) and `promotion_basis`. Consistent with "projection not evaluation" — but it means
the shadow sees the **envelope, not the verdict**. It is structurally blind to everything
that distinguishes a good receipt from a bad one.

**4. One receipt, multiple legitimate uses, adapter hardcodes one — YES, twice.**
- `ReplayHoldoutReceipt` is projected `OBSERVED` + `is_proof=False` +
  `presented_as_system_safety=False`. But a non-regression replay is plausibly relied on
  **as a safety/falsification proof** — exactly where R5 would bite. The adapter
  pre-decides the benign framing, **disarming its own tripwire**.
- `OperatorBasisReceipt` is projected `NORMATIVE` (authority). It is equally readable as
  `TESTIMONIAL` (the operator's testimony). The charitable reading never trips R4; the
  testimony-presented-as-fact reading would. The adapter picks the reading that can't fail.

In both, the verdict is **baked into the projection choice, not discovered**. The shadow's
"ADMITTED" is the adapter agreeing with itself.

## The answer to the actual question

**The matrix is boring and clean — decisively. On current AG receipt shapes, normal_form
is restating doctrine over a carefully shaped adapter, not observing a live seam.** No
current promotion-evidence receipt attempts an illegitimate species conversion, so every
refusal rule is unreachable and the shadow is a constant ADMITTED.

The honest nuance: this all-ADMITTED result is **true, not a bug**. AG's promotion path
does not mix epistemic species — domain admissibility (found/fresh/in-bounds/walkable/
operator-basis) is the gate's, and that is genuinely where AG's risk lives. The
species/conversion seam normal_form describes is real *in the abstract*; it is simply **not
load-bearing in AG's promotion path today**. The shadow's value is therefore purely
prospective — a tripwire for a *future* evidence type that emits `MODEL_BOUND`/
`TESTIMONIAL`, sets `kind_claim`/`instrument_role`, or is relied on as proof/safety. None
exists now.

## Recommendation

**P0 is done for now.** Making the shadow "more observed" by manufacturing a violation
(e.g. adding a `TESTIMONIAL` receipt type just to watch a rule fire) would be theater with
better test coverage. The next AG move is a **fresh cold admission for the real P4 trial
evidence path** — that is what produces the non-empty real evidence set a genuine semantic
witness would need, and it deserves its own admission, not P0 ornamentation.

Stop here. No wiring, no new enforcement.
