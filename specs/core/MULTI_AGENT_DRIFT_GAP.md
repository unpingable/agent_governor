# Gap Note: Multi-Agent Drift → Governance Receipts

**Date:** 2026-02-10
**Context:** arXiv:2602.08567 (ValueFlow) just dropped
**Status:** Background validation for governor work

---

## The Claim (from ValueFlow)

Multi-agent LLM coupling causes measurable value drift. Single-agent alignment evals don't generalize to networks.

Key findings:
- **β-susceptibility**: Agent sensitivity to perturbed peer signals (varies wildly)
- **System susceptibility (SS)**: How perturbations at one node infect final output
- **Topology determines drift**: Network structure matters more than individual "alignment"

Their conclusion: "Alignment" in isolation is meaningless once agents interact.

---

## What They Measured (Diagnostics)

| Metric | Meaning |
|--------|---------|
| β (beta) | How much an agent's output shifts when peers are perturbed |
| SS | End-to-end propagation of value perturbation through system |
| Value drift | Delta between pre/post interaction value scores (Schwartz basis) |

They used an LLM judge to score outputs against a 56-value survey. Recursive authority problem, but the structural insight holds.

---

## What's Missing (Control)

They diagnose drift. They don't stop it.

| They Have | They Don't Have |
|-----------|-----------------|
| Drift measurement | Admissibility gate |
| Susceptibility metrics | Pinned invariants |
| Topology analysis | "No act without proof" |
| Value scoring | External reference (y vs ŷ) |

In Δt terms: they're measuring the disease, not building the immune system.

---

## The Wedge: Receipts as Enforcement Boundary

The control surface they're missing:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent A   │────▶│    Gate     │────▶│   Action    │
│  (drifted)  │     │  (receipt)  │     │  (or not)   │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                    ┌─────┴─────┐
                    │ Invariant │
                    │  Check    │
                    └───────────┘
```

Drift can happen upstream. The gate doesn't care about the agent's internal state. It checks:
- Does this action satisfy pinned invariants?
- Is there admissible evidence?
- Does quorum approve?

If no → no action. Receipt records the refusal.

**Receipts are the enforcement boundary between generation and action.**

---

## What Governor Already Has (as of 2.0)

The "irreducible primitive" described below is already shipped:

```python
# src/governor/gate_receipt.py — SHIPPED
@dataclass
class GateReceipt:
    receipt_id: str          # Content-addressed: H(schema_v + gate + subject_hash + evidence_hash + policy_hash)
    schema_version: str
    timestamp: datetime
    gate: str
    verdict: str             # "allow" or "block"
    subject_hash: str
    evidence_hash: str
    policy_hash: str
```

- All gates wired: evidence_gate, intent_compiler, pre_commit, wrapper, continuity_checker
- Split store: ReceiptStore (JSONL) + EvidenceStore (content-addressed blobs)
- CLI: `governor receipts --gate/--verdict/--last/--json/--id/--evidence`

---

## The Actual Gap: Multi-Agent Drift Measurement

What we DON'T have yet:

1. **β-susceptibility tracking** — measuring how much each agent's output shifts when peer context changes
2. **Topology-aware propagation** — tracking which agent influences which, and how perturbations flow
3. **Cross-agent receipt correlation** — linking receipts across agents to detect drift patterns
4. **System susceptibility (SS) metric** — end-to-end measurement of value perturbation amplification

The existing infrastructure that connects to this:
- `DriftDetector` (src/governor/drift.py) — single-agent temporal drift, premise quarantine
- `SybilDetector` (src/governor/sybil.py) — bloc detection, effective voter count
- `IndependenceScorer` (src/governor/independence.py) — correlation class diversity
- `QuorumManager` (src/governor/quorum.py) — multi-validator consensus with independence requirements

---

## Possible Future Work

### Minimal addition (fits current architecture):
- Add `peer_context_hash` field to gate receipts when multi-agent
- Track receipt verdict changes when peer context varies (β proxy)
- Correlate via dispatcher's agent registry

### Test harness:
1. Build toy 3-agent chain using dispatcher protocol
2. Inject controlled drift (perturb one agent's values)
3. Measure: does governor's gate stop action when invariants violated?
4. Compare: drifted-but-gated vs drifted-and-acted

Demonstrates "drift exists" + "gate prevents commit" without replicating their full metric suite.

---

## References

- arXiv:2602.08567 - ValueFlow: Measuring the Propagation of Value Perturbations in Multi-Agent LLM Systems
- Governor 2.x spec (internal)
- Δt framework (CFD paper, DOI: 10.5281/zenodo.14629919)

---

*"They measured the disease. We build the immune system."*
