# P4 real-trial evidence — COLD admission (2026-06-16)

Cold admission note, written before any code (build-order step 1). This is the
handle for review, not authorization to build. The runner is **not** written; the
first seam (below) has to be adjudicated by the operator first, because inspecting
it changed what "a real trial" can honestly mean.

## Admitted slice (verbatim)

> Run one bounded, real `max_slices=4` self-governance trial and produce durable
> evidence for later inspection.

### Authorized
- Apply the already-defined trial value temporarily.
- Produce real on-disk activation, observation/survival, replay-holdout, and
  operator-basis receipts.
- Preserve artifacts and lineage.
- Evaluate whether the evidence chamber is complete.

### Not authorized (fences)
- Promotion to `ControlBaseline`.
- Baseline mutation or supersession.
- Calling the promotion gate as an effectful operation.
- Fixture/config-hash stand-ins.
- Fuse/kernel work.
- Broadening to a second tunable or profile.
- Repairing weak evidence after seeing the outcome. *(The fence against the trial
  becoming an evidence-manufacturing workshop.)*

## Re-orientation from disk (receipts, not memory)

- **Branch/worktree:** `main`, single worktree `/home/jbeck/git/agent_gov`. Clean
  except pre-existing unrelated working-tree edits + untracked notes.
- **P0 committed + unpushed:** `07fe959` (P0 shadow pass) is the **single** unpushed
  commit; `origin/main = 76497ab`. ✓ matches "P0 committed and unpushed".
- **Memory correction:** `MEMORY.md` / the 2026-06-15 RESUME say the P4.0b mint and
  slices are "local, NOT pushed". On disk they are **already pushed** (mint `e8cb8e2`
  is ~12 commits behind `origin/main`). Only the later P0 work tip is unpushed. The
  push-status line in those notes is stale; the code state is what governs.
- **Chamber empty:** `.governor/control_baselines/`, `.governor/promotion_evidence/`,
  `.governor/active_tunables/`, `.governor/activation_receipts/`,
  `.governor/activation_spend/` are **all absent**. ✓ chamber-empty boundary holds.
- **Machinery present:** P3.1 four-office `activate()` (`activation.py`); the four
  evidence producers + stores (`promotion_evidence.py`, `observation_admissibility.py`,
  `replay_holdout.py`, `operator_basis.py`, `promotion_evidence_store.py`); read-only
  discovery (`promotion_discovery.py`); mint + operational-promotion
  (`promotion_mint.py`, `operational_promotion.py`); `control_baseline.py`.

## The first seam (inspected before the runner) — LOAD-BEARING FINDING

The operator's design question: *prove the trial value was operationally active — a
witness from the execution path or resulting state that binds the trial identity to
the behavior actually run; do not accept "the config contained `max_slices=4`."*

I inspected it. The finding is worse than the warning anticipated, and it falsifies
the naive runner plan:

> **Nothing consumes `decomposition_size / max_slices`.** It is *written* by the
> four-office `activate()` into `ActiveTunableStore`
> (`active_tunables/values.json`), but **no code reads `ActiveTunableStore`** (grep:
> zero readers outside `activation.py` itself). The orchestrator `run()` takes no
> slice-count input; `decomposition_completeness` does not read it; the annealing
> observer classifies *pipeline-outcome patterns*, not "was `max_slices=4` in effect".

Cheapest falsification, run first (per debugging discipline): *"does any execution
path consume the tunable?"* → **no**. So:

1. There is **no execution-path witness** possible: behavior under `max_slices=4` is
   byte-identical to behavior under `8` — the value changes nothing that runs.
2. The **resulting-state witness** can only attest "the value sits in a config file
   written via a custodied four-office receipt." It cannot bind to *behavior actually
   run*, because no behavior depends on it.
3. The code already concedes this in its own words
   (`operational_promotion.py:41`): *"3c performs no live config custody and no real
   `max_slices=4` promotion against a live surface. The 'operational' claim is about
   the real-evidence path + durable persistence, not live config wiring."*

Consequence for the admitted slice: a "live survival witness" produced now would be
observing a workload that is **indifferent to the trial value**. The observations
would be in-bounds-or-not for reasons unrelated to `max_slices`. That is precisely
the "evidence-manufacturing workshop" the admission forbids — dressed as a real
trial. Producing it would launder *inert state custody* into *survival evidence*.

