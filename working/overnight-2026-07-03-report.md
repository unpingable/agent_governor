# Overnight run — 2026-07-03 (aggressive)

Per-lane ledger. Envelope: full (commit+push AG main + siblings), every test
verdict through `governor verify-run`, sandwich (codex-exec) on authority-
touching + receipt-shape changes.

## LANE A — B5 corpus growth ✅ COMPLETE (both repos pushed)

Corpus grew **9 → 13 cases**. AG `golden/corpus/` sovereign + transition-kernel
`vectors/legacy/` mirror, byte-identical, both kernels reproduce.

| slice | what | verdict | commits |
|---|---|---|---|
| A-1..A-4 | LA-token quartet (scope_mismatch, token_revoked, token_expired, unknown_token) — drill scenarios + goldens frozen-from-live + manifest-admitted + Rust ConsumeOutput variants + decide() arms + adapter + conformance 9→13 | differential 13/13 exit 0; cargo test green; corpus_contract + corpus_custody [pass] | ag `cfddc96`, tk `05cd724` |
| A-5 | typed `freshness_subcase` on the spendability receipt (ruling: keep single kind + typed subcase); closed-vocab ENFORCED at emission + membership-tested; golden-08 contract mutation (frozen-from-live, re-hashed, mirror synced) | spendability + corpus [pass] | ag `1ddd781`, tk `9a72f4f` |
| A-6 | closed B2 freshness rows (covered_by_single_kind); scope/token rows DONE; filed freshness-granularity alignment gap (lean.md + backlog + INVENTORY) | — | (in `1ddd781`) |

Sandwiches: B5 quartet — codex BLOCK on suspected Rust decision-order bug,
**disproven** (admission checked before quartet) + **pinned** with 2 ordering
tests. A-5 — codex BLOCK "closed vocab declared not enforced" → enforced at
emission + membership-tested → MERGE-SAFE.

## LANE D — closure (partial) ✅ D-2, D-3 pushed

| slice | what | verdict | commit |
|---|---|---|---|
| D-2 | mirror-side identity check in transition-kernel (`scripts/verify_mirror.py`) vs AG's admission manifest — closes the isolated-CI mirror-skip boundary from the mirror side | 13/13 identical; negative control bites on 1-byte tamper | tk `543dfc5` |
| D-3 | read-plane boundary note (spine/governor-atlas/state_index_export); resolves Q-C2-5 + consolidation #5 | — | ag `6c49ad9` |

Remaining Lane D (morning): D-1 cli-wording-pass (enumerated, docs), D-4 v7
wire-format draft, D-5 packet-schema-custody (G3), D-6 wicket-guard absorption
(ruled EXECUTE — cross-repo compile risk, needs care), D-7 v6 checker pilot.

## LANE B — governed-shell daemon ✅ GS-2b core pushed

| slice | what | verdict | commit |
|---|---|---|---|
| GS-2b | `operator.decisions.list` read-only RPC — unified decision feed over supervised interventions + promotions + pending violation via the hardened aggregator; `build_feed_from_runtime` maps live shapes (remaining monotonic-exact, created_at honest wall-approx) | RPC + aggregator + daemon suite [pass] | ag `7eb577a` + fix `a28d727` |

Sandwich: codex MERGE-SAFE + 2 robustness nits applied (elapsed
degrade-not-crash; defensive params). **Deliberately NOT sourced yet**: docket
+ admissibility + HELD-launch state (need DaemonState plumbing — the envelope
reserves both kinds). GS-4/5/6/3 remaining (morning).

**Scar (recorded):** the GS-2b commit shipped with two stale daemon pins red
because the `governor verify-run` in that step was NOT gated before the `git
commit` (they were newline-separated statements, not `&&`), and the message was
backtick-mangled. Fixed forward (`a28d727`). Rule reinforced: gate the
verify-run EXIT CODE before committing; never chain a commit past a bare
newline after a test run.

## LANE C — ag_shell_client (NOT started)

Morning item. Isolated `libs/ag_shell_client/` extraction (de-triplicate
framing/socket-path/JSON-RPC from maude+phosphor); unblocks both shells.

## Gate

Every slice green via `governor verify-run` (receipts in
`.governor/verify_receipts/`). Full-suite end-of-run gate: pending (morning,
before final sign-off). transition-kernel: differential 13/13 + cargo test
green after each mirror sync.
