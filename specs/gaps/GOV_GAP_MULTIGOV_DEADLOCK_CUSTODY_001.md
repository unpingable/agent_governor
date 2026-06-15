# GOV_GAP_MULTIGOV_DEADLOCK_CUSTODY_001

**Status:** candidate / forward-looking / **capture-and-record, NOT a build authorization**
(operator, 2026-06-14: "might be more forward-looking than we need — capture and record
anyway"). Filed because retrofit cost is real (issue-key identity, fencing, occurrence
epoch) and the review below catches footguns that must not be re-discovered the hard way.

## Doctrine line
> **Multigov observations are plural; custody is singular.**

A detected issue may have many observers, but only one active resolver. The deadlock
detector (`src/governor/deadlock.py`, shipped pure 2026-06-14) becomes a thundering-herd
machine if every governor that sees the same stall escalates / retries / "helpfully"
generates a decision packet. Leader-election, done correctly.

## Forcing case
Not present yet. AG runs a single governor today; the deadlock detector isn't even wired
to halt the loop. This gap opens **only** when ≥2 governors observe shared state. Until
then: spec, don't build (beyond the in-process case below, if/when that topology exists).

## What exists in AG (grep-grounded — the future build composes, not reinvents)
- `storage.py`: a `leases` table (with `expires_at` TTL) + `epoch_counter` /
  `next_epoch()` — a **monotonic counter that is the natural fencing-token source**.
- `storage.py`: **WAL mode = "multiple readers, single writer."** This is the load-bearing
  substrate fact (see Hold line).
- `quorum.py` (QuorumManager) + `sybil.py` (Neff, BlocDetector): the machinery for
  *observer quorum → confidence*, kept separate from *resolver ownership*.
- `deadlock.py`: `DeadlockReceipt` already exists but is **single-governor** — it has
  `loop_id`/`detected_at_turn`, NOT a content-addressed `issue_key` or occurrence epoch.
  Multigov adds those (see corrections #3/#4); single-governor does not need them.

## The HOLD line (the nastiest correction — fake CAS doesn't fail loud)
A CAS / first-writer-wins lease is **a consensus primitive in a receipt costume.** It is
atomic only over a **linearizable** substrate. On a racing store (shared-fs SQLite,
eventually-consistent KV, S3-ish) two governors both "win" — you get *confident
stampede*, worse than no protocol because you'll have removed the downstream dedup that
was saving you.

- **Single host / one SQLite file (WAL, single writer):** linearizable → real CAS lease
  + fencing available **now**. Also the trivial case: governor threads in one process
  with one real lock.
- **Multiple hosts / processes over a shared filesystem:** NOT linearizable → **refused**
  until a real linearizable lease substrate exists (the kernel hands you one).

> **Ruling:** spec distributed multigov now; build only in-process / single-host now (on
> the existing leases + epoch_counter substrate, if that topology arises); hold multi-host
> until a linearizable lease substrate exists. A distributed build with a fake CAS must
> refuse loudly, not pretend.

## Load-bearing corrections (from the review — these are the gap's real content)
1. **CAS lease is consensus, not storage.** Gate the build on substrate linearizability
   (above). `test_distributed_multigov_refuses_without_linearizable_lease`.
2. **The fence must reach the operator sink.** A stale token only matters if the
   bell/webhook/UI path checks it. Operator notification must be emitted *through* the
   fenced custody path; a stale fence → the sink refuses to notify/accept.
   `test_stale_fence_token_cannot_notify_operator_sink`.
3. **`chain_tip` (and anything that moves across concurrent observers) is evidence, NOT
   identity.** Two governors seeing the same deadlock ms apart get different tips →
   different keys → both escalate. Split:
   - `issue_identity` = {deadlock_kind, blocked_artifact_id, normalized involved
     roles/agents, custody-state shape, stable unresolved-transition id}
   - `evidence` = {observed_chain_tip, observed_at, local trace ids}
   Normalization is the soft underbelly: too fine → stampede; too coarse → two distinct
   deadlocks silently merge and one masks the other (**fail-open, the dangerous
   direction**). "Stable across observers, injective across issues" is the whole job.
   `test_chain_tip_variation_does_not_split_same_deadlock`,
   `test_distinct_deadlocks_do_not_coalesce_under_coarse_key`.
4. **Occurrence epoch — content-addressing + `Resolved` is an ABA bug.** Same deadlock
   recurs later → same `issue_key` → lands on the old `Resolved` receipt → swallowed.
   Resolving once would immunize you against ever escalating that shape again. Need
   collision for concurrent observers AND distinctness across recurrences:
   `issue_key = stable_identity`; `occurrence_id = issue_key + epoch/open-instance`.
   The temporal axis again. `test_resolved_occurrence_does_not_suppress_later_recurrence`.
5. **Escalation lease ≠ operator-decision custody (two lifetimes).** The short rotating
   lease stops double-pings; it must NOT invalidate the human's answer because reading the
   cursed options took longer than the TTL. Once an issue is `OperatorRequired`, the
   pending decision *is* the custody object, bound to `occurrence_id + basis_hash`, and
   survives lease rotation. `test_operator_decision_survives_escalation_lease_rotation`.
6. **The race-winner must not author the operator's choice architecture.** First-to-CAS
   isn't best-informed. `options = render_options(issue_key, occurrence_basis_hash,
   policy_version)` — deterministic from the issue basis, NOT `leaseholder.opinion()`.
   (Composes with the single-governor detector's existing rule: the detector recommends
   the PROCESS default, never the content.) `test_race_winner_cannot_change_options_template`.
7. **Quorum raises confidence, not ownership.** N governors observing the same
   `issue_key` → the lease-holder's packet carries `corroboration_count=N`; still one
   resolver. Reuse `quorum.py`/`sybil.py` Neff for confidence. Non-holders may only emit
   `DeadlockCorroboration(issue_key, governor_id, evidence_hash)`.

## Receipt shapes (DESIGN ONLY — not built)
```
DeadlockReceipt:   issue_key, observer_id, surface, blocked_artifact, decision_kind,
                   evidence_hashes, normalized_blocker, occurrence_id   # (chain_tip -> evidence)
