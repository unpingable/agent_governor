# Internal ↔ Ops Glossary

**Status: living glossary. Rows added/ratified as terms surface. PROPOSED rows are operator-proposed but not yet binding consumer-facing vocabulary.**

This glossary maintains the bilingual translation surface between the
constellation's internal/theory/doctrinal vocabulary and the
operator-facing ops vocabulary. It exists because:

1. Other claudes (papers, standing, wicket, nq, scheduler, continuity,
   etc.) are writing the internal vocabulary in parallel; AG cannot
   unilaterally rename the shared terms.
2. Ops-facing surfaces (CLI flags, error messages, dashboards, README,
   run books) need vocabulary that survives contact with logs and with
   people who don't read jurisprudence textbooks.
3. The two layers will drift if there's no canonical mapping. Drift
   between internal and ops vocabulary is how a doctrine gets one
   meaning in the paper and a different meaning in the production
   behavior — i.e., laundering.

## Discipline

- **Do not rename internal native homes.** If a term lives in another
  repo's SPEC, in `docs/doctrine/`, in `~/git/papers/`, or in
  cross-claude continuity scope, the internal name stays.
- **Do not invent ops names without operator review.** Ops names that
  appear in CLI flags, error messages, dashboards, or README copy are
  tier-2 binding (per
  `memory/feedback_artifact_authority_classification.md`); one review
  pass, then land.
- **Do not let the two sides drift.** When an internal term sharpens
  (e.g., the "self-amendment" rule sharpening to "directional custody"
  on 2026-06-10), the ops side either re-syncs or this glossary records
  the divergence with a `Notes:` entry explaining why.
- **Terms with universal-ops fitness stay on both sides** without
  translation (refusal, receipt, witness, scope, freshness, gate).
  These are already operational English; no rename buys anything.

## Status legend

- **PROPOSED** — operator-proposed mapping, not yet binding on
  consumer-facing surfaces. Use the internal name in code until ops
  ratification.
- **RATIFIED** — operator-ratified for use on consumer-facing surfaces
  (CLI, dashboards, error messages, README). Internal name still
  preserved at native home.
- **PROVISIONAL** — landed somewhere but not formally ratified.
  Re-litigation possible.
- **UNIVERSAL** — same term on both sides; no translation.

## Bilingual mapping

| Internal / theory / doctrinal term | Ops term                                | Status     | Native home(s)                                                              | Notes |
| ---------------------------------- | --------------------------------------- | ---------- | --------------------------------------------------------------------------- | ----- |
| genesis fiat                       | operator bootstrap                      | PROPOSED   | doctrine docs; endgame-synthesis-2026-06-10.md                              | Operator-proposed 2026-06-10. The act that mints receipt #0 / boot of the gate stack. |
| receipt #0                         | bootstrap receipt                       | PROPOSED   | endgame-synthesis-2026-06-10.md; constitutional rule discussion             | Operator-proposed 2026-06-10. The first receipt in the chain — the one that authorizes the gate stack to exist. |
| standing grant                     | action entitlement                      | PROPOSED   | `~/git/standing` SPEC; AG `standing/` validator; doctrine                   | Operator-proposed 2026-06-10. Internal `standing grant` stays at native home; ops surfaces should prefer `action entitlement` for legibility. |
| wicket admission                   | gate check                              | PROPOSED   | `~/git/wicket` SPEC; AG `wicket_client.py`                                  | Operator-proposed 2026-06-10. Internal stays; ops uses `gate check` — but `gate` is UNIVERSAL elsewhere, so disambiguation matters. |
| self-amendment                     | unattended gate mutation                | PROPOSED   | endgame-synthesis-2026-06-10.md; directional-invariants.md                  | Operator-proposed 2026-06-10. The constitutional rule's failure mode. |
| operator-curated (work source)     | approved work source                    | PROPOSED   | §3b actuation pin; endgame-synthesis-2026-06-10.md                          | Operator-proposed 2026-06-10. Discriminates allowed backlog sources from agent-generated backlog (the ninth LLM must-not). |
| LLM must-not                       | model boundary rule                     | PROPOSED   | §3b actuation pin (9 must-nots)                                             | Operator-proposed 2026-06-10. The list itself stays internal-doctrinal; ops summary calls them "boundary rules." |
| freeze (frozen reference boundary) | incident suspension                     | PROPOSED   | `~/git/linearaccountant` boundary doctrine                                  | Operator-proposed 2026-06-10. Internal `freeze` is fine; ops surfaces likely benefit from `suspension`. |
| admissibility                      | admission / acceptance                  | PROPOSED   | papers; `docs/architecture/claim-custody-spine.md`                          | From `working/parked-constellation-alignment-pass.md`. Carried forward. |
| jurisdiction                       | authority_scope / route_scope           | PROPOSED   | AG `jurisdictions.py`; doctrine                                             | From parked alignment pass. |
| mandamus                           | bounded_progress / stall_duty           | PROPOSED   | papers; doctrine                                                            | From parked alignment pass. Quarantine to papers unless a specific runtime surface needs it. |
| conversion                         | promotion / effect_upgrade              | PROPOSED   | papers; meta-plan §directional kernel                                       | From parked alignment pass. |
| refusal propagation                | blocker_propagation                     | PROPOSED   | papers; doctrine                                                            | From parked alignment pass. |
| custody                            | source_chain / handoff_chain / provenance | PROPOSED | papers; doctrine                                                            | From parked alignment pass. Multiple ops-side handles depending on which custody axis is named. |
| refusal                            | refusal                                 | UNIVERSAL  | S4-lite vocabulary; CLI                                                     | Operational already; no rename. |
| receipt                            | receipt                                 | UNIVERSAL  | `gate_receipt.py`; CLI; docs                                                | Perfect word. No rename. |
| witness                            | witness                                 | UNIVERSAL  | NQ; AG; CLI                                                                 | Already systems language. |
| scope                              | scope                                   | UNIVERSAL  | AG `scope.py`; CLI                                                          | Already operational. |
| freshness                          | freshness                               | UNIVERSAL  | AG drift / TTL; doctrine                                                    | Already operational. |
| gate                               | gate                                    | UNIVERSAL  | AG `gate_receipt.py`; doctrine                                              | Already operational. (Note: `gate check` uses this for wicket admission ops-side; the term itself is shared.) |
| drill                              | drill                                   | UNIVERSAL  | NQ `origin_mode=drill`; AG `governor why` DRILL prefix; nightshift CLI      | Already ops-shaped via the fire-drill / game-day frame. |
| convertible spend boundary         | (no ops translation yet)                | INTERNAL-ONLY | `~/git/linearaccountant`; endgame-synthesis-2026-06-10.md                | The thaw-trigger language; technical enough to stay internal. |
| directional custody                | (no ops translation yet)                | INTERNAL-ONLY | endgame-synthesis-2026-06-10.md; directional-invariants.md                 | The constitutional rule's underlying *why*; doctrine-only. |

