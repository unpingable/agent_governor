# Linear Accountant — Agent Governor Handoff Note

**Status:** candidate handoff-shape pass. Not ratified, not an integration commitment, not a build authorization.
**Target boundary:** `~/git/linearaccountant/working/linear-accountant-v0-boundary.md` + running crate (`src/lib.rs` + `tests/v0_boundary.rs`).
**Companions:** `~/git/linearaccountant/working/linear-accountant-role.md`, `working/linear-accountant-handoff-packets.md` (per-tool contracts).
**Discipline:** handoff shape only. Per §9 of v0-boundary: "Do NOT audit defects, refactor, implement, or create a component."
**Filed:** 2026-06-03.

Six-section response to the §9 handoff prompt, AG side.

## 1. Role relative to Linear Accountant

**Semantic governor / enforcement coordinator.** AG validates standing, scope, evidence, policy, and tool-call eligibility against its rules. AG **requests** capacity from the accountant; AG never mints, decrements, expires, or revokes spendable capacity. AG may coordinate validity and spendability across its own surfaces, but it must not collapse them onto one mutable substrate or treat its own ALLOW verdicts as proof that capacity exists.

The role is **enforcement coordinator**, not capacity authority. AG decides "this is eligible." The accountant decides "this can be spent."

## 2. Packets AG would send

- `CapacityRequest{actor, action, target, scope, requested_capacity, basis, request_id}` — for any AG surface that becomes a real convertible spend path.
  - `basis` is a **reference** to AG's eligibility finding (e.g., an audit/standing verdict id, a continuity_basis hash, a scope-grant evidence_ref). Never the capacity itself.
  - `request_id` is AG's idempotency key for the *request* (deduplicates retries).
- **Lease/grant renewal:** a *fresh* `CapacityRequest` — never an extension on prior state. Re-validation does not regenerate a token.
- `TestimonyQuery{token_id}` — to learn whether NQ has testified about double-spend, lease reuse, or quota overrun on a token AG observed.

## 3. Packets AG would receive

- `Grant::Granted{request_id, token_id, scope, granted_capacity, expires_at, receipt}` — accountant minted a token. AG carries the `token_id` reference for downstream execution; AG itself does not consume.
- `Grant::Denied{request_id, denial_reason, receipt}` — accountant refused. AG denies the downstream action.
- `Expired`, `AlreadyConsumed`, `InsufficientCapacity`, `UnknownToken`, `Revoked`, `ScopeMismatch` — failure signals when AG queries token state or relays consume failures.
- `Testimony{witness_reference, subject, assertion}` — NQ's response to `TestimonyQuery`.

## 4. What AG must never treat as spendable authority

The cardinal forbidden flows for AG:

- **A verdict is not a budget.** A policy ALLOW from AG (validator chain pass, evidence-gate verdict, scope-check pass, gate receipt with `verdict: allowed`) does not entail that capacity exists. AG must request, not assume.
- **A re-validation is not a fresh token.** When an AG eligibility check passes again (after TTL refresh, after revalidation, after re-derivation), this re-asserts eligibility — it does not regenerate a previously consumed token.
- **A summarized agent context is not capacity.** "Earlier the gate granted me X" is not an authority claim AG should accept from downstream agent reasoning.
- **A receipt is not a token.** `receipt_reference` is evidence; `token_id` is spendability. AG must keep them type-distinct and refuse any path that treats a receipt as a re-spendable handle.
- **A testimony is not allocation.** NQ asserting `no_double_spend` is evidence about the past, not authorization for the future.
- **Accountant state is not mutable from AG.** AG may observe (read-only `inspect_token`) and may request — never directly modify. If the accountant is unavailable, AG **fails closed**: DENY the downstream action.

The crate enforces the wire-level version of this: opaque `TokenId`/`ReceiptId` with no public constructor (only a successful grant produces a `TokenId`). AG cannot fabricate one even if it wanted to.

## 5. Concrete future trigger that would justify integration

A **convertible** spend path in AG, not a co-located one. Per the 2026-06-03 line-level audit (`validity_spendability_audit_2026_06_03.md`, cited by role.md §11):

