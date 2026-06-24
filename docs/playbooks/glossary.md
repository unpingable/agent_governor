# Governed Playbooks — Glossary

Terms of art. Where a term has a one-line doctrine, it's quoted.

## Objects

- **PlaybookSpec** — inert authored artifact: text, hash, `claimed_kind`, provenance,
  typed input constraints. No authority.
- **CertifiedPlaybook** — PlaybookSpec + composition receipt; carries `certified_kind`
  and structural check result. *Certified only over its input domain.*
- **RunRequest** — a request to run a CertifiedPlaybook; the object Wicket admits to
  judgment. Carries origin, proposal state, requested scope/effects.
- **RunPlan** — CertifiedPlaybook + bound inputs + target scope + actor + state
  assumptions + locked dependency closure. *The object Wicket admits at runtime — citing the
  resolved standing grant, spendability, and certification; no single organ admits it.*
- **RunInstance** — an executed RunPlan: step receipts, witnesses, spends, refusals,
  final claim, custody state.
- **BoundaryContract** — the shared leaf primitive (not `StepContract`): preconditions,
  authority required, allowed effects, required witnesses, emitted terminal outcome,
  custody behavior, freshness/reuse. A step / reactor-fence / approval-gate / emit-step
  each *implements* it.
- **ConvergenceFence** — the adaptor sealing a reactor sub-algebra behind a single
  pipeline-visible boundary. Emits one terminal `ConvergenceOutcome`; internal reactor
  multiplicity stays in the trace. The load-bearing, unproven bridge.
- **ConvergenceOutcome** — the one terminal value a fence emits: `AlreadyConverged`,
  `Converged`, `RefusedPreEffect`, `NonConvergedNoEffect`, `NonConvergedPartialKnown`,
  `InterruptedUnknownEffect`. Only the first two permit downstream progress.

## Tags

- **claimed_kind** — author's proposed composition kind; *input* to the checker. A field
  someone writes. Dispatches nothing.
- **certified_kind** — checker's output after verifying the artifact satisfies that
  algebra's invariants; a **measurement** (not authority). *Wicket's admission dispatches on
  this only.*

## Receipts

- **WicketAdmission** — proof a RunRequest is procedurally admissible for judgment. Binds
  request/playbook/kind/closure/input digests, scope, effect classes, origin, proposal
  state, parser/checker versions, validity window.
- **StandingReferenceResolution** — proof that a *referenced* standing grant resolves: the
  badge exists and scans. **Not execution authorization** — it does not mean you may drive
  the forklift. Authorization is split across organs, none of them this one: the grant facts
  (effect classes, budget, revocation epoch) are minted by **external Standing**; the
  **runtime admission verdict** is **Wicket's**; freshness is the **spendability seam**;
  capacity is **LA**. *(The old "Standing evaluates the RunPlan / Standing is the judge" thesis
  is retired as model-wrong: execution permission is the **conjunction** of all those organ
  receipts at the wall, not a verdict any one organ — including Wicket — issues alone.)*
- **LAReservation** — Linear Accountant's hold on scarce effect capacity, bound to the
  admission/eligibility reference (the Wicket admission), resource, mode, amount, ttl, holder,
  run_plan. *Reserves only against a fresh signed grant.*
- **NQ witness** — an observation receipt: "at T, observer O saw predicate P under method
  M." Evidence, not authority. Typed by `observed_claim_type`, subject, `observed_at`,
  method, scope, effect class.
- **refusal witness** — a typed `CannotTestify` / `InsufficientCoverage` /
  `FreshnessExpired` / `SubjectMismatch` receipt. *Missing witness is silence; refusal
  witness is testimony.*
- **approval_receipt** — human approval bound to a *frozen* `run_plan_digest` and effect
  boundary, with expiry. *Approval attaches to a digest, not a vibe.*

## Digests

- **dependency_closure_digest** — hash over the fully-resolved, digest-pinned set of
  sub-playbooks/imports (no `latest`, no mutable refs). Wicket's admission evaluates the whole
  closure, not just the top artifact.
- **bound_input_digest** — hash over the concrete, typed-and-constrained inputs of a
  RunPlan. (Parameter binding is a privilege-escalation surface; a certified playbook is
  certified only over its input domain.)

## Organs (one verb each)

- **Spine** — read plane: what can be found/read. *Presentation must not collapse into
  authority* (C4). Index (no status) / edition / stele. Currently parked (backburner).
- **Continuity** — recorded substrate: what can be relied on.
- **Maude** — human cockpit: render (← Spine) + adjudicate + trigger (→ Standing). *Input
  at Maude is proposal, not authority.* Not a god-surface.
- **Wicket** — may this proposal enter judgment, and is the run admitted? (procedural
  admissibility; owns the *"may run now"* verdict)
- **Standing** — does the *referenced* standing grant resolve? (reference resolution;
  freshness via the spendability seam). *Verification, not execution authorization.*
- **LA / Linear Accountant** — scarce-effect conservation: reserve/consume. *Reserves
  only against a fresh signed `may`.*
- **NQ** — testimony: what was witnessed/refused. *May testify; may not promote
  testimony into permission.*
- **Nightshift** — machine trigger / future candidate. *A schedule is not standing.*
- **Executor** — what effect happened. *Unknown effect is unknown custody, not no-effect.*
- **Registry** — index of inert artifacts (a Spine concern; no status; cannot bless).

## Master demon

> **Past validity is not present authority.** Every seam violation is this in costume:
> YAML / promotion / history / schedule / presence / index-entry doing a signing
> receipt's job.
