# GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001

## Title
The authority/admissibility mint should likely be promoted to a Rust kernel earlier than previously assumed. This is a substrate-placement strategy record, not an Agent Governor rewrite.

## Status
Gap spec — strategy record. **No implementation, no kernel-interface design, no packaging decision (PyO3 vs sidecar vs CLI), no AG-wholesale port is ratified by this filing.** Names the substrate-placement question as architectural timing debt and preserves optionality before consumers grow against a Python mint.

## Origin

Filed 2026-05-07 after a three-substrate convergence pinned the construction-discipline gap (`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`) and its substrate caveat: Lean (formal-theorem side, `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`), Ada (`standing_spark` probe, structural-sealing demonstration), and Common Lisp (negative result — closure/capability mints spoofable by stateful protocol mimicry). The convergence sharpened the read on substrate guarantees:

- Ada / Rust / Lean: **structural** construction discipline available.
- Python / Common Lisp: **conventional** construction discipline only — anti-laundering, not unforgeability.

Agent Governor's implementation language is Python. The mint, if built in Python, will at best be anti-laundering. That is a real and valuable bar — but if the mint becomes the load-bearing surface for action-bearing authority across consumers, the substrate ceiling becomes a liability rather than a current limit.

The strategic question that surfaces:

> If the mint must exist, and the substrate ceiling is real, **when** does the substrate decision get made — before consumers grow against a Python mint, or after?

The cost curve favors before. This gap is filed to name the question before the answer is foreclosed by accidental ABI.

## Core Claim

> **Move the mint, not the metropolis.**

The authority/admissibility mint should likely be promoted to a Rust kernel sooner than the rest of Agent Governor. The rest of AG — orchestration, policy loading, receipt plumbing, CLI/API glue, integration workflows — has no compelling reason to leave Python. Only the mint has one.

This is **not**:

- A proposal to rewrite Agent Governor in Rust.
- A proposal to design the kernel interface tonight.
- A ratification of PyO3 / FFI / sidecar / CLI as the integration shape.
- A claim that Rust solves wire provenance — it does not. Once an authority value crosses a serialization boundary, it becomes a claim again unless revalidated.

This **is**:

- A strategy record that the mint's substrate placement is a decision worth naming early.
- A guardrail against accidental ABI: a Python authority mint, once consumers depend on its types and method signatures, becomes archaeology to migrate.

## Problem Statement

The doctrine in `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001` requires a mint that emits `AuthorizationVerdict` from `(basis × standing × scope × effect)`. The substrate caveat on that gap establishes that a Python implementation can achieve anti-laundering (grep-visible construction sites, recognizable forgery) but not structural unforgeability. That ceiling is acceptable for many use cases.

It is **not** acceptable when:

- The mint output crosses a process or substrate boundary into a less-trusted context.
- Consumers grow that depend on the mint's behavior, types, and ergonomics — at which point migration is structurally expensive and politically harder.
- Authority-bearing deployments expect the substrate guarantee, not the convention.

The timing question is the gap. If the Python mint ships first and accumulates consumers, a later substrate move incurs:

- Migration archaeology (consumer-by-consumer port).
- ABI freeze on whatever shape the Python mint happened to expose.
- Loss of optionality on one-shot / non-`Clone` / non-`Copy` authority semantics that Python cannot express but Rust can.
- A retrofit cost curve that rises with usage spread — exactly the "name early, ratify lazily" scenario the global YAGNI rule covers.

Naming the substrate decision now preserves three options:
1. Build the Python mint first as anti-laundering, port to Rust later (acceptable if migration cost stays bounded).
2. Build the Rust kernel first, treat Python as caller (lower retrofit cost; higher upfront cost).
3. Build both in parallel with the Python version explicitly as a degraded reference (most flexible; most discipline required).

## Existing Governor Coverage / Adjacent Gaps

