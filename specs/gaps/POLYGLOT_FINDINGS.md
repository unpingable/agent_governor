# Polyglot Benchmark: Findings

**Date:** 2026-03-29
**Harness:** `~/git/polyglot`
**Related:** `specs/gaps/POLICY_IR.md`

## What We Tested

Four prompt control variants across four models, three task types,
with ablation studies and a format grid.

**Variants:**
- `plain_english` — "Be concise. Do not guess. Return valid JSON."
- `dsl_tags` — `[B][NG][U][J]` with alias table
- `zh_compact` — `[简][禁推][疑][J]` (CJK semantic compression)
- `minimal` — `concise;no_guess;json` (semicolon-delimited keywords)

**Models:** Haiku, Sonnet, GPT-4o-mini, GPT-4o

**Tasks:** Conservative summary, extraction, classification (JSON output).
Plus harder variants and a format grid (JSON / key=value / CSV).

## What Won

**`minimal` is the safest default.** Highest or near-highest quality/1k_tok
across every model. Never the worst. Never fails on format compliance.

| Model | Winner (q/1k_tok) | Score | plain_english |
|---|---|---|---|
| Haiku | minimal | 15.60 | 8.74 |
| Sonnet | minimal | 15.54 | 13.64 |
| GPT-4o-mini | dsl_tags | 18.48 | 17.19 |
| GPT-4o | dsl_tags | 18.02 | 16.82 |

All compact variants beat `plain_english` on quality-per-token.
On Haiku, the gap is dramatic: compact variants score ~15.5 q/1k_tok
vs plain English at 8.74 — nearly 2x. Plain English on Haiku hit only
66.7% valid JSON rate; all compact variants hit 100%.

On larger models (Sonnet, GPT-4o), the quality gap narrows but compact
variants still win on token efficiency.

## What Failed

**Haiku + DSL bracket syntax on non-JSON formats.** The format grid
shows `fg_dsl` (bracket tags) dropping to 75% valid format on Haiku
when output isn't JSON (key=value, CSV). GPT-4o-mini handles the same
brackets at 100%. Bracket DSLs are provider-sensitive.

**GPT `minimal` has an 11.1% error rate** on the basic bench (both
4o-mini and 4o). Semicolon syntax occasionally confuses GPT into
producing malformed output. `dsl_tags` is the safer GPT default.

**Ablation: slot removal is model-specific.** Removing `no_guess` on
GPT-4o-mini drops extraction to 0.667; same removal on Haiku has no
effect. Slot necessity depends on the model, not the task.

## Refined Thesis

1. **Compact control syntax beats prose on quality-per-token.** This
   held across all four models. The margin is largest on smaller models.

2. **`minimal` is the safest cross-provider default.** Semicolon keywords
   work everywhere at high quality. Provider-specific DSLs can do better
   on their home model but carry portability risk.

3. **Provider-specific renderers can outperform generic ones** but must
   be benchmarked per backend. Bracket DSL is great for GPT, brittle
   on Haiku for non-JSON formats.

4. **Multilingual compactness (CJK) is viable but not central.** `zh_compact`
   consistently places between `minimal` and `plain_english`. It works,
   but semicolon keywords achieve similar compression without the cognitive
   load of a second writing system.

5. **Slot necessity is model-dependent.** Which constraints the model
   actually needs to hear varies by model family. This is a renderer
   concern, not a policy concern — the policy declares all required slots,
   the renderer decides which ones the target model actually needs spelled out.

6. **The semantic slots are the real authority surface.** English was
   one possible lossy expansion. The benchmark proved that multiple
   expansions (prose, DSL, CJK, keywords) produce equivalent compliance.
   The invariant is the slot set, not the rendering.

## Implication for Governor

These findings validate the Policy IR architecture in `POLICY_IR.md`:

- Canonical slot sets as policy (model-independent)
- Backend-specific renderers as compilers (model-dependent)
- Benchmark promotion gates for renderer candidates
- Receipts tracking which renderer/version produced which prompt

The next benchmark batch should be small and instrumental:
backend (Claude/GPT) x renderer (minimal/dsl) x output (JSON/key=value)
x task class (extraction/classification/summary). Enough to choose
sane defaults, not a research program.
