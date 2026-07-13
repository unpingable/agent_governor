# Client Ecosystem

**STATUS: STALE (marker added 2026-07-13, census D3).** Content dates from
2026-02-11 and predates the 2026-07-02 UI-shell rulings — guvnah is RETIRED
(specimen only), maude is reframed as the terminal-native operator shell,
phosphor as the web lane host; see `docs/roadmaps/CONSOLIDATION.md` for the
rulings and `docs/CONSTELLATION_MAP.md` for topology. The per-client narrative
below is retained as history; the daemon-authority principle still holds.

> v2 apps talk to a daemon you own (local). v3 apps talk to a service you operate (remote).

## The Principle

Agent Governor is the authority. Clients are views. Every client talks to the same daemon, gets the same receipts, obeys the same gates. The daemon is the single authority pipeline — clients never bypass it.

The governor doesn't compete on agent features. It competes on **invariants**: reconstructability, single authority, provenance, identity, and "stop the line." Receipts are the wedge. You're selling the seatbelt, not the car.

---

## Invariants (do not regress)

- Single authority pipeline (no split-brain semantics)
- Every gated decision is receipted
- Provenance is recorded (`backend_type`, `model`, `run_id`)
- Identity is recorded (`principal_id`, `tenant_id`) with explicit trust boundary
- "Stop the line" works through all entrypoints (pending-violation latch)
- Selfcheck exists and can be run remotely (integrity verification, not monitoring)

---

## Clients

### VS Code Extension