| Gap / Spec | What it covers | What it does not cover |
|------------|----------------|------------------------|
| `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001` | Construction-discipline gap; substrate caveat (Ada/Rust/Lean = structural; Python/Lisp = conventional); doctrine ("authority observable, not constructible") | Where the mint should be implemented |
| `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001` | Formal/Lean side; bridge theorem `revoked_basis_cannot_be_authorized_step`; verdict algebra | Substrate-of-implementation strategy |
| `~/git/standing` (Rust workload identity) | HMAC-signed `WorkloadId`, content-addressed receipts, CAS on state transitions | Authority verdict emission; admissibility decision algebra |
| `standing.py` integration (slice 2A/2B/2C, per `standing_integration.md` memory) | Identity tokens flowing into Governor (Rust → Python verification) | Mint emission; verdict-emission substrate |
| `receipt_kernel` (libs/receipt_kernel) | Attestation/evidence: "what happened / did invariant pass?" | Authorization: "may this actor act?" — see `attestation_vs_admissibility_split.md` |
| `GOV_GAP_SUBSTRATE_CUSTODY_001` | OS-substrate sandboxing (bubblewrap, action classification) | Programming-substrate construction discipline |
| `VERIFIED_KERNEL.md` | Canonical-JSON unification across receipt modules | Authority kernel substrate |

No existing spec covers the substrate-placement strategy for the authority mint specifically. This gap fills that slot.

## Kernel Shape (informational; not ratified)

The candidate Rust kernel is small. Recorded here for orientation, not as a design commitment:

```text
BasisVerdict + StandingVerdict + ScopeVerdict + RequestedEffect
        ↓
decide()
        ↓
opaque AuthorityToken / AuthorizationVerdict
        ↓
observe() / project() / apply()
```

What Rust would buy:

- Private constructors on the verdict / token types.
- No `Deserialize` for trusted authority types — deserialization produces claims, not authority.
- Optional non-`Clone` / non-`Copy` authority semantics for one-shot tokens.
- Exhaustive `match` discipline when verdicts or effects expand.
- Compile-fail tests for direct construction / duplication.
- A clean type-level distinction between **submitted evidence** and **minted authority**.

What Rust would **not** buy:

- Wire provenance. Once a value is serialized, it becomes shape again unless paired with signing / receipt / re-validation. Distributed trust is a separate problem; not in scope for this gap.
- Performance (not the point).
- Solving the consumer-side discipline problem on the Python orchestration side.

## What Stays in Python

The substrate decision is not "Python is unsafe." It is "Python is fine for everything except the in-process mint boundary." Specifically:

- Orchestration (CLI, daemon, RPC routing).
- Policy loading and registry.
- Receipt plumbing (`gate_receipt.py`, `signal_store.py`, `ledger`).
- Integration workflows (Claude Code adapter, Codex adapter, Gemini CLI adapter, MCP).
- Tool contracts, scope governance, runtime supervisor, intervention queue.
- Tests, telemetry, dashboards, the WebUI.

The slogan: **Python is fine for attestation/orchestration; action-bearing authority wants a substrate with real construction boundaries.**

## Doctrine (proposed; not yet ratified)

> **Rust is the mint. Python is the emulator.**

The Python implementation, if it exists, is a **semantic backport** — same truth table, same API shape where compatible, same refusal modes, same vocabulary — but documented explicitly as anti-laundering by convention, not structural sealing. The two implementations are not peers. Presenting them as peers is the failure mode this doctrine prevents.

Companion guardrail (load-bearing — do not lose):

> **Fallback to the Python backend, when permitted at all, must be observable.** Silent fallback is exactly how "optional" becomes "nobody noticed the safe part wasn't loaded." A serious deployment that loads the Python backend in a path expecting the Rust one should announce it loudly — log line, configuration warning, ideally an explicit opt-in env var or config setting.

## Acceptance Criteria

This gap is closed when a doctrine record exists that:

1. States the substrate-placement claim: the authority/admissibility mint is a candidate for Rust implementation, ahead of the rest of AG, on architectural-timing grounds.
2. Records the cost-curve argument: retrofit cost rises with usage spread; naming the substrate decision before consumers grow preserves optionality.
3. Names the boundary clearly: Rust owns the in-process mint; serialization across boundaries (sockets, files, JSON, log lines) re-creates claims, not authority.
4. Distinguishes the two object classes the boundary implies: an opaque `AuthorityToken` (operational, possibly one-shot, not casually serialized) and an `AuthorizationReceipt` (audit artifact, copyable, serializable, not itself authority).
5. Names the Python-as-emulator framing explicitly: if a Python authority backend exists, it is a degraded-guarantee reference implementation, not a peer of the Rust kernel.
6. States that fallback (if permitted at all) must be observable — opt-in, logged, never silent.
7. Identifies forcing cases that would justify lifting any of the above into binding decisions: a consumer that ships the Python backend to a context where structural sealing was expected; a postmortem in which authority laundering reduced to convention-only enforcement; recurrent pressure to add `Deserialize` / `Clone` on trusted types.

