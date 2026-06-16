# MCP Integration (v3)

status: planning (deferred)

| Field | Value |
|-------|-------|
| Status | `planning (deferred)` |
| Depends on | v2.1 workspaces, SELF_GOVERNANCE_SPEC.md |
| Blocked by | v2.1 completion |

## Guiding principle

> MCP should make the governor **callable** — not make the governor **delegatable**.

## Non-goals (hard constraints)

- MCP is **transport/interop**. Not an architectural rewrite.
- Governor may expose tools via MCP; governor **does not become an MCP toolchain
  orchestrator** without an explicit sandbox spec.
- No "microservice brain" — the governor remains a single-authority pipeline.

---

## Orientation

- [ ] Prefer **Governor-as-MCP-server** (expose governor checks as callable tools
  to MCP-capable clients like ChatGPT, Codex, Claude Desktop)
- [ ] Treat **Governor-as-MCP-client** (governor calls other MCP servers for
  git/filesystem/etc.) as **high-risk** unless heavily sandboxed + allowlisted
- [ ] Default to server posture: keep "reality checks" inside the governor; don't
  outsource your trust boundary to a tool mesh

## Minimal MCP surface for v3

### `mcp-epistemic-governor` (local-first)

Primary server. Exposes the governor's core gates as callable tools:

- tools: `governor.selfcheck`, `governor.verify_patch`, `governor.run_gate`,
  `governor.query_receipts`
- resources: read-only receipt artifacts (optionally)

### `mcp-citation-resolver` (stateless)

External substrate resolution. Thin wrapper over existing `governor external` commands:

- tools: `resolve_doi`, `resolve_arxiv`, `resolve_rfc`, `resolve_cve`, `resolve_pypi`

### `mcp-policy-registry` (decisions ledger)

Policy versioning and diffing:

- tools: `get_policy_version`, `diff_policy`, `pin_policy_hash`

### `mcp-witness-attestation` (future / WLP)

Witness proofs and verification hooks. Deferred until self-governance spec is implemented:

- tools/resources for witness proofs + verification hooks

## Receipt protocol hooks

- [ ] Every MCP tool call produces a **GateReceipt** (same as CLI/daemon paths):
  - include: `transport="mcp"`, `client_id`/fingerprint, `server_id`, `session_id`,
    `tool_name`, `args_hash`
  - ensure: `receipt_id` remains content-addressed over the semantic inputs
    (don't let session IDs poison identity)

## Security posture

MCP is a fresh attack surface. The "official" Git MCP server had path traversal +
arg injection class bugs (CVE-2025-68145), and these are chainable with other servers.
Go here with knives out.

### Hard rules

- [ ] **No raw filesystem paths** accepted by MCP-exposed tools unless
  rooted + normalized + symlink-resolved
- [ ] **No shelling out** with user-controlled args (argument injection class)
- [ ] **Composition hazard**: "safe tools in isolation" does NOT mean safe when chained
  (git + filesystem was the obvious footgun). Document + test explicitly.
- [ ] If wrapping git operations: explicitly avoid repeating the `mcp-server-git`
  failure classes (path traversal via repo flags; arg injection via CLI)
- [ ] Adopt MCP spec security posture explicitly:
  consent/control, tool safety, sampling controls
- [ ] Rate limits + allowlists per tool (capability tokens optional;
  boring allowlists are fine for v3)

### Interop (optional)

- [ ] If exposing receipts to ChatGPT/Codex: MCP server with `search` + `fetch`
  over receipt store (matches OpenAI's MCP connector shape)
- [ ] Treat this as a **read-only** surface. Write operations require separate
  authorization (this is how you accidentally leak your ops brain)

## Abuse harness / tests

- [ ] **Path traversal** regression tests: `..`, absolute paths, symlink escape
- [ ] **Arg injection** tests: flags embedded in params, weird unicode, null bytes
- [ ] **Prompt-injection-style chaining**: tool chaining attempts that should fail
  by construction
- [ ] **Tool surface lint**: tool list + params schema changes must bump
  `code_version` and become receipt-visible

## Relationship to existing MCP code

The governor already has `src/governor/mcp_server.py` (MCP server for Claude integration).
A `src/governor/mcp_safety.py` (rate limiter, backpressure, circuit breaker, idempotency,
latency enforcer, fault handler) existed as a v2 implementation but was **retired-unused
and deleted 2026-06-16** — it had no production consumer (see
`specs/gaps/GOV_GAP_MCP_SAFETY_DISPOSITION_001.md`). The v3 work should:

- Treat MCP self-protection as greenfield, built from a measured failure mode
  outward (do NOT resurrect the deleted module — the resurrection condition is
  in the disposition gap)
- Add the receipt protocol hooks (every tool call → GateReceipt)
- Add the abuse harness tests
- Decide on multi-server topology (one combined server vs. split by concern)

## References

- [MCP Specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)
- [OpenAI MCP server docs](https://platform.openai.com/docs/mcp)
- [CVE-2025-68145: mcp-server-git path traversal + arg injection](https://nvd.nist.gov/vuln/detail/CVE-2025-68145)
- [Anthropic Git MCP server flaws (The Register)](https://www.theregister.com/2026/01/20/anthropic_prompt_injection_flaws/)
