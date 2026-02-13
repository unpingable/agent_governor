# Detector Handoff Contract

## Version 1.0 — Local Model Arbitrage via Gate Receipts

```yaml
status: draft
depends_on:
  - DETECTOR_INTEGRATION_SPEC.md
  - gate_receipt.py (receipt_v1)
  - ../../../detector/scripts/controller.py
blocking: nothing (contract must be agreed before implementation)
```

### Companion to: DETECTOR_INTEGRATION_SPEC.md

---

## Executive Summary

The Δt detector's 3-way controller makes per-prompt decisions about local model
output: accept, retry, or stop. The governor needs those decisions as gate
verdicts with evidence — not as a parallel receipt system.

This spec defines the **handoff contract**: the exact JSON shape that the
detector emits, and how the governor maps it to a standard `GateReceipt`.

**One receipt system.** The detector produces a `controller_decision.json` file.
The governor reads it, maps `final_status` to a verdict, and emits a normal
`GateReceipt` with the decision as the evidence bundle. No new receipt schema.
No parallel storage. No integrity wrapper (the governor's content-addressed
`receipt_id` *is* the integrity guarantee).

---

## 1. The Boundary (unchanged from DETECTOR_INTEGRATION_SPEC)

```
┌──────────────┐   controller_decision.json   ┌──────────────┐
│   Detector   │ ─────────────────────────────→│   Governor   │
│ (controller) │   file artifact               │    (gate)    │
└──────────────┘                               └──────────────┘
```

No imports. No RPC. No shared process. The file is the API.

---

## 2. Detector Output: `controller_decision.json`

The detector's controller emits one JSON file per prompt/task. This is the
**only** artifact the governor needs for handoff decisions. The existing
`signal.json` (19-D raw signal) remains available for dashboards and deep
audit but is **not required** for handoff.

### 2.1 Schema

```json
{
  "schema": "controller_decision/v1",

  "task": {
    "task_id": "string",
    "task_class": "citation | codegen | qa | ...",
    "namespace": "pypi | cve | doi | rfc | code | ...",
    "prompt_hash": "sha256 hex (64 chars)",
    "output_hash": "sha256 hex of the local model's actual output (64 chars)",
    "request_nonce": "governor-generated nonce for freshness binding",
    "oracle_profile": "pypi_locked | cve_locked | code_standard | ..."
  },

  "local_model": {
    "model_id": "Qwen/Qwen2.5-3B-Instruct",
    "quant": "none | 4bit | 8bit",
    "decoding": {
      "temperature": 0.7,
      "retry_temperature": 0.0,
      "seed": 42
    },
    "controller_version": "1.0"
  },

  "decision": {
    "fork_risk": {
      "metric": "prompt_min_margin",
      "value_milliunits": 30,
      "window_k": 16
    },
    "tau_milliunits": 50,
    "controller_action": "FAST_PATH | LOW_MARGIN_RETRY | GROUND | STOP",
    "final_status": "CLEAN | LOW_MARGIN_RECOVERED | CONFIDENT_WRONG | KNOWLEDGE_BOUNDARY | ORACLE_ERROR",
    "decision_ttl_ms": 30000,
    "handoff_recommendation": "NONE | GROUND | ESCALATE_MODEL | ESCALATE_REMOTE | HUMAN_REQUIRED"
  },

  "evidence": {
    "candidates": ["pypi:requests==2.31.0", "pypi:flask==3.0.0"],
    "oracle_checks": [
      {
        "oracle": "pypi_json_api",
        "query": "requests==2.31.0",
        "result": "PASS",
        "latency_ms": 142
      }
    ],
    "failures": [
      {
        "kind": "oracle_fail",
        "message": "pypi:flask==3.0.0 does not exist",
        "attempt": 1
      }
    ],
    "controller_trace_ref": "data/runs/controller_tau0.05_2026-02-12/controller_details.jsonl"
  },

  "economics": {
    "local_tokens_spent": 312,
    "retry_tokens_spent": 0,
    "retry_count": 0,
    "latency_ms": 1840,
    "oracle_latency_ms": 142
  },

  "created_at": "2026-02-12T12:33:00Z"
}
```

### 2.2 Code Variant

For codegen tasks, the same schema applies with code-specific oracles:

