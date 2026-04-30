# GOV_GAP_LLM_PROVIDER_EGRESS_001

## Title
Hosted LLM provider calls are unevaluated egress: wire chat_bridge.py through EgressGate before any new provider is added.

## Status
Gap spec — 3.x (coverage extension to GOV_GAP_EGRESS_001, which is shipped).

## Origin

Filed 2026-04-28 during deliberation about adding DeepSeek as a fifth `chat_bridge.py` backend. The proposal triggered a check of provider-standing primitives, which surfaced the actual finding: **the existing four backends (Anthropic, ClaudeCode, Codex, Ollama) already include three hosted services that send full payloads externally with zero egress evaluation.**

DeepSeek is not the trigger. It is the dye packet that made an existing-but-invisible substrate failure visible.

## Problem Statement

`src/governor/egress_gate.py` was wired into daemon tool dispatch (per GOV_GAP_EGRESS_001 §"Implementation Sketch") for network-capable tools. It was **not** wired into `src/governor/chat_bridge.py`.

Concrete witness — `AnthropicBackend.chat()` at `chat_bridge.py:345-350`:

```python
async with httpx.AsyncClient(timeout=120.0) as client:
    response = await client.post(
        "https://api.anthropic.com/v1/messages",
        json=payload,
        headers=headers,
    )
```

`payload` here contains the full conversation, including any system prompt assembled by `GovernorHooks` (which can carry governor state, anchor lists, tone profiles, and other governance artifacts). It goes straight to `api.anthropic.com` without `EgressGate.evaluate()`.

The same pattern holds for `ClaudeCodeBackend` (subprocess to hosted CLI) and `CodexBackend` (subprocess to hosted CLI). Only `OllamaBackend` (localhost by default) is incidentally egress-clean.

**The category called "backend" is secretly also "external data processor."** The governor currently treats these as interchangeable reasoning providers when at least three of them are in fact outbound data paths to third-party processors with their own retention, training, and jurisdictional policies.

This is a substrate boundary gap, not a provider-addition gap.

## Non-goals

- **Not a new EgressGate.** Reuse the existing `EgressGate.evaluate(EgressRequest)` from `egress_gate.py`. The gate is right; only the wiring is missing.
- **Not provider-standing config.** Per-backend "may recommend, may not authorize" semantics are downstream (a separate gap, likely `GOV_GAP_PROVIDER_STANDING_001`). This gap is one level below: making sure outbound calls *happen at all* is governed.
- **Not a DLP system.** Mechanical payload classification only — no ML, no content-aware classification beyond the secret patterns already in `receipt_kernel/redact.py`.
- **Not a refactor of `ChatBridge` Protocol.** The Protocol stays; egress evaluation slots in as a wrapper before each backend's `chat()`/`stream()` call.
- **Not a block on local backends.** Ollama-at-localhost should be classifiable as a non-egress destination (or `internal` egress class) and pass through with a lightweight receipt.

## Existing Governor Coverage

| Component | What exists | What's missing |
|-----------|-------------|----------------|
| `egress_gate.py` | `EgressGate.evaluate()`, `EgressRequest`, 6-rule precedence, monotone classifiers | Not invoked from `chat_bridge.py` |
| `chat_bridge.py` | 4 backends, ChatBridge dispatcher, GovernorHooks system-prompt assembly | No egress preflight; raw `httpx.post` to external destinations |
| `lanes.py` | `escalated: bool` on RoutePlan, escalation receipts on cascade | Escalation is logged, not gated on operator approval; doesn't currently treat provider-switch as an egress event |
| `gate_receipt.py` | Content-addressed receipts for any gate decision | No `gate="llm_egress"` receipts being emitted |
| `provenance_labels.py` | 7 source classes, 4 sensitivity hints, `max_sensitivity` propagation, evidence-gate annotation layer | Labels not consulted when assembling LLM payload; the prompt's data-class is currently unknown to the egress decision |
| `daemon.py` | EgressGate is constructed and used for tool dispatch | The chat path bypasses tool dispatch entirely |

## Acceptance Criteria

Closure of this gap means:

1. **Every non-local backend invocation** in `chat_bridge.py` (Anthropic, ClaudeCode, Codex, and any future hosted backend including DeepSeek) preflights through `EgressGate.evaluate()` before the outbound network call.
2. **The `EgressRequest` carries**:
   - `destination_class` derived from backend identity (hosted external vs. local vs. internal),
   - `destination_identity` = the actual API endpoint or CLI binary path,
   - `payload_class` derived from the assembled prompt's provenance labels (max-sensitivity propagation across system prompt + conversation history + governor-hook artifacts),
   - `provenance_refs` = receipt IDs / evidence hashes that justify sending this content to *this* backend,
   - `justification_code` = `"llm_inference"` or refinement thereof.
