# Scope — rename `governor.spine` (the project-structure lock)

> **Scope RATIFIED, execution PARKED (2026-06-24).** Name + shape decided (below); **not done.**
> A scoped future cleanup, not a blocker — do it only when it's explicitly the next tiny task.
> Per `pinned_spine_rename_decision`: the `~/git/spine` *repo* keeps "Spine"; **AG's
> `governor.spine` renames to `structure_lock` when next touched** (don't churn pre-emptively).

## Disambiguation FIRST — "spine" means three unrelated things in AG; only one renames

| "spine" usage | What it is | Rename? |
|---|---|---|
| **`governor.spine`** (`src/governor/spine.py`: `Spine`, `SpineManager`) | the **project-structure lock** — `governor spine lock/activate/check`; locks a project's files/dirs, `--forbid` patterns, verifies proposals against the locked structure | **YES — the target** |
| "Instrumentation Spine" (v2.4) | metaphor for the signal substrate (`docs/SIGNAL_PLANE.md`, `FAILURE_CROSSWALK.md`, `REFERENCES.md`) | **no** |
| "self-annealing / workflow spine" | metaphor for the kernel backbone (`docs/doctrine/annealing_and_recomposition.md`, cross-tool notes) | **no** |

A blind `s/spine/<new>/` wrecks two metaphors and the doctrine. The rename is scoped to the
**`SpineManager` symbol + its surface**, NOT the word "spine."

## Blast radius (the target only)

- **Module:** `src/governor/spine.py` — classes `Spine`, `SpineManager`.
- **Src importers (5):** `__init__.py`, `cli.py`, `constraint_compiler.py`, `executor.py`, `slim_mode.py`.
- **Test importers (6):** `test_constraint_compiler`, `test_executor`, `test_failure_injection`,
  `test_golden_files`, `test_slim_mode`, + `test_spine` itself.
- **CLI:** the `governor spine …` group (lock/unlock/list/show/activate/deactivate/check) — user-facing, breaking.
- **Daemon RPC:** **clean** — no `spine.*` methods. (One fewer surface.)

## The two migration-hard spots (where it stops being mechanical)

1. **Persisted artifacts.** `spine_id` threaded ~21× through `cli.py`; a `spine_dir` /
   `.governor/spines/*.json` store. Existing on-disk locks key on `spine_id` + "spine" schema fields.
2. **Golden files.** `test_golden_files` pins the serialized JSON schema. Renaming stored keys
   breaks the goldens → trips the **no-laundering regression** tests. Don't fight that on a
   cosmetic rename.

> **Recommendation: rename the SURFACE, FREEZE the storage.** Rename module + classes + CLI;
> keep the on-disk format (`spine_id`, `.governor/spines/`, JSON keys) byte-identical. Storage is
> opaque — no migration, no golden churn, no laundering-test fight. A storage rename pays no rent.

## The name — DECIDED: `structure_lock` (operator, 2026-06-24)

- **`workspace`** — rejected: collides with `session_continuity`'s *Workspace* layer.
- **`boundary`** — rejected: philosophically right but too broad ("a 'misc' drawer in a
  cathedral" — half the repo is about boundaries).
- **`structure_lock`** — **chosen.** Says what it does: locks allowed project structure, checks/
  activates a bounded layout, prevents files outside the envelope, and does NOT imply the
  read-plane Spine.

The **point** is freeing the bare `spine` name: once `governor.spine` is gone,
`~/git/spine/NAMING.md`'s "don't ship a bare `spine` package" constraint lifts. (Per NAMING: any
interim read-plane code is `spine_readplane` / `constellation_spine`, never bare `spine`.)

### Exact rename mapping

```
module:  governor.spine            → governor.structure_lock
classes: Spine / SpineManager      → StructureLock / StructureLockManager
CLI:     governor spine ...        → governor structure-lock ...
         + keep `governor spine` as a HIDDEN DEPRECATED ALIAS for one cycle
```

### KEEP unchanged (storage-era names — ugly but stable; stability > aesthetic laundering)

```
spine_id · spine_dir · .governor/spines/*.json · serialized "spine" keys · goldens
```

## Execution shape (when actually doing it — NOT NOW)

1. Rename module + classes (→ `StructureLock` / `StructureLockManager`) + the 11 import sites +
   `__init__` exports.
2. Rename the CLI group (`governor structure-lock`); **keep `governor spine` as a hidden
   deprecated alias** for one cycle (scripts/muscle-memory).
3. **Do NOT touch storage or goldens.**
4. `pytest tests/ -q` bare. The golden + no-laundering tests are the canary — green = the rename
   did not leak into storage.

### Acceptance

```
- no golden churn
- no storage migration
- no broad s/spine/structure_lock/   (symbol+surface only; metaphors untouched)
- tests green
```

Effort: ~half-day mechanical IF storage stays frozen; multi-day IF migrated. No reason to migrate.
The patch refuses to confuse **naming** with **state migration**.

## Forcing-case note

The pinned rule is "rename when next touched, don't churn pre-emptively." Operator signal
2026-06-24: "we might touch spine soon based on how annoying this mess has been" — i.e., the
forcing case is forming but hasn't fired. This note is ready for whenever it does.
