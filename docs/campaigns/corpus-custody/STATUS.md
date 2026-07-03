# Status — corpus custody (Packet C)

As of 2026-07-02 night. **Q-B3 RESOLVED; guard shipped; B5 re-scoped.**

## Done

- **C0** — surface inventory (C0-inventory.md). Found: 9 cases in AG
  `golden/corpus/` byte-identical to transition-kernel `vectors/legacy/`, no
  custody_class, three unequal harnesses, helper-as-hidden-authority (G3).
  Corrected one agent over-claim (the origin fence is production-defined +
  test-pinned, not "living in a test file").
- **C1+C2** — custody model (custody-model.md): closed `custody_class`
  taxonomy, admission-source/mirror pattern, admission & mutation rule, known
  boundaries. The classification is an adjudicated artifact, not private
  judgment.
- **C3** — executable guard: `golden/corpus/MANIFEST.json` (admission record) +
  `tests/test_corpus_custody.py`, with `test_corpus_contract.py` coupled to
  consume only manifest funding cases. Review sandwich: codex-exec BLOCK (3
  structural holes + 1 latent) → fixed (verdict-test/manifest coupling;
  generated fail-closed; retired/disputed fenced at consumption) → boundaries
  4/6/7 recorded not pretended-closed → re-review. `governor verify-run` [pass].
- **C4** — B5 unlock adjudication (C4-b5-unlock.md): PARTIALLY BLOCKED, not on
  custody — the corpus live-chain can't yet produce B5's target refusals.
- **Q-B3** resolved in pickup DECISIONS (recommendation overturned:
  AG-sovereign + mirror, not transition-kernel-custodian).

## Not done / next (not this packet)

- B5 proper: build 4 drill scenarios (scope_mismatch, token_revoked/expired/
  unknown) + 1 freshness-typing decision + resolve 2 prior gaps (F-A3b-2,
  stale-basis), freezing each verdict as it becomes producible.
- `packet-schema-custody` follow-up (G3: the standing.grant_use.v1 packet shape
  lives in a test helper) — named, not opened here.
- Mirror-side check: transition-kernel could own a verify against
  `golden/corpus/MANIFEST.json` (closes the isolated-CI mirror-skip boundary).
