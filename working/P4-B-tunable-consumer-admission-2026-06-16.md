# P4-B — tunable consumer (operational-activation witness) — COLD admission (2026-06-16)

Cold admission handle for the slice that **precedes** the real trial-evidence slice.
Written as the record of scope, NOT as authorization to build. No code until this
admission is operator-confirmed and its own verified closeout exists.

Provenance: forced by the negative result of the real-trial slice
(`working/P4-real-trial-evidence-admission-2026-06-16.md`, resolution C). The trial
slice falsified its own premise — `decomposition_size/max_slices` is activatable but
operationally inert (no consumer). B exists to establish the missing causality
*before* any survival/replay evidence is ever minted.

## What B is (scope — narrower than "wire a consumer")

> Establish and witness **causality only**: an activated tunable value changes what
> the canonical decomposition execution actually does. Stop once operational
> activation is witnessed. Produce **no promotion evidence**.

Operator-set steps (verbatim intent):

1. **Identify the canonical decomposition execution point.** The one real place
   where slice count / decomposition size governs bounded execution. (Candidates to
   inspect, not presume: `cooked_context_orchestrator.run`, `decomposition_completeness`,
   `pipeline_types`. The point must be a real executor, not a config echo.)
2. **Make it read the active tunable under explicit custody.** Read
   `decomposition_size/max_slices` from `ActiveTunableStore` via a custodied path —
   not a bare global, not a caller-passed number that launders provenance.
3. **Prove `4` and `8` produce observably different bounded execution.** A real
   behavioral delta (e.g. slice count / boundary set), demonstrable by test, not by
   inspecting the config file.
4. **Bind the execution witness to the actual P3.1 `activation_id`.** The witness of
   "this run executed under the activated value" must reference the four-office
   `activation.ActivationReceipt.activation_id` that wrote the value — closing the
   currently-unbound seam between the P3.1 receipt and any downstream evidence.
5. **Do NOT produce promotion evidence yet.** No `LiveSurvivalObservationReceipt`,
   no replay-holdout, no operator-basis, no bundle, no mint. B stops at causality.
6. **Stop once operational activation is witnessed.** Verified closeout, then halt.
   The real-trial slice reopens only afterward, under its own fresh admission.

## Authorized (when B is confirmed)
- Inspect to find the canonical execution point.
- Wire a single, custodied read of the one admitted P3.1 tunable into that point.
- Add tests proving the `4` vs `8` behavioral delta and the `activation_id` binding.
- Emit a verified closeout (cargo + dogfood verdict; bare-exit-code discipline).

## Not authorized
- Producing ANY promotion evidence (observation/survival, replay, operator-basis,
  bundle, mint) — that is the trial slice, gated behind B's closeout.
- A second tunable, a generic activation/consumer framework, or any surface beyond
  the one P3.1 tunable (`decomposition_size/max_slices`).
- Mutating a `ControlBaseline`; calling promotion/mint as an effect.
- Kernel/fuse/ratification invariant changes.
- Reading the tunable from anywhere other than the custodied `ActiveTunableStore`
  path (no provenance laundering through a caller-supplied integer).

## Open questions for B (resolve at its admission, not now)
- Is there a single canonical decomposition executor, or several? If several, which
  one is the operationally-load-bearing one (the rest may be out of scope)?
- Does the executor currently take a slice count at all, or must the read be
  threaded in? (Determines whether step 2 is a wiring or a small refactor.)
- What is the cheapest test that proves a *behavioral* delta (not just a different
  number flowing through)?

## Litmus (scope check)
This is NOT speculative expansion: the consumer is table-stakes for the category —
"a tunable nothing reads" is a definitional gap in an activation system, not a
future feature. But it IS a new effect surface, so it earns its own cold admission
rather than riding the trial slice's momentum.

## Exit states
- **Confirmed + built:** steps 1–4 done, step 5 honored (zero promotion evidence),
  verified closeout; real-trial slice becomes reopenable.
- **Confirmed but blocked:** no single canonical execution point exists / the
  refactor is larger than a wire → re-scope at B's admission, do not force it.
- **Declined:** B stays a named candidate; the trial-evidence path stays blocked.

---

## INSPECTION RESULT — STOPPED BEFORE CODE (operator-present go, 2026-06-16)

Operator gave B the go; first task was inspection, not wiring, with an explicit
stop condition: *stop before code if there is no single honest insertion point.*
**That condition fired.** Read-only inspection finding:

> **There is no slice-count-bounded executor anywhere.** `max_slices` limits nothing
> today — not planned, not scheduled, not completed slices.

Evidence (cheapest falsification, run first — *who builds a plan / reads a cap in
production?* → nobody):

- The only surface that carries decomposition boundaries is
  `cooked_context_orchestrator.run(recomposition_plan=...)`. That plan is a
  **caller-supplied `Sequence[str]`** the orchestrator only *accounts* (against the
  chain's traversal) — it never **cuts or caps** it.
- `recomposition_plan` is constructed **only inside the orchestrator module itself**;
  there is **no production caller** of `.run()` (none in `cli.py` / `daemon.py`). The
  orchestrator's only users are `drill_runner.py` and `why.py` → it is a **drill-only
  SPEC harness**, not a live execution path (matches `file-structure.md`'s label).
- `max_slices` / `slice_cap` are allowlisted *targets* under `decomposition_size`
  (`activation_preflight.TARGET_ALLOWLISTS`) — names a delta *may activate*. The
  allowlist gates **activation eligibility, not consumption**. Zero readers.

The operator's six pins, answered by the inspection:
- **what `max_slices` limits:** nothing — no executor cuts/caps slices; the only
  plan-bearing surface is a caller-supplied boundary sequence in a drill-only harness.
- **where default `8` comes from:** nowhere in code — "prior baseline 8" was
  illustrative in the P4 plan doc, not a live default.
- **when the active value is resolved:** never (no consumer) → moot.
- **missing/malformed/stale/unsupported active state:** moot (nothing resolves it).
- **how `activation_id` reaches the execution witness:** there is no execution
  witness — no execution consumes the value.
- **what observable difference proves `4 ≠ 8`:** none is honestly producible. The
  only candidate (truncating `recomposition_plan` to a cap) **drops declared
  boundaries**, which is exactly the `refused_laundering` condition the enforcement
  gate exists to refuse. Capping it would be incoherent, not a behavioral delta — and
  it would only ever cap drill fixtures.

The trap the operator named ("don't let the orchestrator merely *report*
`max_slices=4` while producing the same work") is, in this codebase, the **only**
thing currently possible — which is why the honest move is to stop.

**Conclusion:** making `max_slices` operational is not "one bounded consumer." It
requires inventing a slice-planning/capping **actuator** on a real execution path and
deciding where decomposition authority lives — duplicating policy / widening
authority, beyond B's scope. B is **STOPPED before code**, pending an operator
decision on whether to (i) re-target the trial onto a tunable that *already* has a
live consumer, or (ii) open a separate, properly-admitted slice to build the
decomposition actuator first (a much larger surface than B), or (iii) leave the
self-governance trial-evidence path parked as architecturally premature.
