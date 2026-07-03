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

## LANE D — closure ✅ D-1/D-2/D-3/D-6 pushed

| slice | what | verdict | commit |
|---|---|---|---|
| D-1 | docs completeness for shipped slices — feature-history Governed Shell entry + campaign STATUS overnight ledger | — | ag `67ef285` |
| D-2 | mirror-side identity check in transition-kernel (`scripts/verify_mirror.py`) vs AG's admission manifest — closes the isolated-CI mirror-skip boundary | 13/13 identical; bites on 1-byte tamper | tk `543dfc5` |
| D-3 | read-plane boundary note (spine/governor-atlas/state_index_export); resolves Q-C2-5 + consolidation #5 | — | ag `6c49ad9` |
| D-6 | **wicket-guard absorbed into wicket** — cook/diff/surfaces → `wicket/examples/cook_from_diff/`, founding regression → `wicket/tests/` (runnable via `#[path]`, kernel API untouched); wicket-guard reduced to a LINEAGE husk | full `cargo test` green (4 cook + existing); sandwich MERGE-SAFE | wicket `939dbb9`, wicket-guard `a68cc20` |

Deferred (not blocking, lower value): D-4 v7 wire-format draft, D-5
packet-schema-custody (G3), D-7 v6 checker pilot.

## LANE B — governed-shell daemon ✅ COMPLETE (GS-2b/4/5/6/3, all pushed)

Daemon method count **91 → 97**. Every mutation/authority slice codex-exec
sandwiched to MERGE-SAFE; each verify-run-gated before commit.

| slice | what | sandwich | commit |
|---|---|---|---|
| GS-2b | `operator.decisions.list` — unified feed (interventions + promotions + pending violation) via the hardened aggregator | MERGE-SAFE +2 nits | ag `a28d727` |
| GS-4 | `operator.watch` — bounded streaming feed; stable-projection digest (excludes display-clock fields), notify-timeout so a stalled client can't outlive the loop bound | BLOCK→MERGE-SAFE (kinds validation, notify bound, digest churn) | ag `3fe0acb` |
| GS-5 | `runtime.session.send_input` + `OPERATOR_INPUT` event — fail-closed operator input into a running backend; never a silent drop | BLOCK×2→MERGE-SAFE (structured errors, no KeyError/AttributeError leak) | ag `a698abd` |
| GS-6 | exposure batch — `runtime.adapters.list`, `why.chain`, `session.get` capabilities/input_capable | read-only (test-gated) | ag `f3294e4` |
| GS-3 | `operator.decisions.resolve` — THE one mutation door; routes by trusted-feed kind+action to the backing handler, forwards its receipt, mints nothing, adds no refusal vocabulary | FULL BLOCK→MERGE-SAFE (codex confirmed no privilege escalation via forged args) | ag `cd11091` |

**Deferred (documented):** GS-2b remainder (docket + admissibility sources +
HELD-launch state, need DaemonState plumbing — envelope reserves both kinds);
GS-7 (autopilot RPC); GS-9 (maude consumes the client — separate-repo UX). v0
boundary on GS-3: already-resolved → decision_not_found (richer replay needs a
resolution ledger).

## LANE C — ag_shell_client ✅ COMPLETE (pushed)

| slice | what | verdict | commit |
|---|---|---|---|
| GS-8 | `libs/ag_shell_client/` — de-triplicated wire protocol (socket path proven **byte-identical** to `governor.daemon.default_socket_path`) + typed `DecisionItem` models with safe-defaults idiom (missing-identity refused, unknown-kind preserved+flagged, malformed-payload tolerated) | tests [pass] | ag `76397d6` |

Sandwich: MERGE-SAFE + 1 finding (harden dict-typed fields / non-object error
against a malformed daemon payload) applied.

## Gate

Every slice green via `governor verify-run` (receipts in
`.governor/verify_receipts/`; the exit code was gated before each commit — the
GS-2b scar is not repeated). transition-kernel: differential 13/13 + cargo test
green after each mirror sync. wicket: full `cargo test` green.

**Full AG suite end-of-run gate (sign-off):** `python3 -m pytest tests/` via
verify-run (receipt `56b82dee`) — **16219 passed, 66 skipped, 1 failed** in
289s. The single failure is `test_qa_self_governance.py::
test_pyproject_version_matches_latest_git_tag` — a **pre-existing, unrelated**
red: `git describe --tags --abbrev=0` returns the stray working tag
`stage3b2-first-effect` (ahead of `v2.8.1` in ancestry) instead of a release
tag, so it ≠ pyproject `2.8.1`. It fails **identically at the run-start commit
`11a9db6`** — tonight's work touched no `pyproject.toml` and minted no tag.
**Every test in the surface I touched (daemon/corpus/supervisor/client/wicket)
is green.** Recommend (operator, not done unattended): delete the stray
`stage3b2-first-effect` working tag, or narrow the gate to `v*`-pattern tags —
tag surgery on a self-governance gate is surfaced, not silently patched.

## Scars / discipline notes

- **GS-2b commit slip (recorded, fixed forward):** the GS-2b commit shipped with
  stale daemon pins red because the verify-run exit code wasn't gated before the
  `git commit` (newline-separated, not `&&`) and the `-m` was backtick-mangled.
  Fixed forward (`a28d727`). Every subsequent slice gated the exit code first.
- Codex `read-only` sandbox can't read the repo here (nested-bwrap); all reviews
  ran with inlined diffs + "review ONLY the paste". Two codex BLOCKs were
  **disproven+pinned** rather than blindly fixed (Rust decision-order; GS-4/GS-3
  non-dict-params were dispatcher-guarded); the rest were fixed and re-reviewed.
