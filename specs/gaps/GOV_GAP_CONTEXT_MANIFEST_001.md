# GOV_GAP_CONTEXT_MANIFEST_001 — Prompt as Governed Artifact

**Status:** Phase 1 shipped (v2.6.x). Phases 2–3 open.
**Track:** Context governance (v3 precursor)
**Depends on:** gate_receipt (shipped), provenance_labels (shipped), context_manifest (Phase 1 shipped)

---

## Problem

The governor governs tools, data flow, and claims — but the **prompt itself**
is ungoverned. Prompt assembly happens via string concatenation across 6+
sources with no record of what went in, why, or with what permissions.

Phase 1 instruments the build. Phases 2–3 constrain and bind it.

---

## Phase 1 — Observation (SHIPPED)

**What it does:** Build a manifest during prompt assembly, emit it as a side
artifact, make it inspectable via CLI. No enforcement, no gates.

**Artifacts:**
- `ContextRegion` — per-region metadata (kind, hash, sensitivity, mutability, capabilities)
- `ContextManifest` — three identity kinds: prompt_hash (content), manifest_hash (structure), build_id (event)
- `ManifestStore` — JSONL with fcntl.flock
- Gate receipt: `context_build` (verdict=observe), `context_build_failed` (verdict=warn)
- CLI: `governor context manifest [--json] [--limit N] [--id ID]`
- Golden determinism tests (pinned hashes)
- 49 tests

**Key design decisions:**
- `hash_only` default store mode everywhere — no bodies stored
- Fail-open but NOT silent — stderr warning + failure receipt
- Evidence never contains region bodies — hashes only
- `region_id != kind` — kind is category, region_id is stable identity (expandable to subregions)
- Reserved fields present but None: `message_set_hash`, `signature`, `signing_key_id`

---

## Phase 2 — Enforcement / Write Barriers (v3-adjacent)

**What it adds:** Treat prompt regions as capability-bearing objects. Enforce
`mutability` + `capabilities` on any operation that would change
prompt-affecting state.

**Why it's v3-ish:** Moves from tool governance to **context governance** — the
agent's actual operating environment. Becomes a prerequisite for "this service
will not rewrite protected policy / continuity anchors" guarantees.

### Key artifacts

- **`ContextMutationReceipt`** — attempted edit: allowed/denied + reason.
  Gate = `context_mutation`. Verdict = pass/block.

- **Consent tokens** — first-class inputs to mutation requests.
  Even if dumb at first (string + expiry), they establish the pattern.

- **Region capability enforcement:**
  - `frozen` regions: no mutation path exists (reject at proposal time)
  - `protected` regions: mutation requires explicit consent token
  - `mutable` regions: mutation allowed, receipted

- **Capability checks:**
  - `read`: always granted (Phase 1 default)
  - `write`: requires `mutable` or `protected` + consent
  - `append`: allowed for mutable regions (e.g., compaction summaries)

### Implementation sketch

```python
def propose_region_mutation(
    region_id: str,
    new_content: str,
    consent_token: str | None = None,
) -> ContextMutationReceipt:
    """Gate: can this region be changed?"""
```

### Practical heuristic

If it introduces **promises you can't break** ("we won't rewrite your policy
region without consent"), it's Phase 2.

### Estimated scope

- `context_manifest.py` additions (~150 lines)
- `chat_bridge.py` mutation path (~50 lines)
- Tests: ~30

---

## Phase 3 — Binding / Attestation / Service-Grade Storage (v3 proper)

**What it adds:** Optional body store, manifest signing, replayability.
This is where "as a service" starts: audit logs, nonrepudiation,
tenant boundaries, retention policies.

### Key artifacts

- **Body store** — encrypted, tenant-scoped, separate from receipts.
  Keyed by `(manifest_hash, region_id)`. Retention policy from receipt_kernel.

- **Signing** — manifests (or chains) signed with tenant/service key.
  `signing_key_id` + `signature` fields (already reserved in Phase 1).
  Proves "this manifest existed and wasn't tampered with."

- **Replayability** — given `(manifest_hash, region body refs)`, reconstruct
  what was run. Enables: "show me exactly what context was active when this
  output was generated."

- **Hash chaining** — `prev_manifest_hash` / `prev_build_id` (already wired
  in Phase 1) become tamper-evident logs across builds/sessions.

- **`content_ref` pointers** — object store IDs for bodies when body storage
  is enabled. Phase 1's `store_mode` field gates this:
  - `hash_only`: no body (default, Phase 1)
  - `full`: body stored in body store
  - `redacted`: body redacted before storage (secret-bearing regions)

- **`message_set_hash`** — H(full message list). Extends manifest from
  "what system prompt was used" to "what full context was active."

### Practical heuristic

If it introduces **promises you can sell** ("we can prove what context was
used", "audit trail survives tenant rotation"), it's Phase 3.

### Estimated scope

- `context_body_store.py` — NEW (~200 lines)
- `context_manifest.py` additions — signing, content_ref (~100 lines)
- receipt_kernel integration for retention
- Tests: ~50

### Dependencies

- Phase 2 (enforcement must exist before binding makes sense)
- receipt_kernel retention policy (shipped)
- Tenant/key management (not yet designed — v3 prerequisite)

---

## Non-goals

- **Phase 1 does not gate anything.** It's observe-only.
- **Phase 2 does not store bodies.** Enforcement is structural, not archival.
- **Phase 3 does not require all regions to be stored.** `hash_only` remains
  a valid (and default) store mode. Body storage is opt-in per region kind.

---

## Migration path

Each phase is additive:
- Phase 1 → Phase 2: add enforcement layer, existing manifests remain valid
- Phase 2 → Phase 3: add body store + signing, existing receipts remain valid
- `manifest_version` bumps only on breaking schema changes (not expected for Phase 2)

---

## Open questions

1. **Consent token shape:** JWT-like? Simple HMAC? Opaque string + expiry?
   Phase 2 can start with the dumbest thing that works.

2. **Body encryption:** Per-tenant key? Per-region? Envelope encryption?
   Phase 3 design decision, depends on v3 key management.

3. **Cross-session chaining:** Should manifest chains span sessions?
   Phase 1 chains within a session (GovernorHooks lifetime).
   Phase 3 might chain across sessions via session_continuity capsules.

4. **Message-set coverage:** `message_set_hash` covers the full message list.
   Should individual messages get region-like treatment?
   Probably Phase 3+ / v3 proper.
