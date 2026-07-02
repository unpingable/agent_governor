# Next — Slice 1a (Standing) then Slice 1b (AG)

Reduction done (verdict B); D010 **ratified Model X** (DECISIONS.md). Standing owns spend-time
scope-mismatch refusal; AG only inherits. Build order: **Slice 1a in Standing first, then 1b in AG.**

## Slice 1a — Standing scope-checked use  (`~/git/standing`, Rust)  — **DONE** (commit `1e62ba9`, not pushed)

Built: `grant use` names the attempted `(action,target)`; `Store::transition_scoped` refuses
`StoreError::ScopeMismatch{granted, attempted}` before any write (non-consuming — a mismatch
leaves the grant `Active`). Pins: `scope_mismatch_refuses_and_does_not_consume`,
`scope_match_spends_and_single_spend_still_holds` (store), `use_with_wrong_scope_is_refused_and_does_not_consume`
(CLI end-to-end). Full Standing workspace green. Standing now refuses all five load-bearing
classes — the token is fully present for AG to inherit.

### Original Slice 1a spec (for the record)

`grant use` must name the attempted `(action, target)` (and subject/session if not already
present); the store must refuse `StoreError::ScopeMismatch{granted, attempted}` when it differs
from the grant's bound `GrantScope`.

**Non-consuming (D010a):** the scope check runs **before spend**; a mismatch emits a **refusal
receipt** and **leaves the token unspent** (no `Active→Used`). Failed presentation must not burn
a single-use grant — that would be a DoS primitive. (Only flip to consuming if Standing adopts an
explicit "failed presentation burns" doctrine.)

Discipline: failing test first (`cargo test`, observe the real exit code), then the refusal.
Pins: (a) mismatched `(action,target)` → `ScopeMismatch`, grant still `Active`, refusal receipt
emitted; (b) matching `(action,target)` → spends as before; (c) the existing expiry/spend/replay/
subject refusals still hold and still precede/compose correctly.

## Slice 1a-bis — Standing `grant use --json` witness packet  — **DONE** (commit `f101c55`, not pushed)

`standing.grant_use.v1` implemented with asymmetric custody (D010c): success carries
`receipt_digest` + `receipt_kind: grant_used`; refusal carries a closed `refusal_class`
(scope_mismatch/expired/already_spent/subject_mismatch/not_found) + `receipt_digest: null`.
Unmapped `StoreError` stays prose (consumer reads "cannot verify", not a refusal). 5 CLI pins;
full Standing workspace green.

## Slice 1b — AG adapter  (`activation.py` Office 2)  — **ACTIVE NEXT** (unblocked)

AG subprocess-invokes `standing grant use --json …`, parses `standing.grant_use.v1`, applies
the refusal map ([TRANSPORT.md](TRANSPORT.md)), and replaces `activation.py` Office 2's
`standing_ok: bool` with the verified result. Three-way distinction enforced: `used`+digest →
mint + `standing_basis`; `refused`+class → `REFUSED_NO_STANDING`; transport/parse failure →
`REFUSED_NO_STANDING` as *no_verified_result* (NOT a Standing refusal). AG does no local
adjudication.

### Slice 1b cold-start plan (start here next session, ideally fresh)

1. **Reduce the binary-invocation seam first** (before touching `activation.py`). How AG locates
   and invokes the `standing` binary, preferred order:
   1. **Configured explicit path** (e.g. `STANDING_BIN=/path/to/standing`) — best for tests +
      deployment, no PATH séance. **Preferred.**
   2. PATH lookup by command name — acceptable for dev; the receipt should record the resolved
      binary path (and `--version`/commit if available).
   3. Repo-relative cargo artifact (`~/git/standing/target/...`) — local lab only, not durable.
   4. **Direct DB / shared store — NO.** That makes AG a Standing organ, not a consumer.
2. Build `StandingGrantUseClient` around a **subprocess-runner interface** (inject the runner).
3. **Unit-test with a FAKE runner** (canned `standing.grant_use.v1` stdout) for all three
   branches — do not make AG tests hostage to a sibling repo's build path.
4. One **optional live integration specimen** hitting the real `standing` binary if present.
5. Rewire `activation.py` Office 2: `standing_ok: bool` → verified grant-use packet / digest.
6. Pin the boundary (table in [TRANSPORT.md](TRANSPORT.md) refusal map) incl. invalid-JSON /
   unknown-schema / missing-digest → `no_verified_result` (NOT a Standing refusal).
7. Old `standing_ok=True` path gone or quarantined.

Three-way distinction is the acceptance core: `used`+digest → mint + `standing_basis`;
`refused`+class → `REFUSED_NO_STANDING`; transport/parse/schema/digest failure →
`REFUSED_NO_STANDING` as *no_verified_result*, never claiming Standing refused.

Replace `standing_ok: bool` with a verified Standing grant-use **result**. AG receives:
- admitted use receipt / token spend receipt → may mint/continue **this act**;
- missing / expired / spent / replay / subject / **scope-mismatch** → `REFUSED_NO_STANDING`.

`AGGrantAdapter` **inherits** Standing's verdicts; it does **not** inspect grant fields to decide
scope, and does **not** synthesize a scope refusal. Records the Standing receipt id in
`standing_basis` (`activation.py:496`). `StandingClient` graduates from SPEC-stub to a real
cross-repo client **only** for this seam.

## Forbidden (operator, 2026-06-23)

- no AG-local scope adjudication as authority; no adapter-synthesized scope refusal;
- no mint/continue from carried scope fields alone;
- no supervisor hot-path pickup yet (`create_session`/`fork_session`/`_handle_tool_proposed`);
- no conductor/planner changes; no self-hosting-first.

Model Y (adapter-local matching) may appear only as a **non-authorizing diagnostic** demonstrating
the gap — never as the production authority path.

