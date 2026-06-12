# Punch list — W1 exit-criteria stranger run, 2026-06-12

**Gate verdict: FAIL (partial, honest).** A cold codex stranger (fresh clone at
`c95336b`, fresh venv, follow-only-the-docs protocol, 15-minute patience budget)
reached *a* receipt-backed refusal at ~10–12 minutes — but the WRONG one
(`evidence_gate` "claim lacks evidence", not the temporal-lapse custody hero),
ended STUCK on evidence inspection, and **never discovered the demo trilogy at
all**. `demo/refused-spend.sh` / `interrogate.sh` / `opa-contrast.sh` are
mentioned nowhere a stranger looks (README, GETTING_STARTED — verified by grep;
only the internal wire-plan/zoning/loop docs name them).

A failed gate is a successful run of the slice: this list is what the hub /
demo page / README ratchet build against. **No fixes were made in this slice.**

Protocol note: stranger = cold codex (operator, Fable, and the Opus master are
all saturated SMEs — the master staged the room and annotated; the stranger's
findings below are quoted/condensed from its transcript, not edited).

## The stranger's friction points, in encounter order

| # | Finding (stranger's words, condensed) | Master annotation → fix owner |
|---|---|---|
| 1 | `bwrap` sandbox failures on basic reads | Environment artifact of the codex sandbox, not repo friction. No action. |
| 2 | README's quickstart claim ("thread safety blocks") contradicts GETTING_STARTED ("passes until rules are added") | Real doc contradiction. → README ratchet |
| 3 | `governor init` reported "already initialized" on a FRESH clone | **Loop self-inflicted:** the tracked orchestration artifacts (`.governor/loop.json` etc.) make `init`'s bare existence-check fire on every clone. Init must key on runtime markers, not dir existence — or the loop state moves out of `.governor/`. → small build slice (see below) |
| 4 | First gate check printed a Python `SyntaxWarning` | Polish; find and fix the offending pattern. → small build slice |
| 5 | The documented `no-eval` continuity REJECT produced **no visible receipt** — `governor receipts --last 5` showed only the earlier passing receipt | **The stranger's single worst moment** and the product's own thesis contradicted on its front path ("blocked with receipts" → blocked, no receipt). The continuity check path apparently doesn't emit/persist a gate receipt where `receipts` reads. Needs investigation: emit gap vs read-path gap. → build slice, HIGH |
| 6 | `governor trace` also omitted the rejection | Same root as #5, second surface. → same slice |
| 7 | `governor quickstart` repeats the no-eval block, still no receipt surfaced | Same root, third surface — the *guided demo* exhibits it. → same slice |
| 8 | `govlab/serve.py` assumes a browser; terminal user had to GUESS curl | Doc line ("or curl …"). → README ratchet |
| 9 | The refusal finally reached was missing-evidence, not custody | **The headline: the hero specimen is unreachable from the front door.** The trilogy exists, exits 0, and is invisible. → README ratchet + demo page (the front door's FIRST runnable thing should be `demo/refused-spend.sh` → `interrogate.sh`) |
| 10 | `receipts show <id>` exposes hashes only; no documented way to see the evidence payload | The capability EXISTS (`governor receipts --id <id> --evidence`) — pure discoverability gap. Also consider `show <id> --evidence` symmetry. → README ratchet (+ optional tiny CLI alias) |

## What the gate run proves about sequencing

The operator's call was right: every one of #2/#5/#9/#10 would have invalidated
pre-built pages. The pages now have their requirements list:

- **README ratchet (AG):** specimen-before-doctrine — the trilogy as the first
  runnable block (`demo/refused-spend.sh`, then "cross-examine it:
  `demo/interrogate.sh <root>`"); fix the thread-safety contradiction; document
  `receipts --id --evidence`; curl line for govlab.
- **Demo page:** the trilogy transcript IS the page content; OPA contrast
  diagram from `opa-contrast.sh` output.
- **Hub:** links the trilogy; nothing on the hub may claim what #5 contradicts
  until #5 is fixed.

## New build-slice candidates surfaced (filed, not started)

1. `continuity-refusal-receipt-gap` (HIGH): make the continuity REJECT path
   emit/surface a gate receipt visible to `receipts`/`trace`/`quickstart`
   (stranger items 5–7). The front path must not contradict the thesis.
2. `init-clean-clone-detection`: `governor init` keys on runtime markers
   (e.g. `receipt_kernel.db` / `receipts/`), not bare `.governor/` existence
   (item 3). Alternative considered: move loop artifacts to `.loop/` —
   bigger move, only if init fix is awkward.
3. `syntaxwarning-first-run` (tiny): silence the warning (item 4).

## Stranger's bottom line (verbatim shape)

> Did you reproduce a refusal and see its evidence? **Partially.** Receipt
> yes, evidence payload no, custody refusal no. First block ~5–6 min; first
> receipt-backed refusal ~10–12 min; patience exhausted at step 25.