```json
{
  "task": {
    "task_class": "codegen",
    "namespace": "code"
  },
  "evidence": {
    "candidates": ["def process_batch(items: list[Item]) -> BatchResult:"],
    "oracle_checks": [
      {"oracle": "ruff", "query": "patch.py", "result": "PASS", "latency_ms": 80},
      {"oracle": "mypy", "query": "patch.py", "result": "FAIL", "latency_ms": 340, "failure_kind": "typecheck", "error": "Incompatible return type"},
      {"oracle": "pytest", "query": "tests/test_batch.py", "result": "PASS", "latency_ms": 1200}
    ],
    "failures": [
      {"kind": "typecheck_fail", "message": "Incompatible return type \"None\", expected \"BatchResult\"", "attempt": 1}
    ]
  }
}
```

The oracle chain for code is: `ruff` → `mypy`/`pyright` → `pytest` → (optional: build).
First failure stops the chain and becomes the evidence.

### 2.3 Economics Fields

Every decision carries token accounting so the governor can compute cost
surfaces per namespace, task class, and model tier.

| Field | What it measures |
|---|---|
| `local_tokens_spent` | Tokens consumed by the local model (all attempts) |
| `retry_tokens_spent` | Tokens consumed by retry attempts only (0 if fast path) |
| `retry_count` | Number of retries (0 = first attempt accepted or blocked) |
| `latency_ms` | Wall-clock time for the full decision (generation + oracles) |
| `oracle_latency_ms` | Time spent in oracle checks only |

Note: `escalation_tokens_spent` is intentionally omitted. The detector can't
know this at handoff time — the remote model hasn't run yet. Remote token
spend is tracked by the remote model's own receipt.

These enable:
- **Savings ratio**: `1 - (remote_tokens_arbitraged / remote_tokens_naive)`
- **Cost per CLEAN outcome** by namespace
- **Marginal cost of τ reduction** (what does tightening τ by 0.01 cost?)
- **Adaptive τ**: if remote budget is tight, raise τ (ground locally more);
  if budget is flush, lower τ (escalate earlier)

