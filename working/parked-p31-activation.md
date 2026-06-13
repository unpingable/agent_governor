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
