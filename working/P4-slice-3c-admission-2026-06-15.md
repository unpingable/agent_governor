# P4 Slice 3c — Admission / Slice Estimate (operator-present, HIGH)

Produced BEFORE code or mutation, per the operator's opening prompt. Re-entered COLD
from receipts (git log + `working/RESUME_2026-06-15_p4-HIGH-prep.md`), not session
momentum. `loop.json` was found STALE (still naming P4.0b as candidate, dated 2026-06-13);
the git log + RESUME doc are authoritative: P4.0a/P4.0b mint + 3a + 3b all landed
2026-06-15.

## The verb changed
```
3a = report   (discover_promotion_bundle — read-only)        landed f449164
3b = prepare  (prepare_mint_input — read-only, no mint)       landed bc1dc90
3c = PROMOTE  (explicit operator-present act + durable write) THIS SLICE
```
> 3c does not make eligibility powerful. It makes a separately authorized act capable of
> consuming eligibility.

## Question
Can an eligible *real on-disk* promotion-evidence corpus be turned into a real, persisted
`ControlBaseline` via a single explicit operator-present act — and is there provably NO
path from discovery or prepare to a baseline write without that act?

## What already exists (verified cold, 36+55 tests green at HEAD aae6da9)
- Producer stores (`promotion_evidence_store.py`): `put()` on activation / observation /
  replay-holdout / operator-basis. Real disk writes + integrity/tamper checks.
- `discover_promotion_bundle` (3a) — reads stores → bundle → gate verdict. Read-only.
- `prepare_mint_input` (3b) — discovery + eligibility → `MintInput`. Never mints/writes.
- `mint_promotion` (P4.0b) — pure four-office act (gate + strong operator basis + single
  content-addressed `PromotionReceipt` + `admit_baseline` w/ `supersedes`). No IO.
- `ControlBaselineStore` (`control_baseline.py:139`) — file-per-record, put/get/list_ids,
  **no delete** (supersession-only). The durable custody sink already exists.

## The missing wire (3c builds exactly this, nothing more)
1. `PromotionReceiptStore` — durable spend-ledger for the `PromotionReceipt`
   (file-per-receipt under `<root>/promotion_evidence/promotion_receipts/`). Mirrors the
   existing store pattern; content-addressed, no delete.
2. `operational_promote(root, candidate, *, <gate/discovery params>, baseline_name,
   minted_by, prior_baseline=None)` — the explicit act:
   `prepare_mint_input` → (eligible?) → `mint_promotion` (re-derives) → persist receipt +
   baseline. Refuses with no write otherwise.

## Invariant (the one thing that must hold at every seam)
> No `ControlBaseline`/`PromotionReceipt` byte reaches disk except through an
> `operational_promote` call carrying operator act inputs (`baseline_name` + `minted_by`)
> AND a mint that independently re-derived eligibility + strong operator basis from real
> on-disk evidence.

## Allowed
- New module `operational_promotion.py` + `PromotionReceiptStore`.
- New test file `tests/test_operational_promotion.py`.
- Additive `__init__.py` exports (public API surface; not kernel/spec).
- A live-root refusal specimen + tracking updates (loop.json / RESUME / closeout).

## Forbidden (hard fences, verbatim from the operator prompt)
- No synthetic promotion masquerading as operational. Tests write evidence through the
  REAL producers to a tmp store (the established 3a/3b pattern); the LIVE `.governor/`
  root is never given a real `max_slices=4` baseline.
- If no real eligible evidence exists → refuse cleanly. **Do not manufacture evidence.**
- No second profile. No fuse/kernel enforcement. No spec rewrite. (If an authority/spec
  gap appears → STOP and surface.)
- No operator fiat curing missing/stale/out-of-bounds evidence. `operational_promote` has
  NO override/force/allow-missing parameter.
- No baseline mutation until discovery is eligible, mint input prepared, mint re-derived.
- Promotion is an explicit act input — never triggered by discovery or prepare.
- `_config_hashes_for` stays the accepted fixture stand-in (no live config custody). The
  "operational" claim is about the real-evidence path + persistence, NOT live config wiring.
  (Documented bootstrap limit, carried forward.)
- No CLI front door in 3c (would invite live `max_slices=4` minting; YAGNI on that surface
  until a forcing case). Filed as candidate, not built.
- No push (operator owns the signal; work-hours rule).

## Acceptance (each a test)
- Eligible real evidence → real `ControlBaseline` minted + **persisted** via explicit act;
  `supersedes == prior.baseline_id`; prior baseline still on disk (no delete).
- Missing / stale / out-of-bounds / wrong-trial / wrong-profile(tunable) evidence → refuses,
  **zero files written**.
- Weak↔strong operator-basis mismatch: refusal lives in `mint_promotion` (covered by
  `test_promotion_mint.py`); on the disk path it is structurally UNREACHABLE because the
  store derives weak via `facts.project()` — asserted as a positive invariant, framed
  honestly (not hidden).
- Discovery alone does not mint (no write). Prepare alone does not mint (no write).
- **Negative priority**: `promotion_discovery` / `promotion_mint_input` source carry no
  import of the write path (static), AND produce no baseline/receipt files (behavioral).
- Revert remains supersession (new baseline supersedes promoted; promoted not deleted).
- Idempotent: same inputs → same ids; re-persist creates no second baseline.

## Live-root specimen (the loaded gun fired at an empty chamber)
Run `operational_promote` against the real `.governor/` root → expect `missing` refusal
(no activation evidence on disk) → record: the trigger assembly fired, the chamber was
empty, it refused cleanly, nothing was written to the live store. **This refusal is the
successful 3c outcome**, not a failure.

## Exit states
- DONE: code + tests green (exit-code-observed), live specimen = clean refusal recorded,
  tracking updated, committed local (NOT pushed).
- STOP: any authority/spec gap, any need to manufacture evidence, any pressure to write a
  live baseline.

## Two-verdict frame
- Cargo verdict: the operational path exists + the full suite stays green.
- Dogfood verdict: the fence held — no write without the act; the live run refused closed.
  Dogfood validated FIRST.
