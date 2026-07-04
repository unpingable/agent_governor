# Governed Playbooks — Slice 5 exit ticket

**Done 2026-06-25** (gov loop, branch `feat/playbooks-gov-loop`). Durable, exactly-once
playbook spend — the first Track A pickup, and the line where the chain stops being a harness
story and becomes **runtime law**. Files: `src/governor/playbooks/durable_spend.py` (new),
`src/governor/cooked_context_orchestrator.py` (optional durable-spend gate, post-admission/pre-LA),
`tests/test_playbook_durable_spend.py` (8 tests). Orchestrator + recomposition + playbooks
regression: **226 passed, exit 0**.

## The boss fight, and it is boring

> Same playbook activation, retried after a crash/replay → does NOT double-spend.

`DurableSpendLedger.consume(key)` is the **write-ahead exactly-once** primitive — the ratified
Office-3 pattern from `activation.py` (`LocalSpendLedger`): claim *before* the effect; a replayed
key refuses before any LA call. `test_replay_does_not_double_spend` runs the same spend twice
against the same file-backed ledger (a fresh orchestrator = a new process); the second run refuses
at `SEAM_DURABLE_SPEND` with `playbook_spend_replayed`, and the LA consume callable is invoked
**exactly once across both runs**. Replay is boring. Boring is how you know the goblin is dead.

## The four non-collapses, mechanical

- **observe ≠ pass** (S3/S4): evidence record is `verdict=observe`; authority is `verdict=pass`.
- **pass ≠ spend** (S4): the LA spend basis is the pass admission, never the observe record
  (`build_authority_admission_verifier`).
- **spend ≠ execution** (S5): the durable gate decides only whether the spend may proceed exactly
  once; it performs no effect. The LA consume is the spend; nothing here executes anything.
- **durability ≠ permission** (S5): the durable ledger records *that a spend happened*; it never
  authorizes one. A claimed key only ever *refuses a replay* — it cannot admit, authorize, or spend.

## Spend binding (no naked spend)

The durable spend key is content-addressed over the **authority-bound** identity: the wicket pass
admission receipt id + principal + effect + resource + amount + playbook spec digest + step id. So:
- a different step / effect / resource / principal / authority is a **different** key (its own spend),
- the **same** spend is the same key (replay refuses),
- an **incomplete** binding (missing field) refuses with `playbook_spend_basis_incomplete` — no LA
  consume. (`test_unbound_spend_is_rejected`, `test_durable_key_binds_authority_receipt`.)

The durable claim receipt (`verdict=observe`) cites the wicket pass admission as parent, so
`governor why` walks spend → admission → standing.

## Did Slice 5 touch supervisor.py / activate()? — NO, deliberately. Read this.

The operator's Slice 5 checklist included "supervisor/activation path touched narrowly." **I touched
neither, on purpose, and this is a decision to confirm, not a silent omission.**

- **`activate()` is hard-fenced** to exactly one tunable (`decomposition_size/max_slices`); routing a
  playbook spend through it is the explicitly-forbidden "widen activation semantics." So I reused its
  **ratified exactly-once *pattern*** (`LocalSpendLedger` → `DurableSpendLedger`), not its gate. The
  durability boundary — the actual "runtime law" line — is crossable *without* mutating `activate()`.
- **`supervisor.py` (1337 lines) owns a divergent spend path** already: `bootstrap_lab` with LA as
  sole spend authority, budget ledgers, continuation grants, a transition-kernel route, present/burn
  C3. Wiring playbook-governed spend into *that* is redesign-class, not "teach it only enough." Per
  the operator's own stop-clause ("if the runtime boundary cannot be crossed narrowly, stop and write
  the obstruction"), I stopped and wrote it.

**Reconciliation with the operator's Slice 5/6/7 roadmap (received mid-slice):** the roadmap resolves
the tension cleanly. Slice 5 = *runtime law* (durable spend) — done here. Slice 6 = *first self-hosted
chore*: AG runs one boring governed-playbook task end-to-end, which is where a **live tool-dispatch
actually exists to route** — so the supervisor wiring earns its forcing case there, against a real
(unsexy) task, not as speculative plumbing now. The operator's own line — "Not when the supervisor can
dispatch" is the autopilot threshold — confirms supervisor-dispatch belongs to the dogfood slice, not
Slice 5. So the durability axis was crossed narrowly via a new gate; the **supervisor-dispatch axis is
the named obstruction, deferred to Slice 6** with a concrete task to force it.

> Autopilot begins when the agent can spend a permission without remembering it. — operator, 2026-06-25

Slice 5 builds exactly that "spend without remembering": a durable, replay-safe, authority-bound
spend whose receipt-chain a later AG cannot gaslight. It does **not** yet make AG *do* anything with
it — that is Slice 6 (dogfood execution), and autopilot is Slice 7 (a ration card, not a hat).

## Branch-custody note

Slice 5 did **not** require the Track A `feat/transition-kernel-slice-1b` branch (the
`GrantUseResult` / `standing_grant_use.py` seam). Durable spend is downstream of authority; the
playbook chain's authority is the Standing-verified Wicket admission (S3/S4), already on this branch.
No branch merge was needed; the durable gate composes on the existing chain.

## Intentionally NOT done (stop line held)

- No `supervisor.py` edit. No `activate()` edit (pattern ported, gate untouched). No live tool-dispatch.
- No spend-release on failure: the claim is write-ahead, so a crashed/failed attempt fail-closes its
  own retry (auditable via the claim record). Bias = **never double-spend** > always-recover — the
  same bias `activation.py` Office 3 ships. A crash-after-consume-before-claim window does NOT exist
  here because the claim is *before* the consume; the residual window (claim, then crash before
  consume) fail-closes an honest retry, the safe direction.
- No new closed refusal vocab leaked outside the durable seam (`playbook_spend_replayed`,
  `playbook_spend_basis_incomplete` are owned by `durable_spend.py`).

## Next possible slice (do NOT start without operator go)

**Slice 6 — first self-hosted governed-playbook chore** (operator's roadmap): AG runs ONE boring,
low-risk maintenance task (e.g. refresh a generated ledger / append a non-authoritative report
receipt / run a read-only audit) end-to-end through the governed playbook → durable spend chain.
This is *dogfood execution*, NOT autopilot. It is where the supervisor live-dispatch wiring earns its
forcing case against a real task. Slice 7 (bounded autopilot, fresh admission per run, scoped/expiring
Standing) comes after.
