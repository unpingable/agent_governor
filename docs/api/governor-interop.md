# Governor Interop Contract (v0 framing)

**Status: CANDIDATE — positioning umbrella, non-binding.** Provenance: operator +
ChatGPT framing, 2026-07-05 ("Maude is the tell"). This is **not a new law table** —
it is the umbrella over the interop artifacts that already exist. The normative
shapes live in [`work-container-contract.md`](work-container-contract.md),
[`provider-integration.md`](provider-integration.md), and
[`agent-integration.md`](agent-integration.md); the callable surface already lives in
the daemon RPCs. This doc adds *positioning and a gap list*, nothing law-bearing.

> The interop contract is a **projection of AG decisions** for external harnesses. It
> is not the source of governance truth.

## The positioning

Once Maude is a real operator shell, AG stops being "an internal daemon with vibes"
and becomes a **governance service with consumers** — a constitutional kernel with a
stable syscall boundary. The law:

> **Agents may ask. Harnesses may perform. Only AG admits.**

**Maude is not special — it is the first serious consumer.** The boundary is one
boring treaty every adapter signs:

```
Agent / Harness / Runtime  →  candidate plan or actor output  →  AG interop surface
   →  admissibility / refusal / review packet / receipts / ration+standing state
   →  Maude, Night Shift, NQ, Porter, dashboards, humans
```

AG must **not** become an octopus of adapters. Maude consumer-facing, Porter
courier-facing, NQ witness-facing, Night Shift run-facing, Claude/Codex/Hermes
actor-facing — AG stays the admission authority behind one narrow projection.

## The dangerous wrong version (explicitly refused)

> "Make AG callable by agents so they can govern themselves." — laundering with a
> socket.

A harness may **submit** `actor_output.v0` claiming "implemented X"; AG replies with
a decision that separates supported from unsupported claims and never treats the
submitter's framing as authority. The submitter's `claim` is input to review, never a
verdict.

## Three contracts Maude forces (mapped to what exists)

### 1. Ingress contract — things entering governance
bounded plans · actor outputs · receipt packets · transcripts · proposed memory/skill
updates · proposed standing/ration uses.
- **Exists:** `intent.compile` / plan-envelope-v0; playbook queue + `QueuedPlaybook`;
  `runtime.session.create/launch`; `ActorOutputNormalizer` (actor can't self-green).
- **Gap:** a single named `submit_plan` / `submit_actor_output` / `submit_receipt_packet`
  front door that unifies these under the WorkContainer projection.

### 2. Decision contract — "what happened?"
admitted · refused · blocked · obstructed · candidate-only · needs-human-review ·
keep/discard-pending · promotion-eligible · stale-substrate · classifier-boundary-hit.
- **Exists:** `chain.preflight` (`allow|would_block|blocked`); `operator.decisions.list`;
  `runtime.promotion.get/diff/resolve`; `receipts.list/detail`; gate-receipt verdicts
  (`pass|warn|block|observe|proceed`); `why.chain` / `explain`.
- **Gap:** a stable `query_decision` / `explain_refusal` projection that renders these
  in the boring vocabulary Maude already surfaces (V1 labels).

### 3. Receipt contract — what downstream must preserve
what was claimed · who claimed it · what evidence exists · what is self-authored ·
what was independently verified · what was promoted · what remains candidate · what
authority (if any) was consumed.
- **Exists:** `gate_receipt` + evidence store; `ReviewPacket` (`used ≤ granted`);
  `provider_run_receipt.v1` / `provider_obstruction.v1`; `work_container.v1` custody.

## Verbs (a projection of existing RPCs, not new authority)

`describe_capabilities` · `submit_plan` · `request_admission` · `submit_actor_output`
· `submit_receipt_packet` · `review_packet` · `record_obstruction` · `query_decision`
· `query_standing` · `acknowledge_keep_discard` · `explain_refusal`. **Method names
may move; the ABI (envelopes) is what harnesses build against.**

## Envelopes (the ABI — mostly shipped)

`WorkContainer.v0` ✓ · `ReviewPacket.v0` ✓ · `RationCardRef` (scope/ration projection)
✓ · `GovernedPlanBinding` ✓ · `Refusal`/`Obstruction` (`provider_obstruction.v1`,
closed refusal classes) ✓ · `ActorOutput.v0` (gap — a named inert-actor-output
envelope) · `ReceiptPacket.v0` (partially covered by `provider_run_receipt.v1`) ·
`PromotionCandidate.v0` (gap — a named promotion-eligibility envelope).

## Minimal v0

1. submit bounded plan · 2. submit inert actor output · 3. submit receipt packet ·
4. return review packet · 5. return refusal/obstruction · 6. return keep/discard
pending state.

## Explicitly NOT v0 (the badge-refusal list)

live autonomous execution permission · agent self-standing · write authority ·
promotion authority · model-routing authority · fallback-around-refusal authority ·
memory-update minting. Otherwise every vendor-shaped thing shows up wearing a
"but I'm integrated with Governor" badge. No.

## Naming

Avoid "AG API" as the primary object (too implementation-shaped). Prefer **Governor
Interop Contract** / **AG External Projection**. Do not let `WorkContainer` become a
second fake law table — it is a projection, and this umbrella keeps it one.
