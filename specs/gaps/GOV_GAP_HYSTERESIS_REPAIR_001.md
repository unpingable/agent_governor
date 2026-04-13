# GOV_GAP_HYSTERESIS_REPAIR_001

## Title
Hysteresis-Aware Shadow State Remediation

## Status
Draft. Design hypothesis committed to continuity (2026-04-13).

## Problem Statement

Governor can block, permit, and receipt bounded actions. It lacks a formal
remediation operator for **already-durable shadow state** that has acquired
governing force without authorized promotion.

Existing controls assume forward governance: proposals flow through gates,
receipts are emitted, scars accumulate. But when unauthorized state has already
become load-bearing -- when the system has reorganized around it -- "just
enforce the rules" can break the plant. The gap is a principled operator for
repairing captured or hysteretic governance state.

This is the control-law consequence of the state-promotion calculus:

- Lower-tier state gaining higher-tier force without proper promotion is
  **unauthorized durability** (shadow governance).
- Shadow vs formal state are distinct control variables.
- Hysteresis determines whether remediation is enforcement or migration.

## What Already Exists

These modules are substrate, not redundant:

| Module | Relationship to repair |
|--------|----------------------|
| `drift.py` | Detects temporal asymmetry -- shadow state accumulating. Does not remediate. |
| `claim_diff.py` | Detects confidence drift, provenance laundering, silent retraction. Measurement, not repair. |
| `evidence_gate.py` | Gates forward claims. Does not address already-durable unauthorized state. |
| `scars.py` | Failure provenance, hysteresis. Constrains future actions based on past failures. Closest existing primitive. |
| `continuity.py` | Anchor registry, convergence. Enforces invariants forward. Does not classify or remediate backward. |
| `regime.py` / `boil.py` | Regime detection and mode control. The enforcement-vs-migration branch maps here. |
| `quarantine` (in `drift.py`) | Premise quarantine exists. Not generalized to shadow-state items. |
| `receipt_kernel` | Append-only hash-chained receipts. Transport for repair receipts. |

## What's New

### 1. Governed cell model

A governed scope expressed as a tuple for repair purposes:

```
G = (R, S_f, S_s, B, W, C)
```

- `R` = current regime / invariant set
- `S_f` = formal state (receipted, promoted through valid paths)
- `S_s` = shadow state (durable consequences without valid promotion)
- `B` = write barriers / promotion controls
- `W` = witness / receipt / observability surface
- `C` = child cells (recursive scopes)

### 2. Shadow divergence measure

```
D(G,t) = |S_s(t)| / (|S_f(t)| + |S_s(t)|)
```

Where magnitude is **effective influence on behavior**, not item count.
One regime-wide policy reversal and one trivial config fix are not equal.

### 3. Control variables

```
H(G,t) = hysteresis / reversibility cost
O(G,t) = observability quality
```

- High `H` = system has reorganized around shadow state; enforcement risks breakage.
- Low `O` = you can see consequences but not the promotion path that produced them.

### 4. Repair operator

```
R(G) = freeze -> surface -> classify -> choose mode -> reconstitute -> recurse
```

#### Phase 1: Freeze unauthorized promotion

Tighten write barriers. Stop digging before auditing the flood.

#### Phase 2: Surface shadow state

Build candidate set from: unreceipted durable consequences, gap-flagged
objects, policy deltas with no attestation path, observed actions with no
proposal/evaluation trail.

#### Phase 3: Classify shadow items

For each item, assign one of:

| Outcome | Meaning |
|---------|---------|
| **ratify** | Shadow state carried something normatively superior. Promote formally. |
| **reissue** | Same outcome, but replay through valid ceremony. Process was broken, not content. |
| **quarantine** | Keep effect visible but non-expanding. Containment. |
| **repeal** | Remove force. |
| **defer** | Insufficient standing or evidence. Isolate and revisit. |

The `ratify` vs `reissue` distinction is the sovereign hinge:
- `reissue` = formal state was right in principle; path was broken.
- `ratify` = formal state was incomplete, blind, or wrong; shadow state carried
  something the formal regime failed to capture.

`ratify` implies a legitimacy source not reducible to current formal state.
That is the point where the operator stops being cleanup and starts being
actual sovereign competence. See Sub-gap B below.

