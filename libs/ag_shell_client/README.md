# ag_shell_client

The governor daemon **shell contract surface** — the protocol + typed models
that operator shells (maude terminal, phosphor web lane) rely on. AG's mouth,
not a shell's guts (boundary law: *maude runs the room; AG decides what the room
is allowed to claim*).

It exists to **de-triplicate** what was copied in three places — the daemon,
maude's client, phosphor's daemon_client: the Unix socket path derivation,
Content-Length framing, JSON-RPC 2.0 request/response, and the `-32001` auth
error. A shell pins this package; the package is CI-tested in-repo against the
daemon it speaks to (`test_socket_path_matches_daemon_derivation` asserts
byte-identity with `governor.daemon.default_socket_path`), so the contract
cannot drift silently.

## v0 surface (implemented)

- `default_socket_path(gov_dir)` — the daemon's socket path, proven identical.
- `encode_message` / `read_message` — Content-Length framing (injected read fns
  → testable over BytesIO, reusable over a socket).
- `make_request` / `parse_response` — JSON-RPC 2.0; `parse_response` raises
  `DaemonAuthError` on `-32001`, `RPCError` otherwise.
- `DecisionItem` / `DecisionOption` / `decisions_from_response` — the decision
  envelope (shell-contract v0 §2), safe-defaults `from_dict`: missing optional
  fields tolerated, unknown fields ignored (forward compat), a missing
  `decision_id`/`kind` REFUSED, an unknown KIND preserved + flagged
  (`is_known_kind`), never dropped or guessed.

## Contract

The full contract + rationale live in
`docs/design/governed-shell/shell-contract-v0.md` (CANDIDATE). This package
implements the transport + model half of it; the daemon side is
`operator.decisions.list` (GS-2b) and growing. Promotion of the contract doc to
`docs/specs/shell-contract/v0.md` (implemented-against) follows when the RPC
surface it names is built out (GS-3/4/5/6). NOT yet here: a live-socket client
class (the codec + models are the tested core; a thin socket wrapper is a
follow-on) and a TS client (phosphor's backend proxies this Python package).
