# Artifact Binding Gap Analysis

## Receipts for Mutable Substrates

```yaml
status: gap
relates_to:
  - gate_receipt.py (GateReceipt, ReceiptStore, EvidenceStore)
  - evidence_gate.py (EvidenceGate, custody scoring)
  - regime.py (RegimeDetector, RegimeSignals)
  - interferometry.py (multi-model claim comparison)
  - chat_bridge.py (ChatBridge, backend abstraction)
  - PHASE_GATING_GAP.md (stage register, stage-gated invariants)
  - SELF_GOVERNANCE_SPEC.md (admissibility, quorum, dual ledger)
blocking: nothing
priority: v3
```

---

## The Shift

Governor v2 enforces behavior of a **fixed model**. The substrate (which model,
which tools, which retrieval corpus) is assumed mostly static. Receipts bind
policy to evidence to decisions.

Governor v3 must enforce invariants across a **changing substrate**. Models get
swapped. Tool endpoints get versioned. Retrieval corpora get re-indexed.
Routing configs change. The receipt primitive must evolve to bind decisions
to the specific substrate state that was present when the decision was made.

Without this, "same weights" can mask "different world."

---

## What Exists Today (v2)

`GateReceipt` has 8 fields:

```
receipt_id, schema_version, timestamp, gate, verdict,
subject_hash, evidence_hash, policy_hash
```

`subject_hash` includes a kind tag (`H(kind + \x00 + bytes)`) to prevent
cross-type collisions. `evidence_hash` and `policy_hash` bind the decision
to what was checked and what rules applied.

What's missing: **no binding to the substrate that produced the evidence.**
A receipt says "evidence_gate passed with this evidence under this policy"
but not "...while running model X with tool schema Y against corpus Z."

---

## What v3 Needs

### 1. Artifact Binding

Receipts must bind:

- **`model_artifact_id`** — hash of weights, model package, or explicit
  version string. Even if you don't mutate weights, you swap models
  (Ollama → Claude → Codex). Without this, you lose replayability.
- **`regime_hash`** — hash of the operational regime at decision time:
  tool endpoint versions + schemas, retrieval corpus snapshot digest,
  routing config. This is the "world under the model."
- **`evidence_digest`** — hash of eval manifest + results summary +
  dataset IDs. Already partially present as `evidence_hash`, but v3
  should make the eval provenance explicit.

These are additions to the receipt schema, not replacements. The existing
`subject_hash`, `evidence_hash`, `policy_hash` stay.

### 2. Substrate-Conditional Expiry (Guarantee TTL)

v2 has TTL enforcement for claims (`ttl.py`). v3 generalizes:

> A claim's validity is conditional on its substrate remaining unchanged.

If the substrate changes, cached guarantees auto-expire:

- Model version changes → invalidate receipts bound to old `model_artifact_id`
- Tool version changes → invalidate capability receipts bound to old tool schemas
- Retrieval corpus changes → invalidate truth claims bound to old corpus digest
- Routing config changes → invalidate routing decisions bound to old config

This is not time-based expiry. It's **substrate-change-triggered invalidation**.
The receipt's `regime_hash` is the binding — if current regime hash differs
from the receipt's regime hash, the receipt is stale.

This is philosophically consistent with existing architecture: claims decay
when their evidence substrate changes. v3 just makes "substrate" explicit
and hashable.

### 3. Admission Control

The governor should refuse execution if:

- `model_artifact_id` not in approved set
- `policy_hash` mismatch (policy was updated, receipt is stale)
- Receipt missing entirely
- Regime drift detected (current `regime_hash` ≠ receipt's `regime_hash`)

This is the "teeth" — the reference monitor says "no valid receipt, no
execution." It's the same pattern as the evidence gate, but applied to
the substrate itself.

Fail modes must be explicit and policy-controlled:

- **Fail closed** for high-risk actions (writes, external effects, money)
- **Degrade to read-only / no-tools / ask-user** for lower risk
- Not ad hoc — configured per action class

### 4. Renewal Loop

When a receipt expires (substrate change or time), the system needs:

- Ability to re-run evaluation on the new artifact
- Regenerate receipts against current substrate
- Promote only if new receipts are valid

This is a minimal promotion gate, not a CI/CD pipeline. The expensive part
is eval latency, which lives off the request path but sets the maximum
safe update rate.

### 5. Deterministic Replay Contract

Production incidents require reproducing the bad run. A receipt must bind
enough state to replay:

- `model_artifact_id`
- Tool schema versions (in `regime_hash`)
- Retrieval corpus digest (in `regime_hash`)
- `policy_hash`
- Prompt/template version
- Sampling params (or a `non_deterministic` flag if you can't)

If you can't replay, receipts are vibes with signatures.

### 6. Tamper-Evident Run Log

Receipts are only toothy if you can't rewrite history:

- Append-only log (hash chain) of: request → decision → evidence refs →
  tool calls → outputs → receipt_id
- Even if it starts as local SQLite + chained hashes
- Each entry includes hash of previous entry (Merkle-ish)

This connects to `SELF_GOVERNANCE_SPEC.md`'s requirement for no epistemic
laundering — the run log is the physical enforcement of that principle.

---

## Receipt Schema Evolution

### v2 (current)

```python
receipt_id          # H(schema_v + gate + subject_hash + evidence_hash + policy_hash)
schema_version      # "receipt_v1"
timestamp           # metadata, not identity
gate                # which gate produced this
verdict             # pass/warn/block
subject_hash        # H(kind + \x00 + subject_bytes)
evidence_hash       # H(canonical_json(evidence))
policy_hash         # H(canonical_json(policy))
```

### v3 (proposed additions)

```python
# Everything from v2, plus:
model_artifact_id   # hash of model weights/package/version
regime_hash         # H(tool_schemas + corpus_digest + routing_config)
evidence_digest     # H(eval_manifest + results_summary + dataset_ids)
valid_until         # explicit expiry (time-based)
substrate_valid     # bool: regime_hash still matches current regime
signer              # optional now, required when distributed trust needed
```

`receipt_id` computation would include the new fields. Schema version
bumps to `receipt_v2`.

---

## Canonical Identifiers (Lock In Early)

Even before building v3, define how these are computed:

| Identifier | What gets hashed | Notes |
|------------|-----------------|-------|
| `model_artifact_id` | Model weights or package manifest | For API models: provider + model_id + version string |
| `policy_hash` | Normalized policy bundle (canonical JSON) | Already exists in v2 |
| `regime_hash` | Tool schemas + endpoint versions + corpus snapshot + routing config | New |
| `evidence_digest` | Eval manifest + results summary + dataset IDs | Extends existing `evidence_hash` |

Hashing early avoids future migration pain. The identifiers are
deployment-shape-independent.

---

## What This Does NOT Do

1. **Build a model registry.** The governor tracks artifact IDs, it doesn't
   store or serve models.
2. **Handle weight updates / continual learning.** v3 supports swappable
   backends, not gradient descent.
3. **Become a CI/CD pipeline.** The renewal loop is a promotion gate, not
   a build system.
4. **Require distributed trust on day 1.** Signing is optional until the
   governor runs as a shared service.

---

## Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| `SELF_GOVERNANCE_SPEC.md` | Tamper-evident log + admission control are physical enforcement of no-laundering |
| `PHASE_GATING_GAP.md` | Stage advancement could require valid receipts for all active invariants |
| `EXPANDER_VERIFICATION_GAP.md` | Multiple verification paths, but each path produces artifact-bound receipts |
| `SCALAR_COLLAPSE_GAP.md` | Regime hash includes metric configuration — collapse detection is regime-aware |
