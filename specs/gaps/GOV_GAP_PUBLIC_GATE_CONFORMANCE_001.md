# GOV_GAP_PUBLIC_GATE_CONFORMANCE_001

## Title
Public AG gate surfaces should expose a Wicket-shaped **conformance projection** — verdict, reason codes, receipt hash, and explicit gap/unaccounted behavior — over the same small input bundle (basis × standing × precedence × scope × revocation). Divergence between AG and Wicket on a shared fixture is either a bug, a doctrine mismatch, or evidence that the AG surface is not actually a gate.

## Status
Gap spec — candidate inventory. **No implementation, no test-suite construction, no AG refactor, no Wicket consumption by AG, and no fixture parity work is ratified by this filing.** Names the noticed door and the keeper phrasing; future forcing cases promote.

## Origin

Filed 2026-05-09 after a brainstorming pass with `~/git/wicket` (admissibility preflight kernel, Rust, ~1.4k LOC, SPEC-led, built 2026-05-08/09 as a legibility surface for AG gate doctrine). Cross-checked with ChatGPT in the same session.

The provoking observation: AG has the doctrine but it is distributed across ~60 modules and ~14k tests. Wicket compresses the kernel-shaped doctrine into 684 lines of SPEC + ~1.4k LOC of literal Rust. That compression makes the doctrine *legible* — disagreement-shaped — in a way AG's organic structure cannot be. The natural follow-up question, "should this be a goal for AG itself," surfaced two failure modes and one correct version.

Failure mode A — *architecture anorexia*: "redesign AG around Wicket's shape." AG has earned its weird organs. Most of AG isn't a gate — it's regime detection, scar tissue, runtime supervision, writing-mode constraints, session continuity, interferometry, homeostat. Those are elaborator-shaped, not kernel-shaped. Trying to make the elaborator look like the kernel is what people do when they don't understand why elaborators are big.

Failure mode B — *kernel sovereignty*: "Wicket becomes the validator of AG." Promotes a sibling implementation into a parent authority. Not what Wicket is for.

Correct version — the keeper sentence:

> **AG has kernel-shaped surfaces and elaborator-shaped internals, and the discipline is keeping them from contaminating each other.**

And the load-bearing refinement (ChatGPT, 2026-05-09):

> **"Wicket-fixture-reproducible" should mean verdict-surface reproducible, not reasoning-trace reproducible.**

## Core Claim

> **Every AG public gate should have a Wicket-shaped conformance projection.**

Not "every AG gate is Wicket." Not "AG should call Wicket." Not "Wicket becomes the sovereign validator of AG." The shape is:

```text
AG may elaborate.
Wicket may classify.
Lean may prove.
The public gate surface must be comparable.
```

The conformance projection collapses AG's elaboration into the same small verdict algebra that Wicket exposes:

```text
given this caller-cooked input bundle
  (basis × standing × precedence × scope × revocation × operation_class)
the public gate returns this verdict
  ∈ {authorized, advisory_only, denied, gap, unaccounted}
with this receipt shape
  (content-addressed, RFC 8785 canonical JSON, evidence_hash bundle)
and these reason codes
  (drawn from the Wicket §8.3 registry, or a documented superset)
```

It explicitly does **not** require Wicket (or any third-party verifier) to reproduce:

- how AG discovered or accumulated the basis;
- how scars accumulated and which actions are restricted by them;
- how the regime detector classified the operational state;
- how continuity supplied prior context or anchor evidence;
- how the homeostat's exploration budget shifted;
- how interferometry resolved multi-model disagreement;
- how session continuity rehydrated authority across reconnects.

That is **elaborator territory.** It can — and should — inform the cooked input. It must not leak into the kernel contract.

## Problem Statement

AG's public gate surfaces today are kernel-shaped in *behavior* but inconsistently kernel-shaped in *contract*. `gate_receipt.py` already implements the canonical-JSON content-addressed receipt that Wicket inherits. `evidence_gate`, `intent_compiler`, `scope`, `verifier_gate`, `ci`, and `governed_activity` all emit gate receipts with verdicts. The doctrine *is* there.

What is missing:

1. **A doctrinal SPEC for the gate surface.** AG has 14k tests but no SPEC.md analogous to Wicket's. The gate doctrine is implicit in the test corpus, the gate_receipt contract docs, and the modules' organic shape. An external implementation cannot ratify what it cannot read.

2. **A fixture corpus that is the contract surface.** Wicket's `cases/` is a doctrine-pressure test bank: each fixture is a single Intent and an expected verdict, hash-stable, machine-checkable across implementations. AG has tests, but they are mostly implementation tests, not contract tests against a shared verdict algebra. Wicket fixtures cannot today be replayed against AG to confirm the public verdict matches.

3. **Identification of which AG modules expose public gates and which do not.** The kernel/elaborator partition is real but currently undeclared. Some modules clearly produce verdicts that ought to conform (`evidence_gate`, `verifier_gate`); others clearly do not (`regime`, `homeostat`, `scars`); some are in-between (`scope` produces verdicts but also tracks state across sessions). Without the partition declared, the conformance question has no surface to land on.