#### Phase 4: Choose regime

```
enforcement   if D <= epsilon and H <= eta
migration     if D > epsilon or H > eta
```

- **Enforcement**: remove violating state directly.
- **Migration**: construct formal successor state alongside shadow, cut over gradually.

#### Phase 5: Reconstitute formal state

- Shadow state is not silently erased.
- Every promotion, quarantine, repeal, or supersession emits a repair receipt.
- Historical shadow artifacts remain legible as historical facts.
- New state gains force only through explicit repair acts.

#### Phase 6: Recurse into child cells

Same operator, same diagnostic, same enforcement/migration choice. Aggregate
divergence upward weighted by scope criticality / blast radius.

### 5. Repair telemetry (sibling metric to D)

Three separate concerns that must not collapse into one number:

| Metric | Measures |
|--------|----------|
| `D(G,t)` | What is broken -- divergence between formal and shadow state |
| `P_R(G,[t0,t1])` | How we are responding -- distribution of repair outcomes |
| `Gamma(G,[t0,t1])` | Whether the response works -- effectiveness deltas |

#### Repair profile vector

```
P_R = (rho_ratify, rho_reissue, rho_quarantine, rho_repeal, rho_defer)
```

Weighted by effective influence, not count.

#### Diagnostic reading

- High `reissue`: process debt, legitimacy mostly intact.
- High `ratify`: formal regime lagging reality, constitutional blind spots.
- High `quarantine` + `defer`: epistemic or standing deficit; operator buying time.
- High `repeal`: restoration pressure; active conflict with shadow state.

#### Derived indices

- `L = rho_ratify` (Formal Lag)
- `E = rho_reissue` (Process Debt)
- `C = rho_repeal` (Restoration Pressure)
- `Q = rho_quarantine + rho_defer` (Epistemic Deficit)

#### Effectiveness

```
Gamma = alpha * delta_D + beta * delta_H + gamma * delta_O
```

Style is not performance. A regime can have nice profile + bad performance,
or ugly profile + good performance.

## Sub-gaps

### A. Repair taxonomy and control loop

Implementable under delegated regime authority. The five-outcome taxonomy,
enforcement/migration branch, repair receipts, telemetry indices, recursive
scoping -- this is Governor runtime behavior with existing primitives.

### B. Sovereign standing for `ratify`

Not yet implementable. `ratify` requires a higher-order authority source --
an answer to "who can say the shadow state was actually right?" that is not
reducible to the formal state that missed it in the first place.

Initial approach: feature-gate `ratify` as "proposed ratification" requiring
explicit operator confirmation. Stub the standing question; don't pretend it's
solved.

`reissue / quarantine / repeal / defer` are all implementable without solving
the legitimacy question.

## Acceptance Criteria (MVP)

1. Governor can declare a governed cell with: formal state snapshot, shadow
   inventory, repair mode.

2. Governor can classify shadow items into the five outcome categories.

3. Governor can choose enforcement (low D, low H) vs migration (high D or
   high H).

4. Every repair action emits a receipt/scar object.

5. Historical shadow state remains visible and linked, not rewritten away.

6. Repair telemetry can be computed: D, repair profile, effectiveness deltas.

7. A child scope can be repaired with the same grammar (self-similar).

## Non-goals

- Solving the legitimacy source for `ratify`. That is Sub-gap B.
- Inter-polity arbitration of competing repair operators.
- Detecting or remediating L3 capture.
- Universal constitutional layer.

## Relationship to other systems

- **WLP**: Repair actions emit WLP-class receipts sufficient for historical
  legibility, audit, and outcome distinction. WLP is the receipt substrate.
- **RPP**: This gap does not assume any RPP dependency. Public or federated
  publication of repair receipts is a separate concern.
- **GAP-003**: Federation plumbing for external witnessing. Orthogonal to
  repair logic.

## Provenance

Design hypothesis from state-promotion calculus (2026-04-13). Key insight
from DeepSeek review: `ratify` as distinct from `reissue` implies an
extra-formal legitimacy source, which is the actual sovereign hinge. Repair
receipt chain gives second-order legibility of repair behavior, not L4
sovereignty -- measurement, not authority.
