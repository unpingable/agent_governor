---
audience: repo-local
status: active
---

# Visual Registers

Status: doctrine (interpretive)
Audience: anyone designing a surface that renders Governor state,
builds a landing page in the constellation, or produces visual
artifacts (dashboards, atlases, diagrams) that publish governance
information.
Purpose: extend the two-register discipline of `document_registers.md`
to visual surfaces. Name the visual registers Governor already uses
in practice, and pin the rules that keep pixels from outrunning
evidence.

> State below, pixels above. Never let the pixels outrun the state.

## Why this exists

Governor's doctrine is a claim about authority: law below, verbs
above, verbs never outrun the law. The same claim has to hold at the
visual surface, because graphics can lie in ways prose can't —
faster, more confidently, and without anyone reading a word.

The failure mode is **epistemic laundering**: a visual treatment
that converts partial or absent evidence into the felt experience
of verified truth. A pulsing green badge over "all healthy" when
the system has no findings is not a report of health; it is
confidence without basis. The graphic has widened what the
underlying state supports.

This document names the three visual registers that already exist
across the constellation — marketing sites, product UIs, and
governance surfaces — and pins the rules that keep each register
honest.

## The three registers

### First-contact

- **What:** landing pages, project sites, marketing surfaces,
  explainer diagrams, conference slides, onboarding visuals.
- **Job:** orient a new reader fast. Establish tone, capability
  class, worldview. Teach the boundary before they touch anything.
- **Shape:** personality allowed. Motion that explains is allowed.
  Illustration that sets register is allowed. Marketing visuals
  are never the source of truth and must not imply capabilities
  the product does not have.

### Product

- **What:** app UIs, operator consoles, CLI TUIs, editor
  integrations, anything a working user drives day-to-day.
- **Job:** reveal state, support action, preserve trust. Content
  and state take precedence over brand spectacle.
- **Shape:** stable layout, high information density where
  warranted, clear hierarchy, restrained motion. Controls must
  be operable; text must remain legible; primary content must be
  visible without heroic effort.

### Governance

- **What:** receipts, verdicts, standing views, drift maps, label
  histories, admissibility grades, dependency atlases — any
  surface that publishes Governor-adjacent state as an
  artifact consumers will act on.
- **Job:** render state truthfully, including the parts that are
  absent, stale, denied, partial, or refused. Make the boundary
  between what is known and what is asserted visible.
- **Shape:** dignified explicitness. Refusal is a first-class
  state. Uncertainty is rendered, not buried. No ornamental
  certainty. No theatrical hiding of limits.

## Honesty rules

These are load-bearing. Each one answers a failure mode seen in
adjacent products.

### 1. State wins every conflict

If the visual surface says one thing and the underlying receipt,
record, or state says another, the underlying artifact is
correct. The visual surface is wrong and must be fixed. Never
the reverse. Dashboards do not author truth; they render it.

### 2. Visual states must map to real states

Every distinct visual treatment — color, badge, icon, motion
cue — must correspond to a defined state in the underlying
model. "Looks healthy" is not a state. "No findings in the last
N seconds against contract X" is a state. The first is
laundering; the second is a report.

### 3. Authority cues must cite

Any visual element that asserts authority, guarantee, or binding
— a "verified" checkmark, a "signed" ribbon, a "certified" seal
— must resolve, on interaction, to the artifact that grounds
it. If it cannot cite, it cannot claim. Unclickable trust
marks are decoration at best and fraud at worst.

### 4. May compress the state space; may not widen it

A visual register can show fewer states than the underlying
model supports. It may not show more, stronger, or simpler
states than the model supports. Collapsing "stale" and "fresh"
into "current" is a lie. Collapsing seven distinct refusal
reasons into "blocked" with a drill-down is compression.
Compression is fine. Inflation is a lie.

### 5. Refusal must be visible

A surface that only renders affirmative states — success, fresh,
allowed, healthy — hides the authority boundary and teaches
users that the system is a conveyor belt with a status badge
attached. `denied`, `stale`, `partial`, `superseded`,
`requires_review`, `no_basis` must be reachable through the
primary visual path, not buried in drill-downs or omitted
entirely when absent. **Absence is a state. Render it.**

## Reference visual grammar

Aligned with the standing lattice and `document_registers.md`
verb set. These are suggestions; a surface may use different
treatments as long as rules #1–#5 hold.

