# GOV_GAP_WORKFLOW_KERNEL_PROTOCOL_001

## Title

TransformationPipeline protocol + profiles + intent fidelity classes: the generic workflow
kernel that names what the cooked-context orchestrator already instantiates, with the layer
badges that prevent the primitives from becoming adaptive soup.

## Status

Gap spec — **proposed, awaiting one-nod ratification.** Phase 0 deliverable of
`working/campaign-workflow-kernel-annealing.md`. No build authorized by this filing.

## Origin

2026-06-12 design session: the governor's pipelines are first-class typed transformations
(text→action, event→action, data→action, claim→verdict, evidence→standing, slice→packet,
packet→publication), each with a different admissibility rule, all sharing one skeleton.
The reusable primitive is `TransformationPipeline<Input, Output, Witness, Verdict>` with the
invariant: *output is not admissible unless its recomposition can account for every admitted
decomposition boundary* (teeth live in GOV_GAP_RECOMPOSITION_RECEIPT_001).

**The refusal that cannot be expressed today:** "this stage transition discarded
scope/basis/witness/exit-status/recomposition-rule/publication-boundary without a receipt."
The six preserved properties exist as scattered discipline (verify.py for exit status,
scope.py for scope, egress for publication) but no type asserts their joint preservation
across a pipeline.

## What exists

1. **`cooked_context_orchestrator.py`** — the reference instance: wicket → standing-
   spendability → LA request → LA consume, origin fence, typed consequence split. The
   protocol is extracted FROM this; the orchestrator is not refactored before Phase 3.
2. **`intent_compiler.py`** — intent projection with mode-gated `IntentFormPolicy`
   (TEMPLATE_ONLY / VALIDATED_CUSTOM / CUSTOM_OK), deterministic compilation, escape
   classification, receipts. Structurally parallel to fidelity but semantically distinct:
   form policy is *how intent enters*; fidelity is *how much loss is licensed downstream*.
   Do not merge the enums.
3. **`executor.py`/`execution.py`** — step loop with budget check → invariant verify →
   checkpoint; `lanes.py` CascadeExecutor — routing/escalation; `spine.py`/`invariants.py`
   — the slice-kernel surface; `policy_engine.py` — abstract verdict substrate.
4. **`docs/loop-protocol.md` FSM** — the process-level pipeline, deliberately doc-side.
5. Kernel-level occupants per `docs/doctrine/annealing_and_recomposition.md` §3 layer-badge
   table — the hierarchy maps to EXISTING components; this gap adds no new kernel classes.

## What needs building

1. **`src/governor/pipeline_types.py`**: `TransformationPipeline` Protocol (~4 methods:
   `project_intent`, `decompose`, `execute`, `recompose`), `ProjectedIntent`, `SliceSpec`
   (with minted boundary IDs), `SliceResult`, `PipelineProfile` (pipeline_type,
   fidelity_default, checkpoint seams, verifier contracts, decomposition caps).
   Thin protocol + frozen dataclasses; no engine, no base-class behavior.
2. **Fidelity classes on intent**: `intent_compiler.py` gains optional
   `fidelity_class ∈ {exact, bounded, heuristic, exploratory}` + `losses_declared` + loss
   posture on `IntentCompilationResult` and its receipt — defaulted, unenforced in Phase 1.
   Judged at recomposition (declared vs actual losses), shadow-assessed first.
   LA echoes `fidelity_class`/`loss_budget_ref` opaquely; zero LA change
   (`working/seam-la-fidelity-pools.md`).
3. **Two profiles, sequenced**: `self_governance` (text→action over the loop discipline;
   no masked verifier exits, no scope widening, dogfood-before-cargo, publication windows)
   ships first; `ops_nq` (testimony workflows: claim→verdict, coverage/freshness/silence
   invariants) is **constructor-refused absent a self-governance promotion receipt**
   (Phase 4; dogfood before cargo, mechanically).
4. **`accepted_by_kernel` discipline**: every recomposition names the kernel/profile that
   accepted it (provisional naming allowed while shadow).

## Acceptance criteria

- AC1 (Phase 1): protocol + dataclasses land with golden-fixture tests only; no existing
  call sites change; the orchestrator's existing behavior is *describable* by the protocol
  vocabulary without modification (shadow receipt proves it).
- AC2 (Phase 1): `intent_compiler` emits fidelity_class + loss posture on its receipt;
  defaults preserve current behavior bit-for-bit; full suite green.
- AC3: profiles are config + receipts, not class hierarchies — a profile is serializable
  and content-addressable.
- AC4 (Phase 4): ops_nq constructor refusal absent self-governance promotion receipt is a
  typed, tested refusal.
- AC5: `IntentFormPolicy` and fidelity_class remain distinct enums with distinct receipts
  fields (anti-merge pin test).

## Non-goals

- NO new kernel classes for system/app/workflow/slice levels — the hierarchy maps onto
  existing components (receipt_kernel/validator = system; spine/policy_engine = app;
  orchestrator/intent_compiler/lanes = workflow; spine budgets/verify = slice).
- NO workflow engine / executor rewrite; `AutonomousExecutor` and `CascadeExecutor` are
  untouched.
- NO loop-protocol FSM codification (doc-side until the receipt shape survives contact).
- NO governor-as-a-service surface; this is the singular-instance track.
- NO LA/wicket/standing contract changes (cross-repo scout 2026-06-12: all composition is
  AG-internal; wicket admission of deltas wraps as authorize-class intents).

## Open questions

1. Pipeline-type registry: closed enum now vs string + registry? Bias: closed enum of the
   seven named types; extension is a vocabulary change, not a runtime registration.
2. Do `SliceSpec` boundary IDs subsume work-reservation scopes (`reservations.py`) or stay
   parallel? Phase 2 question; bias parallel until a conflict fixture forces it.
3. Is `ProjectedIntent` a new type or an alias over `IntentCompilationResult`? Bias: thin
   new type holding the compilation result + fidelity block, to keep intent_compiler
   unaware of pipelines.
