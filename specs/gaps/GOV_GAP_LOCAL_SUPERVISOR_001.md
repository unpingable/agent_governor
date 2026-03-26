# GOV_GAP_LOCAL_SUPERVISOR_001

## Title
Local LLM Supervisor in Maude (Cheap Cognition Layer)

## Status
Gap spec (no code yet)

## Problem Statement

The current supervised session workflow requires the operator to manually approve every write tool call, review every promotion diff, and interpret every denial. This works but doesn't scale — the operator IS the reasoning layer in the loop.

The actual usage pattern: James tells Claude Code (via this session) to drive another Claude Code session through the governor. One expensive model supervising another expensive model, with a human as the routing layer between them.

A small local LLM sitting in Maude can automate the boring parts of supervision: classify tool requests, summarize diffs, draft approval rationales, and flag only the things that actually need human eyes. The expensive model does real work. The cheap model watches. The governor enforces. The operator gets escalations, not a firehose.

## Architecture

```
Operator (human)
    ↑ escalations only
    |
Maude + Local LLM (cheap supervisor)
    ↑ proposals, summaries, classifications
    |
Governor (enforcement boundary)
    ↑ receipts, verdicts
    |
Claude Code / Codex / etc (expensive worker)
```

The local LLM is a **clerk**, not a judge. It proposes. Governor decides. The operator confirms when needed.

### Trust Boundaries

- **Worker model**: untrusted (NLAI applies)
- **Governor**: trusted enforcement (receipts, invariants)
- **Local supervisor model**: semi-trusted — can propose, classify, summarize. Cannot mutate state, override policy, or bypass gates.
- **Operator**: final authority for anything the supervisor can't handle

The local model emits **proposals**, not decisions. Governor still says yes/no.

## What the Local Supervisor Does

### Phase 0: Classification and Summarization

Minimal useful slice. No auto-approval.

- **Tool request classification**: label each intervention as `low / medium / high` risk
  - `low`: read-only tools, safe bash commands (ls, cat, grep)
  - `medium`: file edits in governed scope, test runs
  - `high`: bash with side effects, network, git mutations, out-of-scope writes
- **Diff summarization**: before promotion review, produce a one-paragraph summary of what changed and why
- **Denial explanation**: when governor or operator denies, explain in natural language what happened and what the agent should do instead
- **Session state compression**: reduce noisy event streams to "what matters right now"

The operator still approves everything. The local model just makes the decisions faster by pre-digesting information.

### Phase 1: Auto-Approve Low Risk

Once classification is trusted:

- Auto-approve `low` risk tool calls without operator confirmation
- Auto-approve read-only promotions (no file changes, just reads)
- Still escalate `medium` and `high` to operator
- Still escalate anything the classifier is uncertain about

Governor receipts record whether approval was operator or supervisor, with the classifier's reasoning.

### Phase 2: Session Management

- Preflight commands: "this looks destructive" / "this is read-only"
- Suggest promotion candidates from workspace changes
- Manage session lifecycle (pause on anomaly, resume on operator confirmation)
- "Why was this blocked?" natural-language explanations from receipt data

## Model Requirements

The local model needs to be:

- **Small**: 7B-14B parameter range. Qwen, Llama, Phi.
- **Fast**: classification and summarization, not generation-heavy tasks.
- **Conservative**: the right default is "I'm not sure, ask the operator." Uncertainty = escalate.
- **Local**: no API credits burned on supervision. This is the whole point.
- **Deterministic-ish**: same tool request should get the same risk classification. Temperature 0 or near-0.

It does NOT need to:
- Write code
- Understand complex architectures
- Have large context windows
- Be "smart" in general

"Should I approve `bash: rm -rf /`?" is an easy problem. "Should I approve `bash: pytest tests/ -v`?" is also easy. The hard cases get escalated.

## Integration with Existing Modules

| Module | How the supervisor uses it |
|--------|--------------------------|
| `supervisor.py` | Reads interventions, submits approve/deny/escalate |
| `promotion.py` | Reads pending promotion, summarizes diff |
| `budget.py` | Reads spend status, flags budget pressure |
| `events.py` | Reads event stream for session state |
| Maude `app.py` | Renders supervisor summaries, shows classifications |

New module: `src/governor/runtime/local_supervisor.py`
- `classify_tool_request(tool_name, tool_input) -> RiskLevel`
- `summarize_diff(diff_text) -> str`
- `explain_denial(event) -> str`
- `should_escalate(intervention) -> bool`

Backend: Ollama API (already available, `localhost:11434`).

## What It Should NOT Do

- **Override governor verdicts.** Governor says no, it's no.
- **Mutate state directly.** Everything goes through governor gates.
- **Approve high-risk actions autonomously.** Operator decides.
- **Accumulate authority over time.** No "the model learned to trust this pattern" drift.
- **Interpret policy.** Policy is deterministic rules. The model classifies inputs, not rules.

## Receipt Changes

Intervention resolution gains:

```python
@dataclass
class InterventionResolution:
    decision: str  # approve | deny | escalate
    decided_by: str  # operator | local_supervisor | policy | timeout
    risk_classification: str | None  # low | medium | high
    supervisor_rationale: str | None  # one-line explanation
```

This makes the audit trail show who decided and why — human, local model, or automatic policy.

## Economics

| Layer | Model | Cost | Purpose |
|-------|-------|------|---------|
| Worker | Claude Opus / Sonnet (API) | $$$ | Actual coding work |
| Supervisor | Qwen 7B / Llama 8B (local) | ~$0 | Classification, summarization |
| Governor | Deterministic code | $0 | Enforcement, receipts |

The expensive model does expensive work. The cheap model does cheap work. Nobody pays API rates for "is this bash command dangerous?"

## Phase Plan

### Phase 0: Classify + Summarize (no auto-approve)

- Wire Ollama into Maude for tool classification
- Show risk labels in intervention display
- Summarize promotion diffs before operator review
- Operator still approves everything

### Phase 1: Auto-Approve Low Risk

- Auto-approve low-risk tool calls
- Receipts record supervisor decisions with rationale
- Escalation for medium/high/uncertain
- Operator can tighten/loosen classification thresholds

### Phase 2: Session Intelligence

- Session state compression
- Anomaly detection (flag weird tool patterns)
- "Why blocked?" explanations
- Preflight risk assessment before launch

## Open Questions

1. **Which local model?** Qwen 7B is fast and good at classification. Llama 8B is more general. Phi is smaller but may miss edge cases. Probably: start with whatever Ollama has cached locally.

2. **Classification prompt design.** The prompt needs to be tight — tool name + input → risk level. No room for the model to philosophize. Few-shot with examples of each risk level.

3. **Escalation threshold.** How uncertain does the classifier need to be before escalating? Probably: any classification confidence below 0.8 → escalate. But "confidence" from a local model is not well-calibrated.

4. **Latency budget.** Classification needs to be faster than the intervention timeout. If the local model takes 5 seconds to classify and the timeout is 10 seconds, that's too tight. Target: <1 second for classification.
