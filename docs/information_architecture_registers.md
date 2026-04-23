---
audience: repo-local
status: active
---

# Information Architecture Registers

Status: doctrine (interpretive)
Audience: anyone organizing a governed surface — product UI, atlas,
console, documentation tree, queue, inventory, admissibility view.
Purpose: extend the register discipline of `document_registers.md`
and `visual_registers.md` to information architecture. Name the
three IA registers Governor already uses in practice, and pin the
rules that keep layout from silently widening what the system
actually supports.

> Questions above, objects below. Never let the menu outrun the pantry.

## Why this exists

Prose and pixels can lie. So can **arrangement**.

A surface organized by implementation — "detectors," "services,"
"rules engine," "schema registry" — quietly teaches the operator
that the system *is* those things, and that questions must be
asked in those terms. A surface organized by operator question —
"what is happening," "why does the system believe that," "what is
blocked" — teaches what the system is *for*.

The failure mode is **ontological smuggling by navigation**: the
left nav becomes the schema, the schema becomes the worldview, and
the user stops noticing that denial, staleness, and partiality have
no home in the surface at all. By the time that's been true for a
week, the system has drifted into "things that don't appear here
don't exist."

Layout is policy. This document names the three IA registers
Governor already uses, and pins the rules that keep the menu from
outrunning the pantry.

## The three registers

### Situation

- **What:** atlases, overview dashboards, top-level indexes,
  system-wide queues, health strips, "everything in scope right now"
  views.
- **Job:** answer "what is going on across the scope I am
  responsible for?" at a glance. Orient without deciding.
- **Shape:** summary rendering, universe declaration mandatory,
  refusal and partiality reachable from the top level. Compresses
  underlying objects. Must not widen what those objects support.

### Subject

- **What:** the canonical home of a governed object — a receipt, a
  policy, a dependency, a memory, an admissibility decision, a scar.
  One definite place per object.
- **Job:** render the object in full: state, basis, freshness,
  allowed actions, blockers, history. Answer "what is this thing
  and where does it stand."
- **Shape:** the blunt spine (below) in stable placement. Every
  register-relevant fact in a predictable slot. Links out to
  evidence, not inline reproduction.

### Cross-cut

- **What:** queues, filtered lists, search results, pivoted views,
  dependency maps, "all objects matching X."
- **Job:** help the operator find or compare objects across the
  population.
