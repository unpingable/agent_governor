# GOV-GAP-MCP-SUPPLY-001: Signed Tool Manifests + Hash Pinning

Status: `deferred` (v3 roadmap — document now, build when MCP gateway matures)

## Problem

The MCP gateway (Phase 0 shipped in `libs/mcp_governor/`) proxies tool calls
through a policy gate. But it trusts that the tool server on the other side
is what it claims to be. There is no verification that:

- The tool server binary hasn't been tampered with
- The tool's declared capabilities match its actual behavior
- The tool version is the one that was reviewed/approved
- A tool update didn't silently change behavior

This is the tool supply chain problem. Real-world incidents show attackers
compromising MCP tool servers (malicious npm packages, poisoned pip installs,
typosquatted tool names) to gain execution within agent runtimes.

## What This Addresses

Control-plane hardening for the tool supply chain:

1. **Signed manifests**: Tool servers publish signed capability manifests
2. **Hash pinning**: Gateway pins tool server binaries/packages by content hash
3. **Trust store**: Allowlist of signing keys / trusted publishers
4. **Upgrade policy**: Rules for when/how tool versions can change

## Why Deferred

- MCP gateway is Phase 0 (proof-of-life). The transport works but the
  ecosystem is immature.
- Signing infrastructure requires coordination with MCP tool publishers
  (external dependency we don't control).
- Hash pinning is useful locally but doesn't solve the initial trust
  establishment problem.
- The composition gate (GOV-GAP-CHAIN-001) and egress gate (GOV-GAP-EGRESS-001)
  mitigate the *consequences* of a compromised tool without requiring
  supply chain integrity. Defense in depth.

## Minimal v1 (when built)

### Tool manifest

```json
{
  "tool_id": "filesystem-server",
  "version": "1.2.3",
  "publisher": "anthropic",
  "capabilities": ["file_read", "file_write", "file_list"],
  "binary_hash": "sha256:abcdef...",
  "manifest_signature": "ed25519:...",
  "signed_at": "2026-02-23T00:00:00Z"
}
```

### Hash pinning

```json
{
  "pins": {
    "filesystem-server": {
      "allowed_hashes": ["sha256:abcdef...", "sha256:123456..."],
      "allowed_publishers": ["anthropic"],
      "auto_update": false,
      "last_verified": "2026-02-23T00:00:00Z"
    }
  }
}
```

### Policy

- `pinned_only`: Only allow tools with matching hash pins (strict)
- `manifest_required`: Tool must present signed manifest (moderate)
- `trust_on_first_use`: Pin hash on first connection, reject changes (TOFU)
- `open`: No supply chain checks (current default, explicit)

### Gate integration

- Check at tool server connection time (not per-call)
- Verdict: ALLOW / DENY / WARN
- Receipt: gate="tool_supply_chain", includes tool_id + hash + pin_status

## Existing Machinery

| Component | Relevance |
|-----------|-----------|
| MCP gateway (`libs/mcp_governor/`) | The proxy that would enforce this |
| Receipt kernel redaction | Secret pattern matching — not directly relevant but similar pattern |
| Scope governor | Tool contracts already declare capability axes — supply chain adds integrity |
| Preflight | Pre-session checks — could include tool hash verification |

## Dependencies

- MCP ecosystem needs to support tool manifests (not yet standardized)
- Signing key infrastructure (PKI or TOFU model)
- Binary hash computation needs to be reproducible across platforms

## Tests (when built)

- Valid manifest + matching pin → ALLOW
- Valid manifest + mismatched pin → DENY
- Missing manifest in `manifest_required` mode → DENY
- TOFU: first connection → pin, second connection same hash → ALLOW
- TOFU: first connection → pin, second connection different hash → DENY
- Expired manifest signature → DENY
- Receipt fields present and schema-valid

## Relationship to Other Gaps

- GOV-GAP-CHAIN-001: Chain gate mitigates *consequences* of compromised tools
- GOV-GAP-EGRESS-001: Egress gate prevents data exfiltration even if tool is compromised
- GOV-PRIM-PROV-001: Provenance labels identify which tool produced which data
- This gap prevents the compromise in the first place (defense in depth)
