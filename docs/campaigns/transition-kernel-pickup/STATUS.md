# Status — transition-kernel pickup

As of 2026-07-04 (B2 + B6 + B7 executed; prior snapshots preserved below).

## Current disposition — custody successor (2026-07-14)

The discovery manifest's 2026-06-23 `next_build.status: active` and its
"Standing commits not pushed" comments are historical snapshots, not current
state. Q-B1 established that Standing `1e62ba9` and `f101c55` are contained by
`origin/main`; Slice 1b/B4 was then adopted on AG `main` and independently
verified by receipt `59cf2553` (status commit `8a9dd85`). The B-series buildable
set is exhausted. Remaining entries stay classified as design-blocked or
operator-gated below; this successor does not select one.

State axes: admission=`ratified`; selection=`unselected`;
plan_approval=`not_attached_to_unselected_remainders`;
runtime_activity=`inactive`;
effect_authority=`not_evidenced_for_unselected_remainders`; custody=`partial`.

## 2026-07-04 (later) — B6 + B7 executed; B-series buildable set EXHAUSTED

- **B6** (v6 checker pilot): INVENTORY §"Pilot: v6 finite-support checker" —
  firstDeficient over all 13 corpus cases (lake env eval, EXIT=0). 8
  unconditional agreements / 4 expected divergences {05,10,11,12} on exactly
  the scope-fence-excluded axes / case 13 encoding-dependent (both encodings
  run and exhibited) / 0 unexpected. Sandwiched: codex BLOCK on the case-13
  encoding resolved by exhibiting both models; re-review PASS. Checker stays
  non-binding (SCRATCH); no kernel changes. Commit cites lean v6.0.0.
- **B7** (v7 wire-format lane): `working/v7-profile-lane/` — README + 4
  CANDIDATE schemas (artifact_profile, profile_bridge_receipt,
  stage_ascent_receipt, jurisdiction_frame) + 3 specimens (incl. the
  parse-implies-authority refusal specimen). All parse (json.tool 7/7);
  structured specimens jsonschema-validate. 5 candidate refusal classes
  NAMED, kernel enum untouched. No gate built (forcing event named: a
  cross-project artifact actually presented as AG authority). Q-B7 narrowed
  to the promotion question (DECISIONS).
- **Remaining B-series is now entirely blocked-by-design or operator-gated:**
  B5 request-side linearity (LA fence design), B5 stale-basis (mapping
  design), freshness variants (granularity gap — consumer-forced), Q-B7
  promotion, continuation specimen (transition-kernel frontier repo). Plus
  housekeeping: B5-work-order stale table, stale branch pointer, Q-B4 moot.

## 2026-07-04 — B2 executed (fresh Fable pass, cold from receipts)

The invariant survival map was re-derived per `B2-coldstart.md` at lean HEAD
`84d6d24`, superseding the 2026-07-02 draft in place (INVENTORY §"Invariant
survival map"). What the fresh pass changed:

- **3 missing enumerated rows added:** finitary exhaustively-matched verdict
  enums ([1.0] typed-verdict API ↔ the closed Rust enums ↔ MANIFEST
  closed-world admission); the Standing/LA/kernel/receipts separation (no
  citable Lean warrant — `NoFreeStandingBridge` is UNRATIFIED-CANDIDATE;
  authority is D010 Model X + seam-named refusals + the D010c misattribution
  guard); citation tiers themselves (enforced by review, not type).
- **2 tier corrections** (per-file `Custody-Class` headers verified, not
  assumed): `one_receipt_cannot_license_two_discharges` is SCRATCH
  (`Scratch/ExecutionObligationSequent.lean:219`), not "[v4-resident]" — the
  single-spend row's authority is operational (Standing terminal `Used` +
  durable-spend write-ahead + corpus 06), Lean warrant pilot-tier; and the
  separation row must not lean on the CANDIDATE bridge module.
- **Freshness refinement:** Lean [1.0] proves FIVE negative theorems (opaque
  `Time.le` splits the two incoherence directions); AG's 4-value
  `freshness_subcase` folds both into `incoherent_interval`. Recorded in the
  granularity gap (+ stub note) — fold-by-argument, not oversight.
- **Better warrant adopted:** `PredicateWitnessSeparation` (ANNEX, promoted
  2026-06-27) cited on the synthetic-evidence row alongside
  WitnessInvariance-adjacent [1.0].
