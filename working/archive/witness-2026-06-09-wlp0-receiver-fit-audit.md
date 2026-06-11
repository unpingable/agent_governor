# Witness: WLP0 — Receiver-Fit Audit

**Filed:** 2026-06-09. **Scope:** classification only. No code changes. No new receiver. No policy rule. No enforcement.

## Verdict

**C. Existing receiver consumes packet but ignores `unsettled`.**

With the additional clarification that the existing receiver consumes neither `receipt_references.governor_receipts` nor any Governor receipt content. The current Nightshift → Wicket → WLP → Continuity chain reads NS posture data (`closure_candidate`, `attention.*`, `posture_class`, `evidence_state`) but treats the new `unsettled` field as if it does not exist.

## Surfaces inspected

| # | Surface | Status |
|---|---|---|
| 1 | `~/git/scheduler/crates/nightshiftd/src/mvp_a.rs` (the Nightshift cross-component path: `cook_intent` → `wicket::check` → wrap as WLP `AuthorizationReceipt` → `wlp::handle`) | **consumes Packet; ignores `unsettled` and `governor_receipts`** |
| 2 | `~/git/wicket/src/` | no references to Nightshift Packet, `unsettled`, GateReceipt, or governor_receipts. Wicket is a generic admissibility kernel — it sees only the cooked Intent that the producer (NS) builds for it. |
| 3 | `~/git/wlp/src/` | same: no Nightshift Packet / unsettled / GateReceipt references. WLP wraps the Wicket Outcome into an `AuthorizationReceipt`/`HandlingReceipt` envelope; it has no per-system semantic awareness. |
| 4 | `~/git/wlp/examples/receiver_gate/` (fixture-local example: `receiver_gate.py`, `admission.py`, `wicket_policy.py`) | self-described as *"fixture-local, non-normative, not a SPEC promotion."* Consumes generic claim dicts with HMAC custody — not Nightshift Packets, not Governor GateReceipts. Different ontology. Counts as a candidate receiver pattern, not a current consumer of our surfaces. |
| 5 | `~/git/continuity/adapters/wlp.py` + tests | consumes WLP `HandlingReceipt` and `AuthorizationReceipt` artifacts (the wrapped output of step 1, NOT the Nightshift Packet directly). Persists them in SQLite with hash-match invariants. Does not gate, does not refuse, does not read `unsettled`. Grep for `unsettled\|GateReceipt\|governor_receipts` across the whole repo returns hits only in `docs/gaps/CROSS_ISLAND_BRIDGES_GAP.md` (a gap-doc reference, not code). |
| 6 | `~/git/wlp/WLP_RECEIVER_GATE_CANDIDATE.md` | doctrine candidate from 2026-06-01. Explicitly status `candidate / non-binding`. Names the lie-class (*"no receiver mutates state on an action-bearing claim unless the claim is attributable and carries the witness required by the receiver's admission policy"*) but does not couple to a specific Nightshift Packet field or Governor GateReceipt field. Not built; not wired into any of surfaces 1–5. |

## What the existing receiver (`mvp_a.rs`) actually reads from Packet

From the wrapped WLP `AuthorizationReceipt` sample at `~/git/continuity/tests/fixtures/ns_wlp_authorization_sample.json`, the `transition.payload` enumerates exactly what NS forwards:

- `ns_finding_key`, `ns_agenda_id`, `ns_packet_id`, `ns_run_id`
- `ns_closure_candidate`, `ns_attention_state`, `ns_posture_class`, `ns_evidence_state`
- `nq_content_hash`, `nq_claim`, `nq_subject`, `nq_evaluator`, `nq_cannot_testify`
- `wicket_*` (Outcome dimensions, reason codes, receipt hashes)

What is conspicuously absent:

- `ns_unsettled` — the packet's new `unsettled` summary
- `governor_receipt_ids` — the `receipt_references.governor_receipts: Vec<String>`
- any non-discharge / freshness / horizon-Defer signal

The packet's `unsettled` and `receipt_references.governor_receipts` exist in the Rust struct, render in YAML to the operator, and are written into the run-store — but they do not enter the cook → admit → wrap → persist pipeline that produces the cross-system warranted artifact.

## The downstream effect that would be authorized

If the receiver consumed `packet.unsettled`, the candidate effects (per the WLP_RECEIVER_GATE_CANDIDATE doctrine + the Nightshift cook discipline) are:

1. **Refuse to cook.** If `packet.unsettled` contains a `freshness` claim, the cook table maps the NS-classification-action to an Intent shape that requires a freshness witness. Since the Defer outcome explicitly says the freshness condition is *not settled*, the cook either:
   - returns `unsupported` (cook-table miss for the deferred shape), or
   - returns `refused` (witness requirement unmet)
2. **Forward as ns_unsettled in `transition.payload`.** If the cook proceeds, the persisted WLP `AuthorizationReceipt` could carry the unsettled summary as a first-class field, so Continuity-stored artifacts preserve "what this verdict did not settle" alongside what it settled.
3. **Refuse to wrap.** A receiver could refuse to mint the WLP `AuthorizationReceipt` at all when the packet carries an unresolved horizon condition (`unsettled[*].kind == freshness`). This is the strongest "receiver gate" shape from the candidate doc.

Effects 1 and 3 are governed: they authorize a refusal that prevents downstream reliance. Effect 2 is observational: it preserves the signal without changing what reliance is permitted.

## Nuance: the receiver_gate example is structurally aligned but ontologically detached

The WLP `examples/receiver_gate/` directory implements *exactly the shape* B1 needs — `ReceiverGate.handle(claim)` consults an `AdmissionPolicy`, returns a `HandlingReceipt { verdict, reason, mutated }`. But it consumes generic claim dicts with HMAC custody, not Nightshift Packet, not Governor GateReceipt. The receiver pattern exists; the wiring to our surfaces does not.

The shortest path from C to the next slice's "Receiver refuses or defers reliance on packet when unsettled contains freshness" is probably:

- An `mvp_a.rs`-level refusal: if `packet.unsettled` is non-empty and contains a `freshness` claim, return early with `NS_REFUSAL` before invoking `cook_intent`. The existing `maybe_run_mvp_a` already has a refusal-emit path (`schema: "ns.refusal.v1"`), so the wire shape exists.
- Add `ns_unsettled` to the cooked `transition.payload` for the non-refusal path so downstream Continuity artifacts carry the signal even when the cook proceeds.

That's the next slice's design space, not this slice's work.

## What this session did NOT do

- **Did not** change any code, schema, or test.
- **Did not** add a new receiver, policy rule, admission policy, or quarantine behavior.
- **Did not** propose `unsettled blocks closure` semantics. That's a governed effect; needs a receiver/effect pair, which is the next slice if opened.
- **Did not** inspect `Standing` or `Cadence` surfaces — out of scope for this audit's named targets (WLP / ReceiverGate / Wicket / Continuity / Nightshift packet consumers).
- **Did not** fix the pre-existing standing-validator bootstrap drift.

## Recommendation

C is confirmed. The receiver exists (`mvp_a.rs`), reads Packet, ignores `unsettled`. The receiver-gate doctrine candidate (`WLP_RECEIVER_GATE_CANDIDATE.md`) is on file; the shape to bind to is named; the wiring does not exist.

The next slice — if opened — should likely be scoped to `mvp_a.rs` only, since that is the *one and only* current consumer of `Packet` outside of the run-store and the YAML render to stdout. A "receiver refuses reliance on packet when unsettled contains freshness" rule landing in `mvp_a.rs` would close the C verdict without standing up a new receiver crate, without modifying WLP/Wicket/Continuity, and without widening any existing surface.

## Provenance

Filed 2026-06-09 after B1 landed (packet-side `unsettled` visibility). Read-only inspection across six surfaces in four repos (scheduler, wicket, wlp, continuity). Direct artifact reads:

- `~/git/scheduler/crates/nightshiftd/src/mvp_a.rs` (full receiver flow, including the `transition.payload` build site)
- `~/git/continuity/tests/fixtures/ns_wlp_authorization_sample.json` (live MVP-A run artifact, 2026-05-28)
- `~/git/wlp/examples/receiver_gate/README.md` + headers of `receiver_gate.py`, `admission.py`, `wicket_policy.py`
- `~/git/wlp/WLP_RECEIVER_GATE_CANDIDATE.md` (doctrine candidate)
- `~/git/continuity/tests/test_wlp_persistence_adapter.py` (consumer-side test surface)

Grep confirmation: `unsettled / GateReceipt / governor_receipts / NonDischarge` returns zero code-level hits in `~/git/wicket/src/`, `~/git/wlp/src/`, and `~/git/continuity/`. The single hit in Continuity is `docs/gaps/CROSS_ISLAND_BRIDGES_GAP.md`, a gap-document reference, not a code consumer.

No code changes. No tests added. Verdict is C; receiver site for next slice is `mvp_a.rs`.
