# Implicit Side-Effect Governance

status: draft

## Core Invariant

**Any operation that produces observable effects outside the agent's reasoning
context is a governed action, whether or not it was invoked as an explicit
tool call.**

Rendering markdown, deserializing state, preprocessing inputs, counting
tokens — if it touches the network, the filesystem, or credential storage,
it is a tool call in governance terms. The fact that no tool was "invoked"
is irrelevant. The effect happened.

---

## The Problem

Threat intel (2025-2026) shows a recurring pattern: attackers bypass tool-call
governance entirely by triggering side effects through implicit channels.

| Implicit channel | Effect | Real-world example |
|-----------------|--------|-------------------|
| Markdown image rendering | Network fetch (egress) | EchoLeak (CVE-2025-32711): Copilot exfils data via auto-fetched images |
| Markdown link rendering | Network fetch (egress) | CodeGPT: prompt injection → image URL with embedded data |
| Serialization/deserialization | Object instantiation, secret loading | LangGrinch (CVE-2025-68664/68665): `lc` key injection |
| Token counting | SSRF | LangChain (CVE-2026-26013): vision token counter fetches arbitrary URLs |
| RAG crawlers | Network fetch, internal access | LangChain RecursiveUrlLoader domain escape (CVE-2026-26019) |
| URL parameter loading | Prompt execution | Copilot Reprompt (Jan 2026): `q` param auto-executes prompt |
| Memory/state writes | Persistent configuration change | OpenAI Atlas CSRF → memory poisoning |

Every one of these bypasses tool-call gating because the effect was produced
by something that doesn't look like a tool.

---

## Invariants

### I-1: Effect equivalence

If an implicit operation produces the same observable effect as an explicit
tool call, it must be subject to the same governance constraints.

```
network fetch via tool call    → egress gate + receipt
network fetch via image render → egress gate + receipt   (SAME)
```

### I-2: Implicit fetches are egress attempts

Any rendering, preprocessing, or framework operation that triggers a network
request MUST be surfaced as an egress attempt. Clients MUST either:

- Route the fetch through the egress policy gate, OR
- Block implicit fetches by default

"Just markdown" is not an exemption.

### I-3: Receipts include implicit side effects

Receipts for any governed action MUST include side effects triggered by
implicit channels during that action. This includes:

- Network requests triggered by rendering
- Object instantiation triggered by deserialization
- Filesystem access triggered by preprocessing
- Credential access triggered by framework internals

If a side effect is not in the receipt, it didn't happen as far as governance
is concerned — and that's a gap.

### I-4: Deserialization is a privileged operation

Reconstructing objects from serialized state — especially state that may
contain model outputs, tool responses, or external data — MUST be treated
as a privileged boundary crossing. Requirements:

- Strict typed schemas (no "magic key" interpretation)
- No implicit secret loading from environment
- No object instantiation from untrusted fields
- Provenance tagging on deserialized state

### I-5: Preprocessing must be side-effect-free

Operations that occur before the primary governed action (token counting,
prompt assembly, input validation) MUST NOT produce observable side effects.
If a preprocessing step requires network access or filesystem mutation,
it must be promoted to an explicit governed operation with its own receipt.

---

## Client Contracts

This spec defines governance-level invariants. Enforcement is split between
governor-core and client implementations.

### Governor-core responsibilities

- Egress gate accepts implicit-fetch events (already supported — egress gate
  is stateless and classifies any `EgressRequest`)
- Receipt schema accommodates implicit side effects (evidence bundles already
  support arbitrary evidence entries)
- Provenance labels apply to implicit channels (already supported — label
  assignment is rule-based on source class)

### Client responsibilities (Phosphor, VS Code extension, Clerk, MCP gateway)

Clients MUST:

1. **Disable auto-fetch by default** in any rendering context (markdown,
   HTML, rich text). External resources require explicit user action or
   policy approval.

2. **Route implicit fetches through egress policy** if auto-fetch is enabled.
   The fetch URL, destination classification, and originating context must
   be included in the egress request.

3. **Emit receipt events for implicit side effects.** If rendering triggers
   a network request, the client must log it as a receipt-eligible event
   with provenance (what rendered, what was fetched, why).

4. **Treat deserialized state as untrusted.** State loaded from persistence
   (session capsules, memory, cached tool outputs) must pass through typed
   validation before use. No raw object reconstruction.

---

## Relationship to Existing Subsystems

| Subsystem | Role |
|-----------|------|
| Egress gate | Enforcement point for I-2 (implicit fetches as egress attempts) |
| Provenance labels | Taint tracking for I-3 (receipt inclusion of side effects) |
| Scope governor | Authority separation — implicit channels cannot widen scope |
| MCP safety controls | Rate limiting / circuit breaking apply to implicit fetches too |
| Evidence gate | I-1 applies — implicit effects are governed the same as explicit ones |

No new subsystems required. This spec codifies the governance stance so that
existing enforcement points are applied consistently to implicit channels.

---

## What This Is NOT

- Not a client implementation spec (each client decides HOW to enforce)
- Not a new subsystem or code deliverable for governor-core
- Not specific to MCP (applies to any execution context with implicit effects)
- Not about prompt injection defense (that's a separate concern; this is about
  governing the effects regardless of how they were triggered)

---

## Threat Model Summary

The attacker's goal: trigger a governed effect (exfiltration, mutation,
credential access) through a channel that governance doesn't monitor.

The defense: there are no unmonitored channels. If it produces an effect,
it's governed. The channel is irrelevant.

```
Attacker: "But it's just markdown."
Governor: "It made a network request. That's egress. Show me the receipt."
```

---

## References

- EchoLeak (CVE-2025-32711): zero-click Copilot exfiltration via email
- LangGrinch (CVE-2025-68664/68665): serialization injection
- LangChain SSRF (CVE-2026-26013): token counter side effect
- LangChain crawler escape (CVE-2026-26019): RAG domain bypass
- Copilot Reprompt (Jan 2026): URL parameter prompt execution
- CodeGPT prompt injection: markdown image exfiltration
- OpenAI Atlas: CSRF memory poisoning
- Trail of Bits (Oct 2025): argument injection in approved commands
- MCP DNS rebinding (CVE-2025-66416): localhost tool exposure
