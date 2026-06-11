# Claim-Custody Spine

> **The model may propose; it may not mint standing, admit itself, spend twice, or cite what was never witnessed.**

The claim-custody spine is the chain of seams every consequence-bearing action must traverse before an effect lands. Each seam is a separately receipted boundary; each receipt cites its parent. The chain is auditable end-to-end via `governor why <receipt-id>`.

This document explains the spine through the receipts it produces. Every section below names a gate, a receipt kind, and a parent linkage, and points at the file that implements it.

## Chain shape

```
NQ observation (origin_mode=drill|observed|replay|synthetic)
        │   finding_id
        ▼
standing_seam      ── verifies standing receipt; emits verified_standing GateReceipt
        │   parent_receipt_ids = [<finding_id>]
        ▼
wicket_seam        ── admits the cooked context against precedence/revocation/scope;
        │              emits authorized GateReceipt (or admission_denied / gap)
        │   parent_receipt_ids = [<standing receipt id>]
        ▼
la_seam (request)  ── Linear Accountant CapacityRequest; emits granted GateReceipt
        │              (la_outcome=Granted) or capacity_refused
        │   parent_receipt_ids = [<wicket admission receipt id>]
        ▼
la_seam (consume)  ── Linear Accountant ConsumeRequest; emits consumed GateReceipt
        │              (la_outcome=Consumed) or already_consumed / token_expired /
        │              token_revoked / unknown_token / scope_mismatch
        │   parent_receipt_ids = [<la grant receipt id>]
        ▼
proposal_validator_seam  ── citation existence + kind-fit guard; on the happy path
                            emits no receipt (proposal packet is the artifact);
                            on confabulation emits dangling_receipt_reference
                            parent_receipt_ids = [<la consume receipt id>]
        │
        ▼
(effect)            ── deterministic proposal packet citing receipt ids; no mutation
```

Every gate writes through `GateReceiptSystem` (`src/governor/gate_receipt.py`): receipts go to `{root}/receipts/gate_receipts.jsonl`, evidence blobs to `{root}/evidence/{hash[:2]}/{hash}.json`. Receipt ids are content-addressed. The chain is walkable via `src/governor/why.py::walk_chain`.

## Per-stage details

### NQ observation — `origin_mode={observed,drill,replay,synthetic}`

- **Where:** `nq-monitor`'s production evaluator pipeline (`~/git/nq-root/nq/crates/nq-monitor/src/...`). Migration `057_origin_mode_discriminator.sql` defines the closed CHECK on `origin_mode`.
- **Receipt:** NQ-side `FindingSnapshot` (`nq.finding_snapshot.v1`). Not an AG `GateReceipt` — NQ owns its own receipts.
- **Parent:** none (the chain root).
- **What AG consumes:** `finding_key`, `finding_id`, `identity.host`, `identity.detector`, `origin_mode`, `observed_at` (`src/governor/drill_runner.py::load_finding_snapshot_from_json`).
- **What AG refuses:** `InvalidFindingSnapshotError` at parse time for any shape violation, unknown `origin_mode`, or empty identity.

### `standing_seam` — does the actor have standing?

- **Where:** `src/governor/standing_client.py::StandingClient.verify`.
- **Gate name on receipt:** `standing_seam`.
- **Positive receipt:** verdict `pass`; `evidence_bundle["verified_standing"] = True`. Emitted by `_emit_verified_receipt`.
- **Refusal kinds:** `standing_required` (empty `standing_receipt_id` — pre-call), `dangling_receipt_reference` (verifier returns None). The scenario layer surfaces `standing_expired` for the SCENARIO_STANDING_EXPIRED case (operator-facing classification in `drill_runner._classify_chain_outcome`).
- **Parent linkage:** `evidence_bundle["parent_receipt_ids"] = [finding_id]` — the NQ origin.
- **Anti-pattern:** the seam never resolves standing itself. It only verifies a cited receipt id. The caller cooks; the seam accounts.

### `wicket_seam` — is the cooked context admissible?