The hole is not in AG's behavior. It is in the **legibility of AG's gate surface as a contract** that a sibling implementation could ratify. The right substrate-discipline word is **projection**, not **parity** — AG is allowed to be bigger; the public boundary must collapse cleanly into the shared verdict algebra.

## Doctrine (proposed; not yet ratified)

> **AG public gates emit verdicts in the same small language as Wicket.**

> **AG internals may elaborate freely; the elaboration must not appear in the verdict surface.**

> **Conformance is measured at projection, not at machinery.** Two implementations of the same doctrine may compute the verdict by entirely different means. They must agree on the verdict, the reason codes (or a documented superset), and the receipt shape. They are not required to agree on how they got there.

> **The dangerous-version exclusion is load-bearing.** AG must not be reshaped to look like Wicket. Wicket must not be promoted to validator-of-AG. The doctrine binds the boundary, not the bodies.

The keeper sentence (the thing this gap is named to preserve):

> **AG should know which of its organs terminate in a public gate, and those gates should speak the same small language as Wicket.**

## Existing Coverage / What's Already in Shape

| Component | Already kernel-shaped at surface | Has SPEC | Has fixture-shaped tests |
|-----------|----------------------------------|----------|-------------------------|
| `gate_receipt.py` | Yes (content-addressed, canonical JSON) | Partial (`docs/RECEIPT_KERNEL_CONTRACT.md`) | Partial |
| `evidence_gate` | Yes (verdict + claims + violations + receipt) | No | Implementation tests, not contract tests |
| `intent_compiler` | Yes (compiled-intent + receipt) | No | Implementation tests |
| `scope` | Yes (allow/deny + escalation receipt) | No | Implementation tests |
| `verifier_gate` | Yes (suite verdict + VERIFY_SUMMARY) | No | Implementation tests |
| `ci` (`ci_verify`) | Yes (verdict + meta-receipt) | No | Implementation tests |
| `governed_activity` | Yes (drift verdict + receipt) | No | Implementation tests |
| `regime`, `homeostat`, `scars`, `runtime/`, writing modules, interferometry, session continuity | Elaborator-shaped — out of scope for this gap | n/a | n/a |

The conformance question applies only to the first seven rows. The eighth row is explicitly out of scope and is what makes the dangerous-version exclusion necessary.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. **Names the kernel/elaborator partition explicitly for AG.** A current list of which AG modules expose public gates (kernel-shaped at surface) and which do not (elaborator-shaped throughout). The partition is itself doctrine, not implementation, and is allowed to evolve with new modules.
2. **States the conformance-projection rule.** Public AG gates expose verdict, reason codes, and receipt shape compatible with the Wicket verdict algebra. Reason codes drawn from Wicket §8.3 registry, or a documented superset with named extensions.
3. **Distinguishes verdict-surface conformance from reasoning-trace conformance.** Conformance binds the projection, not the elaboration. AG may discover, weight, accumulate, retract, and re-derive freely upstream of the gate surface.
4. **Identifies the failure modes ruled out:** architecture anorexia (reshape AG to look like Wicket), kernel sovereignty (Wicket as validator-of-AG), reasoning-trace coupling (require AG to expose its elaboration as part of the contract).
5. **Identifies forcing cases that would justify promotion to fixture corpus or test-suite work** (deferred, not ratified by this filing): a gate disagreement between AG and Wicket on a documentable input; a downstream consumer needing to validate AG output against an external admissibility checker; a proposed new AG gate whose doctrine cannot be expressed in the Wicket algebra (which would force either Wicket extension or admission that the surface is not a gate).
6. **Records what is *not* ratified:** no fixture corpus construction, no test-suite migration, no AG refactor, no Wicket-as-dependency adoption, no SPEC.md authoring beyond this gap record.

## Non-goals

- **Not implementing fixture parity tonight.** This filing is a containment vessel; corpus construction is deferred work.
- **Not refactoring AG to "look like Wicket."** Explicit non-goal — architecture anorexia. AG's organic shape encodes real knowledge.
- **Not promoting Wicket to validator-of-AG.** Sibling implementation, not parent authority.
- **Not requiring AG to consume Wicket as a dependency.** Two implementations of one doctrine, not a runtime coupling.
- **Not authoring SPEC.md for AG gates yet** — that is the sibling gap (`GOV_GAP_GATE_DOCTRINE_SPEC_001`), filed alongside.
- **Not a "while here" cleanup of `gate_receipt`, `evidence_gate`, or any other module.** Those are downstream of the partition declaration and the SPEC, and out of scope until those exist.
- **Not a Wicket spec-amendment proposal.** If AG exposes a verdict shape Wicket cannot represent, the response is either a documented superset or evidence that the surface is not a gate — not unilateral Wicket spec growth.
- **Not constraining AG internals.** Elaborator modules (`regime`, `homeostat`, `scars`, etc.) are out of scope and remain free to evolve.