- **Refreshed ground truth:** corpus 13 (differential re-run this pass:
  13 cases, 0 unaccepted divergences, EXIT=0); Slice 1b on main (receipt
  `59cf2553`); B5 enumeration updated (A-1..A-4 done; freshness variants →
  alignment gap; continuation specimen → frontier corpus).
- **Stop condition not triggered** — no invariant needed new kernel
  vocabulary; nothing filed in DECISIONS.

B6/B7 prereq [B2] now satisfied. Remaining B5 drills stay blocked as recorded
in `B5-work-order.md` (note: its "buildable now" table is stale — those 4
shipped 2026-07-03).

## 2026-07-03 — B4 verify-and-adopt CLOSED (Slice 1b fully on main)

Slice 1b (AG standing grant-use adapter, `activation.py` Office 2 +
`standing_grant_use.py`) is confirmed ADOPTED and VERIFIED on main:
- **Adoption:** `git merge-base main feat/transition-kernel-slice-1b` == the
  branch tip `ae05353` (Step C2, witness-integrity on the REFUSED path), i.e.
  the branch is entirely contained in main — zero unadopted commits. Steps A/B
  (`24acd8f`, `f003519`) and C2 (`ae05353`) all reachable from main. The branch
  is a stale pointer (safe to `git branch -d`; remote deletion is operator's
  call).
- **Verification:** the Slice 1b band (standing_grant_use, activation[+drill/
  preflight], transition_enforce_3b1/3b2/3c, runtime_transition_probe[+enforce/
  supervisor/gap3b], standing_envelope_corpus, corpus_contract, drill_temporal_
  lapse) passes on main. verify-run receipt `59cf2553` [pass]
  exit_source=child_exit.

B4 was "verify-and-adopt", not "build" — the work landed overnight; this closes
the confirmation. Next transition-kernel work: **B2** (invariant survival map)
per NEXT.md; B6/B7 and the 4 remaining B5 drills (blocked on operator/prior-gap,
`B5-work-order.md`) after.

## 2026-07-03 — B5 quartet + freshness_subcase DONE (corpus 9->13)

- B5 A-1..A-4 (scope_mismatch/token_revoked/token_expired/unknown_token) +
  A-5 typed freshness_subcase + A-6 closure: golden/corpus grew 9->13, AG
  sovereign + transition-kernel mirror byte-identical, both kernels
  reproduce (differential 13/13). Sandwiched (2 codex BLOCKs resolved).
  Freshness-granularity alignment gap filed. B5-work-order.md tracks the
  4 remaining (blocked on operator/prior-gap). Mirror-side check shipped
  (transition-kernel scripts/verify_mirror.py).

## 2026-07-02 evening — B1 done, Q-B1 resolved, B4 unblocked

- **B1 executed** (INVENTORY §Three worlds): differential green 9/9 EXIT=0;
  corpus enumerated; packet's wicket-verdict map REFUTED (shared vocabulary =
  12-kind refusal enum + 5 seams; corpus is the contract); B5 seed named
  (scope_mismatch, LA token kinds, stale-basis have no cases).
- **Q-B1 RESOLVED BY EVIDENCE**: Standing 1e62ba9/f101c55 already on
  origin/main; the "unpushed" record was stale.
- **B4 = verify-and-adopt**: Slice 1b Steps A+B already committed on
  `feat/transition-kernel-slice-1b` (24acd8f, f003519; 501-line client +
  Office 2 rewire + 453 test lines). Next: run its tests via
  `governor verify-run` (receipted), review, adopt.
- **B2 next** (invariant survival map) — ground truth updated by B1.

## 2026-07-02 — resume (B0 executed)

- Campaign resumed as Packet B of the roadmap program
  (`docs/roadmaps/README.md`); B-series slices added to NEXT.md; Rust-lane
  stop-lines added to CAMPAIGN.md; sign-off questions Q-B1/Q-B3/Q-B4/Q-B7 filed
  in DECISIONS.md.
- **Three-world finding:** the standalone `~/git/transition-kernel` repo (HEAD
  2026-06-18) — Rust Admit/Refuse/Escalate kernel, 9-case byte-conformance vs
  Python via `scripts/differential.py`, summit `stage3b2-first-effect`, Branch A
  Lean feedstock (NoFreeContinuation) authored — was not in the 2026-06-23
  inventory. B1 reconciles it before any Rust work resumes.
- Slice 1b (= **B4**) remains ACTIVE NEXT, gated only by Q-B1 (confirm + push of
  Standing `1e62ba9`/`f101c55`), independent of the reconciliation campaign.

## Done (as of 2026-06-23)

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
