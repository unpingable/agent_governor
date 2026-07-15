# Unresolved authority seams — decision packet

**Filed:** 2026-07-14  
**Status:** **UNRULED — findings only; authorizes no implementation**  
**Source:** authority/state-custody audit at AG `e52355c`

This packet separates semantic decisions from the mechanical custody cleanup.
Nothing here is part of the authorized reconciliation implementation. Each
decision below must be ruled independently before it changes a runtime gate,
authority artifact, or approval lifecycle.

## A-1 — What admits a runtime session to effect-bearing execution? — **RULED 2026-07-15**

> **Ruled via the successor packet**
> (`working/decision-packet-a1-runtime-admission-2026-07-15.md`): Option 4b
> now (derived lane labeling, observe-only, implemented same day), 4a
> (ungoverned×autonomous restriction) as a named follow-up gated on labeled
> usage data (`a1-lane-restriction-4a`). Options 1–3 not adopted. The
> original statement below is retained unchanged as history. A-2..A-6 remain
> UNRULED; this ruling authorizes nothing in them.

**Observed:** `runtime.session.create` and `runtime.session.launch` do not consult
`loop.json`, a selected slice, Plan Review Agenda authority, campaign
ratification, or WorkContainer admission. Optional runtime gates can constrain
individual calls, but no single checkpoint joins program admission, selection,
exact-plan approval, runtime state, effect authority, and custody.

**Decision required:** choose and specify one of these without silently
collapsing their meanings:

1. a selected loop slice is mandatory for every governed run;
2. an exact verified plan or Agenda is sufficient independently of loop
   selection;
3. both are required for the governed lane;
4. a separately named ungoverned lane may launch without either, with an
   explicit non-authority label and its own effect rules.

**Compatibility questions:** existing direct RPC callers, Maude plain runs,
tests that construct sessions directly, recovery/fork paths, and external
clients that do not carry loop identity.

**Stop line:** do not wire Plan Review, ScopeGrant, WorkContainer, or governed
dispatch as an incidental answer. This is a canonical runtime-authorization
decision.

## A-2 — Selection condition when PLAN is idle

**Observed:** `docs/loop-protocol.md` says PLAN ordinarily selects from admitted
work by ratified priority and requires fresh operator ratification at named
boundaries. The 2026-07-14 `loop.json` snapshot instead said the next selection
was necessarily the operator's but cited no boundary or receipt.

**Current reconciliation:** records the inconsistency and leaves the selector
empty. It neither auto-selects work nor establishes an operator-only rule.

**Decision required only if an operator hold is intended:** record its scope,
basis, start, and release condition. Otherwise the ordinary protocol remains
the only cited doctrine. The reporting checker must keep distinguishing
`unselected` from `requires_operator`.

## A-3 — Durable approval lifecycle

**Observed:** Plan Review Agenda authority and exact-plan approval witnesses are
content-bound, but lack general consumed, revoked, expired, or superseded state.
The completed CD-4 v0 plan and approval witness therefore remain mechanically
admissible to the file-based Maude resolver even though implementation and
promotion custody are complete.

**Decision required:** whether approvals are reusable capabilities, one-run
acts, or durable decisions whose current applicability is owned by a separate
lease. Define the consumer and migration policy before adding lifecycle fields.

**Current reconciliation:** append-only `current_disposition.json` sidecars may
say a historical run is complete. They are reporting/custody successors only;
they do not revoke or consume approval.

## A-4 — Dormant authority-shaped surfaces

**Observed:** Plan Review `authorize_agenda`, `ScopeGrant`, WorkContainer
preflight, governed dispatch, and ration-card dispatch each have canonical-
looking types or gates, but they are not one live production authorization
path. Some have only test callers or explicitly stop before launch.

**Decision required:** for each surface, choose one disposition:

- operative and wired to a named consumer;
- projection/test-only and explicitly labelled non-operative;
- retired/superseded with lineage retained.

This audit does not authorize wiring or retirement.

## A-5 — Meaning of `receipt_role=authority`

**Observed:** a role label alone is not a live-grant predicate. Nightshift
lifecycle testimony can label promoted, authorized, applied, and denied events
as role=`authority` while the gate verdict remains observational. Other
authority artifacts have different lifecycles and consumers.

**Decision required:** specify the tuple a consumer must evaluate—at minimum
gate, verdict, subject, event kind, scope, issuer, and lifecycle—not the role
string alone. Decide whether denied/after-the-fact testimony should retain the
authority role or move to a distinct testimony role in a separately versioned
change.

## A-6 — Standing expiry materialization and sweep testimony

**Observed:** the local Standing database contains one grant whose materialized
state is `active` although `expires_at` is 2026-07-05. Use-time checks refuse it,
so it is not spendable. `standing grant sweep --dry-run` identifies exactly that
grant. The authorized sweep could not update the sibling database from the AG
workspace sandbox and emitted contradictory CLI testimony: a per-grant
`skip ... attempt to write a readonly database` followed by `1 grant(s) swept`.

**Required custody action:** run the canonical sweep in a writable Standing
workspace, then verify a `grant_expired` receipt and materialized `expired`
state. This is an external operator action, not an AG-local authority change.

**Candidate Standing defect:** a failed transition must not contribute to the
reported swept count, and an all-failed sweep should return nonzero. This needs a
Standing-local packet and tests; it is not authorized here.

## A-7 — `operator_mode` fail-open — **RULED + CLOSED 2026-07-15**

The confirmed reproduction, compatibility analysis, smallest repair, and exact
acceptance tests are isolated in
`working/security-slice-operator-mode-closed-domain-2026-07-14.md`. That packet
must be ruled separately. No runtime repair was applied during reconciliation.

**Ruled by the operator 2026-07-15 and implemented as filed** — closed domain at
`create_session`, fail-closed at the effect point (`!= "autonomous"`), CLI
closed choice. See that packet's Disposition section for receipts. A-1..A-6
remain **UNRULED**; this closure authorizes nothing in them. In particular the
slice did not answer A-1 (what admits a session to effect-bearing execution) —
it only ensured that whatever admits one cannot be an unvetted string.
