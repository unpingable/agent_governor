# Constellation Lexicon — register & metaphor hygiene

**Status: PROVISIONAL** (landed 2026-06-10). The control surface for the language
ratchet. Where the internal↔ops glossary (`docs/reference/internal-ops-glossary.md`)
maps *terms* between layers, this lexicon governs *register and metaphor* in prose —
two different surfaces; do not merge them.

This lexicon is **frozen during any sweep that patches against it**: workers patch
against the lexicon, not alongside it. Proposed amendments go to a receipt for operator
review, never as live edits mid-sweep.

## Core invariant

> **Refusal is an evidentiary boundary operation, not punitive enforcement.**

The machinery checks evidence at boundaries. It does not patrol, prosecute, or punish.

## Register rule (operator-ratified)

agent_gov's register is the model, tilted **ops over governance**: prefer ops verbs
(check, gate, refuse, admit, quarantine, hold, release, verify) over governance nouns
(adjudication, sanction, ceremony) **and** over law-enforcement / border / carceral /
courtroom metaphor. When in doubt, describe the mechanism (what evidence is checked,
what boundary is crossed, what is admitted or refused) rather than reaching for a
policing or courtroom image.

## Deprecation map

Applies to **prose framing on active / public / operator-facing surfaces**. Not code
identifiers, APIs, enums, CLI flags, or schema fields (those need their own forcing
case).

| Deprecated | Preferred (ops register) | Notes |
|---|---|---|
| border cop / traffic cop / cop | boundary checker / verifier / gate | "Governor (traffic cop)" → "Governor (gate)" |
| police / policing | check / validate / gate | "enforce" ONLY where the substrate actually blocks (AG's write-gate genuinely enforces — keep there) |
| border (metaphor) | boundary / admissibility surface | "Z3 border scanner" → "Z3 boundary scanner/checker". CSS/geometry `border` exempt |
| illegal X | inadmissible / unsupported / invalid X | incl. "illegal state/verb/lift" |
| offender | rejected claim / invalid artifact | |
| jail / prison / carceral | quarantine / containment / holding | |
| parole | release / promotion / re-admission | |
| arrest | halt / stop | |
| criminal | (drop metaphor; name the actual failure class) | |
| trial (courtroom) | evaluation / check run | English "trial run" exempt |
| judge (role metaphor) | reviewer / checker / evaluator | "the wicket judge" → "the wicket checker". **"judgment model" / "judge panel" (model-tier & harness vocab) stay** — they name discretion grade, not courtroom drama |
| court / courtroom / verdict-drama prose | review surface / evaluation | |
| sentence (punitive) | outcome / consequence | English "sentence" exempt — manual-review term, never bulk-grep |
| deport / immigration / ICE / migra | (drop metaphor; describe admission/refusal mechanics) | |
| law enforcement / LEO | checking / gating | |
| notquery | **nq** | all active/public surfaces; one "(formerly notquery)" lineage note per doc is permitted where genuinely historical |

## Retained terms of art (NOT deprecated — do not "fix")

- **verdict** — live code + doctrine vocabulary (receipt_kernel `Verdict` enum,
  SuiteVerdict, the two-verdict ratchet). Retained as a term of art; just don't build
  new courtroom prose around it.
- **enforcement** — where a gate actually blocks (AG's core promise). Replace only
  vibe-usages.
- **jurisdiction, quorum, dissent, custody, witness, refusal, admissibility** —
  established native-home terms (glossary discipline: never rename native homes).
- Code identifiers, APIs, enums, CLI flags, schema fields — out of scope entirely.

## Exempt content classes (skip even when terms match)

1. Editorial / essay content about literal law, politics, prisons (e.g. neutral.zone
   archive essays).
2. Paper titles + citations (e.g. P25 `epistemic-border-control`) — lineage, not framing.
3. Quoted material, unless re-used as current framing.
4. Archived / historical notes not indexed into active surfaces. If an index/README
   leaks them into operator view, patch the *index-side* framing or quarantine the link.
5. CSS/UI `border`, geometry, "trial run", grammatical "sentence".

## Preserve-distinctions list

signed ≠ witnessed; observed ≠ authorized; authorized ≠ safe; present ≠ fresh;
consumer A ≠ consumer B; missing bridge ≠ logical impossibility; runtime refusal ≠
Lean refutation; **refusal ≠ punishment**.

## Control-surface rule (binding for any sweep)

The lexicon is the control surface; workers patch against it, not alongside it. It is
**frozen** for the duration of a sweep — no worker, and no coordinator mid-sweep,
"improves" it. A worker who believes the lexicon is wrong for a case files the case in
their *ambiguous-left-untouched* bucket; proposed amendments land in the rollup receipt
as follow-ups for operator review, never as live edits.

## Dead-name refusal line (binding)

> Do not bulk-rewrite historical lineage, citations, archived notes, or old release
> references merely to erase provenance; patch **active / public / operator-facing
> leakage only**. The goal is *no leakage*, not *memory-hole everything and break
> lineage*.

## Composes with

- `docs/reference/internal-ops-glossary.md` — maps internal↔ops *terms*; this lexicon
  governs *register/metaphor*. Distinct surfaces.
- `memory/feedback_kind_fit_is_guard_not_enum` — this is PROVISIONAL prose doctrine, not
  a linter or code enum. A lint/CI hook is a future candidate only if drift recurs.