- scope.py `use_count` (testimony, not capacity) — **does not trigger**.
- reservations.py heartbeat (mutex, not budget) — **does not trigger**.
- ttl.py refresh (validity refresh, not capacity refresh) — **does not trigger**.
- overrides.py `compute_pressure()` advisory smell (operator action required to mint; not agentic) — **does not trigger**.
- quorum.py vote counts (mitigated by dissent gate) — **does not trigger**.

The trigger fires when an AG surface introduces a real conversion path: a finite-count spend that is genuinely consumable (one-shot override-uses, dispatcher leases that grant spendable budget, per-tool quotas that an agent can regenerate from validity refresh, blast-radius slots, retry allowances with a hard cap). Specifically:

- **Override-uses with exactly-once semantics:** if an override grants N spendable uses (rather than a TTL window), the N count is linear and needs accountant custody.
- **Dispatcher leases with capacity:** if a lease grants budget for N actions (not just deadlock prevention), the N count is linear.
- **Per-tool spend caps that ratchet:** if a per-tool cap is decremented per use with a hard floor at zero, it is linear.
- **Retry allowances with caps:** if AG enforces "at most N retries against this validation," the N is linear.

Until such a surface appears: **AG-side trigger absent.** AG implements no integration.

## 6. Existing AG docs/gaps that should cross-reference this

- **`specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md`** — the AG-side gap that named the cut (filed 2026-06-03). Core invariant ("validation may mint eligibility, not capacity") is the AG-altitude version of the accountant's wire-level enforcement. The Linear Accountant boundary is the **target** AG would emit against if a convertible spend path appeared.
- **`~/.claude/projects/-home-jbeck-git-agent-gov/memory/validity_spendability_audit_2026_06_03.md`** — the audit pass that calibrated convertibility-not-co-location for AG surfaces. Cited by linearaccountant role.md §11 directly. Calibration: 3 KILLED on convertibility, 1 PARTIAL (advisory), 1 WEAK.
- **`~/.claude/projects/-home-jbeck-git-agent-gov/memory/linearaccountant_repo.md`** — long-form companion to this handoff note. How-to-apply guide for future-AG-Claude.
- **`specs/gaps/GOV_GAP_AUTHORIZATION_SAFETY_BRIDGE_001.md`** — sibling gap (authorized ≠ safe). Composes with this handoff at the verdict→consequence boundary: even when AG holds a `Grant::Granted`, downstream safety remains a separate predicate.
- **`specs/gaps/GOV_GAP_RETROACTIVE_LEGITIMATION_BOUNDARY_001.md`** — sibling gap (post-validated ≠ pre-authorized). The `basis` reference AG sends in `CapacityRequest` must be a pre-state basis; a post-state-dependent basis is retroactive legitimation.
- **`specs/gaps/GOV_GAP_PHASE_WITNESS_MAPPING_001.md`** — adjacent. Phase witnesses testify to what AG gates did; the Linear Accountant `Testimony` packet routes through NQ's grammar.
- **`docs/doctrine/`** — should eventually cross-reference once a real integration fires. Not yet.

## Calibration note: co-location ≠ convertibility

The 2026-06-03 audit established the discriminating principle that v0-boundary §9 names verbatim: **"Co-location is not a violation; convertibility is — a surface is suspicious only if validity state can mint, refresh, regenerate, extend, or substitute for capacity."**

Three AG surfaces look mixed at description level (`use_count` adjacent to `is_active`, heartbeat lease, TTL refresh) and read as sealed at line level. None has a conversion path; none triggers Linear Accountant integration. Future AG audits apply the same calibration: the convertibility check is line-level, not surface-level.

## Posture

AG does not build the accountant. AG does not coordinate the accountant role across the constellation. AG does not promote the linearaccountant repo from candidate to ratified. AG **does** know where the boundary lives, applies the never-do list to any future AG code that touches spend surfaces, and would emit `CapacityRequest` against this boundary if/when a convertible spend path appears.

Until then: handoff-shape acknowledged, integration deferred, posture hands-off.