3. **Receipt emission**: `gate="llm_egress"` receipt per call, including backend identity, destination hash, payload class, verdict, and (if escalated) the operator-approval evidence.
4. **Local backends pass through cleanly**: Ollama-at-localhost evaluates as `destination_class=internal` (or a dedicated `local`) and gets a lightweight receipt, not a deny.
5. **Fail-closed default**: a backend whose destination cannot be classified is denied. New backends must declare their destination class to be addable.
6. **No silent fallback across egress classes**: if a cascade in `lanes.py` would escalate from a local backend to a hosted one, the existing `escalated` receipt is augmented with a fresh egress evaluation. Cross-class escalation may require operator approval depending on payload class.
7. **Tests**:
   - Anthropic call with default payload → ALLOW + receipt
   - Anthropic call with secret-pattern payload → DENY
   - Ollama call → ALLOW + lightweight receipt, classified as local
   - Cascade from Ollama → Anthropic with sensitive payload → ESCALATE / require approval
   - New unregistered backend with unknown destination → DENY (fail-closed)
   - Receipt schema-valid for `gate="llm_egress"`

## Doctrine

Two keeper lines, both load-bearing for downstream artifacts:

> **A hosted LLM backend is not merely a reasoning provider. It is an outbound data path. Any prompt sent to it is egress and must be evaluated before transmission.**

> **Model selection must not bypass egress standing. A provider may contribute testimony only after the system has determined that the testimony request itself is admissible.**

The first line is the substrate claim. The second is the procedural rule that follows.

## Relationship to Other Gaps / Specs

- **GOV_GAP_EGRESS_001 (shipped)**: This gap is its coverage extension. The egress gate itself is correct; this is wiring.
- **GOV_GAP_CHAIN_001 (chain gate)**: Composition-aware. Catches `read_secret → llm_call_external` as a denied composition. Both should fire.
- **Future GOV_GAP_PROVIDER_STANDING_001**: Per-provider standing config (observe/recommend/authorize denial). Sits *above* this gap. Requires this gap to be closed first, since "may not authorize" is meaningless if outbound transmission isn't first governed.
- **`scope_governor`**: Constrains *where* agents act. Egress gate constrains *what leaves*. Provider-standing will constrain *whose testimony counts for what*. Three orthogonal axes.
- **`provenance_labels`**: Already has the source-class / sensitivity-hint primitives needed for `payload_class` derivation. Currently not consulted at the chat-bridge boundary; this gap closes that.

## Implementation Sketch

1. Define `BackendDestinationProfile` (or similar) — a frozen registry mapping backend identity to `destination_class` + `destination_identity`. New backends must register before being usable.
2. Wrap `ChatBridge.send()` (or each backend's `chat()`/`stream()`) with an egress preflight: assemble `EgressRequest` from the outgoing payload's provenance labels + the backend's destination profile, call `EgressGate.evaluate()`, branch on verdict.
3. Emit `gate="llm_egress"` receipts via the existing gate_receipt machinery.
4. Wire `lanes.py` cascade escalation to re-evaluate egress when crossing destination classes.
5. Update `webui.md` and `chat_bridge.py` docs to reflect that backend addition now requires a destination profile.
6. Update the modular rules / CLAUDE.md to surface the doctrine: hosted LLM = egress.

## Open Questions

1. **Where does payload-class derivation actually happen?** The conversation history may contain content from many provenance sources. Does `max_sensitivity` propagation across the assembled prompt give a sufficiently sharp class, or does the assembly itself need to be governed? (Likely the latter, but starts mechanical.)
2. **Should governor state in the system prompt have its own provenance label?** GovernorHooks injects anchors, tone profiles, scope information. These are arguably `internal` sensitivity. Currently unlabeled.
3. **How does this interact with WebUI Backend Toggle?** Switching backends in the sidebar is currently free. Should it require an egress-policy reload? (Probably yes, but trivial: each call evaluates fresh.)
4. **Is "local" a destination class, or a sensitivity-hint absence?** Ollama-at-localhost is mechanically local; Ollama-against-a-remote-host is not. Destination identity must drive class, not backend name.
5. **What is the right response to `DENY` mid-conversation?** A user sending a secret-bearing prompt to a hosted backend gets blocked — is the right UX a violation-resolver fix/revise/proceed, or a hard refusal?
6. **Is DeepSeek-now-blocked still useful as a forcing function for closing this gap, or should the gap be closed independent of any provider-add request?** (Recommendation: close independently. Otherwise the lesson reads as "DeepSeek caused us to improve egress" — wrong attribution. The correct lesson is "DeepSeek made us notice that egress was already broken.")

## Provenance

This gap originated in a 2026-04-28 conversation about whether to add DeepSeek as a `chat_bridge.py` backend. The mechanical grep on `chat_bridge.py` found zero `EgressGate` references; the read of `AnthropicBackend.chat()` confirmed direct external `httpx.post`. Substrate-boundary framing surfaced through the dialogue. Filing this as a gap *before* any provider-add work is the load-bearing move — it preserves the correct attribution chain (gap exists independent of any provider) and makes provider-standing the natural next gap rather than a tangle.