## Relationship to Other Gaps / Specs

- **`GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001`** — Substrate-placement question for the authority/admissibility *mint* (Python anti-laundering vs Rust structural). This gap is the conformance-surface complement: the substrate question is "where does the mint live"; this question is "what does the public boundary of any mint or gate look like to outside readers." Wicket-as-Rust is one candidate substrate for that authority kernel; Wicket-as-conformance-shape is independent of the substrate decision.
- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — Construction discipline on `AuthorizationVerdict`. The conformance projection consumes the verdict the mint emits; this gap is about how that verdict's *shape* must look at the AG public surface.
- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Lean-side bridge theorem (`revoked_basis_cannot_be_authorized_step`). Wicket fixture #9 is the operational shadow of that theorem. Conformance projection extends the relationship: AG, Wicket, and Lean are three implementations of one doctrine, and the bridge theorem is the canonical example of a doctrinal claim each implementation should agree on.
- **`GOV_GAP_GATE_DOCTRINE_SPEC_001`** — Sibling gap (filed in same commit). That gap names the SPEC-led methodology for kernel-shaped AG surfaces. This gap names the conformance projection over whatever those SPECs ratify.
- **`receipt_kernel`** — The attestation substrate AG already uses; Wicket-shaped receipts already pass through `gate_receipt.py` with the same canonical-JSON content-addressing. The conformance projection inherits this directly.
- **`~/git/wicket/SPEC.md` §11.4** — "A future AG kernel (or Lean-checked Wicket) should be able to: (1) read Wicket fixtures unchanged and reproduce the surface verdict; (2) discharge each fixture as a theorem with the dimensional triple as inputs; (3) translate Wicket verdicts into AG verdicts via a stable map." This gap names the AG-side commitment that makes (1) reachable.
- **`~/git/lean/LeanProofs/Admissibility/`** — Formal substrate, frozen as *Admissibility Calculus 1.0* (concept DOI [10.5281/zenodo.20369489](https://doi.org/10.5281/zenodo.20369489); eight-module public surface aggregated via `CalculusOne.lean`). The doctrinal claim of this gap composes: Lean specifies, Wicket implements literally, AG implements with elaboration, all three projections must agree.

## Open Questions

1. **What is the canonical representation of AG's public gate set?** A directory? A registry function? A decorator pattern (`@public_gate`)? An entry in `implementation-summary.md`? The partition is doctrine and needs a stable home.
2. **Does the Wicket §8.3 reason code registry suffice for AG, or does AG need a documented superset?** AG has codes Wicket does not (e.g., scar-related codes, regime-state codes, homeostat tuning codes). Most are elaborator-shaped and would not appear at a public gate surface. The audit is itself the work.
3. **How does the conformance projection interact with `governed_activity` drift verdicts?** Drift is a temporal concept; Wicket is single-call and stateless. The projection may need to record "drift state at call time" as caller-cooked context (revocation-shaped) rather than as a fourth dimension. Worth checking.
4. **Does the projection apply to `runtime/` adapter outcomes (Claude Code / Gemini CLI supervised sessions)?** Adapters emit gate-shaped events at tool boundaries. They may belong in the kernel-shaped column, or may be elaborator-shaped at the session boundary and kernel-shaped only at the per-tool admission moment.
5. **What is the relationship between Wicket fixtures and the existing `tests/` corpus?** Some AG tests are already fixture-shaped and could be promoted to a shared format. Most are not. The migration question is a forcing-case-driven decision, not pre-ratified here.
6. **Is the projection symmetric?** AG → Wicket-fixture is the strong direction (every AG gate has a fixture). Wicket-fixture → AG is the weaker direction (every Wicket fixture is reproducible against AG, allowing for AG's elaborator context). Both, or only one? The asymmetric version is probably honest; the symmetric version is what the "ratification surface" framing implies.

## Provenance

Filed 2026-05-09 after a brainstorming pass with `~/git/wicket` (~1.4k LOC Rust kernel built 2026-05-08/09 as a SPEC-led legibility surface for AG gate doctrine). Cross-checked with ChatGPT in the same session, who provided the load-bearing refinement: *verdict-surface reproducible, not reasoning-trace reproducible*. The keeper sentence — "AG has kernel-shaped surfaces and elaborator-shaped internals, and the discipline is keeping them from contaminating each other" — was articulated jointly and is the thing this gap is named to preserve.

The dangerous-version pair (architecture anorexia, kernel sovereignty) was named explicitly in the conversation that produced this filing, and is recorded in Doctrine and Non-goals so a future session that re-derives the question does not collapse onto either failure mode.

This filing is a **noticed door**, not a roadmap entry. Per the global YAGNI-scope rule (`~/.claude/CLAUDE.md`): "A record is not authorization to build. It is a handle for review. Name early. Ratify lazily. Implement only when the current task, failure mode or acceptance criteria justify it." The retrofit cost curve here rises with usage spread (every AG gate that ships without a conformance-projection check is one more module to retro-fit later); naming early preserves optionality without committing to construction.
