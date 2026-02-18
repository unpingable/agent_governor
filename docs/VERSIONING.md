# Versioning Policy

## Coupling Rule

**Hard-coupled clients** track Governor **major.minor** — client 2.3.x expects
governor 2.3.x. Patch versions are independent. This is the simplest possible
compatibility statement: no matrix, no interpretive dance.

**Loosely coupled clients** have independent semver and declare contract version
requirements (RPC protocol, schema versions) in their `COMPAT.md`.

Each satellite repo has a `COMPAT.md` with: version coupling rule, required
governor version range, contract versions, and feature negotiation/degrade behavior.

## Semver vs Contract Versions

Semver is for release bundles. Contract versions are explicit integers that only
change on actual breaking schema/protocol changes:

| Contract | Version | Location |
|----------|---------|----------|
| RPC protocol | 1.0 | `daemon.py:PROTOCOL_VERSION` |
| StatusRollup schema | 1 | `status_rollup.py:ROLLUP_SCHEMA_VERSION` |
| ViewModel schema | v2 | `viewmodel.py:SCHEMA_VERSION` |
| Receipt schema | 2 | `gate_receipt.py:RECEIPT_SCHEMA_VERSION` |
| CLuD schema | 1 | `clud.py:CLUD_SCHEMA_VERSION` |

Clients check these at startup or first call. Mismatch = clear error + feature disable.

---

## Governor CLI (`agent_gov`)

Semantic versioning. Tags and GitHub releases.

## VS Code Extension (`vscode-governor`) — hard-coupled

Tracks Governor CLI **major.minor**. Extension `2.3.x` targets Governor `>=2.3.0 <2.4.0`.
Patch versions drift independently.

Features are capability-probed at runtime (`governor doctor --json`).
If a subcommand doesn't exist on the user's CLI version, the corresponding UI
silently degrades — no error, no notification spam.

## Maude (`maude`) — hard-coupled

Tracks Governor CLI **major.minor**. Client `2.3.x` targets Governor `>=2.3.0 <2.4.0`.
Talks to governor daemon via JSON-RPC (Unix socket). Shape adapters normalize
daemon responses to Pydantic models; missing fields get safe defaults.

## Guvnah (`guvnah`) — hard-coupled

Tracks Governor CLI **major.minor**. Client `2.3.x` targets Governor `>=2.3.0 <2.4.0`.
Spawns governor daemon as child process (`governor serve --stdio`). RPC client
handles protocol negotiation via `governor.hello`.

## Web UI (`gov-webui`) — loosely coupled

Independent versioning. Gates on contract versions (RPC protocol, schema versions),
not on governor's semver tag. The web UI can rev faster or slower than the CLI.

## Receipt Kernel (`libs/receipt_kernel`)

Independent versioning. Stdlib-only, zero external deps. Imported by governor
core as a path dependency. Version tracks its own API surface.
