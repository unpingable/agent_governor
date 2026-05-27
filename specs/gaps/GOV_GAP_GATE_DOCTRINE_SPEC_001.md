# GOV_GAP_GATE_DOCTRINE_SPEC_001

## Title
Kernel-shaped AG surfaces need SPEC-led doctrine independent of organic AG implementation history. Public gates encode admissibility doctrine that is currently legible only by reading ~14k tests; doctrine that cannot be read by an outside implementation cannot be ratified by one.

## Status
Gap spec — methodology record. **No SPEC.md is authored by this filing. No module is selected for SPEC-leading. No test corpus is migrated. No documentation refactor is ratified.** Names the methodology gap and preserves the candidate inventory entry; future forcing cases promote.

## Origin

Filed 2026-05-09 alongside `GOV_GAP_PUBLIC_GATE_CONFORMANCE_001`. Same brainstorming pass, same Wicket comparison, same ChatGPT refinement. Where the sibling gap names the *projection* (verdict-surface conformance), this gap names the *methodology* (doctrine articulated separately from the implementation that realizes it).

The provoking observation — Wicket is **SPEC-led**: a 684-line `SPEC.md` is authoritative; the Rust code is "the bug" if they disagree. AG has the inverse posture: ~14k tests embody the doctrine, no SPEC.md exists, and the doctrine is recoverable only by reading the implementation. That is correct posture for elaborator modules (regime detector, scar ledger, runtime supervisor — those modules' doctrine *is* their behavior, and tests are the right shape for it). It is increasingly inadequate posture for kernel-shaped surfaces, where doctrine is supposed to be readable, disagreement-shaped, and stable across implementations.

The ChatGPT refinement reframed the conformance question (sibling gap) and surfaces this one as its prerequisite: a public gate cannot meaningfully be conformance-checked against an external SPEC if no SPEC exists for it on the AG side.

## Core Claim

> **Kernel-shaped AG surfaces deserve SPEC-led doctrine.**

The methodology Wicket demonstrates ("SPEC.md is authoritative; code is the bug") should apply to AG's kernel-shaped public surfaces (the `gate_receipt`, `evidence_gate`, `intent_compiler`, `scope`, `verifier_gate`, `ci`, `governed_activity` partition named in `GOV_GAP_PUBLIC_GATE_CONFORMANCE_001`). It should **not** apply to elaborator-shaped internals (regime, scar, homeostat, runtime, writing modules, etc.) — those modules' doctrine is appropriately encoded in tests and organic structure, and a SPEC.md for them would be wrong-shaped.

The asymmetry is the load-bearing point: SPEC-led methodology is right for the *kernel* portion of AG, wrong for the *elaborator* portion. Imposing it uniformly is architecture anorexia (sibling gap names this failure mode); leaving it absent uniformly leaves doctrine illegible at the surfaces where legibility matters most.

## Problem Statement

AG today:

- 14k tests across 60+ modules.
- `docs/RECEIPT_KERNEL_CONTRACT.md` (one document, partial coverage of one module).
- `docs/doctrine/decisions/` (validator versioning ceremony — tightly scoped to the standing validator).
- `.claude/rules/` (orientation for Claude Code, not doctrine).
- `BUILD_SPEC.md` (build guide, claim/receipt enumeration — closer to architectural overview than doctrinal SPEC).
- `MULTI_AGENT.md` (concurrency model — closer to design doc than doctrinal SPEC).
- No per-gate SPEC analogous to Wicket's.

The gate doctrine an outside reader would want to find — *what does `evidence_gate` consider admissible? what reason codes can it emit? what does its receipt obligation look like? what verdicts are forbidden? what happens at edge cases like simultaneous violations?* — is recoverable only by reading the module source and its tests. That is fine for someone working *inside* AG; it is failure-shaped for ratification by a sibling implementation, formal verification, external audit, or even a fresh-eyes session months later.

Wicket exists because this gap exists. Wicket compresses *one* gate's doctrine (admissibility preflight) into 684 lines of SPEC + ~1.4k LOC of literal Rust. The compression made the doctrine readable enough to disagree with. The pattern is generalizable to AG's other kernel-shaped surfaces — but only if the methodology is adopted, not by accident.

The hole is methodological, not behavioral. AG's gates *behave* doctrinally. Their doctrine is just illegible.

## Doctrine (proposed; not yet ratified)

> **Kernel-shaped AG surfaces lead with a SPEC. The implementation conforms literally.**

> **Elaborator-shaped AG modules are appropriately doctrine-by-test.** The methodology asymmetry is a feature, not a transitional state.

> **A SPEC.md is small.** Wicket's is 684 lines for the entire admissibility surface. An AG gate SPEC that grows past ~1000 lines is probably either covering more than one gate or letting elaborator concerns leak in.

> **Methodology applies at the kernel boundary, not throughout the module.** A module like `evidence_gate` may have a small SPEC governing its public verdict surface and a much larger body of test coverage governing its internal heuristics, claim extraction, custody scoring, etc. The SPEC binds the contract, not the body.

The keeper sentence:

> **AG can be SPEC-led at its kernel surfaces and test-led at its elaborator interiors. The two postures are not in tension; they are responses to different shapes of doctrine.**

## Existing Coverage / Adjacent Documentation

| Artifact | What it covers | Why it is not the SPEC this gap names |
|----------|----------------|---------------------------------------|
| `BUILD_SPEC.md` | Step-by-step build guide, claim/receipt type enumeration | Architectural overview; not per-gate doctrinal contract |
| `MULTI_AGENT.md` | Concurrency model, dispatcher protocol | Design doc for one subsystem; doctrinal but scoped to multi-agent coordination |
| `docs/RECEIPT_KERNEL_CONTRACT.md` | Receipt kernel invariants, event types | Closest existing artifact in shape; covers one library, not the gate surface |
| `docs/doctrine/validator_contract.md` | Standing validator obligations (Q1–Q4 ratification) | Per-component doctrine; methodology proof-of-concept |
| `docs/doctrine/decisions/validator-v0_*.md` | Supersession ceremony for validator versions | Methodology proof-of-concept; specific to the validator |
| `.claude/rules/*.md` | Orientation for Claude Code working in the repo | Travel guide, not doctrine |
| Test corpus (`tests/test_*.py`) | Behavior under specific inputs | Implementation-coupled; doctrine recoverable by reading, not by index |

The existence of `docs/doctrine/validator_contract.md` and the validator-version supersession ceremony is significant — it is methodology proof-of-concept, not a counterexample. The standing validator already has SPEC-led doctrine. The question this gap names is whether that posture should extend to the rest of the kernel-shaped surface (`evidence_gate`, `intent_compiler`, `scope`, `verifier_gate`, `ci`, `governed_activity`, `gate_receipt`).

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. **Names the methodology asymmetry explicitly:** SPEC-led for kernel surfaces, test-led for elaborator internals; the asymmetry is permanent, not transitional.
2. **Identifies the candidate kernel surfaces** that warrant SPEC-led treatment (in coordination with `GOV_GAP_PUBLIC_GATE_CONFORMANCE_001`'s partition declaration).
3. **States the SPEC shape constraints:** small (target ≤1000 lines per gate), bounded (covers public verdict surface, not internal heuristics), versioned with explicit supersession (`docs/doctrine/decisions/` pattern), authoritative ("if SPEC and code disagree, code is the bug").
4. **Identifies the methodology proof-of-concept** already in `docs/doctrine/validator_contract.md` as the precedent and the ceremony pattern (`validator-v0_*.md`) as the supersession discipline.
5. **Records what is *not* ratified:** no SPEC is authored, no module is selected for SPEC-leading, no documentation refactor is committed, no migration plan from test-led to SPEC-led is scheduled.
6. **Identifies forcing cases that would justify promotion to SPEC authoring** (deferred, not ratified by this filing): a public gate whose doctrine becomes load-bearing for an external integration; a Wicket-shaped fixture that AG cannot answer without the gate's doctrine being read out of the implementation; a doctrinal disagreement between AG and a sibling implementation that has no authoritative resolution because no AG SPEC exists.

## Non-goals

- **Not authoring any SPEC tonight.** This filing is a containment vessel; SPEC authoring is deferred per-module work.
- **Not ratifying which modules get SPECs and which do not.** The partition is shared with `GOV_GAP_PUBLIC_GATE_CONFORMANCE_001` and is itself doctrine to be settled, not pre-decided here.
- **Not deprecating the test corpus.** Tests remain the right shape for elaborator-internal doctrine and for behavioral coverage of SPEC'd surfaces. SPEC-led ≠ test-replacing.
- **Not a documentation reorganization.** No moves of existing docs, no renames, no consolidation. Existing artifacts stay where they are.
- **Not extending the validator-version ceremony to other modules.** The standing validator's supersession discipline is the *precedent*, not the *prescription*. Each kernel surface that gets a SPEC also gets a versioning approach appropriate to its rate of doctrinal change.
- **Not committing to Wicket-style 1:1 spec-to-code literal-translation.** That methodology is appropriate for Wicket because Wicket has one job and ~1.4k LOC. AG modules typically have larger codebases with the SPEC binding only the public surface; the SPEC and the code are not 1:1 in size or in line-by-line correspondence.
- **Not a public-doctrine-publication commitment.** Whether AG SPEC files become external publication targets (vs. internal doctrine artifacts) is a separate question outside this gap's scope.

## Relationship to Other Gaps / Specs

- **`GOV_GAP_PUBLIC_GATE_CONFORMANCE_001`** — Sibling gap, filed in the same commit. That gap names the verdict-surface conformance projection. This gap names the SPEC-led methodology that gives the conformance projection something to be conformant *to*. The two compose: a SPEC declares the doctrine, the projection is the wire-level conformance check, the implementation realizes it.
- **`docs/doctrine/validator_contract.md`** + **`docs/doctrine/decisions/validator-v0_*.md`** — Methodology proof-of-concept. Demonstrates that SPEC-led doctrine + supersession ceremony works in AG. This gap argues for extending the *posture*, not the *exact form*.
- **`GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001`** — Substrate-placement question for the authority mint. Independent of substrate (Python anti-laundering vs Rust structural), the mint surface deserves a SPEC. Substrate decisions can defer; SPEC discipline can begin earlier.
- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — Construction discipline on `AuthorizationVerdict`. The doctrine that gap names ("authority observable, not constructible") is the kind of doctrine that would live in a SPEC; the gap is currently a containment vessel because no SPEC exists for it to land in.
- **`~/git/wicket/SPEC.md`** — The methodology proof-of-concept from outside AG. 684 lines, authoritative, literal Rust translation, fixture-driven. The shape this gap argues should generalize (with module-appropriate scaling) to AG's kernel-shaped surfaces.

## Open Questions

1. **What is a "module" for SPEC purposes?** Wicket's SPEC covers one library with one entry point. `evidence_gate` is one module but exposes several distinct verdict-emitting surfaces (custody scoring, claim extraction, contradiction detection, exit-shape checking). Does each surface get a sub-SPEC, or does one SPEC cover the module with sectional structure?
2. **What is the right home for AG SPECs?** `docs/doctrine/` (alongside the existing validator contract) is the obvious candidate. `specs/` is currently used for gap specs. The two are different shapes (gaps name absences; SPECs name doctrine), and conflating them would be wrong-shaped.
3. **Does the methodology asymmetry mean elaborator modules cannot ever be SPEC-led?** Probably not — *some* elaborator-internal doctrine is stable enough to deserve SPEC treatment (e.g., the regime detector's hysteresis state machine has stable shape). The general posture is "test-led by default for elaborators, SPEC-led where doctrine is stable enough to warrant it." The exact partition is per-module.
4. **What is the relationship between SPEC-led doctrine and `.claude/rules/feature-history.md`?** Feature history is verbose per-feature design notes, not doctrine. If a SPEC exists for a kernel surface, the feature-history entry can compress (or point at it). If no SPEC exists, feature-history is the closest available record.
5. **How does SPEC discipline interact with the gap-spec format itself?** Gap specs name absences and candidate doctrine; SPECs name ratified doctrine. A gap spec promoted to ratified doctrine becomes (or feeds) a SPEC. The supersession path is presumably: gap spec → forcing case → SPEC + retired/superseded gap spec. This gap does not formalize that path; just notes it.
6. **Should AG SPECs reference Wicket SPEC explicitly?** For surfaces that overlap (admissibility-shaped gates), reference seems right — both implementations conform to the same doctrine. For surfaces that don't (e.g., `governed_activity` drift verdicts, which Wicket does not represent), reference would be misleading. Per-SPEC decision.

## Provenance

Filed 2026-05-09 alongside `GOV_GAP_PUBLIC_GATE_CONFORMANCE_001` after a brainstorming pass with `~/git/wicket` and ChatGPT. Wicket is the methodology proof-of-concept from outside AG; `docs/doctrine/validator_contract.md` is the proof-of-concept from inside AG. This gap names the methodology that bridges them.

Per the global YAGNI-scope rule (`~/.claude/CLAUDE.md`): "A record is not authorization to build. It is a handle for review. Name early. Ratify lazily. Implement only when the current task, failure mode or acceptance criteria justify it." Methodology choices for kernel surfaces have a retrofit cost curve that rises with usage — once consumers grow against an undocumented gate's de-facto behavior, lifting that behavior into SPEC discipline incurs migration cost. Naming early preserves the option without committing to authoring work.

The dangerous-version pair from the sibling gap applies here too: this is *not* a "rewrite AG documentation" proposal. It is a posture record. AG's existing test-led doctrine for elaborator internals stays as-is; the SPEC-led posture is proposed only for the kernel-shaped surfaces partition that the sibling gap names.
