# Workspaces (v2.1)

This is the v2 answer to "multi-project": **filesystem-partitioned state**.
Not tenants. Not a registry. Not a service. Just: "which `.governor/` am I in?"

## Definitions

- **Workspace root**: a directory that contains `.governor/`
- **Workspace dir**: `${workspace_root}/.governor/`
- **Workspace-scoped state**: receipts, sessions, pending violations, exceptions, caches—everything that makes governor "remember"

A workspace is the boundary where "context + policy + artifacts" stay coherent.

## v2 vs v3 boundary

### v2 (workspaces)
- Partition by **filesystem directory**
- Identity is "this path" (optionally hashed to a `workspace_id`)
- Remote access is operational (SSH tunnel/VPN), not a product surface
- Default posture: **one daemon per workspace**

### v3 (tenants)
- Partition by **service-level tenant/workspace object**
- Auth, capabilities, isolation, billing, revocation
- Remote is the product surface

Rule of thumb:
- v2: **workspace = repo-adjacent**
- v3: **workspace = account/tenant**

## Workspace resolution

Resolution precedence (highest wins):

1. Explicit flag `--governor-dir`
2. Environment `GOVERNOR_DIR`
3. Discovery: walk up from CWD looking for `.governor/`
4. Legacy fallback: existing monolithic/default dir (backcompat only)

Notes:
- Discovery should stop at filesystem root.
- Discovery may optionally stop at `.git/` and only accept `.governor/` within that tree (policy choice; keep it boring).
- Resolution returns:
  - `workspace_root`
  - `governor_dir` (workspace dir)
  - `workspace_id` (stable identifier; e.g., hash of canonical path)

## Storage posture

Default: **do not commit workspace artifacts to git**.

Recommended layout:
- `.governor/` contains runtime artifacts (receipts, sessions, exceptions, pending, blobs)
- Optional versioned policy file:
  - `.governor/config.toml` (or similar)
  - everything else ignored

The goal is: "policy can be shared; artifacts stay local."

## Daemon topology (v2)

Default: **one daemon per workspace**.

- Daemon reads/writes only within the resolved `governor_dir`.
- Daemon socket is unique per workspace.

### Socket resolution

Precedence:
1. `--socket`
2. `GOVERNOR_SOCKET`
3. Derived default from workspace:
   - `${governor_dir}/daemon.sock` (or `${governor_dir}/run/daemon.sock`)

If no workspace can be resolved, fall back to the legacy default socket behavior.

## CLI affordances

### `governor init`
Creates a workspace in the current directory:
- makes `.governor/`
- optionally writes a minimal config stub
- does not start daemons, does not register projects, does not "manage" anything

### "Do the right thing" behavior
Commands should use workspace resolution automatically:
- `governor selfcheck`
- `governor check`
- receipts/state commands

Expectation: you can run commands from any subdir in a repo and it resolves correctly.

## Client implications

Clients must be able to select a workspace by selecting a `governor_dir`.

- VS Code extension:
  - default `governorDir = ${workspaceFolder}/.governor` (if present)
  - otherwise use resolver behavior and/or offer `governor init`
- WebUI:
  - remains a daemon client
  - workspace selection is "which daemon/socket are we talking to?"
- Example clients (Maude/Guvnah):
  - keep local-first; remote access (if any) is via tunnel/proxy, not a v2 feature

## Invariants

Workspaces must not break the core promises:
- single authority pipeline (no split-brain)
- receipts always emitted (or failures are loud)
- provenance captured (backend_type, model, run_id)
- identity captured where trusted (principal_id/tenant_id)
- pending-violation latch works across entrypoints
- selfcheck can detect degraded/partial states inside a workspace

## Non-goals (v2.1)

- Multi-workspace daemon routing
- Cross-workspace queries/indexing
- Remote transport as a first-class feature
- Tenancy/auth/capabilities/billing
- "Fleet" (that's v3)

If you feel the urge to build a registry, stop. You're in v3 territory.
