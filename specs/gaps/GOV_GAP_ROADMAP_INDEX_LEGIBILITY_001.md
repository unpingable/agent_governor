# GOV_GAP_ROADMAP_INDEX_LEGIBILITY_001 — docs/roadmaps/ is invisible to the state index

**Status:** SCOPE (candidate, non-binding). Filed 2026-07-02 with the roadmap
program setup. Nothing below is authorized to build; the paired backlog item is
`.governor/backlog/state-index-roadmap-kind.json`.

## What exists

- `src/governor/state_index_export.py` (state-registry Slice 0, shipped
  2026-07-01) scans hard-enumerated roots: `specs/gaps/*.md`,
  `docs/playbooks/*.md`, the named campaign files, `working/*.md`,
  `.governor/backlog/*.json`, `.governor/campaigns/*.yaml`. Kinds include `gap`,
  `playbook`, `planned_slice`, `work_packet`, `operator_decision`,
  `backlog_item`, `parked_candidate`, `waiver` — there is **no** `tool_roadmap`
  and **no** `dependency_edge`.
- `docs/roadmaps/` (2026-07-02): hub README, ROUTING, PARKED, CONSOLIDATION, 17
  `tools/*.md` files with `**Status:**` lines in exporter-parsable position, and
  slices carrying explicit `prereq: [...]` lists.
- Interim bridge (already in place): one backlog stub per tool roadmap, so the
  program is exporter-visible as `backlog_item` records with `spec_ref`
  pointers.

## What needs building (when authorized)

1. Add `docs/roadmaps/tools/*.md` as a scan root emitting kind `tool_roadmap`
   (observed_state; status from the existing `_md_status` parse; id
   path-derived; source_hash as elsewhere).
2. Optionally add `docs/roadmaps/{PARKED,CONSOLIDATION}.md` scanning (kinds
   `parked_candidate` rows / `promotion_candidate`-adjacent — reuse existing
   kinds where they fit; mint `tool_roadmap` only).
3. Candidate, separately gated: `dependency_edge` records derived from slice
   `prereq:` lists — this is a NEW kind with graph semantics; it should not ride
   in on the same slice as (1).

## Acceptance criteria

- `python3 -m pytest tests/test_state_index_export.py -v` green (real exit code)
  with new fixtures covering a tool_roadmap doc (status parse + hash + id
  stability).
- Export remains deterministic and byte-stable across runs; existing record
  kinds and ids unchanged (no renumbering of the current corpus).
- A tool roadmap with a malformed/missing `**Status:**` line surfaces as a
  warning record, not a crash and not a fabricated status.

## Non-goals

- No SQLite projection, no authority migration, no execution_state writes
  (Slice 0's deferrals stand).
- No scanner rewriting of roadmap docs (declared/observed custody split holds).
- No `dependency_edge` in the first slice (see 3 above — separate gate).

## Open questions

- Should `tool_roadmap` records carry the drift-severity table row (structured)
  or just status + pointer? Default: pointer-only; structure follows a consumer.
