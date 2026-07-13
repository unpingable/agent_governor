# S6 sandwich — surfaced authority-model findings (operator ruling needed)

> Adversarial refuter: codex gpt-5.5, read-only, against the frozen basis
> **maude `6a35965`** + **agent_gov `dc0a383`**. Verdict: "Claim refuted. Modes
> 1, 2, 4, 6 land." Modes 3 (two-sources) + 5 (axis creep) confirmed SAFE.
> The three MECHANICAL findings (#3 TOCTOU, #4 newline aliasing, #5 type
> confusion) are FIXED in maude `a48df3b`. This note records the two the
> refuter rated Critical — both **pre-existing admission-model gaps** S6
> inherited, not regressions it introduced. They need an operator ruling
> because closing them changes contracts (approval-witness format; §7
> value-verification), not just code.

## Severity context (read first)

Both findings degrade **paper** authority guarantees, not (yet) live execution:
the grant is `enforcement: declared-effects-only` (nothing armed — no
SyntheticCage/seccomp), and the runtime supervisor still gates every tool call
independently. So neither yields RCE today. What they break is the *legibility*
claim S6 was built to make — "the operator approves what's real" — by letting a
plan assert authority backing it does not have. That is exactly the class S6
cares about, so they are recorded, not waved off.

## Finding 1 (codex Critical) — §7 citations are not value-verified

**What.** `admit_for_execution` verifies that each load-bearing citation
*resolves* and (for `sha256:` refs) that the resolved bytes hash to the cited
digest. It does **not** verify that a `governance.projected` value MATCHES its
cited source. So a v1 plan may cite `execution_request.commands` against a
benign RationCard while the actual declared commands (e.g. `rm -rf /`) are
nothing the ration authorizes — admission passes, and the commands are copied
into the grant (which, in the compression path, auto-approves them silently).

**Pre-existing?** Yes. In v0 the commands were *pulled from* the ration
(bounded by it); the v0 `scope_allowlist` projected-citation was likewise
presence-checked only, never value-compared. S6 makes it more consequential
because v1 commands are now **plan-declared**, so a false citation is now a
false claim about command authority rather than a no-op.

**Note the design note over-promised.** `design-s6-execution-request-schema.md`
§7 says "`execution_request.commands` disagrees with the cited RationCard →
`governance_ref_mismatch`." That behavior is **specified but not implemented**
(true in v0 for `scope_allowlist` too). The note should be corrected or the
behavior built.

**Fix shape (needs ruling).** At admission, for a projected
`execution_request.{commands,write_paths}` citing a RationCard: resolve the
ration, parse it, and verify containment (declared ⊆ allowed) → else
`governance_ref_mismatch`. This couples maude admission to the RationCard schema
(currently only the v0 projector parses it) and raises a policy question: should
a governed plan be *required* to cite its request against an AG object, or is an
uncited request an author-asserted "these are my own, not AG-derived" (the v0
§7 stance)? The ration containment check is the high-value half; the
require-citation half is the policy call.

## Finding 2 (codex Critical) — approval is not bound to plan bytes

**What.** A governed plan cites `approval_ref` (e.g. `"operator:act-1"` or a
witness filename). Admission checks the ref *resolves* to witness bytes (and, if
the ref is a `sha256:`, that they hash to it) — but **never that the approval
act names `env.plan_ref`**. So Plan B can reuse Plan A's approval witness and
admit: approval replay. The doctrine "approval attaches to plan bytes" is
literally violated — the witness attaches to nothing verifiable about the plan.

**Pre-existing?** Yes — entirely. This is v0 admission behavior; S6 did not
touch approval binding. The NS-1 first run relied on a colocated witness file
resolved by name; nothing bound it to NS-1's bytes.

**Fix shape (needs ruling).** The approval witness must name/bind `plan_ref`
(e.g. the witness content includes the plan_ref, and admission checks it; or the
`approval_ref` format carries the plan_ref and must equal `env.plan_ref`). This
is an **approval-witness contract change** that ripples the NS-1 / NS-1R
approval procedure (README steps) and any operator tooling that mints witnesses.
Its own slice.

## Recommendation

- **Mechanical seam of S6 is sound** (refuter confirmed the discrimination,
  frozen-gating, two-sources, and axis handling; the three mechanical holes are
  fixed). S6's *own* claim — first-class request block, versioned contract,
  frozen v0 — stands.
- **Findings 1 & 2 are the admission model around it**, pre-existing, and
  inert-to-execution while unarmed. Rule on them as a follow-up: (a) build the
  §7 ration-containment check (finding 1, arguably completes an S6 design-note
  promise), and (b) schedule the approval-binds-plan-bytes contract change
  (finding 2, its own slice). Neither should be silently folded into S6 at
  session-tail.

Full refuter transcript retained in the session scratchpad
(`s6_codex_out.txt`); provenance = codex gpt-5.5, read-only, 2026-07-13.