Break down by namespace. You'll likely see:
- PyPI-like tasks → massive savings (local model knows this)
- CVE-like tasks → moderate savings (some escalations)
- DOI-like tasks → possibly negative savings (ground early or don't bother)

Track latency separately from tokens. You might save 70% of tokens but add
300ms median latency. That's a real decision surface, not a single number.

### 2.4 Field Semantics and Constraints

**`controller_action` vs `final_status`**: These are distinct enums. `controller_action`
is what the controller *did* (a verb: FAST_PATH, LOW_MARGIN_RETRY, GROUND, STOP).
`final_status` is the *outcome* after all attempts (a noun: CLEAN, CONFIDENT_WRONG, etc.).
`CONFIDENT_WRONG` appears only in `final_status`, never in `controller_action` — it's
a diagnosis, not an action.

**STOP invariant**: `controller_action=STOP` means "halt local attempt." It MUST NOT
appear with `final_status=CLEAN`. Valid `final_status` values when action is STOP:
`CONFIDENT_WRONG`, `KNOWLEDGE_BOUNDARY`, `ORACLE_ERROR`. Governor rejects the
decision file if this invariant is violated (schema validation error, not a verdict).

**Float canonicalization**: All float values in the schema are represented as integer
milliunits to ensure deterministic hashing. `fork_risk.value_milliunits: 30` means
0.030. `tau_milliunits: 50` means 0.050. The canonical JSON uses these integer fields
directly. No floating-point values appear in hashable fields.

Rounding convention: `milliunits = round(value * 1000)` (round-half-to-even, Python
default). Truncation is not used — it would systematically bias τ downward.

Note: `local_model.decoding.temperature` and `retry_temperature` remain raw floats.
These are metadata (not hashed), so canonicalization is not required.

**Oracle result enum**: `oracle_checks[].result` is one of `PASS | FAIL | ERROR`.
`PASS` = assertion holds. `FAIL` = assertion violated (the oracle worked but the
output is wrong). `ERROR` = oracle itself failed to execute.

`failure_kind` on `FAIL` entries is a closed enum (not freeform):
`NOT_FOUND | MALFORMED | VERSION_MISMATCH | TYPECHECK | LINT | TEST_FAIL`.
Extend the enum explicitly when new failure modes are discovered.

`error_kind` on `ERROR` entries is a closed enum:
`TIMEOUT | NETWORK | RATE_LIMIT | BINARY_MISSING | PARSE`.
`ERROR` entries also include a freeform `error` message for diagnostics.

**Replay/substitution protection**: `request_nonce` is a governor-generated opaque
string passed to the controller before generation. It binds the decision to a specific
governor request — a stale decision file can't be replayed. `output_hash` is the
SHA-256 of the local model's actual output bytes. The governor verifies it matches
the output before accepting a `CLEAN` verdict — a decision can't be grafted onto
different output. `decision_ttl_ms` is the maximum age of a decision file the
governor will accept (default: 30000ms). Expired decisions are treated as
`ORACLE_ERROR` → `"block"`.

**Clock source**: TTL is evaluated against **governor time**, not detector time.
The governor stamps `received_at` on ingest and checks:
`(now - received_at) <= decision_ttl_ms` AND `created_at` is not in the future
(with 5s tolerance for clock skew). Detector clock skew cannot extend the TTL window.

**`oracle_profile`**: Machine-readable identifier for the oracle chain used (e.g.,
`"pypi_locked"`, `"code_standard"`, `"cve_locked"`). The governor can enforce that
specific task classes use specific oracle profiles.

v1 semantics: **exact match only**. Remote model must use the same `oracle_profile`
as the local model. Partial-order ("stricter superset") is deferred to v2 — it
requires formalizing oracle containment, which we don't need yet.

**ORACLE_ERROR semantics**: Default verdict is `"block"` (fail-closed). Override to
`"warn"` is scoped per task class (not per gate instance, not global). The governor
maintains a low-risk allowlist of task classes that may use the override:
`gate_config.oracle_error_override_classes: ["qa", ...]`. A task class not in the
list gets `"block"` regardless. The governor logs the override decision in the
evidence bundle. No global "ignore oracle failures" switch exists.

### 2.5 What Is NOT in This File

- Raw logits or token streams (too large, not needed for decisions)
- Full prompts (hash is sufficient; prompt lives in trace)
- Per-token margins (pointer via `controller_trace_ref` for deep audit)
- Governor-side verdict (that's the receipt's job)

---

## 3. Governor Mapping: Decision → Gate Receipt

The governor reads `controller_decision.json` and calls
`GateReceiptSystem.emit()` with the existing interface. No new types.

### 3.1 Verdict Mapping

| `final_status` | Governor `verdict` | Semantics |
|---|---|---|
| `CLEAN` | `"pass"` | Accept local output |
| `LOW_MARGIN_RECOVERED` | `"pass"` | Accept (slow path taken, annotated) |
| `CONFIDENT_WRONG` | `"block"` | Reject; escalation required |
| `KNOWLEDGE_BOUNDARY` | `"block"` | Reject; local model can't solve this |
| `ORACLE_ERROR` | `"block"` | Can't verify; default fail-closed (low-risk tasks may override to `"warn"` via gate_config) |

`"block"` means the governor will not allow the local output to be acted upon.
Escalation is a separate decision (see Section 4).

### 3.2 Gate Call Shape

```python
receipt_system.emit(
    gate="detector_handoff",
    verdict=verdict,                       # mapped from final_status
    subject_kind="controller_decision",
    subject_bytes=canonical_json(decision_file),  # entire file
    evidence_bundle={
        # FROM decision.evidence:
        "candidates": [...],
        "oracle_checks": [...],
        "failures": [...],
        "controller_trace_ref": "...",
        # FROM decision.decision:
        "fork_risk": {"metric": "...", "value_milliunits": 30, "window_k": 16},
        "tau_milliunits": 50,
        "controller_action": "LOW_MARGIN_RETRY",
        "final_status": "CONFIDENT_WRONG",
        "handoff_recommendation": "ESCALATE_REMOTE",
        # FROM decision.economics:
        "local_tokens_spent": 312,
        "retry_tokens_spent": 0,
        "retry_count": 0,
        "latency_ms": 1840,
    },
    gate_config={
        "gate": "detector_handoff",
        "schema": "controller_decision/v1",
        "model_id": "Qwen/Qwen2.5-3B-Instruct",
        "task_class": "citation",
        "namespace": "pypi",
        "enforcement": "gated",             # not posthoc
    },
)
```

This is an ordinary `GateReceipt`. The `receipt_id` is content-addressed from
`gate + subject_hash + evidence_hash + policy_hash`. The `timestamp` is
ordering metadata. No new receipt schema needed.

### 3.3 Subject Hashing

The `subject_bytes` is the canonical JSON of the entire
`controller_decision.json` file. The `subject_kind` is
`"controller_decision"`. This means:

- Same decision + same evidence + same policy = same receipt_id
- Different timestamp does not change the receipt_id
- The receipt is deduplicated if the same decision is processed twice

---

## 4. Escalation Protocol

When the verdict is `"block"`, the governor produces an **escalation bundle**:
the evidence from the handoff receipt, packaged for a remote/larger model.

### 4.1 Escalation Bundle Shape

```python
escalation = {
    "reason": final_status,                    # "CONFIDENT_WRONG" or "KNOWLEDGE_BOUNDARY"
    "handoff_recommendation": "ESCALATE_REMOTE",
    "receipt_id": receipt.receipt_id,           # link back to gate receipt

    # Task context
    "task_id": decision["task"]["task_id"],
    "task_class": decision["task"]["task_class"],
    "namespace": decision["task"]["namespace"],
    "prompt_hash": decision["task"]["prompt_hash"],

    # What was tried
    "local_model": decision["local_model"],
    "candidates": decision["evidence"]["candidates"],

    # Why it failed
    "oracle_checks": decision["evidence"]["oracle_checks"],
    "failures": decision["evidence"]["failures"],
}
```

The remote model receives the diagnosis, not just the task. This prevents:
- Blind retries without evidence
- Model laundering (flaky local → confident remote without provenance)
- Silent upgrades that lose the failure trail

### 4.2 Remote Model Constraints

The remote model must either:
- Produce oracle-confirmed output (same oracle chain, verified)
- Explicitly return "no valid output found"

No silent paraphrasing of local output. No accepting local candidates without
re-verification. The escalation bundle makes this enforceable because the
governor knows what was already tried.

### 4.3 Anti-Laundering

The handoff contract prevents **model laundering** — the pattern where:
1. A flaky local model produces junk
2. A remote model paraphrases it confidently
3. You lose provenance

With receipts + oracle failures in the escalation bundle, the governor can
enforce: the remote model's output must pass the same oracle chain that the
local model failed. If the remote model can't produce oracle-confirmed
output, it must say so explicitly. No silent upgrades.

This also prevents the reverse: a remote model's output being demoted to
"local-quality" by stripping its provenance. Every receipt carries the
model tier and the oracle results that justified the verdict.

---

## 5. Code-Specific Extensions

### 5.1 Precision Span Detection (Code "Identifier Windows")

Same concept as namespace identifier windows, applied to code:

| Span Type | Pattern | Risk if Wrong |
|---|---|---|
| Import paths | `import x from "y"` | Module resolution failure |
| Symbol names | `obj.method()`, `cls.attr` | AttributeError, NameError |
| CLI invocations | `subprocess.run(["cmd", ...])` | Silent wrong behavior |
| Config keys | `config["key"]`, YAML keys | KeyError, wrong config |
| SQL fragments | `SELECT col FROM table` | Query failure, wrong data |
| Regex literals | `re.compile(r"...")` | Silent wrong matches |
| Type annotations | `-> ReturnType` | Typecheck failure |
| Test expectations | `assert x == "expected"` | False pass/fail |

Fork risk in these spans triggers grounding (query the repo instead of
generating).

### 5.2 Code Oracle Chain

```
oracle_chain = [
    ("ruff",    "lint + format check"),
    ("mypy",    "type check"),
    ("pytest",  "unit tests for changed files"),
    ("build",   "optional: compilation / bundling"),
]
```

First failure stops the chain. The failing oracle's output becomes the
evidence.

### 5.3 Repo-Derived Symbol Oracle

For `GROUND` action on code:
- Parse AST or ripgrep + tokenize to build a per-file symbol allowlist
- Constrain the model to observed identifiers
- If model emits an unknown symbol and margin is low → stop and ground

This is the code analogue of "oracle-confirmed candidates." The symbol
allowlist is a per-repo artifact, regenerated on demand.

### 5.4 Patch Volatility as Secondary Fork Risk

For code, top-2 margin alone may not suffice. A secondary signal:
- Edit distance between retry outputs
- AST diff size between retries

High patch volatility + low margin = the model is guessing. This correlates
with the detector's `perturbation_sensitivity` dimension.

---

## 6. What the Governor Does NOT Do

- **Does not recompute fork_risk.** The detector/controller decides. The
  governor enforces. Re-deciding is how you get divergence bugs.
- **Does not import detector code.** File artifact only.
- **Does not store per-token data.** Evidence bundle has bounded fields +
  a pointer (`controller_trace_ref`) for deep audit.
- **Does not auto-escalate.** It blocks and produces an escalation bundle.
  The routing decision (which remote model, at what cost) is a separate
  concern.

---

## 7. Model Tiering and Adaptive τ

Once the handoff contract is in place, models become compute tiers:

| Tier | Example | Cost | Authority |
|---|---|---|---|
| 0 | Local 3B (Qwen 2.5 3B) | Cheap | Low — unstable on hard namespaces |
| 1 | Local 7B (Qwen 2.5 7B 4-bit) | Moderate | Medium — sharper margins, fewer knowledge boundaries |
| 2 | Remote (Claude, GPT) | Expensive | High — broader knowledge, better reasoning |

Fork risk + oracle outcomes give a principled routing signal:

- **Tier 0 sufficient**: fork_risk ≥ τ, oracles pass → stay local
- **Tier 0 → Tier 1**: fork_risk < τ, oracle inconclusive → try bigger local before going remote
- **Tier 0/1 → Tier 2**: CONFIDENT_WRONG or KNOWLEDGE_BOUNDARY → escalate with evidence
- **Tier 2 not needed**: task class historically succeeds at Tier 0 (e.g., RFC citations for Qwen)

### 7.1 Adaptive τ

τ can be dynamic based on cost budget:

```
if remote_budget.remaining > remote_budget.target * 0.5:
    tau = tau_conservative    # escalate more freely
else:
    tau = tau_aggressive      # ground locally, spend less on remote
```

The governor already has `ExplorationBudget` and `BoilController` for
this kind of adaptive scheduling. τ becomes another tunable parameter
in the homeostat.

### 7.2 Trigger Rate as Difficulty Classifier

The controller's trigger rate per namespace is a free "difficulty
classifier" for tasks:

- CVE triggers >> PyPI triggers → CVE is harder for this model
- DOI triggers are hostile → expect fabrications at Tier 0

The governor can learn these rates from receipts and pre-route:
- Choose model/decoding/controller *before* generating
- Or require grounding upfront for known-hard namespaces

---

## 8. Versioning

- `"controller_decision/v1"` — this spec
- Bump the `/v1` suffix on breaking changes to the file schema
- Governor should reject unknown schema versions (fail-closed)
- `controller_version` in `local_model` tracks the detector's controller
  logic version independently

---

## 9. Relationship to Existing Artifacts

| Artifact | Status | Relationship |
|---|---|---|
| `signal.json` (19-D raw) | Existing | Remains for dashboards. NOT required for handoff |
| `controller_decision.json` | **NEW** | This spec. The handoff artifact |
| `GateReceipt` | Existing | Governor wraps the decision as a standard receipt |
| `EvidenceStore` | Existing | Stores the evidence bundle (content-addressed) |
| `gate_receipts.jsonl` | Existing | Append-only log of all gate receipts |

No new storage infrastructure. No new receipt types. One new gate name
(`"detector_handoff"`), one new `subject_kind` (`"controller_decision"`).

---

## 10. Implementation Checklist (for planning phase)

### Detector side

- [ ] `controller.py` → emit `controller_decision.json` alongside existing outputs
- [ ] Map `run_prompt()` return to the v1 schema
- [ ] Use `controller_action` (FAST_PATH/LOW_MARGIN_RETRY/GROUND/STOP), not `policy`
- [ ] Use integer milliunits for `fork_risk.value_milliunits` and `tau_milliunits`
- [ ] Oracle results use `PASS | FAIL | ERROR` enum; `FAIL` includes `failure_kind`
- [ ] Accept `request_nonce` from governor, echo it in task section
- [ ] Compute `output_hash` (SHA-256 of local model output bytes)
- [ ] Set `oracle_profile` to identify the oracle chain used
- [ ] Include `decision_ttl_ms` (default 30000)
- [ ] Include economics fields (local_tokens_spent, retry_tokens_spent, retry_count, latency_ms, oracle_latency_ms)
- [ ] Include `controller_trace_ref` pointing to stored run

### Governor side

- [ ] `LocalModelGate` (or extend `DetectorIntegration`) that reads the file
- [ ] Schema validation (reject unknown schema versions — fail-closed)
- [ ] `final_status` → `verdict` mapping (Section 3.1), ORACLE_ERROR → block by default
- [ ] Nonce validation: verify `request_nonce` matches the one we issued
- [ ] Output hash validation: verify `output_hash` matches actual output before accepting CLEAN
- [ ] TTL validation: reject decisions older than `decision_ttl_ms`
- [ ] Oracle profile enforcement: verify task class uses expected oracle profile
- [ ] `GateReceiptSystem.emit()` call (Section 3.2)
- [ ] Escalation bundle builder (Section 4.1)
- [ ] `gate_config.oracle_error_override` for low-risk task allowlist
- [ ] CLI: `governor detector handoff <path>` (process a decision file)
- [ ] Tests: verdict mapping, evidence bundling, escalation shape, nonce/TTL/hash validation
- [ ] Cost surface queries: per-namespace, per-task-class, per-model breakdowns

### Code extensions (later)

- [ ] Precision span detectors (imports, defs, attr access, config keys)
- [ ] Code oracle chain (ruff → mypy → pytest)
- [ ] Repo symbol allowlist generator
- [ ] Patch volatility signal
- [ ] AST diff volatility as secondary fork-risk proxy
