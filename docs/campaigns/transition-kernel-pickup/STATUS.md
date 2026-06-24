# Status — transition-kernel pickup

As of 2026-06-23.

## Done

- **Reduction** — verdict B: Standing issues an honest grant-token; the one gap was spend-time
  scope matching. Mint boundary = `activation.py` Office 2.
- **D010 (Model X)** ratified: Standing owns spend-time scope refusal; AG only inherits.
- **Slice 1a** (`~/git/standing`, `1e62ba9`, not pushed): `Store::transition_scoped` refuses
  `ScopeMismatch` non-consuming; Standing now refuses all five load-bearing classes.
- **Transport reduction** — verdict C: Standing's `grant use` was prose-only. Custody finding
  (rule #4): a non-consuming refusal has no transition → no receipt → **D010c asymmetric custody**.
- **D010b/D010c** ratified: the `standing.grant_use.v1` witness packet (success digest required;
  refusal class-only, null digest).
- **Slice 1a-bis** (`~/git/standing`, `f101c55`, not pushed): `grant use --json` emits the v1
  witness packet. **Standing JSON witness is now available** for AG to consume.

## Slice 1b — in progress

**Step A — `StandingGrantUseClient` (binary-invocation seam) — DONE** (this session, not
committed). `src/governor/standing_grant_use.py` + `tests/test_standing_grant_use.py`
(32 tests, exit 0, fake-runner only — no real binary; AG tests never hostage to Standing's build).

- Operator decision ratified: **trigger the spend** (not verify an upstream receipt) — the built
  `grant use` contract supports it; `verify-use` doesn't exist (would expand Standing).
- **Spendful-once / no-retry** baked in: invoke ONCE; a dispatched-then-died call →
  `NoVerifiedResult(standing_unknown_custody, may_have_spent=True)` — the grant may be `Used`, so
  AG refuses + never re-invokes (double-spend / DoS guard). Same shape as the playbooks
  `InterruptedUnknownEffect` poison.
- Three-way distinction is a **type split** (`GrantUsed | GrantRefused | NoVerifiedResult`), not a
  flag — only `GrantUsed` carries a mintable `receipt_digest`. Witness-integrity: a `used` packet
  whose `attempted` scope ≠ the request → `standing_request_mismatch` (not adjudication — Standing
  owns scope; this only defeats stale/confused packets).
- Binary resolution: `STANDING_BIN` (configured, preferred) → PATH → cargo lab → **never DB**.
- **Contract finding (doc vs code):** the real `grant_use_refusal_class` (standing@`f101c55`)
  emits **5** classes — `scope_mismatch / expired / already_spent / subject_mismatch / not_found`.
  **`replay` is in D010c's prose but NOT emitted** by `grant use`. AG recognizes the real 5; an
  unrecognized class → `no_verified_result`, never a synthesized refusal.
  *(TRANSPORT.md / D010c prose should drop `replay` from the grant-use set.)*

**Step B — rewire `activation.py` Office 2 — DONE** (this session, committed separately from
Step A per the revertability rule). `standing_ok: bool` + the carried-not-parsed
`external_standing_receipt` are **gone**; Office 2 now consumes a typed `standing` input:

- **`constellation`** consumes a verified `GrantUseResult` (D010 Model X — AG inherits, never
  adjudicates): `GrantUsed` → mint, `standing_basis = receipt_digest` (the verified digest, not
  a carried string) + still requires external LA + NQ; `GrantRefused` → `REFUSED_NO_STANDING`
  (`standing_refused:<class>`, inherited verbatim); `NoVerifiedResult` → `REFUSED_NO_STANDING`
  (`no_verified_result:<reason>`, **never** claiming Standing refused).
- **`standalone_degraded`** carries an explicit `BootstrapStanding(granted: bool)` operator-fiat
  (replaces the bare `standing_ok` bool; `granted=False` is the honest deny path;
  `standing_basis = "bootstrap_substitute"`). Presenting a constellation `GrantUseResult` or
  external LA/NQ refs in degraded mode → `REFUSED_DEGRADED_CLAIMS_BACKING` ("run poor, don't
  fake rich"). The fiat is now a *named type* Office 2 can reject in constellation mode, not a
  laundering boolean.

Design note: a **type split** (`GrantUseResult | BootstrapStanding`), not a bool + optional —
mode-honesty is type-enforced, consistent with the Step-A result discipline. Tests:
`test_activation.py` (+4 new constellation branches: inherit refusal / no_verified_result ≠
refusal / reject bootstrap fiat / verified-digest-as-basis), `test_activation_drill.py`. Relevant
suite (5 files) 93 passed exit 0; full-suite collection 16180 clean (no cycle from the new
`activation → standing_grant_use` import; no `src` module imports `activation` — P4-parked, zero
readers, so blast radius is the 5 test files).

**Remaining (optional):** one live integration specimen against a real `standing` binary
(skipped if absent). Supervisor hot-path pickup (`supervisor.py:752/:433`) stays deferred —
separate forcing case each (Office 2 was the sanctioned seam).

## Unpushed (nothing pushed — operator's trigger)

- `~/git/standing`: `1e62ba9` (Slice 1a), `f101c55` (Slice 1a-bis).
- `~/git/agent_gov`: the reduction + D010/D010a/D010b/D010c + capsule commits.

## Not touched (deferred, named)

Supervisor hot-path pickup (`supervisor.py:752` observe-mode self-authorization,
`supervisor.py:433` `fork_session` on prior local approval) — follow-on slices, each with its
own forcing case. Office 2 first. Refusal-witness receipts (Model A) — a separate future
Standing custody campaign.