There is also a structural seam underneath: the **promotion-evidence
`ActivationReceipt`** (chain root, `trial_id`/`trial_value`, in
`promotion_evidence.py`) is a *different object* from the **P3.1
`activation.ActivationReceipt`** (the four-office receipt that actually writes the
config surface). Today nothing binds the former to the latter. Even an honest
resulting-state witness would require choosing that binding (e.g. promotion-evidence
`trial_id`/a new field = the four-office `activation_id`).

## The fork (operator's call — HIGH / authority boundary)

I am stopping here rather than writing a runner, because which of these the slice
*means* is the operator's to decide, and getting it wrong manufactures fake custody:

- **A — resulting-state-only trial, honestly labelled.** Run the real four-office
  `activate(max_slices=4)` against `.governor/` (real config write + custodied P3.1
  receipt), bind the promotion-evidence chain to that `activation_id`, and produce
  observation/replay/operator-basis receipts — but record on every receipt and in the
  closeout that the survival witness attests *state custody*, **not** survival of the
  value's effects (no consumer exists). The chamber fills; the evidence is real *as
  state-custody evidence* and explicitly weak as *operational-survival* evidence. Risk:
  it still reads like a "real `max_slices=4` trial" downstream unless the hollowness is
  loud and permanent.

- **B — wire a real consumer first (new surface; needs its own admission).** Make the
  decomposition path actually read `decomposition_size/max_slices` from
  `ActiveTunableStore`, so `4` vs `8` changes what runs and observations witness real
  behavior. This is the only path to a *genuine* operationally-active witness — and it
  is a new surface this slice does not authorize. Would require a fresh cold admission.

- **C — record the falsification and hold.** Treat "nothing consumes the tunable" as
  the slice's real (negative) result: the chamber **cannot be honestly filled** as an
  operational-survival trial without B. No runner. Capture this note + a one-line
  status update; leave the chamber empty by design (the same shape as the successful
  3c outcome).

My recommendation: **C now, B as the real next slice.** A is admissible only if the
operator explicitly wants the chamber populated with state-custody evidence under a
loud "not operational-survival" label — but A spends effort producing evidence whose
own honest caption says it doesn't answer the trial's question, which is close to the
forbidden workshop. The cheapest honest move is to name the missing consumer (B) as
the precondition the plan actually always had.

## Exit states
- **C (recommended):** this note + status line; chamber stays empty; B queued with
  its own admission. No code.
- **A (if operator elects):** runner that produces real-but-state-only receipts, every
  artifact captioned non-operational; closeout states the survival witness is hollow.
- **B (if operator elects):** new cold admission for wiring a tunable consumer, then a
  genuine trial on top of it.

## Do-not-touch
Kernel/fuse/ratification invariants; second profile; mint/promotion as an effect;
the pushed mint commits; `convergence_tuning` import direction.

---

## RESOLUTION — C (operator-present, 2026-06-16)

Operator elected **C now, B as a separate narrowly-scoped slice next**. Rationale
(operator, verbatim sense): *the admitted trial slice has already produced its
decisive result — there is no trial surface; continuing would counterfeit the
premise rather than test it. A is the bad option: "state-custody, not
operational-survival" is honest in the artifact body, but downstream structure still
looks like a populated promotion chamber — evidence whose main semantic property is a
disclaimer is how weak evidence acquires tenure.*

### Slice closeout (the negative result of record)
- `max_slices` is persistently **activatable but operationally inert** (written to
  `ActiveTunableStore`; no reader anywhere).
- **No behavioral trial occurred** (none is possible without a consumer).
- **No survival or replay evidence may be minted** from this slice.
- **Promotion chamber remains empty** (by design — same shape as the successful 3c
  outcome).
- The **P4 trial-evidence path is BLOCKED on an actual consumer** (slice B below).
- The **P3.1 `activation.ActivationReceipt` and the promotion-evidence activation
  root are also unbound** (a second precondition B must close).

### Three-layer separation (why B ≠ trial ≠ promotion)
- **B establishes CAUSALITY:** activated value → changed execution.
- **Trial slice establishes CONSEQUENCE:** changed execution → observed
  survival/replay evidence.
- **Promotion establishes AUTHORITY:** evidence → baseline change.

Combining them would let one slice invent the actuator, run it, judge it, *and*
prepare its promotion record — efficient, and how small constitutional monarchies
happen. The real-trial slice reopens only after B has its own verified closeout.

Cold admission for B: `working/P4-B-tunable-consumer-admission-2026-06-16.md`.
No code was written this session.
