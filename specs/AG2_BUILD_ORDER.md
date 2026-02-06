# AG2 Build Order

## 2.0 Implementation Sequence — 14 Gap Specs

```yaml
status: planning
branch: dev (create before starting)
approach: complete-per-layer (no MVPs, no half-implementations)
dogfood: use slim mode to govern 2.0 development once Layer 0 lands
```

---

## Dependency Graph

```
Layer 0 (Substrate)
  AG2_INSTRUMENT_SPEC ──────────────────────┐
  SLIM_MODE_SPEC ───────────────────────────┤
                                            │
Layer 1 (Control Plane)                     │
  CONSTRAINT_COMPILER_SPEC ─────────────────┤ (emits receipts into instrument)
  DETECTOR_INTEGRATION_SPEC ────────────────┤ (signals as artifacts)
                                            │
Layer 2 (New Math)                          │
  COMMITMENT_TRANSPORT_SPEC ────────────────┤ (needs compiler for projection validation)
  SPECTRAL_STABILITY_SPEC ──────────────────┤ (needs instrument for reports, compiler for gating)
  SCALAR_COLLAPSE_SPEC ─────────────────────┤ (needs telemetry history from instrument)
                                            │
Layer 3 (Interfaces)                        │
  CLI_CHAT_SPEC ────────────────────────────┤ (needs compiler for constraint projection)
  MAUDE_RENAME_SPEC ────────────────────────┤ (after CLI surfaces stabilize)
                                            │
Layer 4 (Docs + Polish)                     │
  DOC_GOVERNANCE_SPEC ──────────────────────┤ (needs commitment transport + instrument)
  AG2_DASHBOARD_UX_SPEC ────────────────────┤ (needs instrument for run-centric UI)
  AG2_WEBUI_DEMO_GAP_SPEC ─────────────────┘ (needs dashboard + working demos)

Parallel Track (Security)
  AG2_TEMPORAL_ATTACK_SURFACE_SPEC ──── incremental, starts after Layer 0

Parallel Track (Docs)
  AG2_DOCS_GAP_SPEC ──── incremental, can run anytime
```

---

## Layer 0: Substrate

**Build first. Everything else depends on these.**

### 1. AG2_INSTRUMENT_SPEC (Large)

Instrumented execution: append-only events, content-addressed artifacts, replayable runs.

- Run IDs, `events.jsonl`, artifact store
- Every subsequent spec wants to emit receipts into this system
- If this isn't done first, every other spec invents its own logging and you re-plumb later

**Key dependency edges:**
- Constraint compiler receipts → need artifact store
- Detector signals → need artifact store
- Doc governance receipts → need artifact store
- Dashboard → needs run-centric event stream
- Scalar collapse → needs telemetry history

### 2. SLIM_MODE_SPEC (Medium)

Single-developer governance for high-iteration workflows.

- `governor decide`, `governor anchor`, `governor lock`, `governor must-pass`
- Claude Code / Codex hook integration
- **This is how you dogfood 2.0 while building it**
- In a no-CI environment, the tool only exists if it's ergonomic locally

**Key dependency edges:**
- Every subsequent layer uses slim mode during development
- CLI chat builds on slim mode's UX patterns
- Doc governance uses slim mode's one-liner registration pattern

**Layer 0 outcome:** A run-centric skeleton that can log, replay, and not punish you. You start using the governor on itself.

---

## Layer 1: Control Plane

**The new architecture class. Governor becomes a constraint compiler, not just a gate.**

### 3. CONSTRAINT_COMPILER_SPEC (Medium)

Pre-execution constraint projection. Override warrants. Prefix budgeting. Caching.

- `compile_constraints()` pure function
- 11-layer monotonic resolution
- Scar taxonomy (hard/soft/procedural)
- Warrant quorum policy
- Emits receipts into instrument system

### 4. DETECTOR_INTEGRATION_SPEC (Small-Medium)

Sensor/controller boundary for Δt temporal coherence signals.

- Signal collapse (19 dims → 5 control signals)
- `DETECTOR_SIGNAL` evidence type
- Monotonic influence (signals tighten only)
- Failure-safe default (silence = higher bar)
- File artifact only — no torch in governor

**Layer 1 outcome:** Governor becomes "controller with receipts," fed by sensors. Pre-execution projection reduces generate-reject churn.

---

## Layer 2: New Math

**Structural admissibility + meaning preservation + anti-Goodhart.**

### 5. COMMITMENT_TRANSPORT_SPEC (Medium)

Representational invariance under compression.

- Commitment extraction (MUST/SHOULD/MAY/MUST_NOT)
- Transport classification (PRESERVED/WEAKENED/DROPPED/CONTRADICTED)
- Shear metric with modality weighting
- Wraps `context_compact.py` and continuity bridges
- Immediate value: catches what compaction drops

