# Versioning Policy

## Governor CLI (`agent_gov`)

Semantic versioning. Tags and GitHub releases.

## VS Code Extension (`vscode-governor`)

Tracks Governor CLI **major/minor**. Extension `2.MINOR.x` targets Governor `>= 2.MINOR.0`.
Patch versions drift independently.

Features are capability-probed at runtime (`governor <subcommand> --help`).
If a subcommand doesn't exist on the user's CLI version, the corresponding UI
silently degrades — no error, no notification spam.

## Web UI (`gov-webui`)

Independent versioning. Gates on `api_schema_version` returned by the governor
daemon, not on governor's semver tag. The web UI can rev faster or slower than
the CLI without coupling concerns.

## TUI clients (`maude`, `guvnah`)

Independent versioning. Talk to the governor daemon via JSON-RPC (Unix socket
or stdio). Protocol compatibility is the contract, not version numbers.

## Receipt Kernel (`libs/receipt_kernel`)

Independent versioning. Stdlib-only, zero external deps. Imported by governor
core as a path dependency. Version tracks its own API surface.