- **Shape:** explicit about the slice ("what universe, which filter,
  as of when"). Never the canonical home for any object. Follows
  back to Subject for full state.

A surface typically contains all three registers. The discipline is
in not confusing them: a queue view is not a dashboard and is not
an object page, and collapsing any of the three into another
produces the same class of lie.

## The blunt spine

Every governed object, on its canonical Subject page, organizes
around seven slots, in this order:

1. **What it is** — kind, identity, scope.
2. **What state it is in** — current classification.
3. **Why the system believes that** — basis, evidence, provenance.
4. **How fresh that belief is** — last assessed, contract-relative
   freshness.
5. **What is allowed next** — actions currently authorized on this
   object.
6. **What is blocked, partial, or denied** — refusal reasons,
   missing inputs, suppressions, required review.
7. **What changed** — history, supersession, recent transitions.

If one of these seven slots is absent, the absence is itself a
claim. Render it ("no actions available," "no prior state," "no
blockers") rather than omitting the slot.

## Honesty rules

Load-bearing. Each answers a failure mode seen in adjacent products.

### 1. Organize by operator question, not implementation

Top-level structure maps to operator questions — state, basis,
action, refusal, history — not to how the codebase emits things.
"Detectors," "services," and "subsystems" are implementation
categories; they may appear as *filters* but never as the
organizing spine.

### 2. State, basis, and action are separate

If a surface collapses "what is true" / "why the system believes
it" / "what you can do about it" into one block, fake authority
appears immediately. The three must be visually and structurally
distinguishable. Actions are not evidence. Evidence is not verdict.

### 3. Time is a state, not metadata

Freshness is part of the claim. "Active" without "last assessed"
is incomplete. "Current" without a freshness contract is a lie.
For governed surfaces the time axis lives in the spine, not in a
tooltip.

(Borrowed from ARIA's states-vs-properties distinction: freshness
*changes*, so it is state; state does not live in a footnote.)

### 4. Refusal and partiality need homes

`denied`, `stale`, `partial`, `suppressed`, `requires_review`,
`no_basis` must live cleanly in the IA — reachable from Situation,
surfaced on Subject, filterable in Cross-cut. If refusal is only
visible by clicking "advanced" or parsing an error string, refusal
does not exist in the surface.

### 5. Descend situation → subject → proof

Navigation goes overview → object → evidence. The operator can
always answer "what," then "which one," then "on what basis."
Skipping a tier — Situation views that jump straight to evidence
blobs, or Proof views without a linked Subject — strands the
operator.

(This is the HATEOAS insight applied to IA: each tier must name
its possible next moves. Affordance is a layout requirement, not a
style preference.)

### 6. Organize by consequence, not just type

A flat list of "alerts" or "findings" is too flat. Severity is a
subset of consequence, not the whole of it. Operational
consequence — what is blocked, what must be reviewed, what is
stale past its contract — is the axis. Type is a secondary filter.

### 7. Stable things get stable homes

Freshness, basis state, scope, authority, source links, policy id,
supersession lineage — if these move between views, users stop
reading them and start *vibing* them. A field that appears in the
upper-right of one view and the bottom of another loses its
meaning. Consistency of placement is consistency of claim.

### 8. Compress, do not widen

A Situation rollup may be less detailed than the Subject pages it
summarizes. It may not claim more, stronger, or simpler states
than those Subjects support. Rolling up seven distinct refusal
reasons into "attention needed" is compression; rolling "stale"
and "fresh" into "current" is widening. Compression is fine.
Inflation is a lie.

(Same discipline as `document_registers.md` rule #4 and
`visual_registers.md` rule #4, applied to arrangement. Every
register, every surface, same rule.)

### 9. Exhaustiveness is a claim

Every map, atlas, queue, or dashboard must answer, visibly, "what
universe of things am I looking at?" The closed set:

- **exhaustive** — all known objects of this kind, in scope, now
- **curated** — a human-chosen subset (identify the curator)
- **sampled** — statistical subset (identify the sampling rule)
- **filtered** — a named filter is active
- **partial** — evidence is incomplete (name what is missing)
- **delayed** — data lag past a named threshold

Unmarked defaults silently to "exhaustive" in the operator's mind
and is the most common IA lie. Declare the universe, or do not
ship the surface.

(The RFC tradition calls this the applicability statement: a
spec without one will be read against whatever scope the reader
happens to want. Same mechanism applies to a dashboard.)

### 10. Cross-cuts are views; every object has a canonical home

Search, filters, tag pivots, saved queries, queues, atlases —
fine, often essential. But every object must have one definite
Subject page where its full state and lifecycle live. Without that
anchor, the surface becomes query-shaped mush: every object is
everywhere and nowhere, and no claim about the object has a
stable citation target.

## Reference IA grammar

Aligned with the standing lattice, `document_registers.md`, and
`visual_registers.md`. Suggestions; a surface may use other names
as long as rules #1–#10 hold.

| Region | Register | Holds |
|---|---|---|
| **Overview / atlas** | Situation | universe declaration, counts by state, refusal and partiality visible from the top |
| **Object page** | Subject | the blunt spine (1–7) in stable placement |
| **Evidence panel** | Subject (nested) | basis, receipts, provenance, freshness contract |
| **Queue / list** | Cross-cut | named slice, explicit scope, links back to Subject |
| **Map / atlas view** | Situation or Cross-cut | exhaustiveness declared; absence rendered as absence |
| **History / timeline** | Subject (nested) | supersession, transitions, scoped to the object |
| **Search** | Cross-cut | explicit query state; no claim of exhaustiveness unless declared |

**Universe declaration, refusal surfacing, and a canonical Subject
are not optional.** A surface missing any of these three is
operating on vibes, not state.

## Non-goals

This document does **not**:

- standardize navigation labels or component hierarchies globally
- force every surface into exactly one of three registers
- prescribe a specific sitemap, left-nav structure, or URL scheme
- replace platform-specific guidance (mobile, CLI, TUI) where
  concrete affordance constraints dominate
- mandate a specific universe-declaration vocabulary (the list in
  rule #9 is a reference, not a ratification)

It stays scoped to **register, arrangement, and authority**, not
"how to structure an app."

## Examples

### Paired: admissibility decision

- **Situation:** the top-level cadence view shows counts by verdict
  (admissible / inadmissible / stale / partial), declares universe
  ("all admissibility checks in the last 24h, as of *N seconds
  ago*").
- **Subject:** the decision page shows what-state-basis-freshness-
  allowed-blocked-changed for *this* decision. Violations listed as
  first-class items with explain-links to the validator contract.
- **Cross-cut:** "all inadmissibility decisions this week" is a
  filter view, links to each Subject, never doubles as a Subject
  itself.

### Paired: memory record

- **Situation:** the memory browser shows counts by reliance class,
  with `observed` and `committed` as structurally separate rows,
  never summed into a single "memory count."
- **Subject:** the memory page shows reliance class as a state
  (rule #3), basis as a separate section (rule #2), allowed
  actions distinct from evidence (rule #2 again).
- **Rejected:** a single "memories" list that interleaves observed
  and committed without visual separation. Violates rule #2 (state
  and basis collapsed), rule #4 (no home for the boundary), rule
  #8 (widens the operator's sense of authority).

### Paired: dependency atlas

- **Situation:** grid-dependency-atlas declares its universe
  ("mapped critical infrastructure, as of *last-refresh*; partial
  for regions *X, Y*"). Gaps rendered as gaps.
- **Subject:** each dependency node has a canonical page with
  jurisdiction, operator, upstream, supersession, last audit.
- **Rejected:** a smooth national heatmap with no universe
  declaration. Violates rule #9 (exhaustiveness not declared),
  rule #4 (partial regions have no visible home), rule #8
  (interpolation widens the coverage claim).

### Rejected: a bad IA

- A governance console with top-level nav: Services / Rules /
  Events / Settings.
- Rejected because: organized by implementation, not operator
  question (rule #1); denial, partiality, and refusal have no home
  in the nav (rule #4); no universe declaration at the top level
  (rule #9); objects do not have canonical pages — they appear
  under Services *and* Rules *and* Events depending on what fired
  (rule #10).
- Corrected: State / Why / Actions / Blocked / History as the
  top-level spine, with Services/Rules/Events available as filters
  inside each. Compressed, but faithful — and each top-level region
  maps to an operator question.

## Adoption by reference

Other repos in the constellation (Continuity, NQ, Night Shift,
Custody, Dossier, grid-dependency-atlas, etc.) may **adopt this
pattern by reference**. No central body ratifies adoption. A
downstream surface that wants IA register discipline can cite this
document and follow rules #1–#10.

"Adopt by reference" rather than "inherit" because nothing here is
automatic. It is a pattern others can reach for when it fits their
surface; it is not a cross-repo IA contract.

## The residual risk

An IA that enforces these rules is still *navigable*, not austere.
The aim is not bureaucratic interfaces. The aim is that the
arrangement of the surface carry the same boundary the docs and
pixels carry: refusal exists, evidence is named, scope is
declared, freshness is claimed.

The specific trap at 2am under deadline pressure is **nav-by-
codebase**: shipping a left-nav that mirrors whatever subsystems
happen to exist, because that is the structure already in the
committer's head. That nav teaches the operator the product *is*
the subsystems — which is almost never what the operator needs to
ask. Resisting that shape is part of the job.

## Compressed lines

- Questions above, objects below.
- Never let the menu outrun the pantry.
- Layout is policy.
- Exhaustiveness is a claim. Declare your universe.
- Absence is a state. Give it a home.
- `denied` is not optional. Neither is `stale` or `partial`.
- Every object has a canonical home or it has no home at all.
