# Language Ratchet — audit receipt

Date: 2026-06-10. Control surface: `docs/reference/constellation-lexicon.md` (frozen
during this sweep). Core invariant: *refusal is an evidentiary boundary operation, not
punitive enforcement.*

## Scope decision (coordinator)

The plan envisioned a Sonnet fan-out across 13 repos. The pre-sweep scan (below) showed
the genuine contamination surface is **small and judgment-dominated** — most raw hits are
retained doctrine, legal-standard usage, established live-ops vocabulary, or provenance
attributions, where a naive sweep would *damage* meaning (the exact risk the negative
controls guard against). Per the coordinator's "define scope, prevent overreach" mandate,
the fan-out was scoped down to a **coordinator-led pass**: ~6 clear metaphor fixes applied
directly, everything else deliberately retained or deferred with reasons. The operator's
prediction held — disciplined islands, few corner cases.

## Scan methodology

Word-bounded `rg` over `.md`, exempt dirs excluded (`archive/`, `historical/`,
`graveyard/`, `.git/`). Tuned term set (NO bare `sentence`, NO `verdict`, NO
case-folded `ice`):

```
border cop|traffic cop|cops?|police|policing|illegal|offender|jail|prison|parole|
arrest|criminal|courtroom|court|judges?|deport|immigration|migra|law enforcement|LEO|notquery
```

In-scope repos scanned: agent_gov, scheduler, nightshift, maude, linearaccountant,
atproto-nutrition, rpp, wlp, verifier, wicket, standing, nq-root/nq. neutral.zone:
non-archive only (archive essays are exempt class 1 — literal law/politics/prison
content).

## Files changed (6 changes, 2 repos)

**agent_gov** (5):
- `docs/architecture/OVERVIEW.md` — "Governor (traffic cop)" → "Governor (gate)".
- `docs/architecture/claim-custody-spine.md` — "tiny courtroom" → "tiny adversarial
  review"; "the wicket judge" → "the wicket checker" (the lexicon's named example).
- `docs/agent-governor-meta-plan.md` — "Lean is constitutional law. Z3 is the border
  scanner … before the judge has to pretend" → "Lean is the constitutional kernel. Z3
  is the boundary scanner … before it reaches a gate that would have to pretend".

**verifier** (1):
- `README.md` — "A border cop between measurement and claim." → "A boundary checker
  between measurement and claim." (public README first line; `verdict` usages retained.)

Also (separate, committed in Slice 0): NQ path correction `~/git/notquery` →
`~/git/nq-root/nq` across active agent_gov docs + a hardcoded test path.

## Deliberately retained (negative-control survivors — NOT contamination)

- **LinearAccountant "judge" (all usages)** — *core doctrine*: "it counts spend; it does
  not judge … a cash register, not a judge." "Judge" is the precise contrast-concept LA
  is built to refuse. Sweeping it would damage doctrine. `linearaccountant` left CLEAN.
- **COMPLIANCE.md "judged ex ante"** — the fiduciary / prudent-person legal standard
  (literal legal context, exempt class 1). Untouched.
- **"not a judge" / "not a court" contrast framing** — verifier, rpp, wlp, atproto
  ("does not judge truth"), agent-governor-meta-plan "checker, not judge" heading. These
  *deprecate* the metaphor by negation; already correct. Untouched.
- **`verdict`** (receipt_kernel, SuiteVerdict, two-verdict ratchet, verifier output),
  **`enforcement`** (where the gate blocks), **`jurisdiction/quorum/dissent/custody/
  witness/admissibility`** (native-home terms) — retained terms of art, zero diff hunks.
- **CS idiom "illegal transition"** (RECEIPT_KERNEL_CONTRACT.md) — standard state-machine
  vocabulary; left (low-value, idiomatic). Logged as borderline.

## Deferred — cross-repo owners' call (not patched)

- **atproto-nutrition "parole-mode"** (PROD_STATUS.md, RUNBOOK.md) — an *established live
  operational mode name* doing real semantic work ("parole, not exoneration" =
  conditional/revocable override vs permanent). Carceral metaphor, but rewriting a live
  ops term in another project's runbook is its owner's call. Label: `language-cleanup-needed`.
- **wicket "Tiny courthouse, not Supreme Court cosplay"** (gap doc) — self-aware
  deprecation humor in another repo's gap doc. Label: `language-cleanup-needed`.
- **wlp / standing "filed by notquery-Claude"** — *provenance attributions* of a 2026-05-27
  filing. Per the dead-name refusal line (don't erase lineage), left as historical record.
- **scheduler / nightshift dead `notquery` path refs** (gap/decision docs) — broken
  cross-references to the moved NQ repo (`../../../../notquery/...`, `~/git/notquery/...`).
  These need repathing to `~/git/nq-root/nq`, but that's those repos' owners' correctness
  fix, not a language patch. Label: `nq-path-correction-needed`. (Also: scheduler and
  nightshift returned byte-identical hit lists — possible mirror/shared content, worth a
  separate look.)

## Ambiguous, left untouched (the anti-overreach fuse)

All of the "Deferred" items above are also the ambiguous bucket — each is untouched *with
a recorded reason*. No item was rewritten on a guess.

## Follow-up labels needed

- `language-cleanup-needed`: atproto-nutrition (parole-mode), wicket (courthouse).
- `nq-path-correction-needed`: scheduler, nightshift (dead notquery path refs).

## Negative controls (all PASS)

- `verdict` retained where a term of art (verifier README: 12 occurrences, untouched).
- `enforcement` unchanged where the substrate blocks.
- `jurisdiction/quorum/dissent/custody/witness/admissibility` — zero diff hunks.
- CSS/geometry `border` (`visual_registers.md`) — UNCHANGED.
- `neutral.zone/content/archive/` — repo CLEAN (never touched).
- `linearaccountant` — repo CLEAN (doctrine preserved).
- Paper titles/citations (e.g. `epistemic-border-control`) — intact.

## Commits

agent_gov: Slice 0 (lexicon + path correction) `1a32142`; Slice 1 metaphor fixes +
this receipt (separate commit). verifier: one commit. No pushes.