### 6. SPECTRAL_STABILITY_SPEC (Medium)

Coupling matrix verification for governance topology.

- ρ(M) computation from layer rates/feedback
- Hard block at ρ ≥ 1 (no override — physics)
- Five kinetic regions (Coherent → Decoherent)
- Preflight check for autonomy configurations
- Needs instrument for stability reports, compiler for gating

### 7. SCALAR_COLLAPSE_SPEC (Medium)

Eigenstructure evaporation detection in governance chains.

- Effective dimension, variance concentration, action entropy, metric agreement
- Freeze auto-tuning when collapse detected
- Irreversibility warning (recovery requires exogenous forcing, not tuning)
- Needs telemetry history — build last in this layer

**Layer 2 outcome:** The governor can detect structural instability (spectral), meaning loss (transport), and optimization pathology (collapse). These are the failure modes that look like success until they don't.

---

## Layer 3: Interfaces

**Make the new capabilities accessible.**

### 8. CLI_CHAT_SPEC (Small)

Governed conversational CLI with backend switching.

- `governor chat`, `governor backend switch`
- Quick interferometry via `--compare`
- Thin layer over existing `ChatBridge` + `GovernorHooks`
- Wait until compiler exists so constraint projection works in chat

### 9. MAUDE_RENAME_SPEC (Small)

Rename `maude_lite.py` to something that describes the function.

- Do after CLI surfaces stabilize (post slim mode, post CLI chat)
- Otherwise you rename twice
- Breaking change to CLI — bundle with other 2.0 CLI changes

**Layer 3 outcome:** The new capabilities are usable from a terminal. The naming makes sense.

---

## Layer 4: Docs + Polish

**Make it presentable. Do when you want outside eyeballs.**

### 10. DOC_GOVERNANCE_SPEC (Medium-Large)

Docs as governed artifacts: authority scope, staleness, commitment preservation.

- Depends heavily on commitment transport + instrumentation
- Export hooks for Obsidian/Logseq
- "Make the org's memory real" — powerful but not the first brick

### 11. AG2_DASHBOARD_UX_SPEC (Large)

Run-centric dashboard UI.

- Needs instrument spec for event streams and run model
- Streaming events, cancellation contracts, run templates

### 12. AG2_WEBUI_DEMO_GAP_SPEC (Medium)

Automated screenshot generation for demos.

- Needs working dashboard + updated WebUI
- Last in sequence — polish, not structure

**Layer 4 outcome:** The system is documentable, demonstrable, and adoptable.

---

## Parallel Tracks

### AG2_TEMPORAL_ATTACK_SURFACE_SPEC (Large, incremental)

Δt-aware security analysis. Start adding checks after Layer 0 lands. Don't block the main sequence — implement as policies and scanner rules incrementally as the other layers provide the enforcement substrate.

### AG2_DOCS_GAP_SPEC (Medium, incremental)

Missing documentation and ADR extraction. Can run anytime. Good for sessions where you want useful work that doesn't require deep concentration.

---

## Key Dependency Edges (Summary)

| Spec | Hard Dependencies |
|------|------------------|
| AG2_INSTRUMENT | None (first) |
| SLIM_MODE | None (first) |
| CONSTRAINT_COMPILER | Instrument (receipts) |
| DETECTOR_INTEGRATION | Instrument (artifacts) |
| COMMITMENT_TRANSPORT | Compiler (projection validation) |
| SPECTRAL_STABILITY | Instrument (reports), Compiler (gating) |
| SCALAR_COLLAPSE | Instrument (telemetry history) |
| CLI_CHAT | Compiler (constraint projection) |
| MAUDE_RENAME | Slim Mode, CLI Chat (CLI surface stability) |
| DOC_GOVERNANCE | Commitment Transport, Instrument |
| AG2_DASHBOARD_UX | Instrument (run model) |
| AG2_WEBUI_DEMO_GAP | Dashboard |
| TEMPORAL_ATTACK_SURFACE | Instrument (parallel, incremental) |
| AG2_DOCS_GAP | None (parallel, incremental) |

---

## Estimated Sequence (Complete-Per-Layer)

```
Week(s) 1-2:  Layer 0  — Instrument + Slim Mode
Week(s) 3-4:  Layer 1  — Constraint Compiler + Detector Integration
Week(s) 5-6:  Layer 2  — Commitment Transport + Spectral Stability + Scalar Collapse
Week(s) 7:    Layer 3  — CLI Chat + Maude Rename
Week(s) 8+:   Layer 4  — Doc Governance + Dashboard + Demo
Ongoing:       Parallel — Temporal Attack Surface + Docs Gap
```

Time estimates are vibes, not commitments. The governor would reject them.
