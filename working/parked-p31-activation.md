# PARKED: P3.1 scoped activation + rollback

Status: **PARKED 2026-06-13, uncommitted.** Draft moved to `working/parked-p31/`
(`activation.py.draft`, `test_activation.py.draft`) — out of the live tree so the
rejected effect-bearing code is neither importable nor suite-collected. Resume
only after the `DebtLedger` precondition slice (P3.0b) lands.

## Why parked (not committed, not deferred-as-debt)

P3.1's core claim is *activation recomputes the live claim set AT the gate*. The
draft recomputed from a caller-supplied `debts` param — which is not live; it is
a caller-supplied alibi, the exact office-fusion the four-office note
(`docs/cross-tool/rung-activation-four-office-note.md`) exists to prevent. So the
missing authoritative claim source is **not future-rung debt** — it falsifies the
current rung's claim.

> Debt can be deferred only when deferral preserves the truth of the current
> rung's claim. (Here it doesn't — so it halts.)
> An activation gate without an authoritative live claim source is not a gate;
> it is a caller-supplied alibi.

Codex pass-2 finding triage (operator-ratified classification):
- missing DebtLedger (authoritative live source) → **current-rung prerequisite**.
- forged-receipt write path (`apply_activation`/`apply_rollback`/`rollback` honor
  a directly-constructed receipt) → **current-rung blocker, fix on resume**.
- `LocalSpendLedger.consume` non-atomic → **defense-in-depth** unless concurrency
  becomes admitted (AG loop is single-writer / WIP-1).

## Carry-forward for the P3.1 resume (do NOT lose these)

The draft's four-office shape is sound and worth reusing; the rewrite must add:

1. **Read claims from the DebtLedger, not a param:**
   `live_claim_set = debt_ledger.open_claims(target_rung=N+1)` — recompute at the
   gate from the authoritative source. The `presented_claim_digest` check stays
   (defense in depth) but the *source* must be the ledger.
2. **Custody-anchor the writes:** `ActiveTunableStore.apply_activation` /
   `apply_rollback` and `rollback()` must honor a receipt ONLY if it is custodied
   (`receipt_store.has(activation_id)`) — a directly-constructed forged receipt
   must not drive a write. (Raises the bar; Python has no true private methods,
   so this is mitigation: forge+put+apply is still possible by a determined
   internal caller — acceptable for bootstrap, note it.)
3. **Spend atomicity:** add `flock` (repo `signal_store` pattern) to the spend
   ledger if concurrency is admitted; otherwise the temp+rename is adequate for
   single-writer bootstrap. Decide on resume.
4. Preserve everything that passed pass-2: four offices (admissibility recompute ·
   act-standing/substitute · exactly-once spend · durable custody), the closed
   refusal vocabulary, mode honesty (`standalone_degraded` forbids external refs;
   `constellation` requires Standing+LA+NQ; LA ref carried-not-parsed), rollback
   restores absence topology (delete, not null) + re-checks P3.1 scope + never
   erases the activation receipt, and the 8 negative tests.

The draft passed `verify-run` (17 tests) but Codex `verdict: fail` (forged-write +
caller-supplied-claims) — it was NOT committed.

## Resume sequence

P3.0b (DebtLedger) → resume P3.1 reading from it + custody-anchor + (flock?). Do
not commit P3.1 until it reads from the DebtLedger.

## RESUME pass (2026-06-13) — built, re-verified, Codex pass-2 = FAIL, HALTED on fuse

Resumed against the now-landed DebtLedger. Implemented carry-forward 1–4:
- Office 1 reads `debt_ledger.open_claims(P31_RUNG)`, recomputes `real_digest`,
  refuses on mismatch (`REFUSED_STALE_DIGEST`); eligibility over the live set.
  `parked_boundary_ids` dropped (was caller-controlled).
- `apply_rollback` now derives the write authoritatively from the custodied
  activation receipt — ignores the rb's claimed surface/target/value (closes the
  pass-1 redirect; regression test at test_activation.py:213 proves a forged rb
  with a real activation_id + wrong surface restores the *custodied* P31 surface).
- `LocalSpendLedger.consume` wrapped in `fcntl.flock` (`_exclusive()`).
- `rollback()` dropped its caller `mode` param; inherits mode from the custodied
  activation receipt.

`governor verify-run` over `tests/test_activation.py`: **pass** (exit-code
witnessed, `child_exit`, `masked_risk=False`). Then the single Codex re-validation
(fuse pass 2): **verdict fail**, 3 "blocking" findings. §11.3 classification
(verified against code, not Codex's framing):

1. *Direct `apply_rollback` call bypasses `rollback()`* → **defense-in-depth.**
   Post-fix the writer derives only from the custodied activation; a direct call
   with a forged rb can only restore that real activation's own prior value — no
   arbitrary write. The activation receipt remains the authority.
2. *forge → `ActivationReceiptStore.put()` → `apply_activation`* → **SPLIT.**
   - scope-leak half: `apply_activation` carries no P31 surface guard, so
     forge+put+apply could write a non-P31 surface. **Current-rung, cheap fix** —
     lift the P31 `surface/target` guard into the store writer (strictly tightening).
   - forge-custody half: making `put()` unforgeable in-process is the documented
     capability-microkernel boundary (`receipt-sovereignty-microkernel-note.md`),
     **future custody-affecting** — already pre-classified in this note's point 2
     ("Python has no true private methods … acceptable for bootstrap, note it").
3. *Caller-minted standing* → **by-design + future-rung.** Standalone `standing_ok`
   is operator-fiat by design (non-convertible stub; "the nod is the operator's").
   Constellation presence-checking is a stub for offices not yet wired, and
   constellation is not P3.1's dogfood claim (standalone self-governance is).

**HALTED per chain fuse (>1 refinement pass).** State left uncommitted:
`activation.py` (staged+modified `AM`), `tests/test_activation.py` (untracked).
The one clearly in-scope current-rung fix is finding 2's scope-leak half (P31
guard into `apply_activation`). Whether to authorize that one bounded fix + a
final commit, or accept the documented microkernel-deferred limit and commit as-is
with the limit noted, is the operator's jurisdiction call — findings 2 (forge-
custody) and 3 sit exactly on the "is this current-rung or activation-generally?"
line the operator reserved ("if it tries to become activation generally, shoot
the radio"). No third Codex cycle without operator re-authorization.
