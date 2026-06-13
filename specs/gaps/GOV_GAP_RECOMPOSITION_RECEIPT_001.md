# GOV_GAP_RECOMPOSITION_RECEIPT_001

## Title

RecompositionReceipt + boundary accounting: the typed refusal for laundering at the
decompose→recompose seam. "All slices passed" must not imply "the whole is admissible."

## Status

Gap spec — **proposed, awaiting one-nod ratification.** Phase 0 deliverable of
`working/campaign-workflow-kernel-annealing.md`. No build is authorized by this filing;
the first build slice (Phase 1) enters the backlog only after ratified acceptance criteria
+ loop AUDIT selection.

## Origin

2026-06-12 operator/ChatGPT design session ("recomposition is where laundering usually
happens"), reconciled against `specs/core/SELF_GOVERNANCE_SPEC.md` §No Epistemic Laundering
(same path-not-value principle, different plane: the spec polices θ/U_t; this gap polices
*work*). Doctrine: `docs/doctrine/annealing_and_recomposition.md` §2.

**The refusal that cannot be expressed today** (grain-of-refusal justification): a run whose
slices all individually passed, but where an admitted decomposition boundary was silently
dropped, narrowed, or substituted between decomposition and recomposition. Today nothing
types that as a refusal — success of the parts launders the whole. The masked-exit scar
(`cargo test | tail`, migration 058) was the single-witness version of this bug;
`verify.py` closed it for one witness. This gap closes it for the *aggregation* of
witnesses.

## What exists

1. `verify.py` — per-verifier exit-status custody (the witness end of the seam).
2. `cooked_context_orchestrator.py` — typed chain results (`OperationalConsumed` /
   `DemonstratedConsumed`), receipts at every seam, origin fence. The first wiring point
   (operator-pinned 2026-06-12: orchestrator, immediately after `ChainResult`; the loop FSM
   stays doc-side).
3. `gate_receipt.py` — content-addressed receipt substrate the new receipt rides on.
4. Loop protocol AUDIT phase (doc-side) — the process-level recomposition this receipt will
   eventually also describe (deferred; see non-goals).

## What needs building

1. **`RecompositionReceipt`** (frozen dataclass, `src/governor/pipeline_types.py`):
   `projected_intent_hash`, `fidelity_class`, `boundaries_admitted: list[str]` (IDs minted
   at decomposition), `boundaries_accounted: dict[str, str]` (id → completed | failed |
   parked | refused), `losses_declared: list[str]`, `la_spend` summary, `accepted_by_kernel`
   (which kernel/profile rendered the verdict — provisional naming allowed in shadow),
   `shadow: bool` / `effective: bool`, source receipt ids, verdict.
2. **`account_boundaries(admitted, accounted) -> verdict`** — pure, total: every admitted
   boundary must appear with a disposition; any unaccounted boundary forces
   `refused_laundering` regardless of slice success. The anti-laundering teeth in one
   function.
3. **Verdict vocabulary** (closed): `admissible`, `admissible_partial_progress` (losses
   declared and within fidelity budget), `refused_laundering` (unaccounted boundary),
   `refused_<gate>` (upstream gate refusal carried through).
4. **Shadow emission** at the orchestrator seam: after `ChainResult`, emit the receipt with
   `shadow: true / effective: false`. Blocks, gates, retries, and mutates nothing.
5. **Golden fixtures**: replays of existing receipt trails (a cooked-context chain run; a
   loop AUDIT cycle) through `account_boundaries`, plus one synthetic dropped-slice fixture
   that must yield `refused_laundering`.

## Acceptance criteria (Phase 1 slice)

- AC1: `account_boundaries` is total — property test over synthetic decompositions; an
  unaccounted admitted boundary always forces `refused_laundering`.
- AC2: synthetic laundering fixture (slice dropped between decompose and recompose, all
  remaining slices green) yields `refused_laundering` in shadow.
- AC3: shadow non-interference teeth — downstream call counts unchanged when the shadow
  verdict is `refused_laundering` (call-count-zero style assertion).
- AC4: full suite green with zero modifications to existing tests.
- AC5: receipt carries `shadow: true / effective: false` explicitly; names its accepting
  kernel/profile as provisional; cites source `ChainResult` receipt basis.
- AC6: verdicts derive from receipted facts only — no log-string parsing anywhere in the
  verdict path (verifier exit status arrives via `verify.py`-shaped receipts).

Enforcement flip (`refused_laundering` actually blocks) is **Phase 3b**, hard-gated on the
Phase 3a activation/rollback drill passing (operator amendment 2026-06-12: one new
enforcement surface per release band).

## Non-goals

- NOT a receipt_kernel invariant in v1 — stays app-level in `src/governor`; constitutional
  promotion into the 13-invariant kernel would need its own supersession-grade ceremony.
- NOT a codification of the loop-protocol FSM (stays doc-side until the receipt shape has
  scars; a loop-AUDIT projection is a Phase 4 candidate).
- NOT enforcement in Phase 1–2 (shadow only).
- NOT a generic workflow engine; the receipt describes recomposition, it does not execute it.

## Open questions

1. Boundary ID minting discipline: content-addressed from slice spec vs sequential per
   decomposition — pick at Phase 1 implementation, bias content-addressed.
2. Does `refused_<gate>` carry the upstream refusal kind verbatim (LA-style closed
   vocabulary) or by receipt reference only? Bias: reference + kind, never prose.
3. Where does the partial-progress / fidelity-budget comparison run when fidelity_class is
   absent (pre-fidelity callers)? Bias: absent fidelity ⇒ treated as `exact` for shadow
   reporting, never for enforcement.
