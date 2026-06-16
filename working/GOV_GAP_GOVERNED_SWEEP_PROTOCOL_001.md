# GOV_GAP_GOVERNED_SWEEP_PROTOCOL_001

## Title
Periodic sweeps may generate testimony and detect acceptance; they may not decide. A cron-driven discovery front-end for the governor loop, gated so automation can refresh evidence and stage candidates but never accept data or authorize implementation.

## Status
**Candidate — parked in `working/`, drafted 2026-06-12.** Design captured, **not authorized, not built.** Synthesized from a ChatGPT protocol sketch + Claude-Fable's three load-bearing seams + the operator's currency/claim-axis ruling. Explicit instruction: *design the protocol as docs; stop before wiring cron execution.* No implementation beyond docs unless clearly local-only and additive.

## Origin

Operator, 2026-06-12, after the NQ provenance/SILENCE batch: a periodic sweep could keep gap/doc/test/promotion state fresh, but cron must not become the decider. The governing line:

> **cron can generate testimony. governor can package it. human validates acceptance.**
> **Cron is a janitor with a watch.**

The chain this protects:

> observed → packeted → validated → accepted → executable

NOT: *"cron saw a thing, ship it"* — famous last words, carved into every outage report.

## The load-bearing invariant — currency axis ⊥ claim axis

This is the seam that, if collapsed, turns the refresh loop into silent claim mutation (the exact failure governance exists to refuse). Two **orthogonal** axes on any tracked item (edge / claim / gap / receipt):

```
claim axis:     documented | authorized | inferred | speculative
currency axis:  current | stale | contested | unreachable | superseded | pending_review
```

- A sweep may move an item **downward on the currency axis** (current → stale → contested → unreachable) — those are *observations* about whether the basis is still witnessed *as of now*. This is `unlinked_not_closed` applied to receipts: a dead source does **not** make a documented edge *not documented*; it makes it `documented(stale, last_verified=…)`.
- A sweep may **never** move an item on the **claim axis** (documented→authorized, retirement, new edge). That is promotion-class mutation → escrow → operator acceptance.

> **A sweep may say "this receipt was observed again" or "this receipt needs review." It may not say "therefore the claim changed."**

## The only autonomous write: observation-receipt append for no-op re-verification

The cron write boundary is not "no writes." It is exactly one class: **hash-identical re-verification appends an observation receipt** (re-fetched source, content hash identical → bump `observed` date, optionally a fresh archive snapshot). That adds evidence without changing any claim. Everything else emits a packet and stops.

Sweep diff-class taxonomy (the dispatch table):

| Sweep observation | Autonomous write? | Result |
|---|---|---|
| hash-identical re-fetch | **yes** | append observation receipt; bump verified date |
| source reachable, content drifted | no | escrow packet with the diff |
| source 404 / moved / unreachable | no | escrow packet; *proposed* currency downgrade |
| staleness-horizon breach | no (or an explicit **non-claim** `needs_reverify` marker if that marker is provably claim-inert) | escrow packet |
| new index/API hit (FR/SORN/etc.) | no | candidate packet only |
| new edge proposed | **absolutely not** | requires document examination + validation + operator acceptance |

### Indexed is not read (relay-as-witness)

The most dangerous class. An index/API hit testifies that a *document exists*; it does not testify that the document *supports the edge*. A candidate-edge packet must require its validation note to attest the document was **actually examined**, not merely detected. Otherwise the sweep is relay laundering with a search endpoint wearing a tiny robe.

## Three artifacts (typed authority, no collapsing)

1. **Sweep packet** — auto-generated. Facts, diffs, observed state, candidate conclusion. **No authority by itself.** Carries packet_sha256.
2. **Validation note** — model or human review. **Testimony, not acceptance.** Typed:
   ```yaml
   validation_note:
     authority_type: model_testimony | human_review | operator_review
     reviewer: claude-fable | chatgpt | operator
     supports: [...]
     objections: [...]
     document_examined: true   # required for candidate-edge class
   ```
3. **Acceptance receipt** — **operator-signed only.** Records who/scope/timestamp/packet_hash/validation_hash. Model validation notes are admissible *inputs* to acceptance; they are never acceptance themselves.
   ```yaml
   acceptance_receipt:
     authority_type: operator_acceptance
     accepted_by: operator
     packet: <id>
     packet_sha256: ...
     accepted_claims: [...]
     not_accepted: [...]     # the anti-footgun — see below
     scope: { ... }          # data-scoped, not ambient
   ```

No path where "interactive model validated it → ambient automation accepted it." That is two relays deep with zero witnesses wearing a receipt chain as a costume — the machine handing itself a little crown.

## Review escrow + acceptance horizon

**Review escrow.** A sweep places a packet in escrow; the loop may not *spend* it until an acceptance receipt exists.

```
packet_state: generated → reviewed → accepted → spent
                                  \→ rejected
                                  \→ superseded
```

**Acceptance horizon — acceptance is a bounded fuel cell, not a blessing.** A spent acceptance is not reusable forever:

```yaml
acceptance_horizon:
  expires_after: 30d
  invalidated_by:
    - touched_paths            # scoped artifacts changed
    - schema_version_change
    - doctrine_version_change
    - methodology_version_change   # for consumers whose "what counts as documented" is a versioned doc
    - failed_reproduction
```

## Scope is data-scoped, not ambient

`accepted: blackbox provenance` is a coupon for future crimes. The unit is consumer-native:
- code repos (governor, nq) → paths + the claim list.
- graph consumers (atlas) → `edge_ids` / `receipt_ids` / `case_ids`.

The **`not_accepted` field is the load-bearing anti-footgun**: it fences what acceptance does *not* cover (e.g. "additive queryability is accepted; changing series identity is NOT; public-release readiness is NOT"). Without it, acceptance silently widens.

## Two modes

- **Advisory sweep** — emit packets only (stale gaps, blocked Lane A items, doc/code mismatch, tests that flipped, candidate promotions). `… --mode advisory --emit packets/`.
- **Acceptance pickup** — ingest human-reviewed files, emit acceptance receipts. `… --inbox accepted/ --emit-receipts`.

## Composition with existing AG primitives

- **Loop protocol** — a sweep is a discovery front-end that **stops at REVIEW**. It never runs PLAN/DISPATCH on its own findings.
- **Standing Conditional Authorization** (`nq/docs/loop-protocol.md`, candidate for AG promotion) — this is its natural complement: a sweep packet needing acceptance *is* a Lane-B item awaiting operator authorization; the observation-receipt-only autonomous write *is* the SCA "local-only additive" class; escrow *is* the awaiting-authorization state. The sweep generates candidates; SCA governs what the loop may then spend without re-asking.
- **`capture.py`** (CaptureClassifier / CaptureReceipt — "detect structured intent in chat, stage for promotion") is the closest existing primitive; the sweep packet generalizes it from chat-intent to evidence-refresh.
- **Receipt kernel** — observation receipts are the append-only no-op-verification record.

## Consumers (named; not built here)

- **The governor's own loop** — refresh stale gaps / flipped tests / doc-code drift. Overlaps NQ's loop discipline but **not 1:1**.
- **NQ** — the cron→sweep→review→accept shape echoes NQ's witness/finding/acceptance discipline; a future NQ consumer would map onto its own grammar.
- **The atlas projects** (`grid-dependency-atlas` — substantially cooked; `intake-composition-atlas` — in progress) — the **strongest** consumer because the atlas already has receipt discipline for the sweep to hang off. Atlas-local invariants (captured here so the atlas can consume later; **atlas build is a separate session, out of scope for this gap**):
  - currency/claim axis split is the atlas's specific load-bearing invariant (above);
  - acceptance scope is `edge_ids`/`receipt_ids`/`case_ids`;
  - **surface currency state publicly** — an atlas about evidentiary composition must not present stale evidence as fresh; edges with packets in escrow render "verification pending / last verified …" (currency state only, not packet guts). An atlas that hid its own staleness would be a compact self-indictment.
  - `invalidated_by` includes `methodology_version_change` (METHODOLOGY.md changes what counts as documented).

## Non-goals (load-bearing)

- **Do NOT wire cron execution.** Design the protocol; stop before automation.
- Cron must not autonomously accept data or authorize implementation.
- No collapsing the currency axis into the claim axis.
- No ambient or model-only acceptance.
- No implementation beyond docs unless clearly local-only and additive.
- Not the atlas build (separate session).

## Acceptance criteria (for the eventual doc-design slice, when authorized)

1. Three schemas defined: sweep packet, validation note, acceptance receipt — with `packet_sha256`, typed `authority_type`, required `not_accepted`.
2. Packet lifecycle state machine (generated/reviewed/accepted/rejected/superseded/spent).
3. Currency-axis vs claim-axis separation written as an enforced invariant, with the autonomous-write taxonomy table.
4. `acceptance_horizon` invalidation rules incl. `doctrine_version_change` and `methodology_version_change`.
5. Two worked example packets: **blackbox-provenance-2026-06-12** and **SILENCE_UNIFICATION** (both from this session's NQ work — they are ready-made specimens).
6. Document-examined attestation required for candidate-edge packets (indexed≠read).
7. Stops before any cron-execution wiring.

## Open questions

1. Relationship to the loop REVIEW phase and `capture.py` — does the sweep packet subsume capture staging, or sit beside it?
2. Is a `needs_reverify` staleness marker ever truly claim-inert, or does any auto-marker risk being read as a claim signal? (Fable's "no-ish".)
3. One generalized scope-unit abstraction across consumers (paths vs edge/receipt IDs), or per-consumer scope schemas?
4. Does acceptance-receipt storage reuse the gate-receipt / receipt_v1 store, or a separate escrow store?

## The keeper

> **Acceptance is not a blessing. It is a bounded fuel cell.**
> **A sweep may refresh evidence or flag review. It may not change what a claim means.**
