# Policy IR A/B Findings

**Date:** 2026-03-31
**Model:** claude-haiku-4-5-20251001 (Haiku)
**Harness:** bench/run_ab.py
**Corpus:** bench/corpus.json (12 tasks × 4 modes)

## What happened

1. Built Policy IR: control slots as canonical policy, two renderers
   (prose = incumbent, minimal = compact syntax).

2. First live run exposed a hidden dependency: prose wasn't just policy,
   it was also smuggling output-shape constraints. Minimal saved input
   tokens but the model compensated by generating more output.

3. Promoted the hidden semantic into explicit slots: `OUTPUT_DISCIPLINE`
   (global) and `PATCH_OVER_ESSAY` (code-specific). MinimalRenderer v0.2
   adds brief inline expansions for output-category slots.

4. Third run: net +761 tokens saved including worst outlier, +2,820
   excluding it. 11 of 12 tasks are net positive.

## Results by mode

| Mode | Input saved | Output delta | Net | Verdict |
|------|-------------|-------------|-----|---------|
| Fiction (3 tasks) | ~268/task | +37/task | **+231/task** | Strong win |
| Nonfiction (3 tasks) | ~160/task | -162/task | **+322/task** | Excellent |
| Research (3 tasks) | ~182/task | -165/task | **+347/task** | Excellent |
| Code (3 tasks) | -14/task* | +632/task** | -646/task** | Mixed |

\* Code minimal is slightly larger than prose (expansion text)
\*\* Dominated by one outlier task

## The outlier: code_architectural

"Add a caching layer to the API endpoints" — no file context, no
existing code, no constraints. Prose: 411 output tokens. Minimal:
2,470 output tokens. This is a task-shape problem, not a renderer
problem. The task is an unconstrained greenfield prompt that invites
design-essay behavior.

The other two code tasks are fine:
- code_decision_ref: minimal 466 vs prose 505 (minimal wins)
- code_file_check: minimal 76 vs prose 201 (minimal wins big)

## What we learned

1. **Some prompt semantics are policy; some are behavioral priors.**
   The IR refactor forced this distinction into the open. Output shaping
   was never named as a control slot — it was hiding in prose formatting.

2. **Explicit output-shaping slots recover most of the loss.**
   Once `OUTPUT_DISCIPLINE` and `PATCH_OVER_ESSAY` were named and slotted,
   the verbosity blowout collapsed on most tasks.

3. **Unbounded tasks amplify renderer differences.**
   The outlier isn't about prose vs minimal. It's about "invent something"
   vs "change something specific." The benchmark corpus needs both types
   but should score them separately.

4. **Minimal is already the right default for nonfiction and research.**
   Consistent wins on both input and output. Fiction is a net win with
   small output overhead. Code needs bounded tasks to show its strength.

## Next steps

- Split code corpus into bounded-edit vs greenfield tasks
- Add 1-2 bounded code tasks with real file context
- Don't flip the default renderer yet
- Don't add more slots blindly — the current set is sufficient
- Push after hours
