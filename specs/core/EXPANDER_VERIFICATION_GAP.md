# Expander Verification Graph Gap Analysis

## Dense Evidence Routing vs. Hierarchical Enforcement

```yaml
status: gap
relates_to:
  - interferometry.py (multi-model claim comparison)
  - evidence_gate.py (evidence-gated coding harness)
  - independence.py (IndependenceScorer, Jaccard similarity)
  - quorum.py (QuorumManager, multi-agent consensus)
  - audit.py (AuditPipeline, failure mode classification)
blocking: nothing
priority: deferred for v2, candidate for v3
```

---

## Insight

Amazon replaced Clos (hierarchical, tidy, predictable) datacenter networks
with Jellyfish-style random regular graphs. The counterintuitive result:
controlled randomness at the link level produces better spectral gap, better
expansion, and better worst-case cut properties than clean hierarchy.

The governor analog:

> **Keep enforcement as Clos. Make evidence acquisition an expander.**

The control graph (gates, receipts, invariants, policy lattice) stays
hierarchical, explicit, and auditable. Boring on purpose.

The verification graph (how claims get checked, how evidence is gathered,
how ground truth is reached) becomes dense, redundant, and low-correlation.
No single bottleneck. Graceful degradation when any one path fails.

---

## What Exists Today

The governor already has proto-expander properties in its verification layer:

- **Interferometry** runs the same prompt through multiple models and compares
  claims. Multiple low-correlation routes to the same assertion.
- **Independence scoring** measures method-signature diversity across quorum
  voters. Anti-cheat via Jaccard similarity.
- **External constraint attachment** binds claims to multiple substrates
  (Wikidata, Wikipedia, Scholar). Independent authorities for the same fact.

But these are opt-in, ad hoc, and not structurally guaranteed. There's no
policy that says "claims of class X must be reachable via N independent
verification routes."

---

## Where Expander Logic Applies

### 1. Evidence Path Redundancy (Anti-Chokepoint)

Don't let a single namespace be the spine. Important claims should be
verifiable via multiple independent anchors:

- CVE API + NVD + vendor advisory (not three mirrors of the same upstream)
- DOI + publisher + CrossRef
- Test suite + static analysis + runtime trace

The expander property: many short alternate paths to a checkable fact.

### 2. Graceful Degradation Under Partial Tool Failure

When one verification path is down (rate-limited, 404, timeout), the run
should degrade predictably: confidence drops, response class changes, but
no hallucinated output. This is the Jellyfish property — random graphs
maintain connectivity when links die.

### 3. Avoiding Tier Chokepoints

One brittle "golden checker" becomes a single point of failure. Expander
thinking distributes trust: require quorum for certain claim classes, keep
policy robust to one checker being wrong or compromised.

---

## Where It Does NOT Apply

### The Control Graph Stays Hierarchical

The policy lattice, invariant enforcement, authority tiers, audit trail
immutability, and capability scoping are constitutive constraints. These
are the routing protocol, not the link topology. Randomizing them produces
chaos, not resilience.

### Debuggability Is a Product Feature

Jellyfish works because routing software eats complexity invisibly. The
governor needs explainability. Too much verification "connectivity" without
legibility produces: "why did the run fail?" followed by a shrug. Every
path considered must be traceable in receipts.

---

## v3 Shape (No Implementation Details Yet)

When v2 is boring and stable, and there's real failure data (tool flakiness,
namespace drift, adversarial sources, rate limits), the following become
concrete:

- **Evidence quorum policies.** N-of-M independent anchors required by
  response class. "HARD claims need 3 independent verification routes."
- **Low-correlation routing.** Prefer genuinely independent authorities
  over mirrors of the same upstream. Measure source correlation.
- **Adaptive path selection.** Choose the next check based on current
  failure mode (timeout vs 404 vs mismatch), not a fixed chain.
- **Graph introspection in receipts.** Not just "failed," but "here are
  the alternate routes considered, attempted, skipped, and why."

---

## Why Not Now

- Core invariants need to be solid first. More paths without correctness
  just amplifies noise.
- v2 is still paying down correctness debt (schema, receipts, failure
  classes). Expander mode multiplies surface area.
- ROI only shows up with real failure data. Until then it's a cathedral
  for a weather pattern.

---

## The Bumper Sticker

> Keep enforcement as Clos.
> Make evidence acquisition an expander.

Hierarchy where you need auditability.
Redundancy where you need resilience.