## Non-goals

- **Not a port of Agent Governor to Rust.** The metropolis stays Python. This gap is about the mint, not the city.
- **Not a kernel-interface design.** The kernel shape recorded above is informational; the binding interface design is deferred until forcing cases ratify the substrate decision.
- **Not a packaging-shape decision.** PyO3 vs sidecar vs CLI vs bundled-wheel-with-fallback is candidate territory only; this gap does not pick.
- **Not a wire-provenance solution.** Rust solves in-process construction discipline. Distributed trust requires signing/receipt/re-validation and is out of scope.
- **Not a ratification of "Rust is required."** Rust is named as the substrate that *can* provide structural sealing. Whether the deployment actually requires structural sealing (vs. anti-laundering) is a per-context question.
- **Not a Python-mint-prohibition.** A Python anti-laundering mint may still be the right first move for some deployments. The gap's role is to prevent that choice from becoming permanent by accident.
- **Not "rewrite governance because the bit got spicy."** The convergence (Lean / Ada / CL) supplies the substrate-guarantee distinction; the gap merely files the timing.
- **Not a `~/git/standing` integration extension.** The standing repo's identity-token integration is shipped (per `standing_integration.md` memory). Whether the mint lives in the same repo, an adjacent crate, or a new repo is a separate decision.

## Downstream Effects (candidate; not ratified)

Recorded for orientation. None of the following are ratified by this filing.

**Packaging shapes (each has tradeoffs; none picked):**

- **Rust crate + Python via PyO3.** Best ergonomics for Python users; ships as a wheel; in-process mint boundary inside Rust. Cons: packaging matrix (manylinux, x86/ARM, macOS), FFI lifetime weirdness for one-shot tokens.
- **Rust sidecar binary / daemon.** Best conceptual boundary; language-independent consumers; opaque handles. Cons: install/startup/supervision; wire boundary appears immediately.
- **Rust CLI as first artifact.** Easiest to ship, test, and call from any language. Cons: every boundary is text/JSON-shaped; awkward for token semantics.

