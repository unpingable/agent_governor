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