**Repo:** [github.com/unpingable/vscode-governor](https://github.com/unpingable/vscode-governor)

**Role:** Daily driver. The editor is where you actually live.

- v2: CLI-based integration (`governor check --json`, `governor selfcheck --json`). Local only.
- v3: Persistent daemon client via `governor serve --stdio`. Streaming, session awareness, workspace/tenant selection.

**v2 Roadmap (CLI-based, no daemon/RPC work):**

1. **Problems panel diagnostics** — `governor check --json` mapped to `DiagnosticCollection`. Issues show up where you already look. Single biggest "native" feel upgrade.
2. **Status bar selfcheck** — Poll `governor selfcheck --json` on save. Show OK/WARN/FAIL + last backend/model. Click opens detail panel.
3. **Receipt explorer TreeView** — Latest N receipts with principal/backend/model/verdict badges. Click opens JSON + linked evidence + exception.
4. **Command palette staples** — "Governor: Explain Selection", "Governor: Explain Git Diff", "Governor: Run Pending Violation Workflow".
5. **Workspace settings** — `governorDir`, `governorSocket`, `principalId`. Read from env by default, override via settings.

**v3 Roadmap (daemon-aware):**

1. **Stdio daemon mode** — Extension spawns `governor serve --stdio`, speaks JSON-RPC persistently. No sockets, no remote exposure, no XDG_RUNTIME_DIR nonsense. Works on every platform.
2. **Streaming chat panel** — Minimal UI. Daemon is the streaming source. Key: streaming + receipt link per turn.
3. **Active session model** — Sidebar shows current session, last N messages, last receipt IDs.
4. **Identity + attribution** — `principal_id` from config or environment. Per-principal usage stats (receipt count, last activity).

### WebUI (gov-webui)

**Repo:** [github.com/unpingable/governor_webui](https://github.com/unpingable/governor_webui)

**Role:** Workflow console — three opinionated panels, not a generic admin UI.

Gov-WebUI is three workflow panels that map to the governor's major operating modes. Each panel runs the same authority pipeline: augmentation, gating, receipts, stop-the-line latch.

#### Panel: Fiction

- **Purpose:** Fiction drafting / story work with governance constraints.
- **Typical outputs:** Drafted text + receipts (backend/model provenance).
- Core invariants: augmentation → gating → receipts; violation latch applies.

#### Panel: Nonfiction / Research

- **Purpose:** Research + synthesis workflows — evidence handling, citation discipline, iterative claims.
- **Typical outputs:** Research notes, claim structures, citations, receipts/selfcheck signals.
- Stronger emphasis on provenance and evidence artifacts.

#### Panel: Coding

- **Purpose:** Code-assist workflows as a convenience surface.
- **Typical outputs:** Same authority pipeline; receipts capture backend/model + principal_id.
- Coding mode exists mainly for parity and remote fallback; editor integrations are the intended daily driver.

**Notes:**
- WebUI remains a daemon client (no bypass paths). Chat delegates to daemon via Unix socket RPC.
- v2: Local-first workflows; the only client that *should* feel "remote" since it's already HTTP. Also serves as demo surface.
- v3: Graduates to canonical service UI — OIDC/session/tenant-aware.
- A separate private research app may exist later; if so, it orbits the same daemon authority.

### Maude

**Repo:** `~/git/maude` (not published)

**Role:** Example TUI client. Proof that the daemon RPC contract works from Python/Textual.

- v2: Unix socket JSON-RPC client. Keep as reference implementation. Don't promise it.
- v3: Either retire or promote to real client only if it earns its keep.

### Guvnah

**Repo:** `~/git/guvnah` (not published)

**Role:** POC Electron dashboard. Proof that stdio daemon mode works from TypeScript.

- v2: Spawns `governor serve --stdio` as child process. Fine for local use.
- v3: Only matters if it becomes an ops console or "fleet" view. Otherwise stays a toy.

---

## Transport Posture

### v2: Remote is an ops convenience

- Daemon exposes **UDS** (shared daemon) or **stdio** (child process). That's it.
- Remote access via **SSH tunnel / VPN** when you personally need it. Not a feature.
- Don't add TCP/remote transports to clients "just because."
- The correct remote story: **tunnel the daemon** or **use the WebUI**.

### v3: Remote is the product

- Pick a real transport (likely HTTPS + OIDC + sessions, or gRPC with auth).
- Treat remote as hostile by default.
- Design tenancy and capabilities around receipts.
- Questions that matter: who is allowed to reach it, what are they allowed to do, how do we audit and rate-limit, how do we isolate tenants, how do we revoke and recover.

### Why CLI stays the default for VS Code

- **Portability**: VS Code extensions run on macOS/Linux/Windows, Remote-SSH, Codespaces, containers. CLI works everywhere. Unix sockets do not.
- **Stability**: CLI is the public API. Daemon RPC can evolve without breaking the extension.
- **Failure modes are boring**: "binary not found" beats "socket permissions / stale socket / transport framing."

When latency matters, upgrade to `governor serve --stdio` — not to sockets.

---

## Fleet Primitive (v3, deferred)

The minimal "fleet" concept, if it earns its way in:

| Primitive | What It Is |
|-----------|-----------|
| `AgentLease` | Who owns a worker right now |
| `Job` | What to do |
| `Capabilities` | What it's allowed to touch (tools, filesystem scope, model allowlist) |
| `Receipts` | What it actually did |

Everything else is UI.

**Prerequisites already built:** single authority pipeline, receipts, integrity checks, agent leases (multi-agent v2), permissions, operating envelopes. That's the substrate that prevents "The Gang Gives Root (Distributed Edition)."

**Workspace manifests** (v3): "this repo + these env vars + these tool permissions + these policies" as a declarative blob you can reproduce. Attribution via `{tenant, principal, backend_type, model, run_id}`.

---

## Decision Heuristics

### Only promote a feature if it:

- Reduces manual context switching **today**, or
- Strengthens auditability/integrity **today**.

Everything else waits.

### Don't compete on agent features. Compete on invariants:

- Reconstructability
- Single authority
- Provenance
- Identity
- "Stop the line"

### The market window:

The "novel problem" window is narrowing — big vendors are shipping guardrails. But the "boring control-plane machinery that actually makes this survivable" window is opening. Vendor guardrails will be proprietary, ecosystem-locked, and optimized for "reduce liability" rather than "reconstruct what happened."

The differentiator isn't "my agent is better." It's **"I'm the thing that wraps agents and makes them auditable and stoppable."**
