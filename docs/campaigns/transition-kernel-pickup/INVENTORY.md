# Inventory / crosswalk — transition-kernel pickup (reduction)

Date: 2026-06-23. Reduction mode only — no implementation. Two cross-repo inventories
(Standing: `~/git/standing`; AG mint boundary: `/home/jbeck/git/agent_gov`).

## Verdict: **(B)** — an honest Standing grant-token exists, but one named refusal is missing: **spend-time scope matching**

Standing issues a real grant-token (`Grant` + the SQLite store *is* the enforcement layer)
that refuses **4 of the 5** load-bearing classes itself, with typed errors + content-addressed
receipts — a consumer inherits real refusals, not stored fields it must police. The fifth,
scope-mismatch-at-spend, is not refused by Standing and is exactly the "has scope-ish fields
≠ may mint" demon. So: close, but not fully present by the operator's own rule.

## Standing side — what it issues (`~/git/standing`)

`Grant { id, subject: Principal, scope: GrantScope{action,target}, issued_at, expires_at }`
(`crates/standing-grant/src/grant.rs:30`), persisted with `state`, `latest_receipt_digest`
(CAS head), `expires_at`. Mint boundary: `GrantAction::Request → GrantMachine::issue →
store.record_transition(Issued)` (`standing-cli/src/main.rs:394`).

| Load-bearing refusal | Standing refuses it itself? | Mechanism (verbatim) |
|---|---|---|
| **expiry** | YES | `StoreError::GrantExpired` once `now >= expires_at` (`standing-store/src/lib.rs:429`) |
| **single-spend** | YES | terminal `Used` FSM (zero transitions) + CAS on `latest_receipt_digest` (`lifecycle.rs:62`, `lib.rs:461`) |
| **replay** | YES | `jti`+audience replay guard → `ReplayDetected` (`standing-identity` `replay.rs:31`) |
| **subject/binding** | YES | `Unauthorized` if `actor.principal.id != grant.subject_id` (`lib.rs:413`) |
| **scope (mismatch at spend)** | **NO** | scope bound at issue + carried on the receipt chain, but `grant use` names no action/target (`main.rs:202`) → no `ScopeMismatch` refusal at consumption |

Other properties present: issuer/authority (operator-fiat genesis root, exactly-one,
`policy_hash` pinned at issue); provenance (content-addressed `Receipt` digest, hash-chained).
Caveat: identity is HMAC-over-shared-secret (`IDENTITY-SCARS.md`) — bounds the *strength* of
the refusals, not their presence.

Smallest shape to close the gap: give Standing's `transition()` (the `Used` path) the
attempted `(action, target)` and refuse `StoreError::ScopeMismatch{granted, attempted}` when
it differs from the grant's bound `GrantScope`.

## AG side — where AG mints/continues authority (the pickup boundary)

VALIDATE-only surfaces (not mint): `standing_client.py` (`StandingClient.verify()` — a
SPEC-honoring consumer stub, "replace with real cross-repo client when wiring lands"),
`standing/` validator package (validates chains, never issues).

**Live MINT/CONTINUE boundaries** (`runtime/supervisor.py`) — the D010 target:

| Boundary | Authorizes | Basis TODAY |
|---|---|---|
| `create_session` (`supervisor.py:257`) | a session exists / is supervised | AG-local fiat; effect budget = LA grant |
| `fork_session` (`supervisor.py:413`) | child continues parent authority | prior local `approved` promotion — **no standing** |
| `_handle_tool_proposed` (`supervisor.py:614`) | a WRITE step crosses to effect | LA consume on hot path; continuation grant is **AG-internal** |
| `activate` Office 2 (`activation.py:449`) | rung-activation act-standing | **`standing_ok: bool` fiat**; `external_standing_receipt` carried-not-parsed |

**Cleanest seam for `StandingGrantToken → AGGrantAdapter`:** `activation.py` Office 2
(`activation.py:449`). It is already an isolated, transactional "act-standing" office with a
typed refusal (`REFUSED_NO_STANDING`), a reserved receipt field (`standing_basis`, line 496),
and a constellation-mode contract that already expects an external standing receipt id. The
adapter would replace the `standing_ok: bool` parameter with a verified `StandingGrantToken`.
(The supervisor boundaries are higher *value* — they are the actual actor/session/step
authority — but harder: three boundaries on the hot path. Activation is the cleanest *first*
demonstration of the pattern.)

## Crosswalk: clean-map / missing / would-launder-if-inferred

- **Maps cleanly** (Standing already refuses; AG inherits): issuer, subject-binding, expiry,
  single-spend/replay, provenance/receipt-id. AG's `REFUSED_NO_STANDING` ↔ Standing's
  `GrantNotFound`; AG's exactly-once-spend office ↔ Standing's terminal `Used`.
- **Missing (named):** spend-time **scope-mismatch** refusal. Standing binds scope but does
  not adjudicate it at consumption.
- **Would be laundering if inferred:** treating "a Standing grant exists / is unspent" as "a
  grant **for this act/target** exists." That inference is the demon — it converts a scope
  *field* into mint authority without anyone refusing a mismatch.

## The one unresolved fork (exhibit both, do not axiomatize — CLAUDE.md debugging discipline)

Where does spend-time scope-mismatch refusal live?

- **Model X — Standing's job.** The token is not fully present until Standing refuses
  `ScopeMismatch` at spend. Honors the operator's rule literally ("refuse scope … without AG
  inventing locally"). Cost: a cross-repo Standing change before AG adapts.
- **Model Y — the consumer's job at the mint boundary.** The scope *value* is Standing-attested
  (issued, content-addressed, on the chain); matching an attested scope against the requested
  act is ordinary consumer behavior (cf. a JWT `aud`/`scope` claim). Not laundering, because AG
  invents no scope — it only applies an attested one. Cost: AG performs the match; the
  refusal's *locus* is AG, which is precisely what the operator's rule is wary of.

This fork is the ratification question for D010 and decides Slice 1's shape (see NEXT.md).
Recommendation: do not let scope-match be *implicit* either way — it must be an explicit,
receipted refusal with a named locus.