## Artifact classification pin: documents vs procedures

**Operator-ratified 2026-06-10.** Classification by authority effect, not file format:

> **Documents describe; procedures bind action to condition.**
>
> Procedures are binding-class artifacts: unlike documents, which
> describe, procedures pre-authorize action under named conditions and
> must be ratified, hash-pinned, drilled, and cited by hash in run
> receipts.

Consequences of the pin (the pin itself is ratified; everything below
the line items is demand-side, not yet designed):

- `document` → descriptive-class → tier-1/2 of
  `memory/feedback_artifact_authority_classification.md` (land/one
  review pass).
- `procedure` → binding-class / pre-authorized intent → HIGH band:
  ratification cadence like policy admission, hash-pinned, drillable,
  revocable, cited by hash in every run receipt.
- **"Runbook" is ambiguous and must not flatten procedures into
  documentation.** Filing a consequence-bearing artifact under "docs"
  is claim-kind laundering. A markdown file can be a document; it can
  also be a loaded gun wearing YAML — classify by what it *binds*, not
  what it looks like. (The existing `ops_governor` `Runbook` type
  predates this pin; renaming it is demand-side cleanup for whenever
  that surface is next touched, not now.)

**Not designed yet, deliberately:** ProcedureSchema, step taxonomy,
reversibility ontology, procedure-mode wiring in Maude/Nightshift. The
wal-bloat gauntlet is the first procedure-shaped forcing case; its gap
list names the future fields. Jurisdictional sketch (candidate,
non-binding): nightshift owns procedures and their runs (watchbill =
scheduled half, procedures = event-triggered half); Maude supervises
procedure execution, never orchestrates; NQ witnesses
preconditions/postconditions/closure.

## How to use this glossary (for any claude reading this)

If you're writing code that touches consumer-facing surfaces (CLI flags,
error messages, dashboards, README copy):

1. Look up the term you want to use.
2. If RATIFIED, use the ops name.
3. If PROPOSED, use the internal name in code (matches existing
   codebase) but write CLI/error-message copy that uses the ops name
   AND surface the proposal to the operator for ratification.
4. If UNIVERSAL, use as-is.
5. If INTERNAL-ONLY, don't use it on consumer-facing surfaces; pick
   adjacent ops-friendly framing.

If you're writing doctrine docs, papers, or cross-claude continuity
material, use the internal names. Internal vocabulary is the canonical
form for cross-tool coordination.

If you find a term that's missing from this glossary and you need to
make a decision about which side to use it on: stop, add a PROPOSED row
to this file with `Status: PROPOSED — not-yet-classified`, and surface
to the operator. Do not invent an ops translation unilaterally.

## Composes with

- `working/parked-constellation-alignment-pass.md` — the original park
  of this rename pass. Operator unparked it 2026-06-10 with the
  bilingual refinement: the rename is glossary maintenance, not
  rip-and-replace.
- `memory/feedback_artifact_authority_classification.md` — tier-2 rules
  for ratification cadence on ops-side terms.
- `working/endgame-synthesis-2026-06-10.md` — the synthesis that
  surfaced the need to lock the bilingual mapping before Maude/LA
  wiring begins.
- `docs/agent-governor-meta-plan.md` — the §3b actuation pin's
  vocabulary (refusal kinds, outcome classes, LLM must-nots) is
  primarily INTERNAL by intent; the ops-friendly summary lives in
  `docs/reference/refusal-and-outcome-vocabulary.md`.
- `docs/reference/refusal-and-outcome-vocabulary.md` — the
  closed-vocabulary reference is ops-friendly today; it's the model
  for what RATIFIED bilingual terms look like.
- `memory/relational_role_induction_keepers.md` — handle ≠ standing;
  reminder that ops naming can paper over standing distinctions if
  rename is sloppy. Glossary discipline guards against this.
