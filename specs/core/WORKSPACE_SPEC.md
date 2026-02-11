# Workspace Spec (v2.1)

| Field | Value |
|-------|-------|
| Status | `ahead` |
| Depends on | All 2.0 specs (complete) |
| Blocked by | Nothing |
| Design doc | `docs/WORKSPACES.md` |

## Scope

Add **filesystem-partitioned workspaces** so governor state is isolated per project/repo.

- Workspace is defined by a `.governor/` directory.
- Default behavior: **one daemon per workspace**.
- Clients select a workspace by selecting a socket and/or `GOVERNOR_DIR`.

## Non-goals (explicit)

- Multi-workspace daemon routing
- Cross-workspace indexing/query
- First-class remote transport/auth (v3)
- "Fleet" / worker registry (v3)
- `workspace add/list/remove` (that's a registry; registries are v3)
- User-chosen workspace names (names become registries; use derived hash)

If you feel the urge to build a registry, stop. That's v3.

## Current state (the integration gap)

The data model is already workspace-ready:

- **Every state module** takes `gov_dir` as a parameter: `GateReceiptSystem(root)`,
  `SessionStore(base_path)`, `ViolationResolver(governor_dir)`, `DaemonState(governor_dir)`,
  `ScarLedger`, etc. All state artifacts live under the passed-in directory.
- **Socket derivation** exists: `default_socket_path(governor_dir)` in `daemon.py:1234`
  hashes the canonical path to produce a unique socket name.
- **Walk-up discovery** exists in `claude_hooks.py:42-49` (generated hook scripts walk
  `[cwd] + list(cwd.parents)` looking for `.governor/`).

What's missing: the **CLI doesn't use any of this**. It has a `--root` flag that defaults
to `"."` and hardcodes `get_governor_dir(ctx) = Path(root) / ".governor"`. No env var,
no walk-up, no workspace identity.

The fix is **one resolver module**, threaded into every entrypoint.

---

## Design

### Workspace identity

- **Workspace root**: a directory containing `.governor/`
- **Governor dir**: `${workspace_root}/.governor/`
- **Workspace ID**: `sha256(canonical_governor_dir)[:12]` — always derived, never user-chosen

### Resolution precedence (highest wins)

1. CLI flag `--governor-dir` / `-g`
2. Environment variable `GOVERNOR_DIR`
3. Walk-up discovery: from CWD, check each ancestor for `.governor/`
4. Legacy fallback: `${CWD}/.governor` (current behavior, backcompat)

Canonicalize paths (`resolve()`) so IDs and comparisons are stable.

### Socket resolution precedence

**Default socket lives with the workspace** for discoverability; implementations fall
back to the existing XDG-hash socket when workspace storage is unavailable.

1. `--socket` flag (already exists on `serve`)
2. `GOVERNOR_SOCKET` environment variable
3. Workspace-scoped default: `${governor_dir}/daemon.sock`
4. Fallback: `${XDG_RUNTIME_DIR}/governor-{hash}.sock` (if bind to workspace socket
   fails — read-only FS, perms, weird mount — fall back here and **log a warning**)

### Daemon topology

One daemon per workspace. No multi-workspace routing.

---

## Implementation plan

### Step 1: Workspace resolver module

**New file: `src/governor/workspaces.py`**

The single source of truth for "where is my governor state?" Everything else calls this.

```python
@dataclass
class ResolvedWorkspace:
    workspace_root: Path       # parent of .governor/
    governor_dir: Path         # the .governor/ directory itself
    workspace_id: str          # sha256(canonical_path)[:12]
    source: str                # "flag" | "env" | "discovery" | "fallback"

def resolve_workspace(
    governor_dir: str | Path | None = None,   # from --governor-dir flag
    cwd: Path | None = None,                   # override CWD for testing
) -> ResolvedWorkspace:
    """Resolve workspace using precedence: flag > env > discovery > fallback."""
    ...

def find_workspace_root(start: Path) -> Path | None:
    """Walk up from start looking for .governor/. Stop at filesystem root."""
    ...

def derive_default_socket(governor_dir: Path) -> Path:
    """Default socket inside the workspace: ${governor_dir}/daemon.sock.
    Caller should catch bind failure and fall back to XDG-hash socket."""
    ...

def workspace_id(governor_dir: Path) -> str:
    """Stable hash of canonical path. Derived, never user-chosen."""
    ...
```

**Critical**: Pull the walk-up logic from `claude_hooks.py:42-49` into this module.
Then make hooks import from here. One implementation, not two.

**Tests** (~20):
- Flag wins over env wins over discovery wins over fallback
- Discovery walks up from nested subdir, finds correct `.governor/`
- Discovery stops at filesystem root, returns None
- Fallback produces `CWD/.governor` when nothing discovered
- `workspace_id` is stable across calls, differs for different paths
- Symlinks resolve canonically
- `derive_default_socket` returns path inside governor_dir

### Step 2: Thread resolver into every entrypoint that touches state

**Modify: `src/governor/cli.py`**

This is the bulk of the wiring. The goal: there is exactly **one** "how do I find my
state?" logic, and it's shared.

Touchpoints:
- Replace `get_governor_dir(ctx)` internals to call `resolve_workspace()`
- Add `--governor-dir` / `-g` option to the `cli()` group
- Keep `--root` as a backcompat alias (same behavior, one canonical name in docs)
- `ensure_initialized(ctx)` uses the resolver
- All ~50+ commands that call `get_governor_dir(ctx)` get workspace support for free

Behavioral change: `governor selfcheck` from `repo/src/deep/` finds `repo/.governor/`.

**Modify: `src/governor/daemon.py` (`run_daemon` + `serve` CLI command)**

- Resolve `governor_dir` using resolver
- Socket resolution: try `derive_default_socket(governor_dir)` first; if bind fails,
  fall back to `default_socket_path(governor_dir)` (XDG hash) and log warning
- Replace `default_socket_path()` calls with resolver-based derivation

**Modify: `src/governor/claude_hooks.py`**

- Remove inline walk-up implementation from generated hook scripts
- Import `find_workspace_root` from `workspaces` module instead
- One source of truth for discovery

**Mechanical enforcement**: After wiring, grep for `GOVERNOR_DIR = ".governor"`,
`default_governor_dir`, `default_socket_path` — any direct callers that bypass the
resolver are bugs. Either make old functions delegate to the resolver and mark
deprecated, or delete them.

**Tests** (~15):
- `--governor-dir` flag resolves correctly
- `GOVERNOR_DIR` env var resolves correctly
- Commands work from subdirectory (walk-up)
- `--root` still works (backcompat)
- Error message when no workspace found
- Daemon uses workspace-scoped socket by default
- Daemon falls back to XDG socket on bind failure (with warning)
- `--socket` flag wins over env var wins over derived default
- `GOVERNOR_SOCKET` env var used when no flag
- CLI from nested dir resolves workspace (regression guard)

### Step 3: Make `governor init` workspace-aware

**Modify: `src/governor/cli.py` (init command)**

- `governor init` creates `.governor/` in CWD (same as now)
- Create minimal directory structure required by daemon/selfcheck
- Expand default `.gitignore` to cover all runtime artifacts:

```gitignore
# Runtime state (never commit)
*.db
*.db-wal
*.db-shm
rejections.log
pending_violations.json
scars.json
sessions/
receipts/
evidence/
exceptions/
daemon.sock

# Optional: uncomment to version policy
# !config.toml
```

- Optionally write `.governor/config.toml` stub
- Do NOT start daemons, do NOT manage registries

**Tests** (~5):
- Init creates `.governor/` with expected structure
- Init creates expanded `.gitignore`
- Init warns if already initialized
- Init from repo subdir creates `.governor/` in CWD (not repo root)

### Step 4: Selfcheck workspace reporting

**Modify: selfcheck command**

Add workspace info to selfcheck output so users can verify resolution:

```json
{
  "items": [
    {"name": "workspace_root", "status": "ok", "detail": "/home/user/repo"},
    {"name": "workspace_id", "status": "ok", "detail": "80f5c2338ca6"},
    {"name": "resolution", "status": "ok", "detail": "discovery"},
    ...existing items...
  ],
  "overall": "ok"
}
```

Also: `governor workspace info` (convenience alias) — print resolved workspace root,
governor_dir, workspace_id, resolution source. JSON with `--json`. That's it. No
`workspace add/list/remove`.

**Tests** (~5):
- Selfcheck includes workspace fields
- Selfcheck shows resolution source
- Selfcheck from subdirectory reports correct root

### Step 5: Workspace ID in receipts (optional, low-cost)

**Modify: `src/governor/gate_receipt.py`**

Not required for isolation, but useful for later aggregation:

- Add optional `workspace_id` field to `GateReceipt`
- NOT part of the content-addressed `receipt_id` (that would be a schema break)
- Stored as metadata alongside timestamp
- Derived from canonical `governor_dir` hash — no user-chosen names
- Populated automatically when receipt system initialized with workspace-aware path

**Tests** (~5):
- `workspace_id` appears in receipt JSON
- `workspace_id` is NOT part of `receipt_id` hash (schema stability)
- Receipts without `workspace_id` still deserialize (backcompat)

### Step 6: Docs

- `docs/WORKSPACES.md` — already written (design doc)
- Add short section to `docs/DEPLOYMENT.md`: "Run one daemon per workspace"
  - Examples: `cd repo && governor serve`, env override for VS Code / WebUI
- One paragraph in main README: "Governor is workspace-scoped; create `.governor/`
  per repo; run daemon per workspace."

---

## Build order

```
Step 1: workspaces.py (resolver)       ← foundation, no deps
Step 2: Thread into CLI + daemon       ← depends on Step 1 (this is the big one)
Step 3: governor init improvements     ← independent (can parallel with Step 2)
Step 4: selfcheck workspace reporting  ← depends on Step 2
Step 5: receipt workspace_id metadata  ← independent
Step 6: docs                           ← independent
```

## Test budget

| Step | Tests |
|------|-------|
| 1. Workspace resolver | ~20 |
| 2. CLI + daemon wiring | ~15 |
| 3. Init improvements | ~5 |
| 4. Selfcheck reporting | ~5 |
| 5. Receipt workspace_id | ~5 |
| **Total** | **~50** |

## Client implications (noted, not in v2.1 scope)

- **VS Code extension**: default `governorDir = ${workspaceFolder}/.governor` if present;
  offer init if missing. Already works with the resolver pattern.
- **WebUI (gov-webui)**: remains a daemon client; workspace = "which socket."
- **Maude/Guvnah**: keep `--governor-dir` / `--socket` flags; resolver happens CLI-side.

## Invariants

- Single authority pipeline per workspace (no split-brain)
- All state artifacts stay under `governor_dir` (no external state)
- Workspace ID is stable, derived, never user-chosen (names become registries)
- `--governor-dir` always wins (explicit > discovered)
- No workspace registry (filesystem IS the registry)
- Exactly one resolver implementation (everything calls it; grep to enforce)

## Traps to avoid

- **Socket on weird FS**: default to in-workspace, fall back to XDG with warning. Don't
  make it a matrix.
- **Walk-up reimplementation**: `claude_hooks.py` already has one. Move it to the resolver
  module. Don't end up with three slightly different "find my governor dir" functions.
- **`--root` confusion**: one canonical name (`--governor-dir`) in all docs and examples.
  `--root` is a silent alias for old scripts.
- **Workspace subcommands creep**: `workspace info` is enough. No `add/list/remove`.
  If you're storing a global list, you're building v3.

## Acceptance criteria

After v2.1, a developer can:

1. `cd ~/repos/project-a && governor init` — workspace in project A
2. `cd ~/repos/project-b && governor init` — workspace in project B
3. `cd ~/repos/project-a/src/deep/ && governor selfcheck` — finds project A's workspace
4. `governor serve` in each repo — separate daemons, separate sockets, zero cross-contamination
5. `governor receipts` shows only that workspace's receipts

No registry. No config file pointing at other projects. Just `.governor/` directories.
No breaking changes for users still using the monolithic default.

## Release

- Version bump: **2.1.0**
- Changelog headline: "Workspace isolation (per-repo `.governor/`) + workspace-scoped daemons"