**Default-and-fallback shape (ChatGPT's framing, recorded):**

```text
authority-kernel-rust    — default / production / strong construction discipline
authority-kernel-python  — fallback / dev / portability / explicitly weaker substrate guarantees
```

Or config-level:

```yaml
authority_kernel:
  backend: rust         # default for production
  fallback: python      # explicit, logged, requires opt-in
```

**Object-class distinction (load-bearing for any packaging shape):**

```text
AuthorityToken
  operational capability
  opaque
  possibly one-shot / non-Clone
  not serialized casually

AuthorizationReceipt
  audit artifact
  copyable
  serializable
  not itself authority
```

This distinction probably saves the whole boundary. Lose it and Rust's structural guarantees leak across the wire as JSON-shaped claims.

**Phased move (one candidate ordering, not ratified):**

1. Standalone Rust crate / binary proving the mint against a small spec (likely derived from `standing_spark`, `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`, and the Lean kernel shape).
2. Python calls Rust through a brutally narrow interface — minimum surface area.
3. Only then decide PyO3 vs sidecar vs CLI based on what the call sites actually need.
4. Never: AG wholesale port.

## Relationship to Other Gaps / Specs

- **`GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`** — Construction-discipline gap. This gap names *where* its mint should live; that gap names *that* a mint must exist.
- **`GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`** — Formal/Lean side. Substrate-agnostic. Specifies what the mint must compute; this gap names where the mint should be implemented.
- **`~/git/standing` (Rust workload identity)** — Already-shipped Rust substrate adjacent to AG. Whether the authority kernel lives in the same repo, a sibling crate, or a new repo is an open question (recorded below).
- **`standing_integration.md`** (memory, Python-side identity verification, slices 2A/2B/2C) — Identity tokens flow inbound. The mint produces verdicts outbound. Different valves; both cross the Rust↔Python boundary.
- **`receipt_kernel`** — Attestation/evidence kernel. Different role from the authority kernel (see `attestation_vs_admissibility_split.md`). Both already involve cross-language work patterns; the AG codebase has experience to draw on.
- **`GOV_GAP_SUBSTRATE_CUSTODY_001`** — OS-substrate custody (sandboxing). Different layer; complementary.
- **`VERIFIED_KERNEL.md`** — Canonical-JSON unification across receipt modules. Substrate-internal hygiene, not substrate-placement strategy.

## Implementation Sketch (deferred)

Deliberately empty. Implementation is gated on forcing cases beyond the substrate caveat:

- A consumer that ships AG with the Python mint to a context where structural sealing was expected.
- A postmortem in which authority laundering reduced to convention-only enforcement.
- Recurrent pressure to add `Deserialize` / `Clone` on `AuthorizationVerdict` or whatever Python-side trusted type accumulates.
- A second AG-adjacent project (e.g., `~/git/standing` extending into authority emission) that forces the substrate decision by integration deadline.

None of these are present today. The gap exists to be cited when one appears.

## Open Questions

1. Where does the Rust kernel live: extending `~/git/standing`, sibling crate, new repo? `~/git/standing` has shipped the identity-token side; the authority kernel may be the natural next slice.
2. Does the Python orchestration side ever hold an `AuthorityToken`, or only an `AuthorizationReceipt`? The strict reading is "tokens never leave Rust." The pragmatic reading is "tokens may transit Python as opaque handles, never inspected." Which one is canonical?
3. Is the mint pure (basis + chain + scope + effect → verdict) or stateful (consults policy registry, revocation store, evidence ledger at mint time)? Pure is easier to type-check across the FFI/wire boundary; stateful matches what the mint must actually do.
4. Should the Python backend exist at all, or should the Rust kernel be a hard dependency? If Python-as-emulator exists, what trust class is it permitted to operate in? (Dev/test only? CI? Some prod paths with explicit opt-in?)
5. How does the operator-override channel (per `~/.claude/CLAUDE.md` "Operator override") cross the Rust boundary? Operator reaffirmation is currently undeclared in the verdict algebra; if it's a legitimate input to the mint, the FFI/wire shape must carry it explicitly without losing the substrate guarantees on the verdict it produces.
6. What is the test discipline for "Python cannot mint authorization through normal code paths" if the test suite runs in Python? Compile-fail tests are a Rust feature; the Python side requires grep-discipline tests + adversarial fuzzing rather than type-system enforcement.

## Provenance

Filed 2026-05-07 after a three-substrate convergence: Lean (`Authority.lean` / `Execution.lean`, formal-theorem side, `GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001`, filed 2026-04-30), Ada (`standing_spark` probe, 2026-05-06, prompted the original construction-discipline finding and `GOV_GAP_SEALED_OUTCOME_BOUNDARY_001`), and Common Lisp (parallel CL probe, 2026-05-07, negative result that named the substrate-guarantee distinction — dynamic-substrate closure/capability mints are spoofable by stateful protocol mimicry, so they are not "sealed" in the Ada/Rust/Lean sense). The CL finding is what bumped the substrate question from "later concern" to "name-it-now strategy gap" — ChatGPT's diagnosis: the Ada/Lisp sequence changed the risk model. Before, "Python is fine if disciplined" was plausible. After, the sharper read is that action-bearing authority wants a substrate with real construction boundaries, and the Python mint, if shipped first, becomes accidental ABI by procrastination.

The filing is strategy-only. No kernel construction, no interface design, no packaging choice, no AG port is ratified. The gap is named so the substrate decision can be ratified lazily, on forcing cases, before consumers foreclose it.

Keeper phrases (load-bearing across the gap):

> **Move the mint, not the metropolis.**
>
> **Rust is the mint. Python is the emulator.**

The first prevents the wholesale-port mistake. The second prevents the peer-implementations mistake.
