# Roadmap — transition-kernel × AG

**Status:** RATIFIED (2026-07-02, A8 — snapshot + drift confirmed by executed evidence slices)
Repo: `~/git/transition-kernel` (HEAD 2026-06-18, summit `stage3b2-first-effect`)
· Campaign: **`docs/campaigns/transition-kernel-pickup/` is the build lane** —
this file is the tool-view index; it does not duplicate the capsule.

## 1. Contract snapshot — what AG assumes today

- The Rust kernel decides `Admit | Refuse(kind, reasons) |
  Escalate(required_authority)`; **sole minter of "admitted"**; explicitly does
  NOT establish standing, mint capacity, execute effects, or ratify policy.
- Conformance: 9 corpus cases byte-for-byte (Rust ≡ frozen ≡ live Python) via
  `scripts/differential.py` — the corpus is the contract (memory:
  rust_kernel_port_ruling).
- At-most-once authority consumption + replay-legible execution of one
  idempotent bounded effect (stage3b2).
- Branch A Lean feedstock (NoFreeContinuation) authored; Branch B remains.
- AG-side pins: `tests/test_runtime_transition_probe*.py`,
  `tests/test_transition_enforce_3c.py`, `test_continuation_enforce_c3.py`
  (schema `transition_kernel.composed_snapshot.v1`).

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| Three worlds unreconciled: this repo (06-18) vs AG parked branch `feat/transition-kernel-slice-1b` vs Standing unpushed 1a/1a-bis — the 2026-06-23 capsule inventory predates knowledge of this repo's summit state | pickup STATUS.md 2026-07-02 entry | MED — slice B1 |

## 3. Named gaps (non-binding)

- Corpus custody (Q-B3) and invariant coverage (B2 rows without cases → B5..Bn)
  are tracked in the capsule, not here.

## 4. Slices

**See `docs/campaigns/transition-kernel-pickup/NEXT.md`** — B0 (done with program
setup), B1 (three-world inventory), B2 (invariant survival map), B3 (corpus
plan), B4 (= Slice 1b, ACTIVE NEXT gated on Q-B1), B5..Bn (corpus expansion),
B6 (Lean v6 checker pilot), B7 (v7 schema lane). Six-field shapes live there.

## 5. Do-not-build

The capsule's stop-lines govern (CAMPAIGN.md §Stop-lines): Rust is not the truth
mint; smallest invariant-bearing core; no silent Python fallback; Python AG stays
orchestration/reference; wicket verdict map frozen; no implicit LA spend.

## 6. Operator questions

Q-B1 (confirm+push), Q-B3 (corpus custody), Q-B4 (sequencing), Q-B7 (v7
exposure) — all in the capsule DECISIONS.md.