---

# B-series — Rust-kernel lane (added 2026-07-02, roadmap program)

Slice 1b above **is B4** in program numbering; it remains ACTIVE NEXT, gated only
by Q-B1 (operator confirm+push of Standing `1e62ba9`/`f101c55`) — NOT by the
reconciliation campaign. Six-field shape per `docs/roadmaps/ROUTING.md`.

### B0 — capsule reconciliation  **(EXECUTED with program setup 2026-07-02)**
tier: conceptual · executor: fable · prereq: []
- purpose: capsule reflects the three-world state (AG parked branch ·
  `~/git/transition-kernel` repo · Standing unpushed 1a/1a-bis) and carries the
  Rust-lane stop-lines.
- files: CAMPAIGN.md, NEXT.md, STATUS.md, DECISIONS.md (this update).
- tests: doc-only; capsule cross-references resolve.
- refusal mode: n/a. · receipt shape: the program-setup commit.
- stop condition: no ratified-decision text altered — additive only.

### B1 — three-world inventory refresh
tier: mechanical · executor: codex · prereq: [B0]
- purpose: INVENTORY.md gains the Rust-kernel world: diff AG parked branch
  `feat/transition-kernel-slice-1b` vs `~/git/transition-kernel` HEAD vs Standing
  HEAD; record the 9-case corpus list, differential.py invocation, and the wicket
  verdict map as the frozen contract surface.
- files: INVENTORY.md (append §"Three worlds, 2026-07-02").
- tests: `~/git/transition-kernel/scripts/differential.py` run recorded verbatim
  with real exit code; every claim carries repo+hash.
- refusal mode: n/a. · receipt shape: commit citing all three HEADs.
- stop condition: differential fails or corpus ≠ 9 cases — record verbatim, STOP
  (that changes B2's ground truth; do not reinterpret).

### B2 — invariant survival map (packet core)
tier: conceptual · executor: fable · prereq: [B1]
- purpose: the table of Lean-backed distinctions that must survive in Rust types/
  verdicts/receipts/refusals: typed refusals **naming the offender** (v5/v6);
  metric-time freshness (4 refusals + skew/divergence params); finitary
  exhaustively-matched verdict enums; corrective = down-edge;
  `checkpoint_mints_nothing`; one-receipt-one-discharge; the
  Standing/LA/kernel/receipts separation; citation tiers ([1.0] citable / ANNEX
  exact-theorem / SCRATCH pilot-only / CANDIDATE uncitable).
- files: INVENTORY.md §"Invariant survival map" — row = invariant · Lean source ·
  Rust surface · corpus case · refusal mode.
- tests: every row cites Lean module+theorem+tier; rows lacking a corpus case
  enumerate into B5.
- refusal mode: may name missing refusals; adds none.
- receipt shape: commit citing lean repo HEAD.
- stop condition: an invariant statable only with new kernel vocabulary — mark
  `requires_operator`, file in DECISIONS.

### B3 — corpus plan (operator sign-off)
tier: conceptual · executor: fable · prereq: [B2]
- purpose: settle corpus custody. Recommendation: `~/git/transition-kernel`
  remains custodian (owns differential.py + the conformant 9); wicket fixtures
  grow in wicket for wicket's contract, cross-referenced not merged; AG
  contributes cases via its v7 JSON-schema lane.
- files: INVENTORY.md §corpus + DECISIONS Q-B3.
- tests: n/a (plan doc). · refusal mode: n/a.
- receipt shape: commit; Q-B3 OPEN until ruled.
- stop condition: recommendation conflicts with C2's repo-boundary evidence —
  surface both, do not pick silently.

### B5..Bn — corpus expansion (one case = one slice, enumerated by B2)
tier: mechanical · executor: local-qwen or codex · prereq: [B2, B3 ruled]
- purpose: every B2 row without a differential case gets one: scope-mismatch
  non-consuming; stale-basis-as-live; each freshness refusal (expired /
  not_yet_valid / divergence_excessive / incoherent_interval); replay/single-spend.
- files: corpus home per Q-B3 ruling; differential harness only.
- tests: differential.py green over old+new cases (real exit code).
- refusal mode: the case's named refusal, from existing closed vocab.
- receipt shape: one commit per case citing the B2 row.
- stop condition: a case needs kernel behavior change to pass — STOP; that is a
  kernel slice, not a corpus slice.

### B6 — Lean v6 proof-of-payment checker pilot
tier: review · executor: codex-exec (framing by fable) · prereq: [B2]
- purpose: run the v6 finite-support checker (typed `CheckResult`, offender-naming
  refusals, `firstDeficient_decides_check`) as a **non-binding oracle** over the
  corpus; report divergences.
- files: report → INVENTORY.md §pilot; no kernel changes.
- tests: checker invocation + verdicts recorded verbatim.
- refusal mode: n/a (SCRATCH-tier pilot; uncitable as authority).
- receipt shape: report commit citing lean v6.0.0 tag.
- stop condition: any temptation to make the checker load-bearing — v6 is
  SCRATCH-promoted; pilot only until Lean promotes.

### B7 — v7 wire-format lane draft
tier: conceptual · executor: fable · prereq: [B2]
- purpose: draft AG's v7-assigned lane (JSON schemas for artifact-authority
  profiles against the CANDIDATE fields), explicitly non-binding until v7
  ratifies; WLP stays envelope/causal-parent, never semantics.
- files: new working/ draft (promotes to specs/ only on v7 ratification).
- tests: schema examples validate (`python3 -m json.tool`).
- refusal mode: draft marks every field CANDIDATE — nothing citable.
- receipt shape: commit citing lean v7 gap spec.
- stop condition: v7 gap spec changes under us — re-sync, do not guess.
