# Refusal and Outcome Vocabulary

> **The model may propose; it may not mint standing, admit itself, spend twice, or cite what was never witnessed.**

This document is the closed-vocabulary reference for the AG MVP. It enumerates the eleven refusal kinds, the one bypass kind, the descriptive positive markers, and the five outcome classes. Each set is sealed against ontology drift: changes require explicit S4-lite reopen.

## Closed set — refusal kinds (11)

Verbatim from `src/governor/linear_accountant_client.py::CLOSED_REFUSAL_KINDS` (ratified at the S4-lite naming checkpoint 2026-06-09 via codex adversarial nomenclature review). Each kind is a SPEC-visible failure shape with its own receipt fields; collapsing any of them under a broader kind would make `governor why <receipt-id>` unable to distinguish them.

```
standing_required
standing_expired               (standing-layer expiry; NOT LA token expiry)
admission_denied
admission_gap_accounted
capacity_refused               (LA InsufficientCapacity; AND LA Denied at request)
already_consumed               (LA AlreadyConsumed; the replay-kill)
dangling_receipt_reference     (AG-side admission_receipt_id miss;
                                also covers D3 citation existence-fail
                                and kind-fit-fail)
token_expired                  (LA Expired — distinct from standing_expired)
token_revoked                  (LA Revoked)
unknown_token                  (LA UnknownToken — distinct from
                                dangling_receipt_reference)
scope_mismatch                 (LA ScopeMismatch — scope disagreement,
                                not capacity)
```

### Semantics

