# MCP Governor Gateway — Hardening Guide

How not to bypass this.

## stdout / stderr rule

**stdout is protocol only.** Any logging, diagnostic, or debug output on
stdout is a protocol integrity failure — the MCP client will parse it as a
JSON-RPC message and break.

- All gateway logging goes to stderr via `print(..., file=sys.stderr)`.
- Upstream tool server stderr is either inherited or drained in a background
  thread. It is **never** redirected into stdout.
- If you add debug/trace modes, they write to stderr or a file. Never stdout.

This is not a style preference. It's a correctness invariant.

## Bypass patterns and mitigations

### 1. Gateway spawns the tool server

In stdio mode, the gateway launches the upstream tool server as a child process.
The client never sees the spawn command, the child's PID, or any handle to the
child's stdin/stdout. The only way to reach the tool server is through the gateway.

**Don't:**
- Expose the upstream command in environment variables, logs, or error messages.
- Let the client specify which server to connect to (config is operator-controlled).
- Give the client a way to bypass the gateway and talk to the child directly.

### 2. Don't expose upstream directly

If the upstream tool server listens on a network port (Phase 2+ HTTP mode):
- Bind to `127.0.0.1` only. Never `0.0.0.0`.
- Use mTLS or a shared secret between gateway and upstream.
- The gateway is the only externally reachable endpoint.

For stdio mode: the child process's stdin/stdout are pipes owned by the gateway.
There is no network port to accidentally expose.

### 3. No env var leaks

Tool arguments and error messages are the two places secrets sneak into receipts
"by helpfulness."

- `args_summary` is keys-only. Never includes argument values.
  Format: `"args: key1, key2, key3"` — not `"args: {key1: secret_value}"`.
- `error` is single-line, capped at 256 characters, and scrubbed for secret
  patterns (API keys, bearer tokens, passwords, AWS keys, GitHub tokens, private
  key headers).
- `result_hash` is omitted by default. Tool results often contain secrets or PII.
  Only enable result hashing when you have a sanitized result channel.

Environment variables are never logged, included in receipts, or passed through
to the client. The upstream command is stored as a SHA-256 hash in
`ext.gov.mcp.upstream.command_hash`, never as raw text.

### 4. Debug dumps are off by default

There is no debug dump mode in Phase 0. When one is added:
- It must be opt-in (explicit flag or env var, not default behavior).
- It must write to a file or stderr, never stdout.
- It must carry a loud warning that tool args and results may contain secrets.
- Receipt files with debug content should be treated as sensitive.

### 5. Receipt file security

- Receipt files are created with `0o600` (owner read/write only).
- If an existing file has more open permissions, the gateway warns on stderr.
  It does not silently proceed.
- Rotation is size-based (default 10 MB, keep 5 files). Rotated files inherit
  the permissions of the original.
- Receipt files contain: tool names, argument key names, sanitized error messages,
  agent identity, timestamps, and receipt hashes. Even without argument values,
  this metadata can be sensitive. Protect receipt files like logs.

### 6. Child process hygiene

On gateway exit:
1. Close upstream stdin (signals EOF).
2. Wait 2 seconds for clean exit.
3. SIGTERM if still running.
4. Wait 2 more seconds.
5. SIGKILL if still running.

Upstream stderr is drained in a background daemon thread. If the upstream server
floods stderr, the drain thread consumes it without blocking the proxy loop. The
drain thread dies when the gateway exits (daemon thread).

### 7. JSON-RPC framing

stdio transport uses newline-delimited JSON-RPC. One line = one message.
`json.dumps` with compact separators (`(",",":")`) never emits literal newlines.
This is per the MCP spec for stdio transport.

**Don't:**
- Use Content-Length framing for stdio (that's HTTP transport).
- Allow embedded newlines in messages.
- Parse non-JSON lines as messages (they're errors).

### 8. Policy engine is a bootstrap shim

Phase 0's `PolicyEngine` (denylist regex) lives in the gateway because the
governor policy interface isn't wired yet. It's a bootstrap shim, not the real
policy brain. The gateway's two primacy invariants:

1. **Single policy brain:** Gateway never invents governance semantics. As the
   governor policy interface stabilizes, the gateway becomes a thin caller.
2. **Receipt format is downstream of governor:** The gateway writes what the
   governor decided. It doesn't define new receipt fields or reason codes.

When someone asks "why was this denied," the answer should point to governor
policy provenance, not gateway regexes.
