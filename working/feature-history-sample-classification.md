# Sample Classification — GOV_GAP_FEATURE_HISTORY_LIFECYCLE_001

Date: 2026-05-26
Discipline: §6.2 edge-case sample against §5.1 seed criteria.
Status: provisional — criteria-survival verdict + recommendation pending acceptance.

## Method

Applied §5.1 seed criteria (include 1-5, exclude 1-5) to 10 deliberately
edge-loaded entries from `.claude/rules/feature-history.md`:

- **Oldest** (Phase 1-3 substrate): Phase 1-3 BUILD_SPEC base, Multi-Agent v2.
- **Newest** (Standing C-series): C2, C3, C4, C5.
- **Genuinely ambiguous** (web Claude's flags): Puppet Mode, Interferometry, Convergence Auto-Tuning, Boil Control.

For each: proposed bin, which criteria fired, classifier confidence,
whether criteria did the work or judgment was needed.

## Classifications

### 1. Phase 1-3 (BUILD_SPEC base — claim types, receipt types, FSM, verifiers, envelopes, hooks, wrapper)

- **Bin**: 3.x platform
- **Fired**: include (1) runtime governance surface; (4) service/platform operation; (5) known-good → next bridge.
- **Confidence**: high
- **Notes**: Foundational substrate; every other entry sits on it. The 2.8.1 known-good bundle IS this substrate. Five-artifact ontology (include 2) is the *next* shape; Phase 1-3 has the predecessor receipt/claim types — partial match, but doesn't need to fire because (1)(4)(5) already do.

### 2. Multi-Agent v2 (SQLite backend, leases, epochs, dispatcher protocol)

- **Bin**: 3.x platform
- **Fired**: include (1) runtime governance surface (leases govern concurrent access; dispatcher governs agent coordination); (4) service/platform operation (daemon depends on this).
- **Confidence**: high
- **Notes**: Clean classification. No exclusion candidates trigger.

### 3. Standing-Class Chain Validator (C2)

- **Bin**: 3.x platform
- **Fired**: include (1) runtime governance surface (validates standing chains that gate authorization); (3) public gate / fixture-reproducible boundary (validator_contract.md, ratified Q1-Q4 decisions, SPEC-led); (4) service/platform operation.
- **Confidence**: high
- **Notes**: Exemplar of the public-gate criterion. Bootstrap-fail-closed, validation receipts. This is the *prototype* of what (3) is naming.

### 4. Standing Schema Discipline (C3)

- **Bin**: 3.x platform
- **Fired**: include (1), (3), (4). Same family as C2. Validator v0.2.0 supersession.
- **Confidence**: high
- **Notes**: Same shape as C2.

### 5. Standing Check Basis Discipline (C4)

- **Bin**: 3.x platform
- **Fired**: include (1), (3), (4). Same family. Validator v0.3.0. CheckBasis structuring.
- **Confidence**: high

### 6. Standing Continuity Basis (C5)

- **Bin**: 3.x platform
- **Fired**: include (1), (3), (4). Continuity-facing phase. Validator v0.4.0.
- **Confidence**: high
- **Notes**: Same family as C2-C4. The Standing C-series is the cleanest cluster of 3.x platform anchors in the corpus.

### 7. Puppet Mode (persona pinning, voice constraints, semantic diff guard, builtin profiles)

- **Bin**: candidate substrate
- **Fired**: weak partial match on include (4) — productized with CLI/registry. Stronger exclusion (1) "interesting doctrine with no runtime governance surface" — persona/voice constraints are output constraints, not runtime gates on activity/transitions/tools/sessions.
- **Confidence**: **low — criteria don't sharply cut.**
- **Notes**: **Edge case found.** Puppet Mode is *adjacent* to governance (constrains model output via persona) but doesn't sit on the runtime governance hot path (daemon/RPC/hook). The exclusion (1) "no runtime governance surface" is the cutting blade, but the phrase is vague — Puppet Mode arguably has *some* runtime surface via the semantic diff guard.
- **Sharpening signal**: criterion text needs to distinguish "voice/output constraint" from "live activity gate."

### 8. Interferometry (multi-model claim comparison; Code Interferometry with CheckFinding bridge)

- **Bin**: candidate substrate
- **Fired**: weak partial match on include (3) — Code Interferometry has CheckFinding bridge to VS Code (public surface). But interferometry itself doesn't *gate* anything — it analyzes and surfaces. Exclusion (1) fires: "interesting doctrine with no runtime governance surface" — it's an analysis layer feeding governance, not a gate.
- **Confidence**: medium-low — similar shape to Puppet Mode.
- **Notes**: Capability exists, may matter if interferometry becomes input to a runtime gate. Currently substrate.
- **Sharpening signal**: same as Puppet Mode — "analysis/surface layer feeding governance" vs. "runtime governance gate" distinction.

### 9. Convergence Auto-Tuning (offline system identification + proposal engine)

- **Bin**: current research
- **Fired**: exclusion (3) "research probe whose value is conceptual rather than platform-operational" — *partially*. It's productized (CLI, ProposalStore, admissibility checks) so not purely conceptual. But the analyzer is offline (not runtime), and proposals require human approval before they affect platform behavior.
- **Confidence**: medium
- **Notes**: Offline analysis loop with proposal engine. Could promote to candidate substrate if proposals get auto-applied or if the analyzer becomes runtime. Current shape is exploration of "can we tune the platform from observed traces?"
- **Sharpening signal**: criterion (1) wants an "offline analysis with platform output" vs. "live runtime tuning" distinction.

### 10. Boil Control (named presets, dwell time, tripwires)

- **Bin**: 3.x platform (with separate-question caveat — see notes)
- **Fired**: include (1) runtime governance surface clearly (dwell time, tripwires, transitions); (4) service/platform operation (CLI surface present, parallel to regime detection / homeostat).
- **Confidence**: high on criterion fit; **flagged** for separate question.
- **Notes**: Criterion (1) fires clearly — Boil Control IS runtime governance. **But** Boil Control may be functionally redundant with Regime Detection + Ultrastability + Homeostat + Coupling (the newer governance family). Criteria don't surface the *supersession* question — they ask "does this fit a bin," not "is this the current/best fit for this surface area." Per §7.2 retirement brake, retirement-because-superseded is a separate decision; the criteria correctly stop at bin assignment.
- **Sharpening signal**: **none for the criteria.** Supersession resolution belongs to a follow-on audit after the cleanup pass. Criteria correctly defer.

## Findings

| Entry | Criteria did the work? | Why / why not |
|---|---|---|
| Phase 1-3 | Yes | Multiple includes fire cleanly. |
| Multi-Agent v2 | Yes | Clear (1)+(4). |
| Standing C2 | Yes | Exemplar of (1)+(3)+(4). |
| Standing C3 | Yes | Same family as C2. |
| Standing C4 | Yes | Same family as C2. |
| Standing C5 | Yes | Same family as C2. |
| Puppet Mode | **No** | Exclusion (1) "no runtime governance surface" is vague. |
| Interferometry | **No** | Same as Puppet Mode. |
| Convergence Auto-Tuning | Partial | (3) partial fire; needs "offline vs. live" distinction. |
| Boil Control | Yes (for bin); supersession is correctly out of scope | Criteria stop at bin assignment. |

**Score: 7 clean, 1 partial, 2 weak. No fundamental collapse.**

## Did §8 honesty clause fire?

**No.** 3.x platform criteria were drafted from prior context (five-artifact ontology, public-gate discipline, service-as-platform direction), survived sample testing on the obvious anchors (Phase 1-3, Multi-Agent v2, Standing C2-C5), and surfaced *specific text-level* edge-case tension on three middle-layer features. That is "criteria held with edits required," not "3.x is undefined."

## Sharpening proposed

Two small text edits to §5.1 before mechanical execution:

### Sharpening 1 — sharpen include (1) "runtime governance surface"

Current text:
> Participates in live governance of activity, transitions, tools, sessions, overrides, leases, recovery, or containment state.

Proposed text:
> Directly gates, transitions, or constrains live *activity* — tool calls, RPC dispatch, hook firing, lease acquisition, session lifecycle, override application — at the daemon / RPC / hook layer. Analysis layers and voice/output constraints that *feed* governance but do not gate live activity belong to `candidate substrate`, not `3.x platform`.

This would cleanly classify Puppet Mode and Interferometry as candidate substrate (no live-activity gating) and keep Boil Control / Multi-Agent v2 / Standing C-series as 3.x platform.

### Sharpening 2 — add an offline/live qualifier

Add a clarifier after include (1):

> **Offline-analysis features** (e.g., trace analysis with proposal output) classify as `current research` unless they are wired into live platform behavior (auto-apply, runtime feedback loop). Productized CLI surface for an offline tool does not by itself promote to 3.x platform.

This would cleanly classify Convergence Auto-Tuning as `current research` per its current offline shape, and provide a promotion path if the analyzer becomes runtime.

## Recommendation

**Apply Sharpening 1 + Sharpening 2 to §5.1, then proceed to mechanical execution.**

Criteria did not collapse. They classified the obvious anchors cleanly (7/10), surfaced specific text-level ambiguity on three middle-layer features that small refinements resolve, and correctly deferred supersession on Boil Control to a follow-on audit.

**Do not** recut the bin taxonomy. The bins (3.x platform / current research / candidate substrate / retire) hold; what needs sharpening is the *criteria text*, not the *bin shape*.

**Do not** proceed to execution without the sharpening — the unsharpened criteria would force per-entry judgment on ~10% of entries, defeating §6.3 mechanical execution.

## Next step

Apply Sharpening 1 + Sharpening 2 to `specs/gaps/GOV_GAP_FEATURE_HISTORY_LIFECYCLE_001.md` §5.1, then run the mechanical execution pass over `feature-history.md`.

Supersession audit (Boil Control vs. Regime/Ultrastability/Homeostat/Coupling) is **not in scope** for this gap. File as a follow-on candidate.
