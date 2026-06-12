# AUTO_RUN audit — maiden voyage, overnight 2026-06-12

Per the override contract (receipt `2026-06-12T043000Z.override-auto-run`):
straight overnight, no supervised trial, operator override on the record.
This audit is the contract's mandated exit artifact. **AUTO_RUN started in
AUDIT (controller-transition resume) and ends in AUDIT (this document).**

## 1. What changed, by commit

| Commit | Slice | Change |
|---|---|---|
| `496d527` | 1: init-clean-clone-detection | `_runtime_initialized()` marker predicate; clone-with-loop-artifacts initializes alongside; negative pinned |
| `cab1006` | 2: continuity-refusal-receipt-gap (HIGH) | Emit gap was one constructor arg: CLI now passes `GateReceiptSystem` to `ContinuityChecker`; failing check prints receipt id + `--evidence` inspect command |
| `ff64195` | 3: readme-front-door-ratchet | README leads with the trilogy; fictional DENY sample → verified-live `--strict` block; venv'd govlab line; `--evidence` documented; SyntaxWarning fixed at source (punch item 4 folded) |

All commits unpushed. Every command printed in the new docs was executed live
before landing.

## 2. Punch-list items addressed

Retired: **3** (init on clone), **4** (SyntaxWarning), **5/6/7** (continuity
receipt across receipts/trace/quickstart), **2** (README↔GETTING_STARTED
contradiction — settled empirically AGAINST the README), **8** (govlab
browserless), **9** (trilogy now the front door), **10** (`--evidence`
documented + printed at block time). Item **1** was sandbox artifact.

## 3. Failures that recurred (rerun vs first run)

- `bwrap` sandbox friction (environment artifact, both runs — not repo).
- Nothing else recurred: the first run's worst moment (invisible continuity
  receipt) and headline (trilogy unreachable) did not reproduce.

## 4. New failures that appeared

- **Receipt-id mismatch (rerun's worst moment):** Act-1's surface "leaf
  receipt," the printed interrogation command, and the JSON envelope cite
  `receipt_ids[-1]` = the WICKET pass — the refusal receipt id is never
  appended to `DrillRunResult.receipt_ids` on the refusal path. Verified by
  probe. Filed `refusal-receipt-id-mismatch` (tier-1, first morning
  candidate). interrogate.sh unaffected (reads the store for verdict=block).
- **Strict-path taint error leak** (found in slice-3 verification, not by the
  stranger): `release taint computation failed: 'ReceiptKernelBridge' object
  has no attribute '_store'` printed on the README's own recommended strict
  command. Filed `strict-path-taint-error-leak` (tier-1). NOT fixed (membrane).
- Minor: README lacks venv lines; interrogate no-arg wording says "those same
  receipts" but re-runs Act 1 fresh. Filed
  `readme-venv-and-interrogate-wording` (tier-4).

## 5. Did the stranger reach the trilogy?

**YES.** Rerun (cold codex, fresh clone, same protocol): reproduced the
temporal-lapse refusal via `demo/refused-spend.sh` + `demo/interrogate.sh`
and inspected the refusal receipt's evidence — `refusal_kind=
standing_before_spendability_not_bounded`, `gap_ns=11e9 > bound_ns=10e9`,
named monotonic `gap_basis`, `origin_mode=drill` — at **~7–8 minutes of 15**
(first run: wrong refusal at 10–12 min, STUCK on evidence, trilogy never
found). **The W1 stranger gate now PASSES.**

## 6. Does the no-eval continuity refusal emit visible receipt evidence?

**YES** — verified live on all three surfaces (`receipts`, `trace`,
`quickstart`), regression-pinned in `tests/test_fresh_clone.py::
test_continuity_reject_emits_visible_receipt`. The block prints its receipt
id and the exact inspect command.

## 7. Do README / GETTING_STARTED / demo / hub agree?

README ↔ GETTING_STARTED: **yes** — the contradiction was settled empirically
(plain gate check passes until rules; README now says so; the block sample
uses `--strict` with real output). README ↔ demo: **yes** — every printed
command executed live. **Hub: not in tonight's scope** — still unbuilt
(launch item 3); nothing on it can disagree yet, and the continuity-receipt
claim it must not contradict is now true anyway.

## 8. §11 violations or stretches

- **Stretch, recorded:** the rerun's receipt-id bug is IN code touched
  tonight; fixing it would have been a 4th slice. Budget said 3 — filed
  instead. (The contract held over the temptation; this line is the receipt.)
- Patch attempts used: 0 of 2 per slice. Wall-clock: well under 6h.
  Unclassified failures: none. Custody ambiguity: none. Scope: one NEW bug
  was *found* in non-queued code (strict taint leak) and filed, not fixed.
- No HitL guesses: nothing required clarification.

## 9. Residual risk / next candidate slice

- **Next:** `refusal-receipt-id-mismatch` (tier-1, small, pinned acceptance).
- Then: `strict-path-taint-error-leak` (tier-1), `check.py` unified-check
  receipt gap (same class as slice 2, different surface — noted in slice-2
  receipt, not yet filed as its own entry), `readme-venv-and-interrogate-wording`
  (tier-4), then launch items 3/4 (hub, demo page) against the updated punch
  state, then the remaining constellation README ratchet (launch 5).
- Risk: the gate rerun used a LOCAL clone — a GitHub clone post-push is the
  true condition (expected identical; receipts/transcripts preserved at
  /tmp/ag-stranger2.* for comparison).

## 10. Final loop state + exact resume point

`loop.json`: phase=AUDIT→PLAN handoff recorded; `current_slice=null`;
`last_verified_commit=ff64195`; master=opus; 6 commits ahead of origin,
unpushed. **Exact resume:** run the re-entry probes in loop.json, then
dispatch `refusal-receipt-id-mismatch` (or operator reorders). The W1 exit
gate is GREEN pending one post-push re-verification.
