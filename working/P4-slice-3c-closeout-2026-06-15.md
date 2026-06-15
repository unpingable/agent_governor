# P4 Slice 3c — Closeout (operational promotion)

Re-entered COLD from receipts. Admission: `working/P4-slice-3c-admission-2026-06-15.md`.

## What 3c shipped (zero existing source modified)
- `src/governor/operational_promotion.py`:
  - `operational_promote(root, candidate, *, …, baseline_name, minted_by, prior_baseline=None)`
    — the single explicit operator-present act. Pipeline: `prepare_mint_input` (discover
    real stores + gate) → `mint_promotion` (four-office, re-derives) → persist receipt +
    superseding baseline. Refuses with **zero writes** on any ineligibility.
  - `PromotionReceiptStore` — durable spend-ledger for `PromotionReceipt` under
    `<root>/promotion_evidence/promotion_receipts/`. Content-addressed, atomic, integrity-
    checked, **no delete** (mirrors `ControlBaselineStore`).
  - `OperationalPromotionOutcome` — promoted XOR refused; on refusal nothing written.
- `tests/test_operational_promotion.py` — 15 tests (acceptance + negatives + static guards).
- No `__init__.py` change: promotion modules are imported by module path (existing
  pattern); 3c follows it. Touched zero existing source files.

## The structural guarantee (the invariant)
> No `ControlBaseline`/`PromotionReceipt` byte reaches disk except through an
> `operational_promote` call carrying operator act inputs (`baseline_name` + `minted_by`)
> AND a mint that independently re-derived eligibility + strong operator basis from real
> on-disk evidence.

Enforced + tested three ways:
1. **Behavioral** — `discover_promotion_bundle` / `prepare_mint_input` produce no
   baseline/receipt files (`test_discovery_alone_does_not_mint`, `…prepare…`).
2. **Static** — those modules' source carries no import of `operational_promote` /
   `PromotionReceiptStore` / `ControlBaselineStore` / `admit_baseline`
   (`test_read_only_modules_carry_no_write_path_import`).
3. **No fiat knob** — `operational_promote` has no `force`/`allow_missing`/override
   parameter (`test_no_fiat_parameter_exists`); missing act inputs raise `ValueError`
   before any disk read and write nothing (`test_missing_act_inputs_raise_before_disk_read`).

## Acceptance results
- Eligible real evidence → real persisted `ControlBaseline`; receipt↔baseline cross-named;
  supersedes prior; prior survives (no delete). ✓
- Missing / stale-operator-review / out-of-bounds / wrong-trial / off-surface-tunable →
  refuses, zero writes. ✓ (exact refusal kinds asserted)
- Weak↔strong operator-basis mismatch: **structurally unreachable on the disk path** (the
  store derives weak via `facts.project()`; asserted as the end-to-end projection
  invariant). The mismatch *refusal* lives in `mint_promotion`, covered by
  `test_promotion_mint.py`. Framed honestly, not hidden. ✓
- Idempotent: same inputs → same ids; exactly one baseline/receipt on re-promote. ✓
- Revert is supersession (new baseline supersedes promoted; promoted not deleted). ✓

## Fixture bug found + fixed (a real receipt, not a stumble)
First run: the two `prior_baseline` tests refused `promotion_operator_basis_absent`. Root
cause was the FIXTURE, not the code: with a prior baseline, `basis_bundle_hash` binds the
supersession lineage, so the operator must review THAT hash. The fixture minted operator
basis against the bare (no-prior) hash → bundle-binding mismatch → correct refusal. Fixed
by threading `prior_baseline_hash` into the reviewed bundle hash. **The gate caught a
lineage-binding inconsistency exactly as designed.**

## Live-root specimen — the loaded gun fired at an empty chamber
Ran `operational_promote` against the real `.governor/` root (candidate
`no-such-real-trial`):
```
promoted: False
refusals: ('promotion_evidence_insufficient', 'promotion_evidence_not_walkable',
           'promotion_replay_holdout_missing', 'promotion_operator_basis_absent')
receipt_path: None   baseline_path: None
```
`.governor/control_baselines/` and `.governor/promotion_evidence/promotion_receipts/` were
empty before AND after — **nothing written**. The trigger assembly is complete; the live
chamber is empty; it refused cleanly. **This refusal is the successful 3c outcome.**

## Two-verdict
- **Cargo:** operational path exists end-to-end; full suite green (exit-code observed).
- **Dogfood: HELD.** No write without the act (3 ways). No fiat knob. Live run refused
  closed. The gate caught the fixture's lineage error rather than minting on a mismatch.

## Fences honored (none breached)
No synthetic-as-operational (tests drive real producers to tmp; live root untouched). No
manufactured evidence. No second profile. No fuse/kernel/ratification change. No spec
rewrite. No live `max_slices=4` (config_hashes stay the accepted fixture stand-in). No CLI
front door (deferred; would invite live minting — candidate, not built). No push.

## Carried forward (unchanged bootstrap limits / candidates)
- `_config_hashes_for` fixture stand-in → live config custody is later gated work.
- CLI front door for operational promotion — candidate, gated on a forcing case.
- A real `max_slices=4` promotion still needs a real trial producing real survival +
  replay receipts on disk (slice-4 territory, gated).