ResolutionLease:   issue_key, occurrence_id, owner_id, fencing_token, expires_at,
                   acquired_from_receipt
OperatorDecisionRequired:  issue_key, occurrence_id, lease_owner, fencing_token,
                   decision_name, options, recommended_default, forbidden_actions,
                   corroborating_governors    # options rendered from basis, not leaseholder
```
Issue state machine: `Observed → Claimed → Corroborated → OperatorRequired → Resolved`,
plus `Expired` / `Superseded`. Only the latest fencing token may advance state. Only the
lease holder may reach `OperatorRequired`; non-holders attach corroboration.

## Lean (Lean-Claude's, not AG's to write) — LANDED [scratch] 2026-06-15
The marquee `at_most_one_active_resolver` is decorative (a partial function has ≤1 value
by type). The load-bearing scratch theorems now exist in `Scratch/DeadlockEscalation.lean`
([scratch], informs-not-ratifies) — one per correction above: `concurrent_observations_coalesce`,
`distinct_issues_do_not_merge`, `chain_tip_in_key_splits_same_issue` (#3),
`coarse_key_merges_distinct_issues` (#3 fail-open), `resolved_does_not_suppress_recurrence`
(#4 ABA), `decision_survives_lease_rotation` / `token_bound_decision_dies_on_rotation` (#5),
`leaseholder_authored_options_vary` (#6), `atomic_lease_gives_unique_winner` +
`fake_cas_admits_two_winners` (#1 the hold line). Same lesson as the observer slices — the
risk isn't in the marquee.

## Non-goals (this filing)
No build. No multi-host. No wiring of the single-governor detector to halt the loop
(that is its own consequence-bearing slice, separate from this). No reuse of AG's
existing leases as a *distributed* lease without proving cross-host linearizability.

## Open questions
- Is AG's `epoch_counter`/`next_epoch()` the right fencing-token source, or does multigov
  need a per-issue token? (Likely per-occurrence.)
- Does the single-governor `DeadlockReceipt` need `issue_key`/`occurrence_id` *now* (cheap
  forward-compat) or only when a second observer appears? (Lean toward adding the stable
  `issue_key` early — it's the retrofit-expensive identity surface; the occurrence epoch
  can wait for multigov.)
- Which topology does AG actually run when this fires — governor threads in one process,
  or processes/hosts? That single answer decides build-now vs hold.
```