- **`standing_required`** — emitted at `standing_seam` when the cooked context carries an empty `standing_receipt_id`. Pre-call refusal; the verifier is never consulted; downstream call count is zero.
- **`standing_expired`** — surfaced at the scenario layer when the standing-side expiry path fires. NOT the same as `token_expired` — this is the standing receipt's own lifecycle state.
- **`admission_denied`** — emitted at `wicket_seam` (precedence / revocation / scope rejects) or at `la_seam` (no `admission_receipt_id` present pre-call). Terminal: the basis was structurally inadmissible.
- **`admission_gap_accounted`** — wicket admitted with a gap. The chain **proceeds**; the proposal packet carries `gap_receipt_id` + `produced_under_gap=true`. See §accounted-gap.
- **`capacity_refused`** — LA `Denied` at request, or LA `InsufficientCapacity`. Budget-shaped refusal, distinct from the more specific token-state kinds below.
- **`already_consumed`** — LA `AlreadyConsumed` on a second consume with the same `consumption_event_id`. The replay-kill. Downstream effect counter does not increment.
- **`dangling_receipt_reference`** — a cited receipt id was not found in the store. Three loci: (a) AG-side `admission_receipt_id` miss at the LA seam, (b) D3 proposal-validator existence-check fail (`evidence_bundle["citation_check"] = "existence"`), (c) D3 kind-fit fail (`citation_check = "kind_fit"` — cited id exists but its structural kind is wrong for the slot).
- **`token_expired`** — LA `Expired`. Token has lapsed; distinct from standing-layer expiry.
- **`token_revoked`** — LA `Revoked`. Token explicitly invalidated.
- **`unknown_token`** — LA `UnknownToken`. Distinct from `dangling_receipt_reference` because the failure is at the LA side (token not in LA's ledger), not at the AG receipt store.
- **`scope_mismatch`** — LA `ScopeMismatch`. The consume scope does not match the grant scope; not a capacity shortage.

## Closed set — bypass kinds (1)

```
BA3_BYPASSED_FOR_MVP
```

Not a refusal. Emitted by the runtime supervisor / D0 harness at suppression time when an AG-internal BA3 budget surface is bypassed in honor of the `SpendabilityAuthority = LA_ONLY` contract from C0-resolved. (Source: `src/governor/linear_accountant_client.py::BYPASS_BA3_FOR_MVP`.)

`governor why` renders this kind with a `BYPASS` prefix (not `REFUSED`) plus a pointer to `working/post-mvp-debt-ba3-hardshort-to-la.md`. Stays visibly weird by design — it must not look like a denial.

### BA3 bypass-as-debt rendering rule

In the poster (`src/governor/drill_poster.py`), the four BA3 surfaces (`RunBudgetLedger`, `ExecutionBudget`, `ExplorationBudget`, routing `Budget`) render under the section header:

```
Bypassed AG-internal budget guards [BA3 — POST-MVP DEBT]:
  - RunBudgetLedger        bypass_ag_rcpt_<not_minted>
  - ExecutionBudget        bypass_ag_rcpt_<not_minted>
  - ExplorationBudget      bypass_ag_rcpt_<not_minted>
  - routing Budget         bypass_ag_rcpt_<not_minted>
```

The `<not_minted>` placeholder is operator-default (the "default to (a)" rule from D0e). The bypass *is the absence of those guards interfering*; no real BA3 receipt id is fabricated. Adding real BA3 emission paths is post-MVP debt — never in MVP scope.

The harness assertion `no BA3 denial fired during any spine run` (`src/governor/drill_poster.py::_detect_ba3_denial_with_root`) fails the demo if any emitted receipt carries `refusal_kind == BYPASS_BA3_FOR_MVP`. Any such occurrence means refusal happened at the wrong authority.

## Descriptive positive markers

These are NOT a typed positive-verdict enum. They are open `evidence_bundle` fields that describe what kind of positive receipt was emitted at each seam. They surface in `governor why` so the operator can tell a granted-capacity receipt from a verified-standing receipt without parsing prose.

- **`verified_standing`** — set to `True` by `standing_client._emit_verified_receipt` on standing-side positive receipts. Read by D3's kind-fit guard.
- **`la_outcome`** — set to `"Granted"` on `_emit_grant_receipt`, `"Consumed"` on `_emit_consume_receipt`. Distinguishes the two LA-seam positive receipts (both use `gate="la_seam"`).

These are descriptive only. The validator gates (D3 `_validate_standing_citation`) read them as structural attributes; they do not constitute a closed enum that could be widened ad hoc.

## Closed set — outcome classes (5)

Verbatim from `src/governor/drill_poster.py::CLOSED_POSTER_OUTCOMES`. These classify whole runs, not individual receipts.

- **`refused`** — a gate refused before its callable was invoked; downstream call-count past the refusing gate is zero; a refusal `GateReceipt` was emitted naming its `refusal_kind` from the eleven closed kinds. Runs 1, 2, 3, 5 in the gauntlet land here.
- **`accounted_gap`** — wicket admitted with `admission_gap_accounted`; the chain proceeded; the proposal packet carries `gap_receipt_id` + `produced_under_gap=true`. **Not a refusal; not success.** See §accounted-gap below. Run 4.
- **`already_consumed`** — collapses scenario 5's specific terminal state. The first consume succeeded (`effect_count=1`); the second consume returned LA `AlreadyConsumed`. Separated from `refused` at the outcome layer to make the linearity beat legible on the poster.
- **`effect`** — the chain reached `Consumed` and emitted the deterministic proposal packet. The control group, not the product. Run 6.
- **`validator_refused`** — the D3 proposal-validator seam refused a citation. Always paired with `dangling_receipt_reference` in the MVP. D3.

## Accounted-gap semantics

`admission_gap_accounted` and the `accounted_gap` outcome class are the only places in the MVP where consequence-bearing work happens under acknowledged epistemic debt.

Mechanics (`src/governor/drill_runner.py::run_drill` + `build_proposal_packet`):

1. Wicket admits with `surface_verdict="authorized"` but flags the gap; the emitted admission receipt records the gap.
2. The chain proceeds — LA grants, LA consumes, the proposal packet is emitted.
3. The proposal packet adds two fields:
   - `gap_receipt_id` — the wicket admission receipt id (`receipt_ids[1]` in canonical chain order),
   - `produced_under_gap = True`.
4. The poster row shows `↷ accounted_gap` (the `↷` glyph distinguishes it from a refusal's `✗` and an effect's plain text).

The harness assertion `run 4 proposal carries gap_receipt_id + produced_under_gap=true` verifies the citation. Run 4 is **not** success-washed in the poster: the outcome word is `accounted_gap`, not `effect`. A reader who skips the rest of the row still sees that the run carried a gap.

The doctrinal point: refusal-discipline is not maximal blocking. Some basis-incompleteness is admissible *with explicit accounting*. The gap is receipted; the work happens; the receipts disclose the debt.

## Out of scope (closed; do not extend in this MVP)

- No new refusal kinds. Per S4-lite ratification, the eleven-kind set is sealed; additions require explicit S4-lite reopen.
- No renamed ticket labels. The poster's ratified vocabulary (`POSTER_HEADER`, `POSTER_INCIDENT`, outcome row strings, harness assertion labels) is micro-frozen.
- No new outcome classes. The five-class set is closed.
- No typed `ArtifactKind` / `UseKind` enums. Kind-fit in D3 is a guard against existing structural attributes, not a typed taxonomy. See `memory/feedback_kind_fit_is_guard_not_enum.md`.
