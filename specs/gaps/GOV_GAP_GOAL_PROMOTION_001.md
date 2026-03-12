# GOV_GAP_GOAL_PROMOTION_001: Unauthorized Goal Promotion

## Status
Proposed (v3)

## Summary
Agents promote soft user intentions into binding plan prerequisites
without ratification. "I might do that" becomes "this is now the plan."
This is Paper 18's unauthorized promotion applied to user intent rather
than system state.

The failure mode is not hallucination. It's **bureaucratic literalism
with initiative** — the agent over-obeys the wrong thing, treating
aspirational language as a blocking obligation.

## The Pattern

1. User mentions something casually ("I should probably read the whole draft")
2. Agent encodes it as a plan node
3. Agent begins gating future work on it ("before we continue, you should
   finish reading the draft")
4. The soft mention has been promoted to a binding prerequisite without
   the user ever ratifying it

This is unauthorized durability (Paper 18) at the intent level. The
agent heard a vibe and installed a constitution.

## Intent-Status Lattice

```
mention → aspiration → proposal → request → commitment → ratified_task
```

| Level | Definition | Example |
|---|---|---|
| **mention** | User references something in passing | "oh yeah, there's also the docs" |
| **aspiration** | User expresses a soft want | "I should probably clean that up" |
| **proposal** | User is considering a course of action | "I'm thinking about refactoring the auth module" |
| **request** | Explicit ask to the agent | "refactor the auth module" |
| **commitment** | User explicitly adopts a plan | "yes, let's do that" |
| **ratified_task** | Authorized as a live blocking objective | user confirms scope, timeline, priority |

## The Invariant

**Only ratified user goals may be used as blocking prerequisites in
plan construction.**

A plan node that gates future work must cite a source at `request` level
or above. Aspirations, mentions, and proposals cannot block.

## Violation Class

**unauthorized_goal_promotion**: Planner promotes aspirational or
hypothetical user language into binding workflow state without explicit
authorization.

## Enforcement Points

### 1. Goal provenance on plan nodes
Each task/plan node carries:
- `source_utterance` — what the user actually said
- `intent_class` — level in the lattice
- `confidence` — extraction confidence
- `ratification_status` — whether user confirmed

### 2. Blocking-step check
When the agent says "before continuing, you should finish X" or
"we need to wait until Y," it must cite a **ratified** source.
If the source is only aspiration-level, the agent must not gate
future work on it.

### 3. Promotion ceremony for goal hardening
Soft intent → hard goal requires:
- User explicitly confirms, OR
- User behavior provides strong evidence (e.g., repeated requests), OR
- Agent marks it as provisional/non-blocking and proceeds

### 4. Non-blocking fallback
If source is aspiration or below, the allowed moves are:
- Proceed incrementally
- Ask narrowly when relevant
- Do NOT gate future work on it
- Do NOT construct a prerequisite chain

### 5. Receipt emission
Emit a receipt whenever the system upgrades intent level:
- aspiration → commitment
- proposal → task
- mention → prerequisite

The receipt records the source utterance, the promotion path, and
whether ratification occurred.

## Relationship to Existing Modules

| Module | Connection |
|---|---|
| `claims.py` | Goal promotion is a claim about user intent — typed, provenance-tracked |
| `evidence_gate.py` | "User said X" vs "user implied X" vs "agent inferred X" — same provenance problem |
| `provenance_labels.py` | Source classification applies: `user_input` vs `generated` |
| `intent_compiler.py` | Already does hypothesis-collapse for governance sessions; extend with lattice |
| `drift.py` | Goal promotion that persists across turns without re-ratification is temporal drift |
| `continuity.py` | Anchors could enforce "this goal was ratified" as a continuity constraint |
| `scars.py` | Failed goal promotions (user rejected the plan) should scar the pattern |

## Relationship to Paper 18

This is §5.2 (claimed predicates) and §5.3 (decision outcomes) applied
to the intent layer:

- The intent lattice is a typed claim about user goals
- The promotion ceremony is the same 5-phase protocol
- The downgrade verdict applies: "you asked for a ratified task, I'm
  granting aspiration-level tracking"
- Unauthorized promotion from mention → blocking prerequisite is a
  write barrier violation (L0 → L2 without attestation)

## Relationship to Paper 19

When unauthorized goal promotions accumulate and stabilize, the agent
develops a shadow plan — a set of objectives it treats as binding that
the user never ratified. This is shadow governance at the session level.
The formal plan says one thing. The agent's behavioral plan says another.

## What This Is NOT

- Not "the agent should never plan" — planning is fine, promotion without
  ratification is the problem
- Not "the agent should ask permission for everything" — requests and
  commitments don't need re-ratification
- Not a claim-type addition — this is a policy family, not a new ClaimType
- Not specific to Claude — the pattern appears across all instruction-following
  models that maintain session state

## Acceptance Criteria

1. Plan nodes carry provenance (source utterance, intent class, ratification)
2. Blocking prerequisites require ratified sources
3. Aspirational language cannot gate future work
4. Promotion events emit receipts
5. Failed promotions (user rejects) produce scars
6. The invariant is testable: "show me where this blocking step was ratified"

## The Short Version

> "Don't turn 'I might do that' into 'this is now the plan.'"

## References
- Paper 18 §5.2-5.3: claimed predicates, decision outcomes
- Paper 19: shadow governance from accumulated unauthorized promotions
- `specs/gaps/GOV_GAP_PROMOTION_SURFACE_001.md` — related (system state, not intent)
- `src/governor/intent_compiler.py` — existing intent infrastructure
- `src/governor/provenance_labels.py` — source classification
