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
adjudication. Open sub-question: how AG locates/invokes the `standing` binary (PATH / configured
path / built artifact) — a small reduction at the start of 1b.

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
