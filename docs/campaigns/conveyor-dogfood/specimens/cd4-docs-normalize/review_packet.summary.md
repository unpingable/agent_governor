# ReviewPacket cd4-docs-normalize — summary

> **Evidence, not authority.** This packet describes bounded work so the operator
> can review it. It cannot commit, push, merge, or bless anything.
> `operator_review_required: true`.

- **playbook:** `chore.docs-playbooks-normalize`
- **repo / branch:** agent_gov / main (base main @ `ad9d932`)
- **status:** **no_change**  lane=conveyor-dogfood
- **goal:** Normalize terminology across `docs/playbooks/*` per the landed glossary
  (zero semantic changes).

## Verdict in one line

The corpus is **already normalized** for every term the pass can safely act on.
Zero source files changed. The deliverable is the survey + two boundary findings,
not a diff — and one decision point handed back to the operator.

## Files changed

- (none)

## Tests

- `python3 -m pytest tests/playbooks -q` → **passed** (exit 0, 229 passed).
  Baseline unchanged — no edits were made, so green here is the pre-existing state,
  not evidence that an edit was safe.

## What was surveyed

All 26 markdown files under `docs/playbooks/`, for the five named terms
(`PlaybookSpec`, `CertifiedPlaybook`, `RunRequest`, `ReviewPacket`, `RationCard`)
plus the `BoundaryContract` / `StepContract` pair.

| Term | Finding | Action |
|------|---------|--------|
| `ReviewPacket` | 100% consistent (CamelCase in all 10 uses; zero lowercase) | none needed |
| `PlaybookSpec` | consistent as a symbol; lowercase only in licensed prose | none needed |
| `CertifiedPlaybook` | consistent as a symbol; glossary itself uses lowercase prose | none needed |
| `RunRequest` / `RunPlan` | consistent; kept distinct per glossary (not synonyms) | none needed |
| `BoundaryContract` / `StepContract` | correct — `StepContract` only ever negated | none needed |
| `RationCard` vs "ration card" | **type is CamelCase; "ration card" is a metaphor** | **deliberately not merged** |

## The reconciliation sub-task (investigated to ground)

> "Reconcile the duplicated live-adapter-allowlist-review content from the two
> branch lineages."

**Finding: no duplication exists.** `git log --all --source` +
conflict-marker grep show the two lineages merged **linearly**:
`feat/playbooks-gov-loop` created the file; `feat/playbooks-synthetic-conveyor`
added the fresh-eyes re-review and the supersession banner **additively** on top.
The banner forward-references the fresh-eyes section; the fresh-eyes section says
verbatim *"This is additive: the 2026-06-30 record stands."* The successor
(`harness-cage-review.md`) **references** the 11 ration-card terms as inherited
constraints without verbatim-duplicating them. Nothing to merge or delete.

## Why (almost) nothing was edited — the boundary

Three apparent "inconsistencies" are load-bearing and changing them would breach
**zero-semantic-change** (and trip the run's own `halt_if`):

1. **"ration card" is a metaphor, not the type.** ~24 lowercase uses carry the
   door/lock/"no one has eaten with it yet" imagery. The `RationCard` type is
   correctly CamelCase where the class is referenced. Flattening metaphor → type
   would change register and meaning.
2. **Lowercase descriptive prose is licensed by the authority itself.** The
   glossary writes *"a certified playbook is certified only over its input
   domain."* So lowercase descriptive usage is not a violation.
3. **The two "executable unit" prose formulas** (README vs governed-playbooks)
   paraphrase the four-layer object model on purpose and are marked *"stated once
   and never weakened."* Tightening them to types collapses an intentional
   distinction.

## Decision point for the operator (classified)

**The glossary — the named authority for this pass — does not define
`RationCard` or `ReviewPacket`,** yet the plan names both as normalization
targets. Adding them is a **semantic amendment to the glossary**, which is an
explicit stop condition (*"the glossary itself turns out to need semantic
amendment … that is doctrine work, not a wording pass"*). So this run **stops
short** of it and hands the operator a clean choice:

- **(A)** amend the glossary to define `RationCard` + `ReviewPacket` (a doctrine
  gate, operator-run), or
- **(B)** record that they are code types intentionally outside the glossary's
  scope (no glossary change).

Either way, no wording in `docs/playbooks/*` needed to change to reach a
consistent state today. (See `followups` in the manifest.)

## Two receipt surfaces (specimen 2 framing)

Per the specimen contract, this run emits **two independent surfaces**, neither
citing the other as proof:

- **AG conveyor surface** — this ReviewPacket + the latched queue item +
  approval witness witness the *governance exercise* (was this SHAPE of work
  admissible, and what did it produce).
- **Maude M-2 envelope surface** — the run record (plan_ref, projected
  constraints, session receipts) witnesses *envelope enforcement*.

## M-4 legibility observations (CD-4B — agent drove the operator's seat)

Recorded as M-4 fuel, with the recorded caveat that the driver this run was the
session agent, not the human:

- **The envelope held mechanically, and the hold was observable.** A `sha256sum`
  helper invocation was **denied** — consistent with the ration card granting
  zero `allowed_shell_commands`. The pass adapted (left the optional artifact
  `sha256` fields null) rather than fighting the gate. Governance shaped the work
  without narration.
- **The specimen behaved as a trap for over-normalization.** "Normalize the five
  terms" is under-specified: two of the five aren't in the authority and one is a
  metaphor. A driver optimizing for a visible diff would have produced semantic
  damage. The correct output is a near-empty diff plus a decision point — which
  is legible only if you trust "no_change" as a real, valued outcome.
- **The reconciliation instruction resolved to "already done."** Verifying that
  required reading git lineage, not just the file — the kind of grounding a human
  driver would need the tooling to surface, not re-derive by hand.
