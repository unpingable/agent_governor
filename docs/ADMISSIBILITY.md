# Admissibility, Not Correctness

This system does not prove an agent's actions were "correct" in the sense of guaranteeing good outcomes. It proves whether an action was **admissible** under declared rules, evidence, and risk constraints at the time it was taken.

That distinction is the whole point.

---

## Why outcomes are the wrong bar

In domains where decisions play out under uncertainty (finance, medicine, operations, creative work), outcomes are stochastic. A decision can be reasonable and still fail. If correctness were defined by outcome:

- Every losing trade is malpractice
- Every failed deployment is proof the checklist was wrong
- Every divergent chapter draft is evidence of incompetence

That's not how accountability works in any serious field.

## What admissibility means

> **Admissibility** = an action is permitted if it satisfies declared rules, evidence gates, and risk constraints at the time of commitment.

Given a gate receipt, the system can show:

1. **Authorization**: Was the agent allowed to take this class of action under an explicit policy?
2. **Constraints**: Did the action satisfy declared limits (concentration caps, risk budgets, required checks)?
3. **Evidence basis**: Which inputs were treated as admissible? What remained unresolved? Which gates were passed or waived?
4. **Decision lineage**: Proposed alternatives, rejected options, the exact commit point where irreversibility occurred.
5. **Waivers**: Any override was intentional, attributable, and durable. Overrides leave scars.

## What the system cannot prove

- That the market would not move against the position
- That the action would produce favorable outcomes
- That the agent's model of the world was "true"

Those are not governable properties. They are bounded (at best) by policy, process, and risk limits.

---

## How this changes the conversation

### Without receipts

Post-incident discourse is narrative:

- "The AI decided..."
- "Markets were unprecedented..."
- "Nobody could have known..."

### With receipts

Post-incident discourse is audit:

- Was this action admissible under the declared rules?
- If admissible, who authored the rules that permitted it?
- If inadmissible, where did enforcement fail?
- If a waiver enabled it, who explicitly accepted the risk?

This is not exculpation. It is **liability routing**: when outcomes are bad, we can determine whether the system violated its declared constraints, or whether a human explicitly chose to accept the risk.

---

## Worked example: the pension fund

Suppose a financial agent allocates 100% of a pension fund into a single volatile asset, and losses occur.

### The wrong question

> "Why did it buy Bitcoin?"

### The right questions

1. Was that allocation admissible under the fund's mandate and diversification constraints?
2. If admissible: who authored those constraints? (They're on the hook.)
3. If inadmissible: where did enforcement fail? (The system violated its own rules.)
4. If a waiver existed: who signed it? (They explicitly accepted liability.)
5. If no receipt exists: the deployment was negligent by definition.

### What actually gets constrained

You don't write rules like "don't buy Bitcoin." You write:

- **Concentration constraints**: No single asset may exceed X% of portfolio exposure without an explicit, attributed waiver.
- **Volatility constraints**: Expected volatility bounds, worst-case drawdown assumptions, liquidity stress scenarios.
- **Mandate constraints**: Allowed instrument classes, explicit exclusions, time horizon compatibility.
- **Irreversibility mechanics**: Anything outside the safe envelope requires a signed waiver. Waivers are durable, attributable, and visible in receipts.

Bitcoin then becomes irrelevant as a special case. If it violates concentration limits, it's inadmissible. If it doesn't, then someone explicitly chose to allow it, and that choice is recorded.

The goal is not to prevent bad decisions. The goal is to make bad decisions **explicit, attributable, and intentional**.

---

## Constraints, authority, and the role of AI

The system draws a hard boundary between suggestion, authority, and enforcement.

### AI may propose constraints

AI is useful for:

- Drafting candidate constraints from natural-language policies
- Translating mandates into formal rules
- Surfacing implicit assumptions ("you probably want a concentration cap here")
- Stress-testing constraints against historical or simulated scenarios

All such outputs are non-authoritative. They are proposals.

### Humans authorize constraints

A constraint becomes active only when:

- A human or accountable institution explicitly signs it
- The constraint is pinned (hash-addressed and versioned)
- Its scope and applicability are declared

This signature is the point where responsibility transfers and liability becomes legible.

AI does not sign constraints. This is intentional.

### Enforcement is mechanical

Once a constraint is active, enforcement is deterministic, non-interpretive, and non-discretionary. The governor does not reason about whether an action is wise. It checks whether the action is admissible under the signed constraints.

- **AI** = generative, fallible, advisory
- **Governor** = rigid, boring, enforceable

They are not interchangeable.

### Waivers are explicit

Actions outside the safe envelope require an explicit waiver. The waiver is signed, durable, and visible in receipts. Overrides leave scars. There is no silent bypass.

### After-action analysis

AI may be used post-incident to analyze constraint failures, detect patterns of waiver abuse, and propose revised constraints. These outputs are again advisory. New constraints require new signatures.

---

## Design principle

This system does not attempt to make agents "always right."

It ensures that when agents act, we can determine what rules were in force, what uncertainty remained, who accepted the risk, and whether the action was admissible at the time.

**Outcomes are stochastic. Constraints and accountability are not.**

---

## Related

- [COMPLIANCE.md](COMPLIANCE.md) -- How this maps to fiduciary law and regulatory standards
- [architecture/OVERVIEW.md](architecture/OVERVIEW.md) -- System architecture
