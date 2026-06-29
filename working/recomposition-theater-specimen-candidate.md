# Candidate specimen: "recomposition theater" (NOT doctrine, do not promote)

> Status: **candidate specimen / failure-mode label.** Non-binding scribble. Do NOT
> create a doctrine doc from this; do NOT add the "prompt forge" to AG. This is a
> shard kept for legibility, cross-linking primitives AG already has.

## The label

**Recomposition theater:** the failure mode where *structured-completeness-as-competence*
causes recomposed advisory material to be misread as grounded authority.

- "Recomposition theater" = the field name.
- "Structured-completeness-as-competence" = the sharper analytic term.
- Public aphorism: **"Cute plan. Show me the custody chain."**

## Why it's a specimen, not a new object

The decompose → recompose pipeline (intake → diagnosis → options → comparison →
recommendation → execution → artifacts) is **not** an AG primitive — it's how
consultants make slide decks. The AG-relevant thing is the single sentence:

> structured completeness is rhetorically persuasive enough to impersonate authority.

That collapse is the same one AG is already built to refuse — for agent output, not
just consumer output:

```
agent produced steps  →  agent may run steps          (NO)
recomposed plan       →  authorized plan              (NO)
structured-completeness → grounded authority          (NO — this specimen)
```

## Consumer example (the specimen)

A ChatGPT consumer-app ad: a prompt that compresses intake → diagnosis → options →
visual mockups → comparison → execution plan, so the user sees a designer + analyst
+ shopper + PM + budgeter shape and starts treating that shape as competence /
authority. The completeness is the persuasion; the custody chain is absent.

## Governed counter-example (already built)

The synthetic overnight conveyor is the governed variant of the same pattern:
`ReviewPacket` = recomposed decision material that is **structurally** non-authoritative
(`operator_review_required` defaults True; status is evidence, not authority);
`QueuedPlaybook` = decomposed intent with an explicit authority fence;
the S5 validator = recomposition may not exceed granted authority.

## Cross-link ONLY (do not restate these — they are the actual law)

- `src/governor/pipeline_types.py` — `account_boundaries()` / `RecompositionReceipt` /
  `VERDICT_REFUSED_LAUNDERING`: a decomposition whose dropped boundary is unaccounted
  is refused regardless of how green the surviving slices are.
- `working/directional-invariants.md` — one-way kernel: "no later-stage artifact may
  supply an earlier-stage authority"; the 6 forbidden conversions.
- `docs/doctrine/annealing_and_recomposition.md` — existing recomposition doctrine.
- `src/governor/decomposition_completeness.py` — "decomposition ≠ understanding".
- Synthetic conveyor: `src/governor/playbooks/review_packet.py` +
  `review_packet_validator.py` (the governed counter-example above).

## If it ever graduates

File as a *specimen* (the way `case_railway` / `case_do_router` are filed — memory
topic files), pointing UP at the primitives above. Never as a parallel doctrine doc
(that would be the duplicate-authority smell AG exists to detect).
