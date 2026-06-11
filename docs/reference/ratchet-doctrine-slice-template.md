# Ratchet-Doctrine Slice — template

**Status: PROVISIONAL** (2026-06-10). A reusable shape for the kind of slice that
*formalizes a builder-loop / ratchet doctrine* — docs-and-records only, no code. Distilled
from the **two-verdict ratchet** slice (commit `2b8eca3`,
`working/campaign-tick-tock-builder-ratchet.md` § "The builder loop"), which is the worked
exemplar — read it alongside this skeleton.

Use this when a campaign has surfaced a recurring discipline worth naming and pinning
(an invariant, an ordering rule, a verdict split) and you want it landed cleanly without
scope creep into code, schema, or premature global promotion.

## 1. Frame (one block, top of plan)

- **Who executes:** name the tier per the routing rule (`feedback_model_tier_routing`).
  Doctrine/vocabulary seams are judgment-tier; the *landing* of agreed doctrine is often
  downgradeable. State it.
- **Scope:** "docs/records only; no code, no schema, no enum, no glossary row" — say what
  it is NOT, up front.
- **Estimate:** small. If a doctrine slice is growing past ~an hour, it's smuggling
  implementation.

## 2. Context

- **Forcing specimen.** A *concrete* observation that motivates the doctrine — the real
  event, not an abstraction. (Two-verdict: "Tick 1 shipped green cargo while the control
  plane was failing open.") Cite it by name.
- **Operator direction**, and where it was ratified.
- **The named invariant ("the knife")** — one sentence, quotable, goes verbatim into the
  canonical doc. (Two-verdict: *"the patch worked" must not launder "the process was
  unsafe."*)
- **Naming decisions, incl. rejected names + why.** If a name was considered and
  rejected, record the rejection (two-verdict rejected "Epicycles" — implied compensating
  for a wrong model). Saves future re-litigation.

## 3. Changes (records only)

- **Campaign card** (the canonical home): add the doctrine section — the rule/loop, the
  invariant, an **ordering or precedence note** if the doctrine has one, a **worked
  example** retro-cast from the forcing specimen, and a one-line **name breadcrumb**.
  Add a maturity/“why this matters” line.
- **Memory**: short addendum to the relevant `feedback_*` pin + the MEMORY.md index
  line. Doctrine-promotion rule: **stays local until a second campaign repeats it** —
  do not promote to `~/.claude/CLAUDE.md` on first sighting.
- **Cross-links**: one line each into the adjacent reference surfaces it touches
  (task-packet-template, glossary, lexicon) — light cross-reference, *not* a merge.
  ("Don't overbraid it into a scarf.")

## 4. Non-goals (load-bearing — copy and adapt)

- No code, no enum/schema, no report-format tooling. Prose vocabulary in a working doc is
  a guard, not a typed `Kind` (`feedback_kind_fit_is_guard_not_enum` fires if tempted).
- No renaming the campaign/file (the doctrine is a *name inside* the campaign, not a
  rebrand).
- No glossary row (internal working vocabulary ≠ consumer-facing rename) unless it
  genuinely reaches an operator surface.
- No promotion to `~/.claude/CLAUDE.md` (candidate until a second campaign uses it).
- No retro-editing prior tick/tock/run reports — they used the older numbering; note the
  mapping, don't rewrite history.

## 5. Verification

- Read-back coherence pass: canonical doc carries the rule + invariant + ordering +
  worked example + breadcrumb; memory addendum indexed; cross-links present.
- **One commit.** (Push per session policy.)

## Composes with

- `working/campaign-tick-tock-builder-ratchet.md` — the campaign these slices live in;
  the two-verdict section is the exemplar.
- `docs/reference/task-packet-template.md` — sibling template (for cargo packets, not
  doctrine slices). Different artifact: packets bind *action*; this lands *doctrine*.
- `memory/feedback_campaign_card_discipline.md`, `memory/feedback_model_tier_routing.md`,
  `memory/feedback_kind_fit_is_guard_not_enum.md` — the disciplines this template encodes.
