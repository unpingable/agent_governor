# DECISIONS — AG-classic Reference Freeze

> All items **OPEN** — none ruled. Recommendations are planner output, not authority.
> Per loop-protocol §9, a ratified entry's `default_action` may be applied without
> re-asking; until ratification there are no defaults in force.

## D1 — GAP-M: Gemini adapter fail-open

- **Question:** `runtime/adapters/gemini_cli.py` fail-opens on socket error, while
  fail-closed pre-tool gating is a guarantee-typed claim of the reference (Claude Code
  adapter was fixed in tock-01; Gemini was ruled-as-deferred).
- **Options:** (a) fix — make the Gemini pre-tool gate fail-closed, mirroring tock-01;
  (b) demote — Gemini adapter to Tier 4 with a hard disclaimer ("supervised Gemini
  sessions are NOT fail-closed governed").
- **Recommendation:** (a) fix. Guarantee-typed seam → coverage is conjunctive; the fix is
  small and pattern-proven. If declined, (b) is mandatory — silence is an overclaim.
- `applies_when`: S5. `requires_human_if`: always (this ruling).

## D2 — R1–R4 inexpressibility family

- **Question:** the program's top unruled item is custody-affecting and predates this
  campaign. The freeze cannot silently close or bypass it.
- **Options:** (a) rule R1–R4 before the freeze declaration; (b) explicitly park them
  *as part of* the freeze declaration (recorded in G6 text as known-unruled, successor-era).
- **Recommendation:** none — genuinely operator's; depends on whether any R1–R4 ruling
  would change frozen-contract content.
- `applies_when`: before S7. `requires_human_if`: always.

## D3 — Card weight

- **Question:** heavyweight capsule (`docs/campaigns/ag-classic-reference-freeze/`) vs
  lightweight `working/campaign-*.md`.
- **Recommendation:** capsule (filed as such): terminal gates, cross-repo touchpoints,
  and vocabulary authoring exceed the lightweight form. Ratification confirms or demotes.
- `applies_when`: S0.

## D4 — Correspondence pin timing

- **Question:** author the ledger now against Lean v14-pushed (candidate pin) with a
  mandatory re-pin at Lean-DOI inside G4, or wait for the DOI mint before S4.
- **Recommendation:** candidate-pin now. The three-beat sequencing was built to overlap
  the DOI audit with beats 1–2; G4 still hard-requires the DOI pin, so nothing launders.
- `applies_when`: S4.

## D5 — Release tag naming / version

- **Question:** what the reference release is called and what version digit it carries.
- **Constraint:** per `versioning_by_custody_grade` — the major digit is the authority
  verb lawful at REAL custody grade; the tag must not overclaim grade.
- **Recommendation:** operator names it at S7; the card deliberately does not pre-coin it.
- `applies_when`: S7. `requires_human_if`: always (custody-affecting).