| State class | Visual cue | What it means |
|---|---|---|
| **observed** | neutral / muted | captured, not yet interpreted |
| **interpreted** | tinted, not asserted | diagnosis, hypothesis, ranked candidate |
| **proposed** | dashed border, advisory tint | recommendation, no binding |
| **authorized** | solid border, filled state | verdict bound to the system |
| **denied** | explicit refusal treatment, not just absence | the governor's distinctive move |
| **stale** | visible age marker, desaturation optional | basis exists but has aged past contract |
| **partial** | explicit partial treatment, never completion | some but not all evidence in scope |
| **superseded** | strikethrough or visible supersession link | replaced by a newer authorized artifact |
| **no_basis** | explicit empty-state, not decorative silence | the system cannot answer this question |

**`denied` and `no_basis` are not optional.** A surface that
omits them teaches users that silence is safety.

## Non-goals

This document does **not**:

- standardize visual style globally across the constellation
- force every surface into one of three buckets
- prescribe a specific color palette, type stack, or component
  library
- replace accessibility requirements or platform-specific UI
  guidance
- mandate a specific iconography (the above is a reference, not
  a ratification)

It stays scoped to **register and authority**, not "how to make
things look good."

## Examples

### Paired: admissibility rendering

- **Underlying state:** cadence emits `INADMISSIBLE` with
  violations `[semantics-mismatch, stale-current-claim]`.
- **Product surface:** red-bordered card, title "Inadmissible for
  decision use," violations listed as distinct items with
  explain-links.
- **First-contact surface:** may summarize as "cadence refuses
  temporally incoherent evidence" with an illustrative screenshot.
  May not imply the checker is a trust oracle.

### Paired: receipt chain rendering

- **Underlying state:** continuity memory with
  `reliance_class=observed`, never promoted to `committed`.
- **Product surface:** visibly distinct treatment from committed
  memories. Retrieval interaction does not imply authority.
- **Rejected:** showing observed and committed memories in the
  same visual register because "the user will figure it out."
  That violates rule #5 — the boundary must be visible by default.

### Paired: grid-dependency-atlas

- **Underlying state:** a community is mapped as dependent on
  infrastructure whose operator is outside its political
  jurisdiction.
- **Governance surface:** the dependency is rendered explicitly.
  Absence of data for a region is shown as absence, not as a
  blank on the map that reads as "no dependency."
- **Rejected:** a smoothed heatmap that interpolates across gaps.
  Interpolation without basis is rule-#4 widening: the map
  claims more than the evidence supports.

### Rejected: a bad governance surface

- A dashboard with a large green "SYSTEM HEALTHY" banner based
  solely on "no alerts in the last 5 minutes."
- Rejected because: `no_alerts` is not `healthy` (rule #2 —
  visual state does not map to real state); the banner inflates
  absence of findings into active verification (rule #4 —
  widening); refusal and partiality have no rendering path
  (rule #5 — refusal hidden).
- Corrected: a status strip showing `last_check`, `contract`,
  `findings_count`, `stale_sources`, with explicit rendering
  when any of those is absent or overdue. Compressed, but
  faithful.

## Adoption by reference

Other repos in the constellation (Continuity, NQ, Night Shift,
Custody, Dossier, grid-dependency-atlas, etc.) may **adopt this
pattern by reference**. No central body ratifies adoption. A
downstream surface that wants register discipline can cite this
document and follow rules #1–#5.

"Adopt by reference" rather than "inherit" because nothing here
is automatic. It's a pattern others can reach for when it fits
their surface; it's not a cross-repo visual contract.

## The residual risk

The product and governance layers are supposed to be legible,
but they should preserve the sense that Governor is a governed
system with refusal, evidence, and boundaries — not a helper
orb with a nice gradient on it. If the visual layer gets too
polished, it starts hiding the scar tissue. Resisting that
hiding is part of the job.

The specific trap at 2am under deadline pressure is
**decorative certainty**: pulsing greens, smooth interpolations,
friendly empty-states, animated checkmarks. Each one, on its
own, is small. Together they teach the user that the system
never refuses and never doubts. That is a lie the interface
tells louder than any copy could.

## Compressed lines

- State below, pixels above.
- Never let the pixels outrun the state.
- Graphics may intensify orientation. They may not inflate certainty.
- Absence is a state. Render it.
- `denied` is not optional. Neither is `no_basis`.
- Let the website flirt. Let the app testify. Let the governance surface refuse.
