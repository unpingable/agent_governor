# GOV-GAP-SESSION-001: Cryptographic Session Binding

Status: `deferred` (v3 roadmap — placeholder fields in v2, full crypto in v3)

## Problem

The governor daemon communicates over Unix sockets (local) or potentially
TCP (remote deployment). Currently, session identity is implicit — whoever
connects to the socket is the session. There is no:

- Cryptographic binding between client and session
- Protection against session hijacking on shared hosts
- Replay protection for RPC calls
- Authentication of the connecting principal

For local single-user deployment this is acceptable (Unix socket permissions
provide OS-level access control). For remote daemon deployment (v3), this
becomes a real security gap.

## What This Addresses

Mechanical protocol plumbing for authenticated, replay-resistant daemon
communication:

1. **Session tokens**: Cryptographic session binding (not just connection identity)
2. **Nonce binding**: Per-request nonces prevent replay
3. **Request/response MACs**: Integrity protection on RPC payloads
4. **Replay windows**: Time-bounded acceptance of requests

## Why Deferred

- v2 is single-node, local deployment. Unix socket permissions are sufficient.
- Cryptographic session binding adds complexity that isn't justified until
  the daemon serves remote clients.
- The principal model (who is connecting) needs to be designed first — crypto
  binds *to* an identity, so the identity model must exist.
- No current threat model requires this for local operation.

## What v2 Should Bake In Now

Even though full crypto is v3, v2 should include **placeholder fields** in
the relevant data structures so that v3 doesn't require breaking changes:

### In daemon RPC responses

```python
# Already in governor.hello response — add:
"session": {
    "session_id": "...",        # Already exists
    "principal": null,          # v3: authenticated identity
    "auth_method": "local",     # v3: "mtls" | "token" | "local"
    "session_token": null,      # v3: cryptographic session token
}
```

### In receipt schema

```python
# Receipt already has schema_version — add optional field:
"principal_ref": null           # v3: hash of authenticated principal
```

### In daemon config

```ini
[security]
# auth_mode = local             # v3: "local" | "token" | "mtls"
# session_token_ttl = 3600      # v3: token lifetime in seconds
# replay_window = 300           # v3: max age of accepted requests
```

These are null/commented-out in v2 but structurally present so v3 can
populate them without schema migration.

## Minimal v3 Design (when built)

### mTLS option

- Daemon generates self-signed CA on `governor init`
- Client certificates issued per principal
- Standard TLS mutual authentication
- Session token = TLS session ID

### Token option (simpler)

- Daemon generates HMAC key on `governor init`
- Client presents signed token on connect
- Token includes: principal_id, issued_at, nonce
- Daemon validates signature + freshness

### Per-request integrity

```
request_mac = HMAC(session_key, canonical_json(request))
```

Included in JSON-RPC request envelope. Daemon rejects mismatched MACs.

### Replay protection

- Each request includes monotonic sequence number per session
- Daemon rejects sequence numbers ≤ last seen
- Time-based replay window as fallback (handle clock skew)

## Existing Machinery

| Component | Relevance |
|-----------|-----------|
| Daemon (`governor serve`) | The server that would enforce this |
| Content-Length framing | Already in place — crypto wraps the framed payload |
| `governor.hello` RPC | Session establishment — natural place for auth handshake |
| Receipt canonical JSON | Deterministic serialization — needed for MAC computation |
| Config file (`daemon.conf`) | Already supports `[sections]` — add `[security]` |

## Dependencies

- Principal model (who are the actors?) — needs design before crypto
- Key management (generation, storage, rotation) — operational complexity
- Client libraries (Guvnah, Maude) need to support auth handshake

## Relationship to Other Gaps

- GOV-GAP-CHAIN-001: Chain gate evaluates *what* happens — session binding ensures *who* requested it
- GOV-GAP-EGRESS-001: Egress gate evaluates outbound data — session binding authenticates the requestor
- GOV-GAP-MCP-SUPPLY-001: Tool supply chain integrity — session binding is principal integrity
- GOV-PRIM-PROV-001: Provenance labels tag *what* — principal_ref tags *who*