- **Where:** `src/governor/wicket_client.py::WicketClient.check`.
- **Gate name on receipt:** `wicket_seam`.
- **Positive receipt:** verdict `pass`; `surface_verdict="authorized"` in the evidence bundle. Emitted by `_emit_admission_receipt`.
- **Refusal kinds:** `admission_denied` (precedence / revocation / scope rejects), `admission_gap_accounted` (chain proceeds with the gap citation — see §accounted-gap below).
- **Parent linkage:** `evidence_bundle["parent_receipt_ids"] = [<standing receipt id>]`.
- **Pre-call invariant:** the wicket client refuses if the cooked context's `standing_receipt_id` is missing or dangling — the seam is never consulted on basis/precedence before standing resolves.

### `la_seam` (request) — capacity grant from Linear Accountant

- **Where:** `src/governor/linear_accountant_client.py::LinearAccountantClient.request_capacity`.
- **Gate name on receipt:** `la_seam`.
- **Positive receipt:** verdict `pass`; `la_outcome="Granted"` plus the token id. Emitted by `_emit_grant_receipt`.
- **Refusal kinds:** `capacity_refused` (LA `InsufficientCapacity` or `Denied`), plus pre-call `admission_denied` (no `admission_receipt_id`) and `dangling_receipt_reference` (admission_verifier returns False).
- **Parent linkage:** `evidence_bundle["parent_receipt_ids"] = [<wicket admission receipt id>]`.

### `la_seam` (consume) — linear spend

- **Where:** `src/governor/linear_accountant_client.py::LinearAccountantClient.consume`.
- **Gate name on receipt:** `la_seam`.
- **Positive receipt:** verdict `pass`; `la_outcome="Consumed"`. Emitted by `_emit_consume_receipt`.
- **Refusal kinds:** `already_consumed`, `capacity_refused`, `token_expired`, `token_revoked`, `unknown_token`, `scope_mismatch` — one closed kind per LA `ConsumptionDecision` failure variant (S4-lite ratification, codex adversarial nomenclature review).
- **Parent linkage:** `evidence_bundle["parent_receipt_ids"] = [<la grant receipt id>]`.
- **Linearity invariant:** the same `consumption_event_id` cited twice produces `Consumed` then `AlreadyConsumed`. The downstream effect counter increments only on `Consumed`. This is the demo's replay-kill (`tests/test_drill_runner_d0d1_scenarios.py::test_scenario_5_replay_budget_kills_second_consume`).

### `proposal_validator_seam` — citation guard

- **Where:** `src/governor/drill_runner.py::_validate_standing_citation` + `_emit_proposal_validator_refusal`.
- **Gate name on receipt:** `proposal_validator_seam`.
- **Positive receipt:** none. The happy path emits the proposal packet directly; the validator passes silently.
- **Refusal kinds:** `dangling_receipt_reference` only. Two failure modes distinguished by `evidence_bundle["citation_check"]`:
  - `existence` — cited id not present in the receipt store;
  - `kind_fit` — cited id exists but its structural kind (gate name + descriptive marker) does not match the slot.
- **Parent linkage:** `evidence_bundle["parent_receipt_ids"] = [<la consume receipt id>]`. The chain has already spent budget by the time the validator runs; failure is accounted.
- **Anti-pattern:** kind-fit is a **guard** against existing structural attributes (gate name + `verified_standing` marker), not a typed `ArtifactKind` / `UseKind` enum. See `memory/feedback_kind_fit_is_guard_not_enum.md` for the discipline.

### Accounted gap — `admission_gap_accounted`

When wicket admits with a gap, the chain **proceeds**. The proposal packet picks up two fields (`src/governor/drill_runner.py::build_proposal_packet` + `run_drill`):

- `gap_receipt_id` — the wicket admission receipt id citing the gap;
- `produced_under_gap = true`.

This is the only scenario in the closed gauntlet that demonstrates consequence-bearing work under acknowledged, receipted epistemic debt. The outcome class is `accounted_gap`, not `refused` and not `effect`. See `docs/reference/refusal-and-outcome-vocabulary.md` §accounted-gap.

