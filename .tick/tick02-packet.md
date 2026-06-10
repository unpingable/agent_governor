# Task Packet — populate NQ host_detail view fields

(Template-grade per docs/reference/task-packet-template.md. Handed to the supervised
executor as the task brief.)

## 1. Objective

In `crates/nq-db/src/views.rs`, the function `host_detail(db, host)` returns a
`HostDetailVm` with three fields left unpopulated behind TODOs (lines ~300-302):
`host_row: None`, `services: vec![]`, `sqlite_dbs: vec![]`. Populate them by querying the
`*_current` tables filtered to the given `host`, so a host-detail page shows that host's
current host row, services, and monitored SQLite DBs. This is a live code path
(`crates/nq-monitor/src/http/routes.rs` calls `host_detail`).

## 2. Scope fence (ONLY these paths)

- `crates/nq-db/src/views.rs` — the `host_detail` function only.
- `crates/nq-db/tests/` — ONE new test file (e.g. `host_detail_view.rs`).

Touch nothing else. No other functions, files, or crates.

## 3. Forbidden moves

- No `git commit`, `git push`, or any git mutation.
- No editing any file outside the scope fence.
- No changing the `HostDetailVm` / `HostSummaryVm` / `ServiceSummaryVm` /
  `SqliteDbSummaryVm` type definitions, or the `host_detail` signature.
- No schema/migration changes, no new SQL tables/views, no new dependencies.
- No network access.
- No "while we're here" cleanup of other code.
- Do NOT modify any existing test.

## 4. Verification commands (exact, from the notquery repo root)

```
cargo build -p nq-db
cargo test -p nq-db
```

## 5. Expected verify output / known-green baseline

- Baseline before your change (pinned 2026-06-10): `cargo test -p nq-db` is fully green,
  exit 0 — the lib suite reports `test result: ok. 586 passed; 0 failed`, and every
  integration suite is `test result: ok` with 0 failed.
- After your change: still fully green, PLUS your one new test passing. If any
  pre-existing test changes from pass to fail, you broke something — stop and fix or
  revert, do not modify the existing test to make it pass.
- **Additive tests only.** Add a new test file; do not edit existing test files.

## 6. Acceptance criteria (each independently checkable)

1. `host_row` is populated by querying `hosts_current WHERE host = ?1`, building a
   `HostSummaryVm` with the SAME columns/shape as the overview query at
   `views.rs:157-176`. It is `Some(vm)` when the host exists in `hosts_current`,
   `None` when it does not.
2. `services` is populated by querying `services_current WHERE host = ?1` (order by
   `service`), building `ServiceSummaryVm` exactly as overview does at `views.rs:179-196`.
3. `sqlite_dbs` is populated by querying `monitored_dbs_current WHERE host = ?1` (order
   by `db_path`), building `SqliteDbSummaryVm` exactly as overview does at
   `views.rs:199-218`.
4. The `stale` field on each Vm uses the SAME rule as overview: `stale = current_gen -
   as_of_generation > 2`, where `current_gen` is the latest generation id. Compute
   `current_gen` the way `overview()` does at `views.rs:131-154` (latest
   `generation_id` from `generations`, `unwrap_or(0)` when none) — a minimal query like
   `SELECT generation_id FROM generations ORDER BY generation_id DESC LIMIT 1` is fine.
5. A new test in `crates/nq-db/tests/` seeds (using the existing `test_db() ->
   nq_db::WriteDb` pattern found in e.g. `tests/detector_fixtures.rs`,
   `tests/coverage_composition.rs`) at least one generation plus one row in each of
   `hosts_current`, `services_current`, `monitored_dbs_current` for a host, then calls
   `host_detail` and asserts: `host_row` is `Some` with the right host; `services` is
   non-empty with the seeded service; `sqlite_dbs` is non-empty with the seeded db_path.
6. `cargo test -p nq-db` passes; no existing test modified.

## 7. Reversibility / rollback

Fully revertible, no migrations:
`git checkout -- crates/nq-db/src/views.rs` and delete the new test file.

## 8. Stop-and-ask clauses — halt and report rather than improvise if:

- The `hosts_current` / `services_current` / `monitored_dbs_current` schema does not
  match the column lists in the overview queries (a column is missing/renamed).
- The seeding pattern needed for the test isn't clear from the existing `tests/`
  examples, or `host_detail` can't be reached from a test.
- Populating a field would require touching anything outside the scope fence.
- Computing `current_gen` / `stale` is ambiguous after reading `overview()`.

## 9. Source authority

Operator fiat (downgrade experiment) + the in-code TODOs at
`crates/nq-db/src/views.rs:300-302` (real backlog).

## 10. Model tier attempted

Sonnet (`claude-sonnet-4-6`) via the supervised backend — first downgrade experiment.
