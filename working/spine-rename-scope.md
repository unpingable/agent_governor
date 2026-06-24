# Scope — rename `governor.spine` (the project-structure lock)

> **Scoping note, not authorization to execute.** Read-only analysis 2026-06-24. The pinned
> decision (memory `pinned_spine_rename_decision`): the `~/git/spine` *repo* keeps the name
> "Spine"; **AG's `governor.spine` is the one slated to rename when next touched** (don't churn
> pre-emptively). This note scopes that rename so it's not oral tradition when the time comes.

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

## The name (pinned: "workspace/boundary")

- **`workspace`** — **collides**: `session_continuity` already owns a *Workspace* layer
  (Ledger/Workspace/Transcript). Avoid.
- **`boundary`** — the pinned fallback; fits (it's a write-fence); generic (AG has many "boundaries").
- **`structure_lock` / `layout_lock`** — more precise (locks the project *structure/layout*); no
  collision. Slight lean.

Whichever: the **point** is freeing the bare `spine` name. Once `governor.spine` is gone,
`~/git/spine/NAMING.md`'s "don't ship a bare `spine` package" constraint lifts; the name belongs
to the read-plane organ if it ever lands in AG. (Per NAMING: any interim read-plane code is
`spine_readplane` / `constellation_spine`, never bare `spine`.)

## Suggested execution shape (when actually doing it)

1. Pick the name (`boundary` or `structure_lock`).
2. Rename module + classes + the 11 import sites + `__init__` exports.
3. Rename the CLI group; **keep `spine` as a hidden deprecated alias** for one cycle (scripts/muscle-memory).
4. **Do NOT touch storage or goldens.**
5. `pytest tests/ -q` bare. The golden + no-laundering tests are the canary — green = the rename
   did not leak into storage.

Effort: ~half-day mechanical IF storage stays frozen; multi-day IF migrated. No reason to migrate.

## Forcing-case note

The pinned rule is "rename when next touched, don't churn pre-emptively." Operator signal
2026-06-24: "we might touch spine soon based on how annoying this mess has been" — i.e., the
forcing case is forming but hasn't fired. This note is ready for whenever it does.
