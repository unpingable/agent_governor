# Deployment Modes

Three deployment modes. Pick one. Don't mix assumptions.

---

## Mode 1: Local (Same Machine)

**Transport:** Unix domain socket or `127.0.0.1` loopback
**Auth:** Per-session bearer token, file-permission gated
**TLS:** None. Localhost traffic doesn't leave the machine.

This is the right mode for:
- Development
- Single-user CLI usage (Maude, Claude Code, Codex)
- `test-with-governor.sh` local testing

### Wiring

```
Governor daemon  →  unix:/run/governor/governor.sock  (or 127.0.0.1:8000)
Maude client     →  connects to socket/loopback
Token            →  ~/.config/governor/token (0600)
```

### Threat model

"Someone already on your box" is game-over regardless. OS user permissions are the access control. A bearer token prevents accidental cross-user access and stages the auth boundary for later modes.

### What's implemented today

- Governor binds `0.0.0.0:8000` (via uvicorn) or Docker port mapping
- No auth, no token validation
- CORS: `allow_origins=["*"]`

### What needs to change for proper local mode

1. Bind to `127.0.0.1` instead of `0.0.0.0` (or UDS)
2. Generate a session token on `governor init`, store at `~/.governor/token`
3. Check `Authorization: Bearer <token>` header on all mutating endpoints
4. Read endpoints: low friction (or no-auth for dev)
5. Commit/waiver endpoints: require token

---

## Mode 2: Private Network

**Transport:** Overlay network (Tailscale, WireGuard) + HTTPS
**Auth:** Bearer token or OIDC/JWT
**TLS:** Provisioned by overlay (Tailscale Serve) or `mkcert` for local HTTPS

This is the right mode for:
- Team dev environments
- Cross-machine access (laptop to server)
- Internal tooling, homelab

### Options

| Approach | Complexity | Notes |
|----------|-----------|-------|
| **Tailscale Serve** | Low | Provisions HTTPS certs for tailnet names automatically |
| **mkcert** | Low | Local trusted CA, good for browser HTTPS behavior |
| **Caddy reverse proxy** | Medium | Auto HTTPS with internal CA for `*.localhost` |
| **WireGuard + token** | Medium | Manual overlay, but full control |

### Tailscale pattern (recommended)

```bash
# On the machine running governor:
tailscale serve https / http://127.0.0.1:8000

# Maude on another machine:
GOVERNOR_URL=https://governor.tail12345.ts.net maude
```

Tailscale handles cert provisioning, rotation, and identity. You get HTTPS without becoming an OpenSSL shaman.

---

## Mode 3: Public

**Transport:** ACME TLS (Let's Encrypt)
**Auth:** OIDC/JWT for user-to-service, mTLS for service-to-service
**TLS:** Terminated at ingress/proxy, auto-renewed

This is the right mode for:
- Public SaaS API
- Multi-tenant deployments
- Anything reachable from the open internet

### Architecture

```
Internet  →  [Ingress/Proxy]  →  [Governor]
               ↑                    ↑
          ACME TLS              127.0.0.1 only
          Rate limiting         Token/JWT validation
          WAF rules             Audit logging
```

### Components

| Layer | Tool | Purpose |
|-------|------|---------|
| TLS termination | Caddy / nginx / Traefik | ACME cert + renewal |
| Auth | OIDC provider or API keys | User identity |
| Rate limiting | Ingress middleware | Abuse prevention |
| mTLS (service-to-service) | SPIFFE/SPIRE | Workload identity + rotation |
| Audit | Governor receipts | Every action logged |

### What this requires beyond Mode 1-2

- Strong auth on all endpoints (not just mutating ones)
- Rate limiting
- Request signing or nonce for commit endpoints
- Strict CORS (no `*`)
- Separate operator UI from agent authority API

---

## Auth Boundary Design

Even in Mode 1, the auth abstraction should exist. Same interface, different verifier.

### Endpoint tiers

| Tier | Examples | Auth requirement |
|------|----------|-----------------|
| **Read** | `/health`, `/governor/now`, `/governor/status` | Low (or none in dev) |
| **Propose** | `/sessions/`, `/governor/code/constraints` | Token required |
| **Commit** | Apply decisions, waivers | Token + nonce + active session |
| **Admin** | Profile switching, backend toggle | Operator identity |

### Token flow (Mode 1)

```
governor init
  → generates token → ~/.governor/token (0600)
  → governor daemon reads token on startup

maude / CLI client
  → reads ~/.governor/token
  → sends Authorization: Bearer <token>

governor
  → validates token on mutating endpoints
  → rejects unknown tokens with 401
```

### Token flow (Mode 2+)

Same interface. Replace file-based token with:
- OIDC token from SSO provider
- JWT with scoped claims
- mTLS client certificate (SPIFFE SVID)

The governor doesn't care *how* identity is established. It cares that mutating actions have attribution.

---

## Transport Matrix

| | Mode 1: Local | Mode 2: Private | Mode 3: Public |
|---|---|---|---|
| **Binding** | `127.0.0.1` / UDS | Overlay IP | `0.0.0.0` behind proxy |
| **TLS** | None | Tailscale / mkcert | ACME (Let's Encrypt) |
| **Auth** | File token | Token / OIDC | JWT / mTLS |
| **CORS** | `*` (dev only) | Tailnet origins | Strict allowlist |
| **Rate limit** | None | Optional | Required |
| **Audit** | Receipts | Receipts | Receipts + access logs |
| **Identity** | OS user | Overlay identity | OIDC/SPIFFE |

---

## What to do today

1. **Dev**: Use Mode 1. Bind `127.0.0.1`, skip TLS, optionally add token.
2. **Cross-machine dev**: Use Tailscale Serve. Zero cert management.
3. **Don't** add self-signed certs, custom CA hierarchies, or TLS bypass flags. That's ceremony that protects nothing.

The governor's natural strength is the *commit boundary*, not the transport layer. Get auth attribution right (who approved this action?) and the transport is a solved problem at every scale.