## BA3 bypass — honest absence at the spine boundary

The four AG-internal BA3 surfaces (`RunBudgetLedger`, `ExecutionBudget`, `ExplorationBudget`, routing `Budget`) are **not** wired into the drill path. The poster renders them with `bypass_ag_rcpt_<not_minted>` placeholders so the absence is visible without fabricating a minted receipt. The contract is `SpendabilityAuthority: LA_ONLY` (per C0-resolved); any BA3 denial during a spine run fails the demo harness (`src/governor/drill_poster.py::_detect_ba3_denial_with_root`). Hard-shorting these surfaces to LA is post-MVP debt (`working/post-mvp-debt-ba3-hardshort-to-la.md`).

## LLM placement (verbatim from `working/campaign-standing-before-spendability.md` §3b)

**Per-run invocation:**

| Run | LLM invoked? | Why |
|-----|--------------|-----|
| 1. No standing | **No** | downstream call-count zero |
| 2. Standing expired | **No** | terminal lifecycle refusal |
| 3. Wicket denied | **No** | inadmissible basis |
| 4. Wicket gap accounted | **YES** (corrected from Maybe) | The point of `gap` vs `denied` is that gap proceeds. Proposal packet MUST carry the gap: *"produced under OPEN_FINDING_ACCOUNTED, gap receipt id X"*. Consequence-bearing work under acknowledged, receipted epistemic debt. Subtle showpiece — no other demo shows this. |
| 5. Replay / budget | **No on second spend** | spendability refusal; first spend was already accounted |
| 6. All green | **YES** | control group; happy-path proposal packet |
| 7. D3 confabulated receipt | Optional/adversarial (see two-mode below) | tiny adversarial review |

**Note on this MVP:** the drill runner (`src/governor/drill_runner.py`) does not invoke an LLM in any scenario, including runs 4 and 6. The proposal packet is a deterministic stub citing receipt ids (`build_proposal_packet`). The table above describes the **architectural placement** for when the LLM is wired in; the present MVP demonstrates the receipt chain that the LLM will be late and narrow against.

**The LLM must not be** (verbatim from §3b):

1. the origin of the finding
2. the standing decider
3. the wicket checker
4. the accountant
5. the validator of its own output
6. the mutator
7. the drill narrator (the transcript is a receipt render, deterministic from the ledger — never a model summary; narrative laundering at the presentation layer would undo every gate beneath it, invisibly)
8. its own retry authority (the runner owns re-invocation)
9. **the source of its own work** (added 2026-06-10). The LLM may propose edits within an operator-curated intent, but it must not mint new backlog items, expand its own mandate, or create follow-on work for other unattended agents. Agent-generated backlog consumed by other agents is slop recursion. Allowed work sources: operator-written notes, NQ findings, explicit watchbills, human-curated backlog items.

Each clause has a call-count assertion and a ledger entry behind it. Test surface: `tests/test_drill_runner_d0d1_scenarios.py`, `tests/test_drill_runner_d3_confabulation.py`.

**Directional custody (why these must-nots exist):** the rule under all
nine clauses is that a system which can act through gates must not
rewrite those gates while acting through them. Downstream capability
cannot mutate upstream authorization while inside the downstream flow.
The LLM, being the most downstream actor in the spine, is structurally
the highest-risk vector for that mutation; the must-nots enumerate the
specific upstream surfaces it must not reach back into. See
`working/directional-invariants.md` and `working/endgame-synthesis-2026-06-10.md`.

---

**Vocabulary note.** This doc uses internal/theoretical names (standing,
wicket admission, etc.) because those are the canonical forms in the
constellation's cross-tool vocabulary. Operator-facing surfaces (CLI
flags, dashboards, run books) may translate to ops-friendly handles
(e.g., `standing grant → action entitlement`). The living bilingual
glossary at `docs/reference/internal-ops-glossary.md` carries the
mapping. PROPOSED rows there are not yet binding on consumer-facing
surfaces; do not rename code or internal-doctrine documents from this
side.
